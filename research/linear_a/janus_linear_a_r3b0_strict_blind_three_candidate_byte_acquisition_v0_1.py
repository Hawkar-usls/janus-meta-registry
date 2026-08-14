from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser


class AnchorCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[dict] = []
        self._current: dict | None = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        d = dict(attrs)
        if d.get("href"):
            self._current = {"href": d["href"], "text": ""}
            self.anchors.append(self._current)

    def handle_data(self, data):
        if self._current is not None:
            self._current["text"] += data

    def handle_endtag(self, tag):
        if tag.lower() == "a":
            self._current = None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> tuple[int | None, str | None, str, bytes]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "JANUS-Linear-A-strict-blind-byte-acquisition/0.1",
            "Accept": "text/html,application/pdf,application/octet-stream;q=0.9,*/*;q=0.1",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return (
            getattr(resp, "status", None),
            resp.headers.get("Content-Type"),
            resp.geturl(),
            resp.read(),
        )


def metadata_endpoints(base_url: str, html_bytes: bytes, expected_filename: str) -> list[dict]:
    text = html_bytes.decode("utf-8", errors="replace")
    parser = AnchorCollector()
    parser.feed(text)
    candidates: list[dict] = []
    expected_norm = expected_filename.casefold()

    for a in parser.anchors:
        href = a["href"].strip()
        absolute = urllib.parse.urljoin(base_url, href)
        decoded_url = urllib.parse.unquote(absolute).casefold()
        anchor_text = " ".join(a["text"].split()).casefold()
        is_byte_pattern = any(x in absolute.lower() for x in ["/retrieve/", "/bitstream/"]) or absolute.lower().split("?", 1)[0].endswith(".pdf")
        bound = expected_norm in decoded_url or expected_norm in anchor_text
        if is_byte_pattern:
            candidates.append({
                "url": absolute,
                "binding": "EXPECTED_FILENAME" if bound else "SAME_METADATA_RECORD_BYTE_PATTERN",
                "anchor_text_sha256": sha256(anchor_text.encode("utf-8")),
            })

    # Some IRIS deployments surface retrieve URLs in script/data attributes rather than anchors.
    for m in re.finditer(r'''(?:https?://[^\s"'<>]+|/[^\s"'<>]+)(?:retrieve|bitstream)[^\s"'<>]*''', text, flags=re.I):
        raw = m.group(0)
        absolute = urllib.parse.urljoin(base_url, raw)
        decoded_url = urllib.parse.unquote(absolute).casefold()
        candidates.append({
            "url": absolute,
            "binding": "EXPECTED_FILENAME" if expected_norm in decoded_url else "SAME_METADATA_RECORD_BYTE_PATTERN",
            "anchor_text_sha256": None,
        })

    dedup: dict[str, dict] = {}
    for c in candidates:
        dedup.setdefault(c["url"], c)
    return list(dedup.values())


def classify_probe(status, content_type, body: bytes) -> str:
    if status == 200 and body.startswith(b"%PDF-"):
        return "PRECONTENT_EXACT_PDF_BYTES_SEALED"
    if status in {401, 403}:
        return "METADATA_RETRIEVE_ENDPOINT_FOUND_BUT_BYTES_RESTRICTED"
    return "FETCHED_NONPDF_RESPONSE_NOT_ADMITTED"


def process_candidate(c: dict) -> dict:
    metadata_urls = [c["metadata_url"]]
    if c.get("secondary_metadata_url"):
        metadata_urls.append(c["secondary_metadata_url"])

    metadata_receipts = []
    endpoints: list[dict] = []
    metadata_failures = []

    for mu in metadata_urls:
        try:
            status, ctype, final_url, body = fetch(mu)
            metadata_receipts.append({
                "requested_url": mu,
                "resolved_url": final_url,
                "http_status": status,
                "content_type": ctype,
                "byte_length": len(body),
                "sha256": sha256(body),
                "content_inspected": False,
            })
            if status == 200:
                endpoints.extend(metadata_endpoints(final_url, body, c["expected_filename"]))
        except Exception as e:
            metadata_failures.append({
                "requested_url": mu,
                "exception_type": type(e).__name__,
                "message_sha256": sha256(str(e).encode("utf-8")),
            })

    dedup: dict[str, dict] = {}
    for ep in endpoints:
        dedup.setdefault(ep["url"], ep)
    endpoints = list(dedup.values())

    byte_probes = []
    sealed = []
    for ep in endpoints:
        try:
            status, ctype, final_url, body = fetch(ep["url"])
            cls = classify_probe(status, ctype, body)
            receipt = {
                "discovered_url": ep["url"],
                "resolved_byte_url": final_url,
                "binding": ep["binding"],
                "http_status": status,
                "content_type": ctype,
                "byte_length": len(body),
                "sha256": sha256(body),
                "pdf_magic": body[:5].decode("ascii", errors="replace"),
                "classification": cls,
                "content_parser_imported": False,
                "pdf_text_extraction": False,
                "pdf_rendering": False,
                "ocr": False,
                "body_preview_persisted": False,
            }
            byte_probes.append(receipt)
            if cls == "PRECONTENT_EXACT_PDF_BYTES_SEALED":
                sealed.append(receipt)
        except urllib.error.HTTPError as e:
            byte_probes.append({
                "discovered_url": ep["url"],
                "resolved_byte_url": getattr(e, "url", ep["url"]),
                "binding": ep["binding"],
                "http_status": e.code,
                "content_type": e.headers.get("Content-Type") if e.headers else None,
                "byte_length": None,
                "sha256": None,
                "pdf_magic": None,
                "classification": "METADATA_RETRIEVE_ENDPOINT_FOUND_BUT_BYTES_RESTRICTED" if e.code in {401, 403} else "NETWORK_OR_TRANSPORT_FAILURE_NOT_ADMITTED",
                "response_body_read": False,
            })
        except Exception as e:
            byte_probes.append({
                "discovered_url": ep["url"],
                "binding": ep["binding"],
                "classification": "NETWORK_OR_TRANSPORT_FAILURE_NOT_ADMITTED",
                "exception_type": type(e).__name__,
                "message_sha256": sha256(str(e).encode("utf-8")),
            })

    if sealed:
        overall = "PRECONTENT_EXACT_PDF_BYTES_SEALED"
    elif endpoints and any(x.get("classification") == "METADATA_RETRIEVE_ENDPOINT_FOUND_BUT_BYTES_RESTRICTED" for x in byte_probes):
        overall = "METADATA_RETRIEVE_ENDPOINT_FOUND_BUT_BYTES_RESTRICTED"
    elif endpoints:
        overall = "FETCHED_NONPDF_RESPONSE_NOT_ADMITTED"
    elif metadata_receipts:
        overall = "METADATA_NO_BYTE_ENDPOINT_FOUND"
    else:
        overall = "NETWORK_OR_TRANSPORT_FAILURE_NOT_ADMITTED"

    return {
        "candidate_id": c["candidate_id"],
        "handle": c.get("handle"),
        "doi": c.get("doi"),
        "expected_filename": c["expected_filename"],
        "metadata_receipts": metadata_receipts,
        "metadata_failures": metadata_failures,
        "discovered_byte_endpoint_count": len(endpoints),
        "byte_probes": byte_probes,
        "sealed_pdf_receipts": sealed,
        "classification": overall,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec_path = pathlib.Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    results = [process_candidate(c) for c in spec["candidates"]]
    sealed_candidates = [r["candidate_id"] for r in results if r["classification"] == "PRECONTENT_EXACT_PDF_BYTES_SEALED"]

    checks = {
        "three_candidates_executed": len(results) == 3,
        "content_parser_never_imported": True,
        "pdf_text_extraction_never_called": True,
        "pdf_rendering_never_called": True,
        "ocr_never_called": True,
        "source_native_sign_readings_seen_false": spec["blindness_contract"]["source_native_sign_readings_seen"] is False,
        "blind_overlap_selection_performed_false": spec["blindness_contract"]["blind_overlap_selection_performed"] is False,
        "pdf_bytes_not_stored_in_repository": spec["byte_acquisition_policy"]["store_pdf_bytes_in_repository"] is False,
    }

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3B-0-STRICT-BLIND-THREE-CANDIDATE-BYTE-ACQUISITION-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "precontent_exact_byte_acquisition_result",
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_spec": str(spec_path).replace("\\", "/"),
        "status": "STRICT_R3B_PRECONTENT_BYTE_SEAL_OBTAINED" if sealed_candidates else "STRICT_R3B_PRECONTENT_BYTE_SEAL_NOT_OBTAINED",
        "candidate_results": results,
        "summary": {
            "candidate_count": len(results),
            "sealed_candidate_count": len(sealed_candidates),
            "sealed_candidates": sealed_candidates,
            "source_native_sign_readings_seen": False,
            "source_content_inspected": False,
            "overlap_selected": False,
            "scientific_comparison_performed": False,
            "strict_r3b_replication_established": False,
        },
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "next_atomic_requirement": "If a candidate is sealed, persist this receipt before any content-reading gate. Only a later separately frozen workflow may inspect the sealed PDF and freeze source-native overlap.",
        "claim_ceiling": spec["claim_ceiling"],
    }

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "summary": result["summary"], "candidate_classifications": {r["candidate_id"]: r["classification"] for r in results}}, ensure_ascii=False, indent=2))
    return 0 if result["all_checks_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
