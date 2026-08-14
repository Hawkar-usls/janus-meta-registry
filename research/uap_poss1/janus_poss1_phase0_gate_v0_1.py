#!/usr/bin/env python3
"""JANUS POSS-I Phase-0 fail-closed intake and plate-day exposure builder.

This tool does not infer scientific truth from unavailable data. It freezes byte
identity, validates the exact VASCO input family, reconciles catalog/daily counts,
and builds a plate-day matrix only from explicitly mapped columns.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

RUNNER_ID = "JANUS-POSS1-PHASE0-GATE-v0.1"
EXPECTED = {
    "catalog_rows": 107875,
    "catalog_unique_plates": 635,
    "daily_rows": 2718,
    "daily_transient_total_reported": 107862,
    "study_start": "1949-11-19",
    "study_end": "1957-04-28",
}


def sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".csv":
        return pd.read_csv(path, low_memory=False)
    if suffix in {".tsv", ".txt"}:
        return pd.read_csv(path, sep="\t", low_memory=False)
    raise ValueError(f"unsupported table format: {path}")


def load_mapping(path: Path) -> dict[str, str]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("mapping must be a JSON object")
    return {str(k): str(v) for k, v in obj.items()}


def require_columns(df: pd.DataFrame, mapping: dict[str, str], required: list[str], label: str) -> None:
    missing_keys = [k for k in required if k not in mapping]
    if missing_keys:
        raise ValueError(f"{label}: mapping missing keys {missing_keys}")
    missing_cols = [mapping[k] for k in required if mapping[k] not in df.columns]
    if missing_cols:
        raise ValueError(f"{label}: mapped columns not found {missing_cols}; available={list(df.columns)}")


def iso_date_series(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, utc=True, errors="coerce")
    if dt.isna().any():
        bad = int(dt.isna().sum())
        raise ValueError(f"timestamp/date parse failed for {bad} rows")
    return dt.dt.strftime("%Y-%m-%d")


def audit_file(path: Path) -> dict[str, Any]:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_path(path)}


def validate_catalog(path: Path, mapping: dict[str, str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = load_table(path)
    require_columns(df, mapping, ["plate_id", "timestamp_utc"], "catalog")
    plates = df[mapping["plate_id"]].astype(str).str.strip()
    if (plates == "").any() or plates.isna().any():
        raise ValueError("catalog: blank plate IDs")
    dates = iso_date_series(df[mapping["timestamp_utc"]])
    report = audit_file(path)
    report.update({
        "rows": int(len(df)),
        "unique_plate_ids": int(plates.nunique()),
        "first_observation_date": str(dates.min()),
        "last_observation_date": str(dates.max()),
        "expected_rows": EXPECTED["catalog_rows"],
        "expected_unique_plates": EXPECTED["catalog_unique_plates"],
        "row_count_match": len(df) == EXPECTED["catalog_rows"],
        "plate_count_match": plates.nunique() == EXPECTED["catalog_unique_plates"],
    })
    return df, report


def validate_daily(path: Path, mapping: dict[str, str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = load_table(path)
    require_columns(df, mapping, ["date", "transient_count"], "daily")
    dates = iso_date_series(df[mapping["date"]])
    counts = pd.to_numeric(df[mapping["transient_count"]], errors="coerce")
    if counts.isna().any():
        raise ValueError("daily: non-numeric transient_count")
    total = int(counts.sum())
    report = audit_file(path)
    report.update({
        "rows": int(len(df)), "transient_total": total,
        "first_date": str(dates.min()), "last_date": str(dates.max()),
        "expected_rows": EXPECTED["daily_rows"],
        "expected_transient_total_reported": EXPECTED["daily_transient_total_reported"],
        "row_count_match": len(df) == EXPECTED["daily_rows"],
        "reported_total_match": total == EXPECTED["daily_transient_total_reported"],
        "study_span_match": dates.min() == EXPECTED["study_start"] and dates.max() == EXPECTED["study_end"],
    })
    return df, report


def validate_nuclear(path: Path, mapping: dict[str, str]) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = load_table(path)
    require_columns(df, mapping, ["test_id", "date", "country", "above_ground"], "nuclear")
    dates = iso_date_series(df[mapping["date"]])
    normalized = df[mapping["above_ground"]].astype(str).str.strip().str.lower().map({
        "1": True, "true": True, "yes": True, "y": True,
        "0": False, "false": False, "no": False, "n": False,
    })
    if normalized.isna().any():
        raise ValueError("nuclear: above_ground must be explicit boolean-like values")
    ids = df[mapping["test_id"]].astype(str)
    if ids.duplicated().any():
        raise ValueError("nuclear: duplicate test_id")
    report = audit_file(path)
    report.update({
        "rows": int(len(df)), "above_ground_rows": int(normalized.sum()),
        "countries": sorted(df[mapping["country"]].astype(str).unique().tolist()),
        "first_date": str(dates.min()), "last_date": str(dates.max()),
    })
    return df, report


def build_matrix(catalog, catalog_map, nuclear, nuclear_map, plate_meta=None, plate_map=None) -> pd.DataFrame:
    c = pd.DataFrame({
        "plate_id": catalog[catalog_map["plate_id"]].astype(str).str.strip(),
        "obs_timestamp_utc": pd.to_datetime(catalog[catalog_map["timestamp_utc"]], utc=True, errors="raise"),
    })
    c["obs_date_utc"] = c["obs_timestamp_utc"].dt.strftime("%Y-%m-%d")
    if "validated_score" in catalog_map and catalog_map["validated_score"] in catalog.columns:
        c["validated_score"] = pd.to_numeric(catalog[catalog_map["validated_score"]], errors="coerce")
    grouped = c.groupby(["plate_id", "obs_date_utc"], as_index=False).agg(
        candidate_count=("plate_id", "size"),
        first_candidate_timestamp_utc=("obs_timestamp_utc", "min"),
        last_candidate_timestamp_utc=("obs_timestamp_utc", "max"),
    )
    if "validated_score" in c.columns:
        val = c.assign(is_validated=c["validated_score"] >= 0.5).groupby(
            ["plate_id", "obs_date_utc"], as_index=False
        )["is_validated"].sum().rename(columns={"is_validated": "candidate_count_ml_ge_0_5"})
        grouped = grouped.merge(val, on=["plate_id", "obs_date_utc"], how="left", validate="one_to_one")

    if plate_meta is not None:
        if plate_map is None:
            raise ValueError("plate_map required with plate_meta")
        require_columns(plate_meta, plate_map, ["plate_id"], "plate_meta")
        pm = plate_meta.copy()
        pm["__plate_id"] = pm[plate_map["plate_id"]].astype(str).str.strip()
        if pm["__plate_id"].duplicated().any():
            raise ValueError("plate_meta: plate_id must be unique")
        keep = ["__plate_id"]
        rename = {"__plate_id": "plate_id"}
        for key in ["exposure_seconds", "plate_area_deg2", "copy_generation", "scanner", "survey_code", "emulsion", "plate_center_ra_deg", "plate_center_dec_deg"]:
            col = plate_map.get(key)
            if col and col in pm.columns:
                keep.append(col); rename[col] = key
        grouped = grouped.merge(pm[keep].rename(columns=rename), on="plate_id", how="left", validate="many_to_one")

    if "exposure_seconds" in grouped.columns and "plate_area_deg2" in grouped.columns:
        exp_s = pd.to_numeric(grouped["exposure_seconds"], errors="coerce")
        area = pd.to_numeric(grouped["plate_area_deg2"], errors="coerce")
        grouped["exposure_deg2_min"] = area * exp_s / 60.0
        grouped["exposure_kind"] = "deg2_min"
    else:
        grouped["exposure_deg2_min"] = math.nan
        grouped["exposure_kind"] = "plate_day_count_only__NOT_AREA_TIME_NORMALIZED"

    n = pd.DataFrame({
        "test_id": nuclear[nuclear_map["test_id"]].astype(str),
        "date": pd.to_datetime(nuclear[nuclear_map["date"]], utc=True, errors="raise").dt.normalize(),
        "above_ground_raw": nuclear[nuclear_map["above_ground"]],
    })
    truth = n["above_ground_raw"].astype(str).str.strip().str.lower().map({
        "1": True, "true": True, "yes": True, "y": True,
        "0": False, "false": False, "no": False, "n": False,
    })
    n = n[truth == True].copy()  # noqa: E712
    test_dates = set(n["date"].dt.date.tolist())
    obs_dates = pd.to_datetime(grouped["obs_date_utc"], utc=True).dt.date
    for lag in range(-4, 5):
        grouped[f"nuclear_lag_{lag:+d}"] = [((d - timedelta(days=lag)) in test_dates) for d in obs_dates]
    grouped["nuclear_window_m1_p1"] = grouped[["nuclear_lag_-1", "nuclear_lag_+0", "nuclear_lag_+1"]].any(axis=1)
    grouped["nuclear_window_m2_p2"] = grouped[[f"nuclear_lag_{lag:+d}" for lag in range(-2, 3)]].any(axis=1)
    grouped["nuclear_window_m4_p4"] = grouped[[f"nuclear_lag_{lag:+d}" for lag in range(-4, 5)]].any(axis=1)
    grouped["nuclear_test_count_m1_p1"] = [sum(1 for td in test_dates if abs((td - d).days) <= 1) for d in obs_dates]
    return grouped.sort_values(["obs_date_utc", "plate_id"]).reset_index(drop=True)


def cmd_validate(args) -> int:
    catalog_map, daily_map, nuclear_map = map(lambda x: load_mapping(Path(x)), [args.catalog_map, args.daily_map, args.nuclear_map])
    catalog, cr = validate_catalog(Path(args.catalog), catalog_map)
    _, dr = validate_daily(Path(args.daily), daily_map)
    _, nr = validate_nuclear(Path(args.nuclear), nuclear_map)
    delta = int(len(catalog) - dr["transient_total"])
    hard = cr["row_count_match"] and cr["plate_count_match"] and dr["row_count_match"] and dr["study_span_match"]
    status = "PASS_PHASE0_INPUT_IDENTITY" if hard and delta == 0 else ("BLOCKED_COUNT_RECONCILIATION_REQUIRED" if hard else "BLOCKED_INPUT_IDENTITY_MISMATCH")
    report = {
        "runner_id": RUNNER_ID, "status": status, "catalog": cr, "daily": dr, "nuclear": nr,
        "catalog_minus_daily_transient_total": delta,
        "known_literature_discrepancy": {"catalog_rows_reported": 107875, "daily_total_reported_by_independent_replication": 107862, "difference": 13, "rule": "Do not silently normalize or delete 13 records; explain row membership/date filtering before admission."}
    }
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": status, "output": args.output, "delta": delta}))
    return 0 if status.startswith("PASS") else 2


def cmd_build(args) -> int:
    catalog_map, nuclear_map = load_mapping(Path(args.catalog_map)), load_mapping(Path(args.nuclear_map))
    catalog, cr = validate_catalog(Path(args.catalog), catalog_map)
    nuclear, _ = validate_nuclear(Path(args.nuclear), nuclear_map)
    if not cr["row_count_match"] or not cr["plate_count_match"]:
        raise SystemExit("fail-closed: catalog is not exact 107875-row / 635-plate family")
    plate_meta = load_table(Path(args.plate_meta)) if args.plate_meta else None
    plate_map = load_mapping(Path(args.plate_map)) if args.plate_map else None
    if plate_meta is not None and plate_map is None:
        raise SystemExit("--plate-map required with --plate-meta")
    matrix = build_matrix(catalog, catalog_map, nuclear, nuclear_map, plate_meta, plate_map)
    output = Path(args.output); matrix.to_csv(output, index=False)
    manifest = {
        "runner_id": RUNNER_ID, "status": "PLATE_DAY_MATRIX_BUILT", "output": audit_file(output),
        "matrix_rows": int(len(matrix)), "unique_plate_ids": int(matrix["plate_id"].nunique()),
        "unique_observation_dates": int(matrix["obs_date_utc"].nunique()), "candidate_count_sum": int(matrix["candidate_count"].sum()),
        "area_time_exposure_available": bool(matrix["exposure_deg2_min"].notna().all()),
        "primary_model_admission": "READY" if matrix["exposure_deg2_min"].notna().all() else "BLOCKED_ON_PLATE_EXPOSURE_DENOMINATOR",
        "rule": "A plate-day matrix without plate-area/time exposure may be used for descriptive schedule checks, not for the primary exposure-normalized beta_nuclear claim."
    }
    Path(str(output) + ".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2)); return 0


def build_parser():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    for name in ["catalog", "catalog-map", "daily", "daily-map", "nuclear", "nuclear-map", "output"]: v.add_argument("--" + name, required=True)
    v.set_defaults(func=cmd_validate)
    b = sub.add_parser("build")
    for name in ["catalog", "catalog-map", "nuclear", "nuclear-map", "output"]: b.add_argument("--" + name, required=True)
    b.add_argument("--plate-meta"); b.add_argument("--plate-map"); b.set_defaults(func=cmd_build)
    return p


def main() -> int:
    args = build_parser().parse_args(); return args.func(args)


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (ValueError, FileNotFoundError, KeyError) as exc:
        print(json.dumps({"status": "ERROR_FAIL_CLOSED", "error": str(exc)}), file=sys.stderr); raise SystemExit(2)
