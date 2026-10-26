#!/usr/bin/env python3
"""Source-bound descriptive Rowan/local 1EY0 T8A delta comparison, no labels.

Requires THREE authentic independent source receipts:
  1. Local real GPU WT+T8A, SHA-pinned source files.
  2. JANUS Rowan cloud submit receipt (exact one new workflow; weekly pool).
  3. JANUS Rowan read-only outcome (same UUID, no new spend, confirmed scores).
Uses already-pinned Rowan WT and local WT from previous primary receipts.
No other experiments, private account details or stability claims.
"""
import argparse,hashlib,json,math
from pathlib import Path

LOCAL_RECEIPT_SHA="34b9f2ebfc81a5e1b72a36d1434f722a26f4f4ac608e2e3a170a736ece87419d"
WT_SHA="94a6f4324114f9e643076e2bfcb727145d400345f4c5feff0607e5c1fb787be1"
MUT_SHA="1c9ea97ff41ea9f659d1712e422c2ea1f4aa3373463b1e17d3d682c156cddacb"
NAME="JANUS-ROWAN-1EY0-RCSB-136AA-T8A-20261026-R0"
UUID="835d7f87-8508-4513-8a02-b62fad098cfb"
WT_ROWAN={"ptm":.943,"avg_lddt":.948}
FROZEN_ROWAN_WT_REF="data/rowan/provenance/ROWAN-1EY0-WT-ACTUAL-WEEKLY-API-SUCCESS-2026-10-26-v1.json"
FROZEN_REG="data/rowan/protocols/ROWAN-1EY0-T8A-SINGLE-MUTANT-STRUCTURAL-DELTA-PREREG-2026-10-26-v1.json"
CAP=10
class Hold(ValueError):pass
def h(b):return hashlib.sha256(b).hexdigest()
def safe_read(p,max_bytes=120000):
 if not p.is_file() or p.stat().st_size>max_bytes:raise Hold("MISSING_OR_OVERSIZE_INPUT_"+p.name)
 b=p.read_bytes()
 try:z=json.loads(b)
 except ValueError:raise Hold("NON_JSON_SOURCE_"+p.name)
 return b,z
def number(v,label):
 if type(v) not in (int,float) or not math.isfinite(v):raise Hold("NONFINITE_"+label)
 return float(v)
def compare(local,sub,provider):
 if local.get("technical_status")!="PASS_TWO_REAL_LOCAL_BOLTZ2_1EY0_WT_T8A_MSA_RUNS":
  raise Hold("LOCAL_SOURCE_AUDIT_NOT_PASS")
 if local.get("wt_sequence_sha256")!=WT_SHA or local.get("mutant_T8A_sequence_sha256")!=MUT_SHA:
  raise Hold("LOCAL_SOURCE_SEQUENCE_SHA_DRIFT")
 if local.get("source_prereg")!=FROZEN_REG:
  raise Hold("LOCAL_SOURCE_PREREG_DRIFT")
 if sub.get("status")!="ONE_PREREGISTERED_T8A_PROVIDER_JOB_SUBMITTED":
  raise Hold("ACTUAL_ONE_JOB_SUBMISSION_MISSING")
 if sub.get("new_jobs")!=1 or sub.get("credit_source")!="ORG_WEEKLY_MIN_30_VERIFIED":
  raise Hold("INVALID_OR_UNKNOWN_WEEKLY_CREDIT_SOURCE")
 if provider.get("provider_result_state")!="PROVIDER_RESULT_RETURNED":
  raise Hold("PROVIDER_RESULT_NOT_COMPLETE")
 if provider.get("actual_provider_status")!="Status.COMPLETED_OK":
  raise Hold("PROVIDER_NOT_COMPLETED_OK")
 if provider.get("status")!="EXISTING_SINGLE_MUTANT_NO_SPEND" or provider.get("new_jobs")!=0:
  raise Hold("DUPLICATE_WORKFLOW_OR_PROVIDER_SUBMIT")
 for tag,r in (("submit",sub),("provider",provider)):
  if r.get("case_name")!=NAME or r.get("workflow_uuid")!=UUID:
   raise Hold("MUTATION_CASE_OR_PROVIDER_UUID_DRIFT_"+tag)
  if r.get("source_mutant_sha256")!=MUT_SHA or r.get("wt_sha256")!=WT_SHA:
   raise Hold("PROVIDER_MUTANT_SEQUENCE_DRIFT_"+tag)
  if r.get("model")!="BOLTZ_2" or r.get("use_msa_server") is not True or r.get("num_samples")!=1:
   raise Hold("PROVIDER_MSA_OR_MODEL_DRIFT_"+tag)
  if r.get("original_zip_PDB_bytes_attested") is not False:
   raise Hold("FALSIFIED_ARCHIVED_PDB_IDENTITY_"+tag)
  if r.get("mutation_level_ddg_claim") is not False or r.get("shadow_model_weights_modified") is not False:
   raise Hold("FALSE_SCIENTIFIC_CLAIM_"+tag)
  if r.get("FireProt_210_inference_authorized") is not False:
   raise Hold("MASS_SCAN_AUTHORIZATION_DRIFT_"+tag)
 if sub.get("max_credits_per_new_job")!=CAP:
  raise Hold("SUBMISSION_MAX_CREDIT_CAP_DRIFT")
 charge=number(provider.get("credits_charged"),"provider_credits_charged")
 if not 0<=charge<=CAP:raise Hold("PROVIDER_CREDIT_CAP_EXCEEDED")
 a=local.get("wt");b=local.get("T8A")
 if type(a) is not dict or type(b) is not dict:raise Hold("LOCAL_PAIR_MISSING")
 vals={}
 for name,case in (("wt",a),("T8A",b)):
  ptm=number(case.get("ptm"),"local_"+name+"_ptm")
  ld=number(case.get("mean_plddt"),"local_"+name+"_plddt")
  if not 0<=ptm<=1 or not 0<=ld<=1 or case.get("count")!=136:
   raise Hold("LOCAL_136AA_CONFIDENCE_INVALID_"+name)
  vals[name]={"ptm":ptm,"plddt":ld}
 if abs(vals["wt"]["ptm"]-0.9377234578132629)>1e-9 or abs(vals["wt"]["plddt"]-0.9478468894958496)>1e-9:
  raise Hold("PRIOR_PUBLISHED_WT_LOCAL_DRIFT")
 if abs(vals["T8A"]["ptm"]-0.9397260546684265)>1e-9 or abs(vals["T8A"]["plddt"]-0.9504383206367493)>1e-9:
  raise Hold("PRIOR_PUBLISHED_MUTANT_LOCAL_DRIFT")
 p_ptm=number(provider.get("ptm"),"rowan_ptm")
 p_ld=number(provider.get("avg_lddt"),"rowan_avg_lddt")
 if not 0<=p_ptm<=1 or not 0<=p_ld<=1:raise Hold("ROWAN_SCORE_RANGE")
 local_delta_ptm=vals["T8A"]["ptm"]-vals["wt"]["ptm"]
 local_delta_ld=vals["T8A"]["plddt"]-vals["wt"]["plddt"]
 rowan_delta_ptm=p_ptm-WT_ROWAN["ptm"]
 rowan_delta_ld=p_ld-WT_ROWAN["avg_lddt"]
 return {
  "schema_id":"janus.meta_registry.rowan_1ey0_T8A.real_pair_structural_delta.v1",
  "date_utc":"2026-10-26",
  "status":"PASS_REAL_ONE_MUTANT_WT_VS_T8A_PROVIDER_AND_LOCAL_DELTA_COMPARISON",
  "scientific_status":"DESCRIPTIVE_STRUCTURAL_CONFIDENCE_ONLY_NO_FITNESS_GENERALIZATION",
  "scientific_scope":"Exactly 1/20 frozen 1EY0 mutations, compare local and Rowan model change from each provider's own WT",
  "frozen_prereg":FROZEN_REG,
  "mutant_sha256":MUT_SHA,
  "original_FireProt_PDB_archive_member_bytes_verified":False,
  "source": {
   "local_receipt":"data/rowan/provenance/ROWAN-1EY0-T8A-REAL-LOCAL-BOLTZ2-MSA-DELTA-2026-10-26-v1.json",
   "rowan_WT_receipt":FROZEN_ROWAN_WT_REF,
   "rowan_mutant_submit_workflow":"https://github.com/Hawkar-usls/Janus/actions/runs/40297250718",
   "rowan_mutant_collect_workflow":"https://github.com/Hawkar-usls/Janus/actions/runs/40297710868",
   "provider_job_url":"https://labs.rowansci.com/protein-cofolding/"+UUID,
   "rowan_submission_workflow_uuid":UUID,
   "rowan_mutant_submission_receipt_sha256":None,
   "rowan_mutant_collection_receipt_sha256":None,
   "local_verified_receipt_sha256":LOCAL_RECEIPT_SHA
  },
  "rowan":{"WT_ptm":WT_ROWAN["ptm"],"WT_avg_lddt":WT_ROWAN["avg_lddt"],
           "T8A_ptm":p_ptm,"T8A_avg_lddt":p_ld,
           "delta_ptm":rowan_delta_ptm,"delta_avg_lddt":rowan_delta_ld,
           "actual_credits_charged":charge,"authorized_credit_cap":CAP,
           "provider_result":"Status.COMPLETED_OK","extra_jobs_created_on_collection":0},
  "local": {"WT_ptm":vals["wt"]["ptm"],"T8A_ptm":vals["T8A"]["ptm"],
            "WT_pLDDT":vals["wt"]["plddt"],"T8A_pLDDT":vals["T8A"]["plddt"],
            "delta_ptm":local_delta_ptm,"delta_pLDDT":local_delta_ld},
  "cross_provider":{
   "rowan_minus_local_delta_ptm":rowan_delta_ptm-local_delta_ptm,
   "rowan_minus_local_delta_plddt":rowan_delta_ld-local_delta_ld,
   "absolute_delta_ptm_discrepancy":abs(rowan_delta_ptm-local_delta_ptm),
   "absolute_delta_plddt_discrepancy":abs(rowan_delta_ld-local_delta_ld),
   "ptm_mutation_delta_sign_disagrees":(rowan_delta_ptm*local_delta_ptm<0),
   "provider_confidence_precision":"Rowan values reported at 3 decimal places; a difference of two rounded values carries up to about 0.001 uncertainty.",
   "Rowan_MSA":"private Rowan hosted, exact alignment unavailable",
   "local_MSA":"public ColabFold, exact file SHA-256 pinned in local receipt",
   "protein_fitness_or_DDG_inference":False,
   "provider_equivalence_proven":False
  },
  "firewalls":{"experimental_DDG_labels_accessed":False,
     "genuine_blind_validation":False,"independent_unpublished_custodian":False,
     "FireProt_210_scale_up_authorized":False,
     "additional_protein_mutations_authorized":False,
     "shadow_weights_retrained":False,
     "production_model_promoted":False}
 }
def main():
 p=argparse.ArgumentParser()
 for name in ("local","submit","collect","out"):
  p.add_argument("--"+name,type=Path,required=True)
 a=p.parse_args()
 try:
  if a.out.exists():raise Hold("IMMUTABLE_REPORT_ALREADY_EXISTS")
  lb,l=safe_read(a.local)
  if h(lb)!=LOCAL_RECEIPT_SHA:raise Hold("LOCAL_VERIFIED_RECEIPT_SHA_DRIFT")
  sb,s=safe_read(a.submit);cb,c=safe_read(a.collect)
  report=compare(l,s,c)
  report["source"]["rowan_mutant_submission_receipt_sha256"]=h(sb)
  report["source"]["rowan_mutant_collection_receipt_sha256"]=h(cb)
  a.out.write_text(json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
  print("JANUS_ROWAN_T8A_PAIR="+report["status"])
  print("DELTA_PTM_DIFFERENCE="+str(report["cross_provider"]["rowan_minus_local_delta_ptm"]))
  print("DELTA_PLDDT_DIFFERENCE="+str(report["cross_provider"]["rowan_minus_local_delta_plddt"]))
  return 0
 except (OSError,ValueError,Hold) as exc:
  print("JANUS_ROWAN_T8A_PAIR=HOLD_"+str(exc))
  return 2
if __name__=="__main__":raise SystemExit(main())
