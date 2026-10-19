from __future__ import annotations

import json
import unittest
from pathlib import Path


RECORD = Path(__file__).resolve().parents[1] / "registry/experimental/JANUS-GENESIS-THIRD-WISH-SCIONE-STRONG-BLIND-JUDGE-R6-2026-10-19-v1.0.json"


class StrongBlindJudgeR6MetaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text())

    def test_append_only_and_preregistered_frozen_model(self):
        r = self.record
        self.assertFalse(r["prior_third_wish_receipts_modified"])
        self.assertFalse(r["r5_parent"]["r5_scores_rewritten"])
        p = r["genesis_r6"]
        self.assertEqual(p["model"], "gemma3:12b-it-q4_K_M")
        self.assertEqual(p["gold_calibration_controls"], 6)
        self.assertEqual(p["calibration_negative_controls"], 4)
        self.assertEqual(p["calibration_positive_controls"], 2)
        self.assertEqual(p["score_items"], 44)
        self.assertEqual(p["mandatory_calibration_gate"], "ALL_4_NEGATIVES_AND_AT_LEAST_1_POSITIVE")
        for k in ("protocol_sha256", "runner_sha256", "workflow_sha256"):
            self.assertEqual(len(p[k]), 64)

    def test_preserves_r5_and_blind_source_no_map(self):
        r = self.record
        s = r["r6_blind_sources"]
        self.assertEqual(s["r3_note_count"] + s["r4_note_count"], 44)
        self.assertTrue(s["framing_scrub_identical_to_r5"])
        self.assertFalse(s["raw_blind_packet_bytes_modified"])
        self.assertFalse(s["experiment_condition_map_opened"])
        self.assertFalse(s["arm_mapping_used_as_input"])
        self.assertEqual(r["r5_parent"]["r5_score_set_sha256"], "367c5f67d82743051e74c5ec6f196b4b5d86280ca27b65fc8c3774119f033832")

    def test_agreement_not_equated_with_ground_truth_or_effect_authority(self):
        r = self.record
        self.assertFalse(r["predeclared_agreement"]["r5_r6_agreement_proves_correctness"])
        self.assertFalse(r["observation"]["experiment_arm_comparison_performed"])
        self.assertFalse(r["observation"]["arm_mapping_read_by_this_research"])
        self.assertFalse(r["observation"]["human_independent_review_completed"])
        self.assertFalse(r["observation"]["causal_memory_creativity_advantage_proven"])
        self.assertEqual(r["authority"]["new_external_world_effect_grants"], 0)
        self.assertEqual(r["authority"]["production_habitat_mutations"], 0)
        self.assertFalse(r["authority"]["automatic_production_promotion"])


if __name__ == "__main__":
    unittest.main()
