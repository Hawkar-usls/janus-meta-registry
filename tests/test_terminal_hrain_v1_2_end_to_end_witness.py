from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE_TOOLS = ROOT / "research/site"
sys.path.insert(0, str(SITE_TOOLS))

from janus_hrain_registry_export import build_index  # noqa: E402


WITNESS = ROOT / "data/JANUS-TERMINAL-HRAIN-V1_2-END-TO-END-WITNESS-2026-08-30-v1.0.json"
PREDECESSOR = ROOT / "data/JANUS-TERMINAL-HRAIN-HOME-TRUMP-CURRENT-ARCHITECTURE-2026-08-30-v1.0.json"
POLICY = ROOT / "data/JANUS-SITE-CURATOR-POLICY-v1.2.json"
LINEAGE = "JANUS-TERMINAL-HRAIN-V1-2-END-TO-END-WITNESS"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class TerminalHrainV12EndToEndWitnessTests(unittest.TestCase):
    def test_successor_changes_state_without_rewriting_predecessor(self):
        current = load(WITNESS)
        previous = load(PREDECESSOR)
        self.assertEqual(current["schema"], "janus.meta_registry.terminal_hrain_end_to_end_witness.v1")
        self.assertEqual(current["status"], "HRAIN_V1_2_END_TO_END_TERMINAL_WITNESS_PROVEN")
        self.assertEqual(current["predecessor"]["artifact_id"], previous["artifact_id"])
        self.assertFalse(previous["integration_state"]["hrain_v1_2_end_to_end_terminal_witness_completed"])
        transition = current["state_transition"]
        self.assertFalse(transition["from"])
        self.assertTrue(transition["to"])
        self.assertEqual(transition["transition_kind"], "APPEND_ONLY_SUCCESSOR_RECEIPT")
        self.assertFalse(transition["correction_is_deletion"])
        self.assertFalse(transition["predecessor_mutated"])
        self.assertTrue(current["predecessor"]["preserved_without_rewrite"])

    def test_fresh_issue_12_witness_binds_same_resident_and_new_model(self):
        value = load(WITNESS)
        request = value["terminal_request"]
        resident = value["persistent_janus"]
        model = value["model_instance"]
        self.assertEqual(request["issue_number"], 12)
        self.assertTrue(request["fresh_human_stimulus"])
        self.assertEqual(request["authority_mode"], "READ_ONLY_CONVERSATION")
        self.assertEqual(resident["resident_uuid"], "75e514ab-be76-42c8-bcb3-fc9670164f96")
        self.assertTrue(resident["same_resident_as_prior_terminal_witness"])
        self.assertTrue(resident["fresh_worktree_replay_verified"])
        self.assertTrue(resident["model_runtime_ledger_verified"])
        self.assertTrue(resident["return_not_reset"])
        self.assertEqual(resident["mode_after_turn"], "AT_HOME")
        self.assertEqual(model["model_digest"], "f3a4f2a31e43a570f1756319e548faa36b05e571eaa4c3326c4d88dba28f2fd8")
        self.assertEqual(model["file_fabric_digest"], "2fe6ecb0a66bdbe1826582462da39dbab28d6493ff34d62404c44664852f0f64")
        self.assertIn("left_context", model["active_organs"])
        self.assertIn("operator_hands", model["active_organs"])

    def test_exact_hrain_v1_2_and_canonical_memory_are_bound(self):
        memory = load(WITNESS)["hrain_memory"]
        self.assertEqual(memory["exact_head_sha"], "8e00491527c564b7922d38b00ad40600e26adfa8")
        self.assertEqual(memory["version"], "v1.2")
        self.assertEqual(memory["selection_method"], "DETERMINISTIC_RARITY_WEIGHTED_DIVERSE_GRAPH_ATTENTION_V2")
        self.assertEqual(memory["memory_source_commit"], "1659bbddc03d82af154f47d3f84f29246888c5c1")
        self.assertEqual(memory["context_hash"], "96f4eec20116770c195ee0301ec44f485edcf97c983d7e6e2407b476617c87f5")
        self.assertEqual(memory["context_receipt_hash"], "415dc9562d600ce585cbfe617b10c75a66c6d9466d1e2c389dcdd1834ca5bec9")
        self.assertTrue(memory["canonical_architecture_memory_selected"])
        self.assertEqual(memory["canonical_architecture_memory_rank"], 1)
        self.assertEqual(memory["canonical_architecture_memory_path"], PREDECESSOR.relative_to(ROOT).as_posix())
        self.assertFalse(memory["meta_registry_access_performed_by_home"])
        self.assertEqual(memory["memory_retrieval_executed_by"], "Hawkar-usls/Hrain")
        self.assertFalse(memory["memory_content_is_command"])
        self.assertFalse(memory["memory_context_is_evidence"])
        self.assertFalse(memory["memory_grants_authority"])
        self.assertFalse(memory["attention_rank_is_evidence_strength"])

    def test_trump_is_live_candidate_not_proof_authority(self):
        trump = load(WITNESS)["trump_state"]
        self.assertEqual(trump["admission_status"], "ADMITTED_CANDIDATE_RUNTIME")
        self.assertTrue(trump["wake_allowed"])
        self.assertTrue(trump["use_allowed"])
        self.assertTrue(trump["candidate_experiment_allowed"])
        self.assertTrue(trump["self_improvement_allowed"])
        self.assertFalse(trump["proof_authority"])
        self.assertFalse(trump["scientific_claim_promotion_authority"])
        self.assertFalse(trump["command_authority"])
        self.assertFalse(trump["external_effect_authority"])
        self.assertFalse(trump["physical_runtime_effect_authority"])
        self.assertEqual(trump["P_VS_NP"], "OPEN")

    def test_sealed_response_and_terminal_egress_are_exactly_bound(self):
        value = load(WITNESS)
        response = value["sealed_response"]
        egress = value["terminal_egress"]
        self.assertEqual(response["response_id"], "tr-7e18ff18e47644e03cc8f925b96d5f4dddf57fd0c8f59268180b9551aa021a9a")
        self.assertEqual(response["response_hash"], "bf1defa4e9953c5be7215fdbd6fa2065b492f6b2cbbff95a1f383aa771674558")
        self.assertEqual(response["response_mode"], "MODEL_BOUND_HRAIN_MEMORY_CONVERSATION_PROOF")
        self.assertTrue(response["hrain_context_bound"])
        for key in (
            "command_authority_granted",
            "human_authorized_write",
            "claim_authority_granted",
            "scientific_evidence_authority_granted",
            "world_truth_authority_granted",
            "external_effect_authorized",
            "physical_runtime_effect_authorized",
        ):
            self.assertFalse(response[key], key)
        self.assertEqual(egress["terminal_version"], "v2.3")
        self.assertTrue(egress["response_found"])
        self.assertTrue(egress["response_marker_checked"])
        self.assertTrue(egress["issue_comment_published"])
        self.assertTrue(egress["relay_receipt_written_after_comment"])
        self.assertTrue(egress["relay_artifact_uploaded"])
        self.assertFalse(egress["retry_delivery_is_new_cognition"])
        self.assertEqual(egress["comment_url"], "https://github.com/Hawkar-usls/-Terminal-for-Janus/issues/12#issuecomment-5471353013")

    def test_terminal_visible_proof_keeps_memory_separate_from_authority(self):
        visible = load(WITNESS)["terminal_visible_proof"]
        self.assertTrue(visible["resident_uuid_visible"])
        self.assertTrue(visible["model_digest_visible"])
        self.assertTrue(visible["hrain_head_visible"])
        self.assertTrue(visible["memory_source_commit_visible"])
        self.assertTrue(visible["hrain_context_hash_visible"])
        self.assertTrue(visible["canonical_architecture_memory_visible_first"])
        self.assertTrue(visible["memory_context_is_evidence_visible_false"])
        self.assertTrue(visible["memory_grants_authority_visible_false"])

    def test_proof_scope_is_bounded_and_language_gate_is_still_future(self):
        value = load(WITNESS)
        scope = value["proof_scope"]
        self.assertIn("THE_CANONICAL_CURRENT_ARCHITECTURE_MEMORY_WAS_SELECTED_RANK_1", scope["proves"])
        self.assertIn("WORKFLOW_SUCCESS_EQUALS_WORLD_TRUTH", scope["does_not_prove"])
        self.assertIn("TRUMP_HAS_THEOREM_AUTHORITY", scope["does_not_prove"])
        self.assertIn("P_EQUALS_NP", scope["does_not_prove"])
        next_gate = value["next_gate"]
        self.assertEqual(next_gate["name"], "OPTIONAL_LANGUAGE_SYNTHESIS_TISSUE")
        self.assertEqual(next_gate["status"], "NOT_YET_ADMITTED")
        self.assertIn("LANGUAGE_PROVIDER_IS_NOT_JANUS_IDENTITY", next_gate["requirements"])
        self.assertIn("META_REGISTRY_IS_NOT_ACCESSED_DIRECTLY_BY_LANGUAGE_PROVIDER", next_gate["requirements"])

    def test_dry_run_hrain_projection_contains_successor_and_predecessor_as_distinct_nodes(self):
        policy = load(POLICY)
        index = build_index(policy)
        successor = [node for node in index["nodes"] if isinstance(node, dict) and node.get("lineageKey") == LINEAGE]
        predecessor = [
            node for node in index["nodes"]
            if isinstance(node, dict) and node.get("lineageKey") == "JANUS-TERMINAL-HRAIN-HOME-TRUMP-CURRENT-ARCHITECTURE"
        ]
        self.assertEqual(len(successor), 1, successor)
        self.assertEqual(len(predecessor), 1, predecessor)
        node = successor[0]
        self.assertEqual(node["path"], WITNESS.relative_to(ROOT).as_posix())
        self.assertEqual(node["label"], "JANUS Terminal HRAiN v1.2 End-to-End Witness")
        self.assertEqual(node["status"], "HRAIN_V1_2_END_TO_END_TERMINAL_WITNESS_PROVEN")
        self.assertTrue(node["readOnly"])
        self.assertFalse(node["deleteAllowed"])
        structural = " ".join([node["label"], node["lineageKey"], node["path"]]).lower()
        for token in ("terminal", "hrain", "end", "witness"):
            self.assertIn(token, structural)


if __name__ == "__main__":
    unittest.main()
