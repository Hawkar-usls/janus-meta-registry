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


if __name__ == "__main__":
    unittest.main()
