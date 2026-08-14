#!/usr/bin/env python3
"""Shared punctuation-aware parser policy for the JANUS Linear A corrective replay v0.6.1.

This module preserves the historical pre-filter runners and provides corrected parser
functions for replay. The correction removes Aegean punctuation/control markers from the
lexical/logographic candidate universe before any hashing, scoring, null generation, or
record-role geometry is computed.

The frozen corpus maps:
  *900 -> U+10101 AEGEAN WORD SEPARATOR DOT
  *901 -> U+10100 AEGEAN WORD SEPARATOR LINE
  *902 -> U+10100 AEGEAN WORD SEPARATOR LINE (corpus alias)
  *903 -> U+10102 AEGEAN CHECK MARK

*904 is intentionally NOT filtered: the frozen corpus maps it back into the Linear A sign
repertoire rather than Aegean punctuation.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_full_corpus as base

PARSER_POLICY_ID = "JANUS-LINA-PARSER-POLICY-v0.6.1"
PARSER_POLICY_VERSION = "0.6.1"

NON_LEXICAL_MARKERS = {
    "*900": {"unicode": "U+10101", "glyph": "𐄁", "name": "AEGEAN WORD SEPARATOR DOT"},
    "*901": {"unicode": "U+10100", "glyph": "𐄀", "name": "AEGEAN WORD SEPARATOR LINE"},
    "*902": {"unicode": "U+10100", "glyph": "𐄀", "name": "AEGEAN WORD SEPARATOR LINE", "note": "corpus alias"},
    "*903": {"unicode": "U+10102", "glyph": "𐄂", "name": "AEGEAN CHECK MARK"},
}
NON_LEXICAL_GLYPHS = {meta["glyph"] for meta in NON_LEXICAL_MARKERS.values()}

ROLES = (
    "ROW_INITIAL",
    "ROW_FINAL",
    "PRE_NUMERIC",
    "POST_NUMERIC",
    "DOC_INITIAL",
    "DOC_FINAL",
    "NONNUMERIC_ONLY_ROW",
    "SOLE_TOKEN_ROW",
)


def canonical_piece(token: str) -> str:
    return (token or "").strip()


def is_nonlexical_piece(token: str) -> bool:
    t = canonical_piece(token)
    return t.upper() in NON_LEXICAL_MARKERS or t in NON_LEXICAL_GLYPHS


def parser_policy_manifest() -> dict:
    return {
        "policy_id": PARSER_POLICY_ID,
        "version": PARSER_POLICY_VERSION,
        "operation": "REMOVE_AEGEAN_PUNCTUATION_BEFORE_HASHING_SCORING_NULLS_AND_ROLE_GEOMETRY",
        "excluded_ascii_markers": NON_LEXICAL_MARKERS,
        "excluded_unicode_glyphs": sorted(NON_LEXICAL_GLYPHS),
        "scope": [
            "token_identity",
            "suffix_identity",
            "numeric_adjacency_geometry",
            "candidate_universe",
            "null_universe",
            "record_role_geometry",
        ],
        "explicit_non_exclusion": {
            "*904": "Retained because the frozen corpus maps *904 to a Linear A sign, not to Aegean punctuation."
        },
    }


def scan_marker_counts(corpus: Path) -> dict:
    counts = Counter()
    docs = Counter()
    for path in sorted((corpus / "items").glob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        m = base.READING_SPEC_RE.search(text)
        if not m:
            continue
        body = base.TAG_RE.sub("", m.group(1))
        seen = set()
        for raw in body.splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            rm = base.ROW_RE.match(raw)
            if not rm:
                continue
            _row_i, _line_i, _word_i, token, _status = rm.groups()
            t = canonical_piece(token)
            key = t.upper() if t.upper() in NON_LEXICAL_MARKERS else t
            if key in NON_LEXICAL_MARKERS or t in NON_LEXICAL_GLYPHS:
                if t in NON_LEXICAL_GLYPHS:
                    matches = [k for k, meta in NON_LEXICAL_MARKERS.items() if meta["glyph"] == t]
                    key = matches[0] if matches else t
                counts[key] += 1
                seen.add(key)
        for key in seen:
            docs[key] += 1
    return {
        "occurrences_by_marker": dict(sorted(counts.items())),
        "documents_by_marker": dict(sorted(docs.items())),
        "total_filtered_occurrences": sum(counts.values()),
    }


def corrected_parse_inscription(path: Path):
    """Drop punctuation before the v0.1 token/numeric representation is constructed."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = base.READING_SPEC_RE.search(text)
    if not m:
        return None
    body = base.TAG_RE.sub("", m.group(1))
    by_word = defaultdict(list)
    for raw in body.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        rm = base.ROW_RE.match(raw)
        if not rm:
            continue
        _row_i, _line_i, word_i, token, status = rm.groups()
        by_word[int(word_i)].append((token.strip(), status.lower()))

    words = []
    reveal = {}
    for word_i in sorted(by_word):
        kept = [(token, status) for token, status in by_word[word_i] if not is_nonlexical_piece(token)]
        if not kept:
            continue
        pieces = [token for token, _status in kept]
        statuses = [status for _token, status in kept]
        numeric_parts = [base.parse_numeric_piece(x) for x in pieces]
        if numeric_parts and all(v is not None for v in numeric_parts):
            value = sum(float(v) for v in numeric_parts)
            if value > 0:
                words.append({"kind": "N", "value": value, "word_index": word_i})
            continue

        raw_word = "·".join(pieces)
        raw_suffix = pieces[-1]
        word_hash = base.stable_id(raw_word, "WORD")
        suffix_hash = base.stable_id(raw_suffix, "SUFFIX")
        words.append({
            "kind": "T",
            "word": word_hash,
            "suffix": suffix_hash,
            "word_index": word_i,
            "reading_status": sorted(set(statuses)),
        })
        reveal.setdefault(word_hash, raw_word)
        reveal.setdefault(suffix_hash, raw_suffix)

    if not words:
        return None
    return {
        "doc": path.stem,
        "region": base.region_of(path.stem),
        "words": words,
        "reveal": reveal,
    }


def corrected_parse_layout(path: Path):
    """Drop punctuation before v0.6 row/document geometry and role labels are computed."""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = base.READING_SPEC_RE.search(text)
    if not m:
        return None
    body = base.TAG_RE.sub("", m.group(1))
    by_word = defaultdict(list)
    for raw in body.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        rm = base.ROW_RE.match(raw)
        if not rm:
            continue
        row_i, line_i, word_i, token, status = rm.groups()
        by_word[int(word_i)].append({
            "token": token.strip(),
            "status": status.lower(),
            "row": int(row_i),
            "line": int(line_i),
        })

    words = []
    reveal = {}
    for wi in sorted(by_word):
        kept = [entry for entry in by_word[wi] if not is_nonlexical_piece(entry["token"])]
        if not kept:
            continue
        pieces = [entry["token"] for entry in kept]
        statuses = [entry["status"] for entry in kept]
        unique_rows = sorted({entry["row"] for entry in kept})
        unique_lines = sorted({entry["line"] for entry in kept})
        row = unique_rows[0] if len(unique_rows) == 1 else None
        line = unique_lines[0] if len(unique_lines) == 1 else None
        numeric_parts = [base.parse_numeric_piece(x) for x in pieces]
        if numeric_parts and all(v is not None for v in numeric_parts):
            value = sum(float(v) for v in numeric_parts)
            if value > 0:
                words.append({
                    "kind": "N",
                    "value": value,
                    "word_index": wi,
                    "row": row,
                    "line": line,
                })
            continue

        raw_word = "·".join(pieces)
        raw_suffix = pieces[-1]
        wh = base.stable_id(raw_word, "WORD")
        sh = base.stable_id(raw_suffix, "SUFFIX")
        words.append({
            "kind": "T",
            "word": wh,
            "suffix": sh,
            "word_index": wi,
            "row": row,
            "line": line,
            "reading_status": sorted(set(statuses)),
        })
        reveal.setdefault(wh, raw_word)
        reveal.setdefault(sh, raw_suffix)

    if not words:
        return None

    row_groups = defaultdict(list)
    for i, word in enumerate(words):
        if word.get("row") is not None:
            row_groups[word["row"]].append(i)
    first_t = next((i for i, word in enumerate(words) if word["kind"] == "T"), None)
    last_t = next((i for i in range(len(words) - 1, -1, -1) if words[i]["kind"] == "T"), None)

    positions = []
    for i, word in enumerate(words):
        if word["kind"] != "T":
            continue
        role = {name: False for name in ROLES}
        role["DOC_INITIAL"] = i == first_t
        role["DOC_FINAL"] = i == last_t
        if word.get("row") is not None:
            idxs = sorted(row_groups[word["row"]], key=lambda j: words[j]["word_index"])
            if i in idxs:
                j = idxs.index(i)
                role["ROW_INITIAL"] = j == 0
                role["ROW_FINAL"] = j == len(idxs) - 1
                role["PRE_NUMERIC"] = j + 1 < len(idxs) and words[idxs[j + 1]]["kind"] == "N"
                role["POST_NUMERIC"] = j > 0 and words[idxs[j - 1]]["kind"] == "N"
                role["NONNUMERIC_ONLY_ROW"] = not any(words[k]["kind"] == "N" for k in idxs)
                role["SOLE_TOKEN_ROW"] = len(idxs) == 1
        positions.append({
            "doc": path.stem,
            "region": base.region_of(path.stem),
            "word": word["word"],
            "suffix": word["suffix"],
            "word_index": word["word_index"],
            "roles": role,
        })

    return {
        "doc": path.stem,
        "region": base.region_of(path.stem),
        "positions": positions,
        "reveal": reveal,
    }
