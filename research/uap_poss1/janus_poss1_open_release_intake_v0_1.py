#!/usr/bin/env python3
"""JANUS public-only POSS-I reconstruction intake.

Consumes the pinned public `jannefi/poss1-plate-slice` release, verifies its
published content hashes, reconstructs tile -> plate binding, reads only FITS
header bytes from IRSA's plate-addressed DSS1 archive, and builds plate-day
matrices for frozen open nuclear-calendar definitions.

No unpublished VASCO files are required or accepted by this runner.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

RUNNER_ID = "JANUS-POSS1-OPEN-RELEASE-INTAKE-v0.1"
UPSTREAM_COMMIT = "4005e200541b321ead3d6608f0162a14430ef1c2"
UPSTREAM_BASE = f"https://raw.githubusercontent.com/jannefi/poss1-plate-slice/{UPSTREAM_COMMIT}/results/s0-642-20260814"
STAGE_URL = UPSTREAM_BASE + "/stage_S0.csv.gz"
TILE_MANIFEST_URL = UPSTREAM_BASE + "/tile_manifest.csv.gz"
REPAIRED_URL = UPSTREAM_BASE + "/repaired_astrometry_tiles.csv"
IRSA_PLATE_BASE = "https://irsa.ipac.caltech.edu/data/DSS/images/dss1red"
SIPRI_GIST_URL = "https://gist.githubusercontent.com/ZijunXu/2c9d8a8db6420799ed944187100f8aee/raw/sipri-report-explosions.csv"

EXPECTED = {
    "stage_rows": 122820,
    "tile_rows": 31458,
    "plate_count": 642,
    "stage_sha256_uncompressed": "2ff92f2210acb387ef9ef4b88d561595d3883e9aab27065042627272b96590f0",
    "tile_sha256_uncompressed": "5dcb90dc5d98550e5a60246aced2b097922a267c69e81f27d45d16a288142a99",
}
STUDY_START = date(1949, 11, 19)
STUDY_END = date(1957, 4, 28)
COUNTRIES = {"USA", "USSR", "UK"}
STRICT_ABOVE_GROUND_TYPES = {"AIRDROP", "TOWER", "SURFACE", "ATMOSPH", "BARGE", "BALLOON", "ROCKET", "SHIP"}
BROAD_EXTRA_TYPES = {"CRATER"}
KNOWN_EXCLUDED_TYPES = {"UW", "SHAFT", "TUNNEL"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_bytes(url: str, *, max_bytes: int | None = None, range_header: str | None = None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "JANUS-POSS1-open-reconstruction/0.1"})
    if range_header:
        req.add_header("Range", range_header)
    with urllib.request.urlopen(req, timeout=90) as r:
        if max_bytes is None:
            return r.read()
        return r.read(max_bytes)


def write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def gunzip_verified(blob: bytes, expected_sha: str, label: str) -> bytes:
    raw = gzip.decompress(blob)
    got = sha256_bytes(raw)
    if got != expected_sha:
        raise SystemExit(f"fail-closed: {label} decompressed SHA-256 mismatch: {got} != {expected_sha}")
    return raw


def dict_rows(raw: bytes) -> list[dict[str, str]]:
    text = raw.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def parse_fits_header(data: bytes) -> dict[str, str]:
    # FITS cards are fixed 80-byte ASCII records. Header ends at END.
    out: dict[str, str] = {}
    for pos in range(0, len(data) - 79, 80):
        card_b = data[pos:pos + 80]
        try:
            card = card_b.decode("ascii", errors="strict")
        except UnicodeDecodeError:
            continue
        key = card[:8].strip()
        if key == "END":
            break
        if not key or card[8:10] != "= ":
            continue
        value = card[10:80].split("/", 1)[0].strip()
        if value.startswith("'") and "'" in value[1:]:
            value = value[1:value.find("'", 1)]
        out[key] = value.strip()
    return out


def parse_obs_date(value: str) -> date:
    v = (value or "").strip().strip("'")
    for fmt in ("%Y-%m-%d", "%d/%m/%y", "%m/%d/%y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            d = datetime.strptime(v[:10], fmt).date()
            # FITS two-digit year convention in this dataset is 19xx; strptime already maps 49-68 to 20xx.
            if d.year >= 2000 and len(v.split("/")[-1]) == 2:
                d = d.replace(year=d.year - 100)
            return d
        except ValueError:
            pass
    raise ValueError(f"unparsed DATE-OBS={value!r}")


def parse_float(value: str) -> float | None:
    try:
        return float(str(value).strip().replace("D", "E"))
    except Exception:
        return None


def fetch_plate_header(plate_id: str) -> dict[str, str]:
    url = f"{IRSA_PLATE_BASE}/dss1red_{plate_id}.fits"
    # 128 KiB is far beyond a normal FITS primary header. If Range is ignored,
    # reading stops here and the connection closes; the 374-MB image is not retained.
    raw = download_bytes(url, max_bytes=131072, range_header="bytes=0-131071")
    hdr = parse_fits_header(raw)
    if not hdr:
        raise RuntimeError(f"no FITS header parsed for {plate_id}")
    region = (hdr.get("REGION") or plate_id).strip()
    if region and region != plate_id:
        raise RuntimeError(f"plate identity mismatch requested={plate_id} REGION={region}")
    return hdr


def fetch_all_plate_metadata(plates: Iterable[str], out_csv: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for i, plate in enumerate(sorted(plates), 1):
        hdr = fetch_plate_header(plate)
        obs_raw = hdr.get("DATE-OBS", "")
        exposure = parse_float(hdr.get("EXPOSURE", ""))
        obs_date = parse_obs_date(obs_raw)
        if exposure is None or exposure <= 0:
            raise RuntimeError(f"missing/nonpositive EXPOSURE for {plate}: {hdr.get('EXPOSURE')!r}")
        rows.append({
            "plate_id": plate,
            "obs_date_utc": obs_date.isoformat(),
            "exposure_minutes": f"{exposure:.8g}",
            "region": hdr.get("REGION", ""),
            "platelabel": hdr.get("PLTLABEL", ""),
            "plateid_header": hdr.get("PLATEID", ""),
            "telescop": hdr.get("TELESCOP", ""),
            "emulsion": hdr.get("EMULSION", ""),
            "filter": hdr.get("FILTER", ""),
            "date_obs_raw": obs_raw,
            "source_url": f"{IRSA_PLATE_BASE}/dss1red_{plate}.fits",
        })
        if i % 50 == 0:
            print(f"[plate headers] {i}/{len(set(plates))}")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    return rows


def parse_sipri_csv(raw: bytes) -> list[dict[str, str]]:
    # The public structured file is comma-separated in raw form; fall back to whitespace
    # because mirrors occasionally render it that way.
    text = raw.decode("utf-8-sig").strip()
    if not text:
        raise RuntimeError("empty SIPRI control calendar")
    first = text.splitlines()[0]
    if "," in first:
        return list(csv.DictReader(io.StringIO(text)))
    fields = first.split()
    rows = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        # Names may contain spaces, so whitespace fallback cannot safely reconstruct all columns.
        # It is diagnostic only and fails closed if widths do not match.
        if len(parts) != len(fields):
            raise RuntimeError("SIPRI raw mirror is not CSV; ambiguous whitespace parse refused")
        rows.append(dict(zip(fields, parts)))
    return rows


def build_open_calendars(raw: bytes, out_dir: Path) -> dict[str, list[date]]:
    rows = parse_sipri_csv(raw)
    observed_types: Counter[str] = Counter()
    selected: dict[str, list[dict[str, str]]] = {"strict": [], "broad": []}
    unknown: set[str] = set()
    for r in rows:
        country = (r.get("country") or "").strip().upper()
        if country not in COUNTRIES:
            continue
        ds = (r.get("date_long") or "").strip()
        if not re.fullmatch(r"\d{8}", ds):
            continue
        d = datetime.strptime(ds, "%Y%m%d").date()
        if not (STUDY_START <= d <= STUDY_END):
            continue
        typ = (r.get("type") or "").strip().upper()
        observed_types[typ] += 1
        if typ in STRICT_ABOVE_GROUND_TYPES:
            selected["strict"].append(r)
            selected["broad"].append(r)
        elif typ in BROAD_EXTRA_TYPES:
            selected["broad"].append(r)
        elif typ in KNOWN_EXCLUDED_TYPES:
            pass
        else:
            unknown.add(typ or "<EMPTY>")
    if unknown:
        raise RuntimeError(f"unclassified nuclear test types in study window: {sorted(unknown)}")

    result: dict[str, list[date]] = {}
    for name, sub in selected.items():
        dates = sorted({datetime.strptime(r["date_long"].strip(), "%Y%m%d").date() for r in sub})
        result[name] = dates
        path = out_dir / f"nuclear_calendar_sipri_{name}.csv"
        fields = ["date_utc", "country", "type", "name", "region", "id_no", "source"]
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
            for r in sorted(sub, key=lambda x: (x["date_long"], x.get("country", ""), x.get("id_no", ""))):
                w.writerow({
                    "date_utc": datetime.strptime(r["date_long"].strip(), "%Y%m%d").date().isoformat(),
                    "country": r.get("country", ""), "type": r.get("type", ""), "name": r.get("name", ""),
                    "region": r.get("region", ""), "id_no": r.get("id_no", ""), "source": r.get("source", ""),
                })
    (out_dir / "nuclear_calendar_diagnostic.json").write_text(json.dumps({
        "source_url": SIPRI_GIST_URL,
        "raw_sha256": sha256_bytes(raw),
        "study_window": [STUDY_START.isoformat(), STUDY_END.isoformat()],
        "observed_types": observed_types,
        "strict_unique_dates": len(result["strict"]),
        "broad_unique_dates": len(result["broad"]),
        "semantic_warning": "These are independent open control calendars, not the unrecovered literal 124-row Bruehl/Villarroel calendar.",
    }, indent=2, default=dict), encoding="utf-8")
    return result


def window_flag(d: date, tests: set[date], radius: int) -> int:
    return int(any((d + timedelta(days=k)) in tests for k in range(-radius, radius + 1)))


def build_matrix(stage_rows: list[dict[str, str]], tile_rows: list[dict[str, str]], plate_meta: list[dict[str, str]], tests: list[date], out_csv: Path) -> list[dict[str, str]]:
    tile_to_plate: dict[str, str] = {}
    tiles_per_plate: Counter[str] = Counter()
    for r in tile_rows:
        tile = (r.get("tile_id") or "").strip(); plate = (r.get("plate_id") or "").strip()
        if not tile or not plate:
            raise RuntimeError("tile manifest contains blank tile_id/plate_id")
        prior = tile_to_plate.setdefault(tile, plate)
        if prior != plate:
            raise RuntimeError(f"ambiguous tile -> plate binding for {tile}: {prior} vs {plate}")
        tiles_per_plate[plate] += 1

    candidates_per_plate: Counter[str] = Counter()
    missing_tiles: Counter[str] = Counter()
    for r in stage_rows:
        tile = (r.get("tile_id") or "").strip()
        plate = tile_to_plate.get(tile)
        if not plate:
            missing_tiles[tile] += 1; continue
        candidates_per_plate[plate] += 1
    if missing_tiles:
        raise RuntimeError(f"stage rows reference unmapped tiles: {missing_tiles.most_common(10)}")

    meta_by_plate = {r["plate_id"]: r for r in plate_meta}
    if set(meta_by_plate) != set(tiles_per_plate):
        raise RuntimeError(f"plate metadata identity mismatch missing={sorted(set(tiles_per_plate)-set(meta_by_plate))[:10]} extra={sorted(set(meta_by_plate)-set(tiles_per_plate))[:10]}")

    tests_set = set(tests)
    rows: list[dict[str, str]] = []
    for plate in sorted(tiles_per_plate):
        m = meta_by_plate[plate]
        d = date.fromisoformat(m["obs_date_utc"])
        if not (STUDY_START <= d <= STUDY_END):
            continue
        exp_min = float(m["exposure_minutes"])
        ntiles = int(tiles_per_plate[plate])
        ordinal = d.toordinal()
        # Smooth secular + annual baseline covariates, frozen before beta inspection.
        year_centered = (ordinal - date(1953, 7, 1).toordinal()) / 365.2425
        doy = d.timetuple().tm_yday
        angle = 2.0 * math.pi * doy / 365.2425
        rows.append({
            "plate_id": plate,
            "obs_date_utc": d.isoformat(),
            "candidate_count": str(int(candidates_per_plate.get(plate, 0))),
            "processed_tiles": str(ntiles),
            "exposure_minutes": f"{exp_min:.8g}",
            "exposure_tile_min": f"{ntiles * exp_min:.8g}",
            "year_centered": f"{year_centered:.10g}",
            "season_sin": f"{math.sin(angle):.10g}",
            "season_cos": f"{math.cos(angle):.10g}",
            "nuclear_window_m1_p1": str(window_flag(d, tests_set, 1)),
            "nuclear_window_m2_p2": str(window_flag(d, tests_set, 2)),
            "nuclear_window_m4_p4": str(window_flag(d, tests_set, 4)),
        })
    if not rows:
        raise RuntimeError("no plate-days inside target study window")
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)

    print("[1/5] downloading pinned public release")
    stage_gz = download_bytes(STAGE_URL); tile_gz = download_bytes(TILE_MANIFEST_URL)
    repaired_raw = download_bytes(REPAIRED_URL)
    write_bytes(out / "stage_S0.csv.gz", stage_gz); write_bytes(out / "tile_manifest.csv.gz", tile_gz); write_bytes(out / "repaired_astrometry_tiles.csv", repaired_raw)
    stage_raw = gunzip_verified(stage_gz, EXPECTED["stage_sha256_uncompressed"], "stage_S0.csv")
    tile_raw = gunzip_verified(tile_gz, EXPECTED["tile_sha256_uncompressed"], "tile_manifest.csv")
    stage_rows = dict_rows(stage_raw); tile_rows = dict_rows(tile_raw)
    if len(stage_rows) != EXPECTED["stage_rows"]: raise SystemExit(f"fail-closed: stage rows {len(stage_rows)} != {EXPECTED['stage_rows']}")
    if len(tile_rows) != EXPECTED["tile_rows"]: raise SystemExit(f"fail-closed: tile rows {len(tile_rows)} != {EXPECTED['tile_rows']}")
    plates = sorted({(r.get("plate_id") or "").strip() for r in tile_rows if (r.get("plate_id") or "").strip()})
    if len(plates) != EXPECTED["plate_count"]: raise SystemExit(f"fail-closed: plate count {len(plates)} != {EXPECTED['plate_count']}")

    print("[2/5] streaming public IRSA FITS headers only")
    plate_meta = fetch_all_plate_metadata(plates, out / "plate_metadata.csv")

    print("[3/5] freezing independent open nuclear calendars")
    sipri_raw = download_bytes(SIPRI_GIST_URL)
    write_bytes(out / "sipri-report-explosions.csv", sipri_raw)
    calendars = build_open_calendars(sipri_raw, out)

    print("[4/5] building exposure-normalized open matrices")
    matrix_summary = {}
    for name, dates in calendars.items():
        rows = build_matrix(stage_rows, tile_rows, plate_meta, dates, out / f"plate_day_open_{name}.csv")
        matrix_summary[name] = {
            "rows": len(rows),
            "candidate_total": sum(int(r["candidate_count"]) for r in rows),
            "nuclear_window_plate_days": sum(int(r["nuclear_window_m1_p1"]) for r in rows),
            "unique_observation_dates": len({r["obs_date_utc"] for r in rows}),
            "unique_test_dates": len(dates),
        }

    print("[5/5] writing provenance receipt")
    receipt = {
        "runner_id": RUNNER_ID,
        "status": "OPEN_PUBLIC_RECONSTRUCTION_MATRIX_READY",
        "upstream": {
            "repository": "jannefi/poss1-plate-slice",
            "commit": UPSTREAM_COMMIT,
            "release": "results/s0-642-20260814",
            "stage_expected_uncompressed_sha256": EXPECTED["stage_sha256_uncompressed"],
            "tile_expected_uncompressed_sha256": EXPECTED["tile_sha256_uncompressed"],
            "stage_rows": len(stage_rows), "tile_rows": len(tile_rows), "plates": len(plates),
        },
        "frozen_download_hashes": {
            "stage_gzip_sha256": sha256_bytes(stage_gz),
            "tile_manifest_gzip_sha256": sha256_bytes(tile_gz),
            "repaired_astrometry_tiles_sha256": sha256_bytes(repaired_raw),
            "sipri_control_calendar_raw_sha256": sha256_bytes(sipri_raw),
        },
        "plate_metadata": {
            "source": "IRSA DSS1 plate-addressed full-scan FITS headers",
            "rows": len(plate_meta),
            "retrieval": "stream/range first 128 KiB only; no full image download required",
        },
        "matrices": matrix_summary,
        "exposure_semantics": "processed_tiles * FITS EXPOSURE minutes; deliberately named exposure_tile_min, not deg2_min",
        "calendar_semantics": "SIPRI/IAEA-derived independent OPEN controls. They do not claim byte/row equivalence to Bruehl-Villarroel's 124-date SPSS calendar.",
        "claim_ceiling": "PUBLIC_COHORT_ASSOCIATION_TEST_READY__ROWS_ARE_CATALOG_CANDIDATES_NOT_VERIFIED_PHYSICAL_TRANSIENTS_OR_UAP",
    }
    (out / "open_intake_receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
