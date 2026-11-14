#!/usr/bin/env python3
"""ESSENCE v1.6.4 prospective cross-repo CPU checkpoint fidelity witness.

One-shot read-only GitHub Actions replay in Meta Registry. The external source
commits and model candidate were frozen BEFORE this trial. Public external
text is not an independently blinded lab corpus. No checkpoint mutation,
model training, NAS operation, production service call, or automatic promotion.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import re
import statistics
import struct
import sys
import time
from urllib.request import Request,urlopen

import torch
from torch import nn

ROOT=Path(__file__).resolve().parents[1]
FROZEN_PATH=ROOT/"data"/"essence"/"v164"/"JANUS_ESSENCE_PROSPECTIVE_GITHUB_SOURCES_FREEZE_2026-11-14.json"
FROZEN_GIT_BLOB="2362792104bf1be353fc2f9b0623edd97bb8fe8e"
MODEL_REPO_COMMIT="edc4f104c4da43411d3987616c8de2d1cbd3a99d"
CHECKPOINT_SHA="fc767adb812ac3bea54c44cbccfa9680941f95e2c8a77120559b41da044d9463"
MODEL_PY_BLOB="11e359e89d3946895b2e0d6817c54253f09dfed1"
CHECKPOINT_GIT_BLOB="88cad884b437dd0ab655d913b1c83d6a6d669735"
SCHEMA="janus.essence.prospective_external_cpu_int8/1.6.4"
SUMMARY="janus.essence.prospective_external_cpu_int8_admission/1.6.4"
SELECTED=("blocks.layers.0.linear1","blocks.layers.0.linear2","blocks.layers.1.linear1")
PROVENANCE_LIMIT="EXTERNALLY_SOURCED_FRESH_PUBLIC_TEXT_NOT_EXTERNAL_BLIND_CUSTODIAN"
MAX_SOURCE_BYTES=100000

def digest_bytes(raw):
    return hashlib.sha256(raw).hexdigest()

def git_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def seal(j):
    return digest_bytes(json.dumps(j,sort_keys=True,ensure_ascii=False,
                       allow_nan=False,separators=(",",":")).encode())

def parse(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file() or not 2<=p.stat().st_size<=100000:
        raise ValueError("UNSAFE_JSON_SOURCE")
    return json.loads(p.read_text(encoding="utf8"),
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError("NONFINITE_JSON")))

def freeze():
    if git_blob(FROZEN_PATH.read_bytes())!=FROZEN_GIT_BLOB:
        raise ValueError("FROZEN_SPEC_UNAPPROVED_CHANGE")
    j=parse(FROZEN_PATH)
    if (j.get("schema")!="janus.essence.prospective_external_source_validation_lock/1.6.4"
      or j.get("selected_candidate_mask")!=7
      or j.get("selected_layers")!=list(SELECTED)
      or j.get("model_repo_merge_commit")!=MODEL_REPO_COMMIT
      or j.get("model_checkpoint_sha256")!=CHECKPOINT_SHA
      or j.get("model_source_blob_sha1")!=MODEL_PY_BLOB
      or j.get("model_checkpoint_blob_sha1")!=CHECKPOINT_GIT_BLOB
      or j.get("real_native_cpu_int8_operators_required")!=3
      or j.get("production_authority") is not False
      or j.get("require_no_automatic_model_promotion") is not True
      or len(j.get("sources",[]))!=2
      or j.get("external_independent_custodian") is not False):
        raise ValueError("UNAUTHORIZED_SPEC")
    return j

def verify_model(repo):
    if Path(repo).is_symlink():raise ValueError("MODEL_REPO_SYMLINK")
    if not re.fullmatch("[0-9a-f]{40}",MODEL_REPO_COMMIT):raise ValueError("UNTRUSTED_REF")
    # GitHub checkout action pins this commit; do not implicitly accept tip-of-main.
    import subprocess
    current=subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip()
    if current!=MODEL_REPO_COMMIT:raise ValueError("MODEL_REPO_SHA_DRIFT")
    model=repo/"janus_model"/"model.py"
    weights=repo/"janus_model"/"checkpoints"/"promoted.pt"
    if git_blob(model.read_bytes())!=MODEL_PY_BLOB:raise ValueError("MODEL_PY_SOURCE_CHANGED")
    if git_blob(weights.read_bytes())!=CHECKPOINT_GIT_BLOB:raise ValueError("CHECKPOINT_GIT_BLOB_CHANGED")
    if sha(weights)!=CHECKPOINT_SHA:raise ValueError("CHECKPOINT_CONTENT_CHANGED")
    return weights

def fetch_external(spec):
    repo=spec["repository"]
    if repo not in ("python/cpython","pytorch/pytorch"):
        raise ValueError("EXTERNAL_SOURCE_NOT_WHITELISTED")
    commit=spec["commit"];path=spec["file"]
    if not re.fullmatch(r"[a-f0-9]{40}",commit) or path not in ("README.rst","README.md"):
        raise ValueError("BAD_EXTERNAL_GIT_LOCATOR")
    url=f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"
    with urlopen(Request(url,headers={"User-Agent":"JANUS-ESSENCE-V164-READONLY"}),timeout=20) as req:
        raw=req.read(MAX_SOURCE_BYTES+1)
    if not 200<=len(raw)<=MAX_SOURCE_BYTES:raise ValueError("INVALID_EXTERNAL_SIZE")
    if git_blob(raw)!=spec["git_blob_sha1"]:
        raise ValueError("EXTERNAL_CONTENT_NOT_AT_FROZEN_GIT_BLOB")
    return raw.decode("utf8",errors="replace"),digest_bytes(raw)

def inputs(frozen,external):
    from janus_model.model import ByteTokenizer
    res={}
    L=frozen["evaluation"]["sequence_length"]
    B=frozen["evaluation"]["batch_size"]
    N=frozen["evaluation"]["batches_per_source"]
    for index,(label,text) in enumerate(external):
        encoded=ByteTokenizer.encode(text,bos=True,eos=True)
        if len(encoded)<L+B+2:raise ValueError("EXTERNAL_CORPUS_TOO_SMALL")
        rnd=random.Random(frozen["evaluation"]["seed"]+index*65537)
        rows=[]
        for _ in range(N):
            xs=[];ys=[]
            for _ in range(B):
                start=rnd.randrange(0,len(encoded)-L-1)
                xs.append(encoded[start:start+L])
                ys.append(encoded[start+1:start+L+1])
            rows.append((torch.tensor(xs,dtype=torch.long),
                         torch.tensor(ys,dtype=torch.long)))
        res[label]=rows
    return res

def clone_native_mask7(model):
    from torch.ao.quantization import quantize_dynamic
    clone=copy.deepcopy(model)
    torch.backends.mha.set_fastpath_enabled(False)
    for name in SELECTED:
        target=clone
        *parents,attr=name.split(".")
        for p in parents:
            target=target[int(p)] if p.isdigit() else getattr(target,p)
        child=getattr(target,attr)
        if not isinstance(child,nn.Linear):
            raise ValueError("UNEXPECTED_FFN_LAYER_TYPE")
        actual=quantize_dynamic(nn.Sequential(copy.deepcopy(child)),
                                  {nn.Linear},dtype=torch.qint8,inplace=False)[0]
        if not isinstance(actual,torch.ao.nn.quantized.dynamic.Linear):
            raise ValueError("NATIVE_INT8_OPERATOR_NOT_INSTALLED")
        setattr(target,attr,actual)
    count=sum(isinstance(x,torch.ao.nn.quantized.dynamic.Linear) for x in clone.modules())
    if (count!=3 or not isinstance(clone.lm_head,nn.Linear)
        or clone.lm_head.weight.data_ptr()!=clone.token.weight.data_ptr()):
        raise ValueError("FP32_OUTPUT_HEAD_OR_COUNT_BROKEN")
    return clone,count

def serialize_size(model):
    buffer=io.BytesIO()
    torch.save(model.state_dict(),buffer)
    return len(buffer.getbuffer())

def rss_bytes():
    try:return int(Path("/proc/self/statm").read_text().split()[1])*os.sysconf("SC_PAGE_SIZE")
    except (OSError,IndexError,ValueError):return None

@torch.inference_mode()
def evaluate(model,batches,reference=None):
    records={};raws={}
    for label,pairs in batches.items():
        losses=[];results=[];equal=0;total=0
        for i,(x,y) in enumerate(pairs):
            logits,loss=model(x,y)
            if not torch.isfinite(logits).all() or not math.isfinite(float(loss.item())):
                raise ValueError("NONFINITE_OUTPUT")
            losses.append(float(loss.item()))
            logits=logits.detach().float().cpu()
            if reference:
                ref=reference[label][i]
                if ref.shape!=logits.shape:raise ValueError("REFERENCE_SHAPE_MISMATCH")
                equal+=int((logits.argmax(dim=-1)==ref.argmax(dim=-1)).sum())
                total+=logits.shape[0]*logits.shape[1]
            results.append(logits)
        records[label]={"ce":round(statistics.mean(losses),9),
                        "top1_vs_fp32":round(equal/total,7) if total else None,
                        "batches":len(pairs)}
        raws[label]=results
    return records,raws

@torch.inference_mode()
def latency(model,batches,settings):
    x,y=next(iter(batches.values()))[0]
    for _ in range(settings["latency_warmups"]):model(x,y)
    durations=[]
    for _ in range(settings["latency_repeats"]):
        t=time.perf_counter_ns()
        model(x,y)
        durations.append((time.perf_counter_ns()-t)/1e6)
    return {"median_ms":round(statistics.median(durations),6),
            "min_ms":round(min(durations),6),
            "max_ms":round(max(durations),6),
            "rounds":len(durations),"thread_count":torch.get_num_threads()}

def run(mode,checkout,output):
    locked=freeze()
    weights=verify_model(checkout)
    sys.path.insert(0,str(checkout))
    from janus_model.train_registry import load_checkpoint
    torch.set_num_threads(locked["evaluation"]["cpu_threads"])
    torch.backends.mha.set_fastpath_enabled(False)
    before=sha(weights)
    model,obj=load_checkpoint(weights,expected_sha256=CHECKPOINT_SHA)
    model.eval()
    baseline_bytes=serialize_size(model)
    if mode=="candidate":
        model,n=clone_native_mask7(model)
        model.eval()
    else:n=0
    model_bytes=serialize_size(model)
    external=[]
    source_report=[]
    for spec in locked["sources"]:
        text,rawsha=fetch_external(spec)
        source_report.append({"corpus_name":spec["corpus_name"],
                              "source_commit":spec["commit"],
                              "blob_sha1":spec["git_blob_sha1"],
                              "actual_sha256":rawsha,
                              "bytes_in_unicode":len(text.encode("utf8"))})
        external.append((spec["corpus_name"],text))
    batches=inputs(locked,external)
    reference=None
    if mode=="candidate":
        prior=parse(output/"baseline.json")
        if (prior.get("schema")!=SCHEMA or prior.get("mode")!="baseline"
            or prior.get("source_sha256")!=CHECKPOINT_SHA
            or prior.get("receipt_sha256")!=seal({k:w for k,w in prior.items() if k!="receipt_sha256"})):
            raise ValueError("BASELINE_REPORT_INVALID")
        p=output/"baseline_logits.pt"
        if sha(p)!=prior["baseline_logits_sha256"]:
            raise ValueError("BASELINE_LOGIT_DIGEST_MISMATCH")
        reference=torch.load(p,map_location="cpu",weights_only=True)
        if set(reference)!=set(batches):raise ValueError("REFERENCE_COHORT_MISMATCH")
    quality,logits=evaluate(model,batches,reference)
    speed=latency(model,batches,locked["evaluation"])
    after_rss=rss_bytes()
    if mode=="baseline":
        file=output/"baseline_logits.pt"
        if file.exists():raise FileExistsError("NO_BASELINE_OVERWRITE")
        torch.save(logits,file)
        logsha=sha(file)
    else:logsha=None
    if sha(weights)!=before or before!=CHECKPOINT_SHA:
        raise ValueError("MUTATED_MODEL_SOURCE")
    receipt={
        "schema":SCHEMA,"mode":mode,"source_sha256":CHECKPOINT_SHA,
        "source_model_git_commit":MODEL_REPO_COMMIT,
        "source_model_git_blob_sha1":MODEL_PY_BLOB,
        "frozen_spec_git_blob_sha1":FROZEN_GIT_BLOB,
        "external_cohort_sources":source_report,
        "native_int8_operator_count":n,"output_head_fp32":True,
        "quality":quality,"speed":speed,
        "baseline_serialized_fp32_weights_bytes":baseline_bytes,
        "serialized_state_dict_bytes":model_bytes,
        "storage_saving_fraction":round(1-model_bytes/baseline_bytes,8),
        "current_rss_bytes":after_rss,
        "rss_comparison_limit":"RUNTIME_FULL_PROCESS_CPU_ALLOCATOR_DIFFERENCES",
        "gpu_vram_bytes":None,
        "baseline_logits_sha256":logsha,
        "trial_is_prospective_external_sources":True,
        "independent_external_custodian":False,
        "training_executed":False,"checkpoint_file_mutated":False,
        "live_service_deployed":False,"production_authority":False,
        "automatic_model_promotion":False
    }
    receipt["receipt_sha256"]=seal(receipt)
    f=output/(mode+".json")
    if f.exists():raise FileExistsError("NO_RECEIPT_OVERWRITE")
    f.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"mode":mode,"losses":quality,"serialized_bytes":model_bytes,
                      "median_ms":speed["median_ms"],"resident_bytes":after_rss,
                      "receipt_sha256":receipt["receipt_sha256"]},sort_keys=True))

def combine(output):
    frozen=freeze()
    b=parse(output/"baseline.json")
    c=parse(output/"candidate.json")
    for x,mode in ((b,"baseline"),(c,"candidate")):
        if (x.get("mode")!=mode or x.get("schema")!=SCHEMA
           or x.get("source_sha256")!=CHECKPOINT_SHA
           or x.get("frozen_spec_git_blob_sha1")!=FROZEN_GIT_BLOB
           or x.get("receipt_sha256")!=seal({k:w for k,w in x.items() if k!="receipt_sha256"})
           or x.get("automatic_model_promotion") is not False
           or x.get("checkpoint_file_mutated") is not False):
            raise ValueError("UNTRUSTED_INDEPENDENT_RUN_RESULT")
    if b["external_cohort_sources"]!=c["external_cohort_sources"]:
        raise ValueError("EXTERNAL_DATA_DRIFT")
    if b["native_int8_operator_count"]!=0 or c["native_int8_operator_count"]!=3:
        raise ValueError("UNTRUSTED_NATIVE_OPERATOR_COUNT")
    changed={}
    good=True
    for name in [spec["corpus_name"] for spec in frozen["sources"]]:
        bv=b["quality"][name]["ce"];cv=c["quality"][name]["ce"]
        tv=c["quality"][name]["top1_vs_fp32"]
        if bv<=0:raise ValueError("INVALID_REFERENCE_LOSS")
        loss_delta=(cv/bv-1)
        changed[name]={"loss_delta_fraction":round(loss_delta,8),
                       "top1_agreement":tv}
        good=good and tv>=frozen["thresholds"]["minimum_top1_agreement_each_corpus"] \
               and loss_delta<=frozen["thresholds"]["max_relative_cross_entropy_regression_each_corpus"]
    size_ratio=1-c["serialized_state_dict_bytes"]/b["serialized_state_dict_bytes"]
    speed_ratio=c["speed"]["median_ms"]/b["speed"]["median_ms"]-1
    eligible=(good and size_ratio>=frozen["thresholds"]["min_native_serialized_model_storage_saving"]
              and speed_ratio<=frozen["thresholds"]["max_median_latency_regression"])
    report={
      "schema":SUMMARY,"prospective_source_replay_pass":True,
      "real_native_int8_layers":3,"mode":"selected_mask_7",
      "comparison":changed,
      "model_size_saving":round(size_ratio,8),
      "median_cpu_time_change_fraction":round(speed_ratio,8),
      "development_candidate_pass":eligible,
      "frozen_spec_git_blob_sha1":FROZEN_GIT_BLOB,
      "original_source_sha256":CHECKPOINT_SHA,
      "baseline_receipt_sha256":b["receipt_sha256"],
      "candidate_receipt_sha256":c["receipt_sha256"],
      "new_external_sources_not_used_in_v163_selection":True,
      "fresh_public_sources_not_necessarily_training_disjoint":True,
      "externally_custodied_blind_validation":False,
      "fully_isolated_native_runtime_memory_gain_proven":False,
      "independent_repository_runner":True,
      "production_model_weights_unchanged":True,
      "auto_promotion_authorized":False,
      "next_stage":"REVIEWED_CANARY_WITH_GENUINE_ROLLBACK_AND_EXTERNAL_BLIND_CUSTODIAN",
      "gate":("PROSPECTIVE_RESEARCH_PASS_PRODUCTION_HOLD" if eligible
              else "HOLD_PROSPECTIVE_QUALITY_STORAGE_OR_CPU")
    }
    report["receipt_sha256"]=seal(report)
    f=output/"summary.json"
    if f.exists():raise FileExistsError("NO_SUMMARY_OVERWRITE")
    f.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"gate":report["gate"],"candidate_pass":eligible,
                      "saving":report["model_size_saving"],
                      "time_change":report["median_cpu_time_change_fraction"],
                      "quality":changed,"receipt_sha256":report["receipt_sha256"]},sort_keys=True))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--baseline",action="store_true")
    g.add_argument("--candidate",action="store_true")
    g.add_argument("--combine",action="store_true")
    p.add_argument("--model-checkout",default="runtime/essence_v164/demiurge")
    p.add_argument("--out-dir",default="runtime/essence_v164/result")
    args=p.parse_args()
    d=Path(args.out_dir);d.mkdir(parents=True,exist_ok=True)
    if args.combine:combine(d)
    else:run("baseline" if args.baseline else "candidate",Path(args.model_checkout),d)

if __name__=="__main__":main()
