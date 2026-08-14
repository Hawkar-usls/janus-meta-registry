#!/usr/bin/env python3
import json
import sys
from collections import Counter
from pathlib import Path

DEFAULT = Path("data/JANUS-SING-WHEN-YOURE-WINNING-OUTCOME-RECEIPT-DANGEROUS-CONTROL-SEARCH-v1.0.json")
path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT

d = json.loads(path.read_text(encoding="utf-8"))
errors = []

controls = d.get("controls", [])
by_id = {c.get("control_id"): c for c in controls}

if len(controls) != d.get("derived_counts", {}).get("controls_logged"):
    errors.append("controls_logged does not equal actual control count")

mah = by_id.get("DOR-001")
if not mah:
    errors.append("DOR-001 Mahomes direct counterexample missing")
else:
    required_true = ["source_physical_subject", "one_world", "receipt_outcome_bearing", "chain_outcome_receipt"]
    for field in required_true:
        if mah.get(field) is not True:
            errors.append(f"DOR-001 {field} must be true")
    if mah.get("first_break_physical_outcome") != "NONE":
        errors.append("DOR-001 first_break_physical_outcome must be NONE")
    if mah.get("visible_same_subject_instances", 0) < 2:
        errors.append("DOR-001 must contain multiple visible same-subject instances")
    sources = " ".join(mah.get("official_product_sources", []))
    if "shop.chiefs.com" not in sources and "fanatics.com" not in sources:
        errors.append("DOR-001 official product provenance missing")

bool_hits = sum(c.get("chain_outcome_receipt") is True for c in controls)
recorded_hits = d.get("derived_counts", {}).get("minimum_boolean_outcome_full_chain_hits_under_frozen_rules")
if bool_hits != recorded_hits:
    errors.append(f"boolean full-chain hit count mismatch: derived={bool_hits}, recorded={recorded_hits}")
if bool_hits < 1:
    errors.append("dangerous-control suite must preserve at least one full-chain counterexample once found")

high_conf = sum(c.get("classification") == "HIGH_CONFIDENCE_DIRECT_COUNTEREXAMPLE" for c in controls)
if high_conf != d.get("derived_counts", {}).get("high_confidence_direct_counterexamples"):
    errors.append("high-confidence direct counterexample count mismatch")
if high_conf < 1:
    errors.append("high-confidence direct counterexample disappeared")

if d.get("critical_result", {}).get("scientific_effect") != "OUTCOME_CHAIN_WEAKENED_BY_DIRECT_OFFICIAL_COUNTEREXAMPLE":
    errors.append("scientific effect must preserve weakening by direct counterexample")

anti = d.get("anti_rescue_integrity", {})
for field in [
    "do_not_add_simultaneity_requirement_after_Mahomes",
    "do_not_redefine_trophy_to_exclude_sports_merchandise",
    "do_not_require_exactly_one_outcome_token_retroactively",
    "outcome_cardinality_is_secondary_diagnostic_only",
    "legacy_broad_endpoint_remains_weakened",
    "outcome_endpoint_now_also_weakened_by_counterexample",
    "no_causal_or_supernatural_claim",
]:
    if anti.get(field) is not True:
        errors.append(f"anti-rescue invariant failed: {field}")

if d.get("execution", {}).get("population_prevalence_estimate") is not False:
    errors.append("this purposive search must not claim population prevalence")
if d.get("execution", {}).get("blind") is not False:
    errors.append("this run must remain explicitly non-blind")
if d.get("execution", {}).get("random") is not False:
    errors.append("this run must remain explicitly non-random")

first_breaks = Counter(str(c.get("first_break_physical_outcome", "MISSING")) for c in controls)
summary = {
    "artifact_id": d.get("artifact_id"),
    "controls": len(controls),
    "boolean_outcome_full_chain_hits": bool_hits,
    "high_confidence_direct_counterexamples": high_conf,
    "primary_counterexample": d.get("critical_result", {}).get("primary_counterexample"),
    "scientific_effect": d.get("critical_result", {}).get("scientific_effect"),
    "first_break_counts": dict(sorted(first_breaks.items())),
    "anti_rescue_ok": not errors,
    "errors": errors,
    "ok": not errors,
}
print(json.dumps(summary, indent=2, sort_keys=True))
raise SystemExit(1 if errors else 0)
