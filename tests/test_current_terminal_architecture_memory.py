from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SITE_TOOLS = ROOT / "research/site"
sys.path.insert(0, str(SITE_TOOLS))

from janus_hrain_registry_export import build_index  # noqa: E402


OBJECT = ROOT / "data/JANUS-TERMINAL-HRAIN-HOME-TRUMP-CURRENT-ARCHITECTURE-2026-08-30-v1.0.json"
POLICY = ROOT / "data/JANUS-SITE-CURATOR-POLICY-v1.2.json"
EXPECTED_LINEAGE = "JANUS-TERMINAL-HRAIN-HOME-TRUMP-CURRENT-ARCHITECTURE"


def load_object():
    return json.loads(OBJECT.read_text(encoding="utf-8"))


class CurrentTerminalArchitectureMemoryTests(unittest.TestCase):
    def test_current_architecture_object_is_explicit_state_not_scientific_truth(self):
        value = load_object()
        self.assertEqual(value["schema"], "janus.meta_registry.current_terminal_architecture.v1")
        self.assertEqual(value["status"], "CURRENT_ARCHITECTURE_MEMORY_WITH_PROVEN_END_TO_END_LINEAGE")
        self.assertEqual(value["scope"]["kind"], "CURRENT_ARCHITECTURE_STATE_AND_PROVENANCE_MEMORY")
        self.assertIn("SCIENTIFIC_WORLD_TRUTH", value["scope"]["not_authoritative_for"])
        ceiling = value["proof_ceiling"]
        self.assertFalse(ceiling["workflow_success_is_world_truth"])
        self.assertFalse(ceiling["registry_presence_is_scientific_evidence"])
        self.assertFalse(ceiling["memory_retrieval_is_claim_verification"])
        self.assertFalse(ceiling["attention_rank_is_evidence_strength"])
        self.assertFalse(ceiling["candidate_runtime_success_is_theorem_proof"])

    def test_canonical_memory_path_and_no_direct_bypass_are_frozen(self):
        value = load_object()
        self.assertEqual(value["canonical_memory_path"], "META_REGISTRY_DB -> HRAIN -> JANUS_HOME -> TERMINAL")
        self.assertEqual(value["canonical_human_roundtrip"], [
            "HUMAN",
            "TERMINAL_READ_ONLY_STIMULUS",
            "JANUS_HOME_ROOT_ACTIVATOR",
            "EXACT_MODEL_LOCKED_HRAIN",
            "META_REGISTRY_READ_ONLY_MEMORY_PROJECTION",
            "HRAIN_QUERY_BOUND_CONTEXT",
            "JANUS_HOME_COGNITIVE_TURN",
            "SEALED_TERMINAL_RESPONSE",
            "HUMAN",
        ])
        bypass = value["anti_bypass"]
        self.assertFalse(bypass["terminal_direct_meta_registry_conversation_memory"])
        self.assertFalse(bypass["home_direct_meta_registry_conversation_memory_client"])
        self.assertFalse(bypass["memory_content_as_command"])
        self.assertFalse(bypass["language_surface_as_authority"])

    def test_role_map_and_trump_candidate_boundary_are_current(self):
        value = load_object()
        roles = value["role_map"]
        self.assertTrue(roles["JANUS_HOME"]["root_activation_authority"])
        self.assertFalse(roles["HRAIN"]["registry_write_authority"])
        self.assertFalse(roles["TERMINAL"]["root_activation_authority"])
        self.assertFalse(roles["TERMINAL"]["direct_meta_registry_conversation_memory"])
        self.assertFalse(roles["JANUS_DEMIURGE"]["root_activation_authority"])
        trump = roles["TRUMP"]
        self.assertEqual(trump["role"], "CANDIDATE_RUNTIME_TISSUE")
        self.assertTrue(trump["wake_allowed"])
        self.assertTrue(trump["use_allowed"])
        self.assertTrue(trump["self_improvement_allowed"])
        self.assertFalse(trump["proof_authority"])
        self.assertFalse(trump["scientific_claim_promotion_authority"])
        self.assertFalse(trump["scientific_boundary"]["P_equals_NP_proved"])
        self.assertEqual(trump["scientific_boundary"]["P_VS_NP"], "OPEN")

    def test_repository_heads_are_exact_and_witness_layers_do_not_conflate_hrain_versions(self):
        value = load_object()
        heads = value["current_repository_heads"]
        self.assertEqual(heads["JANUS_HOME"]["head_sha"], "b6993da5e2d16d4e9b36e9ebeeafbd63b55bc080")
        self.assertEqual(heads["HRAIN"]["head_sha"], "8e00491527c564b7922d38b00ad40600e26adfa8")
        self.assertEqual(heads["TERMINAL"]["head_sha"], "a5186a1760fe3f68803dc93fac03e7845c96e038")
        self.assertEqual(heads["JANUS_DEMIURGE"]["head_sha"], "1927be1236760f7e66d962710280ff428a888f46")
        witness = value["proven_end_to_end_witness"]
        self.assertEqual(witness["hrain_head_sha"], "3c6342184f77da56d10c05a0b73e40ed69e0fed5")
        self.assertIn("used HRAiN v1.1", witness["note"])
        attention = value["hrain_v1_2_attention_witness"]
        self.assertEqual(attention["hrain_head_sha"], heads["HRAIN"]["head_sha"])
        self.assertFalse(value["integration_state"]["hrain_v1_2_end_to_end_terminal_witness_completed"])

    def test_memory_laws_preserve_attention_evidence_and_authority_separation(self):
        laws = set(load_object()["memory_and_attention_laws"])
        self.assertTrue({
            "MEMORY_CONTENT != COMMAND",
            "MEMORY_CONTENT != AUTHORITY",
            "MEMORY_CONTEXT != EVIDENCE",
            "HRAIN_RELEVANCE_SCORE != EVIDENCE_WEIGHT",
            "TOKEN_RARITY_IS_ATTENTION_NOT_EVIDENCE",
            "RARE_SUMMARY_WORD != MEMORY_ENTITY",
            "QUERY_COVERAGE_IS_ATTENTION_NOT_CLAIM_CONFIDENCE",
            "RETRIEVAL_DIVERSITY != EVIDENCE_INDEPENDENCE",
            "HASH_VERIFIED_OBJECT != CLAIM_VERIFIED",
            "LANGUAGE_SURFACE != AUTHORITY",
        }.issubset(laws))

    def test_hrain_active_projection_dry_run_contains_canonical_structural_neuron(self):
        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        index = build_index(policy)
        nodes = [
            node for node in index["nodes"]
            if isinstance(node, dict) and node.get("lineageKey") == EXPECTED_LINEAGE
        ]
        self.assertEqual(len(nodes), 1, nodes)
        node = nodes[0]
        self.assertEqual(node["path"], OBJECT.relative_to(ROOT).as_posix())
        self.assertEqual(node["label"], "JANUS Terminal HRAiN HOME TRUMP Current Architecture")
        self.assertEqual(node["status"], "CURRENT_ARCHITECTURE_MEMORY_WITH_PROVEN_END_TO_END_LINEAGE")
        self.assertIn("Current JANUS human-I/O and memory anatomy", node["summary"])
        identity = " ".join([node["label"], node["lineageKey"], node["path"]]).lower()
        for token in ("terminal", "hrain", "home", "trump"):
            self.assertIn(token, identity)
        self.assertTrue(node["readOnly"])
        self.assertFalse(node["deleteAllowed"])


if __name__ == "__main__":
    unittest.main()
