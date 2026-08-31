#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

RECEIPT_SCHEMA = "janus.trump.slime_r6_1_regret_bounded_exploration.frozen_pass_receipt.v1"
REGISTRY_ID = "JANUS-TRUMP-R6-1-REGRET-BOUNDED-EXPLORATION-SCOPED-PASS-2026-08-31-v1.0"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--demiurge-main", required=True)
    ap.add_argument("--receipt-blob", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    if receipt.get("schema") != RECEIPT_SCHEMA:
        raise SystemExit("R6_1_RECEIPT_SCHEMA_DRIFT")
    if receipt.get("status") != "CANONICAL_FROZEN_SCOPED_PASS_RECEIPT":
        raise SystemExit("R6_1_RECEIPT_NOT_CANONICAL_PASS")
    if receipt.get("P_VS_NP") != "OPEN":
        raise SystemExit("R6_1_P_VS_NP_BOUNDARY_DRIFT")
    if not all(receipt["frozen_result"]["gate"].values()):
        raise SystemExit("R6_1_RECEIPT_GATE_NOT_ALL_TRUE")

    meta = {
        "schema": "JANUS/meta/trump-r6-1-regret-bounded-exploration-scoped-pass/v1.0.0",
        "registry_id": REGISTRY_ID,
        "created_at": "2026-08-31",
        "status": "CANONICAL_FROZEN_SCOPED_PASS__REGRET_BOUNDED_M2R_ONLINE_WORK_REDUCTION__P_VS_NP_OPEN",
        "purpose": "Preserve the exact artifact-derived R6.1 result in JANUS memory: the unchanged R6 receipt-grounded Keymaster/M2R machinery regained scoped online exact-R5 work reduction on a fresh frozen same-family mix when the only successor change was a preregistered 1.25 predicted-regret guard on deterministic exploration alternates.",
        "runtime_receipt": {
            "repository": "Hawkar-usls/Janus-Demiurge",
            "main_commit_observed": args.demiurge_main,
            "path": "trump/TRUMP_SLIME_R6_1_REGRET_BOUNDED_EXPLORATION_FROZEN_PASS_RECEIPT_2026-08-31.json",
            "git_blob_sha": args.receipt_blob,
            "runtime_main_commit": receipt["runtime_main_commit"],
            "status": receipt["status"],
            "P_VS_NP": receipt["P_VS_NP"],
        },
        "lineage": {
            "R5_evidence_closure_meta_commit": "9e27e20d1352df6e1c399e9fe69518968f5729bc",
            "R6_negative_runtime_commit": "caef1bd347da69e2d4a66a6adcb914677ce1d3bb",
            "R6_negative_meta_commit": "9ed01c52d966c272ccc118de8b0187505ecb407a",
            "R6_negative_diagnosis": "Unconditional exact execution of supported diversity alternates on deterministic exploration triggers dominated online regret while exact coverage and aggregate M2R memory survived.",
            "R6_1_single_successor_change": receipt["freeze"]["single_successor_change"],
            "base_R6_code_provenance": receipt["freeze"]["base_R6_code_provenance"],
        },
        "provenance": receipt["provenance"],
        "memory": receipt["memory"],
        "frozen_result": receipt["frozen_result"],
        "supported_claim": receipt["supported_claim"],
        "supported_interpretation": receipt["supported_interpretation"],
        "authority": receipt["authority"],
        "scientific_boundary": receipt["scientific_boundary"],
        "explicit_nonclaims": receipt["explicit_nonclaims"],
        "updated_TRUMP_frontier": {
            "R5_exact_decomposition": "SCOPED_SAT_AND_UNSAT_RESCUE_EVIDENCE_CLOSED_WITH_CAUSAL_HASH_CONS_REPEATED_SUBTREE_SAVING",
            "R6_unbounded_exploration": "FROZEN_NEGATIVE",
            "R6_1_regret_bounded_receipt_memory": "FROZEN_SCOPED_PASS",
            "known_GT8_resource_frontier": "OPEN",
            "next_optional_gate": "R7_NEURAL_PIVOT_SLIME_TEACHER_STUDENT_ADVISORY_ROUTING",
            "R7_release_state": "MAY_BE_FROZEN_AS_A_SEPARATE_EXPERIMENT__NOT_DEPLOYED",
            "R7_minimum_constitution": [
                "teacher/student predictions have zero proof authority",
                "R6.1 aggregate-memory route remains an exact advisory baseline/fallback",
                "training/calibration work is fully charged and reported",
                "no same-holdout or same-theorem-face learning",
                "numeric pivot IDs remain witness-local only",
                "exact R5 split verification and decisive receipt replay remain authority",
                "PASS must show added value over frozen R6.1, not merely over raw R5",
                "OPEN remains neutral evidence"
            ]
        },
        "law": "R6_1_PASS_ESTABLISHES_SCOPED_ONLINE_WORK_REDUCTION_FOR_RECEIPT_GROUNDED_M2R_WITH_REGRET_BOUNDED_EXPLORATION__NOT_GENERAL_OR_AMORTIZED_SPEEDUP__NEURAL_PIVOT_SLIME_REMAINS_A_SEPARATE_FUTURE_GATE__P_VS_NP_OPEN"
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
