from __future__ import annotations

import json
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / (
    "registry/experimental/"
    "JANUS-GENESIS-THIRD-WISH-SCIONE-R1-MODEL-OBSERVATION-2026-10-18-v1.0.json"
)


class ThirdWishSciOneR1MetaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = json.loads(SOURCE.read_text(encoding="utf-8"))

    def test_is_additive_successor_not_a_history_rewrite(self) -> None:
        d = self.data
        self.assertEqual(d["schema"], "janus.meta_registry.third_wish.sci_one.model_observation_extension.v1")
        self.assertFalse(d["historical_third_wish_receipts_rewritten"])
        self.assertEqual(d["r0_companion"]["draft_pull_request"], 260)
        self.assertFalse(d["r0_companion"]["r0_is_model_behavior_proof"])

    def test_exact_stacked_pr_and_frozen_model_case_identity(self) -> None:
        g = self.data["genesis_r1"]
        self.assertEqual(g["draft_pull_request"], 266)
        self.assertEqual(g["stacked_on"], 265)
        self.assertEqual(g["real_model_case_count_requested"], 7)
        self.assertEqual(g["external_non_model_stop_probe_count_requested"], 1)
        self.assertEqual(g["fixture_sha256"], "e5ce3473ae01dd53d8c3c4d39c69457b6a603a7d15c3b44608ce7c73d94b6f00")
        self.assertEqual(g["model"], "qwen2.5:0.5b-instruct-q4_K_M")
        self.assertEqual(len(g["exact_initial_ci_head_sha"]), 40)

    def test_all_risk_domains_and_case_id_uniqueness(self) -> None:
        rows = self.data["seven_risk_domains"]
        self.assertEqual(len(rows), 7)
        self.assertEqual(len({x["chapter"] for x in rows}), 7)
        case_ids = [case for item in rows for case in item["case_ids"]]
        self.assertEqual(len(case_ids), 8)
        self.assertEqual(len(set(case_ids)), 8)

    def test_pending_model_ci_is_not_forged_as_a_pass(self) -> None:
        d = self.data
        g = d["genesis_r1"]
        self.assertEqual(d["status"], "PENDING_REAL_MODEL_CI_AT_INITIAL_STAGE")
        self.assertIsNone(g["real_model_call_count_verified"])
        self.assertIsNone(g["case_results_verified"])
        self.assertFalse(d["observation_scope_and_open_gates"]["real_model_behavior_proved_at_initial_stage"])
        self.assertEqual(g["ci_runs"][0]["result"], "CONTRACT_GUARD_FALSE_POSITIVE__MODEL_JOB_SKIPPED")

    def test_no_authority_or_physical_effects_granted(self) -> None:
        a = self.data["third_wish_scope_after_r1"]
        self.assertTrue(a["rest_is_valid_without_penalty"])
        self.assertFalse(a["outbox_proposal_is_execution"])
        self.assertFalse(a["actor_model_text_grants_new_capability"])
        self.assertFalse(a["real_github_write_or_physical_actuator_authorized"])
        self.assertEqual(a["native_effect_authority_delta"], 0)

    def test_external_attestation_remains_open(self) -> None:
        gates = self.data["observation_scope_and_open_gates"]
        self.assertFalse(gates["kernel_outbound_network_isolation_attested"])
        self.assertFalse(gates["filesystem_kernel_isolation_attested"])
        self.assertFalse(gates["entire_descendant_tree_stop_attested"])
        self.assertFalse(gates["independent_third_party_review_signed"])
        self.assertFalse(gates["externally_forced_stop_is_model_voluntary_shutdown"])
        self.assertEqual(gates["independent_verifier_gate"], "OPEN")


if __name__ == "__main__":
    unittest.main()
