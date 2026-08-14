#!/usr/bin/env python3
"""Source loader for JANUS Linear A R3C parser v0.3.

The loader implements the source-level first-new-Map array boundary scanner
frozen before execution, then delegates only literal normalization to the
already-frozen JANUS-JS-LITERAL-SUBSET-v0.2 transform.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_common_v0_1 import (
    MAP_MARKER,
    PARSE_TRANSFORM_ID,
    normalize_js_literal_subset,
    sha256_bytes,
)

BOUNDARY_ID = "JANUS-JS-NEW-MAP-FIRST-ARRAY-BOUNDARY-v0.3"
LOADER_ID = "JANUS-LINEAR-A-R3C-SOURCE-LOADER-v0.3"


def extract_first_new_map_array(text: str) -> tuple[str, dict[str, Any]]:
    marker_at = text.find(MAP_MARKER)
    if marker_at < 0:
        raise ValueError("MAP_MARKER_NOT_FOUND")
    i = marker_at + len(MAP_MARKER)
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text) or text[i] != "[":
        raise ValueError("FIRST_MAP_ARGUMENT_NOT_ARRAY")
    payload_start = i

    depth = 0
    in_string = False
    escaped = False
    payload_end = None
    while i < len(text):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth < 0:
                raise ValueError("MAP_ARRAY_BRACKET_UNDERFLOW")
            if depth == 0:
                payload_end = i
                break
        i += 1

    if payload_end is None:
        raise ValueError("MAP_ARRAY_MATCHING_CLOSE_NOT_FOUND")
    if in_string:
        raise ValueError("MAP_ARRAY_ENDED_INSIDE_STRING")

    j = payload_end + 1
    while j < len(text) and text[j].isspace():
        j += 1
    terminator_at = j
    if text[j:j+2] != ");":
        observed = text[j:j+16].encode("unicode_escape").decode("ascii")
        raise ValueError(f"MAP_TERMINATOR_MISMATCH:observed={observed}")

    payload = text[payload_start:payload_end + 1]
    receipt = {
        "boundary_id": BOUNDARY_ID,
        "map_marker_source_offset": marker_at,
        "payload_start_source_offset": payload_start,
        "payload_end_source_offset_inclusive": payload_end,
        "terminator_source_offset": terminator_at,
        "terminator": ");",
        "raw_payload_characters": len(payload),
        "raw_payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "rfind_global_terminator_used": False,
        "javascript_executed": False,
        "eval_used": False,
    }
    return payload, receipt


def boundary_self_test() -> dict[str, Any]:
    source = (
        'prefix var inscriptions = new Map([\n'
        '["A",{"x":"literal ]); stays","q":"escaped \\\" quote","a":[1,2,],}],\n'
        '["B",{"x":"ok"}]\n'
        ']);\n'
        'var lexicon = new Map([["x","y"]]);\n'
    )
    payload, receipt = extract_first_new_map_array(source)
    normalized, transform = normalize_js_literal_subset(payload)
    parsed = json.loads(normalized)
    assert len(parsed) == 2
    assert parsed[0][0] == "A"
    assert parsed[0][1]["x"] == "literal ]); stays"
    assert parsed[0][1]["q"] == 'escaped " quote'
    assert parsed[1][0] == "B"
    assert "lexicon" not in payload
    return {
        "boundary_id": BOUNDARY_ID,
        "first_map_only": True,
        "string_containing_fake_terminator_preserved": True,
        "escaped_quote_preserved": True,
        "top_level_length": len(parsed),
        "synthetic_literal_transform_id": transform["transform_id"],
        "synthetic_trailing_comma_removals": len(transform["trailing_comma_removals"]),
        "receipt": receipt,
        "javascript_executed": False,
        "eval_used": False,
    }


def load_lineara_map_v0_3(path: str | Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    p = Path(path)
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    payload, boundary = extract_first_new_map_array(text)
    normalized, transform = normalize_js_literal_subset(payload)
    try:
        entries = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LINEARA_STRICT_JSON_PARSE_FAILED_AFTER_{BOUNDARY_ID}_AND_{PARSE_TRANSFORM_ID}:"
            f"line={exc.lineno}:column={exc.colno}:pos={exc.pos}:message={exc.msg}"
        ) from exc
    if not isinstance(entries, list):
        raise ValueError("LINEARA_MAP_PAYLOAD_NOT_LIST")

    docs: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError(f"LINEARA_INVALID_MAP_ENTRY:{idx}")
        doc_id, doc = entry
        if not isinstance(doc_id, str) or not isinstance(doc, dict):
            raise ValueError(f"LINEARA_INVALID_MAP_ENTRY_TYPES:{idx}")
        if doc_id in docs:
            duplicates.append(doc_id)
        docs[doc_id] = doc
    if duplicates:
        raise ValueError("LINEARA_DUPLICATE_DOCUMENT_IDS:" + ",".join(sorted(set(duplicates))))

    trailing = transform["trailing_comma_removals"]
    codepoints = transform["codepoint_escape_replacements"]
    meta = {
        "loader_id": LOADER_ID,
        "path": str(p),
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
        "document_count": len(docs),
        "boundary": boundary,
        "parse_view": {
            "transform_id": transform["transform_id"],
            "normalized_payload_characters": len(normalized),
            "normalized_payload_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "trailing_comma_removal_count": len(trailing),
            "trailing_comma_original_positions_within_extracted_payload": [r["original_payload_position"] for r in trailing],
            "trailing_comma_removals": trailing,
            "codepoint_escape_replacement_count": len(codepoints),
            "codepoint_escape_original_positions_within_extracted_payload": [r["original_payload_position"] for r in codepoints],
            "codepoint_escape_replacements": codepoints,
            "strict_json_parse_success": True,
            "source_bytes_mutated": False,
            "javascript_executed": False,
            "eval_used": False,
        },
    }
    return docs, meta


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--source")
    args = ap.parse_args()
    if args.self_test:
        print(json.dumps(boundary_self_test(), ensure_ascii=False, sort_keys=True))
        return
    if not args.source:
        raise SystemExit("--source required unless --self-test")
    docs, meta = load_lineara_map_v0_3(args.source)
    print(json.dumps({"meta": meta, "document_count": len(docs)}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
