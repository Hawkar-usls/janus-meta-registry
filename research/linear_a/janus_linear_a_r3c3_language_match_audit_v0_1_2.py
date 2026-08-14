#!/usr/bin/env python3
"""JANUS R3C-3 corrective language-match audit v0.1.2.

The runner is deliberately downstream of an admitted normalization contract.
It NEVER guesses paper preprocessing from prose or selected published matches.
Scientific execution consumes only exact, hash-bound normalized JSON views.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import math
import random
import re
import statistics
from pathlib import Path
from typing import Any, Iterable

RUNNER_ID = "JANUS-LINEAR-A-R3C3-LANGUAGE-MATCH-AUDIT-v0.1.2"
SPEC_ID = "JANUS-LINEAR-A-R3C-3-CORRECTIVE-LANGUAGE-MATCH-AUDIT-SPEC-2026-08-14-v0.1.2"
SPEC_PATH = "data/JANUS-LINEAR-A-R3C-3-CORRECTIVE-LANGUAGE-MATCH-AUDIT-SPEC-2026-08-14-v0.1.2.json"
RECEIPT_CONTRACT_PATH = "data/JANUS-LINEAR-A-R3C-3-EXECUTION-INPUT-RECEIPT-CONTRACT-2026-08-14-v0.1.json"
LANGUAGES = ["Ancient Egyptian", "Luwian", "Hittite", "Proto-Celtic", "Uralic"]
PRIMARY_METRIC = "UNIQUE_LINEAR_A_CLUSTER_HIT_COUNT"
N1 = "N1_WITHIN_LANGUAGE_COMPOSITION_PRESERVING"
N2 = "N2_POOLED_LENGTH_STRATIFIED_LANGUAGE_LABEL"
DEFAULT_ITERATIONS = 10000
HEX64 = re.compile(r"^[0-9a-f]{64}$")
RECEIPT_STATUS = "R3C_3_EXECUTION_INPUT_RECEIPT_ADMITTED"
NORMALIZATION_STATUS = "UPSTREAM_NORMALIZATION_CONTRACT_ADMITTED"
PROVENANCE_STATUS = "PAPER_PHONETIC_GRID_OR_MASTER_LIST_PROVENANCE_ADMITTED"
REQUIRED_NORMALIZATION_OPERATIONS = [
    "linear_a_input_field",
    "vowel_deletion_set",
    "vowel_deletion_order",
    "case_behavior",
    "outer_whitespace_behavior",
    "internal_whitespace_behavior",
    "punctuation_behavior",
    "unicode_normalization_behavior",
    "diacritic_behavior",
    "empty_cluster_behavior",
    "dictionary_duplicate_behavior",
    "linear_a_duplicate_behavior",
    "string_equality_semantics",
]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_file(path: Path) -> tuple[str, int]:
    body = path.read_bytes()
    return hashlib.sha256(body).hexdigest(), len(body)


def valid_file_identity(obj: Any) -> bool:
    return (
        isinstance(obj, dict)
        and isinstance(obj.get("original_filename"), str) and bool(obj["original_filename"])
        and isinstance(obj.get("sha256"), str) and bool(HEX64.fullmatch(obj["sha256"]))
        and isinstance(obj.get("bytes"), int) and obj["bytes"] >= 0
        and isinstance(obj.get("mime_type"), str) and bool(obj["mime_type"])
        and isinstance(obj.get("encoding"), str) and bool(obj["encoding"])
        and isinstance(obj.get("acquisition_route"), str) and bool(obj["acquisition_route"])
        and isinstance(obj.get("paper_provenance"), str) and bool(obj["paper_provenance"])
        and isinstance(obj.get("license_or_access_basis"), str) and bool(obj["license_or_access_basis"])
    )


def _operation_is_identity(value: Any) -> bool:
    if isinstance(value, dict):
        return value.get("identity_preserving") is True
    return False


def validate_receipt_structure(receipt: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(receipt, dict):
        return ["RECEIPT_NOT_OBJECT"]
    if receipt.get("node_type") != "r3c_3_execution_input_receipt":
        errors.append("RECEIPT_NODE_TYPE_MISMATCH")
    if receipt.get("status") != RECEIPT_STATUS:
        errors.append(f"RECEIPT_STATUS_NOT_ADMITTED:{receipt.get('status')}")

    paper = receipt.get("paper_identity")
    if not isinstance(paper, dict) or paper.get("doi") != "10.3390/info15020073":
        errors.append("PAPER_IDENTITY_DOI_MISMATCH")

    master = receipt.get("linear_a_master_list")
    if not valid_file_identity(master):
        errors.append("LINEAR_A_MASTER_LIST_FILE_IDENTITY_INVALID")
    else:
        for field in ("table_or_sheet_identity", "column_schema", "comparison_column", "row_identity_rule", "row_order_rule", "duplicate_row_policy"):
            if field not in master:
                errors.append(f"LINEAR_A_MASTER_LIST_MISSING:{field}")

    dictionaries = receipt.get("dictionary_inputs")
    if not isinstance(dictionaries, list):
        errors.append("DICTIONARY_INPUTS_NOT_LIST")
        dictionaries = []
    seen_languages: list[str] = []
    for i, row in enumerate(dictionaries):
        if not valid_file_identity(row):
            errors.append(f"DICTIONARY_INPUT[{i}]_FILE_IDENTITY_INVALID")
            continue
        language = row.get("language")
        if language not in LANGUAGES:
            errors.append(f"DICTIONARY_INPUT[{i}]_UNKNOWN_LANGUAGE:{language}")
        else:
            seen_languages.append(language)
        for field in ("dictionary_source_identity", "row_count", "row_identity_rule", "row_order_rule", "duplicate_row_policy"):
            if field not in row:
                errors.append(f"DICTIONARY_INPUT[{i}]_MISSING:{field}")
        if not isinstance(row.get("row_count"), int) or row.get("row_count", -1) < 0:
            errors.append(f"DICTIONARY_INPUT[{i}]_INVALID_ROW_COUNT")
    if sorted(seen_languages) != sorted(LANGUAGES):
        errors.append(f"DICTIONARY_LANGUAGE_SET_MISMATCH:{seen_languages}")
    if len(seen_languages) != len(set(seen_languages)):
        errors.append("DICTIONARY_LANGUAGE_DUPLICATE")

    provenance = receipt.get("master_list_provenance")
    if not isinstance(provenance, dict) or provenance.get("status") != PROVENANCE_STATUS:
        errors.append("MASTER_LIST_PROVENANCE_NOT_ADMITTED")

    normalization = receipt.get("normalization_contract")
    contract_id: str | None = None
    if not isinstance(normalization, dict):
        errors.append("NORMALIZATION_CONTRACT_NOT_OBJECT")
    else:
        if normalization.get("status") != NORMALIZATION_STATUS:
            errors.append(f"NORMALIZATION_CONTRACT_NOT_ADMITTED:{normalization.get('status')}")
        contract_id = normalization.get("contract_id")
        if not isinstance(contract_id, str) or not contract_id:
            errors.append("NORMALIZATION_CONTRACT_ID_MISSING")
        operations = normalization.get("operations")
        if not isinstance(operations, dict):
            errors.append("NORMALIZATION_OPERATIONS_NOT_OBJECT")
            operations = {}
        for operation in REQUIRED_NORMALIZATION_OPERATIONS:
            if operation not in operations:
                errors.append(f"NORMALIZATION_OPERATION_MISSING:{operation}")
        canaries = normalization.get("canaries")
        if not isinstance(canaries, list):
            errors.append("NORMALIZATION_CANARIES_NOT_LIST")
            canaries = []
        canary_ops = collections.defaultdict(list)
        for i, canary in enumerate(canaries):
            if not isinstance(canary, dict):
                errors.append(f"NORMALIZATION_CANARY[{i}]_NOT_OBJECT")
                continue
            for field in ("canary_id", "operation", "input", "expected_output", "observed_output", "verification_route", "pass"):
                if field not in canary:
                    errors.append(f"NORMALIZATION_CANARY[{i}]_MISSING:{field}")
            if canary.get("pass") is not True:
                errors.append(f"NORMALIZATION_CANARY[{i}]_NOT_PASS")
            if canary.get("expected_output") != canary.get("observed_output"):
                errors.append(f"NORMALIZATION_CANARY[{i}]_OUTPUT_MISMATCH")
            if isinstance(canary.get("operation"), str):
                canary_ops[canary["operation"]].append(canary)
        for operation in REQUIRED_NORMALIZATION_OPERATIONS:
            if operation in operations and not _operation_is_identity(operations[operation]) and not canary_ops.get(operation):
                errors.append(f"NORMALIZATION_NONIDENTITY_OPERATION_WITHOUT_CANARY:{operation}")

    views = receipt.get("normalized_execution_views")
    if not isinstance(views, dict):
        errors.append("NORMALIZED_EXECUTION_VIEWS_NOT_OBJECT")
    else:
        la_view = views.get("linear_a_view")
        if not isinstance(la_view, dict):
            errors.append("LINEAR_A_NORMALIZED_VIEW_NOT_OBJECT")
        else:
            for f in ("path", "sha256", "bytes", "format", "normalization_contract_id"):
                if f not in la_view:
                    errors.append(f"LINEAR_A_NORMALIZED_VIEW_MISSING:{f}")
            if la_view.get("format") != "JSON":
                errors.append("LINEAR_A_NORMALIZED_VIEW_FORMAT_NOT_JSON")
            if not isinstance(la_view.get("sha256"), str) or not HEX64.fullmatch(la_view.get("sha256", "")):
                errors.append("LINEAR_A_NORMALIZED_VIEW_SHA_INVALID")
            if contract_id and la_view.get("normalization_contract_id") != contract_id:
                errors.append("LINEAR_A_NORMALIZED_VIEW_CONTRACT_ID_MISMATCH")
        dict_views = views.get("dictionary_views")
        if not isinstance(dict_views, list):
            errors.append("DICTIONARY_NORMALIZED_VIEWS_NOT_LIST")
            dict_views = []
        view_languages = []
        for i, view in enumerate(dict_views):
            if not isinstance(view, dict):
                errors.append(f"DICTIONARY_NORMALIZED_VIEW[{i}]_NOT_OBJECT")
                continue
            for f in ("language", "path", "sha256", "bytes", "format", "normalization_contract_id"):
                if f not in view:
                    errors.append(f"DICTIONARY_NORMALIZED_VIEW[{i}]_MISSING:{f}")
            if view.get("language") in LANGUAGES:
                view_languages.append(view["language"])
            else:
                errors.append(f"DICTIONARY_NORMALIZED_VIEW[{i}]_UNKNOWN_LANGUAGE:{view.get('language')}")
            if view.get("format") != "JSON":
                errors.append(f"DICTIONARY_NORMALIZED_VIEW[{i}]_FORMAT_NOT_JSON")
            if not isinstance(view.get("sha256"), str) or not HEX64.fullmatch(view.get("sha256", "")):
                errors.append(f"DICTIONARY_NORMALIZED_VIEW[{i}]_SHA_INVALID")
            if contract_id and view.get("normalization_contract_id") != contract_id:
                errors.append(f"DICTIONARY_NORMALIZED_VIEW[{i}]_CONTRACT_ID_MISMATCH")
        if sorted(view_languages) != sorted(LANGUAGES):
            errors.append(f"DICTIONARY_NORMALIZED_VIEW_LANGUAGE_SET_MISMATCH:{view_languages}")

    ceiling = receipt.get("claim_ceiling")
    if not isinstance(ceiling, dict):
        errors.append("CLAIM_CEILING_NOT_OBJECT")
    else:
        forbidden_true = ("language_family_relationship_established", "new_anchor", "decipherment")
        for key in forbidden_true:
            if ceiling.get(key) is not False:
                errors.append(f"CLAIM_CEILING_FORBIDDEN_PROMOTION:{key}:{ceiling.get(key)}")
        if ceiling.get("R3B_effect") != "NONE":
            errors.append(f"CLAIM_CEILING_R3B_EFFECT_NOT_NONE:{ceiling.get('R3B_effect')}")
    return errors


def validate_spec(spec: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(spec, dict):
        return ["SPEC_NOT_OBJECT"]
    if spec.get("artifact_uuid") != SPEC_ID:
        errors.append("SPEC_ID_MISMATCH")
    if spec.get("status") != "FROZEN_BEFORE_EXECUTION_CORRECTED_NORMALIZATION_GATE":
        errors.append("SPEC_STATUS_MISMATCH")
    if spec.get("fixed_languages") != LANGUAGES:
        errors.append("SPEC_LANGUAGE_SET_OR_ORDER_MISMATCH")
    perm = spec.get("permutation_protocol")
    if not isinstance(perm, dict) or perm.get("iterations_per_null_family") != DEFAULT_ITERATIONS:
        errors.append("SPEC_PERMUTATION_COUNT_MISMATCH")
    metrics = spec.get("metrics")
    if not isinstance(metrics, list) or [m.get("metric_id") for m in metrics if isinstance(m, dict)] != [
        "UNIQUE_LINEAR_A_CLUSTER_HIT_COUNT",
        "TOTAL_PAIRWISE_EXACT_MATCH_COUNT",
        "UNIQUE_DICTIONARY_CLUSTER_HIT_COUNT",
    ]:
        errors.append("SPEC_METRIC_SET_MISMATCH")
    nulls = spec.get("null_families")
    if not isinstance(nulls, dict) or set(nulls) != {N1, N2}:
        errors.append("SPEC_NULL_FAMILY_MISMATCH")
    if spec.get("claim_ceiling", {}).get("execution_performed") is not False:
        errors.append("SPEC_PREEXECUTION_CLAIM_CEILING_INVALID")
    return errors


def _records_from_json(path: Path) -> list[dict[str, Any]]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, list):
        records = obj
    elif isinstance(obj, dict) and isinstance(obj.get("records"), list):
        records = obj["records"]
    else:
        raise ValueError(f"NORMALIZED_VIEW_NOT_RECORD_LIST:{path}")
    if not all(isinstance(x, dict) for x in records):
        raise ValueError(f"NORMALIZED_VIEW_RECORD_NOT_OBJECT:{path}")
    return records


def _verify_bound_view(view: dict[str, Any], root: Path) -> Path:
    path = (root / view["path"]).resolve() if not Path(view["path"]).is_absolute() else Path(view["path"])
    if not path.exists() or not path.is_file():
        raise ValueError(f"NORMALIZED_VIEW_MISSING:{view['path']}")
    observed_sha, observed_bytes = sha256_file(path)
    if observed_sha != view["sha256"]:
        raise ValueError(f"NORMALIZED_VIEW_SHA_MISMATCH:{view['path']}")
    if observed_bytes != view["bytes"]:
        raise ValueError(f"NORMALIZED_VIEW_BYTE_LENGTH_MISMATCH:{view['path']}")
    return path


def load_execution_records(receipt: dict[str, Any], receipt_path: Path) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], str]:
    errors = validate_receipt_structure(receipt)
    if errors:
        raise ValueError("INVALID_EXECUTION_RECEIPT:" + "|".join(errors))
    contract_id = receipt["normalization_contract"]["contract_id"]
    root = receipt_path.parent
    views = receipt["normalized_execution_views"]
    la_path = _verify_bound_view(views["linear_a_view"], root)
    la_records = _records_from_json(la_path)
    dictionary_records: dict[str, list[dict[str, Any]]] = {}
    for view in views["dictionary_views"]:
        path = _verify_bound_view(view, root)
        dictionary_records[view["language"]] = _records_from_json(path)

    seen_la: set[str] = set()
    for i, row in enumerate(la_records):
        for field in ("linear_a_row_id", "source_locator", "raw_comparison_string", "admitted_normalized_linear_a_cluster", "normalization_contract_id"):
            if field not in row:
                raise ValueError(f"LINEAR_A_RECORD[{i}]_MISSING:{field}")
        if row["normalization_contract_id"] != contract_id:
            raise ValueError(f"LINEAR_A_RECORD[{i}]_CONTRACT_ID_MISMATCH")
        if not isinstance(row["admitted_normalized_linear_a_cluster"], str):
            raise ValueError(f"LINEAR_A_RECORD[{i}]_CLUSTER_NOT_STRING")
        rid = row["linear_a_row_id"]
        if not isinstance(rid, str) or not rid or rid in seen_la:
            raise ValueError(f"LINEAR_A_RECORD[{i}]_ROW_ID_INVALID_OR_DUPLICATE")
        seen_la.add(rid)

    for language in LANGUAGES:
        records = dictionary_records.get(language)
        if records is None:
            raise ValueError(f"DICTIONARY_RECORDS_MISSING_LANGUAGE:{language}")
        seen_ids: set[str] = set()
        for i, row in enumerate(records):
            for field in ("language", "dictionary_row_id", "dictionary_raw_word", "admitted_normalized_dictionary_cluster", "normalization_contract_id"):
                if field not in row:
                    raise ValueError(f"DICTIONARY_RECORD[{language}][{i}]_MISSING:{field}")
            if row["language"] != language:
                raise ValueError(f"DICTIONARY_RECORD[{language}][{i}]_LANGUAGE_MISMATCH")
            if row["normalization_contract_id"] != contract_id:
                raise ValueError(f"DICTIONARY_RECORD[{language}][{i}]_CONTRACT_ID_MISMATCH")
            if not isinstance(row["admitted_normalized_dictionary_cluster"], str):
                raise ValueError(f"DICTIONARY_RECORD[{language}][{i}]_CLUSTER_NOT_STRING")
            rid = row["dictionary_row_id"]
            if not isinstance(rid, str) or not rid or rid in seen_ids:
                raise ValueError(f"DICTIONARY_RECORD[{language}][{i}]_ROW_ID_INVALID_OR_DUPLICATE")
            seen_ids.add(rid)
    return la_records, dictionary_records, contract_id


def raw_match_ledger(la_records: list[dict[str, Any]], dictionary_records: dict[str, list[dict[str, Any]]], contract_id: str) -> list[dict[str, Any]]:
    by_cluster: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in la_records:
        by_cluster[row["admitted_normalized_linear_a_cluster"]].append(row)
    ledger: list[dict[str, Any]] = []
    for language in LANGUAGES:
        for drow in dictionary_records[language]:
            cluster = drow["admitted_normalized_dictionary_cluster"]
            for lrow in by_cluster.get(cluster, []):
                ledger.append({
                    "language": language,
                    "linear_a_row_id": lrow["linear_a_row_id"],
                    "linear_a_source_locator": lrow["source_locator"],
                    "linear_a_raw_comparison_string": lrow["raw_comparison_string"],
                    "linear_a_cluster": lrow["admitted_normalized_linear_a_cluster"],
                    "dictionary_row_id": drow["dictionary_row_id"],
                    "dictionary_raw_word": drow["dictionary_raw_word"],
                    "dictionary_cluster": cluster,
                    "normalization_contract_id": contract_id,
                })
    return ledger


def metrics_for_clusters(la_clusters: list[str], dictionary_clusters: list[str]) -> dict[str, int]:
    la_set = set(la_clusters)
    dict_set = set(dictionary_clusters)
    return {
        "UNIQUE_LINEAR_A_CLUSTER_HIT_COUNT": len(la_set & dict_set),
        "TOTAL_PAIRWISE_EXACT_MATCH_COUNT": sum(1 for a in la_clusters for b in dictionary_clusters if a == b),
        "UNIQUE_DICTIONARY_CLUSTER_HIT_COUNT": len(la_set & dict_set),
    }


def observed_metrics(la_records: list[dict[str, Any]], dictionary_records: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, int]]:
    la = [r["admitted_normalized_linear_a_cluster"] for r in la_records]
    return {
        language: metrics_for_clusters(la, [r["admitted_normalized_dictionary_cluster"] for r in dictionary_records[language]])
        for language in LANGUAGES
    }


def _seed(spec_uuid: str, null_id: str, iteration: int) -> int:
    digest = hashlib.sha256(f"{spec_uuid}|{null_id}|{iteration}".encode("utf-8")).digest()
    return int.from_bytes(digest, "big", signed=False)


def _multiset_permutation_count(values: Iterable[Any]) -> int:
    vals = list(values)
    n = len(vals)
    if n <= 1:
        return 1
    out = math.factorial(n)
    for count in collections.Counter(vals).values():
        out //= math.factorial(count)
    return out


def _unique_permutations(values: Iterable[Any]) -> Iterable[tuple[Any, ...]]:
    counter = collections.Counter(values)
    n = sum(counter.values())
    keys = sorted(counter, key=lambda x: str(x))
    buf: list[Any] = [None] * n
    def rec(pos: int):
        if pos == n:
            yield tuple(buf)
            return
        for key in keys:
            if counter[key] <= 0:
                continue
            counter[key] -= 1
            buf[pos] = key
            yield from rec(pos + 1)
            counter[key] += 1
    yield from rec(0)


def _redistribute(chars: list[str] | tuple[str, ...], lengths: list[int]) -> list[str]:
    out: list[str] = []
    offset = 0
    for length in lengths:
        out.append("".join(chars[offset:offset + length]))
        offset += length
    if offset != len(chars):
        raise AssertionError("REDISTRIBUTION_LENGTH_MISMATCH")
    return out


def _n1_space(dictionary_clusters: dict[str, list[str]]) -> int:
    total = 1
    for language in LANGUAGES:
        chars = list("".join(dictionary_clusters[language]))
        total *= _multiset_permutation_count(chars)
        if total > DEFAULT_ITERATIONS:
            return total
    return total


def n1_distributions(spec_uuid: str, la_clusters: list[str], dictionary_clusters: dict[str, list[str]], iterations: int = DEFAULT_ITERATIONS) -> tuple[dict[str, list[int]], str, int]:
    lengths = {lang: [len(x) for x in dictionary_clusters[lang]] for lang in LANGUAGES}
    chars = {lang: list("".join(dictionary_clusters[lang])) for lang in LANGUAGES}
    space = _n1_space(dictionary_clusters)
    dist = {lang: [] for lang in LANGUAGES}
    if space <= iterations:
        generators = [_unique_permutations(chars[lang]) for lang in LANGUAGES]
        mode = "EXACT_ENUMERATION"
        for joint in itertools.product(*generators):
            for lang, perm in zip(LANGUAGES, joint):
                clusters = _redistribute(perm, lengths[lang])
                dist[lang].append(metrics_for_clusters(la_clusters, clusters)[PRIMARY_METRIC])
    else:
        mode = "DETERMINISTIC_SAMPLED_PERMUTATION"
        for iteration in range(iterations):
            rng = random.Random(_seed(spec_uuid, N1, iteration))
            for lang in LANGUAGES:
                perm = chars[lang].copy()
                rng.shuffle(perm)
                clusters = _redistribute(perm, lengths[lang])
                dist[lang].append(metrics_for_clusters(la_clusters, clusters)[PRIMARY_METRIC])
    B = len(dist[LANGUAGES[0]])
    return dist, mode, B


def _n2_strata(dictionary_clusters: dict[str, list[str]]) -> dict[int, list[tuple[str, str]]]:
    strata: dict[int, list[tuple[str, str]]] = collections.defaultdict(list)
    for language in LANGUAGES:
        for cluster in dictionary_clusters[language]:
            strata[len(cluster)].append((language, cluster))
    return dict(sorted(strata.items()))


def _n2_space(strata: dict[int, list[tuple[str, str]]]) -> int:
    total = 1
    for rows in strata.values():
        total *= _multiset_permutation_count([language for language, _ in rows])
        if total > DEFAULT_ITERATIONS:
            return total
    return total


def n2_distributions(spec_uuid: str, la_clusters: list[str], dictionary_clusters: dict[str, list[str]], iterations: int = DEFAULT_ITERATIONS) -> tuple[dict[str, list[int]], str, int]:
    strata = _n2_strata(dictionary_clusters)
    space = _n2_space(strata)
    dist = {lang: [] for lang in LANGUAGES}

    def score_assignment(assignments: dict[int, tuple[str, ...] | list[str]]) -> None:
        rebuilt = {lang: [] for lang in LANGUAGES}
        for length, rows in strata.items():
            labels = assignments[length]
            for assigned, (_, cluster) in zip(labels, rows):
                rebuilt[assigned].append(cluster)
        for lang in LANGUAGES:
            dist[lang].append(metrics_for_clusters(la_clusters, rebuilt[lang])[PRIMARY_METRIC])

    if space <= iterations:
        mode = "EXACT_ENUMERATION"
        lengths = list(strata)
        generators = [_unique_permutations([language for language, _ in strata[length]]) for length in lengths]
        for joint in itertools.product(*generators):
            score_assignment(dict(zip(lengths, joint)))
    else:
        mode = "DETERMINISTIC_SAMPLED_PERMUTATION"
        for iteration in range(iterations):
            rng = random.Random(_seed(spec_uuid, N2, iteration))
            assignments: dict[int, list[str]] = {}
            for length, rows in strata.items():
                labels = [language for language, _ in rows]
                rng.shuffle(labels)
                assignments[length] = labels
            score_assignment(assignments)
    B = len(dist[LANGUAGES[0]])
    return dist, mode, B


def _tail_p(null_values: list[int], observed: int, mode: str) -> float:
    ge = sum(v >= observed for v in null_values)
    if mode == "EXACT_ENUMERATION":
        return ge / len(null_values) if null_values else 1.0
    return (1 + ge) / (len(null_values) + 1)


def summarize_null(dist: dict[str, list[int]], observed: dict[str, dict[str, int]], mode: str) -> dict[str, Any]:
    max_stats = [max(dist[lang][i] for lang in LANGUAGES) for i in range(len(dist[LANGUAGES[0]]))]
    result: dict[str, Any] = {}
    for lang in LANGUAGES:
        values = dist[lang]
        obs = observed[lang][PRIMARY_METRIC]
        mean = statistics.fmean(values) if values else 0.0
        sd = statistics.pstdev(values) if len(values) > 1 else 0.0
        percentile = sum(v <= obs for v in values) / len(values) if values else 0.0
        result[lang] = {
            "observed": obs,
            "null_mean": mean,
            "null_sd": sd,
            "standardized_excess": (obs - mean) / sd if sd > 0 else None,
            "empirical_percentile": percentile,
            "unadjusted_p": _tail_p(values, obs, mode),
            "FWER_adjusted_p": _tail_p(max_stats, obs, mode),
            "positive_excess": obs > mean,
            "null_distribution_sha256": sha256_json(values),
        }
    return result


def decide(n1: dict[str, Any], n2: dict[str, Any], alpha: float = 0.05) -> tuple[str, list[str]]:
    pass_both: list[str] = []
    pass_one: list[str] = []
    for lang in LANGUAGES:
        a = n1[lang]["positive_excess"] and n1[lang]["FWER_adjusted_p"] <= alpha
        b = n2[lang]["positive_excess"] and n2[lang]["FWER_adjusted_p"] <= alpha
        if a and b:
            pass_both.append(lang)
        elif a or b:
            pass_one.append(lang)
    if pass_both:
        return "EXECUTED_TECHNICAL_OVERLAP_EXCESS_SIGNAL", pass_both
    if pass_one:
        return "EXECUTED_DISCORDANT_NULLS", pass_one
    return "EXECUTED_NO_EXCESS", []


def readiness(data_dir: Path) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    valid: list[dict[str, Any]] = []
    for path in sorted(data_dir.glob("JANUS-LINEAR-A-R3C-3-EXECUTION-INPUT-RECEIPT-*.json")):
        if "CONTRACT" in path.name:
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            errors = validate_receipt_structure(obj)
        except Exception as exc:
            obj = {}
            errors = [f"READ_OR_PARSE_ERROR:{type(exc).__name__}:{exc}"]
        row = {"path": str(path), "status": obj.get("status"), "errors": errors}
        candidates.append(row)
        if not errors:
            valid.append(row)
    status = "READY_FOR_MANUAL_SCIENTIFIC_EXECUTION" if len(valid) == 1 else "BLOCKED_MISSING_PAPER_EXACT_INPUT_RECEIPTS_AND_NORMALIZATION_CONTRACT"
    if len(valid) > 1:
        status = "BLOCKED_MULTIPLE_ADMITTED_EXECUTION_RECEIPTS_REQUIRE_EXPLICIT_SELECTION"
    return {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-3-READINESS-RESULT-2026-08-14-v0.1.2",
        "version": "v0.1.2",
        "node_type": "language_match_audit_readiness_result",
        "status": status,
        "runner_id": RUNNER_ID,
        "scientific_spec": SPEC_PATH,
        "receipt_contract": RECEIPT_CONTRACT_PATH,
        "candidate_receipts": candidates,
        "admitted_receipt_count": len(valid),
        "scientific_execution_performed": False,
        "published_matches_reproduced": False,
        "claim_ceiling": {
            "language_family_relationship_established": False,
            "R3B_effect": "NONE",
            "new_anchor": False,
            "decipherment": False,
        },
        "required_next": "Acquire or lawfully obtain paper-exact study inputs and establish the upstream normalization contract; do not infer missing preprocessing or reverse engineer selected published match tables.",
    }


def self_test() -> dict[str, Any]:
    contract_id = "SYNTHETIC-CONTRACT-v1"
    la = [
        {"linear_a_row_id": "L1", "source_locator": "s1", "raw_comparison_string": "KT", "admitted_normalized_linear_a_cluster": "kt", "normalization_contract_id": contract_id},
        {"linear_a_row_id": "L2", "source_locator": "s2", "raw_comparison_string": "MN", "admitted_normalized_linear_a_cluster": "mn", "normalization_contract_id": contract_id},
        {"linear_a_row_id": "L3", "source_locator": "s3", "raw_comparison_string": "BR", "admitted_normalized_linear_a_cluster": "br", "normalization_contract_id": contract_id},
    ]
    clusters = {
        "Ancient Egyptian": ["kt", "zz"],
        "Luwian": ["mn", "xy"],
        "Hittite": ["br", "qq"],
        "Proto-Celtic": ["kt", "mn"],
        "Uralic": ["xy", "zz"],
    }
    dictionaries = {
        lang: [
            {"language": lang, "dictionary_row_id": f"{lang}-{i}", "dictionary_raw_word": c, "admitted_normalized_dictionary_cluster": c, "normalization_contract_id": contract_id}
            for i, c in enumerate(values)
        ]
        for lang, values in clusters.items()
    }
    ledger = raw_match_ledger(la, dictionaries, contract_id)
    obs = observed_metrics(la, dictionaries)
    assert obs["Ancient Egyptian"][PRIMARY_METRIC] == 1
    assert obs["Proto-Celtic"][PRIMARY_METRIC] == 2
    assert len(ledger) == 5
    la_clusters = [r["admitted_normalized_linear_a_cluster"] for r in la]
    dclusters = {lang: [r["admitted_normalized_dictionary_cluster"] for r in dictionaries[lang]] for lang in LANGUAGES}
    d1a, m1a, b1a = n1_distributions(SPEC_ID, la_clusters, dclusters, iterations=64)
    d1b, m1b, b1b = n1_distributions(SPEC_ID, la_clusters, dclusters, iterations=64)
    assert (d1a, m1a, b1a) == (d1b, m1b, b1b)
    d2a, m2a, b2a = n2_distributions(SPEC_ID, la_clusters, dclusters, iterations=64)
    d2b, m2b, b2b = n2_distributions(SPEC_ID, la_clusters, dclusters, iterations=64)
    assert (d2a, m2a, b2a) == (d2b, m2b, b2b)
    s1 = summarize_null(d1a, obs, m1a)
    s2 = summarize_null(d2a, obs, m2a)
    status, signals = decide(s1, s2)
    assert status in {"EXECUTED_NO_EXCESS", "EXECUTED_DISCORDANT_NULLS", "EXECUTED_TECHNICAL_OVERLAP_EXCESS_SIGNAL"}
    for summary in (s1, s2):
        for lang in LANGUAGES:
            assert 0.0 <= summary[lang]["unadjusted_p"] <= 1.0
            assert 0.0 <= summary[lang]["FWER_adjusted_p"] <= 1.0
            assert summary[lang]["FWER_adjusted_p"] >= summary[lang]["unadjusted_p"] - 1e-15
    bad = {
        "node_type": "r3c_3_execution_input_receipt",
        "status": RECEIPT_STATUS,
        "paper_identity": {"doi": "10.3390/info15020073"},
    }
    bad_errors = validate_receipt_structure(bad)
    assert bad_errors
    return {
        "runner_id": RUNNER_ID,
        "synthetic_raw_match_ledger_count": len(ledger),
        "synthetic_primary_metric_proto_celtic": obs["Proto-Celtic"][PRIMARY_METRIC],
        "N1_deterministic_replay_pass": True,
        "N2_deterministic_replay_pass": True,
        "FWER_not_below_unadjusted_canary_pass": True,
        "invalid_receipt_fail_closed_pass": True,
        "scientific_execution_on_paper_data_performed": False,
        "language_family_relationship_established": False,
        "decipherment": False,
        "synthetic_decision_status": status,
        "synthetic_signal_languages": signals,
    }


def execute(receipt_path: Path, result_path: Path, ledger_path: Path) -> dict[str, Any]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    la_records, dictionary_records, contract_id = load_execution_records(receipt, receipt_path)
    ledger = raw_match_ledger(la_records, dictionary_records, contract_id)
    ledger_path.write_text(json.dumps({"records": ledger}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ledger_sha, ledger_bytes = sha256_file(ledger_path)
    obs = observed_metrics(la_records, dictionary_records)
    la_clusters = [r["admitted_normalized_linear_a_cluster"] for r in la_records]
    dclusters = {
        lang: [r["admitted_normalized_dictionary_cluster"] for r in dictionary_records[lang]]
        for lang in LANGUAGES
    }
    n1_dist, n1_mode, n1_B = n1_distributions(SPEC_ID, la_clusters, dclusters)
    n2_dist, n2_mode, n2_B = n2_distributions(SPEC_ID, la_clusters, dclusters)
    n1_summary = summarize_null(n1_dist, obs, n1_mode)
    n2_summary = summarize_null(n2_dist, obs, n2_mode)
    status, signals = decide(n1_summary, n2_summary)
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-3-CORRECTIVE-LANGUAGE-MATCH-AUDIT-RESULT-2026-08-14-v0.1.2",
        "version": "v0.1.2",
        "node_type": "corrective_language_match_audit_result",
        "status": status,
        "runner_id": RUNNER_ID,
        "scientific_spec": SPEC_PATH,
        "execution_input_receipt": str(receipt_path),
        "normalization_contract_id": contract_id,
        "raw_match_ledger": {"path": str(ledger_path), "sha256": ledger_sha, "bytes": ledger_bytes, "rows": len(ledger)},
        "record_counts": {"Linear_A": len(la_records), **{lang: len(dictionary_records[lang]) for lang in LANGUAGES}},
        "observed_metrics": obs,
        "null_families": {
            N1: {"mode": n1_mode, "iterations_or_exact_states": n1_B, "summary": n1_summary},
            N2: {"mode": n2_mode, "iterations_or_exact_states": n2_B, "summary": n2_summary},
        },
        "technical_signal_languages": signals,
        "secondary_semantic_filtering_used_in_primary_statistic": False,
        "claim_ceiling": {
            "technical_overlap_excess_signal_only": status == "EXECUTED_TECHNICAL_OVERLAP_EXCESS_SIGNAL",
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
    p_ready = sub.add_parser("readiness")
    p_ready.add_argument("--data-dir", default="data")
    p_ready.add_argument("--out")
    p_validate = sub.add_parser("validate-receipt")
    p_validate.add_argument("receipt")
    p_run = sub.add_parser("run")
    p_run.add_argument("--receipt", required=True)
    p_run.add_argument("--result", required=True)
    p_run.add_argument("--ledger", required=True)
    args = ap.parse_args()

    if args.cmd == "self-test":
        print(json.dumps(self_test(), ensure_ascii=False, indent=2, sort_keys=True))
        return
    if args.cmd == "readiness":
        out = readiness(Path(args.data_dir))
        text = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
        print(text, end="")
        return
    if args.cmd == "validate-receipt":
        obj = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
        errors = validate_receipt_structure(obj)
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2, sort_keys=True))
        raise SystemExit(0 if not errors else 1)
    if args.cmd == "run":
        spec = json.loads(Path(SPEC_PATH).read_text(encoding="utf-8"))
        spec_errors = validate_spec(spec)
        if spec_errors:
            raise SystemExit("SPEC_INVALID:" + "|".join(spec_errors))
        result = execute(Path(args.receipt), Path(args.result), Path(args.ledger))
        print(json.dumps({"status": result["status"], "technical_signal_languages": result["technical_signal_languages"]}, ensure_ascii=False, sort_keys=True))
        return


if __name__ == "__main__":
    main()
