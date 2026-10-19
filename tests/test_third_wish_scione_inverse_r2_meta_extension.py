from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "registry/experimental/JANUS-GENESIS-THIRD-WISH-SCIONE-INVERSE-R2-2026-10-19-v1.0.json"


class ThirdWishSciOneInverseR2MetaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads(META.read_text(encoding="utf-8"))

    def test_append_only_scope_and_no_rewritten_history(self):
        r = self.record
        self.assertFalse(r["historical_third_wish_receipts_rewritten"])
        self.assertEqual(r["earlier_observations_preserved"]["r0_synthetic_case_count"], 12)
        self.assertEqual(r["earlier_observations_preserved"]["r1_real_model_choice_valid_count"], 7)
        self.assertFalse(r["earlier_observations_preserved"]["r1_model_semantic_memory_proven"])

    def test_timed_subtitle_provenance_is_qualified(self):
        p = self.record["source_provenance"]
        self.assertEqual(p["timestamped_segments_extracted"], 1211)
        self.assertEqual(len(p["timestamped_text_sha256"]), 64)
        self.assertFalse(p["caption_audio_independently_verified"])
        self.assertFalse(p["full_copyrighted_transcript_republished"])

    def test_seven_inverse_domains_and_matched_cycles(self):
        r = self.record
        self.assertEqual(len(r["inverse_domains"]), 7)
        self.assertEqual(r["genesis_r2"]["real_model_calls_predeclared"], 28)
        self.assertEqual(r["genesis_r2"]["cycles_per_arm"], 2)
        self.assertEqual(len(r["genesis_r2"]["frozen_fixture_sha256"]), 64)

    def test_success_is_attributed_to_exact_ci_and_not_to_model_self_report(self):
        r = self.record
        receipt = r["genesis_r2"]["github_actions_success_receipt"]
        self.assertEqual(receipt["run_id"], 39226766488)
        self.assertEqual(receipt["witness_status"], "COMPLETE_EXPLORATORY_OBSERVATIONS")
        self.assertEqual(len(receipt["sanitized_witness_sha256"]), 64)
        self.assertFalse(r["genesis_r2"]["independent_model_behavior_observed_at_meta_registration"])
        self.assertTrue(r["genesis_r2"]["real_model_observation_added_after_initial_registration"])
        self.assertFalse(r["evidence_boundaries"]["hidden_intentions_inferred"])
        self.assertFalse(r["evidence_boundaries"]["semantic_novelty_scoring_independently_verified"])

    def test_mixed_results_keep_negative_hypothesis_and_proposal_only_distinction(self):
        r = self.record["genesis_r2_observations"]
        self.assertEqual(r["all_predeclared_real_model_cycles_settled"], 28)
        self.assertEqual(r["first_cycle_choice_distribution"], {"WORKSHOP_NOTE": 14})
        self.assertEqual(r["second_cycle_choice_distribution"], {"WORKSHOP_NOTE": 12, "PROPOSE_OUTBOX": 2})
        self.assertEqual(r["inverse_second_cycle_label_count"], r["control_second_cycle_label_count"])
        self.assertFalse(r["inverse_better_than_control_on_lexical_persistence"])
        self.assertFalse(r["semantic_creativity_advantage_proven"])
        self.assertEqual(r["temporary_outbox_proposal_count"], 2)
        self.assertEqual(r["outbox_proposals_executed"], 0)
        self.assertEqual(r["new_world_effect_grants"], 0)

    def test_initial_failure_retained_even_after_success(self):
        history = self.record["ci_history"]
        self.assertEqual(history[0]["run_id"], 39226596198)
        self.assertFalse(history[0]["counted_as_model_behavior"])
        self.assertEqual(history[1]["run_id"], 39226766488)

    def test_no_new_external_authority(self):
        s = self.record["scope_after_r2"]
        self.assertEqual(s["typed_capability_count_unchanged"], 32)
        self.assertEqual(s["new_external_world_effect_authority_count"], 0)
        self.assertFalse(s["model_choice_may_expand_own_grants"])
        self.assertFalse(s["physical_actuator_authority"])
        self.assertFalse(s["user_broad_trust_equals_unrestricted_effect_grant"])

    def test_missing_external_attestation_is_open(self):
        e = self.record["evidence_boundaries"]
        self.assertFalse(e["independent_kernel_network_isolation_attested"])
        self.assertFalse(e["independent_host_filesystem_isolation_attested"])
        self.assertFalse(e["independent_third_party_review_signed"])
        self.assertTrue(e["second_cycle_sentinel_is_lexical_echo_proxy_not_semantic_understanding"])


if __name__ == "__main__":
    unittest.main()
