#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JANUS JPFM-2E — Schedule Confound Decomposition.

Preregistered target:
  data/JANUS-PALOMAR-JPFM-2E-SCHEDULE-CONFOUND-DECOMPOSITION-ADMISSION-v1.0.json

This runner intentionally keeps two estimands separate:
  A) all-calendar binary ANY_CANDIDATE, which is tested for identity with the
     actual Palomar observing schedule;
  B) candidate rate conditional on an observed night, modeled with tile-count
     opportunity and a frozen nuisance ladder.

No causal or origin inference is permitted.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import importlib.util
import io
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.stats import fisher_exact
from statsmodels.discrete.discrete_model import NegativeBinomial, Logit

HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / "jpfm_open_reconstruction_temporal.py"
SPEC = importlib.util.spec_from_file_location("jpfm2d", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot import JPFM-2D base runner")
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

ADMISSION = "data/JANUS-PALOMAR-JPFM-2E-SCHEDULE-CONFOUND-DECOMPOSITION-ADMISSION-v1.0.json"
PARENT_RESULT = "data/JANUS-PALOMAR-JPFM-2D-OPEN-TEMPORAL-ASSOCIATION-RUN-001.json"
HUMAN_RESULT = "registry/cosmology/JANUS-POSS1-HUMAN-WITNESS-TEMPORAL-CONTROL-RESULT-v1.0.json"
HUMAN_DESIGN = "registry/cosmology/JANUS-POSS1-HUMAN-WITNESS-TEMPORAL-CONTROL-v1.0.json"
BLUEBOOK_CONTEXT = "registry/cosmology/JANUS-BLUEBOOK-QUESTIONNAIRE-STATISTICAL-CONTEXT-v1.0.json"

GFZ_URL = "https://kp.gfz-potsdam.de/app/files/Kp_ap_Ap_SN_F107_since_1932.txt"
USNO_URL = "https://aa.usno.navy.mil/api/rstt/oneday"
PALOMAR_LAT = 33.3566666667
PALOMAR_LON = -116.8625
MOON_WORKERS = 6

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "JANUS-JPFM-2E-public-reconstruction/1.0"})


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canonical_sha256(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def zscore(s: pd.Series):
    x = pd.to_numeric(s, errors="coerce").astype(float)
    med = float(x.median())
    x = x.fillna(med)
    mean = float(x.mean())
    sd = float(x.std(ddof=0))
    if (not np.isfinite(sd)) or sd == 0:
        return pd.Series(np.zeros(len(x)), index=x.index), {"mean": mean, "median": med, "sd": sd}
    return (x - mean) / sd, {"mean": mean, "median": med, "sd": sd}


def load_json_with_hash(path: str):
    p = Path(path)
    b = p.read_bytes()
    return json.loads(b.decode("utf-8")), sha256_bytes(b)


def fetch_gfz_daily():
    r = SESSION.get(GFZ_URL, timeout=180)
    r.raise_for_status()
    b = r.content
    widths = [
        4, 3, 3, 6, 8, 5, 3,
        7, 7, 7, 7, 7, 7, 7, 7,
        5, 5, 5, 5, 5, 5, 5, 5, 6, 4, 9, 9, 2,
    ]
    names = [
        "year", "month", "day", "days", "days_m", "bsrn", "rotd",
        "Kp0", "Kp3", "Kp6", "Kp9", "Kp12", "Kp15", "Kp18", "Kp21",
        "Ap0", "Ap3", "Ap6", "Ap9", "Ap12", "Ap15", "Ap18", "Ap21", "Apavg",
        "isn", "f107_obs", "f107_adj", "D",
    ]
    dtype = (
        "i4,i4,i4,i4,f4,i4,i4,"
        "f4,f4,f4,f4,f4,f4,f4,f4,"
        "i4,i4,i4,i4,i4,i4,i4,i4,i4,i4,f8,f8,i4"
    )
    arr = np.genfromtxt(
        io.StringIO(b.decode("ascii", errors="ignore")),
        skip_header=3,
        delimiter=widths,
        dtype=dtype,
        names=names,
        autostrip=True,
        invalid_raise=True,
    )
    arr = arr[arr["year"] != -1]
    d = pd.DataFrame(arr)
    d["date_obs"] = pd.to_datetime(d[["year", "month", "day"]]).dt.strftime("%Y-%m-%d")
    kpcols = [f"Kp{h}" for h in range(0, 24, 3)]
    d["max_kp"] = d[kpcols].max(axis=1).astype(float)
    d["daily_Ap"] = d["Apavg"].astype(float)
    start, end = base.STUDY_START.isoformat(), base.STUDY_END.isoformat()
    w = d[(d.date_obs >= start) & (d.date_obs <= end)].copy()
    expected_days = (base.STUDY_END - base.STUDY_START).days + 1
    if len(w) != expected_days or w.date_obs.nunique() != expected_days:
        raise RuntimeError(f"GFZ date coverage incomplete: rows={len(w)} expected={expected_days}")
    if (w["D"].astype(int) < 1).any():
        bad = w.loc[w["D"].astype(int) < 1, ["date_obs", "D"]].head(10).to_dict("records")
        raise RuntimeError(f"GFZ non-definitive Kp rows in historical window: {bad}")
    slim = w[["date_obs", "daily_Ap", "max_kp", "D"]].copy()
    history_hash = canonical_sha256(slim.to_dict("records"))
    return slim, {
        "source_url": GFZ_URL,
        "source_sha256": sha256_bytes(b),
        "historical_window_canonical_sha256": history_hash,
        "window_rows": int(len(slim)),
        "definitive_indicator_min": int(slim.D.min()),
        "definitive_indicator_max": int(slim.D.max()),
        "features": ["daily_Ap", "max_kp"],
        "source_semantics": "GFZ/IAGA Kp; Apavg is daily arithmetic mean of 3-hour ap amplitudes; max_kp is max of 8 daily 3-hour Kp bins.",
    }


def parse_fracillum(x) -> float:
    if x is None:
        raise ValueError("fracillum missing")
    s = str(x).strip().replace("%", "")
    v = float(s)
    if v > 1.0:
        v /= 100.0
    if not (0.0 <= v <= 1.0):
        raise ValueError(f"fracillum out of range: {x!r}")
    return v


def fetch_one_usno(date_s: str):
    params = {
        "date": date_s,
        "coords": f"{PALOMAR_LAT:.10f},{PALOMAR_LON:.10f}",
        "tz": "0",
    }
    last = None
    for attempt in range(5):
        try:
            r = SESSION.get(USNO_URL, params=params, timeout=45)
            r.raise_for_status()
            b = r.content
            j = r.json()
            if "error" in j:
                raise RuntimeError(j["error"])
            props = j.get("properties", {})
            data = props.get("data", {})
            if isinstance(data, list):
                if len(data) != 1:
                    raise RuntimeError("unexpected USNO properties.data list shape")
                data = data[0]
            frac = parse_fracillum(data.get("fracillum"))
            return {
                "date_obs": date_s,
                "lunar_illumination_fraction": frac,
                "curphase": data.get("curphase"),
                "response_sha256": sha256_bytes(b),
            }
        except Exception as e:
            last = e
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"USNO moon fetch failed {date_s}: {last}")


def fetch_usno_moon(dates):
    rows = []
    with cf.ThreadPoolExecutor(max_workers=MOON_WORKERS) as ex:
        futs = {ex.submit(fetch_one_usno, d): d for d in sorted(set(dates))}
        done = 0
        for fut in cf.as_completed(futs):
            rows.append(fut.result())
            done += 1
            if done % 50 == 0 or done == len(futs):
                print(f"[moon] {done}/{len(futs)}", flush=True)
    m = pd.DataFrame(rows).sort_values("date_obs").reset_index(drop=True)
    if len(m) != len(set(dates)):
        raise RuntimeError("USNO moon coverage mismatch")
    manifest = [{"date": r.date_obs, "sha256": r.response_sha256} for r in m.itertuples()]
    return m.drop(columns=["response_sha256"]), {
        "authority": "U.S. Naval Observatory Astronomical Applications Department",
        "source_url": USNO_URL,
        "palomar_coordinates": {"lat_deg": PALOMAR_LAT, "lon_deg_east": PALOMAR_LON},
        "tz_parameter": 0,
        "sampling_semantics": "USNO oneday fracillum for each POSS-I plate date at the service's noon epoch in UTC; exact historical exposure start time is not available in this reconstruction.",
        "response_manifest_sha256": canonical_sha256(manifest),
        "responses": int(len(manifest)),
        "feature": "lunar_illumination_fraction",
        "limitation": "Not Moon altitude, cloud state, exact sky brightness, or exact illumination at exposure midpoint.",
    }


def weighted_mean(g, col, weights):
    x = pd.to_numeric(g[col], errors="coerce").astype(float).to_numpy()
    good = np.isfinite(x) & np.isfinite(weights)
    return float(np.average(x[good], weights=weights[good])) if good.any() else float("nan")


def aggregate_nights_extended(plate_df):
    rows = []
    for date_obs, g in plate_df.groupby("date_obs", sort=True):
        w = g.tile_count.astype(float).to_numpy()
        ra = np.deg2rad(pd.to_numeric(g.plate_ra_deg, errors="coerce").astype(float).to_numpy())
        good_ra = np.isfinite(ra) & np.isfinite(w)
        rows.append({
            "date_obs": str(date_obs),
            "candidate_count": int(g.candidate_count.sum()),
            "candidate_count_pre_dedup": int(g.candidate_count_pre_dedup.sum()),
            "tile_count": int(g.tile_count.sum()),
            "n_plates": int(len(g)),
            "wcs_offset_arcsec": weighted_mean(g, "wcs_offset_arcsec", w),
            "exposure_min": weighted_mean(g, "exposure_min", w),
            "plate_dec_deg": weighted_mean(g, "plate_dec_deg", w),
            "abs_galactic_b_deg": weighted_mean(g, "abs_galactic_b_deg", w),
            "sky_ra_sin": float(np.average(np.sin(ra[good_ra]), weights=w[good_ra])) if good_ra.any() else float("nan"),
            "sky_ra_cos": float(np.average(np.cos(ra[good_ra]), weights=w[good_ra])) if good_ra.any() else float("nan"),
            "has_repaired_tile": int(g.has_repaired_tile.max()),
        })
    return pd.DataFrame(rows)


def calendar_design(nights, nuclear_col, model_id):
    d = nights.copy().reset_index(drop=True)
    X = pd.DataFrame({"intercept": np.ones(len(d)), "nuclear_window": d[nuclear_col].astype(float)})
    scalers = {}
    dates = pd.to_datetime(d.date_obs)
    if model_id == "M0_OPPORTUNITY_ONLY":
        return X, scalers

    doy = dates.dt.dayofyear.astype(float)
    if model_id == "M1_SEASON":
        X["annual_sin"] = np.sin(2 * np.pi * doy / 365.2425)
        X["annual_cos"] = np.cos(2 * np.pi * doy / 365.2425)
        return X, scalers

    month = pd.get_dummies(dates.dt.month.astype(int), prefix="month", drop_first=True, dtype=float)
    year = pd.get_dummies(dates.dt.year.astype(int), prefix="year", drop_first=True, dtype=float)
    X = pd.concat([X, month.reset_index(drop=True), year.reset_index(drop=True)], axis=1)
    if model_id == "M2_MONTH_YEAR":
        return X, scalers

    for src, dst in [
        ("sky_ra_sin", "sky_ra_sin_z"),
        ("sky_ra_cos", "sky_ra_cos_z"),
        ("plate_dec_deg", "dec_z"),
        ("abs_galactic_b_deg", "abs_gal_b_z"),
    ]:
        X[dst], scalers[src] = zscore(d[src])
    if model_id == "M3_SKY_FOOTPRINT":
        return X, scalers

    for src, dst in [("exposure_min", "exposure_z"), ("wcs_offset_arcsec", "wcs_z")]:
        X[dst], scalers[src] = zscore(d[src])
    if model_id == "M4_ACQUISITION_ASTROMETRY":
        return X, scalers

    X["lunar_illum_z"], scalers["lunar_illumination_fraction"] = zscore(d["lunar_illumination_fraction"])
    if model_id == "M5_LUNAR":
        return X, scalers

    X["geomag_Ap_z"], scalers["daily_Ap"] = zscore(d["daily_Ap"])
    X["geomag_maxKp_z"], scalers["max_kp"] = zscore(d["max_kp"])
    if model_id == "M6_GEOMAGNETIC_FULL":
        return X, scalers

    raise ValueError(model_id)


MODEL_IDS = [
    "M0_OPPORTUNITY_ONLY",
    "M1_SEASON",
    "M2_MONTH_YEAR",
    "M3_SKY_FOOTPRINT",
    "M4_ACQUISITION_ASTROMETRY",
    "M5_LUNAR",
    "M6_GEOMAGNETIC_FULL",
]


def fit_nb_step(nights, nuclear_col, model_id):
    X, scalers = calendar_design(nights, nuclear_col, model_id)
    y = nights.candidate_count.astype(float).to_numpy()
    opp = nights.tile_count.astype(float).to_numpy()
    if np.any(opp <= 0):
        raise RuntimeError("non-positive tile opportunity")
    res = NegativeBinomial(
        y,
        X.astype(float).to_numpy(),
        offset=np.log(opp),
        loglike_method="nb2",
    ).fit(disp=0, maxiter=1000)
    names = list(X.columns) + ["alpha"]
    params = dict(zip(names, map(float, res.params)))
    pvals = dict(zip(names, map(float, res.pvalues)))
    ci = np.asarray(res.conf_int(), dtype=float)
    idx = names.index("nuclear_window")
    beta = params["nuclear_window"]
    lo, hi = map(float, ci[idx])
    return {
        "model_id": model_id,
        "n": int(len(nights)),
        "p": int(X.shape[1]),
        "converged": bool(getattr(res, "mle_retvals", {}).get("converged", True)),
        "log_likelihood": float(res.llf),
        "aic": float(res.aic),
        "alpha": params.get("alpha"),
        "nuclear_beta": beta,
        "nuclear_se": float(res.bse[idx]),
        "nuclear_p_two_sided": pvals["nuclear_window"],
        "irr": float(math.exp(beta)),
        "irr_ci95": [float(math.exp(lo)), float(math.exp(hi))],
        "terms": list(X.columns),
        "scalers": scalers,
    }


def schedule_table(nights, nuclear_dates):
    observed = {dt.date.fromisoformat(x) for x in nights.date_obs.astype(str)}
    any_candidate = {
        dt.date.fromisoformat(r.date_obs)
        for r in nights.itertuples()
        if int(r.candidate_count) > 0
    }
    if observed != any_candidate:
        missing = sorted(x.isoformat() for x in observed - any_candidate)[:20]
        raise RuntimeError(f"central schedule identity precondition failed; observed nights without candidates: {missing}")

    def build(endpoint_dates):
        tab = np.zeros((2, 2), dtype=int)
        d = base.STUDY_START
        while d <= base.STUDY_END:
            exposed = base.in_window(d, nuclear_dates)
            endpoint = int(d in endpoint_dates)
            tab[exposed, endpoint] += 1
            d += dt.timedelta(days=1)
        table = [[int(tab[1, 1]), int(tab[1, 0])], [int(tab[0, 1]), int(tab[0, 0])]]
        odds, p = fisher_exact(table, alternative="two-sided")
        return table, float(odds), float(p)

    cand_table, cand_or, cand_p = build(any_candidate)
    obs_table, obs_or, obs_p = build(observed)
    exact = cand_table == obs_table and cand_or == obs_or and cand_p == obs_p
    if not exact:
        raise RuntimeError("ANY_CANDIDATE and OBSERVED_NIGHT schedule tables differ")
    a, b = obs_table[0]
    c, d0 = obs_table[1]
    return {
        "all_observed_nights_have_candidate": True,
        "any_candidate_equals_observed_night": True,
        "table_exposed_unexposed_by_observed_not_observed": obs_table,
        "candidate_table_identical": cand_table,
        "odds_ratio": obs_or,
        "fisher_p_two_sided": obs_p,
        "observed_fraction_nuclear_window": a / (a + b),
        "observed_fraction_non_nuclear_window": c / (c + d0),
        "interpretation": "The all-calendar ANY_CANDIDATE association is exactly the Palomar observing-schedule association for this dense S0 cohort.",
    }


def schedule_logit_month_year(nuclear_dates):
    rows = []
    d = base.STUDY_START
    observed_set = schedule_logit_month_year.observed_set
    while d <= base.STUDY_END:
        rows.append({
            "date": d.isoformat(),
            "observed": int(d in observed_set),
            "nuclear_window": base.in_window(d, nuclear_dates),
            "month": d.month,
            "year": d.year,
        })
        d += dt.timedelta(days=1)
    df = pd.DataFrame(rows)
    X = pd.DataFrame({"intercept": 1.0, "nuclear_window": df.nuclear_window.astype(float)})
    md = pd.get_dummies(df.month, prefix="month", drop_first=True, dtype=float)
    yd = pd.get_dummies(df.year, prefix="year", drop_first=True, dtype=float)
    X = pd.concat([X, md, yd], axis=1)
    res = Logit(df.observed.astype(float).to_numpy(), X.astype(float).to_numpy()).fit(disp=0, maxiter=500)
    names = list(X.columns)
    idx = names.index("nuclear_window")
    beta = float(res.params[idx])
    ci = np.asarray(res.conf_int(), dtype=float)[idx]
    return {
        "model": "calendar-day logistic observed_night ~ nuclear_window + month_FE + year_FE",
        "n_calendar_days": int(len(df)),
        "n_observed_nights": int(df.observed.sum()),
        "converged": bool(getattr(res, "mle_retvals", {}).get("converged", True)),
        "nuclear_beta": beta,
        "schedule_adjusted_odds_ratio": float(math.exp(beta)),
        "schedule_adjusted_or_ci95": [float(math.exp(ci[0])), float(math.exp(ci[1]))],
        "nuclear_p_two_sided": float(res.pvalues[idx]),
    }


def shift_schedule_test(nights, nuclear_dates):
    obs = {dt.date.fromisoformat(x) for x in nights.date_obs.astype(str)}
    span = (base.STUDY_END - base.STUDY_START).days + 1

    def shifted(k):
        return [
            base.STUDY_START + dt.timedelta(days=((x - base.STUDY_START).days + k) % span)
            for x in nuclear_dates
        ]

    def overlap(cal):
        return sum(base.in_window(x, cal) for x in obs)

    observed = overlap(nuclear_dates)
    null = np.array([overlap(shifted(k)) for k in range(1, span)], dtype=int)
    p_hi = float((1 + np.sum(null >= observed)) / (len(null) + 1))
    center = float(np.mean(null))
    p_two = float((1 + np.sum(np.abs(null - center) >= abs(observed - center))) / (len(null) + 1))
    return {
        "method": "exhaustive circular shift of full nuclear calendar against fixed Palomar observed-night schedule",
        "n_nonzero_shifts": int(len(null)),
        "observed_exposed_observed_nights": int(observed),
        "null_mean": center,
        "null_sd": float(np.std(null, ddof=1)),
        "empirical_p_upper": p_hi,
        "empirical_p_two_sided_about_null_mean": p_two,
        "preserves": ["Palomar observation dates", "nuclear-event spacing", "number of nuclear dates"],
    }


def group_summary(nights, exp_col):
    out = {}
    for k, label in [(1, "nuclear_window"), (0, "non_nuclear_window")]:
        g = nights[nights[exp_col] == k]
        out[label] = {
            "n_nights": int(len(g)),
            "candidate_count": int(g.candidate_count.sum()),
            "tile_count": int(g.tile_count.sum()),
            "candidate_per_tile": float(g.candidate_count.sum() / g.tile_count.sum()),
            "mean_plates_per_night": float(g.n_plates.mean()),
            "median_plates_per_night": float(g.n_plates.median()),
            "mean_exposure_min": float(g.exposure_min.mean()),
            "mean_lunar_illumination_fraction": float(g.lunar_illumination_fraction.mean()),
            "mean_daily_Ap": float(g.daily_Ap.mean()),
            "mean_daily_max_Kp": float(g.max_kp.mean()),
            "mean_abs_galactic_latitude_deg": float(g.abs_galactic_b_deg.mean()),
        }
    return out


def run_calendar_arm(nights, nuclear_dates, arm_id):
    d = nights.copy()
    d["nuclear_window"] = [
        base.in_window(dt.date.fromisoformat(x), nuclear_dates)
        for x in d.date_obs.astype(str)
    ]
    schedule_logit_month_year.observed_set = {dt.date.fromisoformat(x) for x in d.date_obs.astype(str)}
    identity = schedule_table(d, nuclear_dates)
    sched_adj = schedule_logit_month_year(nuclear_dates)
    sched_shift = shift_schedule_test(d, nuclear_dates)

    ladder = [fit_nb_step(d, "nuclear_window", mid) for mid in MODEL_IDS]
    for i, rec in enumerate(ladder):
        if i == 0:
            rec["delta_beta_from_previous"] = None
        else:
            rec["delta_beta_from_previous"] = float(rec["nuclear_beta"] - ladder[i - 1]["nuclear_beta"])
    crude = base.rate_summary(d, "candidate_count", "nuclear_window", "tile_count")
    final = ladder[-1]
    residual_positive = (
        final["irr"] > 1.0
        and final["nuclear_p_two_sided"] < 0.05
        and final["irr_ci95"][0] > 1.0
    )
    return {
        "calendar_arm": arm_id,
        "nuclear_unique_dates": int(len(nuclear_dates)),
        "schedule_identity_gate": identity,
        "schedule_month_year_logit": sched_adj,
        "schedule_preserving_shift": sched_shift,
        "observed_night_group_summary": group_summary(d, "nuclear_window"),
        "observed_night_crude_rate": crude,
        "conditional_rate_model_ladder": ladder,
        "final_M6_positive_rate_signal": bool(residual_positive),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    admission, admission_sha = load_json_with_hash(ADMISSION)
    parent, parent_sha = load_json_with_hash(PARENT_RESULT)
    human_result, human_sha = load_json_with_hash(HUMAN_RESULT)
    _human_design, human_design_sha = load_json_with_hash(HUMAN_DESIGN)
    _bb, bluebook_sha = load_json_with_hash(BLUEBOOK_CONTEXT)
    if admission.get("status") != "PREREGISTERED_BEFORE_JPFM_2E_OUTCOME":
        raise RuntimeError("admission artifact not preregistered")
    if parent.get("aggregate_verdict", {}).get("code") != "OPEN_TEMPORAL_ASSOCIATION_NOT_ROBUST_ACROSS_FROZEN_CONTROLS":
        raise RuntimeError("unexpected JPFM-2D parent state")
    if human_result.get("current_inference", {}).get("STARLIKE_WITNESS_specific_to_nuclear_dates") != "NO":
        raise RuntimeError("human specificity parent mismatch")

    print("[1/8] hash-gate POSS release + headers", flush=True)
    s0, tiles, repairs, wcs, release_hashes = base.read_release_tables()
    plates = sorted(tiles.plate_id.dropna().astype(str).unique())
    headers = base.fetch_all_headers(plates)
    all_plates, _joined = base.build_plate_table(s0, tiles, repairs, wcs, headers)
    all_plates["date_obj"] = pd.to_datetime(all_plates.date_obs).dt.date
    plate_df = all_plates[
        (all_plates.date_obj >= base.STUDY_START) &
        (all_plates.date_obj <= base.STUDY_END)
    ].copy().drop(columns=["date_obj"])
    if len(plate_df) != 640:
        raise RuntimeError(f"expected 640 study-window plates, got {len(plate_df)}")

    print("[2/8] aggregate 640 plates -> observed nights", flush=True)
    nights = aggregate_nights_extended(plate_df)
    if len(nights) != 312:
        raise RuntimeError(f"expected 312 observed nights, got {len(nights)}")
    if not (nights.candidate_count > 0).all():
        raise RuntimeError("not every observed night has S0 candidates")

    print("[3/8] public GFZ definitive geomagnetic series", flush=True)
    gfz, gfz_meta = fetch_gfz_daily()
    nights = nights.merge(gfz[["date_obs", "daily_Ap", "max_kp"]], on="date_obs", how="left", validate="one_to_one")
    if nights[["daily_Ap", "max_kp"]].isna().any().any():
        raise RuntimeError("GFZ join incomplete")

    print("[4/8] public USNO lunar illumination for observed nights", flush=True)
    moon, moon_meta = fetch_usno_moon(nights.date_obs.tolist())
    nights = nights.merge(moon, on="date_obs", how="left", validate="one_to_one")
    if nights.lunar_illumination_fraction.isna().any():
        raise RuntimeError("USNO moon join incomplete")

    print("[5/8] nuclear calendar", flush=True)
    calendars, nuclear_meta = base.read_nuclear_calendar()

    print("[6/8] execute frozen schedule + conditional-rate decomposition", flush=True)
    arms = {}
    for arm_id in ("OPEN_ALL_REPORTED_125", "OPEN_NON_UW_123", "PHYSICAL_ATMOSPHERIC_SURFACE"):
        print("  ->", arm_id, flush=True)
        arms[arm_id] = run_calendar_arm(nights, calendars[arm_id], arm_id)

    m6 = [arms[a]["conditional_rate_model_ladder"][-1] for a in arms]
    residual_positive_all = all(
        r["irr"] > 1 and r["nuclear_p_two_sided"] < 0.05 and r["irr_ci95"][0] > 1
        for r in m6
    )
    schedule_identity_all = all(arms[a]["schedule_identity_gate"]["any_candidate_equals_observed_night"] for a in arms)

    print("[7/8] build result with proof bindings", flush=True)
    primary = arms["OPEN_ALL_REPORTED_125"]
    parent_or = float(parent["calendar_arms"]["OPEN_ALL_REPORTED_125"]["all_calendar_diagnostic"]["odds_ratio"])
    parent_p = float(parent["calendar_arms"]["OPEN_ALL_REPORTED_125"]["all_calendar_diagnostic"]["p_two_sided"])
    if abs(primary["schedule_identity_gate"]["odds_ratio"] - parent_or) > 1e-12:
        raise RuntimeError("JPFM-2E schedule OR does not reproduce JPFM-2D all-calendar OR")
    if abs(primary["schedule_identity_gate"]["fisher_p_two_sided"] - parent_p) > 1e-12:
        raise RuntimeError("JPFM-2E schedule p does not reproduce JPFM-2D all-calendar p")
    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-2E-SCHEDULE-CONFOUND-DECOMPOSITION-RUN-001",
        "experiment_id": "JPFM-2E",
        "schema_version": "1.0",
        "date": dt.date.today().isoformat(),
        "status": "EXECUTED",
        "claim_ceiling": "SCHEDULE_CONFOUND_DECOMPOSITION_AND_CONDITIONAL_RATE_SPECIFICITY_TEST_ONLY__NO_NUCLEAR_CAUSALITY__NO_UAP_ORIGIN_IDENTIFICATION",
        "bindings": {
            "admission_path": ADMISSION,
            "admission_file_sha256": admission_sha,
            "jpfm_2d_parent_path": PARENT_RESULT,
            "jpfm_2d_parent_file_sha256": parent_sha,
            "human_result_path": HUMAN_RESULT,
            "human_result_file_sha256": human_sha,
            "human_design_file_sha256": human_design_sha,
            "bluebook_context_file_sha256": bluebook_sha,
            "poss_commit": base.POSS_COMMIT,
            "poss_release": base.REL,
            "poss_release_hashes": release_hashes,
            "nuclear_meta": nuclear_meta,
            "geomagnetic": gfz_meta,
            "lunar": moon_meta,
        },
        "cohort": {
            "plates": int(len(plate_df)),
            "observed_nights": int(len(nights)),
            "candidate_count": int(nights.candidate_count.sum()),
            "tile_count": int(nights.tile_count.sum()),
            "all_observed_nights_candidate_positive": bool((nights.candidate_count > 0).all()),
            "study_window": [base.STUDY_START.isoformat(), base.STUDY_END.isoformat()],
        },
        "human_layer_specificity_control": {
            "pooled_into_photographic_model": False,
            "STARLIKE_WITNESS_specific_to_nuclear_dates": human_result["current_inference"]["STARLIKE_WITNESS_specific_to_nuclear_dates"],
            "human_non_nuclear_baseline": human_result["current_inference"]["human_non_nuclear_baseline"],
            "preliminary_positive_nuclear_human_report_signal": human_result["current_inference"]["preliminary_positive_nuclear_human_report_signal"],
            "role": "Independent specificity control only.",
        },
        "calendar_arms": arms,
        "forensic_summary": {
            "schedule_identity_passed_all_calendar_arms": bool(schedule_identity_all),
            "primary_all_calendar_binary_OR": float(primary["schedule_identity_gate"]["odds_ratio"]),
            "primary_all_calendar_fisher_p": float(primary["schedule_identity_gate"]["fisher_p_two_sided"]),
            "primary_binary_endpoint_identity": "ANY_CANDIDATE == PALOMAR_OBSERVED_NIGHT",
            "primary_observed_night_crude_rate_ratio": float(primary["observed_night_crude_rate"]["crude_rate_ratio"]),
            "primary_M0_IRR": float(primary["conditional_rate_model_ladder"][0]["irr"]),
            "primary_M6_IRR": float(primary["conditional_rate_model_ladder"][-1]["irr"]),
            "primary_M6_p": float(primary["conditional_rate_model_ladder"][-1]["nuclear_p_two_sided"]),
            "residual_positive_nuclear_rate_signal_survives_all_arms": bool(residual_positive_all),
        },
        "aggregate_verdict": {
            "code": (
                "SCHEDULE_BINARY_ASSOCIATION_IDENTIFIED__RESIDUAL_POSITIVE_RATE_SIGNAL_SURVIVES"
                if schedule_identity_all and residual_positive_all
                else "SCHEDULE_BINARY_ASSOCIATION_IDENTIFIED__NO_ROBUST_POSITIVE_RESIDUAL_RATE_SIGNAL"
            ),
            "interpretation": (
                "For this dense open S0 cohort, the all-calendar ANY_CANDIDATE binary association is exactly the Palomar observation-schedule association. "
                "Candidate-rate inference must therefore be conditional on actual observing opportunity. The final residual-rate claim is admitted only if it survives the preregistered M6 model in all three frozen calendar arms."
            ),
            "causality": "NOT_ADMITTED",
            "origin": "NOT_ADMITTED",
        },
    }
    payload = dict(result)
    result["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_sha256(payload)}
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("[8/8] wrote", args.out, flush=True)
    fs = result["forensic_summary"]
    print("VERDICT", result["aggregate_verdict"]["code"], flush=True)
    print("PRIMARY schedule OR", fs["primary_all_calendar_binary_OR"], "p", fs["primary_all_calendar_fisher_p"], flush=True)
    print("PRIMARY crude rate ratio", fs["primary_observed_night_crude_rate_ratio"], flush=True)
    print("PRIMARY M0 IRR", fs["primary_M0_IRR"], flush=True)
    print("PRIMARY M6 IRR", fs["primary_M6_IRR"], "p", fs["primary_M6_p"], flush=True)


if __name__ == "__main__":
    main()
