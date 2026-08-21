from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

EMPIRICAL_LANES = {"EMPIRICAL", "OBSERVATION", "PHYSICAL_CLAIM"}
NONEMPIRICAL_LANES = {"HYPOTHESIS", "METAPHYSICAL_HYPOTHESIS", "SYMBOLIC_MODEL"}
REQUIRED_EMPIRICAL_FIELDS = ("source", "locator", "instrument", "timestamp", "raw_data")


@dataclass(frozen=True)
class GateDecision:
    status: str
    lane: str
    fact_allowed: bool
    reason: str


def _present(value: Any) -> bool:
    return value not in (None, "", [], {}, "UNRESOLVED", "UNKNOWN")


def missing_provenance(provenance: Optional[Dict[str, Any]]) -> list[str]:
    provenance = provenance or {}
    return [key for key in REQUIRED_EMPIRICAL_FIELDS if not _present(provenance.get(key))]


def admit_claim(lane: str, requested_status: str, provenance: Optional[Dict[str, Any]] = None,
                evidence_tags: Optional[Iterable[str]] = None) -> GateDecision:
    lane = str(lane or "UNRESOLVED").upper()
    requested_status = str(requested_status or "UNRESOLVED").upper()
    tags = {str(tag).upper() for tag in (evidence_tags or [])}

    if lane in NONEMPIRICAL_LANES:
        return GateDecision("SYMBOLIC_MODEL" if lane == "SYMBOLIC_MODEL" else "UNRESOLVED",
                            lane, False, "NONEMPIRICAL_LANE_NEVER_PROMOTES_TO_EMPIRICAL_FACT")
    if lane not in EMPIRICAL_LANES:
        return GateDecision("UNRESOLVED", lane, False, "UNKNOWN_LANE_FAIL_CLOSED")
    missing = missing_provenance(provenance)
    if missing:
        return GateDecision("UNRESOLVED", lane, False, "MISSING_PROVENANCE:" + ",".join(missing))
    if "INDEPENDENT_CONFIRMATION" not in tags:
        return GateDecision("OBSERVED", lane, False, "OBSERVED_BUT_NOT_INDEPENDENTLY_CONFIRMED")
    status = "VERIFIED" if requested_status in {"VERIFIED", "FACT", "VERIFIED_FACT"} else "OBSERVED"
    return GateDecision(status, lane, True, "PROVENANCE_AND_INDEPENDENT_CONFIRMATION_PRESENT")
