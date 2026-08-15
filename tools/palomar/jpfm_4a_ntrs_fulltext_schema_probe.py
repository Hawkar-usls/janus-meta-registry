#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import requests

DOC_ID = "19720015241"
TXT_URL = f"https://ntrs.nasa.gov/api/citations/{DOC_ID}/downloads/{DOC_ID}.txt"
UA = "JANUS-JPFM-4A-NTRS-fulltext-schema-probe/1.0 (+source-only; no-outcome-join)"
STUDY_YEARS = tuple(range(1949, 1958))
YEAR_RE = re.compile(r"\b(?:1949|1950|1951|1952|1953|1954|1955|1956|1957)\b")
DATE_TOKEN_RE = re.compile(r"\b(?:19(?:49|5[0-7]))[-/. ](?:0?[1-9]|1[0-2])[-/. ](?:0?[1-9]|[12]\d|3[01])\b|\b(?:0?[1-9]|[12]\d|3[01])[-/. ](?:0?[1-9]|1[0-2])[-/. ](?:19(?:49|5[0-7]))\b")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def context(lines: list[str], idx: int, radius: int = 1) -> dict:
    lo = max(0, idx - radius)
    hi = min(len(lines), idx + radius + 1)
    return {
        "line_number_1based": idx + 1,
        "lines": [{"n": j + 1, "text": clean(lines[j])[:500]} for j in range(lo, hi)],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "text/plain,*/*"})
    r = s.get(TXT_URL, timeout=180, allow_redirects=True)
    r.raise_for_status()
    raw = r.content
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()

    year_hits = collections.Counter()
    date_hit_contexts = []
    year_hit_contexts = []
    keyword_contexts: dict[str, list[dict]] = {k: [] for k in ["V-2", "AEROBEE", "WHITE SANDS", "LAUNCH", "DATE", "SITE"]}

    for i, line in enumerate(lines):
        for m in YEAR_RE.finditer(line):
            year_hits[m.group(0)] += 1
        if YEAR_RE.search(line) and len(year_hit_contexts) < 300:
            year_hit_contexts.append(context(lines, i, 1))
        if DATE_TOKEN_RE.search(line) and len(date_hit_contexts) < 300:
            date_hit_contexts.append(context(lines, i, 1))
        upper = line.upper()
        for key in keyword_contexts:
            if key in upper and len(keyword_contexts[key]) < 30:
                keyword_contexts[key].append(context(lines, i, 1))

    nonempty = [len(line) for line in lines if line.strip()]
    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-4A-NTRS-19720015241-FULLTEXT-SCHEMA-PROBE-v1.0",
        "experiment_id": "JPFM-4A",
        "date": dt.date.today().isoformat(),
        "status": "OFFICIAL_NTRS_FULLTEXT_BYTES_FROZEN__SOURCE_SCHEMA_PROBED__NO_OUTCOME_JOIN",
        "source": {
            "authority": "NASA Technical Reports Server (NTRS)",
            "document_id": DOC_ID,
            "url": TXT_URL,
            "final_url": r.url,
            "http_status": r.status_code,
            "content_type": r.headers.get("content-type"),
            "bytes": len(raw),
            "sha256": sha256(raw),
            "line_count": len(lines),
            "form_feed_count": text.count("\f"),
        },
        "line_geometry": {
            "nonempty_lines": len(nonempty),
            "min_length": min(nonempty) if nonempty else 0,
            "max_length": max(nonempty) if nonempty else 0,
            "median_length": sorted(nonempty)[len(nonempty)//2] if nonempty else 0,
        },
        "study_year_hit_counts": dict(sorted(year_hits.items())),
        "date_token_contexts": date_hit_contexts,
        "study_year_contexts_first_300": year_hit_contexts,
        "keyword_contexts": keyword_contexts,
        "probe_limits": {
            "context_is_source_only": True,
            "no_row_semantics_assigned_yet": True,
            "no_absence_as_no_launch": True,
            "no_bluebook_access": True,
            "no_poss_access": True,
        },
        "outcome_blindness": {
            "bluebook_access": False,
            "poss1_access": False,
            "nuclear_calendar_access": False,
            "association_computed": False,
        },
        "next_gate": "Use this source-only schema probe to freeze a deterministic row parser for scientifically-successful rocket entries in the JANUS study window; validate parsed row count/locators against the official text before any outcome join.",
        "current_authority_changed": False,
        "claim_ceiling": "OFFICIAL_NASA_FULLTEXT_SCHEMA_ONLY__NO_ROCKET_ASSOCIATION_OR_NEGATIVE_LAUNCH_CONTROL",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
