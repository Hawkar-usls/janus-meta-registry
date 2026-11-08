"""R1.3 independent-implementation *reference* timing challenge in pinned Docker.

No import of R1.2 timer, screen, or receipt verification logic. No claim of
external blind independence, real production baseline, or actual model gain.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
import timeit

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "experiments/closed_loop_retry_delay_r1"
CHALLENGE_FILE = ROOT / "experiments/closed_loop_retry_delay_r13/CHALLENGE_PROTOCOL.json"
CODER = ROOT / "modules/autonomy_coder"
sys.path.insert(0, str(CODER))
from policy import validate_source

PREREGISTRATION_COMMIT = "0f6cc28fa20ce5e484440afdbadbef57e430c2ef"
CANDIDATE_COMMIT = "2652dd70d8f65385316cd309d4a74db2b948dc46"
CANDIDATE_SHA = "a45bf9b5814e432a89334e46f8acac63a9fa1d2846dc393ed21e6dd6695b2611"
BASELINE_SHA = "1a76285172a0891f910b94d7dad51d111a82faf36a84c386dd88b14005e94da0"
ROUNDS = 7
REPEAT_OPS = 30000
CHALLENGE_CASES = 24


class Hold(ValueError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canon(data) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")


def safe_read(path: Path, limit=30000) -> bytes:
    if not path.is_file() or path.stat().st_size > limit:
        raise Hold("MISSING_OR_OVERSIZE_SOURCE")
    return path.read_bytes()


def load_json(path: Path):
    return json.loads(safe_read(path))


def validate_inputs(candidate_root):
    challenge_raw = safe_read(CHALLENGE_FILE)
    challenge = json.loads(challenge_raw)
    if (challenge.get("schema") != "janus.closed_loop.retry_delay_challenge.v1" or
            challenge.get("status") != "PRE_REGISTERED_BEFORE_FIRST_R13_EXECUTION" or
            challenge.get("candidate_sha256") != CANDIDATE_SHA or
            challenge.get("source_candidate_commit") != CANDIDATE_COMMIT or
            challenge.get("source_reference_baseline_sha256") != BASELINE_SHA or
            challenge.get("fresh_case_count") != CHALLENGE_CASES or
            challenge.get("network") is not False or
            challenge.get("read_only") is not True or
            challenge.get("auto_merge") is not False or
            challenge.get("scientific_authority_delta") != 0 or
            challenge.get("production_authority_delta") != 0 or
            challenge.get("result_does_not_prove_runtime_improvement") is not True or
            challenge.get("independence_level") != "SEPARATE_IMPLEMENTATION_SAME_REPOSITORY_NOT_EXTERNAL_BLIND"):
        raise Hold("CHALLENGE_POLICY_DRIFT")
    reference_raw = safe_read(FOLDER / "BASELINE.py")
    candidate_raw = safe_read(candidate_root / "candidate_modules/retry_delay/module.py")
    if sha(reference_raw) != BASELINE_SHA or sha(candidate_raw) != CANDIDATE_SHA:
        raise Hold("SOURCE_SHA_CHANGED")
    prior_protocol = load_json(FOLDER / "PROTOCOL.json")
    if sha(canon(prior_protocol)) != challenge["r12_proof_protocol_sha256"]:
        raise Hold("ORIGINAL_PROTOCOL_CHANGED")
    train = load_json(FOLDER / "TRAIN_MANIFEST.json")
    old_holdout = load_json(FOLDER / "HOLDOUT_MANIFEST.json")
    if (sha(canon(train)) != challenge["training_manifest_sha256"] or
            sha(canon(old_holdout)) != challenge["r12_holdout_sha256"]):
        raise Hold("PRIOR_CASES_CHANGED")
    excluded = {(r["attempt"], r["cap"]) for r in train["cases"] + old_holdout["cases"]}
    if len(excluded) != len(train["cases"]) + len(old_holdout["cases"]):
        raise Hold("TRAIN_HOLDOUT_COLLISION")
    rng = random.Random(challenge["challenge_seed"])
    fresh, seen = [], set()
    for _ in range(10000):
        candidate = rng.randrange(13), rng.randrange(1, 901)
        if candidate in excluded or candidate in seen:
            continue
        fresh.append(candidate)
        seen.add(candidate)
        if len(fresh) >= CHALLENGE_CASES:
            break
    if len(fresh) != CHALLENGE_CASES:
        raise Hold("CHALLENGE_GENERATION_INCOMPLETE")
    # The candidate must pass JANUS's independently maintained AST policy;
    # the pow() reference is NOT admitted as an autonomous Coder module.
    validate_source(candidate_raw.decode("utf-8"), "retry_delay")
    baseline_is_admitted = True
    try:
        validate_source(reference_raw.decode("utf-8"), "retry_delay")
    except ValueError:
        baseline_is_admitted = False
    if baseline_is_admitted:
        raise Hold("ASSUMED_UNADMITTED_REFERENCE_IS_NOW_ADMITTED_REVIEW_REQUIRED")
    if (not ast.parse(reference_raw.decode("utf-8")) or
            not ast.parse(candidate_raw.decode("utf-8"))):
        raise Hold("SYNTAX_ERROR")
    return challenge, sha(challenge_raw), fresh, reference_raw, candidate_raw


def load_function(raw, tag):
    globals_ = {"__builtins__": {"pow": pow, "min": min}}
    exec(compile(raw.decode("utf-8"), tag, "exec"), globals_)
    return globals_["retry_delay"]


def independently_check(fn):
    total = 0
    for attempt in range(13):
        for cap in [1, 2, 3, 7, 30, 255, 900]:
            if type(fn(attempt, cap)) is not int or fn(attempt, cap) != min(cap, 2 ** attempt):
                raise Hold("EXHAUSTIVE_FUNCTION_MISMATCH")
            total += 1
    rng = random.Random("janus-r13-independent-behavior-v1")
    for _ in range(200):
        attempt, cap = rng.randrange(13), rng.randrange(1, 901)
        if type(fn(attempt, cap)) is not int or fn(attempt, cap) != min(cap, 2 ** attempt):
            raise Hold("SEEDED_FUNCTION_MISMATCH")
        total += 1
    return total


def independent_timer(fn, attempt, cap):
    timer = timeit.Timer(lambda: fn(attempt, cap))
    return timer.timeit(number=REPEAT_OPS) / REPEAT_OPS * 1_000_000


def run(candidate_root, *, source_head, github_run_id):
    if not isinstance(source_head, str) or len(source_head) != 40 or any(c not in "0123456789abcdef" for c in source_head):
        raise Hold("UNPINNED_EXPERIMENT_COMMIT")
    if not github_run_id.isdecimal():
        raise Hold("UNPINNED_RUN_ID")
    challenge, challenge_file_sha, cases, baseline_raw, candidate_raw = validate_inputs(candidate_root)
    reference_fn = load_function(baseline_raw, "r13_reference")
    candidate_fn = load_function(candidate_raw, "r13_candidate")
    reference_checked = independently_check(reference_fn)
    candidate_checked = independently_check(candidate_fn)
    rows = []
    for n, (attempt, cap) in enumerate(cases):
        expected = min(cap, 2 ** attempt)
        for fn in (reference_fn, candidate_fn):
            for _ in range(500):
                if fn(attempt, cap) != expected:
                    raise Hold("WARMUP_FUNCTION_MISMATCH")
        a, b, control_a, control_b = [], [], [], []
        for j in range(ROUNDS):
            # Independent timing implementation and ABBA-style order balancing.
            if (n + j) % 2 == 0:
                a.append(independent_timer(reference_fn, attempt, cap))
                b.append(independent_timer(candidate_fn, attempt, cap))
                control_a.append(independent_timer(candidate_fn, attempt, cap))
                control_b.append(independent_timer(candidate_fn, attempt, cap))
            else:
                control_b.append(independent_timer(candidate_fn, attempt, cap))
                control_a.append(independent_timer(candidate_fn, attempt, cap))
                b.append(independent_timer(candidate_fn, attempt, cap))
                a.append(independent_timer(reference_fn, attempt, cap))
        ma, mb = statistics.median(a), statistics.median(b)
        mc1, mc2 = statistics.median(control_a), statistics.median(control_b)
        rows.append({
            "case_id": f"challenge-{n:02d}",
            "attempt": attempt, "cap": cap,
            "baseline_timeit_us_per_op": round(ma, 9),
            "candidate_timeit_us_per_op": round(mb, 9),
            "neutral_a_us_per_op": round(mc1, 9),
            "neutral_b_us_per_op": round(mc2, 9),
            "paired_gain_us_per_op": round(ma - mb, 9),
            "neutral_abs_difference_us_per_op": round(abs(mc1 - mc2), 9),
            "raw_timeit_us_per_op": {
                "baseline": [round(x, 9) for x in a],
                "candidate": [round(x, 9) for x in b],
                "neutral_a": [round(x, 9) for x in control_a],
                "neutral_b": [round(x, 9) for x in control_b],
            }
        })
    means = {
        "baseline_us_per_op": statistics.mean(r["baseline_timeit_us_per_op"] for r in rows),
        "candidate_us_per_op": statistics.mean(r["candidate_timeit_us_per_op"] for r in rows),
        "candidate_gain_us_per_op": statistics.mean(r["paired_gain_us_per_op"] for r in rows),
        "neutral_abs_difference_us_per_op": statistics.mean(r["neutral_abs_difference_us_per_op"] for r in rows),
    }
    means["relative_candidate_gain_pct"] = (100 * means["candidate_gain_us_per_op"] /
                                             means["baseline_us_per_op"])
    regressions = sum(row["paired_gain_us_per_op"] < 0 for row in rows)
    report = {
        "schema": "janus.closed_loop.r13_cross_implementation_replay.v1",
        "status": "RECORDED_REFERENCE_REPLAY",
        "experiment": "retry_delay_cross_implementation_with_neutral_control",
        "challenge_preregistration_commit": PREREGISTRATION_COMMIT,
        "challenge_policy_sha256_raw_file": challenge_file_sha,
        "source_head_sha": source_head,
        "github_run_id": github_run_id,
        "candidate_commit": CANDIDATE_COMMIT,
        "candidate_source_sha256": CANDIDATE_SHA,
        "reference_source_sha256": BASELINE_SHA,
        "sandbox": "NETWORKLESS_READONLY_PINNED_DOCKER",
        "case_count": len(rows),
        "correctness_oracle_cases_per_variant": reference_checked,
        "correctness_oracle_cases_candidate": candidate_checked,
        "timing_rounds_per_case": ROUNDS,
        "operations_per_timed_block": REPEAT_OPS,
        "metric": "timeit_us_per_function_call",
        "baseline_admitted_by_current_coder_policy": False,
        "candidate_admitted_by_current_coder_policy": True,
        "reference_is_production_baseline": False,
        "externally_independent_blind": False,
        "same_repo_independent_timer_implementation": True,
        "neutral_control_included": True,
        "means": means,
        "regressions": regressions,
        "pairs": rows,
        "runtime_consumption_attested": False,
        "scientific_proof": False,
        "production_promotion": False,
        "auto_merge": False,
        "authority_delta": 0,
    }
    report["report_sha256"] = sha(canon(report))
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--candidate-root", type=Path, required=True)
    p.add_argument("--source-head", required=True)
    p.add_argument("--run-id", required=True)
    args = p.parse_args()
    print(json.dumps(run(args.candidate_root,
                         source_head=args.source_head,
                         github_run_id=args.run_id),
                     sort_keys=True, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
