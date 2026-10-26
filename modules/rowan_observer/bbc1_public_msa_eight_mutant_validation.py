#!/usr/bin/env python3
"""Audit all nine BBC1 public-MSA model outputs against frozen original Rowan.

Only descriptive structural confidence comparability. No experimental label
files or Rowan API calls; a locally close pTM does not authorize FireProt.
"""
from __future__ import annotations
import argparse,hashlib,json,math,statistics
from pathlib import Path
import numpy as np

PREDECLARED=[
 ("E27F",0.929,0.969),("W38L",0.929,0.967),
 ("K13N",0.928,0.967),("G64Q",0.929,0.968),
 ("Q44V",0.927,0.970),("E42H",0.930,0.972)]
MODEL="boltz2==2.2.1 / torch==2.12.1+cu126 / public ColabFold MSA"
class AuditHold(ValueError):pass
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def check(what,p,expected):
    p=Path(p)
    if not p.is_file() or sha(p)!=expected:raise AuditHold("SOURCE_SHA_MISMATCH_"+what)
def verify_six(six,inputs,outputs):
    if [x.get("mutation") for x in six.get("records",[])]!=[x[0] for x in PREDECLARED]:
        raise AuditHold("EXACT_SIX_FROZEN_ORDER_MISSING_OR_DRIFT")
    if six.get("partial_completed_count")!=6 or six.get("paid_rowan_jobs")!=0 or six.get("FireProt_210_jobs")!=0:
        raise AuditHold("INCOMPLETE_OR_CREDITS_DRIFT")
    values=[]
    for rec,(mut,origptm,origlddt) in zip(six["records"],PREDECLARED):
        if rec["rowan"]!={"ptm":origptm,"avg_lddt":origlddt}:
            raise AuditHold("ORIGINAL_ROWAN_REFERENCE_CHANGED_"+mut)
        name="BBC1_"+mut+"_MSA"
        base=Path(outputs)/("boltz_results_"+name)
        conf=base/"predictions"/name/("confidence_"+name+"_model_0.json")
        plddt=base/"predictions"/name/("plddt_"+name+"_model_0.npz")
        check(mut+"_YAML",Path(inputs)/(name+".yaml"),rec["source"]["input_sha256"])
        check(mut+"_CONFIDENCE",conf,rec["source"]["confidence_json_sha256"])
        check(mut+"_PLDDT",plddt,rec["source"]["plddt_npz_sha256"])
        raw=json.loads(conf.read_bytes())
        for field,provided in (("ptm",rec["local"]["ptm"]),("complex_plddt",rec["local"]["complex_plddt"])):
            if type(provided) not in (int,float) or not math.isfinite(provided) or not 0<=provided<=1:
                raise AuditHold("BAD_SCORE_RANGE")
            if provided!=raw[field]:raise AuditHold("RECORDED_SCORE_NOT_FILE_"+mut)
        with np.load(plddt,allow_pickle=False) as z:
            arr=z["plddt"]
            if arr.shape!=(64,) or not np.isfinite(arr).all() or abs(float(arr.mean())-raw["complex_plddt"])>1e-7:
                raise AuditHold("RESIDUE_MEAN_NOT_MATCH_"+mut)
        if len(rec["source"]["msa"])!=2:raise AuditHold("TWO_MSA_FILES_REQUIRED_"+mut)
        for f in rec["source"]["msa"]:
            msa_candidates=list(base.rglob(f["name"]))
            if len(msa_candidates)!=1:raise AuditHold("MSA_NOT_EXACTLY_ONE_"+mut)
            msa=msa_candidates[0]
            check(mut+"_"+f["name"],msa,f["sha256"])
            if msa.stat().st_size!=f["bytes"]:raise AuditHold("MSA_SIZE_DRIFT")
        values.append({"mutation":mut,"ptm":raw["ptm"],"complex_plddt":raw["complex_plddt"],
                       "rowan_ptm":origptm,"rowan_avg_lddt":origlddt,
                       "confidence_sha256":rec["source"]["confidence_json_sha256"]})
    return values

def summary(three,six,inputs,outputs):
    cases=three.get("cases")
    if three.get("state")!="PASS_LOCAL_BBC1_THREE_MSA_SOURCE_VERIFIED_METRIC_PROVIDER_EQUIVALENCE_HOLD":
        raise AuditHold("PINNED_THREE_CASE_BRIDGE_NOT_VERIFIED")
    if list(cases)!=["BBC1_G48D_MSA","BBC1_G53A_MSA","BBC1_WT_MSA"] and set(cases)!={"BBC1_WT_MSA","BBC1_G53A_MSA","BBC1_G48D_MSA"}:
        raise AuditHold("INITIAL_THREE_CASE_SET_DRIFT")
    for name in cases:
        source=cases[name]
        original=(("G48D",.926,.971),("G53A",.918,.968),("WT",.927,.963))
        this=next((k for k in original if name=="BBC1_"+k[0]+"_MSA"),None)
        if this is None or abs(source["rowan_ptm"]-this[1])>1e-12 or abs(source["rowan_avg_lddt"]-this[2])>1e-12:
            raise AuditHold("INITIAL_THREE_ROWAN_DRIFT")
    sixvalues=verify_six(six,inputs,outputs)
    wt=cases["BBC1_WT_MSA"]
    rows=[]
    for name in ("BBC1_G53A_MSA","BBC1_G48D_MSA"):
        v=cases[name]
        rows.append({"mutation":name[5:-4],"ptm":v["ptm"],"complex_plddt":v["complex_plddt"],
                     "rowan_ptm":v["rowan_ptm"],"rowan_avg_lddt":v["rowan_avg_lddt"]})
    rows+=sixvalues
    for r in rows:
        r["local_delta_ptm"]=r["ptm"]-wt["ptm"]
        r["rowan_delta_ptm"]=r["rowan_ptm"]-wt["rowan_ptm"]
        r["delta_ptm_difference"]=r["local_delta_ptm"]-r["rowan_delta_ptm"]
        r["local_delta_plddt"]=r["complex_plddt"]-wt["complex_plddt"]
        r["rowan_delta_avg_lddt"]=r["rowan_avg_lddt"]-wt["rowan_avg_lddt"]
        r["delta_plddt_difference"]=r["local_delta_plddt"]-r["rowan_delta_avg_lddt"]
    ptm=[abs(r["delta_ptm_difference"]) for r in rows]
    plddt=[abs(r["delta_plddt_difference"]) for r in rows]
    return {
      "schema_id":"janus.rowan.bbc1.complete_8_mutant_public_msa_metric_transfer_descriptive.v1",
      "state":"PUBLIC_MSA_9_OF_9_TECHNICAL_PASS_ROWAN_PROVIDER_EQUIVALENCE_OPEN",
      "model":MODEL,
      "frozen_initial_three_receipt":"data/rowan/provenance/ROWAN-BBC1-WT-G53A-G48D-PUBLIC-MSA-BRIDGE-2026-10-26-v2.json",
      "predeclared_remaining_six":"data/rowan/protocols/ROWAN-BBC1-REMAINING-SIX-PUBLIC-MSA-PREREG-2026-10-26-v1.json",
      "sample_size":8,"wildtype_n":1,
      "wt_ptm":{"local":wt["ptm"],"rowan":wt["rowan_ptm"]},
      "wt_plddt":{"local":wt["complex_plddt"],"rowan":wt["rowan_avg_lddt"]},
      "mean_abs_mutant_delta_ptm_discrepancy":statistics.mean(ptm),
      "max_abs_mutant_delta_ptm_discrepancy":max(ptm),
      "mean_abs_mutant_delta_plddt_discrepancy":statistics.mean(plddt),
      "max_abs_mutant_delta_plddt_discrepancy":max(plddt),
      "source_bound_frozen_mutant_rows":rows,
      "fireprot_210_authorized":False,
      "provider_alignment_equivalence":"NOT_DEMONSTRATED_ROWAN_PRIVATE_VS_PUBLIC_COLABFOLD",
      "rowan_model_checkpoint_and_seed_identity":"NOT_ATTESTED",
      "scientific_fitness_or_stability_claim":False,
      "independent_blind_label_test":"NOT_STARTED",
      "rowan_credits_spent":0,
      "production_model_promotion":False
    }
def main():
    p=argparse.ArgumentParser()
    for option in ("three","six","inputs","outputs","out"):p.add_argument("--"+option,required=True,type=Path)
    a=p.parse_args()
    try:
        if a.out.exists():raise AuditHold("IMMUTABLE_OUTPUT_EXISTS")
        three=json.loads(a.three.read_bytes());six=json.loads(a.six.read_bytes())
        result=summary(three,six,a.inputs,a.outputs)
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf8")
        print("BBC1_PUBLIC_MSA_CROSS_COMPATIBILITY="+result["state"])
        return 0
    except (OSError,ValueError,AuditHold) as exc:
        print("BBC1_PUBLIC_MSA_CROSS_COMPATIBILITY=HOLD_"+str(exc))
        return 2
if __name__=="__main__":raise SystemExit(main())
