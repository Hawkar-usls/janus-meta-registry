#!/usr/bin/env python3
"""JPFM-2F-C2B0: label-blind decomposition of C2A local-reference support failure."""
from __future__ import annotations
import argparse, gzip, hashlib, io, json, math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from astropy.coordinates import SkyCoord
import astropy.units as u
import statsmodels.api as sm

EXPECTED_ROWS = 512
C2A_CANON = "ef0d238fa28380130fa9b540517c322a83c10e96c811379205eb6ac1c54ae510"
C2A_CSV_SHA = "032fccc7637b58ebfa5a63383765cc6a89b934503298855fe5f0880bf23467aa"
C2A_GZ_SHA = "624f316b5104064d742407162f603a552487e5e193603f65b4b0e6d86e9cda73"
C0M_CANON = "2bc8ee104cb05d588a264a7f25d3d3713907f689da9aafb7c72f726627bdf5ba"
C0M_CSV_SHA = "d41bfc95e9f0219d76ee383d057938287dcaaef8ba5005c66414d4a2422f75c0"
C0M_GZ_SHA = "8493e1dc6b3d89ecd1984d0826b663f2a12ede9664a3c5bb4812b51b6d3a0eca"
ADMISSION_CANON = "ccb70d6d01f411f4b666153dc3147db529be67f1c9d9cf0e5d63148840ace2e5"
REF_MIN = 20

GROUPS = {
    "sky_environment": [
        "abs_galactic_latitude_deg",
        "log1p_plate_s0_candidate_count",
        "log1p_tile_s0_candidate_count",
        "log1p_plate_s0_candidates_per_active_tile",
        "log1p_shape_stars_used",
    ],
    "target_brightness_detection": ["pass2_mag_auto", "log1p_pass2_snr_win"],
    "tile_plate_geometry": ["log1p_distance_to_tile_edge_px", "plate_radius_norm"],
    "wcs_context": [
        "tan_refit_median_arcsec", "tan_refit_max_arcsec",
        "crpix_offset_norm_px", "local_pixel_scale_arcsec",
    ],
    "frozen_sampling_context": ["structural_cluster", "sample_role"],
}

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def canonical_sha(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())

def load_gz_csv(path: Path, gz_sha: str, csv_sha: str) -> pd.DataFrame:
    gz = path.read_bytes()
    if sha256_bytes(gz) != gz_sha:
        raise RuntimeError(f"{path.name}: gzip hash mismatch")
    raw = gzip.decompress(gz)
    if sha256_bytes(raw) != csv_sha:
        raise RuntimeError(f"{path.name}: csv hash mismatch")
    return pd.read_csv(io.BytesIO(raw))

def verify_json(path: Path, expected_canon: str, status_key=None, status_value=None):
    d = json.loads(path.read_text(encoding="utf-8"))
    payload = dict(d)
    integ = payload.pop("integrity", None)
    if not integ or canonical_sha(payload) != integ.get("canonical_payload_sha256_without_integrity"):
        raise RuntimeError(f"{path.name}: self canonical hash invalid")
    if integ["canonical_payload_sha256_without_integrity"] != expected_canon:
        raise RuntimeError(f"{path.name}: canonical binding mismatch")
    if status_key and d.get(status_key) != status_value:
        raise RuntimeError(f"{path.name}: status/outcome mismatch")
    return d

def qstats(x):
    a = pd.to_numeric(pd.Series(x), errors="coerce").to_numpy(float)
    a = a[np.isfinite(a)]
    if not len(a):
        return {"n_finite": 0}
    return {
        "n_finite": int(len(a)), "min": float(a.min()),
        "p05": float(np.quantile(a, .05)), "p25": float(np.quantile(a, .25)),
        "median": float(np.median(a)), "p75": float(np.quantile(a, .75)),
        "p95": float(np.quantile(a, .95)), "max": float(a.max()),
    }

def robust_z_with_missing(s: pd.Series):
    a = pd.to_numeric(s, errors="coerce").astype(float)
    finite = np.isfinite(a.to_numpy())
    vals = a.to_numpy()[finite]
    med = float(np.median(vals)) if len(vals) else 0.0
    mad = float(np.median(np.abs(vals-med))) if len(vals) else 0.0
    scale = 1.4826*mad
    if not math.isfinite(scale) or scale <= 0:
        scale = float(np.std(vals)) if len(vals)>1 else 1.0
    if not math.isfinite(scale) or scale <= 0:
        scale = 1.0
    filled = a.fillna(med).to_numpy(float)
    z = (filled-med)/scale
    miss = (~finite).astype(float)
    return z, miss, {"median": med, "robust_scale": scale, "missing_n": int(miss.sum())}

def spearman_record(x, y):
    xx = pd.to_numeric(pd.Series(x), errors="coerce").to_numpy(float)
    yy = pd.to_numeric(pd.Series(y), errors="coerce").to_numpy(float)
    m = np.isfinite(xx) & np.isfinite(yy)
    if int(m.sum()) < 4 or len(np.unique(xx[m])) < 2 or len(np.unique(yy[m])) < 2:
        return {"n": int(m.sum()), "rho": None, "p_two_sided": None}
    r = spearmanr(xx[m], yy[m])
    return {"n": int(m.sum()), "rho": float(r.statistic), "p_two_sided": float(r.pvalue)}

def quartile_census(df, col):
    x = pd.to_numeric(df[col], errors="coerce")
    m = x.notna()
    if int(m.sum()) < 8 or x[m].nunique() < 4:
        return {"status": "INSUFFICIENT_VARIATION"}
    try:
        q = pd.qcut(x[m], 4, duplicates="drop")
    except Exception:
        return {"status": "QCUT_FAILED"}
    z = df.loc[m, ["reference_eligible20"]].copy()
    z["bin"] = q.astype(str)
    out=[]
    for b,g in z.groupby("bin", sort=False, observed=True):
        out.append({"bin": str(b), "n": int(len(g)), "eligible_n": int(g.reference_eligible20.sum()), "eligible_fraction": float(g.reference_eligible20.mean())})
    return {"status":"OK","bins":out}

def fit_logit(df, selected_groups):
    group_cols = {}
    meta = {}
    Xparts = {}
    for g in selected_groups:
        if g == "frozen_sampling_context":
            continue
        group_cols[g] = []
        for c in GROUPS[g]:
            z, miss, zm = robust_z_with_missing(df[c])
            zn = f"z__{c}"
            Xparts[zn] = z
            group_cols[g].append(zn)
            meta[c] = zm
            if miss.sum() > 0:
                mn = f"missing__{c}"
                Xparts[mn] = miss
                group_cols[g].append(mn)
    if "frozen_sampling_context" in selected_groups:
        cl = pd.to_numeric(df.structural_cluster, errors="raise").astype(int)
        for k in range(1,16):
            n=f"cluster_{k}"
            Xparts[n]=(cl.to_numpy()==k).astype(float)
        Xparts["sample_role_unusual"]=(df.sample_role.astype(str).to_numpy()=="unusual").astype(float)
        group_cols["frozen_sampling_context"]=[f"cluster_{k}" for k in range(1,16)]+["sample_role_unusual"]
    X = pd.DataFrame(Xparts, index=df.index)
    X = sm.add_constant(X, has_constant="add")
    y = df.reference_eligible20.astype(int).to_numpy()
    try:
        fit = sm.GLM(y, X, family=sm.families.Binomial()).fit(maxiter=250, disp=0)
        return {
            "ok": True, "deviance": float(fit.deviance), "null_deviance": float(fit.null_deviance),
            "aic": float(fit.aic), "converged": bool(getattr(fit, "converged", True)),
            "n_params": int(len(fit.params)), "params": {k: float(v) for k,v in fit.params.items()},
            "pvalues": {k: float(v) for k,v in fit.pvalues.items()},
            "design_meta": meta, "group_design_columns": group_cols,
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}:{e}"[:500], "group_design_columns": group_cols, "design_meta": meta}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--admission",required=True,type=Path)
    ap.add_argument("--c2a-result",required=True,type=Path)
    ap.add_argument("--c2a-sidecar",required=True,type=Path)
    ap.add_argument("--c0m-result",required=True,type=Path)
    ap.add_argument("--c0m-map",required=True,type=Path)
    ap.add_argument("--out-json",required=True,type=Path)
    ap.add_argument("--out-sidecar-gz",required=True,type=Path)
    args=ap.parse_args(); args.out_json.parent.mkdir(parents=True,exist_ok=True)

    print("[C2B0] [1/8] bind preregistration and negative parent", flush=True)
    adm=verify_json(args.admission, ADMISSION_CANON, "status", "PREREGISTERED_AFTER_C2A_NEGATIVE_CERTIFICATE_BEFORE_C2B0_DECOMPOSITION_OUTCOME")
    verify_json(args.c2a_result, C2A_CANON, "measurement_outcome", "FAIL_CLOSED_LOCAL_REFERENCE_NORMALIZATION")
    verify_json(args.c0m_result, C0M_CANON, "outcome", "PASS_FULL_S0_HEADER_ONLY_ACQUISITION_MAP_FROZEN")
    if adm["frozen_reference_contract"]["minimum_reference_stars"] != 20:
        raise RuntimeError("reference minimum changed")
    if adm["external_label_firewall"]["external_label_reveal_authorized"] is not False:
        raise RuntimeError("external-label firewall open")

    print("[C2B0] [2/8] hash-gate C2A 512 sidecar and full-S0 C0M map", flush=True)
    c=load_gz_csv(args.c2a_sidecar,C2A_GZ_SHA,C2A_CSV_SHA); c["src_id"]=c.src_id.astype(str)
    m=load_gz_csv(args.c0m_map,C0M_GZ_SHA,C0M_CSV_SHA); m["src_id"]=m.src_id.astype(str)
    if len(c)!=512 or c.src_id.nunique()!=512:
        raise RuntimeError("C2A sidecar invariant failed")
    if len(m)!=122820 or m.src_id.nunique()!=122820:
        raise RuntimeError("C0M map invariant failed")
    if set(c.src_id)-set(m.src_id):
        raise RuntimeError("C2A sources missing from C0M")

    print("[C2B0] [3/8] derive only predeclared technical/astronomical support covariates", flush=True)
    plate_count=m.groupby("plate_id").size().astype(int)
    tile_count=m.groupby("tile_id").size().astype(int)
    plate_tiles=m.groupby("plate_id").tile_id.nunique().astype(int)
    keep=["src_id","ra","dec","plate_id","tile_id","fullplate_x0","fullplate_y0",
          "distance_to_tile_edge_px","tan_refit_median_arcsec","tan_refit_max_arcsec",
          "crpix_dx","crpix_dy","local_pixel_scale_arcsec"]
    d=c.merge(m[keep],on="src_id",how="left",validate="one_to_one",suffixes=("","_c0m"))
    for col in ("plate_id","tile_id"):
        cc=f"{col}_c0m"
        if cc in d and not (d[col].astype(str)==d[cc].astype(str)).all():
            raise RuntimeError(f"{col} identity drift")
    d["plate_s0_candidate_count"]=d.plate_id.astype(str).map(plate_count).astype(float)
    d["tile_s0_candidate_count"]=d.tile_id.astype(str).map(tile_count).astype(float)
    d["plate_active_tile_count"]=d.plate_id.astype(str).map(plate_tiles).astype(float)
    d["plate_s0_candidates_per_active_tile"]=d.plate_s0_candidate_count/d.plate_active_tile_count
    sky=SkyCoord(pd.to_numeric(d.s0_ra,errors="coerce").to_numpy(float)*u.deg,
                 pd.to_numeric(d.s0_dec,errors="coerce").to_numpy(float)*u.deg, frame="icrs")
    d["abs_galactic_latitude_deg"]=np.abs(sky.galactic.b.deg)
    d["shape_stars_used"]=pd.to_numeric(d.get("stars_used"),errors="coerce")
    d["pass2_mag_auto"]=pd.to_numeric(d.get("pass2_mag_auto"),errors="coerce")
    d["pass2_snr_win"]=pd.to_numeric(d.get("pass2_snr_win"),errors="coerce")
    d["log1p_pass2_snr_win"]=np.log1p(np.clip(d.pass2_snr_win,0,None))
    d["log1p_shape_stars_used"]=np.log1p(np.clip(d.shape_stars_used,0,None))
    d["log1p_plate_s0_candidate_count"]=np.log1p(d.plate_s0_candidate_count)
    d["log1p_tile_s0_candidate_count"]=np.log1p(d.tile_s0_candidate_count)
    d["log1p_plate_s0_candidates_per_active_tile"]=np.log1p(d.plate_s0_candidates_per_active_tile)
    d["log1p_distance_to_tile_edge_px"]=np.log1p(np.clip(pd.to_numeric(d.distance_to_tile_edge_px,errors="coerce"),0,None))
    d["plate_radius_norm"]=np.hypot(pd.to_numeric(d.fullplate_x0,errors="coerce")-7000.0,
                                    pd.to_numeric(d.fullplate_y0,errors="coerce")-7000.0)/7000.0
    d["crpix_offset_norm_px"]=np.hypot(pd.to_numeric(d.crpix_dx,errors="coerce"),
                                       pd.to_numeric(d.crpix_dy,errors="coerce"))
    d["reference_count"]=pd.to_numeric(d.local_reference_star_count,errors="coerce")
    if d.reference_count.isna().any():
        raise RuntimeError("reference count missing")
    d["reference_eligible20"]=(d.reference_count>=REF_MIN).astype(int)
    if int(d.reference_eligible20.sum()) != 104:
        raise RuntimeError("C2A eligibility count drift")

    print("[C2B0] [4/8] frozen descriptive decomposition", flush=True)
    numeric=[]
    for g,cols in GROUPS.items():
        if g=="frozen_sampling_context": continue
        numeric.extend(cols)
    correlations={c:spearman_record(d[c],d.reference_count) for c in numeric}
    bins={c:quartile_census(d,c) for c in numeric}
    gal_bins=pd.cut(d.abs_galactic_latitude_deg,[-1e-9,10,20,40,90],labels=["0-10","10-20","20-40","40-90"],include_lowest=True)
    gal_census=[]
    for b,g in d.assign(gal_bin=gal_bins.astype(str)).groupby("gal_bin",sort=False):
        gal_census.append({"abs_b_bin_deg":str(b),"n":int(len(g)),"reference_count_median":float(g.reference_count.median()),
                           "eligible_n":int(g.reference_eligible20.sum()),"eligible_fraction":float(g.reference_eligible20.mean())})
    cluster=[]
    for (cl,role),g in d.groupby(["structural_cluster","sample_role"],sort=True):
        cluster.append({"cluster":int(cl),"sample_role":str(role),"n":int(len(g)),
                        "reference_count":qstats(g.reference_count),
                        "eligible_n":int(g.reference_eligible20.sum()),"eligible_fraction":float(g.reference_eligible20.mean())})

    print("[C2B0] [5/8] preregistered multivariable logistic model", flush=True)
    group_order=list(GROUPS)
    full=fit_logit(d,group_order)
    ablations={}
    if full.get("ok"):
        for g in group_order:
            red=fit_logit(d,[x for x in group_order if x!=g])
            rec={"reduced_ok":bool(red.get("ok"))}
            if red.get("ok"):
                rec.update({"full_deviance":full["deviance"],"reduced_deviance":red["deviance"],
                            "delta_deviance_removed_group":float(red["deviance"]-full["deviance"]),
                            "delta_aic_removed_group":float(red["aic"]-full["aic"])})
            else: rec["error"]=red.get("error")
            ablations[g]=rec

    print("[C2B0] [6/8] preserve diagnostic sidecar", flush=True)
    outcols=["src_id","plate_id","tile_id","structural_cluster","sample_role","reference_count","reference_eligible20"]+numeric
    side=d[outcols].sort_values(["structural_cluster","sample_role","src_id"],kind="stable")
    raw=side.to_csv(index=False,lineterminator="\n",float_format="%.12g").encode()
    csv_sha=sha256_bytes(raw)
    with args.out_sidecar_gz.open("wb") as f:
        with gzip.GzipFile(filename="",mode="wb",fileobj=f,mtime=0) as z: z.write(raw)
    gz_sha=sha256_bytes(args.out_sidecar_gz.read_bytes())

    print("[C2B0] [7/8] write result; C2A remains failed and labels remain sealed", flush=True)
    ranked=[]
    for g,r in ablations.items():
        if r.get("reduced_ok") and math.isfinite(r.get("delta_deviance_removed_group",float("nan"))):
            ranked.append((g,float(r["delta_deviance_removed_group"])))
    ranked=sorted(ranked,key=lambda x:(-x[1],x[0]))
    result={
        "artifact_id":"JANUS-PALOMAR-JPFM-2F-C2B0-REFERENCE-SUPPORT-DECOMPOSITION-RUN-001",
        "experiment_id":"JPFM-2F-C2B0","schema_version":"1.0",
        "date":pd.Timestamp.utcnow().date().isoformat(),
        "status":"EXECUTED_DIAGNOSTIC_ONLY",
        "outcome":"C2A_REFERENCE_SUPPORT_VARIATION_DECOMPOSED__C2A_REMAINS_NEGATIVE_CERTIFICATE",
        "claim_ceiling":"REFERENCE_SUPPORT_FAILURE_DIAGNOSTIC_ONLY__NO_C2A_RESCUE__NO_MORPHOLOGY_INFERENCE__NO_EXTERNAL_LABEL_REVEAL__NO_CAUSAL_OR_ORIGIN_CLAIM",
        "bindings":{
            "admission_canonical_sha256":ADMISSION_CANON,"C2A_result_canonical_sha256":C2A_CANON,
            "C2A_sidecar_csv_sha256":C2A_CSV_SHA,"C2A_sidecar_gzip_sha256":C2A_GZ_SHA,
            "C0M_result_canonical_sha256":C0M_CANON,"C0M_manifest_csv_sha256":C0M_CSV_SHA,"C0M_manifest_gzip_sha256":C0M_GZ_SHA},
        "reference_contract":{"minimum_reference_stars":20,"unchanged":True,"eligible_rows":int(d.reference_eligible20.sum()),"rows":512,
                              "eligible_fraction":float(d.reference_eligible20.mean()),"reference_count":qstats(d.reference_count)},
        "stellar_density_semantics":adm["stellar_density_semantics"],
        "galactic_latitude_fixed_bin_census":gal_census,
        "cluster_role_census":cluster,
        "spearman_reference_count_vs_covariates":correlations,
        "quartile_eligibility_census":bins,
        "multivariable_logistic":full,
        "frozen_group_ablation":ablations,
        "diagnostic_group_ranking_by_delta_deviance":[{"group":g,"delta_deviance":v} for g,v in ranked],
        "interpretation_guardrails":[
            "Group ranking is diagnostic predictive structure, not causal attribution.",
            "No C2A morphology inference is revived from the 104 complete rows.",
            "No threshold or reference filter was changed.",
            "No external temporal/human/nuclear/geomagnetic/lunar labels were joined."
        ],
        "sidecar":{"path":str(args.out_sidecar_gz),"rows":512,"csv_sha256":csv_sha,"gzip_sha256":gz_sha},
        "external_label_firewall":{"external_label_reveal_authorized":False,"date_or_external_environment_used":False},
        "next_gate":"PREREGISTER_C2B1_REFERENCE_SUPPORT_REPAIR__KEEP_MINIMUM_20__NEW_NONOVERLAPPING_HOLDOUT_REQUIRED_FOR_ANY_MORPHOLOGY_INFERENCE"
    }
    result["integrity"]={"canonical_payload_sha256_without_integrity":canonical_sha(result)}
    args.out_json.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

    print("[C2B0] [8/8] complete",flush=True)
    print("C2B0_ELIGIBLE",int(d.reference_eligible20.sum()),"/",len(d),flush=True)
    print("C2B0_GROUP_RANKING",ranked,flush=True)
    print("C2B0_RESULT_CANONICAL",result["integrity"]["canonical_payload_sha256_without_integrity"],flush=True)

if __name__=="__main__":
    main()
