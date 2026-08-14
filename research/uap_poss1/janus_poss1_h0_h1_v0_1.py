#!/usr/bin/env python3
"""Fit preregistered H0 schedule/artifact vs H1 baseline+trigger on plate-day data.

Primary fit: NB2 with estimated dispersion and an explicit area-time exposure term.
Sensitivity fit: Poisson GLM with robust/clustered covariance. The script refuses
plate-count-only matrices for the primary beta_nuclear claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy.stats import chi2

RUNNER_ID = "JANUS-POSS1-H0-H1-v0.1"


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def robust_kwargs(df: pd.DataFrame) -> tuple[str, dict]:
    if "obs_date_utc" in df.columns and df["obs_date_utc"].nunique() >= 20:
        return "cluster", {"groups": df["obs_date_utc"].astype(str)}
    return "HC1", {}


def extract_term(result, term: str) -> dict:
    beta = float(result.params[term]); se = float(result.bse[term])
    return {"beta": beta, "se": se, "irr": math.exp(beta), "irr_95ci": [math.exp(beta - 1.96 * se), math.exp(beta + 1.96 * se)], "p_value": float(result.pvalues[term])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matrix", required=True); ap.add_argument("--output", required=True)
    ap.add_argument("--covariates", default="", help="Comma-separated preregistered formula terms already present as columns")
    ap.add_argument("--nuclear-term", default="nuclear_window_m1_p1")
    args = ap.parse_args()
    path = Path(args.matrix); df = pd.read_csv(path)
    required = {"candidate_count", "exposure_deg2_min", args.nuclear_term}; missing = sorted(required - set(df.columns))
    if missing: raise SystemExit(f"fail-closed: missing columns {missing}")
    exposure = pd.to_numeric(df["exposure_deg2_min"], errors="coerce")
    if exposure.isna().any() or (exposure <= 0).any(): raise SystemExit("fail-closed: primary model requires positive area-time exposure for every row")
    y = pd.to_numeric(df["candidate_count"], errors="coerce")
    if y.isna().any() or (y < 0).any(): raise SystemExit("fail-closed: invalid candidate_count")
    df = df.copy(); df["candidate_count"] = y
    df[args.nuclear_term] = df[args.nuclear_term].astype(str).str.lower().map({"true": 1, "false": 0, "1": 1, "0": 0})
    if df[args.nuclear_term].isna().any(): raise SystemExit("fail-closed: nuclear term must be binary")
    covariates = [x.strip() for x in args.covariates.split(",") if x.strip()]
    for c in covariates:
        if c not in df.columns: raise SystemExit(f"fail-closed: preregistered covariate missing or non-column term: {c}")
    h0_formula = "candidate_count ~ " + (" + ".join(covariates) if covariates else "1")
    h1_formula = h0_formula + " + " + args.nuclear_term
    cov_type, cov_kwds = robust_kwargs(df)

    nb0_plain = smf.negativebinomial(h0_formula, data=df, exposure=exposure).fit(disp=False)
    nb1_plain = smf.negativebinomial(h1_formula, data=df, exposure=exposure).fit(disp=False)
    nb1 = smf.negativebinomial(h1_formula, data=df, exposure=exposure).fit(disp=False, cov_type=cov_type, cov_kwds=cov_kwds)
    nb_term = extract_term(nb1, args.nuclear_term); lrt = max(0.0, 2.0 * (float(nb1_plain.llf) - float(nb0_plain.llf)))
    offset = np.log(exposure)
    pois1 = smf.glm(h1_formula, data=df, family=sm.families.Poisson(), offset=offset).fit(cov_type=cov_type, cov_kwds=cov_kwds)
    pois_term = extract_term(pois1, args.nuclear_term)
    alpha = float(nb1_plain.params.get("alpha", float("nan")))
    result = {
        "runner_id": RUNNER_ID, "status": "MODEL_FIT_COMPLETE_NOT_CAUSAL_PROOF",
        "input": {"path": str(path), "sha256": sha256_path(path), "rows": int(len(df))},
        "exposure": "deg2_min", "covariance": {"type": cov_type, "cluster_column": "obs_date_utc" if cov_type == "cluster" else None},
        "h0_formula": h0_formula, "h1_formula": h1_formula,
        "primary_nb2": {"dispersion_alpha_estimated": alpha, "nuclear": nb_term, "aic_h0": float(nb0_plain.aic), "aic_h1": float(nb1_plain.aic), "delta_aic_h1_minus_h0": float(nb1_plain.aic - nb0_plain.aic), "likelihood_ratio_chi2_1df": lrt, "likelihood_ratio_p": float(chi2.sf(lrt, 1))},
        "poisson_sensitivity": {"nuclear": pois_term, "aic_h1": float(pois1.aic)},
        "beta_nuclear_primary": nb_term["beta"], "irr_nuclear_primary": nb_term["irr"], "irr_95ci_primary": nb_term["irr_95ci"], "p_value_primary": nb_term["p_value"],
        "interpretive_ceiling": "Association after preregistered exposure/covariate controls only; no causal/UAP/non-human promotion.",
        "required_sensitivity": ["alternate frozen nuclear calendars without post-hoc calendar choice", "lag windows +/-2 and +/-4 days", "cluster/block permutation preserving season and observation schedule", "plate/copy/scanner artifact covariates", "Kp/Ap, lunar, precipitation/cloud covariates where source-complete", "center-of-plate and edge-stratified analyses", "candidate-quality/ML threshold strata only if thresholds are frozen before effect inspection"]
    }
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8"); print(json.dumps(result, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
