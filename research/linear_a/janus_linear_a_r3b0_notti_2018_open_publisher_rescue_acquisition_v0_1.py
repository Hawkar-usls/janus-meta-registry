from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import urllib.request
from datetime import datetime, timezone

from pypdf import PdfReader


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pdf-tmp", required=True)
    args = ap.parse_args()

    spec_path = pathlib.Path(args.spec)
    out_path = pathlib.Path(args.out)
    pdf_path = pathlib.Path(args.pdf_tmp)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    candidate = spec["candidate"]
    url = candidate["official_publisher_pdf_url"]
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "JANUS-Linear-A-proof-carrying-research/0.1 (+https://github.com/Hawkar-usls/janus-meta-registry)"
        },
        method="GET",
    )

    http_status = None
    content_type = None
    error = None
    data = b""
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            http_status = getattr(resp, "status", None)
            content_type = resp.headers.get("Content-Type")
            data = resp.read()
    except Exception as exc:  # fail-closed, receipt still emitted
        error = f"{type(exc).__name__}: {exc}"

    pdf_magic_ok = data.startswith(b"%PDF-")
    byte_length = len(data)
    digest = sha256_bytes(data) if data else None
    page_count = None
    pdf_parse_error = None

    if data:
        pdf_path.write_bytes(data)
        if pdf_magic_ok:
            try:
                page_count = len(PdfReader(str(pdf_path)).pages)
            except Exception as exc:
                pdf_parse_error = f"{type(exc).__name__}: {exc}"

    expected_pages = int(candidate["expected_pdf_pages"])
    checks = {
        "http_200": http_status == 200,
        "nonempty_bytes": byte_length > 0,
        "pdf_magic": pdf_magic_ok,
        "sha256_present": isinstance(digest, str) and len(digest) == 64,
        "page_count_exact": page_count == expected_pages,
        "pre_seal_content_exposure_preserved": bool(spec["contamination_ledger"]["pre_seal_content_exposure_occurred"]),
        "blind_novelty_credit_forbidden": spec["contamination_ledger"]["blind_novelty_credit_allowed"] is False,
    }
    passed = all(checks.values()) and error is None and pdf_parse_error is None

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3B-0-NOTTI-2018-OPEN-PUBLISHER-RESCUE-ACQUISITION-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "alternate_editorial_source_rescue_acquisition_result",
        "status": (
            "EXACT_OPEN_PUBLISHER_BYTES_ACQUIRED_CONTENT_VISIBLE_NONBLIND_RESCUE_WITNESS"
            if passed
            else "ACQUISITION_FAILED_OR_RECEIPT_INCOMPLETE"
        ),
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_spec": str(spec_path).replace("\\", "/"),
        "candidate": candidate,
        "transport_receipt": {
            "url": url,
            "http_status": http_status,
            "content_type": content_type,
            "byte_length": byte_length,
            "sha256": digest,
            "pdf_magic_ok": pdf_magic_ok,
            "page_count": page_count,
            "expected_page_count": expected_pages,
            "transport_error": error,
            "pdf_parse_error": pdf_parse_error,
        },
        "checks": checks,
        "all_checks_pass": passed,
        "content_and_blinding_classification": {
            "pre_seal_content_exposure_occurred": True,
            "blind_novelty_credit": False,
            "scientific_use_allowed": "NONBLIND_CORRECTIVE_ALTERNATE_EDITORIAL_CONTROL",
            "pdf_bytes_persisted_in_registry": False,
        },
        "next_atomic_requirement": (
            "Freeze and execute an all-table, no-cherry-picking deterministic comparison against exact reference corpus versions; preserve all disagreements and uncertainties."
            if passed
            else "Repair only the acquisition transport/receipt layer; do not infer or inherit scientific comparison results."
        ),
        "claim_ceiling": spec["claim_ceiling"],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": checks, "receipt": result["transport_receipt"]}, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
