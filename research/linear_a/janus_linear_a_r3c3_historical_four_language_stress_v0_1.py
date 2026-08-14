#!/usr/bin/env python3
"""JANUS Linear A R3C-3 historical four-language stress test v0.1.

This is a clean-room statistical stress test of the exact public 2021 Mac
bundle. It is NOT a reproduction of the 2024 paper. Third-party code is never
executed or imported, and raw lexical values/match pairs are never persisted.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import math
import random
import statistics
import zipfile
from pathlib import Path
from typing import Any

SPEC_PATH = "data/JANUS-LINEAR-A-R3C-3-HISTORICAL-FOUR-LANGUAGE-STRESS-TEST-SPEC-2026-08-14-v0.1.json"
SPEC_ID = "JANUS-LINEAR-A-R3C-3-HISTORICAL-FOUR-LANGUAGE-STRESS-TEST-SPEC-2026-08-14-v0.1"
RUNNER_ID = "JANUS-LINEAR-A-R3C3-HISTORICAL-FOUR-LANGUAGE-STRESS-v0.1"
BUNDLE_SHA256 = "a4627d4c2e26668593e8f6f9c8a004ae75bb3f1bbf497a39c0d4a772c9012850"
BUNDLE_BYTES = 1765475
LANGUAGES = ["Ancient Egyptian", "Luwian", "Hittite", "Proto-Celtic"]
PROFILES = ["P1_NUMBERED_RAW_LOWER", "P2_MATCHED_RAW_LOWER", "P3_MATCHED_HISTORICAL_GENERAL_DECIPHERMENT"]
N1 = "N1_WITHIN_LANGUAGE_COMPOSITION_PRESERVING"
N2 = "N2_POOLED_LENGTH_STRATIFIED_LANGUAGE_LABEL"
ITERATIONS = 10000
PRIMARY = "UNIQUE_LINEAR_A_CLUSTER_HIT_COUNT"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def stream_hash(values: list[str]) -> str:
    h = hashlib.sha256()
    for value in values:
        b = value.encode("utf-8")
        h.update(len(b).to_bytes(8, "big"))
        h.update(b)
    return h.hexdigest()


def seed_for(null_id: str, profile_id: str, iteration: int) -> int:
    text = f"{SPEC_ID}|{null_id}|{profile_id}|{iteration}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(text).digest(), "big", signed=False)


def historical_general_cluster(value: str) -> str:
    # Faithful clean-room reconstruction of the historical rem_vowel/openFileDialog
    # case order: iterate over value.lower(), remove lowercase vowel x from the
    # original-case value, then lowercase only at equality comparison.
    out = value
    vowels = ("a", "e", "i", "o", "u")
    for x in value.lower():
        if x in vowels:
            out = out.replace(x, "")
    return out.lower()


def apply_profile(profile_id: str, row: dict[str, str]) -> str:
    if profile_id == "P1_NUMBERED_RAW_LOWER":
        return str(row["Numbered_Words"]).lower()
    if profile_id == "P2_MATCHED_RAW_LOWER":
        return str(row["Matched_Words"]).lower()
    if profile_id == "P3_MATCHED_HISTORICAL_GENERAL_DECIPHERMENT":
        return historical_general_cluster(str(row["Matched_Words"]))
    raise ValueError(f"UNKNOWN_PROFILE:{profile_id}")


def load_csv_member(zf: zipfile.ZipFile, member: str, expected_sha: str) -> bytes:
    data = zf.read(member)
    observed = sha256_bytes(data)
    if observed != expected_sha:
        raise ValueError(f"MEMBER_SHA_MISMATCH:{member}:{observed}:{expected_sha}")
    return data


def decode_csv(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV_DECODE_FAILED")


def load_linear_a(zf: zipfile.ZipFile, spec: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    cfg = spec["linear_a_input"]
    data = load_csv_member(zf, cfg["member"], cfg["sha256"])
    rows = list(csv.reader(io.StringIO(decode_csv(data), newline="")))
    clusters: list[str] = []
    locators: list[str] = []
    short_rows = 0
    for row in rows:
        if len(row) <= cfg["comparison_column_index_zero_based"]:
            short_rows += 1
            raise ValueError(f"LINEAR_A_ROW_TOO_SHORT:index={len(clusters)}:width={len(row)}")
        clusters.append(row[cfg["comparison_column_index_zero_based"]])
        locators.append(row[cfg["source_locator_column_index_zero_based"]] if len(row) > cfg["source_locator_column_index_zero_based"] else "")
    info = {
        "member": cfg["member"],
        "sha256": cfg["sha256"],
        "bytes": len(data),
        "row_count": len(clusters),
        "unique_cluster_count": len(set(clusters)),
        "empty_cluster_count": sum(x == "" for x in clusters),
        "ordered_cluster_stream_sha256": stream_hash(clusters),
        "source_locator_stream_sha256": stream_hash(locators),
        "short_row_count": short_rows,
        "raw_values_persisted": False,
    }
    return clusters, info


def load_dictionaries(zf: zipfile.ZipFile, spec: dict[str, Any]) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    configs = {row["language"]: row for row in spec["dictionary_inputs"]}
    if list(configs) != LANGUAGES:
        raise ValueError(f"DICTIONARY_LANGUAGE_ORDER_MISMATCH:{list(configs)}")
    out: dict[str, list[dict[str, str]]] = {}
    info: dict[str, Any] = {}
    for lang in LANGUAGES:
        cfg = configs[lang]
        data = load_csv_member(zf, cfg["member"], cfg["sha256"])
        reader = csv.DictReader(io.StringIO(decode_csv(data), newline=""))
        fields = reader.fieldnames or []
        for required in spec["dictionary_schema"]["required_headers"]:
            if required not in fields:
                raise ValueError(f"DICTIONARY_HEADER_MISSING:{lang}:{required}:{fields}")
        rows: list[dict[str, str]] = []
        for row in reader:
            rows.append({
                "Numbered_Words": "" if row.get("Numbered_Words") is None else str(row.get("Numbered_Words")),
                "Matched_Words": "" if row.get("Matched_Words") is None else str(row.get("Matched_Words")),
            })
        out[lang] = rows
        info[lang] = {
            "member": cfg["member"],
            "sha256": cfg["sha256"],
            "bytes": len(data),
            "headers": fields,
            "row_count": len(rows),
            "numbered_stream_sha256": stream_hash([r["Numbered_Words"] for r in rows]),
            "matched_stream_sha256": stream_hash([r["Matched_Words"] for r in rows]),
            "raw_values_persisted": False,
        }
    return out, info


def metrics(la_counter: collections.Counter[str], la_unique: set[str], dictionary_clusters: list[str]) -> dict[str, int]:
    dc = collections.Counter(dictionary_clusters)
    shared = la_unique.intersection(dc)
    return {
        "UNIQUE_LINEAR_A_CLUSTER_HIT_COUNT": len(shared),
        "TOTAL_PAIRWISE_EXACT_MATCH_COUNT": sum(la_counter[c] * dc[c] for c in shared),
        "UNIQUE_DICTIONARY_CLUSTER_HIT_COUNT": len(shared),
    }


def redistribute(chars: list[str], lengths: list[int]) -> list[str]:
    result: list[str] = []
    pos = 0
    for length in lengths:
        result.append("".join(chars[pos:pos + length]))
        pos += length
    if pos != len(chars):
        raise ValueError("REDISTRIBUTION_LENGTH_MISMATCH")
    return result


def describe_clusters(values: list[str]) -> dict[str, Any]:
    return {
        "row_count": len(values),
        "unique_count": len(set(values)),
        "empty_count": sum(x == "" for x in values),
        "ordered_cluster_stream_sha256": stream_hash(values),
        "ordered_length_sequence_sha256": canonical_sha256([len(x) for x in values]),
        "global_codepoint_multiset_sha256": canonical_sha256(sorted(collections.Counter("".join(values)).items())),
    }


def summarize_distribution(values: list[int], observed: int, global_max: list[int]) -> dict[str, Any]:
    mean = statistics.fmean(values) if values else 0.0
    sd = statistics.pstdev(values) if len(values) > 1 else 0.0
    ge = sum(v >= observed for v in values)
    ge_max = sum(v >= observed for v in global_max)
    return {
        "observed": observed,
        "null_mean": mean,
        "null_sd_population": sd,
        "observed_minus_null_mean": observed - mean,
        "standardized_excess": (observed - mean) / sd if sd > 0 else None,
        "empirical_percentile_le_observed": sum(v <= observed for v in values) / len(values) if values else 0.0,
        "unadjusted_empirical_one_sided_p": (1 + ge) / (len(values) + 1),
        "FWER_adjusted_p_max12": (1 + ge_max) / (len(global_max) + 1),
        "positive_excess": observed > mean,
        "null_distribution_sha256": canonical_sha256(values),
    }


def n1_distributions(la_counter: collections.Counter[str], la_unique: set[str], clusters: dict[str, dict[str, list[str]]]) -> tuple[dict[str, dict[str, list[int]]], list[int]]:
    dist = {p: {l: [] for l in LANGUAGES} for p in PROFILES}
    global_max: list[int] = []
    lengths = {p: {l: [len(x) for x in clusters[p][l]] for l in LANGUAGES} for p in PROFILES}
    chars = {p: {l: list("".join(clusters[p][l])) for l in LANGUAGES} for p in PROFILES}
    for iteration in range(ITERATIONS):
        iter_stats: list[int] = []
        for profile in PROFILES:
            rng = random.Random(seed_for(N1, profile, iteration))
            for lang in LANGUAGES:
                perm = chars[profile][lang].copy()
                rng.shuffle(perm)
                rebuilt = redistribute(perm, lengths[profile][lang])
                stat = metrics(la_counter, la_unique, rebuilt)[PRIMARY]
                dist[profile][lang].append(stat)
                iter_stats.append(stat)
        global_max.append(max(iter_stats) if iter_stats else 0)
    return dist, global_max


def n2_distributions(la_counter: collections.Counter[str], la_unique: set[str], clusters: dict[str, dict[str, list[str]]]) -> tuple[dict[str, dict[str, list[int]]], list[int]]:
    dist = {p: {l: [] for l in LANGUAGES} for p in PROFILES}
    strata_by_profile: dict[str, dict[int, list[tuple[str, str]]]] = {}
    for profile in PROFILES:
        strata: dict[int, list[tuple[str, str]]] = collections.defaultdict(list)
        for lang in LANGUAGES:
            for cluster in clusters[profile][lang]:
                strata[len(cluster)].append((lang, cluster))
        strata_by_profile[profile] = dict(sorted(strata.items()))
    global_max: list[int] = []
    for iteration in range(ITERATIONS):
        iter_stats: list[int] = []
        for profile in PROFILES:
            rng = random.Random(seed_for(N2, profile, iteration))
            rebuilt = {l: [] for l in LANGUAGES}
            for _, rows in strata_by_profile[profile].items():
                labels = [lang for lang, _ in rows]
                rng.shuffle(labels)
                for assigned, (_, cluster) in zip(labels, rows):
                    rebuilt[assigned].append(cluster)
            for lang in LANGUAGES:
                stat = metrics(la_counter, la_unique, rebuilt[lang])[PRIMARY]
                dist[profile][lang].append(stat)
                iter_stats.append(stat)
        global_max.append(max(iter_stats) if iter_stats else 0)
    return dist, global_max


def decide(n1: dict[str, dict[str, Any]], n2: dict[str, dict[str, Any]], alpha: float = 0.05) -> tuple[str, list[str], list[str]]:
    both: list[str] = []
    one: list[str] = []
    for profile in PROFILES:
        for lang in LANGUAGES:
            cell = f"{profile}|{lang}"
            a = n1[profile][lang]["positive_excess"] and n1[profile][lang]["FWER_adjusted_p_max12"] <= alpha
            b = n2[profile][lang]["positive_excess"] and n2[profile][lang]["FWER_adjusted_p_max12"] <= alpha
            if a and b:
                both.append(cell)
            elif a or b:
                one.append(cell)
    if both:
        return "EXECUTED_HISTORICAL_TECHNICAL_OVERLAP_EXCESS", both, one
    if one:
        return "EXECUTED_HISTORICAL_DISCORDANT_NULLS", [], one
    return "EXECUTED_HISTORICAL_NO_FWER_EXCESS", [], []


def self_test() -> dict[str, Any]:
    assert historical_general_cluster("AbaE") == "abe"  # lowercase a removed; uppercase A/E survive then lowercase
    assert historical_general_cluster("banana") == "bnn"
    assert historical_general_cluster("") == ""
    assert seed_for(N1, PROFILES[0], 0) == seed_for(N1, PROFILES[0], 0)
    la = ["kt", "mn", "kt", ""]
    m = metrics(collections.Counter(la), set(la), ["kt", "zz", "kt"])
    assert m[PRIMARY] == 1 and m["TOTAL_PAIRWISE_EXACT_MATCH_COUNT"] == 4
    rebuilt = redistribute(list("abcd"), [1, 0, 3])
    assert rebuilt == ["a", "", "bcd"]
    return {
        "historical_case_order_canary_pass": True,
        "metric_multiplicity_canary_pass": True,
        "empty_cluster_redistribution_canary_pass": True,
        "deterministic_seed_canary_pass": True,
        "scientific_bundle_execution_performed": False,
    }


def execute(bundle_path: Path, result_path: Path) -> dict[str, Any]:
    spec = json.loads(Path(SPEC_PATH).read_text(encoding="utf-8"))
    if spec.get("status") != "FROZEN_BEFORE_EXECUTION":
        raise ValueError("SPEC_NOT_FROZEN")
    if spec.get("scope", {}).get("languages_fixed") != LANGUAGES:
        raise ValueError("LANGUAGE_SET_OR_ORDER_MISMATCH")
    if [p["profile_id"] for p in spec.get("profiles_fixed_before_execution", [])] != PROFILES:
        raise ValueError("PROFILE_SET_OR_ORDER_MISMATCH")
    if spec["permutation_protocol"]["iterations_per_null_family"] != ITERATIONS:
        raise ValueError("ITERATION_COUNT_MISMATCH")
    if spec["multiple_testing_family"]["cells"] != 12:
        raise ValueError("MULTIPLE_TESTING_FAMILY_MISMATCH")

    raw = bundle_path.read_bytes()
    if len(raw) != BUNDLE_BYTES or sha256_bytes(raw) != BUNDLE_SHA256:
        raise ValueError("BUNDLE_IDENTITY_MISMATCH")

    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        la_clusters, la_info = load_linear_a(zf, spec)
        dictionaries, dictionary_info = load_dictionaries(zf, spec)
        normalized = {p: {l: [apply_profile(p, row) for row in dictionaries[l]] for l in LANGUAGES} for p in PROFILES}

    la_counter = collections.Counter(la_clusters)
    la_unique = set(la_clusters)
    observed: dict[str, dict[str, dict[str, int]]] = {p: {} for p in PROFILES}
    profile_input_fingerprints: dict[str, dict[str, Any]] = {p: {} for p in PROFILES}
    for profile in PROFILES:
        for lang in LANGUAGES:
            vals = normalized[profile][lang]
            observed[profile][lang] = metrics(la_counter, la_unique, vals)
            profile_input_fingerprints[profile][lang] = describe_clusters(vals)

    n1_dist, n1_max = n1_distributions(la_counter, la_unique, normalized)
    n2_dist, n2_max = n2_distributions(la_counter, la_unique, normalized)
    n1_summary = {p: {l: summarize_distribution(n1_dist[p][l], observed[p][l][PRIMARY], n1_max) for l in LANGUAGES} for p in PROFILES}
    n2_summary = {p: {l: summarize_distribution(n2_dist[p][l], observed[p][l][PRIMARY], n2_max) for l in LANGUAGES} for p in PROFILES}
    status, both, one = decide(n1_summary, n2_summary)

    cells = []
    for profile in PROFILES:
        for lang in LANGUAGES:
            cells.append({
                "profile_id": profile,
                "language": lang,
                "observed_metrics": observed[profile][lang],
                "input_fingerprint": profile_input_fingerprints[profile][lang],
                N1: n1_summary[profile][lang],
                N2: n2_summary[profile][lang],
            })
    top_observed = sorted(
        [{"cell": f"{p}|{l}", "observed": observed[p][l][PRIMARY]} for p in PROFILES for l in LANGUAGES],
        key=lambda x: (-x["observed"], x["cell"]),
    )

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-3-HISTORICAL-FOUR-LANGUAGE-STRESS-TEST-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "historical_public_bundle_language_match_stress_test_result",
        "status": status,
        "runner_id": RUNNER_ID,
        "frozen_spec": SPEC_PATH,
        "bundle": {"sha256": sha256_bytes(raw), "bytes": len(raw), "git_blob_sha1": "b58e8a3043911f6de921be39bbf516755839829f"},
        "linear_a_input": la_info,
        "dictionary_inputs": dictionary_info,
        "family": {"languages": LANGUAGES, "profiles": PROFILES, "cells": 12, "paper_2024_missing_language": "Uralic"},
        "cells": cells,
        "null_families": {
            N1: {"mode": "DETERMINISTIC_SAMPLED_PERMUTATION", "iterations": ITERATIONS, "global_max12_distribution_sha256": canonical_sha256(n1_max)},
            N2: {"mode": "DETERMINISTIC_SAMPLED_PERMUTATION", "iterations": ITERATIONS, "global_max12_distribution_sha256": canonical_sha256(n2_max)},
        },
        "top_observed_cells": top_observed,
        "cells_clearing_both_nulls_after_max12_FWER": both,
        "cells_clearing_exactly_one_null_after_max12_FWER": one,
        "safety_and_contamination": {
            "third_party_python_executed": False,
            "third_party_python_imported": False,
            "raw_dictionary_words_persisted": False,
            "raw_match_pairs_persisted": False,
            "cluster_values_persisted": False,
            "manual_semantic_filtering": False,
            "tablet_context_filtering": False,
            "post_result_language_selection": False,
            "post_result_profile_selection": False,
        },
        "claim_ceiling": {
            "historical_public_bundle_stress_test_only": True,
            "paper_exact_2024_reproduction": False,
            "technical_overlap_excess_signal_only": status == "EXECUTED_HISTORICAL_TECHNICAL_OVERLAP_EXCESS",
            "language_family_relationship_established": False,
            "cognacy_established": False,
            "translation_established": False,
            "phonetic_grid_correctness_established": False,
            "R3B_effect": "NONE",
            "new_anchor": False,
            "decipherment": False,
        },
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("self-test")
    run = sub.add_parser("execute")
    run.add_argument("bundle")
    run.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cmd == "self-test":
        print(json.dumps(self_test(), ensure_ascii=False, sort_keys=True))
        return
    result = execute(Path(args.bundle), Path(args.out))
    compact = {
        "status": result["status"],
        "linear_a_rows": result["linear_a_input"]["row_count"],
        "top_observed": result["top_observed_cells"][:5],
        "both": result["cells_clearing_both_nulls_after_max12_FWER"],
        "one": result["cells_clearing_exactly_one_null_after_max12_FWER"],
    }
    print(json.dumps(compact, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
