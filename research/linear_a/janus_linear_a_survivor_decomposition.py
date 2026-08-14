#!/usr/bin/env python3
"""
JANUS Linear A post-reveal survivor decomposition audit v0.3.

This stage does NOT discover new candidates and must not be used as a blind confirmation.
It attempts to explain or invalidate survivors from the already-completed candidate-specific
held-out run by testing known accounting-family decomposition and representation integrity.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_full_corpus as base

VERSION = "JANUS-LINA-SURVIVOR-DECOMPOSITION-v0.3"
KNOWN_RO_ACCOUNTING_WORDS = {"KURO", "POTOKURO", "KIRO"}
UNICODE_BLOCK_RE = re.compile(
    r"<transcribed-reading-unicode\\b[^>]*>.*?<reading-text>(.*?)</reading-text>.*?</transcribed-reading-unicode>",
    flags=re.IGNORECASE | re.DOTALL,
)
UNICODE_WORD_RE = re.compile(r'<word\\s+number="(\\d+)"[^>]*>(.*?)</word>', flags=re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


def normalize_label(s: str) -> str:
    return re.sub(r"[^A-Z0-9*?+]", "", (s or "").upper())


def parse_unicode_words(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    m = UNICODE_BLOCK_RE.search(text)
    if not m:
        return {}
    out = {}
    for wm in UNICODE_WORD_RE.finditer(m.group(1)):
        idx = int(wm.group(1))
        raw = TAG_RE.sub("", wm.group(2)).strip()
        if raw:
            out[idx] = raw
    return out


def detailed_pairs(docs, corpus_items: Path, reveal):
    unicode_cache = {}
    pairs = []
    for d in docs:
        seq = d["words"]
        for a, b in zip(seq, seq[1:]):
            if a["kind"] != "T" or b["kind"] != "N":
                continue
            if d["doc"] not in unicode_cache:
                unicode_cache[d["doc"]] = parse_unicode_words(corpus_items / f"{d['doc']}.html")
            word_label = reveal.get(a["word"])
            suffix_label = reveal.get(a["suffix"])
            unicode_word = unicode_cache[d["doc"]].get(a["word_index"])
            pairs.append({
                "doc": d["doc"],
                "region": d["region"],
                "word_hash": a["word"],
                "suffix_hash": a["suffix"],
                "word_label": word_label,
                "suffix_label": suffix_label,
                "word_index": a["word_index"],
                "reading_status": a.get("reading_status", []),
                "unicode_word": unicode_word,
                "value": b["value"],
                "log2_value": math.log2(b["value"]),
                "bucket": base.bucket(b["value"]),
            })
    return pairs


def region_means(rows):
    by = defaultdict(list)
    for r in rows:
        by[r["region"]].append(r["log2_value"])
    return {k: statistics.fmean(v) for k, v in by.items()}


def residual_effect(candidate_rows, all_rows, region_mean=None):
    if not candidate_rows:
        return None
    rmean = region_mean or region_means(all_rows)
    vals = [r["log2_value"] - rmean[r["region"]] for r in candidate_rows if r["region"] in rmean]
    return statistics.fmean(vals) if vals else None


def fixed_candidate_region_null(all_rows, candidate_selector, permutations, seed, direction=1):
    """Post-reveal diagnostic p-value. Candidate identity is fixed before this function is called."""
    rng = random.Random(seed)
    rmean = region_means(all_rows)
    idxs = [i for i, r in enumerate(all_rows) if candidate_selector(r)]
    if len(idxs) < 3:
        return {"status": "INSUFFICIENT_OCCURRENCES", "n": len(idxs)}
    logs = [r["log2_value"] for r in all_rows]
    by_region = defaultdict(list)
    for i, r in enumerate(all_rows):
        by_region[r["region"]].append(i)
    obs = statistics.fmean(logs[i] - rmean[all_rows[i]["region"]] for i in idxs)
    signed_obs = direction * obs
    null = []
    for _ in range(permutations):
        perm = list(logs)
        for region_idxs in by_region.values():
            vals = [perm[i] for i in region_idxs]
            rng.shuffle(vals)
            for i, v in zip(region_idxs, vals):
                perm[i] = v
        eff = statistics.fmean(perm[i] - rmean[all_rows[i]["region"]] for i in idxs)
        null.append(direction * eff)
    p = (1 + sum(x >= signed_obs for x in null)) / (1 + len(null))
    return {
        "status": "EXECUTED",
        "n": len(idxs),
        "regions": sorted({all_rows[i]["region"] for i in idxs}),
        "residual_effect": obs,
        "direction_tested": "HIGH" if direction > 0 else "LOW",
        "exploratory_one_sided_p": p,
        "permutations": permutations,
        "null_operator": "WITHIN_REGION_NUMERIC_REWIRE_FIXED_POST_REVEAL_CANDIDATE",
        "claim_ceiling": "EXPLORATORY_DIAGNOSTIC_NOT_CONFIRMATORY",
    }


def summarize_word_groups(rows, top_n=30):
    by = defaultdict(list)
    for r in rows:
        by[r["word_label"]].append(r)
    out = []
    for label, rr in by.items():
        vals = [x["value"] for x in rr]
        out.append({
            "word": label,
            "normalized_word": normalize_label(label),
            "n": len(rr),
            "documents": len({x["doc"] for x in rr}),
            "regions": sorted({x["region"] for x in rr}),
            "mean_value": statistics.fmean(vals),
            "median_value": statistics.median(vals),
            "mean_log2_value": statistics.fmean(x["log2_value"] for x in rr),
            "min_value": min(vals),
            "max_value": max(vals),
        })
    out.sort(key=lambda x: (-x["n"], x["normalized_word"]))
    return out[:top_n]


def loo_document_effects(candidate_rows, all_rows):
    rmean = region_means(all_rows)
    docs = sorted({r["doc"] for r in candidate_rows})
    out = []
    for doc in docs:
        rr = [r for r in candidate_rows if r["doc"] != doc]
        eff = residual_effect(rr, all_rows, rmean)
        out.append({"excluded_doc": doc, "remaining_n": len(rr), "residual_effect": eff})
    return out


def unicode_identity_summary(rows):
    counts = Counter(r.get("unicode_word") or "<MISSING>" for r in rows)
    forms = []
    for raw, n in counts.most_common():
        forms.append({
            "unicode_word": None if raw == "<MISSING>" else raw,
            "n": n,
            "codepoints": [] if raw == "<MISSING>" else [f"U+{ord(ch):04X}" for ch in raw],
        })
    return {
        "distinct_unicode_forms_in_adjacent_numeric_occurrences": len([k for k in counts if k != "<MISSING>"]),
        "missing_unicode_mapping_occurrences": counts.get("<MISSING>", 0),
        "forms": forms,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--permutations", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=260814225)
    args = ap.parse_args()

    corpus = Path(args.corpus)
    paths = sorted((corpus / "items").glob("*.html"))
    docs, failures = [], []
    for p in paths:
        try:
            d = base.parse_inscription(p)
            if d:
                docs.append(d)
            else:
                failures.append({"doc": p.stem, "reason": "NO_PARSEABLE_READING_SPEC"})
        except Exception as exc:
            failures.append({"doc": p.stem, "reason": f"PARSE_EXCEPTION:{type(exc).__name__}"})
    if len(docs) < 300:
        raise SystemExit("FULL_CORPUS_GATE_FAIL")

    reveal = base.collect_reveal(docs)
    rows = detailed_pairs(docs, corpus / "items", reveal)
    if len(rows) < 100:
        raise SystemExit("PAIR_GATE_FAIL")

    ro_rows = [r for r in rows if normalize_label(r.get("suffix_label")) == "RO"]
    ro_known = [r for r in ro_rows if normalize_label(r.get("word_label")) in KNOWN_RO_ACCOUNTING_WORDS]
    ro_residual = [r for r in ro_rows if normalize_label(r.get("word_label")) not in KNOWN_RO_ACCOUNTING_WORDS]
    ro_all_test = fixed_candidate_region_null(
        rows, lambda r: normalize_label(r.get("suffix_label")) == "RO", args.permutations, args.seed + 1, direction=1
    )
    ro_resid_test = fixed_candidate_region_null(
        rows,
        lambda r: normalize_label(r.get("suffix_label")) == "RO" and normalize_label(r.get("word_label")) not in KNOWN_RO_ACCOUNTING_WORDS,
        args.permutations,
        args.seed + 2,
        direction=1,
    )

    vir_rows = [r for r in rows if (r.get("word_label") or "") == "VIR+[?]"]
    vir_family = [r for r in rows if normalize_label(r.get("word_label")).startswith("VIR")]
    vir_test = fixed_candidate_region_null(
        rows, lambda r: (r.get("word_label") or "") == "VIR+[?]", args.permutations, args.seed + 3, direction=1
    )
    vir_unicode = unicode_identity_summary(vir_rows)
    vir_loo = loo_document_effects(vir_rows, rows)
    vir_status_counts = Counter(s for r in vir_rows for s in r.get("reading_status", []))
    vir_identity_unresolved = (
        "?" in "VIR+[?]" or "[" in "VIR+[?]" or
        vir_unicode["distinct_unicode_forms_in_adjacent_numeric_occurrences"] != 1 or
        vir_unicode["missing_unicode_mapping_occurrences"] > 0
    )

    known_share = (len(ro_known) / len(ro_rows)) if ro_rows else None
    ro_residual_pass = bool(
        ro_resid_test.get("status") == "EXECUTED"
        and ro_resid_test.get("residual_effect", 0) > 0
        and ro_resid_test.get("exploratory_one_sided_p", 1) <= 0.05
    )

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-SURVIVOR-DECOMPOSITION-2026-08-14-v0.3",
        "version": VERSION,
        "status": "POST_REVEAL_FALSIFICATION_RECEIPT",
        "source": {
            "repository": "mwenge/lineara.xyz",
            "frozen_commit": base.CORPUS_COMMIT,
            "LinearAInscriptions_js_blob_sha": base.CORPUS_BLOB,
        },
        "corpus_counts": {
            "parsed_inscriptions": len(docs),
            "parse_failures": len(failures),
            "token_to_number_pairs": len(rows),
        },
        "methodology": {
            "stage": "POST_REVEAL_EXPLANATION_AND_REPRESENTATION_AUDIT",
            "blind_confirmation": False,
            "new_candidate_discovery_allowed": False,
            "purpose": "Attempt to explain held-out survivors using known accounting families or representation defects.",
        },
        "RO_SUFFIX_DECOMPOSITION": {
            "survivor_origin": "candidate-specific held-out v0.2",
            "direction_from_prior_stage": "HIGH",
            "all_ro_occurrences": len(ro_rows),
            "known_accounting_words_excluded": sorted(KNOWN_RO_ACCOUNTING_WORDS),
            "known_accounting_occurrences": len(ro_known),
            "known_accounting_share": known_share,
            "residual_non_known_ro_occurrences": len(ro_residual),
            "full_word_composition": summarize_word_groups(ro_rows),
            "all_ro_diagnostic": ro_all_test,
            "after_known_accounting_exclusion": ro_resid_test,
            "interpretation": (
                "RESIDUAL_RO_EFFECT_REMAINS_EXPLORATORY_AFTER_KNOWN_ACCOUNTING_EXCLUSION"
                if ro_residual_pass else
                "RO_SIGNAL_NOT_SHOWN_TO_SURVIVE_KNOWN_ACCOUNTING_OPERATOR_DECOMPOSITION"
            ),
            "claim_ceiling": "NOT_A_NEW_LEXICAL_ANCHOR",
        },
        "VIR_UNRESOLVED_IDENTITY_AUDIT": {
            "survivor_origin": "candidate-specific held-out v0.2",
            "direction_from_prior_stage": "HIGH",
            "candidate_label_post_reveal": "VIR+[?]",
            "candidate_occurrences": len(vir_rows),
            "candidate_documents": len({r["doc"] for r in vir_rows}),
            "candidate_regions": sorted({r["region"] for r in vir_rows}),
            "reading_status_counts": dict(sorted(vir_status_counts.items())),
            "fixed_candidate_diagnostic": vir_test,
            "leave_one_document_out": vir_loo,
            "unicode_identity": vir_unicode,
            "vir_family_occurrences": len(vir_family),
            "vir_family_word_composition": summarize_word_groups(vir_family),
            "sign_identity_gate_pass": not vir_identity_unresolved,
            "interpretation": (
                "FAIL_SIGN_IDENTITY_UNRESOLVED_OR_COLLAPSED"
                if vir_identity_unresolved else
                "SIGN_IDENTITY_STABLE_BUT_SEMANTIC_NOVELTY_NOT_ESTABLISHED"
            ),
            "claim_ceiling": "CANNOT_PROMOTE_BEYOND_SIGN_IDENTITY_WHILE_LABEL_CONTAINS_UNRESOLVED_MODIFIER",
        },
        "epistemic_gate": {
            "new_anchor_established": False,
            "decipherment_established": False,
            "RO_promotable_as_new_anchor": False,
            "VIR_promotable_as_new_anchor": False,
            "promotion": "BLOCKED",
            "required_next": [
                "for RO: inspect residual RO-final full-word families and defeat KU-RO/PO-TO-KU-RO/KI-RO explanation without post-hoc promotion",
                "for VIR+[?]: resolve underlying sign identity from facsimile/Unicode before lexical or morphological interpretation",
                "independent parser/corpus implementation",
                "literature novelty audit against personnel-logogram and accounting-operator scholarship",
            ],
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "artifact": str(out),
        "rows": len(rows),
        "ro_n": len(ro_rows),
        "ro_known_share": known_share,
        "ro_residual_p": ro_resid_test.get("exploratory_one_sided_p"),
        "vir_n": len(vir_rows),
        "vir_unicode_forms": vir_unicode["distinct_unicode_forms_in_adjacent_numeric_occurrences"],
        "vir_sign_identity_gate_pass": not vir_identity_unresolved,
        "new_anchor_established": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
