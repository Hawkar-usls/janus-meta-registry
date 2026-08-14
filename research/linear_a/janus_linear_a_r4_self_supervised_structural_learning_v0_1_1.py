#!/usr/bin/env python3
"""R4-0 v0.1.1 pre-execution corrective wrapper.

The frozen science functions are imported unchanged from v0.1.  This wrapper
only replaces the invalid lowercase JSON-style boolean in result assembly.
No scientific execution of v0.1 occurred before this correction.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import janus_linear_a_r4_self_supervised_structural_learning_v0_1 as core

VERSION = "JANUS-LINEAR-A-R4-0-SELF-SUPERVISED-v0.1.1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = json.load(open(args.spec, encoding="utf-8"))
    assert spec["source"]["frozen_commit"] == core.FROZEN_COMMIT
    assert spec["partition"]["selection_from_test_forbidden"] is True
    assert spec["leakage_firewall"]["Notti_2021_2025_PH13_content_used"] is False

    docs, reveal, failures = core.load_corpus(Path(args.corpus))
    by_split = {s: [d for d in docs if d["split"] == s] for s in ("TRAIN", "DEV", "TEST")}
    model = core.build_train_model(by_split["TRAIN"], min_freq=5, rank=32)
    evaluation = core.evaluate(by_split["TEST"], model)
    analogies = core.analogy_probe(by_split["TRAIN"], by_split["TEST"], model, reveal, topn=30)

    m0 = evaluation["metrics"]["B0_UNIGRAM"]
    m1 = evaluation["metrics"]["M1_DIRECTIONAL_PPMI_SVD"]
    enough = evaluation["evaluable_test_masks"] >= 50
    structure_signal = bool(
        enough
        and m1["mean_reciprocal_rank"] is not None
        and m0["mean_reciprocal_rank"] is not None
        and m1["mean_reciprocal_rank"] > m0["mean_reciprocal_rank"]
        and m1["top5_accuracy"] > m0["top5_accuracy"]
    )
    if not enough:
        status = "BLOCKED_INSUFFICIENT_EVALUABLE_TEST_MASKS"
    elif structure_signal:
        status = "SELF_SUPERVISED_INTERNAL_STRUCTURE_SIGNAL_PRESENT"
    else:
        status = "SELF_SUPERVISED_INTERNAL_STRUCTURE_SIGNAL_NOT_ESTABLISHED"

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R4-0-SELF-SUPERVISED-STRUCTURAL-LEARNING-RESULT-2026-08-14-v0.1.1",
        "version": "v0.1.1",
        "node_type": "self_supervised_structural_learning_result",
        "status": status,
        "source": {
            "repository": "Hawkar-usls/lineara.xyz",
            "upstream_lineage": "mwenge/lineara.xyz",
            "frozen_commit": core.FROZEN_COMMIT,
            "parsed_documents": len(docs),
            "parse_failures_or_empty": failures
        },
        "pre_execution_correction": {
            "parent_runner": "research/linear_a/janus_linear_a_r4_self_supervised_structural_learning_v0_1.py",
            "scientific_execution_of_parent_occurred": False,
            "scientific_functions_reused_unchanged": [
                "parse_document", "load_corpus", "directional_context",
                "build_train_model", "evaluate", "analogy_probe"
            ],
            "permitted_change": "result-assembly Python boolean serialization only"
        },
        "split_counts": {k: len(v) for k, v in by_split.items()},
        "training": {
            "raw_labels_available_to_training": False,
            "candidate_vocabulary_size": len(model["vocab"]),
            "directional_context_feature_count": len(model["features"]),
            "svd_rank_requested": 32,
            "svd_rank_used": model["rank_used"],
            "minimum_train_frequency": 5,
            "translations_used": False,
            "language_dictionaries_used": False,
            "external_semantic_supervision_used": False
        },
        "heldout_masked_prediction": evaluation,
        "primary_structure_signal": structure_signal,
        "structural_analogy_probe": analogies,
        "leakage_firewall": {
            "test_used_for_model_selection": False,
            "Notti_2021_2025_PH13_content_used": False,
            "Notti_2018_readings_used": False,
            "R3C_language_dictionary_inputs_used": False,
            "R3B_blind_eligibility_affected": False
        },
        "epistemic_gate": {
            "internal_distributional_structure_learned": structure_signal,
            "structural_analogy_candidates_are_semantic_equivalences": False,
            "translation_established": False,
            "phonetic_value_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "R3B_external_replication_established": False
        },
        "claim_ceiling": {
            "allowed": "Held-out predictive structure and train-selected/test-scored structural analogy candidates only.",
            "forbidden": [
                "No translation claim.",
                "No semantic-equivalence claim.",
                "No phonetic assignment.",
                "No language-family assignment.",
                "No new anchor.",
                "No Linear A decipherment.",
                "No R3B external replication."
            ]
        }
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "documents": len(docs),
        "split_counts": result["split_counts"],
        "vocab": result["training"]["candidate_vocabulary_size"],
        "evaluable_test_masks": evaluation["evaluable_test_masks"],
        "metrics": evaluation["metrics"],
        "test_replicated_analogy_pairs": analogies["test_replicated_pairs"],
        "decipherment_established": False
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
