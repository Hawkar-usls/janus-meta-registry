#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JANUS JPFM-3A — preregistered cross-event atlas.

Primary: frozen Blue Book STARLIKE dates -> POSS-I candidate rate conditional on
an actually observed Palomar night. Discovery: solar, geomagnetic, meteor and
lunar event families frozen in the JPFM-3A admission JSON before outcome.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import io
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from statsmodels.discrete.discrete_model import NegativeBinomial

HERE = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


base = load_module("jpfm2d", HERE / "jpfm_open_reconstruction_temporal.py")
decomp = load_module("jpfm2e", HERE / "jpfm_schedule_confound_decomposition.py")

ADMISSION = Path("data/JANUS-PALOMAR-JPFM-3A-CROSS-EVENT-ATLAS-ADMISSION-v1.0.json")
SOURCE_AUDIT = Path("data/JANUS-PALOMAR-JPFM-3A-SOURCE-COVERAGE-CORRECTIVE-AUDIT-v1.0.json")
STAR_FREEZE = Path("data/JANUS-BLUEBOOK-STARLIKE-DAY-FREEZE-v1.0.json")
START, END = base.STUDY_START, base.STUDY_END
GFZ_URL = decomp.GFZ_URL
N_PERM = 50000
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "JANUS-JPFM-3A-cross-event-atlas/1.1"})

DISCOVERY_IDS = [
    "D1_SOLAR_F107_HIGH", "D2_SUNSPOT_HIGH", "D3_GEOMAG_STORM",
    "D5_MAJOR_METEOR_SHOWER_PROXY", "D6_LUNAR_DARK", "D7_LUNAR_BRIGHT",
]

METEOR_PEAKS = [(1,3,"QUA"),(4,22,"LYR"),(5,6,"ETA"),(7,30,"SDA"),
                (8,12,"PER"),(10,21,"ORI"),(11,17,"LEO"),(12,14,"GEM")]


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(p: Path) -> str:
    return sha_bytes(p.read_bytes())


def zscore(s: pd.Series):
    x = pd.to_numeric(s, errors="coerce").astype(float)
    med = float(x.median()); x = x.fillna(med)
    mu = float(x.mean()); sd = float(x.std(ddof=0))
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(np.zeros(len(x)), index=x.index), {"mean": mu, "median": med, "sd": sd}
    return (x - mu) / sd, {"mean": mu, "median": med, "sd": sd}


def fetch_gfz_extended():
    r = SESSION.get(GFZ_URL, timeout=180); r.raise_for_status(); b = r.content
    widths = [4,3,3,6,8,5,3,7,7,7,7,7,7,7,7,5,5,5,5,5,5,5,5,6,4,9,9,2]
    names = ["year","month","day","days","days_m","bsrn","rotd",
             "Kp0","Kp3","Kp6","Kp9","Kp12","Kp15","Kp18","Kp21",
             "Ap0","Ap3","Ap6","Ap9","Ap12","Ap15","Ap18","Ap21","Apavg",
             "isn","f107_obs","f107_adj","D"]
    dtype = "i4,i4,i4,i4,f4,i4,i4,f4,f4,f4,f4,f4,f4,f4,f4,i4,i4,i4,i4,i4,i4,i4,i4,i4,i4,f8,f8,i4"
    arr = np.genfromtxt(io.StringIO(b.decode("ascii", errors="ignore")), skip_header=3,
                        delimiter=widths, dtype=dtype, names=names, autostrip=True, invalid_raise=True)
    arr = arr[arr["year"] != -1]
    d = pd.DataFrame(arr)
    d["date_obj"] = pd.to_datetime(d[["year","month","day"]]).dt.date
    d = d[(d.date_obj >= START) & (d.date_obj <= END)].copy()
    expected = (END - START).days + 1
    if len(d) != expected or d.date_obj.nunique() != expected:
        raise RuntimeError(f"GFZ coverage {len(d)} != {expected}")
    kpcols = [f"Kp{h}" for h in range(0,24,3)]
    d["max_kp"] = d[kpcols].max(axis=1).astype(float)
    d["daily_Ap"] = d.Apavg.astype(float)
    for c in ["isn","f107_obs","f107_adj"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").astype(float)
        d.loc[d[c] < 0, c] = np.nan
    if d.isn.isna().any():
        bad = d[d.isn.isna()][["date_obj","isn"]].head(10).to_dict("records")
        raise RuntimeError(f"GFZ sunspot field incomplete in study window: {bad}")
    f107_missing = int(d.f107_adj.isna().sum())
    f107_complete = f107_missing == 0
    f107_q90 = float(d.f107_adj.quantile(.90, interpolation="linear")) if f107_complete else None
    isn_q90 = float(d.isn.quantile(.90, interpolation="linear"))
    if f107_complete:
        d["D1_SOLAR_F107_HIGH"] = (d.f107_adj >= f107_q90).astype(int)
    d["D2_SUNSPOT_HIGH"] = (d.isn >= isn_q90).astype(int)
    d["D3_GEOMAG_STORM"] = (d.max_kp >= 5.0).astype(int)
    d["D4_GEOMAG_SEVERE_SENSITIVITY"] = (d.max_kp >= 7.0).astype(int)
    event_counts = {
        "D2_SUNSPOT_HIGH": int(d["D2_SUNSPOT_HIGH"].sum()),
        "D3_GEOMAG_STORM": int(d["D3_GEOMAG_STORM"].sum()),
        "D4_GEOMAG_SEVERE_SENSITIVITY": int(d["D4_GEOMAG_SEVERE_SENSITIVITY"].sum()),
    }
    if f107_complete:
        event_counts["D1_SOLAR_F107_HIGH"] = int(d["D1_SOLAR_F107_HIGH"].sum())
    return d, {
        "source_url": GFZ_URL,
        "source_sha256": sha_bytes(b),
        "rows": len(d),
        "isn_complete_days": int(d.isn.notna().sum()),
        "f107_adj_complete_days": int(d.f107_adj.notna().sum()),
        "f107_adj_missing_days": f107_missing,
        "f107_adj_complete_for_preregistered_D1": f107_complete,
        "f107_adj_q90": f107_q90,
        "isn_q90": isn_q90,
        "event_day_counts": event_counts,
        "D1_execution": "EXECUTED" if f107_complete else "NOT_EXECUTED_SOURCE_COVERAGE_INCOMPLETE",
    }


def date_range():
    d = START
    while d <= END:
        yield d
        d += dt.timedelta(days=1)


def meteor_dates(radius=2):
    out = set(); by_shower = defaultdict(list)
    for y in range(START.year, END.year + 1):
        for m, day, code in METEOR_PEAKS:
            peak = dt.date(y,m,day)
            for k in range(-radius, radius+1):
                x = peak + dt.timedelta(days=k)
                if START <= x <= END:
                    out.add(x); by_shower[code].append(x.isoformat())
    return out, dict(by_shower)


def load_star_freeze():
    j = json.loads(STAR_FREEZE.read_text(encoding="utf-8"))
    rows = [(dt.date.fromisoformat(r["date"]), int(r["count"])) for r in j["event_days"]]
    if len(rows) != 78 or sum(c for _,c in rows) != 82:
        raise RuntimeError("STARLIKE freeze invariant failed")
    return dict(rows), {"sha256": sha_file(STAR_FREEZE), "event_days": len(rows), "cases": sum(c for _,c in rows)}


def expand_dates(days: set[dt.date], radius: int):
    return {x for d in days for k in range(-radius,radius+1)
            if START <= (x := d + dt.timedelta(days=k)) <= END}


def shifted_dates(days: set[dt.date], lag: int):
    return {x for d in days if START <= (x := d + dt.timedelta(days=lag)) <= END}


def add_event_col(df, days, col):
    s = set(days)
    df[col] = [int(dt.date.fromisoformat(str(x)) in s) for x in df.date_obs]


def design(nights, event_col, include_lunar=True, include_geomag=True):
    d = nights.copy().reset_index(drop=True)
    X = pd.DataFrame({"intercept":np.ones(len(d)), "event":d[event_col].astype(float)})
    dates = pd.to_datetime(d.date_obs)
    X = pd.concat([X,
        pd.get_dummies(dates.dt.month.astype(int), prefix="month", drop_first=True, dtype=float).reset_index(drop=True),
        pd.get_dummies(dates.dt.year.astype(int), prefix="year", drop_first=True, dtype=float).reset_index(drop=True)], axis=1)
    scalers = {}
    for src,dst in [("sky_ra_sin","sky_ra_sin_z"),("sky_ra_cos","sky_ra_cos_z"),
                    ("plate_dec_deg","dec_z"),("abs_galactic_b_deg","abs_gal_b_z"),
                    ("exposure_min","exposure_z"),("wcs_offset_arcsec","wcs_z")]:
        X[dst], scalers[src] = zscore(d[src])
    if include_lunar:
        X["lunar_z"], scalers["lunar_illumination_fraction"] = zscore(d.lunar_illumination_fraction)
    if include_geomag:
        X["Ap_z"], scalers["daily_Ap"] = zscore(d.daily_Ap)
        X["Kp_z"], scalers["max_kp"] = zscore(d.max_kp)
    return X.astype(float), scalers


def fit_event_nb(nights, event_col, include_lunar=True, include_geomag=True):
    d = nights.copy().reset_index(drop=True)
    exposed = int(d[event_col].sum())
    if exposed < 3 or exposed > len(d)-3:
        return {"status":"INSUFFICIENT_EVENT_VARIATION", "exposed_nights":exposed, "n":len(d)}
    X, scalers = design(d,event_col,include_lunar,include_geomag)
    y = d.candidate_count.astype(float).to_numpy(); opp = d.tile_count.astype(float).to_numpy()
    res = NegativeBinomial(y, X.to_numpy(), offset=np.log(opp), loglike_method="nb2").fit(disp=0,maxiter=1000)
    names = list(X.columns)+["alpha"]; idx=names.index("event")
    beta=float(res.params[idx]); ci=np.asarray(res.conf_int(),float)[idx]
    a=d[d[event_col]==1]; b=d[d[event_col]==0]
    ra=float(a.candidate_count.sum()/a.tile_count.sum()); rb=float(b.candidate_count.sum()/b.tile_count.sum())
    return {"status":"OK","n":len(d),"exposed_nights":exposed,"event_beta":beta,"event_se":float(res.bse[idx]),
            "p_two_sided":float(res.pvalues[idx]),"irr":float(math.exp(beta)),
            "irr_ci95":[float(math.exp(ci[0])),float(math.exp(ci[1]))],
            "rate_exposed":ra,"rate_unexposed":rb,"crude_rate_ratio":float(ra/rb),"alpha":float(res.params[-1]),
            "aic":float(res.aic),"scalers":scalers}


def lag_profile(nights, days, lags):
    out={}
    for lag in lags:
        s=shifted_dates(set(days),lag)
        mask=np.array([dt.date.fromisoformat(x) in s for x in nights.date_obs.astype(str)])
        if mask.sum()==0 or (~mask).sum()==0:
            rr=None
        else:
            ra=float(nights.loc[mask,"candidate_count"].sum()/nights.loc[mask,"tile_count"].sum())
            rb=float(nights.loc[~mask,"candidate_count"].sum()/nights.loc[~mask,"tile_count"].sum())
            rr=float(ra/rb) if rb else None
        out[str(lag)]={"exposed_nights":int(mask.sum()),"crude_rate_ratio":rr}
    return out


def block_null(outcome_by_date: dict[dt.date,int], event_days: set[dt.date], n_perm=N_PERM, seed=19520719):
    blocks=defaultdict(list)
    for d in date_range(): blocks[(d.year,d.month)].append(d)
    event_counts=Counter((d.year,d.month) for d in event_days)
    obs=sum(outcome_by_date.get(d,0) for d in event_days)
    rng=np.random.default_rng(seed); null=np.zeros(n_perm,dtype=np.int32)
    for key,days in blocks.items():
        k=event_counts.get(key,0)
        if k<=0: continue
        vals=np.array([outcome_by_date.get(d,0) for d in days],dtype=np.int16)
        if k>=len(days): null += vals.sum(); continue
        r=rng.random((n_perm,len(days)))
        ix=np.argpartition(r,k-1,axis=1)[:,:k]
        null += vals[ix].sum(axis=1)
    upper=float((1+np.sum(null>=obs))/(n_perm+1)); lower=float((1+np.sum(null<=obs))/(n_perm+1))
    return {"observed":int(obs),"null_mean":float(null.mean()),"null_sd":float(null.std(ddof=1)),
            "p_upper_positive":upper,"p_lower_negative":lower,"p_two_sided":float(min(1,2*min(upper,lower))),
            "iterations":n_perm,"seed":seed,"event_days":len(event_days)}


def bh(pmap: dict[str,float]):
    items=sorted((p,k) for k,p in pmap.items() if p is not None and np.isfinite(p))
    m=len(items); q={}; prev=1.0
    for rank in range(m,0,-1):
        p,k=items[rank-1]; val=min(prev,p*m/rank); q[k]=float(val); prev=val
    return q


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--out",required=True,type=Path); args=ap.parse_args(); args.out.parent.mkdir(parents=True,exist_ok=True)
    admission=json.loads(ADMISSION.read_text(encoding="utf-8")); source_audit=json.loads(SOURCE_AUDIT.read_text(encoding="utf-8"))
    star_counts,star_meta=load_star_freeze(); star_days=set(star_counts)
    print("[1/7] public POSS release + FITS header reconstruction",flush=True)
    s0,tiles,repairs,wcs,release_hashes=base.read_release_tables(); plates=sorted(tiles.plate_id.dropna().astype(str).unique())
    headers=base.fetch_all_headers(plates); all_plates,_=base.build_plate_table(s0,tiles,repairs,wcs,headers)
    all_plates["date_obj"]=pd.to_datetime(all_plates.date_obs).dt.date
    p=all_plates[(all_plates.date_obj>=START)&(all_plates.date_obj<=END)].copy().drop(columns=["date_obj"])
    nights=decomp.aggregate_nights_extended(p)
    if len(nights)!=312: raise RuntimeError(f"expected 312 observed nights, got {len(nights)}")
    print("[2/7] GFZ solar + geomagnetic fields",flush=True)
    gfz,gfz_meta=fetch_gfz_extended(); gs=gfz[["date_obj","daily_Ap","max_kp","isn"]].copy(); gs["date_obs"]=gs.date_obj.astype(str)
    nights=nights.merge(gs.drop(columns=["date_obj"]),on="date_obs",how="left",validate="one_to_one")
    print("[3/7] USNO lunar control on observed nights",flush=True)
    moon,moon_meta=decomp.fetch_usno_moon(nights.date_obs.astype(str)); nights=nights.merge(moon[["date_obs","lunar_illumination_fraction"]],on="date_obs",how="left",validate="one_to_one")
    meteor,meteor_by=meteor_dates(2)
    gfz_by_date={r.date_obj:r for r in gfz.itertuples()}
    event_sets={
        "D2_SUNSPOT_HIGH":{d for d,r in gfz_by_date.items() if r.D2_SUNSPOT_HIGH},
        "D3_GEOMAG_STORM":{d for d,r in gfz_by_date.items() if r.D3_GEOMAG_STORM},
        "D4_GEOMAG_SEVERE_SENSITIVITY":{d for d,r in gfz_by_date.items() if r.D4_GEOMAG_SEVERE_SENSITIVITY},
        "D5_MAJOR_METEOR_SHOWER_PROXY":meteor,
    }
    if gfz_meta["f107_adj_complete_for_preregistered_D1"]:
        event_sets["D1_SOLAR_F107_HIGH"]={d for d,r in gfz_by_date.items() if r.D1_SOLAR_F107_HIGH}
    # Lunar binary families are observation-layer controls only in v1 because USNO was bound only on observed Palomar nights.
    nights["D6_LUNAR_DARK"]=(nights.lunar_illumination_fraction<=.10).astype(int)
    nights["D7_LUNAR_BRIGHT"]=(nights.lunar_illumination_fraction>=.90).astype(int)
    print("[4/7] primary cross-channel test",flush=True)
    p1={}
    for radius,label in [(0,"exact_day"),(1,"plus_minus_1")]:
        days=expand_dates(star_days,radius); col=f"P1_{radius}"; add_event_col(nights,days,col)
        p1[label]={"poss_rate":fit_event_nb(nights,col,True,True),
                   "lag_profile_minus7_plus7":lag_profile(nights,star_days,range(-7,8)) if radius==0 else None}
    observed_night={dt.date.fromisoformat(x):1 for x in nights.date_obs.astype(str)}
    p1["palomar_schedule_overlap_year_month_null"]=block_null(observed_night,star_days,N_PERM,19520719)
    print("[5/7] frozen external families on POSS layer",flush=True)
    poss={}; poss_p={}
    if "D1_SOLAR_F107_HIGH" not in event_sets:
        poss["D1_SOLAR_F107_HIGH"]={"status":"NOT_EXECUTED_SOURCE_COVERAGE_INCOMPLETE","source_missing_days":gfz_meta["f107_adj_missing_days"]}
    for arm,days in event_sets.items():
        col=arm; add_event_col(nights,days,col)
        include_geomag=arm not in {"D3_GEOMAG_STORM","D4_GEOMAG_SEVERE_SENSITIVITY"}
        fit=fit_event_nb(nights,col,True,include_geomag)
        lags=range(-7,8) if arm in {"D1_SOLAR_F107_HIGH","D2_SUNSPOT_HIGH"} else (range(-4,5) if arm in {"D3_GEOMAG_STORM","D4_GEOMAG_SEVERE_SENSITIVITY"} else range(-3,4))
        poss[arm]={"event_days":len(days),"fit":fit,"lag_profile":lag_profile(nights,days,lags)}
        if arm in DISCOVERY_IDS and fit.get("status")=="OK": poss_p[arm]=fit["p_two_sided"]
    for arm in ["D6_LUNAR_DARK","D7_LUNAR_BRIGHT"]:
        fit=fit_event_nb(nights,arm,False,True); poss[arm]={"event_days_on_observed_nights":int(nights[arm].sum()),"fit":fit,"bluebook_layer":"DEFERRED_NO_FULL_CALENDAR_USNO_FREEZE"}
        if fit.get("status")=="OK": poss_p[arm]=fit["p_two_sided"]
    poss_q=bh(poss_p)
    for arm,q in poss_q.items(): poss[arm]["bh_q"]=q
    print("[6/7] frozen external families on Blue Book STARLIKE layer",flush=True)
    blue={}; blue_p={}
    if "D1_SOLAR_F107_HIGH" not in event_sets:
        blue["D1_SOLAR_F107_HIGH"]={"status":"NOT_EXECUTED_SOURCE_COVERAGE_INCOMPLETE","source_missing_days":gfz_meta["f107_adj_missing_days"]}
    blue_arms=[x for x in ["D1_SOLAR_F107_HIGH","D2_SUNSPOT_HIGH","D3_GEOMAG_STORM","D5_MAJOR_METEOR_SHOWER_PROXY"] if x in event_sets]
    for i,arm in enumerate(blue_arms):
        x=block_null(star_counts,event_sets[arm],N_PERM,19520605+i*1009); blue[arm]=x; blue_p[arm]=x["p_two_sided"]
    blue_q=bh(blue_p)
    for arm,q in blue_q.items(): blue[arm]["bh_q_executed_bluebook_families"]=q
    # Nested severe Kp sensitivity, kept outside discovery multiplicity family.
    blue["D4_GEOMAG_SEVERE_SENSITIVITY"]=block_null(star_counts,event_sets["D4_GEOMAG_SEVERE_SENSITIVITY"],N_PERM,19560329)
    blue["D6_LUNAR_DARK"]={"status":"DEFERRED_NO_FULL_CALENDAR_USNO_FREEZE"}; blue["D7_LUNAR_BRIGHT"]={"status":"DEFERRED_NO_FULL_CALENDAR_USNO_FREEZE"}
    cross={}
    for arm in ["D1_SOLAR_F107_HIGH","D2_SUNSPOT_HIGH","D3_GEOMAG_STORM","D5_MAJOR_METEOR_SHOWER_PROXY"]:
        if arm not in event_sets:
            cross[arm]={"classification":"NOT_EXECUTED_SOURCE_COVERAGE_INCOMPLETE"}
            continue
        pf=poss[arm]["fit"]; br=blue[arm]
        pdir=np.sign(math.log(pf["irr"])) if pf.get("status")=="OK" else 0
        bdir=np.sign(br["observed"]-br["null_mean"])
        cross[arm]={"direction_concordant":bool(pdir==bdir and pdir!=0),"poss_bh_q":poss[arm].get("bh_q"),
                    "bluebook_bh_q":blue[arm].get("bh_q_executed_bluebook_families"),
                    "classification":"CROSS_LAYER_PATTERN_CANDIDATE" if (pdir==bdir and pdir!=0 and poss[arm].get("bh_q",1)<=.10 and blue[arm].get("bh_q_executed_bluebook_families",1)<=.10) else "NOT_CROSS_LAYER_ADMITTED"}
    print("[7/7] write result",flush=True)
    result={
      "artifact_id":"JANUS-PALOMAR-JPFM-3A-CROSS-EVENT-ATLAS-RUN-001","experiment_id":"JPFM-3A","date":dt.date.today().isoformat(),"status":"EXECUTED",
      "claim_ceiling":"TEMPORAL_CROSS_EVENT_PATTERN_SEARCH_ONLY__NO_SHARED_OBJECT_CAUSALITY_OR_ORIGIN_CLAIM",
      "bindings":{"admission":str(ADMISSION),"admission_sha256":sha_file(ADMISSION),"source_coverage_audit":str(SOURCE_AUDIT),"source_coverage_audit_sha256":sha_file(SOURCE_AUDIT),
                  "source_coverage_policy":source_audit["correction"],"bluebook_starlike_freeze":str(STAR_FREEZE),"bluebook_starlike_meta":star_meta,
                  "poss_release_hashes":release_hashes,"gfz":gfz_meta,"usno":moon_meta,"meteor_proxy":{"peaks":METEOR_PEAKS,"radius_days":2,"by_shower":meteor_by}},
      "cohort":{"palomar_observed_nights":len(nights),"palomar_plates":len(p),"palomar_candidates":int(nights.candidate_count.sum()),"bluebook_starlike_days":len(star_days),"bluebook_starlike_cases":sum(star_counts.values())},
      "primary_cross_channel":p1,"poss_discovery":poss,"bluebook_discovery":blue,"cross_layer_gate":cross,
      "interpretation_rules":admission["admission_rules"],
      "context_only_not_inferential_v1":admission["context_only_not_inferential_v1"]
    }
    args.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))


if __name__=="__main__": main()
