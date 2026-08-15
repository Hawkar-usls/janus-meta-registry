#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JPFM-3B NOAA/NCEI H-alpha source-byte freezer.

Acquisition only. This program MUST NOT read Blue Book, POSS-I, nuclear-calendar,
or any outcome file. It downloads the preregistered annual H-alpha report files,
hashes raw bytes, records structural coverage diagnostics, and writes a manifest.
It deliberately does not interpret a missing report row as a no-flare day.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import requests

BASE = "https://www.ngdc.noaa.gov/stp/space-weather/solar-data/solar-features/solar-flares/h-alpha/reports/merged"
YEARS = list(range(1949, 1958))
USER_AGENT = "JANUS-JPFM-3B-source-freezer/1.0"


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", required=True, type=Path)
    ap.add_argument("--manifest", required=True, type=Path)
    args = ap.parse_args()
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "text/plain,*/*"})
    rows = []
    for year in YEARS:
        name = f"halpha-flare-reports_merged_{year}.txt"
        url = f"{BASE}/{name}"
        print(f"[fetch] {year} {url}", flush=True)
        r = s.get(url, timeout=180)
        r.raise_for_status()
        raw = r.content
        if len(raw) < 10:
            raise RuntimeError(f"fail-closed: implausibly small source file {year}: {len(raw)} bytes")
        p = args.raw_dir / name
        p.write_bytes(raw)
        text = raw.decode("ascii", errors="replace")
        lines = text.splitlines()
        nonblank = [x for x in lines if x.strip()]
        rows.append({
            "year": year,
            "filename": name,
            "url": url,
            "sha256": sha256(raw),
            "bytes": len(raw),
            "lines": len(lines),
            "nonblank_lines": len(nonblank),
            "first_nonblank_line_sha256": sha256(nonblank[0].encode("utf-8")) if nonblank else None,
            "last_nonblank_line_sha256": sha256(nonblank[-1].encode("utf-8")) if nonblank else None,
        })
    manifest = {
        "artifact_id": "JANUS-PALOMAR-JPFM-3B-NOAA-HALPHA-SOURCE-FREEZE-v1.0",
        "experiment_id": "JPFM-3B",
        "date": dt.date.today().isoformat(),
        "status": "SOURCE_BYTES_FROZEN__SCHEMA_AND_COVERAGE_NOT_YET_ADMITTED",
        "gate": "data/JANUS-PALOMAR-JPFM-3B-EVENT-MANIFEST-ACQUISITION-GATE-v1.0.json",
        "authority": "NOAA/NCEI historical Solar-Terrestrial Physics H-alpha flare report archive",
        "base_url": BASE,
        "years": YEARS,
        "files": rows,
        "combined_ordered_raw_sha256": sha256(b"".join((args.raw_dir / r["filename"]).read_bytes() for r in rows)),
        "coverage_warning": "Annual file presence and row count do not establish continuous observing/reporting opportunity. No-report dates are not physical zero-flare dates until observatory coverage semantics are modeled.",
        "outcome_blindness": {
            "bluebook_access": False,
            "poss1_access": False,
            "nuclear_calendar_access": False,
            "association_computed": False,
        },
        "next_gate": "Parse documented source schema, consolidate multiple station reports into physical flare-event candidates, quantify coverage/missingness, then preregister event severity and lag endpoints before any STARLIKE/POSS-I join.",
        "claim_ceiling": "NOAA_HALPHA_SOURCE_BYTE_FREEZE_ONLY__NO_FLARE_EVENT_OR_ASSOCIATION_CLAIM",
    }
    args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
