#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
from typing import Any

SCHEMA = "janus.eye.r3_1.strict_order_gate.v1"


def load_r2(root: Path):
    path = root / "EYE/r2/eye_r2_novel_bridge_miner.py"
    spec = importlib.util.spec_from_file_location("eye_r2_novel_bridge_miner_r31", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("R3_1_R2_MODULE_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def earliest_anchor(text: str, signals: tuple[str, ...] | list[str]) -> tuple[int, str] | None:
    low = text.casefold()
    hits: list[tuple[int, str]] = []
    for signal in signals:
        s = str(signal).casefold()
        pos = low.find(s)
        if pos >= 0:
            hits.append((pos, str(signal)))
    if not hits:
        return None
    hits.sort(key=lambda x: (x[0], x[1].casefold()))
    return hits[0]


def ordered_witness(text: str, machine: tuple[str, ...], operators: dict[str, dict[str, Any]]) -> dict[str, Any]:
    anchors: list[dict[str, Any]] = []
    for op in machine:
        cfg = operators[op]
        hit = earliest_anchor(text, cfg.get("signals", ()))
        if hit is None:
            return {
                "passes": False,
                "reason": "OPERATOR_SIGNAL_MISSING",
                "missing_operator": op,
                "anchors": anchors,
            }
        pos, token = hit
        anchors.append({"operator": op, "position": pos, "anchor": token})
    positions = [a["position"] for a in anchors]
    anchor_tokens = [a["anchor"].casefold() for a in anchors]
    strict = all(positions[i] < positions[i + 1] for i in range(len(positions) - 1))
    distinct_tokens = len(set(anchor_tokens)) == len(anchor_tokens)
    if not strict:
        reason = "POSITION_TIE_OR_WRONG_ORDER"
    elif not distinct_tokens:
        reason = "NON_DISTINCT_EARLIEST_ANCHORS"
    else:
        reason = "STRICT_DISTINCT_ORDER"
    return {
        "passes": bool(strict and distinct_tokens),
        "reason": reason,
        "anchors": anchors,
        "strict_positions": strict,
        "distinct_anchor_tokens": distinct_tokens,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--target", default="EYE/r3/generated/EYE-R3-PALOMAR-MUSIC-GENESIS-CONSTELLATION.json")
    ap.add_argument("--output", default="EYE/r3_1/generated/EYE-R3.1-STRICT-ORDER-GATE-RECEIPT.json")
    ap.add_argument("--min-lineages", type=int, default=2)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    r2 = load_r2(root)
    target_path = root / args.target
    target = json.loads(target_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []

    for candidate in target.get("candidates", []):
        machine = tuple(candidate["machine"])
        alternates = [p for p in itertools.permutations(machine) if p != machine]
        domain_results: dict[str, Any] = {}
        source_drift: list[dict[str, str]] = []

        for domain, docs in sorted(candidate["provenance"].items()):
            strict_lineages: set[str] = set()
            strict_docs: list[dict[str, Any]] = []
            rejected_docs: list[dict[str, Any]] = []
            alt_lineages: dict[tuple[str, ...], set[str]] = {p: set() for p in alternates}

            for doc in docs:
                rel = doc["path"]
                path = root / rel
                if not path.is_file():
                    source_drift.append({"path": rel, "reason": "SOURCE_MISSING"})
                    continue
                data = path.read_bytes()
                actual_sha = sha256_bytes(data)
                expected_sha = doc["sha256"]
                if actual_sha != expected_sha:
                    source_drift.append({
                        "path": rel,
                        "reason": "SHA256_DRIFT",
                        "expected_sha256": expected_sha,
                        "actual_sha256": actual_sha,
                    })
                    continue
                text = data.decode("utf-8", errors="replace")
                witness = ordered_witness(text, machine, r2.OPERATORS)
                witness_record = {
                    "path": rel,
                    "sha256": actual_sha,
                    "lineage": doc["lineage"],
                    "witness": witness,
                }
                if witness["passes"]:
                    strict_lineages.add(doc["lineage"])
                    strict_docs.append(witness_record)
                else:
                    rejected_docs.append(witness_record)

                for alt in alternates:
                    alt_witness = ordered_witness(text, alt, r2.OPERATORS)
                    if alt_witness["passes"]:
                        alt_lineages[alt].add(doc["lineage"])

            alt_counts = {
                " -> ".join(alt): len(lineages)
                for alt, lineages in sorted(alt_lineages.items(), key=lambda kv: tuple(kv[0]))
            }
            best_alt = max(alt_counts.values(), default=0)
            candidate_count = len(strict_lineages)
            domain_results[domain] = {
                "candidate_strict_independent_lineages": candidate_count,
                "minimum_required": args.min_lineages,
                "best_alternate_permutation_independent_lineages": best_alt,
                "candidate_order_beats_all_alternates": candidate_count > best_alt,
                "alternate_permutation_counts": alt_counts,
                "strict_support_documents": strict_docs,
                "rejected_support_documents": rejected_docs,
            }

        if source_drift:
            verdict = "SOURCE_DRIFT_BLOCKED"
        else:
            enough = all(v["candidate_strict_independent_lineages"] >= args.min_lineages for v in domain_results.values())
            beats = all(v["candidate_order_beats_all_alternates"] for v in domain_results.values())
            if enough and beats and len(domain_results) >= 3:
                verdict = "STRICT_ORDER_PASS__MECHANISM_VERIFY_STILL_REQUIRED"
            elif enough and not beats:
                verdict = "ORDER_CONTROL_FAIL"
            else:
                verdict = "INSUFFICIENT_STRICT_ORDER_SUPPORT"

        results.append({
            "candidate_id": candidate["candidate_id"],
            "machine": list(machine),
            "r3_score": candidate.get("score"),
            "r3_confidence_class": candidate.get("confidence_class"),
            "r3_1_verdict": verdict,
            "source_drift": source_drift,
            "domains": domain_results,
            "claim_ceiling": "SOURCE_GROUNDED_DISCRIMINATING_TEXTUAL_ORDER_ONLY__NOT_CAUSAL_MECHANISM_PROOF",
        })

    verdict_counts: dict[str, int] = {}
    for r in results:
        verdict_counts[r["r3_1_verdict"]] = verdict_counts.get(r["r3_1_verdict"], 0) + 1
    passing = [r for r in results if r["r3_1_verdict"] == "STRICT_ORDER_PASS__MECHANISM_VERIFY_STILL_REQUIRED"]

    receipt = {
        "schema": SCHEMA,
        "artifact_id": "JANUS-EYE-R3.1-STRICT-ORDER-GATE-RECEIPT",
        "status": "PASS_WITH_SURVIVING_STRICT_ORDER_CANDIDATES" if passing else "OPEN_NO_STRICT_ORDER_SURVIVORS",
        "source_git_commit": os.environ.get("GITHUB_SHA", "LOCAL_OR_UNKNOWN"),
        "input_target_artifact": args.target,
        "input_target_sha256": sha256_bytes(target_path.read_bytes()),
        "target_domains": target.get("domains", ["PALOMAR", "MUSIC", "GENESIS"]),
        "named_target_bonus": False,
        "requirements": {
            "source_sha256_matches_r3_provenance": True,
            "strictly_increasing_earliest_operator_positions": True,
            "distinct_earliest_anchor_tokens": True,
            "minimum_independent_strict_order_lineages_per_domain": args.min_lineages,
            "candidate_order_must_beat_every_alternate_permutation_in_each_domain": True,
        },
        "candidate_count": len(results),
        "verdict_counts": dict(sorted(verdict_counts.items())),
        "surviving_candidate_ids": [r["candidate_id"] for r in passing],
        "results": results,
        "authority_firewall": [
            "TEXTUAL_ORDER != CAUSAL_ORDER",
            "STRICT_ORDER_PASS != MECHANISM_PROOF",
            "R3_1_PASS != INDEPENDENT_REPLICATION",
            "VERIFY_DECIDES",
        ],
        "next_gate": "For each survivor, manually/semantically map input state -> transformation -> output state and use held-out domain-specific controls. Do not promote to mechanism identity from textual order alone.",
        "seal": "UNTIE THE STARS BEFORE CALLING THEM A CONSTELLATION."
    }

    out = root / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": receipt["status"],
        "candidate_count": len(results),
        "survivors": len(passing),
        "surviving_candidate_ids": receipt["surviving_candidate_ids"],
        "receipt_sha256": sha256_bytes(out.read_bytes()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
