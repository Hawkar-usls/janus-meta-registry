#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import importlib.util
import itertools
import json
import os
import statistics
from pathlib import Path
from typing import Any


def load_r2(root: Path):
    path = root / "EYE/r2/eye_r2_novel_bridge_miner.py"
    spec = importlib.util.spec_from_file_location("eye_r2_novel_bridge_miner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("R2_MODULE_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def all_positions(text: str, needle: str) -> list[int]:
    low = text.casefold()
    n = needle.casefold()
    out: list[int] = []
    start = 0
    while True:
        pos = low.find(n, start)
        if pos < 0:
            break
        out.append(pos)
        start = pos + max(1, len(n))
    return out


def strictly_increasing(xs: list[float]) -> bool:
    return all(a < b for a, b in zip(xs, xs[1:]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--target", default="EYE/r3/generated/EYE-R3-PALOMAR-MUSIC-GENESIS-CONSTELLATION.json")
    ap.add_argument("--output", default="EYE/r3/generated/EYE-R3-STRICT-ORDER-VERIFICATION.json")
    ap.add_argument("--max-read-bytes", type=int, default=800000)
    ap.add_argument("--max-signal-owners", type=int, default=1)
    ap.add_argument("--min-distinctive-signals", type=int, default=2)
    ap.add_argument("--min-lineages-per-domain", type=int, default=2)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    target_path = root / args.target
    target = json.loads(target_path.read_text(encoding="utf-8"))
    r2 = load_r2(root)

    signal_owners: dict[str, set[str]] = collections.defaultdict(set)
    for op, cfg in r2.OPERATORS.items():
        for signal in cfg.get("signals", ()):
            signal_owners[str(signal).casefold()].add(op)

    candidates_out: list[dict[str, Any]] = []
    survivors: list[str] = []

    for cand in target.get("candidates", []):
        machine = tuple(cand["machine"])
        permutations = list(itertools.permutations(machine))
        per_domain: dict[str, Any] = {}
        candidate_pass = True

        for domain in cand.get("domains", []):
            docs_out: list[dict[str, Any]] = []
            order_counts: collections.Counter[tuple[str, ...]] = collections.Counter()
            actual_pass_lineages: set[str] = set()

            for doc in cand.get("provenance", {}).get(domain, []):
                rel = doc["path"]
                text = r2.safe_text(root, rel, args.max_read_bytes)
                op_anchors: dict[str, Any] = {}
                anchors: list[float] = []
                all_ops_anchored = True

                for op in machine:
                    cfg = r2.OPERATORS[op]
                    distinctive = []
                    for signal in cfg.get("signals", ()):
                        s = str(signal).casefold()
                        if len(signal_owners[s]) > args.max_signal_owners:
                            continue
                        positions = all_positions(text, str(signal))
                        if positions:
                            distinctive.append((str(signal), positions[0]))
                    if len(distinctive) < args.min_distinctive_signals:
                        all_ops_anchored = False
                        op_anchors[op] = {
                            "status": "INSUFFICIENT_DISTINCTIVE_SIGNAL",
                            "distinctive_hits": [s for s, _ in distinctive],
                            "required": args.min_distinctive_signals,
                        }
                        continue
                    pos_values = [p for _, p in distinctive]
                    median_pos = float(statistics.median(pos_values))
                    norm = median_pos / max(1, len(text.casefold()))
                    anchors.append(norm)
                    op_anchors[op] = {
                        "status": "ANCHORED",
                        "distinctive_hits": [s for s, _ in distinctive],
                        "first_positions": {s: p for s, p in distinctive},
                        "median_anchor": round(norm, 8),
                    }

                observed_order: list[str] | None = None
                strict_actual = False
                if all_ops_anchored:
                    observed_order = sorted(machine, key=lambda op: op_anchors[op]["median_anchor"])
                    observed_tuple = tuple(observed_order)
                    order_counts[observed_tuple] += 1
                    strict_actual = observed_tuple == machine and strictly_increasing(
                        [op_anchors[op]["median_anchor"] for op in machine]
                    )
                    if strict_actual:
                        actual_pass_lineages.add(doc["lineage"])

                docs_out.append({
                    "path": rel,
                    "lineage": doc["lineage"],
                    "all_operators_distinctively_anchored": all_ops_anchored,
                    "observed_order": observed_order,
                    "strict_actual_order_pass": strict_actual,
                    "operator_anchors": op_anchors,
                })

            alt = {
                " -> ".join(p): order_counts[p]
                for p in permutations
                if p != machine and order_counts[p] > 0
            }
            actual_support = len(actual_pass_lineages)
            max_alt_support = max(alt.values(), default=0)
            domain_pass = actual_support >= args.min_lineages_per_domain and actual_support > max_alt_support
            candidate_pass = candidate_pass and domain_pass
            per_domain[domain] = {
                "actual_order": " -> ".join(machine),
                "actual_order_unique_lineage_support": actual_support,
                "minimum_required": args.min_lineages_per_domain,
                "max_reordered_control_support": max_alt_support,
                "reordered_control_support": dict(sorted(alt.items())),
                "strict_domain_pass": domain_pass,
                "documents": docs_out,
            }

        status = "STRICT_ORDER_SURVIVES" if candidate_pass else "REJECTED_BY_STRICT_ORDER_GATE"
        if candidate_pass:
            survivors.append(cand["candidate_id"])
        candidates_out.append({
            "candidate_id": cand["candidate_id"],
            "machine": list(machine),
            "automatic_score": cand.get("score"),
            "automatic_confidence_class": cand.get("confidence_class"),
            "strict_status": status,
            "per_domain": per_domain,
        })

    output = {
        "schema": "janus.eye.r3.strict_order_verification.v1",
        "artifact_id": "JANUS-EYE-R3-STRICT-ORDER-VERIFICATION",
        "status": "PASS_SURVIVORS_REQUIRE_MANUAL_SEMANTIC_VERIFY" if survivors else "NULL_ALL_TARGET_CANDIDATES_REJECTED_BY_STRICT_ORDER",
        "source_git_commit": os.environ.get("GITHUB_SHA", "LOCAL_OR_UNKNOWN"),
        "target_source": args.target,
        "method": {
            "shared_signal_decontamination": True,
            "signal_owner_ceiling": args.max_signal_owners,
            "minimum_distinctive_signals_per_operator_per_document": args.min_distinctive_signals,
            "anchor": "median of first occurrences of operator-exclusive signals",
            "equal_or_nonincreasing_anchors_allowed": False,
            "minimum_unique_lineages_per_domain": args.min_lineages_per_domain,
            "reordered_permutation_controls": True,
            "domain_rule": "actual-order unique-lineage support >= minimum AND > strongest reordered control support",
        },
        "candidate_count": len(candidates_out),
        "survivor_count": len(survivors),
        "survivor_ids": survivors,
        "candidates": candidates_out,
        "authority": "STRICT_ORDER_SURVIVAL_IS_NOT_SEMANTIC_MACHINE_PROOF__MANUAL_INPUT_STATE_OUTPUT_VERIFY_STILL_REQUIRED",
        "firewalls": [
            "CO_OCCURRENCE != ORDER",
            "LEXICAL_TIE_BREAK != MACHINE_SEQUENCE",
            "SHARED_SIGNAL != OPERATOR_IDENTITY",
            "STRICT_ORDER != SHARED_CAUSE",
            "VERIFY_DECIDES"
        ],
    }

    out = root / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": output["status"],
        "candidate_count": output["candidate_count"],
        "survivor_count": output["survivor_count"],
        "survivor_ids": output["survivor_ids"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
