#!/usr/bin/env python3
"""First-party JANUS Linear A adapters into JANUS-LINEAR-TRANSCRIPTION-IR-v1.0.

Adapters are intentionally source-specific:
- mwenge/lineara.xyz consumes the frozen reading-spec row grammar and v0.6.2 typing policy;
- SigLA consumes the frozen native word-view contract and standard sign-ID seq-pattern grammar.

A shared IR is NOT permission to share a parser grammar. CTLA/TMT/RILA adapters remain blocked
until R3B-0 freezes exact source bytes/pages and source-native notation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

import janus_linear_a_full_corpus as mwbase
import janus_linear_a_parser_policy_v0_6_1 as p61
import janus_linear_a_token_typing_policy_v0_6_2 as v62
import janus_linear_a_sigla_native_blind_role_v0_1 as sigrole
import janus_linear_a_sigla_parser_integrity_preflight_v0_1 as sigpre
import janus_linear_a_transcription_ir_v1_0 as ircore

ADAPTER_SUITE_ID = "JANUS-LINEAR-A-FIRST-PARTY-IR-ADAPTERS-v1.0"
MWENGE_ADAPTER_ID = "JANUS-LINEAR-A-MWENGE-TO-IR-v1.0"
SIGLA_ADAPTER_ID = "JANUS-LINEAR-A-SIGLA-WORDVIEW-TO-IR-v1.0"

STATUS_MAP = {
    "certain": "CERTAIN",
    "doubtful": "UNCERTAIN",
    "none": "UNKNOWN",
}


def sha256_file(path: Path) -> tuple[str, int]:
    body = path.read_bytes()
    return hashlib.sha256(body).hexdigest(), len(body)


def _numeric_token_from_mwenge(raw: str) -> tuple[str, dict | None]:
    typ = v62.token_type(raw)
    if typ == "NUMERIC_EXACT":
        parsed = ircore.parse_generic_unicode_rational(raw)
        if not parsed or parsed.get("kind") != "EXACT":
            raise ValueError(f"MWENGE_EXACT_NUMERIC_IR_PARSE_FAIL:{raw}")
        denominator = int(parsed["denominator"])
        token_type = "FRACTION_EXACT" if denominator != 1 else "NUMERIC_EXACT"
        return token_type, {
            "source_expression": raw,
            "numerator": parsed["numerator"],
            "denominator": parsed["denominator"],
            "canonical_fraction": parsed["canonical_fraction"],
        }
    if typ == "NUMERIC_APPROX_OR_UNCERTAIN":
        parsed = ircore.parse_generic_unicode_rational(raw)
        token_type = "NUMERIC_APPROX_OR_UNCERTAIN"
        if parsed and parsed.get("kind") == "APPROX_OR_UNCERTAIN":
            stripped = raw.strip()
            while stripped.startswith(v62.APPROX_PREFIXES):
                stripped = stripped[1:].strip()
            inner = ircore.parse_generic_unicode_rational(stripped)
            if inner and inner.get("kind") == "EXACT" and int(inner["denominator"]) != 1:
                token_type = "FRACTION_APPROX_OR_UNCERTAIN"
            return token_type, {
                "marker": parsed.get("marker"),
                "source_expression": raw,
                "bounded_interval": None,
                "exact_value": None,
            }
        return token_type, {
            "marker": None,
            "source_expression": raw,
            "bounded_interval": None,
            "exact_value": None,
        }
    if typ == "PUNCTUATION":
        return "PUNCTUATION", None
    return "SIGN", None


def mwenge_item_to_ir(path: Path, *, source_locator: str | None = None) -> dict:
    """Convert one frozen mwenge HTML item into lossless JANUS IR."""
    body_bytes = path.read_bytes()
    text = body_bytes.decode("utf-8", errors="replace")
    m = mwbase.READING_SPEC_RE.search(text)
    if not m:
        raise ValueError(f"MWENGE_READING_SPEC_NOT_FOUND:{path}")
    body = mwbase.TAG_RE.sub("", m.group(1))

    rows = []
    for source_line, raw_line in enumerate(body.splitlines(), start=1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        rm = mwbase.ROW_RE.match(raw_line)
        if not rm:
            continue
        row_i, line_i, word_i, token, status = rm.groups()
        rows.append({
            "source_line": source_line,
            "row": int(row_i),
            "line": int(line_i),
            "word": int(word_i),
            "token": token.strip(),
            "status": status.lower(),
        })
    if not rows:
        raise ValueError(f"MWENGE_NO_TYPED_ROWS:{path}")

    file_sha = hashlib.sha256(body_bytes).hexdigest()
    file_id = "F1"
    base_prov = {
        "file_id": file_id,
        "page": None,
        "bbox": None,
        "source_url": source_locator,
        "extraction_method": "SOURCE_HTML",
        "extractor_version": MWENGE_ADAPTER_ID,
    }

    # Lines are source-native layout segments. Multiple row indices may map to a line; preserve both in source_label.
    line_keys = []
    for r in rows:
        key = (r["row"], r["line"])
        if key not in line_keys:
            line_keys.append(key)
    segment_id_by_key = {key: f"L{i}" for i, key in enumerate(line_keys)}

    provenance_refs = []
    tokens = []
    by_word: dict[int, list[str]] = defaultdict(list)
    token_seq = 0
    for r in rows:
        pref = f"P{token_seq + 1}"
        provenance_refs.append({
            "ref_id": pref,
            **base_prov,
            "line": r["source_line"],
            "source_record_id": f"row={r['row']};line={r['line']};word={r['word']};token-ordinal={token_seq}",
        })
        token_type, numeric = _numeric_token_from_mwenge(r["token"])
        tid = f"T{token_seq}"
        gid = f"G{r['word']}"
        token = {
            "token_id": tid,
            "source_raw": r["token"],
            "token_type": token_type,
            "sequence_index": token_seq,
            "source_sign_id": r["token"] if token_type == "SIGN" else None,
            "source_reading_label": None,
            "normalized_sign_id": r["token"] if token_type == "SIGN" else None,
            "segment_id": segment_id_by_key[(r["row"], r["line"])],
            "group_ids": [gid],
            "reading_status": STATUS_MAP.get(r["status"], "UNKNOWN"),
            "certainty": None,
            "alternatives": [],
            "numeric": numeric,
            "damage": None,
            "editorial": None,
            "provenance_refs": [pref],
        }
        tokens.append(token)
        by_word[r["word"]].append(tid)
        token_seq += 1

    groups = []
    for word_i in sorted(by_word):
        member_ids = by_word[word_i]
        member_tokens = [next(t for t in tokens if t["token_id"] == tid) for tid in member_ids]
        member_types = {t["token_type"] for t in member_tokens}
        if member_types and all(t in {"NUMERIC_EXACT", "FRACTION_EXACT", "NUMERIC_APPROX_OR_UNCERTAIN", "FRACTION_APPROX_OR_UNCERTAIN", "PUNCTUATION"} for t in member_types):
            group_type = "SOURCE_NUMERIC_GROUP"
        else:
            group_type = "SOURCE_WORD"
        prov = []
        for t in member_tokens:
            prov.extend(t["provenance_refs"])
        groups.append({
            "group_id": f"G{word_i}",
            "group_type": group_type,
            "member_token_ids": member_ids,
            "source_group_index": word_i,
            "derived": False,
            "provenance_refs": sorted(set(prov)),
        })

    segments = []
    for index, key in enumerate(line_keys):
        member_rows = [r for r in rows if (r["row"], r["line"]) == key]
        segments.append({
            "segment_id": segment_id_by_key[key],
            "segment_type": "LINE",
            "parent_segment_id": None,
            "surface_id": None,
            "source_label": f"row={key[0]};line={key[1]}",
            "sequence_index": index,
            "bbox": None,
            "polygon": None,
            "provenance_refs": sorted({f"P{rows.index(r)+1}" for r in member_rows}),
        })

    relations = []
    for i, (a, b) in enumerate(zip(tokens, tokens[1:])):
        relations.append({
            "relation_id": f"R{i}",
            "relation_type": "NEXT_TOKEN",
            "source_refs": [f"token:{a['token_id']}"],
            "target_refs": [f"token:{b['token_id']}"],
            "evidence_class": "SOURCE_NATIVE",
            "provenance_refs": sorted(set(a["provenance_refs"] + b["provenance_refs"])),
        })

    ir = {
        "ir_format": ircore.IR_FORMAT,
        "source": {
            "source_id": "MWENGE-LINEARA-XYZ",
            "source_family": "MWENGE_LINEARA_XYZ",
            "edition_id": mwbase.CORPUS_COMMIT,
            "independence_level": "L0_DERIVATIVE_TRANSFORM",
            "adapter_id": MWENGE_ADAPTER_ID,
            "native_identifier_scheme": "mwenge document stem + reading-spec raw tokens",
            "native_numeric_grammar_id": "JANUS-LINA-TOKEN-TYPING-POLICY-v0.6.2",
            "native_uncertainty_grammar_id": "mwenge-reading-spec:certain|doubtful|none",
            "native_boundary_grammar_id": "mwenge-reading-spec:row,line,word indices",
        },
        "document": {
            "document_id": path.stem,
            "source_document_id": path.stem,
            "artifact_class": "UNKNOWN",
            "site": mwbase.region_of(path.stem),
        },
        "surfaces": [],
        "segments": segments,
        "tokens": tokens,
        "groups": groups,
        "relations": relations,
        "disagreements": [],
        "provenance_receipt": {
            "source_files": [{
                "file_id": file_id,
                "filename": path.name,
                "sha256": file_sha,
                "bytes": len(body_bytes),
                "mime_type": "text/html",
                "page_count": None,
                "source_locator": source_locator,
            }],
            "provenance_refs": provenance_refs,
            "adapter": {
                "adapter_id": MWENGE_ADAPTER_ID,
                "suite_id": ADAPTER_SUITE_ID,
                "source_parser": "reading-spec + ROW_RE",
                "typing_policy": v62.POLICY_ID,
            },
            "ingest_timestamp": "2026-08-14T14:56:00+03:00",
            "validation_state": "SEALED_VALIDATION_PENDING",
            "ir_sha256": None,
        },
    }
    sealed = ircore.seal_ir(ir)
    errors = ircore.validate_ir(sealed)
    if errors:
        raise ValueError("MWENGE_IR_VALIDATION_FAIL:" + "|".join(errors[:20]))
    return sealed


def _sigla_contract(html_text: str) -> tuple[sigpre.InterfaceParser, dict]:
    parser = sigpre.InterfaceParser()
    parser.feed(html_text)
    structural_state = sigpre.structural_counts(html_text)
    missing_scripts = sorted(sigpre.REQUIRED_SCRIPTS - set(parser.scripts))
    missing_classes = sorted(sigpre.REQUIRED_CLASSES - parser.classes)
    missing_style = sigpre.REQUIRED_STYLESHEET not in set(parser.stylesheets)
    sign_view_count = sum(1 for a in parser.anchors if a["text"] == "[sign view]")
    failures = []
    if missing_scripts: failures.append("missing_required_scripts")
    if missing_classes: failures.append("missing_required_classes")
    if missing_style: failures.append("missing_required_stylesheet")
    if sign_view_count < 1: failures.append("missing_sign_view_anchor")
    if structural_state["document_view_container_count"] != 1: failures.append("document_view_container_count_not_one")
    return parser, {
        "pass": not failures,
        "failures": failures,
        "sign_view_anchor_count": sign_view_count,
        "document_view_container_count": structural_state["document_view_container_count"],
    }


def sigla_word_view_to_ir(path: Path, *, sigla_id: str, source_locator: str | None = None) -> dict:
    """Convert one frozen SigLA native word-view HTML page into sign-token IR.

    Only the frozen machine `!seq-pattern:` sign-ID sequence is tokenized. Visible transliteration
    is intentionally not required for token identity. A source-native word group is created for
    each seq-pattern anchor, but it remains SOURCE_WORD rather than universal linguistic wordhood.
    """
    body_bytes = path.read_bytes()
    html_text = body_bytes.decode("utf-8", errors="replace")
    interface, contract = _sigla_contract(html_text)
    if not contract["pass"]:
        raise ValueError(f"SIGLA_INTERFACE_CONTRACT_FAIL:{sigla_id}:{contract['failures']}")

    visible = interface.norm(" ".join(interface.visible_parts))
    matches = sigrole.WORD_COUNT_RE.findall(visible)
    if len(matches) != 1:
        raise ValueError(f"SIGLA_WORD_COUNT_PARSE_FAIL:{sigla_id}:{len(matches)}")
    reported = int(matches[0])

    word_rows = []
    for anchor in interface.anchors:
        href = anchor.get("href") or ""
        m = sigrole.SEQ_RE.search(href)
        if not m:
            continue
        pattern = m.group(1).strip()
        if not pattern:
            raise ValueError(f"SIGLA_EMPTY_SEQ_PATTERN:{sigla_id}")
        # Frozen SigLA standard sign-ID sequence grammar observed in the claim-bearing parser.
        sign_ids = pattern.split("-")
        if not sign_ids or any(not re.fullmatch(r"[A-Za-z0-9*]+", x) for x in sign_ids):
            raise ValueError(f"SIGLA_SIGN_ID_SEQUENCE_GRAMMAR_FAIL:{sigla_id}:{pattern}")
        word_rows.append({"href": href, "pattern": pattern, "sign_ids": sign_ids})
    if len(word_rows) != reported:
        raise ValueError(f"SIGLA_REPORTED_WORD_COUNT_MISMATCH:{sigla_id}:reported={reported}:observed={len(word_rows)}")

    file_sha = hashlib.sha256(body_bytes).hexdigest()
    provenance_refs = [{
        "ref_id": "P0",
        "file_id": "F1",
        "page": None,
        "line": None,
        "bbox": None,
        "source_record_id": f"document-word-view:{sigla_id}",
        "source_url": source_locator,
        "extraction_method": "SOURCE_HTML",
        "extractor_version": SIGLA_ADAPTER_ID,
    }]
    tokens = []
    groups = []
    relations = []
    token_seq = 0
    previous_tid = None
    for wi, word in enumerate(word_rows):
        pref = f"P{wi + 1}"
        provenance_refs.append({
            "ref_id": pref,
            "file_id": "F1",
            "page": None,
            "line": None,
            "bbox": None,
            "source_record_id": f"word-ordinal={wi};seq-pattern={word['pattern']}",
            "source_url": source_locator,
            "extraction_method": "SOURCE_HTML",
            "extractor_version": SIGLA_ADAPTER_ID,
        })
        member_ids = []
        for sign_id in word["sign_ids"]:
            tid = f"T{token_seq}"
            member_ids.append(tid)
            tokens.append({
                "token_id": tid,
                "source_raw": sign_id,
                "token_type": "SIGN",
                "sequence_index": token_seq,
                "source_sign_id": sign_id,
                "source_reading_label": None,
                "normalized_sign_id": sign_id,
                "segment_id": None,
                "group_ids": [f"G{wi}"],
                "reading_status": "UNKNOWN",
                "certainty": None,
                "alternatives": [],
                "numeric": None,
                "damage": None,
                "editorial": None,
                "provenance_refs": [pref],
            })
            if previous_tid is not None:
                relations.append({
                    "relation_id": f"R{len(relations)}",
                    "relation_type": "NEXT_TOKEN",
                    "source_refs": [f"token:{previous_tid}"],
                    "target_refs": [f"token:{tid}"],
                    "evidence_class": "SOURCE_NATIVE",
                    "provenance_refs": [pref],
                })
            previous_tid = tid
            token_seq += 1
        groups.append({
            "group_id": f"G{wi}",
            "group_type": "SOURCE_WORD",
            "member_token_ids": member_ids,
            "source_group_index": wi,
            "source_sequence_expression": word["pattern"],
            "source_reference_href": word["href"],
            "derived": False,
            "provenance_refs": [pref],
        })

    ir = {
        "ir_format": ircore.IR_FORMAT,
        "source": {
            "source_id": "SIGLA",
            "source_family": "SIGLA_THE_SIGNS_OF_LINEAR_A",
            "edition_id": sigpre.REQUIRED_DB_SHA,
            "independence_level": "L1_INDEPENDENT_DIGITIZATION_SHARED_TRANSCRIPTION",
            "adapter_id": SIGLA_ADAPTER_ID,
            "native_identifier_scheme": "SigLA document id + standard sign IDs in word-match !seq-pattern anchors",
            "native_numeric_grammar_id": "NOT_USED_BY_WORD_VIEW_SEQ_PATTERN_ADAPTER-v1.0",
            "native_uncertainty_grammar_id": "SIGLA_WORD_VIEW_SEQ_PATTERN_ONLY_NO_VISIBLE_TRANSLITERATION_UNCERTAINTY-v1.0",
            "native_boundary_grammar_id": "SigLA reported words + seq-pattern anchor order + word-N/index-word-N structural contract",
        },
        "document": {
            "document_id": sigla_id.replace(" ", ""),
            "source_document_id": sigla_id,
            "artifact_class": "UNKNOWN",
            "site": sigrole.location_from_sigla_id(sigla_id),
        },
        "surfaces": [],
        "segments": [],
        "tokens": tokens,
        "groups": groups,
        "relations": relations,
        "disagreements": [],
        "provenance_receipt": {
            "source_files": [{
                "file_id": "F1",
                "filename": path.name,
                "sha256": file_sha,
                "bytes": len(body_bytes),
                "mime_type": "text/html",
                "page_count": None,
                "source_locator": source_locator,
            }],
            "provenance_refs": provenance_refs,
            "adapter": {
                "adapter_id": SIGLA_ADAPTER_ID,
                "suite_id": ADAPTER_SUITE_ID,
                "interface_contract": "JANUS-LINEAR-A-SIGLA-SOURCE-ADAPTER-CONTRACT-2026-08-14-v0.1",
                "unit_reference_contract": "JANUS-LINEAR-A-SIGLA-WORD-UNIT-REFERENCE-CONTRACT-2026-08-14-v0.1",
                "content_identity": "standard sign-ID sequence from !seq-pattern anchor; visible transliteration excluded from identity",
            },
            "ingest_timestamp": "2026-08-14T14:56:00+03:00",
            "validation_state": "SEALED_VALIDATION_PENDING",
            "ir_sha256": None,
        },
    }
    sealed = ircore.seal_ir(ir)
    errors = ircore.validate_ir(sealed)
    if errors:
        raise ValueError("SIGLA_IR_VALIDATION_FAIL:" + "|".join(errors[:20]))
    return sealed


def adapter_manifest() -> dict:
    return {
        "suite_id": ADAPTER_SUITE_ID,
        "ir_format": ircore.IR_FORMAT,
        "adapters": {
            "mwenge": {
                "adapter_id": MWENGE_ADAPTER_ID,
                "source_grammar": "reading-spec ROW_RE + v0.6.2 token typing",
                "numeric_grammar": v62.POLICY_ID,
                "lossless_raw": True,
                "source_native_boundaries": ["row", "line", "word"],
                "independence_level": "L0_DERIVATIVE_TRANSFORM",
            },
            "sigla": {
                "adapter_id": SIGLA_ADAPTER_ID,
                "source_grammar": "frozen SigLA word-view interface + !seq-pattern standard sign-ID sequence",
                "numeric_grammar": "NOT_USED_BY_THIS_ADAPTER",
                "lossless_machine_sequence": True,
                "visible_transliteration_required": False,
                "source_native_boundaries": ["reported_word_count", "seq-pattern anchor order", "word ordinal reference contract"],
                "independence_level": "L1_INDEPENDENT_DIGITIZATION_SHARED_TRANSCRIPTION",
            },
        },
        "blocked_future_adapters": ["CTLA", "TMT", "RILA_S1"],
        "unblock_condition": "Exact source bytes/pages and source-native notation grammar frozen under R3B-0/R3B-1.",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_m = sub.add_parser("mwenge")
    p_m.add_argument("path")
    p_m.add_argument("--source-locator", default=None)
    p_m.add_argument("--out", required=True)

    p_s = sub.add_parser("sigla")
    p_s.add_argument("path")
    p_s.add_argument("--sigla-id", required=True)
    p_s.add_argument("--source-locator", default=None)
    p_s.add_argument("--out", required=True)

    sub.add_parser("manifest")
    args = ap.parse_args()
    if args.cmd == "manifest":
        print(json.dumps(adapter_manifest(), ensure_ascii=False, indent=2, sort_keys=True))
        return
    if args.cmd == "mwenge":
        ir = mwenge_item_to_ir(Path(args.path), source_locator=args.source_locator)
    else:
        ir = sigla_word_view_to_ir(Path(args.path), sigla_id=args.sigla_id, source_locator=args.source_locator)
    Path(args.out).write_text(json.dumps(ir, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "ir_sha256": ir["provenance_receipt"]["ir_sha256"],
        "document": ir["document"]["document_id"],
        "tokens": len(ir["tokens"]),
        "groups": len(ir["groups"]),
        "valid": not ircore.validate_ir(ir),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
