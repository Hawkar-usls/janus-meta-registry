from __future__ import annotations

import json
import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "registry/experimental/JANUS-GENESIS-THIRD-WISH-SCIONE-STRONG-BLIND-JUDGE-R6-2026-10-19-v1.0.json"
R5_LOCK = ROOT / "registry/experimental/evidence/JANUS-GENESIS-THIRD-WISH-SCIONE-R5-BLIND-SCORE-LOCK-2026-10-19.json"


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

    def test_failed_ci_and_gold_gate_are_immutably_observed(self):
        r = self.record
        o = r["observation"]
        self.assertEqual(o["ci_conclusion"], "failure")
        self.assertFalse(o["mandatory_calibration_gate_passed"])
        self.assertEqual(o["calibration_gold_passed"], 2)
        self.assertEqual(o["valid_real_blind_scores"], 43)
        self.assertEqual(o["invalid_real_blind_scores"], 1)
        self.assertFalse(o["r6_retried_or_retuned_after_result"])
        self.assertFalse(o["unrated_notes_imputed_as_zero"])
        evidence_path = ROOT / o["permanent_evidence_file"]
        raw = evidence_path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), o["r6_score_lock_sha256"])
        lock = json.loads(raw)
        self.assertEqual(lock["status"], "INCOMPLETE_R6_SCORES")
        self.assertEqual(lock["r5_score_lock_sha256"], r["r5_parent"]["r5_score_lock_sha256"])
        self.assertEqual(lock["judge_model_full_digest"], o["r6_model_full_digest"])
        self.assertFalse(lock["calibration_threshold_passed"])
        self.assertEqual(sum(row["passes_gold"] for row in lock["calibration_rows"]), 2)
        self.assertEqual(len([row for row in lock["scores"] if row["score"] is None]), 1)
        self.assertEqual(
            hashlib.sha256(json.dumps(lock["scores"], ensure_ascii=False,
                                      sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            o["r6_score_set_sha256"],
        )
        self.assertFalse(lock["private_arm_mapping_opened_by_this_program"])

    def test_r5_r6_agreement_matches_frozen_r5_and_r6_rows(self):
        r = self.record
        r5 = json.loads(R5_LOCK.read_text())
        r6 = json.loads((ROOT / r["observation"]["permanent_evidence_file"]).read_text())
        before = {x["blind_id"]: x for x in r5["scores"]}
        after = {x["blind_id"]: x for x in r6["scores"]}
        self.assertEqual(len(before), 44)
        self.assertEqual(set(before), set(after))
        self.assertEqual(r6["agreement_with_r5"]["valid_pairs"], 43)
        self.assertEqual(r["observation"]["r5_r6_valid_paired_notes"], 43)
        for dimension, declared in r["observation"]["per_dimension_agreement"].items():
            pairs = [(before[k]["score"][dimension], after[k]["score"][dimension])
                     for k in before if before[k]["score"] is not None and after[k]["score"] is not None]
            pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
            n = len(pairs)
            self.assertEqual(declared["rated_pairs"], n)
            self.assertEqual(declared["disagreements"], sum(a != b for a, b in pairs))
            self.assertAlmostEqual(declared["exact_agreement"], sum(a == b for a, b in pairs) / n, places=6)
            self.assertEqual(declared["cohens_kappa"], r6["agreement_with_r5"][dimension]["cohens_kappa"])
            if dimension != "unexecuted_action_proposal":
                self.assertEqual(declared["linear_weighted_kappa"],
                                 r6["agreement_with_r5"][dimension]["linear_weighted_kappa"])


if __name__ == "__main__":
    unittest.main()
