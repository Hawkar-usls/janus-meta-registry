from __future__ import annotations

import argparse
import hashlib
import html
import json
import pathlib
import re
import unicodedata
import urllib.request
from datetime import datetime, timezone

from pypdf import PdfReader
from research.linear_a import janus_linear_a_r3b0_notti_2018_source_parser_integrity_audit_v0_1 as source_parser


def fetch_bytes(url: str) -> tuple[int | None, str | None, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "JANUS-Linear-A-corrective-sign-id/0.1.1"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return getattr(resp, "status", None), resp.headers.get("Content-Type"), resp.read()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reference_sign_ids(item_html: str) -> list[str]:
    m = re.search(
        r"<transcribed-reading-unicode>.*?<reading-text>(.*?)</reading-text>.*?</transcribed-reading-unicode>",
        item_html,
        flags=re.S | re.I,
    )
    if not m:
        return []
    block = html.unescape(m.group(1))
    ids: list[str] = []
    for ch in block:
        name = unicodedata.name(ch, "")
        mm = re.fullmatch(r"LINEAR A SIGN (AB\d{3}|A\d{3})", name)
        if mm:
            ids.append(mm.group(1))
    return ids


def levenshtein(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def lcp(a: list[str], b: list[str]) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def fresh_source_record(doc: str, rows: dict[str, dict]) -> dict:
    if doc == "THE7":
        parts = [rows.get("THE7A"), rows.get("THE7B")]
        present = [p for p in parts if p]
        raw = "\n".join(p["raw"] for p in present)
        provenance = [{k: p[k] for k in ["page", "start_line", "end_line"]} for p in present]
    else:
        p = rows.get(doc)
        raw = p["raw"] if p else ""
        provenance = [{k: p[k] for k in ["page", "start_line", "end_line"]}] if p else []
    norm, idx = source_parser.normalize_with_map(raw)
    frags = source_parser.prefixed_fragments(raw)
    cls = source_parser.classify(frags)
    return {
        "source_row_provenance": provenance,
        "raw_row_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest() if raw else None,
        "raw_row_character_count": len(raw),
        "normalized_row_sha256": hashlib.sha256(norm.encode("utf-8")).hexdigest() if raw else None,
        "normalization_index_map_length": len(idx),
        "fragments": frags,
        "source_parser_classification": cls,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--receipt", required=True)
    ap.add_argument("--bridge", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pdf-tmp", required=True)
    args = ap.parse_args()

    spec_path = pathlib.Path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    receipt = json.loads(pathlib.Path(args.receipt).read_text(encoding="utf-8"))
    bridge = json.loads(pathlib.Path(args.bridge).read_text(encoding="utf-8"))
    audit = json.loads(pathlib.Path(args.audit).read_text(encoding="utf-8"))

    status, ctype, pdf = fetch_bytes(receipt["transport_receipt"]["url"])
    pdf_path = pathlib.Path(args.pdf_tmp)
    pdf_path.write_bytes(pdf)
    reader = PdfReader(str(pdf_path))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            pass

    rows = source_parser.extract_plain_rows(reader, [
        {"page": 2, "first_line": 4, "last_line": 45},
        {"page": 3, "first_line": 4, "last_line": 15},
    ])
    audit_map = {d["document"]: d for d in audit["documents"]}
    bridge_map = {x["notti_id"]: x for x in bridge["bridged_identities"]}

    results = []
    source_audit_continuity = []
    reference_hash_continuity = []
    zero_ids = []

    for doc in spec["comparison_family"]:
        src = fresh_source_record(doc, rows)
        audit_doc = audit_map[doc]
        audit_match = (
            src["raw_row_sha256"] == audit_doc["raw_row_sha256"]
            and src["source_parser_classification"] == audit_doc["classification"]
        )
        source_audit_continuity.append(audit_match)
        for frag in src["fragments"]:
            zero_ids.extend([{"document": doc, "id": sid} for sid in frag["candidate_sign_ids"] if sid in {"AB000", "A000"}])

        b = bridge_map[doc]
        hstatus, hctype, hbytes = fetch_bytes(b["reference_url"])
        hdigest = sha256(hbytes)
        href_ok = hstatus == 200 and hdigest == b["reference_sha256"]
        reference_hash_continuity.append(href_ok)

        if src["source_parser_classification"] == "AMBIGUOUS_MULTIFRAGMENT_SOURCE_ROW":
            classification = "NONCOMPARABLE_SOURCE_ROW_AMBIGUITY"
            source_seq = None
            ref_seq = None
            distance = None
            prefix = None
        elif src["source_parser_classification"] == "NO_SOURCE_SIGN_SEQUENCE":
            classification = "NONCOMPARABLE_EMPTY_SOURCE_SEQUENCE"
            source_seq = []
            ref_seq = None
            distance = None
            prefix = None
        elif src["source_parser_classification"] == "PARSER_NUMERIC_SEQUENCE_DEFECT":
            raise RuntimeError(f"Fail-closed parser defect remained for {doc}")
        else:
            usable = [f for f in src["fragments"] if f["candidate_sign_ids"]]
            if len(usable) != 1:
                raise RuntimeError(f"Single-source classification does not have exactly one usable fragment for {doc}")
            source_seq = usable[0]["candidate_sign_ids"]
            ref_seq = reference_sign_ids(hbytes.decode("utf-8", errors="replace"))
            if not ref_seq:
                classification = "NONCOMPARABLE_EMPTY_SOURCE_SEQUENCE"
                distance = None
                prefix = None
            elif source_seq == ref_seq:
                classification = "EXACT_SIGN_ID_SEQUENCE_MATCH"
                distance = 0
                prefix = len(source_seq)
            else:
                classification = "SIGN_ID_SEQUENCE_MISMATCH"
                distance = levenshtein(source_seq, ref_seq)
                prefix = lcp(source_seq, ref_seq)

        results.append({
            "notti_id": doc,
            "reference_id": b["reference_id"],
            "source_parser_classification": src["source_parser_classification"],
            "source_audit_raw_and_classification_match": audit_match,
            "source_row_provenance": src["source_row_provenance"],
            "raw_row_sha256": src["raw_row_sha256"],
            "source_fragments": src["fragments"],
            "source_sign_ids_used_for_comparison": source_seq,
            "reference_html_sha256": hdigest,
            "reference_html_hash_matches_bridge_receipt": href_ok,
            "reference_sign_ids_used_for_comparison": ref_seq,
            "longest_common_prefix_length": prefix,
            "levenshtein_distance": distance,
            "classification": classification,
        })

    classes = spec["outcome_classes"]
    counts = {c: sum(r["classification"] == c for r in results) for c in classes}
    comparable = counts["EXACT_SIGN_ID_SEQUENCE_MATCH"] + counts["SIGN_ID_SEQUENCE_MISMATCH"]
    noncomparable = counts["NONCOMPARABLE_SOURCE_ROW_AMBIGUITY"] + counts["NONCOMPARABLE_EMPTY_SOURCE_SEQUENCE"]

    checks = {
        "parent_result_not_inherited": spec["family_rules"]["parent_v0_1_exact_or_mismatch_labels_are_not_inherited"] is True,
        "source_audit_admitted": audit["status"] == "SOURCE_PARSER_PARENT_DEFECT_CONFIRMED_SOURCE_ONLY_CORRECTIVE_CONTRACT_READY" and audit["all_checks_pass"] is True,
        "identity_bridge_admitted": bridge["status"] == "IDENTITY_BRIDGE_13_PASS_ZB14_ZB15_COLLISION_PRESERVED",
        "exact_pdf_receipt_admitted": receipt["status"] == "EXACT_OPEN_PUBLISHER_BYTES_ADMITTED_CONTENT_VISIBLE_NONBLIND_RESCUE_WITNESS",
        "fresh_pdf_http_200": status == 200,
        "fresh_pdf_same_bytes": len(pdf) == receipt["transport_receipt"]["byte_length"],
        "fresh_pdf_same_sha256": sha256(pdf) == receipt["transport_receipt"]["sha256"],
        "fresh_pdf_same_page_count": len(reader.pages) == receipt["transport_receipt"]["page_count"],
        "all_13_documents_emitted": len(results) == 13 and {r["notti_id"] for r in results} == set(spec["comparison_family"]),
        "all_source_rows_reproduce_audit": all(source_audit_continuity),
        "all_reference_hashes_reproduce_bridge": all(reference_hash_continuity),
        "zero_sign_ids_absent": zero_ids == [],
        "family_partition_complete": comparable + noncomparable == 13,
        "ambiguous_rows_never_compared": all(r["classification"] == "NONCOMPARABLE_SOURCE_ROW_AMBIGUITY" for r in results if r["source_parser_classification"] == "AMBIGUOUS_MULTIFRAGMENT_SOURCE_ROW"),
        "phonetic_transliteration_not_used": spec["reference_contract"]["phonetic_transliteration_used"] is False,
        "semantic_mapping_not_used": spec["reference_contract"]["semantic_mapping_used"] is False,
        "blind_novelty_credit_false": spec["contamination_and_claims"]["blind_novelty_credit"] is False,
        "decipherment_not_performed": spec["contamination_and_claims"]["decipherment_performed"] is False,
    }
    passed = all(checks.values())

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3B-0-NOTTI-2018-SIGN-ID-CONFORMANCE-CORRECTIVE-RESULT-2026-08-14-v0.1.1",
        "version": "v0.1.1",
        "node_type": "nonblind_corrective_alternate_editorial_sign_id_conformance_corrective_result",
        "status": "CORRECTIVE_REPLAY_ALL_13_SOURCE_AMBIGUITY_PRESERVED" if passed else "CORRECTIVE_REPLAY_NONPASS",
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_spec": str(spec_path).replace("\\", "/"),
        "parent_result_preserved_not_inherited": spec["parent_result"],
        "source_parser_audit": spec["source_parser_audit"],
        "source_receipt": {"http_status": status, "content_type": ctype, "byte_length": len(pdf), "sha256": sha256(pdf), "page_count": len(reader.pages)},
        "representation_contract": {
            "source": "source-only parser v0.1.1: exactly one A/AB prefixed fragment required for comparison",
            "reference": "Unicode character names LINEAR A SIGN AB###/A###",
            "ambiguous_source_rows": "NONCOMPARABLE; no fragment selection",
            "phonetic_values_used": False,
            "semantic_values_used": False,
        },
        "document_results": results,
        "summary": {
            "family_size": 13,
            "comparable_count": comparable,
            "exact_match_count": counts["EXACT_SIGN_ID_SEQUENCE_MATCH"],
            "mismatch_count": counts["SIGN_ID_SEQUENCE_MISMATCH"],
            "source_ambiguity_noncomparable_count": counts["NONCOMPARABLE_SOURCE_ROW_AMBIGUITY"],
            "empty_noncomparable_count": counts["NONCOMPARABLE_EMPTY_SOURCE_SEQUENCE"],
            "blind_novelty_credit": False,
            "strict_R3B_replication_established": False,
        },
        "checks": checks,
        "all_checks_pass": passed,
        "claim_ceiling": spec["claim_ceiling"],
    }
    out_path = pathlib.Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "summary": result["summary"], "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
