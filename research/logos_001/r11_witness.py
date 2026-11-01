"""Independent scientific witness for NIST real-measurement R1.1.

Imports original observed data ONLY. Does not import discoverer or its fitting
code. Recomputes model predictions and independently fits ordinary baselines.
The public data and their published model family are not cryptographically blind.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
import sys
from pathlib import Path

import r11_data

IDS=("PONTIUS","NORRIS","PONTIUS_SHUFFLED_VAL","NORRIS_SHUFFLED_VAL")
BASIS=("x","x2","x3","sin_pi_x","cos_pi_x")

def basis_value(n,x):
    if n=="x":return x
    if n=="x2":return x**2
    if n=="x3":return x**3
    if n=="sin_pi_x":return math.sin(math.pi*x)
    if n=="cos_pi_x":return math.cos(math.pi*x)
    raise ValueError("Unapproved symbolic term")

def model_predict(m,x):
    if type(m)!=dict or set(m)!={"basis","coefficients"}:
        raise ValueError("Noncanonical model")
    terms=m["basis"];coef=m["coefficients"]
    if not isinstance(terms,list) or not (1<=len(terms)<=2) or len(set(terms))!=len(terms) or terms!=sorted(terms,key=BASIS.index):
        raise ValueError("Model vocabulary/order/dimension")
    if any(t not in BASIS for t in terms) or len(coef)!=len(terms)+1 or any(type(c) not in (int,float) or not math.isfinite(c) for c in coef):
        raise ValueError("Illegal coefficients")
    return float(coef[0])+math.fsum(float(c)*basis_value(t,x) for c,t in zip(coef[1:],terms))

def calc_rmse(points,predict):
    return math.sqrt(math.fsum((predict(x)-y)**2 for x,y in points)/len(points))

def independent_baseline_fit(points,degree):
    # Different algorithm from discovery fit: solve direct 1x1/2x2/3x3
    # with row-pivot Gaussian elimination and no shared code.
    a=[[math.fsum(x**(i+j) for x,y in points) for j in range(degree+1)]
        for i in range(degree+1)]
    b=[math.fsum((x**i)*y for x,y in points) for i in range(degree+1)]
    for i in range(degree+1):
        pivot=max(range(i,degree+1),key=lambda k:abs(a[k][i]))
        if abs(a[pivot][i])<1e-13:raise ValueError("Degenerate benchmark")
        a[i],a[pivot]=a[pivot],a[i];b[i],b[pivot]=b[pivot],b[i]
        for j in range(i+1,degree+1):
            fac=a[j][i]/a[i][i]
            for k in range(i,degree+1):a[j][k]-=fac*a[i][k]
            b[j]-=fac*b[i]
    c=[0.0]*(degree+1)
    for i in reversed(range(degree+1)):
        c[i]=(b[i]-math.fsum(a[i][j]*c[j] for j in range(i+1,degree+1)))/a[i][i]
    return c

def baseline_models(train):
    mean=math.fsum(y for x,y in train)/len(train)
    models={"CONSTANT_MEAN":lambda x:mean}
    for deg,label in ((1,"LINEAR_OLS"),(2,"QUADRATIC_OLS")):
        c=independent_baseline_fit(train,deg)
        models[label]=lambda x,c=c:math.fsum(v*(x**i) for i,v in enumerate(c))
    return models

def check(candidate):
    if type(candidate)!=dict or set(candidate)!={"experiment","phase","generator","source_sha256","cases","provenance","scientific_limit"}:
        raise ValueError("Noncanonical evidence envelope")
    if candidate["experiment"]!="JANUS-LOGOS-001" or candidate["phase"]!="R1.1" or candidate["generator"]!="REAL_NIST_STRD_TRAIN_VALIDATION_ONLY":
        raise ValueError("Wrong provenance")
    d=r11_data.discovery()
    raw=json.dumps(d,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()
    if candidate["source_sha256"]!=hashlib.sha256(raw).hexdigest():
        raise ValueError("Input/dataset SHA mismatch")
    if [c.get("id") for c in candidate["cases"]]!=list(IDS):raise ValueError("Frozen case list changed")
    case_by_id={v["id"]:v for v in d["datasets"]}
    results=[]
    for c in candidate["cases"]:
        id=c["id"]
        if not set(c).issubset({"id","decision","validation_rmse","validation_constant_baseline_rmse","validation_nrmse","rule","model","reason"}):
            raise ValueError("Unexpected candidate fields")
        if c["decision"] not in ("PROPOSE","ABSTAIN") or c["rule"]!="TRAIN_OLS_PLUS_VALIDATION_RMSE_COMPLEXITY_0025":
            raise ValueError("Unfrozen decision mechanism")
        p=case_by_id[id]
        train=p["train"];valid=p["validation"]
        mu=math.fsum(y for x,y in train)/len(train)
        const_val=calc_rmse(valid,lambda x:mu)
        if abs(const_val-c["validation_constant_baseline_rmse"])>1e-7*max(1,const_val):
            raise ValueError("Constant baseline mismatch")
        if id.endswith("_SHUFFLED_VAL"):
            if c["decision"]!="ABSTAIN" or "model" in c:
                raise ValueError("Corrupted pairings falsely treated as physical law")
            results.append({"dataset":id,"decision":"REJECTED_SHUFFLED_VALIDATION","status":"PASS_NEGATIVE_CONTROL"})
            continue
        if c["decision"]=="ABSTAIN":
            if "model" in c or c.get("reason")!="FAILED_FROZEN_VALIDATION_GATE":
                raise ValueError("Abstention contract")
            results.append({"dataset":id,"decision":"ABSTAIN","status":"NO_SCIENTIFIC_PROMOTION"})
            continue
        if "model" not in c:raise ValueError("Missing model")
        m=c["model"]
        err_val=calc_rmse(valid,lambda x:model_predict(m,x))
        if abs(err_val-c["validation_rmse"])>1e-6*max(1,err_val):
            raise ValueError("Evidence does not match coefficients")
        if abs(err_val/const_val-c["validation_nrmse"])>1e-6 or err_val/const_val>=0.20:
            raise ValueError("Validation not supported")
        all_splits=r11_data.split(id)
        test=all_splits["test"]
        baselines=baseline_models(train)
        metrics={}
        for name,model in baselines.items():
            metrics[name]={"validation_rmse":calc_rmse(valid,model),"test_rmse":calc_rmse(test,model)}
        chosen=min(metrics,key=lambda k:(metrics[k]["validation_rmse"],k))
        y_scale=math.sqrt(math.fsum((y-mu)**2 for x,y in train)/len(train))
        own_test=calc_rmse(test,lambda x:model_predict(m,x))
        improvement=1-own_test/metrics[chosen]["test_rmse"]
        results.append({
            "dataset":id,"decision":"PROPOSE","test_rmse":own_test,
            "test_rmse_normalized_by_training_y_std":own_test/y_scale,
            "test_n":len(test),"validation_n":len(valid),"train_n":len(train),
            "benchmarks":metrics,"best_baseline_selected_on_validation":chosen,
            "holdout_improvement_vs_selected_baseline":improvement,
            "comparison":("IMPROVEMENT_5PCT_OR_MORE" if improvement>=0.05 else
                          ("WITHIN_5PCT_OF_BENCHMARK" if improvement>=-0.05 else "WORSE_THAN_BENCHMARK_5PCT")),
            "interpretation":"OBSERVED_CALIBRATION_PREDICTION_ONLY__NO_NOVEL_PHYSICS"})
    return {"experiment":"JANUS-LOGOS-001","phase":"R1.1",
            "witness":"SEPARATE_STD_LIB_HOLDOUT_AND_INDEPENDENT_BASELINE_FIT",
            "source":"NIST_OBSERVED_CALIBRATION_DATA_PUBLIC",
            "results":results,
            "positive_real_cases_evaluated":sum(v["decision"]=="PROPOSE" for v in results[:2]),
            "corrupted_pairing_controls_rejected":2,
            "verdict":"PASS_SCIENTIFIC_EVALUATION_INTEGRITY",
            "scientific_ceiling":"OBSERVED_DATA_NOT_UNKNOWN_PHYSICS_NOT_EXTERNAL_BLIND_LAB_NOT_DIVINE_PROOF"}

def tamper_checks(candidate):
    trials={}
    for target in ("bad_digest","forbidden_model_term","coeff_injection","false_negative_promotion"):
        altered=copy.deepcopy(candidate)
        if target=="bad_digest":altered["source_sha256"]="f"*64
        if target=="forbidden_model_term":
            c=altered["cases"][0];c["decision"]="PROPOSE";c["model"]={"basis":["__import__"],"coefficients":[0.0,1.0]}
        if target=="coeff_injection":
            c=altered["cases"][0];c["decision"]="PROPOSE"
            if "model" in c:c["model"]["coefficients"][0]+=100.
            else:c["model"]={"basis":["x"],"coefficients":[100.0,0.0]}
        if target=="false_negative_promotion":
            c=altered["cases"][-1]
            c["decision"]="PROPOSE";c["model"]={"basis":["x"],"coefficients":[0.,1.]}
        try:check(altered)
        except (ValueError,TypeError,KeyError,IndexError):
            trials[target]="REJECTED"
        else:raise AssertionError("EVIDENCE_TAMPER_ACCEPTED:"+target)
    return trials

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--candidate",required=True);p.add_argument("--out",required=True);p.add_argument("--self-test",action="store_true")
    a=p.parse_args();candidate=json.loads(Path(a.candidate).read_text(encoding="utf-8"))
    obj=check(candidate)
    if a.self_test:obj["tamper_checks"]=tamper_checks(candidate)
    Path(a.out).write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(obj,sort_keys=True,indent=2))
if __name__=="__main__":main()
