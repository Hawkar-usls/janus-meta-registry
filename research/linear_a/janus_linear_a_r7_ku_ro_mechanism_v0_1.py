#!/usr/bin/env python3
"""R7-E0 frozen-target mechanism falsification gate for KU-RO in HT.

This module deliberately does not discover or rank words.  It validates the frozen
R7-E0 preregistration and, when supplied with an evidence JSON, evaluates exactly
two predeclared mechanism families for the already-admitted parent claim
KU-RO -> ROW-OPENING-LIKE in HT.

A mechanism failure is a scientific negative result, not an infrastructure error:
it retains the parent C3 role and reports MECHANISM_UNRESOLVED.  No outcome from
this module establishes translation, exact lexical meaning, phonetics, language
family, decipherment, cross-region universality, or external replication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

SPEC_ID = "JANUS-LINEAR-A-R7-E0-KU-RO-MECHANISM-2026-08-15-v0.1"
CANONICAL_VERSION = "v2.30"
BASELINE_COMMIT = "e93e5ee00ae815739965c6ded7f0e3f16a0cc871"
TARGET = "KU-RO"
REGION = "HT"
PARENT_ROLE = "ROW-OPENING-LIKE"
PARENT_STATUS = "REGION_SCOPED_PROBABLE_STRUCTURAL_FUNCTION_ADMITTED"
MECHANISM_IDS = ("ARITHMETIC_SUMMARY", "SECTION_BOUNDARY")
EXPECTED_SEEDS = {"ARITHMETIC_SUMMARY": 71001, "SECTION_BOUNDARY": 71002}
EXPECTED_REFINEMENTS = {
    "ARITHMETIC_SUMMARY": "SUMMARY-ROW-OPENING-LIKE",
    "SECTION_BOUNDARY": "ACCOUNTING-SECTION-MARKER-LIKE",
}
EXPECTED_THRESHOLDS = {
    "minimum_eligible_target_events": 20,
    "minimum_documents": 15,
    "minimum_physical_objects": 12,
    "permutations_per_mechanism": 10000,
    "familywise_alpha": 0.01,
    "multiple_testing": "HOLM_2_FAMILY",
    "minimum_effect_lift_over_matched_null": 0.20,
    "minimum_leave_one_object_out_positive_fraction": 0.90,
    "maximum_single_object_support_fraction": 0.15,
    "editorial_stratum_minimum_n_for_directional_check": 5,
    "editorial_stratum_required_minimum_effect": 0.0,
}
FALSE_CLAIMS = (
    "exact_word_meaning_established",
    "translation_established",
    "phonetic_value_established",
    "language_family_established",
    "new_anchor_established",
    "decipherment_established",
    "universal_cross_region_function_established",
    "external_replication_established",
)


class GateError(ValueError):
    """Raised for malformed or contract-violating preregistration/evidence."""


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise GateError(f"{path}: top level must be a JSON object")
    return value


def canonical_json_sha256(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def _exact(mapping: Mapping[str, Any], key: str, expected: Any, prefix: str) -> None:
    _require(key in mapping, f"{prefix}.{key}: missing")
    _require(mapping[key] == expected, f"{prefix}.{key}: expected {expected!r}, got {mapping[key]!r}")


def validate_spec(spec: Mapping[str, Any]) -> Dict[str, Any]:
    _exact(spec, "spec_id", SPEC_ID, "spec")
    _exact(spec, "stage", "R7-E0", "spec")
    _exact(spec, "status", "PREREGISTERED_BEFORE_MECHANISM_EVIDENCE", "spec")

    parent = spec.get("frozen_parent")
    _require(isinstance(parent, Mapping), "spec.frozen_parent: object required")
    _exact(parent, "canonical_version", CANONICAL_VERSION, "spec.frozen_parent")
    _exact(parent, "baseline_commit_sha", BASELINE_COMMIT, "spec.frozen_parent")
    _exact(parent, "target", TARGET, "spec.frozen_parent")
    _exact(parent, "region", REGION, "spec.frozen_parent")
    _exact(parent, "inherited_admitted_role", PARENT_ROLE, "spec.frozen_parent")
    _exact(parent, "inherited_admission_status", PARENT_STATUS, "spec.frozen_parent")

    anti = spec.get("anti_reselection_contract")
    _require(isinstance(anti, Mapping), "spec.anti_reselection_contract: object required")
    for key in (
        "target_is_frozen_before_e0_scoring",
        "region_is_frozen_before_e0_scoring",
        "parent_role_is_frozen_before_e0_scoring",
        "condition_only_on_already_row_first_eligible_contexts",
        "do_not_rank_vocabulary",
        "do_not_use_row_first_enrichment_as_e0_test_statistic",
        "do_not_retune_thresholds_after_e0_evidence",
        "failure_does_not_revoke_parent_c3_admission",
    ):
        _exact(anti, key, True, "spec.anti_reselection_contract")

    forbidden = spec.get("forbidden_inputs")
    _require(isinstance(forbidden, Mapping), "spec.forbidden_inputs: object required")
    for key in (
        "translation",
        "lexical_semantics",
        "phonetic_value",
        "language_family",
        "external_proposed_meanings",
        "post_score_candidate_selection",
    ):
        _exact(forbidden, key, True, "spec.forbidden_inputs")

    mechanisms = spec.get("mechanism_families")
    _require(isinstance(mechanisms, list) and len(mechanisms) == 2, "spec.mechanism_families: exactly two required")
    by_id = {entry.get("mechanism_id"): entry for entry in mechanisms if isinstance(entry, Mapping)}
    _require(set(by_id) == set(MECHANISM_IDS), f"spec.mechanism_families: ids must be {MECHANISM_IDS}")
    for mechanism_id in MECHANISM_IDS:
        entry = by_id[mechanism_id]
        _exact(entry, "candidate_refinement", EXPECTED_REFINEMENTS[mechanism_id], f"mechanism.{mechanism_id}")
        _exact(entry, "permutation_seed", EXPECTED_SEEDS[mechanism_id], f"mechanism.{mechanism_id}")
        null_contract = entry.get("null_contract")
        _require(isinstance(null_contract, list) and len(null_contract) >= 4, f"mechanism.{mechanism_id}.null_contract: >=4 clauses required")

    thresholds = spec.get("decision_thresholds")
    _require(isinstance(thresholds, Mapping), "spec.decision_thresholds: object required")
    for key, expected in EXPECTED_THRESHOLDS.items():
        _exact(thresholds, key, expected, "spec.decision_thresholds")

    ceiling = spec.get("claim_ceiling")
    _require(isinstance(ceiling, Mapping), "spec.claim_ceiling: object required")
    _exact(ceiling, "mechanism_refinement_may_be_established", True, "spec.claim_ceiling")
    for key in FALSE_CLAIMS:
        _exact(ceiling, key, False, "spec.claim_ceiling")

    promotion = spec.get("promotion_policy")
    _require(isinstance(promotion, Mapping), "spec.promotion_policy: object required")
    for key in (
        "e0_pass_does_not_automatically_promote_canonical_state",
        "separate_result_freeze_required",
        "separate_canonical_promotion_gate_required",
        "untouched_external_replication_remains_required_for_external_replication_claim",
    ):
        _exact(promotion, key, True, "spec.promotion_policy")

    return {
        "stage": "R7-E0",
        "status": "R7_E0_PREREGISTRATION_VALIDATED",
        "spec_id": SPEC_ID,
        "spec_sha256": canonical_json_sha256(spec),
        "canonical_version": CANONICAL_VERSION,
        "target": TARGET,
        "region": REGION,
        "inherited_role": PARENT_ROLE,
        "mechanism_families": list(MECHANISM_IDS),
        "mechanism_result_established": False,
        **{key: False for key in FALSE_CLAIMS},
    }


def empirical_p(ge_observed: int, n: int) -> float:
    _require(isinstance(ge_observed, int) and ge_observed >= 0, "permutation.ge_observed must be a nonnegative integer")
    _require(isinstance(n, int) and n > 0, "permutation.n must be a positive integer")
    _require(ge_observed <= n, "permutation.ge_observed cannot exceed permutation.n")
    return (1.0 + ge_observed) / (1.0 + n)


def holm_adjust_two(p_by_id: Mapping[str, float]) -> Dict[str, float]:
    _require(set(p_by_id) == set(MECHANISM_IDS), "Holm family must contain exactly the two preregistered mechanisms")
    ordered = sorted(p_by_id.items(), key=lambda item: (item[1], item[0]))
    (id1, p1), (id2, p2) = ordered
    adj1 = min(1.0, 2.0 * p1)
    adj2 = min(1.0, max(adj1, p2))
    return {id1: adj1, id2: adj2}


def _number(value: Any, path: str) -> float:
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{path}: number required")
    result = float(value)
    _require(math.isfinite(result), f"{path}: finite number required")
    return result


def _validate_evidence_provenance(evidence: Mapping[str, Any], spec_sha256: str) -> None:
    _exact(evidence, "schema_version", "1.0", "evidence")
    _exact(evidence, "stage", "R7-E0", "evidence")
    _exact(evidence, "spec_id", SPEC_ID, "evidence")
    _exact(evidence, "spec_sha256", spec_sha256, "evidence")
    _exact(evidence, "canonical_version", CANONICAL_VERSION, "evidence")
    _exact(evidence, "target", TARGET, "evidence")
    _exact(evidence, "region", REGION, "evidence")
    _exact(evidence, "inherited_role", PARENT_ROLE, "evidence")
    _exact(evidence, "row_first_conditioned", True, "evidence")
    _exact(evidence, "vocabulary_ranking_performed", False, "evidence")
    _exact(evidence, "row_first_enrichment_used_as_test_statistic", False, "evidence")
    _exact(evidence, "semantic_inputs_used", False, "evidence")
    _exact(evidence, "phonetic_inputs_used", False, "evidence")
    _exact(evidence, "external_meaning_inputs_used", False, "evidence")
    _exact(evidence, "post_reveal_retuning", False, "evidence")


def _evaluate_pre_holm(entry: Mapping[str, Any], mechanism_id: str) -> Dict[str, Any]:
    _exact(entry, "mechanism_id", mechanism_id, f"evidence.{mechanism_id}")
    _exact(entry, "permutation_seed", EXPECTED_SEEDS[mechanism_id], f"evidence.{mechanism_id}")

    eligible = entry.get("eligible_target_events")
    documents = entry.get("documents")
    physical_objects = entry.get("physical_objects")
    for value, name in ((eligible, "eligible_target_events"), (documents, "documents"), (physical_objects, "physical_objects")):
        _require(isinstance(value, int) and value >= 0, f"evidence.{mechanism_id}.{name}: nonnegative integer required")

    observed = _number(entry.get("observed_score"), f"evidence.{mechanism_id}.observed_score")
    null_mean = _number(entry.get("matched_null_mean"), f"evidence.{mechanism_id}.matched_null_mean")
    effect = observed - null_mean

    permutation = entry.get("permutation")
    _require(isinstance(permutation, Mapping), f"evidence.{mechanism_id}.permutation: object required")
    n_perm = permutation.get("n")
    ge_observed = permutation.get("ge_observed")
    raw_p = empirical_p(ge_observed, n_perm)

    loo = entry.get("leave_one_object_out_effects")
    _require(isinstance(loo, list) and loo, f"evidence.{mechanism_id}.leave_one_object_out_effects: nonempty list required")
    loo_values = [_number(value, f"evidence.{mechanism_id}.leave_one_object_out_effects") for value in loo]
    positive_fraction = sum(value > 0.0 for value in loo_values) / len(loo_values)

    object_counts = entry.get("object_event_counts")
    _require(isinstance(object_counts, Mapping) and object_counts, f"evidence.{mechanism_id}.object_event_counts: object required")
    counts: List[int] = []
    for object_id, count in object_counts.items():
        _require(isinstance(object_id, str) and object_id, f"evidence.{mechanism_id}.object_event_counts: nonempty object ids required")
        _require(isinstance(count, int) and count > 0, f"evidence.{mechanism_id}.object_event_counts.{object_id}: positive integer required")
        counts.append(count)
    _require(sum(counts) == eligible, f"evidence.{mechanism_id}.object_event_counts must sum to eligible_target_events")
    _require(len(counts) == physical_objects, f"evidence.{mechanism_id}.object_event_counts count must equal physical_objects")
    max_object_fraction = max(counts) / eligible if eligible else 1.0

    strata = entry.get("editorial_strata")
    _require(isinstance(strata, list), f"evidence.{mechanism_id}.editorial_strata: list required")
    directional_failures: List[str] = []
    checked_strata: List[str] = []
    min_stratum_n = EXPECTED_THRESHOLDS["editorial_stratum_minimum_n_for_directional_check"]
    min_stratum_effect = EXPECTED_THRESHOLDS["editorial_stratum_required_minimum_effect"]
    for index, stratum in enumerate(strata):
        _require(isinstance(stratum, Mapping), f"evidence.{mechanism_id}.editorial_strata[{index}]: object required")
        name = stratum.get("name")
        n = stratum.get("n")
        _require(isinstance(name, str) and name, f"evidence.{mechanism_id}.editorial_strata[{index}].name required")
        _require(isinstance(n, int) and n >= 0, f"evidence.{mechanism_id}.editorial_strata[{index}].n invalid")
        stratum_effect = _number(stratum.get("effect"), f"evidence.{mechanism_id}.editorial_strata[{index}].effect")
        if n >= min_stratum_n:
            checked_strata.append(name)
            if stratum_effect < min_stratum_effect:
                directional_failures.append(name)

    support_pass = (
        eligible >= EXPECTED_THRESHOLDS["minimum_eligible_target_events"]
        and documents >= EXPECTED_THRESHOLDS["minimum_documents"]
        and physical_objects >= EXPECTED_THRESHOLDS["minimum_physical_objects"]
        and n_perm == EXPECTED_THRESHOLDS["permutations_per_mechanism"]
    )
    effect_pass = effect >= EXPECTED_THRESHOLDS["minimum_effect_lift_over_matched_null"]
    loo_pass = positive_fraction >= EXPECTED_THRESHOLDS["minimum_leave_one_object_out_positive_fraction"]
    concentration_pass = max_object_fraction <= EXPECTED_THRESHOLDS["maximum_single_object_support_fraction"]
    editorial_pass = not directional_failures

    return {
        "mechanism_id": mechanism_id,
        "candidate_refinement": EXPECTED_REFINEMENTS[mechanism_id],
        "eligible_target_events": eligible,
        "documents": documents,
        "physical_objects": physical_objects,
        "observed_score": observed,
        "matched_null_mean": null_mean,
        "effect_lift": effect,
        "permutation_n": n_perm,
        "permutation_ge_observed": ge_observed,
        "raw_empirical_p": raw_p,
        "leave_one_object_out_positive_fraction": positive_fraction,
        "maximum_single_object_support_fraction": max_object_fraction,
        "editorial_strata_checked": checked_strata,
        "editorial_directional_failures": directional_failures,
        "support_pass": support_pass,
        "effect_pass": effect_pass,
        "loo_pass": loo_pass,
        "object_concentration_pass": concentration_pass,
        "editorial_robustness_pass": editorial_pass,
    }


def evaluate_evidence(spec: Mapping[str, Any], evidence: Mapping[str, Any]) -> Dict[str, Any]:
    spec_validation = validate_spec(spec)
    spec_sha256 = spec_validation["spec_sha256"]
    _validate_evidence_provenance(evidence, spec_sha256)

    entries = evidence.get("mechanisms")
    _require(isinstance(entries, list) and len(entries) == 2, "evidence.mechanisms: exactly two entries required")
    by_id = {entry.get("mechanism_id"): entry for entry in entries if isinstance(entry, Mapping)}
    _require(set(by_id) == set(MECHANISM_IDS), f"evidence.mechanisms: ids must be {MECHANISM_IDS}")

    evaluated = {mechanism_id: _evaluate_pre_holm(by_id[mechanism_id], mechanism_id) for mechanism_id in MECHANISM_IDS}
    adjusted = holm_adjust_two({mechanism_id: result["raw_empirical_p"] for mechanism_id, result in evaluated.items()})
    alpha = EXPECTED_THRESHOLDS["familywise_alpha"]

    passed: List[str] = []
    for mechanism_id in MECHANISM_IDS:
        result = evaluated[mechanism_id]
        result["holm_adjusted_p"] = adjusted[mechanism_id]
        result["holm_pass"] = adjusted[mechanism_id] <= alpha
        result["mechanism_pass"] = all(
            result[key]
            for key in (
                "support_pass",
                "effect_pass",
                "loo_pass",
                "object_concentration_pass",
                "editorial_robustness_pass",
                "holm_pass",
            )
        )
        if result["mechanism_pass"]:
            passed.append(mechanism_id)

    pass_set = set(passed)
    if pass_set == {"ARITHMETIC_SUMMARY"}:
        status = "MECHANISM_REFINEMENT_ADMITTED"
        refinement = "SUMMARY-ROW-OPENING-LIKE"
        ambiguity = False
    elif pass_set == {"SECTION_BOUNDARY"}:
        status = "MECHANISM_REFINEMENT_ADMITTED"
        refinement = "ACCOUNTING-SECTION-MARKER-LIKE"
        ambiguity = False
    elif pass_set == set(MECHANISM_IDS):
        status = "MECHANISM_REFINEMENT_ADMITTED_WITH_AMBIGUITY"
        refinement = "SUMMARY/SECTION-BOUNDARY-LIKE"
        ambiguity = True
    else:
        status = "MECHANISM_UNRESOLVED_RETAIN_ROW-OPENING-LIKE"
        refinement = PARENT_ROLE
        ambiguity = False

    return {
        "stage": "R7-E0",
        "status": status,
        "spec_id": SPEC_ID,
        "spec_sha256": spec_sha256,
        "evidence_sha256": canonical_json_sha256(evidence),
        "canonical_version": CANONICAL_VERSION,
        "target": TARGET,
        "region": REGION,
        "inherited_admission_status": PARENT_STATUS,
        "inherited_probable_region_scoped_structural_function_established": True,
        "inherited_role_retained": True,
        "inherited_role": PARENT_ROLE,
        "mechanism_refinement_established": bool(passed),
        "admitted_refinement": refinement,
        "mechanism_ambiguity": ambiguity,
        "passed_mechanism_families": passed,
        "mechanisms": [evaluated[mechanism_id] for mechanism_id in MECHANISM_IDS],
        "automatic_canonical_promotion_permitted": False,
        **{key: False for key in FALSE_CLAIMS},
    }


def emit(value: Mapping[str, Any], output: Path | None) -> None:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output is None:
        sys.stdout.write(rendered)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path, help="Frozen R7-E0 preregistration JSON")
    parser.add_argument("--validate-spec", action="store_true", help="Validate preregistration only; make no mechanism claim")
    parser.add_argument("--evidence", type=Path, help="Frozen R7-E0 mechanism evidence JSON")
    parser.add_argument("--output", type=Path, help="Optional machine-readable result output path")
    parser.add_argument("--require-mechanism-pass", action="store_true", help="Return exit 1 when valid evidence resolves no mechanism")
    args = parser.parse_args(argv)
    _require(args.validate_spec ^ bool(args.evidence), "choose exactly one of --validate-spec or --evidence")
    _require(not args.require_mechanism_pass or args.evidence, "--require-mechanism-pass requires --evidence")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        spec = load_json(args.spec)
        if args.validate_spec:
            result = validate_spec(spec)
        else:
            evidence = load_json(args.evidence)
            result = evaluate_evidence(spec, evidence)
        emit(result, args.output)
        if args.require_mechanism_pass and not result["mechanism_refinement_established"]:
            return 1
        return 0
    except (GateError, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"R7-E0 GATE ERROR: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
