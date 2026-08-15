#!/usr/bin/env python3
"""Parallel I/O wrapper for JANUS POSS-I public-only intake v0.1.

Scientific semantics are unchanged. Only the independent IRSA FITS-header reads
are parallelized with a bounded thread pool; output rows are sorted by plate_id
before writing so the resulting metadata and matrices remain deterministic.
"""
from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Iterable

import janus_poss1_open_release_intake_v0_1 as base

RUNNER_ID = "JANUS-POSS1-OPEN-RELEASE-INTAKE-v0.2"
MAX_WORKERS = 8


def _one_plate(plate: str) -> dict[str, str]:
    hdr = base.fetch_plate_header(plate)
    obs_raw = hdr.get("DATE-OBS", "")
    exposure = base.parse_float(hdr.get("EXPOSURE", ""))
    obs_date = base.parse_obs_date(obs_raw)
    if exposure is None or exposure <= 0:
        raise RuntimeError(f"missing/nonpositive EXPOSURE for {plate}: {hdr.get('EXPOSURE')!r}")
    return {
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
        "source_url": f"{base.IRSA_PLATE_BASE}/dss1red_{plate}.fits",
    }


def fetch_all_plate_metadata_parallel(plates: Iterable[str], out_csv: Path) -> list[dict[str, str]]:
    plate_list = sorted(set(plates))
    results: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="irsa-header") as pool:
        futures = {pool.submit(_one_plate, plate): plate for plate in plate_list}
        for done, fut in enumerate(as_completed(futures), 1):
            plate = futures[fut]
            try:
                results[plate] = fut.result()
            except Exception as exc:
                errors.append(f"{plate}:{type(exc).__name__}:{exc}")
            if done % 50 == 0 or done == len(plate_list):
                print(f"[plate headers parallel] {done}/{len(plate_list)} errors={len(errors)}")
    if errors:
        raise RuntimeError("plate-header acquisition failed closed: " + " | ".join(sorted(errors)))
    rows = [results[p] for p in plate_list]
    if len(rows) != len(plate_list):
        raise RuntimeError(f"plate-header row count mismatch: {len(rows)} != {len(plate_list)}")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return rows


def main() -> int:
    base.RUNNER_ID = RUNNER_ID
    base.fetch_all_plate_metadata = fetch_all_plate_metadata_parallel
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
