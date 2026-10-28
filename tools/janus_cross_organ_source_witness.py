#!/usr/bin/env python3
"""Bounded JANUS cross-organ source witness; observation only, never dispatch."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
SOURCES={
 "rowan":("janus-meta-registry","data/rowan/CANONICAL_STATE.json","SCIENCE"),
 "topa":("janus-meta-registry","data/rowan/topa/TOPA-SHADOW-86ca72205cc89a03.json","SCIENCE"),
 "cosmos":("Janus-Cosmos","data/integrations/rowan/LATEST.json","SCIENCE"),
 "tranception":("Janus","integrations/tranception_rowan/discovery_manifest.json","SCIENCE"),
 "scoby":("SCOBY-D0","PROJECT_STATUS.json","SCIENCE"),
 "scoby_lineage":("SCOBY-D0","JANUS_SCOBY_UNIVERSAL_RESEARCH_INTEGRATION_1707_v1.0.json","SCIENCE"),
 "fundamentum":("Janus-Fundamentum","experiment_manifest.json","SCIENCE"),
 "terminal":("-Terminal-for-Janus","PROJECT_STATUS.json","CONTROL"),
 "helios":("Janus-HELIOS","PROJECT_STATUS.json","CONTROL"),
 "market":("JANUS-MACHINE-MARKET","ORGAN_SERVICE_MATRIX.json","CONTROL"),
 "voice":("The-Voice-of-Janus","README.md","NOTIFY"),
 "echo":("Echo-Pyramid","README.md","NOTIFY"),
 "link_scoby":("SCOBY-D0",".janus/JANUS_CROSS_ORGAN_SOURCE_LINK.json","SCIENCE"),
 "link_fundamentum":("Janus-Fundamentum",".janus/JANUS_CROSS_ORGAN_SOURCE_LINK.json","SCIENCE"),
 "link_terminal":("-Terminal-for-Janus",".janus/JANUS_CROSS_ORGAN_SOURCE_LINK.json","CONTROL"),
 "link_helios":("Janus-HELIOS",".janus/JANUS_CROSS_ORGAN_SOURCE_LINK.json","CONTROL"),
 "link_market":("JANUS-MACHINE-MARKET",".janus/JANUS_CROSS_ORGAN_SOURCE_LINK.json","CONTROL"),
 "link_voice":("The-Voice-of-Janus",".janus/JANUS_CROSS_ORGAN_SOURCE_LINK.json","NOTIFY"),
 "link_echo":("Echo-Pyramid",".janus/JANUS_CROSS_ORGAN_SOURCE_LINK.json","NOTIFY"),
}
MAX=180_000
class Hold(ValueError):pass

def require(x,why):
 if not x:raise Hold(why)

def fetch(name,repo,path):
 url="https://raw.githubusercontent.com/Hawkar-usls/"+repo+"/main/"+path
 with urlopen(Request(url,headers={"User-Agent":"JANUS-Cross-Organ-Source-Witness/1"}),timeout=25) as response:
  result=response.read(MAX+1)
 require(0<len(result)<=MAX,"SOURCE_UNAVAILABLE_OR_OVERSIZE_"+name)
 return result

def sha(b):return hashlib.sha256(b).hexdigest()

def audit(raw,manifest):
 require(set(raw)==set(SOURCES),"MISSING_OR_EXTRA_SOURCE")
 require(manifest.get("schema")=="janus.agent.observatory.contour-manifest.v2","INVALID_INVENTORY")
 inv={x["repo"].split("/",1)[1]:x for x in manifest["repository_inventory"]}
 for key,(repo,path,lane) in SOURCES.items():
  require(repo in inv and inv[repo]["role"]!="EXTERNAL","SOURCE_NOT_ENROLLED_"+repo)
 parsed={}
 for key,b in raw.items():
  if key in ("voice","echo"):
   require(b"#" in b and len(b)>100,"MISSING_README_"+key)
   parsed[key]={"readme":True}
  else:
   try:parsed[key]=json.loads(b)
   except (UnicodeDecodeError,ValueError) as e:raise Hold("JSON_INVALID_"+key) from e
   require(isinstance(parsed[key],dict),"JSON_NOT_OBJECT_"+key)
 r=parsed
 require(r["rowan"].get("schema_id")=="janus.rowan.observer_state.v1" and
         r["rowan"].get("new_unreviewed_studies")=="PROPOSAL_ONLY_NOT_AUTO_EXECUTED","ROWAN_AUTHORITY_HOLD")
 run=r["rowan"].get("latest_durable_external_run")
 require(type(run) is int and run>0 and r["rowan"].get("last_completed_mutants")==8,"ROWAN_RUN_HOLD")
 require(r["topa"].get("audit")=="PASS_INDEPENDENT_WITHIN_ASSAY_REPLAY" and
         r["topa"].get("promotion_gate")=="SHADOW_ONLY","TOPA_PROMOTION_HOLD")
 require(r["cosmos"].get("status")=="PASS_READ_ONLY_SOURCE_BOUND_REPLAY" and
         r["cosmos"].get("canonical_rowan_run")==run and
         r["cosmos"].get("cosmos_domain_transfer")=="PROTOCOL_AND_PROVENANCE_ONLY","COSMOS_SOURCE_DRIFT")
 require(r["tranception"].get("schema_id")=="janus.tranception.rowan.discovery_manifest.v1","TRANCEPTION_SOURCE_HOLD")
 require(r["scoby"].get("maturity")=="EARLY_R_AND_D" and
         r["scoby_lineage"].get("status")=="INTEGRATED_NAVIGATION_AND_OUTREACH_DRAFTS","SCOBY_SCIENCE_AUTHORITY_HOLD")
 require("P=NP" in r["fundamentum"].get("claim_boundary","") and
         r["fundamentum"].get("status")=="active_experimental_research","FUNDAMENTUM_THEOREM_AUTHORITY_HOLD")
 require(r["terminal"].get("authority",{}).get("default")=="READ_ONLY" and
         r["terminal"].get("authority",{}).get("unbounded_autonomy") is False,"TERMINAL_AUTHORITY_HOLD")
 require(r["helios"].get("compute_boundaries",{}).get("compute_off_by_default") is True and
         r["helios"].get("production_readiness")=="NOT_ESTABLISHED","HELIOS_COMPUTE_AUTHORITY_HOLD")
 require("ORGAN_CAPABILITY != LIVE_MARKET_EXECUTION" in r["market"].get("routing_laws",[]) and
         r["market"].get("services",{}).get("JANUS.FUNDAMENTUM_AUDIT",{}).get("public_live") is False,
         "MARKET_AUTONOMOUS_DISPATCH_HOLD")
 for key,(source_repo,source_path,lane) in SOURCES.items():
  if not key.startswith("link_"):continue
  link=r[key]
  require(link.get("schema")=="janus.organ.cross_organ_source_link.v1" and
          link.get("organ")=="Hawkar-usls/"+source_repo and
          link.get("lane")==lane and
          link.get("link_type")=="RECIPROCAL_READ_ONLY_SOURCE_POINTER" and
          link.get("delivery_witness")=="NOT_ATTESTED_SOURCE_LINK_ONLY",
          "RECIPROCAL_LINK_IDENTITY_HOLD_"+key)
  contracts=link.get("source_contracts")
  require(isinstance(contracts,list) and contracts and contracts[0].get("repo")=="Hawkar-usls/janus-meta-registry" and
          contracts[0].get("path")=="data/integrations/contour/LATEST.json",
          "RECIPROCAL_LINK_UPSTREAM_HOLD_"+key)
  auth=link.get("authority",{})
  require(auth.get("observe_public_provenance") is True and
          all(value is False for prop,value in auth.items() if prop!="observe_public_provenance") and
          {"submit_rowan_job","spend_rowan_credits","trigger_external_workflows",
           "authorize_market_payment","issue_operator_command","promote_scientific_claim",
           "publish_private_data"}<=set(auth),
          "RECIPROCAL_LINK_AUTHORITY_HOLD_"+key)
  if lane=="SCIENCE":
   require(len(contracts)==5,"SCIENCE_LINK_INCOMPLETE_"+key)
  else:require(len(contracts)==1,"CONTROL_OR_NOTIFY_LINK_EXPANDED_"+key)
 hashes={name:sha(raw[name]) for name in sorted(raw)}
 key=sha(json.dumps(hashes,sort_keys=True,separators=(",",":")).encode())
 return {"schema":"janus.cross_organ.source_witness.v1",
         "status":"PASS_PUBLIC_SOURCE_LINKS_ONLY",
         "key":key,"rowan_run":run,
         "source_sha256":hashes,"source_repositories":{name:"Hawkar-usls/"+repo for name,(repo,_,_) in SOURCES.items()},
         "lanes":{"SCIENCE":"SOURCES_BOUND_NO_CROSS_DOMAIN_CLAIM",
                  "CONTROL":"STATUS_READABLE_NO_DISPATCH",
                  "NOTIFY":"VOICE_ECHO_DOCUMENTATION_READABLE_NO_DELIVERY_ATTESTATION"},
         "scientific_calibration":"OPEN",
         "runtime_execution_attested":False,"notification_delivery_attested":False,
         "paid_rowan_jobs_submitted":0,"rowan_credits_spent":0,
         "authority":"READ_ONLY_NO_DISPATCH_NO_MODEL_PROMOTION"}

def encode(data):return (json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode()

def persist(root,record):
 base=root/"data/integrations/contour"
 path=base/"receipts"/("CONTOUR-ORGAN-"+record["key"][:20]+".json")
 blob=encode(record)
 if path.exists():require(path.read_bytes()==blob,"IMMUTABLE_RECEIPT_CONFLICT")
 else:
  path.parent.mkdir(parents=True,exist_ok=True)
  path.write_bytes(blob)
 pointer={"schema":"janus.contour.cross_organ_latest.v1",
          "status":record["status"],"key":record["key"],
          "receipt_path":str(path.relative_to(root)).replace("\\","/"),
          "rowan_run":record["rowan_run"],"runtime_execution_attested":False}
 latest=base/"LATEST.json"
 new=encode(pointer)
 if not latest.exists() or latest.read_bytes()!=new:
  latest.parent.mkdir(parents=True,exist_ok=True);latest.write_bytes(new)
 return path

def offline_test():
 manifest=json.loads((ROOT/"agent-observatory/JANUS_CONTOUR_MANIFEST.json").read_text())
 raw={}
 for k in SOURCES:
  if k in ("voice","echo"):raw[k]=b"# Valid readme\n"+b"documentation "*18
  else:raw[k]=b"{}"
 # Verify fail-closed on absent source and malformed state; no false positives.
 try:audit(raw,manifest)
 except Hold:pass
 else:raise AssertionError("AUDITOR_ACCEPTED_EMPTY_EVIDENCE")
 try:audit({"rowan":b"{}"},manifest)
 except Hold:pass
 else:raise AssertionError("AUDITOR_ACCEPTED_MISSING_SOURCES")
 print("CROSS_ORGAN_NEGATIVE_TESTS=PASS")

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--test",action="store_true")
 p.add_argument("--out",type=Path)
 p.add_argument("--persist-root",type=Path)
 args=p.parse_args()
 try:
  if args.test:offline_test()
  manifest=json.loads((ROOT/"agent-observatory/JANUS_CONTOUR_MANIFEST.json").read_text())
  raw={k:fetch(k,*v[:2]) for k,v in SOURCES.items()}
  record=audit(raw,manifest)
  if args.out:
   args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_bytes(encode(record))
  if args.persist_root:print("CROSS_ORGAN_RECEIPT="+str(persist(args.persist_root,record)))
  print("CROSS_ORGAN_WITNESS="+record["status"])
  print("CROSS_ORGAN_SOURCE_KEY="+record["key"])
 except (Hold,OSError,ValueError) as exc:
  print("CROSS_ORGAN_WITNESS=HOLD_"+str(exc),file=sys.stderr);raise SystemExit(2)
if __name__=="__main__":main()
