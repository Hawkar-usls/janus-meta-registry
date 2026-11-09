#!/usr/bin/env python3
"""JANUS E04 — measured KBC materials data; NOT a human regeneration model.

Uses reported study-level summary measurements, never inferred tissue kinetics.
Std devs are source-reported variability, NOT confidence intervals or prediction
uncertainty. Different studies are never pooled or directly compared.
No external packages.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_INPUT = HERE / "data" / "JANUS_E04_KBC_primary_measured_properties_2026-11-09.json"
DEFAULT_OUTPUT = "JANUS_E04_KBC_MEASURED_MATERIALS_RESULTS.json"

def measured_value(item, key):
    value = item["values"][key]
    assert math.isfinite(value["mean"]) and value["mean"] >= 0
    assert math.isfinite(value["pm"]) and value["pm"] >= 0
    return value["mean"]

def analyze(data):
    assert data["schema"] == "janus.regeneration.materials.observed_v1"
    sources = {x["id"]: x for x in data["sources"]}
    assert set(sources) == {"HE2026_PREPRINT", "DEY2024_PEER_REVIEWED"}
    m = {x["sample_id"]: x for x in sources["HE2026_PREPRINT"]["measurements"]}
    s = {x["sample_id"]: x for x in sources["DEY2024_PEER_REVIEWED"]["measurements"]}
    assert set(m) == {"wet", "oven", "lyophilized"}
    assert set(s) == {"unmodified", "glycerol", "glycerol_turmeric", "glycerol_tulsi"}

    for item in m.values():
        for key in ("tensile_strength_MPa", "young_modulus_MPa", "elongation_at_break_percent"):
            measured_value(item, key)
    for item in s.values():
        for key in ("swelling_percent", "moisture_content_percent"):
            measured_value(item, key)

    def ratio(a, b, prop):
        return round(measured_value(a, prop) / measured_value(b, prop), 5)

    # 1-g dry mass is only a normalization for published percentages, NOT
    # the measured mass of a test specimen.
    reference_dry_mass_g = 1.0
    uptake = {}
    for name, item in s.items():
        water_mass = reference_dry_mass_g * measured_value(item, "swelling_percent") / 100
        uptake[name] = {
            "reference_dry_mass_g": reference_dry_mass_g,
            "water_added_g_from_published_swelling": round(water_mass, 5),
            "illustrative_hydrated_mass_g": round(reference_dry_mass_g + water_mass, 5),
        }

    ratios = {
        "lyophilized_vs_wet_tensile_strength_ratio":
            ratio(m["lyophilized"], m["wet"], "tensile_strength_MPa"),
        "oven_vs_wet_tensile_strength_ratio":
            ratio(m["oven"], m["wet"], "tensile_strength_MPa"),
        "lyophilized_vs_wet_young_modulus_ratio":
            ratio(m["lyophilized"], m["wet"], "young_modulus_MPa"),
        "lyophilized_vs_wet_elongation_ratio":
            ratio(m["lyophilized"], m["wet"], "elongation_at_break_percent"),
        "glycerol_vs_unmodified_swelling_ratio":
            ratio(s["glycerol"], s["unmodified"], "swelling_percent"),
    }

    required_for_skin_scaffold_claim = {
        "direct_measured_kbc_mechanics": True,
        "direct_measured_kbc_water_uptake": True,
        "water_vapor_transmission_measured_for_same_material": False,
        "sterility_or_contamination_risk_characterized": False,
        "keratinocyte_migration_and_viability_comparable_to_control": False,
        "human_skin_wound_repair_effect_measured": False,
        "human_fingertip_regrowth_effect_measured": False,
        "biological_kinetics_parameters_E01_E02_calibrated": False,
    }
    assert not all(required_for_skin_scaffold_claim.values())
    return {
        "schema": "janus.regeneration.materials.E04.results_v1",
        "status": "DESCRIPTIVE_REANALYSIS_OF_PUBLISHED_MEASUREMENTS",
        "input_artifact": data["artifact_id"],
        "source_count": len(sources),
        "source_review_states": {key: value["peer_review_status"] for key, value in sources.items()},
        "n_measurement_conditions": len(m) + len(s),
        "n_reported_primary_properties": len(m)*3 + len(s)*2,
        "same_study_nominal_ratios": ratios,
        "one_gram_dry_mass_normalized_uptake": uptake,
        "gating": required_for_skin_scaffold_claim,
        "clinical_regeneration_claim_permitted": False,
        "readout": (
            "Reported wet/dry KBC mechanics and published water uptake differ by processing or "
            "formulation. There are insufficient measured comparable biological endpoints "
            "to calculate a human tissue regrowth or wound healing prediction."
        ),
        "epistemic_warning": (
            "Ratios of published means are descriptive, not causal treatment effects. "
            "The sources do not report correlated sample-level data; do not invent "
            "confidence intervals. Drying may improve strength while making a material "
            "unsuitable for a wet wound. Raw SCOBY is NOT a sterile medical dressing."
        )
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",default=str(DEFAULT_INPUT))
    parser.add_argument("--output",default=DEFAULT_OUTPUT)
    args=parser.parse_args()
    raw=Path(args.input).read_bytes()
    data=json.loads(raw)
    results=analyze(data)
    results["source_json_sha256"]=hashlib.sha256(raw).hexdigest()
    output=json.dumps(results,sort_keys=True,indent=2,ensure_ascii=False)+"\n"
    Path(args.output).write_text(output,encoding="utf-8")
    # Check determinism and basic data containment without biological assertions.
    assert analyze(data)==analyze(data)
    assert results["same_study_nominal_ratios"]["lyophilized_vs_wet_tensile_strength_ratio"] > 1
    assert results["one_gram_dry_mass_normalized_uptake"]["glycerol"]["water_added_g_from_published_swelling"] == 3.212
    assert results["clinical_regeneration_claim_permitted"] is False
    print(json.dumps({
        "status": results["status"],
        "output":args.output,
        "source_sha256":results["source_json_sha256"],
        "computed_ratios":results["same_study_nominal_ratios"],
        "clinical_regeneration_claim_permitted":False
    },indent=2))

if __name__=="__main__":
    main()
