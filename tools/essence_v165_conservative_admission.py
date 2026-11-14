#!/usr/bin/env python3
"""ESSENCE v1.6.5 fail-closed risk witness over real prospective CPU INT8 evidence.

This is an adjunct post-hoc uncertainty assessment, NOT a retroactive change
to the prespecified v1.6.4 exploratory thresholds. Treats correlated token
agreements as if independent only to compute an *optimistic* Wilson bound.
No independent blind custodian, service rollback, or production authority.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/"data"/"essence"/"v165"/"JANUS_INT8_PROSPECTIVE_RISK_ADMISSION_2026-11-14.json"
EVIDENCE_BLOB="6acaf2bbec6f3885466be8657e37f40c89fcb3a2"
SCHEMA="janus.essence.int8_conservative_admission_review/1.6.5"
EXPECTED_MODEL="fc767adb812ac3bea54c44cbccfa9680941f95e2c8a77120559b41da044d9463"
EXPECTED_V164_RECEIPT="00d0b6dac02765fa87d7d59e94fb7c3732258fa7d163e921c3846c863f3aabee"

def git_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def seal(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,
                       separators=(",",":"),allow_nan=False).encode()).hexdigest()

def strict_load(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file() or not 2<=p.stat().st_size<=40000:
        raise ValueError("UNSAFE_EVIDENCE_PATH")
    return json.loads(p.read_text(encoding="utf-8"),
      parse_constant=lambda _:(_ for _ in ()).throw(ValueError("NONFINITE_JSON")))

def wilson_lower(matches,observations,z=1.96):
    if (type(matches) is not int or type(observations) is not int
         or not 1<=observations<=1000000 or not 0<=matches<=observations
         or type(z) not in (float,int) or not math.isfinite(z) or z<=0):
        raise ValueError("INVALID_STATISTICS_INPUT")
    p=matches/observations
    z2=z*z
    return ((p+z2/(2*observations)
        -z*math.sqrt(p*(1-p)/observations+z2/(4*observations*observations)))
        /(1+z2/observations))

def evaluate(record):
    if (not isinstance(record,dict)
      or record.get("schema")!="janus.essence.native_int8_three_ffn_prospective_and_risk/1.6.5"
      or record.get("source",{}).get("prospective_summary_receipt_sha256")!=EXPECTED_V164_RECEIPT
      or record.get("source",{}).get("checkpoint_sha256")!=EXPECTED_MODEL
      or record.get("algorithm",{}).get("native_int8_linear_operator_count")!=3
      or record.get("algorithm",{}).get("original_checkpoint_sha_unchanged") is not True
      or record.get("algorithm",{}).get("automatic_promotion_enabled") is not False
      or record.get("authority",{}).get("automatic_model_swap_allowed") is not False
      or record.get("authority",{}).get("production_weights_change_allowed") is not False
      or record.get("prospective",{}).get("independent_external_custodian") is not False
      or record.get("prospective",{}).get("training_disjoint_holdout_certified") is not False):
        raise ValueError("UNTRUSTED_AUTHORITY_OR_SOURCE_CLAIM")
    p=record["prospective"]
    risk=record["risk"]
    if (risk.get("method")!="POST_HOC_WILSON_SCORE_95_PERCENT_LOWER_BOUND_PER_TOKEN_AS_IF_INDEPENDENT"
        or risk.get("z")!=1.96
        or risk.get("requested_per_cohort_conservative_lower_bound")!=.97
        or p.get("locked_min_empirical_top1")!=.97
        or not isinstance(p.get("source_cohorts"),list)
        or len(p["source_cohorts"])!=2):
        raise ValueError("UNPINNED_REVIEW_POLICY")
    expected_src=[
        ("external_cpython_readme","91569eb2398d494c71fd0abb48fe7e5f2cfed1ea","b3058f63c27a1201670a2a6a0e0dfea38e43d048"),
        ("external_pytorch_readme","1a6d2a8249e0b28c119661a8c424f9c145fbe1bd","ba8042230e7e1ee0c64ada29878aac14773b328c")
    ]
    details=[];lower_pass=True;empirical_pass=True
    for obj,(name,commit,blob) in zip(p["source_cohorts"],expected_src):
        if (obj.get("name")!=name or obj.get("source_commit")!=commit
          or obj.get("git_blob_sha1")!=blob):
            raise ValueError("SOURCE_FINGERPRINT_MISMATCH")
        k=obj.get("top1_matches");n=obj.get("top1_total");empirical=obj.get("empirical_top1")
        if (type(empirical) not in (float,int) or not math.isfinite(empirical)
            or type(k) is not int or type(n) is not int
            or n!=768 or abs(empirical-k/n)>0.0000001):
            raise ValueError("FABRICATED_OR_UNBOUNDED_TOP1")
        ref=obj["baseline_ce"];candidate=obj["candidate_ce"]
        if (type(ref) not in (float,int) or type(candidate) not in (float,int)
            or ref<=0 or not math.isfinite(ref) or not math.isfinite(candidate)):
            raise ValueError("INVALID_LOSS")
        if candidate/ref-1>p["locked_max_ce_relative_regression"]:
            empirical_pass=False
        raw=k/n
        bound=wilson_lower(k,n,z=risk["z"])
        lower_pass=lower_pass and bound>=risk["requested_per_cohort_conservative_lower_bound"]
        empirical_pass=empirical_pass and raw>=p["locked_min_empirical_top1"]
        details.append({"corpus":name,
          "observed_top1":round(raw,9),"matched_predictions":k,"total_predictions":n,
          "wilson_95_lower_independent_token_assumption":round(bound,9),
          "prespecified_empirical_top1_pass":raw>=.97,
          "conservative_lower_bound_pass":bound>=.97,
          "ce_relative_change_fraction":round(candidate/ref-1,9)})
    if (not .25<=p["serialized_model_saving_fraction"]<=.9
        or p["cpu_current_rss_native_int8_bytes"]>=p["cpu_current_rss_fp32_bytes"] and
           risk.get("statistical_lower_bound_gate")!="HOLD"):
        raise ValueError("PACKING_OR_RSS_CLAIM_CONTRADICTION")
    if risk.get("statistical_lower_bound_gate")!=("PASS" if lower_pass else "HOLD"):
        raise ValueError("EXPECTED_CONSERVATIVE_GATE_CONTRADICTION")
    # Missing external custodian, service rollback, actual model change review,
    # statistically certified speedup, and RAM reduction all hold. Independently
    # of an observational interval, only human-controlled, audited promotions.
    report={
      "schema":SCHEMA,
      "research_only":True,
      "source_prospective_receipt_sha256":EXPECTED_V164_RECEIPT,
      "checkpoint_sha256":EXPECTED_MODEL,
      "cohorts":details,
      "both_prespecified_empirical_thresholds_pass":bool(empirical_pass),
      "both_optimistic_conservative_bounds_pass":bool(lower_pass),
      "per_token_observations_are_correlated":True,
      "wilson_independent_token_assumption_is_optimistic":True,
      "memory_saving_inference_proven":False,
      "source_is_external_public_not_blind_lab":True,
      "true_external_blind_custodian_verified":False,
      "live_service_canary_pass":False,
      "real_service_rollback_pass":False,
      "production_weights_changed":False,
      "automatic_model_change_authority":False,
      "development_gate":"MEASURED_PROSPECTIVE_SAMPLE_PASS" if empirical_pass
                        else "HOLD_OBSERVED_FIDELITY",
      "production_gate":"HOLD_EXTERNAL_BLIND_ROLLBACK_AND_CONSERVATIVE_RELIABILITY",
      "next_required":["INDEPENDENT_EXTERNAL_BLIND_COHORT",
                       "REAL_PRODUCTION_SERVICE_SHADOW_AND_CANARY",
                       "AUTHENTICATED_CHANGE_APPROVAL",
                       "HARDWARE_MATCHED_MEMORY_AND_LATENCY_REPLICATION"]
    }
    report["receipt_sha256"]=seal(report)
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="runtime/essence_v165/risk_review.json")
    a=p.parse_args()
    if git_blob(EVIDENCE.read_bytes())!=EVIDENCE_BLOB:
        raise ValueError("EVIDENCE_GIT_BLOB_CHANGED")
    report=evaluate(strict_load(EVIDENCE))
    dest=Path(a.out)
    if dest.exists():raise FileExistsError("NO_REPORT_OVERWRITE")
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"source_receipt":EXPECTED_V164_RECEIPT,
      "observed_thresholds_pass":report["both_prespecified_empirical_thresholds_pass"],
      "wilson_lower_bounds":[x["wilson_95_lower_independent_token_assumption"]
                             for x in report["cohorts"]],
      "conservative_reliability_pass":report["both_optimistic_conservative_bounds_pass"],
      "production_gate":report["production_gate"],
      "receipt_sha256":report["receipt_sha256"]},sort_keys=True))

if __name__=="__main__":main()
