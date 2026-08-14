#!/usr/bin/env python3
"""JANUS Linear A R3B-0 PH13 pre-content qualification.

This runner fetches only bibliographic/abstract HTML pages. It MUST NOT fetch,
open, parse, or infer the restricted PH13 PDF/transcription content.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SPEC = Path("data/JANUS-LINEAR-A-R3B-0-PAITO-PH13-EDITORIAL-WITNESS-QUALIFICATION-SPEC-2026-08-14-v0.1.json")
UA = "JANUS-proof-carrying-source-qualification/0.1 (+research metadata only)"


def fetch_text(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            status = getattr(r, "status", 200)
            ctype = r.headers.get("Content-Type", "")
        text = raw.decode("utf-8", errors="replace")
        return {
            "fetch_ok": True,
            "http_status": status,
            "content_type": ctype,
            "byte_length": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "text": text,
            "error": None,
        }
    except Exception as exc:
        return {
            "fetch_ok": False,
            "http_status": None,
            "content_type": None,
            "byte_length": 0,
            "sha256": None,
            "text": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def visibleish(s: str) -> str:
    s = re.sub(r"<script\b[^>]*>.*?</script>", " ", s, flags=re.I | re.S)
    s = re.sub(r"<style\b[^>]*>.*?</style>", " ", s, flags=re.I | re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def has_all(text: str, needles: list[str]) -> bool:
    return all(n.lower() in text for n in needles)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    assert spec["status"] == "FROZEN_BEFORE_EXECUTION"
    c = spec["candidate"]

    inst = fetch_text(c["institutional_record"])
    pub = fetch_text(c["publisher_record"])
    project = fetch_text(c["project_context"])

    inst_text = visibleish(inst.pop("text"))
    pub_text = visibleish(pub.pop("text"))
    project_text = visibleish(project.pop("text"))

    title_probe = "the phaistos linear a epigraphic project"
    checks = {
        "institutional_fetch_ok": inst["fetch_ok"],
        "publisher_fetch_ok": pub["fetch_ok"],
        "institutional_identifies_title": title_probe in inst_text,
        "institutional_identifies_PH13": "ph 13" in inst_text or "ph13" in inst_text,
        "institutional_identifies_author_Erika_Notti": "erika notti" in inst_text,
        "institutional_identifies_2024": "2024" in inst_text,
        "institutional_explicit_new_reading": "new reading" in inst_text,
        "institutional_explicit_autoptic_examination": "autoptic examination" in inst_text,
        "institutional_explicit_RTI": "rti" in inst_text and "technology" in inst_text,
        "institutional_restricted_pdf_metadata_visible": ("1.04 mb" in inst_text or "1,04 mb" in inst_text) and ("non accessibile" in inst_text or "richiedi una copia" in inst_text or "request" in inst_text),
        "publisher_identifies_title": title_probe in pub_text,
        "publisher_identifies_author_Erika_Notti": "notti, erika" in pub_text or "erika notti" in pub_text,
        "publisher_identifies_pages_301_317": "301-317" in pub_text or ("301" in pub_text and "317" in pub_text),
        "publisher_identifies_DOI": c["doi"].lower() in pub_text,
        "project_context_fetch_ok": project["fetch_ok"],
        "project_context_mentions_linear_a": "linear a" in project_text,
        "project_context_mentions_epigraphic": "epigraph" in project_text,
    }

    decisive = [
        "institutional_fetch_ok",
        "publisher_fetch_ok",
        "institutional_identifies_title",
        "institutional_identifies_PH13",
        "institutional_identifies_author_Erika_Notti",
        "institutional_explicit_new_reading",
        "institutional_explicit_autoptic_examination",
        "institutional_explicit_RTI",
        "publisher_identifies_title",
        "publisher_identifies_author_Erika_Notti",
        "publisher_identifies_pages_301_317",
        "publisher_identifies_DOI",
    ]

    if all(checks[k] for k in decisive):
        classification = "POTENTIAL_INDEPENDENT_AUTOPTIC_RTI_EDITORIAL_WITNESS_PENDING_EXACT_BYTES"
    elif inst["fetch_ok"] and not (checks["institutional_explicit_new_reading"] and checks["institutional_explicit_autoptic_examination"] and checks["institutional_explicit_RTI"]):
        classification = "BIBLIOGRAPHIC_ONLY_NOT_EDITORIAL_WITNESS"
    else:
        classification = "QUALIFICATION_BLOCKED_SOURCE_METADATA_UNAVAILABLE"

    out = {
        "artifact_uuid": "JANUS-LINEAR-A-R3B-0-PAITO-PH13-EDITORIAL-WITNESS-QUALIFICATION-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "alternate_editorial_source_candidate_qualification_result",
        "status": classification,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_spec": str(SPEC),
        "candidate": c,
        "transport_receipts": {
            "institutional_record": inst,
            "publisher_record": pub,
            "project_context": project,
        },
        "pre_content_checks": checks,
        "decisive_check_ids": decisive,
        "all_decisive_checks_pass": all(checks[k] for k in decisive),
        "content_firewall": {
            "candidate_pdf_fetched": False,
            "candidate_pdf_opened": False,
            "candidate_pdf_parsed": False,
            "PH13_new_reading_extracted": False,
            "PH13_new_reading_compared_to_existing_lineage": False,
            "candidate_specific_sign_or_word_search_performed": False,
        },
        "R3B_effect": {
            "single_document_pilot_candidate_identified": classification.startswith("POTENTIAL_"),
            "exact_editorial_source_bytes_admitted": False,
            "general_R3B_1_overlap_freeze_satisfied": False,
            "independent_transcription_replication_established": False,
        },
        "next_atomic_requirement": "Acquire the original restricted/author-supplied PH13 PDF unchanged; freeze SHA-256, byte length, MIME, page count, acquisition route/time and access terms BEFORE reading the editorial transcription content.",
        "claim_ceiling": spec["claim_ceiling"],
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": classification, "all_decisive_checks_pass": out["all_decisive_checks_pass"], "checks": checks}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
