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
    recovery = spec["recovery_constraints"]
    url = candidate["official_publisher_pdf_url"]
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "JANUS-Linear-A-proof-carrying-research/0.1.1 (+https://github.com/Hawkar-usls/janus-meta-registry)"
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
    except Exception as exc:
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
    expected_bytes = int(recovery["expected_byte_length_from_failed_transport"])
    expected_sha = recovery["expected_sha256_from_failed_transport"]
    checks = {
        "http_200": http_status == 200,
        "nonempty_bytes": byte_length > 0,
        "pdf_magic": pdf_magic_ok,
        "sha256_present": isinstance(digest, str) and len(digest) == 64,
        "same_byte_length_as_parent_failed_transport": byte_length == expected_bytes,
        "same_sha256_as_parent_failed_transport": digest == expected_sha,
        "page_count_exact": page_count == expected_pages,
        "blind_novelty_credit_forbidden": spec["contamination_ledger"]["blind_novelty_credit_allowed"] is False,
        "scientific_comparison_not_started": recovery["scientific_comparison_must_not_start_in_this_gate"] is True,
    }
    passed = all(checks.values()) and error is None and pdf_parse_error is None

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3B-0-NOTTI-2018-OPEN-PUBLISHER-RESCUE-ACQUISITION-RESULT-2026-08-14-v0.1.1",
        "version": "v0.1.1",
        "node_type": "alternate_editorial_source_rescue_acquisition_result",
        "status": (
            "EXACT_OPEN_PUBLISHER_BYTES_ADMITTED_CONTENT_VISIBLE_NONBLIND_RESCUE_WITNESS"
            if passed
            else "RECOVERY_ACQUISITION_FAILED_OR_RECEIPT_INCOMPLETE"
        ),
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_spec": str(spec_path).replace("\\", "/"),
        "parent_failed_run_receipt": spec["parent_failed_run_receipt"],
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
        "recovery_continuity": {
            "expected_parent_byte_length": expected_bytes,
            "expected_parent_sha256": expected_sha,
            "same_bytes_reproduced": byte_length == expected_bytes and digest == expected_sha,
            "scientific_scope_changed": false if False else False,
        },
        "checks": checks,
        "all_checks_pass": passed,
        "content_and_blinding_classification": {
            "pre_seal_content_exposure_occurred": True,
            "blind_novelty_credit": False,
            "scientific_use_allowed": "NONBLIND_CORRECTIVE_ALTERNATE_EDITORIAL_CONTROL",
            "scientific_comparison_started_in_this_gate": False,
            "pdf_bytes_persisted_in_registry": False,
        },
        "next_atomic_requirement": (
            "Freeze and execute a deterministic all-table comparison against exact reference corpus versions; preserve every disagreement, uncertainty and source-only reading; no cherry-picking."
            if passed
            else "Repair only the acquisition dependency/transport layer; do not inherit scientific comparison results."
        ),
        "claim_ceiling": spec["claim_ceiling"],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": checks, "receipt": result["transport_receipt"]}, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
