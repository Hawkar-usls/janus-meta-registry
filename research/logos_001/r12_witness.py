"""R1.2 independent NIST observed-data witness and negative-control falsifier.

No imports from discovery algorithm; holdout labels from pinned source fixtures.
An integrity PASS is not a claim that proposed models beat baselines.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import r12_data

SHA_SOURCE={"ECKERLE4":"2d0d8bf3f139925ebf78e201b80079ea17d36848",
            "CHWIRUT2":"03703de739d642ff62364312f727ac4e8740c1bd"}
IDS=("ECKERLE4","CHWIRUT2","ECKERLE4_SHUFFLED_VALIDATION","CHWIRUT2_SHUFFLED_VALIDATION")

def verify_source_git_blobs():
    for name in r12_data.NAMES:
        raw=(r12_data.HERE/r12_data.FILE[name]).read_bytes()
        digest=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
        if digest!=SHA_SOURCE[name]:raise ValueError("Original dataset file does not match independently retrieved source")

def _polynomial_predict(coeff,x):
    return math.fsum(c*(x**i) for i,c in enumerate(coeff))

def baseline_fit(rows,degree):
    # Independent implementation, not a call into discoverer's fit.
    n=degree+1
    aa=[[math.fsum(x**(i+j) for x,y in rows) for j in range(n)] for i in range(n)]
    bb=[math.fsum(y*x**i for x,y in rows) for i in range(n)]
    for k in range(n):
        pivot=max(range(k,n),key=lambda i:abs(aa[i][k]))
        if abs(aa[pivot][k])<1e-13:raise ValueError("Singular comparison fit")
        aa[k],aa[pivot]=aa[pivot],aa[k];bb[k],bb[pivot]=bb[pivot],bb[k]
        for i in range(k+1,n):
            fact=aa[i][k]/aa[k][k]
            for j in range(k,n):aa[i][j]-=fact*aa[k][j]
            bb[i]-=fact*bb[k]
    coeff=[0.]*n
    for i in reversed(range(n)):
        coeff[i]=(bb[i]-math.fsum(aa[i][j]*coeff[j] for j in range(i+1,n)))/aa[i][i]
    return coeff

def candidate_predict(m,x):
    if not isinstance(m,dict) or set(m)!={"template","coefficients"}:raise ValueError("Unexpected model")
    t=m["template"];c=m["coefficients"]
    if not isinstance(t,dict) or type(c)!=list or any(type(v) not in (int,float) or not math.isfinite(v) for v in c):
        raise ValueError("Untrusted candidate")
    family=t.get("family")
    if family=="poly":
        if set(t)!={"family","degree"} or type(t["degree"])!=int or t["degree"] not in range(5) or len(c)!=t["degree"]+1:
            raise ValueError("Wrong polynomial shape")
        return _polynomial_predict(c,x)
    if family=="gaussian":
        if set(t)!={"family","center","width"} or t["center"] not in tuple(i/40 for i in range(41)) or t["width"] not in (.02,.03,.04,.05,.06,.08,.1,.12,.15,.2,.3,.4,.6):
            raise ValueError("Unfrozen gaussian")
        value=math.exp(-.5*((x-t["center"])/t["width"])**2)
    elif family=="exp_decay":
        if set(t)!={"family","rate"} or t["rate"] not in (.25,.5,1,1.5,2,3,4,6,8,12,16,24):
            raise ValueError("Unfrozen exponential")
        value=math.exp(-t["rate"]*x)
    elif family=="rational_exp":
        if set(t)!={"family","rate","offset"} or t["rate"] not in (0,.25,.5,1,1.5,2,3,4,6,8,12) or t["offset"] not in (.02,.04,.07,.1,.15,.25,.4,.6,1):
            raise ValueError("Unfrozen rational exponential")
        value=math.exp(-t["rate"]*x)/(x+t["offset"])
    else:raise ValueError("Forbidden model family")
    if len(c)!=2:raise ValueError("Wrong model dimension")
    return c[0]+c[1]*value

def rmse(rows,predict):
    if not rows:raise ValueError("Empty evidence")
    return math.sqrt(math.fsum((predict(x)-y)**2 for x,y in rows)/len(rows))

def verify(receipt):
    verify_source_git_blobs()
    if type(receipt)!=dict or set(receipt)!={"experiment","phase","source_sha256","algorithm","cases","input_access","scientific_claim"}:
        raise ValueError("Evidence contract mismatch")
    if receipt["experiment"]!="JANUS-LOGOS-001" or receipt["phase"]!="R1.2" or receipt["algorithm"]!="GROUPED_TRAIN_3FOLD_CV_VALIDATION_COMPLEXITY_GATE" or receipt["input_access"]!="TRAIN_VALIDATION_ONLY_NO_HOLDOUT":
        raise ValueError("Wrong scientific procedure")
    input_data=r12_data.discovery()
    if receipt["source_sha256"]!=r12_data.canonical_sha(input_data):
        raise ValueError("Reconstructed TRAIN+VALIDATION hash mismatch")
    cases=receipt["cases"]
    if [z.get("id") for z in cases]!=list(IDS):raise ValueError("Reordered / missing research cases")
    by_id={v["id"]:v for v in input_data["cases"]}
    results=[]
    for record in cases:
        id=record["id"]
        if record.get("decision") not in ("PROPOSE","ABSTAIN"):raise ValueError("Unknown decision")
        if not set(record).issubset({"id","decision","validation_rmse","baseline_validation_rmse","baseline_degree_selected","selected_family","selection_score","training_cv_rmse","model","reason"}):
            raise ValueError("Extra evidence fields")
        source=by_id[id];train=source["train"];validation=source["validation"]
        base=[]
        for degree in range(4):
            c=baseline_fit(train,degree)
            val=rmse(validation,lambda x,c=c:_polynomial_predict(c,x))
            base.append((val,degree,c))
        best=min(base)
        if abs(record["baseline_validation_rmse"]-best[0])>1e-7*max(1,best[0]):
            raise ValueError("Baseline validation score falsified")
        if record["baseline_degree_selected"]!=best[1]:raise ValueError("Baseline model label incorrect")
        if id.endswith("_SHUFFLED_VALIDATION"):
            if record["decision"]!="ABSTAIN" or "model" in record:
                raise ValueError("False law discovered from scrambled validation data")
            results.append({"id":id,"status":"REJECTED_SHUFFLED_CONTROL"})
            continue
        splits=r12_data.split(id)
        baseline_test=rmse(splits["test"],lambda x,c=best[2]:_polynomial_predict(c,x))
        result={"id":id,"baseline_selected_by_validation":f"POLY_DEGREE_{best[1]}",
                "baseline_validation_rmse":best[0],"baseline_test_rmse":baseline_test,
                "n_train":len(train),"n_validation":len(validation),"n_test":len(splits["test"])}
        if record["decision"]=="ABSTAIN":
            if "model" in record or record.get("reason")!="NO_2PCT_VALIDATION_GAIN_VS_SIMPLE_BASELINE":
                raise ValueError("Invalid abstention evidence")
            result.update({"decision":"ABSTAIN","status":"NO_CANDIDATE_ADVANTAGE_CLAIM"})
        else:
            model=record.get("model")
            if not model:raise ValueError("Missing proposed equation")
            if record["selected_family"]!=model["template"]["family"]:raise ValueError("Changed selected family")
            val_error=rmse(validation,lambda x:candidate_predict(model,x))
            if abs(val_error-record["validation_rmse"])>1e-7*max(1,val_error) or not (val_error<.98*best[0]):
                raise ValueError("Claimed training-validation success is inconsistent")
            test_error=rmse(splits["test"],lambda x:candidate_predict(model,x))
            gain=1-test_error/baseline_test if baseline_test>0 else float("-inf")
            result.update({"decision":"PROPOSE","selected_family":record["selected_family"],
                           "test_rmse":test_error,"test_improvement_vs_baseline":gain,
                           "status":"BEAT_BASELINE_5PCT" if gain>=.05 else "NOT_BETTER_5PCT"})
        results.append(result)
    wins=[r for r in results if r["id"] in r12_data.NAMES and r.get("status")=="BEAT_BASELINE_5PCT"]
    return {"experiment":"JANUS-LOGOS-001","phase":"R1.2",
            "integrity_verdict":"PASS_CODE_AND_SOURCE_INTEGRITY",
            "scientific_performance":"BOTH_DATASETS_BEAT_BASELINE_GE_5PCT" if len(wins)==2 else "NOT_COMPETITIVE_IN_ALL_PREDECLARED_DATASETS",
            "positive_datasets_beating_baseline_5pct":len(wins),
            "negative_controls_rejected":2,
            "production_model_promotion_allowed":False,
            "independence":"SEPARATE_CODE_AND_GITHUB_RUNNER_NOT_SECRET_TEST_OR_EXTERNAL_LAB",
            "source_git_blobs":SHA_SOURCE,
            "results":results,
            "scientific_limit":"REAL_PUBLIC_NIST_DATA_NOT_NEW_PHYSICS_NOT_DIVINE_PROOF_NOT_P_EQUALS_NP"}

def tamper_tests(receipt):
    trials={}
    for case in ("hash","coeff","forbidden_family","fake_negative"):
        changed=copy.deepcopy(receipt)
        if case=="hash":changed["source_sha256"]="0"*64
        elif case=="coeff":
            z=changed["cases"][0]
            if z["decision"]=="PROPOSE":z["model"]["coefficients"][0]+=10.
            else:z["decision"]="PROPOSE";z["model"]={"template":{"family":"poly","degree":1},"coefficients":[10,0]}
        elif case=="forbidden_family":
            z=changed["cases"][0];z["decision"]="PROPOSE"
            z["model"]={"template":{"family":"system","command":"eval"},"coefficients":[1,2]}
        else:
            z=changed["cases"][-1]
            z["decision"]="PROPOSE"
            z["model"]={"template":{"family":"poly","degree":1},"coefficients":[0,1]}
        try:verify(changed)
        except (ValueError,TypeError,KeyError,IndexError,AssertionError):trials[case]="REJECTED"
        else:raise AssertionError("Tamper falsely accepted: "+case)
    return trials

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--candidate",required=True);p.add_argument("--out",required=True)
    p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    c=json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    result=verify(c)
    if args.self_test:result["tamper_checks"]=tamper_tests(c)
    Path(args.out).write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True,indent=2))
if __name__=="__main__":main()
