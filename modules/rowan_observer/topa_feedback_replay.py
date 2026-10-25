#!/usr/bin/env python3
"""TOPA independent arithmetic replay for Rowan incremental feedback weights.

Never imports trainer, never accesses Rowan and never spends credits. The
2x2 ridge weights are recalculated from verified evidence via scalar algebra.
"""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path

BASE=Path("data/rowan")
TRAIN=("G53A","G48D","E27F","W38L","K13N","G64Q")
HELDOUT=("Q44V","E42H")
PIN="ca355a655381c95fe899d61a406251e0cd17d68bbabe287651d526fdeb821f87"

class TOPAHold(ValueError):pass

def f(v):
    if type(v) not in (int,float) or not math.isfinite(v):
        raise TOPAHold("NONFINITE_EVIDENCE")
    return float(v)

def review(model,receipt):
    if model.get("schema_id")!="janus.rowan.bbc1.provider_feedback_shadow.v1":
        raise TOPAHold("UNAPPROVED_FEEDBACK_MODEL")
    if receipt.get("schema_id")!="janus.meta_registry.rowan_evidence_receipt.v1" or receipt.get("original_public_data_sha256")!=PIN:
        raise TOPAHold("SOURCE_NOT_ATTESTED")
    if model.get("source_run_id")!=receipt.get("source",{}).get("run_id"):
        raise TOPAHold("SOURCE_RUN_MISMATCH")
    coef=model.get("fit",{})
    if coef.get("ridge")!=1 or coef.get("scale")!=10 or coef.get("target")!="THIRD_PARTY_PROCESSED_BBC1_ASSAY_LABEL":
        raise TOPAHold("FROZEN_MODEL_PROTOCOL_DRIFT")
    if model["split"].get("frozen_train_mutations")!=list(TRAIN) or model["split"].get("frozen_test_mutations")!=list(HELDOUT):
        raise TOPAHold("FROZEN_HOLDOUT_LEAK")
    cases=receipt.get("cases",[])
    if len(cases)!=8 or [r.get("mutation") for r in cases]!=list(TRAIN+HELDOUT):
        raise TOPAHold("FROZEN_EIGHT_CASES_DRIFT")
    wt=receipt.get("wildtype",{})
    if wt.get("provider_state")!="PROVIDER_RESULT_RETURNED":
        raise TOPAHold("MISSING_WT")
    wt_ptm=f(wt.get("ptm"));wt_lddt=f(wt.get("avg_lddt"))
    records=[]
    for r in cases:
        if r.get("provider_credit_cap_alert"):
            raise TOPAHold("CHARGE_ALARM")
        if r.get("provider_state")!="PROVIDER_RESULT_RETURNED":continue
        p=f(r.get("ptm"));l=f(r.get("avg_lddt"))
        if not (0<=p<=1 and 0<=l<=1):raise TOPAHold("UNPHYSICAL_CONFIDENCE")
        records.append((r["mutation"],10*(p-wt_ptm),10*(l-wt_lddt),f(r.get("published_processed_label"))))
    train=[r for r in records if r[0] in TRAIN]
    test=[r for r in records if r[0] in HELDOUT]
    if len(train)<3:raise TOPAHold("NOT_ENOUGH_TRAINED_SAMPLES")
    if model["split"].get("completed_training_mutations")!=[r[0] for r in train] or model["split"].get("completed_test_mutations")!=[r[0] for r in test]:
        raise TOPAHold("TRAIN_SPLIT_COMPLETION_MISMATCH")
    xm=sum(r[1] for r in train)/len(train)
    zm=sum(r[2] for r in train)/len(train)
    ym=sum(r[3] for r in train)/len(train)
    xx=sum((r[1]-xm)**2 for r in train)+1
    zz=sum((r[2]-zm)**2 for r in train)+1
    xz=sum((r[1]-xm)*(r[2]-zm) for r in train)
    xy=sum((r[1]-xm)*(r[3]-ym) for r in train)
    zy=sum((r[2]-zm)*(r[3]-ym) for r in train)
    det=xx*zz-xz*xz
    if det<=0:raise TOPAHold("ILL_CONDITIONED")
    c1=(xy*zz-zy*xz)/det
    c2=(zy*xx-xy*xz)/det
    intercept=ym-c1*xm-c2*zm
    given=coef.get("weights")
    if not isinstance(given,list) or len(given)!=2 or any(abs(f(a)-b)>2e-7 for a,b in zip([coef.get("intercept"),*given],[intercept,c1,c2])):
        raise TOPAHold("INDEPENDENT_WEIGHT_REPLAY_FAILED")
    all_test=len(test)==2
    if model["metrics"].get("heldout_two_mutants_complete")!=all_test:
        raise TOPAHold("HOLDOUT_COMPLETION_FALSE")
    if all_test:
        mae=sum(abs(intercept+c1*r[1]+c2*r[2]-r[3]) for r in test)/2
        base=sum(abs(ym-r[3]) for r in test)/2
        if abs(f(model["metrics"]["heldout_mae"])-mae)>2e-7 or abs(f(model["metrics"]["heldout_training_mean_baseline_mae"])-base)>2e-7:
            raise TOPAHold("INDEPENDENT_HOLDOUT_REPLAY_FAILED")
    else:
        if model["metrics"].get("heldout_mae") is not None or model["metrics"].get("heldout_training_mean_baseline_mae") is not None:
            raise TOPAHold("EARLY_HELDOUT_DISCLOSURE")
        mae=base=None
    return {
        "schema_id":"janus.topa.rowan_feedback_replay.v1",
        "audit":"PASS_INDEPENDENT_SCALAR_COEFFICIENT_REPLAY",
        "observed_training_mutations":len(train),
        "heldout_complete":all_test,
        "heldout_mae":round(mae,9) if mae is not None else None,
        "heldout_training_mean_baseline_mae":round(base,9) if base is not None else None,
        "topa_scope":"ALGORITHM_AND_SOURCE_REPLAY_NOT_BIOLOGICAL_VALIDATION",
        "processed_assay_outcome_stratification":"NOT_UNBIASED_POPULATION_PERFORMANCE",
        "promotion":"DENIED_SHADOW_ONLY",
        "weights_updated_in_boltz2":False,
        "rowan_credits_spent":0,
        "external_independent_scientific_review":"OPEN"
    }

def run(root="."):
    root=Path(root)
    files=sorted((root/BASE/"feedback").glob("FEEDBACK-RUN*.json"))
    if not files:
        print("JANUS_TOPA_FEEDBACK=WAIT_FOR_SHADOW_TRAINING_INPUT");return 0
    completed=0
    for path in files:
        raw=path.read_bytes()
        if len(raw)>40000:raise TOPAHold("MODEL_OVERSIZED")
        model=json.loads(raw)
        matching=[]
        for p in (root/BASE/"receipts").glob("ROWAN-S2-*.json"):
            if hashlib.sha256(p.read_bytes()).hexdigest()==model.get("source_receipt_file_sha256"):
                matching.append(p)
        if len(matching)!=1:raise TOPAHold("INDEPENDENT_SOURCE_FILE_NOT_UNIQUE")
        report=review(model,json.loads(matching[0].read_text()))
        report["model_file_sha256"]=hashlib.sha256(raw).hexdigest()
        report["source_receipt_file_sha256"]=model["source_receipt_file_sha256"]
        digest=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(",",":")).encode()).hexdigest()[:16]
        target=root/BASE/"topa"/f"TOPA-FEEDBACK-{digest}.json"
        payload=json.dumps(report,indent=2,allow_nan=False).encode()+b"\n"
        if target.exists() and target.read_bytes()!=payload:raise TOPAHold("AUDIT_FILE_CONFLICT")
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
            completed+=1
    print("JANUS_TOPA_FEEDBACK=SOURCE_AND_COEFFICIENT_REPLAY_PASS")
    print("JANUS_TOPA_FEEDBACK_NEW_AUDITS="+str(completed))
    return 0

if __name__=="__main__":
    try:raise SystemExit(run())
    except Exception:
        print("JANUS_TOPA_FEEDBACK=INDEPENDENT_REPLAY_HOLD")
        raise SystemExit(2)
