#!/usr/bin/env python3
"""JANUS Rowan Observatory: immutable, source-bound GitHub Actions receipts.

Untrusted artifacts are interpreted as DATA, never instructions. Reads only
successful allowlisted main-branch runs and their exact sanitized JSON output.
Cannot call Rowan, purchase credits, submit jobs or modify science workflows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from datetime import datetime, timezone

SOURCE_REPO = "Hawkar-usls/Janus"
WORKFLOW = "rowan-bbc1-stratified-pilot.yml"
ARTIFACT_PREFIX = "bbc1-pilot-eight-public-safe-"
SHA256_PIN = "ca355a655381c95fe899d61a406251e0cd17d68bbabe287651d526fdeb821f87"
FROZEN = (
    (5, "G53A"), (15, "G48D"), (30, "E27F"), (45, "W38L"),
    (60, "K13N"), (75, "G64Q"), (90, "Q44V"), (98, "E42H")
)
BASE = Path("data/rowan")
ALLOWED = {"NOT_SUBMITTED", "PENDING_OR_FAILED", "PROVIDER_RESULT_RETURNED", "RESULT_UNREADABLE"}
MAX_RECEIPT = 80000
MAX_RUNS = 20

class EvidenceHold(ValueError):
    pass

def canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def number(x, *, lo=-100000, hi=100000):
    if type(x) not in (int,float) or not math.isfinite(x) or not lo <= x <= hi:
        raise EvidenceHold("NONFINITE_OR_OUT_OF_RANGE_NUMBER")
    return float(x)

def optional_number(x, *, lo=0, hi=1):
    return None if x is None else number(x,lo=lo,hi=hi)

def secure_row(raw, expected):
    if not isinstance(raw,dict):
        raise EvidenceHold("ROW_NOT_OBJECT")
    q, mut=expected
    if raw.get("quantile") != q or raw.get("mutation") != mut:
        raise EvidenceHold("FROZEN_MUTANT_OR_QUANTILE_DRIFT")
    label=number(raw.get("processed_label"))
    state=raw.get("provider_state")
    if state not in ALLOWED:
        raise EvidenceHold("INVALID_PROVIDER_STATE")
    clean={"quantile":q,"mutation":mut,"published_processed_label":label,"provider_state":state}
    if state=="PROVIDER_RESULT_RETURNED":
        clean["ptm"]=optional_number(raw.get("ptm"))
        clean["avg_lddt"]=optional_number(raw.get("avg_lddt"))
        clean["credits_charged"]=optional_number(raw.get("credits_charged"),lo=0,hi=100)
        if clean["credits_charged"] is not None and clean["credits_charged"]>10:
            clean["provider_credit_cap_alert"]=True
    return clean

def paired_spearman(x,y):
    if len(x)!=len(y) or len(x)<3:
        return None
    def ranks(a):
        ids=sorted(range(len(a)),key=lambda i:(a[i],i))
        out=[0.]*len(a)
        i=0
        while i<len(ids):
            j=i+1
            while j<len(ids) and a[ids[j]]==a[ids[i]]: j+=1
            r=(i+1+j)/2
            for k in range(i,j):out[ids[k]]=r
            i=j
        return out
    ax,ay=ranks(x),ranks(y)
    mx=sum(ax)/len(ax);my=sum(ay)/len(ay)
    vx=sum((v-mx)**2 for v in ax);vy=sum((v-my)**2 for v in ay)
    if not vx or not vy: return None
    return round(sum((a-mx)*(b-my) for a,b in zip(ax,ay))/math.sqrt(vx*vy),6)

def analyze(data):
    if not isinstance(data,dict) or data.get("schema_id")!="janus.rowan.bbc1.stratified_8_mutant_pilot.v1":
        raise EvidenceHold("SCHEMA_NOT_FROZEN")
    if data.get("source_sha256") != SHA256_PIN:
        raise EvidenceHold("PUBLIC_EXPERIMENTAL_SOURCE_SHA_DRIFT")
    if data.get("source_commit") != "cc6b0b56553e694dbf27dc84c6b37a8686e64b85":
        raise EvidenceHold("SOURCE_REVISION_DRIFT")
    records=data.get("pilot_cases")
    if not isinstance(records,list) or len(records)!=8:
        raise EvidenceHold("WRONG_NUMBER_OF_FROZEN_MUTANTS")
    safe=[secure_row(row,key) for row,key in zip(records,FROZEN)]
    w=data.get("wildtype")
    if not isinstance(w,dict):
        raise EvidenceHold("WT_BASELINE_MISSING")
    wstatus=w.get("state")
    if wstatus not in {"PENDING_OR_FAILED","PROVIDER_RESULT_RETURNED","RESULT_UNREADABLE"}:
        raise EvidenceHold("INVALID_WT_STATE")
    wt={"provider_state":wstatus}
    if wstatus=="PROVIDER_RESULT_RETURNED":
        wt.update(ptm=optional_number(w.get("ptm")),
                  avg_lddt=optional_number(w.get("avg_lddt")),
                  credits_charged=optional_number(w.get("credits_charged"),lo=0,hi=100))
    completed=sum(r["provider_state"]=="PROVIDER_RESULT_RETURNED" for r in safe)
    ready=completed==8 and wstatus=="PROVIDER_RESULT_RETURNED"
    ready=bool(ready and all(wt.get(k) is not None for k in ("ptm","avg_lddt"))
        and all(all(r.get(k) is not None for k in ("ptm","avg_lddt")) for r in safe))
    cal={"classification":"INCOMPLETE_NO_CALIBRATION" if not ready else "EXPLORATORY_STRATIFIED_DESCRIPTIVE_ONLY",
         "eight_mutants_with_provider_results":completed,
         "study_design":"OUTCOME_STRATIFIED_NO_HELD_OUT_TEST",
         "topa_independent_review":"OPEN",
         "aura_oracle_role":"NO_UNVALIDATED_PROGNOSTICATION_AS_SCIENCE",
         "weights_self_modified":False,
         "new_experiments_authorized_by_calibration":False,
         "next_research_proposal":"AUDIT_RAW_ASSAY_LABEL_DIRECTION_AND_INDEPENDENT_VARIANT_HOLDOUT"}
    if ready:
        assoc={}
        for field in ("ptm","avg_lddt"):
            sx=[r["published_processed_label"] for r in safe]
            sy=[r[field]-wt[field] for r in safe]
            assoc[field]=paired_spearman(sx,sy)
        upstream=data.get("spearman_processed_label_vs_delta_structure_confidence") or {}
        for field in ("ptm","avg_lddt"):
            expected=upstream.get(field)
            if assoc[field] is None:
                if expected is not None:raise EvidenceHold("UPSTREAM_CORRELATION_CONTRADICTION")
            elif expected is None or abs(number(expected,lo=-1,hi=1)-assoc[field])>0.000002:
                raise EvidenceHold("INDEPENDENT_CORRELATION_REPLAY_MISMATCH")
        cal["spearman_processed_assay_label_vs_delta_structural_confidence"]=assoc
        cal["uncertainty"]="N=8 OUTCOME-STRATIFIED; NO INDEPENDENT VALIDATION; NO CLAIM OF BIOLOGICAL CAUSALITY"
    charge_alarms=[r["mutation"] for r in safe if r.get("provider_credit_cap_alert")]
    if charge_alarms:
        cal["classification"]="BUDGET_ALERT_FAIL_CLOSED"
        cal["next_research_proposal"]="HALT_NEW_STUDIES_AND_INDEPENDENTLY_AUDIT_PROVIDER_BILLING"
    elif ready:
        rho=cal.get("spearman_processed_assay_label_vs_delta_structural_confidence",{})
        numeric=[abs(v) for v in rho.values() if v is not None]
        if not numeric:
            cal["next_research_proposal"]="CHECK_UNINFORMATIVE_STRUCTURE_CONFIDENCE_AND_PREPARE_NEGATIVE_CONTROLS"
        elif max(numeric)>=0.7:
            cal["next_research_proposal"]="DESIGN_INDEPENDENT_PRE_REGISTERED_HELDOUT_VALIDATION"
        elif max(numeric)<0.3:
            cal["next_research_proposal"]="FALSIFY_CONFIDENCE_AS_FITNESS_PROXY_ON_INDEPENDENT_ASSAY"
        else:
            cal["next_research_proposal"]="PRE_REGISTER_BLIND_VALIDATION_WITH_ASSAY_TRANSFORM_CONTROLS"
    cal["credit_cap_alert_mutations"]=charge_alarms
    cal["topa_audit_authority"]="HUMAN_OR_INDEPENDENT_REFERENCE_REQUIRED"
    cal["aura_oracle_use"]="HYPOTHESIS_GENERATION_ONLY_NO_SPENDING_AUTHORITY"
    return {
        "schema_id":"janus.meta_registry.rowan_evidence_receipt.v1",
        "method":"READ_ONLY_INDEPENDENT_PROVIDER_RECEIPT_REPLAY",
        "assay":"BBC1_YEAST_Tsuboyama_2023_1TG0",
        "original_public_data_sha256":SHA256_PIN,
        "cases":safe,"wildtype":wt,
        "calibration":cal,
        "science_gates":{
            "experimentally_validated_fitness":"OPEN",
            "raw_lab_assay_units":"UNVERIFIED",
            "independent_holdout":"NOT_PERFORMED",
            "topa":"OPEN",
            "rowan_structural_output":"MODEL_PREDICTION_NOT_EXPERIMENT",
            "self_improving_general_intelligence":"NOT_ESTABLISHED"
        }
    }

def gh_json(endpoint):
    result=subprocess.run(["gh","api","--method","GET",endpoint],
        text=True,capture_output=True,timeout=35)
    if result.returncode!=0:
        raise EvidenceHold("GITHUB_API_UNAVAILABLE")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise EvidenceHold("GITHUB_API_JSON_INVALID") from exc

def last_runs():
    query=f"repos/{SOURCE_REPO}/actions/workflows/{WORKFLOW}/runs?per_page={MAX_RUNS}&branch=main&status=completed"
    info=gh_json(query)
    rows=info.get("workflow_runs",[])
    if not isinstance(rows,list):raise EvidenceHold("RUN_COLLECTION_NOT_LIST")
    return [r for r in rows if r.get("conclusion")=="success" and r.get("head_branch")=="main"
        and r.get("event") in ("schedule","workflow_dispatch") and isinstance(r.get("id"),int)]

def fetch_artifact(run_id):
    meta=gh_json(f"repos/{SOURCE_REPO}/actions/runs/{run_id}/artifacts?per_page=60")
    name=ARTIFACT_PREFIX+str(run_id)
    matches=[a for a in meta.get("artifacts",[]) if a.get("name")==name and not a.get("expired")]
    if len(matches)!=1:raise EvidenceHold("MATCHING_UNEXPIRED_ARTIFACT_NOT_UNIQUE")
    with TemporaryDirectory(prefix="janus-rowan-artifact-") as tmp:
        completed=subprocess.run(["gh","run","download",str(run_id),"--repo",SOURCE_REPO,
              "--name",name,"--dir",tmp],capture_output=True,text=True,timeout=70)
        if completed.returncode!=0:raise EvidenceHold("RUN_ARTIFACT_DOWNLOAD_FAILED")
        files=list(Path(tmp).rglob("*"))
        files=[f for f in files if f.is_file()]
        if len(files)!=1 or files[0].suffix.lower()!=".json" or files[0].stat().st_size>MAX_RECEIPT:
            raise EvidenceHold("ARTIFACT_PAYLOAD_SHAPE_OR_SIZE_INVALID")
        raw=files[0].read_bytes()
        try:
            return json.loads(raw.decode("utf-8")),hashlib.sha256(raw).hexdigest()
        except (UnicodeDecodeError,json.JSONDecodeError) as exc:
            raise EvidenceHold("ARTIFACT_JSON_INVALID") from exc

def prepare_receipt(run_id, payload, payload_sha):
    v=analyze(payload)
    v["source"]={
        "repo":SOURCE_REPO,
        "workflow_file":WORKFLOW,
        "run_id":run_id,
        "source_artifact_sha256":payload_sha,
        "run_link":f"https://github.com/{SOURCE_REPO}/actions/runs/{run_id}"
    }
    return v

def update_once(root:Path, receipts:list[dict]):
    root=root.resolve()
    paths=[]
    for receipt in receipts:
        run_id=receipt["source"]["run_id"]
        digest=hashlib.sha256(canon(receipt)).hexdigest()
        path=root/BASE/"receipts"/f"ROWAN-S2-{run_id}-{digest[:16]}.json"
        if path.exists():continue
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(json.dumps(receipt,indent=2,ensure_ascii=False,allow_nan=False).encode()+b"\n")
        paths.append(path)
    if receipts:
        newest=max(receipts,key=lambda x:x["source"]["run_id"])
        state_path=root/BASE/"CANONICAL_STATE.json"
        state={
            "schema_id":"janus.rowan.observer_state.v1",
            "latest_durable_external_run":newest["source"]["run_id"],
            "latest_source_uri":newest["source"]["run_link"],
            "latest_scientific_status":newest["calibration"]["classification"],
            "last_completed_mutants":newest["calibration"]["eight_mutants_with_provider_results"],
            "budget_guard_alert_mutations":newest["calibration"]["credit_cap_alert_mutations"],
            "calibration_proposal_no_authority":newest["calibration"]["next_research_proposal"],
            "topa_gate":newest["science_gates"]["topa"],
            "observer_alert":"ONLY_ON_VERIFIED_NEW_RESULT_HOLD_OR_BUDGET_GUARD_CHANGE",
            "autonomous_spend_authority":"ONLY_FROZEN_EIGHT_MUTANT_S2_WITH_EXISTING_WEEKLY_BUDGET",
            "new_unreviewed_studies":"PROPOSAL_ONLY_NOT_AUTO_EXECUTED",
            "notification_dedupe_key":hashlib.sha256(canon(newest["calibration"])).hexdigest()[:20],
            "underlying_state_is_derived_from":newest["source"]["source_artifact_sha256"],
        }
        if not state_path.exists() or json.loads(state_path.read_text())!=state:
            state_path.parent.mkdir(parents=True,exist_ok=True)
            state_path.write_bytes(json.dumps(state,indent=2,ensure_ascii=False).encode()+b"\n")
            paths.append(state_path)
    return [str(x.relative_to(root)) for x in paths]

def pending_source_runs(root: Path, runs: list[dict], limit: int) -> tuple[list[dict], int | None]:
    """Only fetch run IDs newer than a verified durable Rowan checkpoint.

    Old workflow attempts can leave duplicate named artifacts. This routine
    does not select from ambiguous duplicates. Newly discovered runs still
    require the existing strict single-artifact verification.
    """
    root=Path(root)
    state_file=root/BASE/"CANONICAL_STATE.json"
    if not state_file.exists():
        return runs[:limit],None
    state=json.loads(state_file.read_text(encoding="utf-8"))
    if state.get("schema_id")!="janus.rowan.observer_state.v1":
        raise EvidenceHold("INVALID_PREVIOUS_CANONICAL_SCHEMA")
    checkpoint=state.get("latest_durable_external_run")
    source_digest=state.get("underlying_state_is_derived_from")
    completed=state.get("last_completed_mutants")
    if (type(checkpoint) is not int or checkpoint<=0 or
        type(completed) is not int or not 0<=completed<=8 or
        not isinstance(source_digest,str) or not re.fullmatch(r"[0-9a-f]{64}",source_digest)):
        raise EvidenceHold("INVALID_PREVIOUS_CANONICAL_CHECKPOINT")
    matched=False
    for file in sorted((root/BASE/"receipts").glob(f"ROWAN-S2-{checkpoint}-*.json")):
        if file.stat().st_size>MAX_RECEIPT:
            raise EvidenceHold("PREVIOUS_RECEIPT_OVERSIZED")
        previous=json.loads(file.read_text(encoding="utf-8"))
        if (previous.get("source",{}).get("run_id")==checkpoint and
            previous.get("source",{}).get("source_artifact_sha256")==source_digest and
            previous.get("calibration",{}).get("eight_mutants_with_provider_results")==completed):
            matched=True
            break
    if not matched:
        raise EvidenceHold("PREVIOUS_CANONICAL_SOURCE_RECEIPT_NOT_ATTESTED")
    if not runs or max(int(x["id"]) for x in runs)<checkpoint:
        raise EvidenceHold("GITHUB_HISTORY_BEHIND_DURABLE_CHECKPOINT")
    return [x for x in runs if int(x["id"])>checkpoint][:limit],checkpoint


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",default=".")
    parser.add_argument("--limit",type=int,default=8)
    args=parser.parse_args()
    if not 1<=args.limit<=MAX_RUNS:raise SystemExit("BAD_LIMIT")
    receipts=[]
    try:
        selected,checkpoint=pending_source_runs(Path(args.root),last_runs(),args.limit)
        for run in selected:
            rid=run["id"]
            raw,sha=fetch_artifact(rid)
            receipts.append(prepare_receipt(rid,raw,sha))
        if not receipts:
            print("ROWAN_OBSERVER=NO_NEW_SOURCE_RUNS_ALREADY_ATTESTED")
            print("ROWAN_OBSERVER_LAST_DURABLE_RUN="+str(checkpoint))
            return 0
        modified=update_once(Path(args.root),receipts)
        print("ROWAN_OBSERVER=VERIFIED_SOURCE_RECEIPTS")
        print("ROWAN_OBSERVER_PROCESSED="+str(len(receipts)))
        print("ROWAN_OBSERVER_CHANGED_FILES="+str(len(modified)))
        print("ROWAN_OBSERVER_LATEST_RUN="+str(max(r["source"]["run_id"] for r in receipts)))
        return 0
    except (EvidenceHold, OSError, ValueError, subprocess.SubprocessError) as exc:
        print("ROWAN_OBSERVER=BLOCKED_"+type(exc).__name__)
        return 2

if __name__=="__main__":raise SystemExit(main())
