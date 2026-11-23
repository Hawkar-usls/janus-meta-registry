"""Offline, repeatable integrity verification of JANUS R1.2 trial receipts.

Does not rerun CPU timing, trust metadata as scientific proof, use network, or
grant model/code promotion. This replays source bindings and verdict arithmetic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from modules.autonomy_loop.proof_of_improvement import digest, screen, validate_protocol

FOLDER = ROOT / "experiments/closed_loop_retry_delay_r1"
SOURCE_COMMIT = "2652dd70d8f65385316cd309d4a74db2b948dc46"
FROZEN_PROTOCOL_COMMIT = "4e688f25c96590e1b70062bc336d84aba728e49e"
PROTOCOL_SHA = "05b54d4ff49d836c212a6d53228cc72b2d5ba5120279ac2d8446a879e9d25156"
SOURCE_SHA = "a45bf9b5814e432a89334e46f8acac63a9fa1d2846dc393ed21e6dd6695b2611"
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class Hold(ValueError):
    pass


def _load(path):
    p = Path(path)
    if not p.is_file() or p.stat().st_size > 150_000:
        raise Hold("RECEIPT_FILE_UNAVAILABLE")
    return json.loads(p.read_bytes())


def verify(receipt, *, protocol, baseline, training, holdout):
    if (not isinstance(receipt, dict) or
            receipt.get("schema") != "janus.closed_loop.source_bound_run_receipt.v1" or
            receipt.get("evidence_state") != "SOURCE_BOUND_SINGLE_RUN_MEASUREMENT_NO_INDEPENDENT_REPLAY" or
            receipt.get("frozen_protocol_commit") != FROZEN_PROTOCOL_COMMIT or
            receipt.get("frozen_protocol_sha256") != PROTOCOL_SHA):
        raise Hold("RECEIPT_IDENTITY")
    if validate_protocol(protocol) != PROTOCOL_SHA:
        raise Hold("FROZEN_PROTOCOL_CHANGED")
    if hashlib.sha256(baseline).hexdigest() != protocol["baseline_sha256"]:
        raise Hold("BASELINE_SOURCE_REBOUND")
    if digest(training) != protocol["train_manifest_sha256"] or digest(holdout) != protocol["holdout_manifest_sha256"]:
        raise Hold("MANIFEST_REBOUND")
    if (len(training.get("cases", [])) != 91 or
            len(holdout.get("cases", [])) != len(protocol["case_ids"]) or
            [r.get("case_id") for r in holdout["cases"]] != protocol["case_ids"]):
        raise Hold("CASE_MANIFEST_REBOUND")
    train_inputs = {(r["attempt"], r["cap"]) for r in training["cases"]}
    held_inputs = {(r["attempt"], r["cap"]) for r in holdout["cases"]}
    if len(train_inputs) != len(training["cases"]) or len(held_inputs) != len(holdout["cases"]) or train_inputs & held_inputs:
        raise Hold("TRAIN_HOLDOUT_NOT_DISJOINT")
    run = receipt.get("source_run", {})
    artifact = receipt.get("source_artifact", {})
    trial = receipt.get("trial", {})
    stored_screen = receipt.get("screen", {})
    review = receipt.get("review", {})
    run_id = run.get("id")
    if (type(run_id) is not int or run_id < 1 or
            run.get("repository") != "Hawkar-usls/janus-meta-registry" or
            run.get("event") != "pull_request" or
            run.get("status") != "completed" or
            run.get("conclusion") != "success" or
            not isinstance(run.get("source_head_sha"), str) or
            not FULL_SHA.fullmatch(run["source_head_sha"]) or
            run.get("url") != f"https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/{run_id}" or
            not isinstance(run.get("source_job_id"), int)):
        raise Hold("RUN_PROVENANCE_INVALID")
    if (artifact.get("name") != f"janus-retry-delay-reference-trial-{run_id}" or
            not isinstance(artifact.get("archive_sha256"), str) or
            not artifact["archive_sha256"].startswith("sha256:") or
            not SHA256.fullmatch(artifact["archive_sha256"][7:]) or
            artifact.get("api_url") !=
            f"https://api.github.com/repos/Hawkar-usls/janus-meta-registry/actions/artifacts/{artifact.get('id')}"):
        raise Hold("ARTIFACT_PROVENANCE_INVALID")
    if (trial.get("schema") != "janus.closed_loop.retry_delay_trial.v1" or
            trial.get("github_run_id") != str(run_id) or
            trial.get("candidate_source_commit") != SOURCE_COMMIT or
            trial.get("candidate_source_sha256") != SOURCE_SHA or
            trial.get("protocol_sha256") != PROTOCOL_SHA or
            trial.get("baseline_source_sha256") != protocol["baseline_sha256"] or
            trial.get("train_manifest_sha256") != protocol["train_manifest_sha256"] or
            trial.get("holdout_manifest_sha256") != protocol["holdout_manifest_sha256"] or
            trial.get("execution_scope") != "ISOLATED_DOCKER_NO_NETWORK" or
            trial.get("comparison_scope") != "FROZEN_REFERENCE_NOT_PRODUCTION_BASELINE" or
            trial.get("verified_train_holdout_disjoint") is not True or
            trial.get("coder_oracle_cases_per_variant") != 291 or
            trial.get("frozen_training_cases_per_variant") != 91 or
            trial.get("frozen_holdout_cases_per_variant") != 8 or
            trial.get("paired_cases") != 8 or
            trial.get("timing_rounds") != 5 or
            trial.get("timing_repetitions_per_round") != 40000 or
            trial.get("independent_replay_attested") is not False or
            trial.get("runtime_consumption_attested") is not False or
            trial.get("promotion") is not False or
            trial.get("authority_delta") != 0):
        raise Hold("TRIAL_SCOPE_CHANGED")
    if (not isinstance(trial.get("evidence_sha256"), str) or
            trial["evidence_sha256"] != digest({k:v for k,v in trial.items() if k != "evidence_sha256"})):
        raise Hold("TRIAL_DIGEST_CHANGED")
    measurement = trial.get("measurement")
    if not isinstance(measurement, dict) or measurement.get("evaluator_commit") != trial.get("evaluator_commit"):
        raise Hold("EVALUATOR_REBOUND")
    if trial.get("candidate_preflight_sha256") is None or not SHA256.fullmatch(trial["candidate_preflight_sha256"]):
        raise Hold("MISSING_PREFLIGHT_DIGEST")
    calculated = screen(protocol, measurement)
    if calculated != stored_screen:
        raise Hold("SCREEN_REPLAY_MISMATCH")
    if (review.get("mode") != "DRAFT_ONLY" or
            review.get("runtime_install") is not False or
            review.get("auto_merge") is not False or
            review.get("independent_replay_attested") is not False or
            review.get("production_baseline_attested") is not False or
            review.get("authority_delta") != 0 or
            review.get("scientific_promotion") is not False):
        raise Hold("REVIEW_AUTHORITY_CHANGED")
    return {
        "schema": "janus.closed_loop.recorded_receipt_verification.v1",
        "status": "PASS_SOURCE_BOUND_SCREEN_REPLAY_ONLY",
        "github_run_id": run_id,
        "receipt_sha256": digest(receipt),
        "measured_screen_status": calculated["status"],
        "case_count": calculated["case_count"],
        "regressions": calculated["regressions"],
        "mean_paired_gain_us": calculated["mean_paired_gain"],
        "independent_timing_replay_attested": False,
        "production_baseline_attested": False,
        "runtime_consumption_attested": False,
        "authority_delta": 0,
    }


def verify_all(root=FOLDER):
    protocol = _load(root / "PROTOCOL.json")
    train = _load(root / "TRAIN_MANIFEST.json")
    holdout = _load(root / "HOLDOUT_MANIFEST.json")
    baseline = (root / "BASELINE.py").read_bytes()
    paths = sorted((root / "receipts").glob("github-run-*.json"))
    if not paths or len(paths) > 32:
        raise Hold("RECEIPT_COUNT")
    records = [verify(_load(p), protocol=protocol, baseline=baseline,
                      training=train, holdout=holdout) for p in paths]
    if len({r["github_run_id"] for r in records}) != len(records):
        raise Hold("DUPLICATE_RUN_RECEIPTS")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=FOLDER)
    args = parser.parse_args()
    try:
        rows = verify_all(args.root)
    except (Hold, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        print(json.dumps({"status":"HOLD_INVALID_RECEIPT","authority_delta":0}))
        return 2
    print(json.dumps({"status":"PASS_SOURCE_BOUND_SCREEN_REPLAY_ONLY",
                      "receipt_count":len(rows),"runs":rows,
                      "independent_timing_replay_attested":False,
                      "authority_delta":0},sort_keys=True,allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
