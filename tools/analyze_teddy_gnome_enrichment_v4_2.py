#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "tools/analyze_teddy_gnome_enrichment.py"

_spec = importlib.util.spec_from_file_location("janus_bear_base_v4_0", BASE_PATH)
base = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(base)


def hypergeom_pmf(x: int, population: int, success_positions: int, draws: int) -> float:
    if population < 0 or success_positions < 0 or draws < 0:
        return 0.0
    if success_positions > population or draws > population:
        return 0.0
    lo = max(0, draws - (population - success_positions))
    hi = min(draws, success_positions)
    if x < lo or x > hi:
        return 0.0
    den = math.comb(population, draws)
    if den == 0:
        return 0.0
    return (
        math.comb(success_positions, x)
        * math.comb(population - success_positions, draws - x)
        / den
    )


def convolve_distributions(a: dict[int, float], b: dict[int, float]) -> dict[int, float]:
    out: dict[int, float] = defaultdict(float)
    for xa, pa in a.items():
        for xb, pb in b.items():
            out[xa + xb] += pa * pb
    return dict(out)


def exact_cell_stratified_enrichment(teddies, controls, skeletons, threshold: float) -> dict:
    locations = sorted(
        {
            r.get("location_key", "")
            for r in [*teddies, *controls]
            if r.get("location_key", "")
        }
    )

    combined = {0: 1.0}
    observed_total = 0
    strata = []

    for loc in locations:
        ts = [r for r in teddies if r.get("location_key") == loc]
        cs = [r for r in controls if r.get("location_key") == loc]
        if not ts:
            continue
        candidates = [*ts, *cs]
        ss = [r for r in skeletons if r.get("location_key") == loc]

        flags = [int(base.within(base.nearest(r, ss), threshold)) for r in candidates]
        teddy_flags = [int(base.within(base.nearest(r, ss), threshold)) for r in ts]

        n_total = len(candidates)
        n_near = sum(flags)
        n_teddy = len(ts)
        observed = sum(teddy_flags)
        observed_total += observed

        lo = max(0, n_teddy - (n_total - n_near))
        hi = min(n_teddy, n_near)
        dist = {
            x: hypergeom_pmf(x, n_total, n_near, n_teddy)
            for x in range(lo, hi + 1)
        }
        combined = convolve_distributions(combined, dist)

        strata.append(
            {
                "location_key": loc,
                "candidate_misc_positions": n_total,
                "near_skeleton_positions": n_near,
                "teddy_positions": n_teddy,
                "observed_teddy_near": observed,
            }
        )

    p_enrichment = sum(p for x, p in combined.items() if x >= observed_total)
    expectation = sum(x * p for x, p in combined.items())

    return {
        "threshold_units": threshold,
        "test": "EXACT_CONDITIONAL_CELL_STRATIFIED_HYPERGEOMETRIC_CONVOLUTION",
        "alternative": "TEDDY_ENRICHED_NEAR_SKELETON_PROXY",
        "observed_teddy_near": observed_total,
        "null_expected_teddy_near": expectation,
        "one_sided_p_enrichment": min(1.0, p_enrichment),
        "strata_count": len(strata),
        "strata": strata,
        "semantics": "Within each exact location_key, teddy labels are conditionally exchangeable only among teddy plus ordinary MISC control positions; cell-specific skeleton density is held fixed.",
    }


def nearest_with_geometry(anchor, candidates):
    loc = anchor.get("location_key", "")
    if not loc:
        return None
    ax = base.fnum(anchor, "position_x")
    ay = base.fnum(anchor, "position_y")
    az = base.fnum(anchor, "position_z")
    if None in (ax, ay, az):
        return None

    measured = []
    for c in candidates:
        if c.get("location_key", "") != loc:
            continue
        if c.get("record_formid", "") == anchor.get("record_formid", ""):
            continue
        bx = base.fnum(c, "position_x")
        by = base.fnum(c, "position_y")
        bz = base.fnum(c, "position_z")
        if None in (bx, by, bz):
            continue
        dx = float(bx - ax)
        dy = float(by - ay)
        dz = float(bz - az)
        d2 = math.hypot(dx, dy)
        d3 = math.sqrt(dx * dx + dy * dy + dz * dz)
        measured.append((d3, d2, abs(dz), c))

    if not measured:
        return None
    measured.sort(key=lambda x: x[0])
    d3, d2, dz_abs, c = measured[0]
    return {
        "record_formid": c.get("record_formid"),
        "target_kind": c.get("target_kind"),
        "distance_3d_units": round(d3, 3),
        "distance_2d_units": round(d2, 3),
        "abs_vertical_delta_units": round(dz_abs, 3),
        "within_512_3d": d3 <= 512,
        "within_512_3d_and_vertical_band_128": d3 <= 512 and dz_abs <= 128,
        "within_128_3d": d3 <= 128,
    }


def analyze(rows, context_map=None):
    result = base.analyze(rows, context_map=context_map)

    placed = [r for r in rows if r.get("location_key", "")]
    teddies = [r for r in placed if r.get("target_kind") == base.TEDDY_KIND]
    skeletons = [r for r in placed if r.get("target_kind") in base.SKELETON_KINDS]

    teddy_locations = {r.get("location_key") for r in teddies if r.get("location_key")}
    misc_controls = [
        r for r in placed
        if r.get("location_key") in teddy_locations
        and r.get("target_kind", "OTHER") not in base.EXCLUDED_CONTROL_KINDS
        and r.get("record_signature") == "REFR"
        and r.get("base_signature") == "MISC"
    ]

    geometry = []
    for t in teddies:
        geometry.append(
            {
                "teddy_ref": t.get("record_formid"),
                "location_key": t.get("location_key"),
                "nearest_skeleton_proxy": nearest_with_geometry(t, skeletons),
            }
        )

    result["v4_2_hardening"] = {
        "units_interpretation": {
            "128_units_approx_meters": 1.83,
            "512_units_approx_meters": 7.31,
            "source_semantics": "GECK-scale approximation; 128 units is approximately six feet and about one player height.",
        },
        "population_semantics": {
            "target_is_static_skeleton_proxy_not_all_human_remains": True,
            "all_human_remains_claim_allowed": False,
        },
        "cell_stratified_exact_test": {
            "128": exact_cell_stratified_enrichment(teddies, misc_controls, skeletons, 128),
            "512": exact_cell_stratified_enrichment(teddies, misc_controls, skeletons, 512),
        },
        "geometry_diagnostics": geometry,
        "geometry_claim_ceiling": {
            "within_128_3d": "LOCAL_SPATIAL_PROXIMITY_ONLY",
            "within_512_3d": "BROAD_SPATIAL_NEIGHBORHOOD_ONLY",
            "same_scene_from_distance_alone": False,
            "line_of_sight_established": False,
            "wall_or_floor_separation_excluded": False,
            "vertical_band_128_is_sensitivity_filter_not_visibility_proof": True,
        },
        "primary_inference_priority": [
            "exact cell-stratified one-sided enrichment p",
            "pooled same-cell MISC risk ratio / Fisher as descriptive secondary statistic",
            "per-location distribution",
            "geometry sensitivity diagnostics",
        ],
    }

    result["claim_ceiling"]["all_human_remains_measured"] = False
    result["claim_ceiling"]["same_scene_established_by_512_distance"] = False
    result["claim_ceiling"]["cell_stratified_exact_test_available"] = True
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--context-map", type=Path)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    context_map = None
    if args.context_map:
        context_map = json.loads(args.context_map.read_text(encoding="utf-8"))
        if not isinstance(context_map, dict):
            raise SystemExit("context map must be a JSON object")

    result = analyze(base.load(args.tsv), context_map=context_map)
    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
