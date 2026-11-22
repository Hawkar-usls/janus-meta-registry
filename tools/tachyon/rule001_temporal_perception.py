"""JANUS TACHYON RULE #1: offline metrics for SUBJECTIVE time.

Research-only reference implementation. No hardware or human-subject control.
No inference about physical time travel, other minds, or brain programming.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

ARMS = frozenset({"A_LOOP", "B_DIVERSITY", "C_NEUTRAL"})
PHYSICAL_VERDICT = "NOT_EVALUATED_BY_THIS_ALGORITHM"


def _numeric_nonnegative(value: object) -> bool:
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
    )


def _empty(verdict: str, reason: str) -> dict:
    return {
        "guard_verdict": verdict,
        "reason": reason,
        "physical_time_travel_verdict": PHYSICAL_VERDICT,
        "scientific_verdict": "NOT_TESTED",
        "evidence_of_timeless_consciousness": False,
    }


def score_session(session: Mapping) -> dict:
    """Validate one session and compute falsifiable non-physiological proxies.

    A single session CANNOT establish a mechanism: null / positive evaluations
    require pre-registered aggregate analyses with independent heldout data.
    """
    if not isinstance(session, Mapping):
        return _empty("INVALID_INPUT", "SESSION_NOT_MAPPING")
    if session.get("adverse_event_log"):
        return _empty("STOP_FOR_SAFETY", "SELF_STOP_OR_DISCOMFORT")
    if session.get("consent") is not True:
        return _empty("STOP_FOR_SAFETY", "NO_EXPLICIT_CONSENT")

    if session.get("condition") not in ARMS:
        return _empty("INVALID_INPUT", "UNKNOWN_ARM")
    start, end = session.get("external_clock_start_ns"), session.get("external_clock_end_ns")
    if type(start) is not int or type(end) is not int or end <= start:
        return _empty("INVALID_INPUT", "NONMONOTONIC_CLOCK")
    duration_s = (end - start) / 1e9
    if not math.isfinite(duration_s) or duration_s <= 0:
        return _empty("INVALID_INPUT", "INVALID_DURATION")

    events = session.get("stimulus_events", [])
    if not isinstance(events, list):
        return _empty("INVALID_INPUT", "BAD_EVENT_LOG")
    count, last_ms = 0, -1.0
    for evt in events:
        if not isinstance(evt, Mapping) or not _numeric_nonnegative(evt.get("time_offset_ms")):
            return _empty("INVALID_INPUT", "BAD_STIMULUS_EVENT")
        offset = float(evt["time_offset_ms"])
        if offset < last_ms or offset > duration_s * 1000 + 1e-6:
            return _empty("INVALID_INPUT", "BAD_EVENT_ORDER_OR_RANGE")
        marker = evt.get("transition_marker")
        if type(marker) is not bool:
            return _empty("INVALID_INPUT", "UNMARKED_EVENT")
        count += int(marker)
        last_ms = offset

    boundaries = session.get("boundary_labels")
    if boundaries is None:
        remembered = None
    elif isinstance(boundaries, list):
        if any(not isinstance(x, Mapping)
               or type(x.get("is_distinct_boundary")) is not bool
               for x in boundaries):
            return _empty("INVALID_INPUT", "BAD_BLIND_BOUNDARY_CODING")
        remembered = sum(x["is_distinct_boundary"] for x in boundaries)
    else:
        return _empty("INVALID_INPUT", "BAD_BOUNDARY_LABELS")

    immediate = session.get("immediate_report")
    delayed = session.get("delayed_report")
    if immediate is not None and not isinstance(immediate, Mapping):
        return _empty("INVALID_INPUT", "BAD_IMMEDIATE_REPORT")
    if delayed is not None and not isinstance(delayed, Mapping):
        return _empty("INVALID_INPUT", "BAD_DELAYED_REPORT")

    def maybe_ratio(data, key):
        if data is None or key not in data:
            return None
        if not _numeric_nonnegative(data[key]):
            raise ValueError("INVALID_DURATION_REPORT")
        return float(data[key]) / duration_s

    try:
        prospective = maybe_ratio(immediate, "subjective_duration_seconds")
        retrospective = maybe_ratio(delayed, "retrospective_duration_seconds")
    except ValueError:
        return _empty("INVALID_INPUT", "INVALID_DURATION_REPORT")

    passage = None if immediate is None else immediate.get("passage_of_time_rating")
    if passage is not None and not _numeric_nonnegative(passage):
        return _empty("INVALID_INPUT", "BAD_PASSAGE_RATING")

    checks = session.get("awareness_checks")
    awareness = "NOT_MEASURED"
    if checks is not None:
        if not isinstance(checks, list) or any(type(x) is not bool for x in checks):
            return _empty("INVALID_INPUT", "BAD_ENGAGEMENT_CHECK")
        awareness = ("OBSERVABLE_ENGAGEMENT_PRESENT"
                     if checks and all(checks) else "INSUFFICIENT_EVIDENCE")

    is_complete = remembered is not None and retrospective is not None
    return {
        "guard_verdict": ("VALID_FOR_COGNITIVE_ANALYSIS"
                          if is_complete else "ABSTAIN_MISSING_MEASUREMENTS"),
        "condition": session["condition"],
        "objective_duration_s": duration_s,
        "stimulus_transition_density_per_min": count * 60.0 / duration_s,
        "remembered_boundary_density_per_min":
            None if remembered is None else remembered * 60.0 / duration_s,
        "prospective_duration_ratio": prospective,
        "retrospective_duration_ratio": retrospective,
        "subjective_time_passage_rating": passage,
        "awareness_integrity": awareness,
        "physical_time_travel_verdict": PHYSICAL_VERDICT,
        "scientific_verdict": "NOT_TESTED",
        "evidence_of_timeless_consciousness": False,
    }


# JANUS RULE #1 is a classification framework for research evidence,
# not an ontological claim that physical processes need minds.
EVENT_KINDS = frozenset({
    "PHYSICAL_EVENT",
    "SUBJECTIVE_EXPERIENCE",
    "SOCIAL_INTERPRETATION",
    "PHYSICAL_SPACETIME_CHANGE",
})
EVENT_TYPES = frozenset({
    "ACOUSTIC_FALL",
    "SUBJECTIVE_SOUND",
    "SUBJECTIVE_TIMELESSNESS",
    "TIME_JUMP",
    "COLLECTIVE_SYNCHRONIZATION",
    "OTHER",
})


def classify_temporal_claim(claim: Mapping) -> dict:
    """Apply RULE #1 to a proposed event or subjective-time assertion.

    No sound sensation without a hearer does NOT imply no air-pressure wave;
    no felt time without temporal sequencing does NOT imply stopped clocks.
    The classification is a protective evidence ontology, not a QFT proof.
    """
    if not isinstance(claim, Mapping):
        return {"verdict": "INVALID_INPUT", "reason": "CLAIM_NOT_MAPPING"}
    kind, event = claim.get("kind"), claim.get("event_type")
    if kind not in EVENT_KINDS or event not in EVENT_TYPES:
        return {"verdict": "INVALID_INPUT", "reason": "UNKNOWN_EVENT_TYPE_OR_KIND"}
    observer = claim.get("observer_present")
    if observer is not None and type(observer) is not bool:
        return {"verdict": "INVALID_INPUT", "reason": "INVALID_OBSERVER_FLAG"}
    # Never interpret source text or participant reports as independent physics.
    if kind == "PHYSICAL_SPACETIME_CHANGE" or event == "TIME_JUMP":
        return {
            "verdict": "HOLD_INDEPENDENT_PHYSICAL_EVIDENCE",
            "physical_event_may_exist_without_observer": True,
            "physical_time_travel_verified": False,
        }
    if event == "ACOUSTIC_FALL":
        if kind != "PHYSICAL_EVENT":
            return {"verdict": "REJECT_CATEGORY_ERROR", "reason": "FALL_IS_PHYSICAL_EVENT"}
        return {
            "verdict": "PHYSICAL_EVENT_CONCEPTUALLY_POSSIBLE",
            "physical_event_may_exist_without_observer": True,
            "subjective_hearing": "NOT_PRESENT_FOR_ABSENT_OBSERVER"
            if observer is False else "NOT_ESTABLISHED_BY_EVENT_ALONE",
            "acoustic_wave_measured": False,
            "physical_time_travel_verified": False,
        }
    if event == "SUBJECTIVE_SOUND":
        if kind != "SUBJECTIVE_EXPERIENCE":
            return {"verdict": "REJECT_CATEGORY_ERROR", "reason": "SOUND_QUALIA_NEEDS_EXPERIENCER"}
        if observer is False:
            return {"verdict": "REJECT_CATEGORY_ERROR",
                    "reason": "NO_HEARING_BY_ABSENT_OBSERVER"}
        return {"verdict": "SUBJECTIVE_REPORT_REQUIRES_CONFIRMATION",
                "physical_time_travel_verified": False}
    if event == "SUBJECTIVE_TIMELESSNESS":
        if kind != "SUBJECTIVE_EXPERIENCE":
            return {"verdict": "REJECT_CATEGORY_ERROR",
                    "reason": "TIMELESSNESS_REPORT_IS_PHENOMENOLOGY"}
        return {
            "verdict": "FIRST_PERSON_REPORT_ONLY__CHECK_AWARENESS_MEMORY_AND_CLOCK",
            "memory_loss_ruled_out": False,
            "external_time_unchanged_by_claim": True,
            "physical_time_travel_verified": False,
        }
    if event == "COLLECTIVE_SYNCHRONIZATION":
        if kind != "SOCIAL_INTERPRETATION":
            return {"verdict": "REJECT_CATEGORY_ERROR",
                    "reason": "GROUP_REPORT_REQUIRES_SOCIAL_CLASS"}
        return {
            "verdict": "SOCIAL_OR_PHENOMENOLOGICAL_EFFECT__PHYSICAL_CHANGE_UNVERIFIED",
            "independent_external_measurement_required": True,
            "physical_time_travel_verified": False,
        }
    return {"verdict": "CLASSIFIED_FOR_RESEARCH_ONLY",
            "physical_time_travel_verified": False}
