from __future__ import annotations

import copy
import json
import pathlib
from datetime import datetime, timezone, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

PARENT = DATA / "JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.17.json"
SPEC = DATA / "JANUS-LINEAR-A-RESEARCH-STATE-PROMOTION-SPEC-2026-08-14-v2.18.json"
ACQ = DATA / "JANUS-LINEAR-A-R3B-0-NOTTI-2018-OPEN-PUBLISHER-RESCUE-ACQUISITION-RESULT-2026-08-14-v0.1.1.json"
BRIDGE = DATA / "JANUS-LINEAR-A-R3B-0-NOTTI-2018-IDENTITY-BRIDGE-RESULT-2026-08-14-v0.1.json"
AUDIT = DATA / "JANUS-LINEAR-A-R3B-0-NOTTI-2018-SOURCE-PARSER-INTEGRITY-AUDIT-RESULT-2026-08-14-v0.1.json"
COMPARE = DATA / "JANUS-LINEAR-A-R3B-0-NOTTI-2018-SIGN-ID-CONFORMANCE-CORRECTIVE-RESULT-2026-08-14-v0.1.1.json"

CANDIDATE = DATA / "JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.18-CANDIDATE.json"
CANONICAL = DATA / "JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.18.json"
CANON_AUDIT = DATA / "JANUS-LINEAR-A-RESEARCH-STATE-CANONICALITY-AUDIT-2026-08-14-v2.18.json"


def load(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: pathlib.Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parent, spec, acq, bridge, parser_audit, compare = map(load, [PARENT, SPEC, ACQ, BRIDGE, AUDIT, COMPARE])

    prereq_checks = {
        "parent_is_v2_17_current_canonical": parent.get("version") == "v2.17" and parent.get("status") == "CURRENT_CANONICAL_RESEARCH_STATE" and parent.get("canonicality", {}).get("current_source_of_truth") is True,
        "acquisition_status": acq.get("status") == "EXACT_OPEN_PUBLISHER_BYTES_ADMITTED_CONTENT_VISIBLE_NONBLIND_RESCUE_WITNESS",
        "acquisition_exact_bytes": acq.get("transport_receipt", {}).get("byte_length") == 397594,
        "acquisition_exact_sha256": acq.get("transport_receipt", {}).get("sha256") == "9b9ecee53733bd7f778d6cc4c1edf9a98e0b06385f97f6852de519c2082ec863",
        "acquisition_exact_pages": acq.get("transport_receipt", {}).get("page_count") == 9,
        "acquisition_blind_credit_false": acq.get("content_and_blinding_classification", {}).get("blind_novelty_credit") is False,
        "bridge_status": bridge.get("status") == "IDENTITY_BRIDGE_13_PASS_ZB14_ZB15_COLLISION_PRESERVED",
        "bridge_13": bridge.get("summary", {}).get("bridged_identity_count") == 13,
        "bridge_collision_preserved": bridge.get("summary", {}).get("standalone_mapping_for_collision_created") is False and bridge.get("unresolved_alias_collision", {}).get("collision_proved") is True,
        "source_parser_audit_status": parser_audit.get("status") == "SOURCE_PARSER_PARENT_DEFECT_CONFIRMED_SOURCE_ONLY_CORRECTIVE_CONTRACT_READY" and parser_audit.get("all_checks_pass") is True,
        "source_parser_THE9_defect_confirmed": parser_audit.get("summary", {}).get("THE9_parent_truncation_defect_confirmed") is True,
        "source_parser_reference_side_unused": parser_audit.get("summary", {}).get("reference_readings_fetched") is False,
        "corrective_compare_status": compare.get("status") == "CORRECTIVE_REPLAY_ALL_13_SOURCE_AMBIGUITY_PRESERVED" and compare.get("all_checks_pass") is True,
        "compare_family_13": compare.get("summary", {}).get("family_size") == 13,
        "compare_9_comparable": compare.get("summary", {}).get("comparable_count") == 9,
        "compare_7_exact": compare.get("summary", {}).get("exact_match_count") == 7,
        "compare_2_mismatch": compare.get("summary", {}).get("mismatch_count") == 2,
        "compare_4_source_ambiguous": compare.get("summary", {}).get("source_ambiguity_noncomparable_count") == 4,
        "compare_0_empty": compare.get("summary", {}).get("empty_noncomparable_count") == 0,
        "compare_blind_credit_false": compare.get("summary", {}).get("blind_novelty_credit") is False,
        "compare_strict_R3B_false": compare.get("summary", {}).get("strict_R3B_replication_established") is False,
    }
    if not all(prereq_checks.values()):
        print(json.dumps({"status": "PROMOTION_BLOCKED_PREREQUISITE_NONPASS", "checks": prereq_checks}, indent=2))
        return 2

    exact_ids = [r["notti_id"] for r in compare["document_results"] if r["classification"] == "EXACT_SIGN_ID_SEQUENCE_MATCH"]
    mismatch_ids = [r["notti_id"] for r in compare["document_results"] if r["classification"] == "SIGN_ID_SEQUENCE_MISMATCH"]
    ambiguous_ids = [r["notti_id"] for r in compare["document_results"] if r["classification"] == "NONCOMPARABLE_SOURCE_ROW_AMBIGUITY"]
    assert exact_ids == ["THEZB2", "THEZB3", "THEZB4", "THEZB6", "THE10", "THE11", "THE12"]
    assert mismatch_ids == ["THEZB1", "THE7"]
    assert ambiguous_ids == ["THEZG5", "THE8", "THE9", "THEZB13"]

    now_ua = datetime.now(timezone(timedelta(hours=3))).isoformat()
    candidate = copy.deepcopy(parent)
    candidate["artifact_uuid"] = "JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.18"
    candidate["timestamp"] = now_ua
    candidate["version"] = "v2.18"
    candidate["title"] = "JANUS Linear A canonical candidate after exact-byte Notti 2018 nonblind independent-editorial corrective conformance"
    candidate["status"] = "CANONICAL_CANDIDATE_AWAITING_AUDIT"
    candidate["canonicality"] = {
        "current_source_of_truth": False,
        "parent_state": PARENT.relative_to(ROOT).as_posix(),
        "promotion_spec": SPEC.relative_to(ROOT).as_posix(),
        "promotion_prerequisites_pass": True,
        "history_is_not_deleted": True,
        "candidate_path": CANDIDATE.relative_to(ROOT).as_posix(),
        "canonicality_audit": CANON_AUDIT.relative_to(ROOT).as_posix(),
        "canonicality_audit_status": "PENDING",
        "promotion_rule_satisfied": False,
    }

    candidate["R3B_nonblind_independent_editorial_corrective_control_2018"] = {
        "status": "EXECUTED_EXACT_BYTE_NONBLIND_CORRECTIVE_CONTROL",
        "source": {
            "author": "Erika Notti",
            "publication_year": 2018,
            "venue": "Proceedings of the 12th International Congress of Cretan Studies",
            "exact_source_receipt": ACQ.relative_to(ROOT).as_posix(),
            "byte_length": 397594,
            "sha256": "9b9ecee53733bd7f778d6cc4c1edf9a98e0b06385f97f6852de519c2082ec863",
            "page_count": 9,
            "pre_seal_content_exposure": True,
            "blind_novelty_credit": False,
        },
        "identity_layer": {
            "bridge_result": BRIDGE.relative_to(ROOT).as_posix(),
            "bridged_identities": 13,
            "THEZb14_THEZb15_collision": "UNRESOLVED_ALIAS_COLLISION_NO_SILENT_MAPPING",
        },
        "source_parser_integrity": {
            "audit_result": AUDIT.relative_to(ROOT).as_posix(),
            "parent_THE9_AB000_truncation_defect_confirmed": True,
            "source_only_repair": True,
            "reference_readings_used_to_repair": False,
        },
        "corrective_sign_id_conformance": {
            "result": COMPARE.relative_to(ROOT).as_posix(),
            "family_size": 13,
            "comparable": 9,
            "exact_matches": 7,
            "mismatches": 2,
            "source_ambiguous_noncomparables": 4,
            "empty_noncomparables": 0,
            "exact_match_ids": exact_ids,
            "mismatch_ids": mismatch_ids,
            "source_ambiguous_ids": ambiguous_ids,
            "representation": "Notti A/AB numeric sign IDs versus reference Unicode LINEAR A SIGN A###/AB### names; no phonetic or semantic values",
        },
        "interpretation": "This establishes a reproducible nonblind independent-editorial corrective control, not blinded R3B replication. Seven of nine source-unambiguous bridged documents have exact mechanical sign-ID sequence agreement; two preserve technical editorial differences; four remain noncomparable because the source table exposes multiple prefixed fragments that JANUS refuses to choose among using the reference side.",
        "strict_R3B_replication_established": False,
        "new_anchor_established": False,
        "decipherment_established": False,
    }

    lane = copy.deepcopy(candidate.get("R3B_independent_editorial_replication_lane", {}))
    lane.update({
        "status": "QUALIFIED_ACQUISITION_FRONTIER_PLUS_NONBLIND_INDEPENDENT_EDITORIAL_CONTROL",
        "R3B_0": "STRICT_BLINDED_CANDIDATE_BYTES_PENDING; NOTTI_2018_EXACT_BYTES_ADMITTED_ONLY_AS_NONBLIND_CORRECTIVE_CONTROL",
        "R3B_1": "STRICT_RUNNER_READY_PENDING_UNCONTAMINATED_NOTTI_2021_2025_PH13_OR_OTHER_EXACT_BYTES; NOTTI_2018_INELIGIBLE_FOR_BLIND_REPLICATION",
        "R3B_2": "BLOCKED",
        "R3B_3": "BLOCKED",
        "R3B_4": "BLOCKED",
        "reason": "Notti 2018 now supplies a real exact-byte independent-editorial corrective control, but pre-seal content exposure makes it ineligible for strict blinded R3B admission. Uncontaminated exact bytes for Notti 2021/2025, PH13, RILA-S1 or another alternate-editorial source remain required.",
    })
    candidate["R3B_independent_editorial_replication_lane"] = lane

    for row in candidate.get("roadmap", []):
        if row.get("id") == "R3B_0_SOURCE_ACQUISITION":
            row["status"] = "ACTIVE_BLOCKER_WITH_NONBLIND_EXACT_EDITORIAL_CONTROL_AVAILABLE"
        if row.get("id") == "R3B_1_OVERLAP_FREEZE":
            row["status"] = "READY_BUT_BLOCKED_FOR_STRICT_BLIND_SOURCE_RECEIPT"

    candidate["next_atomic_requirements"] = [
        {
            "id": "P0_STRICT_NOTTI_THERA_OR_PH13_BYTE_ACQUISITION",
            "action": "Acquire unchanged Notti 2021/2025 or PH13 bytes through a route that preserves a pre-content exact-byte receipt; freeze actual source-native overlap before reading/selection. Notti 2018 cannot satisfy this blinded gate because its content was visible before sealing."
        },
        *[x for x in parent.get("next_atomic_requirements", []) if x.get("id") != "P0_STRICT_NOTTI_THERA_OR_PH13_BYTE_ACQUISITION"],
    ]

    dump(CANDIDATE, candidate)

    audit_checks = {
        **prereq_checks,
        "all_parent_top_level_sections_preserved": set(parent).issubset(set(candidate)),
        "candidate_version_v2_18": candidate["version"] == "v2.18",
        "candidate_not_yet_canonical": candidate["status"] == "CANONICAL_CANDIDATE_AWAITING_AUDIT" and candidate["canonicality"]["current_source_of_truth"] is False,
        "nonblind_control_recorded": candidate["R3B_nonblind_independent_editorial_corrective_control_2018"]["status"] == "EXECUTED_EXACT_BYTE_NONBLIND_CORRECTIVE_CONTROL",
        "strict_R3B_still_false": candidate["R3B_nonblind_independent_editorial_corrective_control_2018"]["strict_R3B_replication_established"] is False,
        "no_decipherment_promotion": candidate["R3B_nonblind_independent_editorial_corrective_control_2018"]["decipherment_established"] is False,
        "claim_counts_exact": candidate["R3B_nonblind_independent_editorial_corrective_control_2018"]["corrective_sign_id_conformance"] == {
            "result": COMPARE.relative_to(ROOT).as_posix(),
            "family_size": 13,
            "comparable": 9,
            "exact_matches": 7,
            "mismatches": 2,
            "source_ambiguous_noncomparables": 4,
            "empty_noncomparables": 0,
            "exact_match_ids": exact_ids,
            "mismatch_ids": mismatch_ids,
            "source_ambiguous_ids": ambiguous_ids,
            "representation": "Notti A/AB numeric sign IDs versus reference Unicode LINEAR A SIGN A###/AB### names; no phonetic or semantic values",
        },
        "strict_lane_requires_uncontaminated_bytes": "INELIGIBLE_FOR_BLIND_REPLICATION" in candidate["R3B_independent_editorial_replication_lane"]["R3B_1"],
    }
    audit_pass = all(audit_checks.values())
    audit_obj = {
        "artifact_uuid": "JANUS-LINEAR-A-RESEARCH-STATE-CANONICALITY-AUDIT-2026-08-14-v2.18",
        "version": "v2.18",
        "node_type": "canonicality_audit",
        "status": "CANONICALITY_AUDIT_PASS" if audit_pass else "CANONICALITY_AUDIT_FAIL",
        "executed_at": now_ua,
        "parent": PARENT.relative_to(ROOT).as_posix(),
        "candidate": CANDIDATE.relative_to(ROOT).as_posix(),
        "promotion_spec": SPEC.relative_to(ROOT).as_posix(),
        "checks": audit_checks,
        "all_checks_pass": audit_pass,
        "claim_ceiling": spec["forbidden_promotions"],
    }
    dump(CANON_AUDIT, audit_obj)
    if not audit_pass:
        print(json.dumps(audit_obj, indent=2))
        return 3

    canonical = copy.deepcopy(candidate)
    canonical["status"] = "CURRENT_CANONICAL_RESEARCH_STATE"
    canonical["canonicality"].update({
        "current_source_of_truth": True,
        "canonicality_audit_status": "CANONICALITY_AUDIT_PASS",
        "promotion_rule_satisfied": True,
    })
    dump(CANONICAL, canonical)
    print(json.dumps({
        "status": "PROMOTED_V2_18",
        "canonical": CANONICAL.relative_to(ROOT).as_posix(),
        "audit": CANON_AUDIT.relative_to(ROOT).as_posix(),
        "nonblind_control_summary": canonical["R3B_nonblind_independent_editorial_corrective_control_2018"]["corrective_sign_id_conformance"],
        "strict_R3B_replication_established": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
