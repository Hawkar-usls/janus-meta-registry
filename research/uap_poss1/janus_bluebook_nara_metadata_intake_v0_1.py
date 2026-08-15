#!/usr/bin/env python3
"""JANUS public NARA Project Blue Book metadata intake.

Purpose
-------
Inspect the official NARA bulk metadata and compact series ZIP for Project
Blue Book without downloading the hundreds of GB of sanitized scan images.
The runner is deliberately schema-tolerant: it freezes source hashes, records
archive contents, walks the JSON tree, detects occurrence-date-like strings,
and emits candidate case/file-unit rows for a later exact-date witness test.

This runner does NOT infer extraordinary origin from a witness report and does
not silently treat report/submission dates as occurrence dates.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import urllib.request
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

RUNNER_ID = "JANUS-BLUEBOOK-NARA-METADATA-INTAKE-v0.1"
NARA_JSON_URL = "https://catalog.archives.gov/medialz/bulk-downloads/uaps/JSON/catalog-export-595466.json"
NARA_ZIP_URL = "https://catalog.archives.gov/medialz/bulk-downloads/uaps/ZIP/595466.zip"
SIPRI_URL = "https://gist.githubusercontent.com/ZijunXu/2c9d8a8db6420799ed944187100f8aee/raw/sipri-report-explosions.csv"
EXPECTED_SIPRI_SHA256 = "1bdfb18cc41741e6c45c5bdfa3d70d8d0739e08b406c647aa1913ce013ee5b95"
STUDY_START = date(1949, 11, 19)
STUDY_END = date(1957, 4, 28)
COUNTRIES = {"USA", "USSR", "UK"}
STRICT_TYPES = {"AIRDROP", "TOWER", "SURFACE", "ATMOSPH", "BARGE", "BALLOON", "ROCKET", "SHIP"}

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
MONTH_RE = re.compile(
    r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(19\d{2})\b",
    re.I,
)
ISO_RE = re.compile(r"\b(19\d{2})[-/](\d{1,2})[-/](\d{1,2})\b")
US_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(19\d{2})\b")
YEAR_RE = re.compile(r"\b(19\d{2})\b")
STARLIKE_RE = re.compile(r"\b(star(?:-like|like|s)?|point(?:-like)?|light(?:s)?|spark(?:le|ling|s)?|glimmer(?:ing)?|flash(?:ing|es)?|bright)\b", re.I)
FORMATION_RE = re.compile(r"\b(formation|cluster|group|row|rows|trail|v-formation|diamond)\b", re.I)


def download(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "JANUS-BlueBook-NARA/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def iter_nodes(obj: Any, path: str = "$"):
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from iter_nodes(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from iter_nodes(v, f"{path}[{i}]")


def flatten_strings(obj: Any, max_chars: int = 24000) -> str:
    vals: list[str] = []
    total = 0
    if isinstance(obj, dict):
        iterable = obj.values()
    elif isinstance(obj, list):
        iterable = obj
    else:
        iterable = [obj]
    stack = list(iterable)
    while stack and total < max_chars:
        v = stack.pop()
        if isinstance(v, str):
            vals.append(v)
            total += len(v)
        elif isinstance(v, dict):
            stack.extend(v.values())
        elif isinstance(v, list):
            stack.extend(v)
    return " | ".join(reversed(vals))[:max_chars]


def extract_dates(text: str) -> list[date]:
    found: set[date] = set()
    for m in MONTH_RE.finditer(text):
        try:
            found.add(date(int(m.group(3)), MONTHS[m.group(1).lower().rstrip(".")], int(m.group(2))))
        except ValueError:
            pass
    for m in ISO_RE.finditer(text):
        try:
            found.add(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    for m in US_RE.finditer(text):
        try:
            found.add(date(int(m.group(3)), int(m.group(1)), int(m.group(2))))
        except ValueError:
            pass
    return sorted(found)


def identifier_from_dict(d: dict[str, Any]) -> str:
    for key in ("naId", "naid", "id", "identifier", "localIdentifier", "local_identifier"):
        v = d.get(key)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return ""


def title_from_dict(d: dict[str, Any]) -> str:
    for key in ("title", "name", "recordTitle", "description", "scopeAndContentNote"):
        v = d.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def parse_strict_calendar(raw: bytes) -> list[date]:
    got = sha256(raw)
    if got != EXPECTED_SIPRI_SHA256:
        raise SystemExit(f"fail-closed: SIPRI bytes changed {got} != {EXPECTED_SIPRI_SHA256}")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    dates: set[date] = set()
    for r in rows:
        if (r.get("country") or "").strip().upper() not in COUNTRIES:
            continue
        typ = (r.get("type") or "").strip().upper()
        if typ not in STRICT_TYPES:
            continue
        ds = (r.get("date_long") or "").strip()
        if not re.fullmatch(r"\d{8}", ds):
            continue
        d = datetime.strptime(ds, "%Y%m%d").date()
        if STUDY_START <= d <= STUDY_END:
            dates.add(d)
    return sorted(dates)


def min_lag_days(d: date, events: list[date]) -> int:
    # Signed lag to nearest test; ties prefer smaller absolute then earlier event.
    best = min(events, key=lambda e: (abs((d - e).days), e))
    return (d - best).days


def summarize_zip(blob: bytes, out_dir: Path) -> dict[str, Any]:
    zpath = out_dir / "nara_595466.zip"
    zpath.write_bytes(blob)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        infos = zf.infolist()
        rows = []
        for i in infos:
            rows.append({
                "name": i.filename,
                "compressed_bytes": i.compress_size,
                "uncompressed_bytes": i.file_size,
                "crc32": f"{i.CRC:08x}",
            })
        with (out_dir / "nara_595466_zip_manifest.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["name", "compressed_bytes", "uncompressed_bytes", "crc32"])
            w.writeheader(); w.writerows(rows)
        # Extract only small text-like files for diagnostics, never opaque large payloads.
        text_samples = []
        for i in infos:
            lower = i.filename.lower()
            if i.file_size <= 5_000_000 and lower.endswith((".txt", ".csv", ".json", ".xml", ".html", ".htm")):
                try:
                    raw = zf.read(i)
                    text = raw.decode("utf-8-sig", errors="replace")
                    text_samples.append({"name": i.filename, "chars": len(text), "sample": text[:2000]})
                except Exception as exc:
                    text_samples.append({"name": i.filename, "error": str(exc)})
        return {
            "members": len(infos),
            "total_uncompressed_bytes": sum(i.file_size for i in infos),
            "extensions": dict(Counter(Path(i.filename).suffix.lower() or "<none>" for i in infos)),
            "first_members": rows[:30],
            "small_text_samples": text_samples[:20],
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="work/bluebook_nara")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("[1/5] downloading official NARA metadata and compact series ZIP")
    jblob = download(NARA_JSON_URL)
    zblob = download(NARA_ZIP_URL)
    sblob = download(SIPRI_URL)
    (out / "catalog-export-595466.json").write_bytes(jblob)

    print("[2/5] parsing NARA JSON schema generically")
    root = json.loads(jblob.decode("utf-8-sig"))
    node_type_counts = Counter()
    key_counts = Counter()
    date_candidates: list[dict[str, Any]] = []
    seen_fingerprints: set[str] = set()
    for path, node in iter_nodes(root):
        node_type_counts[type(node).__name__] += 1
        if isinstance(node, dict):
            key_counts.update(node.keys())
            text = flatten_strings(node)
            dates = [d for d in extract_dates(text) if STUDY_START <= d <= STUDY_END]
            if dates:
                ident = identifier_from_dict(node)
                title = title_from_dict(node)
                fingerprint = hashlib.sha256((path + "\n" + ident + "\n" + title + "\n" + text[:1000]).encode()).hexdigest()
                if fingerprint in seen_fingerprints:
                    continue
                seen_fingerprints.add(fingerprint)
                for d in dates:
                    date_candidates.append({
                        "occurrence_date_candidate": d.isoformat(),
                        "json_path": path,
                        "identifier_candidate": ident,
                        "title_candidate": title[:500],
                        "starlike_keyword_screen": int(bool(STARLIKE_RE.search(text))),
                        "formation_keyword_screen": int(bool(FORMATION_RE.search(text))),
                        "text_sample": re.sub(r"\s+", " ", text)[:1200],
                    })

    print("[3/5] inspecting compact official ZIP")
    zip_summary = summarize_zip(zblob, out)

    print("[4/5] joining candidate dates to frozen strict nuclear calendar")
    strict_dates = parse_strict_calendar(sblob)
    for r in date_candidates:
        d = date.fromisoformat(r["occurrence_date_candidate"])
        lag = min_lag_days(d, strict_dates)
        r["nearest_strict_nuclear_lag_days"] = lag
        r["strict_nuclear_day"] = int(lag == 0)
        r["strict_nuclear_pm1"] = int(abs(lag) <= 1)
        r["strict_nuclear_pm2"] = int(abs(lag) <= 2)
        r["strict_nuclear_pm4"] = int(abs(lag) <= 4)

    fields = [
        "occurrence_date_candidate", "json_path", "identifier_candidate", "title_candidate",
        "starlike_keyword_screen", "formation_keyword_screen", "text_sample",
        "nearest_strict_nuclear_lag_days", "strict_nuclear_day", "strict_nuclear_pm1",
        "strict_nuclear_pm2", "strict_nuclear_pm4",
    ]
    with (out / "nara_date_candidates.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(date_candidates)

    print("[5/5] writing fail-transparent diagnostic receipt")
    unique_candidate_dates = sorted({r["occurrence_date_candidate"] for r in date_candidates})
    receipt = {
        "runner_id": RUNNER_ID,
        "status": "NARA_PUBLIC_METADATA_INSPECTED__CANDIDATE_DATES_REQUIRE_SEMANTIC_VALIDATION",
        "sources": {
            "nara_json": {"url": NARA_JSON_URL, "bytes": len(jblob), "sha256": sha256(jblob)},
            "nara_zip": {"url": NARA_ZIP_URL, "bytes": len(zblob), "sha256": sha256(zblob)},
            "strict_calendar": {"url": SIPRI_URL, "sha256": sha256(sblob), "unique_dates": len(strict_dates)},
        },
        "json_structure": {
            "root_type": type(root).__name__,
            "node_type_counts": dict(node_type_counts),
            "top_keys": key_counts.most_common(80),
        },
        "date_candidate_diagnostic": {
            "rows": len(date_candidates),
            "unique_dates": len(unique_candidate_dates),
            "first_dates": unique_candidate_dates[:30],
            "last_dates": unique_candidate_dates[-30:],
            "exact_nuclear_candidate_rows": sum(int(r["strict_nuclear_day"]) for r in date_candidates),
            "pm1_candidate_rows": sum(int(r["strict_nuclear_pm1"]) for r in date_candidates),
            "starlike_screen_rows": sum(int(r["starlike_keyword_screen"]) for r in date_candidates),
        },
        "zip": zip_summary,
        "semantic_warning": "Date-like strings found recursively in archival metadata are candidate occurrence dates only. Production dates, coverage dates, scan dates and embedded text dates must be distinguished before inferential use.",
        "claim_ceiling": "OFFICIAL_NARA_PUBLIC_METADATA_INTAKE_ONLY__NO_WITNESS_NUCLEAR_ASSOCIATION_CLAIM_FROM_UNVALIDATED_DATE_STRINGS",
    }
    (out / "nara_metadata_intake_receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(receipt, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
