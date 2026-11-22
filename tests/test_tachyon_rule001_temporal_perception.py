"""No participants or brain devices: synthetic control tests for RULE #1."""
import copy
import unittest

from tools.tachyon.rule001_temporal_perception import score_session


def fixture():
    return {
        "session_id": "SYNTHETIC_ONLY",
        "consent": True,
        "condition": "A_LOOP",
        "external_clock_start_ns": 1_000_000_000,
        "external_clock_end_ns": 301_000_000_000,
        "stimulus_events": [
            {"time_offset_ms": 0, "stimulus_id": "a", "transition_marker": False},
            {"time_offset_ms": 60_000, "stimulus_id": "a", "transition_marker": True},
            {"time_offset_ms": 120_000, "stimulus_id": "a", "transition_marker": True},
        ],
        "immediate_report": {
            "subjective_duration_seconds": 360,
            "passage_of_time_rating": 3,
        },
        "delayed_report": {"retrospective_duration_seconds": 180},
        "boundary_labels": [
            {"event_key": "one", "is_distinct_boundary": True},
            {"event_key": "two", "is_distinct_boundary": False},
        ],
        "awareness_checks": [True, True],
        "adverse_event_log": [],
    }


class SubjectiveTimeRule1Tests(unittest.TestCase):
    def test_separate_physical_and_two_subjective_time_ratios(self):
        output = score_session(fixture())
        self.assertEqual(output["guard_verdict"], "VALID_FOR_COGNITIVE_ANALYSIS")
        self.assertEqual(output["objective_duration_s"], 300)
        self.assertAlmostEqual(output["prospective_duration_ratio"], 1.2)
        self.assertAlmostEqual(output["retrospective_duration_ratio"], 0.6)
        self.assertAlmostEqual(output["remembered_boundary_density_per_min"], 0.2)
        self.assertAlmostEqual(output["stimulus_transition_density_per_min"], 0.4)
        self.assertEqual(output["awareness_integrity"], "OBSERVABLE_ENGAGEMENT_PRESENT")

    def test_no_physical_time_travel_even_when_subjective_compression(self):
        x = score_session(fixture())
        self.assertEqual(x["physical_time_travel_verdict"], "NOT_EVALUATED_BY_THIS_ALGORITHM")
        self.assertFalse(x["evidence_of_timeless_consciousness"])
        self.assertEqual(x["scientific_verdict"], "NOT_TESTED")

    def test_consent_mandatory(self):
        x = fixture()
        del x["consent"]
        self.assertEqual(score_session(x)["guard_verdict"], "STOP_FOR_SAFETY")

    def test_stop_on_discomfort(self):
        x = fixture()
        x["adverse_event_log"] = ["participant stopped"]
        self.assertEqual(score_session(x)["guard_verdict"], "STOP_FOR_SAFETY")

    def test_backward_clock_rejected(self):
        x = fixture()
        x["external_clock_end_ns"] = -1
        self.assertEqual(score_session(x)["reason"], "NONMONOTONIC_CLOCK")

    def test_time_offset_out_of_range_rejected(self):
        x = fixture()
        x["stimulus_events"].append({"time_offset_ms": 310_000,
                                     "transition_marker": True})
        self.assertEqual(score_session(x)["reason"], "BAD_EVENT_ORDER_OR_RANGE")

    def test_unordered_events_rejected(self):
        x = fixture()
        x["stimulus_events"][2]["time_offset_ms"] = 59_000
        self.assertEqual(score_session(x)["reason"], "BAD_EVENT_ORDER_OR_RANGE")

    def test_missing_delayed_cannot_claim_retrospective_effect(self):
        x = fixture()
        del x["delayed_report"]
        r = score_session(x)
        self.assertEqual(r["guard_verdict"], "ABSTAIN_MISSING_MEASUREMENTS")
        self.assertIsNone(r["retrospective_duration_ratio"])

    def test_missing_memory_cannot_claim_retrospective_effect(self):
        x = fixture()
        del x["boundary_labels"]
        self.assertEqual(score_session(x)["guard_verdict"], "ABSTAIN_MISSING_MEASUREMENTS")

    def test_invalid_negative_recall_duration(self):
        x = fixture()
        x["delayed_report"]["retrospective_duration_seconds"] = -1
        self.assertEqual(score_session(x)["reason"], "INVALID_DURATION_REPORT")

    def test_unknown_condition_invalid(self):
        x = fixture()
        x["condition"] = "ALL_HUMANS"
        self.assertEqual(score_session(x)["guard_verdict"], "INVALID_INPUT")

    def test_awareness_check_failure_not_timelessness(self):
        x = fixture()
        x["awareness_checks"] = [True, False]
        out = score_session(x)
        self.assertEqual(out["awareness_integrity"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(out["evidence_of_timeless_consciousness"])

    def test_no_auto_inference_about_brain_from_synthetic_data(self):
        x = fixture()
        x["delayed_report"]["retrospective_duration_seconds"] = 0
        r = score_session(x)
        self.assertEqual(r["retrospective_duration_ratio"], 0)
        self.assertFalse(r["evidence_of_timeless_consciousness"])

    def test_zero_duration_and_bool_clock_rejected(self):
        x = fixture()
        x["external_clock_end_ns"] = x["external_clock_start_ns"]
        self.assertEqual(score_session(x)["guard_verdict"], "INVALID_INPUT")
        x["external_clock_start_ns"] = True
        self.assertEqual(score_session(x)["guard_verdict"], "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
