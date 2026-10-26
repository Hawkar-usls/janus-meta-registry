#!/usr/bin/env python3
"""Read-only TOPA rounding bound on source-frozen real Rowan/local 1EY0 T8A pair.

This audit does NOT estimate inference stochasticity, validate MSA equivalence,
or interpret structural confidence as experimental mutation stability.
"""
from __future__ import annotations
import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

SOURCE = "data/rowan/provenance/ROWAN-1EY0-T8A-REAL-ROWAN-VS-LOCAL-MUTATION-DELTA-2026-10-26-v1.json"
STEP = Decimal("0.001")
HALF = STEP / 2
EXPECTED_STATUS = "PASS_REAL_ONE_MUTANT_WT_VS_T8A_PROVIDER_AND_LOCAL_DELTA_COMPARISON"

class GateHold(ValueError):
    pass

def exact_decimal(value):
    if type(value) not in (float, int, str):
        raise GateHold("NON_NUMERIC_SOURCE")
    try:
        d = Decimal(str(value))
    except InvalidOperation as e:
        raise GateHold("BAD_DECIMAL") from e
    if not d.is_finite() or not Decimal(0) <= d <= Decimal(1):
        raise GateHold("INVALID_CONFIDENCE_RANGE")
    return d

def audit(source):
    if source.get("status") != EXPECTED_STATUS:
        raise GateHold("SOURCE_STATUS_UNVERIFIED")
    fw = source.get("firewalls", {})
    for flag in ("experimental_DDG_labels_accessed", "genuine_blind_validation",
                 "independent_unpublished_custodian", "FireProt_210_scale_up_authorized",
                 "additional_protein_mutations_authorized",
                 "shadow_weights_retrained", "production_model_promoted"):
        if fw.get(flag) is not False:
            raise GateHold("SCIENTIFIC_FIREWALL_CHANGED_" + flag)
    rowan = source.get("rowan", {})
    local = source.get("local", {})
    if rowan.get("provider_result") != "Status.COMPLETED_OK" or rowan.get("extra_jobs_created_on_collection") != 0:
        raise GateHold("PROVIDER_NOT_FROZEN_COMPLETE")
    if source.get("cross_provider", {}).get("provider_equivalence_proven") is not False:
        raise GateHold("FALSE_PROVIDER_EQUIVALENCE")
    if source.get("cross_provider", {}).get("protein_fitness_or_DDG_inference") is not False:
        raise GateHold("FALSE_FITNESS_INFERENCE")
    w, m = (exact_decimal(rowan["WT_ptm"]), exact_decimal(rowan["T8A_ptm"]))
    lw, lm = (exact_decimal(local["WT_ptm"]), exact_decimal(local["T8A_ptm"]))
    for value in (w, m):
        if value != value.quantize(STEP):
            raise GateHold("ROWAN_PRECISION_NOT_THREE_DECIMALS")
    delta_local = lm - lw
    rounded = m - w
    lower, upper = rounded - STEP, rounded + STEP
    if not (upper < 0 and delta_local > 0):
        raise GateHold("SIGN_SEPARATION_NOT_ESTABLISHED")
    return {
        "schema_id": "janus.topa.rowan_1ey0_T8A_precision_only_gate.v1",
        "date_utc": "2026-10-26",
        "source_meta_registry_path": SOURCE,
        "source_status": EXPECTED_STATUS,
        "analysis": "interval_arithmetic_for_decimal_reporting_only",
        "reported_rowan_delta_ptm": str(rounded),
        "rowan_rounding_step": str(STEP),
        "rowan_rounding_only_delta_lower": str(lower),
        "rowan_rounding_only_delta_upper": str(upper),
        "local_observed_delta_ptm": str(delta_local),
        "rowan_minus_local_delta_lower": str(lower - delta_local),
        "rowan_minus_local_delta_upper": str(upper - delta_local),
        "sign_disagreement_survives_three_decimal_rounding": True,
        "same_checkpoint_and_msa_proven": False,
        "provider_ensemble_or_seed_repeats_available": False,
        "stochasticity_quantified": False,
        "rowan_avg_lddt_equivalent_to_local_mean_plddt_proven": False,
        "true_prospective_blind": False,
        "ddg_or_fitness_predicted": False,
        "additional_rowan_credits_spent_by_this_audit": 0,
        "new_rowan_jobs": 0,
        "fireprot_210_authorized": False,
        "shadow_weights_modified": False,
        "next_gate": "Require independent seed/sampling and exact model MSA metadata before attributing structural pTM difference to biology."
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", default=SOURCE, type=Path)
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args()
    try:
        if a.out.exists():
            raise GateHold("IMMUTABLE_RECEIPT_ALREADY_EXISTS")
        obj = json.loads(a.source.read_text(encoding="utf8"))
        report = audit(obj)
        a.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
        print("JANUS_TOPA_PRECISION_GATE=PASS_ROUNDING_ONLY_CANNOT_EXPLAIN_SIGN")
        print("JANUS_TOPA_STOCHASTICITY=NOT_TESTED")
        return 0
    except (OSError, ValueError, KeyError, InvalidOperation) as e:
        print("JANUS_TOPA_PRECISION_GATE=HOLD_" + str(e))
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
