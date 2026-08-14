#!/usr/bin/env python3
"""Non-evaluating JS-vs-JSON payload diagnostic for R3C parser recovery.

The script never evals/executes the source. It attempts JSON decoding only to
locate the first syntax break, then emits an escaped context and lightweight
lexical classification around that exact position.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

MAP_MARKER = "new Map("


def esc(s: str) -> str:
    return s.encode("unicode_escape").decode("ascii")


def classify_context(payload: str, pos: int) -> dict:
    before = payload[max(0, pos - 300):pos]
    after = payload[pos:min(len(payload), pos + 300)]
    nearby = before + after
    stripped_after = after.lstrip()
    ch = payload[pos] if 0 <= pos < len(payload) else ""
    prev_nonspace = next((c for c in reversed(before) if not c.isspace()), "")
    next_nonspace = next((c for c in after if not c.isspace()), "")
    candidates = {
        "line_comment_nearby": "//" in nearby,
        "block_comment_nearby": "/*" in nearby or "*/" in nearby,
        "undefined_nearby": bool(re.search(r"\bundefined\b", nearby)),
        "nan_nearby": bool(re.search(r"\bNaN\b", nearby)),
        "infinity_nearby": bool(re.search(r"\bInfinity\b", nearby)),
        "single_quote_nearby": "'" in nearby,
        "trailing_comma_candidate": bool(re.search(r",\s*[}\]]", nearby)),
        "js_identifier_value_candidate": bool(re.match(r"[A-Za-z_$][A-Za-z0-9_$]*", stripped_after)),
        "template_literal_nearby": "`" in nearby,
    }
    return {
        "character": esc(ch),
        "character_codepoint": f"U+{ord(ch):04X}" if ch else None,
        "character_unicode_name": unicodedata.name(ch, "UNKNOWN") if ch else None,
        "previous_nonspace": esc(prev_nonspace),
        "next_nonspace": esc(next_nonspace),
        "lexical_candidates": candidates,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--context", type=int, default=600)
    args = ap.parse_args()

    p = Path(args.source)
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    marker = text.find(MAP_MARKER)
    if marker < 0:
        raise SystemExit("MAP_MARKER_NOT_FOUND")
    start = marker + len(MAP_MARKER)
    end = text.rfind(");")
    if end <= start:
        raise SystemExit("MAP_TERMINATOR_NOT_FOUND")
    payload = text[start:end].strip()

    try:
        json.loads(payload)
    except json.JSONDecodeError as e:
        lo = max(0, e.pos - args.context)
        hi = min(len(payload), e.pos + args.context)
        line_start = payload.rfind("\n", 0, e.pos) + 1
        line_end = payload.find("\n", e.pos)
        if line_end < 0:
            line_end = len(payload)
        lines = payload.splitlines()
        line_lo = max(1, e.lineno - 5)
        line_hi = min(len(lines), e.lineno + 5)
        exact_lines = [
            {"line": n, "escaped": esc(lines[n - 1])}
            for n in range(line_lo, line_hi + 1)
        ]
        result = {
            "artifact_uuid": "JANUS-LINEAR-A-R3C-1A-JS-PAYLOAD-DIAGNOSTIC-RESULT-2026-08-14-v0.1",
            "version": "v0.1",
            "node_type": "parser_failure_diagnostic",
            "status": "FIRST_JSON_SYNTAX_BREAK_LOCALIZED",
            "source": {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "map_payload_characters": len(payload),
            },
            "json_error": {
                "message": e.msg,
                "line": e.lineno,
                "column": e.colno,
                "character_offset": e.pos,
            },
            "exact_error_line_escaped": esc(payload[line_start:line_end]),
            "context_window": {
                "start": lo,
                "end": hi,
                "escaped": esc(payload[lo:hi]),
            },
            "surrounding_lines": exact_lines,
            "lexical_classification": classify_context(payload, e.pos),
            "safety": {
                "javascript_executed": false,
                "eval_used": false,
                "source_mutated": false,
            },
            "claim_ceiling": {
                "parser_diagnostic_only": true,
                "scientific_metrics_computed": false,
                "R3B_effect": "NONE",
                "decipherment": false,
            },
        }
    else:
        result = {
            "artifact_uuid": "JANUS-LINEAR-A-R3C-1A-JS-PAYLOAD-DIAGNOSTIC-RESULT-2026-08-14-v0.1",
            "version": "v0.1",
            "node_type": "parser_failure_diagnostic",
            "status": "PAYLOAD_IS_STRICT_JSON_UNEXPECTED_RELATIVE_TO_PRIOR_FAILURE",
            "source": {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
            "safety": {"javascript_executed": false, "eval_used": false, "source_mutated": false},
            "claim_ceiling": {"parser_diagnostic_only": true, "scientific_metrics_computed": false, "R3B_effect": "NONE", "decipherment": false},
        }

    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
