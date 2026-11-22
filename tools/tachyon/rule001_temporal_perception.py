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
