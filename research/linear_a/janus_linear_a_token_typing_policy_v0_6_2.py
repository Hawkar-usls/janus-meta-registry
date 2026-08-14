#!/usr/bin/env python3
"""Typed-token policy for JANUS Linear A corrective replay v0.6.2.

Extends the v0.6.1 punctuation policy by preventing numeric literals from entering the
lexical/logographic candidate universe. Exact numeric literals are parsed generically;
approximate/uncertain numeric-like literals are treated as non-lexical numeric markers
for structural geometry but are not assigned false exact magnitudes.

This is a representation repair, not a decipherment step.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import janus_linear_a_full_corpus as base
import janus_linear_a_parser_policy_v0_6_1 as p61

POLICY_ID = "JANUS-LINA-TOKEN-TYPING-POLICY-v0.6.2"
POLICY_VERSION = "0.6.2"

SUPERSCRIPT_DIGITS = str.maketrans({
    "⁰":"0", "¹":"1", "²":"2", "³":"3", "⁴":"4", "⁵":"5", "⁶":"6", "⁷":"7", "⁸":"8", "⁹":"9",
})
SUBSCRIPT_DIGITS = str.maketrans({
    "₀":"0", "₁":"1", "₂":"2", "₃":"3", "₄":"4", "₅":"5", "₆":"6", "₇":"7", "₈":"8", "₉":"9",
})
VULGAR_FRACTIONS = {
    "½": 1/2, "⅓": 1/3, "⅔": 2/3, "¼": 1/4, "¾": 3/4,
    "⅕": 1/5, "⅖": 2/5, "⅗": 3/5, "⅘": 4/5,
    "⅙": 1/6, "⅚": 5/6, "⅛": 1/8, "⅜": 3/8, "⅝": 5/8, "⅞": 7/8,
}
APPROX_PREFIXES = ("≈", "~", "∼")


def _normalize_fraction_text(token: str) -> str:
    t = (token or "").strip().replace(",", "")
    t = t.translate(SUPERSCRIPT_DIGITS).translate(SUBSCRIPT_DIGITS)
    t = t.replace("⁄", "/")
    return t


def parse_exact_numeric_literal(token: str):
    """Return a float only when the token is an exact numeric literal."""
    raw = (token or "").strip()
    if not raw:
        return None
    if raw.startswith(APPROX_PREFIXES):
        return None
    if raw in VULGAR_FRACTIONS:
        return float(VULGAR_FRACTIONS[raw])
    t = _normalize_fraction_text(raw)
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", t):
        return float(t)
    m = re.fullmatch(r"([+-]?\d+)\s*/\s*(\d+)", t)
    if m:
        den = int(m.group(2))
        if den == 0:
            return None
        return float(Fraction(int(m.group(1)), den))
    # Single Unicode numeric characters that Python explicitly classifies as numeric.
    if len(raw) == 1:
        try:
            v = unicodedata.numeric(raw)
        except (TypeError, ValueError):
            v = None
        if v is not None and v >= 0:
            return float(v)
    return None


def is_numeric_like_literal(token: str) -> bool:
    """True for exact or approximate textual numeric literals that must not be lexical candidates."""
    raw = (token or "").strip()
    if not raw:
        return False
    if parse_exact_numeric_literal(raw) is not None:
        return True
    stripped = raw
    while stripped.startswith(APPROX_PREFIXES):
        stripped = stripped[1:].strip()
    if stripped != raw and parse_exact_numeric_literal(stripped) is not None:
        return True
    # Catch fraction typography even if the expression cannot safely receive an exact value.
    if "⁄" in raw or re.fullmatch(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+⁄[₀₁₂₃₄₅₆₇₈₉]+", raw):
        return True
    if any(ch in VULGAR_FRACTIONS for ch in raw) and not any(ch.isalpha() for ch in raw):
        return True
    return False


def typed_numeric_piece(token: str):
    """Compatibility numeric parser: exact literals return value; other tokens return None."""
    exact = parse_exact_numeric_literal(token)
    if exact is not None:
        return exact
    return base._JANUS_V061_ORIGINAL_PARSE_NUMERIC_PIECE(token) if hasattr(base, "_JANUS_V061_ORIGINAL_PARSE_NUMERIC_PIECE") else None


def token_type(token: str) -> str:
    if p61.is_nonlexical_piece(token):
        return "PUNCTUATION"
    if parse_exact_numeric_literal(token) is not None:
        return "NUMERIC_EXACT"
    if is_numeric_like_literal(token):
        return "NUMERIC_APPROX_OR_UNCERTAIN"
    return "SEMANTIC_CANDIDATE"


def policy_manifest() -> dict:
    return {
        "policy_id": POLICY_ID,
        "version": POLICY_VERSION,
        "inherits": p61.PARSER_POLICY_ID,
        "operation": "TYPE_PUNCTUATION_AND_NUMERIC_LITERALS_BEFORE_HASHING_SCORING_NULLS_AND_ROLE_GEOMETRY",
        "exact_numeric_support": [
            "decimal/integer ASCII literals",
            "ordinary fractions a/b",
            "superscript-numerator + fraction-slash + subscript-denominator forms such as ¹⁄₅",
            "Unicode vulgar fractions including thirds, fifths, sixths, eighths",
        ],
        "approximate_numeric_policy": "Approximate numeric-like literals are excluded from semantic candidate identity but are not assigned an exact magnitude.",
        "punctuation_policy": p61.parser_policy_manifest(),
    }


def scan_numeric_typing(corpus: Path) -> dict:
    counts = Counter()
    docs = defaultdict(set)
    legacy_missed = Counter()
    legacy_missed_docs = defaultdict(set)
    for path in sorted((corpus / "items").glob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        m = base.READING_SPEC_RE.search(text)
        if not m:
            continue
        body = base.TAG_RE.sub("", m.group(1))
        for raw in body.splitlines():
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            rm = base.ROW_RE.match(raw)
            if not rm:
                continue
            _r, _l, _w, tok, _status = rm.groups()
            tok = tok.strip()
            typ = token_type(tok)
            if typ.startswith("NUMERIC"):
                counts[tok] += 1
                docs[tok].add(path.stem)
                old = base._JANUS_V061_ORIGINAL_PARSE_NUMERIC_PIECE(tok) if hasattr(base, "_JANUS_V061_ORIGINAL_PARSE_NUMERIC_PIECE") else None
                if old is None:
                    legacy_missed[tok] += 1
                    legacy_missed_docs[tok].add(path.stem)
    return {
        "all_numeric_literal_occurrences": sum(counts.values()),
        "unique_numeric_literal_tokens": len(counts),
        "legacy_missed_occurrences": sum(legacy_missed.values()),
        "legacy_missed_unique_tokens": len(legacy_missed),
        "legacy_missed_tokens": [
            {"token": tok, "occurrences": n, "documents": len(legacy_missed_docs[tok]), "type": token_type(tok)}
            for tok, n in legacy_missed.most_common()
        ],
    }


def corrected_parse_inscription(path: Path):
    """Punctuation + numeric typing before v0.1 sequence representation."""
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

    words, reveal = [], {}
    for wi in sorted(by_word):
        kept = [(tok, st) for tok, st in by_word[wi] if not p61.is_nonlexical_piece(tok)]
        if not kept:
            continue
        pieces = [tok for tok, _ in kept]
        statuses = [st for _, st in kept]
        exact_values = [parse_exact_numeric_literal(tok) for tok in pieces]
        if exact_values and all(v is not None for v in exact_values):
            value = sum(float(v) for v in exact_values)
            if value > 0:
                words.append({"kind": "N", "value": value, "word_index": wi})
            continue
        # If the word is entirely numeric-like but not safely exact, type it as a numeric slot
        # without a magnitude. It must not enter semantic identity. Older magnitude stages ignore it.
        if pieces and all(is_numeric_like_literal(tok) for tok in pieces):
            words.append({"kind": "N_UNCERTAIN", "word_index": wi})
            continue
        # Mixed numeric-like + semantic pieces are conservatively stripped of numeric-like pieces.
        semantic = [(tok, st) for tok, st in kept if not is_numeric_like_literal(tok)]
        if not semantic:
            continue
        pieces = [tok for tok, _ in semantic]
        statuses = [st for _, st in semantic]
        raw_word = "·".join(pieces)
        raw_suffix = pieces[-1]
        wh = base.stable_id(raw_word, "WORD")
        sh = base.stable_id(raw_suffix, "SUFFIX")
        words.append({"kind": "T", "word": wh, "suffix": sh, "word_index": wi, "reading_status": sorted(set(statuses))})
        reveal.setdefault(wh, raw_word)
        reveal.setdefault(sh, raw_suffix)
    if not words:
        return None
    return {"doc": path.stem, "region": base.region_of(path.stem), "words": words, "reveal": reveal}


def corrected_parse_layout(path: Path):
    """Punctuation + numeric typing before record-role geometry."""
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
        by_word[int(word_i)].append({"token": token.strip(), "status": status.lower(), "row": int(row_i), "line": int(line_i)})

    words, reveal = [], {}
    for wi in sorted(by_word):
        kept = [e for e in by_word[wi] if not p61.is_nonlexical_piece(e["token"])]
        if not kept:
            continue
        unique_rows = sorted({e["row"] for e in kept})
        unique_lines = sorted({e["line"] for e in kept})
        row = unique_rows[0] if len(unique_rows) == 1 else None
        line = unique_lines[0] if len(unique_lines) == 1 else None
        pieces = [e["token"] for e in kept]
        exact_values = [parse_exact_numeric_literal(tok) for tok in pieces]
        if exact_values and all(v is not None for v in exact_values):
            value = sum(float(v) for v in exact_values)
            if value > 0:
                words.append({"kind": "N", "value": value, "word_index": wi, "row": row, "line": line})
            continue
        if pieces and all(is_numeric_like_literal(tok) for tok in pieces):
            words.append({"kind": "N_UNCERTAIN", "word_index": wi, "row": row, "line": line})
            continue
        semantic = [e for e in kept if not is_numeric_like_literal(e["token"])]
        if not semantic:
            continue
        pieces = [e["token"] for e in semantic]
        statuses = [e["status"] for e in semantic]
        raw_word = "·".join(pieces)
        raw_suffix = pieces[-1]
        wh = base.stable_id(raw_word, "WORD")
        sh = base.stable_id(raw_suffix, "SUFFIX")
        words.append({"kind": "T", "word": wh, "suffix": sh, "word_index": wi, "row": row, "line": line, "reading_status": sorted(set(statuses))})
        reveal.setdefault(wh, raw_word)
        reveal.setdefault(sh, raw_suffix)

    if not words:
        return None
    row_groups = defaultdict(list)
    for i, w in enumerate(words):
        if w.get("row") is not None:
            row_groups[w["row"]].append(i)
    first_t = next((i for i, w in enumerate(words) if w["kind"] == "T"), None)
    last_t = next((i for i in range(len(words)-1, -1, -1) if words[i]["kind"] == "T"), None)
    positions = []
    for i, w in enumerate(words):
        if w["kind"] != "T":
            continue
        role = {name: False for name in p61.ROLES}
        role["DOC_INITIAL"] = i == first_t
        role["DOC_FINAL"] = i == last_t
        if w.get("row") is not None:
            idxs = sorted(row_groups[w["row"]], key=lambda j: words[j]["word_index"])
            if i in idxs:
                j = idxs.index(i)
                role["ROW_INITIAL"] = j == 0
                role["ROW_FINAL"] = j == len(idxs)-1
                role["PRE_NUMERIC"] = j+1 < len(idxs) and words[idxs[j+1]]["kind"] in {"N", "N_UNCERTAIN"}
                role["POST_NUMERIC"] = j > 0 and words[idxs[j-1]]["kind"] in {"N", "N_UNCERTAIN"}
                role["NONNUMERIC_ONLY_ROW"] = not any(words[k]["kind"] in {"N", "N_UNCERTAIN"} for k in idxs)
                role["SOLE_TOKEN_ROW"] = len(idxs) == 1
        positions.append({"doc": path.stem, "region": base.region_of(path.stem), "word": w["word"], "suffix": w["suffix"], "word_index": w["word_index"], "roles": role})
    return {"doc": path.stem, "region": base.region_of(path.stem), "positions": positions, "reveal": reveal}
