#!/usr/bin/env python3
"""Post-hoc diagnostics for the JANUS public-only POSS-I reconstruction.

This runner is deliberately NOT part of the preregistered primary hypothesis test.
It localizes the temporal shape of any residual nuclear-window association and
checks whether simple year-blocked schedule permutations reproduce the observed
contrast. It must never be used to promote a causal/UAP interpretation.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

RUNNER_ID = "JANUS-POSS1-OPEN-POSTHOC-DIAGNOSTICS-v0.1"
DEFAULT_SEED = 20260815
DEFAULT_PERMUTATIONS = 20000


def extract_term(result, term: str) -> dict:
    beta = float(result.params[term])
    se = float(result.bse[term])
    return {
        "beta": beta,
        "se": se,
        "irr": math.exp(beta),
        "irr_95ci": [math.exp(beta - 1.96 * se), math.exp(beta + 1.96 * se)],
        "p_value": float(result.pvalues[term]),
    }


def robust_kwargs(df: pd.DataFrame) -> tuple[str, dict]:
    if df["obs_date_utc"].nunique() >= 20:
        return "cluster", {"groups": df["obs_date_utc"].astype(str)}
    return "HC1", {}


def load_calendar(path: Path) -> set[date]:
    cal = pd.read_csv(path)
    if "date_utc" not in cal.columns:
        raise SystemExit("fail-closed: calendar must contain date_utc")
    dates = pd.to_datetime(cal["date_utc"], errors="raise").dt.date
    return set(dates)


def lag_flag(d: date, tests: set[date], lag: int) -> int:
    # lag=+1 means observation occurred one day AFTER a nuclear-test date.
    return int((d - timedelta(days=lag)) in tests)


def window_flag(d: date, tests: set[date], radius: int) -> int:
    return int(any((d - timedelta(days=k)) in tests for k in range(-radius, radius + 1)))


def fit_nb(df: pd.DataFrame, formula: str, exposure_col: str):
    cov_type, cov_kwds = robust_kwargs(df)
    exposure = pd.to_numeric(df[exposure_col], errors="raise")
    return smf.negativebinomial(formula, data=df, exposure=exposure).fit(
        disp=False, cov_type=cov_type, cov_kwds=cov_kwds
    )


def standardized_h0_residuals(df: pd.DataFrame, exposure_col: str) -> np.ndarray:
    exposure = pd.to_numeric(df[exposure_col], errors="raise")
    h0 = smf.negativebinomial(
        "candidate_count ~ year_centered + season_sin + season_cos",
        data=df,
        exposure=exposure,
    ).fit(disp=False)
    mu = np.asarray(h0.predict(df, exposure=exposure), dtype=float)
    alpha = float(h0.params.get("alpha", 0.0))
    var = np.maximum(mu + alpha * mu * mu, 1e-12)
    return (np.asarray(df["candidate_count"], dtype=float) - mu) / np.sqrt(var)


def aggregate_dates(df: pd.DataFrame, residuals: np.ndarray, tests: set[date]) -> pd.DataFrame:
    tmp = df[["obs_date_utc"]].copy()
    tmp["residual"] = residuals
    tmp["obs_date"] = pd.to_datetime(tmp["obs_date_utc"]).dt.date
    # Multiple plates can share a date; use mean standardized residual so the
    # randomization unit is the observation date, not duplicated plate rows.
    out = tmp.groupby("obs_date", as_index=False)["residual"].mean()
    out["year"] = [d.year for d in out["obs_date"]]
    for radius in (1, 2, 4):
        out[f"w{radius}"] = [window_flag(d, tests, radius) for d in out["obs_date"]]
    return out


def residual_contrast(values: np.ndarray, flags: np.ndarray) -> float:
    inside = values[flags == 1]
    outside = values[flags == 0]
    if len(inside) == 0 or len(outside) == 0:
        raise RuntimeError("degenerate permutation contrast")
    return float(np.mean(inside) - np.mean(outside))


def blocked_permutation(date_df: pd.DataFrame, radius: int, n_perm: int, seed: int) -> dict:
    rng = np.random.default_rng(seed + radius)
    values = np.asarray(date_df["residual"], dtype=float)
    flags = np.asarray(date_df[f"w{radius}"], dtype=int)
    observed = residual_contrast(values, flags)
    years = np.asarray(date_df["year"], dtype=int)
    groups = {y: np.flatnonzero(years == y) for y in np.unique(years)}
    exceed = 0
    for _ in range(n_perm):
        perm = flags.copy()
        for idx in groups.values():
            perm[idx] = rng.permutation(perm[idx])
        stat = residual_contrast(values, perm)
        if abs(stat) >= abs(observed):
            exceed += 1
    p = (exceed + 1) / (n_perm + 1)
    return {
        "radius_days": radius,
        "observed_standardized_residual_contrast_inside_minus_outside": observed,
        "permutations": n_perm,
        "seed": seed + radius,
        "two_sided_p": p,
        "randomization_unit": "unique observation date",
        "blocking": "calendar year",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matrix", required=True)
    ap.add_argument("--calendar", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--exposure-col", default="exposure_tile_min")
    ap.add_argument("--permutations", type=int, default=DEFAULT_PERMUTATIONS)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args()

    matrix_path = Path(args.matrix)
    calendar_path = Path(args.calendar)
    df = pd.read_csv(matrix_path)
    required = {
        "candidate_count", "obs_date_utc", args.exposure_col,
        "year_centered", "season_sin", "season_cos",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise SystemExit(f"fail-closed: missing matrix columns {missing}")
    exposure = pd.to_numeric(df[args.exposure_col], errors="raise")
    if (exposure <= 0).any():
        raise SystemExit("fail-closed: nonpositive exposure")

    tests = load_calendar(calendar_path)
    obs_dates = pd.to_datetime(df["obs_date_utc"], errors="raise").dt.date
    for lag in range(-4, 5):
        df[f"lag_{lag:+d}"] = [lag_flag(d, tests, lag) for d in obs_dates]

    base = "candidate_count ~ year_centered + season_sin + season_cos"
    individual = {}
    for lag in range(-4, 5):
        term = f"lag_{lag:+d}"
        # Patsy cannot parse '+'/'-' in column names directly; bind a safe alias.
        safe = f"lag_m{abs(lag)}" if lag < 0 else f"lag_p{lag}"
        df[safe] = df[term]
        fit = fit_nb(df, base + f" + {safe}", args.exposure_col)
        individual[str(lag)] = {
            **extract_term(fit, safe),
            "plate_rows_flagged": int(df[safe].sum()),
        }

    # Localize the original literature's most salient window without mixing it
    # with wider exploratory lags: -1, 0, +1 are fitted jointly.
    df["lag_m1_joint"] = df["lag_-1"]
    df["lag_0_joint"] = df["lag_+0"]
    df["lag_p1_joint"] = df["lag_+1"]
    joint_formula = base + " + lag_m1_joint + lag_0_joint + lag_p1_joint"
    joint = fit_nb(df, joint_formula, args.exposure_col)
    joint_result = {
        "day_minus_1": extract_term(joint, "lag_m1_joint"),
        "test_day": extract_term(joint, "lag_0_joint"),
        "day_plus_1": extract_term(joint, "lag_p1_joint"),
    }

    residuals = standardized_h0_residuals(df, args.exposure_col)
    date_df = aggregate_dates(df, residuals, tests)
    perms = {
        str(radius): blocked_permutation(date_df, radius, args.permutations, args.seed)
        for radius in (1, 2, 4)
    }

    result = {
        "runner_id": RUNNER_ID,
        "status": "POST_HOC_DIAGNOSTIC_NOT_PREREGISTERED",
        "inputs": {
            "matrix": str(matrix_path),
            "calendar": str(calendar_path),
            "matrix_rows": int(len(df)),
            "unique_observation_dates": int(df["obs_date_utc"].nunique()),
            "unique_test_dates": int(len(tests)),
            "exposure_column": args.exposure_col,
        },
        "individual_exact_lag_nb2": individual,
        "joint_minus1_testday_plus1_nb2": joint_result,
        "year_blocked_schedule_permutation": perms,
        "interpretation_rules": [
            "These diagnostics were added after seeing the primary open +/-1 result and are not confirmatory preregistered tests.",
            "A negative lag/window coefficient does not establish nuclear suppression; pre-event effects are especially diagnostic of schedule/field confounding.",
            "Permutation p-values here test a simple year-blocked schedule null on H0 standardized residuals; they are not exact causal randomization inference.",
            "No result may be promoted to UAP, non-human, or physical-transient evidence without independent object-level and artifact controls.",
        ],
        "next_required_controls": [
            "plate/tile sky-position controls including Galactic latitude or an external stellar-density proxy",
            "exact valid geometric footprint exposure rather than tile-minute proxy",
            "plate/copy/scanner/WCS quality strata",
            "geomagnetic Kp/Ap and weather/lunar controls where source-complete",
        ],
    }
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
