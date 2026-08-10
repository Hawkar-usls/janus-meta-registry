#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

REQ_HARDWARE = {
    "logical_ref_formid", "winning_file", "hardware_kind", "base_signature",
    "base_fixed_formid", "base_editorid", "base_name", "position_x", "position_y",
    "position_z", "initially_disabled", "enable_parent_raw", "owner_raw",
    "ref_script_raw", "base_script_raw", "full_path",
}
REQ_LINKS = {
    "owner_scope", "owner_kind", "owner_file", "owner_signature", "owner_formid",
    "owner_editorid", "owner_name", "element_path", "element_name", "element_value",
    "linked_file", "linked_signature", "linked_formid", "linked_editorid", "linked_name",
}
REQ_REVERSE = {
    "anchor_scope", "anchor_kind", "anchor_file", "anchor_signature", "anchor_formid",
    "anchor_editorid", "anchor_name", "referencing_file", "referencing_signature",
    "referencing_formid", "referencing_editorid", "referencing_name", "referencing_full_path",
}
REQ_SEMANTIC = {
    "record_file", "record_signature", "record_formid", "record_editorid", "record_name",
    "matched_term", "element_path", "element_name", "element_value", "linked_file",
    "linked_signature", "linked_formid", "linked_editorid", "record_full_path",
}

VISIONTRON_BASES = {"0002A45B", "000B364C", "000B06D4"}
COMPUTER_KINDS = {"TERMINAL", "COMPUTER_IDENTITY"}
MEMORY_TERMS = {"memory", "mem chip", "memory chip", "memchip", "neural", "archive", "persist", "restore", "reload", "snapshot", "storage", "buffer", "cache", "slot", "transfer", "serialize", "copy", "write"}
BACKEND_TERMS = {"think machine", "3600r", "visiontron", "sync", "synchron", "resident", "user unknown"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_tsv(path: Path) -> tuple[list[dict[str, str]], set[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return list(reader), set(reader.fieldnames or [])


def check_columns(actual: set[str], required: set[str], label: str) -> None:
    missing = sorted(required - actual)
    if missing:
        raise SystemExit(f"missing {label} columns: {missing}")


def norm(s: str) -> str:
    return " ".join(str(s or "").lower().split())


def pfloat(v: str, field: str) -> float:
    try:
        x = float(str(v).strip())
    except Exception as exc:
        raise ValueError(f"{field} must be numeric, got {v!r}") from exc
    if not math.isfinite(x):
        raise ValueError(f"{field} must be finite")
    return x


def xyz(row: dict[str, str]) -> tuple[float, float, float]:
    rid = row.get("logical_ref_formid", "?")
    return (
        pfloat(row.get("position_x", ""), f"{rid}.position_x"),
        pfloat(row.get("position_y", ""), f"{rid}.position_y"),
        pfloat(row.get("position_z", ""), f"{rid}.position_z"),
    )


def distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def row_key(file: str, sig: str, formid: str) -> str:
    return f"{file.strip()}|{sig.strip().upper()}|{formid.strip().upper()}"


def semantic_class(term: str) -> str:
    t = norm(term)
    if t in MEMORY_TERMS:
        return "MEMORY_OR_PERSISTENCE"
    if t in BACKEND_TERMS:
        return "BACKEND_OR_RESIDENT"
    return "OTHER"


def audit(hardware: list[dict[str, str]], links: list[dict[str, str]], reverse: list[dict[str, str]], semantic: list[dict[str, str]]) -> dict:
    if not hardware:
        raise ValueError("hardware export is empty")

    seen_refs = set()
    for row in hardware:
        rid = row.get("logical_ref_formid", "").strip().upper()
        if not rid:
            raise ValueError("hardware row missing logical_ref_formid")
        if rid in seen_refs:
            raise ValueError(f"duplicate hardware logical RefID: {rid}")
        seen_refs.add(rid)
        xyz(row)

    monitors = [r for r in hardware if r.get("hardware_kind") == "JAMES_MONITOR"]
    visiontrons = [r for r in hardware if r.get("hardware_kind") == "VISIONTRON"]
    computers = [r for r in hardware if r.get("hardware_kind") in COMPUTER_KINDS]

    for row in visiontrons:
        base = row.get("base_fixed_formid", "").strip().upper()
        if base not in VISIONTRON_BASES:
            raise ValueError(f"VISIONTRON row has unexpected base {base}")

    monitor_to_visiontron = []
    james_visiontron_ids: set[str] = set()
    for mon in monitors:
        ranked = sorted(
            ((distance(xyz(mon), xyz(v)), v) for v in visiontrons),
            key=lambda x: (x[0], x[1].get("logical_ref_formid", "")),
        )
        if not ranked:
            continue
        nearest_d, nearest = ranked[0]
        second_d = ranked[1][0] if len(ranked) > 1 else None
        tie = second_d is not None and abs(second_d - nearest_d) < 1e-6
        vid = nearest.get("logical_ref_formid", "").strip().upper()
        james_visiontron_ids.add(vid)
        monitor_to_visiontron.append({
            "monitor_refid": mon.get("logical_ref_formid"),
            "visiontron_refid": vid,
            "visiontron_base_formid": nearest.get("base_fixed_formid"),
            "distance_units": nearest_d,
            "second_nearest_distance_units": second_d,
            "exact_distance_tie": tie,
            "classification": "GEOMETRIC_JAMES_VISIONTRON_CANDIDATE",
            "functional_binding_proven": False,
        })

    # For every Visiontron, rank nearby terminal/computer-like hardware.
    lounger_shard_candidates = []
    nearest_base_counts = Counter()
    per_visiontron_nearest: dict[str, dict] = {}
    for v in visiontrons:
        ranked = sorted(
            ((distance(xyz(v), xyz(c)), c) for c in computers),
            key=lambda x: (x[0], x[1].get("logical_ref_formid", "")),
        )
        if not ranked:
            continue
        d, c = ranked[0]
        vid = v.get("logical_ref_formid", "").strip().upper()
        cid = c.get("logical_ref_formid", "").strip().upper()
        item = {
            "visiontron_refid": vid,
            "visiontron_base_formid": v.get("base_fixed_formid"),
            "candidate_refid": cid,
            "candidate_kind": c.get("hardware_kind"),
            "candidate_base_signature": c.get("base_signature"),
            "candidate_base_formid": c.get("base_fixed_formid"),
            "candidate_base_editorid": c.get("base_editorid"),
            "candidate_base_name": c.get("base_name"),
            "distance_units": d,
            "within_128": d <= 128.0,
            "within_512": d <= 512.0,
            "within_1024": d <= 1024.0,
            "classification": "NEAREST_COMPUTER_LIKE_LAYOUT_CANDIDATE",
            "functional_shard_binding_proven": False,
        }
        per_visiontron_nearest[vid] = item
        lounger_shard_candidates.append(item)
        nearest_base_counts[c.get("base_fixed_formid", "").strip().upper()] += 1

    for item in lounger_shard_candidates:
        base = item["candidate_base_formid"].strip().upper()
        item["same_base_nearest_for_visiontron_count"] = nearest_base_counts[base]
        item["repeated_layout_pattern"] = nearest_base_counts[base] >= 2

    james_shards = []
    for vid in sorted(james_visiontron_ids):
        if vid in per_visiontron_nearest:
            item = dict(per_visiontron_nearest[vid])
            item["classification"] = "JAMES_PER_LOUNGER_SHARD_LAYOUT_CANDIDATE"
            item["james_specific_backend_handle_proven"] = False
            james_shards.append(item)

    james_anchor_keys = set()
    for m in monitors:
        james_anchor_keys.add(row_key(m.get("winning_file", ""), "REFR", m.get("logical_ref_formid", "")))
        james_anchor_keys.add(row_key("Fallout3.esm", m.get("base_signature", ""), m.get("base_fixed_formid", "")))
    for v in visiontrons:
        if v.get("logical_ref_formid", "").strip().upper() in james_visiontron_ids:
            james_anchor_keys.add(row_key(v.get("winning_file", ""), "REFR", v.get("logical_ref_formid", "")))
            james_anchor_keys.add(row_key("Fallout3.esm", v.get("base_signature", ""), v.get("base_fixed_formid", "")))
    for s in james_shards:
        james_anchor_keys.add(row_key("Fallout3.esm", "REFR", s["candidate_refid"]))
        james_anchor_keys.add(row_key("Fallout3.esm", s["candidate_base_signature"], s["candidate_base_formid"]))

    # Direct linked-form evidence from hardware leaves.
    direct_link_candidates = []
    for row in links:
        owner_key = row_key(row.get("owner_file", ""), row.get("owner_signature", ""), row.get("owner_formid", ""))
        if owner_key not in james_anchor_keys:
            continue
        linked = row.get("linked_formid", "").strip().upper()
        if not linked:
            continue
        text = " ".join([row.get("element_name", ""), row.get("element_value", ""), row.get("linked_editorid", ""), row.get("linked_name", "")])
        term_hits = sorted({t for t in MEMORY_TERMS | BACKEND_TERMS if t in norm(text)})
        direct_link_candidates.append({
            "owner_key": owner_key,
            "owner_kind": row.get("owner_kind"),
            "owner_scope": row.get("owner_scope"),
            "element_path": row.get("element_path"),
            "linked_formid": linked,
            "linked_signature": row.get("linked_signature"),
            "linked_editorid": row.get("linked_editorid"),
            "linked_name": row.get("linked_name"),
            "semantic_terms": term_hits,
            "classification": "DIRECT_JAMES_BACKEND_LINK_CANDIDATE",
            "persistence_direction_proven": False,
        })

    # Reverse references to James anchors.
    reverse_by_record: dict[str, set[str]] = defaultdict(set)
    reverse_rows_by_key: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in reverse:
        anchor_key = row_key(row.get("anchor_file", ""), row.get("anchor_signature", ""), row.get("anchor_formid", ""))
        if anchor_key not in james_anchor_keys:
            continue
        ref_key = row_key(row.get("referencing_file", ""), row.get("referencing_signature", ""), row.get("referencing_formid", ""))
        reverse_by_record[ref_key].add(anchor_key)
        reverse_rows_by_key[ref_key].append(row)

    semantic_by_record: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in semantic:
        key = row_key(row.get("record_file", ""), row.get("record_signature", ""), row.get("record_formid", ""))
        semantic_by_record[key].append(row)

    source_bound_semantic = []
    for key in sorted(set(reverse_by_record) & set(semantic_by_record)):
        rows = semantic_by_record[key]
        classes = Counter(semantic_class(r.get("matched_term", "")) for r in rows)
        terms = sorted({norm(r.get("matched_term", "")) for r in rows})
        has_memory = any(t in MEMORY_TERMS for t in terms)
        has_backend = any(t in BACKEND_TERMS for t in terms)
        exemplar = rows[0]
        source_bound_semantic.append({
            "record_key": key,
            "record_editorid": exemplar.get("record_editorid"),
            "record_name": exemplar.get("record_name"),
            "semantic_terms": terms,
            "semantic_class_counts": dict(classes),
            "reverse_links_to_james_anchors": sorted(reverse_by_record[key]),
            "memory_or_persistence_term_present": has_memory,
            "backend_or_resident_term_present": has_backend,
            "classification": "SOURCE_BOUND_BACKEND_STATE_CANDIDATE",
            "james_specific_persisted_state_proven": False,
        })

    high_priority = [x for x in source_bound_semantic if x["memory_or_persistence_term_present"]]

    # A stronger structural candidate exists when James's nearest computer-like object
    # repeats as the nearest same base around multiple Visiontrons. This still does not
    # prove functional wiring, but it is a useful per-lounger-shard signature.
    repeated_james_shards = [x for x in james_shards if x.get("repeated_layout_pattern") and x.get("within_1024")]

    return {
        "schema": "janus.fo3.vault112_per_lounger_backend_shard_audit.v2_0",
        "hardware_row_count": len(hardware),
        "james_monitor_ref_count": len(monitors),
        "visiontron_ref_count": len(visiontrons),
        "computer_like_ref_count": len(computers),
        "monitor_to_visiontron_candidates": monitor_to_visiontron,
        "lounger_nearest_computer_candidates": lounger_shard_candidates,
        "james_per_lounger_shard_candidates": james_shards,
        "james_repeated_layout_shard_candidate_count": len(repeated_james_shards),
        "james_repeated_layout_shard_candidates": repeated_james_shards,
        "direct_james_backend_link_candidate_count": len(direct_link_candidates),
        "direct_james_backend_link_candidates": direct_link_candidates,
        "source_bound_backend_state_candidate_count": len(source_bound_semantic),
        "source_bound_backend_state_candidates": source_bound_semantic,
        "high_priority_memory_persistence_candidate_count": len(high_priority),
        "high_priority_memory_persistence_candidates": high_priority,
        "admission": {
            "lounger23_monitor_is_dynamic_memory_store": False,
            "james_visiontron_geometric_candidate_bound": bool(monitor_to_visiontron),
            "per_lounger_repeated_hardware_pattern_detected_for_james": bool(repeated_james_shards),
            "james_specific_backend_handle": "NOT_ESTABLISHED_BY_LAYOUT_OR_REFERENCE_GRAPH_ALONE",
            "james_specific_persisted_memory_state": "NOT_ESTABLISHED",
            "james_specific_removable_memory_carrier": "NOT_ESTABLISHED",
            "persisted_james_memory_state_reconstruction": "BLOCKED_PENDING_PRIMARY_SEMANTIC_BINDING",
        },
        "claim_ceiling": {
            "NEAREST_MONITOR_TO_VISIONTRON_EQUALS_FUNCTIONAL_BINDING": False,
            "NEAREST_COMPUTER_TO_VISIONTRON_EQUALS_PER_LOUNGER_SHARD": False,
            "REPEATED_LAYOUT_EQUALS_FUNCTIONAL_WIRING": False,
            "DIRECT_LINK_EQUALS_PERSISTENCE_DIRECTION": False,
            "REVERSE_REFERENCE_EQUALS_STATE_OWNERSHIP": False,
            "MEMORY_TERM_EQUALS_AUTOBIOGRAPHICAL_MEMORY_PAYLOAD": False,
            "THINK_MACHINE_SHARED_BACKEND_EQUALS_SHARED_MEMORY_BUFFER": False,
            "HIGH_PRIORITY_CANDIDATE_EQUALS_PASS": False,
            "manual_primary_record_review_required": True,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hardware", required=True, type=Path)
    ap.add_argument("--links", required=True, type=Path)
    ap.add_argument("--reverse", required=True, type=Path)
    ap.add_argument("--semantic", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    hardware, hc = read_tsv(args.hardware)
    links, lc = read_tsv(args.links)
    reverse, rc = read_tsv(args.reverse)
    semantic, sc = read_tsv(args.semantic)
    check_columns(hc, REQ_HARDWARE, "hardware")
    check_columns(lc, REQ_LINKS, "links")
    check_columns(rc, REQ_REVERSE, "reverse")
    check_columns(sc, REQ_SEMANTIC, "semantic")

    result = audit(hardware, links, reverse, semantic)
    result["source_binding"] = {
        "hardware_sha256": sha256(args.hardware),
        "hardware_links_sha256": sha256(args.links),
        "hardware_reverse_refs_sha256": sha256(args.reverse),
        "backend_semantic_candidates_sha256": sha256(args.semantic),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
