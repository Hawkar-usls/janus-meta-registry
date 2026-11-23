"""Source-pinned R1.4 read-only profiling of the actual JANUS is_fresh path.

Executed only in a GitHub PR job with the pinned real model in JANUS's
pre-existing networkless Docker oracle. This is baseline profiling, NOT a
model/candidate optimization or an external independent timing attestation.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import sys
import time
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
CONSUMER = ROOT / "modules/autonomy_coder/real_operational_consumer.py"
FOLDER = ROOT / "experiments/closed_loop_is_fresh_r14"
STATE_SHA = "ccb2f82edb0f1c61c460aa0a4521a9991e8d5eb2"
ORIGINAL_MAIN_SHA = "a44942be5ed510d2aa58c4c3d33b580d771c29b8"
PREREGISTRATION_SHA = "6200377978184360868c0f328adcc1b95f1f56c8"
SOURCE_BLOB_SHA = "c787f96523442cf314f2327bf57af658a06e1a47"
MODEL_SOURCE_SHA = "30a35a12b9c864af6ff066fe30dd94ece681e81fa6e8b95c3c4a43dc3fd9c5a2"
DOCKER_IMAGE = "python@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b"

sys.path.insert(0, str(ROOT / "modules/autonomy_coder"))
import real_operational_consumer as consumer
from lifecycle import isolated_check


class EvidenceHold(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(path, max_bytes=100_000):
    p = Path(path)
    if not p.is_file() or p.stat().st_size > max_bytes:
        raise EvidenceHold("UNAVAILABLE_OR_OVERSIZE_EVIDENCE")
    return json.loads(p.read_bytes())


def git_blob_sha(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def validate_protocol(protocol):
    if (protocol.get("schema") != "janus.closed_loop.real_is_fresh_profile.v1" or
            protocol.get("status") != "PREREGISTERED_BEFORE_FIRST_R14_RUN" or
            protocol.get("baseline_commit") != ORIGINAL_MAIN_SHA or
            protocol.get("baseline_blob_sha") != SOURCE_BLOB_SHA or
            protocol.get("state_commit") != STATE_SHA or
            protocol.get("source_snapshot_commit") != ORIGINAL_MAIN_SHA or
            protocol.get("model_source_sha256") != MODEL_SOURCE_SHA or
            protocol.get("module") != "is_fresh" or
            protocol.get("execution", {}).get("repeat_probes") != 3 or
            protocol.get("execution", {}).get("networkless_model_oracle") is not True or
            protocol.get("execution", {}).get("fixed_clock_once_per_run") is not True or
            protocol.get("execution", {}).get("no_paid_models") is not True or
            protocol.get("claims", {}).get("auto_merge") is not False or
            protocol.get("claims", {}).get("production_promotion") is not False or
            protocol.get("claims", {}).get("code_authority_delta") != 0 or
            protocol.get("claims", {}).get("candidate_improvement_proven") is not False):
        raise EvidenceHold("UNTRUSTED_OR_REBOUND_PROTOCOL")
    source = CONSUMER.read_bytes()
    if git_blob_sha(source) != SOURCE_BLOB_SHA:
        raise EvidenceHold("CONSUMER_SOURCE_NOT_MAIN_BASELINE")
    if (consumer.EXPECTED_SOURCE_SHA256 != MODEL_SOURCE_SHA or
            consumer.STATE_SOURCE_COMMIT != STATE_SHA or
            isolated_check.__module__ != "lifecycle"):
        raise EvidenceHold("CONSUMER_LIFECYCLE_CHANGED")


def probe_snapshot(state_path, latest_path, *, fixed_now, idx):
    elapsed = {"verify_ns": 0, "oracle_ns": 0}
    actual_verify = consumer.module_registry.verify

    def measured_verify(*args, **kwargs):
        start = time.perf_counter_ns()
        try:
            return actual_verify(*args, **kwargs)
        finally:
            elapsed["verify_ns"] += time.perf_counter_ns() - start

    def measured_oracle(source, task, *, call, seed):
        start = time.perf_counter_ns()
        try:
            # Unchanged real lifecycle.isolated_check -> pinned networkless Docker
            return isolated_check(source, task, call=call, seed=seed)
        finally:
            elapsed["oracle_ns"] += time.perf_counter_ns() - start

    with mock.patch.object(consumer.module_registry, "verify", measured_verify):
        start = time.perf_counter_ns()
        receipt = consumer.probe(state_path, latest_path,
                                 now=fixed_now, check=measured_oracle)
        total_ns = time.perf_counter_ns() - start
    write_start = time.perf_counter_ns()
    raw_receipt = consumer.canonical(receipt) + b"\n"
    serialize_ns = time.perf_counter_ns() - write_start
    if (receipt.get("schema") != "janus.autonomous_coder.real_operational_consumer.v1" or
            receipt.get("module_source_sha256") != MODEL_SOURCE_SHA or
            receipt.get("source_state_commit") != STATE_SHA or
            receipt.get("executed_in_networkless_oracle") is not True or
            receipt.get("behavioral_cases", 0) < 200 or
            receipt.get("authority_delta") != 0 or
            receipt.get("installed_into_trusted_runtime") is not False or
            receipt.get("source_writeback") is not False or
            receipt.get("automatic_merge") is not False or
            receipt.get("status") not in ("FRESH_SOURCE_DIAGNOSTIC_ONLY",
                                         "STALE_SOURCE_DIAGNOSTIC_ONLY")):
        raise EvidenceHold("UNTRUSTED_CONSUMER_RECEIPT")
    if (total_ns <= 0 or elapsed["verify_ns"] <= 0 or elapsed["oracle_ns"] <= 0 or
            elapsed["verify_ns"] + elapsed["oracle_ns"] > total_ns):
        raise EvidenceHold("PROFILE_CLOCK_INCONSISTENT")
    return {
        "index": idx,
        "total_ms": round(total_ns / 1e6, 6),
        "module_catalog_verify_ms": round(elapsed["verify_ns"] / 1e6, 6),
        "networkless_docker_oracle_ms": round(elapsed["oracle_ns"] / 1e6, 6),
        "other_source_preflight_ms": round(
            (total_ns - elapsed["verify_ns"] - elapsed["oracle_ns"]) / 1e6, 6),
        "receipt_serialization_ms": round(serialize_ns / 1e6, 6),
        "receipt_sha256": hashlib.sha256(raw_receipt).hexdigest(),
        "observation_sha256": receipt["autonomy_snapshot_sha256"],
        "status": receipt["status"],
        "behavioral_cases": receipt["behavioral_cases"],
        "model_source_sha256": MODEL_SOURCE_SHA,
        "authority_delta": 0,
    }


def run(state_path, latest_path, main_source_path, *, head_sha, run_id):
    if (len(head_sha) != 40 or
            any(x not in "0123456789abcdef" for x in head_sha) or
            not run_id.isdecimal()):
        raise EvidenceHold("SOURCE_HEAD_OR_RUN_ID_UNPINNED")
    protocol = read_json(FOLDER / "PROTOCOL.json")
    validate_protocol(protocol)
    if Path(main_source_path).read_bytes() != CONSUMER.read_bytes():
        raise EvidenceHold("PR_AND_MAIN_CONSUMER_SOURCE_DIFFER")
    state_path, latest_path = Path(state_path), Path(latest_path)
    latest_raw = latest_path.read_bytes()
    if len(latest_raw) > 100_000:
        raise EvidenceHold("LATEST_TOO_LARGE")
    latest = json.loads(latest_raw)
    if latest.get("schema") != "janus.autonomy.latest.v1" or \
       latest.get("ecosystem_status") not in ("AUTONOMY_PARTIAL", "AUTONOMY_FULL"):
        raise EvidenceHold("LATEST_NOT_VALID_REAL_CONSUMER_INPUT")
    fixed_now = datetime.now(timezone.utc)
    profiles = []
    for index in range(protocol["execution"]["repeat_probes"]):
        profiles.append(probe_snapshot(state_path, latest_path,
                                      fixed_now=fixed_now, idx=index))
    if len({p["receipt_sha256"] for p in profiles}) != 1:
        raise EvidenceHold("DIFFERENT_RECEIPTS_WITH_FROZEN_CLOCK")
    if len({p["observation_sha256"] for p in profiles}) != 1:
        raise EvidenceHold("OBSERVATION_CHANGED_INSIDE_EXPERIMENT")
    metrics = ["total_ms", "module_catalog_verify_ms", "networkless_docker_oracle_ms",
               "other_source_preflight_ms", "receipt_serialization_ms"]
    medians = {m: round(statistics.median(row[m] for row in profiles), 6)
               for m in metrics}
    medians["oracle_share_pct"] = round(100 * medians["networkless_docker_oracle_ms"] /
                                        medians["total_ms"], 3)
    outcome = {
        "schema": "janus.closed_loop.is_fresh_real_path_profile.v1",
        "status": "MEASURED_ACTUAL_SOURCE_CONSUMER_NO_CANDIDATE_COMPARISON",
        "scope": "READ_ONLY_REAL_MAIN_BASELINE_PROFILE",
        "source_repo": "Hawkar-usls/janus-meta-registry",
        "github_run_id": run_id,
        "experiment_pr_head_or_merge_sha": head_sha,
        "baseline_main_sha": ORIGINAL_MAIN_SHA,
        "state_sha": STATE_SHA,
        "preregistration_commit": PREREGISTRATION_SHA,
        "protocol_sha256": digest(protocol),
        "snapshot_source_commit": ORIGINAL_MAIN_SHA,
        "snapshot_sha256": hashlib.sha256(latest_raw).hexdigest(),
        "snapshot_last_observed_at_utc": latest.get("last_observed_at_utc"),
        "frozen_evaluation_time_utc": fixed_now.isoformat().replace("+00:00", "Z"),
        "source_module": "is_fresh",
        "source_module_sha256": MODEL_SOURCE_SHA,
        "container_image": DOCKER_IMAGE,
        "container_network": "none",
        "profiles": profiles,
        "medians": medians,
        "candidate_improvement_proven": False,
        "independent_external_replay": False,
        "system_runtime_speedup": False,
        "runtime_source_mutation": False,
        "auto_merge": False,
        "authority_delta": 0,
    }
    outcome["report_sha256"] = digest(outcome)
    return outcome


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--latest", type=Path, required=True)
    parser.add_argument("--main-source", type=Path, required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.state, args.latest, args.main_source,
                         head_sha=args.head_sha, run_id=args.run_id),
                     sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
