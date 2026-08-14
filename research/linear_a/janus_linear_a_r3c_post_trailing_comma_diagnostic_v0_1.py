#!/usr/bin/env python3
"""Locate the next strict-JSON break after the already-frozen trailing-comma view.

Diagnostic only: no new normalization is introduced and no JavaScript is executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from janus_linear_a_r3c_common_v0_1 import MAP_MARKER, normalize_js_trailing_commas


def esc(s: str) -> str:
    return s.encode("unicode_escape").decode("ascii")


def normalized_to_original(norm_pos: int, removal_positions: list[int]) -> int:
    """Invert deletion-only transform positions deterministically."""
    original = norm_pos
    while True:
        removed_before_or_at = sum(1 for p in removal_positions if p <= original)
        candidate = norm_pos + removed_before_or_at
        if candidate == original:
            return original
        original = candidate


def inspect(source: str) -> dict:
    p = Path(source)
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    marker = text.find(MAP_MARKER)
    if marker < 0:
        raise ValueError("MAP_MARKER_NOT_FOUND")
    start = marker + len(MAP_MARKER)
    end = text.rfind(");")
    if end <= start:
        raise ValueError("MAP_TERMINATOR_NOT_FOUND")
    payload = text[start:end].strip()
    normalized, removals = normalize_js_trailing_commas(payload)
    positions = [r["original_payload_position"] for r in removals]
    try:
        json.loads(normalized)
    except json.JSONDecodeError as e:
        original_pos = normalized_to_original(e.pos, positions)
        nlo, nhi = max(0, e.pos - 500), min(len(normalized), e.pos + 500)
        olo, ohi = max(0, original_pos - 500), min(len(payload), original_pos + 500)
        line_start = normalized.rfind("\n", 0, e.pos) + 1
        line_end = normalized.find("\n", e.pos)
        if line_end < 0:
            line_end = len(normalized)
        fragment = normalized[max(0, e.pos - 50):min(len(normalized), e.pos + 100)]
        escape_candidates = []
        for m in re.finditer(r"\\[^\"\\/bfnrtu]|\\u[^0-9a-fA-F]|\\u[0-9a-fA-F]{0,3}(?![0-9a-fA-F])", fragment):
            escape_candidates.append({"relative_start": m.start() - min(50, e.pos), "escaped": esc(m.group(0))})
        ch = normalized[e.pos] if e.pos < len(normalized) else ""
        return {
            "status": "SECOND_STRICT_JSON_BREAK_LOCALIZED",
            "source": {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
            "transform": {
                "id": "JANUS-JS-LITERAL-TRAILING-COMMA-ONLY-v0.1",
                "removal_count": len(removals),
                "removal_positions_original": positions,
                "normalized_payload_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            },
            "json_error": {
                "message": e.msg,
                "normalized_line": e.lineno,
                "normalized_column": e.colno,
                "normalized_character_offset": e.pos,
                "mapped_original_payload_offset": original_pos,
            },
            "error_character": {
                "escaped": esc(ch),
                "codepoint": f"U+{ord(ch):04X}" if ch else None,
                "unicode_name": unicodedata.name(ch, "UNKNOWN") if ch else None,
            },
            "exact_normalized_error_line_escaped": esc(normalized[line_start:line_end]),
            "normalized_context_escaped": esc(normalized[nlo:nhi]),
            "original_context_escaped": esc(payload[olo:ohi]),
            "local_escape_candidates": escape_candidates,
            "safety": {"javascript_executed": False, "eval_used": False, "new_normalization_added": False},
        }
    return {
        "status": "STRICT_JSON_PASS_AFTER_TRAILING_COMMA_ONLY",
        "source": {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
        "transform": {"removal_count": len(removals), "normalized_payload_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest()},
        "safety": {"javascript_executed": False, "eval_used": False, "new_normalization_added": False},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--historical", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    historical = inspect(args.historical)
    current = inspect(args.current)
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1A-POST-TRAILING-COMMA-DIAGNOSTIC-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "parser_failure_diagnostic",
        "status": "SECOND_BREAK_DIAGNOSTIC_COMPLETE",
        "historical": historical,
        "current": current,
        "same_error_message": historical.get("json_error", {}).get("message") == current.get("json_error", {}).get("message"),
        "claim_ceiling": {"diagnostic_only": True, "scientific_metrics_computed": False, "R3B_effect": "NONE", "decipherment": False},
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
