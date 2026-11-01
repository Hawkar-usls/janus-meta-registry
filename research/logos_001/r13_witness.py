"""Independent R1.3 witness: strong baselines, uncertainty and falsifiers.

Only witness, not discoverer, may access TEST. Baseline selection uses
TRAIN/VALIDATION only; no post hoc TEST-based model selection. TEST group
paired bootstrap describes conditional sampling uncertainty, not a blind
external experiment or laboratory replication.
Requires numpy 1.26.4, scipy 1.14.1, scikit-learn 1.5.2.
"""
import argparse
import copy
import json
import math
import random
from pathlib import Path
import numpy as np
from scipy.interpolate import PchipInterpolator, UnivariateSpline
from sklearn.ensemble import RandomForestRegressor
from sklearn.kernel_ridge import KernelRidge
from sklearn.linear_model import Ridge
import r13_data
from r12_witness import candidate_predict

NAMES=r13_data.NAMES
IDS=NAMES+tuple(n+"_SHUFFLED_VALIDATION" for n in NAMES)
B=2000
RNG_SEED=1301

def rmse(y,pred):
    if len(y)!=len(pred):raise ValueError("Score dimensions")
    a=np.asarray(y,dtype=float);b=np.asarray(pred,dtype=float)
    if not np.all(np.isfinite(b)):return float("inf")
    return float(np.sqrt(np.mean((a-b)**2)))

def baseline_factory(train):
    xx=np.asarray([x for x,y in train]); yy=np.asarray([y for x,y in train])
    xr=xx.reshape(-1,1)
    for degree in range(6):
        features=np.column_stack([xx**d for d in range(degree+1)])
        coef=np.linalg.lstsq(features,yy,rcond=None)[0]
        yield (f"POLY{degree}",lambda q,coef=coef:sum(c*np.asarray(q)**d for d,c in enumerate(coef)))
    ridge=Ridge(alpha=0.01,fit_intercept=True)
    ridge.fit(np.column_stack([xx**d for d in range(1,6)]),yy)
    yield ("RIDGE_POLY5_A001",lambda q,m=ridge:m.predict(np.column_stack([np.asarray(q)**d for d in range(1,6)])))
    groups={}
    for x,y in train:groups.setdefault(x,[]).append(y)
    ux=np.array(sorted(groups))
    uy=np.array([float(np.mean(groups[x])) for x in ux])
    if len(ux)>3:
        pchip=PchipInterpolator(ux,uy,extrapolate=True)
        yield ("PCHIP_GROUPED",lambda q,m=pchip:m(np.asarray(q)))
        sy=float(np.std(yy))
        for weight in (.01,.1,1.):
            smoothing=len(ux)*(sy*weight)**2
            try:spline=UnivariateSpline(ux,uy,s=smoothing,k=3)
            except (ValueError,RuntimeError):continue
            yield (f"SMOOTH_SPLINE_{weight}",lambda q,m=spline:m(np.asarray(q)))
    for leaf in (1,3,5):
        m=RandomForestRegressor(n_estimators=300,min_samples_leaf=leaf,
                                random_state=RNG_SEED,n_jobs=1)
        m.fit(xr,yy)
        yield (f"RF300_LEAF{leaf}",lambda q,m=m:m.predict(np.asarray(q).reshape(-1,1)))
    for gamma in (.5,2.,8.,32.):
        for alpha in (.001,.1,1.):
            m=KernelRidge(kernel="rbf",gamma=gamma,alpha=alpha)
            m.fit(xr,yy)
            yield (f"KRR_RBF_G{gamma}_A{alpha}",
                   lambda q,m=m:m.predict(np.asarray(q).reshape(-1,1)))

def choose_baseline(train,validation):
    vx=[x for x,y in validation];vy=[y for x,y in validation]
    candidates=[]
    for name,predict in baseline_factory(train):
        try:val=rmse(vy,predict(vx))
        except (OverflowError,ValueError,ZeroDivisionError,RuntimeError):continue
        if math.isfinite(val):candidates.append((val,name,predict))
    if not candidates:raise ValueError("Baseline suite failed")
    return min(candidates,key=lambda z:(z[0],z[1]))

def bootstrap_gain(rows,candidate,baseline):
    # Cluster sampling by unique instrument x avoids treating repeated x as independent.
    groups={}
    for x,y in rows:
        groups.setdefault(x,[]).append((
            (float(candidate(x))-y)**2,
            (float(baseline(x))-y)**2))
    vals=list(groups.values())
    rng=random.Random(RNG_SEED)
    out=[]
    for _ in range(B):
        sample=[vals[rng.randrange(len(vals))] for k in range(len(vals))]
        sq1=[v[0] for group in sample for v in group]
        sq2=[v[1] for group in sample for v in group]
        b=math.sqrt(math.fsum(sq2)/len(sq2))
        if b<=1e-14:continue
        a=math.sqrt(math.fsum(sq1)/len(sq1))
        out.append(1-a/b)
    if len(out)!=B:raise ValueError("Invalid bootstrap baseline")
    out.sort()
    return {"method":"PAIRED_DISTINCT_X_GROUP_BOOTSTRAP",
            "resamples":B,"seed":RNG_SEED,
            "ci95":[out[int(.025*B)],out[int(.975*B)-1]],
            "p_bootstrap_gain_le_zero":sum(x<=0 for x in out)/B,
            "n_independent_test_x":len(vals),
            "interpretation":"Conditional fixed-model test-group uncertainty; not external blind replication."}

def verify(obj):
    if not isinstance(obj,dict) or set(obj)!={
        "experiment","phase","algorithm","source_sha256",
        "input_access","cases","scientific_status"}:
        raise ValueError("Changed evidence envelope")
    if (obj["experiment"],obj["phase"],obj["algorithm"],obj["input_access"])!=(
        "JANUS-LOGOS-001","R1.3","FROZEN_R12_TRAIN_CV_VALIDATION_SELECTION",
        "TRAIN_VALIDATION_ONLY_NO_HOLDOUT"):
        raise ValueError("Unexpected provenance or evaluation authority")
    d=r13_data.discovery_input()
    if r13_data.canonical_sha(d)!=obj["source_sha256"]:
        raise ValueError("Reconstructed data SHA mismatch")
    if [c.get("id") for c in obj["cases"]]!=list(IDS):
        raise ValueError("Reordered or missing dataset/controls")
    source={c["id"]:c for c in d["cases"]}
    results=[]
    for row in obj["cases"]:
        ident=row["id"];case=source[ident]
        if row.get("decision") not in ("PROPOSE","ABSTAIN"):
            raise ValueError("Unknown decision")
        if not set(row).issubset({"id","decision","validation_rmse",
            "baseline_validation_rmse","baseline_degree_selected","selected_family",
            "selection_score","training_cv_rmse","model","reason"}):
            raise ValueError("Extra fields in untrusted model proposal")
        if ident.endswith("_SHUFFLED_VALIDATION"):
            if row["decision"]!="ABSTAIN" or "model" in row:
                raise ValueError("Corrupted validation pairing incorrectly promoted")
            results.append({"dataset":ident,"decision":"ABSTAIN","negative_control":"REJECTED"})
            continue
        train=case["train"];validation=case["validation"]
        bx=choose_baseline(train,validation)
        x_val=[x for x,y in validation];y_val=[y for x,y in validation]
        test=r13_data.split(ident)["test"]
        test_x=[x for x,y in test];test_y=[y for x,y in test]
        baseline_test_rmse=rmse(test_y,bx[2](test_x))
        summary={"dataset":ident,"n_train":len(train),"n_validation":len(validation),
            "n_test":len(test),"strong_baseline":bx[1],
            "strong_baseline_validation_rmse":bx[0],
            "strong_baseline_test_rmse":baseline_test_rmse}
        if row["decision"]=="ABSTAIN":
            if "model" in row or row.get("reason")!="NO_2PCT_VALIDATION_GAIN_VS_SIMPLE_BASELINE":
                raise ValueError("Unverified abstention contract")
            summary["decision"]="ABSTAIN";summary["status"]="NO_EQUATION_PROPOSED"
            results.append(summary);continue
        model=row.get("model")
        if not isinstance(model,dict) or row["selected_family"]!=model["template"].get("family"):
            raise ValueError("Wrong candidate")
        original_v=rmse(y_val,[candidate_predict(model,x) for x in x_val])
        if (abs(original_v-row["validation_rmse"])>1e-7*max(1,original_v)
                or original_v>=.98*row["baseline_validation_rmse"]):
            raise ValueError("Candidate not supported by frozen validation")
        candidate_test_rmse=rmse(test_y,[candidate_predict(model,x) for x in test_x])
        if baseline_test_rmse<=1e-14:raise ValueError("Near-zero baseline invalid ratio")
        gain=1-candidate_test_rmse/baseline_test_rmse
        ci=bootstrap_gain(test,lambda x:candidate_predict(model,x),lambda x:float(bx[2]([x])[0]))
        summary.update({"decision":"PROPOSE","model_family":row["selected_family"],
            "candidate_validation_rmse":original_v,"candidate_test_rmse":candidate_test_rmse,
            "test_rmse_gain":gain,"gain_ci":ci,
            "status":"POINT_GAIN_5PCT_AND_LOWER_CI_GT_ZERO"
                     if gain>=.05 and ci["ci95"][0]>0 else
                     "INSUFFICIENT_OR_NEGATIVE_GAIN"})
        results.append(summary)
    success=sum(z.get("status")=="POINT_GAIN_5PCT_AND_LOWER_CI_GT_ZERO" for z in results)
    return {"experiment":"JANUS-LOGOS-001","phase":"R1.3",
        "integrity":"PASS_SOURCE_AND_PROPOSAL_CHECKS",
        "scientific_verdict":"ALL_THREE_STRONG_BASELINE_AND_CI_GATES_PASS"
                              if success==3 else "NOT_ALL_THREE_COMPETITIVE",
        "successes":success,"total_real_datasets":3,
        "negative_controls_rejected":3,
        "production_model_promotion_allowed":False,
        "results":results,
        "scientific_scope":"PUBLIC_OBSERVED_NIST_NOT_EXTERNAL_SEALED_DATA_NOT_NEW_PHYSICS_NOT_DIVINE_PROOF"}

def tamper_checks(obj):
    checked={}
    for label in ("digest","model_coefficient","model_injection","negative_promotion"):
        altered=copy.deepcopy(obj);case=altered["cases"][0]
        if label=="digest":altered["source_sha256"]="0"*64
        elif label=="model_coefficient":
            if case["decision"]=="PROPOSE":case["model"]["coefficients"][0]+=999
            else:case["decision"]="PROPOSE";case["model"]={"template":{"family":"poly","degree":1},"coefficients":[999,1]}
        elif label=="model_injection":
            case["decision"]="PROPOSE"
            case["model"]={"template":{"family":"exec","code":"bad"},"coefficients":[0,1]}
        else:
            case=altered["cases"][-1]
            case["decision"]="PROPOSE"
            case["model"]={"template":{"family":"poly","degree":1},"coefficients":[0,1]}
        try:verify(altered)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError,ZeroDivisionError):
            checked[label]="REJECTED"
        else:raise AssertionError("Evidence tamper accepted: "+label)
    return checked

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--candidate",required=True);p.add_argument("--out",required=True)
    p.add_argument("--self-test",action="store_true")
    a=p.parse_args()
    obj=json.loads(Path(a.candidate).read_text(encoding="utf-8"))
    result=verify(obj)
    if a.self_test:result["tamper_checks"]=tamper_checks(obj)
    Path(a.out).write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True,indent=2))
if __name__=="__main__":main()
