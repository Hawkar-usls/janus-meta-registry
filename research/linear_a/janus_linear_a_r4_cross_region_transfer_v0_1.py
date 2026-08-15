#!/usr/bin/env python3
"""JANUS Linear A R4-3 cross-region transfer audit.

Reuses the frozen R4 sign parser/model/evaluator without changing its scientific
hyperparameters. Regions are selected only by parsed-document count. Each selected
region is then held out in full, so no document from that archaeological region can
enter the corresponding training model.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import janus_linear_a_r4_self_supervised_structural_learning_v0_1 as r4

FROZEN_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
MODELS = ("B0_UNIGRAM", "B1_DIRECTIONAL_CONTEXT_COUNT", "M1_DIRECTIONAL_PPMI_SVD")


def weighted_aggregate(rows):
    out = {}
    for model in MODELS:
        n = sum(x["evaluation"]["metrics"][model]["evaluable_masks"] for x in rows)
        def wa(field):
            if not n:
                return None
            return sum(
                x["evaluation"]["metrics"][model][field]
                * x["evaluation"]["metrics"][model]["evaluable_masks"]
                for x in rows
            ) / n
        out[model] = {
            "evaluable_masks": n,
            "top1_accuracy": wa("top1_accuracy"),
            "top5_accuracy": wa("top5_accuracy"),
            "mean_reciprocal_rank": wa("mean_reciprocal_rank"),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = json.load(open(args.spec, encoding="utf-8"))
    assert spec["source"]["frozen_commit"] == FROZEN_COMMIT
    assert spec["region_selection"]["selected_region_count"] == 3
    assert spec["region_selection"]["selection_uses_target_labels"] is False
    assert spec["region_selection"]["selection_uses_prediction_metrics"] is False
    assert spec["transfer_protocol"]["source_status_none_reinterpreted"] is False
    assert spec["transfer_protocol"]["source_status_doubtful_reinterpreted"] is False
    assert spec["transfer_protocol"]["hyperparameters_changed_after_R4_1"] is False

    docs, _, failures = r4.load_corpus(Path(args.corpus))
    region_counts = Counter(r4.base.region_of(d["doc"]) for d in docs)
    selected_regions = [
        region for region, _ in sorted(region_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    ]
    if len(selected_regions) != 3:
        raise SystemExit("R4_3_REGION_SELECTION_FAIL")

    rows = []
    for region in selected_regions:
        train = [d for d in docs if r4.base.region_of(d["doc"]) != region]
        test = [d for d in docs if r4.base.region_of(d["doc"]) == region]
        if not train or not test:
            raise SystemExit("R4_3_EMPTY_TRANSFER_PARTITION")
        model = r4.build_train_model(train, min_freq=5, rank=32)
        ev = r4.evaluate(test, model)
        b0 = ev["metrics"]["B0_UNIGRAM"]
        b1 = ev["metrics"]["B1_DIRECTIONAL_CONTEXT_COUNT"]
        m1 = ev["metrics"]["M1_DIRECTIONAL_PPMI_SVD"]
        both_mrr = bool(
            b0["mean_reciprocal_rank"] is not None
            and b1["mean_reciprocal_rank"] is not None
            and m1["mean_reciprocal_rank"] is not None
            and b1["mean_reciprocal_rank"] > b0["mean_reciprocal_rank"]
            and m1["mean_reciprocal_rank"] > b0["mean_reciprocal_rank"]
        )
        rows.append({
            "heldout_region": region,
            "heldout_documents": len(test),
            "train_documents": len(train),
            "train_vocab_size": len(model["vocab"]),
            "svd_rank_used": model["rank_used"],
            "both_context_models_beat_unigram_MRR": both_mrr,
            "evaluation": ev,
        })

    agg = weighted_aggregate(rows)
    b0, b1, m1 = agg["B0_UNIGRAM"], agg["B1_DIRECTIONAL_CONTEXT_COUNT"], agg["M1_DIRECTIONAL_PPMI_SVD"]
    total_masks = m1["evaluable_masks"]
    regions_both = sum(x["both_context_models_beat_unigram_MRR"] for x in rows)
    enough = total_masks >= spec["admission_gate"]["minimum_aggregate_evaluable_masks"]
    aggregate_pass = bool(
        b0["mean_reciprocal_rank"] is not None
        and b1["mean_reciprocal_rank"] > b0["mean_reciprocal_rank"]
        and b1["top5_accuracy"] > b0["top5_accuracy"]
        and m1["mean_reciprocal_rank"] > b0["mean_reciprocal_rank"]
        and m1["top5_accuracy"] > b0["top5_accuracy"]
    )
    region_pass = regions_both >= spec["admission_gate"]["minimum_regions_where_both_context_models_beat_unigram_MRR"]
    admitted = bool(enough and aggregate_pass and region_pass)
    status = (
        "CROSS_REGION_INTERNAL_CONTEXT_STRUCTURE_TRANSFER_ADMITTED"
        if admitted else
        "CROSS_REGION_INTERNAL_CONTEXT_STRUCTURE_TRANSFER_NOT_ESTABLISHED"
    )

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R4-3-CROSS-REGION-TRANSFER-RESULT-2026-08-15-v0.1",
        "version": "v0.1",
        "node_type": "cross_region_self_supervised_transfer_result",
        "status": status,
        "source": {
            "repository": "Hawkar-usls/lineara.xyz",
            "frozen_commit": FROZEN_COMMIT,
            "parsed_documents": len(docs),
            "parse_failures_or_empty": failures,
        },
        "region_selection": {
            "rule": spec["region_selection"]["rule"],
            "all_region_document_counts": dict(sorted(region_counts.items())),
            "selected_regions": selected_regions,
            "selection_used_prediction_metrics": False,
            "selection_used_target_labels": False,
        },
        "per_region_transfer": rows,
        "aggregate_transfer": agg,
        "admission": {
            "minimum_aggregate_evaluable_masks": spec["admission_gate"]["minimum_aggregate_evaluable_masks"],
            "actual_aggregate_evaluable_masks": total_masks,
            "minimum_regions_where_both_context_models_beat_unigram_MRR": spec["admission_gate"]["minimum_regions_where_both_context_models_beat_unigram_MRR"],
            "actual_regions_where_both_context_models_beat_unigram_MRR": regions_both,
            "enough_evidence": enough,
            "aggregate_requirements_pass": aggregate_pass,
            "region_consistency_requirement_pass": region_pass,
            "cross_region_transfer_admitted": admitted,
        },
        "leakage_firewall": {
            "Notti_2018_readings_used": False,
            "Notti_2021_2025_PH13_content_used": False,
            "R3C_language_dictionary_inputs_used": False,
            "external_dictionaries_used": False,
            "translations_used": False,
            "Linear_B_supervision_used": False,
            "heldout_region_documents_used_for_training": False,
            "heldout_metrics_used_for_region_selection": False,
            "R3B_blind_eligibility_affected": False,
        },
        "epistemic_gate": {
            "cross_region_internal_context_structure_transfer_established": admitted,
            "semantic_equivalence_established": False,
            "translation_established": False,
            "phonetic_value_established": False,
            "language_family_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "R3B_external_replication_established": False,
        },
        "claim_ceiling": spec["claim_ceiling"],
    }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "selected_regions": selected_regions, "admission": result["admission"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
