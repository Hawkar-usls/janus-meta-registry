#!/usr/bin/env python3
"""JANUS 6243 azurin, actual 1E5Y heavy-atom N-H direction geometry, zero Rowan jobs.

Public NMR-STAR source with 2 temperature series; 500/600 training, 800 held out.
Global tau and global axial ratio are SHARED among each protein sample's residues.
PDB principal shape axis is a geometric surrogate, NOT a measured diffusion axis.
Hydrogens absent in diffraction; amide N-H bond direction is inferred ideally.
"""
from __future__ import annotations
from collections import defaultdict
import hashlib, json, math, os, statistics, sys, urllib.request
from pathlib import Path
import numpy as np
import pynmrstar
from Bio.PDB import MMCIFParser
from Bio.SeqUtils import seq1
from scipy.optimize import least_squares
from fn1_external_relax_bmrb_axial_csa_gate import rates

ROOT=Path(__file__).resolve().parents[2]
PROTO=ROOT/"data/rowan/protocols/ROWAN-NMR-AZURIN6243-PDB1E5Y-PRE_FIT-500600-TO-800-2026-10-26-v1.json"
MODEL_NAMES=("AZ_M0_ISO_FIXED_CSA","AZ_M1_ISO_VARIABLE_CSA",
             "AZ_M2_STRUCTURAL_AXIAL_FIXED_CSA","AZ_M3_STRUCTURAL_AXIAL_VARIABLE_CSA")
TAGS={"heteronucl_T1_relaxation":"R1","heteronucl_T2_relaxation":"R2","heteronucl_NOEs":"NOE"}
FIELDS=(500,600,800)
class Hold(Exception):pass

def load_raw(url,sha,size):
    req=urllib.request.Request(url,headers={"User-Agent":"JANUS-6243-geometry-read-only/1.0"})
    with urllib.request.urlopen(req,timeout=40) as u: content=u.read(size+1000)
    if len(content)!=size or hashlib.sha256(content).hexdigest()!=sha:
        raise Hold("EXPERIMENTAL_SOURCE_BYTES_OR_SHA_CHANGED")
    return content

def normalized(vec):
    a=np.asarray(vec,dtype=float)
    n=np.linalg.norm(a)
    if n<1e-6 or not math.isfinite(n):raise Hold("DEGENERATE_VECTOR")
    return a/n

def structural_theta(pdb_bytes, expected_sequence):
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".cif") as tmp:
        tmp.write(pdb_bytes);tmp.flush()
        structure=MMCIFParser(QUIET=True).get_structure("azurin",tmp.name)
    chain=structure[0]["A"]
    residues={r.id[1]:r for r in chain if r.id[0]==" "}
    if set(residues)!=set(range(1,129)):raise Hold("PDB_A_EXACT_128_RESIDUE_MAP_FAILED")
    actual="".join(seq1(residues[i].resname) for i in range(1,129))
    if actual!=expected_sequence:raise Hold("PDB_6243_SEQUENCE_IDENTITY_FAILED")
    ca=np.array([residues[i]["CA"].coord for i in range(1,129)])
    eigval,eigvec=np.linalg.eigh(np.cov(ca.T))
    if eigval[-1]<1.05*eigval[-2]:raise Hold("PDB_PCA_LONG_AXIS_DEGENERATE")
    axis=normalized(eigvec[:,-1])
    polar={}
    omitted={}
    for i in range(1,129):
        r=residues[i]
        if i==1 or r.resname=="PRO":
            omitted[i]="N_TERM_OR_PROLINE_NO_AMIDE_H";continue
        prev=residues[i-1]
        if not all(atom in r for atom in ("N","CA")) or "C" not in prev:
            omitted[i]="MISSING_N_CA_OR_PREV_C";continue
        ni=r["N"].coord
        ci=prev["C"].coord
        if np.linalg.norm(ci-ni)>1.9:
            omitted[i]="PRECEDING_PEPTIDE_BOND_GEOMETRY_BROKEN";continue
        # Estimate amide H as external bisector of heavy-atom CA-N-Cprev angle.
        nh=normalized(-normalized(ci-ni)-normalized(r["CA"].coord-ni))
        theta=math.degrees(math.acos(float(np.clip(abs(np.dot(nh,axis)),0,1))))
        polar[i]=theta
    if len(polar)<100:raise Hold("INSUFFICIENT_PHYSICAL_NH_HEAVY_GEOMETRY")
    return polar,omitted,{
      "experimental_PDB":"1E5Y","chain":"A","mapped_amide_NH_angles":len(polar),
      "PCA_CA_eigenvalues_A_squared":[float(v) for v in eigval],
      "axis_xyz":[float(v) for v in axis],
      "hydrogen_positions_directly_observed":False,
      "diffusion_axis_independently_measured":False
    }

def parse_nmr(text):
    entry=pynmrstar.Entry.from_string(text)
    if str(entry.entry_id)!="6243":raise Hold("BMRB_WRONG_ENTRY")
    ent=[x for x in entry.frame_list if x.category=="entity" and x.name=="azurin"]
    if len(ent)!=1:raise Hold("NMR_128_RESIDUE_ENTITY_MISSING")
    seq="".join(dict(ent[0].tags)["Polymer_seq_one_letter_code"].split())
    if len(seq)!=128:raise Hold("BMRB_ENTITY_SEQUENCE_LEN_WRONG")
    conditions={}
    for frame in entry.frame_list:
        if frame.category!="sample_conditions":continue
        cid={"condition_one":1,"condition_two":2}.get(frame.name)
        if cid is None:continue
        loop=frame.get_loop_by_category("_Sample_condition_variable")
        tags=loop.tags
        tcol=tags.index("Type");vcol=tags.index("Val")
        vals={row[tcol]:float(row[vcol]) for row in loop.data}
        conditions[cid]=vals
    if conditions.get(1,{}).get("temperature")!=289 or conditions.get(2,{}).get("temperature")!=317:
        raise Hold("NMR_SOURCE_TEMPERATURE_CONDITIONS_CHANGED")
    if conditions[1]["pH"]!=5.5 or conditions[2]["pH"]!=5.5:
        raise Hold("NMR_SOURCE_PH_CHANGED")
    datasets={}
    for frame in entry.frame_list:
        if frame.category not in TAGS:continue
        ob=TAGS[frame.category];md=dict(frame.tags)
        freq=int(float(md["Spectrometer_frequency_1H"]))
        if freq not in FIELDS:continue
        cond=int(md["Sample_condition_list_ID"])
        if cond not in (1,2):raise Hold("SOURCE_CONDITION_UNRECOGNIZED")
        if ob in ("R1","R2") and md.get("T1_val_units" if ob=="R1" else "T2_val_units")!="s":
            raise Hold("AZURIN_RELAXATION_UNIT_MUST_BE_SECONDS")
        l=frame.get_loop_by_category({"R1":"_T1","R2":"_T2","NOE":"_Heteronucl_NOE"}[ob])
        seq_id="Seq_ID_1" if ob=="NOE" else "Seq_ID"
        comp="Comp_ID_1" if ob=="NOE" else "Comp_ID"
        val="T2_val" if ob=="R2" else "Val"
        err="T2_val_err" if ob=="R2" else "Val_err"
        ix=[l.tags.index(x) for x in (seq_id,comp,val,err)]
        values={}
        for row in l.data:
            try: index=int(row[ix[0]]);raw=float(row[ix[2]]);sd=float(row[ix[3]])
            except (ValueError,TypeError):continue
            if index<1 or index>128 or not math.isfinite(raw) or not math.isfinite(sd) or sd<=0:
                raise Hold("SOURCE_NONFINITE_OR_MISSING_UNCERTAINTY")
            if ob in ("R1","R2") and raw<=0:raise Hold("SOURCE_T_RELAX_NONPOSITIVE")
            if index in values:raise Hold("BMRB_DUPLICATE_POSITION")
            # R1 or R2 rate in inverse seconds; NOE dimensionless.
            x=1/raw if ob in ("R1","R2") else raw
            err_y=sd/raw**2 if ob in ("R1","R2") else sd
            values[index]=(row[ix[1]],x,err_y,raw,sd)
        key=(cond,freq,ob)
        if key in datasets:raise Hold("DUPLICATE_FIELD_AND_SERIES")
        datasets[key]=values
    required={(c,f,ob) for c in (1,2) for f in FIELDS for ob in ("R1","R2","NOE")}
    if set(datasets)!=required:raise Hold("ALL_18_EXPERIMENTAL_SERIES_NOT_FOUND")
    series={}
    for cond,count in ((1,116),(2,114)):
        keys=[(cond,f,ob) for f in FIELDS for ob in ("R1","R2","NOE")]
        shared=set.intersection(*(set(datasets[k]) for k in keys))
        if len(shared)!=count:raise Hold("NMR_COMPLETE_NINEFOLD_INTERSECTION_CHANGED")
        res=[]
        for pos in sorted(shared):
            aa3={datasets[k][pos][0] for k in keys}
            if len(aa3)!=1 or seq1(next(iter(aa3)))!=seq[pos-1]:
                raise Hold("PDB_NMR_RESIDUE_IDENTITY_DRIFT")
            datum={}
            for f in FIELDS:
                datum[str(f)]={}
                for ob in ("R1","R2","NOE"):
                    a,b,sd,original,original_sd=datasets[(cond,f,ob)][pos]
                    datum[str(f)][ob]={"value":b,"SE":sd,"source_original":original,"source_SE":original_sd}
            res.append({"pos":pos,"aa3":next(iter(aa3)),"data":datum})
        series[cond]=res
    return seq,series,conditions

def fit_local(row,tau,ratio,theta,variable_CSA):
    train=[(f,ob,row["data"][str(f)][ob]) for f in (500,600) for ob in ("R1","R2","NOE")]
    def resid(x):
        ss=float(x[0]);csa=float(x[1]) if variable_CSA else -170.
        values={f:rates(f,tm_ns=tau,s2=ss,te_ns=.1,csa_ppm=csa,
                        axial_ratio=ratio,angle_deg=theta)[0] for f in (500,600)}
        return np.array([(values[f][("R1","R2","NOE").index(ob)]-dat["value"])/dat["SE"]
                          for f,ob,dat in train])
    lo=[.05,-220.] if variable_CSA else [.05]
    hi=[1.,-120.] if variable_CSA else [1.]
    best=None
    for start in (.45,.75,.95):
        x0=[start,-170.] if variable_CSA else [start]
        sol=least_squares(resid,x0,bounds=(lo,hi),max_nfev=75,ftol=1e-8)
        loss=float(sol.fun@sol.fun)
        if not math.isfinite(loss):raise Hold("OPTIMIZER_LOSS_NOT_FINITE")
        if best is None or loss<best[0]:
            best=(loss,sol.x,sol.success)
    return best

def calculate(series,polar,condition_id,proto):
    # Enforce common residue set across model variants. NH vectors are constructed
    # from actual crystallographic heavy atoms; PDB missing residues rejected.
    residues=[dict(row,theta_NH_deg=polar[row["pos"]]) for row in series
              if row["pos"] in polar]
    without_geometry=[row["pos"] for row in series if row["pos"] not in polar]
    if len(residues)<98:raise Hold("LACK_OF_SOURCE_ALIGNED_NH_DIRECTIONS")
    grid=proto["models"]
    output={}
    for model in ("AZ_M0_ISO_FIXED_CSA","AZ_M1_ISO_VARIABLE_CSA",
                  "AZ_M2_STRUCTURAL_AXIAL_FIXED_CSA","AZ_M3_STRUCTURAL_AXIAL_VARIABLE_CSA"):
        axial="STRUCTURAL_AXIAL" in model
        varying="VARIABLE_CSA" in model
        candidates=[]
        for tau in grid["global_tau_grid_ns"]:
            for ratio in (grid["global_axial_ratio_grid"] if axial else [1]):
                fits=[]
                for row in residues:
                    theta=row["theta_NH_deg"] if axial else 0.
                    loss,pars,success=fit_local(row,tau,ratio,theta,varying)
                    fits.append((loss,pars,success))
                total=sum(r[0] for r in fits)
                candidates.append((total,tau,ratio,fits))
        total,tau,ratio,fits=min(candidates,key=lambda c:c[0])
        rows=[]
        for row,(loss,x,success) in zip(residues,fits):
            s2=float(x[0]);csa=float(x[1]) if varying else -170.
            predicted=rates(800,tm_ns=tau,s2=s2,te_ns=.1,csa_ppm=csa,
                            axial_ratio=ratio,
                            angle_deg=row["theta_NH_deg"] if axial else 0.)[0]
            hold={}
            for k,ob in enumerate(("R1","R2","NOE")):
                source=row["data"]["800"][ob]
                z=(predicted[k]-source["value"])/source["SE"]
                hold[ob]={"predict":float(predicted[k]),"observed":source["value"],
                          "reported_SE":source["SE"],"z":float(z),
                          "chi2":float(z*z),"inside_2SE":bool(abs(z)<=2)}
            rows.append({"pos":row["pos"],"theta_NH_deg":row["theta_NH_deg"],
                         "S2":s2,"CSA_ppm":csa,"optimizer_success":bool(success),
                         "train_chi2":loss,"holdout":hold,
                         "holdout_chi2_all":sum(hold[x]["chi2"] for x in ("R1","R2","NOE")),
                         "holdout_all_3_2SE":all(x["inside_2SE"] for x in hold.values())})
        output[model]={
            "training_selection_shared_global_tau_ns":tau,
            "training_selection_shared_axial_ratio":ratio,
            "training_total_chi2":total,
            "n_NH_residues":len(rows),
            "n_not_converged":sum(not r["optimizer_success"] for r in rows),
            "n_CSA_at_-120_bound":sum(r["CSA_ppm"]>=-120.0001 for r in rows) if varying else None,
            "n_CSA_at_-220_bound":sum(r["CSA_ppm"]<=-219.9999 for r in rows) if varying else None,
            "n_all_3_holdout_2SE":sum(r["holdout_all_3_2SE"] for r in rows),
            "median_800MHz_total_chi2":float(statistics.median(r["holdout_chi2_all"] for r in rows)),
            "per_observable_median_abs_z":{
                o:float(statistics.median(abs(r["holdout"][o]["z"]) for r in rows))
                for o in ("R1","R2","NOE")},
            "each_residue":rows
        }
        print("AZURIN",condition_id,model,"global_tau",tau,"ratio",ratio,
              "median_holdout_chi2",output[model]["median_800MHz_total_chi2"],file=sys.stderr)
    base={r["pos"]:r for r in output["AZ_M0_ISO_FIXED_CSA"]["each_residue"]}
    for m in output:
        if m=="AZ_M0_ISO_FIXED_CSA":continue
        output[m]["n_better_than_M0_on_holdout"]=sum(
          row["holdout_chi2_all"]<base[row["pos"]]["holdout_chi2_all"]
          for row in output[m]["each_residue"])
    return {"temperature_condition":condition_id,"n_full_nmr_before_geometry":len(series),
            "n_skipped_NH":len(without_geometry),"skipped_NH_residues":without_geometry,
            "per_model":output}

def main():
    try:
        p=json.loads(PROTO.read_text(encoding="utf8"))
        if p["schema_id"]!="janus.rowan.azurin_BMRB6243_1E5Y_structure_holdout.v1":
            raise Hold("PRE_FIT_PROTOCOL_NOT_FROZEN")
        orig=load_raw(p["source"]["nmr_url"],p["source"]["nmr_sha256"],323833)
        cif=load_raw(p["source"]["pdb_url"],p["source"]["pdb_sha256"],471185)
        sequence,series,conditions=parse_nmr(orig.decode("utf8"))
        directions,excluded,geometry=structural_theta(cif,sequence)
        calculated={}
        for cid in (1,2):calculated[str(cid)]=calculate(series[cid],directions,cid,p)
        result={
          "schema_id":"janus.rowan.nmr_azurin6243_PDB1E5Y_2temperatures_3field_real_structural_angle_heldout.v1",
          "source_protocol":str(PROTO.relative_to(ROOT)),
          "source_NMR_SHA256":p["source"]["nmr_sha256"],
          "source_PDB_SHA256":p["source"]["pdb_sha256"],
          "source_series_conditions":conditions,
          "structure_geometry":geometry,
          "geometry_exclusions":excluded,
          "train_fields_MHz":[500,600],"test_field_MHz":800,
          "results":calculated,
          "scientific_scope":{
            "other_protein_azurin_not_FNII":True,
            "estimated_amide_protons_not_Xray_measured":True,
            "global_axis_CA_shape_not_measured_diffusion_tensor_axis":True,
            "two_temperatures_fit_separately":True,
            "all_800MHz_scores_computed_only_after_500600_fit":True,
            "no_prospective_blind":True,
            "no_rowan_jobs":0,"no_rowan_credits":0,
            "no_FNII_angular_ensemble_inference":True,
            "no_weight_promotion":True
          }
        }
        path=os.environ.get("JANUS_AZURIN_REAL_RECEIPT")
        if not path:raise Hold("NO_RECEIPT_PATH")
        out=Path(path)
        if out.exists():raise Hold("IMMUTABLE_RECEIPT_PATH_ALREADY_EXISTS")
        out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf8")
        print("AZURIN_6243=SOURCE_LOCKED_3FIELD_STRUCTURE_AWARE_HELDOUT_COMPLETED")
        return 0
    except Hold as err:
        print("AZURIN_6243_HOLD="+str(err),file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())
