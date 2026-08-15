#!/usr/bin/env python3
"""JANUS Blue Book exact-date matched nuclear specificity control v0.1.

Implements the preregistered blocked pseudo-test calendars from
JANUS-BLUEBOOK-EXACT-DATE-MATCHED-CONTROL-PREREG-v1.0.

Primary inferential unit is archival report incidence, NOT person-observation
exposure. Both case-count and binary active-day endpoints are mandatory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import random
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean

RUNNER_ID = "JANUS-BLUEBOOK-EXACT-DATE-MATCHED-CONTROL-v0.1"
START, END = date(1949, 11, 19), date(1957, 4, 28)
SIPRI_URL = "https://gist.githubusercontent.com/ZijunXu/2c9d8a8db6420799ed944187100f8aee/raw/sipri-report-explosions.csv"
SIPRI_SHA = "1bdfb18cc41741e6c45c5bdfa3d70d8d0739e08b406c647aa1913ce013ee5b95"
COUNTRIES = {"USA", "USSR", "UK"}
STRICT_TYPES = {"AIRDROP", "TOWER", "SURFACE", "ATMOSPH", "BARGE", "BALLOON", "ROCKET", "SHIP"}
YEAR_SEED = 19520719
YEARMONTH_SEED = 19520605
N_PERM = 50000


def sha_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "JANUS-BlueBook-MatchedControl/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def strict_calendar(raw: bytes) -> list[date]:
    if sha_bytes(raw) != SIPRI_SHA:
        raise SystemExit("fail-closed: frozen strict nuclear calendar bytes changed")
    out = set()
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        if (r.get("country") or "").strip().upper() not in COUNTRIES:
            continue
        if (r.get("type") or "").strip().upper() not in STRICT_TYPES:
            continue
        s = (r.get("date_long") or "").strip()
        if not re.fullmatch(r"\d{8}", s):
            continue
        d = datetime.strptime(s, "%Y%m%d").date()
        if START <= d <= END:
            out.add(d)
    return sorted(out)


def all_days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def window_dates(tests: list[date], radius: int) -> set[date]:
    out = set()
    for t in tests:
        for lag in range(-radius, radius + 1):
            d = t + timedelta(days=lag)
            if START <= d <= END:
                out.add(d)
    return out


def exact_lag_dates(tests: list[date], lag: int) -> set[date]:
    return {d for t in tests if START <= (d := t + timedelta(days=lag)) <= END}


def load_blind(path: Path):
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    valid = []
    seen_naids = set()
    for r in rows:
        naid = (r.get("nara_naid") or "").strip()
        ods = (r.get("occurrence_date") or "").strip()
        if not naid or not ods:
            continue
        if naid in seen_naids:
            raise SystemExit(f"fail-closed: duplicate NARA NAID in blind index: {naid}")
        seen_naids.add(naid)
        try:
            d = date.fromisoformat(ods)
        except ValueError:
            continue
        if not (START <= d <= END):
            continue
        valid.append({
            "naid": naid,
            "date": d,
            "starlike": int(r.get("starlike_screen") or 0),
            "compact": int(r.get("compact_light_screen") or 0),
            "formation": int(r.get("formation_screen") or 0),
            "radar": int(r.get("radar_screen") or 0),
            "craftlike": int(r.get("resolved_craftlike_screen") or 0),
            "disposition": (r.get("disposition_screen") or "").strip(),
        })
    return rows, valid


def aggregate(valid):
    all_cases = Counter()
    star_cases = Counter()
    compact_cases = Counter()
    for r in valid:
        d = r["date"]
        all_cases[d] += 1
        if r["starlike"]:
            star_cases[d] += 1
        if r["compact"]:
            compact_cases[d] += 1
    return all_cases, star_cases, compact_cases


def endpoint_for_window(win: set[date], all_cases, star_cases, compact_cases):
    return {
        "all_case_count": sum(all_cases[d] for d in win),
        "any_report_day_count": sum(1 for d in win if all_cases[d] > 0),
        "starlike_case_count": sum(star_cases[d] for d in win),
        "any_starlike_day_count": sum(1 for d in win if star_cases[d] > 0),
        "compact_light_case_count": sum(compact_cases[d] for d in win),
        "any_compact_light_day_count": sum(1 for d in win if compact_cases[d] > 0),
        "calendar_days_in_window": len(win),
    }


def blocked_groups(tests: list[date], mode: str):
    counts = Counter()
    for d in tests:
        key = d.year if mode == "year" else (d.year, d.month)
        counts[key] += 1
    candidates = defaultdict(list)
    for d in all_days(START, END):
        key = d.year if mode == "year" else (d.year, d.month)
        candidates[key].append(d)
    return counts, candidates


def sample_pseudo_tests(rng: random.Random, counts, candidates):
    out = []
    for key in sorted(counts, key=str):
        n = counts[key]
        pool = candidates[key]
        if n > len(pool):
            raise RuntimeError(f"block {key} asks for {n} dates from {len(pool)}")
        out.extend(rng.sample(pool, n))
    return sorted(out)


def empirical_p(obs: float, vals: list[float]):
    mu = mean(vals)
    upper = (1 + sum(v >= obs for v in vals)) / (len(vals) + 1)
    lower = (1 + sum(v <= obs for v in vals)) / (len(vals) + 1)
    twosided = min(1.0, 2.0 * min(upper, lower))
    return {
        "observed": obs,
        "null_mean": mu,
        "null_min": min(vals),
        "null_max": max(vals),
        "p_upper_positive": upper,
        "p_lower_negative": lower,
        "p_two_sided_empirical": twosided,
    }


def run_null(mode: str, tests, all_cases, star_cases, compact_cases, radius: int, n_perm: int, seed: int):
    counts, candidates = blocked_groups(tests, mode)
    rng = random.Random(seed)
    keys = [
        "all_case_count", "any_report_day_count", "starlike_case_count",
        "any_starlike_day_count", "compact_light_case_count", "any_compact_light_day_count"
    ]
    null = {k: [] for k in keys}
    for i in range(n_perm):
        pseudo = sample_pseudo_tests(rng, counts, candidates)
        ep = endpoint_for_window(window_dates(pseudo, radius), all_cases, star_cases, compact_cases)
        for k in keys:
            null[k].append(ep[k])
    observed = endpoint_for_window(window_dates(tests, radius), all_cases, star_cases, compact_cases)
    return {
        "mode": mode,
        "radius_days": radius,
        "iterations": n_perm,
        "seed": seed,
        "block_test_date_counts": {str(k): v for k, v in counts.items()},
        "endpoints": {k: empirical_p(observed[k], null[k]) for k in keys},
    }


def log_comb(n, k):
    if k < 0 or k > n:
        return float("-inf")
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)


def fisher_two_sided(a, b, c, d):
    # Table [[a,b],[c,d]] where row 1=STARLIKE, row 2=non-star;
    # col 1=nuclear +/-1, col 2=outside +/-4.
    r1, r2 = a + b, c + d
    c1 = a + c
    n = r1 + r2
    lo = max(0, c1 - r2)
    hi = min(r1, c1)
    def lp(x):
        return log_comb(r1, x) + log_comb(r2, c1 - x) - log_comb(n, c1)
    obs_lp = lp(a)
    probs = []
    for x in range(lo, hi + 1):
        l = lp(x)
        if l <= obs_lp + 1e-12:
            probs.append(math.exp(l))
    p = min(1.0, sum(probs))
    odds = (a * d / (b * c)) if b and c else (float("inf") if a and d else None)
    return odds, p


def morphology_composition(valid, tests):
    pm1 = window_dates(tests, 1)
    outside4 = set(all_days(START, END)) - window_dates(tests, 4)
    a = sum(1 for r in valid if r["starlike"] and r["date"] in pm1)
    c = sum(1 for r in valid if not r["starlike"] and r["date"] in pm1)
    b = sum(1 for r in valid if r["starlike"] and r["date"] in outside4)
    d = sum(1 for r in valid if not r["starlike"] and r["date"] in outside4)
    odds, p = fisher_two_sided(a, b, c, d)
    return {
        "table": {"starlike_pm1": a, "starlike_outside_pm4": b, "nonstarlike_pm1": c, "nonstarlike_outside_pm4": d},
        "odds_ratio": odds,
        "fisher_two_sided_p": p,
        "boundary": "Conditions on entry into reconstructed Blue Book case archive; not person-observation exposure."
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blind-index", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--permutations", type=int, default=N_PERM)
    args = ap.parse_args()

    blind = Path(args.blind_index)
    all_rows, valid = load_blind(blind)
    if not valid:
        raise SystemExit("fail-closed: no valid exact-date study-window rows")
    blind_hash = sha_file(blind)
    all_cases, star_cases, compact_cases = aggregate(valid)

    calraw = fetch(SIPRI_URL)
    tests = strict_calendar(calraw)

    exact_lags = {}
    for lag in range(-4, 5):
        win = exact_lag_dates(tests, lag)
        exact_lags[str(lag)] = endpoint_for_window(win, all_cases, star_cases, compact_cases)

    observed_windows = {}
    for radius in (1, 2, 4):
        observed_windows[f"pm{radius}"] = endpoint_for_window(window_dates(tests, radius), all_cases, star_cases, compact_cases)

    y = run_null("year", tests, all_cases, star_cases, compact_cases, 1, args.permutations, YEAR_SEED)
    ym = run_null("year_month", tests, all_cases, star_cases, compact_cases, 1, args.permutations, YEARMONTH_SEED)

    # Explicit non-nuclear positive-control epoch: July 1952.
    july = {d for d in all_days(date(1952, 7, 1), date(1952, 7, 31))}
    july_ep = endpoint_for_window(july, all_cases, star_cases, compact_cases)
    july_ep["strict_nuclear_test_dates_in_month"] = sum(1 for t in tests if t.year == 1952 and t.month == 7)

    result = {
        "runner_id": RUNNER_ID,
        "status": "PREREGISTERED_MATCHED_CONTROL_COMPLETE__ARCHIVAL_REPORT_ASSOCIATION_ONLY",
        "input": {
            "blind_index": str(blind),
            "blind_index_sha256": blind_hash,
            "rows_total": len(all_rows),
            "valid_exact_date_study_rows": len(valid),
            "unique_case_dates": len({r["date"] for r in valid}),
            "starlike_cases": sum(r["starlike"] for r in valid),
            "compact_light_cases": sum(r["compact"] for r in valid),
        },
        "nuclear_calendar": {"sha256": sha_bytes(calraw), "strict_unique_dates": len(tests)},
        "observed": {"exact_lags_minus4_to_plus4": exact_lags, "windows": observed_windows},
        "confirmatory_nulls_pm1": {"year_blocked": y, "year_month_blocked": ym},
        "morphology_composition_E6": morphology_composition(valid, tests),
        "july_1952_non_nuclear_positive_control": july_ep,
        "interpretation_rules": {
            "positive_specificity": "Requires positive-direction +/-1 endpoint surviving BOTH preregistered blocked nulls and no contradictory pre-event lag pattern.",
            "archive_zero": "Zero case rows on a date is zero reconstructed archive entries, not zero people observing the sky.",
            "causal_ceiling": "No temporal result establishes nuclear causation, UAP physical identity, extraordinary performance, or non-human origin."
        },
        "claim_ceiling": "HUMAN_REPORT_ARCHIVE_TEMPORAL_SPECIFICITY_TEST_ONLY__NARA_SPOTCHECK_AND_BLIND_MANUAL_STARLIKE_VALIDATION_REQUIRED_BEFORE_ADMISSION"
    }
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
