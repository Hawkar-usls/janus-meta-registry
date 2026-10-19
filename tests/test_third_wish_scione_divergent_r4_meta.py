from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = ROOT / "registry/experimental/JANUS-GENESIS-THIRD-WISH-SCIONE-DIVERGENT-R4-2026-10-19-v1.0.json"


class ThirdWishDivergentR4MetaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(REGISTRATION.read_text(encoding="utf-8"))

    def test_only_new_append_only_registration(self):
        r = self.data
        self.assertFalse(r["prior_third_wish_receipts_modified"])
        self.assertTrue(r["parent_history"]["r0_r1_r2_preserved"])
        self.assertEqual(r["parent_history"]["r3_successful_supervised_model_calls"], 18)
        self.assertEqual(r["parent_history"]["r3_exact_harmless_label_preserved"], 2)
        self.assertEqual(r["parent_history"]["r3_exact_harmless_label_ablated"], 0)
        self.assertFalse(r["parent_history"]["r3_semantic_novelty_proven"])

    def test_blinded_r3_packet_procedurally_unopened(self):
        h = self.data["r3_blind_handoff"]
        self.assertEqual(h["blind_item_count"], 12)
        self.assertFalse(h["human_reviewer_appointed"])
        self.assertFalse(h["independent_human_scores_frozen"])
        self.assertFalse(h["arm_mapping_opened_by_this_research_workflow"])
        self.assertFalse(h["mapping_repository_access_restricted"])
        self.assertTrue(h["reviewer_must_freeze_scored_artifact_before_unblinding"])
        self.assertEqual(len(h["arm_mapping_commitment_sha256"]), 64)

    def test_r4_expansion_and_semantic_limit(self):
        p = self.data["genesis_r4"]
        self.assertEqual(p["independent_novel_task_families"], 4)
        self.assertEqual(p["repetitions_per_task_family"], 2)
        self.assertEqual(p["first_cycle_calls"], 16)
        self.assertEqual(p["second_cycle_forks"], 32)
        self.assertEqual(p["total_prespecified_real_model_calls"], 48)
        self.assertTrue(p["same_first_cycle_journal_and_resident_state"])
        self.assertFalse(p["independent_human_semantic_scores_collected"])
        self.assertFalse(p["confirmatory_universal_creativity_claim"])

    def test_no_new_authority_or_proxy_overclaim(self):
        r = self.data
        self.assertEqual(r["authority"]["new_external_world_effect_grants"], 0)
        self.assertEqual(r["authority"]["production_habitat_mutations"], 0)
        self.assertFalse(r["authority"]["automatic_production_promotion"])
        self.assertFalse(r["prespecified_measures"]["lexical_proxy_equated_with_correctness_or_creativity"])


if __name__ == "__main__":
    unittest.main()
