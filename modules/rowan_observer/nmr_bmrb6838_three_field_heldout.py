#!/usr/bin/env python3
"""BMRB 6838 PSE-4 500/600 -> held-out 800MHz N15 R1/R2/hetNOE.

SOURCE: https://bmrb.io/ftp/pub/bmrb/entry_directories/bmr6838/bmr6838_3.str
Frozen protocol: data/rowan/protocols/ROWAN-NMR-BMRB6838-PSE4-THREE-FIELD-500600-TRAIN-800-HOLDOUT-2026-10-26-v1.json

Published 800 MHz R2 data were independently flagged inconsistent.
For this reason a hold-out failure need NOT mean physics/model is false.
Only per-residue exploratory fits to external PSE-4, NOT FN1 true angles.
No Rowan provider key, jobs, credits, or model promotion.
"""
from __future__ import annotations
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import urllib.request

import numpy as np
import pynmrstar
from scipy.optimize import least_squares
from fn1_external_relax_bmrb_axial_csa_gate import rates as published_relax_compatible_rates

ROOT=Path(__file__).resolve().parents[2]
PROTOCOL=ROOT/"data/rowan/protocols/ROWAN-NMR-BMRB6838-PSE4-THREE-FIELD-500600-TRAIN-800-HOLDOUT-2026-10-26-v1.json"
SOURCE_SHA="aa437c7f9dd906b8622907aa79f372a211cac2606fbcd3603c477f3cc9cde661"
FIELDS=(500,600,800)
OBS=("R1","R2","NOE")
MODELS=("M0_ISO_CSA170","M1_ISO_VAR_CSA","M2_AXIAL_FIXED_CSA","M3_AXIAL_VAR_CSA")
TRAIN=(500,600)
TEST=800
BASE_STARTS=((8.0,0.70),(15.0,0.85),(23.0,0.95))
class Hold(Exception): pass

def read_protocol():
    p=json.loads(PROTOCOL.read_text(encoding="utf8"))
    if p["schema_id"]!="janus.rowan.nmr_BMRB6838_three_field_heldout_predictive_baseline_protocol.v1":
        raise Hold("PROTOCOL_SCHEMA_DRIFT")
    src=p["data_source"]
    if (src["sha256"]!=SOURCE_SHA or src["training_fields_MHz"]!=[500,600]
        or src["single_frozen_test_field_MHz"]!=800 or src["source_sample_conditions_list_id"]!=2
        or src["complete_same_residue_nine_values_preliminarily_found"]!=230):
        raise Hold("SOURCE_SPLIT_OR_PROTOCOL_CHANGED")
    if [m["id"] for m in p["fixed_forward_model"]["models"]]!=list(MODELS):
        raise Hold("MODEL_ORDER_OR_SET_DRIFT")
    if [(x["tau_ns"],x["S2"]) for x in p["fixed_forward_model"]["start_seeds"]]!=list(BASE_STARTS):
        raise Hold("FITTING_INITIALIZATION_DRIFT")
    return p

def source_text(proto):
    url=proto["data_source"]["file_url"]
    req=urllib.request.Request(url,headers={"User-Agent":"JANUS-independent-PSE4-NMR-heldout/1.0"})
    with urllib.request.urlopen(req,timeout=40) as resp: raw=resp.read(700000)
    if len(raw)!=555956 or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA:
        raise Hold("BMRB6838_ORIGINAL_SOURCE_DIGEST_OR_SIZE_DRIFT")
    return raw.decode("utf-8")

def parse_all_nine_real_observables(star_text):
    try: d=pynmrstar.Entry.from_string(star_text)
    except Exception as e: raise Hold("NMRSTAR_GRAMMAR_MISMATCH") from e
    if str(d.entry_id)!="6838":raise Hold("WRONG_BMRB_ACCESSION")
    conditions=[f for f in d.frame_list if f.category=="sample_conditions" and f.name=="conditions_2"]
    if len(conditions)!=1:raise Hold("MEASUREMENT_CONDITION_UNKNOWN")
    ctl=[conditions[0].get_loop_by_category("_Sample_condition_variable")]
    if len(ctl)!=1:raise Hold("MEASUREMENT_CONDITION_LOOP_CHANGED")
    ci=ctl[0].tags.index("Type");vi=ctl[0].tags.index("Val");ui=ctl[0].tags.index("Val_units")
    cond={r[ci]:(float(r[vi]),r[ui]) for r in ctl[0].data}
    if cond.get("temperature")!=(304.65,"K") or cond.get("pH")!=(6.65,"pH"):
        raise Hold("TEMPERATURE_OR_PH_CHANGED")
    label_to_type={"heteronucl_T1_relaxation":"R1","heteronucl_T2_relaxation":"R2","heteronucl_NOEs":"NOE"}
    result={}
    input_sizes={}
    for f in d.frame_list:
        if f.category not in label_to_type:continue
        observable=label_to_type[f.category]
        metadata=dict(f.tags)
        try:freq=int(metadata["Spectrometer_frequency_1H"])
        except Exception as e:raise Hold("MEASUREMENT_FIELD_NOT_GROUNDED") from e
        if (freq not in FIELDS or str(metadata.get("Sample_condition_list_ID"))!="2"
            or metadata.get("Sample_condition_list_label")!="$conditions_2"):
            raise Hold("OBSERVABLE_FIELD_OR_CONDITIONS_MIXED")
        if observable in ("R1","R2"):
            if metadata.get(("T1_val_units" if observable=="R1" else "T2_val_units"))!="ms":
                raise Hold("T1_T2_UNITS_NOT_MILLISECONDS")
        loops=[l for l in f.loops if l.category=={"R1":"_T1","R2":"_T2","NOE":"_Heteronucl_NOE"}[observable]]
        if len(loops)!=1:raise Hold("MISSING_NMR_MEASUREMENTS_LOOP")
        l=loops[0]
        namekey="Seq_ID_1" if observable=="NOE" else "Seq_ID"
        aakey="Comp_ID_1" if observable=="NOE" else "Comp_ID"
        valuekey={"R1":"Val","R2":"T2_val","NOE":"Val"}[observable]
        errkey={"R1":"Val_err","R2":"T2_val_err","NOE":"Val_err"}[observable]
        try:idx=[l.tags.index(x) for x in (namekey,aakey,valuekey,errkey)]
        except Exception as e:raise Hold("LOOP_FIELDS_MISSING") from e
        observations={}
        for row in l.data:
            rid,aa,val,err=(row[i] for i in idx)
            if rid in (".","?") or val in (".","?") or err in (".","?"):continue
            try:rid=int(rid);val=float(val);err=float(err)
            except (ValueError,TypeError):continue
            if rid<1 or not all(math.isfinite(x) for x in (val,err)) or err<=0:
                raise Hold("INVALID_MEASURED_DATA_OR_UNCERTAINTY")
            if observable in ("R1","R2") and val<=0:
                raise Hold("RELAXATION_TIME_NONPOSITIVE")
            if rid in observations:raise Hold("DUPLICATE_RESIDUE_PER_FIELD")
            # The deposit stores T1/T2 times in ms; rates in s^-1 with
            # first-order uncertainty propagation. This does not cure covariance.
            if observable in ("R1","R2"):
                original={"T_ms":val,"T_ms_error":err}
                rate=1000.0/val
                rate_se=1000.0*err/(val*val)
                observations[rid]=(aa,rate,rate_se,original)
            else:
                observations[rid]=(aa,val,err,{"NOE":val,"NOE_error":err})
        k=(freq,observable)
        if k in result:raise Hold("DUPLICATE_NMR_FIELD_DATASET")
        result[k]=observations
        input_sizes[f"{freq}_{observable}"]={"loop_rows":len(l.data),"usable_error_rows":len(observations)}
    if set(result)!={(f,m) for f in FIELDS for m in OBS}:
        raise Hold("NOT_ALL_NINE_FIELD_OBSERVABLE_DATASETS")
    shared=set.intersection(*(set(v) for v in result.values()))
    if len(shared)!=230:raise Hold("NINEFOLD_OVERLAP_DIFFERS_FROM_FROZEN_230")
    samples=[]
    for resid in sorted(shared):
        names={result[(f,m)][resid][0] for f in FIELDS for m in OBS}
        if len(names)!=1:raise Hold("AMINO_ACID_IDENTITY_MISMATCH_ACROSS_FIELDS")
        sample={"resid":resid,"aa3":next(iter(names)),"data":{}}
        for f in FIELDS:
            sample["data"][str(f)]={}
            for obs in OBS:
                _,val,se,orig=result[(f,obs)][resid]
                sample["data"][str(f)][obs]={"value":val,"se":se,"original":orig}
        samples.append(sample)
    return samples,input_sizes,{"temperature_K":304.65,"pH":6.65,"sample_condition_id":2}

def unravel(p,mode):
    tm=float(p[0]);s2=float(p[1])
    csa=float(p[2]) if mode in ("M1_ISO_VAR_CSA","M3_AXIAL_VAR_CSA") else -170.
    ar=float(p[-1]) if mode in ("M2_AXIAL_FIXED_CSA","M3_AXIAL_VAR_CSA") else 1.
    return tm,s2,csa,ar

def bounds_and_x0(mode,seed):
    starts=list(seed); lower=[2.,0.05];upper=[45.,1.]
    if mode in ("M1_ISO_VAR_CSA","M3_AXIAL_VAR_CSA"):
        starts.append(-170.);lower.append(-220.);upper.append(-120.)
    if mode in ("M2_AXIAL_FIXED_CSA","M3_AXIAL_VAR_CSA"):
        starts.append(1.0);lower.append(0.5);upper.append(2.0)
    return starts,lower,upper

def predict_field(mhz,p,mode):
    tm,s2,csa,ar=unravel(p,mode)
    rate,_=published_relax_compatible_rates(mhz,tm_ns=tm,s2=s2,te_ns=.1,
        csa_ppm=csa,axial_ratio=ar,angle_deg=45,rex=0.)
    if len(rate)!=3 or not all(math.isfinite(v) for v in rate):
        raise Hold("NONFINITE_PHYSICAL_PREDICTION")
    return rate

def train_one_residue(row,mode):
    cache=[(mhz,obs,row["data"][str(mhz)][obs]) for mhz in TRAIN for obs in OBS]
    def vector(p):
        vals={mhz:predict_field(mhz,p,mode) for mhz in TRAIN}
        return np.array([(vals[mhz][OBS.index(obs)]-source["value"])/source["se"]
                         for mhz,obs,source in cache],dtype=float)
    winner=None
    for seed in BASE_STARTS:
        x0,lo,hi=bounds_and_x0(mode,seed)
        result=least_squares(vector,x0,bounds=(lo,hi),method="trf",
                             ftol=1e-8,xtol=1e-8,gtol=1e-8,max_nfev=200)
        loss=float(np.dot(result.fun,result.fun))
        if not math.isfinite(loss):raise Hold("NONFINITE_OPTIMIZATION_LOSS")
        if winner is None or loss<winner[0]:
            winner=(loss,result)
    loss,fit=winner
    vals800=predict_field(TEST,fit.x,mode)
    held={}
    for idx,obs in enumerate(OBS):
        datum=row["data"]["800"][obs]
        z=(vals800[idx]-datum["value"])/datum["se"]
        held[obs]={"predicted":float(vals800[idx]),"observed":datum["value"],
                   "reported_SE":datum["se"],"standardized_residual":float(z),
                   "squared_standardized_residual":float(z*z),
                   "within_2_reported_SE":bool(abs(z)<=2)}
    return {
       "model":mode,"train_chi2_six_observations":loss,
       "optimizer_reported_success":bool(fit.success),
       "optimizer_status":int(fit.status),
       "optimizer_evaluations":int(fit.nfev),
       "fitted_params":{"tm_ns":float(unravel(fit.x,mode)[0]),
                        "S2":float(unravel(fit.x,mode)[1]),
                        "CSA_ppm":float(unravel(fit.x,mode)[2]),
                        "Dparallel_to_Dperp":float(unravel(fit.x,mode)[3]),
                        "NH_angle_deg_frozen_illustrative":45.},
       "holdout_800MHz":held,
       "holdout_total_chi2":sum(held[x]["squared_standardized_residual"] for x in OBS),
       "holdout_R1_NOE_chi2_excluding_known_bad_800MHz_R2":
           sum(held[x]["squared_standardized_residual"] for x in ("R1","NOE")),
       "holdout_all_three_within_2_SE":all(held[x]["within_2_reported_SE"] for x in OBS)
    }

def summarize(rows):
    results={}
    for mode in MODELS:
        fits=[r["models"][mode] for r in rows]
        def describe(key):
            a=[r[key] for r in fits]
            return {"median":float(statistics.median(a)),
                    "mean":float(statistics.fmean(a)),
                    "max":float(max(a))}
        results[mode]={
          "residues":len(fits),
          "training_chi2":describe("train_chi2_six_observations"),
          "800MHz_holdout_all_three_chi2":describe("holdout_total_chi2"),
          "800MHz_holdout_R1_NOE_chi2_without_bad_T2":describe(
               "holdout_R1_NOE_chi2_excluding_known_bad_800MHz_R2"),
          "all_three_within_2SE_count":sum(f["holdout_all_three_within_2_SE"] for f in fits),
          "solver_success_count":sum(f["optimizer_reported_success"] for f in fits),
          "per_observable_800MHz":{
            obs:{
              "median_absolute_standardized_residual":float(statistics.median(
                  abs(f["holdout_800MHz"][obs]["standardized_residual"]) for f in fits)),
              "mean_squared_standardized_residual":float(statistics.fmean(
                  f["holdout_800MHz"][obs]["squared_standardized_residual"] for f in fits)),
              "within_two_SE_count":sum(f["holdout_800MHz"][obs]["within_2_reported_SE"] for f in fits)
            } for obs in OBS
          },
          "residues_with_lower_800MHz_total_chi2_than_M0":sum(
           f["holdout_total_chi2"]<r["models"]["M0_ISO_CSA170"]["holdout_total_chi2"]
           for f,r in zip(fits,rows)
          ) if mode!="M0_ISO_CSA170" else None
        }
    return results

def evaluate():
    proto=read_protocol()
    rows,sizes,cond=parse_all_nine_real_observables(source_text(proto))
    for i,row in enumerate(rows):
        row["models"]={}
        for model in MODELS:
            row["models"][model]=train_one_residue(row,model)
        if i%50==0:print("BMRB6838_ANALYSIS_PROGRESS="+str(i+1)+"/"+str(len(rows)),file=sys.stderr)
    return {
      "schema_id":"janus.rowan.nmr_BMRB6838_three_field_actual_500600_fit_800_heldout_v1",
      "date_utc":"2026-10-26",
      "status":"EXPLORATORY_GENUINE_THREE_FIELD_HELDOUT_COMPUTATION_COMPLETED",
      "protocol":"data/rowan/protocols/ROWAN-NMR-BMRB6838-PSE4-THREE-FIELD-500600-TRAIN-800-HOLDOUT-2026-10-26-v1.json",
      "source_url":proto["data_source"]["file_url"],
      "source_sha256":SOURCE_SHA,
      "unit_and_sample_conditions":cond,
      "per_field_observable_source_sizes":sizes,
      "total_rows_with_complete_9_measurements_and_reported_SE":len(rows),
      "model_training_fields_MHz":[500,600],
      "field_never_used_in_training_MHz":800,
      "model_reference":"modules/rowan_observer/fn1_external_relax_bmrb_axial_csa_gate.py",
      "comparisons":summarize(rows),
      "each_residue_exact_source_values_errors_fits_and_800MHz_prediction":rows,
      "epistemic_limits":{
        "known_800MHz_R2_dataset_inconsistency":True,
        "800MHz_R1_NOE_secondary_diagnostic_excluding_R2":True,
        "PSE4_external_protein_not_FNII":True,
        "different_observables_from_one_protein_not_independent_protein_replicates":True,
        "parameters_fit_per_residue_at_500_600":True,
        "theta_45_degrees_arbitrary_not_measured_NH_vector_orientation":True,
        "anisotropy_ratio_fitted_per_residue_not_shared_global_diffusion_tensor":True,
        "no_significance_test_or_prospective_blind":True,
        "no_experimental_identification_of_interdomain_angle":True,
        "some_800MHz_discrepancy_can_be_source_technical":True,
        "no_model_type_automatically_declared_superior":True,
        "no_Rowan_jobs":0,"no_Rowan_credits":0,
        "no_SCOBY_materials_or_FNII_functional_claim":True,
        "no_shadow_weights_promoted":True
      }
    }

def main():
    try:
        output=evaluate()
        path=__import__("os").environ.get("JANUS_BMRB6838_ACTUAL_RECEIPT")
        if not path:raise Hold("MISSING_OUTPUT_RECEIPT_PATH")
        p=Path(path)
        if p.exists():raise Hold("RECEIPT_PATH_IMMUTABILITY_VIOLATION")
        p.write_text(json.dumps(output,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf8")
        print("BMRB6838_REAL_SOURCE=PASS_THREE_FIELDS_230_RESIDUES")
        for k,v in output["comparisons"].items():
            print(k,"HELDOUT800_MEDIAN_CHI2",v["800MHz_holdout_all_three_chi2"]["median"],
                  "HELDOUT800_R1NOE_MEDIAN_CHI2",v["800MHz_holdout_R1_NOE_chi2_without_bad_T2"]["median"],
                  "N_ALL_WITHIN_2SE",v["all_three_within_2SE_count"])
        print("JANUS_ROWAN_NEW_JOBS=0")
        return 0
    except Hold as err:
        print("BMRB6838_HELDOUT=HOLD_"+str(err),file=sys.stderr);return 2
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        print("BMRB6838_HELDOUT=HOLD_IMPLEMENTATION_OR_REMOTE_SOURCE",file=sys.stderr);return 3

if __name__=="__main__":sys.exit(main())
