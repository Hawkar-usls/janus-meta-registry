#!/usr/bin/env python3
"""Pre-content qualification of the Notti Theran Linear A editorial family.

Only public metadata pages and identity-level entry keys from a frozen 2021
mwenge snapshot are inspected. Candidate PDF/transcription bytes are forbidden.
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

SPEC = Path("data/JANUS-LINEAR-A-R3B-0-NOTTI-THERA-EDITORIAL-CORPUS-FAMILY-QUALIFICATION-SPEC-2026-08-14-v0.1.json")
UA = "JANUS-R3B-source-qualification/0.1"


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,text/plain,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read()
            status = getattr(r, "status", 200)
            ctype = r.headers.get("Content-Type", "")
        return {
            "ok": True,
            "http_status": status,
            "content_type": ctype,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "raw": raw,
            "error": None,
        }
    except Exception as exc:
        return {"ok": False, "http_status": None, "content_type": None, "bytes": 0, "sha256": None, "raw": b"", "error": f"{type(exc).__name__}: {exc}"}


def textify(raw: bytes) -> str:
    s = raw.decode("utf-8", errors="replace")
    s = re.sub(r"<script\b[^>]*>.*?</script>", " ", s, flags=re.I | re.S)
    s = re.sub(r"<style\b[^>]*>.*?</style>", " ", s, flags=re.I | re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip().lower()


def public_receipt(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "raw"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    assert spec["status"] == "FROZEN_BEFORE_EXECUTION"
    sources = {x["id"]: x for x in spec["editorial_family"]["sources"]}
    ref = spec["historical_reference_identity_universe"]

    p2021 = fetch(sources["NOTTI_THERA_2021"]["institutional_record"])
    p2021pub = fetch(sources["NOTTI_THERA_2021"]["publisher_record"])
    p2025 = fetch(sources["NOTTI_THERA_2025"]["institutional_record"])

    raw_url = f"https://raw.githubusercontent.com/{ref['repository']}/{ref['commit']}/{ref['path']}"
    historical = fetch(raw_url)

    t21 = textify(p2021["raw"])
    t21pub = textify(p2021pub["raw"])
    t25 = textify(p2025["raw"])

    theran_ids = []
    if historical["ok"]:
        src = historical["raw"].decode("utf-8", errors="strict")
        # Identity-only scanner: source-level Map entry keys beginning THE.
        theran_ids = re.findall(r'^\s*\[\s*"(THE[^"]+)"\s*,\s*\{', src, flags=re.M)
    unique_theran_ids = list(dict.fromkeys(theran_ids))

    checks = {
        "2021_institutional_fetch_ok": p2021["ok"],
        "2021_title_and_author_visible": "writing in late bronze age thera" in t21 and "notti" in t21,
        "2021_new_autopsies_explicit": "nuove autopsie" in t21 or "new autops" in t21,
        "2021_comprehensive_revision_explicit": "revisione complessiva" in t21 or "comprehensive revision" in t21,
        "2021_texts_presented_explicit": "vengono presentati i testi" in t21 or "texts are presented" in t21,
        "2021_facsimile_explicit": "facsimile" in t21,
        "2021_publisher_fetch_ok": p2021pub["ok"],
        "2021_publisher_title_pages_visible": "writing in late bronze age thera" in t21pub and "207-225" in t21pub,
        "2025_institutional_fetch_ok": p2025["ok"],
        "2025_title_identifies_linear_a_documents": "overview of linear a documents" in t25,
        "2025_epigraphic_palaeographic_comments_visible": "epigraphic and palaeographic comments" in t25,
        "historical_reference_fetch_ok": historical["ok"],
        "historical_reference_prefix_THE_identity_count_at_least_10": len(unique_theran_ids) >= int(ref["minimum_count_required_for_general_R3B_1_potential"]),
    }

    decisive = [
        "2021_institutional_fetch_ok",
        "2021_title_and_author_visible",
        "2021_new_autopsies_explicit",
        "2021_comprehensive_revision_explicit",
        "2021_texts_presented_explicit",
        "2021_facsimile_explicit",
        "2025_institutional_fetch_ok",
        "2025_title_identifies_linear_a_documents",
        "2025_epigraphic_palaeographic_comments_visible",
        "historical_reference_fetch_ok",
    ]

    if all(checks[k] for k in decisive):
        if checks["historical_reference_prefix_THE_identity_count_at_least_10"]:
            status = "POTENTIAL_MULTI_DOCUMENT_AUTOPTIC_EDITORIAL_CORPUS_FAMILY_WITH_R3B1_SCALE_PENDING_EXACT_BYTES"
        else:
            status = "POTENTIAL_EDITORIAL_CORPUS_FAMILY_REFERENCE_SCALE_BELOW_R3B1_MINIMUM"
    else:
        status = "QUALIFICATION_BLOCKED_SOURCE_METADATA_UNAVAILABLE"

    out = {
        "artifact_uuid": "JANUS-LINEAR-A-R3B-0-NOTTI-THERA-EDITORIAL-CORPUS-FAMILY-QUALIFICATION-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "alternate_editorial_multi_document_source_family_qualification_result",
        "status": status,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_spec": str(SPEC),
        "transport_receipts": {
            "NOTTI_THERA_2021_institutional": public_receipt(p2021),
            "NOTTI_THERA_2021_publisher": public_receipt(p2021pub),
            "NOTTI_THERA_2025_institutional": public_receipt(p2025),
            "historical_reference_LinearAInscriptions_js": public_receipt(historical),
            "historical_reference_raw_url": raw_url,
        },
        "checks": checks,
        "decisive_checks": decisive,
        "all_decisive_checks_pass": all(checks[k] for k in decisive),
        "historical_reference_identity_probe": {
            "commit": ref["commit"],
            "selection_rule": ref["selection_rule"],
            "raw_matching_entry_count": len(theran_ids),
            "unique_matching_identity_count": len(unique_theran_ids),
            "unique_identity_ids": unique_theran_ids,
            "candidate_exact_coverage_count_inferred": False,
        },
        "candidate_content_firewall": {
            "2021_candidate_pdf_fetched": False,
            "2021_candidate_pdf_opened": False,
            "2021_candidate_readings_extracted": False,
            "2025_candidate_pdf_fetched": False,
            "2025_candidate_pdf_opened": False,
            "2025_candidate_readings_extracted": False,
            "candidate_readings_compared_to_reference": False,
            "candidate_specific_sign_word_or_reading_search_performed": False,
        },
        "R3B_effect": {
            "multi_document_editorial_family_candidate_identified": status.startswith("POTENTIAL_MULTI_DOCUMENT"),
            "reference_universe_scale_compatible_with_R3B1_minimum_10": len(unique_theran_ids) >= 10,
            "candidate_actual_overlap_frozen": False,
            "exact_candidate_source_bytes_admitted": False,
            "R3B_1_admitted": False,
            "independent_transcription_replication_established": False,
        },
        "next_atomic_requirement": "Acquire unchanged original bytes for Notti 2021 and/or 2025; seal receipt before content inspection, then inventory source-native document IDs only and freeze actual overlap. If actual overlap >=10, execute the existing R3B_1 deterministic validation/holdout partition.",
        "claim_ceiling": spec["claim_ceiling"],
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "historical_unique_THE_ids": len(unique_theran_ids), "checks": checks}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
