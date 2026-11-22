"""No participants or brain devices: synthetic control tests for RULE #1."""
import copy
import unittest

from tools.tachyon.rule001_temporal_perception import score_session, classify_temporal_claim


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


class FirstPersonEventOntologyTests(unittest.TestCase):
    """Synthetic category-error controls for foundational research RULE #1."""

    def test_falling_rock_without_hearer_does_not_erase_physical_wave(self):
        r = classify_temporal_claim({
            "kind": "PHYSICAL_EVENT",
            "event_type": "ACOUSTIC_FALL",
            "observer_present": False,
        })
        self.assertTrue(r["physical_event_may_exist_without_observer"])
        self.assertEqual(r["subjective_hearing"], "NOT_PRESENT_FOR_ABSENT_OBSERVER")
        self.assertFalse(r["acoustic_wave_measured"])

    def test_no_listener_cannot_report_sound_experience(self):
        r = classify_temporal_claim({
            "kind": "SUBJECTIVE_EXPERIENCE",
            "event_type": "SUBJECTIVE_SOUND",
            "observer_present": False,
        })
        self.assertEqual(r["verdict"], "REJECT_CATEGORY_ERROR")

    def test_heard_sound_is_not_the_falling_event_itself(self):
        r = classify_temporal_claim({
            "kind": "PHYSICAL_EVENT",
            "event_type": "SUBJECTIVE_SOUND",
            "observer_present": True,
        })
        self.assertEqual(r["verdict"], "REJECT_CATEGORY_ERROR")

    def test_timelessness_report_does_not_stop_external_clocks(self):
        r = classify_temporal_claim({
            "kind": "SUBJECTIVE_EXPERIENCE",
            "event_type": "SUBJECTIVE_TIMELESSNESS",
            "observer_present": True,
            "subjective_report": "I felt no passage of time",
        })
        self.assertEqual(r["verdict"], "FIRST_PERSON_REPORT_ONLY__CHECK_AWARENESS_MEMORY_AND_CLOCK")
        self.assertFalse(r["memory_loss_ruled_out"])
        self.assertTrue(r["external_time_unchanged_by_claim"])
        self.assertFalse(r["physical_time_travel_verified"])

    def test_felt_timelessness_as_physical_time_is_category_error(self):
        r = classify_temporal_claim({
            "kind": "PHYSICAL_EVENT",
            "event_type": "SUBJECTIVE_TIMELESSNESS",
        })
        self.assertEqual(r["verdict"], "REJECT_CATEGORY_ERROR")

    def test_single_person_physical_time_jump_is_hold(self):
        r = classify_temporal_claim({
            "kind": "PHYSICAL_SPACETIME_CHANGE",
            "event_type": "TIME_JUMP",
            "subjective_report": "transported",
        })
        self.assertEqual(r["verdict"], "HOLD_INDEPENDENT_PHYSICAL_EVIDENCE")
        self.assertFalse(r["physical_time_travel_verified"])

    def test_collective_synchronization_not_physical_spacetime(self):
        r = classify_temporal_claim({
            "kind": "SOCIAL_INTERPRETATION",
            "event_type": "COLLECTIVE_SYNCHRONIZATION",
        })
        self.assertTrue(r["independent_external_measurement_required"])
        self.assertFalse(r["physical_time_travel_verified"])

    def test_collective_as_physical_is_hold(self):
        r = classify_temporal_claim({
            "kind": "PHYSICAL_SPACETIME_CHANGE",
            "event_type": "COLLECTIVE_SYNCHRONIZATION",
        })
        self.assertEqual(r["verdict"], "HOLD_INDEPENDENT_PHYSICAL_EVIDENCE")

    def test_invalid_event_and_observer_types(self):
        self.assertEqual(classify_temporal_claim({"kind":"POSSIBLE", "event_type":"OTHER"})["verdict"],
                         "INVALID_INPUT")
        self.assertEqual(classify_temporal_claim({"kind":"PHYSICAL_EVENT",
                             "event_type":"ACOUSTIC_FALL", "observer_present":"none"})["verdict"],
                         "INVALID_INPUT")

    def test_research_only_default_no_physical_certification(self):
        r = classify_temporal_claim({"kind":"PHYSICAL_EVENT", "event_type":"OTHER"})
        self.assertEqual(r["verdict"], "CLASSIFIED_FOR_RESEARCH_ONLY")
        self.assertFalse(r["physical_time_travel_verified"])


if __name__ == "__main__":
    unittest.main()
