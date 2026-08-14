from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import unicodedata
import urllib.request
from datetime import datetime, timezone

from pypdf import PdfReader


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> tuple[int | None, str | None, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "JANUS-Linear-A-source-parser-audit/0.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return getattr(resp, "status", None), resp.headers.get("Content-Type"), resp.read()


def normalize_with_map(raw: str) -> tuple[str, list[int]]:
    out: list[str] = []
    index_map: list[int] = []
    for i, ch in enumerate(raw):
        for dch in unicodedata.normalize("NFD", ch):
            if unicodedata.category(dch) == "Mn":
                continue
            out.append(dch)
            index_map.append(i)
    return "".join(out), index_map


def row_id(line: str) -> str | None:
    if re.match(r"^THE\s+7[-–]12\b", line):
        return None
    m = re.match(r"^THE\s+Z([bBgG])\s+(\d+)\**\b", line)
    if m:
        return f"THEZ{m.group(1).upper()}{int(m.group(2))}"
    m = re.match(r"^THE\s+(\d+)([ab]?)\b", line, re.I)
    if m:
        return f"THE{int(m.group(1))}{m.group(2).upper()}"
    return None


def extract_plain_rows(reader: PdfReader, regions: list[dict]) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for reg in regions:
        page_no = int(reg["page"])
        lines = (reader.pages[page_no - 1].extract_text() or "").splitlines()
        subset = lines[int(reg["first_line"]) - 1 : int(reg["last_line"])]
        current = None
        buf: list[str] = []
        start_line = None
        for offset, line in enumerate(subset, start=int(reg["first_line"])):
            rid = row_id(line)
            is_range = bool(re.match(r"^THE\s+7[-–]12\b", line))
            if rid is not None or is_range:
                if current is not None:
                    rows[current] = {
                        "page": page_no,
                        "start_line": start_line,
                        "end_line": offset - 1,
                        "raw": "\n".join(buf),
                    }
                current = rid
                start_line = offset
                buf = [line] if rid is not None else []
            else:
                if current is not None:
                    buf.append(line)
        if current is not None:
            rows[current] = {
                "page": page_no,
                "start_line": start_line,
                "end_line": int(reg["last_line"]),
                "raw": "\n".join(buf),
            }
    return rows


def prefixed_fragments(raw: str) -> list[dict]:
    norm, idx = normalize_with_map(raw)
    starts = list(re.finditer(r"\b(?:AB|A)\s*\d", norm, flags=re.I))
    fragments: list[dict] = []
    for n, m in enumerate(starts):
        start = m.start()
        # Bound the fragment by the next explicit A/AB prefix, comma/semicolon, line break,
        # or end of row. This intentionally prevents silent concatenation of source cells.
        next_prefix = starts[n + 1].start() if n + 1 < len(starts) else len(norm)
        candidates = [next_prefix]
        for sep in [",", ";", "\n"]:
            pos = norm.find(sep, start, next_prefix)
            if pos != -1:
                candidates.append(pos)
        end = min(candidates)
        frag_norm = norm[start:end].rstrip()
        if not frag_norm:
            continue
        orig_start = idx[start] if start < len(idx) else 0
        orig_end_norm_index = max(start, end - 1)
        orig_end = (idx[orig_end_norm_index] + 1) if orig_end_norm_index < len(idx) else len(raw)
        frag_raw = raw[orig_start:orig_end]

        pm = re.match(r"(AB|A)\s*(.*)", frag_norm, flags=re.I | re.S)
        prefix = pm.group(1).upper() if pm else None
        numeric_tail = pm.group(2) if pm else ""
        # Only the first hyphen-connected numeric expression is a parser candidate.
        nm = re.match(r"([0-9\s]+(?:\s*-\s*[0-9\s]+)*)", numeric_tail)
        numeric_expr = nm.group(1).strip() if nm else ""
        components = re.split(r"\s*-\s*", numeric_expr) if numeric_expr else []
        joined_components = [re.sub(r"\s+", "", c) for c in components]
        valid_components = [c for c in joined_components if c.isdigit()]
        sign_ids = [f"{prefix}{int(c):03d}" for c in valid_components] if prefix else []
        zero_ids = [sid for sid in sign_ids if sid in {"AB000", "A000"}]
        fragments.append({
            "normalized_start": start,
            "normalized_end": end,
            "original_start": orig_start,
            "original_end": orig_end,
            "raw_fragment": frag_raw,
            "raw_fragment_sha256": hashlib.sha256(frag_raw.encode("utf-8")).hexdigest(),
            "normalized_fragment": frag_norm,
            "prefix": prefix,
            "numeric_expression": numeric_expr,
            "numeric_components_after_digit_whitespace_join": valid_components,
            "candidate_sign_ids": sign_ids,
            "zero_sign_ids": zero_ids,
            "index_map_length": len(idx),
            "source_span_mapped": bool(idx and orig_end >= orig_start),
        })
    return fragments


def classify(frags: list[dict]) -> str:
    if any(f["zero_sign_ids"] for f in frags):
        return "PARSER_NUMERIC_SEQUENCE_DEFECT"
    usable = [f for f in frags if f["candidate_sign_ids"]]
    if not usable:
        return "NO_SOURCE_SIGN_SEQUENCE"
    if len(usable) == 1:
        return "SINGLE_UNAMBIGUOUS_SOURCE_SIGN_SEQUENCE"
    return "AMBIGUOUS_MULTIFRAGMENT_SOURCE_ROW"


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
    src = spec["source_receipt"]

    status, ctype, data = fetch(src["url"])
    pdf_path.write_bytes(data)
    reader = PdfReader(str(pdf_path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            pass

    rows = extract_plain_rows(reader, spec["audit_scope"]["plain_text_regions"])
    # Preserve both plain and layout text evidence for pages 2 and 3. No reference is fetched.
    page_evidence = []
    layout_the_lines = []
    for page_no in spec["audit_scope"]["pdf_pages"]:
        page = reader.pages[int(page_no) - 1]
        plain = page.extract_text() or ""
        try:
            layout = page.extract_text(extraction_mode="layout") or ""
        except TypeError:
            layout = ""
        page_evidence.append({
            "page": page_no,
            "plain_text_sha256": hashlib.sha256(plain.encode("utf-8")).hexdigest(),
            "plain_line_count": len(plain.splitlines()),
            "layout_text_sha256": hashlib.sha256(layout.encode("utf-8")).hexdigest(),
            "layout_line_count": len(layout.splitlines()),
        })
        for line_no, line in enumerate(layout.splitlines(), start=1):
            if "THE" in line:
                layout_the_lines.append({
                    "page": page_no,
                    "line": line_no,
                    "raw_line": line,
                    "raw_line_sha256": hashlib.sha256(line.encode("utf-8")).hexdigest(),
                })

    documents = []
    for doc in spec["audit_scope"]["documents"]:
        if doc == "THE7":
            parts = [rows.get("THE7A"), rows.get("THE7B")]
            present = [p for p in parts if p]
            raw = "\n".join(p["raw"] for p in present)
            provenance = [{k: p[k] for k in ["page", "start_line", "end_line"]} for p in present]
        else:
            p = rows.get(doc)
            raw = p["raw"] if p else ""
            provenance = [{k: p[k] for k in ["page", "start_line", "end_line"]}] if p else []
        norm, idx = normalize_with_map(raw)
        frags = prefixed_fragments(raw)
        cls = classify(frags)
        documents.append({
            "document": doc,
            "source_row_provenance": provenance,
            "raw_row": raw,
            "raw_row_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest() if raw else None,
            "normalized_row": norm,
            "normalized_row_sha256": hashlib.sha256(norm.encode("utf-8")).hexdigest() if raw else None,
            "normalization_index_map_length": len(idx),
            "fragments": frags,
            "classification": cls,
        })

    by_doc = {d["document"]: d for d in documents}
    the9 = by_doc["THE9"]
    parent_defect_confirmed = (
        "AB000" not in [sid for f in the9["fragments"] for sid in f["candidate_sign_ids"]]
        and any("04" in f["numeric_expression"] and any(sid == "AB008" for sid in f["candidate_sign_ids"]) for f in the9["fragments"])
        and "AB 04-0" in the9["raw_row"]
    )

    zero_ids = [
        {"document": d["document"], "id": sid}
        for d in documents for f in d["fragments"] for sid in f["candidate_sign_ids"]
        if sid in {"AB000", "A000"}
    ]
    all_spans_mapped = all(f["source_span_mapped"] for d in documents for f in d["fragments"])
    class_counts = {c: sum(d["classification"] == c for d in documents) for c in spec["output_classes"]}

    checks = {
        "http_200": status == 200,
        "exact_bytes": len(data) == int(src["byte_length"]),
        "exact_sha256": sha256(data) == src["sha256"],
        "exact_page_count": len(reader.pages) == int(src["page_count"]),
        "all_15_source_document_slots_emitted": len(documents) == 15,
        "reference_readings_fetched": False,
        "no_zero_sign_ids_after_integrity_parser": len(zero_ids) == 0,
        "all_fragment_spans_mapped_to_original_source": all_spans_mapped,
        "THE9_parent_truncation_defect_confirmed_from_source_only": parent_defect_confirmed,
        "layout_evidence_persisted": len(page_evidence) == 2,
        "multiple_fragments_are_classified_not_concatenated": class_counts["AMBIGUOUS_MULTIFRAGMENT_SOURCE_ROW"] >= 1,
    }
    passed = all(v is True for k, v in checks.items() if k != "reference_readings_fetched") and checks["reference_readings_fetched"] is False

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3B-0-NOTTI-2018-SOURCE-PARSER-INTEGRITY-AUDIT-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "source_only_parser_integrity_audit_result",
        "status": "SOURCE_PARSER_PARENT_DEFECT_CONFIRMED_SOURCE_ONLY_CORRECTIVE_CONTRACT_READY" if passed else "SOURCE_PARSER_INTEGRITY_AUDIT_NONPASS",
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_spec": str(spec_path).replace("\\", "/"),
        "source_receipt": {"http_status": status, "content_type": ctype, "byte_length": len(data), "sha256": sha256(data), "page_count": len(reader.pages)},
        "page_evidence": page_evidence,
        "layout_lines_containing_THE": layout_the_lines,
        "documents": documents,
        "summary": {
            "document_slots": len(documents),
            "classification_counts": class_counts,
            "zero_sign_ids": zero_ids,
            "THE9_parent_truncation_defect_confirmed": parent_defect_confirmed,
            "reference_readings_fetched": False,
        },
        "checks": checks,
        "all_checks_pass": passed,
        "next_atomic_requirement": "Freeze source-parser v0.1.1 using only this source-only audit. A corrected comparison must rerun all 13 bridged documents from exact source bytes; ambiguous multifragment rows must not be collapsed into a single sequence.",
        "claim_ceiling": spec["claim_ceiling"],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "summary": result["summary"], "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
