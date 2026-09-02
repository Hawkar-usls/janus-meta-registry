#!/usr/bin/env python3
import json, pathlib, sys
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from eye_r4_7_rt_1_minimax_adapter import load, solve_minimax, route_outcome, validate_source

C=load(HERE/"retro_tahyon_prospective_outcome_contract.json")
M=load(HERE/"retro_tahyon_r4_2_minimax_model.json")
ROOT=HERE.parents[1]
S=load(ROOT/"registry/uap/Retro-Tahyon.json")

def test_exact_minimax_policy():
    r=solve_minimax(M)
    assert r["status"]=="EXACT_MINIMAX_POLICY_FOUND",r
    assert r["root_next_test"]=="TOPA-RT-H2",r
    assert r["worst_case_cost_to_identification"]==4.0,r

def test_no_probabilistic_semantics():
    assert M["probability_semantics"]=="NONE"
    assert all("prior" not in x for x in M["cause_classes"])
    text=json.dumps(M).lower()
    assert "likelihood" not in text
    assert "outcome_probab" not in text

def test_h1_effect_routes_h3():
    row=route_outcome(C,"TOPA-RT-H1","PROSPECTIVE_EFFECT_SURVIVES_PREREGISTERED_HOLDOUT")
    assert row["status"]=="CONTRACT_OUTCOME"
    assert row["next_test"]=="TOPA-RT-H3"

def test_h3_physical_routes_h4():
    row=route_outcome(C,"TOPA-RT-H3","PHYSICAL_SYSTEM_DOMINANT")
    assert row["next_test"]=="TOPA-RT-H4"

def test_invalid_does_not_promote():
    row=route_outcome(C,"TOPA-RT-H1","H1_PROTOCOL_INVALID_OR_LEAKAGE_NOT_EXCLUDED")
    assert row["status"]=="PROTOCOL_INVALID"
    assert row["cause_promotion_permitted"] is False

def test_out_of_contract_fails_closed():
    row=route_outcome(C,"TOPA-RT-H3","MAYBE_RETROCAUSAL")
    assert row["status"]=="OUT_OF_CONTRACT"
    assert row["authority"]=="NO_POST_HOC_INTERPRETATION"

def test_source_grounding_and_h5_firewall():
    g=validate_source(C,S)
    assert g["status"]=="PASS_SOURCE_GROUNDING"
    h5=next(t for t in C["tests"] if t["id"]=="TOPA-RT-H5")
    assert h5["available"] is False

def test_r4_3_blocked_until_calibration():
    p=C["probability_policy"]
    assert p["r4_3_gate"]=="BLOCKED_PENDING_REAL_CALIBRATION"
    assert p["status"]=="FORBIDDEN_UNTIL_EMPIRICALLY_CALIBRATED_LIKELIHOODS_EXIST"

if __name__=="__main__":
    tests=[v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests: t()
    print(f"PASS_{len(tests)}_OF_{len(tests)}")
