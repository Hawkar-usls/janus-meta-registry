"""Offline arithmetic and source-binding replay of the JANUS R1.3 challenge.

This checks recorded *claims* against stored bytes and raw paired repetitions.
It does not rerun timing, read private sources or grant production authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics

ROOT = Path(__file__).resolve().parents[2]
R12 = ROOT / "experiments/closed_loop_retry_delay_r1"
R13 = ROOT / "experiments/closed_loop_retry_delay_r13"
RUN_ID = 42482603402
RUN_PR_HEAD_SHA = "2ec50e0aede9ebc4331abfe4f5e45020dd5fb5de"
RUN_CHECKOUT_MERGE_SHA = "02ebf0f5a4c693e5250cd7e40d2a67c833cef0e6"
SOURCE_SHA = "a45bf9b5814e432a89334e46f8acac63a9fa1d2846dc393ed21e6dd6695b2611"
BASE_SHA = "1a76285172a0891f910b94d7dad51d111a82faf36a84c386dd88b14005e94da0"
PRECOMMIT = "0f6cc28fa20ce5e484440afdbadbef57e430c2ef"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")


class Hold(ValueError):
    pass


def read_json(p):
    p = Path(p)
    if not p.is_file() or p.stat().st_size > 150_000:
        raise Hold("RECORD_UNAVAILABLE_OR_OVERSIZE")
    return json.loads(p.read_bytes())


def sha(x):
    return hashlib.sha256(x).hexdigest()


def canon(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def close(a, b, tol=1e-8):
    return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= tol


def verify(root=ROOT):
    root = Path(root)
    r12 = root / "experiments/closed_loop_retry_delay_r1"
    r13 = root / "experiments/closed_loop_retry_delay_r13"
    p = r13 / f"receipts/github-run-{RUN_ID}.json"
    rec = read_json(p)
    trial = rec.get("report")
    meta = rec.get("source_run", {})
    art = rec.get("source_artifact", {})
    bind = rec.get("preregistration", {})
    scope = rec.get("analysis_scope", {})
    if (rec.get("schema") != "janus.closed_loop.r13_source_bound_receipt.v1" or
            rec.get("status") != "RECORDED_ALTERNATE_TIMER_NOT_EXTERNAL_BLIND" or
            not isinstance(trial, dict) or
            meta.get("repository") != "Hawkar-usls/janus-meta-registry" or
            meta.get("id") != RUN_ID or
            meta.get("url") != f"https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/{RUN_ID}" or
            meta.get("status") != "completed" or meta.get("conclusion") != "success" or
            meta.get("event") != "pull_request" or
            type(meta.get("job_id")) is not int or meta["job_id"] < 1 or
            not isinstance(meta.get("head_sha"), str) or not HEX40.fullmatch(meta["head_sha"]) or
            meta["head_sha"] != RUN_PR_HEAD_SHA):
        raise Hold("RECEIPT_RUN_PROVENANCE")
    if (type(art.get("id")) is not int or art["id"] < 1 or
            art.get("name") != f"janus-r13-cross-implementation-{RUN_ID}" or
            not isinstance(art.get("sha256"), str) or
            not art["sha256"].startswith("sha256:") or
            not HEX64.fullmatch(art["sha256"][7:]) or
            art.get("api_url") != f"https://api.github.com/repos/Hawkar-usls/janus-meta-registry/actions/artifacts/{art['id']}"):
        raise Hold("ARTIFACT_METADATA")
    if (bind.get("commit") != PRECOMMIT or
            bind.get("candidate_commit") != "2652dd70d8f65385316cd309d4a74db2b948dc46" or
            bind.get("source_sha256") != SOURCE_SHA):
        raise Hold("SOURCE_PREREGISTRATION")
    challenge_raw = (r13 / "CHALLENGE_PROTOCOL.json").read_bytes()
    policy = json.loads(challenge_raw)
    if (bind.get("challenge_policy_sha256_raw_file") != sha(challenge_raw) or
            policy.get("status") != "PRE_REGISTERED_BEFORE_FIRST_R13_EXECUTION" or
            policy.get("challenge_seed") != "janus-r13-independent-replay-20261108-fixed-v1" or
            policy.get("fresh_case_count") != 24 or
            policy.get("candidate_sha256") != SOURCE_SHA or
            policy.get("source_reference_baseline_sha256") != BASE_SHA or
            policy.get("auto_merge") is not False or
            policy.get("result_does_not_prove_runtime_improvement") is not True):
        raise Hold("CHALLENGE_POLICY_CHANGED")
    if sha((r12 / "BASELINE.py").read_bytes()) != BASE_SHA:
        raise Hold("FROZEN_BASELINE_CHANGED")
    excluded = set()
    for file, expected in (("TRAIN_MANIFEST.json", policy["training_manifest_sha256"]),
                           ("HOLDOUT_MANIFEST.json", policy["r12_holdout_sha256"])):
        manifest = read_json(r12 / file)
        if sha(canon(manifest)) != expected:
            raise Hold("ORIGINAL_CASES_CHANGED")
        excluded.update((r["attempt"], r["cap"]) for r in manifest["cases"])
    rng = random.Random(policy["challenge_seed"])
    wanted = []
    seen = set()
    for _ in range(10000):
        pair = (rng.randrange(13), rng.randrange(1, 901))
        if pair not in excluded and pair not in seen:
            seen.add(pair)
            wanted.append(pair)
            if len(wanted) == 24:
                break
    if len(wanted) != 24:
        raise Hold("CHALLENGE_GENERATION_FAILED")
    if (trial.get("schema") != "janus.closed_loop.r13_cross_implementation_replay.v1" or
            trial.get("status") != "RECORDED_REFERENCE_REPLAY" or
            trial.get("github_run_id") != str(RUN_ID) or
            trial.get("source_head_sha") != RUN_CHECKOUT_MERGE_SHA or
            trial.get("candidate_source_sha256") != SOURCE_SHA or
            trial.get("reference_source_sha256") != BASE_SHA or
            trial.get("challenge_preregistration_commit") != PRECOMMIT or
            trial.get("challenge_policy_sha256_raw_file") != sha(challenge_raw) or
            trial.get("case_count") != 24 or
            trial.get("correctness_oracle_cases_per_variant") != 291 or
            trial.get("correctness_oracle_cases_candidate") != 291 or
            trial.get("timing_rounds_per_case") != 7 or
            trial.get("operations_per_timed_block") != 30000 or
            trial.get("baseline_admitted_by_current_coder_policy") is not False or
            trial.get("candidate_admitted_by_current_coder_policy") is not True or
            trial.get("externally_independent_blind") is not False or
            trial.get("reference_is_production_baseline") is not False or
            trial.get("runtime_consumption_attested") is not False or
            trial.get("production_promotion") is not False or
            trial.get("auto_merge") is not False or
            trial.get("authority_delta") != 0 or
            trial.get("report_sha256") != sha(canon({k:v for k,v in trial.items() if k != "report_sha256"}))):
        raise Hold("TRIAL_IDENTITY_OR_DIGEST")
    if (scope.get("separate_implementation_not_independently_governed") is not True or
            scope.get("production_baseline") is not False or
            scope.get("external_blind") is not False or
            scope.get("results_not_core_speedup") is not True or
            scope.get("auto_merge") is not False or
            scope.get("authority_delta") != 0):
        raise Hold("SCOPE_PROMOTION_DENIED")
    rows = trial.get("pairs")
    if not isinstance(rows, list) or len(rows) != 24:
        raise Hold("INCOMPLETE_CHALLENGE_RECORD")
    measures = []
    for i, (row, pair) in enumerate(zip(rows, wanted)):
        if (row.get("case_id") != f"challenge-{i:02d}" or
                (row.get("attempt"), row.get("cap")) != pair):
            raise Hold("CHALLENGE_ORDER_CHANGED")
        raw = row.get("raw_timeit_us_per_op", {})
        means = {}
        for name, out in (("baseline","baseline_timeit_us_per_op"),
                          ("candidate","candidate_timeit_us_per_op"),
                          ("neutral_a","neutral_a_us_per_op"),
                          ("neutral_b","neutral_b_us_per_op")):
            seq = raw.get(name)
            if (not isinstance(seq, list) or len(seq) != 7 or
                    any(type(x) not in (int, float) or not math.isfinite(x) or
                        x <= 0 or x >= 1e6 for x in seq)):
                raise Hold("BAD_RAW_TIMER_VALUES")
            expected = statistics.median(seq)
            if not close(expected, row.get(out)):
                raise Hold("MEDIAN_REPLAY_CHANGED")
            means[name] = expected
        delta = means["baseline"] - means["candidate"]
        noise = abs(means["neutral_a"] - means["neutral_b"])
        if (not close(delta, row.get("paired_gain_us_per_op")) or
                not close(noise, row.get("neutral_abs_difference_us_per_op"))):
            raise Hold("PAIR_ARITHMETIC_CHANGED")
        measures.append((row["baseline_timeit_us_per_op"],
                         row["candidate_timeit_us_per_op"],
                         row["paired_gain_us_per_op"],
                         row["neutral_abs_difference_us_per_op"]))
    actual = trial.get("means", {})
    wanted_mean = {
        "baseline_us_per_op": statistics.mean(x[0] for x in measures),
        "candidate_us_per_op": statistics.mean(x[1] for x in measures),
        "candidate_gain_us_per_op": statistics.mean(x[2] for x in measures),
        "neutral_abs_difference_us_per_op": statistics.mean(x[3] for x in measures),
    }
    wanted_mean["relative_candidate_gain_pct"] = 100 * (
        wanted_mean["candidate_gain_us_per_op"] / wanted_mean["baseline_us_per_op"])
    if any(not close(value, actual.get(name)) for name,value in wanted_mean.items()):
        raise Hold("AVERAGE_REPLAY_CHANGED")
    if trial.get("regressions") != sum(v[2] < 0 for v in measures):
        raise Hold("REGRESSION_COUNT_CHANGED")
    return {
        "schema": "janus.closed_loop.r13_recorded_arithmetic_replay.v1",
        "status": "PASS_RECORDED_VALUES_ONLY",
        "github_run_id": RUN_ID,
        "receipt_sha256": sha(canon(rec)),
        "challenge_case_count": len(measures),
        "candidate_reference_gain_pct": actual["relative_candidate_gain_pct"],
        "neutral_abs_difference_us": actual["neutral_abs_difference_us_per_op"],
        "independent_timing_execution_reproduced": False,
        "production_baseline": False,
        "external_blind": False,
        "authority_delta": 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = verify(args.root)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
        print(json.dumps({"status":"HOLD_INVALID_RECORDED_EVIDENCE","authority_delta":0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
