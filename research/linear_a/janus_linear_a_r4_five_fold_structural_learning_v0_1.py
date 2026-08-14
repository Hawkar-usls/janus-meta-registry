#!/usr/bin/env python3
"""JANUS Linear A R4-1 five-fold cross-validated structural learning.

Reuses the frozen R4-0 parser/model/evaluator with unchanged hyperparameters.
Only document fold assignment and cross-fold aggregation are new.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path

import janus_linear_a_r4_self_supervised_structural_learning_v0_1 as core

FOLD_NAMESPACE = "JANUS-LINA-R4-1-CV-v0.1"
MODELS = ("B0_UNIGRAM", "B1_DIRECTIONAL_CONTEXT_COUNT", "M1_DIRECTIONAL_PPMI_SVD")


def fold_of(doc_id: str) -> int:
    return int(hashlib.sha256(f"{FOLD_NAMESPACE}|{doc_id}".encode("utf-8")).hexdigest()[:8], 16) % 5


def weighted_aggregate(fold_rows):
    out = {}
    for model_name in MODELS:
        total_n = sum(r["evaluation"]["metrics"][model_name]["evaluable_masks"] for r in fold_rows)
        if total_n == 0:
            out[model_name] = {
                "evaluable_masks": 0,
                "top1_accuracy": None,
                "top5_accuracy": None,
                "mean_reciprocal_rank": None,
            }
            continue
        def wavg(field):
            num = 0.0
            for r in fold_rows:
                m = r["evaluation"]["metrics"][model_name]
                num += m[field] * m["evaluable_masks"]
            return num / total_n
        out[model_name] = {
            "evaluable_masks": total_n,
            "top1_accuracy": wavg("top1_accuracy"),
            "top5_accuracy": wavg("top5_accuracy"),
            "mean_reciprocal_rank": wavg("mean_reciprocal_rank"),
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--parent-result", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = json.load(open(args.spec, encoding="utf-8"))
    parent = json.load(open(args.parent_result, encoding="utf-8"))
    assert parent["status"] == spec["parent_status_required"]
    assert parent["source"]["frozen_commit"] == core.FROZEN_COMMIT
    assert spec["model_frozen_from_R4_0"]["minimum_train_target_frequency"] == 5
    assert spec["model_frozen_from_R4_0"]["directional_context_window"] == 2
    assert spec["model_frozen_from_R4_0"]["svd_rank"] == 32
    assert spec["cross_validation"]["evaluation_target_status"] == "certain_only"
    assert spec["cross_validation"]["source_status_none_reinterpreted"] is False

    docs, reveal, failures = core.load_corpus(Path(args.corpus))
    doc_fold = {d["doc"]: fold_of(d["doc"]) for d in docs}
    fold_counts = {str(k): sum(v == k for v in doc_fold.values()) for k in range(5)}
    if any(v == 0 for v in fold_counts.values()):
        raise SystemExit("EMPTY_CV_FOLD")

    fold_rows = []
    pair_history = defaultdict(lambda: {
        "selected_folds": [], "replicated_folds": [], "test_eligible_folds": [],
        "train_cosines": [], "test_cosines": []
    })

    for fold in range(5):
        train_docs = [d for d in docs if doc_fold[d["doc"]] != fold]
        test_docs = [d for d in docs if doc_fold[d["doc"]] == fold]
        model = core.build_train_model(train_docs, min_freq=5, rank=32)
        evaluation = core.evaluate(test_docs, model)
        # Pass an empty reveal map so source labels cannot appear until all folds are scored.
        analogies = core.analogy_probe(train_docs, test_docs, model, {}, topn=30)
        for row in analogies["pairs_after_postscore_source_label_reveal"]:
            key = (row["token_a"], row["token_b"])
            h = pair_history[key]
            h["selected_folds"].append(fold)
            h["train_cosines"].append(row["train_latent_cosine"])
            if row["test_eligible"]:
                h["test_eligible_folds"].append(fold)
            if row["test_context_cosine"] is not None:
                h["test_cosines"].append(row["test_context_cosine"])
            if row["replicated_context_similarity"]:
                h["replicated_folds"].append(fold)

        b0 = evaluation["metrics"]["B0_UNIGRAM"]
        b1 = evaluation["metrics"]["B1_DIRECTIONAL_CONTEXT_COUNT"]
        m1 = evaluation["metrics"]["M1_DIRECTIONAL_PPMI_SVD"]
        both_beat_mrr = bool(
            b0["mean_reciprocal_rank"] is not None
            and b1["mean_reciprocal_rank"] is not None
            and m1["mean_reciprocal_rank"] is not None
            and b1["mean_reciprocal_rank"] > b0["mean_reciprocal_rank"]
            and m1["mean_reciprocal_rank"] > b0["mean_reciprocal_rank"]
        )
        fold_rows.append({
            "fold": fold,
            "train_documents": len(train_docs),
            "heldout_documents": len(test_docs),
            "vocabulary_size": len(model["vocab"]),
            "svd_rank_used": model["rank_used"],
            "evaluation": evaluation,
            "train_selected_analogy_pairs": analogies["selected_train_pairs"],
            "heldout_eligible_analogy_pairs": analogies["test_eligible_pairs"],
            "heldout_replicated_analogy_pairs": analogies["test_replicated_pairs"],
            "both_context_models_beat_unigram_MRR": both_beat_mrr,
        })

    aggregate = weighted_aggregate(fold_rows)
    b0 = aggregate["B0_UNIGRAM"]
    b1 = aggregate["B1_DIRECTIONAL_CONTEXT_COUNT"]
    m1 = aggregate["M1_DIRECTIONAL_PPMI_SVD"]
    enough = aggregate["M1_DIRECTIONAL_PPMI_SVD"]["evaluable_masks"] >= 200
    fold_robust = sum(r["both_context_models_beat_unigram_MRR"] for r in fold_rows)
    both_aggregate = bool(
        b1["mean_reciprocal_rank"] > b0["mean_reciprocal_rank"]
        and b1["top5_accuracy"] > b0["top5_accuracy"]
        and m1["mean_reciprocal_rank"] > b0["mean_reciprocal_rank"]
        and m1["top5_accuracy"] > b0["top5_accuracy"]
    ) if enough else False
    admitted = bool(enough and both_aggregate and fold_robust >= 4)

    pair_rows = []
    for (a, b), h in pair_history.items():
        selected_n = len(h["selected_folds"])
        replicated_n = len(h["replicated_folds"])
        cv_rep = selected_n >= 3 and replicated_n >= 2
        pair_rows.append({
            "token_a": a,
            "token_b": b,
            "folds_selected": h["selected_folds"],
            "folds_test_eligible": h["test_eligible_folds"],
            "folds_replicated": h["replicated_folds"],
            "selected_fold_count": selected_n,
            "replicated_fold_count": replicated_n,
            "mean_train_latent_cosine": statistics.fmean(h["train_cosines"]) if h["train_cosines"] else None,
            "mean_test_context_cosine_when_available": statistics.fmean(h["test_cosines"]) if h["test_cosines"] else None,
            "CV_REPLICATED_STRUCTURAL_ANALOGY": cv_rep,
        })
    pair_rows.sort(key=lambda r: (
        -int(r["CV_REPLICATED_STRUCTURAL_ANALOGY"]),
        -r["replicated_fold_count"],
        -r["selected_fold_count"],
        -(r["mean_train_latent_cosine"] or 0.0),
        r["token_a"], r["token_b"]
    ))
    # Source labels are added only after every fold's train selection and heldout scoring is complete.
    revealed_pairs = [
        {**r, "source_label_a": reveal.get(r["token_a"]), "source_label_b": reveal.get(r["token_b"])}
        for r in pair_rows
    ]
    replicated_pairs = [r for r in revealed_pairs if r["CV_REPLICATED_STRUCTURAL_ANALOGY"]]

    status = (
        "CROSS_VALIDATED_INTERNAL_CONTEXT_STRUCTURE_SIGNAL_PRESENT"
        if admitted else
        "CROSS_VALIDATED_INTERNAL_CONTEXT_STRUCTURE_SIGNAL_NOT_ADMITTED"
    )
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R4-1-FIVE-FOLD-CROSS-VALIDATED-STRUCTURAL-LEARNING-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "cross_validated_self_supervised_structural_learning_result",
        "status": status,
        "source": {
            "repository": "Hawkar-usls/lineara.xyz",
            "frozen_commit": core.FROZEN_COMMIT,
            "parsed_documents": len(docs),
            "parse_failures_or_empty": failures,
        },
        "parent_R4_0": {
            "path": args.parent_result,
            "status": parent["status"],
            "evaluable_test_masks": parent["heldout_masked_prediction"]["evaluable_test_masks"],
            "promotion_inherited": False,
        },
        "fold_assignment": {
            "namespace": FOLD_NAMESPACE,
            "fold_counts": fold_counts,
            "each_document_held_out_exactly_once": True,
        },
        "fold_results": fold_rows,
        "aggregate_masked_prediction": aggregate,
        "admission": {
            "minimum_aggregate_evaluable_masks": 200,
            "actual_aggregate_evaluable_masks": aggregate["M1_DIRECTIONAL_PPMI_SVD"]["evaluable_masks"],
            "enough_evidence": enough,
            "both_context_models_beat_unigram_aggregate_MRR_and_top5": both_aggregate,
            "folds_where_both_context_models_beat_unigram_MRR": fold_robust,
            "minimum_required_folds": 4,
            "cross_validated_internal_context_structure_admitted": admitted,
        },
        "cross_fold_structural_analogy": {
            "unique_train_selected_pairs_across_folds": len(revealed_pairs),
            "CV_replicated_pair_count": len(replicated_pairs),
            "CV_replicated_pairs": replicated_pairs,
            "all_train_selected_pairs_after_postscore_source_label_reveal": revealed_pairs,
            "semantic_equivalence_claimed": False,
        },
        "leakage_firewall": {
            "source_status_none_reinterpreted": False,
            "source_status_doubtful_reinterpreted": False,
            "translations_used": False,
            "language_dictionaries_used": False,
            "Notti_2018_readings_used": False,
            "Notti_2021_2025_PH13_content_used": False,
            "Linear_B_semantic_supervision_used": False,
            "R3B_blind_eligibility_affected": False,
        },
        "epistemic_gate": {
            "internal_context_structure_learned_cross_validated": admitted,
            "CV_replicated_structural_analogies_are_semantic_equivalences": False,
            "translation_established": False,
            "phonetic_value_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "R3B_external_replication_established": False,
        },
        "claim_ceiling": {
            "allowed": "Cross-validated internal context predictability and cross-fold structural analogy candidates only.",
            "forbidden": ["translation", "semantic equivalence", "phonetic assignment", "language-family identification", "new anchor", "decipherment", "R3B replication"]
        }
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "parsed_documents": len(docs),
        "fold_counts": fold_counts,
        "aggregate": aggregate,
        "folds_where_both_context_models_beat_unigram_MRR": fold_robust,
        "CV_replicated_pair_count": len(replicated_pairs),
        "decipherment_established": False,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
