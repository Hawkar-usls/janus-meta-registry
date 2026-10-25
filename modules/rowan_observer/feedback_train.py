#!/usr/bin/env python3
"""Stage-2 Rowan feedback learner: bounded, actual incremental SHADOW weights.

Train on completed preregistered variants 0..5. Reserve variants 6,7 for
unchanged holdout. Never use heldout targets to choose coefficients or tuning.
Evidence source = exact Meta Registry durable receipt, not provider accounts.
"""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np

BASE=Path("data/rowan")
MUTATIONS=("G53A","G48D","E27F","W38L","K13N","G64Q","Q44V","E42H")
QUANTILES=(5,15,30,45,60,75,90,98)
PIN="ca355a655381c95fe899d61a406251e0cd17d68bbabe287651d526fdeb821f87"
RIDGE=1.
MIN_TRAIN=3
TRAIN_INDICES=tuple(range(6))
HOLDOUT_INDICES=(6,7)

class Hold(ValueError):pass

def canonical(data):
    return json.dumps(data,sort_keys=True,separators=(",",":"),allow_nan=False).encode()

def proper(v,lo=-1e6,hi=1e6):
    if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:
        raise Hold("INVALID_NUMERIC_DATA")
    return float(v)

def find_verified_receipt(root):
    root=Path(root)
    state=json.loads((root/BASE/"CANONICAL_STATE.json").read_text())
    if state.get("schema_id")!="janus.rowan.observer_state.v1":raise Hold("INVALID_STATE_SCHEMA")
    source=state.get("underlying_state_is_derived_from")
    run=state.get("latest_durable_external_run")
    fingerprint=state.get("notification_dedupe_key")
    if type(run)!=int or run<=0 or not isinstance(source,str) or len(source)!=64:
        raise Hold("INVALID_STATE_PROVENANCE")
    matched=[]
    for f in (root/BASE/"receipts").glob("ROWAN-S2-*.json"):
        if f.stat().st_size>100_000:raise Hold("OVERSIZED_RECEIPT")
        r=json.loads(f.read_text())
        info=r.get("source",{})
        if info.get("run_id")!=run or info.get("source_artifact_sha256")!=source:
            continue
        k=hashlib.sha256(canonical(r.get("calibration"))).hexdigest()[:20]
        if k==fingerprint:matched.append((r,hashlib.sha256(f.read_bytes()).hexdigest()))
    if len(matched)!=1:
        raise Hold("CANONICAL_STATE_RECEIPT_NOT_UNIQUE")
    r,digest=matched[0]
    if r.get("schema_id")!="janus.meta_registry.rowan_evidence_receipt.v1":
        raise Hold("INVALID_IMMUTABLE_RECEIPT")
    if r.get("original_public_data_sha256")!=PIN:raise Hold("PUBLIC_ASSAY_PROVENANCE_DRIFT")
    cases=r.get("cases")
    if not isinstance(cases,list) or len(cases)!=8:
        raise Hold("NOT_EIGHT_MUTATION_CASES")
    for case,(mut,q) in zip(cases,zip(MUTATIONS,QUANTILES)):
        if case.get("mutation")!=mut or case.get("quantile")!=q:
            raise Hold("FROZEN_CASE_DRIFT")
        proper(case.get("published_processed_label"))
        if case.get("provider_credit_cap_alert"):raise Hold("CREDIT_CAP_ALERT_BLOCKS_LEARNING")
    return r,digest

def fit_feedback(receipt,source_sha):
    wt=receipt.get("wildtype",{})
    if wt.get("provider_state")!="PROVIDER_RESULT_RETURNED":return None
    ptm=proper(wt.get("ptm"),0,1);lddt=proper(wt.get("avg_lddt"),0,1)
    rows=[]
    for i,c in enumerate(receipt["cases"]):
        if c.get("provider_state")!="PROVIDER_RESULT_RETURNED":continue
        if c.get("provider_credit_cap_alert"):raise Hold("CREDIT_CAP_ALARM")
        x=(10*(proper(c.get("ptm"),0,1)-ptm),10*(proper(c.get("avg_lddt"),0,1)-lddt))
        rows.append((i,x,proper(c["published_processed_label"])))
    train=[v for v in rows if v[0] in TRAIN_INDICES]
    test=[v for v in rows if v[0] in HOLDOUT_INDICES]
    if len(train)<MIN_TRAIN:return None
    x=np.array([r[1] for r in train],dtype=float)
    y=np.array([r[2] for r in train],dtype=float)
    xm=x.mean(axis=0);ym=float(y.mean())
    w=np.linalg.solve((x-xm).T@(x-xm)+RIDGE*np.eye(2),(x-xm).T@(y-ym))
    intercept=float(ym-xm@w)
    if not np.isfinite(w).all() or not math.isfinite(intercept):
        raise Hold("MODEL_FIT_NONFINITE")
    evaluated=len(test)==2
    test_mae=None;mean_mae=None
    if evaluated:
        predictions=[intercept+float(np.dot(w,v[1])) for v in test]
        test_mae=round(sum(abs(p-v[2]) for p,v in zip(predictions,test))/2,9)
        mean_mae=round(sum(abs(ym-v[2]) for v in test)/2,9)
    return {
        "schema_id":"janus.rowan.bbc1.provider_feedback_shadow.v1",
        "source_receipt_file_sha256":source_sha,
        "source_run_id":receipt["source"]["run_id"],
        "source_artifact_sha256":receipt["source"]["source_artifact_sha256"],
        "fit":{"intercept":round(intercept,12),"weights":[round(float(v),12) for v in w],
               "ridge":RIDGE,"scale":10,"target":"THIRD_PARTY_PROCESSED_BBC1_ASSAY_LABEL"},
        "split":{"frozen_train_mutations":list(MUTATIONS[:6]),"frozen_test_mutations":list(MUTATIONS[6:]),
                 "completed_training_mutations":[MUTATIONS[r[0]] for r in train],
                 "completed_test_mutations":[MUTATIONS[r[0]] for r in test]},
        "metrics":{"heldout_two_mutants_complete":evaluated,
                   "heldout_mae":test_mae,"heldout_training_mean_baseline_mae":mean_mae,
                   "within_assay_outcome_stratified":True},
        "authority":{"trained_weights":True,"scope":"SHADOW_HYPOTHESIS_ONLY",
            "boltz2_weights_modified":False,"rowan_credits_used":0,
            "new_mutations_or_budget_authorized":False,
            "independent_wetlab_science_audit":"OPEN"}
    }

def learning_input_digest(receipt):
    """Fingerprint only data that can change fitted weights or heldout metrics.

    Excludes source run/receipt identity so harmless repeated status snapshots do
    not create new models. Heldout inputs enter only after BOTH are complete.
    """
    if (receipt.get("schema_id")!="janus.meta_registry.rowan_evidence_receipt.v1"
            or receipt.get("original_public_data_sha256")!=PIN):
        raise Hold("LEARNING_SOURCE_SCHEMA_OR_PIN_DRIFT")
    cases=receipt.get("cases")
    if not isinstance(cases,list) or len(cases)!=8:
        raise Hold("INVALID_TRAINING_SOURCE_CASES")
    wt=receipt.get("wildtype",{})
    if wt.get("provider_state")!="PROVIDER_RESULT_RETURNED":
        raise Hold("LEARNING_WT_NOT_COMPLETE")
    material={"wildtype":[proper(wt.get("ptm"),0,1),proper(wt.get("avg_lddt"),0,1)],
              "training":[],"heldout":None}
    heldout=[]
    for i,case in enumerate(cases):
        if (case.get("mutation")!=MUTATIONS[i] or case.get("quantile")!=QUANTILES[i]):
            raise Hold("LEARNING_FROZEN_CASE_DRIFT")
        if case.get("provider_credit_cap_alert"):
            raise Hold("LEARNING_CREDIT_CAP_ALERT")
        if case.get("provider_state")!="PROVIDER_RESULT_RETURNED":
            continue
        row=[MUTATIONS[i],proper(case.get("ptm"),0,1),
             proper(case.get("avg_lddt"),0,1),
             proper(case.get("published_processed_label"))]
        (material["training"] if i in TRAIN_INDICES else heldout).append(row)
    if len(heldout)==len(HOLDOUT_INDICES):
        material["heldout"]=heldout
    return hashlib.sha256(canonical(material)).hexdigest()


def prior_model_with_matching_input(root, receipt, model):
    """Verify exact previous source receipts, then suppress duplicate training."""
    current=learning_input_digest(receipt)
    prior_paths=sorted((root/BASE/"feedback").glob("FEEDBACK-RUN*.json"))
    if not prior_paths:
        return None
    receipt_by_hash={}
    for path in (root/BASE/"receipts").glob("ROWAN-S2-*.json"):
        if path.stat().st_size>100_000:
            raise Hold("OVERSIZED_HISTORICAL_RECEIPT")
        raw=path.read_bytes()
        key=hashlib.sha256(raw).hexdigest()
        if key in receipt_by_hash:
            raise Hold("DUPLICATED_HISTORICAL_RECEIPT_HASH")
        receipt_by_hash[key]=json.loads(raw)
    found=None
    for path in prior_paths:
        if path.stat().st_size>40_000:
            raise Hold("OVERSIZED_HISTORICAL_SHADOW_MODEL")
        old=json.loads(path.read_bytes())
        if old.get("schema_id")!="janus.rowan.bbc1.provider_feedback_shadow.v1":
            raise Hold("HISTORICAL_SHADOW_MODEL_SCHEMA_DRIFT")
        original=receipt_by_hash.get(old.get("source_receipt_file_sha256"))
        if original is None:
            raise Hold("HISTORICAL_SHADOW_SOURCE_MISSING")
        if (original.get("source",{}).get("run_id")!=old.get("source_run_id")
                or original.get("source",{}).get("source_artifact_sha256")!=
                    old.get("source_artifact_sha256")):
            raise Hold("HISTORICAL_SHADOW_SOURCE_MISMATCH")
        if learning_input_digest(original)!=current:
            continue
        # A matching original experiment must yield the identical bounded fit.
        # Never hide a discrepant fit behind a no-op optimization.
        for field in ("fit","split","metrics","authority"):
            if old.get(field)!=model.get(field):
                raise Hold("SAME_INPUT_DIVERGENT_FEEDBACK_MODEL")
        if found is not None:
            raise Hold("MULTIPLE_MODELS_FOR_IDENTICAL_LEARNING_INPUT")
        found=path
    return found


def run(root="."):
    base=Path(root)
    receipt,sha=find_verified_receipt(base)
    model=fit_feedback(receipt,sha)
    if model is None:
        print("JANUS_ROWAN_FEEDBACK=WAIT_FOR_THREE_COMPLETED_TRAINING_MUTANTS")
        return None
    previous=prior_model_with_matching_input(base,receipt,model)
    if previous is not None:
        print("JANUS_ROWAN_FEEDBACK=UNCHANGED_TRAINING_INPUT_NO_NEW_WEIGHTS")
        print("JANUS_ROWAN_FEEDBACK_REUSED_SOURCE_MODEL="+previous.name)
        return previous
    digest=hashlib.sha256(canonical(model)).hexdigest()
    path=base/BASE/"feedback"/f"FEEDBACK-RUN{model['source_run_id']}-{digest[:16]}.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    payload=json.dumps(model,indent=2,allow_nan=False).encode()+b"\n"
    if path.exists() and path.read_bytes()!=payload:
        raise Hold("IMMUTABLE_SHADOW_MODEL_CONFLICT")
    if not path.exists():path.write_bytes(payload)
    print("JANUS_ROWAN_FEEDBACK=SHADOW_WEIGHTS_UPDATED_FROM_VERIFIED_PROVIDER_RESULTS")
    print("JANUS_ROWAN_FEEDBACK_TRAINED="+str(len(model["split"]["completed_training_mutations"])))
    print("JANUS_ROWAN_FEEDBACK_WETLAB_VALIDATION=OPEN")
    return path

if __name__=="__main__":
    try:run()
    except Exception:
        print("JANUS_ROWAN_FEEDBACK=SOURCE_OR_MODEL_HOLD")
        raise SystemExit(2)
