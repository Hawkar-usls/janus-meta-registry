#!/usr/bin/env python3
"""Train narrow, reproducible BBC1 assay-label ridge weights on public frozen data.

Never touches Rowan, Boltz-2, Tranception model weights, private accounts or
paid services. Freeze split before fitting, select lambda without test data.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,math
from pathlib import Path
from urllib.request import Request,urlopen
import numpy as np

PIN="ca355a655381c95fe899d61a406251e0cd17d68bbabe287651d526fdeb821f87"
REV="cc6b0b56553e694dbf27dc84c6b37a8686e64b85"
URL=f"https://huggingface.co/datasets/genbio-ai/ProteinGYM-DMS/resolve/{REV}/singles_substitutions/BBC1_YEAST_Tsuboyama_2023_1TG0.tsv"
WT="EVPFKVVAQFPYKSDYEDDLNFEKDQEIIVTSVEDAEWYFGEYQDSNGDVIEGIFPKSFVAVQG"
AA="ACDEFGHIKLMNPQRSTVWY"
HY={"A":1.8,"C":2.5,"D":-3.5,"E":-3.5,"F":2.8,"G":-.4,"H":-3.2,"I":4.5,"K":-3.9,"L":3.8,"M":1.9,"N":-3.5,"P":-1.6,"Q":-3.5,"R":-4.5,"S":-.8,"T":-.7,"V":4.2,"W":-.9,"Y":-1.3}
SALT="JANUS-TOPA-20261025-SPLIT-V1"
LAMS=(.1,1.,10.,100.)
SCHEMA="janus.rowan.bbc1.sequence_shadow_ridge.v1"

class GateError(ValueError):pass

def source_bytes(path=None):
    if path is not None:
        return Path(path).read_bytes()
    with urlopen(Request(URL,headers={"User-Agent":"JANUS-TOPA-independent-research/1"}),timeout=45) as resp:
        return resp.read(1_000_001)

def parse(raw):
    if not isinstance(raw,bytes) or len(raw)>1_000_000 or hashlib.sha256(raw).hexdigest()!=PIN:
        raise GateError("PINNED_ASSAY_BYTES_MISMATCH")
    try:
        rd=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")),delimiter="\t")
    except UnicodeDecodeError as exc:
        raise GateError("NON_UTF8_SOURCE") from exc
    if not rd.fieldnames or not {"sequences","labels","fold_id"}<=set(rd.fieldnames):
        raise GateError("ASSAY_HEADERS_MISSING")
    found={}
    for row in rd:
        s=(row.get("sequences") or "").strip()
        if s in found or len(s)!=64 or any(c not in AA for c in s):
            raise GateError("DUPLICATE_OR_INVALID_SEQUENCE")
        changed=[i for i in range(64) if WT[i]!=s[i]]
        if len(changed)!=1:
            raise GateError("NOT_SINGLE_MUTANT")
        try: y=float(row["labels"])
        except (TypeError,ValueError) as exc:raise GateError("NON_NUMERIC_LABEL") from exc
        if not math.isfinite(y):raise GateError("NONFINITE_LABEL")
        found[s]=(changed[0]+1,y)
    if len(found)!=1084:
        raise GateError("ASSAY_VARIANT_COUNT_CHANGED")
    return sorted([(s,p,y) for s,(p,y) in found.items()])

def positions():
    ps=list(range(1,65))
    ps.sort(key=lambda p:(hashlib.sha256(f"{SALT}|{p}".encode()).hexdigest(),p))
    return {"test":ps[:16],"valid":ps[16:28],"train":ps[28:]}

def features(seq,p):
    src,dst=WT[p-1],seq[p-1]
    x=[0.]*44
    x[AA.index(src)]=1.
    x[20+AA.index(dst)]=1.
    dh=HY[dst]-HY[src]
    x[40]=dh/10.
    x[41]=abs(dh)/10.
    x[42]=p/64.
    x[43]=(p/64.)**2
    return x

def fit(rows,lam):
    x=np.asarray([features(s,p) for s,p,y in rows],dtype=np.float64)
    y=np.asarray([y for s,p,y in rows],dtype=np.float64)
    xm=x.mean(axis=0);ym=y.mean()
    x=x-xm
    w=np.linalg.solve(x.T@x+np.eye(44)*lam,x.T@(y-ym))
    intercept=float(ym-xm@w)
    if not all(map(math.isfinite,w)) or not math.isfinite(intercept):
        raise GateError("FIT_COEFFICIENTS_NONFINITE")
    return intercept,w

def score(rows,intercept,w):
    y=np.asarray([r[2] for r in rows],dtype=float)
    pred=np.asarray([intercept+float(np.asarray(features(s,p))@w) for s,p,_ in rows])
    return {"mae":round(float(np.mean(np.abs(pred-y))),9),
            "rmse":round(float(np.sqrt(np.mean((pred-y)**2))),9),
            "count":len(rows)}

def train(raw):
    rows=parse(raw)
    splits=positions()
    sets={k:[r for r in rows if r[1] in ps] for k,ps in splits.items()}
    training=sets["train"]
    validation=sets["valid"]
    full=training+validation
    test=sets["test"]
    if min(map(len,sets.values()))<50 or len(set(r[1] for r in rows))!=64:
        raise GateError("INSUFFICIENT_GROUP_SUPPORT")
    tune=[]
    for lam in LAMS:
        b,w=fit(training,lam)
        v=score(validation,b,w)
        tune.append({"lambda":lam,"valid_mae":v["mae"]})
    selected=min(tune,key=lambda t:(t["valid_mae"],t["lambda"]))["lambda"]
    b,w=fit(full,selected)
    tested=score(test,b,w)
    baseline=float(np.mean([r[2] for r in full]))
    baseline_result=score(test,baseline,np.zeros(44))
    gain=(baseline_result["mae"]-tested["mae"])/max(baseline_result["mae"],1e-12)
    obj={
        "schema_id":SCHEMA,
        "source":{"sha256":PIN,"revision":REV,"assay":"BBC1_YEAST_Tsuboyama_2023_1TG0",
                  "source_class":"PUBLIC_THIRD_PARTY_PROCESSED_NOT_RAW_ASSAY"},
        "model":{"type":"RIDGE_LINEAR_SEQUENCE_SHADOW","weights":[round(float(z),12) for z in w],
                 "intercept":round(b,12),"features":44,"lambda":selected,
                 "method":"CENTERED_RIDGE_CLOSED_FORM_NO_TEST_FIT"},
        "split":{"salt":SALT,"test_positions":splits["test"],"validation_positions":splits["valid"],
                 "training_positions":splits["train"],"train_size":len(training),
                 "valid_size":len(validation),"test_size":len(test)},
        "tuning":{"precommitted_lambdas":list(LAMS),"validation_only":tune},
        "performance":{"test":tested,"train_mean_baseline_mae":baseline_result["mae"],
                       "train_mean_baseline_rmse":baseline_result["rmse"],
                       "heldout_mae_relative_improvement":round(gain,9)},
        "authority":{"trained_weights":True,"github_cpu_only":True,
            "rowan_credits_used":0,"rowan_or_tranception_weights_modified":False,
            "deployment":"SHADOW_ONLY","independent_heldout_assay":"NOT_AVAILABLE",
            "clinical_or_biological_stability_validation":"NOT_ESTABLISHED",
            "next_study_spend_authorized":False}
    }
    return obj

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--assay-tsv")
    parser.add_argument("--output-dir",default="data/rowan/learned")
    args=parser.parse_args()
    try: out=train(source_bytes(args.assay_tsv))
    except Exception:
        print("JANUS_SHADOW_TRAIN=INPUT_OR_FIT_GATE_HOLD");return 2
    digest=hashlib.sha256(json.dumps(out,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    path=Path(args.output_dir)/f"SHADOW-BBC1-{digest[:16]}.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(out,indent=2,allow_nan=False).encode()+b"\n"
    if path.exists():
        if path.read_bytes()!=raw:
            print("JANUS_SHADOW_TRAIN=IMMUTABLE_CHECKPOINT_CONFLICT");return 2
    else:path.write_bytes(raw)
    print("JANUS_SHADOW_TRAIN=ACTUAL_WEIGHTS_FITTED_SHADOW")
    print("JANUS_SHADOW_TRAIN_MODEL_SHA="+digest[:16])
    print("JANUS_SHADOW_TEST_MAE="+str(out["performance"]["test"]["mae"]))
    print("JANUS_SHADOW_BASELINE_MAE="+str(out["performance"]["train_mean_baseline_mae"]))
    print("JANUS_SHADOW_PRODUCTION_PROMOTION=DENIED")
    return 0

if __name__=="__main__":raise SystemExit(main())
