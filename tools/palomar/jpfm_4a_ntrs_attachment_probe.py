#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import requests

DOC_ID = "19720015241"
LANDING = f"https://ntrs.nasa.gov/citations/{DOC_ID}"
API = f"https://ntrs.nasa.gov/api/citations/{DOC_ID}"
PDF_ENDPOINTS = [
    f"https://ntrs.nasa.gov/api/citations/{DOC_ID}/downloads/{DOC_ID}.pdf",
    f"https://ntrs.nasa.gov/api/citations/{DOC_ID}/downloads/{DOC_ID}.pdf?attachment=true",
]
UA = "JANUS-JPFM-4A-NTRS-attachment-probe/1.0 (+public-source-freeze; no-PDF-analysis)"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_get(session: requests.Session, url: str, *, timeout: int = 180) -> dict[str, Any]:
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        return {
            "ok": bool(200 <= r.status_code < 300),
            "status": int(r.status_code),
            "url": url,
            "final_url": r.url,
            "content_type": r.headers.get("content-type"),
            "content_length_header": r.headers.get("content-length"),
            "redirect_count": len(r.history),
            "bytes": len(r.content),
            "sha256": sha256(r.content),
            "content": r.content,
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": None,
            "url": url,
            "final_url": None,
            "content_type": None,
            "content_length_header": None,
            "redirect_count": None,
            "bytes": None,
            "sha256": None,
            "error_class": type(exc).__name__,
            "error": str(exc)[:1000],
            "content": None,
        }


def public_view(rec: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in rec.items() if k != "content"}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json,text/html,application/pdf,*/*"})

    landing = safe_get(session, LANDING)
    api = safe_get(session, API)
    api_summary: dict[str, Any] = public_view(api)
    if api.get("content") and str(api.get("content_type") or "").lower().startswith("application/json"):
        try:
            payload = json.loads(api["content"].decode("utf-8"))
            api_summary["json_top_level_keys"] = sorted(payload.keys()) if isinstance(payload, dict) else []
            if isinstance(payload, dict):
                api_summary["document_id_field"] = payload.get("id") or payload.get("documentId") or payload.get("stiTypeDetails")
                downloads = payload.get("downloads")
                if isinstance(downloads, list):
                    api_summary["downloads"] = [
                        {k: item.get(k) for k in ("name", "type", "links", "size", "url") if k in item}
                        for item in downloads if isinstance(item, dict)
                    ]
        except Exception as exc:
            api_summary["json_parse_error"] = repr(exc)

    attempts = []
    chosen = None
    for endpoint in PDF_ENDPOINTS:
        rec = safe_get(session, endpoint)
        is_pdf = bool(rec.get("content") and rec["content"].startswith(b"%PDF-"))
        item = public_view(rec)
        item["pdf_magic"] = is_pdf
        attempts.append(item)
        if chosen is None and rec.get("ok") and is_pdf:
            chosen = item

    if chosen:
        status = "NTRS_PUBLIC_PDF_BYTES_FROZEN__CONTENT_NOT_ANALYZED"
        disposition = "PASS_BYTE_FREEZE"
    else:
        status = "NTRS_PUBLIC_PDF_ATTACHMENT_TRANSPORT_BLOCKED_FAIL_CLOSED"
        disposition = "REMOTE_ATTACHMENT_NOT_BYTE_FROZEN"

    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-4A-NTRS-19720015241-ATTACHMENT-PROBE-v1.0",
        "experiment_id": "JPFM-4A",
        "date": dt.date.today().isoformat(),
        "status": status,
        "source": {
            "authority": "NASA Technical Reports Server (NTRS)",
            "document_id": DOC_ID,
            "report_number": "NASA-TM-X-68822",
            "landing_url": LANDING,
            "declared_attachment_name": f"{DOC_ID}.pdf",
            "population_semantics": "NASA landing metadata describes a cumulative listing of scientifically successful rockets; positive-event-only, not an all-attempt denominator.",
        },
        "landing_fetch": public_view(landing),
        "api_probe": api_summary,
        "pdf_endpoint_attempts": attempts,
        "byte_freeze": chosen,
        "disposition": disposition,
        "pdf_analysis": {
            "performed": False,
            "reason": "This probe intentionally freezes transport/bytes only. No PDF text, table, figure, row or page content is interpreted here.",
        },
        "outcome_blindness": {
            "bluebook_access": False,
            "poss1_access": False,
            "nuclear_calendar_access": False,
            "association_computed": False,
        },
        "next_gate": "If PDF bytes are frozen, perform a separate visually grounded PDF schema/page audit before any row parser is admitted; otherwise retain the attachment as remotely blocked and seek an official alternate representation.",
        "current_authority_changed": False,
        "claim_ceiling": "NASA_SOURCE_TRANSPORT_AND_BYTE_FREEZE_ONLY__NO_ROCKET_ROW_OR_ASSOCIATION_CLAIM",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
