#!/usr/bin/env python3
"""JANUS Linear A R7-0 cross-fitted exact formula-slot completion.

Candidate formula frames are selected on training documents only. Lexical source words
remain opaque hashes throughout selection and held-out scoring. Human-readable source
labels are attached only after candidate p-values, BH q-values, and admission decisions
have been computed.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_r5_word_level_role_learning_v0_1 as r5

FROZEN_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"


def eligible_positions(docs):
    """Yield internal all-certain lexical target slots with all-certain immediate neighbors."""
    for d in docs:
        seq = d["sequence"]
        for i in range(1, len(seq) - 1):
            left, target, right = seq[i - 1], seq[i], seq[i + 1]
            if target.get("kind") != "W" or not target.get("certain"):
                continue
            if not left.get("certain") or not right.get("certain"):
                continue
            yield d, left["context"], target["word"], right["context"]


def select_train_candidates(train_docs, spec):
    cfg = spec["train_candidate_gate"]
    frame_targets = defaultdict(Counter)
    frame_docs = defaultdict(set)
    target_freq = Counter()
    total_targets = 0
    for d, left, target, right in eligible_positions(train_docs):
        frame = (left, right)
        frame_targets[frame][target] += 1
        frame_docs[frame].add(d["doc"])
        target_freq[target] += 1
        total_targets += 1

    selected = []
    for frame in sorted(frame_targets):
        counts = frame_targets[frame]
        n = sum(counts.values())
        if n < cfg["minimum_frame_occurrences"]:
            continue
        if len(frame_docs[frame]) < cfg["minimum_frame_documents"]:
            continue
        ranked = counts.most_common()
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            continue
        target, k = ranked[0]
        rate = k / n
        if k < cfg["minimum_dominant_target_occurrences"]:
            continue
        if rate < cfg["minimum_dominant_target_rate"]:
            continue
        p0 = target_freq[target] / total_targets if total_targets else 0.0
        selected.append({
            "left": frame[0],
            "right": frame[1],
            "target": target,
            "train_frame_occurrences": n,
            "train_frame_documents": len(frame_docs[frame]),
            "train_dominant_target_occurrences": k,
            "train_dominant_target_rate": rate,
            "train_target_unigram_probability": p0,
        })
    return selected, total_targets


def score_candidate_on_test(test_docs, cand):
    n = 0
    k = 0
    docs = set()
    hit_docs = set()
    regions = set()
    alternatives = Counter()
    for d, left, target, right in eligible_positions(test_docs):
        if left != cand["left"] or right != cand["right"]:
            continue
        n += 1
        docs.add(d["doc"])
        regions.add(r5.base.region_of(d["doc"]))
        alternatives[target] += 1
        if target == cand["target"]:
            k += 1
            hit_docs.add(d["doc"])
    return {
        "heldout_occurrences": n,
        "heldout_hits": k,
        "heldout_documents": sorted(docs),
        "heldout_hit_documents": sorted(hit_docs),
        "heldout_regions": sorted(regions),
        "heldout_alternatives": dict(alternatives),
    }


def poisson_binomial_upper_tail(probabilities, observed):
    """Exact P(X >= observed) for independent Bernoulli trials with unequal p."""
    n = len(probabilities)
    if observed <= 0:
        return 1.0
    if observed > n:
        return 0.0
    dp = [0.0] * (n + 1)
    dp[0] = 1.0
    used = 0
    for p in probabilities:
        p = min(1.0, max(0.0, float(p)))
        used += 1
        for j in range(used, 0, -1):
            dp[j] = dp[j] * (1.0 - p) + dp[j - 1] * p
        dp[0] *= (1.0 - p)
    return min(1.0, max(0.0, sum(dp[observed:])))


def bh_qvalues(rows):
    """Benjamini-Hochberg adjusted q-values in-place by row index."""
    m = len(rows)
    if not m:
        return []
    order = sorted(range(m), key=lambda i: (rows[i]["p_value"], i))
    q = [1.0] * m
    running = 1.0
    for rev_rank in range(m - 1, -1, -1):
        idx = order[rev_rank]
        rank = rev_rank + 1
        raw = rows[idx]["p_value"] * m / rank
        running = min(running, raw)
        q[idx] = min(1.0, running)
    return q


def reveal_context(token, reveal):
    if token.startswith("N:"):
        return token
    return reveal.get(token, token)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--parent-canonical", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = json.load(open(args.spec, encoding="utf-8"))
    parent = json.load(open(args.parent_canonical, encoding="utf-8"))
    assert spec["source"]["frozen_commit"] == FROZEN_COMMIT
    assert spec["parent_canonical_target"] == "v2.24"
    assert parent["version"] == "v2.24" and parent["status"] == "CURRENT_CANONICAL_RESEARCH_STATE"
    assert spec["cross_fitting"]["candidate_selection_uses_train_only"] is True
    assert spec["train_candidate_gate"]["manual_candidate_addition_forbidden"] is True
    assert spec["train_candidate_gate"]["manual_candidate_removal_forbidden"] is True
    assert spec["certainty"]["none_reinterpreted_as_certain"] is False
    assert spec["certainty"]["doubtful_reinterpreted_as_certain"] is False

    docs, reveal, failures = r5.load_corpus(Path(args.corpus))
    by_fold = {fold: [d for d in docs if d["fold"] == fold] for fold in range(5)}

    history = defaultdict(lambda: {
        "selected_folds": [],
        "train_rows": [],
        "test_rows": [],
        "null_probabilities": [],
    })
    per_fold = []

    for fold in range(5):
        train = [d for d in docs if d["fold"] != fold]
        test = by_fold[fold]
        selected, train_eligible_targets = select_train_candidates(train, spec)
        heldout_frame_occurrences = 0
        for cand in selected:
            key = (cand["left"], cand["target"], cand["right"])
            scored = score_candidate_on_test(test, cand)
            heldout_frame_occurrences += scored["heldout_occurrences"]
            h = history[key]
            h["selected_folds"].append(fold)
            h["train_rows"].append({"fold": fold, **cand})
            h["test_rows"].append({"fold": fold, **scored})
            h["null_probabilities"].extend(
                [cand["train_target_unigram_probability"]] * scored["heldout_occurrences"]
            )
        per_fold.append({
            "fold": fold,
            "train_documents": len(train),
            "heldout_documents": len(test),
            "train_eligible_targets": train_eligible_targets,
            "train_selected_formula_candidates": len(selected),
            "heldout_occurrences_of_selected_frames": heldout_frame_occurrences,
        })

    cfg = spec["heldout_candidate_gate"]
    family = []
    for (left, target, right), h in sorted(history.items()):
        selected_folds = sorted(h["selected_folds"])
        if len(selected_folds) < cfg["minimum_selected_folds"]:
            continue  # train-only eligibility filter
        n = sum(x["heldout_occurrences"] for x in h["test_rows"])
        k = sum(x["heldout_hits"] for x in h["test_rows"])
        docs_all = sorted({d for x in h["test_rows"] for d in x["heldout_documents"]})
        hit_docs = sorted({d for x in h["test_rows"] for d in x["heldout_hit_documents"]})
        regions = sorted({r for x in h["test_rows"] for r in x["heldout_regions"]})
        alternatives = Counter()
        for x in h["test_rows"]:
            alternatives.update(x["heldout_alternatives"])
        probs = h["null_probabilities"]
        p = poisson_binomial_upper_tail(probs, k) if n else 1.0
        family.append({
            "left_token": left,
            "target_token": target,
            "right_token": right,
            "selected_folds": selected_folds,
            "selected_fold_count": len(selected_folds),
            "train_rows": h["train_rows"],
            "heldout_occurrences": n,
            "heldout_hits": k,
            "heldout_precision": (k / n) if n else None,
            "heldout_document_ids": docs_all,
            "heldout_hit_document_ids": hit_docs,
            "heldout_document_count": len(docs_all),
            "heldout_region_set": regions,
            "heldout_alternative_counts_opaque": dict(alternatives),
            "p_value": p,
        })

    qvals = bh_qvalues(family)
    admitted = []
    for row, q in zip(family, qvals):
        row["BH_q"] = q
        precision = row["heldout_precision"] if row["heldout_precision"] is not None else 0.0
        passes = bool(
            row["heldout_occurrences"] >= cfg["minimum_heldout_occurrences"]
            and row["heldout_document_count"] >= cfg["minimum_heldout_documents"]
            and precision >= cfg["minimum_heldout_precision"]
            and q <= cfg["FDR_q_max"]
        )
        row["FORMULA_SLOT_CANDIDATE_ADMITTED"] = passes
        if passes:
            admitted.append(row)

    # Human-readable source labels are attached strictly after all scoring/admission.
    def revealed_row(row):
        out = dict(row)
        out["source_left_after_scoring"] = reveal_context(row["left_token"], reveal)
        out["source_target_after_scoring"] = reveal.get(row["target_token"], row["target_token"])
        out["source_right_after_scoring"] = reveal_context(row["right_token"], reveal)
        out["heldout_alternative_counts_after_scoring"] = {
            reveal.get(tok, tok): n for tok, n in row["heldout_alternative_counts_opaque"].items()
        }
        return out

    family_revealed = [revealed_row(x) for x in family]
    admitted_revealed = [x for x in family_revealed if x["FORMULA_SLOT_CANDIDATE_ADMITTED"]]
    family_revealed.sort(key=lambda x: (not x["FORMULA_SLOT_CANDIDATE_ADMITTED"], x["BH_q"], -(x["heldout_precision"] or 0.0), -x["heldout_occurrences"]))
    admitted_revealed.sort(key=lambda x: (x["BH_q"], -(x["heldout_precision"] or 0.0), -x["heldout_occurrences"]))

    status = (
        "CROSS_FITTED_CONCRETE_FORMULA_SLOT_CANDIDATES_ADMITTED"
        if admitted_revealed else
        "CROSS_FITTED_CONCRETE_FORMULA_SLOT_CANDIDATES_NOT_ESTABLISHED"
    )
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R7-0-CROSS-FITTED-FORMULA-SLOT-COMPLETION-RESULT-2026-08-15-v0.1",
        "version": "v0.1",
        "node_type": "cross_fitted_concrete_formula_slot_completion_result",
        "status": status,
        "source": {
            "repository": "Hawkar-usls/lineara.xyz",
            "frozen_commit": FROZEN_COMMIT,
            "parsed_documents": len(docs),
            "parse_failures_or_empty": failures,
        },
        "method": {
            "folds": 5,
            "frame": "LEFT -> [TARGET] -> RIGHT",
            "candidate_selection": "train-only exact two-sided all-certain internal frames",
            "test": "cross-fitted exact formula completion",
            "null": cfg["null"],
            "multiple_testing": cfg["multiple_testing"],
            "FDR_q_max": cfg["FDR_q_max"],
        },
        "per_fold": per_fold,
        "cross_fitted_candidate_family_size": len(family_revealed),
        "admitted_formula_slot_candidate_count": len(admitted_revealed),
        "admitted_formula_slot_candidates": admitted_revealed,
        "candidate_family_after_scoring": family_revealed,
        "leakage_firewall": {
            "candidate_selection_used_heldout_documents": False,
            "source_labels_used_for_selection_or_scoring": False,
            "translations_used": False,
            "external_dictionaries_used": False,
            "Linear_B_supervision_used": False,
            "Notti_readings_used": False,
            "manual_candidate_addition_or_removal": False,
            "R3B_blind_eligibility_affected": False,
        },
        "epistemic_gate": {
            "concrete_formula_slot_candidates_established": bool(admitted_revealed),
            "probable_function_established": False,
            "word_meaning_established": False,
            "grammatical_label_established": False,
            "translation_established": False,
            "phonetic_value_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "R3B_external_replication_established": False,
        },
        "next_gate": (
            "Freeze admitted candidate family unchanged for R7-1 cross-region formula transfer and R7-2 adversarial destruction."
            if admitted_revealed else
            "Preserve negative result; preregister a typed/formula-family abstraction without relaxing R7-0 post hoc."
        ),
        "claim_ceiling": spec["claim_ceiling"],
    }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "candidate_family_size": len(family_revealed),
        "admitted": len(admitted_revealed),
        "decipherment_established": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
