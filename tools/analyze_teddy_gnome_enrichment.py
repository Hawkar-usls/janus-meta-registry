#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

TEDDY_KIND = "TEDDY"
SKELETON_KINDS = {
    "SKELETON_CLOTHES",
    "SKELETON_RAGS",
    "SKELETON_MALE",
    "SKELETON_FEMALE",
}
GNOME_KINDS = {"GNOME_GENERIC", "GNOME_INTACT", "GNOME_DAMAGED"}
EXCLUDED_CONTROL_KINDS = {TEDDY_KIND, *SKELETON_KINDS, *GNOME_KINDS}


def load(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def fnum(row, key):
    try:
        return float(row.get(key, ""))
    except (TypeError, ValueError):
        return None


def distance(a, b):
    av = [fnum(a, k) for k in ("position_x", "position_y", "position_z")]
    bv = [fnum(b, k) for k in ("position_x", "position_y", "position_z")]
    if any(v is None for v in av + bv):
        return None
    return math.dist(av, bv)


def nearest(anchor, candidates):
    loc = anchor.get("location_key", "")
    if not loc:
        return None
    measured = []
    for c in candidates:
        if c.get("location_key", "") != loc:
            continue
        if c.get("record_formid", "") == anchor.get("record_formid", ""):
            continue
        d = distance(anchor, c)
        if d is not None:
            measured.append((d, c))
    if not measured:
        return None
    measured.sort(key=lambda x: x[0])
    d, c = measured[0]
    return {
        "record_formid": c.get("record_formid"),
        "target_kind": c.get("target_kind"),
        "distance_units": round(d, 3),
        "record_file": c.get("record_file"),
        "base_editorid": c.get("base_editorid"),
        "base_name": c.get("base_name"),
    }


def within(nearest_obj, threshold):
    return bool(nearest_obj and nearest_obj["distance_units"] <= threshold)


def choose(n, k):
    if k < 0 or k > n:
        return 0
    return math.comb(n, k)


def hypergeom_prob(a, row1, col1, n):
    den = choose(n, row1)
    return (choose(col1, a) * choose(n-col1, row1-a) / den) if den else 0.0


def fisher_two_sided(a, b, c, d):
    n = a+b+c+d
    row1 = a+b
    col1 = a+c
    lo = max(0, row1-(n-col1))
    hi = min(row1, col1)
    p_obs = hypergeom_prob(a, row1, col1, n)
    p = 0.0
    eps = 1e-15
    for x in range(lo, hi+1):
        px = hypergeom_prob(x, row1, col1, n)
        if px <= p_obs + eps:
            p += px
    return min(1.0, p)


def ratio(success_a, total_a, success_b, total_b):
    if total_a == 0 or total_b == 0:
        return None
    ra = success_a / total_a
    rb = success_b / total_b
    if rb == 0:
        return "INF" if ra > 0 else None
    return ra / rb


def odds_ratio(a,b,c,d):
    if b == 0 or c == 0:
        if a > 0 and d > 0:
            return "INF"
        return None
    return (a*d)/(b*c)


def threshold_stats(teddies, controls, skeletons, threshold):
    t_success = 0
    c_success = 0

    for t in teddies:
        ns = nearest(t, skeletons)
        t_success += int(within(ns, threshold))

    for c in controls:
        ns = nearest(c, skeletons)
        c_success += int(within(ns, threshold))

    a = t_success
    b = len(teddies)-t_success
    c = c_success
    d = len(controls)-c_success
    fisher = fisher_two_sided(a,b,c,d) if len(teddies) and len(controls) else None

    return {
        "threshold_units": threshold,
        "teddy": {
            "n": len(teddies),
            "near_skeleton": t_success,
            "rate": (t_success/len(teddies)) if teddies else None,
        },
        "matched_clutter_controls": {
            "n": len(controls),
            "near_skeleton": c_success,
            "rate": (c_success/len(controls)) if controls else None,
        },
        "risk_ratio_teddy_vs_control": ratio(t_success, len(teddies), c_success, len(controls)),
        "odds_ratio_teddy_vs_control": odds_ratio(a,b,c,d),
        "fisher_exact_two_sided_p": fisher,
        "table": {"teddy_near":a,"teddy_not_near":b,"control_near":c,"control_not_near":d},
    }


def analyze(rows, context_map=None):
    placed = [r for r in rows if r.get("location_key", "")]
    teddies = [r for r in placed if r.get("target_kind") == TEDDY_KIND]
    skeletons = [r for r in placed if r.get("target_kind") in SKELETON_KINDS]
    gnomes = [r for r in placed if r.get("target_kind") in GNOME_KINDS]

    teddy_locations = {r.get("location_key") for r in teddies if r.get("location_key")}
    broad_controls = [
        r for r in placed
        if r.get("location_key") in teddy_locations
        and r.get("target_kind", "OTHER") not in EXCLUDED_CONTROL_KINDS
        and r.get("record_signature") == "REFR"
    ]
    misc_controls = [
        r for r in broad_controls
        if r.get("base_signature") == "MISC"
    ]

    per_teddy = []
    teddy_gnome_128 = teddy_gnome_512 = 0
    teddy_skel_128 = teddy_skel_512 = 0
    triad_512 = 0
    for t in teddies:
        ns = nearest(t, skeletons)
        ng = nearest(t, gnomes)
        s128 = within(ns, 128)
        s512 = within(ns, 512)
        g128 = within(ng, 128)
        g512 = within(ng, 512)
        teddy_skel_128 += int(s128)
        teddy_skel_512 += int(s512)
        teddy_gnome_128 += int(g128)
        teddy_gnome_512 += int(g512)
        triad_512 += int(s512 and g512)
        per_teddy.append({
            "teddy_ref": t.get("record_formid"),
            "record_file": t.get("record_file"),
            "location_key": t.get("location_key"),
            "nearest_skeleton": ns,
            "nearest_gnome": ng,
            "skeleton_within_128": s128,
            "skeleton_within_512": s512,
            "gnome_within_128": g128,
            "gnome_within_512": g512,
        })

    per_gnome = []
    gnome_skel_128 = gnome_skel_512 = 0
    gnome_teddy_128 = gnome_teddy_512 = 0
    for g in gnomes:
        ns = nearest(g, skeletons)
        nt = nearest(g, teddies)
        s128 = within(ns,128); s512 = within(ns,512)
        t128 = within(nt,128); t512 = within(nt,512)
        gnome_skel_128 += int(s128); gnome_skel_512 += int(s512)
        gnome_teddy_128 += int(t128); gnome_teddy_512 += int(t512)
        per_gnome.append({
            "gnome_ref": g.get("record_formid"),
            "gnome_kind": g.get("target_kind"),
            "record_file": g.get("record_file"),
            "location_key": g.get("location_key"),
            "nearest_skeleton": ns,
            "nearest_teddy": nt,
            "skeleton_within_128": s128,
            "skeleton_within_512": s512,
            "teddy_within_128": t128,
            "teddy_within_512": t512,
        })

    by_plugin = Counter(r.get("record_file","") for r in teddies)
    gnome_by_kind = Counter(r.get("target_kind","") for r in gnomes)

    cell = {}
    for loc in sorted(teddy_locations):
        ts = [r for r in teddies if r.get("location_key")==loc]
        cs = [r for r in misc_controls if r.get("location_key")==loc]
        ss = [r for r in skeletons if r.get("location_key")==loc]
        cell[loc] = {
            "teddy_count": len(ts),
            "skeleton_count": len(ss),
            "control_count": len(cs),
            "teddy_near_skeleton_128": sum(within(nearest(t,ss),128) for t in ts),
            "teddy_near_skeleton_512": sum(within(nearest(t,ss),512) for t in ts),
            "control_near_skeleton_128": sum(within(nearest(c,ss),128) for c in cs),
            "control_near_skeleton_512": sum(within(nearest(c,ss),512) for c in cs),
        }

    context_map = context_map or {}
    context_summary = {}
    if context_map:
        cats = defaultdict(lambda: {
            "location_count": 0,
            "teddy_count": 0,
            "misc_reference_count": 0,
            "skeleton_count": 0,
            "teddy_near_skeleton_128": 0,
            "teddy_near_skeleton_512": 0,
        })
        locations_by_cat = defaultdict(set)
        for r in placed:
            loc = r.get("location_key", "")
            cat = context_map.get(loc)
            if not cat:
                continue
            locations_by_cat[cat].add(loc)
            if r.get("target_kind") == TEDDY_KIND:
                cats[cat]["teddy_count"] += 1
                ns = nearest(r, skeletons)
                cats[cat]["teddy_near_skeleton_128"] += int(within(ns,128))
                cats[cat]["teddy_near_skeleton_512"] += int(within(ns,512))
            if r.get("base_signature") == "MISC" and r.get("record_signature") == "REFR":
                cats[cat]["misc_reference_count"] += 1
            if r.get("target_kind") in SKELETON_KINDS:
                cats[cat]["skeleton_count"] += 1
        for cat, stats in cats.items():
            stats["location_count"] = len(locations_by_cat[cat])
            denom = stats["misc_reference_count"]
            stats["teddies_per_1000_misc_refs"] = (
                1000.0 * stats["teddy_count"] / denom if denom else None
            )
            t = stats["teddy_count"]
            stats["teddy_near_skeleton_128_rate"] = (
                stats["teddy_near_skeleton_128"] / t if t else None
            )
            stats["teddy_near_skeleton_512_rate"] = (
                stats["teddy_near_skeleton_512"] / t if t else None
            )
        context_summary = dict(cats)

    return {
        "schema": "janus.fo3_teddy_gnome_enrichment_receipt.v1",
        "population": {
            "placed_reference_count": len(placed),
            "teddy_count": len(teddies),
            "skeleton_count": len(skeletons),
            "gnome_count": len(gnomes),
            "matched_misc_clutter_control_count": len(misc_controls),
            "matched_broad_reference_control_count": len(broad_controls),
            "teddy_location_count": len(teddy_locations),
            "teddy_by_plugin": dict(by_plugin),
            "gnome_by_kind": dict(gnome_by_kind),
        },
        "teddy_skeleton_enrichment": {
            "primary_misc_baseline": {
                "128": threshold_stats(teddies,misc_controls,skeletons,128),
                "512": threshold_stats(teddies,misc_controls,skeletons,512),
                "definition": "other MISC REFRs in the same location keys that contain teddies; teddy/skeleton/gnome targets excluded",
            },
            "secondary_broad_reference_baseline": {
                "128": threshold_stats(teddies,broad_controls,skeletons,128),
                "512": threshold_stats(teddies,broad_controls,skeletons,512),
                "definition": "all other REFRs in the same location keys; target objects excluded",
            },
        },
        "teddy_gnome_grammar": {
            "teddy_with_gnome_within_128": teddy_gnome_128,
            "teddy_with_gnome_within_512": teddy_gnome_512,
            "teddy_with_skeleton_and_gnome_within_512": triad_512,
            "gnome_with_teddy_within_128": gnome_teddy_128,
            "gnome_with_teddy_within_512": gnome_teddy_512,
            "gnome_with_skeleton_within_128": gnome_skel_128,
            "gnome_with_skeleton_within_512": gnome_skel_512,
        },
        "per_teddy": per_teddy,
        "per_gnome": per_gnome,
        "per_teddy_location": cell,
        "context_ledger_summary": context_summary,
        "context_ledger_semantics": "Only exact location_key labels supplied by an external reference-bound ledger are used; no automatic name heuristic is promoted to evidence.",
        "claim_ceiling": {
            "real_spatial_enrichment_measured": bool(teddies and misc_controls),
            "enrichment_proves_authorial_intent": False,
            "enrichment_proves_single_in_world_placer": False,
            "gnome_proximity_proves_gnomes_alive": False,
            "teddy_proximity_proves_child_owner": False,
            "context_specific_child_room_store_rates": "REQUIRE_SEPARATE_REFERENCE_BOUND_CONTEXT_LEDGER",
        },
        "invariants": {
            "SAME_LOCATION_REQUIRED_FOR_PAIRING": True,
            "TARGET_OBJECTS_EXCLUDED_FROM_CLUTTER_CONTROLS": True,
            "PROXIMITY_DOES_NOT_PROVE_CAUSALITY": True,
            "STATISTICAL_ENRICHMENT_DOES_NOT_IDENTIFY_PLACER": True,
            "GNOME_IS_ANALYZED_AS_PROXY_OBJECT_NOT_LIVING_AGENT": True,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--context-map", type=Path, help="Optional JSON object mapping exact location_key -> context category")
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()
    context_map = None
    if args.context_map:
        context_map = json.loads(args.context_map.read_text(encoding="utf-8"))
        if not isinstance(context_map, dict):
            raise SystemExit("context map must be a JSON object mapping location_key to category")
    result = analyze(load(args.tsv), context_map=context_map)
    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.out:
        args.out.write_text(text+"\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
