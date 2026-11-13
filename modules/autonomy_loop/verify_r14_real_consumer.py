"""Offline verifier for R1.4 real is_fresh operational-baseline profiling.

Recomputes stage medians and source-linked receipt digests; does not re-run
Docker or attest production improvements. No secrets, network or mutation.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics
import re

ROOT = Path(__file__).resolve().parents[2]
RUN_ID = 42503712794
RUN_PR_HEAD_SHA = "0655adaa2249cd3831748be5a92a89dee147d9aa"
RUN_PR_MERGE_SHA = "a8315076e192241f99b8ba27593df8f46caa20ac"
FROZEN_MAIN_SHA = "a44942be5ed510d2aa58c4c3d33b580d771c29b8"
PRE_REG_COMMIT = "6200377978184360868c0f328adcc1b95f1f56c8"
MODEL_SHA = "30a35a12b9c864af6ff066fe30dd94ece681e81fa6e8b95c3c4a43dc3fd9c5a2"
STATE_SHA = "ccb2f82edb0f1c61c460aa0a4521a9991e8d5eb2"
SNAPSHOT_SHA = "f1e3f1e7bf193c9bb7637d1b293cb14c2be97c1ef5bc74402d6da01a9f30a4dc"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class Hold(ValueError):
    pass


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canon(value)).hexdigest()


def read_json(path, limit=50_000):
    p = Path(path)
    if not p.is_file() or p.stat().st_size > limit:
        raise Hold("RECEIPT_SOURCE_MISSING")
    return json.loads(p.read_bytes())


def validate(record, protocol):
    if (record.get("schema") != "janus.closed_loop.is_fresh_r14_durable_receipt.v1" or
            record.get("status") != "MEASURED_ACTUAL_SOURCE_NO_OPTIMIZATION_CLAIM" or
            record.get("pre_registration_commit") != PRE_REG_COMMIT):
        raise Hold("RECEIPT_SCHEMA_OR_PRECOMMIT")
    origin = record.get("source_run") or {}
    art = record.get("source_artifact") or {}
    claim = record.get("scope") or {}
    x = record.get("report") or {}
    if (origin.get("repository") != "Hawkar-usls/janus-meta-registry" or
            origin.get("id") != RUN_ID or
            origin.get("url") != f"https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/{RUN_ID}" or
            origin.get("workflow") != "JANUS Self-Writer Real Operational Consumer" or
            origin.get("event") != "pull_request" or
            origin.get("status") != "completed" or origin.get("conclusion") != "success" or
            origin.get("source_pr_head_sha") != RUN_PR_HEAD_SHA or
            origin.get("source_checkout_sha") != RUN_PR_MERGE_SHA or
            type(origin.get("job_id")) is not int or origin["job_id"] <= 0):
        raise Hold("RUN_SOURCE_BINDING")
    if (type(art.get("id")) is not int or
            art.get("name") != f"janus-r14-real-consumer-profile-{RUN_ID}" or
            not isinstance(art.get("sha256"), str) or
            not art["sha256"].startswith("sha256:") or
            not HEX64.fullmatch(art["sha256"][7:]) or
            art.get("api_url") != f"https://api.github.com/repos/Hawkar-usls/janus-meta-registry/actions/artifacts/{art['id']}"):
        raise Hold("GITHUB_ARTIFACT_BINDING")
    if (claim.get("source_is_actual_main") is not True or
            claim.get("main_modified") is not False or
            claim.get("independently_governed_timing") is not False or
            claim.get("candidate_compared") is not False or
            claim.get("workload_calls") != 3 or
            claim.get("generated_code_executed_in_existing_networkless_docker") is not True or
            claim.get("scientific_claim") is not False or
            claim.get("authority_delta") != 0 or claim.get("auto_merge") is not False):
        raise Hold("UNSAFE_SCOPE_ESCALATION")
    if (protocol.get("schema") != "janus.closed_loop.real_is_fresh_profile.v1" or
            protocol.get("baseline_commit") != FROZEN_MAIN_SHA or
            protocol.get("state_commit") != STATE_SHA or
            protocol.get("claims",{}).get("candidate_improvement_proven") is not False or
            protocol.get("claims",{}).get("auto_merge") is not False or
            protocol.get("execution",{}).get("repeat_probes") != 3 or
            x.get("protocol_sha256") != digest(protocol)):
        raise Hold("PREREGISTERED_PROTOCOL_REBOUND")
    if (x.get("schema") != "janus.closed_loop.is_fresh_real_path_profile.v1" or
            x.get("status") != "MEASURED_ACTUAL_SOURCE_CONSUMER_NO_CANDIDATE_COMPARISON" or
            x.get("source_repo") != "Hawkar-usls/janus-meta-registry" or
            x.get("baseline_main_sha") != FROZEN_MAIN_SHA or
            x.get("snapshot_source_commit") != FROZEN_MAIN_SHA or
            x.get("state_sha") != STATE_SHA or
            x.get("preregistration_commit") != PRE_REG_COMMIT or
            x.get("source_module") != "is_fresh" or
            x.get("source_module_sha256") != MODEL_SHA or
            x.get("snapshot_sha256") != SNAPSHOT_SHA or
            x.get("github_run_id") != str(RUN_ID) or
            x.get("experiment_pr_head_or_merge_sha") != RUN_PR_MERGE_SHA or
            x.get("candidate_improvement_proven") is not False or
            x.get("independent_external_replay") is not False or
            x.get("system_runtime_speedup") is not False or
            x.get("runtime_source_mutation") is not False or
            x.get("auto_merge") is not False or x.get("authority_delta") != 0 or
            x.get("report_sha256") != digest({k:v for k,v in x.items() if k != "report_sha256"})):
        raise Hold("PROFILE_IDENTITY_OR_DIGEST")
    records = x.get("profiles")
    if not isinstance(records, list) or len(records) != 3:
        raise Hold("EXPECTED_THREE_REPEATS")
    keys = ("total_ms", "module_catalog_verify_ms", "networkless_docker_oracle_ms",
            "other_source_preflight_ms", "receipt_serialization_ms")
    for i,p in enumerate(records):
        if (p.get("index") != i or
                p.get("behavioral_cases") != 270 or
                p.get("model_source_sha256") != MODEL_SHA or
                p.get("observation_sha256") != SNAPSHOT_SHA or
                p.get("status") not in ("FRESH_SOURCE_DIAGNOSTIC_ONLY", "STALE_SOURCE_DIAGNOSTIC_ONLY") or
                p.get("authority_delta") != 0 or
                not isinstance(p.get("receipt_sha256"), str) or
                not HEX64.fullmatch(p["receipt_sha256"])):
            raise Hold("PROFILE_ROW_BOUNDARY")
        if any(type(p.get(key)) not in (float, int) or not math.isfinite(p[key]) or p[key] < 0 for key in keys):
            raise Hold("PROFILE_TIMING_NONFINITE")
        if not math.isclose(p["total_ms"], p["networkless_docker_oracle_ms"] +
                            p["module_catalog_verify_ms"] +
                            p["other_source_preflight_ms"],abs_tol=0.000005):
            raise Hold("PROFILE_STAGE_SUM_INVALID")
    if (len({p["receipt_sha256"] for p in records}) != 1 or
            len({p["status"] for p in records}) != 1):
        raise Hold("FROZEN_SNAPSHOT_NOT_REPLAYED")
    means = x.get("medians") or {}
    for key in keys:
        measured = round(statistics.median(p[key] for p in records), 6)
        if (type(means.get(key)) not in (int,float) or
                not math.isclose(means[key],measured,abs_tol=0.000003)):
            raise Hold("MEDIAN_ARITHMETIC_TAMPERED")
    percent = round(means["networkless_docker_oracle_ms"] /
                    means["total_ms"] * 100, 3)
    if not math.isclose(means.get("oracle_share_pct", -1), percent,abs_tol=0.0005):
        raise Hold("PERCENTAGE_ARITHMETIC_TAMPERED")
    if means["oracle_share_pct"] < 90:
        raise Hold("PROFILE_UNEXPECTED_DOCKER_SHARE")
    # Just a memo of a valid historical observation, not a current freshness claim.
    return {
        "schema": "janus.closed_loop.r14_recorded_profile_verification.v1",
        "status": "PASS_RECORDED_ARITHMETIC_AND_SOURCE_BINDINGS_ONLY",
        "github_run_id": RUN_ID,
        "receipt_sha256": digest(record),
        "replayed_probes": len(records),
        "median_total_ms": means["total_ms"],
        "median_networkless_oracle_ms": means["networkless_docker_oracle_ms"],
        "oracle_share_pct": percent,
        "independently_remeasured_cpu_time": False,
        "candidate_improvement_proven": False,
        "production_promotion": False,
        "authority_delta": 0,
    }


def verify(root=ROOT):
    protocol = read_json(Path(root)/"experiments/closed_loop_is_fresh_r14/PROTOCOL.json")
    record = read_json(Path(root)/f"experiments/closed_loop_is_fresh_r14/receipts/github-run-{RUN_ID}.json")
    return validate(record, protocol)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=ROOT)
    args=parser.parse_args()
    try:
        result=verify(args.root)
    except (ValueError,TypeError,KeyError,OSError,OverflowError,json.JSONDecodeError):
        print(json.dumps({"status":"HOLD_INVALID_SOURCE_BOUND_PROFILE","authority_delta":0}))
        return 2
    print(json.dumps(result,sort_keys=True,allow_nan=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
