#!/usr/bin/env python3
"""Independent azurin 1E5Y shape-only hydrodynamic Rotne-Prager-Yamakawa gate.

Use EXACT published BMRB6243 + PDB1E5Y source bytes, never train on 800MHz.
This RPY C-alpha bead estimate is *not* HYDRONMR and NOT measured diffusion.
Rex is a global preset TRAINING sensitivity; values are not physically detected.
"""
from __future__ import annotations
import hashlib,io,json,math,os,statistics,sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from Bio.PDB import MMCIFParser
from nmr_azurin6243_1e5y_structural_holdout import load_raw,parse_nmr,normalized
from fn1_external_relax_bmrb_axial_csa_gate import rates

ROOT=Path(__file__).resolve().parents[2]
PROTO=ROOT/"data/rowan/protocols/ROWAN-AZURIN6243-RPY-HYDRODYNAMIC-CSA-REX-NH-SENSITIVITY-2026-10-26-v1.json"
MODELS=("RPY_CSA_FIXED_REX0","RPY_CSA_VAR_REX0",
        "RPY_CSA_FIXED_REX_GLOBAL","RPY_CSA_VAR_REX_GLOBAL")
RADIUS_GRID=(2.5,3.,3.5)
TAU_GRID=(3,4,6,8,10,14)
REX_GRID=(0.,1.,2.)
TRAIN_FIELDS=(500,600)
OBS=("R1","R2","NOE")
class Hold(Exception):pass

def load_structure(cif,sequence):
    structure=MMCIFParser(QUIET=True).get_structure("azurin",io.StringIO(cif.decode("utf8")))
    from Bio.SeqUtils import seq1
    res={r.id[1]:r for r in structure[0]["A"] if r.id[0]==" "}
    if set(res)!=set(range(1,129)):raise Hold("STRUCTURE_RESIDUE_MAP_CHANGED")
    found="".join(seq1(res[i].resname) for i in range(1,129))
    if found!=sequence:raise Hold("STRUCTURE_NMR_SEQUENCE_MISMATCH")
    xyz=np.array([res[i]["CA"].coord for i in range(1,129)],dtype=np.float64)
    nh={}
    omitted={}
    for i in range(1,129):
        if i==1 or res[i].resname=="PRO":
            omitted[i]="TERMINUS_OR_PROLINE";continue
        if not all(x in res[i] for x in ("CA","N")) or "C" not in res[i-1]:
            omitted[i]="HEAVY_ATOM_MISSING";continue
        n=np.asarray(res[i]["N"].coord,dtype=float)
        ca=np.asarray(res[i]["CA"].coord,dtype=float)
        c=np.asarray(res[i-1]["C"].coord,dtype=float)
        if np.linalg.norm(c-n)>1.9:
            omitted[i]="BROKEN_PEPTIDE_BOND";continue
        nh[i]=normalized(-normalized(c-n)-normalized(ca-n))
    if len(nh)!=123:raise Hold("SOURCE_CONSTRUCT_NH_COUNT_DRIFT")
    return xyz,nh,omitted

def rpy_rotational_tensor(ca,bead_radius_A):
    """6x6 rigid hydrodynamic diffusion mobility from overlapping-sphere RPY."""
    n=len(ca)
    if n!=128 or bead_radius_A not in RADIUS_GRID:raise Hold("RPY_FROZEN_SOURCE_OR_RADIUS_DRIFT")
    points=ca-ca.mean(axis=0)
    mobility=np.zeros((3*n,3*n),dtype=float)
    eye=np.eye(3)
    a=bead_radius_A
    for i in range(n):
        mobility[3*i:3*i+3,3*i:3*i+3]=eye/(6*math.pi*a)
        for j in range(i+1,n):
            delta=points[i]-points[j]
            r=float(np.linalg.norm(delta))
            if r<1e-6:raise Hold("RPY_IDENTICAL_BEAD_CENTERS")
            nn=np.outer(delta/r,delta/r)
            if r<=2*a:
                block=((1-9*r/(32*a))*eye+(3*r/(32*a))*nn)/(6*math.pi*a)
            else:
                block=((1+2*a*a/(3*r*r))*eye+(1-2*a*a/(r*r))*nn)/(8*math.pi*r)
            mobility[3*i:3*i+3,3*j:3*j+3]=block
            mobility[3*j:3*j+3,3*i:3*i+3]=block
    k=np.zeros((3*n,6),dtype=float)
    for i,(x,y,z) in enumerate(points):
        k[3*i:3*i+3,:3]=eye
        k[3*i:3*i+3,3:]=[[0,z,-y],[-z,0,x],[y,-x,0]]
    if not np.allclose(mobility,mobility.T,atol=1e-13):
        raise Hold("RPY_MATRIX_NOT_SYMMETRIC")
    chol=np.linalg.cholesky(mobility)
    friction=k.T@np.linalg.solve(mobility,k)
    m6=np.linalg.inv(friction)
    rot=(m6[3:,3:]+m6[3:,3:].T)/2
    values,vectors=np.linalg.eigh(rot)
    if min(values)<=0:raise Hold("NONPOSITIVE_RPY_ROTATIONAL_MOBILITY")
    ratio=float(values[2]/((values[0]+values[1])/2))
    axis=normalized(vectors[:,-1])
    pca_eig,pca_axes=np.linalg.eigh(np.cov(ca.T))
    long_axis=normalized(pca_axes[:,-1])
    return {
      "bead_radius_A":a,
      "rotational_mobility_eigenvalues_unscaled":[float(v) for v in values],
      "rotational_diffusion_fast_to_two_transverse_mean_ratio":ratio,
      "transverse_ratio_max_over_min":float(values[1]/values[0]),
      "fast_axis_xyz":[float(v) for v in axis],
      "PCA_long_axis_xyz":[float(v) for v in long_axis],
      "abs_dot_fast_axis_PCA_long_axis":float(abs(np.dot(axis,long_axis))),
      "theoretical_eigenvalues_independent_of_NMR":True,
      "assumed_viscosity_not_used":True,
      "approximation_CA_centric_beads_not_hydronmr":True
    }

def theta_for_vectors(vectors,hydro):
    axis=np.array(hydro["fast_axis_xyz"])
    return {i:math.degrees(math.acos(float(np.clip(abs(np.dot(v,axis)),0,1))))
            for i,v in vectors.items()}

def one_local_fit(row,tau,ratio,angle,rex,var_csa):
    train=[(f,ob,row["data"][str(f)][ob]) for f in TRAIN_FIELDS for ob in OBS]
    def residual(p):
        s2=float(p[0]);csa=float(p[1]) if var_csa else -170.
        out={}
        for f in TRAIN_FIELDS:
            r,_=rates(f,tm_ns=tau,s2=s2,te_ns=.1,csa_ppm=csa,
                      axial_ratio=ratio,angle_deg=angle,rex=rex)
            out[f]=r
        return np.array([(out[f][OBS.index(ob)]-val["value"])/val["SE"]
                         for f,ob,val in train])
    best=None
    for seed in (.45,.75,.95):
        x=[seed,-170.] if var_csa else [seed]
        lo=[.05,-220.] if var_csa else [.05]
        hi=[1.,-120.] if var_csa else [1.]
        result=least_squares(residual,x,bounds=(lo,hi),max_nfev=75,
                             method="trf",ftol=1e-8,xtol=1e-8)
        loss=float(result.fun@result.fun)
        if not math.isfinite(loss):raise Hold("TRAINING_LOSS_NONFINITE")
        if best is None or loss<best[0]:
            best=(loss,[float(v) for v in result.x],bool(result.success))
    return best

def fit_series(temperature_id,source_rows,angles,hydro):
    used=[row for row in source_rows if row["pos"] in angles]
    if len(used)!=len(source_rows):raise Hold("STRUCTURE_SOURCE_COVERAGE_NOT_COMPLETE")
    ratio=hydro["rotational_diffusion_fast_to_two_transverse_mean_ratio"]
    output={}
    for model in MODELS:
        var_csa="VAR" in model
        rex_possible=REX_GRID if "REX_GLOBAL" in model else (0.,)
        candidates=[]
        for tau in TAU_GRID:
            for rex in rex_possible:
                fits=[one_local_fit(row,tau,ratio,angles[row["pos"]],rex,var_csa)
                      for row in used]
                candidates.append((sum(v[0] for v in fits),tau,rex,fits))
        train_loss,tau,rex,fits=min(candidates,key=lambda x:x[0])
        per=[]
        for row,(loss,pars,success) in zip(used,fits):
            s2=pars[0];csa=pars[1] if var_csa else -170.
            prediction,_=rates(800,tm_ns=tau,s2=s2,te_ns=.1,csa_ppm=csa,
                               axial_ratio=ratio,angle_deg=angles[row["pos"]],rex=rex)
            test={}
            for j,ob in enumerate(OBS):
                actual=row["data"]["800"][ob]
                z=(prediction[j]-actual["value"])/actual["SE"]
                test[ob]={"predicted":float(prediction[j]),"measured":actual["value"],
                          "reported_SE":actual["SE"],"z":float(z),"z_squared":float(z*z)}
            per.append({
              "index":row["pos"],"aa3":row["aa3"],"angle_NH_to_RPY_fast_axis_deg":angles[row["pos"]],
              "training_fit_S2":s2,"training_fit_CSA_ppm":csa,
              "training_chi2":loss,"optimizer_success":success,"800MHz":test,
              "all_three_800MHz_2SE":all(abs(test[x]["z"])<=2 for x in OBS),
              "total_test_z2":sum(test[x]["z_squared"] for x in OBS)})
        output[model]={
          "global_tau_perp_ns_selected_on_training_only":tau,
          "global_Rex_s_inv_selected_on_training_only":rex,
          "hydrodynamic_ratio_independent_of_NMR":ratio,
          "training_sum_chi2":train_loss,
          "n_residues":len(per),
          "n_optimizer_failure":sum(not v["optimizer_success"] for v in per),
          "median_800MHz_all_channels_z2":float(statistics.median(v["total_test_z2"] for v in per)),
          "within_two_SE_all_three":sum(v["all_three_800MHz_2SE"] for v in per),
          "n_CSA_upper_bound":sum(v["training_fit_CSA_ppm"]>=-120.0001 for v in per) if var_csa else None,
          "per_channel_median_abs_z":{ob:float(statistics.median(abs(v["800MHz"][ob]["z"]) for v in per))
                                      for ob in OBS},
          "per_residue":per
        }
        print("RPY",temperature_id,model,"TAU",tau,"REX",rex,
              "RATIO",round(ratio,5),"MEDIANZ2",output[model]["median_800MHz_all_channels_z2"],file=sys.stderr)
    return output

def nh_perturbation_envelopes(rows,nh,hydro,selected):
    """Forward-only angle sensitivities; do NOT pick perturbation by 800 errors."""
    axis=np.array(hydro["fast_axis_xyz"])
    data={}
    for row in rows:
        pos=row["pos"]
        if pos not in nh:continue
        vec=nh[pos]
        anchor=np.array([1.,0.,0.]) if abs(vec[0])<.85 else np.array([0.,1.,0.])
        basis1=normalized(np.cross(vec,anchor))
        basis2=normalized(np.cross(vec,basis1))
        fitted=selected["per_residue"][next(i for i,x in enumerate(selected["per_residue"]) if x["index"]==pos)]
        tau=selected["global_tau_perp_ns_selected_on_training_only"]
        rex=selected["global_Rex_s_inv_selected_on_training_only"]
        variants=[]
        for deg in (0,5,10):
            for phase in ((0,) if deg==0 else (0,90,180,270)):
                angle=math.radians(deg)
                az=math.radians(phase)
                pert=normalized(math.cos(angle)*vec + math.sin(angle)*
                     (math.cos(az)*basis1+math.sin(az)*basis2))
                theta=math.degrees(math.acos(float(np.clip(abs(np.dot(pert,axis)),0,1))))
                pred,_=rates(800,tm_ns=tau,s2=fitted["training_fit_S2"],
                             csa_ppm=fitted["training_fit_CSA_ppm"],
                             te_ns=.1,axial_ratio=selected["hydrodynamic_ratio_independent_of_NMR"],
                             angle_deg=theta,rex=rex)
                variants.append({"NH_deviation_deg":deg,"azimuth_deg":phase,
                                 "NH_to_RPY_axis_deg":theta,
                                 "R1_s_inv":float(pred[0]),"R2_s_inv":float(pred[1]),
                                 "heteronuclear_NOE":float(pred[2])})
        data[str(pos)]={
          "forward_without_800_refitting":True,
          "NH_scenarios":variants,
          "R1_range":[min(v["R1_s_inv"] for v in variants),max(v["R1_s_inv"] for v in variants)],
          "R2_range":[min(v["R2_s_inv"] for v in variants),max(v["R2_s_inv"] for v in variants)],
          "NOE_range":[min(v["heteronuclear_NOE"] for v in variants),
                       max(v["heteronuclear_NOE"] for v in variants)]}
    return data

def evaluate():
    protocol=json.loads(PROTO.read_text(encoding="utf8"))
    if protocol["schema_id"]!="janus.rowan.azurin6243_rpy_pdb_hydrodynamics_csa_rex_NH_uncertainty.v1":
        raise Hold("RPY_PROTOCOL_IDENTITY_FAILED")
    origin=protocol["prior_sources"]
    cif=load_raw("https://files.rcsb.org/download/1E5Y.cif",
                 origin["PDB1E5Y_SHA256"],471185)
    star=load_raw("https://bmrb.io/ftp/pub/bmrb/entry_directories/bmr6243/bmr6243_3.str",
                  origin["BMRB6243_SHA256"],323833)
    seq,data,conditions=parse_nmr(star.decode("utf-8"))
    ca,nh,omitted=load_structure(cif,seq)
    hydro_list=[rpy_rotational_tensor(ca,a) for a in RADIUS_GRID]
    hydro=hydro_list[1]
    angles=theta_for_vectors(nh,hydro)
    results={str(temp):fit_series(temp,data[temp],angles,hydro) for temp in (1,2)}
    NH_noise={str(temp):nh_perturbation_envelopes(data[temp],nh,hydro,
         results[str(temp)]["RPY_CSA_VAR_REX0"]) for temp in (1,2)}
    return {
      "schema_id":"janus.rowan.azurin6243_structure_only_RPY_diffusion_CSA_Rex_NH_noise_actual.v1",
      "date_utc":"2026-10-26",
      "status":"RETROSPECTIVE_INDEPENDENT_STRUCTURE_RPY_TENSOR_AND_TRAIN_ONLY_CSA_REX_NH_SENSITIVITY_COMPUTED",
      "source_PDB_sha256":origin["PDB1E5Y_SHA256"],
      "source_BMRB_sha256":origin["BMRB6243_SHA256"],
      "hydrodynamic_structure_only_bead_radius_sensitivity":hydro_list,
      "PDB_NH_ideal_vectors_count":len(nh),
      "PDB_NH_skipped":omitted,
      "experimental_source_conditions":conditions,
      "trained_only_500_600_and_800_evaluated":results,
      "NH_direction_envelopes_forward_only":NH_noise,
      "epistemic":{
       "RPY_Calpha_spheres_not_gold_standard_HYDRONMR":True,
       "RPY_not_exp_measured_rotational_tensor":True,
       "no_800_used_to_choose_parameter_or_hydrodynamic_radius":True,
       "800mhz_prior_already_revealed_this_is_retrospective":True,
       "CSA_bounds_and_Rex_global_grid_not_physical_detections":True,
       "NH_angles_ideal_geometry_and_perturbations_not_proton_observations":True,
       "no_FNII_ensemble_inference":True,"zero_rowan_new_jobs":True,
       "zero_rowan_credit_spent":True,"no_training_weights_promoted":True
      }
    }

def main():
    try:
        out=evaluate()
        path=os.environ.get("JANUS_RPY_ACTUAL_RECEIPT")
        if not path:raise Hold("MISSING_IMMUTABLE_JSON_OUTPUT_PATH")
        p=Path(path)
        if p.exists():raise Hold("IMMUTABLE_RECEIPT_ALREADY_EXISTS")
        p.write_text(json.dumps(out,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf8")
        print("RPY_STRUCTURE_ONLY=PASS_BEAD_RADII_"+str(len(RADIUS_GRID)))
        for cond,models in out["trained_only_500_600_and_800_evaluated"].items():
            for name,m in models.items():
                print("AZURIN_6243_RPY",cond,name,"RATIO",m["hydrodynamic_ratio_independent_of_NMR"],
                   "REX",m["global_Rex_s_inv_selected_on_training_only"],
                   "N",m["n_residues"],"800_MEDIAN_Z2",m["median_800MHz_all_channels_z2"],
                   "ALL_2SE",m["within_two_SE_all_three"])
        return 0
    except Hold as e:
        print("JANUS_RPY=HOLD_"+str(e),file=sys.stderr)
        return 2
if __name__=="__main__":raise SystemExit(main())
