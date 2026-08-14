#!/usr/bin/env python3
r"""Inventory active JavaScript \u{...} escapes inside double-quoted source strings.

Diagnostic only. No source mutation, parsing, eval, or JavaScript execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

DOC_START_RE = re.compile(r'\["([^"\\]+)",\{')


def nearest_document(text: str, pos: int) -> str | None:
    window_start = max(0, pos - 5000)
    matches = list(DOC_START_RE.finditer(text, window_start, pos))
    return matches[-1].group(1) if matches else None


def inventory(path: str) -> dict:
    p = Path(path)
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    rows = []
    in_string = False
    i = 0
    line = 1
    while i < len(text):
        ch = text[i]
        if ch == "\n":
            line += 1
        if not in_string:
            if ch == '"':
                in_string = True
            i += 1
            continue
        if ch == '"':
            in_string = False
            i += 1
            continue
        if ch != "\\":
            i += 1
            continue

        if i + 1 >= len(text):
            i += 1
            continue
        nxt = text[i + 1]
        if nxt == "\\":
            i += 2
            continue
        if nxt == '"':
            i += 2
            continue
        if nxt == "u" and i + 2 < len(text) and text[i + 2] == "{":
            close = text.find("}", i + 3, min(len(text), i + 12))
            literal = text[i:close + 1] if close >= 0 else text[i:min(len(text), i + 12)]
            hexpart = text[i + 3:close] if close >= 0 else ""
            valid_hex = bool(re.fullmatch(r"[0-9A-Fa-f]{1,6}", hexpart))
            cp = int(hexpart, 16) if valid_hex else None
            valid_scalar = bool(cp is not None and 0 <= cp <= 0x10FFFF and not 0xD800 <= cp <= 0xDFFF)
            rows.append({
                "source_character_offset": i,
                "source_line": line,
                "literal": literal,
                "hex": hexpart,
                "codepoint": f"U+{cp:04X}" if cp is not None else None,
                "valid_hex_1_to_6": valid_hex,
                "valid_unicode_scalar": valid_scalar,
                "document_context": nearest_document(text, i),
            })
            i = close + 1 if close >= 0 else i + 2
            continue
        i += 2

    return {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "active_js_codepoint_escape_count": len(rows),
        "valid_unicode_scalar_count": sum(1 for r in rows if r["valid_unicode_scalar"]),
        "invalid_count": sum(1 for r in rows if not r["valid_unicode_scalar"]),
        "literal_counts": Counter(r["literal"] for r in rows).most_common(),
        "document_counts": Counter(r["document_context"] for r in rows).most_common(),
        "occurrences": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--historical", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    historical = inventory(args.historical)
    current = inventory(args.current)
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1A-JS-CODEPOINT-ESCAPE-INVENTORY-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "source_grammar_inventory",
        "status": "JS_CODEPOINT_ESCAPE_INVENTORY_COMPLETE",
        "historical": historical,
        "current": current,
        "same_literal_multiset": historical["literal_counts"] == current["literal_counts"],
        "same_document_multiset": historical["document_counts"] == current["document_counts"],
        "safety": {"javascript_executed": False, "eval_used": False, "source_mutated": False},
        "claim_ceiling": {"diagnostic_only": True, "scientific_metrics_computed": False, "R3B_effect": "NONE", "decipherment": False},
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "historical_count": historical["active_js_codepoint_escape_count"], "current_count": current["active_js_codepoint_escape_count"], "historical_literals": historical["literal_counts"], "current_literals": current["literal_counts"]}, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
