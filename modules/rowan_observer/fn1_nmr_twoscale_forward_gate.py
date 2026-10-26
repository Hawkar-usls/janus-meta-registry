#!/usr/bin/env python3
"""Minimal NMR forward model gate for isolated FNII1-FNII2 15N T1/T2/NOE.

Physical R1,R2, heteronuclear NOE equations: Hoffmann et al., eqs (1)-(5):
https://www.hereon.de/imperia/md/content/hzg/zentrale_einrichtungen/bibliothek/journals/hoffmann_39187.pdf

No protein MD simulations and no interdomain angle inference. No Rowan API.
The *two-timescale spectral density* is a phenomenological rotational-motion
mixture, NOT a protein conformational ensemble. All real data are prior seen;
this is an explicitly exploratory non-blind model adequacy test.
"""
from __future__ import annotations
from itertools import product
from math import pi, isfinite
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"data/rowan/provenance/ROWAN-FN1-ISOLATED-FNII-PAIR-SMITH2000-ORIGINAL-15N-SI-2026-10-26-v1.json"
PROTOCOL=ROOT/"data/rowan/protocols/ROWAN-FN1-NMR-T1-T2-NOE-TWOSCALE-FORWARD-EXPLORATORY-2026-10-26-v1.json"
FIELD_T=11.7
MU0=4*pi*1e-7
HBAR=1.054571817e-34
GAMMA_H=2*pi*42.57747892e6
GAMMA_15N=-2*pi*4.316e6
NH_DISTANCE_M=1.02e-10
CSA_DELTA=-170e-6
OMEGA_H=GAMMA_H*FIELD_T
OMEGA_N=GAMMA_15N*FIELD_T
FDD=.25*(MU0*HBAR*GAMMA_H*GAMMA_15N/(4*pi*NH_DISTANCE_M**3))**2
FCSA=(OMEGA_N*CSA_DELTA)**2/3
FAST_NS=(0.02,0.05,0.1,0.2,0.4,0.7,1.0)
SLOW_NS=(2.0,3.0,4.0,5.0,6.0,8.0,10.0,12.0,15.0)
FAST_WEIGHT=tuple(i/20 for i in range(21))
REX_NONE=(0.0,)
REX_SENSITIVITY=(0.0,1.0,2.0,4.0,6.0)
ALLOWED=FAST_NS,SLOW_NS,FAST_WEIGHT
SOURCE_SHA256="b426ae59845e3bc944dc968619911ef99d59a54e1b5ca8020ea9027caa103f3e"

class Hold(ValueError):
    pass

def spectral_density(omega_rad_per_s, fast_ns, slow_ns, fast_weight):
    if not (0<fast_ns<slow_ns and 0<=fast_weight<=1):
        raise Hold("INVALID_SPECTRAL_DENSITY_PARAMETERS")
    f=fast_ns*1e-9
    s=slow_ns*1e-9
    return 0.4*(fast_weight*f/(1+(omega_rad_per_s*f)**2)
                +(1-fast_weight)*s/(1+(omega_rad_per_s*s)**2))

def predict(fast_ns, slow_ns, fast_weight, rex_s_inverse=0):
    if not (isfinite(rex_s_inverse) and rex_s_inverse>=0):
        raise Hold("REX_NOT_FINITE_OR_NONNEGATIVE")
    J=lambda x: spectral_density(x,fast_ns,slow_ns,fast_weight)
    jm=J(OMEGA_H-OMEGA_N)
    jp=J(OMEGA_H+OMEGA_N)
    jn=J(OMEGA_N)
    jh=J(OMEGA_H)
    j0=J(0.0)
    r1=FDD*(jm+3*jn+6*jp)+FCSA*jn
    r2=0.5*FDD*(4*j0+jm+3*jn+6*jh+6*jp)+(FCSA/6)*(4*j0+3*jn)+rex_s_inverse
    if r1<=0 or r2<=0:
        raise Hold("NONPOSITIVE_RELAXATION_RATE")
    noe=1.0+(FDD/r1)*(GAMMA_H/GAMMA_15N)*(6*jp-jm)
    if not all(map(isfinite,(r1,r2,noe))):
        raise Hold("NONFINITE_OBSERVABLE")
    return 1000.0/r1,1000.0/r2,noe

def read_real_subset():
    data=json.loads(SOURCE.read_text(encoding="utf8"))
    proto=json.loads(PROTOCOL.read_text(encoding="utf8"))
    if (data["schema_id"]!="janus.rowan.fn1_isolated_fnii_pair_original_author_supplement_relaxation_2000.v1"
        or proto["schema_id"]!="janus.rowan.fn1_heteronuclear_NOE_twotimescale_forward_grid_exploratory.v1"
        or data["archived_author_supplement"]["independently_computed_sha256"]!=SOURCE_SHA256
        or proto["source_pdf_sha256"]!=SOURCE_SHA256):
        raise Hold("ORIGINAL_SOURCE_OR_PROTOCOL_IDENTITY_DRIFT")
    g=proto["grid"]
    if (tuple(g["tau_fast_ns"])!=FAST_NS
        or tuple(float(x) for x in g["tau_slow_ns"])!=SLOW_NS
        or g["grid_size_per_residue_no_Rex"]!=len(FAST_NS)*len(SLOW_NS)*len(FAST_WEIGHT)
        or g["grid_size_per_residue_with_Rex"]!=len(FAST_NS)*len(SLOW_NS)*len(FAST_WEIGHT)*len(REX_SENSITIVITY)):
        raise Hold("FROZEN_GRID_DRIFT")
    c=proto["physical_constants"]
    if (c["field_T"]!=FIELD_T
        or c["hbar_J_s"]!=HBAR or c["r_NH_m"]!=NH_DISTANCE_M
        or c["delta_15N_CSA"]!=CSA_DELTA):
        raise Hold("FROZEN_CONSTANT_DRIFT")
    seq=data["exact_target_mapping"]["modeled_FN1_sequence"]
    if len(seq)!=109 or hashlib.sha256(seq.encode("ascii")).hexdigest()!=data["exact_target_mapping"]["modeled_sequence_sha256"]:
        raise Hold("FROZEN_109AA_SEQUENCE_DRIFT")
    rows=data["selected_real_rows_table_III"]
    if len(rows)!=10 or len({r["si_residue"] for r in rows})!=10:
        raise Hold("MANUALLY_VERIFIED_NMR_10_ROW_SET_DRIFT")
    linker={61,62,63,64,66,69}
    core={52,53,70,71}
    if {r["si_residue"] for r in rows}!=linker|core:
        raise Hold("NMR_HAND_VERIFIED_POSITIONS_DRIFT")
    from fn1_tandem_pair_original_si_noe_gate import run as original_provenance_check
    original_provenance_check(data)
    return rows

def score_single(row, rex_grid):
    # T1 and T2 alone are used to accept each model; NOE is an out-of-fit check.
    obs_t1=float(row["T1_ms"])
    obs_t2=float(row["T2_ms"])
    obs_noe=float(row["het_NOE"])
    t1err=float(row["T1_uncertainty_ms"])
    t2err=float(row["T2_uncertainty_ms"])
    noeerr=float(row["NOE_uncertainty"])
    if not all(isfinite(z) and z>0 for z in (obs_t1,obs_t2,t1err,t2err,noeerr)):
        raise Hold("MISSING_OR_NONPOSITIVE_UNCERTAINTY")
    if not isfinite(obs_noe):
        raise Hold("MISSING_NOE")
    candidates=[]
    for f,s,w in product(FAST_NS,SLOW_NS,FAST_WEIGHT):
        p_t1,p_t2,p_noe=predict(f,s,w,0.0)
        # Recompute R2 from explicit Rex only, R1/NOE unchanged.
        base_R2=1000/p_t2
        if abs(p_t1-obs_t1)>2*t1err:
            continue
        for rex in rex_grid:
            t2_rex=1000.0/(base_R2+rex)
            if abs(t2_rex-obs_t2)>2*t2err:
                continue
            candidates.append((f,s,w,rex,p_noe))
    noe_pass=[x for x in candidates if abs(x[4]-obs_noe)<=2*noeerr]
    return {
      "si_residue_index":row["si_residue"],
      "aa_three_letter":row["residue"],
      "class":row["category"],
      "T1_observed_ms":obs_t1,
      "T2_observed_ms":obs_t2,
      "heteronuclear_NOE_observed":obs_noe,
      "reported_T1_uncertainty_ms":t1err,
      "reported_T2_uncertainty_ms":t2err,
      "reported_NOE_uncertainty":noeerr,
      "T1_T2_accept_count":len(candidates),
      "NOE_independent_2sigma_check_count":len(noe_pass),
      "NOE_2sigma_compatible_fraction_in_T1T2_models":round(len(noe_pass)/len(candidates),6) if candidates else None,
      "NOE_predicted_range_from_T1_T2_only":[round(min(x[4] for x in candidates),6),round(max(x[4] for x in candidates),6)] if candidates else None,
      "NOE_compatible_parameter_ranges":{
        "fast_tau_ns":[min(x[0] for x in noe_pass),max(x[0] for x in noe_pass)],
        "slow_tau_ns":[min(x[1] for x in noe_pass),max(x[1] for x in noe_pass)],
        "fast_weight":[min(x[2] for x in noe_pass),max(x[2] for x in noe_pass)],
        "Rex_s_minus_one":[min(x[3] for x in noe_pass),max(x[3] for x in noe_pass)]
      } if noe_pass else None,
      "outcome":"COARSE_GRID_NO_T1T2_FIT" if not candidates else
               ("SOME_NOE_COMPATIBLE_POINTS_NOT_UNIQUE_POSE" if noe_pass else "T1T2_FIT_BUT_NO_NOE_CHECK_PASS")
    }

def evaluate():
    rows=read_real_subset()
    variants={}
    for name,values in (("strict_Rex_zero",REX_NONE),("Rex_nonnegative_sensitivity",REX_SENSITIVITY)):
        records=[score_single(row,values) for row in rows]
        variants[name]={
          "grid_points_per_residue":len(FAST_NS)*len(SLOW_NS)*len(FAST_WEIGHT)*len(values),
          "rows_total":len(records),
          "rows_with_T1T2_grid_point":sum(r["T1_T2_accept_count"]>0 for r in records),
          "rows_with_T1T2_AND_heldout_NOE_grid_point":sum(r["NOE_independent_2sigma_check_count"]>0 for r in records),
          "individual_residues":records
        }
    return {
      "schema_id":"janus.rowan.fn1_original_smith2000_t1t2_heteronuclear_noe_twoscale_forward_validation.v1",
      "date_utc":"2026-10-26",
      "status":"EXPLORATORY_FIXED_PHYSICAL_FORWARD_MODEL_ADEQUACY_TEST_COMPLETED",
      "theory_url":"https://www.hereon.de/imperia/md/content/hzg/zentrale_einrichtungen/bibliothek/journals/hoffmann_39187.pdf",
      "source_pdf_sha256":SOURCE_SHA256,
      "source_registry_file":str(SOURCE.relative_to(ROOT)),
      "protocol_registry_file":str(PROTOCOL.relative_to(ROOT)),
      "physics":{
        "B0_T":FIELD_T, "r_NH_m":NH_DISTANCE_M,"CSA_delta":CSA_DELTA,
        "gamma_H_rad_s_T":GAMMA_H,"gamma_15N_rad_s_T":GAMMA_15N,
        "spectral_J":"two-exponential phenomenological second-rank NH correlation, factor 2/5; not interdomain spatial coordinate ensemble",
        "NOE":"steady-state heteronuclear 1H-15N NOE, NOT interproton 1H-1H NOESY restraint"
      },
      "models":variants,
      "comparative_scope":{
        "calibration_uses_T1_T2_only":True,
        "heldout_observable_NOE_not_fit":True,
        "data_seen_before_protocol":True,
        "no_prospective_blind":True,
        "T1_T2_2_sigma_rectangular_acceptance_not_joint_CI":True,
        "Rex_model_is_unverified_sensitivity_only":True,
        "CSA_anisotropic_diffusion_and_covariances_not_fitted":True,
        "grid_evidence_not_posterior_samples":True,
        "domain_rotation_angles_not_identifiable":True,
        "no_prediction_of_FNII_3D_ensemble_or_fiber_materials":True,
        "new_rowan_jobs":0, "new_rowan_credits":0, "no_model_promotion":True
      }
    }

def main():
    try:
        print(json.dumps(evaluate(),sort_keys=True,indent=2,allow_nan=False))
        return 0
    except Hold as error:
        print("JANUS_FNII_NMR_FORWARD=HOLD_"+str(error),file=sys.stderr)
        return 2
    except Exception:
        print("JANUS_FNII_NMR_FORWARD=HOLD_UNEXPECTED_SOURCE_OR_NUMERIC_ERROR",file=sys.stderr)
        return 3

if __name__=="__main__":
    sys.exit(main())
