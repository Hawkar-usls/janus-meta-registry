#!/usr/bin/env python3
"""SCOBY/placental ECM JANUS Rowan pair of separate real protein-pilot receipts.

Four immutable source artifacts are required, one submit + read-only collect
per protein. No patient/donor/assay data. Scientific claims are capped at
single-chain Boltz2 confidence, not SCOBY or placenta material properties.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path

PREREG="data/rowan/protocols/ROWAN-SCOBY-KOMBUCHA-PLACENTAL-ECM-TWO-PROTEIN-PILOT-PREREG-2026-10-26-v1.json"
CASES={
 "scoby_acsD":{
  "name":"JANUS-SCOBY-ACSD-P37719-20261026-R0",
  "uniprot":"P37719","length":156,
  "source_sha":"a7fa1a2d359ae60b7f88b4fefadf6502c9b578e3edb543ae01bf4ecca044adf9",
  "uuid":"d6857380-d46b-4c27-bf79-faf761c9af36",
  "submit_run":40312396616,"collect_run":None,
  "structure_reference":"https://www.rcsb.org/structure/3A8E",
  "scientific_limit":"Monomer-only: native AcsD is crystallographically octameric; do not infer cellulose production or pore function."
 },
 "placenta_fn1":{
  "name":"JANUS-PLACENTA-ECM-FN1-TYPEII-355-463-20261026-R0",
  "uniprot":"P02751","length":109,
  "source_sha":"d8658e68f40439d7021df84a16c84fa7102a3cc939bd3a96b288b2944985ae0e",
  "uuid":"74a70ba9-8fa2-4011-b89a-70c761cc632f",
  "submit_run":40312510366,"collect_run":None,
  "structure_reference":"https://www.uniprot.org/uniprotkb/P02751/entry",
  "scientific_limit":"Generic human FN1 fragment only; neither placenta-specific tissue nor complex with SCOBY nor cellulose affinity is modeled."
 }
}
class Hold(ValueError):pass
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read_json(p):
 if not p.is_file() or p.stat().st_size>150000:raise Hold("MISSING_OR_OVERSIZE_SOURCE_"+p.name)
 return json.loads(p.read_text(encoding="utf8"))
def number(v,k):
 if type(v) not in (int,float) or not math.isfinite(v):raise Hold("NON_FINITE_"+k)
 return float(v)
def validate_one(case,submission,collection):
 if case not in CASES:raise Hold("UNKNOWN_OR_UNFROZEN_CASE")
 m=CASES[case]
 for kind,r in (("submission",submission),("collection",collection)):
  if r.get("case")!=case or r.get("case_name")!=m["name"] or r.get("provider_uuid")!=m["uuid"]:
   raise Hold("SOURCE_CASE_NAME_UUID_DRIFT_"+kind+"_"+case)
  if r.get("source_uniprot")!=m["uniprot"] or r.get("sequence_sha256")!=m["source_sha"] or r.get("sequence_length")!=m["length"]:
   raise Hold("SOURCE_SEQUENCE_IDENTITY_DRIFT_"+kind+"_"+case)
  if r.get("model")!="BOLTZ_2" or r.get("use_msa_server") is not True or r.get("num_samples")!=1:
   raise Hold("MODEL_OR_MSA_CONFIG_DRIFT_"+kind+"_"+case)
  if r.get("source_registry_protocol")!=PREREG or r.get("max_credits_per_new_job")!=10:
   raise Hold("PRECOMMIT_OR_CREDIT_CAP_DRIFT_"+kind+"_"+case)
  for flag in ("SCOBY_microbiome_predicted","placental_tissue_or_BC_composite_predicted","experimental_material_performance_proven"):
   if r.get(flag) is not False:raise Hold("FALSE_MATERIALS_CLAIM_"+flag)
 if submission.get("status")!="ONE_PREREGISTERED_SCOBY_RELATED_PROTEIN_SUBMITTED" or submission.get("new_jobs")!=1:
  raise Hold("NOT_EXACTLY_ONE_GENUINE_PROVIDER_SUBMISSION_"+case)
 if submission.get("weekly_authorization")!="ORG_WEEKLY_AVAILABLE_GE_30_AT_SUBMIT":
  raise Hold("NO_VERIFIED_WEEKLY_ONLY_CREDITS_"+case)
 if collection.get("status")!="CASE_ALREADY_EXISTS_NO_NEW_SUBMISSION" or collection.get("new_jobs")!=0 or collection.get("additional_jobs")!=0:
  raise Hold("DUPLICATE_OR_NOT_READONLY_COLLECTION_"+case)
 if collection.get("result_state")!="PROVIDER_SCORES_RETURNED":
  raise Hold("NOT_YET_REAL_RESULT_"+case)
 if str(collection.get("provider_status"))!="Status.COMPLETED_OK":
  raise Hold("PROVIDER_RESULT_NOT_COMPLETED_OK_"+case)
 ptm=number(collection.get("ptm"),"PTM")
 ld=number(collection.get("avg_lddt"),"AVG_LDDT")
 cost=number(collection.get("charged_credits"),"CHARGED_CREDITS")
 if not 0<=ptm<=1 or not 0<=ld<=1:raise Hold("SCORES_OUT_OF_RANGE_"+case)
 if not 0<=cost<=10:raise Hold("CREDIT_SPEND_CAP_EXCEEDED_"+case)
 return {
  "case":case,"uniprot":m["uniprot"],"source_aa_sha256":m["source_sha"],
  "sequence_length":m["length"],"rowan_uuid":m["uuid"],
  "rowan_job_url":"https://labs.rowansci.com/protein-cofolding/"+m["uuid"],
  "rowan_submission_run":"https://github.com/Hawkar-usls/Janus/actions/runs/"+str(m["submit_run"]),
  "ptm":ptm,"avg_lddt":ld,"credits_charged":cost,
  "provider_state":"Status.COMPLETED_OK","new_jobs_on_submission":1,"new_jobs_on_collection":0,
  "experimental_structure_reference":m["structure_reference"],
  "scientific_interpretation_limit":m["scientific_limit"]
 }
def audit(paths):
 records=[]
 total=0
 for case in ("scoby_acsD","placenta_fn1"):
  sp,cp=paths[case]
  sb=read_json(sp);cb=read_json(cp)
  row=validate_one(case,sb,cb)
  row["actual_provider_submission_receipt_sha256"]=sha(sp)
  row["actual_provider_collection_receipt_sha256"]=sha(cp)
  records.append(row);total+=row["credits_charged"]
 return {
  "schema_id":"janus.scoby.kombucha_placenta.real_rowan_2x1_pilot_score_receipt.v1",
  "date_utc":"2026-10-26",
  "status":"TWO_REAL_SEPARATE_ROWAN_BOLTZ2_PROTEIN_STRUCTURE_PILOTS_COMPLETED",
  "prereg":PREREG,
  "source_audit":"data/scoby/provenance/SCOBY-KOMBUCHA-PLACENTA-ROWAN-RESEARCH-AUDIT-2026-10-26-v1.json",
  "sources_verified":len(records),"provider_jobs_total":2,"provider_credits_total":total,
  "protein_predictions":records,
  "scientific_boundaries":{
   "not_a_Kombucha_multispecies_SCOBY_simulation":True,
   "not_a_placental_tissue_simulation":True,
   "not_a_placenta_milk_SCOBY_composite_prediction":True,
   "not_a_bacterial_cellulose_output_yield_prediction":True,
   "not_a_heteromeric_acsD_fn1_binding_prediction":True,
   "no_human_sample_involved":True,
   "no_DDG_experimental_label_inference":True,
   "no_cellulose_material_strength_or_function_proven":True,
   "no_shadow_weights_updated":True,
   "no_production_promotion":True
  },
  "followup":"Protein structure confidence can be checked against known structural data for AcsD; native octamer requires a separate preregistered complex experiment. FN1 short sequence has no biological specificity to placental tissue. These results alone cannot test the SCOBY+placental ECM hypothesis."
 }
def main():
 p=argparse.ArgumentParser()
 for k in ("acsD_submit","acsD_collect","fn1_submit","fn1_collect","out"):p.add_argument("--"+k,type=Path,required=True)
 a=p.parse_args()
 try:
  if a.out.exists():raise Hold("IMMUTABLE_RECEIPT_EXISTS")
  obj=audit({"scoby_acsD":(a.acsD_submit,a.acsD_collect),"placenta_fn1":(a.fn1_submit,a.fn1_collect)})
  a.out.parent.mkdir(parents=True,exist_ok=True)
  a.out.write_text(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
  print("JANUS_SCOBY_ROWAN_TWO_REAL_PROTEINS="+obj["status"])
  return 0
 except (Hold,OSError,ValueError) as ex:
  print("JANUS_SCOBY_ROWAN_TWO_REAL_PROTEINS=HOLD_"+str(ex))
  return 2
if __name__=="__main__":raise SystemExit(main())
