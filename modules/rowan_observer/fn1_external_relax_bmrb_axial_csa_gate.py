#!/usr/bin/env python3
"""Independent published relax fixture, BMRB6470 real single-field rows,
and axial diffusion / residue-variable CSA sensitivity, all NO ROWAN SPEND.

Numerical relax fixture is frozen from external nmr-relax commit and source SHA.
BMRB 6470 is six observable lists ALL at 600 MHz, not multi-field validation.
Axial tensor theta is an illustrative NH-vector polar angle, not FN1 angles.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import urllib.request

ROOT=Path(__file__).resolve().parents[2]
PROTOCOL=ROOT/"data/rowan/protocols/ROWAN-FN1-INDEPENDENT-RELAX-BMRB6470-AXIAL-CSA-GATES-2026-10-26-v1.json"
pi=math.pi
MU0=4*pi*1e-7
HBAR=6.62606876e-34/(2*pi)  # Exactly the original published nmr-relax fixture constant; not current CODATA.
# Exact constants for independently published relax fixture, not JANUS constants.
G1H=267522212.0
GN15=-27126000.0
R_NH=1.02e-10
DIPOLAR=.25*(MU0/(4*pi))**2*(G1H*GN15*HBAR)**2/R_NH**6

class Hold(Exception): pass

def density(omega, tau_ns, s2=.8, te_ns=.1, axial_ratio=1., angle_deg=0):
    if not(0<tau_ns<=100 and 0<te_ns<=10 and 0<=s2<=1 and
           0.25<=axial_ratio<=4 and 0<=angle_deg<=180):
        raise Hold("SPECTRAL_PARAMETERS_OUT_OF_PHYSICAL_GRID")
    Dp=1/(6*tau_ns*1e-9)
    Dl=axial_ratio*Dp
    modes=[6*Dp,5*Dp+Dl,2*Dp+4*Dl]
    c=math.cos(angle_deg*pi/180)
    s=math.sin(angle_deg*pi/180)
    weights=[.25*(3*c*c-1)**2,3*c*c*s*s,.75*s**4]
    if abs(sum(weights)-1)>1e-12:
        raise Hold("AXIAL_SPECTRAL_MODE_WEIGHTS_NOT_NORMALIZED")
    out=0.
    for rate,weight in zip(modes,weights):
        tau=1/rate
        tau_i=1/(rate+1/(te_ns*1e-9))
        out+=weight*(s2*tau/(1+(omega*tau)**2)
                    +(1-s2)*tau_i/(1+(omega*tau_i)**2))
    return .4*out

def rates(proton_MHz,tm_ns=6, s2=.8, te_ns=.1, csa_ppm=-170,
          axial_ratio=1., angle_deg=0, rex=0):
    if not (0<proton_MHz<1500 and -400<csa_ppm<400 and 0<=rex<100):
        raise Hold("SPECTRAL_FIELD_OR_CSA_OUT_OF_RANGE")
    wh=2*pi*proton_MHz*1e6
    wn=wh*(GN15/G1H)
    J=lambda w:density(w,tm_ns,s2,te_ns,axial_ratio,angle_deg)
    j0,jn,jhm,jh,jhp=[J(w) for w in (0,wn,wh-wn,wh,wh+wn)]
    csa=(wn*csa_ppm*1e-6)**2/3
    r1=DIPOLAR*(3*jn+jhm+6*jhp)+csa*jn
    r2=.5*DIPOLAR*(4*j0+3*jn+jhm+6*jh+6*jhp)+(csa/6)*(4*j0+3*jn)+rex
    noe=1+(G1H/GN15)*DIPOLAR*(6*jhp-jhm)/r1
    if not all(math.isfinite(x) and x>0 for x in (r1,r2)):
        raise Hold("NONFINITE_OR_NONPOSITIVE_PHYSICAL_RATE")
    return (r1,r2,noe),[j0,jn,jhm,jh,jhp]

def independent_relax_comparison(protocol):
    ref=protocol["independent_software"]
    if (ref["commit"]!="c48b81e4042f12df1610c8fd32a79448ff857783"
       or ref["source_file_sha256"]!="b149bfb6f3f328020ae71268bcc12b05d90188d160b20c7b42866b60fd83ebd7"
       or len(ref["fixtures"])!=3):
        raise Hold("EXTERNAL_REFERENCE_SOURCE_OR_FIXTURE_DRIFT")
    rows=[]
    for case in ref["fixtures"]:
        pred,j=rates(case["proton_MHz"])
        expected=[case["R1_s_inv"],case["R2_s_inv"],case["NOE"]]
        absdiff=[abs(a-b) for a,b in zip(pred,expected)]
        jdiff=[abs(a-b) for a,b in zip(j,case["J_0_N_Hdiff_H_Hplus"])]
        if max(absdiff)>1e-10 or max(jdiff)>1e-19:
            raise Hold("INDEPENDENT_RELAX_NUMERICAL_DISAGREEMENT_"+str(case["proton_MHz"]))
        rows.append({
          "proton_MHz":case["proton_MHz"],
          "independent_relax_R1_R2_NOE":expected,
          "JANUS_R1_R2_NOE":[round(x,12) for x in pred],
          "max_absolute_relax_R1_R2_NOE_error":max(absdiff),
          "max_J_spectral_density_absolute_error_s":max(jdiff),
          "PASS_independent_external_reference":True
        })
    return rows

def get_bmrb(protocol):
    b=protocol["published_data"]
    req=urllib.request.Request(b["source_url"],headers={"User-Agent":"JANUS-NMR-public-source-evidence/1.0"})
    with urllib.request.urlopen(req,timeout=30) as f:
        data=f.read(400000)
    if len(data)!=b["source_bytes_observed"] or hashlib.sha256(data).hexdigest()!=b["source_sha256"]:
        raise Hold("BMRB_REAL_SOURCE_SIZE_OR_HASH_DRIFT")
    return data.decode("utf8")

def parse_bmrb_frames(star):
    # Narrow BMRB6470 STAR v3 parser: content parsed inside six fixed saveframes,
    # simple whitespace-delimited rows only; will HOLD if unknown loop grammar.
    target={
     "15N_T1_set_1":("_T1.","_T1.Seq_ID","_T1.Val"),
     "15N_T1_set_2":("_T1.","_T1.Seq_ID","_T1.Val"),
     "15N_T2_set_1":("_T2.","_T2.Seq_ID","_T2.T2_val"),
     "15N_T2_set_2":("_T2.","_T2.Seq_ID","_T2.T2_val"),
     "heteronuclear_NOE_set_1":("_Heteronucl_NOE.","_Heteronucl_NOE.Seq_ID_1","_Heteronucl_NOE.Val"),
     "heteronuclear_NOE_set_2":("_Heteronucl_NOE.","_Heteronucl_NOE.Seq_ID_1","_Heteronucl_NOE.Val")
    }
    out={}
    for name,(prefix,seqtag,valtag) in target.items():
        start="save_"+name+"\n"
        if star.count(start)!=1:
            raise Hold("BMRB_SAVEFRAME_MISSING_OR_DUPLICATE_"+name)
        f=star.split(start,1)[1].split("\nsave_",1)[0]
        if "_"+("Heteronucl_NOE_list" if "NOE" in name else ("Heteronucl_T1_list" if "T1" in name else "Heteronucl_T2_list"))+".Spectrometer_frequency_1H" not in f:
            raise Hold("BMRB_SPECTROMETER_FREQUENCY_NOT_FOUND_"+name)
        import re
        field=re.search(r"Spectrometer_frequency_1H\s+(\S+)",f)
        if not field or float(field.group(1))!=600.:
            raise Hold("BMRB_NOT_SINGLE_600MHZ_ALL_SIX_SETS")
        matched=None
        lines=f.splitlines()
        for n,line in enumerate(lines):
            if line.strip()!="loop_":
                continue
            i=n+1
            tags=[]
            while i<len(lines) and lines[i].strip().startswith("_"):
                tags.append(lines[i].strip())
                i+=1
            if seqtag not in tags or valtag not in tags:
                continue
            matched={}
            i_seq=tags.index(seqtag)
            i_val=tags.index(valtag)
            while i<len(lines) and lines[i].strip()!="stop_":
                cur=lines[i].strip()
                if cur and not cur.startswith("#"):
                    parts=cur.split()
                    if len(parts)!=len(tags):
                        raise Hold("BMRB_NONCOMPACT_ROW_OR_GRAMMAR_CHANGED_"+name)
                    seq=parts[i_seq]
                    val=parts[i_val]
                    if seq not in (".","?") and val not in (".","?"):
                        k=int(seq)
                        if k in matched:
                            raise Hold("BMRB_DUPLICATE_RESIDUE_"+name)
                        matched[k]=float(val)
                i+=1
            break
        if matched is None or len(matched)!=68:
            raise Hold("BMRB_DATASET_LENGTH_OR_LOOP_CHANGED_"+name)
        if any(not math.isfinite(x) for x in matched.values()):
            raise Hold("BMRB_NONFINITE_MEASUREMENT")
        out[name]=matched
    return out

def summarize_bmrb(maps):
    p={}
    common=set.intersection(*(set(x) for x in maps.values()))
    if len(common)!=68:
        raise Hold("BMRB_SIX_LIST_SHARED_RESIDUES_INCOMPLETE")
    for key in ("15N_T1","15N_T2","heteronuclear_NOE"):
        a=maps[key+"_set_1"]
        b=maps[key+"_set_2"]
        if set(a)!=set(b):
            raise Hold("BMRB_PAIRED_SETS_NOT_IDENTICAL_RESIDUE_KEYS")
        differences=[abs(a[k]-b[k]) for k in common]
        p[key]={
          "n_common_residues":len(common),
          "set1_median":round(statistics.median(a.values()),6),
          "set2_median":round(statistics.median(b.values()),6),
          "median_absolute_difference_between_two_600MHz_sets":round(statistics.median(differences),6),
          "max_absolute_difference_between_sets":round(max(differences),6),
          "original_units":"seconds" if key in ("15N_T1","15N_T2") else "dimensionless",
          "no_uncertainty_calibrated_validation":True
        }
    return p

def sensitivity():
    cases=[]
    for frequency in (400,600,800):
        for axial_ratio in (.5,1.,2.):
            for theta in (0,45,90):
                for csa in (-155,-170,-185):
                    p,_=rates(frequency,axial_ratio=axial_ratio,angle_deg=theta,csa_ppm=csa)
                    cases.append({
                     "proton_MHz":frequency,"Dparallel_to_Dperp":axial_ratio,
                     "NH_polar_angle_deg_not_FN1_fitted":theta,"CSA_ppm":csa,
                     "R1_s_inv":round(p[0],9),"R2_s_inv":round(p[1],9),"NOE":round(p[2],9)
                    })
    for f in (400,600,800):
        subset=[x for x in cases if x["proton_MHz"]==f]
        controls=[x for x in subset if x["Dparallel_to_Dperp"]==1 and x["CSA_ppm"]==-170]
        if len(controls)!=3 or any(abs(x["R1_s_inv"]-controls[0]["R1_s_inv"])>1e-9 for x in controls):
            raise Hold("AXIAL_SPHERICAL_LIMIT_FAILS_ANGLE_INVARIANCE")
    return {
      "cases_count":len(cases),
      "cases":cases,
      "full_grid_aggregate_by_field": {
        str(f):{
          name:{"min":min(x[name] for x in cases if x["proton_MHz"]==f),
                "max":max(x[name] for x in cases if x["proton_MHz"]==f)}
          for name in ("R1_s_inv","R2_s_inv","NOE")}
        for f in (400,600,800)
      }
    }

def evaluate():
    protocol=json.loads(PROTOCOL.read_text(encoding="utf8"))
    if protocol["schema_id"]!="janus.rowan.fn1_independent_relax_backcalc_bmrb6470_aniso_csa_sources.v1":
        raise Hold("PREREG_SCHEMA_DRIFT")
    measured=summarize_bmrb(parse_bmrb_frames(get_bmrb(protocol)))
    source=protocol["published_data"]
    return {
      "schema_id":"janus.rowan.fn1_external_relax_formula_reference_bmrb6470_singlefield_axial_csa_sensitivity.v1",
      "date_utc":"2026-10-26",
      "status":"PASS_INDEPENDENT_RELAX_NUMERICAL_REFERENCE_AND_PUBLIC_BMRB600MHZ_SOURCE",
      "external_software_numerical_comparison":independent_relax_comparison(protocol),
      "BMRB_data":{"entry":6470,"source_sha256":source["source_sha256"],"all_six_sets_600MHz":True,
                   "NOT_MULTIFIELD_EXPERIMENT":True,"real_measured_values":measured},
      "axial_CSA_theoretical_sensitivity_not_FN1_fitted":sensitivity(),
      "scientific_limits":{
        "real_pub_experiment_not_fitted_by_our_anisotropy_grid":True,
        "BMRB_6470_is_600MHz_only":True,
        "reference_relax_exact_physics_math_comparison":True,
        "axial_diffusion_axis_orientation_to_FN1_not_measured":True,
        "CSA_ppm_sweep_is_assumption_sensitivity":True,
        "no_unique_FNII_domain_angular_ensemble":True,
        "NOE_is_heteronuclear_local_dynamics_not_NOESY_distance":True,
        "multi_field_predictions_are_theoretical_only":True,
        "no_new_Rowan_jobs":0,"no_new_Rowan_credits":0,"no_shadow_promotion":True
      }
    }

def main():
    try:
        obj=evaluate()
        print(json.dumps(obj,indent=2,sort_keys=True,allow_nan=False))
        return 0
    except Hold as e:
        print("JANUS_FN1_INDEPENDENT_PHYSICS=HOLD_"+str(e),file=sys.stderr);return 2
    except Exception:
        print("JANUS_FN1_INDEPENDENT_PHYSICS=HOLD_SOURCE_NOT_AVAILABLE_OR_MALFORMED",file=sys.stderr);return 3
if __name__=="__main__":sys.exit(main())
