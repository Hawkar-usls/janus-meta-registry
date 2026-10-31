#!/usr/bin/env python3
"""Read-only, fail-closed integrity checks for SAT_REPRODUCIBILITY_001.

Validation of an internal DRAFT is NOT proof of a historical SAT experiment,
custodian independence, benchmark correctness or prospective freeze.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "data/sat_reproducibility/SAT_REPRODUCIBILITY_001.json"
EXPECTED_NS = (220, 225, 230, 235, 240)
EXPECTED_RATIOS = (4.0, 4.267, 4.5)
EXPECTED_COUNTS = {"L1": 300, "L2": 600, "L3": 600, "total": 1500}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def unique_keys(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=unique_keys,
                      parse_constant=lambda s: (_ for _ in ()).throw(
                          ValueError(f"non-finite JSON number: {s}")))


def is_sha(x):
    return isinstance(x, str) and bool(SHA256.fullmatch(x))


def valid_v1(p: dict) -> list[str]:
    problems = []

    def require(ok, label):
        if not ok:
            problems.append(label)

    if not isinstance(p, dict):
        return ["NOT_OBJECT"]
    require(p.get("schema_id") == "janus.sat_reproducibility.preregistration.v1", "BAD_SCHEMA")
    require(p.get("experiment_id") == "SAT_REPRODUCIBILITY_001", "BAD_EXPERIMENT")
    lifecycle = p.get("lifecycle")
    require(lifecycle in ("DRAFT_NOT_FROZEN", "PREREG_FROZEN"), "BAD_LIFECYCLE")
    hypotheses = p.get("hypotheses", [])
    require(isinstance(hypotheses, list) and
            [x.get("id") for x in hypotheses if isinstance(x, dict)] == ["L1", "L2", "L3"],
            "MISSING_HYPOTHESES")
    design = p.get("instance_design", {})
    require(design.get("n_variables") == list(EXPECTED_NS), "VARIABLE_GRID_CHANGED")
    require(design.get("clause_variable_ratios") == list(EXPECTED_RATIOS),
            "DENSITY_GRID_CHANGED")
    cells = design.get("strata", [])
    require(isinstance(cells, list) and len(cells) == 15, "STRATA_COUNT")
    seen = set()
    sums = {"L1": 0, "L2": 0, "L3": 0}
    if isinstance(cells, list):
        for cell in cells:
            if not isinstance(cell, dict):
                problems.append("INVALID_CELL")
                continue
            pair = (cell.get("n_variables"), cell.get("ratio"))
            require(pair in {(n, d) for n in EXPECTED_NS for d in EXPECTED_RATIOS}
                    and pair not in seen, "DUPLICATE_OR_INVALID_CELL")
            seen.add(pair)
            for key, count in (("L1", 20), ("L2", 40), ("L3", 40)):
                n = cell.get(key)
                require(type(n) is int and n == count, f"BAD_COUNT_{key}")
                if type(n) is int:
                    sums[key] += n
    require(len(seen) == 15, "INCOMPLETE_GRID")
    counts = design.get("planned_counts")
    require(counts == EXPECTED_COUNTS, "PROPOSED_SAMPLE_COUNT_CHANGED")
    require(sums == {k: EXPECTED_COUNTS[k] for k in sums}, "STRATA_SUM_MISMATCH")
    require([x.get("designated_n") for x in hypotheses if isinstance(x, dict)] ==
            [300, 600, 600], "HYPOTHESIS_N_MISMATCH")

    historic = p.get("historic_claim", {})
    require(historic.get("epistemic_status") == "UNVERIFIED_HISTORICAL_CLAIM",
            "HISTORICAL_CLAIM_PROMOTED")
    require(historic.get("performance_data_verified") is False,
            "FALSE_HISTORICAL_PERFORMANCE_VERIFICATION")
    original = historic.get("archived_microgpt", {})
    require(original.get("relationship_to_historical_sat_solver") == "NOT_ESTABLISHED",
            "MICROGPT_FALSE_SAT_BINDING")
    require(original.get("production_runtime_active") is False and
            original.get("never_unpickle_untrusted_models") is True,
            "UNSAFE_MICROGPT_PROMOTION")
    require(is_sha(original.get("nas_original_sha256")), "MISSING_NAS_SOURCE_HASH")

    modes = p.get("solver_modes", {})
    complete = modes.get("complete_sat_unsat", {})
    search = modes.get("sat_witness_search", {})
    require(complete.get("required_for_unsat") is True and
            search.get("required_for_unsat") is False and
            modes.get("compare_across_modes") is False and
            modes.get("scoring_requires_same_mode") is True,
            "SAT_UNSAT_MODE_CONFLATION")

    metrics = p.get("metrics", {})
    require(metrics.get("minimum_practical_reduction") == 0.05, "EFFECT_MARGIN_CHANGED")
    require("2*T" in metrics.get("primary_L2", ""), "PAR2_TIMEOUT_RULE_MISSING")
    require("cluster bootstrap" in metrics.get("interval", ""),
            "INSTANCE_CLUSTERING_MISSING")
    require(metrics.get("missing_and_timeout_policy", "").find("2*T") >= 0,
            "MISSING_HARD_CASES")
    training = p.get("training", {})
    require(training.get("train_seeds_required_minimum", 0) >= 3 and
            training.get("solver_seeds_per_version_required", 0) >= 5 and
            training.get("no_access_to_L2_or_L3_instances_during_training") is True,
            "TRAINING_HOLDOUT_LEAK")
    require(training.get("promotion_to_production") == "BLOCKED_IN_THIS_EXPERIMENT",
            "UNAUTHORIZED_PRODUCTION_PROMOTION")
    contract = p.get("evidence_contract", {})
    require(contract.get("append_only_negative_and_positive_equal_discoverability") is True and
            contract.get("no_silent_result_deletion") is True and
            contract.get("no_posthoc_selection") is True,
            "NEGATIVE_EVIDENCE_NOT_PRESERVED")
    require(contract.get("sample_results_present") is False, "PREMATURE_RESULT_CLAIM")
    required_run = set(contract.get("run_required", []))
    require({"instance_sha256", "verdict", "verification_status",
             "failure_reason", "receipt_sha256", "solver_seed",
             "environment_digest"} <= required_run, "RECEIPT_PROVENANCE_MISSING")
    require(p.get("independence", {}).get("scientific_authority_delta") == 0 and
            p.get("independence", {}).get("paid_compute_authority_delta") == 0 and
            p.get("independence", {}).get("mainline_model_promotion_authority_delta") == 0,
            "AUTHORITY_ESCALATION")
    custody = p.get("blind_custody", {})
    require(custody.get("no_candidate_access_to_private_seeds_cnf_labels_or_solver_logs") is True
            and custody.get("single_public_hash_not_sufficient_for_independence") is True
            and custody.get("no_synthetic_public_test_masquerading_as_blind") is True,
            "BLIND_CUSTODY_BYPASS")

    gate = p.get("freeze_gate", {})
    require("P_EQUALS_NP_PROVEN" in gate.get("forbidden_claims", []),
            "P_NP_FALSE_PROMOTION")
    reqs = gate.get("requirements", [])
    require(isinstance(reqs, list) and len(reqs) >= 7, "INCOMPLETE_FREEZE_GATE")

    if lifecycle == "DRAFT_NOT_FROZEN":
        require(gate.get("status") == "BLOCKED_NOT_FROZEN" and
                gate.get("satisfied") == [], "DRAFT_WRONGLY_FROZEN")
        require(p.get("registered_immutable_prereg_sha256") is None,
                "FALSE_IMMUTABLE_REGISTRATION")
        for key in ("custodian_id", "custodian_key_fingerprint",
                    "public_precommit_manifest_sha256",
                    "private_dataset_manifest_sha256", "sealed_creation_utc",
                    "frozen_candidate_submission_utc", "reveal_utc"):
            require(custody.get(key) is None, f"DRAFT_FAKE_CUSTODY_{key}")
        require(custody.get("custody_status") == "UNASSIGNED_UNSEALED",
                "DRAFT_FAKE_SEAL")
        for key in ("generator_commit", "generator_sha256",
                    "seed_manifest_private_sha256", "public_instance_manifest_sha256",
                    "pilot_power_analysis"):
            require(design.get(key) is None, f"DRAFT_FAKE_GENERATOR_{key}")
        for key in ("frozen_before_sha256", "frozen_after_sha256"):
            require(training.get(key) is None, f"DRAFT_FAKE_MODEL_{key}")
    elif lifecycle == "PREREG_FROZEN":
        # A future freeze is only eligible for separate external audit: this
        # syntactic gate cannot attest who had access to the blind corpus.
        require(gate.get("status") == "FROZEN_EXTERNAL_REVIEW_REQUIRED",
                "UNREVIEWED_FREEZE")
        require(set(reqs) <= set(gate.get("satisfied", [])), "FREEZE_REQUIREMENTS_UNMET")
        for value in (p.get("registered_immutable_prereg_sha256"),
                      custody.get("public_precommit_manifest_sha256"),
                      custody.get("private_dataset_manifest_sha256"),
                      design.get("generator_sha256"),
                      training.get("frozen_before_sha256"),
                      training.get("frozen_after_sha256")):
            require(is_sha(value), "FROZEN_MISSING_SHA256")
        require(custody.get("custodian_id") not in (None, "", "UNAPPOINTED")
                and custody.get("custodian_key_fingerprint") is not None,
                "FROZEN_WITHOUT_INDEPENDENT_CUSTODIAN")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=DEFAULT)
    args = parser.parse_args()
    try:
        problems = valid_v1(read(args.path))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"SAT_PREREG_INTEGRITY=FAIL: {type(exc).__name__}: {exc}")
        return 1
    if problems:
        print("SAT_PREREG_INTEGRITY=FAIL: " + ",".join(sorted(set(problems))))
        return 1
    print("SAT_PREREG_INTEGRITY=PASS_DRAFT_ONLY_NOT_SCIENTIFIC_VALIDATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
