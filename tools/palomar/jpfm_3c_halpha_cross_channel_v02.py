#!/usr/bin/env python3
"""Technical hotfix wrapper for JPFM-3C.

The preregistered scientific design is unchanged. The v0.1 runner can receive
NaN standard errors/p-values from statsmodels when a small lag/sensitivity NB2
fit has a singular Hessian. v0.2 converts such model outputs into an explicit
fail-closed status before the v0.1 result serializer runs.
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE / "jpfm_3c_halpha_cross_channel.py"
SPEC = importlib.util.spec_from_file_location("jpfm3c_v01", BASE)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {BASE}")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

_original_fit_poss = mod.fit_poss


def _finite_number(x) -> bool:
    try:
        return bool(np.isfinite(float(x)))
    except Exception:
        return False


def _finite_or_none(x):
    return float(x) if _finite_number(x) else None


def fit_poss_fail_closed(nights, solar_rows):
    out = _original_fit_poss(nights, solar_rows)
    if out.get("status") != "OK":
        return out

    required = [
        "event_beta", "event_se", "p_two_sided", "irr",
        "crude_rate_flare", "crude_rate_nonflare", "crude_rate_ratio",
        "aic", "alpha",
    ]
    ci = out.get("irr_ci95")
    finite_ci = isinstance(ci, list) and len(ci) == 2 and all(_finite_number(v) for v in ci)
    bad = [k for k in required if not _finite_number(out.get(k))]
    if bad or not finite_ci:
        return {
            "status": "MODEL_NONFINITE_INFERENCE_FAIL_CLOSED",
            "n": int(out.get("n", 0)),
            "flare_nights": int(out.get("flare_nights", 0)),
            "nonflare_nights": int(out.get("nonflare_nights", 0)),
            "nonfinite_fields": bad + ([] if finite_ci else ["irr_ci95"]),
            "crude_rate_flare": _finite_or_none(out.get("crude_rate_flare")),
            "crude_rate_nonflare": _finite_or_none(out.get("crude_rate_nonflare")),
            "crude_rate_ratio": _finite_or_none(out.get("crude_rate_ratio")),
            "scientific_design_changed": False,
            "interpretation": "NB2 Hessian/covariance inference was non-finite; this fit is excluded rather than serialized as NaN or used for admission."
        }
    return out


mod.fit_poss = fit_poss_fail_closed

if __name__ == "__main__":
    mod.main()
