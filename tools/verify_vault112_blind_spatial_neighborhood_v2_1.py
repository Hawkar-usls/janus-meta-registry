#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

REQ = {
    "logical_ref_formid", "winning_file", "base_signature", "base_fixed_formid",
    "base_editorid", "base_name", "ref_editorid", "ref_name", "position_x",
    "position_y", "position_z", "initially_disabled", "enable_parent_raw",
    "owner_raw", "ref_script_raw", "base_script_raw", "base_model_raw", "full_path",
}

VISIONTRON_BASES = {"0002A45B", "000B364C", "000B06D4"}
JAMES_MONITOR_BASE = "00031190"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_tsv(path: Path) -> tuple[list[dict[str, str]], set[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f, delimiter="\t")
        return list(r), set(r.fieldnames or [])


def check_columns(actual: set[str]) -> None:
    missing = sorted(REQ - actual)
    if missing:
        raise ValueError(f"missing columns: {missing}")


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


def formid(row: dict[str, str], field: str = "logical_ref_formid") -> str:
    return str(row.get(field, "")).strip().upper()


def row_summary(row: dict[str, str]) -> dict:
    return {
        "refid": formid(row),
        "base_signature": str(row.get("base_signature", "")).strip().upper(),
        "base_formid": formid(row, "base_fixed_formid"),
        "base_editorid": row.get("base_editorid", ""),
        "base_name": row.get("base_name", ""),
        "ref_editorid": row.get("ref_editorid", ""),
        "ref_name": row.get("ref_name", ""),
        "base_model_raw": row.get("base_model_raw", ""),
        "initially_disabled": row.get("initially_disabled", ""),
        "enable_parent_raw": row.get("enable_parent_raw", ""),
        "owner_raw": row.get("owner_raw", ""),
        "ref_script_raw": row.get("ref_script_raw", ""),
        "base_script_raw": row.get("base_script_raw", ""),
    }


def audit(rows: list[dict[str, str]], *, top_n: int = 32, radius: float = 1024.0) -> dict:
    if not rows:
        raise ValueError("all-refs export is empty")
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("radius must be finite and positive")

    seen: set[str] = set()
    for row in rows:
        rid = formid(row)
        if not rid:
            raise ValueError("row missing logical_ref_formid")
        if rid in seen:
            raise ValueError(f"duplicate logical RefID: {rid}")
        seen.add(rid)
        xyz(row)

    monitors = [r for r in rows if formid(r, "base_fixed_formid") == JAMES_MONITOR_BASE]
    visiontrons = [r for r in rows if formid(r, "base_fixed_formid") in VISIONTRON_BASES]

    monitor_to_visiontron = []
    james_visiontron_ids: set[str] = set()
    for mon in monitors:
        ranked = sorted(
            ((distance(xyz(mon), xyz(v)), v) for v in visiontrons),
            key=lambda x: (x[0], formid(x[1])),
        )
        if not ranked:
            continue
        d, nearest = ranked[0]
        second = ranked[1][0] if len(ranked) > 1 else None
        tie = second is not None and abs(second - d) < 1e-6
        vid = formid(nearest)
        james_visiontron_ids.add(vid)
        monitor_to_visiontron.append({
            "monitor_refid": formid(mon),
            "visiontron_refid": vid,
            "distance_units": d,
            "second_nearest_distance_units": second,
            "exact_distance_tie": tie,
            "classification": "GEOMETRIC_JAMES_VISIONTRON_CANDIDATE",
            "functional_binding_proven": False,
        })

    neighbors_by_visiontron: dict[str, list[dict]] = {formid(v): [] for v in visiontrons}
    base_to_visiontrons: dict[str, set[str]] = defaultdict(set)
    blind_rows = []

    # Assign every non-Visiontron reference to its uniquely nearest Visiontron first.
    # This prevents one placed object from being counted as a local shard for two
    # loungers merely because both are inside a broad radius.
    visiontron_ids = {formid(v) for v in visiontrons}
    for candidate in rows:
        cid = formid(candidate)
        if cid in visiontron_ids:
            continue
        ranked_v = sorted(
            ((distance(xyz(candidate), xyz(v)), v) for v in visiontrons),
            key=lambda x: (x[0], formid(x[1])),
        )
        if not ranked_v:
            continue
        d, nearest_v = ranked_v[0]
        second = ranked_v[1][0] if len(ranked_v) > 1 else None
        tie = second is not None and abs(second - d) < 1e-6
        if d > radius:
            continue
        vid = formid(nearest_v)
        summary = row_summary(candidate)
        summary.update({
            "visiontron_refid": vid,
            "distance_units": d,
            "second_nearest_visiontron_distance_units": second,
            "nearest_visiontron_tie": tie,
            "within_64": d <= 64.0,
            "within_128": d <= 128.0,
            "within_256": d <= 256.0,
            "within_512": d <= 512.0,
            "within_1024": d <= 1024.0,
            "semantic_preclassification_used": False,
            "classification": "BLIND_SPATIAL_AMBIGUOUS_NEIGHBOR" if tie else "BLIND_SPATIAL_NEIGHBOR",
            "functional_binding_proven": False,
        })
        neighbors_by_visiontron.setdefault(vid, []).append(summary)

    # Rank only after unique-nearest assignment. Tied refs remain visible but do
    # not contribute to repeated per-lounger base patterns.
    for vid, items in neighbors_by_visiontron.items():
        items.sort(key=lambda x: (x["distance_units"], x["refid"]))
        kept = items[:top_n]
        neighbors_by_visiontron[vid] = kept
        for rank, summary in enumerate(kept, 1):
            summary["rank"] = rank
            blind_rows.append(summary)
            base = summary["base_formid"]
            if base and not summary["nearest_visiontron_tie"]:
                base_to_visiontrons[base].add(vid)

    base_exemplars: dict[str, dict] = {}
    for item in blind_rows:
        base = item["base_formid"]
        if base and base not in base_exemplars:
            base_exemplars[base] = item

    repeated = []
    for base, vids in sorted(base_to_visiontrons.items()):
        if len(vids) < 2:
            continue
        ex = base_exemplars[base]
        repeated.append({
            "base_formid": base,
            "base_signature": ex["base_signature"],
            "base_editorid": ex["base_editorid"],
            "base_name": ex["base_name"],
            "base_model_raw": ex["base_model_raw"],
            "visiontron_count": len(vids),
            "visiontron_refids": sorted(vids),
            "unnamed_base": not (str(ex["base_editorid"]).strip() or str(ex["base_name"]).strip()),
            "classification": "REPEATED_BLIND_NEIGHBOR_BASE_CANDIDATE",
            "functional_shard_binding_proven": False,
        })
    repeated.sort(key=lambda x: (-x["visiontron_count"], x["base_formid"]))

    james_neighbors = []
    repeated_bases = {x["base_formid"] for x in repeated}
    for vid in sorted(james_visiontron_ids):
        for item in neighbors_by_visiontron.get(vid, []):
            x = dict(item)
            x["repeated_across_visiontrons"] = x["base_formid"] in repeated_bases
            x["classification"] = (
                "JAMES_REPEATED_BLIND_SHARD_CANDIDATE"
                if x["repeated_across_visiontrons"]
                else "JAMES_BLIND_NEIGHBOR_CANDIDATE"
            )
            x["james_specific_backend_handle_proven"] = False
            james_neighbors.append(x)

    unnamed_repeated = [x for x in repeated if x["unnamed_base"]]
    james_repeated = [x for x in james_neighbors if x["repeated_across_visiontrons"]]

    return {
        "schema": "janus.fo3.vault112_blind_spatial_neighborhood_audit.v2_1",
        "all_ref_row_count": len(rows),
        "james_monitor_ref_count": len(monitors),
        "visiontron_ref_count": len(visiontrons),
        "monitor_to_visiontron_candidates": monitor_to_visiontron,
        "neighbor_radius_units": radius,
        "neighbors_per_visiontron_limit": top_n,
        "blind_neighbor_row_count": len(blind_rows),
        "repeated_blind_neighbor_base_candidate_count": len(repeated),
        "repeated_blind_neighbor_base_candidates": repeated,
        "unnamed_repeated_base_candidate_count": len(unnamed_repeated),
        "unnamed_repeated_base_candidates": unnamed_repeated,
        "james_blind_neighbor_candidate_count": len(james_neighbors),
        "james_blind_neighbor_candidates": james_neighbors,
        "james_repeated_blind_candidate_count": len(james_repeated),
        "james_repeated_blind_candidates": james_repeated,
        "admission": {
            "name_based_hardware_filter_removed": True,
            "all_vault112a_refr_export_required": True,
            "unnamed_generic_local_shard_can_be_discovered": True,
            "james_specific_backend_handle": "NOT_ESTABLISHED_BY_PROXIMITY",
            "james_specific_persisted_memory_state": "NOT_ESTABLISHED",
            "persisted_james_state_candidate": "BLOCKED_PENDING_REAL_ESM_AND_PRIMARY_BINDING",
        },
        "claim_ceiling": {
            "NEAREST_OBJECT_EQUALS_FUNCTIONAL_SHARD": False,
            "REPEATED_BASE_EQUALS_FUNCTIONAL_WIRING": False,
            "UNNAMED_REPEATED_BASE_EQUALS_BACKEND": False,
            "PROXIMITY_EQUALS_STATE_OWNERSHIP": False,
            "SPATIAL_PATTERN_EQUALS_MEMORY_PERSISTENCE": False,
            "JAMES_NEIGHBOR_EQUALS_JAMES_STORAGE": False,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("all_refs_tsv", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--top-n", type=int, default=32)
    ap.add_argument("--radius", type=float, default=1024.0)
    args = ap.parse_args()

    rows, cols = read_tsv(args.all_refs_tsv)
    check_columns(cols)
    result = audit(rows, top_n=args.top_n, radius=args.radius)
    result["input"] = {"path": str(args.all_refs_tsv), "sha256": sha256(args.all_refs_tsv)}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
