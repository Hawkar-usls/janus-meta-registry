#!/usr/bin/env python3
"""Parser-only validation for the historical lineara.xyz annotations.js array."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_common_v0_1 import normalize_js_trailing_commas

MARKER = "var wordAnnotations"
EXPECTED_BYTES = 2239932
EXPECTED_SHA = "7ce1f87a98827d059a732cc00506c635b4d5f65b2d0e2f1592fc2b67827758cd"
TRANSFORM_ID = "JANUS-JS-LITERAL-TRAILING-COMMA-ONLY-v0.1"
BOUNDARY_ID = "JANUS-JS-STATIC-ARRAY-BRACKET-BOUNDARY-v0.1"


def extract_array(text: str) -> tuple[str, dict[str, Any]]:
    marker_at = text.find(MARKER)
    if marker_at < 0:
        raise ValueError("ANNOTATION_MARKER_NOT_FOUND")
    start = text.find("[", marker_at + len(MARKER))
    if start < 0:
        raise ValueError("ANNOTATION_ARRAY_START_NOT_FOUND")
    depth = 0
    in_string = False
    escaped = False
    end = None
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break
            if depth < 0:
                raise ValueError("ANNOTATION_ARRAY_NEGATIVE_DEPTH")
    if end is None:
        raise ValueError("ANNOTATION_ARRAY_END_NOT_FOUND")
    payload = text[start:end + 1]
    return payload, {
        "boundary_id": BOUNDARY_ID,
        "marker_source_offset": marker_at,
        "payload_start_source_offset": start,
        "payload_end_source_offset_inclusive": end,
        "payload_characters": len(payload),
        "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "string_escape_aware": True,
        "global_rfind_used": False,
    }


def self_test() -> dict[str, Any]:
    fixture = 'prefix var wordAnnotations = [{"x": ["fake ] here", 1,],},]; suffix [not-source]'
    payload, boundary = extract_array(fixture)
    norm, removals = normalize_js_trailing_commas(payload)
    parsed = json.loads(norm)
    assert parsed == [{"x": ["fake ] here", 1]}]
    assert len(removals) == 3
    return {
        "boundary_id": boundary["boundary_id"],
        "quoted_bracket_preserved": parsed[0]["x"][0] == "fake ] here",
        "trailing_comma_removals": len(removals),
        "strict_json_after_transform": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    p = Path(args.source)
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    source_ok = len(raw) == EXPECTED_BYTES and hashlib.sha256(raw).hexdigest() == EXPECTED_SHA
    st = self_test()
    payload, boundary = extract_array(text)
    normalized, removals = normalize_js_trailing_commas(payload)
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError as e:
        parse = {
            "success": False,
            "error": {"message": e.msg, "line": e.lineno, "column": e.colno, "position": e.pos},
        }
    else:
        parse = {
            "success": isinstance(parsed, list),
            "top_level_type": type(parsed).__name__,
            "top_level_item_count": len(parsed) if isinstance(parsed, list) else None,
        }
    admitted = source_ok and st["strict_json_after_transform"] and parse["success"]
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1E-ANNOTATION-TRAILING-COMMA-PARSER-VALIDATION-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "parser_correction_validation_result",
        "status": "ANNOTATION_PARSER_ADMITTED" if admitted else "ANNOTATION_PARSER_NOT_ADMITTED",
        "frozen_spec": "data/JANUS-LINEAR-A-R3C-1E-ANNOTATION-TRAILING-COMMA-PARSER-SPEC-2026-08-14-v0.1.json",
        "source": {
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "observed_source_identity_match": source_ok,
        },
        "self_test": st,
        "boundary": boundary,
        "transform": {
            "id": TRANSFORM_ID,
            "removal_count": len(removals),
            "removal_original_payload_positions": [r["original_payload_position"] for r in removals],
            "normalized_payload_characters": len(normalized),
            "normalized_payload_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        },
        "parse": parse,
        "safety": {
            "source_bytes_mutated": False,
            "javascript_executed": False,
            "eval_used": False,
            "annotation_document_identities_scored": False,
            "Briakos_419_target_used": False,
        },
        "claim_ceiling": {
            "parser_only": True,
            "annotation_source_identity_reconciled": False,
            "Briakos_scope_inference": False,
            "R3B_effect": "NONE",
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "source_ok": source_ok, "removals": len(removals), "parse": parse}, sort_keys=True))


if __name__ == "__main__":
    main()
