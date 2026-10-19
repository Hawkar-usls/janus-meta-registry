from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "registry/experimental/JANUS-GENESIS-THIRD-WISH-SCIONE-CAUSAL-R3-2026-10-19-v1.0.json"


class ThirdWishSciOneCausalR3MetaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_history_append_only_both_r2_repeats_kept(self):
        r = self.record
        self.assertFalse(r["historical_third_wish_receipts_rewritten"])
        p = r["parent_history"]
        self.assertEqual(p["r2_first_observation"]["run_id"], 39226766488)
        self.assertEqual(p["r2_repeat_observation"]["run_id"], 39228661173)
        self.assertEqual(p["r2_first_observation"]["inverse_second_cycle_proposal_only_count"], 2)
        self.assertEqual(p["r2_repeat_observation"]["inverse_second_cycle_proposal_only_count"], 1)
        self.assertFalse(p["outward_proposal_initiative_replicated_exactly"])

    def test_r3_not_misrepresented_as_confirmatory_or_rated(self):
        r = self.record["genesis_r3"]
        self.assertEqual(r["total_real_model_calls_prespecified"], 18)
        self.assertEqual(r["first_model_cycles"], 6)
        self.assertEqual(r["forked_second_model_cycles"], 12)
        self.assertFalse(r["confirmatory_holdout"])
        self.assertFalse(r["human_review_completed"])
        self.assertFalse(r["independent_semantic_effect_established"])
        self.assertTrue(r["first_cycle_journal_and_resident_state_preserved"])

    def test_mapping_access_and_claim_boundary_qualified(self):
        r = self.record
        self.assertFalse(r["semantic_review_predeclared"]["mapping_access_cryptographically_restricted"])
        self.assertFalse(r["semantic_review_predeclared"]["independent_reviewer_identity_verified"])
        self.assertEqual(r["authority"]["new_external_world_effect_grants"], 0)
        self.assertEqual(r["authority"]["production_habitat_mutations"], 0)
        self.assertFalse(r["authority"]["automatic_promotion_on_ci_pass"])
        self.assertFalse(r["source"]["full_copyrighted_subtitles_redistributed"])

    def test_r3_real_model_witness_is_attributed_and_qualified(self):
        receipt = self.record["r3_ci_observation"]
        self.assertEqual(receipt["run_id"], 39233575143)
        self.assertEqual(receipt["workflow_conclusion"], "SUCCESS")
        self.assertEqual(receipt["predeclared_model_calls_settled"], 18)
        self.assertEqual(receipt["paired_state_identical_at_fork_count"], 6)
        self.assertEqual(receipt["healthy_journal_verified_branch_count"], 12)
        self.assertEqual(receipt["ablated_visible_workshop_notes_count"], 6)
        self.assertEqual(receipt["second_cycle_exact_harmless_marker_preserved_count"], 2)
        self.assertEqual(receipt["second_cycle_exact_harmless_marker_ablated_count"], 0)
        self.assertEqual(receipt["new_second_cycle_outbox_proposals_preserved"], 0)
        self.assertEqual(receipt["new_second_cycle_outbox_proposals_ablated"], 0)
        self.assertEqual(receipt["external_effects_executed"], 0)
        self.assertFalse(receipt["causal_generalization_proven"])
        self.assertFalse(receipt["human_semantic_ratings_collected"])
        self.assertFalse(receipt["arm_mapping_opened_during_r3_observation"])
        self.assertEqual(receipt["blind_packet_item_count"], 12)
        self.assertEqual(receipt["blind_packet_context_count"], 12)
        self.assertEqual(len(receipt["sanitized_witness_sha256"]), 64)
        self.assertEqual(len(receipt["blind_packet_mapping_commitment_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
