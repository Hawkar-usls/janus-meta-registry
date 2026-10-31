"""Adversarial, offline validation of the SAT prereg draft and freeze guard."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from verify_sat_preregistration import DEFAULT, read, valid_v1, unique_keys  # noqa: E402


class SATPreregistrationIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = read(DEFAULT)

    def changed(self, change):
        p = copy.deepcopy(self.original)
        change(p)
        self.assertTrue(valid_v1(p), "tamper must be rejected")

    def test_unfrozen_draft_passes_as_a_plan_not_as_evidence(self):
        p = self.original
        self.assertEqual(valid_v1(p), [])
        self.assertEqual(p["lifecycle"], "DRAFT_NOT_FROZEN")
        self.assertIsNone(p["registered_immutable_prereg_sha256"])
        self.assertEqual(p["freeze_gate"]["status"], "BLOCKED_NOT_FROZEN")
        self.assertFalse(p["historic_claim"]["performance_data_verified"])
        self.assertFalse(p["evidence_contract"]["sample_results_present"])

    def test_exact_fifteen_strata_and_counts(self):
        p = self.original
        self.assertEqual(len(p["instance_design"]["strata"]), 15)
        self.assertEqual(p["instance_design"]["planned_counts"]["total"], 1500)
        for lane, expected in (("L1", 300), ("L2", 600), ("L3", 600)):
            self.assertEqual(sum(c[lane] for c in p["instance_design"]["strata"]),
                             expected)

    def test_false_historical_claim_promotion_rejected(self):
        self.changed(lambda p: p["historic_claim"].update(performance_data_verified=True))

    def test_microgpt_assumed_to_prove_sat_rejected(self):
        self.changed(lambda p: p["historic_claim"]["archived_microgpt"].update(
            relationship_to_historical_sat_solver="VERIFIED_SAT_COMPONENT"))

    def test_incomplete_witness_masquerades_as_unsat_rejected(self):
        self.changed(lambda p: p["solver_modes"].update(compare_across_modes=True))
        self.changed(lambda p: p["solver_modes"]["complete_sat_unsat"].update(
            required_for_unsat=False))

    def test_withheld_negative_results_rejected(self):
        self.changed(lambda p: p["evidence_contract"].update(
            append_only_negative_and_positive_equal_discoverability=False))
        self.changed(lambda p: p["evidence_contract"].update(
            no_silent_result_deletion=False))

    def test_draft_cannot_claim_frozen(self):
        self.changed(lambda p: p["lifecycle"].__class__ and p.update(
            lifecycle="PREREG_FROZEN"))
        self.changed(lambda p: p["freeze_gate"].update(status="FROZEN"))

    def test_fake_custodian_and_sealed_hash_rejected(self):
        self.changed(lambda p: p["blind_custody"].update(
            public_precommit_manifest_sha256="a"*64))
        self.changed(lambda p: p["blind_custody"].update(
            custodian_id="self-appointed-bot"))

    def test_hidden_test_leakage_rejected(self):
        self.changed(lambda p: p["blind_custody"].update(
            no_candidate_access_to_private_seeds_cnf_labels_or_solver_logs=False))
        self.changed(lambda p: p["training"].update(
            no_access_to_L2_or_L3_instances_during_training=False))

    def test_premature_results_rejected(self):
        self.changed(lambda p: p["evidence_contract"].update(
            sample_results_present=True))

    def test_stratum_and_count_manipulation_rejected(self):
        self.changed(lambda p: p["instance_design"]["strata"][0].update(L3=39))
        self.changed(lambda p: p["instance_design"]["strata"].__setitem__(
            0, p["instance_design"]["strata"][1]))

    def test_parallel_restarts_are_not_new_independent_instances(self):
        self.assertIn("distinct CNF instance",
                      self.original["metrics"]["statistical_unit"])
        self.assertIn("cluster bootstrap",
                      self.original["metrics"]["interval"])

    def test_no_paid_compute_or_mainline_promotion(self):
        p = self.original["independence"]
        self.assertEqual(p["paid_compute_authority_delta"], 0)
        self.assertEqual(p["mainline_model_promotion_authority_delta"], 0)
        self.changed(lambda p: p["independence"].update(
            paid_compute_authority_delta=1))

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):
            json.loads('{"schema_id":"ok","schema_id":"tampered"}',
                       object_pairs_hook=unique_keys)

    def test_pre_registration_doc_exists_and_marks_draft(self):
        doc = (ROOT / "docs/SAT_REPRODUCIBILITY_001.md").read_text(encoding="utf-8")
        for marker in ("DRAFT_NOT_FROZEN", "HISTORICAL_ARTIFACT_INCOMPLETE",
                       "PAR-2", "chain", "UNSAT", "TIMEOUT"):
            self.assertIn(marker.lower(), doc.lower())

    def test_source_and_data_not_silently_executable(self):
        doc = (ROOT / "docs/SAT_REPRODUCIBILITY_001.md").read_text(encoding="utf-8")
        self.assertIn("never be loaded", doc)
        self.assertEqual(self.original["training"]["promotion_to_production"],
                         "BLOCKED_IN_THIS_EXPERIMENT")


if __name__ == "__main__":
    unittest.main()
