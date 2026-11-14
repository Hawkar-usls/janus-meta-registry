#!/usr/bin/env python3
"""Independent ESSENCE v1.7 public GitHub source-and-no-authority witness.

Verifies exact immutable source bytes from a pinned Demiurge merge commit
without executing downloaded Python or deserializing model weights. Checks
the Meta Registry append-only record and reports that actual independent
closed-data, hardware and live rollback evidence is STILL MISSING.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
STATUS=ROOT/"data/essence/v17/JANUS_ESSENCE_REAL_MODEL_ADMISSION_HOLD_2026-11-14.json"
STATUS_BLOB="7d19cfb18668eea26dc25a4503c5883d4eb0f225"
CHECKER_COMMIT="1815939c15506ad380af521254338f0794adf255"
CHECKER_BLOB="9f661cddf3a5cc11268986cb8748f3d0fc9f1867"
CHECKPOINT_BLOB="88cad884b437dd0ab655d913b1c83d6a6d669735"
CHECKPOINT_SHA256="fc767adb812ac3bea54c44cbccfa9680941f95e2c8a77120559b41da044d9463"

def git_blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def get_raw(repo,commit,path,max_bytes):
    if (repo!="Hawkar-usls/Janus-Demiurge"
        or commit!=CHECKER_COMMIT
        or path not in ("tools/essence_v17_three_gate_review.py",
                        "janus_model/checkpoints/promoted.pt")):
        raise ValueError("UNPINNED_REMOTE_SOURCE")
    url=f"https://raw.githubusercontent.com/{repo}/{commit}/{path}"
    with urlopen(Request(url,headers={"User-Agent":"janus-essence-v17-github-source-witness"}),
                 timeout=25) as response:
        data=response.read(max_bytes+1)
    if not data or len(data)>max_bytes:
        raise ValueError("REMOTE_SOURCE_MISSING_OR_TOO_LARGE")
    return data

def status_record():
    if STATUS.is_symlink() or git_blob(STATUS.read_bytes())!=STATUS_BLOB:
        raise ValueError("META_REGISTRY_STATUS_CHANGED")
    data=json.loads(STATUS.read_text())
    if (data.get("schema")!="janus.essence.real_model_admission_evidence_status/1.7"
        or data.get("reviewer",{}).get("merged_commit")!=CHECKER_COMMIT
        or data["reviewer"]["reviewer_git_blob_sha1"]!=CHECKER_BLOB
        or data.get("candidate",{}).get("source_model_checkpoint_sha256")!=CHECKPOINT_SHA256
        or data.get("admission",{}).get("production_model_swap_allowed") is not False
        or data["admission"].get("automatic_model_swap_allowed") is not False
        or data["admission"].get("genuine_external_evidence")!="HOLD"
        or data["admission"].get("actual_service_canary_and_rollback")!="HOLD"):
        raise ValueError("META_REGISTRY_STATUS_AUTHORITY_DRIFT")
    return data

def witness(fetch=get_raw):
    record=status_record()
    code=fetch("Hawkar-usls/Janus-Demiurge",CHECKER_COMMIT,
              "tools/essence_v17_three_gate_review.py",100_000)
    model=fetch("Hawkar-usls/Janus-Demiurge",CHECKER_COMMIT,
               "janus_model/checkpoints/promoted.pt",2_500_000)
    if git_blob(code)!=CHECKER_BLOB:
        raise ValueError("EXTERNAL_VERIFIER_CODE_CHANGED")
    if git_blob(model)!=CHECKPOINT_BLOB or hashlib.sha256(model).hexdigest()!=CHECKPOINT_SHA256:
        raise ValueError("SOURCE_CHECKPOINT_CHANGED")
    output={
       "schema":"janus.essence.independent_public_source_witness/1.7",
       "checker_merged_commit":CHECKER_COMMIT,
       "checker_git_blob_sha1":CHECKER_BLOB,
       "source_checkpoint_git_blob_sha1":CHECKPOINT_BLOB,
       "source_checkpoint_sha256":CHECKPOINT_SHA256,
       "github_source_replayed_without_execution":True,
       "checkpoint_bytes_examined_only_as_opaque_bytes":True,
       "meta_registry_record_git_blob_sha1":STATUS_BLOB,
       "run_was_read_only":True,
       "externally_custodied_private_holdout":False,
       "target_hardware_benchmark":False,
       "actual_deployed_service_rollback":False,
       "four_real_signer_attestations":False,
       "research_code_contract_pass":True,
       "operational_admission":"HOLD",
       "production_authority":False,
       "automatic_model_change":False,
    }
    canonical=json.dumps(output,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    output["receipt_sha256"]=hashlib.sha256(canonical).hexdigest()
    return output

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--out",default="runtime/essence_v17/independent_source_witness.json")
    a=p.parse_args()
    result=witness()
    f=Path(a.out)
    if f.exists():raise FileExistsError("READONLY_WITNESS_NO_OVERWRITE")
    f.parent.mkdir(parents=True,exist_ok=True)
    f.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["operational_admission"],
                      "source_verified":result["research_code_contract_pass"],
                      "production_authority":False,"receipt_sha256":result["receipt_sha256"]},
                    sort_keys=True))

if __name__=="__main__":main()
