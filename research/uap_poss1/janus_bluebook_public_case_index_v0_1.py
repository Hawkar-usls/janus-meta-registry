#!/usr/bin/env python3
"""JANUS public Project Blue Book exact-date case-index builder.

This runner deliberately avoids the NARA Catalog API because read access requires
an API key. It discovers a public mirror of declassified Project Blue Book case
pages, keeps the NARA NAID/T1206 provenance carried by each page, extracts a
BLIND witness morphology layer first, freezes it by SHA-256, and only then joins
it to the already frozen JANUS strict nuclear-test calendar.

Important epistemic boundary
-----------------------------
A mirrored/transcribed case page is a convenience access layer, not a new
primary source. Rows are retained only when a NARA NAID is present. The
resulting case index must be spot-checked against the underlying NARA record
cards before admission.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable

RUNNER_ID = "JANUS-BLUEBOOK-PUBLIC-CASE-INDEX-v0.1"
BASE = "https://www.govweird.com"
TOPIC_PREFIX = "/topics/ufo/project-blue-book/"
ROBOTS_URL = BASE + "/robots.txt"
SITEMAP_CANDIDATES = [
    BASE + "/sitemap.xml",
    BASE + "/sitemap_index.xml",
    BASE + "/sitemap-0.xml",
]
USER_AGENT = "JANUS-BlueBook-PublicIndex/0.1 (+research; provenance-preserving)"

SIPRI_URL = "https://gist.githubusercontent.com/ZijunXu/2c9d8a8db6420799ed944187100f8aee/raw/sipri-report-explosions.csv"
EXPECTED_SIPRI_SHA256 = "1bdfb18cc41741e6c45c5bdfa3d70d8d0739e08b406c647aa1913ce013ee5b95"
COUNTRIES = {"USA", "USSR", "UK"}
STRICT_TYPES = {"AIRDROP", "TOWER", "SURFACE", "ATMOSPH", "BARGE", "BALLOON", "ROCKET", "SHIP"}
STUDY_START = date(1949, 11, 19)
STUDY_END = date(1957, 4, 28)

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
MON = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
DATE_PATTERNS = [
    re.compile(rf"\b({MON})\s+(\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+(19\d{{2}})\b", re.I),
    re.compile(rf"\b(\d{{1,2}})\s+({MON})[,]?\s+(19\d{{2}})\b", re.I),
]
CARD_DATE_RE = re.compile(r"(?:^|\n)\s*(?:1\.\s*)?DATE\s*(?:\||:)?\s*(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{2,4})\b", re.I)
NAID_RE = re.compile(r"(?:Case File NARA NAID|Source:\s*National Archives Catalog\s*[·\-:]?\s*NAID)\s*(\d{6,12})", re.I)
ROLL_RE = re.compile(r"T1206\s*,?\s*Roll\s*(\d{1,3})", re.I)
PAGE_RE = re.compile(r"Page count\s*(\d+)", re.I)

# Frozen BLIND morphology screen. These labels are generated before any nuclear
# calendar is loaded or joined. They are screeners, not scientific identities.
STARLIKE_PATTERNS = [
    re.compile(r"\bstar[- ]?like\b", re.I),
    re.compile(r"\blike (?:a |the )?(?:large |bright |big )?star\b", re.I),
    re.compile(r"\bpoint of light\b", re.I),
    re.compile(r"\bpinpoint(?:s)? of light\b", re.I),
    re.compile(r"\bsmall (?:white |blue |red |yellow )?light(?:s)?\b", re.I),
]
FORMATION_RE = re.compile(r"\b(formation|v[- ]formation|rows?|cluster|group|trail formation|diamond formation)\b", re.I)
RADAR_RE = re.compile(r"\b(ground[- ]radar|air[- ]intercept radar|radar[- ]visual|radar contact|radar)\b", re.I)
CRAFT_RE = re.compile(r"\b(disc|disk|cigar|cylinder|triangular|triangle|saucer|fuselage|wingless|elliptical craft|craft body)\b", re.I)
ASTRO_RE = re.compile(r"\b(probably astronomical|was astronomical|possibly astronomical|venus|jupiter|meteor|fireball|star identified|astronomical)\b", re.I)
AIRCRAFT_RE = re.compile(r"\b(was aircraft|probably aircraft|possibly aircraft|identified as .*aircraft|jet aircraft|contrail)\b", re.I)
BALLOON_RE = re.compile(r"\b(was balloon|probably balloon|possibly balloon|weather balloon|pilot balloon|balloon)\b", re.I)
UNKNOWN_RE = re.compile(r"\b(unidentified|unknown)\b", re.I)
INSUFF_RE = re.compile(r"\binsufficient data\b", re.I)


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0
        self.links: list[str] = []
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag == "a":
            for k, v in attrs:
                if k.lower() == "href" and v:
                    self.links.append(v)
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "tr", "td", "th", "section"}:
            self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript"} and self.skip:
            self.skip -= 1
        if tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "tr", "section"}:
            self.parts.append("\n")
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)
    def text(self) -> str:
        raw = "".join(self.parts).replace("\r", "\n")
        raw = re.sub(r"[\t ]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n", raw)
        return raw.strip()


def fetch(url: str, timeout: int = 45) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml,text/xml,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_robots() -> tuple[bool, str, list[str]]:
    try:
        raw = fetch(ROBOTS_URL).decode("utf-8", errors="replace")
    except Exception as exc:
        # Fail closed for bulk crawl if robots cannot be inspected.
        return False, f"robots_fetch_failed:{exc}", []
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(raw.splitlines())
    allowed = rp.can_fetch(USER_AGENT, BASE + TOPIC_PREFIX + "example")
    sitemaps = []
    for line in raw.splitlines():
        if line.lower().startswith("sitemap:"):
            sitemaps.append(line.split(":", 1)[1].strip())
    return allowed, raw, sitemaps


def parse_sitemap(url: str, seen: set[str], depth: int = 0) -> set[str]:
    if url in seen or depth > 4:
        return set()
    seen.add(url)
    try:
        blob = fetch(url)
        root = ET.fromstring(blob)
    except Exception:
        return set()
    tag = root.tag.lower()
    urls: set[str] = set()
    nsless = lambda t: t.split("}")[-1].lower()
    if nsless(root.tag) == "sitemapindex":
        for el in root.iter():
            if nsless(el.tag) == "loc" and el.text:
                urls |= parse_sitemap(el.text.strip(), seen, depth + 1)
    else:
        for el in root.iter():
            if nsless(el.tag) == "loc" and el.text:
                loc = el.text.strip()
                try:
                    p = urllib.parse.urlparse(loc)
                except Exception:
                    continue
                if p.netloc.endswith("govweird.com") and p.path.startswith(TOPIC_PREFIX):
                    urls.add(loc)
    return urls


def discover_urls(robots_sitemaps: list[str]) -> tuple[list[str], dict]:
    tried = []
    urls: set[str] = set()
    seen: set[str] = set()
    for sm in list(dict.fromkeys(robots_sitemaps + SITEMAP_CANDIDATES)):
        tried.append(sm)
        urls |= parse_sitemap(sm, seen)
    fallback_used = False
    if not urls:
        # Public topic hub fallback. Only one page fetch; no recursive crawling.
        fallback_used = True
        for hub in [BASE + "/topics/ufo/project-blue-book", BASE + "/topics/ufo/project-blue-book/"]:
            try:
                html = fetch(hub).decode("utf-8", errors="replace")
                ex = TextExtractor(); ex.feed(html)
                for href in ex.links:
                    loc = urllib.parse.urljoin(BASE, href)
                    p = urllib.parse.urlparse(loc)
                    if p.netloc.endswith("govweird.com") and p.path.startswith(TOPIC_PREFIX):
                        urls.add(loc.split("#", 1)[0].split("?", 1)[0])
            except Exception:
                pass
    return sorted(urls), {"sitemaps_tried": tried, "fallback_topic_hub_used": fallback_used}


def normalize_year(y: int) -> int:
    if y < 100:
        return 1900 + y
    return y


def month_num(s: str) -> int | None:
    k = s.strip().lower().rstrip(".")
    if k in MONTHS:
        return MONTHS[k]
    k3 = k[:3]
    return MONTHS.get(k3)


def extract_exact_dates(text: str) -> list[date]:
    found: list[date] = []
    # First prioritize record-card style date fields.
    for m in CARD_DATE_RE.finditer(text):
        mon = month_num(m.group(2))
        if not mon:
            continue
        try:
            found.append(date(normalize_year(int(m.group(3))), mon, int(m.group(1))))
        except ValueError:
            pass
    # Then narrative exact-date strings.
    for pat_i, pat in enumerate(DATE_PATTERNS):
        for m in pat.finditer(text):
            try:
                if pat_i == 0:
                    mon = month_num(m.group(1)); day = int(m.group(2)); year = int(m.group(3))
                else:
                    day = int(m.group(1)); mon = month_num(m.group(2)); year = int(m.group(3))
                if mon:
                    found.append(date(year, mon, day))
            except ValueError:
                pass
    # stable unique order
    out = []
    seen = set()
    for d in found:
        if d not in seen:
            seen.add(d); out.append(d)
    return out


def choose_occurrence_date(text: str, dates: list[date]) -> tuple[str, str]:
    if not dates:
        return "", "NO_EXACT_DATE_FOUND"
    in_window = [d for d in dates if STUDY_START <= d <= STUDY_END]
    # The first exact date in a record-card/narrative page is normally the incident
    # date, but we refuse ambiguous pages if multiple distinct in-window dates occur
    # before any clear record-card DATE field can be isolated.
    card = CARD_DATE_RE.search(text)
    if card:
        mon = month_num(card.group(2))
        try:
            d = date(normalize_year(int(card.group(3))), mon or 0, int(card.group(1)))
            return d.isoformat(), "RECORD_CARD_DATE"
        except ValueError:
            pass
    if len(in_window) == 1:
        return in_window[0].isoformat(), "SINGLE_IN_WINDOW_EXACT_DATE"
    if len(in_window) > 1:
        return "", "AMBIGUOUS_MULTIPLE_IN_WINDOW_DATES"
    return dates[0].isoformat(), "OUTSIDE_STUDY_DATE"


def classify_blind(text: str) -> dict[str, int | str]:
    low = text.lower()
    starlike = int(any(p.search(text) for p in STARLIKE_PATTERNS))
    formation = int(bool(FORMATION_RE.search(text)))
    radar = int(bool(RADAR_RE.search(text)))
    craftlike = int(bool(CRAFT_RE.search(text)))
    # Evaluation screen prioritizes explicit explained outcomes over generic page words.
    if ASTRO_RE.search(text):
        disposition = "EXPLAINED_OR_PROBABLY_ASTRONOMICAL"
    elif AIRCRAFT_RE.search(text):
        disposition = "EXPLAINED_OR_PROBABLY_AIRCRAFT"
    elif BALLOON_RE.search(text):
        disposition = "EXPLAINED_OR_PROBABLY_BALLOON"
    elif INSUFF_RE.search(text):
        disposition = "INSUFFICIENT_DATA"
    elif UNKNOWN_RE.search(text):
        disposition = "UNKNOWN_OR_UNIDENTIFIED"
    else:
        disposition = "UNPARSED"
    return {
        "starlike_screen": starlike,
        "formation_screen": formation,
        "radar_screen": radar,
        "resolved_craftlike_screen": craftlike,
        "disposition_screen": disposition,
    }


@dataclass
class CaseRow:
    source_url: str
    nara_naid: str
    title: str
    occurrence_date: str
    occurrence_date_rule: str
    microfilm_roll: str
    page_count: str
    starlike_screen: int
    formation_screen: int
    radar_screen: int
    resolved_craftlike_screen: int
    disposition_screen: str
    page_text_sha256: str
    source_text_chars: int
    source_text_sample: str
    parse_status: str


def parse_case(url: str) -> CaseRow:
    try:
        blob = fetch(url)
        html = blob.decode("utf-8", errors="replace")
        ex = TextExtractor(); ex.feed(html)
        text = ex.text()
        na = NAID_RE.search(text)
        title = ""
        mtitle = re.search(r"Project Blue Book:\s*([^<\n]+)", html, re.I)
        if mtitle:
            title = re.sub(r"\s+", " ", mtitle.group(1)).strip()
        if not title:
            # h1-like text often follows Project Blue Book Case File
            tm = re.search(r"Project Blue Book Case File\s*\n([^\n]{3,250})", text, re.I)
            if tm: title = tm.group(1).strip()
        dates = extract_exact_dates(text)
        occurrence_date, date_rule = choose_occurrence_date(text, dates)
        roll = ROLL_RE.search(text)
        pages = PAGE_RE.search(text)
        blind = classify_blind(text)
        parse_status = "OK"
        if not na:
            parse_status = "REJECT_NO_NARA_NAID"
        elif not occurrence_date:
            parse_status = date_rule
        return CaseRow(
            source_url=url,
            nara_naid=na.group(1) if na else "",
            title=title[:300],
            occurrence_date=occurrence_date,
            occurrence_date_rule=date_rule,
            microfilm_roll=roll.group(1) if roll else "",
            page_count=pages.group(1) if pages else "",
            starlike_screen=int(blind["starlike_screen"]),
            formation_screen=int(blind["formation_screen"]),
            radar_screen=int(blind["radar_screen"]),
            resolved_craftlike_screen=int(blind["resolved_craftlike_screen"]),
            disposition_screen=str(blind["disposition_screen"]),
            page_text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            source_text_chars=len(text),
            source_text_sample=re.sub(r"\s+", " ", text)[:1200],
            parse_status=parse_status,
        )
    except Exception as exc:
        return CaseRow(url, "", "", "", "FETCH_ERROR", "", "", 0, 0, 0, 0, "UNPARSED", "", 0, str(exc)[:1200], "FETCH_ERROR")


def parse_strict_calendar(raw: bytes) -> list[date]:
    got = sha256_bytes(raw)
    if got != EXPECTED_SIPRI_SHA256:
        raise SystemExit(f"fail-closed: frozen strict calendar bytes changed {got}")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    dates: set[date] = set()
    for r in rows:
        if (r.get("country") or "").strip().upper() not in COUNTRIES:
            continue
        if (r.get("type") or "").strip().upper() not in STRICT_TYPES:
            continue
        ds = (r.get("date_long") or "").strip()
        if not re.fullmatch(r"\d{8}", ds):
            continue
        d = datetime.strptime(ds, "%Y%m%d").date()
        if STUDY_START <= d <= STUDY_END:
            dates.add(d)
    return sorted(dates)


def nearest_lag(d: date, tests: list[date]) -> int:
    best = min(tests, key=lambda t: (abs((d - t).days), t))
    return (d - best).days


def write_csv(path: Path, rows: Iterable[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="work/bluebook_exact")
    ap.add_argument("--max-pages", type=int, default=0, help="0 means all discovered pages")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)

    allowed, robots_info, robots_sitemaps = parse_robots()
    if not allowed:
        raise SystemExit(f"fail-closed: bulk crawl not allowed or robots unavailable: {robots_info[:500]}")
    (out / "govweird_robots.txt").write_text(robots_info, encoding="utf-8")

    urls, discovery = discover_urls(robots_sitemaps)
    if not urls:
        raise SystemExit("fail-closed: no Project Blue Book public case URLs discovered")
    all_count = len(urls)
    if args.max_pages > 0:
        urls = urls[:args.max_pages]

    print(f"[discover] bluebook_urls={all_count} selected={len(urls)} workers={args.workers}")
    (out / "discovered_urls.txt").write_text("\n".join(urls) + "\n", encoding="utf-8")

    rows: list[CaseRow] = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
        futs = {pool.submit(parse_case, u): u for u in urls}
        done = 0
        for fut in as_completed(futs):
            rows.append(fut.result())
            done += 1
            if done % 100 == 0 or done == len(urls):
                print(f"[cases] {done}/{len(urls)}")
    rows.sort(key=lambda r: (r.occurrence_date or "9999", r.nara_naid, r.source_url))

    # BLIND freeze: only source/provenance/date/morphology; nuclear calendar has not
    # yet been downloaded or joined.
    blind_fields = list(asdict(rows[0]).keys()) if rows else []
    blind_path = out / "bluebook_case_index_blind.csv"
    write_csv(blind_path, [asdict(r) for r in rows], blind_fields)
    blind_sha = sha256_file(blind_path)
    print(f"[blind-freeze] sha256={blind_sha}")

    # Nuclear join happens strictly after blind file exists and is hashed.
    sblob = fetch(SIPRI_URL)
    tests = parse_strict_calendar(sblob)
    joined = []
    for r in rows:
        d = asdict(r)
        if r.occurrence_date:
            od = date.fromisoformat(r.occurrence_date)
            if STUDY_START <= od <= STUDY_END:
                lag = nearest_lag(od, tests)
                d.update({
                    "nearest_strict_nuclear_lag_days": lag,
                    "nuclear_day": int(lag == 0),
                    "nuclear_pm1": int(abs(lag) <= 1),
                    "nuclear_pm2": int(abs(lag) <= 2),
                    "nuclear_pm4": int(abs(lag) <= 4),
                })
            else:
                d.update({"nearest_strict_nuclear_lag_days": "", "nuclear_day": "", "nuclear_pm1": "", "nuclear_pm2": "", "nuclear_pm4": ""})
        else:
            d.update({"nearest_strict_nuclear_lag_days": "", "nuclear_day": "", "nuclear_pm1": "", "nuclear_pm2": "", "nuclear_pm4": ""})
        joined.append(d)
    joined_fields = blind_fields + ["nearest_strict_nuclear_lag_days", "nuclear_day", "nuclear_pm1", "nuclear_pm2", "nuclear_pm4"]
    joined_path = out / "bluebook_case_index_nuclear_joined.csv"
    write_csv(joined_path, joined, joined_fields)

    valid = [r for r in rows if r.nara_naid and r.occurrence_date and STUDY_START <= date.fromisoformat(r.occurrence_date) <= STUDY_END]
    starlike = [r for r in valid if r.starlike_screen]
    exact_counts = {
        "all_valid_cases": len(valid),
        "starlike_screen_cases": len(starlike),
        "formation_screen_cases": sum(r.formation_screen for r in valid),
        "radar_screen_cases": sum(r.radar_screen for r in valid),
        "resolved_craftlike_screen_cases": sum(r.resolved_craftlike_screen for r in valid),
    }
    for name, subset in [("all", valid), ("starlike", starlike)]:
        lags = []
        for r in subset:
            lag = nearest_lag(date.fromisoformat(r.occurrence_date), tests)
            lags.append(lag)
        exact_counts[f"{name}_nuclear_day"] = sum(l == 0 for l in lags)
        exact_counts[f"{name}_nuclear_pm1"] = sum(abs(l) <= 1 for l in lags)
        exact_counts[f"{name}_outside_pm4"] = sum(abs(l) > 4 for l in lags)

    # Daily event-count matrix over full study interval. Zero-report dates are explicit.
    by_date_all: dict[date, int] = {}
    by_date_star: dict[date, int] = {}
    for r in valid:
        d = date.fromisoformat(r.occurrence_date)
        by_date_all[d] = by_date_all.get(d, 0) + 1
        if r.starlike_screen:
            by_date_star[d] = by_date_star.get(d, 0) + 1
    daily = []
    d = STUDY_START
    from datetime import timedelta
    while d <= STUDY_END:
        lag = nearest_lag(d, tests)
        daily.append({
            "date": d.isoformat(),
            "bluebook_case_count": by_date_all.get(d, 0),
            "starlike_screen_count": by_date_star.get(d, 0),
            "nearest_strict_nuclear_lag_days": lag,
            "nuclear_day": int(lag == 0),
            "nuclear_pm1": int(abs(lag) <= 1),
            "nuclear_pm2": int(abs(lag) <= 2),
            "nuclear_pm4": int(abs(lag) <= 4),
        })
        d += timedelta(days=1)
    write_csv(out / "bluebook_daily_counts.csv", daily, list(daily[0].keys()))

    receipt = {
        "runner_id": RUNNER_ID,
        "status": "PUBLIC_CASE_INDEX_BUILT__BLIND_MORPHOLOGY_FROZEN_BEFORE_NUCLEAR_JOIN",
        "source": {
            "mirror": BASE,
            "topic_prefix": TOPIC_PREFIX,
            "provenance_requirement": "NARA NAID required per retained case",
            "authority_reference": "NARA T1206 / Project Blue Book case files",
            "robots_sha256": hashlib.sha256(robots_info.encode()).hexdigest(),
            "discovery": discovery,
            "discovered_urls_total": all_count,
            "selected_urls": len(urls),
        },
        "blind_freeze": {
            "file": blind_path.name,
            "sha256": blind_sha,
            "rule": "Morphology screen generated and hashed before nuclear calendar download/join.",
        },
        "nuclear_calendar": {
            "sha256": sha256_bytes(sblob),
            "strict_unique_dates": len(tests),
        },
        "parse": {
            "rows_total": len(rows),
            "rows_with_nara_naid": sum(bool(r.nara_naid) for r in rows),
            "rows_with_exact_date": sum(bool(r.occurrence_date) for r in rows),
            "valid_in_study_window": len(valid),
            "status_counts": {s: sum(r.parse_status == s for r in rows) for s in sorted({r.parse_status for r in rows})},
            "occurrence_date_rule_counts": {s: sum(r.occurrence_date_rule == s for r in rows) for s in sorted({r.occurrence_date_rule for r in rows})},
        },
        "exploratory_counts_not_rate_normalized": exact_counts,
        "mandatory_next_controls": [
            "Spot-check a preregistered random sample against underlying NARA record-card scans.",
            "Deduplicate multiple pages/case bundles that may represent one event.",
            "Validate starlike phenotype manually/blindly on a frozen subset before inferential use.",
            "Model reporting opportunity/media-wave structure; zero-report dates are not equivalent to surveyed person-days.",
            "Use matched non-nuclear dates and block/permutation controls before interpreting nuclear proximity.",
        ],
        "claim_ceiling": "PUBLIC_EXACT_DATE_INDEX_AND_BLIND_SCREEN_ONLY__NO_CAUSAL_OR_UAP_ORIGIN_INFERENCE",
    }
    (out / "bluebook_public_case_index_receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(receipt, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
