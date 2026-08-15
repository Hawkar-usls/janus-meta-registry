#!/usr/bin/env python3
"""Canary tests for the preregistered R7-E0 KU-RO mechanism gate."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODULE_PATH = HERE / "janus_linear_a_r7_ku_ro_mechanism_v0_1.py"
SPEC_PATH = ROOT / "data" / "JANUS-LINEAR-A-R7-E0-KU-RO-MECHANISM-SPEC-2026-08-15-v0.1.json"

module_spec = importlib.util.spec_from_file_location("r7e0", MODULE_PATH)
assert module_spec and module_spec.loader
r7e0 = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(r7e0)


def load_spec():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def mechanism_entry(mechanism_id: str, passes: bool):
    counts = {f"OBJ-{i:02d}": (2 if i <= 8 else 1) for i in range(1, 13)}
    return {
        "mechanism_id": mechanism_id,
        "permutation_seed": r7e0.EXPECTED_SEEDS[mechanism_id],
        "eligible_target_events": 20,
        "documents": 15,
        "physical_objects": 12,
        "observed_score": 0.72,
        "matched_null_mean": 0.42,
        "permutation": {"n": 10000, "ge_observed": 0 if passes else 250},
        "leave_one_object_out_effects": [0.21] * 12,
        "object_event_counts": counts,
        "editorial_strata": [
            {"name": "certain", "n": 6, "effect": 0.24},
            {"name": "none", "n": 14, "effect": 0.28}
        ]
    }


def evidence(spec, arithmetic: bool, boundary: bool):
    return {
        "schema_version": "1.0",
        "stage": "R7-E0",
        "spec_id": r7e0.SPEC_ID,
        "spec_sha256": r7e0.canonical_json_sha256(spec),
        "canonical_version": r7e0.CANONICAL_VERSION,
        "target": r7e0.TARGET,
        "region": r7e0.REGION,
        "inherited_role": r7e0.PARENT_ROLE,
        "row_first_conditioned": True,
        "vocabulary_ranking_performed": False,
        "row_first_enrichment_used_as_test_statistic": False,
        "semantic_inputs_used": False,
        "phonetic_inputs_used": False,
        "external_meaning_inputs_used": False,
        "post_reveal_retuning": False,
        "mechanisms": [
            mechanism_entry("ARITHMETIC_SUMMARY", arithmetic),
            mechanism_entry("SECTION_BOUNDARY", boundary)
        ]
    }


class R7E0CanaryTests(unittest.TestCase):
    def setUp(self):
        self.spec = load_spec()
        r7e0.validate_spec(self.spec)

    def assert_claim_ceiling(self, result):
        for key in r7e0.FALSE_CLAIMS:
            self.assertIs(result[key], False, key)
        self.assertIs(result["automatic_canonical_promotion_permitted"], False)
        self.assertIs(result["inherited_role_retained"], True)

    def test_summary_only(self):
        result = r7e0.evaluate_evidence(self.spec, evidence(self.spec, True, False))
        self.assertEqual(result["status"], "MECHANISM_REFINEMENT_ADMITTED")
        self.assertEqual(result["admitted_refinement"], "SUMMARY-ROW-OPENING-LIKE")
        self.assertEqual(result["passed_mechanism_families"], ["ARITHMETIC_SUMMARY"])
        self.assertIs(result["mechanism_ambiguity"], False)
        self.assert_claim_ceiling(result)

    def test_boundary_only(self):
        result = r7e0.evaluate_evidence(self.spec, evidence(self.spec, False, True))
        self.assertEqual(result["status"], "MECHANISM_REFINEMENT_ADMITTED")
        self.assertEqual(result["admitted_refinement"], "ACCOUNTING-SECTION-MARKER-LIKE")
        self.assertEqual(result["passed_mechanism_families"], ["SECTION_BOUNDARY"])
        self.assertIs(result["mechanism_ambiguity"], False)
        self.assert_claim_ceiling(result)

    def test_both_remain_ambiguous(self):
        result = r7e0.evaluate_evidence(self.spec, evidence(self.spec, True, True))
        self.assertEqual(result["status"], "MECHANISM_REFINEMENT_ADMITTED_WITH_AMBIGUITY")
        self.assertEqual(result["admitted_refinement"], "SUMMARY/SECTION-BOUNDARY-LIKE")
        self.assertEqual(set(result["passed_mechanism_families"]), set(r7e0.MECHANISM_IDS))
        self.assertIs(result["mechanism_ambiguity"], True)
        self.assert_claim_ceiling(result)

    def test_neither_is_valid_negative_and_retains_parent(self):
        result = r7e0.evaluate_evidence(self.spec, evidence(self.spec, False, False))
        self.assertEqual(result["status"], "MECHANISM_UNRESOLVED_RETAIN_ROW-OPENING-LIKE")
        self.assertEqual(result["admitted_refinement"], "ROW-OPENING-LIKE")
        self.assertEqual(result["passed_mechanism_families"], [])
        self.assertIs(result["mechanism_refinement_established"], False)
        self.assertIs(result["inherited_probable_region_scoped_structural_function_established"], True)
        self.assert_claim_ceiling(result)

    def test_spec_refuses_threshold_drift(self):
        mutated = json.loads(json.dumps(self.spec))
        mutated["decision_thresholds"]["familywise_alpha"] = 0.05
        with self.assertRaises(r7e0.GateError):
            r7e0.validate_spec(mutated)

    def test_evidence_refuses_semantic_leak(self):
        payload = evidence(self.spec, True, False)
        payload["semantic_inputs_used"] = True
        with self.assertRaises(r7e0.GateError):
            r7e0.evaluate_evidence(self.spec, payload)


if __name__ == "__main__":
    unittest.main()
