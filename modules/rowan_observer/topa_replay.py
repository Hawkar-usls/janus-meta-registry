#!/usr/bin/env python3
"""TOPA separate-code-path verification of trained BBC1 shadow model.

Independent HTTP download, TSV decoding, reconstruction of position heldout
and predictions (pure Python, no import from model trainer). Fail closed.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math
from pathlib import Path
from urllib.request import Request,urlopen

PIN="ca355a655381c95fe899d61a406251e0cd17d68bbabe287651d526fdeb821f87"
REV="cc6b0b56553e694dbf27dc84c6b37a8686e64b85"
SRC=f"https://huggingface.co/datasets/genbio-ai/ProteinGYM-DMS/resolve/{REV}/singles_substitutions/BBC1_YEAST_Tsuboyama_2023_1TG0.tsv"
WT="EVPFKVVAQFPYKSDYEDDLNFEKDQEIIVTSVEDAEWYFGEYQDSNGDVIEGIFPKSFVAVQG"
LETTERS="ACDEFGHIKLMNPQRSTVWY"
H=(1.8,2.5,-3.5,-3.5,2.8,-.4,-3.2,4.5,-3.9,3.8,1.9,-3.5,-1.6,-3.5,-4.5,-.8,-.7,4.2,-.9,-1.3)
SALT="JANUS-TOPA-20261025-SPLIT-V1"

class TOPAHold(ValueError):pass

def get_source(path=None):
    if path:return Path(path).read_bytes()
    with urlopen(Request(SRC,headers={"User-Agent":"JANUS-TOPA-independent-auditor/1"}),timeout=45) as r:
        return r.read(1_000_001)

def rows(data):
    if not data or len(data)>1_000_000 or hashlib.sha256(data).hexdigest()!=PIN:
        raise TOPAHold("REFERENCE_HASH_FAILED")
    parsed=csv.DictReader(io.StringIO(data.decode("utf-8-sig")),delimiter="\t")
    if not parsed.fieldnames or not {"sequences","labels","fold_id"}<=set(parsed.fieldnames):
        raise TOPAHold("INVALID_PUBLIC_SOURCE_HEADERS")
    vals={}
    for x in parsed:
        seq=x.get("sequences","").strip()
        if len(seq)!=len(WT) or seq in vals:
            raise TOPAHold("INVALID_OR_DUPLICATE_ROW")
        differences=[p for p in range(len(WT)) if WT[p]!=seq[p]]
        if len(differences)!=1 or any(aa not in LETTERS for aa in seq):
            raise TOPAHold("UNRECOGNIZED_MUTATION")
        try:label=float(x["labels"])
        except (ValueError,TypeError) as e:raise TOPAHold("INVALID_SCORE") from e
        if not math.isfinite(label):raise TOPAHold("NONFINITE_SCORE")
        vals[seq]=(differences[0]+1,label)
    if len(vals)!=1084:raise TOPAHold("VARIANT_COUNT_DRIFT")
    return vals

def split_independent():
    allpos=sorted(range(1,65),key=lambda p:(hashlib.sha256((SALT+"|"+str(p)).encode()).hexdigest(),p))
    return {"test":allpos[:16],"valid":allpos[16:28],"train":allpos[28:]}

def predict(seq,p,coef,intercept):
    from_aa=WT[p-1]
    to_aa=seq[p-1]
    origin=LETTERS.index(from_aa)
    destination=LETTERS.index(to_aa)
    hydro_delta=H[destination]-H[origin]
    relative_pos=p/64.
    return (intercept+coef[origin]+coef[20+destination]+coef[40]*(hydro_delta/10)
            +coef[41]*(abs(hydro_delta)/10)+coef[42]*relative_pos
            +coef[43]*(relative_pos**2))

def calc_err(pairs):
    if not pairs:raise TOPAHold("NO_VALID_TEST_PAIRS")
    residual=[a-b for a,b in pairs]
    return (sum(abs(z) for z in residual)/len(residual),
            math.sqrt(sum(z*z for z in residual)/len(residual)))

def attest(model, source):
    if not isinstance(model,dict) or model.get("schema_id")!="janus.rowan.bbc1.sequence_shadow_ridge.v1":
        raise TOPAHold("MODEL_SCHEMA_UNRECOGNIZED")
    if model.get("source",{}).get("sha256")!=PIN:
        raise TOPAHold("TRAINING_SOURCE_MISMATCH")
    m=model.get("model",{})
    if m.get("type")!="RIDGE_LINEAR_SEQUENCE_SHADOW" or len(m.get("weights",[]))!=44:
        raise TOPAHold("MODEL_SHAPE_CHANGED")
    if m.get("lambda") not in (.1,1.,10.,100.):
        raise TOPAHold("UNPREREGISTERED_HYPERPARAMETER")
    w=m["weights"];b=m.get("intercept")
    if any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e6 for v in [*w,b]):
        raise TOPAHold("COEFFICIENTS_NONFINITE_OR_EXTREME")
    split=split_independent()
    if any(model.get("split",{}).get(key+"_positions")!=split[key] for key in split):
        raise TOPAHold("HELDOUT_POSITION_LEAK_OR_DRIFT")
    data=rows(source)
    if set(x[0] for x in data.values())!=set(range(1,65)):
        raise TOPAHold("MISSING_POSITION_GROUPS")
    train=[y for p,y in data.values() if p not in split["test"]]
    if not train:raise TOPAHold("NO_TRAINING_ROWS")
    train_mean=sum(train)/len(train)
    observed=[]
    baseline=[]
    for seq,(pos,label) in data.items():
        if pos in split["test"]:
            observed.append((label,predict(seq,pos,w,b)))
            baseline.append((label,train_mean))
    if model["split"]["test_size"]!=len(observed) or model["split"]["train_size"]+model["split"]["valid_size"]!=len(train):
        raise TOPAHold("REPORTED_COUNTS_WRONG")
    mae,rmse=calc_err(observed)
    base_mae,base_rmse=calc_err(baseline)
    report=model.get("performance",{})
    expected=(("test",mae,rmse),
              ("train_mean_baseline_mae",base_mae,None),
              ("train_mean_baseline_rmse",base_rmse,None))
    for key,expected_mae,expected_rmse in expected:
        claimed=report.get(key)
        if key=="test":
            if not isinstance(claimed,dict) or abs(claimed.get("mae",float("inf"))-expected_mae)>2e-6 or abs(claimed.get("rmse",float("inf"))-expected_rmse)>2e-6:
                raise TOPAHold("TEST_SCORES_NOT_REPRODUCED")
        elif type(claimed) not in (int,float) or abs(claimed-expected_mae)>2e-6:
            raise TOPAHold("BASELINE_NOT_REPRODUCED")
    relative_gain=(base_mae-mae)/max(1e-12,base_mae)
    if abs(report.get("heldout_mae_relative_improvement",float("inf"))-relative_gain)>2e-6:
        raise TOPAHold("REPORTED_GAIN_MISMATCH")
    shuffled=[(obs[0],observed[len(observed)-1-i][1]) for i,obs in enumerate(observed)]
    shuffled_mae,_=calc_err(shuffled)
    return {
        "schema_id":"janus.topa.independent_shadow_replay.v1",
        "independent_code_path":True,
        "independent_remote_source_sha256":hashlib.sha256(source).hexdigest(),
        "audit":"PASS_INDEPENDENT_WITHIN_ASSAY_REPLAY",
        "model_family":"RIDGE_LINEAR_SEQUENCE_SHADOW",
        "training_source":"FROZEN_PUBLIC_PROCESSED_BBC1",
        "position_group_holdout_count":16,
        "heldout_variant_count":len(observed),
        "test_mae_independent":round(mae,9),
        "test_rmse_independent":round(rmse,9),
        "training_mean_baseline_mae_independent":round(base_mae,9),
        "relative_test_mae_improvement":round(relative_gain,9),
        "test_label_permutation_negative_control_mae":round(shuffled_mae,9),
        "test_improvement_status":"BETTER_THAN_BASELINE" if relative_gain>0 else "FAIL_NO_BASELINE_GAIN",
        "promotion_gate":"SHADOW_ONLY",
        "rowan_credits_consumed_by_training_or_topa":0,
        "fundamental_model_weights_updated":False,
        "topa_audit_scope":"CODE_PATH_AND_MEASUREMENT_REPLAY_NOT_THIRD_PARTY_WETLAB_VALIDATION",
        "external_lab_replication":"OPEN",
        "raw_assay_units_and_biological_replicates":"NOT_VERIFIED",
        "out_of_assay_generalization":"NOT_TESTED",
        "claims_of_biological_fitness_causality":False,
    }

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--model",required=True)
    a.add_argument("--assay-tsv")
    a.add_argument("--output-dir",default="data/rowan/topa")
    args=a.parse_args()
    try:
        src=get_source(args.assay_tsv)
        modelraw=Path(args.model).read_bytes()
        if len(modelraw)>50000:raise TOPAHold("MODEL_FILE_OVERSIZED")
        obj=json.loads(modelraw)
        r=attest(obj,src)
        modelsha=hashlib.sha256(modelraw).hexdigest()
    except Exception:
        print("JANUS_TOPA=INDEPENDENT_REPLAY_HOLD")
        return 2
    r["model_file_sha256"]=modelsha
    digest=hashlib.sha256(json.dumps(r,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    out=Path(args.output_dir)/f"TOPA-SHADOW-{digest[:16]}.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    blob=json.dumps(r,indent=2,allow_nan=False).encode()+b"\n"
    if out.exists():
        if out.read_bytes()!=blob:
            print("JANUS_TOPA=IMMUTABLE_RECEIPT_CONFLICT");return 2
    else:out.write_bytes(blob)
    print("JANUS_TOPA=INDEPENDENT_REPLAY_PASS")
    print("JANUS_TOPA_MODEL_SHA="+modelsha[:16])
    print("JANUS_TOPA_HOLDOUT_GAIN="+str(r["relative_test_mae_improvement"]))
    print("JANUS_TOPA_DEPLOYMENT=SHADOW_ONLY")
    return 0

if __name__=="__main__":raise SystemExit(main())
