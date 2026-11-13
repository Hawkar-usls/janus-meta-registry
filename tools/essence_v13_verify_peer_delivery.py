#!/usr/bin/env python3
"""Independently verify six GitHub-stored ESSENCE peer inboxes by pinned blobs.

HTTP(S) GET requests are restricted to exact public GitHub raw URLs for known
source commits. No remote Python is imported, executed or interpreted beyond
JSON parsing. The witness is evidence of GitHub file delivery, not model gain.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"data"/"essence"/"v13"/"JANUS_ESSENCE_GITHUB_PEER_DELIVERY_2026-11-14.json"
SCHEMA="janus.essence.github_peer_delivery_witness/1.3"
SOURCE_LEDGER="249ff817dc5436b967114331aaa394c55e324efa"
SOURCE_COMMIT="88c5eec58a5a8cdd0844034b2dcf584cfb67a8ec"
CODE_BLOB="6a08b366fe1556186a9681e51102d51e241e981d"
OWNED=(
 "Hawkar-usls/Janus_Genesis",
 "Hawkar-usls/Janus-Demiurge",
 "Hawkar-usls/Demi_Head",
 "Hawkar-usls/janus-distributed-ai-swarm",
 "Hawkar-usls/Janus-Cosmos",
 "Hawkar-usls/Hrain",
)

def canonical(x):
    return json.dumps(x,ensure_ascii=False,sort_keys=True,
                      separators=(",",":"),allow_nan=False).encode("utf-8")

def digest(x):
    return hashlib.sha256(canonical(x)).hexdigest()

def git_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def is_hex(x,n):
    return isinstance(x,str) and len(x)==n and all(c in "0123456789abcdef" for c in x)

def load():
    if SOURCE.is_symlink() or not SOURCE.is_file() or SOURCE.stat().st_size>15000:
        raise ValueError("UNSAFE_EVIDENCE_SOURCE")
    return json.loads(SOURCE.read_text(encoding="utf-8"),
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))

def validate(doc):
    if (not isinstance(doc,dict) or doc.get("schema")!=SCHEMA
            or doc.get("method")!="GITHUB_VERSIONED_JSON_INBOX_PER_REPOSITORY_WITH_INDEPENDENT_SOURCE_PIN"
            or doc.get("source_exchange_merge_commit_sha1")!=SOURCE_COMMIT
            or doc.get("source_ledger_git_blob_sha1")!=SOURCE_LEDGER
            or doc.get("validator_code_git_blob_sha1")!=CODE_BLOB
            or doc.get("claim")!="SIX_VERSIONED_JSON_OFFERS_DELIVERED_TO_MERGED_REPOSITORIES_AND_PR_VERIFIED"
            or doc.get("evidence_tier")!="GITHUB_MERGED_MAIN_AND_SUCCESSFUL_PEER_INBOX_PR_CI"):
        raise ValueError("INVALID_GITHUB_PEER_DELIVERY_CLAIM")
    receivers=doc.get("receivers")
    if not isinstance(receivers,list) or len(receivers)!=6:
        raise ValueError("MISSING_DELIVERY_RECEIVERS")
    if {r.get("repository") for r in receivers if isinstance(r,dict)}!=set(OWNED):
        raise ValueError("INVALID_RECEIVER_SET")
    for item in receivers:
        if (item.get("source_repository") not in OWNED
                or item["source_repository"]==item["repository"]
                or not is_hex(item.get("merge_commit_sha1"),40)
                or not is_hex(item.get("inbox_git_blob_sha1"),40)
                or not is_hex(item.get("source_offer_sha256"),64)
                or type(item.get("pr_number")) is not int or item["pr_number"]<1
                or type(item.get("ci_run_id")) is not int or item["ci_run_id"]<1
                or item.get("ci_conclusion")!="success"
                or item.get("source_code_imported") is not False
                or item.get("proposal_executed") is not False
                or item.get("production_authority") is not False
                or item.get("automatic_model_promotion") is not False):
            raise ValueError("FORGED_OR_UNSAFE_PEER_DELIVERY")
    limits=doc.get("limits")
    if (not isinstance(limits,dict) or limits.get("github_only") is not True
            or any(limits.get(key) is not False for key in (
                "automated_cross_repo_live_inference",
                "verified_new_model_performance_gain",
                "external_independent_blind_trial",
                "peer_control_messages_sent",
                "actual_software_module_activation",
                "roundtrip_communication_to_runtime"))):
        raise ValueError("PREMATURE_MODEL_AUTHORITY")
    return True

def github_raw(repo,commit,path,max_bytes=50000):
    if repo not in OWNED+("Hawkar-usls/janus-meta-registry",):
        raise ValueError("REMOTE_REPO_NOT_ALLOWED")
    if not is_hex(commit,40) or path not in (
            "research/essence/peer_v13/inbox.json",
            ".janus/essence/peer_inbox_v13.py",
            "data/essence/v13/JANUS_ESSENCE_GITHUB_PEER_LINEAGE_2026-11-14.json"):
        raise ValueError("REMOTE_PATH_NOT_ALLOWED")
    url="https://raw.githubusercontent.com/"+repo+"/"+commit+"/"+path
    request=Request(url,headers={"User-Agent":"janus-essence-github-readonly-witness/1.3"})
    with urlopen(request,timeout=15) as reply:
        raw=reply.read(max_bytes+1)
    if not 2<=len(raw)<=max_bytes:
        raise ValueError("REMOTE_CONTENT_BOUND")
    return raw

def check_inbox(item,raw):
    if git_blob(raw)!=item["inbox_git_blob_sha1"]:
        raise ValueError("GITHUB_INBOX_BLOB_CHANGED")
    obj=json.loads(raw.decode("utf-8"))
    offer=obj.get("offer",{})
    if (obj.get("schema")!="janus.essence.github_repo_peer_inbox/1.3"
            or obj.get("repository")!=item["repository"]
            or obj.get("source_meta_registry_commit_sha")!=SOURCE_COMMIT
            or obj.get("source_ledger_git_blob_sha1")!=SOURCE_LEDGER
            or obj.get("automatic_merge") is not False
            or obj.get("executable") is not False
            or obj.get("production_authority") is not False
            or offer.get("source_repo")!=item["source_repository"]
            or offer.get("target_repo")!=item["repository"]
            or offer.get("offer_sha256")!=item["source_offer_sha256"]
            or offer.get("offer_sha256")!=digest({k:v for k,v in offer.items() if k!="offer_sha256"})
            or offer.get("proposed_new_algorithm_verified") is not False
            or offer.get("foreign_code_imported") is not False
            or offer.get("performance_evidence")!="NO_NEW_INDEPENDENT_GAIN"
            or offer.get("production_authority") is not False):
        raise ValueError("INVALID_RECEIVED_RESEARCH_OFFER")
    return True

def verify_live(doc):
    validate(doc)
    ledger=github_raw("Hawkar-usls/janus-meta-registry",SOURCE_COMMIT,
                      "data/essence/v13/JANUS_ESSENCE_GITHUB_PEER_LINEAGE_2026-11-14.json")
    if git_blob(ledger)!=SOURCE_LEDGER:
        raise ValueError("META_LINEAGE_BLOB_CHANGED")
    sources={p["repository"]:p for p in json.loads(ledger)["peers"]}
    results=[]
    for item in doc["receivers"]:
        raw=github_raw(item["repository"],item["merge_commit_sha1"],
                       "research/essence/peer_v13/inbox.json")
        check_inbox(item,raw)
        offer=json.loads(raw)["offer"]
        origin=sources[offer["source_repo"]]
        if (origin["merge_commit_sha"]!=offer["source_commit_sha1"]
                or origin["first_run"]["receipt_sha256"]!=offer["source_first_receipt_sha256"]
                or origin["replay_run"]["receipt_sha256"]!=offer["source_replay_receipt_sha256"]):
            raise ValueError("LIVE_GITHUB_ORIGIN_RECEIPT_MISMATCH")
        code=github_raw(item["repository"],item["merge_commit_sha1"],
                        ".janus/essence/peer_inbox_v13.py")
        if git_blob(code)!=CODE_BLOB:
            raise ValueError("GITHUB_VALIDATOR_CODE_MISMATCH")
        results.append({"repository":item["repository"],
                        "source_repository":item["source_repository"],
                        "inbox_git_blob_sha1":git_blob(raw),
                        "offer_sha256":offer["offer_sha256"],
                        "validator_blob_sha1":CODE_BLOB,
                        "code_executed_from_source":False,
                        "production_authority":False})
    witness={
        "schema":"janus.essence.github_peer_live_readonly_verifier/1.3",
        "status":"SIX_VERSIONED_GITHUB_PEER_INBOXES_VERIFIED",
        "verified":results,
        "verification_kind":"PUBLIC_GITHUB_COMMIT_SOURCE_BLOB_AND_JSON_REPLAY",
        "remote_code_imported":False,
        "production_authority":False,
        "independent_model_gain_proven":False,
    }
    witness["receipt_sha256"]=digest(witness)
    return witness

def selftest(doc):
    validate(doc)
    bad=copy.deepcopy(doc);bad["limits"]["github_only"]=False
    try:validate(bad)
    except ValueError:pass
    else:raise AssertionError("INVALID_AUTHORITY_MUTATION_ACCEPTED")
    bad=copy.deepcopy(doc);bad["receivers"][0]["source_repository"]=bad["receivers"][0]["repository"]
    try:validate(bad)
    except ValueError:pass
    else:raise AssertionError("SELF_ORIGIN_MUTATION_ACCEPTED")
    bad=copy.deepcopy(doc);bad["receivers"][1]["source_offer_sha256"]="0"*64
    try:check_inbox(bad["receivers"][1],b'{}')
    except ValueError:pass
    else:raise AssertionError("BAD_BLOB_MUTATION_ACCEPTED")
    return True

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out")
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--live",action="store_true")
    args=ap.parse_args()
    doc=load()
    if args.selftest:selftest(doc)
    witness=verify_live(doc) if args.live else {"schema":SCHEMA,
        "status":"STATIC_PROVENANCE_ONLY_NOT_LIVE_VERIFIED",
        "receiver_count":len(doc["receivers"]),"production_authority":False}
    if args.out:
        p=Path(args.out)
        if p.exists():raise FileExistsError("IMMUTABLE_RESEARCH_OUTPUT")
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(witness,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":witness["status"],
                      "receivers":len(witness.get("verified",[])),
                      "receipt_sha256":witness.get("receipt_sha256")},sort_keys=True))

if __name__=="__main__":
    main()
