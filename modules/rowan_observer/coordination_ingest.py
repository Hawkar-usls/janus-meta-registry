#!/usr/bin/env python3
"""Mirror independently attested Rowan/AURA/Demiurge proposals into Meta Registry.

No provider keys; no Rowan API; no job dispatch. Read-only exact public URLs.
Changes to upstream streams cause append-only record only after byte/source
matching. The immutable Meta Registry Rowan canon remains sole source of data.
"""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from urllib.request import Request,urlopen

BASE=Path("data/rowan/coordination")
STATE=Path("data/rowan/CANONICAL_STATE.json")
AURA_URL="https://raw.githubusercontent.com/Hawkar-usls/aura-oracle-tg/main/research/rowan/LATEST_HYPOTHESES.json"
COUNCIL_URL="https://raw.githubusercontent.com/Hawkar-usls/Janus-Demiurge/main/research/rowan/LATEST_COUNCIL.json"
AURA_HYPOS=("H_CONFIDENCE_SIGNAL","H_NULL_SIGNAL","H_ASSAY_CONFOUND","H_DOMAIN_SHIFT")
BEETLE_LANE="protein_stability_falsifiers"
class Hold(ValueError):pass

def canon(x):
    return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def sha(x):
    return hashlib.sha256(canon(x)).hexdigest()

def clean(meta,aura,council):
    if any(not isinstance(x,dict) for x in (meta,aura,council)):
        raise Hold("NONOBJECT_SOURCE")
    if meta.get("schema_id")!="janus.rowan.observer_state.v1":
        raise Hold("UNTRUSTED_META_CANON")
    if aura.get("schema_id")!="janus.aura.rowan_hypothesis_packet.v1":
        raise Hold("UNKNOWN_AURA_CONTRACT")
    if council.get("schema_id")!="janus.demiurge.rowan_council_proposal.v1":
        raise Hold("UNKNOWN_DEMIURGE_CONTRACT")
    a=aura.get("source",{});d=council.get("sources",{})
    run=meta.get("latest_durable_external_run")
    complete=meta.get("last_completed_mutants")
    if type(run)!=int or run<1 or type(complete)!=int or not 0<=complete<=8:
        raise Hold("INVALID_ROWAN_RUN")
    if a.get("upstream_run")!=run or a.get("completed_mutants")!=complete:
        raise Hold("AURA_NOT_CURRENT")
    state_sha=sha(meta)
    if a.get("state_sha256")!=state_sha or a.get("upstream_artifact_sha256")!=meta.get("underlying_state_is_derived_from"):
        raise Hold("AURA_META_BINDING_INVALID")
    p=dict(aura);digest=p.pop("packet_digest_sha256",None)
    if digest!=sha(p):raise Hold("AURA_PACKET_SHA_CHANGED")
    hypos=aura.get("hypotheses")
    if not isinstance(hypos,list) or tuple(x.get("id") for x in hypos)!=AURA_HYPOS:
        raise Hold("HYPOTHESES_CHANGED")
    if any(x.get("empirical_truth_probability") is not None or x.get("status")!="HYPOTHESIS_ONLY__NOT_MEASURED" for x in hypos):
        raise Hold("HYPOTHESIS_PROMOTION")
    raw=dict(council)
    if raw.pop("content_sha256",None)!=sha(raw):
        raise Hold("DEMIURGE_COUNCIL_SHA_CHANGED")
    if d.get("meta_registry",{}).get("sha256")!=state_sha or d.get("meta_registry",{}).get("canonical_run")!=run:
        raise Hold("DEMIURGE_META_SOURCE_CHANGED")
    if d.get("aura_oracle",{}).get("packet_sha256")!=sha(aura) or d.get("aura_oracle",{}).get("packet_digest")!=digest:
        raise Hold("DEMIURGE_AURA_SOURCE_CHANGED")
    if council.get("completed_pilot_cases")!=complete or council.get("next_beetle_direction_id")!=BEETLE_LANE:
        raise Hold("DEMIURGE_SCOPE_CHANGED")
    gates=council.get("gates",{})
    for key in ("rowan_credit_spend_new","rowan_job_submission_new",
                "aura_predictions_empirical_evidence","beetle_candidates_empirical_evidence",
                "production_model_weight_promotion"):
        if gates.get(key) is not False:
            raise Hold("UNAUTHORIZED_PROMOTION")
    if council.get("scientific_authority")!="NONE__PROPOSAL_NOT_EXPERIMENT":
        raise Hold("DEMIURGE_CLAIM_ESCALATION")
    r={
        "schema_id":"janus.meta_registry.rowan_council_provenance.v1",
        "source_kind":"INDEPENDENT_CROSS_REPO_READ_ONLY_REPLAY",
        "sources":{
            "meta_canonical_run":run,"meta_canonical_sha256":state_sha,
            "rowan_source_artifact_sha256":meta["underlying_state_is_derived_from"],
            "aura_packet_sha256":sha(aura),"aura_packet_digest":digest,
            "demiurge_council_sha256":sha(council),
            "aura_source_url":AURA_URL,"demiurge_source_url":COUNCIL_URL
        },
        "observation":{"completed_mutants":complete,"aura_hypothesis_ids":list(AURA_HYPOS),
            "demiurge_next_question":council.get("next_aura_question_id"),
            "beetle_discovery_direction":BEETLE_LANE,
            "demiurge_research_status":council.get("research_status")},
        "authority":{"new_rowan_jobs":False,"new_credit_spend":False,
            "hypotheses_are_empirical_proof":False,"new_study_authorized":False,
            "topa_external_independent_wetlab_gate":"OPEN"},
    }
    r["source_binding_sha256"]=sha(r)
    return r

def fetch(url):
    with urlopen(Request(url,headers={"User-Agent":"JANUS-META-CROSS-REPO-COUNCIL-VERIFY/1"}),timeout=25) as response:
        data=response.read(60001)
    if len(data)>60000:raise Hold("UNBOUNDED_RESEARCH_SOURCE")
    return json.loads(data.decode("utf-8"))

def ingest(root="."):
    root=Path(root)
    canon_path=root/STATE
    meta=json.loads(canon_path.read_text())
    aura=fetch(AURA_URL)
    demiurge=fetch(COUNCIL_URL)
    receipt=clean(meta,aura,demiurge)
    rid=receipt["sources"]["meta_canonical_run"]
    fingerprint=receipt["source_binding_sha256"]
    out=root/BASE/"receipts"/f"ROWAN-COUNCIL-{rid}-{fingerprint[:16]}.json"
    content=json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2).encode()+b"\n"
    if out.exists() and out.read_bytes()!=content:
        raise Hold("IMMUTABLE_COORDINATION_RECORD_CONFLICT")
    out.parent.mkdir(parents=True,exist_ok=True)
    if not out.exists():out.write_bytes(content)
    latest=root/BASE/"LATEST_COORDINATION_STATE.json"
    current={"schema_id":"janus.meta_registry.rowan_council_state.v1",
             "meta_canonical_run":rid,
             "source_binding_sha256":fingerprint,
             "receipt_path":str(out.relative_to(root)),
             "next_question":receipt["observation"]["demiurge_next_question"],
             "scientific_status":"HYPOTHESES_ONLY_NOT_BIOLOGICAL_DISCOVERY"}
    snapshot=json.dumps(current,ensure_ascii=False,sort_keys=True,indent=2).encode()+b"\n"
    if not latest.exists() or latest.read_bytes()!=snapshot:latest.write_bytes(snapshot)
    print("ROWAN_COUNCIL_ARCHIVE=SOURCE_VERIFIED_APPEND_ONLY")
    print("ROWAN_COUNCIL_ARCHIVE_RUN="+str(rid))
    return out

if __name__=="__main__":
    try:ingest()
    except (Hold,ValueError,OSError,TypeError) as exc:
        print("ROWAN_COUNCIL_ARCHIVE=SOURCE_PENDING_OR_AUTHORITY_HOLD")
        print("ROWAN_COUNCIL_ARCHIVE_REASON="+type(exc).__name__)
        # This optional mirror must not block the authoritative Rowan
        # provider evidence import. Preserve previous verified snapshot.
        raise SystemExit(0)
