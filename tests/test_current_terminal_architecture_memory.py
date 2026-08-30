from __future__ import annotations

import json
from pathlib import Path

from research.site.janus_hrain_registry_export import build_index


ROOT = Path(__file__).resolve().parents[1]
OBJECT = ROOT / "data/JANUS-TERMINAL-HRAIN-HOME-TRUMP-CURRENT-ARCHITECTURE-2026-08-30-v1.0.json"
POLICY = ROOT / "data/JANUS-SITE-CURATOR-POLICY-v1.2.json"
EXPECTED_LINEAGE = "JANUS-TERMINAL-HRAIN-HOME-TRUMP-CURRENT-ARCHITECTURE"


def load_object():
    return json.loads(OBJECT.read_text(encoding="utf-8"))


def test_current_architecture_object_is_explicit_state_not_scientific_truth():
    value = load_object()
    assert value["schema"] == "janus.meta_registry.current_terminal_architecture.v1"
    assert value["status"] == "CURRENT_ARCHITECTURE_MEMORY_WITH_PROVEN_END_TO_END_LINEAGE"
    assert value["scope"]["kind"] == "CURRENT_ARCHITECTURE_STATE_AND_PROVENANCE_MEMORY"
    assert "SCIENTIFIC_WORLD_TRUTH" in value["scope"]["not_authoritative_for"]
    ceiling = value["proof_ceiling"]
    assert ceiling["workflow_success_is_world_truth"] is False
    assert ceiling["registry_presence_is_scientific_evidence"] is False
    assert ceiling["memory_retrieval_is_claim_verification"] is False
    assert ceiling["attention_rank_is_evidence_strength"] is False
    assert ceiling["candidate_runtime_success_is_theorem_proof"] is False


def test_canonical_memory_path_and_no_direct_bypass_are_frozen():
    value = load_object()
    assert value["canonical_memory_path"] == "META_REGISTRY_DB -> HRAIN -> JANUS_HOME -> TERMINAL"
    assert value["canonical_human_roundtrip"] == [
        "HUMAN",
        "TERMINAL_READ_ONLY_STIMULUS",
        "JANUS_HOME_ROOT_ACTIVATOR",
        "EXACT_MODEL_LOCKED_HRAIN",
        "META_REGISTRY_READ_ONLY_MEMORY_PROJECTION",
        "HRAIN_QUERY_BOUND_CONTEXT",
        "JANUS_HOME_COGNITIVE_TURN",
        "SEALED_TERMINAL_RESPONSE",
        "HUMAN",
    ]
    bypass = value["anti_bypass"]
    assert bypass["terminal_direct_meta_registry_conversation_memory"] is False
    assert bypass["home_direct_meta_registry_conversation_memory_client"] is False
    assert bypass["memory_content_as_command"] is False
    assert bypass["language_surface_as_authority"] is False


def test_role_map_and_trump_candidate_boundary_are_current():
    value = load_object()
    roles = value["role_map"]
    assert roles["JANUS_HOME"]["root_activation_authority"] is True
    assert roles["HRAIN"]["registry_write_authority"] is False
    assert roles["TERMINAL"]["root_activation_authority"] is False
    assert roles["TERMINAL"]["direct_meta_registry_conversation_memory"] is False
    assert roles["JANUS_DEMIURGE"]["root_activation_authority"] is False
    trump = roles["TRUMP"]
    assert trump["role"] == "CANDIDATE_RUNTIME_TISSUE"
    assert trump["wake_allowed"] is True
    assert trump["use_allowed"] is True
    assert trump["self_improvement_allowed"] is True
    assert trump["proof_authority"] is False
    assert trump["scientific_claim_promotion_authority"] is False
    assert trump["scientific_boundary"]["P_equals_NP_proved"] is False
    assert trump["scientific_boundary"]["P_VS_NP"] == "OPEN"


def test_repository_heads_are_exact_and_witness_layers_do_not_conflate_hrain_versions():
    value = load_object()
    heads = value["current_repository_heads"]
    assert heads["JANUS_HOME"]["head_sha"] == "b6993da5e2d16d4e9b36e9ebeeafbd63b55bc080"
    assert heads["HRAIN"]["head_sha"] == "8e00491527c564b7922d38b00ad40600e26adfa8"
    assert heads["TERMINAL"]["head_sha"] == "a5186a1760fe3f68803dc93fac03e7845c96e038"
    assert heads["JANUS_DEMIURGE"]["head_sha"] == "1927be1236760f7e66d962710280ff428a888f46"
    witness = value["proven_end_to_end_witness"]
    assert witness["hrain_head_sha"] == "3c6342184f77da56d10c05a0b73e40ed69e0fed5"
    assert "used HRAiN v1.1" in witness["note"]
    attention = value["hrain_v1_2_attention_witness"]
    assert attention["hrain_head_sha"] == heads["HRAIN"]["head_sha"]
    assert value["integration_state"]["hrain_v1_2_end_to_end_terminal_witness_completed"] is False


def test_memory_laws_preserve_attention_evidence_and_authority_separation():
    laws = set(load_object()["memory_and_attention_laws"])
    assert {
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
    }.issubset(laws)


def test_hrain_active_projection_dry_run_contains_canonical_structural_neuron():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    index = build_index(policy)
    nodes = [
        node for node in index["nodes"]
        if isinstance(node, dict) and node.get("lineageKey") == EXPECTED_LINEAGE
    ]
    assert len(nodes) == 1
    node = nodes[0]
    assert node["path"] == OBJECT.relative_to(ROOT).as_posix()
    assert node["label"] == "JANUS Terminal HRAiN HOME TRUMP Current Architecture"
    assert node["status"] == "CURRENT_ARCHITECTURE_MEMORY_WITH_PROVEN_END_TO_END_LINEAGE"
    assert "Current JANUS human-I/O and memory anatomy" in node["summary"]
    identity = " ".join([node["label"], node["lineageKey"], node["path"]]).lower()
    for token in ("terminal", "hrain", "home", "trump"):
        assert token in identity
    assert node["readOnly"] is True
    assert node["deleteAllowed"] is False
