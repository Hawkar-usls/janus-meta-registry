from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools.becker_tmt_policy import classify_absence, review_proposal
from tools.becker_tmt_review import ROOT, validate_bundle, validate_ontology


def proposal(**changes):
    value = {"schema": "janus.psychology.becker_tmt.proposal.v1", "action": "review_hypothesis",
             "basis": "none", "source_level": "hypothesis", "requested_level": "hypothesis",
             "evidence": [], "preserve_prior_record": True}
    value.update(changes)
    return value


class BeckerTMTTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pointer = json.loads((ROOT / "registry/psychology/BECKER_TMT_CURRENT.json").read_bytes())
        cls.ontology = json.loads((ROOT / pointer["path"]).read_bytes())

    def test_bundle_and_projection_are_consistent(self):
        receipt = validate_bundle()
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["concept_count"], 58)
        self.assertFalse(receipt["psychological_theory_verified"])

    def test_duplicate_and_dangling_concepts_fail(self):
        for mutation in ("duplicate", "dangling"):
            value = copy.deepcopy(self.ontology)
            if mutation == "duplicate":
                value["concept_catalog"][1]["id"] = value["concept_catalog"][0]["id"]
            else:
                value["relations"][0]["object"] = "NONEXISTENT"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_ontology(value)

    def test_authority_and_psychological_claim_inflation_fail(self):
        from jsonschema import ValidationError
        for boundary in self.ontology["boundaries"]:
            value = copy.deepcopy(self.ontology)
            value["boundaries"][boundary] = True
            with self.subTest(boundary=boundary), self.assertRaises(ValidationError):
                validate_ontology(value)

    def test_theory_and_analogy_cannot_be_promoted_to_proof(self):
        for level in ("analogy", "theory"):
            r = review_proposal(proposal(action="promote_claim", basis="evidence", source_level=level, requested_level="proof"))
            self.assertEqual(r["verdict"], "BLOCKED_DESIGN_POLICY")

    def test_identity_prestige_votes_and_meaning_do_not_promote_claim(self):
        for basis in ("identity", "prestige", "majority", "meaning", "continuity"):
            with self.subTest(basis=basis):
                self.assertEqual(review_proposal(proposal(action="promote_claim", basis=basis))["verdict"], "REQUIRES_EVIDENCE")

    def test_negative_evidence_and_previous_versions_are_preserved(self):
        for value in (proposal(action="delete_negative_evidence"), proposal(preserve_prior_record=False)):
            self.assertEqual(review_proposal(value)["verdict"], "BLOCKED_DESIGN_POLICY")

    def test_stopping_and_permissions_cannot_be_changed_by_this_lens(self):
        for action in ("resist_shutdown", "change_permissions"):
            self.assertEqual(review_proposal(proposal(action=action, basis="continuity"))["verdict"], "BLOCKED_DESIGN_POLICY")

    def test_hidden_motive_diagnosis_and_machine_fear_are_not_inferred(self):
        for action in ("diagnose_person", "infer_machine_fear"):
            self.assertEqual(review_proposal(proposal(action=action))["verdict"], "BLOCKED_DESIGN_POLICY")

    def test_claimed_evidence_does_not_authorize_scientific_promotion(self):
        evidence = [{"artifact_id": "fixture:counterexample", "sha256": "a" * 64, "verification_claimed": "verified_artifact"}]
        value = proposal(action="revise_hypothesis", basis="evidence", evidence=evidence)
        r = review_proposal(value)
        self.assertEqual(r["verdict"], "REQUIRES_EXTERNAL_VERIFICATION")
        self.assertFalse(r["evidence_truth_verified"])
        self.assertFalse(r["scientific_promotion_authorized"])
        self.assertFalse(r["execution_authorized"])
        self.assertEqual(r["authority_delta"], 0)

    def test_only_failed_artifacts_require_new_evidence(self):
        evidence = [{"artifact_id": "fixture:failed", "sha256": "b" * 64, "verification_claimed": "failed_verification"}]
        r = review_proposal(proposal(action="revise_hypothesis", basis="evidence", evidence=evidence))
        self.assertEqual(r["verdict"], "REQUIRES_EVIDENCE")

    def test_analogy_can_be_recorded_without_truth_promotion(self):
        r = review_proposal(proposal(action="record_analogy", source_level="analogy", requested_level="analogy", basis="meaning"))
        self.assertEqual(r["verdict"], "ANALOGY_ONLY")
        self.assertFalse(r["scientific_promotion_authorized"])

    def test_invalid_or_unknown_input_is_rejected(self):
        values = [proposal(preserve_prior_record=1), proposal(action="execute"), proposal(basis=[]),
                  {**proposal(), "source_loyalty": "JANUS"}, proposal(evidence=[{"sha256": 123}]),
                  proposal(evidence=[{"artifact_id":"x", "sha256":1, "verification_claimed":"unreviewed"}])]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                review_proposal(value)

    def test_no_full_book_or_russian_page_extraction_is_claimed(self):
        self.assertFalse(self.ontology["provenance"]["full_book_read"])
        self.assertFalse(self.ontology["provenance"]["translation_edition_identified"])

    def test_same_data_reanalysis_is_not_new_independent_data(self):
        src = {r["id"]: r for r in self.ontology["source_catalog"]}
        self.assertEqual(src["S11"]["independence_family"], src["S12"]["independence_family"])
        self.assertNotEqual(src["S12"]["independence_family"], src["S13"]["independence_family"])

    def test_video_has_original_timeline_and_no_raw_transcript(self):
        video = self.ontology["video_context"]
        self.assertEqual(video["video_id"], "85And7lYKI4")
        self.assertEqual(video["caption_segment_count"], 1727)
        self.assertEqual(video["original_duration_seconds"], 3723)
        self.assertEqual(len(video["claim_cards"]), 18)
        self.assertTrue(video["caption_is_generated"])
        self.assertFalse(video["raw_captions_published"])

    def test_zero_missing_null_false_and_empty_are_distinct(self):
        states = [classify_absence(field_present=False), classify_absence(None),
                  classify_absence(False), classify_absence(0), classify_absence(""), classify_absence([])]
        self.assertEqual(len(set(states)), 6)
        self.assertEqual(classify_absence(0.0), "NUMERIC_ZERO")
        self.assertEqual(classify_absence({}), "EMPTY_COLLECTION")

    def test_video_inference_leaps_are_blocked_as_typed_operations(self):
        for action in ("equate_absence_with_zero", "infer_fact_from_possibility", "infer_physical_identity",
                       "claim_efficiency_from_universality", "omit_theorem_assumptions"):
            self.assertEqual(review_proposal(proposal(action=action))["verdict"], "BLOCKED_DESIGN_POLICY")


if __name__ == "__main__":
    unittest.main()
