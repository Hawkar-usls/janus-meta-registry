#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import importlib.util
import itertools
import json
import os
import subprocess
from pathlib import Path
from typing import Any

TARGET_MACHINE = (
    "PROVENANCE_CHAIN",
    "STATE_TRANSITION",
    "EXACT_VS_SEMANTIC_IDENTITY",
)
TARGET_TRIO = {"PALOMAR", "MUSIC", "GENESIS"}
MACHINE_ID = "EYE-R3-MACHINE-8d7ae222084e2017"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"MODULE_LOAD_FAILED:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git_first_added(root: Path, rel: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "log", "--diff-filter=A", "--follow", "--format=%aI", "--reverse", "--", rel],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip().splitlines()
        return out[0] if out else None
    except Exception:
        return None


def direct_lineage_refs(text: str) -> list[str]:
    try:
        obj = json.loads(text)
    except Exception:
        return []
    if not isinstance(obj, dict):
        return []
    keys = (
        "parent", "parents", "supersedes", "source_artifacts", "source_artifact",
        "input_artifacts", "input_artifact", "registry_parent", "receipt", "manifest",
    )
    refs: list[str] = []
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str):
            refs.append(value)
        elif isinstance(value, list):
            refs.extend(str(x) for x in value if isinstance(x, (str, int, float)))
    return sorted(set(refs))[:30]


def cross_domain_mentions(text: str, own_domain: str, r2: Any) -> dict[str, list[str]]:
    low = text.casefold()
    found: dict[str, list[str]] = {}
    for domain, needles in r2.DOMAIN_RULES:
        if domain == own_domain:
            continue
        hits = sorted({needle for needle in needles if str(needle).casefold() in low})
        if hits:
            found[domain] = hits[:12]
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--index", required=True)
    ap.add_argument("--catalog", default="EYE/r3/generated/EYE-R3-MACHINE-CATALOG.json")
    ap.add_argument("--output", default="EYE/r3_3/generated/EYE-R3.3-GOVERNANCE-KERNEL-AUDIT.json")
    ap.add_argument("--min-lineages", type=int, default=2)
    ap.add_argument("--max-support-docs", type=int, default=8)
    ap.add_argument("--max-read-bytes", type=int, default=800000)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    r2 = load_module(root / "EYE/r2/eye_r2_novel_bridge_miner.py", "eye_r2_r33")
    r31 = load_module(root / "EYE/r3_1/eye_r3_1_strict_order_gate.py", "eye_r31_r33")
    r3 = load_module(root / "EYE/r3/eye_r3_hidden_machine_miner.py", "eye_r3_r33")

    index = json.loads((root / args.index).read_text(encoding="utf-8"))
    catalog = json.loads((root / args.catalog).read_text(encoding="utf-8"))
    catalog_entry = next((m for m in catalog.get("machines", []) if m.get("machine_id") == MACHINE_ID), None)
    if catalog_entry is None:
        raise SystemExit("TARGET_MACHINE_NOT_IN_CATALOG")
    if tuple(catalog_entry.get("machine", [])) != TARGET_MACHINE:
        raise SystemExit("TARGET_MACHINE_SIGNATURE_DRIFT")
    catalog_domains = list(catalog_entry.get("domains", []))

    raw_support: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in index.get("records", []):
        if record.get("semantic_kind") not in {"JSON", "TEXT"} or record.get("parse_error"):
            continue
        rel = record["path"]
        text = r2.safe_text(root, rel, args.max_read_bytes)
        if not text:
            continue
        domain = r2.domain_for(rel, record.get("artifact_id"), record.get("title"))
        if domain not in catalog_domains:
            continue
        events: list[dict[str, Any]] = []
        for op_name, cfg in r2.OPERATORS.items():
            ev = r3.operator_event(text, cfg, 2)
            if ev is not None:
                events.append({"operator": op_name, **ev})
        events.sort(key=lambda e: (e["position"], e["operator"]))
        signatures = [sig for sig, _, _ in r3.machine_windows(events, 3, 5)] if len(events) >= 3 else []
        if TARGET_MACHINE not in signatures:
            continue
        raw_support[domain].append({
            "path": rel,
            "sha256": record.get("sha256"),
            "artifact_id": record.get("artifact_id"),
            "title": record.get("title"),
            "lineage": r2.lineage_key(record),
            "text": text,
        })

    alternates = [p for p in itertools.permutations(TARGET_MACHINE) if p != TARGET_MACHINE]
    domain_results: dict[str, Any] = {}
    strict_survivors: list[str] = []

    for domain in catalog_domains:
        docs = sorted(raw_support.get(domain, []), key=lambda d: (d["lineage"], d["path"]))
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()
        for doc in docs:
            if doc["lineage"] in seen:
                continue
            seen.add(doc["lineage"])
            selected.append(doc)
            if len(selected) >= args.max_support_docs:
                break

        actual_lineages: set[str] = set()
        alt_lineages: dict[tuple[str, ...], set[str]] = {p: set() for p in alternates}
        out_docs: list[dict[str, Any]] = []
        explicit_cross_refs = 0

        for doc in selected:
            witness = r31.ordered_witness(doc["text"], TARGET_MACHINE, r2.OPERATORS)
            if witness.get("passes"):
                actual_lineages.add(doc["lineage"])
            for alt in alternates:
                if r31.ordered_witness(doc["text"], alt, r2.OPERATORS).get("passes"):
                    alt_lineages[alt].add(doc["lineage"])
            mentions = cross_domain_mentions(doc["text"], domain, r2)
            if mentions:
                explicit_cross_refs += 1
            out_docs.append({
                "path": doc["path"],
                "sha256": doc["sha256"],
                "artifact_id": doc.get("artifact_id"),
                "lineage": doc["lineage"],
                "git_first_added_at": git_first_added(root, doc["path"]),
                "strict_order_witness": witness,
                "cross_domain_mentions_heuristic": mentions,
                "direct_lineage_refs": direct_lineage_refs(doc["text"]),
            })

        alt_counts = {" -> ".join(p): len(v) for p, v in alt_lineages.items()}
        best_alt = max(alt_counts.values(), default=0)
        strict_count = len(actual_lineages)
        strict_pass = strict_count >= args.min_lineages and strict_count > best_alt
        if strict_pass:
            strict_survivors.append(domain)
        domain_results[domain] = {
            "loose_r3_support_lineage_count": len({d["lineage"] for d in docs}),
            "sampled_unique_lineages": len(selected),
            "strict_actual_order_lineages": strict_count,
            "best_alternate_order_lineages": best_alt,
            "strict_order_pass": strict_pass,
            "support_docs_with_cross_domain_mentions": explicit_cross_refs,
            "alternate_order_counts": dict(sorted(alt_counts.items())),
            "support_documents": out_docs,
        }

    strict_set = set(strict_survivors)
    special_exclusive = bool(strict_set) and strict_set == TARGET_TRIO
    non_target_strict = sorted(strict_set - TARGET_TRIO)
    missing_target_strict = sorted(TARGET_TRIO - strict_set)

    if not strict_survivors:
        kernel_status = "NO_CROSS_DOMAIN_STRICT_ORDER_KERNEL_UNDER_R3_1_GATE"
    elif non_target_strict:
        kernel_status = "RECURRENT_KERNEL_EXTENDS_BEYOND_SPECIAL_TARGET_TRIO"
    elif special_exclusive:
        kernel_status = "STRICT_ORDER_CURRENTLY_TARGET_TRIO_ONLY__SEMANTIC_AND_ORIGIN_VERIFY_REQUIRED"
    else:
        kernel_status = "PARTIAL_TARGET_SUPPORT__OPEN"

    output = {
        "schema": "janus.eye.r3_3.governance_kernel_audit.v1",
        "artifact_id": "JANUS-EYE-R3.3-GOVERNANCE-KERNEL-AUDIT",
        "status": kernel_status,
        "source_git_commit": os.environ.get("GITHUB_SHA", "LOCAL_OR_UNKNOWN"),
        "source_index_corpus_digest_sha256": index.get("corpus_root_digest_sha256"),
        "machine_id": MACHINE_ID,
        "r3_operator_sequence": list(TARGET_MACHINE),
        "r3_2_functional_rebinding": ["SOURCE_BIND", "CONTROLLED_TRANSITION", "OUTPUT_IDENTITY_CEILING"],
        "catalog_domains": catalog_domains,
        "catalog_domain_count": len(catalog_domains),
        "strict_order_surviving_domains": sorted(strict_survivors),
        "strict_order_surviving_domain_count": len(strict_survivors),
        "non_target_strict_domains": non_target_strict,
        "missing_target_strict_domains": missing_target_strict,
        "special_palomar_music_genesis_exclusivity_under_strict_order": special_exclusive,
        "domain_results": domain_results,
        "origin_classification": {
            "artifact_lineage_independence": "MEASURED_PER_DOMAIN_BUT_NOT_SUFFICIENT",
            "conceptual_independence": "OPEN",
            "shared_governance_transfer": "PLAUSIBLE",
            "independent_reinvention": "PLAUSIBLE_BUT_NOT_ESTABLISHED",
            "reason": "All source artifacts are inside the JANUS ecosystem; distinct artifact lineages and chronological separation cannot by themselves exclude conceptual transfer or common authoring norms."
        },
        "method": {
            "catalog_target_bonus": False,
            "all_catalog_domains_enumerated": True,
            "loose_support_recomputed_from_fresh_index": True,
            "r3_1_strict_distinct_order_reapplied_to_all_catalog_domains": True,
            "all_alternate_permutations_used_as_controls": True,
            "cross_domain_mentions_are_heuristic_not_proof_of_transfer": True,
            "git_first_added_dates_are_chronology_not_causal_provenance": True,
        },
        "authority_firewall": [
            "STRICT_TEXT_ORDER != SEMANTIC_MACHINE",
            "ARTIFACT_LINEAGE_INDEPENDENCE != CONCEPTUAL_INDEPENDENCE",
            "NO_CROSS_REFERENCE != NO_TRANSFER",
            "CROSS_REFERENCE != MECHANISM_TRANSFER",
            "COMMON_KERNEL != SPECIAL_CONSTELLATION",
            "R3_3_AUTOMATION != INDEPENDENT_ORIGIN_PROOF"
        ],
        "next_gate": "Manually map the R3.2 functional roles in at least two strict-support lineages for every non-target surviving domain, then compare chronology and explicit transfer paths. If the kernel survives outside the special trio, demote the trio-specific constellation and treat the structure as a general JANUS governance kernel."
    }

    out = root / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": output["status"],
        "catalog_domains": output["catalog_domains"],
        "strict_survivors": output["strict_order_surviving_domains"],
        "non_target_strict": output["non_target_strict_domains"],
        "special_trio_exclusive": output["special_palomar_music_genesis_exclusivity_under_strict_order"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
