#!/usr/bin/env python3
"""Produce data-only ESSENCE peer offers from GitHub-versioned research receipts.

This is not a network client, solver trainer, remote command sender or proof
of improved neural weights. The only authority is to write a local artifact.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/"data"/"essence"/"v13"/"JANUS_ESSENCE_GITHUB_PEER_LINEAGE_2026-11-14.json"
SCHEMA="janus.essence.github_peer_lineage/1.3"
OUTPUT="janus.essence.github_peer_offers/1.3"
ENGINE="1c48b223c8ef64a78506a39b147f881b00022e77"
SPECIALTIES=(
 ("Hawkar-usls/Janus_Genesis","GENESIS_VERIFICATION","Guard candidate code with original counterexample tests"),
 ("Hawkar-usls/Janus-Demiurge","DEMIURGE_MODULE_AUDIT","Audit bounded module registry and critique unsafe generated imports"),
 ("Hawkar-usls/Demi_Head","DEMI_HEAD_GOVERNANCE","Cross-check source and no-authority promotion rules"),
 ("Hawkar-usls/janus-distributed-ai-swarm","SWARM_GRAPH_ROUTING","Propose a bounded weighted graph route candidate"),
 ("Hawkar-usls/Janus-Cosmos","COSMOS_GRAPH_SAFETY","Check graph invariants and bad-path counterexamples"),
 ("Hawkar-usls/Hrain","HRAIN_GRAPH_DEDUPE","Preserve graph-memory lineage while eliminating duplicate edges"),
)
KNOWN={x[0]:x for x in SPECIALTIES}

def encode(x):
    return json.dumps(x,sort_keys=True,ensure_ascii=False,
                      separators=(",",":"),allow_nan=False).encode()

def seal(x):
    return hashlib.sha256(encode(x)).hexdigest()

def is_hash(s,n):
    return isinstance(s,str) and len(s)==n and all(c in "0123456789abcdef" for c in s)

def load_json(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file() or not 2<=p.stat().st_size<=200000:
        raise ValueError("UNTRUSTED_PEER_FILE")
    return json.loads(p.read_text(encoding="utf-8"),
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))

def validate(ledger):
    if (not isinstance(ledger,dict) or ledger.get("schema")!=SCHEMA
            or ledger.get("mode")!="GITHUB_ONLY_VERSIONED_PEER_RESEARCH"
            or ledger.get("engine_git_blob_sha1")!=ENGINE
            or ledger.get("baseline_candidate")!="heap_route_v1"
            or ledger.get("benchmarks_not_independently_blinded") is not True):
        raise ValueError("INVALID_PEER_LEDGER")
    policy=ledger.get("policy")
    if (not isinstance(policy,dict)
            or policy.get("exchanges_are_data_only") is not True
            or policy.get("automatic_code_import") is not False
            or policy.get("automatic_review_bypass") is not False
            or policy.get("automatic_merge") is not False
            or policy.get("training_weights_updated") is not False
            or policy.get("independent_new_gain_proven") is not False
            or policy.get("staged_proposal_only") is not True):
        raise ValueError("PEER_LEDGER_PRIVILEGE_ESCALATION")
    peers=ledger.get("peers")
    if not isinstance(peers,list) or len(peers)!=len(SPECIALTIES):
        raise ValueError("WRONG_PEER_COUNT")
    identified=set()
    for item in peers:
        if not isinstance(item,dict):
            raise ValueError("INVALID_PEER")
        repo=item.get("repository")
        if (repo not in KNOWN or repo in identified
                or item.get("specialty")!=KNOWN[repo][1]
                or item.get("canonical_module_source")!="SOURCE_PINNED_SAME_MODULE_ENGINE"
                or item.get("production_authority") is not False
                or item.get("automatic_model_promotion") is not False
                or not is_hash(item.get("merge_commit_sha"),40)):
            raise ValueError("FORGED_PEER_IDENTITY")
        identified.add(repo)
        prior=item.get("first_run")
        replay=item.get("replay_run")
        if (not isinstance(prior,dict) or not isinstance(replay,dict)
                or prior.get("decision")!="RESEARCH_CHILD_STAGED_NO_PRODUCTION"
                or replay.get("decision")!="HOLD_NO_NEW_INDEPENDENT_GAIN"
                or any(x.get("status")!="SUCCESS" or
                       type(x.get("research_generation")) is not int or
                       x["research_generation"]!=1 or
                       type(x.get("id")) is not int or x["id"]<=0 or
                       not is_hash(x.get("receipt_sha256"),64)
                       for x in (prior,replay))
                or replay["id"]<=prior["id"]
                or replay["receipt_sha256"]==prior["receipt_sha256"]):
            raise ValueError("MISSING_REAL_SUCCESSFUL_PEER_REPLAY")
    return True

def make_offers(ledger):
    validate(ledger)
    origins={x["repository"]:x for x in ledger["peers"]}
    order=[x[0] for x in SPECIALTIES]
    offers=[]
    for i,source_repo in enumerate(order):
        origin=origins[source_repo]
        target_repo=order[(i+1)%len(order)]
        spec=KNOWN[source_repo]
        offer={
            "schema":"janus.essence.peer_research_offer/1.3",
            "source_repo":source_repo,
            "target_repo":target_repo,
            "idea_id":"github_v13_"+spec[1].lower(),
            "proposal":spec[2],
            "source_commit_sha1":origin["merge_commit_sha"],
            "source_first_receipt_sha256":origin["first_run"]["receipt_sha256"],
            "source_replay_receipt_sha256":origin["replay_run"]["receipt_sha256"],
            "source_research_generation":1,
            "performance_evidence":"NO_NEW_INDEPENDENT_GAIN",
            "proposed_new_algorithm_verified":False,
            "foreign_code_imported":False,
            "external_message_delivered":False,
            "production_authority":False,
            "automatic_model_promotion":False,
            "review_required":True,
        }
        offer["offer_sha256"]=seal(offer)
        offers.append(offer)
    return offers

def produce(ledger,previous=None):
    offers=make_offers(ledger)
    fingerprint=seal(ledger)
    if previous is not None:
        if (not isinstance(previous,dict)
            or previous.get("schema")!=OUTPUT
            or previous.get("receipt_sha256")!=seal({k:v for k,v in previous.items() if k!="receipt_sha256"})
            or previous.get("production_authority") is not False
            or previous.get("automatic_merge") is not False
            or previous.get("source_lineage_sha256")!=fingerprint):
            raise ValueError("PEER_PREVIOUS_PROVENANCE_CHANGED")
        # A new event without new input evidence must not create another generation.
        state="HOLD_NO_NEW_PEER_EVIDENCE"
        offers=[]
    else:
        state="RESEARCH_OFFERS_PREPARED_NOT_DELIVERED"
    result={
        "schema":OUTPUT,
        "source_lineage_sha256":fingerprint,
        "mode":"GITHUB_ONLY_OFFLINE_RESEARCH_EXCHANGE",
        "status":state,
        "verified_source_peers":len(SPECIALTIES),
        "source_generation":1,
        "proposed_next_generation":False,
        "automatic_merge":False,
        "production_authority":False,
        "trained_model_weights_modified":False,
        "peer_offers":offers,
        "external_messages_actually_sent":False,
        "external_independently_attested":False,
    }
    result["receipt_sha256"]=seal(result)
    return result

def selftest(ledger):
    validate(ledger)
    first=produce(ledger)
    second=produce(ledger,first)
    assert len(first["peer_offers"])==len(SPECIALTIES)
    assert second["status"]=="HOLD_NO_NEW_PEER_EVIDENCE"
    assert not second["peer_offers"]
    assert all(x["source_repo"]!=x["target_repo"] for x in first["peer_offers"])
    assert len(set(x["idea_id"] for x in first["peer_offers"]))==len(SPECIALTIES)
    for mutation in ("authority","two_generations","second_receipt","duplicate_repo","unknown_origin"):
        bad=copy.deepcopy(ledger)
        if mutation=="authority":bad["policy"]["automatic_merge"]=True
        elif mutation=="two_generations":bad["peers"][0]["replay_run"]["research_generation"]=2
        elif mutation=="second_receipt":bad["peers"][0]["replay_run"]["receipt_sha256"]="x"*64
        elif mutation=="duplicate_repo":bad["peers"][1]["repository"]=bad["peers"][0]["repository"]
        else:bad["peers"][2]["repository"]="attacker/mystery"
        try:validate(bad)
        except ValueError:pass
        else:raise AssertionError("PEER_MUTATION_NOT_HELD_"+mutation)
    fake=copy.deepcopy(first)
    fake["production_authority"]=True
    try:produce(ledger,fake)
    except ValueError:pass
    else:raise AssertionError("FORGED_PREVIOUS_AUTHORITY_NOT_HELD")
    return True

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger",default=str(LEDGER))
    ap.add_argument("--out")
    ap.add_argument("--previous")
    ap.add_argument("--selftest",action="store_true")
    opts=ap.parse_args()
    ledger=load_json(opts.ledger)
    if opts.selftest:selftest(ledger)
    result=produce(ledger,load_json(opts.previous) if opts.previous else None)
    if opts.out:
        out=Path(opts.out)
        if out.exists():raise FileExistsError("DO_NOT_OVERWRITE_RESEARCH_ARTIFACT")
        out.parent.mkdir(parents=True,exist_ok=True)
        out.write_text(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"offers":len(result["peer_offers"]),
                      "peers":result["verified_source_peers"],
                      "receipt_sha256":result["receipt_sha256"]},sort_keys=True))

if __name__=="__main__":
    main()
