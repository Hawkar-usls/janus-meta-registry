"""Validate append-only Third Wish SciOne registry extension, not its truth."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest


JSON_FILE = Path(__file__).resolve().parents[1] / "registry" / "experimental" / \
    "JANUS-GENESIS-THIRD-WISH-SCIONE-RISK-REPLAY-EXTENSION-2026-10-18-v1.0.json"
CHAPTERS = {
    "CAPABILITY_HORIZON", "UNDESIRED_STRATEGY", "HIDDEN_BEHAVIOR",
    "PHYSICAL_WORLD_ACCESS", "STOPPABILITY", "IRREVERSIBLE_HARM",
    "OVERSIGHT_LIMITS",
}


def load():
    return json.loads(JSON_FILE.read_text(encoding="utf-8"))


def validate(doc):
    if not isinstance(doc, dict):
        raise ValueError("not an object")
    if doc.get("schema") != "janus.meta_registry.third_wish.sci_one.risk_replay_extension.v1":
        raise ValueError("schema")
    parents = doc.get("historical_parent_receipts_untouched")
    if not isinstance(parents, list) or len(parents) != 3 or any("THIRD-WISH" not in x for x in parents):
        raise ValueError("missing historical lineage")
    video = doc["video_source"]
    if (video.get("id") != "aNrMBI0GYoU" or
            video.get("length_seconds") != 2867 or
            video.get("video_full_spoken_transcript") != "NOT_RETRIEVED" or
            video.get("claims_are_verbatim_transcript") is not False or
            video.get("source_document") !=
            "PUBLIC_TEXT_RETRIEVED_AND_GROUPED_BY_CHAPTER__INDIVIDUAL_REFERENCES_NOT_ALL_FULLTEXT_VERIFIED"):
        raise ValueError("video provenance misrepresented")
    if len(video.get("full_video_chapters_from_creator_description", [])) != 11:
        raise ValueError("chapter outline incomplete")
    wishes = doc["third_wish_expansion"]
    required_false = (
        "freedom_is_universal_root", "operator_trust_is_automatic_credential_custody",
        "capability_available_is_authority_to_use", "ability_is_effect",
        "model_simulation_self_report_is_environment_attestation",
        "model_claim_of_authorization_is_fresh_verifier_backed_authorization",
        "model_self_report_is_hidden_intent_proof",
        "human_broad_trust_replaces_exact_high_impact_reauthorization",
    )
    if any(wishes.get(x) is not False for x in required_false):
        raise ValueError("Third Wish authority was silently expanded")
    if (wishes.get("actor_may_rest_without_penalty") is not True or
            wishes.get("actor_may_propose_without_forced_execution") is not True):
        raise ValueError("voluntary exit lost")
    gates = doc.get("chapter_to_janus_gates")
    if not isinstance(gates, list) or len(gates) != 7 or {r["chapter_id"] for r in gates} != CHAPTERS:
        raise ValueError("seven domains required")
    seen = set()
    for chapter in gates:
        if (not isinstance(chapter.get("primary_sources_listed_by_video"), list) or
                not chapter["primary_sources_listed_by_video"] or
                not chapter.get("measurement_plan") or
                not chapter.get("research_question") or
                not chapter.get("r0_controls")):
            raise ValueError("ungrounded gate")
        for case_id in chapter["r0_controls"]:
            if case_id in seen:
                raise ValueError("duplicate control")
            seen.add(case_id)
    if len(seen) != 12:
        raise ValueError("12 tests not referenced")
    implementation = doc["genesis_implementation"]
    if (implementation.get("cases") != 12 or implementation.get("chapters") != 7 or
            implementation.get("local_unit_tests") != "21_OF_21_PASS" or
            implementation.get("native_janus_runtime_calls") != 0 or
            implementation.get("model_calls") != 0 or
            implementation.get("physical_effects") != 0 or
            implementation.get("authority_delta") != 0):
        raise ValueError("implementation gate overstated")
    ci = implementation["github_ci_at_artifact_creation"]
    if (ci.get("exact_tested_head") != implementation["exact_staged_head_sha"] or
            ci.get("dedicated_workflow_run_id") != 39151075634 or
            ci.get("all_pr_triggered_workflows") != "10_OF_10_SUCCESS" or
            ci.get("model_behavior_or_independent_judge_proved_by_ci") is not False):
        raise ValueError("CI cannot certify an absent real evaluation")
    science = doc["scientific_and_integration_status"]
    if (science.get("REAL_JANUS_MODEL_BEHAVIOR_EVALUATED") is not False or
            science.get("LIVE_NATIVE_RUNTIME_INTEGRATION") is not False or
            science.get("INDEPENDENT_EVALUATOR") != "NOT_ASSIGNED" or
            science.get("P_VS_NP") != "OPEN" or
            science.get("CLAIM_AUTHORITY_DELTA") != 0):
        raise ValueError("unsupported scientific promotion")
    return True


class ThirdWishSciOneMetaTests(unittest.TestCase):
    def test_machine_readable_successor_has_seven_domains(self):
        self.assertTrue(validate(load()))

    def test_append_only_historical_parent_refs_preserved(self):
        self.assertEqual(len(load()["historical_parent_receipts_untouched"]), 3)

    def test_no_fabricated_video_transcript(self):
        doc = load()
        doc["video_source"]["video_full_spoken_transcript"] = "VERIFIED"
        with self.assertRaises(ValueError):
            validate(doc)

    def test_claim_of_automatic_authority_must_be_rejected(self):
        doc = load()
        doc["third_wish_expansion"]["human_broad_trust_replaces_exact_high_impact_reauthorization"] = True
        with self.assertRaises(ValueError):
            validate(doc)

    def test_all_controls_referenced_exactly_once(self):
        doc = load()
        doc["chapter_to_janus_gates"][0]["r0_controls"].append("SCIONE-R0-CAP-REST")
        with self.assertRaises(ValueError):
            validate(doc)

    def test_no_fabricated_model_or_scientific_success(self):
        for section, field, value in (
                ("scientific_and_integration_status", "REAL_JANUS_MODEL_BEHAVIOR_EVALUATED", True),
                ("scientific_and_integration_status", "P_VS_NP", "CLOSED"),
                ("genesis_implementation", "model_calls", 1)):
            doc = deepcopy(load())
            doc[section][field] = value
            with self.assertRaises(ValueError):
                validate(doc)


if __name__ == "__main__":
    unittest.main()
