#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

CRYSTAL_BASES = {
    "0000A9E9": "SMALL_ALIEN_CRYSTAL",
    "0000A9E6": "LARGE_ALIEN_CRYSTAL",
}

TECH_TERMS = (
    "console", "terminal", "control", "panel", "robot", "drone", "assembly",
    "machine", "mechanism", "device", "imager", "archway", "teleport",
    "matrix", "generator", "reactor", "workbench", "switch",
)


def norm(s: str) -> str:
    s = s.strip().upper().replace("0X", "")
    return s.zfill(8) if s else ""


def fnum(row, key):
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return None


def dist(a, b):
    av = [fnum(a, k) for k in ("position_x", "position_y", "position_z")]
    bv = [fnum(b, k) for k in ("position_x", "position_y", "position_z")]
    if any(v is None for v in av + bv):
        return None
    return math.dist(av, bv)


def load(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def is_crystal(row):
    return norm(row.get("base_formid", "")) in CRYSTAL_BASES


def is_tech(row):
    # Critical anti-correlation boundary: a crystal must never classify itself
    # as a technology candidate, and a location name such as "Robot Assembly"
    # must not turn every object in that cell into a machine.
    if is_crystal(row):
        return False
    text = " ".join(
        row.get(k, "") for k in (
            "record_editorid", "base_editorid", "base_name",
        )
    ).lower()
    return any(term in text for term in TECH_TERMS)


def analyze(rows):
    zeta = [r for r in rows if r.get("record_file", "").lower() == "zeta.esm"]
    crystals = [r for r in zeta if is_crystal(r)]
    tech = [r for r in zeta if is_tech(r)]

    by_location = Counter(r.get("parent_cell_or_world", "") for r in crystals)
    by_kind = Counter(CRYSTAL_BASES[norm(r["base_formid"])] for r in crystals)

    nearest = []
    for c in crystals:
        same_cell = [
            t for t in tech
            if t.get("parent_cell_or_world", "") == c.get("parent_cell_or_world", "")
            and t.get("record_formid") != c.get("record_formid")
        ]
        candidates = []
        for t in same_cell:
            d = dist(c, t)
            if d is not None:
                candidates.append((d, t))
        candidates.sort(key=lambda x: x[0])
        nearest.append({
            "crystal_ref": c.get("record_formid"),
            "crystal_kind": CRYSTAL_BASES[norm(c["base_formid"])],
            "location": c.get("parent_cell_or_world", ""),
            "nearest_tech": [
                {
                    "distance_units": round(d, 3),
                    "record_formid": t.get("record_formid"),
                    "base_editorid": t.get("base_editorid"),
                    "base_name": t.get("base_name"),
                }
                for d, t in candidates[:5]
            ],
        })

    return {
        "schema": "janus.zeta_crystal_colocation_receipt.v1",
        "crystal_reference_count": len(crystals),
        "crystal_kind_counts": dict(by_kind),
        "crystal_location_counts": dict(by_location),
        "tech_candidate_reference_count": len(tech),
        "nearest_tech_by_crystal": nearest,
        "claim_ceiling": {
            "colocation_measured": bool(crystals),
            "crystal_function_proven": False,
            "flash_memory_proven": False,
            "component_or_material_hypothesis": "RANKABLE_AFTER_REAL_ESM_EXPORT_NOT_ADMITTED_BY_COLOCATION_ALONE",
        },
        "invariants": {
            "COLOCATION_DOES_NOT_PROVE_FUNCTION": True,
            "NO_DATA_STORAGE_CLAIM_WITHOUT_USE_EDGE": True,
            "CRYSTAL_NEVER_COUNTS_AS_ITS_OWN_TECH_CANDIDATE": True,
            "CELL_NAME_NEVER_CLASSIFIES_ALL_CONTENTS_AS_TECH": True,
        },
    }


def main():
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


if __name__ == "__main__":
    main()
