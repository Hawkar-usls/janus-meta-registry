#!/usr/bin/env python3
"""JANUS Linear A R7-C0 cross-fitted positional functional-role discovery.

Human-readable Linear A word labels remain hidden through train selection, heldout
scoring, p-value calculation, BH correction, and admission. Labels are attached only
post-score for interpretation. No translation or semantic label is assigned here.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_r7_arithmetic_summary_role_v0_1 as b0
import janus_linear_a_r7_formula_slot_completion_v0_1 as stats

FROZEN_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
ROLES = (
    "DOCUMENT_HEADER",
    "DOCUMENT_CLOSER",
    "ROW_HEADER",
    "ROW_CLOSER",
    "NUMERIC_BLOCK_INTRODUCER",
    "NUMERIC_BLOCK_CLOSER",
)


def lexical_indices(seq):
    return [i for i, x in enumerate(seq) if x.get("kind") == "W"]


def consecutive_numeric_after(seq, i):
    n = 0
    j = i + 1
    while j < len(seq) and seq[j].get("kind") == "N":
        n += 1
        j += 1
    return n


def consecutive_numeric_before(seq, i):
    n = 0
    j = i - 1
    while j >= 0 and seq[j].get("kind") == "N":
        n += 1
        j -= 1
    return n


def role_occurrences(docs, role):
    """Yield every eligible lexical occurrence with a Boolean role hit."""
    if role not in ROLES:
        raise ValueError(role)
    for d in docs:
        seq = d["sequence"]
        lex = lexical_indices(seq)
        if not lex:
            continue

        if role in {"DOCUMENT_HEADER", "DOCUMENT_CLOSER", "NUMERIC_BLOCK_INTRODUCER", "NUMERIC_BLOCK_CLOSER"}:
            first = lex[0]
            last = lex[-1]
            for i in lex:
                x = seq[i]
                if role == "DOCUMENT_HEADER":
                    hit = i == first
                elif role == "DOCUMENT_CLOSER":
                    hit = i == last
                elif role == "NUMERIC_BLOCK_INTRODUCER":
                    hit = consecutive_numeric_after(seq, i) >= 2
                else:
                    hit = consecutive_numeric_before(seq, i) >= 2
                yield {
                    "role": role,
                    "doc": d["doc"],
                    "fold": d["fold"],
                    "region": d["region"],
                    "word": x["word"],
                    "statuses": x.get("statuses", []),
                    "hit": bool(hit),
                    "row": x["rows"][0] if len(x.get("rows", [])) == 1 else None,
                }
            continue

        # Row roles: only lexical words with exactly one mechanically parsed source row.
        by_row = defaultdict(list)
        for i in lex:
            x = seq[i]
            if len(x.get("rows", [])) == 1:
                by_row[x["rows"][0]].append(i)
        for row in sorted(by_row):
            idxs = by_row[row]
            if not idxs:
                continue
            first, last = idxs[0], idxs[-1]
            for i in idxs:
                x = seq[i]
                hit = i == first if role == "ROW_HEADER" else i == last
                yield {
                    "role": role,
                    "doc": d["doc"],
                    "fold": d["fold"],
                    "region": d["region"],
                    "word": x["word"],
                    "statuses": x.get("statuses", []),
                    "hit": bool(hit),
                    "row": row,
                }


def select_train(train_docs, spec):
    cfg = spec["train_candidate_gate"]
    selected = []
    backgrounds = {}
    observation_counts = {}
    for role in ROLES:
        obs = list(role_occurrences(train_docs, role))
        n_all = len(obs)
        k_all = sum(x["hit"] for x in obs)
        bg = (k_all / n_all) if n_all else 0.0
        backgrounds[role] = bg
        observation_counts[role] = n_all
        by_word = defaultdict(list)
        for x in obs:
            by_word[x["word"]].append(x)
        for word, rows in sorted(by_word.items()):
            n = len(rows)
            hits = [x for x in rows if x["hit"]]
            k = len(hits)
            hit_docs = {x["doc"] for x in hits}
            precision = (k / n) if n else 0.0
            lift = precision - bg
            if n < cfg["minimum_eligible_occurrences"]:
                continue
            if k < cfg["minimum_role_hits"]:
                continue
            if len(hit_docs) < cfg["minimum_role_hit_documents"]:
                continue
            if precision < cfg["minimum_role_precision"]:
                continue
            if lift < cfg["minimum_absolute_precision_lift_over_role_background"]:
                continue
            selected.append({
                "role": role,
                "word": word,
                "train_eligible_occurrences": n,
                "train_role_hits": k,
                "train_role_hit_documents": len(hit_docs),
                "train_role_precision": precision,
                "train_role_background_probability": bg,
                "train_absolute_precision_lift": lift,
            })
    return selected, backgrounds, observation_counts


def score_test(test_docs, candidate):
    rows = [
        x for x in role_occurrences(test_docs, candidate["role"])
        if x["word"] == candidate["word"]
    ]
    hit_rows = [x for x in rows if x["hit"]]
    statuses = Counter()
    for x in rows:
        statuses["+".join(x.get("statuses", [])) or "UNKNOWN"] += 1
    return {
        "heldout_eligible_occurrences": len(rows),
        "heldout_role_hits": len(hit_rows),
        "heldout_document_ids": sorted({x["doc"] for x in rows}),
        "heldout_role_hit_document_ids": sorted({x["doc"] for x in hit_rows}),
        "heldout_regions": sorted({x["region"] for x in rows}),
        "heldout_status_distribution": dict(statuses),
        "heldout_examples": [
            {
                "doc": x["doc"],
                "region": x["region"],
                "row": x["row"],
                "role_hit": x["hit"],
                "statuses": x.get("statuses", []),
            }
            for x in rows
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--parent-canonical", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    spec = json.load(open(a.spec, encoding="utf-8"))
    parent = json.load(open(a.parent_canonical, encoding="utf-8"))
    assert spec["parent_canonical_target"] == "v2.27"
    assert spec["source"]["frozen_commit"] == FROZEN_COMMIT
    assert parent["version"] == "v2.27" and parent["status"] == "CURRENT_CANONICAL_RESEARCH_STATE"
    assert parent["canonicality"]["canonicality_audit_status"] == "CANONICALITY_AUDIT_PASS"
    assert spec["status_policy"]["none_or_doubtful_is_never_reinterpreted_as_certain"] is True
    assert spec["cross_fitting"]["candidate_selection_train_only"] is True
    assert spec["train_candidate_gate"]["manual_candidate_addition_forbidden"] is True
    assert spec["train_candidate_gate"]["manual_candidate_removal_forbidden"] is True

    docs, reveal, failures = b0.load_corpus(Path(a.corpus))
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
        selected, backgrounds, counts = select_train(train, spec)
        heldout = 0
        for cand in selected:
            scored = score_test(test, cand)
            heldout += scored["heldout_eligible_occurrences"]
            key = (cand["role"], cand["word"])
            h = history[key]
            h["selected_folds"].append(fold)
            h["train_rows"].append({"fold": fold, **cand})
            h["test_rows"].append({"fold": fold, **scored})
            h["null_probabilities"].extend(
                [cand["train_role_background_probability"]] * scored["heldout_eligible_occurrences"]
            )
        per_fold.append({
            "fold": fold,
            "train_documents": len(train),
            "heldout_documents": len(test),
            "train_role_domain_occurrence_counts": counts,
            "train_role_background_probabilities": backgrounds,
            "train_selected_candidates": len(selected),
            "heldout_eligible_occurrences_of_selected_candidates": heldout,
        })

    cfg = spec["heldout_candidate_gate"]
    family = []
    for (role, word), h in sorted(history.items()):
        selected_folds = sorted(h["selected_folds"])
        if len(selected_folds) < cfg["minimum_selected_folds"]:
            continue
        n = sum(x["heldout_eligible_occurrences"] for x in h["test_rows"])
        k = sum(x["heldout_role_hits"] for x in h["test_rows"])
        doc_ids = sorted({d for x in h["test_rows"] for d in x["heldout_document_ids"]})
        hit_doc_ids = sorted({d for x in h["test_rows"] for d in x["heldout_role_hit_document_ids"]})
        regions = sorted({r for x in h["test_rows"] for r in x["heldout_regions"]})
        status_counter = Counter()
        examples = []
        for x in h["test_rows"]:
            status_counter.update(x["heldout_status_distribution"])
            examples.extend(x["heldout_examples"])
        p = stats.poisson_binomial_upper_tail(h["null_probabilities"], k) if n else 1.0
        family.append({
            "role": role,
            "word_token": word,
            "selected_folds": selected_folds,
            "selected_fold_count": len(selected_folds),
            "train_rows": h["train_rows"],
            "heldout_eligible_occurrences": n,
            "heldout_role_hits": k,
            "heldout_role_precision": (k / n) if n else None,
            "heldout_document_ids": doc_ids,
            "heldout_document_count": len(doc_ids),
            "heldout_role_hit_document_ids": hit_doc_ids,
            "heldout_role_hit_document_count": len(hit_doc_ids),
            "heldout_region_set": regions,
            "heldout_status_distribution": dict(status_counter),
            "heldout_examples": examples,
            "p_value": p,
        })

    qvals = stats.bh_qvalues(family)
    for row, q in zip(family, qvals):
        row["BH_q"] = q
        precision = row["heldout_role_precision"] or 0.0
        ok = bool(
            row["heldout_eligible_occurrences"] >= cfg["minimum_heldout_eligible_occurrences"]
            and row["heldout_document_count"] >= cfg["minimum_heldout_documents"]
            and row["heldout_role_hit_document_count"] >= cfg["minimum_heldout_role_hit_documents"]
            and precision >= cfg["minimum_heldout_role_precision"]
            and q <= cfg["FDR_q_max"]
        )
        row["POSITIONAL_ROLE_CANDIDATE_ADMITTED"] = ok

    # Reveal source labels only after selection, scoring, p-values, FDR and admission.
    for row in family:
        row["source_word_after_scoring"] = reveal.get(row["word_token"], row["word_token"])

    family.sort(key=lambda x: (
        not x["POSITIONAL_ROLE_CANDIDATE_ADMITTED"],
        x["BH_q"],
        -(x["heldout_role_precision"] or 0.0),
        -x["heldout_role_hits"],
    ))
    admitted = [x for x in family if x["POSITIONAL_ROLE_CANDIDATE_ADMITTED"]]
    status = (
        "CROSS_FITTED_POSITIONAL_FUNCTIONAL_ROLE_CANDIDATES_ADMITTED"
        if admitted else
        "CROSS_FITTED_POSITIONAL_FUNCTIONAL_ROLE_CANDIDATES_NOT_ESTABLISHED"
    )

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R7-C0-POSITIONAL-FUNCTIONAL-ROLE-RESULT-2026-08-16-v0.1",
        "version": "v0.1",
        "node_type": "cross_fitted_positional_functional_role_result",
        "status": status,
        "source": {
            "repository": "Hawkar-usls/lineara.xyz",
            "frozen_commit": FROZEN_COMMIT,
            "parsed_documents": len(docs),
            "parse_failures_or_empty": failures,
        },
        "method": {
            "folds": 5,
            "roles": spec["roles"],
            "role_domains": spec["role_domains"],
            "multiple_testing": cfg["multiple_testing"],
            "FDR_q_max": cfg["FDR_q_max"],
            "null": cfg["null"],
        },
        "per_fold": per_fold,
        "cross_fitted_candidate_family_size": len(family),
        "admitted_candidate_count": len(admitted),
        "admitted_candidates": admitted,
        "candidate_family_after_scoring": family,
        "leakage_firewall": {
            "candidate_selection_used_heldout_documents": False,
            "source_word_labels_used_for_selection_or_scoring": False,
            "none_or_doubtful_reinterpreted_as_certain": False,
            "translations_used": False,
            "external_dictionaries_used": False,
            "Linear_B_supervision_used": False,
            "Notti_readings_used": False,
            "manual_candidate_addition_or_removal": False,
            "R3B_blind_eligibility_affected": False,
        },
        "epistemic_gate": {
            "positional_functional_role_candidates_established": bool(admitted),
            "probable_function_established": False,
            "exact_word_meaning_established": False,
            "translation_established": False,
            "phonetic_value_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "R3B_external_replication_established": False,
        },
        "next_gate": (
            "Freeze admitted candidate family unchanged for R7-C1 full-region holdout and R7-C2 structure-destroying adversarial null."
            if admitted else
            "Preserve negative and move to separately preregistered sequence-state / latent document-template roles without relaxing R7-C0 post hoc."
        ),
        "claim_ceiling": spec["claim_ceiling"],
    }
    Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "candidate_family_size": len(family),
        "admitted": len(admitted),
        "probable_function_established": False,
        "decipherment_established": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
