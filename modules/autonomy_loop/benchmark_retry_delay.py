"""Run one frozen JANUS retry-delay benchmark INSIDE the networkless Coder sandbox.

This script executes reviewed candidate bytes ONLY in an isolated pinned Docker
container. Its output is a measurement, not independent proof or authorization.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
from time import perf_counter_ns

BASE = Path(__file__).resolve().parents[2]
CODER = BASE / "modules" / "autonomy_coder"
sys.path.insert(0, str(CODER))
from checker import cases as oracle_cases
from policy import validate_source
from modules.autonomy_loop.candidate_preflight import preflight
from modules.autonomy_loop.proof_of_improvement import digest, validate_protocol

FOLDER = BASE / "experiments" / "closed_loop_retry_delay_r1"
EXPECTED_PROTOCOL = "05b54d4ff49d836c212a6d53228cc72b2d5ba5120279ac2d8446a879e9d25156"
CANDIDATE_COMMIT = "2652dd70d8f65385316cd309d4a74db2b948dc46"
CANDIDATE_SHA256 = "a45bf9b5814e432a89334e46f8acac63a9fa1d2846dc393ed21e6dd6695b2611"
MEASUREMENT_SCHEMA = "janus.closed_loop.improvement_measurement.v1"
EVIDENCE_SCHEMA = "janus.closed_loop.retry_delay_trial.v1"
REPETITIONS = 40000
ROUNDS = 5


def check_json(path):
    data = path.read_bytes()
    if len(data) > 20000:
        raise ValueError("INPUT_JSON_SIZE")
    return json.loads(data)


def loaded_function(source, name):
    namespace = {"__builtins__": {"min": min, "pow": pow}}
    exec(compile(source, name + ".py", "exec"), namespace)
    return namespace["retry_delay"]


def timed(fn, args, expected):
    start = perf_counter_ns()
    result = None
    for _ in range(REPETITIONS):
        result = fn(*args)
    elapsed = perf_counter_ns() - start
    if result != expected or type(result) is not int:
        raise ValueError("TIMED_REPLAY_BEHAVIOR_DRIFT")
    return elapsed / REPETITIONS / 1000.0


def compare_case(baseline, candidate, args):
    expected = min(args[1], 2 ** args[0])
    # Warm-up is never scored.
    for fn in (baseline, candidate):
        for _ in range(1000):
            if fn(*args) != expected:
                raise ValueError("HOLDOUT_BEHAVIOR_DRIFT")
    a, b = [], []
    for round_idx in range(ROUNDS):
        # Alternate order to reduce systematic first/second-run skew.
        if round_idx % 2:
            b.append(timed(candidate, args, expected))
            a.append(timed(baseline, args, expected))
        else:
            a.append(timed(baseline, args, expected))
            b.append(timed(candidate, args, expected))
    return round(statistics.median(a), 9), round(statistics.median(b), 9)


def run(candidate_root: Path, evaluator_commit: str, run_id: str):
    if len(evaluator_commit) != 40 or any(x not in "0123456789abcdef" for x in evaluator_commit):
        raise ValueError("UNPINNED_EVALUATOR_COMMIT")
    if not run_id.isdigit():
        raise ValueError("UNPINNED_RUN_ID")
    protocol = check_json(FOLDER / "PROTOCOL.json")
    if validate_protocol(protocol) != EXPECTED_PROTOCOL:
        raise ValueError("FROZEN_PROTOCOL_CHANGED")
    train = check_json(FOLDER / "TRAIN_MANIFEST.json")
    holdout = check_json(FOLDER / "HOLDOUT_MANIFEST.json")
    if (digest(train) != protocol["train_manifest_sha256"] or
            digest(holdout) != protocol["holdout_manifest_sha256"]):
        raise ValueError("MANIFEST_BINDING_CHANGED")
    if (train.get("schema") != "janus.closed_loop.retry_delay_train_manifest.v1" or
            holdout.get("schema") != "janus.closed_loop.retry_delay_holdout_manifest.v1" or
            train.get("task_id") != "retry_delay" or holdout.get("task_id") != "retry_delay"):
        raise ValueError("MANIFEST_SCHEMA")
    training = train["cases"]
    unseen = holdout["cases"]
    if (len(training) != 91 or len(unseen) != len(protocol["case_ids"]) or
            [x["case_id"] for x in unseen] != protocol["case_ids"]):
        raise ValueError("UNFROZEN_CASE_SELECTION")
    seen_input = {(x["attempt"], x["cap"]) for x in training}
    holdout_input = [(x["attempt"], x["cap"]) for x in unseen]
    if (len(seen_input) != len(training) or len(set(holdout_input)) != len(unseen) or
            any(x in seen_input for x in holdout_input) or
            any(type(a) is not int or not 0 <= a <= 12 or
                type(c) is not int or not 1 <= c <= 900
                for a, c in seen_input | set(holdout_input))):
        raise ValueError("HOLDOUT_LEAKAGE_OR_DOMAIN")
    base_source = (FOLDER / "BASELINE.py").read_bytes()
    if hashlib.sha256(base_source).hexdigest() != protocol["baseline_sha256"]:
        raise ValueError("BASELINE_SOURCE_CHANGED")
    source_file = candidate_root / "candidate_modules" / "retry_delay" / "module.py"
    proposal_file = candidate_root / "candidate_modules" / "retry_delay" / "PROPOSAL.json"
    source_bytes = source_file.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != CANDIDATE_SHA256:
        raise ValueError("CANDIDATE_CODE_CHANGED")
    proposal = check_json(proposal_file)
    preflight_proof = preflight(proposal, source_bytes.decode(), source_commit=CANDIDATE_COMMIT)
    # Candidate source policy is reviewed and checked before exec.
    validate_source(source_bytes.decode(), "retry_delay")
    baseline = loaded_function(base_source.decode(), "frozen_reference")
    candidate = loaded_function(source_bytes.decode(), "reviewed_model_candidate")
    # Reproduce exactly the existing 291-case Coder oracle, then check the
    # separately frozen train and holdout inputs for both source versions.
    oracle = oracle_cases("retry_delay", "janus-closed-loop-retry-r1-frozen")
    if len(oracle) != 291:
        raise ValueError("CODER_ORACLE_CASE_COUNT_CHANGED")
    for args, expected in oracle:
        for fn in (baseline, candidate):
            if fn(*args) != expected:
                raise ValueError("CODER_ORACLE_FAILED")
    for row in training + unseen:
        args = (row["attempt"], row["cap"])
        expected = min(args[1], 2 ** args[0])
        for fn in (baseline, candidate):
            if fn(*args) != expected:
                raise ValueError("FROZEN_BEHAVIOR_FAILED")
    rows = []
    was_enabled = gc.isenabled()
    try:
        gc.disable()
        for row in unseen:
            base_time, cand_time = compare_case(
                baseline, candidate, (row["attempt"], row["cap"]))
            rows.append({"case_id": row["case_id"],
                         "baseline": base_time, "candidate": cand_time})
    finally:
        if was_enabled:
            gc.enable()
    measurement = {
        "schema": MEASUREMENT_SCHEMA,
        "protocol_sha256": EXPECTED_PROTOCOL,
        "candidate_sha256": CANDIDATE_SHA256,
        "evaluator_commit": evaluator_commit,
        "case_rows": rows,
        "authority_delta": 0,
    }
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "experiment": "retry_delay_r1_reference_vs_model_candidate",
        "github_run_id": run_id,
        "evaluator_commit": evaluator_commit,
        "candidate_source_commit": CANDIDATE_COMMIT,
        "candidate_preflight_sha256": preflight_proof["receipt_sha256"],
        "protocol_sha256": EXPECTED_PROTOCOL,
        "baseline_source_sha256": protocol["baseline_sha256"],
        "candidate_source_sha256": CANDIDATE_SHA256,
        "train_manifest_sha256": protocol["train_manifest_sha256"],
        "holdout_manifest_sha256": protocol["holdout_manifest_sha256"],
        "verified_train_holdout_disjoint": True,
        "coder_oracle_cases_per_variant": 291,
        "frozen_training_cases_per_variant": len(training),
        "frozen_holdout_cases_per_variant": len(unseen),
        "paired_cases": len(rows),
        "timing_repetitions_per_round": REPETITIONS,
        "timing_rounds": ROUNDS,
        "timing_statistic": "median_us_per_function_call",
        "comparison_scope": "FROZEN_REFERENCE_NOT_PRODUCTION_BASELINE",
        "execution_scope": "ISOLATED_DOCKER_NO_NETWORK",
        "independent_replay_attested": False,
        "runtime_consumption_attested": False,
        "promotion": False,
        "authority_delta": 0,
        "measurement": measurement,
    }
    evidence["evidence_sha256"] = digest(evidence)
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--evaluator-commit", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    proof = run(args.candidate_root, args.evaluator_commit, args.run_id)
    print(json.dumps(proof, sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
