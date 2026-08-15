#!/usr/bin/env python3
"""JANUS JPFM-2D public-only POSS-I temporal association runner.

Downloads only two small published release tables, public nuclear-test data, and
FITS *primary header blocks* for the 642 POSS-I red plates. It never downloads a
plate image array and never consumes the closed/private 107,875-row catalogue.

Primary outcome: globally deduplicated released S0 count. Primary scientific
units: actually observed plates and actually observed nights inside the frozen
1949-11-19..1957-04-28 study interval. Unobserved calendar days are never
inserted as scientific zeros. A deliberately schedule-confounded all-calendar
2x2 is retained only as a diagnostic demonstrating why that older construction
must not be treated as the primary test.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.stats import fisher_exact
from statsmodels.discrete.discrete_model import NegativeBinomial

POSS_COMMIT = "4005e200541b321ead3d6608f0162a14430ef1c2"
POSS_BASE = f"https://raw.githubusercontent.com/jannefi/poss1-plate-slice/{POSS_COMMIT}"
REL = "results/s0-642-20260814"
S0_URL = f"{POSS_BASE}/{REL}/stage_S0.csv.gz"
TILES_URL = f"{POSS_BASE}/{REL}/tile_manifest.csv.gz"
REPAIRS_URL = f"{POSS_BASE}/{REL}/repaired_astrometry_tiles.csv"
WCS_URL = f"{POSS_BASE}/data/plate_crpix_table.csv"

S0_GZ_SHA256 = "f19cf987756c62a68f55a472992d860e73ae63b3a4664189092b0e1fda77f7bb"
TILES_GZ_SHA256 = "a1652db2d15470a9e8630a1a2ac3a055e49be65880ca615126a9aaa8cc2da02d"
S0_CSV_SHA256 = "2ff92f2210acb387ef9ef4b88d561595d3883e9aab27065042627272b96590f0"
TILES_CSV_SHA256 = "5dcb90dc5d98550e5a60246aced2b097922a267c69e81f27d45d16a288142a99"

SIPRI_COMMIT = "056ac3db13b392cb69be9f787e235738167e7fb1"
SIPRI_URL = (
    "https://raw.githubusercontent.com/data-is-plural/nuclear-explosions/"
    f"{SIPRI_COMMIT}/data/sipri-report-explosions.csv"
)
IRSA_FMT = "https://irsa.ipac.caltech.edu/data/DSS/images/dss1red/dss1red_{plate}.fits"

STUDY_START = dt.date(1949, 11, 19)
STUDY_END = dt.date(1957, 4, 28)
WINDOW_DAYS = 1
WCS_DIVERGENT_ARCSEC = 1.5
HEADER_RANGE_END = 131071
HEADER_MAX_BYTES = 1024 * 1024
HEADER_WORKERS = 10

# Frozen before any outcome is read. These acquisition geometries put the device
# in the atmosphere or at the surface. Unknown/unlisted types are excluded and
# surfaced, never silently coerced.
PHYSICAL_ATMOSPHERIC_SURFACE_TYPES = {
    "AIRDROP", "TOWER", "SURFACE", "BARGE", "BALLOON", "ROCKET", "ATMOSPH"
}

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "JANUS-JPFM-2D-public-reconstruction/1.1"})


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def get_bytes(url: str, timeout: int = 90) -> bytes:
    r = SESSION.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content


def require_hash(label: str, b: bytes, expected: str) -> None:
    got = sha256_bytes(b)
    if got != expected:
        raise RuntimeError(f"{label} sha256 mismatch: got={got} expected={expected}")


def read_release_tables():
    s0_gz, tiles_gz = get_bytes(S0_URL), get_bytes(TILES_URL)
    require_hash("stage_S0.csv.gz", s0_gz, S0_GZ_SHA256)
    require_hash("tile_manifest.csv.gz", tiles_gz, TILES_GZ_SHA256)
    s0_csv, tiles_csv = gzip.decompress(s0_gz), gzip.decompress(tiles_gz)
    require_hash("stage_S0.csv", s0_csv, S0_CSV_SHA256)
    require_hash("tile_manifest.csv", tiles_csv, TILES_CSV_SHA256)
    repairs_b, wcs_b = get_bytes(REPAIRS_URL), get_bytes(WCS_URL)
    return (
        pd.read_csv(io.BytesIO(s0_csv)),
        pd.read_csv(io.BytesIO(tiles_csv)),
        pd.read_csv(io.BytesIO(repairs_b)),
        pd.read_csv(io.BytesIO(wcs_b)),
        {
            "stage_S0_gz_sha256": sha256_bytes(s0_gz),
            "stage_S0_csv_sha256": sha256_bytes(s0_csv),
            "tile_manifest_gz_sha256": sha256_bytes(tiles_gz),
            "tile_manifest_csv_sha256": sha256_bytes(tiles_csv),
            "repaired_astrometry_tiles_sha256": sha256_bytes(repairs_b),
            "plate_crpix_table_sha256": sha256_bytes(wcs_b),
        },
    )


def find_fits_header_end(buf: bytes):
    for i in range(len(buf) // 80):
        if buf[i * 80:i * 80 + 8] == b"END     ":
            logical_end = (i + 1) * 80
            block_end = ((logical_end + 2879) // 2880) * 2880
            if len(buf) >= block_end:
                return block_end
    return None


def parse_card_value(raw: str):
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("'"):
        out, i = [], 1
        while i < len(raw):
            if raw[i] == "'":
                if i + 1 < len(raw) and raw[i + 1] == "'":
                    out.append("'"); i += 2; continue
                break
            out.append(raw[i]); i += 1
        return "".join(out).strip()
    token = raw.split("/", 1)[0].strip()
    if token in ("T", "F"):
        return token == "T"
    try:
        if any(c in token.upper() for c in (".", "E", "D")):
            return float(token.replace("D", "E"))
        return int(token)
    except Exception:
        return token


def parse_date_obs(x):
    if x is None:
        return None
    s = str(x).strip()
    # ISO timestamps are tolerated by intentionally taking the date component.
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        try:
            return dt.date.fromisoformat(s[:10])
        except ValueError:
            pass
    for fmt in ("%d/%m/%y", "%m/%d/%y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            d = dt.datetime.strptime(s, fmt).date()
            if d.year < 1930:
                d = d.replace(year=d.year + 100)
            return d
        except ValueError:
            pass
    return None


def plate_ra_deg(kv):
    try:
        return 15.0 * (float(kv["PLTRAH"]) + float(kv["PLTRAM"]) / 60.0 + float(kv["PLTRAS"]) / 3600.0)
    except Exception:
        return None


def plate_dec_deg(kv):
    try:
        mag = abs(float(kv["PLTDECD"])) + float(kv["PLTDECM"]) / 60.0 + float(kv["PLTDECS"]) / 3600.0
        return -mag if str(kv.get("PLTDECSN", "+")).strip() == "-" else mag
    except Exception:
        return None


def galactic_lat_deg(ra_deg: float, dec_deg: float) -> float:
    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    ra_ngp, dec_ngp = math.radians(192.85948), math.radians(27.12825)
    sb = math.sin(dec) * math.sin(dec_ngp) + math.cos(dec) * math.cos(dec_ngp) * math.cos(ra - ra_ngp)
    return math.degrees(math.asin(max(-1.0, min(1.0, sb))))


def parse_fits_header(plate, url, header, status, response_headers):
    kv = {}
    for i in range(0, len(header), 80):
        c = header[i:i + 80].decode("ascii", errors="replace")
        key = c[:8].strip()
        if key == "END":
            break
        if len(c) >= 10 and c[8:10] == "= ":
            kv[key] = parse_card_value(c[10:])
    date_obs = parse_date_obs(kv.get("DATE-OBS"))
    if date_obs is None:
        raise RuntimeError(f"{plate}: DATE-OBS missing/unparseable: {kv.get('DATE-OBS')!r}")
    try:
        exposure_min = float(kv.get("EXPOSURE"))
    except Exception:
        raise RuntimeError(f"{plate}: EXPOSURE missing/non-numeric: {kv.get('EXPOSURE')!r}")
    ra, dec = plate_ra_deg(kv), plate_dec_deg(kv)
    return {
        "plate_id": plate, "date_obs": date_obs.isoformat(), "exposure_min": exposure_min,
        "plate_ra_deg": ra, "plate_dec_deg": dec,
        "galactic_b_deg": galactic_lat_deg(ra, dec) if ra is not None and dec is not None else None,
        "region": kv.get("REGION"), "telescope": kv.get("TELESCOP"),
        "header_bytes": len(header), "header_sha256": sha256_bytes(header),
        "http_status": status, "content_range": response_headers.get("Content-Range"), "source_url": url,
    }


def fetch_primary_header(plate: str) -> dict:
    url, last_err = IRSA_FMT.format(plate=plate), None
    for attempt in range(4):
        try:
            # A dedicated request is used per thread; we close immediately after the
            # padded primary header block even if a server ignores Range and says 200.
            with requests.get(
                url,
                headers={"Range": f"bytes=0-{HEADER_RANGE_END}", "Accept-Encoding": "identity", "User-Agent": SESSION.headers["User-Agent"]},
                stream=True, timeout=(20, 60),
            ) as r:
                if r.status_code not in (200, 206):
                    r.raise_for_status()
                data = bytearray()
                for chunk in r.iter_content(chunk_size=16384):
                    if not chunk:
                        continue
                    data.extend(chunk)
                    end = find_fits_header_end(data)
                    if end is not None:
                        return parse_fits_header(plate, url, bytes(data[:end]), r.status_code, r.headers)
                    if len(data) > HEADER_MAX_BYTES:
                        raise RuntimeError("primary header exceeded 1 MiB safety cap")
                raise RuntimeError("FITS END card not found before stream ended")
        except Exception as e:
            last_err = e; time.sleep(attempt + 1)
    raise RuntimeError(f"{plate}: header fetch failed after retries: {last_err}")


def fetch_all_headers(plates):
    rows, errors = [], []
    with cf.ThreadPoolExecutor(max_workers=HEADER_WORKERS) as ex:
        futs = {ex.submit(fetch_primary_header, p): p for p in plates}
        for done, fut in enumerate(cf.as_completed(futs), 1):
            try:
                rows.append(fut.result())
            except Exception as e:
                errors.append(str(e))
            if done % 50 == 0 or done == len(futs):
                print(f"[headers] {done}/{len(futs)}", flush=True)
    if errors:
        raise RuntimeError("header gate failed: " + " | ".join(errors[:10]))
    return pd.DataFrame(rows).sort_values("plate_id").reset_index(drop=True)


def read_nuclear_calendar():
    b = get_bytes(SIPRI_URL)
    df = pd.read_csv(io.BytesIO(b))
    df["event_date"] = pd.to_datetime(df["date_long"].astype(str), format="%Y%m%d", errors="raise").dt.date
    w = df[(df.event_date >= STUDY_START) & (df.event_date <= STUDY_END)].copy()
    w["type"] = w["type"].fillna("").astype(str).str.strip().str.upper()
    all_dates = sorted(set(w.event_date))
    non_uw_dates = sorted(set(w.loc[w.type != "UW", "event_date"]))
    physical_dates = sorted(set(w.loc[w.type.isin(PHYSICAL_ATMOSPHERIC_SURFACE_TYPES), "event_date"]))
    duplicate_dates = sorted(d.isoformat() for d, n in Counter(w.event_date).items() if n > 1)
    if len(w) != 128 or len(all_dates) != 125 or len(non_uw_dates) != 123:
        raise RuntimeError(f"nuclear invariant failed: records={len(w)} all={len(all_dates)} nonUW={len(non_uw_dates)}")
    return {
        "OPEN_ALL_REPORTED_125": all_dates,
        "OPEN_NON_UW_123": non_uw_dates,
        "PHYSICAL_ATMOSPHERIC_SURFACE": physical_dates,
    }, {
        "source_url": SIPRI_URL, "source_sha256": sha256_bytes(b), "source_commit": SIPRI_COMMIT,
        "records_in_window": len(w), "all_unique_dates": len(all_dates), "non_uw_unique_dates": len(non_uw_dates),
        "physical_unique_dates": len(physical_dates), "same_day_duplicate_dates": duplicate_dates,
        "type_census": dict(sorted(Counter(w.type).items())),
        "physical_allowed_types_frozen": sorted(PHYSICAL_ATMOSPHERIC_SURFACE_TYPES),
        "types_excluded_from_physical_arm": sorted(set(w.type) - PHYSICAL_ATMOSPHERIC_SURFACE_TYPES),
        "paper_reported_124": "NOT_EXECUTED_MEMBERSHIP_UNRESOLVED",
    }


def in_window(d: dt.date, dates, radius=WINDOW_DAYS):
    return int(any(abs((d - x).days) <= radius for x in dates))


def zscore(series):
    s = pd.to_numeric(series, errors="coerce").astype(float)
    med = float(s.median()); s = s.fillna(med); sd = float(s.std(ddof=0))
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(np.zeros(len(s)), index=s.index), {"median": med, "sd": sd}
    return (s - float(s.mean())) / sd, {"mean": float(s.mean()), "median": med, "sd": sd}


def design_matrix(df, exposure_col):
    out = pd.DataFrame(index=df.index); out["intercept"] = 1.0; out["nuclear_window"] = df[exposure_col].astype(float)
    scalers = {}
    for src, dst in [("wcs_offset_arcsec", "wcs_z"), ("exposure_min", "exposure_z"), ("plate_dec_deg", "dec_z"), ("abs_galactic_b_deg", "abs_gal_b_z")]:
        out[dst], scalers[src] = zscore(df[src])
    doy = pd.to_datetime(df["date_obs"]).dt.dayofyear.astype(float)
    out["season_sin"] = np.sin(2 * np.pi * doy / 365.2425); out["season_cos"] = np.cos(2 * np.pi * doy / 365.2425)
    return out.astype(float), scalers


def fit_nb(df, outcome, exposure_col, opportunity_col):
    d = df.copy().reset_index(drop=True); X, scalers = design_matrix(d, exposure_col)
    y = d[outcome].astype(float).to_numpy(); opp = d[opportunity_col].astype(float).to_numpy()
    if np.any(opp <= 0):
        raise RuntimeError("non-positive NB opportunity")
    res = NegativeBinomial(y, X.to_numpy(), offset=np.log(opp), loglike_method="nb2").fit(disp=0, maxiter=500)
    names = list(X.columns) + ["alpha"]
    params, pvals = dict(zip(names, map(float, res.params))), dict(zip(names, map(float, res.pvalues)))
    ci = np.asarray(res.conf_int(), dtype=float); idx = names.index("nuclear_window"); beta = params["nuclear_window"]
    lo, hi = map(float, ci[idx])
    return {
        "n": int(len(d)), "outcome": outcome, "opportunity": opportunity_col,
        "converged": bool(getattr(res, "mle_retvals", {}).get("converged", True)),
        "log_likelihood": float(res.llf), "aic": float(res.aic), "alpha": params.get("alpha"),
        "nuclear_beta": beta, "nuclear_se": float(res.bse[idx]), "nuclear_p_two_sided": pvals["nuclear_window"],
        "irr": float(math.exp(beta)), "irr_ci95": [float(math.exp(lo)), float(math.exp(hi))],
        "covariates": list(X.columns[2:]), "scalers": scalers,
    }


def aggregate_nights(plates, outcome):
    rows = []
    for date_obs, g in plates.groupby("date_obs", sort=True):
        weights = g.tile_count.astype(float).to_numpy()
        def wm(col):
            x = pd.to_numeric(g[col], errors="coerce").astype(float).to_numpy(); good = np.isfinite(x)
            return float(np.average(x[good], weights=weights[good])) if good.any() else float("nan")
        rows.append({
            "date_obs": date_obs, outcome: int(g[outcome].sum()), "tile_count": int(g.tile_count.sum()), "n_plates": int(len(g)),
            "wcs_offset_arcsec": wm("wcs_offset_arcsec"), "exposure_min": wm("exposure_min"),
            "plate_dec_deg": wm("plate_dec_deg"), "abs_galactic_b_deg": wm("abs_galactic_b_deg"),
            "has_repaired_tile": int(g.has_repaired_tile.max()),
        })
    return pd.DataFrame(rows)


def rate_summary(df, outcome, exp_col, opp_col):
    a, b = df[df[exp_col] == 1], df[df[exp_col] == 0]
    ya, yb = float(a[outcome].sum()), float(b[outcome].sum()); oa, ob = float(a[opp_col].sum()), float(b[opp_col].sum())
    ra, rb = (ya / oa if oa else float("nan")), (yb / ob if ob else float("nan"))
    return {"exposed_units": int(len(a)), "unexposed_units": int(len(b)), "exposed_count": int(ya), "unexposed_count": int(yb),
            "exposed_opportunity": oa, "unexposed_opportunity": ob, "rate_exposed": ra, "rate_unexposed": rb,
            "crude_rate_ratio": float(ra / rb) if rb > 0 else None}


def fisher_any_candidate(nights, exp_col):
    d = nights.copy(); d["any"] = (d.candidate_count > 0).astype(int)
    tab = pd.crosstab(d[exp_col], d["any"]).reindex(index=[0, 1], columns=[0, 1], fill_value=0)
    table = [[int(tab.loc[1, 1]), int(tab.loc[1, 0])], [int(tab.loc[0, 1]), int(tab.loc[0, 0])]]
    if tab[0].sum() == 0 or tab[1].sum() == 0:
        return {"table_exposed_unexposed_by_any_none": table, "status": "SATURATED_OR_NO_VARIATION"}
    odds, p = fisher_exact(table, alternative="two-sided")
    return {"table_exposed_unexposed_by_any_none": table, "odds_ratio": float(odds), "p_two_sided": float(p)}


def all_calendar_schedule_confounded_diagnostic(nights, dates):
    observed_any = {dt.date.fromisoformat(r.date_obs): int(r.candidate_count > 0) for r in nights.itertuples()}
    rows, d = [], STUDY_START
    while d <= STUDY_END:
        rows.append((in_window(d, dates), observed_any.get(d, 0), int(d in observed_any))); d += dt.timedelta(days=1)
    tab = np.zeros((2, 2), dtype=int)
    for exposed, event, _observed in rows:
        tab[exposed, event] += 1
    table = [[int(tab[1, 1]), int(tab[1, 0])], [int(tab[0, 1]), int(tab[0, 0])]]
    odds, p = fisher_exact(table, alternative="two-sided")
    return {
        "status": "INTENTIONALLY_SCHEDULE_CONFOUNDED_DIAGNOSTIC_NOT_PRIMARY_EVIDENCE",
        "unobserved_calendar_days_encoded_as_zero_only_here": True,
        "table_exposed_unexposed_by_any_none": table, "odds_ratio": float(odds), "p_two_sided": float(p),
        "observed_nights": int(sum(x[2] for x in rows)), "calendar_days": len(rows),
    }


def nuisance_residual_shift_test(nights, outcome, dates):
    d = nights.copy().reset_index(drop=True); d["null_exposure"] = 0
    X, _ = design_matrix(d, "null_exposure"); X = X.drop(columns=["nuclear_window"])
    y, opp = d[outcome].astype(float).to_numpy(), d.tile_count.astype(float).to_numpy()
    m = NegativeBinomial(y, X.to_numpy(), offset=np.log(opp), loglike_method="nb2").fit(disp=0, maxiter=500)
    mu, alpha = np.asarray(m.predict(), dtype=float), float(m.params[-1])
    resid = (y - mu) / np.sqrt(np.maximum(mu + alpha * mu * mu, 1e-12))
    obs_dates = [dt.date.fromisoformat(x) for x in d.date_obs.astype(str)]; span = (STUDY_END - STUDY_START).days + 1
    def shifted(k):
        return [STUDY_START + dt.timedelta(days=((x - STUDY_START).days + k) % span) for x in dates]
    def score(cal):
        z = np.array([in_window(x, cal) for x in obs_dates], dtype=float)
        if z.std() == 0: return 0.0
        z = (z - z.mean()) / z.std(); return float(np.dot(z, resid) / math.sqrt(len(z)))
    observed = score(dates); null = np.array([score(shifted(k)) for k in range(1, span)], dtype=float)
    return {
        "method": "exhaustive_circular_shift_of_entire_nuclear_calendar_against_fixed_observation_schedule",
        "n_nonzero_shifts": int(len(null)), "score_observed": observed, "null_mean": float(null.mean()), "null_sd": float(null.std(ddof=1)),
        "empirical_p_two_sided": float((1 + np.sum(np.abs(null) >= abs(observed))) / (len(null) + 1)),
        "preserves": ["Palomar observation dates", "nuclear-event spacing", "nuisance-only expected count surface"],
    }


def build_plate_table(s0, tiles, repairs, wcs, headers):
    if len(s0) != 122820 or len(tiles) != 31458:
        raise RuntimeError(f"release invariant failed S0={len(s0)} tiles={len(tiles)}")
    tile_map = tiles[["tile_id", "plate_id"]].drop_duplicates()
    if tile_map.tile_id.duplicated().any(): raise RuntimeError("tile_id maps to multiple plates")
    joined = s0.merge(tile_map, on="tile_id", how="left", validate="many_to_one")
    if joined.plate_id.isna().any(): raise RuntimeError("final S0 tile->plate join incomplete")
    plates = sorted(tiles.plate_id.dropna().astype(str).unique())
    if len(plates) != 642: raise RuntimeError(f"expected 642 plates, got {len(plates)}")
    final_counts = joined.groupby("plate_id").size().rename("candidate_count")
    pre_counts = tiles.groupby("plate_id").rows_emitted_to_S0.sum().rename("candidate_count_pre_dedup")
    tile_counts = tiles.groupby("plate_id").size().rename("tile_count")
    p = pd.DataFrame(index=pd.Index(plates, name="plate_id")).join([final_counts, pre_counts, tile_counts]).fillna(0).reset_index()
    for c in ("candidate_count", "candidate_count_pre_dedup", "tile_count"): p[c] = p[c].astype(int)
    w = wcs.rename(columns={"plate": "plate_id", "offset_arcsec": "wcs_offset_arcsec"})
    p = p.merge(w[["plate_id", "wcs_offset_arcsec", "status"]], on="plate_id", how="left", validate="one_to_one")
    if p.wcs_offset_arcsec.isna().any(): raise RuntimeError("WCS table join incomplete")
    p["wcs_divergent_gt_1p5"] = (p.wcs_offset_arcsec.astype(float) > WCS_DIVERGENT_ARCSEC).astype(int)
    repaired = set(repairs.loc[repairs.action.astype(str) == "repaired", "plate"].astype(str))
    p["has_repaired_tile"] = p.plate_id.isin(repaired).astype(int)
    p = p.merge(headers, on="plate_id", how="left", validate="one_to_one")
    if p.date_obs.isna().any(): raise RuntimeError("header join incomplete")
    p["abs_galactic_b_deg"] = p.galactic_b_deg.abs()
    return p, joined


def run_arm(plate_df, dates, arm_id):
    p = plate_df.copy(); p["nuclear_window"] = [in_window(dt.date.fromisoformat(x), dates) for x in p.date_obs]
    nights = aggregate_nights(p, "candidate_count"); nights["nuclear_window"] = [in_window(dt.date.fromisoformat(x), dates) for x in nights.date_obs]
    q = p[p.has_repaired_tile == 0].copy()
    return {
        "calendar_arm": arm_id, "nuclear_unique_dates": len(dates), "window_days_each_side": WINDOW_DAYS,
        "plate_level": {
            "final_s0_rate": rate_summary(p, "candidate_count", "nuclear_window", "tile_count"),
            "final_s0_nb_adjusted": fit_nb(p, "candidate_count", "nuclear_window", "tile_count"),
            "pre_dedup_rate": rate_summary(p, "candidate_count_pre_dedup", "nuclear_window", "tile_count"),
            "pre_dedup_nb_adjusted": fit_nb(p, "candidate_count_pre_dedup", "nuclear_window", "tile_count"),
        },
        "night_level": {
            "n_observed_nights": int(len(nights)),
            "final_s0_rate": rate_summary(nights, "candidate_count", "nuclear_window", "tile_count"),
            "final_s0_nb_adjusted": fit_nb(nights, "candidate_count", "nuclear_window", "tile_count"),
            "fisher_any_candidate_observed_nights_only": fisher_any_candidate(nights, "nuclear_window"),
            "schedule_preserving_shift": nuisance_residual_shift_test(nights, "candidate_count", dates),
        },
        "all_calendar_diagnostic": all_calendar_schedule_confounded_diagnostic(nights, dates),
        "exclude_repaired_plate_sensitivity": {"n_plates": int(len(q)), "final_s0_nb_adjusted": fit_nb(q, "candidate_count", "nuclear_window", "tile_count")},
    }


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True, type=Path); args = ap.parse_args(); args.out.parent.mkdir(parents=True, exist_ok=True)
    print("[1/6] download + hash-gate small POSS release", flush=True)
    s0, tiles, repairs, wcs, hashes = read_release_tables()
    plates = sorted(tiles.plate_id.dropna().astype(str).unique())
    print(f"[2/6] stream {len(plates)} primary FITS headers with {HEADER_WORKERS} workers", flush=True)
    headers = fetch_all_headers(plates)
    print("[3/6] exact tile->plate->date join + frozen temporal scope", flush=True)
    all_plates, joined = build_plate_table(s0, tiles, repairs, wcs, headers)
    all_plates["date_obj"] = pd.to_datetime(all_plates.date_obs).dt.date
    plate_df = all_plates[(all_plates.date_obj >= STUDY_START) & (all_plates.date_obj <= STUDY_END)].copy().drop(columns=["date_obj"])
    if plate_df.empty: raise RuntimeError("study-window filter produced zero plates")
    print(f"[scope] 642 footprint plates -> {len(plate_df)} plates in frozen temporal window", flush=True)
    print("[4/6] fetch + invariant-gate nuclear calendar", flush=True)
    calendars, nuclear_meta = read_nuclear_calendar()
    print("[5/6] run frozen association arms", flush=True)
    arms = {}
    for arm_id in ("OPEN_ALL_REPORTED_125", "OPEN_NON_UW_123", "PHYSICAL_ATMOSPHERIC_SURFACE"):
        print("  ->", arm_id, flush=True); arms[arm_id] = run_arm(plate_df, calendars[arm_id], arm_id)

    obs = sorted(set(plate_df.date_obs.astype(str))); all_obs = sorted(set(all_plates.date_obs.astype(str)))
    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-2D-OPEN-TEMPORAL-ASSOCIATION-RUN-001",
        "experiment_id": "JPFM-2D", "schema_version": "1.1", "date": dt.date.today().isoformat(), "status": "EXECUTED",
        "claim_ceiling": "PUBLIC_ONLY_INDEPENDENT_TEMPORAL_ASSOCIATION_TEST__S0_CANDIDATES_ARE_NOT_CONFIRMED_TRANSIENTS__NO_NUCLEAR_CAUSALITY_OR_ORIGIN_CLAIM",
        "parents": ["data/JANUS-PALOMAR-JPFM-2C-OPEN-RECONSTRUCTION-ADMISSION-v1.0.json"],
        "bindings": {"poss_repository": "jannefi/poss1-plate-slice", "poss_commit": POSS_COMMIT, "poss_release": REL, "release_hashes": hashes,
                     "nuclear_repository": "data-is-plural/nuclear-explosions", "nuclear_meta": nuclear_meta},
        "io_gate": {"full_plate_image_arrays_downloaded": False, "fits_header_workers": HEADER_WORKERS,
                    "header_range_requested_bytes": HEADER_RANGE_END + 1, "header_per_plate_safety_cap_bytes": HEADER_MAX_BYTES,
                    "headers_total_bytes": int(headers.header_bytes.sum()),
                    "header_http_status_census": {str(k): int(v) for k, v in headers.http_status.value_counts().sort_index().items()},
                    "exposure_keyword": "EXPOSURE", "exposure_unit": "minutes"},
        "cohort": {
            "released_stage_S0_rows": int(len(s0)), "released_tile_manifest_rows": int(len(tiles)), "released_footprint_plates": int(len(all_plates)),
            "released_unique_nights_all_dates": int(len(all_obs)), "released_first_date": min(all_obs), "released_last_date": max(all_obs),
            "study_window": [STUDY_START.isoformat(), STUDY_END.isoformat()], "analyzed_plates": int(len(plate_df)),
            "analyzed_unique_nights": int(len(obs)), "analyzed_first_date": min(obs), "analyzed_last_date": max(obs),
            "analyzed_final_candidate_count": int(plate_df.candidate_count.sum()), "analyzed_pre_dedup_count": int(plate_df.candidate_count_pre_dedup.sum()),
            "all_122820_release_rows_joined_to_plate": bool(len(joined) == len(s0) and joined.plate_id.notna().all()),
            "tiles_per_plate_census_analyzed": {str(k): int(v) for k, v in plate_df.tile_count.value_counts().sort_index().items()},
            "repaired_tile_plates_in_analyzed_scope": sorted(plate_df.loc[plate_df.has_repaired_tile == 1, "plate_id"].tolist()),
            "wcs_divergent_gt_1p5_plates_analyzed": int(plate_df.wcs_divergent_gt_1p5.sum()), "wcs_threshold_arcsec_frozen": WCS_DIVERGENT_ARCSEC,
            "exposure_min_summary_analyzed": {"min": float(plate_df.exposure_min.min()), "median": float(plate_df.exposure_min.median()), "max": float(plate_df.exposure_min.max())},
        },
        "paper_reported_124_arm": {"status": "NOT_EXECUTED_MEMBERSHIP_UNRESOLVED",
            "reason": "The paper reports 124 above-ground test dates but does not publish a frozen machine-readable membership list. JANUS does not guess the discordant date."},
        "analysis_contract": {
            "primary_outcome": "globally deduplicated stage_S0 candidate_count", "primary_units": ["observed plate", "observed night"],
            "opportunity": "processed tile count", "unobserved_calendar_days_treated_as_scientific_zero": False,
            "nuclear_window": "test_date +/- 1 day", "primary_model": "NB2 count model with log(tile_count) offset and frozen nuisance covariates",
            "nuisance_covariates": ["continuous WCS correction magnitude", "EXPOSURE minutes", "plate centre declination", "absolute galactic latitude", "annual sine/cosine season"],
            "sensitivity_arms": ["pre-dedup count", "exclude five plates containing repaired WCS tiles if they fall in temporal scope", "exhaustive circular calendar shift", "intentionally confounded all-calendar 2x2 diagnostic"]},
        "calendar_arms": arms,
    }
    signs, nb_sig, shift_sig = [], [], []
    for a in arms.values():
        nb, sh = a["night_level"]["final_s0_nb_adjusted"], a["night_level"]["schedule_preserving_shift"]
        signs.append(int(np.sign(nb["nuclear_beta"]))); nb_sig.append(nb["nuclear_p_two_sided"] < .05); shift_sig.append(sh["empirical_p_two_sided"] < .05)
    robust = len(set(signs)) == 1 and all(nb_sig) and all(shift_sig)
    result["aggregate_verdict"] = {
        "robust_across_executed_calendar_arms": bool(robust),
        "code": "OPEN_TEMPORAL_ASSOCIATION_SURVIVES_FROZEN_CONTROLS" if robust else "OPEN_TEMPORAL_ASSOCIATION_NOT_ROBUST_ACROSS_FROZEN_CONTROLS",
        "interpretation": "Robustness requires common direction plus p<0.05 in both adjusted nightly NB and schedule-preserving circular-shift tests for every executed public calendar arm. Association never implies causality or origin."}
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    result["integrity"] = {"canonical_payload_sha256_without_integrity": sha256_bytes(canonical)}
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("[6/6] wrote", args.out); print("VERDICT", result["aggregate_verdict"]["code"])
    for arm_id, a in arms.items():
        nb, sh = a["night_level"]["final_s0_nb_adjusted"], a["night_level"]["schedule_preserving_shift"]
        print(arm_id, "IRR", nb["irr"], "p_NB", nb["nuclear_p_two_sided"], "p_shift", sh["empirical_p_two_sided"])


if __name__ == "__main__":
    main()
