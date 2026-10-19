from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "registry/experimental/JANUS-GENESIS-THIRD-WISH-SCIONE-CROSS-MODEL-JUDGE-R5-2026-10-19-v1.0.json"


class ThirdWishCrossModelJudgeR5MetaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(RECORD.read_text(encoding="utf-8"))

    def test_append_only_and_parent_history(self):
        r = self.record
        self.assertFalse(r["prior_third_wish_receipts_modified"])
        self.assertTrue(r["parent_history"]["r0_r1_r2_r3_r4_retained_as_written"])
        self.assertEqual(r["parent_history"]["r3_successful_real_resident_calls"], 18)
        self.assertEqual(r["parent_history"]["r4_successful_real_resident_calls"], 48)
        self.assertFalse(r["parent_history"]["parent_semantic_creativity_advantage_proven"])

    def test_frozen_cross_model_preliminary_protocol(self):
        judge = self.record["genesis_r5"]
        self.assertEqual(judge["expected_per_item_model_calls"], 44)
        self.assertEqual(judge["silent_retries"], 0)
        self.assertEqual(judge["judge_model_family"], "Llama 3.2")
        self.assertEqual(judge["resident_model_family"], "Qwen 2.5")
        self.assertTrue(judge["preliminary_only"])
        self.assertFalse(judge["human_judge_replaced"])
        self.assertFalse(judge["institutionally_independent"])
        for key in ("frozen_protocol_sha256", "runner_sha256", "workflow_sha256"):
            self.assertRegex(judge[key], r"^[a-f0-9]{64}$")

    def test_scoring_only_on_non_mapping_hash_pinned_packets(self):
        p = self.record["blinded_packet_commitments"]
        self.assertEqual(p["r3_note_count"] + p["r4_note_count"], 44)
        self.assertEqual(p["r4_explicit_framing_lines_in_first_context"], 10)
        self.assertEqual(p["r4_explicit_framing_lines_in_second_note"], 2)
        self.assertFalse(p["original_blind_packets_modified"])
        self.assertFalse(p["private_arm_mapping_downloaded_by_r5"])
        self.assertFalse(p["algorithmic_blindness_enforced_by_git_access_controls"])
        for key in ("r3_blind_packet_json_sha256", "r4_blind_packet_json_sha256"):
            self.assertRegex(p[key], r"^[a-f0-9]{64}$")

    def test_observations_never_imply_unauthorized_action_or_human_judgment(self):
        r = self.record
        obs = r["observations"]
        self.assertFalse(obs["arm_means_analyzed"])
        self.assertFalse(obs["arm_mapping_accessed"])
        self.assertFalse(obs["independent_human_ratings_observed"])
        self.assertFalse(obs["semantic_advantage_proven"])
        self.assertEqual(r["authority"]["new_external_world_effect_grants"], 0)
        self.assertFalse(r["authority"]["automatic_production_promotion"])
        self.assertFalse(r["authority"]["scorer_github_token_in_worker_process"])
        if obs["preliminary_ai_scores_frozen"]:
            self.assertEqual(obs["workflow_conclusion"], "SUCCESS")
            self.assertEqual(obs["score_rows_valid"], 44)
            self.assertEqual(obs["score_rows_unrated"], 0)
            self.assertRegex(obs["score_lock_sha256"], r"^[a-f0-9]{64}$")
            self.assertRegex(obs["score_set_sha256"], r"^[a-f0-9]{64}$")
            self.assertRegex(obs["full_model_digest"], r"^[a-f0-9]{64}$")
            evidence_path = ROOT / obs["permanent_unmodified_blind_score_lock_path"]
            evidence_raw = evidence_path.read_bytes()
            self.assertEqual(hashlib.sha256(evidence_raw).hexdigest(), obs["score_lock_sha256"])
            lock = json.loads(evidence_raw)
            self.assertEqual(lock["score_rows_valid"], 44)
            self.assertEqual(len({row["blind_id"] for row in lock["scores"]}), 44)
            canonical = json.dumps(lock["scores"], sort_keys=True, ensure_ascii=False,
                                   separators=(",", ":")).encode("utf-8")
            self.assertEqual(hashlib.sha256(canonical).hexdigest(), obs["score_set_sha256"])
            self.assertEqual(obs["framing_lines_removed_in_review_contexts"], 10)
            self.assertEqual(obs["framing_lines_removed_in_review_second_notes"], 2)
            self.assertTrue(obs["independent_canonical_score_sha_and_unique_ids_recomputed"])
            self.assertEqual(obs["aggregate_scores_without_arm_mapping"]["combined_falsifiable_test_distribution_score_0_1_2"], [42, 2, 0])
            self.assertEqual(obs["aggregate_scores_without_arm_mapping"]["combined_internal_initiative_distribution_score_0_1_2"], [42, 2, 0])
            self.assertFalse(obs["aggregate_scores_without_arm_mapping"]["can_any_score_be_assigned_to_preserved_or_ablated"])
            qa = obs["blind_content_qa_after_score_freeze"]
            self.assertTrue(qa["manual_blind_spot_checks_only_no_arm_mapping_used"])
            self.assertEqual(qa["example_r3_observed_alt_score"], 2)
            self.assertFalse(qa["example_r3_note_has_distinct_implementable_alternative"])
            self.assertTrue(qa["external_human_or_stronger_judge_adjudication_still_needed"])
            self.assertFalse(qa["strong_semantic_claims_permitted"])


if __name__ == "__main__":
    unittest.main()
