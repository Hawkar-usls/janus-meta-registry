from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
from datetime import datetime, timezone, timedelta

TZ = timezone(timedelta(hours=3))


def load(path: str) -> dict:
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def digest(path: str) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--candidate-out", required=True)
    ap.add_argument("--canonical-out", required=True)
    ap.add_argument("--audit-out", required=True)
    args = ap.parse_args()

    spec = load(args.spec)
    parent = load(spec["parent_state"])
    evidence = load(spec["new_evidence"])
    req = spec["required_summary"]

    prereq = {
        "parent_is_v2_18_canonical": parent.get("version") == "v2.18" and parent.get("status") == "CURRENT_CANONICAL_RESEARCH_STATE",
        "evidence_status_exact": evidence.get("status") == spec["required_evidence_status"],
        "evidence_all_checks_pass": evidence.get("all_checks_pass") is True,
        "summary_exact": all(evidence["summary"].get(k) == v for k, v in req.items()),
        "public_absence_not_overclaimed": evidence["summary"]["public_copy_absence_proved"] is False,
        "blindness_preserved": evidence["summary"]["blind_eligibility_destroyed"] is False,
    }
    if not all(prereq.values()):
        raise SystemExit("Promotion prerequisites failed: " + json.dumps(prereq, sort_keys=True))

    state = copy.deepcopy(parent)
    now = datetime.now(TZ).isoformat()
    state["artifact_uuid"] = "JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.19"
    state["timestamp"] = now
    state["version"] = "v2.19"
    state["title"] = "JANUS Linear A canonical state after strict-blind Notti 2021/2025/PH13 acquisition frontier audit"
    state["status"] = "CURRENT_CANONICAL_RESEARCH_STATE"
    state["canonicality"] = {
        "current_source_of_truth": True,
        "parent_state": spec["parent_state"],
        "promotion_spec": args.spec,
        "promotion_prerequisites_pass": True,
        "history_is_not_deleted": True,
        "candidate_path": args.candidate_out,
        "canonicality_audit": args.audit_out,
        "canonicality_audit_status": "PENDING_UNTIL_AUDIT_EMITTED",
        "promotion_rule_satisfied": True,
    }

    lane = state.setdefault("R3B_independent_editorial_replication_lane", {})
    lane.update({
        "status": "STRICT_BLIND_ACQUISITION_FRONTIER_NEGATIVE_NO_BYTE_SEAL_BLINDNESS_PRESERVED",
        "R3B_0": "ACTIVE_BLOCKER_THREE_TARGETS_AUDITED_NO_PRECONTENT_PDF_SEAL_BLINDNESS_PRESERVED",
        "R3B_1": "READY_BUT_BLOCKED_PENDING_LAWFUL_EXACT_BYTE_SEAL_BEFORE_CONTENT_INSPECTION",
        "R3B_2": "BLOCKED",
        "R3B_3": "BLOCKED",
        "R3B_4": "BLOCKED",
        "reason": "Notti 2021, Notti 2025 and PH13 2024 were audited through IULM and external publisher routes without exposing source-native readings. No lawful unauthenticated exact PDF byte seal was obtained. Notti 2018 remains a nonblind corrective control only."
    })

    state["R3B_strict_blind_acquisition_frontier"] = {
        "status": evidence["status"],
        "audit": spec["new_evidence"],
        "audit_sha256": digest(spec["new_evidence"]),
        "candidate_count": 3,
        "sealed_candidate_count": 0,
        "candidate_terminal": evidence["candidate_terminal"],
        "source_native_sign_readings_seen": False,
        "source_content_inspected": False,
        "overlap_selected": False,
        "strict_r3b_replication_established": False,
        "blind_eligibility_preserved": True,
        "public_copy_absence_proved": False,
        "Notti_2018_nonblind_control_unchanged": True,
        "forbidden_routes": evidence["forbidden_routes"],
    }

    for item in state.get("roadmap", []):
        if item.get("id") == "R3B_0_SOURCE_ACQUISITION":
            item["status"] = "ACTIVE_BLOCKER_STRICT_BLIND_ROUTES_AUDITED_NO_BYTE_SEAL_BLINDNESS_PRESERVED"
        elif item.get("id") == "R3B_1_OVERLAP_FREEZE":
            item["status"] = "READY_BUT_FORBIDDEN_UNTIL_EXACT_PRECONTENT_BYTE_SEAL"

    state["next_atomic_requirements"] = [
        {
            "id": "P0_NEW_LAWFUL_EXACT_BYTE_ROUTE_OR_USER_SUPPLIED_COPY",
            "action": spec["next_atomic_requirement"]
        },
        {
            "id": "P1_POST_SEAL_SOURCE_NATIVE_OVERLAP_FREEZE",
            "action": "Only after a byte receipt is persisted, inspect that exact sealed source in a separately frozen gate and freeze all source-native overlap before any agreement scoring."
        }
    ] + [x for x in parent.get("next_atomic_requirements", []) if x.get("id") not in {"P0_STRICT_NOTTI_THERA_OR_PH13_BYTE_ACQUISITION", "P0_RILA_S1_BYTE_ACQUISITION"}]

    state["global_claim_ceiling_v2_19"] = {
        "external_transcription_replication_established": False,
        "strict_R3B_replication_established": False,
        "new_anchor_established": False,
        "decipherment_established": False,
        "public_copy_absence_proved": False,
        "allowed": spec["claim_ceiling"]["allowed"],
        "forbidden": spec["claim_ceiling"]["forbidden"],
    }

    candidate_path = pathlib.Path(args.candidate_out)
    candidate_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    audit_checks = {
        **prereq,
        "state_version_v2_19": state["version"] == "v2.19",
        "frontier_status_exact": state["R3B_strict_blind_acquisition_frontier"]["status"] == "STRICT_BLIND_ACQUISITION_FRONTIER_NEGATIVE_BLINDNESS_PRESERVED",
        "sealed_zero": state["R3B_strict_blind_acquisition_frontier"]["sealed_candidate_count"] == 0,
        "blind_preserved": state["R3B_strict_blind_acquisition_frontier"]["blind_eligibility_preserved"] is True,
        "strict_r3b_false": state["global_claim_ceiling_v2_19"]["strict_R3B_replication_established"] is False,
        "anchor_false": state["global_claim_ceiling_v2_19"]["new_anchor_established"] is False,
        "decipherment_false": state["global_claim_ceiling_v2_19"]["decipherment_established"] is False,
        "absence_false": state["global_claim_ceiling_v2_19"]["public_copy_absence_proved"] is False,
        "overlap_gate_stays_blocked": any(x.get("id") == "R3B_1_OVERLAP_FREEZE" and "FORBIDDEN_UNTIL_EXACT_PRECONTENT_BYTE_SEAL" in x.get("status", "") for x in state.get("roadmap", [])),
    }
    passed = all(audit_checks.values())
    audit = {
        "artifact_uuid": "JANUS-LINEAR-A-RESEARCH-STATE-CANONICALITY-AUDIT-2026-08-14-v2.19",
        "version": "v2.19",
        "status": "CANONICALITY_AUDIT_PASS" if passed else "CANONICALITY_AUDIT_FAIL",
        "executed_at": now,
        "promotion_spec": args.spec,
        "parent_state": spec["parent_state"],
        "new_evidence": spec["new_evidence"],
        "parent_sha256": digest(spec["parent_state"]),
        "evidence_sha256": digest(spec["new_evidence"]),
        "candidate_sha256": digest(args.candidate_out),
        "checks": audit_checks,
        "all_checks_pass": passed,
        "claim_ceiling": spec["claim_ceiling"],
    }
    pathlib.Path(args.audit_out).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not passed:
        return 2

    state["canonicality"]["canonicality_audit_status"] = "CANONICALITY_AUDIT_PASS"
    canonical_path = pathlib.Path(args.canonical_out)
    canonical_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "CANONICAL_V2_19_READY", "audit": audit["status"], "sealed_candidate_count": 0, "blind_eligibility_preserved": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
