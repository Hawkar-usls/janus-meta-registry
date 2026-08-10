#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

TARGET_KINDS = {"TEDDY", "GNOME_GENERIC", "GNOME_INTACT", "GNOME_DAMAGED"}
REQUIRED_LIFECYCLE_COLUMNS = {
    "logical_ref_formid", "target_kind", "origin_record_file", "winning_record_file",
    "winning_record_formid", "base_file", "base_formid", "base_editorid",
    "location_key", "location_editorid", "position_x", "position_y", "position_z",
    "initially_disabled", "persistent", "override_count", "enable_parent_reference_raw",
    "enable_parent_flags_raw", "owner_raw", "ref_script_raw", "base_script_raw",
    "direct_reverse_reference_count", "full_path",
}
REQUIRED_REVERSE_COLUMNS = {
    "target_logical_ref_formid", "target_kind", "referencing_file",
    "referencing_signature", "referencing_formid", "referencing_editorid",
    "referencing_name", "referencing_full_path",
}


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


def parse_bool(value: str, field: str) -> bool:
    v = str(value).strip().lower()
    if v == "true":
        return True
    if v == "false":
        return False
    raise ValueError(f"{field} must be true/false, got {value!r}")


def parse_int(value: str, field: str) -> int:
    try:
        return int(str(value).strip())
    except Exception as exc:
        raise ValueError(f"{field} must be an integer: {value!r}") from exc


def parse_float(value: str, field: str) -> float:
    try:
        n = float(str(value).strip())
    except Exception as exc:
        raise ValueError(f"{field} must be numeric: {value!r}") from exc
    if not math.isfinite(n):
        raise ValueError(f"{field} must be finite: {value!r}")
    return n


def audit(lifecycle_rows: list[dict[str, str]], reverse_rows: list[dict[str, str]]) -> dict:
    if not lifecycle_rows:
        raise ValueError("lifecycle export contains no target rows")

    ids: set[str] = set()
    by_kind = Counter()
    by_plugin = Counter()
    direct_dynamic = []
    direct_quiet = []
    reverse_by_target: dict[str, list[dict[str, str]]] = defaultdict(list)

    for rr in reverse_rows:
        tid = rr.get("target_logical_ref_formid", "").strip().upper()
        if not tid:
            raise ValueError("reverse-reference row missing target_logical_ref_formid")
        if rr.get("target_kind") not in TARGET_KINDS:
            raise ValueError(f"unexpected reverse target kind: {rr.get('target_kind')}")
        reverse_by_target[tid].append(rr)

    for row in lifecycle_rows:
        rid = row.get("logical_ref_formid", "").strip().upper()
        if not rid:
            raise ValueError("lifecycle row missing logical_ref_formid")
        if rid in ids:
            raise ValueError(f"duplicate logical target REFR: {rid}")
        ids.add(rid)

        kind = row.get("target_kind", "")
        if kind not in TARGET_KINDS:
            raise ValueError(f"unexpected target kind: {kind}")
        by_kind[kind] += 1
        by_plugin[row.get("winning_record_file", "")] += 1

        if not row.get("location_key", "").strip():
            raise ValueError(f"missing canonical location_key for {rid}")
        for axis in ("position_x", "position_y", "position_z"):
            parse_float(row.get(axis, ""), f"{rid}.{axis}")
        initially_disabled = parse_bool(row.get("initially_disabled", ""), f"{rid}.initially_disabled")
        parse_bool(row.get("persistent", ""), f"{rid}.persistent")
        override_count = parse_int(row.get("override_count", ""), f"{rid}.override_count")
        reverse_count = parse_int(row.get("direct_reverse_reference_count", ""), f"{rid}.direct_reverse_reference_count")
        if override_count < 0 or reverse_count < 0:
            raise ValueError(f"negative count for {rid}")
        if reverse_count < len(reverse_by_target.get(rid, [])):
            raise ValueError(f"official reverse-reference export exceeds xEdit count for {rid}")

        markers = []
        if initially_disabled:
            markers.append("INITIALLY_DISABLED")
        if row.get("enable_parent_reference_raw", "").strip():
            markers.append("ENABLE_PARENT")
        if row.get("ref_script_raw", "").strip():
            markers.append("REF_SCRIPT")
        if row.get("base_script_raw", "").strip():
            markers.append("BASE_SCRIPT")
        if reverse_by_target.get(rid):
            markers.append("OFFICIAL_REVERSE_REFERENCES")

        item = {
            "logical_ref_formid": rid,
            "target_kind": kind,
            "winning_record_file": row.get("winning_record_file"),
            "location_key": row.get("location_key"),
            "direct_dynamic_or_dependency_markers": markers,
            "official_reverse_reference_count": len(reverse_by_target.get(rid, [])),
            "initially_disabled": initially_disabled,
            "enable_parent_reference_raw": row.get("enable_parent_reference_raw", ""),
            "ref_script_raw": row.get("ref_script_raw", ""),
            "base_script_raw": row.get("base_script_raw", ""),
        }
        if markers:
            direct_dynamic.append(item)
        else:
            direct_quiet.append(item)

    dangling = sorted(set(reverse_by_target) - ids)
    if dangling:
        raise ValueError(f"reverse-reference rows point to absent lifecycle targets: {dangling[:5]}")

    return {
        "schema": "janus.bear.scene_lifecycle.audit.v4_7",
        "target_count": len(lifecycle_rows),
        "target_by_kind": dict(by_kind),
        "target_by_winning_plugin": dict(by_plugin),
        "official_reverse_reference_edge_count": len(reverse_rows),
        "direct_dependency_marker_target_count": len(direct_dynamic),
        "direct_quiet_target_count": len(direct_quiet),
        "direct_dependency_marker_targets": direct_dynamic,
        "direct_quiet_targets": direct_quiet,
        "claim_ceiling": {
            "exact_refid_population_bound": True,
            "direct_xesp_script_reverse_ref_markers_audited": True,
            "direct_quiet_means_static_lifecycle_proven": False,
            "absence_of_reverse_refs_proves_no_external_runtime_mutation": False,
            "pre_james_b_access_proves_pre_james_b_object_lifecycle": False,
            "temporal_falsification_requires_manual_source_bound_lifecycle_decision": True,
            "james_or_james_b_placement_proven": False,
        },
        "admission_semantics": {
            "DIRECT_DEPENDENCY_MARKER": "The placed REFR has at least one direct lifecycle/dependency signal requiring scene-specific review.",
            "DIRECT_QUIET": "No exported direct marker was found. This is a static-lifecycle candidate only, not proof that no quest or runtime path can affect the scene.",
            "TEMPORAL_FALSIFIER": "May be asserted only after exact RefID, reverse-reference review, direct lifecycle fields and vanilla observation order are source-bound together."
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lifecycle", required=True, type=Path)
    ap.add_argument("--reverse", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    lifecycle_rows, lifecycle_cols = read_tsv(args.lifecycle)
    reverse_rows, reverse_cols = read_tsv(args.reverse)
    missing_lifecycle = sorted(REQUIRED_LIFECYCLE_COLUMNS - lifecycle_cols)
    missing_reverse = sorted(REQUIRED_REVERSE_COLUMNS - reverse_cols)
    if missing_lifecycle:
        raise SystemExit(f"missing lifecycle columns: {missing_lifecycle}")
    if missing_reverse:
        raise SystemExit(f"missing reverse-reference columns: {missing_reverse}")

    result = audit(lifecycle_rows, reverse_rows)
    result["source_binding"] = {
        "lifecycle_tsv_sha256": sha256(args.lifecycle),
        "reverse_refs_tsv_sha256": sha256(args.reverse),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
