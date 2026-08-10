#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

SKELETON_KINDS = {
    "SKELETON_CLOTHES",
    "SKELETON_RAGS",
    "SKELETON_MALE",
    "SKELETON_FEMALE",
}
GNOME_KINDS = {"GNOME_GENERIC", "GNOME_INTACT"}


def load(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def fnum(row: dict[str, str], key: str):
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return None


def distance(a: dict[str, str], b: dict[str, str]):
    av = [fnum(a, k) for k in ("position_x", "position_y", "position_z")]
    bv = [fnum(b, k) for k in ("position_x", "position_y", "position_z")]
    if any(v is None for v in av + bv):
        return None
    return math.dist(av, bv)


def distance_bucket(d):
    if d is None:
        return "POSITION_UNAVAILABLE"
    if d <= 128:
        return "TIGHT"
    if d <= 512:
        return "NEAR"
    return "SAME_CELL"


def nearest_for(teddy, candidates):
    same_location = [
        x for x in candidates
        if x.get("location_key", "")
        and x.get("location_key", "") == teddy.get("location_key", "")
        and x.get("record_formid", "") != teddy.get("record_formid", "")
    ]
    measured = []
    for candidate in same_location:
        d = distance(teddy, candidate)
        if d is not None:
            measured.append((d, candidate))
    measured.sort(key=lambda x: x[0])
    if not measured:
        return None
    d, row = measured[0]
    return {
        "record_formid": row.get("record_formid"),
        "target_kind": row.get("target_kind"),
        "distance_units": round(d, 3),
        "bucket": distance_bucket(d),
        "record_file": row.get("record_file"),
        "full_path": row.get("full_path"),
    }


def analyze(rows: list[dict[str, str]]) -> dict:
    teddies = [r for r in rows if r.get("target_kind") == "TEDDY"]
    skeletons = [r for r in rows if r.get("target_kind") in SKELETON_KINDS]
    gnomes = [r for r in rows if r.get("target_kind") in GNOME_KINDS]

    teddy_rows = []
    skeleton_bucket_counts = Counter()
    locations_with_teddy = Counter()

    for teddy in teddies:
        nearest_skeleton = nearest_for(teddy, skeletons)
        nearest_gnome = nearest_for(teddy, gnomes)
        if nearest_skeleton:
            skeleton_bucket_counts[nearest_skeleton["bucket"]] += 1
        else:
            skeleton_bucket_counts["NO_SKELETON_IN_LOCATION"] += 1
        locations_with_teddy[teddy.get("location_key", "")] += 1
        teddy_rows.append({
            "teddy_ref": teddy.get("record_formid"),
            "record_file": teddy.get("record_file"),
            "location_key": teddy.get("location_key"),
            "initially_disabled": teddy.get("initially_disabled"),
            "deleted": teddy.get("deleted"),
            "full_path": teddy.get("full_path"),
            "nearest_skeleton": nearest_skeleton,
            "nearest_gnome": nearest_gnome,
        })

    close_teddies = sum(
        skeleton_bucket_counts[k] for k in ("TIGHT", "NEAR")
    )

    return {
        "schema": "janus.fo3_teddy_skeleton_proximity_receipt.v1",
        "reference_counts": {
            "teddy": len(teddies),
            "skeleton": len(skeletons),
            "tracked_gnome": len(gnomes),
        },
        "teddy_skeleton_bucket_counts": dict(skeleton_bucket_counts),
        "teddies_with_skeleton_within_512": close_teddies,
        "teddy_locations": dict(locations_with_teddy),
        "teddy_receipts": teddy_rows,
        "claim_ceiling": {
            "spatial_recurrence_measured": bool(teddies),
            "specific_scene_authorship_proven_by_distance": False,
            "single_in_world_placer_proven": False,
            "supernatural_mobility_proven": False,
            "environmental_storytelling_hypothesis": "RANKABLE_WITH_REFERENCE_DATA_AND_MANUAL_SCENE_BINDING",
        },
        "invariants": {
            "PROXIMITY_DOES_NOT_PROVE_OWNERSHIP": True,
            "PROXIMITY_DOES_NOT_IDENTIFY_PLACER": True,
            "DIFFERENT_LOCATION_KEYS_NEVER_PAIR": True,
            "GNOME_IS_NOT_SKELETON": True,
            "TEDDY_CANNOT_PAIR_WITH_ITSELF": True,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    result = analyze(load(args.tsv))
    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
