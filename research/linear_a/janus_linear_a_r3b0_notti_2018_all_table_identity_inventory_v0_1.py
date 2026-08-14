from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
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
    src = spec["source"]

    req = urllib.request.Request(
        src["url"],
        headers={"User-Agent": "JANUS-Linear-A-proof-carrying-research/0.1-table-inventory"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        http_status = getattr(resp, "status", None)
        content_type = resp.headers.get("Content-Type")
        data = resp.read()

    digest = sha256_bytes(data)
    pdf_path.write_bytes(data)
    reader = PdfReader(str(pdf_path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            pass

    regexes = [re.compile(x) for x in spec["identity_recognition"]["regexes"]]
    selected = []
    page_receipts = []
    total_text_lines = 0

    for pageno, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        page_receipts.append({
            "page": pageno,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text_characters": len(text),
            "line_count": len(text.splitlines()),
        })
        for line_no, raw in enumerate(text.splitlines(), start=1):
            total_text_lines += 1
            if "THE" not in raw:
                continue
            matches = []
            for rx in regexes:
                for m in rx.finditer(raw):
                    token = m.group(0)
                    matches.append({
                        "raw_token": token,
                        "machine_candidate": token.upper().replace(" ", ""),
                        "regex": rx.pattern,
                    })
            selected.append({
                "page": pageno,
                "line": line_no,
                "raw_line": raw,
                "raw_line_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                "recognized_identity_candidates": matches,
            })

    unique_candidates = []
    seen = set()
    for row in selected:
        for m in row["recognized_identity_candidates"]:
            c = m["machine_candidate"]
            if c not in seen:
                seen.add(c)
                unique_candidates.append(c)

    checks = {
        "http_200": http_status == 200,
        "pdf_content_type": bool(content_type and "pdf" in content_type.lower()),
        "exact_byte_length": len(data) == int(src["expected_byte_length"]),
        "exact_sha256": digest == src["expected_sha256"],
        "exact_page_count": len(reader.pages) == int(src["expected_pages"]),
        "all_pages_have_text_receipt": len(page_receipts) == int(src["expected_pages"]),
        "at_least_one_THE_line": len(selected) > 0,
        "at_least_one_recognized_identity_candidate": len(unique_candidates) > 0,
        "full_article_text_not_persisted": spec["extraction_scope"]["persist_full_article_text"] is False,
        "blind_novelty_credit_false": spec["contamination_and_use"]["blind_novelty_credit"] is False,
    }
    passed = all(checks.values())

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3B-0-NOTTI-2018-ALL-TABLE-IDENTITY-INVENTORY-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "alternate_editorial_source_table_identity_inventory_result",
        "status": "ALL_THE_LINES_INVENTORIED_NONBLIND_NO_COMPARISON" if passed else "INVENTORY_FAILED",
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_spec": str(spec_path).replace("\\", "/"),
        "source_receipt": {
            "url": src["url"],
            "http_status": http_status,
            "content_type": content_type,
            "byte_length": len(data),
            "sha256": digest,
            "page_count": len(reader.pages),
        },
        "page_text_receipts": page_receipts,
        "extraction_summary": {
            "total_pdf_text_lines": total_text_lines,
            "selected_lines_containing_THE": len(selected),
            "unique_machine_identity_candidates": unique_candidates,
            "unique_machine_identity_candidate_count": len(unique_candidates),
        },
        "selected_lines": selected,
        "checks": checks,
        "all_checks_pass": passed,
        "comparison_performed": false if False else False,
        "blind_novelty_credit": False,
        "next_atomic_requirement": "Freeze explicit source-native identity bridge from this complete inventory to exact mwenge reference IDs, then compare every bridged row without cherry-picking.",
        "claim_ceiling": spec["claim_ceiling"],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "summary": result["extraction_summary"], "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
