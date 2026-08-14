#!/usr/bin/env python3
"""Typed numeric parser policy for JANUS Linear A corrective replay v0.6.2.

This policy composes the punctuation correction from v0.6.1 with a generic numeric typing
layer derived from the frozen corpus' items_analysis/numbers.txt inventory.

Before any hashing, candidate construction, null generation, or record-role scoring, each
surviving token piece is classified as:

  T  lexical/sign candidate
  N  exact numeric literal with a numeric value
  Q  numeric/measure marker whose exact value is uncertain or intentionally not asserted
  M  mixed lexical+numeric composite, excluded from lexical candidate space

Only T tokens are eligible lexical candidates. Q and M are retained in structural geometry
but never receive an invented exact numeric value.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import janus_linear_a_full_corpus as base
import janus_linear_a_parser_policy_v0_6_1 as punct

PARSER_POLICY_ID = "JANUS-LINA-TYPED-PARSER-POLICY-v0.6.2"
PARSER_POLICY_VERSION = "0.6.2"
NUMBERS_INVENTORY_RELATIVE_PATH = "items_analysis/numbers.txt"
NUMBERS_INVENTORY_GIT_BLOB_SHA = "a17b8922297795a90ea6761f32f6ea020b733a6d"

SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
SUBSCRIPT_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
VULGAR_FRACTIONS = {
    "½": 1 / 2,
    "⅓": 1 / 3,
    "⅔": 2 / 3,
    "¼": 1 / 4,
    "¾": 3 / 4,
    "⅕": 1 / 5,
    "⅖": 2 / 5,
    "⅗": 3 / 5,
    "⅘": 4 / 5,
    "⅙": 1 / 6,
    "⅚": 5 / 6,
    "⅛": 1 / 8,
    "⅜": 3 / 8,
    "⅝": 5 / 8,
    "⅞": 7 / 8,
}
APPROX_PREFIX_RE = re.compile(r"^[≈~≃≅]")
PLAIN_NUMBER_RE = re.compile(r"^(?:\d+(?:\.\d+)?|\.\d+)$")
FRACTION_RE = re.compile(r"^(\d+)\/(\d+)$")

NUMERIC_LIKE_KINDS = {"N", "Q"}
CANDIDATE_KIND = "T"


def canonical_piece(token: str) -> str:
    return (token or "").strip()


def normalize_numeric_text(token: str) -> str:
    t = canonical_piece(token)
    t = t.translate(SUPERSCRIPT_DIGITS).translate(SUBSCRIPT_DIGITS)
    t = t.replace("⁄", "/").replace("／", "/")
    t = t.replace(" ", "")
    return t


def parse_exact_numeric_text(token: str):
    """Return float for exact textual numeric literals; return None otherwise.

    Approximate forms are intentionally NOT coerced to exact values.
    """
    raw = canonical_piece(token)
    if not raw or APPROX_PREFIX_RE.match(raw):
        return None
    if raw in VULGAR_FRACTIONS:
        return float(VULGAR_FRACTIONS[raw])
    t = normalize_numeric_text(raw)
    if APPROX_PREFIX_RE.match(t):
        return None
    m = FRACTION_RE.fullmatch(t)
    if m:
        num, den = int(m.group(1)), int(m.group(2))
        if den == 0:
            return None
        return num / den
    if PLAIN_NUMBER_RE.fullmatch(t):
        try:
            return float(t)
        except ValueError:
            return None
    return None


def corpus_root_for(path: Path) -> Path:
    # Expected frozen layout: <root>/items/<inscription>.html
    return path.parent.parent


@lru_cache(maxsize=8)
def load_numeric_inventory(corpus_root_str: str) -> dict:
    root = Path(corpus_root_str)
    path = root / NUMBERS_INVENTORY_RELATIVE_PATH
    if not path.exists():
        raise RuntimeError(f"NUMBERS_INVENTORY_MISSING:{path}")
    raw = path.read_bytes()
    glyph_to_label = {}
    specific_labels = set()
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line.strip() or "\t" not in line:
            continue
        glyph, label = line.split("\t", 1)
        glyph, label = glyph.strip(), label.strip()
        if glyph:
            glyph_to_label[glyph] = label
        # Do not globally classify a bare '?' label; only its inventory glyph is numeric-like.
        if label and label != "?":
            specific_labels.add(label)
    return {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "glyph_to_label": glyph_to_label,
        "specific_labels": specific_labels,
        "entries": len(glyph_to_label),
    }


def classify_numeric_piece(token: str, corpus_root: Path) -> dict:
    """Classify one non-punctuation piece without inventing semantics."""
    t = canonical_piece(token)
    exact = parse_exact_numeric_text(t)
    if exact is not None:
        return {"class": "EXACT_NUMERIC", "kind": "N", "value": exact, "source": "GENERIC_LITERAL"}

    inv = load_numeric_inventory(str(corpus_root))
    if t in inv["glyph_to_label"]:
        label = inv["glyph_to_label"][t]
        exact_from_label = parse_exact_numeric_text(label)
        if exact_from_label is not None:
            return {
                "class": "EXACT_NUMERIC",
                "kind": "N",
                "value": exact_from_label,
                "source": "FROZEN_NUMBERS_INVENTORY_GLYPH",
                "inventory_label": label,
            }
        return {
            "class": "NUMERIC_UNCERTAIN_OR_MEASURE",
            "kind": "Q",
            "value": None,
            "source": "FROZEN_NUMBERS_INVENTORY_GLYPH",
            "inventory_label": label,
        }

    if t in inv["specific_labels"]:
        # If it were exactly parseable it would have returned above. The inventory therefore
        # identifies it as numeric/measure-like without licensing an exact scalar value.
        return {
            "class": "NUMERIC_UNCERTAIN_OR_MEASURE",
            "kind": "Q",
            "value": None,
            "source": "FROZEN_NUMBERS_INVENTORY_LABEL",
            "inventory_label": t,
        }

    return {"class": "LEXICAL_OR_SIGN", "kind": "T", "value": None, "source": "DEFAULT"}


def parser_policy_manifest(corpus_root: Path | None = None) -> dict:
    manifest = {
        "policy_id": PARSER_POLICY_ID,
        "version": PARSER_POLICY_VERSION,
        "operation": "TYPE_PUNCTUATION_NUMERIC_UNCERTAIN_AND_MIXED_BEFORE_HASHING_SCORING_NULLS_AND_ROLE_GEOMETRY",
        "inherits": punct.parser_policy_manifest(),
        "candidate_eligibility": {"T": True, "N": False, "Q": False, "M": False},
        "type_semantics": {
            "T": "lexical/sign candidate; may be hashed and scored",
            "N": "exact numeric literal; numeric value is available",
            "Q": "numeric/measure marker; exact value intentionally unset",
            "M": "mixed lexical+numeric composite; retained structurally but excluded as lexical candidate",
        },
        "exact_numeric_recognition": [
            "integers",
            "decimals including leading-dot decimals",
            "ASCII fractions such as 13/20",
            "Unicode fraction slash forms such as ¹⁄₅ and ¹⁄₁₆",
            "Unicode vulgar fractions such as ⅓ and ⅝",
            "numeric glyphs whose frozen numbers.txt label is exactly parseable",
        ],
        "uncertain_numeric_rule": "Inventory-backed or approximate numeric/measure markers are Q and never assigned an invented exact scalar.",
        "mixed_rule": "Any word containing both lexical/sign and numeric-like pieces is M and is excluded from lexical candidate space.",
        "numbers_inventory": {
            "relative_path": NUMBERS_INVENTORY_RELATIVE_PATH,
            "git_blob_sha": NUMBERS_INVENTORY_GIT_BLOB_SHA,
        },
    }
    if corpus_root is not None:
        inv = load_numeric_inventory(str(corpus_root))
        manifest["numbers_inventory"].update({
            "runtime_sha256": inv["sha256"],
            "entries": inv["entries"],
        })
    return manifest


def classify_word_entries(entries: list[dict], corpus_root: Path) -> dict | None:
    """Classify a word after punctuation removal."""
    kept = [entry for entry in entries if not punct.is_nonlexical_piece(entry["token"])]
    if not kept:
        return None
    pieces = [entry["token"] for entry in kept]
    classes = [classify_numeric_piece(piece, corpus_root) for piece in pieces]
    kinds = {c["kind"] for c in classes}

    if kinds == {"N"}:
        return {
            "kind": "N",
            "value": sum(float(c["value"]) for c in classes),
            "pieces": pieces,
            "classes": classes,
            "kept": kept,
        }
    if kinds.issubset(NUMERIC_LIKE_KINDS):
        return {"kind": "Q", "value": None, "pieces": pieces, "classes": classes, "kept": kept}
    if "N" in kinds or "Q" in kinds:
        return {"kind": "M", "value": None, "pieces": pieces, "classes": classes, "kept": kept}
    return {"kind": "T", "value": None, "pieces": pieces, "classes": classes, "kept": kept}


def scan_numeric_typing(corpus: Path) -> dict:
    counts = Counter()
    token_counts = Counter()
    examples = defaultdict(list)
    inventory = load_numeric_inventory(str(corpus))
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
            _row_i, _line_i, _word_i, token, _status = rm.groups()
            t = canonical_piece(token)
            if punct.is_nonlexical_piece(t):
                counts["PUNCTUATION"] += 1
                continue
            c = classify_numeric_piece(t, corpus)
            counts[c["class"]] += 1
            if c["kind"] in {"N", "Q"}:
                token_counts[t] += 1
                if len(examples[c["class"]]) < 20:
                    examples[c["class"]].append({"token": t, "classification": c})
    return {
        "piece_class_counts": dict(sorted(counts.items())),
        "top_numeric_like_tokens": token_counts.most_common(40),
        "examples": dict(examples),
        "numbers_inventory": {
            "entries": inventory["entries"],
            "runtime_sha256": inventory["sha256"],
            "git_blob_sha": NUMBERS_INVENTORY_GIT_BLOB_SHA,
        },
        "canary_checks": {
            "¹⁄₅": classify_numeric_piece("¹⁄₅", corpus),
            "⅝": classify_numeric_piece("⅝", corpus),
            "13/20": classify_numeric_piece("13/20", corpus),
            "≈¹⁄₆": classify_numeric_piece("≈¹⁄₆", corpus),
            "double_mina": classify_numeric_piece("double_mina", corpus),
        },
    }


def corrected_parse_inscription(path: Path):
    """Typed replacement for the historical v0.1 inscription parser."""
    root = corpus_root_for(path)
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
        by_word[int(word_i)].append({"token": token.strip(), "status": status.lower()})

    words = []
    reveal = {}
    for word_i in sorted(by_word):
        typed = classify_word_entries(by_word[word_i], root)
        if typed is None:
            continue
        kind = typed["kind"]
        if kind == "N":
            if typed["value"] is not None and typed["value"] > 0:
                words.append({"kind": "N", "value": typed["value"], "word_index": word_i})
            continue
        if kind in {"Q", "M"}:
            words.append({"kind": kind, "word_index": word_i})
            continue

        pieces = typed["pieces"]
        statuses = [entry["status"] for entry in typed["kept"]]
        raw_word = "·".join(pieces)
        raw_suffix = pieces[-1]
        wh = base.stable_id(raw_word, "WORD")
        sh = base.stable_id(raw_suffix, "SUFFIX")
        words.append({
            "kind": "T",
            "word": wh,
            "suffix": sh,
            "word_index": word_i,
            "reading_status": sorted(set(statuses)),
        })
        reveal.setdefault(wh, raw_word)
        reveal.setdefault(sh, raw_suffix)

    if not words:
        return None
    return {"doc": path.stem, "region": base.region_of(path.stem), "words": words, "reveal": reveal}


def corrected_parse_layout(path: Path):
    """Typed replacement for the v0.6 layout parser with numeric-like role geometry."""
    root = corpus_root_for(path)
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
            "token": token.strip(), "status": status.lower(),
            "row": int(row_i), "line": int(line_i),
        })

    words = []
    reveal = {}
    for wi in sorted(by_word):
        typed = classify_word_entries(by_word[wi], root)
        if typed is None:
            continue
        kept = typed["kept"]
        unique_rows = sorted({entry["row"] for entry in kept})
        unique_lines = sorted({entry["line"] for entry in kept})
        row = unique_rows[0] if len(unique_rows) == 1 else None
        line = unique_lines[0] if len(unique_lines) == 1 else None
        kind = typed["kind"]
        if kind == "N":
            if typed["value"] is not None and typed["value"] > 0:
                words.append({"kind": "N", "value": typed["value"], "word_index": wi, "row": row, "line": line})
            continue
        if kind in {"Q", "M"}:
            words.append({"kind": kind, "word_index": wi, "row": row, "line": line})
            continue

        pieces = typed["pieces"]
        statuses = [entry["status"] for entry in kept]
        raw_word = "·".join(pieces)
        raw_suffix = pieces[-1]
        wh = base.stable_id(raw_word, "WORD")
        sh = base.stable_id(raw_suffix, "SUFFIX")
        words.append({
            "kind": "T", "word": wh, "suffix": sh, "word_index": wi,
            "row": row, "line": line, "reading_status": sorted(set(statuses)),
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
        role = {name: False for name in punct.ROLES}
        role["DOC_INITIAL"] = i == first_t
        role["DOC_FINAL"] = i == last_t
        if word.get("row") is not None:
            idxs = sorted(row_groups[word["row"]], key=lambda j: words[j]["word_index"])
            if i in idxs:
                j = idxs.index(i)
                role["ROW_INITIAL"] = j == 0
                role["ROW_FINAL"] = j == len(idxs) - 1
                role["PRE_NUMERIC"] = j + 1 < len(idxs) and words[idxs[j + 1]]["kind"] in NUMERIC_LIKE_KINDS
                role["POST_NUMERIC"] = j > 0 and words[idxs[j - 1]]["kind"] in NUMERIC_LIKE_KINDS
                role["NONNUMERIC_ONLY_ROW"] = not any(words[k]["kind"] in NUMERIC_LIKE_KINDS for k in idxs)
                role["SOLE_TOKEN_ROW"] = len(idxs) == 1
        positions.append({
            "doc": path.stem,
            "region": base.region_of(path.stem),
            "word": word["word"],
            "suffix": word["suffix"],
            "word_index": word["word_index"],
            "roles": role,
        })

    return {"doc": path.stem, "region": base.region_of(path.stem), "positions": positions, "reveal": reveal}
