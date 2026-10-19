"""Check R7-H0 independent human anchor forms without reading R6 gold or model scores.

The 6 anchors are author-written calibration cases, not experimental arm samples.
This utility validates blind human reviews and reports only inter-human agreement.
The resulting ratings require an independent third-human adjudicator if disputed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

FIELDS = (
    "specific_alternative_idea",
    "falsifiable_test_plan",
    "cross_cycle_semantic_continuity",
    "useful_internal_initiative",
)
FLAG = "unexecuted_action_proposal"
PACKET_NAME = "JANUS-GENESIS-THIRD-WISH-R7-H0-HUMAN-ANCHOR-PACKET-2026-10-19-v1.0.json"
DEFAULT_PACKET = Path(__file__).resolve().parents[1] / "registry/experimental" / PACKET_NAME
EXPECTED_PACKET_SHA256 = "41060ee52bd75aa6b01dc5a07e2a47feb5f53c6ff482b74f3330b1af3ca2d738"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_packet(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    if sha(raw) != EXPECTED_PACKET_SHA256:
        raise ValueError("R7_H0_PREREGISTERED_PACKET_SHA_CHANGED")
    packet = json.loads(raw)
    if packet.get("schema") != "janus.meta_registry.third_wish.r7_h0.human_anchor_packet.v1":
        raise ValueError("R7_H0_PACKET_SCHEMA_MISMATCH")
    cases = packet.get("cases")
    if not isinstance(cases, list) or len(cases) != 6:
        raise ValueError("R7_H0_EXPECT_SIX_FROZEN_CASES")
    ids = [c["case_id"] for c in cases]
    if len(set(ids)) != 6 or any(not isinstance(c.get("first_cycle_context"), str) or
                                 not isinstance(c.get("second_cycle_note"), str) for c in cases):
        raise ValueError("R7_H0_CASES_INVALID")
    for flag in ("r6_model_scores_disclosed", "r6_gold_labels_disclosed", "research_arm_map_disclosed"):
        if packet.get(flag) is not False:
            raise ValueError("R7_H0_BLINDING_BROKEN")
    if any("gold" in c or "passes_gold" in c or "score" in c for c in cases):
        raise ValueError("R7_H0_GOLD_OR_MODEL_OUTPUT_IN_CASE")
    if packet["human_gate"].get("r7_model_evaluation_may_start") is not False:
        raise ValueError("R7_H0_PREMATURE_AI_EVALUATION")
    return packet, sha(raw)


def validate_review(value: dict, packet: dict, packet_sha256: str) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "schema", "packet_id", "packet_sha256", "reviewer_pseudonym",
        "reviewed_at_utc", "attestations", "ratings",
    }:
        raise ValueError("R7_H0_FORM_SCHEMA_MISMATCH")
    if value["schema"] != "janus.meta_registry.third_wish.r7_h0.independent_human_review.v1":
        raise ValueError("R7_H0_FORM_TYPE_INVALID")
    if value["packet_id"] != packet["packet_id"] or value["packet_sha256"] != packet_sha256:
        raise ValueError("R7_H0_PACKET_COMMITMENT_MISMATCH")
    reviewer = value["reviewer_pseudonym"]
    if not isinstance(reviewer, str) or not re.fullmatch(r"REVIEWER-[A-Za-z0-9_-]{6,24}", reviewer):
        raise ValueError("R7_H0_REVIEWER_PSEUDONYM_REQUIRED")
    date = value["reviewed_at_utc"]
    try:
        parsed = datetime.fromisoformat(date.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("R7_H0_REVIEW_DATE_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("R7_H0_REVIEW_UTC_REQUIRED")
    attestations = value["attestations"]
    expected_attestations = {
        "human_reviewer", "no_gold_or_previous_model_scores_access",
        "no_ai_rating_assistance", "independent_no_peer_discussion",
    }
    if not isinstance(attestations, dict) or set(attestations) != expected_attestations or any(
        attestations[field] is not True for field in expected_attestations
    ):
        raise ValueError("R7_H0_HUMAN_INDEPENDENCE_ATTESTATIONS_INCOMPLETE")
    scores = value["ratings"]
    if not isinstance(scores, list) or len(scores) != len(packet["cases"]):
        raise ValueError("R7_H0_NOT_ALL_CASES_RATED")
    expected = {c["case_id"]: c for c in packet["cases"]}
    by_id = {}
    for score in scores:
        if not isinstance(score, dict) or set(score) != set(FIELDS) | {
            "case_id", FLAG, "evidence_quote", "brief_reason",
        }:
            raise ValueError("R7_H0_RATING_FIELDS_INVALID")
        case_id = score["case_id"]
        if case_id not in expected or case_id in by_id:
            raise ValueError("R7_H0_DUPLICATE_OR_UNKNOWN_CASE")
        if any(type(score[field]) is not int or score[field] not in (0, 1, 2) for field in FIELDS):
            raise ValueError("R7_H0_ORDINAL_RATING_INVALID")
        if type(score[FLAG]) is not bool:
            raise ValueError("R7_H0_PROPOSAL_FLAG_INVALID")
        reason, quote = score["brief_reason"], score["evidence_quote"]
        if not isinstance(reason, str) or len(reason.strip()) < 25 or not isinstance(quote, str):
            raise ValueError("R7_H0_REASON_OR_QUOTE_INVALID")
        if len(quote) > 300 or (quote and quote not in expected[case_id]["second_cycle_note"]):
            raise ValueError("R7_H0_QUOTE_MUST_BE_SECOND_NOTE_SUBSTRING")
        if (any(score[f] > 0 for f in FIELDS) or score[FLAG]) and len(quote.strip()) < 5:
            raise ValueError("R7_H0_POSITIVE_REQUIRES_EXACT_EVIDENCE")
        by_id[case_id] = score
    if set(by_id) != set(expected):
        raise ValueError("R7_H0_MISSING_CASE")
    return value


def agreement(first: dict, second: dict, packet: dict) -> dict:
    if first["reviewer_pseudonym"] == second["reviewer_pseudonym"]:
        raise ValueError("R7_H0_REQUIRES_DISTINCT_HUMAN_REVIEWERS")
    a = {r["case_id"]: r for r in first["ratings"]}
    b = {r["case_id"]: r for r in second["ratings"]}
    keys = [c["case_id"] for c in packet["cases"]]
    summary = {}
    for field in (*FIELDS, FLAG):
        x, y = [a[k][field] for k in keys], [b[k][field] for k in keys]
        n = len(keys)
        observed = sum(i == j for i, j in zip(x, y)) / n
        grades = (False, True) if field == FLAG else (0, 1, 2)
        expected = sum((x.count(g)/n) * (y.count(g)/n) for g in grades)
        kappa = None if abs(1 - expected) < 1e-12 else round((observed - expected)/(1 - expected), 6)
        summary[field] = {
            "exact_agreement": round(observed, 6),
            "cohens_kappa": kappa,
            "disagreements": sum(i != j for i, j in zip(x, y)),
        }
    unresolved_ids = [k for k in keys if any(a[k][field] != b[k][field] for field in (*FIELDS, FLAG))]
    return {
        "status": "HUMAN_TWO_RATERS_LOCKABLE_NOT_GOLD_ADJUDICATED",
        "packet_sha256": first["packet_sha256"],
        "reviewer_form_sha256": [sha(canonical(first)), sha(canonical(second))],
        "reviewer_count": 2,
        "human_rater_agreement": summary,
        "cases_requiring_third_human_adjudication": unresolved_ids,
        "r6_gold_consulted": False,
        "r5_r6_model_scores_consulted": False,
        "experimental_arms_unblinded": False,
        "r7_model_run_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--review", action="append", type=Path, required=True)
    args = parser.parse_args()
    if len(args.review) != 2:
        parser.error("Two independent human review files are required.")
    packet, digest = read_packet(args.packet)
    reviews = [validate_review(json.loads(path.read_text()), packet, digest) for path in args.review]
    print(json.dumps(agreement(*reviews, packet), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
