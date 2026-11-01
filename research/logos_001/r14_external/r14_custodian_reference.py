"""Reference *custodian-side* scoring for external sealed R1.4.

Only the INDEPENDENT DATA HOLDER should execute this with real hidden data.
Participant receives no test y; no labels or per-point TEST errors are emitted
to the signed report. Local fixture tests are NOT an external evaluation.

Requires pinned NumPy/SciPy/scikit-learn; uses the predeclared R1.3 strong
baseline procedure and paired distinct-x bootstrap without test retuning.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import r13_witness
from r14_submission import produce_predictions, PROTOCOL

def _sha(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def evaluate_custodian_private(data,runner=produce_predictions):
    if type(data)!=dict or set(data)!={"benchmark","domains"} or data["benchmark"]!="JANUS-LOGOS-001-R1.4":
        raise ValueError("Wrong external benchmark contract")
    domains=data["domains"]
    if type(domains)!=list or len(domains)!=3:
        raise ValueError("Three independent domains required")
    ids=set();results=[]
    for domain in domains:
        if type(domain)!=dict or set(domain)!={"domain_id","train","validation","test","physical_domain","provider_reference"}:
            raise ValueError("Missing independent scientific provenance")
        if domain["domain_id"] in ids or not isinstance(domain["physical_domain"],str) or not domain["physical_domain"].strip():
            raise ValueError("Repeated or invalid source")
        ids.add(domain["domain_id"])
        train=domain["train"];valid=domain["validation"];test=domain["test"]
        if not isinstance(test,list) or len(test)<10:
            raise ValueError("Insufficient sealed test observations")
        for p in test:
            if type(p)!=list or len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p):
                raise ValueError("Bad private test row")
        predictor_input={"domain_id":domain["domain_id"],"train":train,
                         "validation":valid,"test_x":[x for x,y in test]}
        # Real external evaluation MUST isolate this runner from raw private data.
        predictions=runner(predictor_input)
        if set(predictions).intersection({"test_y","test","ground_truth","labels"}):
            raise ValueError("Prohibited data return from participant")
        if (predictions.get("protocol")!=PROTOCOL or
            predictions.get("domain_id")!=domain["domain_id"] or
            predictions.get("frozen_learner_blob_sha")!="97094ba3ef7461ff1b0eb44541d4a926260c239b" or
            predictions.get("n_test")!=len(test) or
            predictions.get("production_model_promotion_allowed") is not False):
            raise ValueError("Participant returned unapproved protocol or unpinned model")
        bx=r13_witness.choose_baseline(train,valid)
        val_x=[x for x,y in valid];val_y=[y for x,y in valid]
        test_x=[x for x,y in test];test_y=[y for x,y in test]
        baseline_test=r13_witness.rmse(test_y,bx[2](test_x))
        row={
            "domain_id":domain["domain_id"],"physical_domain":domain["physical_domain"],
            "provider_reference":domain["provider_reference"],
            "n_train":len(train),"n_validation":len(valid),"n_sealed_test":len(test),
            "test_source_commitment_sha256":_sha(test),
            "candidate_decision":predictions["decision"],
            "baseline_name":bx[1],
            "baseline_validation_rmse":bx[0],
            "baseline_sealed_rmse":baseline_test,
            "source_truth_disclosed":False
        }
        if predictions["decision"]=="PROPOSE":
            ys=predictions.get("predictions")
            if type(ys)!=list or len(ys)!=len(test) or any(type(v) not in (int,float) or not math.isfinite(v) for v in ys):
                raise ValueError("Invalid participant model prediction vector")
            own=r13_witness.rmse(test_y,ys)
            gain=1-own/baseline_test
            predicted_by_x={x:y for x,y in zip(test_x,ys)}
            # All repeated x should have the same deterministic prediction.
            if any(predicted_by_x[x]!=y for x,y in zip(test_x,ys)):
                raise ValueError("Inconsistent repeated-x predictions")
            ci=r13_witness.bootstrap_gain(test,lambda x:predicted_by_x[x],
                                           lambda x:float(bx[2]([x])[0]))
            row.update({"candidate_sealed_rmse":own,"relative_rmse_gain":gain,
                        "paired_bootstrap_ci95":ci["ci95"],
                        "distinct_test_x_groups":ci["n_independent_test_x"],
                        "pass_5pct_with_positive_lower_ci":gain>=.05 and ci["ci95"][0]>0})
        elif predictions["decision"]=="ABSTAIN":
            if predictions.get("predictions") is not None:
                raise ValueError("Abstention must have null prediction")
            row.update({"candidate_sealed_rmse":None,"relative_rmse_gain":None,
                        "paired_bootstrap_ci95":None,"pass_5pct_with_positive_lower_ci":False})
        else:raise ValueError("Unapproved decision")
        results.append(row)
    if len({d["physical_domain"] for d in results})!=3:
        raise ValueError("Need three unrelated physical domains")
    pass_count=sum(r["pass_5pct_with_positive_lower_ci"] for r in results)
    return {
        "experiment":"JANUS-LOGOS-001","phase":"R1.4",
        "receipt_schema":"JANUS_LOGOS_R14_EVALUATOR_RECEIPT_v1",
        "custodian_benchmark_sha256":_sha(data),
        "three_distinct_real_domains_certified_by_custodian":False,
        "independent_external_evaluation_verified":False,
        "status":"UNSIGNED_DRAFT_NOT_EXTERNAL_PROOF",
        "passed_domain_count":pass_count,
        "scientific_success_gate_met":pass_count==3,
        "production_model_promotion_allowed":False,
        "resamples":2000,"bootstrap_seed":1301,
        "scores":results,
        "privacy_note":"Only aggregate metrics + commitments; no TEST labels or raw measurements released"
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--private-input",required=True,help="Custodian ONLY: do not upload to GitHub")
    p.add_argument("--draft-out",required=True)
    a=p.parse_args()
    secret=json.loads(Path(a.private_input).read_text(encoding="utf-8"))
    outcome=evaluate_custodian_private(secret)
    Path(a.draft_out).write_text(json.dumps(outcome,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":outcome["status"],"passes":outcome["passed_domain_count"],
                      "private_labels_returned":False,"external_witness_confirmed":False}))
if __name__=="__main__":main()
