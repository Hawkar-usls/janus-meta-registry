#!/usr/bin/env python3
"""R3C-1 Briakos 2026 same-lineage reproduction runner v0.1.

The published target vector is known, so this program never tunes parsing or
selection against target values.  It executes every profile frozen in the
method manifest and reports deltas.  Exact historical-source admission is a
byte/SHA gate evaluated before scientific metrics are interpreted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_common_v0_1 import (
    PROFILE_IDS,
    corpus_metrics,
    load_lineara_map,
    ngram_formula_ranking,
    register_metrics,
    scribe_qualifying_metrics,
    site_effect_metrics,
)

EXPECTED_HISTORICAL_BYTES = 1609122
EXPECTED_HISTORICAL_SHA256 = "b7b383b93db55b504eb00c552a8b18c19a588e83bba7ff0ab93ca32277d8bfe2"
HISTORICAL_COMMIT = "568f452c7a5ec80fa292cb307ead2fc6f65d07fb"
CURRENT_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
PRIMARY_PROFILE = "THESIS_LITERAL_ALPHA_v0.1"
PROFILE_ORDER = [
    "THESIS_LITERAL_ALPHA_v0.1",
    "PLUS_BASE_AMBIGUITY_v0.1",
    "EXCLUDE_PLUS_AMBIGUITY_v0.1",
]

PUBLISHED = {
    "basic": {
        "document_count": 419,
        "documents_with_retained_content": 336,
        "documents_without_retained_content": 83,
        "word_tokens": 1244,
        "word_types": 573,
        "sign_tokens": 2481,
        "sign_types": 65,
        "entropy_bits": 5.5826,
        "hapax_word_types": 434,
        "hapax_rate": 0.757,
        "mean_word_length_signs": 1.99,
    },
    "register": {
        "administrative_documents": 299,
        "administrative_sign_tokens": 2139,
        "ceremonial_documents": 37,
        "ceremonial_sign_tokens": 342,
        "jsd_bits": 0.0944,
        "p_raw": 0.018,
        "null_mean": 0.060,
        "null_95_percentile_nearest": 0.084,
    },
    "site": {
        "Khania.documents": 103,
        "Khania.word_tokens": 197,
        "Khania.mean_word_length": 1.584,
        "Phaistos.word_tokens": 43,
        "Phaistos.mean_word_length": 2.326,
        "cohens_d_abs": 0.623,
    },
    "scribe": {"qualifying_scribe_count": 23},
}

PUBLISHED_PRECISION = {
    "entropy_bits": 4,
    "hapax_rate": 3,
    "mean_word_length_signs": 2,
    "jsd_bits": 4,
    "p_raw": 3,
    "null_mean": 3,
    "null_95_percentile_nearest": 3,
    "Khania.mean_word_length": 3,
    "Phaistos.mean_word_length": 3,
    "cohens_d_abs": 3,
}


def comparison(observed: Any, target: Any, metric: str) -> dict[str, Any]:
    row: dict[str, Any] = {"metric": metric, "observed": observed, "published_target": target}
    if observed is None:
        row["status"] = "METHOD_UNDERDETERMINED_OR_NOT_EVALUABLE"
        return row
    if isinstance(target, int) and isinstance(observed, int):
        row["delta"] = observed - target
        row["status"] = "EXACT_MATCH" if observed == target else "FAIL_OR_METHOD_DIVERGENCE"
        return row
    if isinstance(target, (int, float)) and isinstance(observed, (int, float)):
        row["delta"] = observed - target
        digits = PUBLISHED_PRECISION.get(metric)
        if digits is not None and round(float(observed), digits) == round(float(target), digits):
            row["status"] = "MATCH_AT_PUBLISHED_PRECISION"
        elif float(observed) == float(target):
            row["status"] = "EXACT_MATCH"
        else:
            row["status"] = "NUMERIC_DIVERGENCE"
        return row
    row["status"] = "TYPE_OR_METHOD_DIVERGENCE"
    return row


def get_nested_site(site_result: dict[str, Any], dotted: str) -> Any:
    if dotted == "cohens_d_abs":
        return site_result.get("cohens_d_abs")
    site, key = dotted.split(".", 1)
    return site_result.get("groups", {}).get(site, {}).get(key)


def execute_source(path: str, role: str, commit: str) -> dict[str, Any]:
    docs, source_meta = load_lineara_map(path)
    source_meta["role"] = role
    source_meta["commit"] = commit
    if role == "BRIAKOS_HISTORICAL_CANDIDATE":
        byte_match = source_meta["bytes"] == EXPECTED_HISTORICAL_BYTES
        sha_match = source_meta["sha256"] == EXPECTED_HISTORICAL_SHA256
        source_meta["published_expected_bytes"] = EXPECTED_HISTORICAL_BYTES
        source_meta["published_expected_sha256"] = EXPECTED_HISTORICAL_SHA256
        source_meta["byte_match"] = byte_match
        source_meta["sha256_match"] = sha_match
        source_meta["exact_historical_bytes_admitted"] = byte_match and sha_match
    else:
        source_meta["exact_historical_bytes_admitted"] = False
        source_meta["classification"] = "CURRENT_SOURCE_VERSION_TRANSPORT_INPUT"

    profiles: dict[str, Any] = {}
    for profile_id in PROFILE_ORDER:
        basic = corpus_metrics(docs, profile_id)
        register = register_metrics(docs, profile_id, permutations=5000, seed=20260814)
        site = site_effect_metrics(docs, profile_id)
        scribe = scribe_qualifying_metrics(docs, profile_id, threshold=20)
        formula = ngram_formula_ranking(docs, profile_id, top_k=50)
        profiles[profile_id] = {
            "basic": basic,
            "register": register,
            "site_effect": site,
            "scribe": scribe,
            "formula": formula,
        }

    primary = profiles[PRIMARY_PROFILE]
    comparisons: list[dict[str, Any]] = []
    for metric, target in PUBLISHED["basic"].items():
        comparisons.append(comparison(primary["basic"].get(metric), target, metric))
    for metric, target in PUBLISHED["register"].items():
        comparisons.append(comparison(primary["register"].get(metric), target, metric))
    for metric, target in PUBLISHED["site"].items():
        comparisons.append(comparison(get_nested_site(primary["site_effect"], metric), target, metric))
    for metric, target in PUBLISHED["scribe"].items():
        comparisons.append(comparison(primary["scribe"].get(metric), target, metric))

    return {
        "source": source_meta,
        "profiles": profiles,
        "primary_profile_comparisons": comparisons,
        "target_guided_profile_selection_performed": False,
    }


def summarize_breaks(historical: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    hsrc = historical["source"]
    if not hsrc.get("exact_historical_bytes_admitted"):
        first = "SOURCE_IDENTITY"
    else:
        bad = [r for r in historical["primary_profile_comparisons"] if r["status"] not in {"EXACT_MATCH", "MATCH_AT_PUBLISHED_PRECISION"}]
        first = "PARSER_TOKENIZATION_OR_METHOD" if bad else "NONE_FOR_COMPARABLE_PRIMARY_TARGETS"
    return {
        "first_break_against_published_historical_result": first,
        "historical_exact_source_admitted": bool(hsrc.get("exact_historical_bytes_admitted")),
        "current_source_is_separate_transport_leg": True,
        "current_vs_historical_source_sha_equal": current["source"]["sha256"] == historical["source"]["sha256"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--historical", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    assert set(PROFILE_ORDER) == PROFILE_IDS
    historical = execute_source(args.historical, "BRIAKOS_HISTORICAL_CANDIDATE", HISTORICAL_COMMIT)
    current = execute_source(args.current, "JANUS_CURRENT_FROZEN_MWENGE", CURRENT_COMMIT)
    breaks = summarize_breaks(historical, current)

    historical_comparable = historical["primary_profile_comparisons"]
    n_match = sum(1 for r in historical_comparable if r["status"] in {"EXACT_MATCH", "MATCH_AT_PUBLISHED_PRECISION"})
    n_diverge = sum(1 for r in historical_comparable if r["status"] in {"FAIL_OR_METHOD_DIVERGENCE", "NUMERIC_DIVERGENCE", "TYPE_OR_METHOD_DIVERGENCE"})
    if not historical["source"].get("exact_historical_bytes_admitted"):
        status = "BLOCKED_HISTORICAL_SOURCE_HASH_NOT_ADMITTED"
    elif n_diverge == 0:
        status = "R3C_1_PRIMARY_COMPARABLE_TARGETS_REPRODUCED"
    elif n_match > 0:
        status = "R3C_1_PARTIAL_REPRODUCTION_WITH_LOCALIZED_METHOD_DIVERGENCES"
    else:
        status = "R3C_1_REPRODUCTION_FAILED_OR_METHOD_MISMATCH"

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1-BRIAKOS-REPRODUCTION-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "same_lineage_reproduction_result",
        "status": status,
        "frozen_inputs": {
            "historical_commit": HISTORICAL_COMMIT,
            "current_commit": CURRENT_COMMIT,
            "historical_expected_bytes": EXPECTED_HISTORICAL_BYTES,
            "historical_expected_sha256": EXPECTED_HISTORICAL_SHA256,
            "profiles": PROFILE_ORDER,
            "permutations": 5000,
            "JANUS_replay_seed": 20260814,
        },
        "historical": historical,
        "current_transport": current,
        "break_localization": breaks,
        "summary": {
            "primary_comparable_target_count": len(historical_comparable),
            "match_count": n_match,
            "divergence_count": n_diverge,
            "method_underdetermined_count": sum(1 for r in historical_comparable if r["status"] == "METHOD_UNDERDETERMINED_OR_NOT_EVALUABLE"),
            "all_frozen_profiles_reported": True,
            "published_values_used_for_profile_selection": False,
        },
        "known_method_limits": [
            "Briakos original random seed is not published; JANUS uses a frozen replay seed and reports stochastic values as a replay, not bit-identical RNG reproduction.",
            "Exact distinctive-bigram expected-share formula is not sufficiently specified for v0.1 and is not fabricated.",
            "The exact nine-item formula ground-truth list is not invented; top-50 structural ranking is emitted but ground-truth scoring remains method-underdetermined.",
            "The thesis contains a 1448-tablet statement in the formula section that conflicts with the 419-record primary corpus description; JANUS preserves the inconsistency rather than guessing an alternate corpus."
        ],
        "claim_ceiling": {
            "same_lineage_reproduction_only": True,
            "R3B_effect": "NONE",
            "independent_transcription_replication": False,
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "source": historical["source"], "summary": result["summary"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
