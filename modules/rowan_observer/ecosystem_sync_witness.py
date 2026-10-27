#!/usr/bin/env python3
"""Independent read-only Rowan ecosystem synchronization witness.

Reads only bounded PUBLIC GitHub raw files. Does not contact Rowan APIs,
submit jobs, spend credits, alter repos, or promote scientific results.
Distinguishes synchronized source pointers from independent wetlab validation.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

RAW = "https://raw.githubusercontent.com/"
META = "Hawkar-usls/janus-meta-registry/main/"
URLS = {
 "canonical": META+"data/rowan/CANONICAL_STATE.json",
 "pipeline": META+"data/rowan/health/PIPELINE_STATE.json",
 "pointer": META+"data/rowan/coordination/LATEST_COORDINATION_STATE.json",
 "aura": "Hawkar-usls/aura-oracle-tg/main/research/rowan/LATEST_HYPOTHESES.json",
 "council": "Hawkar-usls/Janus-Demiurge/main/research/rowan/LATEST_COUNCIL.json",
 "beetle": "Hawkar-usls/janus-lapis/main/data/beetle/directions.json",
 "shadow": META+"data/rowan/learned/SHADOW-BBC1-abac9057873ac3c4.json",
 "topa": META+"data/rowan/topa/TOPA-SHADOW-86ca72205cc89a03.json",
 "hrain": "Hawkar-usls/Hrain/main/assets/janus-rowan-readonly.mjs",
 "inaihr": "Hawkar-usls/iNaiHR/main/assets/janus-rowan-readonly.mjs",
 "genesis": "Hawkar-usls/Janus_Genesis/main/.janus/ROWAN_RESEARCH_SOURCE_LINK.json",
 "topa_repo": "Hawkar-usls/TOPA/main/.janus/ROWAN_INDEPENDENT_SOURCE_LINK.json",
 "tranception": "Hawkar-usls/Janus/main/integrations/tranception_rowan/discovery_manifest.json",
}
RECEIPT = re.compile(r"^data/rowan/coordination/receipts/ROWAN-COUNCIL-\d+-[0-9a-f]{16}\.json$")
MAX_FILE = 96_000

class Hold(ValueError): pass

def sha_obj(x):
 return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def fetch(path):
 if path not in URLS.values() and not (path.startswith(META) and RECEIPT.fullmatch(path[len(META):])):
  raise Hold("SOURCE_URL_NOT_ALLOWLISTED")
 with urlopen(Request(RAW+path,headers={"User-Agent":"JANUS-ROWAN-ECOSYSTEM-WITNESS/1"}),timeout=25) as response:
  body=response.read(MAX_FILE+1)
 if not body or len(body)>MAX_FILE:raise Hold("SOURCE_UNAVAILABLE_OR_OVERSIZED")
 return body

def load_public():
 raw={key:fetch(path) for key,path in URLS.items()}
 parsed={k:(v.decode("utf-8") if k in ("hrain","inaihr") else json.loads(v)) for k,v in raw.items()}
 pointer=parsed["pointer"]
 path=pointer.get("receipt_path") if isinstance(pointer,dict) else None
 if not isinstance(path,str) or not RECEIPT.fullmatch(path):
  raise Hold("UNTRUSTED_COORDINATION_RECEIPT_PATH")
 raw["receipt"]=fetch(META+path)
 parsed["receipt"]=json.loads(raw["receipt"])
 return parsed,raw

def require(test,reason):
 if not test:raise Hold(reason)

def verify(data,raw):
 m=data["canonical"];p=data["pipeline"];pointer=data["pointer"]
 a=data["aura"];d=data["council"];receipt=data["receipt"]
 require(m.get("schema_id")=="janus.rowan.observer_state.v1","ROWAN_SCHEMA_HOLD")
 run=m.get("latest_durable_external_run");count=m.get("last_completed_mutants")
 require(type(run) is int and run>0 and type(count) is int and count==8,"ROWAN_PILOT_NOT_ATTESTED")
 source=m.get("underlying_state_is_derived_from")
 require(isinstance(source,str) and re.fullmatch(r"[0-9a-f]{64}",source) is not None,"ROWAN_SOURCE_SHA_HOLD")
 require(p.get("latest_archived_source_run")==run and p.get("latest_completed_source_run")==run and p.get("completed_mutants")==count and p.get("archive_status")=="ARCHIVE_CURRENT","ROWAN_ARCHIVE_LAG_HOLD")
 require(p.get("credit_cap_violations")==[] and p.get("science_gates",{}).get("new_billing_authorized_by_watchdog") is False,"ROWAN_BUDGET_AUTHORITY_HOLD")
 require(p.get("science_gates",{}).get("model_production_promotion") is False and p.get("science_gates",{}).get("wetlab_independent_validation")=="OPEN","ROWAN_SCIENCE_AUTHORITY_HOLD")
 require(a.get("schema_id")=="janus.aura.rowan_hypothesis_packet.v1" and a.get("source",{}).get("upstream_run")==run and a["source"].get("completed_mutants")==count and a["source"].get("state_sha256")==sha_obj(m),"AURA_SOURCE_STALE")
 ae=dict(a);ad=ae.pop("packet_digest_sha256",None)
 require(ad==sha_obj(ae) and all(x.get("status")=="HYPOTHESIS_ONLY__NOT_MEASURED" and x.get("empirical_truth_probability") is None for x in a.get("hypotheses",[])) and len(a.get("hypotheses",[]))==4,"AURA_HYPOTHESIS_INTEGRITY_HOLD")
 require(a.get("bounded_authority",{}).get("may_submit_rowan_jobs") is False and a["bounded_authority"].get("may_modify_rowan_credit_budget") is False,"AURA_BUDGET_HOLD")
 de=dict(d);dd=de.pop("content_sha256",None)
 require(dd==sha_obj(de) and d.get("sources",{}).get("meta_registry",{}).get("canonical_run")==run and d["sources"]["meta_registry"].get("sha256")==sha_obj(m),"DEMIURGE_META_SOURCE_STALE")
 require(d["sources"].get("aura_oracle",{}).get("packet_sha256")==sha_obj(a) and d["sources"]["aura_oracle"].get("packet_digest")==ad,"DEMIURGE_AURA_SOURCE_STALE")
 require(d.get("scientific_authority")=="NONE__PROPOSAL_NOT_EXPERIMENT" and d.get("gates",{}).get("rowan_credit_spend_new") is False and d["gates"].get("production_model_weight_promotion") is False,"DEMIURGE_PROMOTION_HOLD")
 require(pointer.get("meta_canonical_run")==run and pointer.get("source_binding_sha256")==receipt.get("source_binding_sha256") and RECEIPT.fullmatch(pointer.get("receipt_path","")) is not None,"COORDINATION_POINTER_STALE")
 rr=dict(receipt);rs=rr.pop("source_binding_sha256",None)
 require(rs==sha_obj(rr) and receipt.get("sources",{}).get("meta_canonical_run")==run and receipt["sources"].get("meta_canonical_sha256")==sha_obj(m) and receipt["sources"].get("aura_packet_sha256")==sha_obj(a) and receipt["sources"].get("demiurge_council_sha256")==sha_obj(d),"COORDINATION_SOURCE_HASH_HOLD")
 require(receipt.get("observation",{}).get("completed_mutants")==count and receipt.get("authority",{}).get("new_credit_spend") is False and receipt["authority"].get("new_rowan_jobs") is False and receipt["authority"].get("hypotheses_are_empirical_proof") is False,"COUNCIL_AUTHORITY_HOLD")
 shadow=data["shadow"];topa=data["topa"]
 require(shadow.get("schema_id")=="janus.rowan.bbc1.sequence_shadow_ridge.v1" and shadow.get("authority",{}).get("deployment")=="SHADOW_ONLY","SHADOW_MODEL_UNSAFE")
 require(topa.get("schema_id")=="janus.topa.independent_shadow_replay.v1" and topa.get("audit")=="PASS_INDEPENDENT_WITHIN_ASSAY_REPLAY" and topa.get("promotion_gate")=="SHADOW_ONLY" and topa.get("model_file_sha256")==hashlib.sha256(raw["shadow"]).hexdigest(),"TOPA_NUMERICAL_REPLAY_HOLD")
 beetle=data["beetle"];directions=[v for v in beetle.get("directions",[]) if v.get("id")=="protein_stability_falsifiers" and v.get("enabled") is True]
 require(len(directions)==1 and set(directions[0].get("mirror_lenses",[]))=={"FORWARD","REVERSE","COUNTEREVIDENCE","CONTROL"},"BEETLE_FALSIFIER_LANE_HOLD")
 for name in ("hrain","inaihr"):
  code=data[name]
  require("ROWAN_CROSS_ORGAN_SOURCE_MISMATCH_HOLD" in code and "credentials: 'omit'" in code and "method: 'GET'" in code and "SYNCED_SOURCE_POINTERS_READ_ONLY" in code,"MINDMAP_READONLY_LINK_MISSING")
 genesis=data["genesis"];topa_repo=data["topa_repo"]
 require(genesis.get("schema")=="janus.genesis.rowan_evidence_source_link.v1" and all(v is False for v in genesis.get("authority",{}).values()),"GENESIS_SOURCE_AUTHORITY_HOLD")
 require(topa_repo.get("schema")=="janus.topa.rowan_independent_replay_source_link.v1" and all(v is False for v in topa_repo.get("authority",{}).values()),"TOPA_REPO_AUTHORITY_HOLD")
 require(data["tranception"].get("schema_id")=="janus.tranception.rowan.discovery_manifest.v1","TRANCEPTION_LINK_HOLD")
 return {"schema":"janus.rowan.ecosystem_sync_witness.v1",
         "status":"PASS_PUBLIC_SOURCE_BINDINGS_NOT_SCIENCE_VALIDATION",
         "canonicalRun":run,"completedMutants":count,"sourceArtifactSha256":source,
         "coordinationSha256":rs,"linkedConsumers":["Meta Registry","TOPA numerical replay","AURA","Demiurge","Universal Beetle","HRAiN","iNaiHR","Genesis","Tranception"],
         "newRowanJobs":False,"creditsSpentByWitness":0,
         "independentWetlab":"OPEN","modelProductionPromotion":False,
         "privateGraphInspected":False,"productionAutonomyAuthorized":False}

def main():
 data,raw=load_public()
 print(json.dumps(verify(data,raw),sort_keys=True,indent=2))

if __name__=="__main__":main()
