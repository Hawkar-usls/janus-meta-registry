#!/usr/bin/env python3
"""TOPA independent triage of durable Beetle discovery ACK, no provider or billing."""
from __future__ import annotations
import hashlib,json,math,re,subprocess
from pathlib import Path
from urllib.parse import urlparse

TARGET="Hawkar-usls/janus-meta-registry"
BASE=Path("data/rowan/coordination/topa_triage")
HEX64=re.compile(r"^[0-9a-f]{64}$")
BID=re.compile(r"^[0-9a-f]{20}$")
HOSTS={"arxiv.org":"/abs/","zenodo.org":"/records/","github.com":"/"}
class Hold(ValueError):pass

def canon(v):return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
def digest(v):return hashlib.sha256(canon(v)).hexdigest()

def relevant(item):
    t=(str(item.get("title",""))+" "+str(item.get("summary",""))).casefold()
    return (any(v in t for v in ("protein","proteolys","bbc1","tsuboyama","1tg0","proteingym"))
      and any(v in t for v in ("mutat","substitut","variant","bbc1","tsuboyama","1tg0","ddg","δδg"))
      and any(v in t for v in ("stabil","proteolys","assay","thermodynam","fold","ddg","δδg")))

def verify_item(x):
    if x.get("schema")!="janus.beetle.repo_memory_item.v2" or x.get("target_repository")!=TARGET:
        raise Hold("UNTRUSTED_ITEM_SCHEMA")
    if x.get("epistemic_status")!="DISCOVERY_INBOX__UNVERIFIED__NO_PROOF_AUTHORITY":
        raise Hold("EVIDENCE_ESCALATION")
    if x.get("mirror_lens") not in ("FORWARD","REVERSE","COUNTEREVIDENCE","CONTROL"):
        raise Hold("UNKNOWN_LENS")
    u=x.get("url")
    if not isinstance(u,str) or len(u)>1200:raise Hold("URL_INVALID")
    p=urlparse(u)
    if p.scheme!="https" or p.netloc not in HOSTS or not p.path.startswith(HOSTS[p.netloc]) or p.username or p.password:
        raise Hold("URL_NOT_ALLOWLISTED")
    if not HEX64.fullmatch(str(x.get("source_context_sha256",""))):
        raise Hold("SOURCE_DIGEST_MISSING")
    if not isinstance(x.get("candidate_id"),str) or len(x["candidate_id"])>100:
        raise Hold("CANDIDATE_ID_INVALID")
    s=x.get("score")
    if type(s) not in (int,float) or not math.isfinite(s) or not 0<=s<=10000:
        raise Hold("SCORE_INVALID")

def triage(ack,batch,commit):
    if ack.get("schema")!="janus.beetle.inbox_ack.v1" or ack.get("target_repository")!=TARGET or ack.get("status")!="INBOX_DURABLE_UNVERIFIED__NOT_RUNTIME_CONSUMPTION" or ack.get("scientific_authority_delta")!=0:
        raise Hold("ACK_NOT_DURABLE")
    n=ack.get("last_sequence"); bid=ack.get("batch_id")
    if type(n)!=int or n<1 or not isinstance(bid,str) or not BID.fullmatch(bid) or not HEX64.fullmatch(str(ack.get("sha256",""))):
        raise Hold("ACK_IDENTITY_INVALID")
    if batch.get("schema")!="janus.beetle.repo_memory_batch.v1" or batch.get("batch_id")!=bid or batch.get("target_repository")!=TARGET or batch.get("claim_ceiling")!="DISCOVERY_MEMORY_ONLY__TARGET_REPO_MUST_VERIFY_INDEPENDENTLY":
        raise Hold("BATCH_NOT_ACK_MATCHED")
    items=batch.get("items")
    if not isinstance(items,list) or len(items)>64:raise Hold("UNBOUNDED_ITEMS")
    parts=batch.get("fragment_count"); index=batch.get("fragment_index")
    if type(parts)!=int or type(index)!=int or not 1<=index<=parts<=10:raise Hold("FRAGMENTS_INVALID")
    if not isinstance(commit,str) or not HEX64.fullmatch(commit):raise Hold("RECEIVER_COMMIT_UNPINNED")
    accepted=[]; seen=set(); raw_count=0
    for x in items:
        if not isinstance(x,dict):raise Hold("ITEM_NOT_OBJECT")
        if x.get("base_direction_id")!="protein_stability_falsifiers":continue
        raw_count+=1
        verify_item(x)
        key=(x["candidate_id"],x["source_context_sha256"])
        if key in seen:continue
        seen.add(key)
        if not relevant(x):continue
        accepted.append({"title":str(x.get("title",""))[:250],
                         "source_url":x["url"],"candidate_id":x["candidate_id"],
                         "source_context_sha256":x["source_context_sha256"],
                         "mirror_lens":x["mirror_lens"],"originating_source":x.get("source"),
                         "status":"UNVERIFIED_DISCOVERY_CANDIDATE_ONLY",
                         "topa_primary_data_audit":"NOT_PERFORMED"})
    accepted.sort(key=lambda x:(x["candidate_id"],x["source_context_sha256"]))
    result={"schema_id":"janus.topa.rowan.beetle_durable_candidate_triage.v1",
            "source":{"repo":TARGET,"branch":"beetle-memory","exact_receiver_commit":commit,
                      "ack_sequence":n,"ack_batch_id":bid,"ack_sha256":ack["sha256"],
                      "ack_object_sha256":digest(ack),"batch_object_sha256":digest(batch),
                      "fragment_count":parts,"fragment_index":index},
            "counts":{"total_items":len(items),"protein_direction_items":raw_count,
                      "domain_relevant_unique":len(accepted)},
            "candidate_previews":accepted[:12],
            "some_previews_omitted":len(accepted)>12 or parts>1,
            "authority":{"topa_independent_primary_source_review":"OPEN",
                         "discovery_candidate_is_evidence":False,"new_rowan_jobs":0,
                         "new_credit_spend":0,"promoted_weights":False}}
    result["content_sha256"]=digest(result)
    return result

def git_json(commit,path):
    r=subprocess.run(["git","show",commit+":"+path],capture_output=True,timeout=30)
    if r.returncode or len(r.stdout)>1000000:raise Hold("ACK_BRANCH_UNREADABLE")
    return json.loads(r.stdout.decode())

def run():
    try:
        commit=subprocess.check_output(["git","rev-parse","FETCH_HEAD"],text=True,timeout=10).strip()
        ack=git_json(commit,"data/beetle-inbox/ACK.json")
        bid=ack.get("batch_id","")
        if not isinstance(bid,str) or not BID.fullmatch(bid):raise Hold("ACK_PATH_REJECTED")
        batch=git_json(commit,"data/beetle-inbox/batches/"+bid+".json")
        result=triage(ack,batch,commit)
        path=BASE/("TOPA-BEETLE-%d-%s.json"%(ack["last_sequence"],result["content_sha256"][:16]))
        blob=json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2).encode()+b"\n"
        if path.exists() and path.read_bytes()!=blob:raise Hold("APPEND_ONLY_CONFLICT")
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():path.write_bytes(blob)
        print("TOPA_BEETLE_TRIAGE=VERIFIED_DURABLE_SOURCE_METADATA_ONLY")
        print("TOPA_BEETLE_RELEVANT="+str(result["counts"]["domain_relevant_unique"]))
    except (Hold,OSError,ValueError,subprocess.SubprocessError) as e:
        print("TOPA_BEETLE_TRIAGE=INBOX_HOLD_NOT_PROMOTED")
        print("TOPA_BEETLE_REASON="+type(e).__name__)
    return 0

if __name__=="__main__":raise SystemExit(run())
