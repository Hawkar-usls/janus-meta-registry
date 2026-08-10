#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict, Counter
from pathlib import Path

SOURCE_TERMS = {
    "mq04doc", "vault112podtermdad", "mq04statusnotedad", "mq04stressnotedad",
}
ADMIN_TERMS = {"braun", "vault112", "vault 112", "user unknown"}
MEMORY_TERMS = {"memory", "neural", "engram"}
CARRIER_TERMS = {"mem chip", "memory chip", "memchip", "neuralizer"}
OPERATION_TERMS = {
    "copy", "write", "rewrite", "export", "transfer", "overwrite", "serialize", "persist", "backup",
}
INVENTORY_TERMS = {"additem", "removeitem", "removeallitems"}
CONTROL_TERMS = {"moveto", "enable", "disable"}
EXEC_SIGNATURES = {"SCPT", "INFO", "QUST", "TERM"}

REQUIRED_CANDIDATE_COLUMNS = {
    "record_file", "record_signature", "record_formid", "root_fixed_formid",
    "record_editorid", "record_name", "matched_keyword", "element_path",
    "element_value", "is_seed_record", "seed_label", "record_full_path",
}
REQUIRED_REVERSE_COLUMNS = {
    "seed_fixed_formid", "seed_label", "seed_file", "seed_signature",
    "referencing_file", "referencing_signature", "referencing_formid",
    "referencing_editorid", "referencing_name", "referencing_full_path",
}

JAMES_SEEDS = {
    "Vault112PodTermDad", "MQ04StressNoteDad", "MQ04StatusNoteDad", "MQ04Doc", "MQ04DocRef", "MQ04DadPodScript",
}
ADMIN_SEEDS = {"MQ04Script", "BettyScript", "MQ04VersionControlCurrent", "MQ04FailsafeTerminalVersionControlSubMenu"}
CARRIER_SEEDS = {"MS08PinkertonLog1", "MS08PinkertonLog2", "MS08PinkertonLog3"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_tsv(path: Path) -> tuple[list[dict[str, str]], set[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = list(reader)
        return rows, set(reader.fieldnames or [])


def category(term: str) -> str:
    t = term.strip().lower()
    if t in SOURCE_TERMS:
        return "JAMES_SOURCE"
    if t in CARRIER_TERMS:
        return "CARRIER"
    if t in OPERATION_TERMS:
        return "OPERATION"
    if t in INVENTORY_TERMS:
        return "INVENTORY_TRANSFER"
    if t in MEMORY_TERMS:
        return "MEMORY"
    if t in ADMIN_TERMS:
        return "BRAUN_ADMIN"
    if t in CONTROL_TERMS:
        return "CONTROL"
    return "OTHER"


def record_key(row: dict[str, str]) -> str:
    return "|".join([
        row.get("record_file", ""),
        row.get("record_signature", ""),
        row.get("record_formid", ""),
    ])


def is_script_surface(row: dict[str, str]) -> bool:
    sig = row.get("record_signature", "").upper()
    path = row.get("element_path", "").lower()
    return sig in EXEC_SIGNATURES or "sctx" in path or "script" in path or "result" in path


def audit(candidate_rows: list[dict[str, str]], reverse_rows: list[dict[str, str]]) -> dict:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in candidate_rows:
        if not row.get("record_formid", "").strip():
            raise ValueError("candidate row missing record_formid")
        term = row.get("matched_keyword", "").strip().lower()
        if not term:
            raise ValueError("candidate row missing matched_keyword")
        grouped[record_key(row)].append(row)

    reverse_by_seed: dict[str, list[dict[str, str]]] = defaultdict(list)
    reverse_by_record: dict[str, set[str]] = defaultdict(set)
    for row in reverse_rows:
        label = row.get("seed_label", "").strip()
        if not label:
            raise ValueError("reverse row missing seed_label")
        reverse_by_seed[label].append(row)
        rkey = "|".join([
            row.get("referencing_file", ""),
            row.get("referencing_signature", ""),
            row.get("referencing_formid", ""),
        ])
        reverse_by_record[rkey].add(label)

    records = []
    category_counts = Counter()
    convergence_counts = Counter()
    high_priority = []

    for key, rows in grouped.items():
        cats = {category(r.get("matched_keyword", "")) for r in rows}
        for c in cats:
            category_counts[c] += 1
        terms = sorted({r.get("matched_keyword", "").strip().lower() for r in rows})
        script_hits = [r for r in rows if is_script_surface(r)]
        seed_links = sorted(reverse_by_record.get(key, set()))
        source_bound = bool(cats & {"JAMES_SOURCE"}) or bool(set(seed_links) & JAMES_SEEDS)
        admin_bound = bool(cats & {"BRAUN_ADMIN"}) or bool(set(seed_links) & ADMIN_SEEDS)
        carrier_bound = bool(cats & {"CARRIER"}) or bool(set(seed_links) & CARRIER_SEEDS)
        memory_bound = "MEMORY" in cats
        operation_bound = bool(cats & {"OPERATION", "INVENTORY_TRANSFER"})
        executable_candidate = bool(script_hits) and operation_bound

        convergence = []
        if source_bound and memory_bound:
            convergence.append("SOURCE+MEMORY")
        if memory_bound and carrier_bound:
            convergence.append("MEMORY+CARRIER")
        if source_bound and operation_bound:
            convergence.append("SOURCE+OPERATION")
        if source_bound and carrier_bound:
            convergence.append("SOURCE+CARRIER")
        if source_bound and carrier_bound and operation_bound:
            convergence.append("SOURCE+CARRIER+OPERATION")
        if source_bound and admin_bound and carrier_bound and operation_bound:
            convergence.append("SOURCE+ADMIN+CARRIER+OPERATION")
        for c in convergence:
            convergence_counts[c] += 1

        exemplar = rows[0]
        item = {
            "record_key": key,
            "record_file": exemplar.get("record_file"),
            "record_signature": exemplar.get("record_signature"),
            "record_formid": exemplar.get("record_formid"),
            "record_editorid": exemplar.get("record_editorid"),
            "record_name": exemplar.get("record_name"),
            "matched_terms": terms,
            "categories": sorted(cats),
            "seed_reverse_links": seed_links,
            "script_surface_hit_count": len(script_hits),
            "source_bound_candidate": source_bound,
            "admin_bound_candidate": admin_bound,
            "carrier_bound_candidate": carrier_bound,
            "memory_bound_candidate": memory_bound,
            "operation_bound_candidate": operation_bound,
            "executable_surface_candidate": executable_candidate,
            "convergence": convergence,
            "manual_review_required": bool(convergence or executable_candidate or seed_links),
            "direct_james_to_carrier_write_edge_proven": False,
        }
        records.append(item)
        if "SOURCE+CARRIER+OPERATION" in convergence or "SOURCE+ADMIN+CARRIER+OPERATION" in convergence:
            high_priority.append(item)

    reverse_counts = {label: len(rows) for label, rows in sorted(reverse_by_seed.items())}
    missing_seed_groups = {
        "james": sorted(JAMES_SEEDS - set(reverse_by_seed)),
        "admin": sorted(ADMIN_SEEDS - set(reverse_by_seed)),
        "carrier": sorted(CARRIER_SEEDS - set(reverse_by_seed)),
    }

    return {
        "schema": "janus.fo3.braun_privileged_memory_bridge_audit.v1_3",
        "candidate_hit_count": len(candidate_rows),
        "candidate_record_count": len(grouped),
        "reverse_reference_edge_count": len(reverse_rows),
        "category_record_counts": dict(category_counts),
        "convergence_record_counts": dict(convergence_counts),
        "high_priority_bridge_candidate_count": len(high_priority),
        "high_priority_bridge_candidates": high_priority,
        "records": records,
        "seed_reverse_reference_counts": reverse_counts,
        "seeds_without_exported_official_reverse_refs": missing_seed_groups,
        "admission": {
            "james_specific_source_binding": "INPUT_FROM_PRIOR_GATE_NOT_REPROVED_BY_LEXICAL_AUDIT",
            "memory_to_physical_carrier_class_exists": "INPUT_FROM_PRIOR_PINKERTON_EVIDENCE_NOT_REPROVED_BY_LEXICAL_AUDIT",
            "direct_james_selected_memory_to_carrier_write_edge": "NOT_ESTABLISHED_BY_DISCOVERY_HITS_ALONE",
            "asset_level_executable_save_james": "BLOCKED_UNLESS_MANUAL_PRIMARY_RECORD_REVIEW_ESTABLISHES_EXECUTABLE_SEMANTICS",
        },
        "claim_ceiling": {
            "keyword_hit_is_executable_edge": False,
            "same_record_term_convergence_is_executable_edge": False,
            "reverse_reference_is_write_direction": False,
            "script_surface_keyword_is_semantic_write_proof": False,
            "high_priority_candidate_is_pass": False,
            "unknown_user_equals_james": False,
            "direct_james_to_carrier_write_edge_proven": False,
            "manual_primary_record_review_required": True,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", required=True, type=Path)
    ap.add_argument("--reverse", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    candidates, ccols = read_tsv(args.candidates)
    reverse, rcols = read_tsv(args.reverse)
    mc = sorted(REQUIRED_CANDIDATE_COLUMNS - ccols)
    mr = sorted(REQUIRED_REVERSE_COLUMNS - rcols)
    if mc:
        raise SystemExit(f"missing candidate columns: {mc}")
    if mr:
        raise SystemExit(f"missing reverse columns: {mr}")

    result = audit(candidates, reverse)
    result["source_binding"] = {
        "candidate_tsv_sha256": sha256(args.candidates),
        "seed_reverse_refs_tsv_sha256": sha256(args.reverse),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
