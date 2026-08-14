#!/usr/bin/env python3
"""Diagnose the first valid JSON value boundary inside lineara new Map(...).

Uses the already-frozen v0.2 literal normalizer, then JSONDecoder.raw_decode.
No new source normalization, eval, or JavaScript execution is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from janus_linear_a_r3c_common_v0_1 import MAP_MARKER, normalize_js_literal_subset


def esc(s: str) -> str:
    return s.encode("unicode_escape").decode("ascii")


def inspect(path: str) -> dict:
    p = Path(path)
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    marker_at = text.find(MAP_MARKER)
    if marker_at < 0:
        raise ValueError("MAP_MARKER_NOT_FOUND")
    payload_start = marker_at + len(MAP_MARKER)
    rfind_end = text.rfind(");")
    if rfind_end < payload_start:
        raise ValueError("NO_RFind_TERMINATOR")
    candidate = text[payload_start:rfind_end].strip()
    normalized, transform = normalize_js_literal_subset(candidate)
    decoder = json.JSONDecoder()
    value, end = decoder.raw_decode(normalized)
    extra = normalized[end:]
    extra_non_ws = len(extra) - len(extra.lstrip())
    first_non_ws_norm = end + extra_non_ws
    first_extra_char = normalized[first_non_ws_norm] if first_non_ws_norm < len(normalized) else ""

    # Source-level delimiter inventory near where the first decoded array should end.
    source_delims = []
    for token in ("]);", "]) ;", "] ) ;", "]);\n", "]\r\n);", ");"):
        start = 0
        while True:
            pos = text.find(token, start)
            if pos < 0:
                break
            if pos >= payload_start:
                source_delims.append({"token": esc(token), "source_offset": pos})
            start = pos + 1
    source_delims.sort(key=lambda r: r["source_offset"])

    # We cannot directly invert replacement+deletion positions for the entire value
    # without a dedicated map; instead record nearest source delimiter candidates and
    # the normalized post-value text. This is diagnostic, not an admission rule.
    return {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "map_marker_source_offset": marker_at,
        "payload_start_source_offset": payload_start,
        "rfind_terminal_source_offset": rfind_end,
        "candidate_source_characters": len(candidate),
        "normalized_characters": len(normalized),
        "normalized_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "transform_counts": {
            "trailing_comma_removals": len(transform["trailing_comma_removals"]),
            "codepoint_escape_replacements": len(transform["codepoint_escape_replacements"]),
        },
        "raw_decode": {
            "value_type": type(value).__name__,
            "top_level_length": len(value) if isinstance(value, list) else None,
            "normalized_value_end_offset": end,
            "remaining_normalized_characters": len(normalized) - end,
            "remaining_after_whitespace_characters": len(normalized) - first_non_ws_norm,
            "first_extra_character_escaped": esc(first_extra_char),
            "post_value_context_escaped": esc(normalized[max(0,end-120):min(len(normalized),end+500)]),
        },
        "source_delimiter_candidates_after_marker": source_delims[-30:],
        "safety": {
            "new_normalization_added": False,
            "javascript_executed": False,
            "eval_used": False,
            "scientific_metrics_computed": False,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--historical", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    h = inspect(args.historical)
    c = inspect(args.current)
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1A-MAP-BOUNDARY-DIAGNOSTIC-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "parser_boundary_diagnostic",
        "status": "FIRST_TOP_LEVEL_JSON_VALUE_BOUNDARY_LOCALIZED",
        "historical": h,
        "current": c,
        "same_first_extra_character": h["raw_decode"]["first_extra_character_escaped"] == c["raw_decode"]["first_extra_character_escaped"],
        "claim_ceiling": {
            "diagnostic_only": True,
            "scientific_metrics_computed": False,
            "R3B_effect": "NONE",
            "new_anchor": False,
            "decipherment": False
        }
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
