"""Independent stdlib-only holdout verifier for JANUS LOGOS R1.

Does NOT import r1_data or r1_discover, does NOT fit or choose hypotheses.
Makes new unseen points, reconstructs the predeclared test oracle, and
independently rechecks TRAIN+VALIDATION digest and prediction errors.
This is independent-code/cloud-job validation, NOT a blind external lab.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

IDS=("C01","C02","C03","C04","N01","N02")
ALLOWED=("x","x2","x3","x4","sin_pi_x","cos_pi_x","sin_2pi_x","exp_x","inv1p_x2")
PROTOCOL="JANUS_LOGOS_001_R1_1_0"

def _pseudo_random(split, i):
    z=hashlib.sha256(("N01|"+split+"|"+str(i)).encode()).digest()
    return 2*(int.from_bytes(z[:8],"big") / 18446744073709551616)-1

def oracle(case, x, split, i):
    # Written independently, never imported from the dataset generator.
    if case=="C01":return 3/4+(3/2)*x
    if case=="C02":return -0.25+0.5*x+1.25*x*x
    if case=="C03":return 2/5+(6/5)*math.sin(math.pi*x)
    if case=="C04":return 1/10-x+(3/2)*x*x*x
    if case=="N01":return _pseudo_random(split,i)
    if case=="N02":return -0.1+0.75*x*x+(1.0 if split=="test" else 0.0)
    raise ValueError("Unexpected case")

def reconstruct_train_validation():
    cases=[]
    for cid in IDS:
        xs_train=[-1.0+2.0*i/29 for i in range(30)]
        xs_valid=[-0.97+1.94*i/22 for i in range(23)]
        cases.append({"id":cid,
            "train":[[x,oracle(cid,x,"train",i)] for i,x in enumerate(xs_train)],
            "validation":[[x,oracle(cid,x,"validation",i)] for i,x in enumerate(xs_valid)]})
    return {"experiment":"JANUS-LOGOS-001","phase":"R1","protocol":PROTOCOL,"cases":cases}

def sha_dataset(d):
    return hashlib.sha256(json.dumps(d,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")).hexdigest()

def function(name,x):
    # Separate implementation from the discoverer's prediction function.
    if name=="x":return x
    if name=="x2":return x**2
    if name=="x3":return x**3
    if name=="x4":return x**4
    if name=="sin_pi_x":return math.sin(math.pi*x)
    if name=="cos_pi_x":return math.cos(math.pi*x)
    if name=="sin_2pi_x":return math.sin(math.tau*x)
    if name=="exp_x":return math.exp(x)
    if name=="inv1p_x2":return 1/(1+x*x)
    raise ValueError("Forbidden expression")

def predict(model,x):
    if not isinstance(model,dict) or set(model)!={"basis","coefficients"}:
        raise ValueError("Unexpected model fields")
    bs=model["basis"];cs=model["coefficients"]
    if not isinstance(bs,list) or len(bs)<1 or len(bs)>2 or len(set(bs))!=len(bs):
        raise ValueError("Invalid basis list")
    if not set(bs).issubset(ALLOWED) or bs!=sorted(bs,key=ALLOWED.index):
        raise ValueError("Unfrozen or reordered basis")
    if not isinstance(cs,list) or len(cs)!=len(bs)+1:
        raise ValueError("Invalid coefficient dimension")
    if any(type(c) not in (int,float) or not math.isfinite(c) or abs(c)>10000 for c in cs):
        raise ValueError("Non-finite/huge coefficient")
    return cs[0]+sum(c*function(b,x) for b,c in zip(bs,cs[1:]))

def score(model,points):
    return math.sqrt(sum((predict(model,x)-y)**2 for x,y in points)/len(points))

def test_points(cid):
    if cid=="N02":
        xs=[1.3+0.4*i/30 for i in range(31)]
    else:
        xs=[-1.4+2.8*i/30 for i in range(31)]
    return [(x,oracle(cid,x,"test",i)) for i,x in enumerate(xs)]

def verify(envelope):
    if not isinstance(envelope,dict) or set(envelope)!={
        "experiment","phase","protocol","evidence_type","dataset_sha256",
        "data_access","cases","scientific_claim_ceiling"}:
        raise ValueError("Altered envelope contract")
    if envelope["experiment"]!="JANUS-LOGOS-001" or envelope["phase"]!="R1" or envelope["protocol"]!=PROTOCOL:
        raise ValueError("Incorrect experiment contract")
    if envelope["data_access"]!="TRAIN_AND_VALIDATION_ONLY__NO_TEST":
        raise ValueError("Leakage contract violated")
    if envelope["dataset_sha256"]!=sha_dataset(reconstruct_train_validation()):
        raise ValueError("Dataset SHA does not match independent reconstruction")
    candidates=envelope["cases"]
    if [z.get("id") for z in candidates]!=list(IDS):
        raise ValueError("Missing or changed cases")
    training={d["id"]:d["train"] for d in reconstruct_train_validation()["cases"]}
    validation={d["id"]:d["validation"] for d in reconstruct_train_validation()["cases"]}
    results=[]
    for row in candidates:
        if row["decision"] not in ("PROPOSE","ABSTAIN"):
            raise ValueError("Invalid decision")
        allowed={"id","decision","validation_baseline_rmse","validation_rmse",
                 "validation_nrmse","selection","reason","model"}
        if not set(row).issubset(allowed):raise ValueError("Unapproved candidate fields")
        cid=row["id"]
        if cid=="N01":
            if row["decision"]!="ABSTAIN" or "model" in row:
                raise ValueError("Noise-only negative control claimed as discovered")
            results.append({"case":cid,"decision":"REJECTED_NOISE_CONTROL","pass":True})
            continue
        if row["decision"]!="PROPOSE" or "model" not in row:
            raise ValueError("True-law / regime-shift diagnostic was not proposed: "+cid)
        model=row["model"]
        pts_train=training[cid];pts_val=validation[cid];pts_test=test_points(cid)
        train_mean=sum(y for x,y in pts_train)/len(pts_train)
        baseline_val=math.sqrt(sum((y-train_mean)**2 for x,y in pts_val)/len(pts_val))
        baseline_test=math.sqrt(sum((y-train_mean)**2 for x,y in pts_test)/len(pts_test))
        validation_error=score(model,pts_val)
        if abs(row["validation_baseline_rmse"]-baseline_val)>1e-7:
            raise ValueError("Validation baseline mismatch: "+cid)
        if abs(row["validation_rmse"]-validation_error)>1e-7:
            raise ValueError("Validation report inconsistent with frozen model: "+cid)
        if validation_error/baseline_val>=0.08:
            raise ValueError("Candidate did not survive validation: "+cid)
        holdout_error=score(model,pts_test)
        ratio=holdout_error/baseline_test
        if cid=="N02":
            if ratio<=0.25:
                raise ValueError("Out-of-domain shift negative control not rejected")
            results.append({"case":cid,"decision":"REJECTED_REGIME_SHIFT","test_nrmse":ratio,"pass":True})
        else:
            if ratio>=0.06:
                raise ValueError("Positive scientific-law test failed on fresh holdout: "+cid)
            results.append({"case":cid,"decision":"PASS_HOLDOUT","test_nrmse":ratio,"pass":True})
    return {
        "experiment":"JANUS-LOGOS-001","phase":"R1",
        "verdict":"PASS_SCOPED_SYNTHETIC_SYMBOLIC_LAW_DISCOVERY",
        "positive_holdout_passes":4,"negative_controls_rejected":2,
        "cases":results,
        "independence":"SEPARATE_STD_LIB_WITNESS_NO_DISCOVERER_IMPORT_PUBLIC_SOURCES",
        "scientific_ceiling":"SYNTHETIC_EQUATION_RECOVERY_NOT_NEW_PHYSICS_NOT_DIVINE_PROOF_NOT_P_VS_NP"}

def tamper_tests(envelope):
    original=verify(envelope)
    trials={}
    for name in ("altered_digest","altered_formula","forbidden_expression","noise_false_positive"):
        tampered=copy.deepcopy(envelope)
        if name=="altered_digest":tampered["dataset_sha256"]="0"*64
        if name=="altered_formula":tampered["cases"][0]["model"]["coefficients"][1]+=2.0
        if name=="forbidden_expression":tampered["cases"][0]["model"]["basis"][0]="__import__"
        if name=="noise_false_positive":
            tampered["cases"][4]["decision"]="PROPOSE"
            tampered["cases"][4]["model"]={"basis":["x"],"coefficients":[0,0]}
        try:verify(tampered)
        except (ValueError,TypeError,KeyError,ZeroDivisionError,OverflowError):
            trials[name]="REJECTED"
        else:raise AssertionError("Tamper was accepted: "+name)
    original["tamper_trials"]=trials
    return original

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--candidate",required=True)
    p.add_argument("--out")
    p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    d=json.loads(Path(args.candidate).read_text(encoding="utf-8"))
    result=tamper_tests(d) if args.self_test else verify(d)
    raw=json.dumps(result,indent=2,sort_keys=True)+"\n"
    if args.out:Path(args.out).write_text(raw,encoding="utf-8")
    print(raw)

if __name__=="__main__":main()
