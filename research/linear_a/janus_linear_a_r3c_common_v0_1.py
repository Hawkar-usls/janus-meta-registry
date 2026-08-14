#!/usr/bin/env python3
"""Shared source/metric layer for JANUS Linear A R3C v0.1.

This module is intentionally semantic-light.  It parses the public lineara.xyz
JavaScript Map payload, preserves source literals, exposes frozen tokenization
profiles, and supplies deterministic descriptive statistics used by R3C
predecessor replays.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

MAP_MARKER = "new Map("
ASCII_ALPHA_RE = re.compile(r"[A-Z]")
PURE_ASCII_NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|\d+\s*/\s*\d+)$")
SUBSCRIPT_TO_ASCII = str.maketrans({
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
})

PROFILE_IDS = {
    "THESIS_LITERAL_ALPHA_v0.1",
    "PLUS_BASE_AMBIGUITY_v0.1",
    "EXCLUDE_PLUS_AMBIGUITY_v0.1",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_lineara_map(path: str | Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    p = Path(path)
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    marker_at = text.find(MAP_MARKER)
    if marker_at < 0:
        raise ValueError("LINEARA_MAP_MARKER_NOT_FOUND")
    payload_start = marker_at + len(MAP_MARKER)
    payload_end = text.rfind(");")
    if payload_end < payload_start:
        raise ValueError("LINEARA_MAP_TERMINATOR_NOT_FOUND")
    payload = text[payload_start:payload_end].strip()
    entries = json.loads(payload)
    if not isinstance(entries, list):
        raise ValueError("LINEARA_MAP_PAYLOAD_NOT_LIST")
    out: dict[str, dict[str, Any]] = {}
    duplicate_ids: list[str] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError(f"LINEARA_INVALID_MAP_ENTRY:{i}")
        doc_id, doc = entry
        if not isinstance(doc_id, str) or not isinstance(doc, dict):
            raise ValueError(f"LINEARA_INVALID_MAP_ENTRY_TYPES:{i}")
        if doc_id in out:
            duplicate_ids.append(doc_id)
        out[doc_id] = doc
    if duplicate_ids:
        raise ValueError("LINEARA_DUPLICATE_DOCUMENT_IDS:" + ",".join(sorted(set(duplicate_ids))))
    meta = {
        "path": str(p),
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
        "document_count": len(out),
    }
    return out, meta


def normalize_alias(s: str) -> str:
    return unicodedata.normalize("NFC", s).translate(SUBSCRIPT_TO_ASCII)


def _is_unicode_numeric_or_punct_only(s: str) -> bool:
    seen = False
    for ch in s:
        if ch.isspace():
            continue
        cat = unicodedata.category(ch)
        if cat.startswith(("N", "P", "S")):
            seen = True
            continue
        try:
            unicodedata.numeric(ch)
            seen = True
            continue
        except (TypeError, ValueError):
            return False
    return seen


def retain_word_literal(item: Any) -> bool:
    if not isinstance(item, str):
        return False
    s = unicodedata.normalize("NFC", item).strip()
    if not s or s in {"None", "NONE", "null", "NULL", "\n"}:
        return False
    if PURE_ASCII_NUMERIC_RE.fullmatch(s):
        return False
    if _is_unicode_numeric_or_punct_only(s):
        return False
    return bool(ASCII_ALPHA_RE.search(s) or re.search(r"\*\d", s))


def word_items(doc: dict[str, Any], profile_id: str) -> list[str]:
    if profile_id not in PROFILE_IDS:
        raise ValueError(f"UNKNOWN_PROFILE:{profile_id}")
    values = doc.get("transliteratedWords", [])
    if not isinstance(values, list):
        return []
    retained: list[str] = []
    for item in values:
        if not retain_word_literal(item):
            continue
        s = unicodedata.normalize("NFC", item).strip()
        if profile_id == "EXCLUDE_PLUS_AMBIGUITY_v0.1" and "+" in s:
            continue
        retained.append(s)
    return retained


def split_word_signs(word: str, profile_id: str) -> list[str]:
    if profile_id not in PROFILE_IDS:
        raise ValueError(f"UNKNOWN_PROFILE:{profile_id}")
    parts = [part for part in word.split("-") if part]
    if profile_id == "PLUS_BASE_AMBIGUITY_v0.1":
        parts = [part.split("+", 1)[0] if "+" in part else part for part in parts]
    return parts


def document_signs(doc: dict[str, Any], profile_id: str) -> list[str]:
    signs: list[str] = []
    for word in word_items(doc, profile_id):
        signs.extend(split_word_signs(word, profile_id))
    return signs


def document_words_and_lengths(doc: dict[str, Any], profile_id: str) -> tuple[list[str], list[int]]:
    words = word_items(doc, profile_id)
    lengths = [len(split_word_signs(w, profile_id)) for w in words]
    return words, lengths


def shannon_entropy_bits(counter: Counter[str]) -> float | None:
    n = sum(counter.values())
    if n <= 0:
        return None
    return -sum((count / n) * math.log2(count / n) for count in counter.values() if count)


def js_divergence_bits(a: Counter[str], b: Counter[str]) -> float | None:
    na = sum(a.values())
    nb = sum(b.values())
    if na <= 0 or nb <= 0:
        return None
    keys = set(a) | set(b)
    pa = {k: a.get(k, 0) / na for k in keys}
    pb = {k: b.get(k, 0) / nb for k in keys}
    m = {k: (pa[k] + pb[k]) / 2 for k in keys}

    def kl(p: dict[str, float], q: dict[str, float]) -> float:
        return sum(v * math.log2(v / q[k]) for k, v in p.items() if v > 0 and q[k] > 0)

    return 0.5 * kl(pa, m) + 0.5 * kl(pb, m)


def sample_mean(xs: list[float | int]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def sample_variance(xs: list[float | int]) -> float | None:
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)


def cohens_d_abs(a: list[float | int], b: list[float | int]) -> float | None:
    if len(a) < 2 or len(b) < 2:
        return None
    va = sample_variance(a)
    vb = sample_variance(b)
    assert va is not None and vb is not None
    denom_df = len(a) + len(b) - 2
    if denom_df <= 0:
        return None
    pooled = math.sqrt(((len(a) - 1) * va + (len(b) - 1) * vb) / denom_df)
    if pooled == 0:
        return 0.0 if sample_mean(a) == sample_mean(b) else None
    return abs((sample_mean(a) - sample_mean(b)) / pooled)  # type: ignore[operator]


def support_class(doc: dict[str, Any]) -> str | None:
    support = str(doc.get("support", "")).strip().lower()
    if support == "tablet":
        return "ADMINISTRATIVE_TABLET"
    if "stone" in support or "vessel" in support:
        return "CEREMONIAL_STONE_OR_VESSEL"
    return None


def aggregate_signs_for_ids(
    docs: dict[str, dict[str, Any]], ids: Iterable[str], profile_id: str
) -> Counter[str]:
    c: Counter[str] = Counter()
    for doc_id in ids:
        c.update(document_signs(docs[doc_id], profile_id))
    return c


def corpus_metrics(docs: dict[str, dict[str, Any]], profile_id: str) -> dict[str, Any]:
    sign_counts: Counter[str] = Counter()
    word_counts: Counter[str] = Counter()
    word_lengths: list[int] = []
    positive_docs = 0
    excluded_plus_words = 0
    support_inventory: Counter[str] = Counter()
    site_inventory: Counter[str] = Counter()
    scribe_inventory: Counter[str] = Counter()

    for doc in docs.values():
        support_inventory[str(doc.get("support", ""))] += 1
        site_inventory[str(doc.get("site", ""))] += 1
        if str(doc.get("scribe", "")).strip():
            scribe_inventory[str(doc.get("scribe", "")).strip()] += 1
        raw_values = doc.get("transliteratedWords", [])
        if isinstance(raw_values, list) and profile_id == "EXCLUDE_PLUS_AMBIGUITY_v0.1":
            excluded_plus_words += sum(
                1 for x in raw_values if isinstance(x, str) and retain_word_literal(x) and "+" in x
            )
        words, lengths = document_words_and_lengths(doc, profile_id)
        if words:
            positive_docs += 1
        word_counts.update(words)
        word_lengths.extend(lengths)
        for word in words:
            sign_counts.update(split_word_signs(word, profile_id))

    hapax = sum(1 for count in word_counts.values() if count == 1)
    return {
        "profile_id": profile_id,
        "document_count": len(docs),
        "documents_with_retained_content": positive_docs,
        "documents_without_retained_content": len(docs) - positive_docs,
        "word_tokens": sum(word_counts.values()),
        "word_types": len(word_counts),
        "sign_tokens": sum(sign_counts.values()),
        "sign_types": len(sign_counts),
        "entropy_bits": shannon_entropy_bits(sign_counts),
        "hapax_word_types": hapax,
        "hapax_rate": hapax / len(word_counts) if word_counts else None,
        "mean_word_length_signs": sample_mean(word_lengths),
        "excluded_plus_words": excluded_plus_words,
        "top_20_signs": sign_counts.most_common(20),
        "top_20_words": word_counts.most_common(20),
        "support_inventory": support_inventory.most_common(),
        "site_inventory": site_inventory.most_common(),
        "documents_with_scribe_metadata": sum(scribe_inventory.values()),
    }


def register_metrics(
    docs: dict[str, dict[str, Any]], profile_id: str, *, permutations: int, seed: int
) -> dict[str, Any]:
    admin_ids = [doc_id for doc_id, doc in docs.items() if support_class(doc) == "ADMINISTRATIVE_TABLET" and document_signs(doc, profile_id)]
    ceremonial_ids = [doc_id for doc_id, doc in docs.items() if support_class(doc) == "CEREMONIAL_STONE_OR_VESSEL" and document_signs(doc, profile_id)]
    admin = aggregate_signs_for_ids(docs, admin_ids, profile_id)
    ceremonial = aggregate_signs_for_ids(docs, ceremonial_ids, profile_id)
    observed = js_divergence_bits(admin, ceremonial)

    eligible = admin_ids + ceremonial_ids
    n_admin = len(admin_ids)
    rng = random.Random(seed)
    null: list[float] = []
    if observed is not None and len(eligible) >= 2 and 0 < n_admin < len(eligible):
        for _ in range(permutations):
            perm = list(eligible)
            rng.shuffle(perm)
            pa_ids = perm[:n_admin]
            pc_ids = perm[n_admin:]
            value = js_divergence_bits(
                aggregate_signs_for_ids(docs, pa_ids, profile_id),
                aggregate_signs_for_ids(docs, pc_ids, profile_id),
            )
            if value is not None:
                null.append(value)

    exceed = sum(1 for x in null if observed is not None and x >= observed)
    sorted_null = sorted(null)

    def quantile_nearest(q: float) -> float | None:
        if not sorted_null:
            return None
        i = min(len(sorted_null) - 1, max(0, round(q * (len(sorted_null) - 1))))
        return sorted_null[i]

    return {
        "profile_id": profile_id,
        "administrative_documents": len(admin_ids),
        "administrative_sign_tokens": sum(admin.values()),
        "ceremonial_documents": len(ceremonial_ids),
        "ceremonial_sign_tokens": sum(ceremonial.values()),
        "jsd_bits": observed,
        "permutations_requested": permutations,
        "permutations_evaluable": len(null),
        "seed": seed,
        "exceedances_ge_observed": exceed,
        "p_raw": exceed / len(null) if null else None,
        "p_plus1": (exceed + 1) / (len(null) + 1) if null else None,
        "null_mean": sample_mean(null),
        "null_95_percentile_nearest": quantile_nearest(0.95),
        "administrative_ids": admin_ids,
        "ceremonial_ids": ceremonial_ids,
    }


def site_effect_metrics(docs: dict[str, dict[str, Any]], profile_id: str) -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = {}
    for site in ("Khania", "Phaistos"):
        ids: list[str] = []
        lengths: list[int] = []
        for doc_id, doc in docs.items():
            if str(doc.get("site", "")) != site or support_class(doc) != "ADMINISTRATIVE_TABLET":
                continue
            words, wlengths = document_words_and_lengths(doc, profile_id)
            if words:
                ids.append(doc_id)
                lengths.extend(wlengths)
        groups[site] = {
            "documents": len(ids),
            "word_tokens": len(lengths),
            "mean_word_length": sample_mean(lengths),
            "document_ids": ids,
            "lengths": lengths,
        }
    d = cohens_d_abs(groups["Khania"]["lengths"], groups["Phaistos"]["lengths"])
    for g in groups.values():
        g.pop("lengths", None)
    return {"profile_id": profile_id, "groups": groups, "cohens_d_abs": d}


def scribe_qualifying_metrics(docs: dict[str, dict[str, Any]], profile_id: str, threshold: int = 20) -> dict[str, Any]:
    signs_by_scribe: Counter[str] = Counter()
    docs_by_scribe: Counter[str] = Counter()
    for doc in docs.values():
        scribe = str(doc.get("scribe", "")).strip()
        if not scribe:
            continue
        signs = document_signs(doc, profile_id)
        if signs:
            signs_by_scribe[scribe] += len(signs)
            docs_by_scribe[scribe] += 1
    qualifying = sorted(s for s, n in signs_by_scribe.items() if n >= threshold)
    return {
        "profile_id": profile_id,
        "threshold_sign_tokens": threshold,
        "qualifying_scribe_count": len(qualifying),
        "qualifying_scribes": [
            {"scribe": s, "sign_tokens": signs_by_scribe[s], "documents": docs_by_scribe[s]}
            for s in qualifying
        ],
        "distinctive_bigram_replay_status": "METHOD_UNDERDETERMINED_NOT_COMPUTED_IN_v0.1",
    }


def ngram_formula_ranking(docs: dict[str, dict[str, Any]], profile_id: str, top_k: int = 50) -> dict[str, Any]:
    tablet_sets: dict[tuple[str, ...], set[str]] = {}
    site_sets: dict[tuple[str, ...], set[str]] = {}
    occurrences: Counter[tuple[str, ...]] = Counter()
    for doc_id, doc in docs.items():
        signs = document_signs(doc, profile_id)
        if not signs:
            continue
        site = str(doc.get("site", ""))
        for n in (1, 2, 3, 4):
            for i in range(0, len(signs) - n + 1):
                ng = tuple(signs[i:i+n])
                occurrences[ng] += 1
                tablet_sets.setdefault(ng, set()).add(doc_id)
                site_sets.setdefault(ng, set()).add(site)
    rows = []
    for ng, occ in occurrences.items():
        n = len(ng)
        tablet_count = len(tablet_sets[ng])
        site_count = len(site_sets[ng])
        score = tablet_count * site_count * n
        rows.append({
            "ngram": list(ng),
            "n": n,
            "occurrences": occ,
            "tablet_count": tablet_count,
            "site_count": site_count,
            "score": score,
        })
    rows.sort(key=lambda r: (-r["score"], -r["tablet_count"], -r["site_count"], -r["n"], r["ngram"]))
    return {
        "profile_id": profile_id,
        "scored_ngram_count": len(rows),
        "top_k": top_k,
        "top": rows[:top_k],
        "ground_truth_evaluation": "METHOD_UNDERDETERMINED_EXACT_NINE_ITEM_LIST_NOT_IN_MANIFEST",
    }
