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
    adm = evidence["admission"]
    agg = evidence["aggregate_masked_prediction"]
    analog = evidence["cross_fold_structural_analogy"]

    prereq = {
        "parent_is_v2_19_canonical": parent.get("version") == "v2.19" and parent.get("status") == "CURRENT_CANONICAL_RESEARCH_STATE",
        "evidence_status_exact": evidence.get("status") == spec["required_evidence_status"],
        "evidence_source_frozen": evidence["source"].get("frozen_commit") == "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a",
        "evaluable_masks_threshold": adm.get("actual_aggregate_evaluable_masks", 0) >= spec["required_admission"]["minimum_evaluable_masks"],
        "admission_true": adm.get("cross_validated_internal_context_structure_admitted") is True,
        "fold_robustness_threshold": adm.get("folds_where_both_context_models_beat_unigram_MRR", 0) >= spec["required_admission"]["minimum_folds_where_both_context_models_beat_unigram_MRR"],
        "replicated_pair_threshold": analog.get("CV_replicated_pair_count", 0) >= spec["required_admission"]["minimum_CV_replicated_structural_analogy_pairs"],
        "B1_MRR_beats_B0": agg["B1_DIRECTIONAL_CONTEXT_COUNT"]["mean_reciprocal_rank"] > agg["B0_UNIGRAM"]["mean_reciprocal_rank"],
        "B1_top5_beats_B0": agg["B1_DIRECTIONAL_CONTEXT_COUNT"]["top5_accuracy"] > agg["B0_UNIGRAM"]["top5_accuracy"],
        "M1_MRR_beats_B0": agg["M1_DIRECTIONAL_PPMI_SVD"]["mean_reciprocal_rank"] > agg["B0_UNIGRAM"]["mean_reciprocal_rank"],
        "M1_top5_beats_B0": agg["M1_DIRECTIONAL_PPMI_SVD"]["top5_accuracy"] > agg["B0_UNIGRAM"]["top5_accuracy"],
        "test_not_used_for_selection": evidence["leakage_firewall"].get("translations_used") is False and evidence["leakage_firewall"].get("language_dictionaries_used") is False,
        "external_blind_lane_untouched": evidence["leakage_firewall"].get("R3B_blind_eligibility_affected") is False,
        "decipherment_false_in_evidence": evidence["epistemic_gate"].get("decipherment_established") is False,
        "anchor_false_in_evidence": evidence["epistemic_gate"].get("new_anchor_established") is False,
        "R3B_false_in_evidence": evidence["epistemic_gate"].get("R3B_external_replication_established") is False,
    }
    if not all(prereq.values()):
        raise SystemExit("Promotion prerequisites failed: " + json.dumps(prereq, sort_keys=True))

    state = copy.deepcopy(parent)
    now = datetime.now(TZ).isoformat()
    state["artifact_uuid"] = "JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.20"
    state["timestamp"] = now
    state["version"] = "v2.20"
    state["title"] = "JANUS Linear A canonical state after cross-validated self-supervised structural learning"
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

    state["R4_self_supervised_discovery_lane"] = {
        "status": "CROSS_VALIDATED_INTERNAL_CONTEXT_STRUCTURE_ADMITTED",
        "R4_0": {
            "path": "data/JANUS-LINEAR-A-R4-0-SELF-SUPERVISED-STRUCTURAL-LEARNING-RESULT-2026-08-14-v0.1.1.json",
            "status": "BLOCKED_INSUFFICIENT_EVALUABLE_TEST_MASKS",
            "evaluable_masks": 41,
            "promotion_inherited": False,
        },
        "R4_1": {
            "path": spec["new_evidence"],
            "status": evidence["status"],
            "evidence_sha256": digest(spec["new_evidence"]),
            "aggregate_evaluable_masks": adm["actual_aggregate_evaluable_masks"],
            "folds_where_both_context_models_beat_unigram_MRR": adm["folds_where_both_context_models_beat_unigram_MRR"],
            "B0_UNIGRAM": agg["B0_UNIGRAM"],
            "B1_DIRECTIONAL_CONTEXT_COUNT": agg["B1_DIRECTIONAL_CONTEXT_COUNT"],
            "M1_DIRECTIONAL_PPMI_SVD": agg["M1_DIRECTIONAL_PPMI_SVD"],
            "CV_replicated_structural_analogy_pair_count": analog["CV_replicated_pair_count"],
            "CV_replicated_structural_analogies": analog["CV_replicated_pairs"],
        },
        "interpretation": "The frozen corpus contains cross-validated learnable contextual structure. Replicated analogy pairs are distributional/functional candidates only, not semantic equivalences.",
        "translation_established": False,
        "phonetic_value_established": False,
        "new_anchor_established": False,
        "decipherment_established": False,
    }

    roadmap = state.setdefault("roadmap", [])
    roadmap = [x for x in roadmap if x.get("id") not in {"R4_SELF_SUPERVISED_DISCOVERY", "R4_2_FUNCTIONAL_SUBSTITUTION_FRAMES"}]
    roadmap.append({"id": "R4_SELF_SUPERVISED_DISCOVERY", "status": "DONE_R4_1_CROSS_VALIDATED_INTERNAL_STRUCTURE_ADMITTED"})
    roadmap.append({"id": "R4_2_FUNCTIONAL_SUBSTITUTION_FRAMES", "status": "READY_NOT_EXECUTED"})
    state["roadmap"] = roadmap

    old_next = [x for x in state.get("next_atomic_requirements", []) if x.get("id") != "R4_2_FUNCTIONAL_SUBSTITUTION_FRAMES"]
    state["next_atomic_requirements"] = [
        {"id": "R4_2_FUNCTIONAL_SUBSTITUTION_FRAMES", "action": spec["next_atomic_requirement"]}
    ] + old_next

    state["global_claim_ceiling_v2_20"] = {
        "internal_context_structure_learned_cross_validated": True,
        "CV_replicated_structural_analogy_pair_count": analog["CV_replicated_pair_count"],
        "translation_established": False,
        "phonetic_value_established": False,
        "semantic_equivalence_established": False,
        "language_family_identified": False,
        "external_transcription_replication_established": False,
        "strict_R3B_replication_established": False,
        "new_anchor_established": False,
        "decipherment_established": False,
        "allowed": spec["claim_ceiling"]["allowed"],
        "forbidden": spec["claim_ceiling"]["forbidden"],
    }

    pathlib.Path(args.candidate_out).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    checks = {
        **prereq,
        "state_version_v2_20": state["version"] == "v2.20",
        "R4_status_exact": state["R4_self_supervised_discovery_lane"]["status"] == "CROSS_VALIDATED_INTERNAL_CONTEXT_STRUCTURE_ADMITTED",
        "R4_masks_509": state["R4_self_supervised_discovery_lane"]["R4_1"]["aggregate_evaluable_masks"] == 509,
        "R4_replicated_pairs_4": state["R4_self_supervised_discovery_lane"]["R4_1"]["CV_replicated_structural_analogy_pair_count"] == 4,
        "internal_structure_true": state["global_claim_ceiling_v2_20"]["internal_context_structure_learned_cross_validated"] is True,
        "translation_false": state["global_claim_ceiling_v2_20"]["translation_established"] is False,
        "semantic_false": state["global_claim_ceiling_v2_20"]["semantic_equivalence_established"] is False,
        "anchor_false": state["global_claim_ceiling_v2_20"]["new_anchor_established"] is False,
        "decipherment_false": state["global_claim_ceiling_v2_20"]["decipherment_established"] is False,
        "R3B_false": state["global_claim_ceiling_v2_20"]["strict_R3B_replication_established"] is False,
    }
    passed = all(checks.values())
    audit = {
        "artifact_uuid": "JANUS-LINEAR-A-RESEARCH-STATE-CANONICALITY-AUDIT-2026-08-14-v2.20",
        "version": "v2.20",
        "status": "CANONICALITY_AUDIT_PASS" if passed else "CANONICALITY_AUDIT_FAIL",
        "executed_at": now,
        "promotion_spec": args.spec,
        "parent_state": spec["parent_state"],
        "new_evidence": spec["new_evidence"],
        "parent_sha256": digest(spec["parent_state"]),
        "evidence_sha256": digest(spec["new_evidence"]),
        "candidate_sha256": digest(args.candidate_out),
        "checks": checks,
        "all_checks_pass": passed,
        "claim_ceiling": spec["claim_ceiling"],
    }
    pathlib.Path(args.audit_out).write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not passed:
        return 2

    state["canonicality"]["canonicality_audit_status"] = "CANONICALITY_AUDIT_PASS"
    pathlib.Path(args.canonical_out).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "CANONICAL_V2_20_READY",
        "audit": audit["status"],
        "R4_status": state["R4_self_supervised_discovery_lane"]["status"],
        "evaluable_masks": adm["actual_aggregate_evaluable_masks"],
        "CV_replicated_pairs": analog["CV_replicated_pair_count"],
        "decipherment_established": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
