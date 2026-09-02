#!/usr/bin/env python3
from __future__ import annotations
import copy, importlib.util, json
from pathlib import Path

HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("r45",HERE/"eye_r4_5_adversarial_model_expander.py")
r45=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(r45)

def load(name): return json.loads((HERE/"benchmarks"/name).read_text(encoding="utf-8"))

def expect_error(fn,needle):
    try: fn()
    except Exception as e:
        assert needle in str(e),(needle,str(e)); return
    raise AssertionError(f"EXPECTED_ERROR:{needle}")

def test_synthetic_counterexample_guided_replan():
    d=load("synthetic_adversarial_expansion.json"); r=r45.solve(d,"SYNTH")
    assert r["status"]=="NO_ADMISSIBLE_BREAKER_FOUND_IN_FINITE_ENVELOPE",r
    assert r["expanded_model_ids"]==["cheap_sensor_joint_breaker"],r
    assert r["rounds"][0]["breaker_evaluation"]["hard_failure_probability"]>0,r
    assert r["final_root_next_test"]=="t_gold",r

def test_no_breaker_vertex():
    d=load("synthetic_adversarial_expansion.json")
    d["uncertainty_envelope"]["vertex_models"]=[{"id":"nominal_clone","provenance":"synthetic clone of nominal model"}]
    r=r45.solve(d,"NO_BREAK")
    assert r["status"]=="NO_ADMISSIBLE_BREAKER_FOUND_IN_FINITE_ENVELOPE",r
    assert r["expanded_model_ids"]==[],r

def test_missing_vertex_provenance_rejected():
    d=load("synthetic_adversarial_expansion.json"); d["uncertainty_envelope"]["vertex_models"]=[{"id":"x"}]
    expect_error(lambda:r45.solve(d),"MISSING_CANDIDATE_PROVENANCE")

def test_duplicate_vertex_rejected():
    d=load("synthetic_adversarial_expansion.json"); v=d["uncertainty_envelope"]["vertex_models"][0]; d["uncertainty_envelope"]["vertex_models"]=[copy.deepcopy(v),copy.deepcopy(v)]
    expect_error(lambda:r45.solve(d),"BAD_OR_DUPLICATE_VERTEX")

def test_unknown_test_override_rejected():
    d=load("synthetic_adversarial_expansion.json"); d["uncertainty_envelope"]["vertex_models"]=[{"id":"x","provenance":"bad test adversary","likelihood_overrides":{"ghost":{"A":{"Y":1},"B":{"Y":1}}}}]
    expect_error(lambda:r45.solve(d),"CANDIDATE_UNKNOWN_TEST")

def test_vertex_ceiling():
    d=load("synthetic_adversarial_expansion.json"); base=d["uncertainty_envelope"]["vertex_models"][0]; d["requirements"]["max_vertices"]=1
    v2=copy.deepcopy(base); v2["id"]="second"; d["uncertainty_envelope"]["vertex_models"].append(v2)
    r=r45.solve(d); assert r["status"]=="UNKNOWN_RESOURCE_LIMIT" and r["reason"]=="VERTEX_COUNT_EXCEEDS_CEILING",r

def test_round_ceiling_with_breaker():
    d=load("synthetic_adversarial_expansion.json"); d["requirements"]["max_expansion_rounds"]=0
    r=r45.solve(d); assert r["status"]=="UNKNOWN_RESOURCE_LIMIT" and r["reason"]=="MAX_EXPANSION_ROUNDS_REACHED_WITH_BREAKERS_REMAINING",r

def test_out_of_policy_support_is_breaker():
    d=load("synthetic_adversarial_expansion.json"); base=d["base_problem"]; causes,tests=r45.parse_base(base); r44=r45.load_r44(); receipt=r44.solve(base,"OUTSUP")
    raw={"id":"new_outcome","provenance":"synthetic support-shift vertex","likelihood_overrides":{"t_robust":{"A":{"NEW_A":0.97,"NEW_B":0.03},"B":{"NEW_A":0.03,"NEW_B":0.97}}}}
    ev=r45.evaluate_policy(receipt,base,r45.build_candidate(base,raw,causes,tests),causes,tests)
    assert ev["out_of_policy_support_probability"]>0,ev

def test_palomar_preserves_baseline_nonidentifiability():
    r=r45.solve(load("palomar_xe325_adversarial_expansion.json"),"PAL")
    assert r["status"]=="BASELINE_NOT_ROBUSTLY_SOLVABLE",r
    assert r["baseline_status"]=="ROBUST_NON_IDENTIFIABLE_UNDER_DECLARED_MODEL_SET",r

def test_search_proof_finds_declared_breaker():
    r=r45.solve(load("search_proof_adversarial_expansion.json"),"SEARCH")
    assert r.get("rounds"),r
    assert r["rounds"][0]["selected_vertex_id"]=="joint_audit_verifier_breaker",r
    assert r["rounds"][0]["breaker_evaluation"]["hard_failure_probability"]>0,r

def main():
    tests=[v for k,v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests: t(); print("PASS",t.__name__)
    print(f"PASS_{len(tests)}_OF_{len(tests)}")
if __name__=="__main__": main()
