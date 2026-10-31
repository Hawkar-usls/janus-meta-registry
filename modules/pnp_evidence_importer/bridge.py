#!/usr/bin/env python3
"""Append-only JANUS PNP content evidence importer (read-only GitHub sources).

Existing journal entries are immutable. Observations and finite replays are
never scientific promotion. Owned Meta Registry GITHUB_TOKEN is sole writer.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.request import Request,urlopen

SCHEMA="janus.registry.pnp_content_import.v1"
OWNER="Hawkar-usls"
ROOT_REPO="Janus-Demiurge"
SOURCE_PATH="janus_model/state/JANUS_PNP_AUTORESEARCH_CONTEXT.json"
DEST="data/pnp_evidence_import"
SHA40=re.compile("[a-f0-9]{40}\\Z")
SHA64=re.compile("[a-f0-9]{64}\\Z")
MAX_SOURCE=200000

class IntakeHold(ValueError):
    pass

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def hash_obj(value):
    return sha(canonical(value))

def sha40(value):
    return isinstance(value,str) and SHA40.fullmatch(value) is not None

def sha64(value):
    return isinstance(value,str) and SHA64.fullmatch(value) is not None

class GithubRead:
    def get(self,url,limit=MAX_SOURCE):
        headers={"User-Agent":"JANUS-PNP-evidence-importer/1",
                 "Accept":"application/vnd.github+json"}
        token=os.getenv("GITHUB_TOKEN","")
        if token and url.startswith("https://api.github.com/"):
            headers["Authorization"]="Bearer "+token
        with urlopen(Request(url,headers=headers),timeout=25) as h:
            raw=h.read(limit+1)
        if len(raw)>limit or not raw:
            raise IntakeHold("EXTERNAL_SOURCE_SIZE_OR_EMPTY")
        return raw
    def head(self,repo):
        try:
            value=json.loads(self.get("https://api.github.com/repos/"+OWNER+"/"+repo+"/commits/main"))
            commit=value["sha"]
        except (ValueError,KeyError) as exc:
            raise IntakeHold("SOURCE_HEAD_UNAVAILABLE") from exc
        if not sha40(commit):
            raise IntakeHold("INVALID_SOURCE_HEAD")
        return commit
    def file(self,repo,commit,path):
        if not sha40(commit) or path.startswith("/") or ".." in path.split("/") \
                or not re.fullmatch("[a-zA-Z0-9_./-]+",path):
            raise IntakeHold("SOURCE_PATH_REJECTED")
        return self.get("https://raw.githubusercontent.com/"+OWNER+"/"+repo+"/"+commit+"/"+path)

def strict_obj(raw,reason):
    try:
        obj=json.loads(raw)
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:
        raise IntakeHold(reason) from exc
    if not isinstance(obj,dict):
        raise IntakeHold(reason)
    return obj

def check_context(context):
    if not isinstance(context,dict) or context.get("schema")!="janus.pnp_autoresearch_context.v1":
        raise IntakeHold("CONTEXT_SCHEMA")
    body=dict(context)
    tag=body.pop("context_sha256",None)
    if not sha64(tag) or tag!=hash_obj(body):
        raise IntakeHold("CONTEXT_HASH")
    if context.get("status")!="ACTIVE_CANDIDATE_RESEARCH" or \
            context.get("fundamentum",{}).get("tracks",{}).get("P_VS_NP")!="OPEN":
        raise IntakeHold("PNP_CLAIM_BOUNDARY")
    science=context.get("authority",{})
    if not isinstance(science,dict) or any(value is not False for value in science.values()):
        raise IntakeHold("SUPERVISOR_AUTHORITY")
    supervisor=context.get("research_supervisor",{})
    if not isinstance(supervisor,dict) or supervisor.get("status")!="ACTIVE_FAIL_CLOSED" \
            or supervisor.get("promotion_barrier")!="BLOCKED" \
            or any(value is not False for key,value in supervisor.items()
                   if key in {"autonomous_merge","fundamentum_mutation","scientific_claim_promotion","p_vs_np_auto_promotion"}):
        raise IntakeHold("SUPERVISOR_PROMOTION")
    routes=supervisor.get("candidate_routes")
    if not isinstance(routes,list) or not routes or \
            any(not isinstance(x,dict) or x.get("promotion_barrier")!="BLOCKED" or
                x.get("content_evidence_verification")!="FINITE_ONLY_NO_PROMOTION" for x in routes):
        raise IntakeHold("SUPERVISOR_ROUTE_PROMOTION")
    content=context.get("content_evidence_bundle")
    if not isinstance(content,dict):
        raise IntakeHold("CONTENT_BUNDLE_MISSING")
    body=dict(content)
    digest=body.pop("bundle_sha256",None)
    if not sha64(digest) or hash_obj(body)!=digest \
            or content.get("schema")!="janus.pnp.content_evidence_bundle.v1" \
            or content.get("status")!="BOUNDED_SOURCE_CONTENT_REPLAYED" or \
            content.get("p_vs_np")!="OPEN":
        raise IntakeHold("CONTENT_BUNDLE_HASH_OR_SCOPE")
    if any(v is not False for v in content.get("authority",{}).values()):
        raise IntakeHold("CONTENT_AUTHORITY_MISMATCH")
    evid=supervisor.get("content_evidence",{})
    if not isinstance(evid,dict) or evid.get("bundle_sha256")!=digest \
            or evid.get("may_satisfy_promotion_gate") is not False \
            or evid.get("source_truth_independently_proven") is not False:
        raise IntakeHold("SUPERVISOR_CONTENT_PROVENANCE")
    f=content.get("fundamentum",{});t=content.get("topa",{});b=content.get("beetle",{})
    if f.get("source_commit")!=context.get("fundamentum",{}).get("commit") \
            or not sha40(f.get("source_commit")) or not sha40(t.get("source_commit")) \
            or not sha40(b.get("source_commit")):
        raise IntakeHold("CROSS_SOURCE_COMMIT_BINDING")
    if t.get("source_reported_result")!="REFUTED_FOR_CURRENT_POLICY0A" \
            or t.get("global_p_vs_np_result")!="OPEN" or \
            t.get("independent_finite_replay",{}).get("full_policy0a_replay_executed") is not False \
            or f.get("independent_finite_replay",{}).get("general_theorem_proved") is not False \
            or b.get("independent_source_truth_established") is not False:
        raise IntakeHold("SCIENCE_CONCLUSION_OVERRUN")
    if not all(sha64(x.get("sha256")) for x in (f,t)):
        raise IntakeHold("SOURCE_BYTES_SHA_MISSING")
    if type(b.get("last_processed_sequence")) is not int:
        raise IntakeHold("BEETLE_SEQUENCE_INVALID")
    return content

def check_sources(fetch,content):
    f=content["fundamentum"];t=content["topa"];b=content["beetle"]
    if f.get("repository")!="Hawkar-usls/Janus-Fundamentum" or \
            t.get("repository")!="Hawkar-usls/TOPA":
        raise IntakeHold("SOURCE_REPOSITORY_NOT_APPROVED")
    for name,s in (("Janus-Fundamentum",f),("TOPA",t)):
        path=s.get("path")
        if path not in ("docs/CURRENT_RESEARCH_STATUS.md",
                        "data/TOPA-P-VS-NP-ISSUE-211-REFUTATION-FINAL-2026-08-24-v1.0.json"):
            raise IntakeHold("SOURCE_PATH_NOT_APPROVED")
        raw=fetch.file(name,s["source_commit"],path)
        if sha(raw)!=s["sha256"]:
            raise IntakeHold("PRIMARY_SOURCE_SHA256_DIFFERS")
    ctx=strict_obj(fetch.file("Janus-Demiurge",b["source_commit"],
                              "data/beetle-runtime/CONTEXT.json"),"BEETLE_CONTEXT_PARSE")
    ack=strict_obj(fetch.file("Janus-Demiurge",b["source_commit"],
                              "data/beetle-runtime/PROCESSING_ACK.json"),"BEETLE_ACK_PARSE")
    c=dict(ctx);c_hash=c.pop("context_sha256",None)
    if c_hash!=hash_obj(c) or c_hash!=b.get("source_context_sha256") or \
            c.get("last_processed_sequence")!=ack.get("last_sequence") or \
            ack.get("last_sequence")!=b["last_processed_sequence"] or \
            ack.get("receipt_sha256")!=b.get("last_processing_receipt_sha256"):
        raise IntakeHold("BEETLE_SOURCE_CONTEXT_ACK_DRIFT")
    if ctx.get("capabilities",{}).get("is_verified_evidence") is not False or \
            ctx.get("capabilities",{}).get("may_grant_mutation_authority") is not False:
        raise IntakeHold("BEETLE_PRIVILEGE_DRIFT")
    return {"fundamentum_bytes_rehashed":True,"topa_bytes_rehashed":True,
            "beetle_context_and_ack_rehashed":True,
            "independent_source_truth_established":False}

def build_record(context,demiurge_commit,verified,observed):
    if not sha40(demiurge_commit):
        raise IntakeHold("DEMIURGE_HEAD_BAD")
    source=check_context(context)
    return {"schema":SCHEMA,"status":"ARCHIVE_READ_ONLY_BOUNDED_EVIDENCE_NOT_PROOF",
            "observed_at_utc":observed,
            "origin":{"repo":"Hawkar-usls/Janus-Demiurge",
                      "commit":demiurge_commit,"path":SOURCE_PATH,
                      "context_sha256":context["context_sha256"]},
            "source_check":verified,
            "source_commits":{
                "fundamentum":source["fundamentum"]["source_commit"],
                "topa":source["topa"]["source_commit"],
                "beetle":source["beetle"]["source_commit"]},
            "content_bundle_sha256":source["bundle_sha256"],
            "content_evidence_bundle":source,
            "candidate_research_handoffs":context["research_supervisor"]["candidate_routes"],
            "proof_status":"P_VS_NP_OPEN",
            "authority_delta":0,
            "scientific_promotion":False,
            "independent_asymptotic_proof_verified":False,
            "beetle_discovery_is_proof":False}

def persist(root,record):
    output=root/DEST
    output.mkdir(parents=True,exist_ok=True)
    tag=record["origin"]["context_sha256"]
    if not sha64(tag):
        raise IntakeHold("RECORD_HASH_INVALID")
    path=output/"records"/(tag+".json")
    def scientific_identity(r):
        stable={k:v for k,v in r.items() if k!="observed_at_utc"}
        stable["origin"]={k:v for k,v in stable["origin"].items() if k!="commit"}
        return stable
    stable=scientific_identity(record)
    if path.exists():
        existing=strict_obj(path.read_bytes(),"REGISTRY_RECORD_BAD")
        if scientific_identity(existing)!=stable:
            raise IntakeHold("IMMUTABLE_RECORD_CONFLICT")
        return {"status":"IDEMPOTENT_NO_CHANGE","record":str(path)}
    path.parent.mkdir(parents=True,exist_ok=True)
    # Deterministic provenance key; no rewrite of historical immutable records.
    raw=json.dumps(record,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    path.write_text(raw,encoding="utf-8")
    history=output/"HISTORY.jsonl"
    old=history.read_text(encoding="utf-8") if history.exists() else ""
    if old and not old.endswith("\n"):
        raise IntakeHold("HISTORY_FORMAT_INVALID")
    line={"schema":"janus.registry.pnp_content_journal.v1",
          "context_sha256":tag,"demiurge_commit":record["origin"]["commit"],
          "content_bundle_sha256":record["content_bundle_sha256"],
          "source_commits":record["source_commits"],
          "observed_at_utc":record["observed_at_utc"],
          "scientific_promotion":False}
    history.write_text(old+json.dumps(line,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    latest=output/"LATEST.json"
    latest.write_text(json.dumps({"schema":"janus.registry.pnp_content_latest.v1",
                                  "context_sha256":tag,"relative_record_path":"records/"+tag+".json",
                                  "proof_status":"P_VS_NP_OPEN","authority_delta":0},
                                 indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return {"status":"APPENDED_UNMODIFIED_HISTORY","record":str(path)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    args=p.parse_args()
    fetch=GithubRead()
    sha_head=fetch.head(ROOT_REPO)
    raw=fetch.file(ROOT_REPO,sha_head,SOURCE_PATH)
    context=strict_obj(raw,"DEMIURGE_CONTEXT_NOT_JSON")
    content=check_context(context)
    verified=check_sources(fetch,content)
    observed=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    record=build_record(context,sha_head,verified,observed)
    print(json.dumps(persist(args.root,record),sort_keys=True))
if __name__=="__main__":
    main()
