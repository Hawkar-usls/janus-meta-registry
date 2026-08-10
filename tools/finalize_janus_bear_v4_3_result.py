#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def stratified(analysis: dict, threshold: str) -> dict:
    return analysis["v4_2_hardening"]["cell_stratified_exact_test"][threshold]


def pooled(analysis: dict, threshold: str) -> dict:
    return analysis["teddy_skeleton_enrichment"]["primary_misc_baseline"][threshold]


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def classify(analysis: dict) -> dict:
    s128 = stratified(analysis, "128")
    s512 = stratified(analysis, "512")
    p128 = s128["one_sided_p_enrichment"]
    p512 = s512["one_sided_p_enrichment"]
    rr128 = pooled(analysis, "128")["risk_ratio_teddy_vs_control"]
    rr512 = pooled(analysis, "512")["risk_ratio_teddy_vs_control"]

    sig128 = finite_number(p128) and p128 <= 0.05
    sig512 = finite_number(p512) and p512 <= 0.05

    if sig128:
        label = "LOCAL_128_CELL_STRATIFIED_ENRICHMENT_CANDIDATE"
    elif sig512:
        label = "BROAD_512_CELL_STRATIFIED_ENRICHMENT_CANDIDATE_ONLY"
    else:
        pooled_signal = rr128 == "INF" or rr512 == "INF" or (
            finite_number(rr128) and rr128 > 1.0
        ) or (
            finite_number(rr512) and rr512 > 1.0
        )
        label = "POOLED_SIGNAL_NOT_CONFIRMED_BY_STRATIFIED_GATE" if pooled_signal else "NO_TEDDY_SKELETON_ENRICHMENT_ADMITTED"

    return {
        "label": label,
        "alpha_descriptive": 0.05,
        "p_128": p128,
        "p_512": p512,
        "risk_ratio_128": rr128,
        "risk_ratio_512": rr512,
        "note": "This classification is a statistical gate label, not a developer-intent claim and not a multiple-testing-corrected discovery claim.",
    }


def build(acquisition: dict, all_analysis: dict, enabled_analysis: dict) -> dict:
    if not str(acquisition.get("status", "")).startswith("PASS_"):
        raise ValueError("acquisition gate is not PASS")

    all_class = classify(all_analysis)
    enabled_class = classify(enabled_analysis)
    pop = all_analysis["population"]
    enabled_pop = enabled_analysis["population"]

    result = {
        "schema": "janus.bear.v4_3.real_esm_spatial_result.v1",
        "status": "REAL_ESM_SPATIAL_STATISTICS_COMPUTED_FROM_HASH_BOUND_EFFECTIVE_REFR_EXPORT",
        "source_binding": {
            "master_bundle": acquisition["master_bundle"],
            "inventory_sha256": acquisition["inventory"]["sha256"],
            "inventory_rows": acquisition["inventory"]["rows"],
            "enabled_only_sha256": acquisition["inventory"].get("enabled_only_sha256"),
            "effective_winning_refr_semantics": True,
        },
        "all_effective_non_deleted_refr": {
            "population": pop,
            "teddy_skeleton": {
                "pooled_128": pooled(all_analysis, "128"),
                "pooled_512": pooled(all_analysis, "512"),
                "cell_stratified_128": stratified(all_analysis, "128"),
                "cell_stratified_512": stratified(all_analysis, "512"),
                "classification": all_class,
            },
            "teddy_gnome_grammar": all_analysis["teddy_gnome_grammar"],
            "geometry_diagnostics": all_analysis["v4_2_hardening"]["geometry_diagnostics"],
        },
        "enabled_only_sensitivity": {
            "population": enabled_pop,
            "teddy_skeleton": {
                "pooled_128": pooled(enabled_analysis, "128"),
                "pooled_512": pooled(enabled_analysis, "512"),
                "cell_stratified_128": stratified(enabled_analysis, "128"),
                "cell_stratified_512": stratified(enabled_analysis, "512"),
                "classification": enabled_class,
            },
            "teddy_gnome_grammar": enabled_analysis["teddy_gnome_grammar"],
        },
        "sensitivity": {
            "classification_changed_when_initially_disabled_removed": all_class["label"] != enabled_class["label"],
            "all_label": all_class["label"],
            "enabled_only_label": enabled_class["label"],
            "rule": "A result that depends strongly on initially-disabled references must be reported as state-sensitive rather than as an unconditional world-placement grammar.",
        },
        "claim_ceiling": {
            "real_hash_bound_effective_REFR_statistics_computed": True,
            "universal_official_distribution_authenticity_cryptographically_proved": False,
            "static_skeleton_proxy_is_all_human_remains": False,
            "euclidean_proximity_is_same_visible_scene": False,
            "statistical_enrichment_is_authorial_intent": False,
            "statistical_enrichment_is_single_in_world_placer": False,
            "gnome_proxy_semantics_is_literal_sentience": False,
            "alpha_0_05_is_preregistered_confirmatory_familywise_threshold": False,
        },
        "next_gate": {
            "if_enrichment_candidate": "manual exact-reference scene review plus context-ledger confirmation and multiple-testing discipline",
            "if_not_admitted": "retain known local staged tableaux but reject game-wide enrichment claim in this tested population",
        },
    }
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--acquisition", required=True, type=Path)
    ap.add_argument("--all-analysis", required=True, type=Path)
    ap.add_argument("--enabled-analysis", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    result = build(load(args.acquisition), load(args.all_analysis), load(args.enabled_analysis))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
