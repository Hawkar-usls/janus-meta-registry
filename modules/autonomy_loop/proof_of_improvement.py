"""Fail-closed, offline screening of measured JANUS code improvements.

This is a review-only gate: a passing result is NEVER execution, independent
attestation, production admission, model promotion, or scientific evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

PROTOCOL_SCHEMA = "janus.closed_loop.improvement_protocol.v1"
MEASUREMENT_SCHEMA = "janus.closed_loop.improvement_measurement.v1"
VERDICT_SCHEMA = "janus.closed_loop.improvement_screen.v1"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
TASK_ID = re.compile(r"[a-z][a-z0-9_-]{2,79}\Z")
MAX_CASES = 256
MAX_FILE_BYTES = 128_000


class EvidenceHold(ValueError):
    """Malformed or insufficiently source-bound evidence; never promote."""


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _is_hash(value, pattern):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _finite(value):
    return (type(value) in (float, int) and
            math.isfinite(value) and abs(value) <= 1_000_000_000_000)


def _fields(value, required, code):
    if not isinstance(value, dict) or set(value) != set(required):
        raise EvidenceHold(code)


def validate_protocol(protocol):
    _fields(protocol, (
        "schema", "task_id", "baseline_sha256", "train_manifest_sha256",
        "holdout_manifest_sha256", "case_ids", "metric",
        "direction", "minimum_mean_gain", "max_regressions",
        "authority_delta", "allow_auto_merge",
    ), "PROTOCOL_FIELDS")
    if protocol["schema"] != PROTOCOL_SCHEMA:
        raise EvidenceHold("PROTOCOL_SCHEMA")
    if not isinstance(protocol["task_id"], str) or not TASK_ID.fullmatch(protocol["task_id"]):
        raise EvidenceHold("TASK_ID")
    for field in ("baseline_sha256", "train_manifest_sha256", "holdout_manifest_sha256"):
        if not _is_hash(protocol[field], HEX64):
            raise EvidenceHold("PROTOCOL_SHA")
    if protocol["train_manifest_sha256"] == protocol["holdout_manifest_sha256"]:
        raise EvidenceHold("TRAIN_HOLDOUT_DIGEST_COLLISION")
    cases = protocol["case_ids"]
    if (not isinstance(cases, list) or not 8 <= len(cases) <= MAX_CASES or
            any(not isinstance(x, str) or not CASE_ID.fullmatch(x) for x in cases) or
            len(set(cases)) != len(cases)):
        raise EvidenceHold("FROZEN_CASE_SET")
    if not isinstance(protocol["metric"], str) or not TASK_ID.fullmatch(protocol["metric"]):
        raise EvidenceHold("METRIC")
    if protocol["direction"] not in ("lower", "higher"):
        raise EvidenceHold("METRIC_DIRECTION")
    if not _finite(protocol["minimum_mean_gain"]) or protocol["minimum_mean_gain"] <= 0:
        raise EvidenceHold("MINIMUM_GAIN")
    if type(protocol["max_regressions"]) is not int or protocol["max_regressions"] != 0:
        raise EvidenceHold("REGRESSION_POLICY")
    if type(protocol["authority_delta"]) is not int or protocol["authority_delta"] != 0:
        raise EvidenceHold("AUTHORITY_PROMOTION")
    if protocol["allow_auto_merge"] is not False:
        raise EvidenceHold("AUTO_MERGE_DENIED")
    return digest(protocol)


def screen(protocol, measurement):
    """Compare paired cases without fetching sources, running code, or granting authority.

    This validates a claimed measurement's shape and arithmetic only.
    An independent, immutable run/holdout replay must attest its truth.
    """
    protocol_sha = validate_protocol(protocol)
    _fields(measurement, (
        "schema", "protocol_sha256", "candidate_sha256", "evaluator_commit",
        "case_rows", "authority_delta",
    ), "MEASUREMENT_FIELDS")
    if measurement["schema"] != MEASUREMENT_SCHEMA:
        raise EvidenceHold("MEASUREMENT_SCHEMA")
    if measurement["protocol_sha256"] != protocol_sha:
        raise EvidenceHold("PROTOCOL_REBINDING")
    if (not _is_hash(measurement["candidate_sha256"], HEX64) or
            not _is_hash(measurement["evaluator_commit"], HEX40)):
        raise EvidenceHold("UNPINNED_CANDIDATE_OR_EVALUATOR")
    if measurement["candidate_sha256"] == protocol["baseline_sha256"]:
        raise EvidenceHold("SAME_CODE_NOT_AN_IMPROVEMENT")
    if type(measurement["authority_delta"]) is not int or measurement["authority_delta"] != 0:
        raise EvidenceHold("MEASUREMENT_AUTHORITY_PROMOTION")
    rows = measurement["case_rows"]
    if not isinstance(rows, list) or len(rows) != len(protocol["case_ids"]):
        raise EvidenceHold("INCOMPLETE_HOLDOUT")
    table = {}
    for row in rows:
        _fields(row, ("case_id", "baseline", "candidate"), "CASE_FIELDS")
        key = row["case_id"]
        if not isinstance(key, str) or key in table:
            raise EvidenceHold("DUPLICATE_OR_INVALID_CASE")
        if not _finite(row["baseline"]) or not _finite(row["candidate"]):
            raise EvidenceHold("NONFINITE_MEASUREMENT")
        table[key] = row
    if set(table) != set(protocol["case_ids"]):
        raise EvidenceHold("HOLDOUT_CASE_REBINDING")

    deltas = []
    for key in protocol["case_ids"]:
        value = table[key]
        delta = (value["baseline"] - value["candidate"] if
                 protocol["direction"] == "lower" else
                 value["candidate"] - value["baseline"])
        deltas.append(delta)
    regressions = sum(delta < 0 for delta in deltas)
    mean_gain = math.fsum(deltas) / len(deltas)
    positive = any(delta > 0 for delta in deltas)
    eligible = (regressions == 0 and positive and
                mean_gain >= protocol["minimum_mean_gain"])
    verdict = {
        "schema": VERDICT_SCHEMA,
        "status": ("ELIGIBLE_FOR_INDEPENDENT_REPLAY" if eligible
                   else "REJECTED_NO_MEASURED_IMPROVEMENT"),
        "task_id": protocol["task_id"],
        "protocol_sha256": protocol_sha,
        "measurement_sha256": digest(measurement),
        "baseline_sha256": protocol["baseline_sha256"],
        "candidate_sha256": measurement["candidate_sha256"],
        "case_count": len(deltas),
        "mean_paired_gain": mean_gain,
        "regressions": regressions,
        "independent_replay_attested": False,
        "runtime_consumption_attested": False,
        "production_promotion": False,
        "allow_auto_merge": False,
        "authority_delta": 0,
    }
    verdict["verdict_sha256"] = digest(verdict)
    return verdict


def _load(path):
    p = Path(path)
    if not p.is_file() or p.stat().st_size > MAX_FILE_BYTES:
        raise EvidenceHold("EVIDENCE_FILE_SIZE")
    try:
        return json.loads(p.read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceHold("EVIDENCE_JSON") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frozen_protocol_json")
    parser.add_argument("measurement_json")
    args = parser.parse_args()
    try:
        verdict = screen(_load(args.frozen_protocol_json), _load(args.measurement_json))
    except (EvidenceHold, OSError, OverflowError, TypeError, ValueError):
        print(json.dumps({"schema": VERDICT_SCHEMA, "status": "HOLD_INVALID_EVIDENCE",
                          "authority_delta": 0, "allow_auto_merge": False}))
        return 2
    print(json.dumps(verdict, sort_keys=True, allow_nan=False))
    return 0 if verdict["status"] == "ELIGIBLE_FOR_INDEPENDENT_REPLAY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
