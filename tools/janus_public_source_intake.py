"""JANUS GitHub-native public-source intake with append-only quarantine receipts.

Only fixed public endpoints. This is NOT a model trainer, factual claim evaluator,
or deployment tool. Search snippets, article text and private questions are NEVER
ingested. Successful scheduled runs propose one immutable JSON via a review PR.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile

SCHEMA = "janus.public_source_intake.quarantine.v1"
OUTPUT_PREFIX = "JANUS-PUBLIC-SOURCES-"
REGISTRY_PATH = "data/observations/public_source_quarantine/"
USER_AGENT = "JANUS-Public-Source-Intake/0.1 (https://github.com/Hawkar-usls/janus-meta-registry)"
GDELT_MANIFEST = "https://data.gdeltproject.org/gdeltv2/lastupdate.txt"
GDELT_MASTER = "https://data.gdeltproject.org/gdeltv2/masterfilelist.txt"
GDELT_TAIL_BYTES = 196608
# GDELT publishes batches about every 15 min. Range fetch reads only the tail.
# Never download the full master (hundreds of MB) in Actions.
GDELT_FALLBACK_MAX_AGE_SLOTS = 96
GDELT_ZIP_RE = re.compile(
    r"^https://data\.gdeltproject\.org/gdeltv2/(20\d{12})\.gkg\.csv\.zip$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
GITHUB_RUNS = (
    "https://api.github.com/repos/Hawkar-usls/Demi_Head/"
    "actions/workflows/tachyon-r2h-parallel-research.yml/runs")
WIKI = "https://ru.wikipedia.org/w/api.php"
OPENALEX = "https://api.openalex.org/works"
# Strict request limits. No retry loops or elevated runner privileges.
BODY_LIMIT = 150_000
ARCHIVE_LIMIT = 9_000_000
SAMPLE_LINES = 3
MAX_LINE_BYTES = 100_000


class IntakeError(ValueError):
    pass


def need(ok: bool, message: str) -> None:
    if not ok:
        raise IntakeError(message)


def canonical(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_url(url: str) -> bool:
    """Fixed provider routes only. No redirect, arbitrary URL or local HTTP."""
    try:
        p = urllib.parse.urlsplit(url)
        if not (p.scheme == "https" and p.username is None
                and p.password is None and p.port in (None, 443)
                and p.fragment == ""):
            return False
        if url in (GDELT_MANIFEST, GDELT_MASTER) or GDELT_ZIP_RE.fullmatch(url):
            return True
        return ((p.hostname == "ru.wikipedia.org" and p.path == "/w/api.php")
                or (p.hostname == "api.openalex.org" and p.path == "/works")
                or (p.hostname == "api.github.com" and p.path ==
                    "/repos/Hawkar-usls/Demi_Head/actions/workflows/"
                    "tachyon-r2h-parallel-research.yml/runs"))
    except ValueError:
        return False


class RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise IntakeError("EXTERNAL_REDIRECT_DENIED")


def http_read(url: str, max_bytes: int) -> bytes:
    need(safe_url(url), "NOT_AN_ALLOWLISTED_SOURCE")
    headers = {
        "Accept": "application/json, text/plain, application/zip",
        "User-Agent": USER_AGENT,
    }
    if url == GDELT_MASTER:
        need(max_bytes == GDELT_TAIL_BYTES, "GDELT_MASTER_RANGE_LIMIT")
        headers["Range"] = f"bytes=-{GDELT_TAIL_BYTES}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(RejectRedirect)
    try:
        with opener.open(req, timeout=15) as response:
            if url == GDELT_MASTER:
                need(response.status == 206 and
                     response.headers.get("Content-Range", "").startswith("bytes "),
                     "GDELT_MASTER_RANGE_NOT_SUPPORTED")
            else:
                need(response.status == 200, "UPSTREAM_NOT_200")
            data = response.read(max_bytes + 1)
            need(len(data) <= max_bytes, "UPSTREAM_TOO_LARGE")
            return data
    except urllib.error.HTTPError as exc:
        raise IntakeError(f"UPSTREAM_HTTP_{exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise IntakeError("UPSTREAM_UNAVAILABLE") from None


def request_json(fetch, base: str, params: dict[str, str]) -> dict:
    url = base + "?" + urllib.parse.urlencode(params)
    need(safe_url(url), "FORBIDDEN_REQUEST_HOST")
    raw = fetch(url, BODY_LIMIT)
    need(len(raw) <= BODY_LIMIT, "JSON_RESPONSE_LIMIT")
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise IntakeError("PROVIDER_NON_JSON") from None
    need(isinstance(obj, dict), "PROVIDER_JSON_NOT_OBJECT")
    return obj


def gdelt_manifest_row(raw: bytes) -> tuple[str, int, str, str]:
    need(len(raw) <= 20_000, "GDELT_MANIFEST_TOO_LARGE")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise IntakeError("GDELT_MANIFEST_NOT_UTF8") from None
    need(1 <= len(lines) <= 10, "GDELT_MANIFEST_LINE_COUNT")
    chosen = []
    for line in lines:
        parts = line.split()
        need(len(parts) == 3 and parts[0].isdigit() and
             re.fullmatch(r"[a-f0-9]{32}", parts[1].lower()) is not None,
             "INVALID_GDELT_MANIFEST_ENTRY")
        raw_link = parts[2]
        # GDELT's manifest historically contains http:// links; secure them
        # by upgrading to the EXACT fixed HTTPS hostname, never a redirect.
        if raw_link.startswith("http://data.gdeltproject.org/"):
            raw_link = "https://" + raw_link[len("http://"):]
        if GDELT_ZIP_RE.fullmatch(raw_link):
            chosen.append((raw_link, int(parts[0]), parts[1].lower(),
                           GDELT_ZIP_RE.fullmatch(raw_link).group(1)))
    need(len(chosen) == 1, "GDELT_GKG_ENTRY_MISSING_OR_AMBIGUOUS")
    url, size, md5, stamp = chosen[0]
    need(0 < size <= ARCHIVE_LIMIT, "GDELT_ZIP_EXCEEDS_BOUNDED_BUDGET")
    return url, size, md5, stamp


def sample_gkg_zip(raw: bytes) -> dict:
    need(len(raw) <= ARCHIVE_LIMIT, "GDELT_ZIP_TOO_LARGE")
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        entries = z.infolist()
        need(len(entries) == 1 and not entries[0].is_dir(),
             "GDELT_ZIP_MEMBER_COUNT")
        info = entries[0]
        need("/" not in info.filename and "\\" not in info.filename
             and info.filename.lower().endswith(".gkg.csv")
             and 0 < info.file_size <= 130_000_000,
             "GDELT_ZIP_MEMBER_UNSAFE")
        with z.open(info, "r") as fp:
            rows = []
            for _ in range(SAMPLE_LINES):
                row = fp.readline(MAX_LINE_BYTES + 1)
                if not row:
                    break
                need(len(row) <= MAX_LINE_BYTES and
                     row.count(b"\t") + 1 == 27, "GDELT_GKG_ROW_SHAPE")
                rows.append(digest(row))
        need(len(rows) >= 1, "GDELT_GKG_EMPTY")
    except (zipfile.BadZipFile, EOFError, OSError):
        raise IntakeError("GDELT_ZIP_INVALID") from None
    return {"sampled_row_count": len(rows), "sample_row_sha256": rows,
            "first_row_field_count": 27, "raw_text_copied": False}


def gdelt_master_fallback(raw: bytes, newer_stamp: str) -> tuple[str, int, str, str]:
    """Choose exactly one prior GKG *advertised* in a bounded official master tail.

    Reject incomplete first line (suffix Range can start midline), malformed
    source URLs, future timestamps, missing manifest checksums and old windows.
    """
    need(len(raw) <= GDELT_TAIL_BYTES, "MASTER_TAIL_TOO_LARGE")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        raise IntakeError("MASTER_TAIL_NOT_UTF8") from None
    need(len(lines) >= 2, "MASTER_TAIL_TOO_SHORT")
    from datetime import datetime, timedelta
    ts = datetime.strptime(newer_stamp, "%Y%m%d%H%M%S")
    eligible = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) != 3:
            continue
        size_str, md5, raw_link = parts
        if not (size_str.isdigit() and re.fullmatch(r"[0-9a-fA-F]{32}", md5)):
            continue
        if raw_link.startswith("http://data.gdeltproject.org/"):
            raw_link = "https://" + raw_link[len("http://"):]
        match = GDELT_ZIP_RE.fullmatch(raw_link)
        if not match:
            continue
        try:
            size = int(size_str)
            stamp = datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
        except ValueError:
            continue
        if (0 < size <= ARCHIVE_LIMIT and
                timedelta(0) < ts - stamp <= timedelta(
                    minutes=15 * GDELT_FALLBACK_MAX_AGE_SLOTS)):
            eligible.append((stamp, raw_link, size, md5.lower(), match.group(1)))
    need(bool(eligible), "NO_MANIFESTED_PRIOR_GKG_BATCH")
    _, url, size, md5, stamp = max(eligible, key=lambda row: row[0])
    return url, size, md5, stamp


def get_gdelt(fetch) -> dict:
    raw_manifest = fetch(GDELT_MANIFEST, 20_000)
    url, expected_size, md5, stamp = gdelt_manifest_row(raw_manifest)
    selected_manifest_url = GDELT_MANIFEST
    selected_manifest_sha = digest(raw_manifest)
    latest_404 = False
    try:
        raw_zip = fetch(url, ARCHIVE_LIMIT)
    except IntakeError as exc:
        if str(exc) != "UPSTREAM_HTTP_404":
            raise
        # Only 404 from the just-advertised ZIP may trigger ONE prior-file
        # request. No tight retry loop and never use an invented archive URL.
        latest_404 = True
        master_tail = fetch(GDELT_MASTER, GDELT_TAIL_BYTES)
        url, expected_size, md5, stamp = gdelt_master_fallback(
            master_tail, stamp)
        selected_manifest_url = GDELT_MASTER
        selected_manifest_sha = digest(master_tail)
        raw_zip = fetch(url, ARCHIVE_LIMIT)
    need(len(raw_zip) == expected_size, "GDELT_ZIP_SIZE_MISMATCH")
    need(hashlib.md5(raw_zip, usedforsecurity=False).hexdigest() == md5,
         "GDELT_ZIP_MANIFEST_MD5_MISMATCH")
    sample = sample_gkg_zip(raw_zip)
    return {"status": "PUBLIC_GKG_BATCH_STRUCTURALLY_READABLE",
            "manifest_url": selected_manifest_url,
            "manifest_sha256": selected_manifest_sha,
            "latest_manifest_sha256": digest(raw_manifest),
            "latest_advertised_gkg_url_returned_404": latest_404,
            "fallback_from_official_master_tail": latest_404,
            "gkg_url": url, "feed_filename_timestamp_utc": stamp,
            "feed_timestamp_is_article_publish_time": False,
            "compressed_bytes": len(raw_zip),
            "zip_sha256": digest(raw_zip),
            "source_manifest_md5_verified": True,
            "sample": sample,
            "source_article_text_saved": False,
            "article_claims_independently_verified": False}


def get_wikipedia(fetch) -> dict:
    doc = request_json(fetch, WIKI, {
        "action": "query", "generator": "search",
        "gsrsearch": "замедление времени", "gsrlimit": "3",
        "gsrnamespace": "0", "prop": "info", "inprop": "url",
        "format": "json", "formatversion": "2"})
    pages = doc.get("query", {}).get("pages", [])
    need(isinstance(pages, list), "WIKIPEDIA_RESPONSE_SHAPE")
    records = []
    for x in pages[:3]:
        if not isinstance(x, dict):
            continue
        title, url = x.get("title"), x.get("fullurl")
        if (isinstance(title, str) and 3 <= len(title) <= 120
                and isinstance(url, str)
                and url.startswith("https://ru.wikipedia.org/wiki/")):
            records.append({"title": title, "article_url": url})
    need(len(records) > 0, "WIKIPEDIA_NO_SOURCES")
    return {"status": "PUBLIC_ENCYCLOPEDIA_METADATA",
            "search_query": "замедление времени",
            "article_metadata": records,
            "article_claims_independently_verified": False}


def get_openalex(fetch) -> dict:
    doc = request_json(fetch, OPENALEX, {
        "search": "quantum causality", "per_page": "3",
        "select": "id,title,doi,publication_date"})
    papers = doc.get("results", [])
    need(isinstance(papers, list), "OPENALEX_RESPONSE_SHAPE")
    records = []
    for x in papers[:3]:
        if not isinstance(x, dict):
            continue
        doi, title = x.get("doi"), x.get("title")
        if (isinstance(doi, str) and doi.startswith("https://doi.org/")
                and isinstance(title, str) and 3 <= len(title) <= 250):
            records.append({"doi_url": doi, "title": title,
                            "publication_date": x.get("publication_date")})
    need(len(records) > 0, "OPENALEX_NO_DOI_METADATA")
    return {"status": "BIBLIOGRAPHIC_METADATA_ONLY",
            "search_query": "quantum causality",
            "papers": records, "abstracts_copied": False,
            "independent_scientific_review": False}


def get_training_runs(fetch) -> dict:
    doc = request_json(fetch, GITHUB_RUNS, {"per_page": "1"})
    runs = doc.get("workflow_runs", [])
    need(isinstance(runs, list) and runs, "GITHUB_NO_PUBLIC_TRAINING_RUN")
    row = runs[0]
    need(isinstance(row, dict) and
         isinstance(row.get("id"), int) and
         re.fullmatch(r"[0-9a-f]{40}", str(row.get("head_sha", ""))),
         "GITHUB_RUN_METADATA_BAD")
    return {"status": "PUBLIC_ACTION_RUN_METADATA_ONLY",
            "repository": "Hawkar-usls/Demi_Head",
            "workflow": "tachyon-r2h-parallel-research.yml",
            "run_id": row["id"], "head_sha": row["head_sha"],
            "run_status": row.get("status"),
            "run_conclusion": row.get("conclusion"),
            "scientific_quality_of_model_verified": False,
            "candidate_auto_promoted": False}


SOURCES = (("gdelt_gkg", get_gdelt), ("wikipedia", get_wikipedia),
           ("openalex", get_openalex), ("tachyon_action", get_training_runs))


def collect(fetch=http_read, at: str | None = None) -> dict:
    observed = at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    results = {}
    success = 0
    for name, callback in SOURCES:
        try:
            item = callback(fetch)
            results[name] = item
            success += 1
        except (IntakeError, ValueError) as exc:
            # Provider messages are allowlisted status tokens, not raw response.
            message = str(exc)
            if not re.fullmatch(r"[A-Z0-9_]+", message):
                message = "SOURCE_PARSE_FAILURE"
            results[name] = {"status": "PROVIDER_UNAVAILABLE",
                             "reason": message}
    need(success > 0, "ALL_PUBLIC_SOURCES_UNAVAILABLE")
    identity = digest(canonical(results))
    doc = {
        "schema": SCHEMA, "record_id": OUTPUT_PREFIX + identity[:20],
        "observed_at_utc": observed, "source_digest_sha256": identity,
        "sources": results,
        "source_count_success": success,
        "source_count_attempted": len(SOURCES),
        "source_class": "PUBLIC_UNTRUSTED_METADATA_QUARANTINE",
        "training_permitted": False,
        "factual_claims_verified": False,
        "model_weight_update": False,
        "hidden_clock_holdout_used": False,
        "auto_merged": False,
        "publication_policy": "APPEND_ONLY_REVIEW_PR",
        "scientific_admission": "HOLD",
    }
    doc["receipt_sha256"] = digest(canonical(doc))
    return doc


def validate_receipt(record: dict) -> None:
    need(record.get("schema") == SCHEMA, "RECEIPT_SCHEMA")
    name = record.get("record_id", "")
    need(isinstance(name, str) and re.fullmatch(
        r"JANUS-PUBLIC-SOURCES-[0-9a-f]{20}", name), "RECEIPT_ID")
    need(record.get("source_class") ==
         "PUBLIC_UNTRUSTED_METADATA_QUARANTINE" and
         record.get("training_permitted") is False and
         record.get("factual_claims_verified") is False and
         record.get("auto_merged") is False and
         record.get("scientific_admission") == "HOLD", "QUARANTINE_BYPASS")
    need(record.get("receipt_sha256") ==
         digest(canonical({k: v for k, v in record.items()
                           if k != "receipt_sha256"})), "RECEIPT_SHA_MISMATCH")
    need(record.get("source_digest_sha256") ==
         digest(canonical(record["sources"])), "SOURCE_DIGEST_MISMATCH")
    need(name.endswith(record["source_digest_sha256"][:20]), "RECEIPT_ID_MISMATCH")


def write_new(doc: dict, outdir: Path) -> tuple[Path, str]:
    validate_receipt(doc)
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / (doc["record_id"] + ".json")
    serialized = json.dumps(doc, ensure_ascii=False, indent=2,
                            sort_keys=True, allow_nan=False) + "\n"
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        validate_receipt(old)
        need(old["source_digest_sha256"] == doc["source_digest_sha256"],
             "DUPLICATE_ID_WITH_WRONG_SOURCE")
        return path, "ALREADY_ARCHIVED_NO_OVERWRITE"
    path.write_text(serialized, encoding="utf-8")
    return path, "NEW_QUARANTINED_SOURCE_RECORD"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--outdir")
    ap.add_argument("--verify")
    args = ap.parse_args()
    if args.verify:
        p = Path(args.verify)
        need(p.name.startswith(OUTPUT_PREFIX) and p.suffix == ".json",
             "INVALID_PUBLIC_SOURCE_FILENAME")
        validate_receipt(json.loads(p.read_text(encoding="utf-8")))
        print("JANUS_PUBLIC_SOURCE_QUARANTINE_RECEIPT_VERIFIED")
        return
    need(args.live and args.outdir, "EXPLICIT_LIVE_MODE_REQUIRED")
    receipt = collect()
    path, status = write_new(receipt, Path(args.outdir))
    print(json.dumps({"status": status, "record_id": receipt["record_id"],
                      "source_success": receipt["source_count_success"],
                      "source_attempted": receipt["source_count_attempted"],
                      "path": str(path), "scientific_admission": "HOLD"},
                     sort_keys=True))


if __name__ == "__main__":
    main()
