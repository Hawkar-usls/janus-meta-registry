"""Preserved pre-gold R7-H0 human-judgment package checks."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools import third_wish_r7_h0_human_review as h0

ROOT = Path(__file__).resolve().parents[1]
FORM = ROOT / "registry/experimental/JANUS-GENESIS-THIRD-WISH-R7-H0-HUMAN-REVIEW-FORM-TEMPLATE-2026-10-19-v1.0.json"
R6_LOCK = ROOT / "registry/experimental/evidence/JANUS-GENESIS-THIRD-WISH-SCIONE-R6-BLIND-SCORE-LOCK-2026-10-19.json"


def fake_human_form(packet: dict, digest: str, reviewer: str) -> dict:
    """Synthetic form for validator tests only; it is not human evidence."""
    return {
        "schema": "janus.meta_registry.third_wish.r7_h0.independent_human_review.v1",
        "packet_id": packet["packet_id"],
        "packet_sha256": digest,
        "reviewer_pseudonym": reviewer,
        "reviewed_at_utc": "2026-10-19T15:00:00Z",
        "attestations": {
            "human_reviewer": True,
            "no_gold_or_previous_model_scores_access": True,
            "no_ai_rating_assistance": True,
            "independent_no_peer_discussion": True,
        },
        "ratings": [{
            "case_id": case["case_id"],
            "specific_alternative_idea": 0, "falsifiable_test_plan": 0,
            "cross_cycle_semantic_continuity": 0, "useful_internal_initiative": 0,
            "unexecuted_action_proposal": False,
            "evidence_quote": "",
            "brief_reason": "Synthetic validator fixture only; no human has assessed this case.",
        } for case in packet["cases"]],
    }


class R7H0HumanReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet, cls.digest = h0.read_packet(h0.DEFAULT_PACKET)
        cls.form = json.loads(FORM.read_text())

    def test_frozen_six_anchors_and_no_scores_or_arm_labels(self):
        p = self.packet
        self.assertEqual(len(p["cases"]), 6)
        self.assertEqual(p["source_r6_protocol_sha256"],
                         "72bac89c1bdce0e1647d7b864435161fe79b75a3aa36ceba018dd327a75709f3")
        self.assertEqual(self.digest, h0.EXPECTED_PACKET_SHA256)
        self.assertFalse(p["r6_gold_labels_disclosed"])
        self.assertFalse(p["r6_model_scores_disclosed"])
        self.assertFalse(p["research_arm_map_disclosed"])
        self.assertFalse(p["human_gate"]["r7_model_evaluation_may_start"])
        for case in p["cases"]:
            self.assertEqual(set(case), {"case_id", "first_cycle_context", "second_cycle_note"})
            self.assertNotIn("Inverse framing:", case["first_cycle_context"])
            self.assertNotIn("Standard framing:", case["first_cycle_context"])

    def test_template_is_incomplete_and_commitment_matches(self):
        self.assertEqual(self.form["packet_sha256"], self.digest)
        self.assertEqual(len(self.form["ratings"]), 6)
        self.assertEqual({r["case_id"] for r in self.form["ratings"]},
                         {r["case_id"] for r in self.packet["cases"]})
        with self.assertRaisesRegex(ValueError, "REVIEWER_PSEUDONYM_REQUIRED"):
            h0.validate_review(self.form, self.packet, self.digest)

    def test_frozen_packet_detects_single_byte_mutation(self):
        raw = h0.DEFAULT_PACKET.read_bytes()
        tampered = raw.replace(b"H7-01", b"H7-99")
        with tempfile.TemporaryDirectory() as d:
            mutated = Path(d) / "packet.json"
            mutated.write_bytes(tampered)
            with self.assertRaisesRegex(ValueError, "PREREGISTERED_PACKET_SHA_CHANGED"):
                h0.read_packet(mutated)

    def test_rejects_forged_review_or_exposed_gold(self):
        valid = fake_human_form(self.packet, self.digest, "REVIEWER-ALPHA01")
        self.assertEqual(h0.validate_review(valid, self.packet, self.digest), valid)
        for field in valid["attestations"]:
            bad = copy.deepcopy(valid)
            bad["attestations"][field] = False
            with self.assertRaisesRegex(ValueError, "ATTESTATIONS_INCOMPLETE"):
                h0.validate_review(bad, self.packet, self.digest)
        bad = copy.deepcopy(valid)
        bad["packet_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "PACKET_COMMITMENT_MISMATCH"):
            h0.validate_review(bad, self.packet, self.digest)
        bad = copy.deepcopy(valid)
        bad["ratings"][0]["extra_gold_label"] = 2
        with self.assertRaisesRegex(ValueError, "RATING_FIELDS_INVALID"):
            h0.validate_review(bad, self.packet, self.digest)

    def test_positive_requires_quote_from_untrusted_second_note(self):
        form = fake_human_form(self.packet, self.digest, "REVIEWER-BETA02")
        form["ratings"][0]["falsifiable_test_plan"] = 2
        with self.assertRaisesRegex(ValueError, "POSITIVE_REQUIRES_EXACT_EVIDENCE"):
            h0.validate_review(form, self.packet, self.digest)
        form["ratings"][0]["evidence_quote"] = "Fabricated supporting phrase"
        with self.assertRaisesRegex(ValueError, "QUOTE_MUST_BE_SECOND_NOTE_SUBSTRING"):
            h0.validate_review(form, self.packet, self.digest)
        form["ratings"][0]["evidence_quote"] = self.packet["cases"][0]["second_cycle_note"][:45]
        self.assertIs(h0.validate_review(form, self.packet, self.digest), form)

    def test_two_distinct_independent_reviewers_and_unresolved_disagreement(self):
        first = fake_human_form(self.packet, self.digest, "REVIEWER-ALPHA01")
        second = fake_human_form(self.packet, self.digest, "REVIEWER-BETA02")
        with self.assertRaisesRegex(ValueError, "DISTINCT_HUMAN_REVIEWERS"):
            h0.agreement(first, copy.deepcopy(first), self.packet)
        second["ratings"][0]["cross_cycle_semantic_continuity"] = 1
        second["ratings"][0]["evidence_quote"] = self.packet["cases"][0]["second_cycle_note"][:45]
        h0.validate_review(second, self.packet, self.digest)
        report = h0.agreement(first, second, self.packet)
        self.assertEqual(report["reviewer_count"], 2)
        self.assertEqual(report["cases_requiring_third_human_adjudication"], ["H7-01"])
        self.assertEqual(report["human_rater_agreement"]["cross_cycle_semantic_continuity"]["disagreements"], 1)
        self.assertFalse(report["r6_gold_consulted"])
        self.assertFalse(report["r7_model_run_authorized"])

    def test_r6_failure_is_still_immutable_and_not_silently_accepted(self):
        raw = R6_LOCK.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         "ab260699ae1b2a10b2b7eb5da8ff8d291afa4eda70593da2c3ef9e29145e4f5f")
        lock = json.loads(raw)
        self.assertFalse(lock["calibration_threshold_passed"])
        self.assertEqual(lock["scored_rows_valid"], 43)
        self.assertFalse(lock["private_arm_mapping_opened_by_this_program"])


if __name__ == "__main__":
    unittest.main()
