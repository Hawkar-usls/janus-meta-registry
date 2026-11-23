#!/usr/bin/env python3
"""JANUS P0.3 recovery matrix — read-only, independently recalculated from pinned bytes.

This EXAMINES the existing autonomy receipt and checkpoint. It cannot wake
workflows, admit phases, assert BEETLE consumption, update CHECKPOINT, fork
repositories, or promote any source. Every output is a HOLD or non-authoritative
diagnostic; real independent private-ACK and Cloud HOME consumption still require
separate external witnesses.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

SCHEMA = "janus.autonomy.p03_recovery_matrix.v1"
POINTER = "data/autonomy_loop/LATEST.json"
CHECKPOINT = "data/autonomy_loop/CHECKPOINT.json"
RECEIPT_PATH = re.compile(r"data/autonomy_loop/receipts/[0-9a-f]{24}\.json\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
EXPECTED_PHASE = "P0.3"
PRIVATE = "Hawkar-usls/SkinGPT"
EXPECTED_REF = "P03_PREFLIGHT_BLOCKED"


class Hold(ValueError):
    """Corrupt, incomplete or incongruent evidence cannot change authority."""


def required(value, condition, reason):
    if not condition:
        raise Hold(reason)
    return value


def decode_strict(raw):
    def reject_duplicate(pairs):
        d = {}
        for key, val in pairs:
            if key in d:
                raise Hold("DUPLICATE_JSON_FIELD")
            d[key] = val
        return d
    def reject_nonfinite(_value):
        raise Hold("NONFINITE_JSON")
    try:
        return json.loads(raw, object_pairs_hook=reject_duplicate,
                          parse_constant=reject_nonfinite)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Hold("INVALID_JSON_BYTES") from exc


def read_evidence(root: Path):
    """Never trust a receipt path from the pointer without an allowlist."""
    root = root.resolve(strict=True)
    pointer_path = root / POINTER
    checkpoint_path = root / CHECKPOINT
    for file in (pointer_path, checkpoint_path):
        required(file, file.is_file() and not file.is_symlink(), "MISSING_TRUSTED_POINTER")
    latest = decode_strict(pointer_path.read_bytes())
    checkpoint = decode_strict(checkpoint_path.read_bytes())
    required(latest, type(latest) is dict and latest.get("schema") == "janus.autonomy.latest.v1",
             "LATEST_SCHEMA_UNVERIFIED")
    required(checkpoint, type(checkpoint) is dict and checkpoint.get("schema") == "janus.autonomy.checkpoint.v1",
             "CHECKPOINT_SCHEMA_UNVERIFIED")
    path = latest.get("receipt_path")
    required(path, type(path) is str and RECEIPT_PATH.fullmatch(path) is not None,
             "UNTRUSTED_RECEIPT_PATH")
    file = root / path
    required(file, file.is_file() and not file.is_symlink()
             and file.resolve(strict=True).is_relative_to(root),
             "MISSING_OR_UNTRUSTED_RECEIPT")
    raw = file.read_bytes()
    required(raw, len(raw) <= 2_000_000, "RECEIPT_TOO_LARGE")
    h = hashlib.sha256(raw).hexdigest()
    required(h, h == latest.get("receipt_sha256"), "RECEIPT_DIGEST_MISMATCH")
    receipt = decode_strict(raw)
    required(receipt, type(receipt) is dict and receipt.get("schema") == "janus.autonomy.snapshot.v1",
             "RECEIPT_SCHEMA_UNVERIFIED")
    s = latest.get("state_sha256")
    required(s, type(s) is str and HEX64.fullmatch(s) is not None
             and receipt.get("state_sha256") == s, "LATEST_STATE_REBINDING")
    required(latest, latest.get("current_phase") == receipt.get("current_phase")
             and latest.get("current_phase") == checkpoint.get("current_phase")
             and receipt.get("ecosystem_status") == "AUTONOMY_PARTIAL"
             and latest.get("ecosystem_status") == "AUTONOMY_PARTIAL"
             and latest.get("full_issue_162_acceptance") is False,
             "PHASE_OR_STATUS_CONTRADICTION")
    return latest, checkpoint, receipt, h


def evaluate(latest, checkpoint, receipt, receipt_digest):
    if any(type(x) is not dict for x in (latest, checkpoint, receipt)):
        raise Hold("INVALID_EVIDENCE_OBJECT")
    if not isinstance(receipt_digest, str) or HEX64.fullmatch(receipt_digest) is None:
        raise Hold("INVALID_EVIDENCE_DIGEST")
    if latest.get("current_phase") != EXPECTED_PHASE:
        raise Hold("PHASE_NOT_P03")
    if receipt.get("state_sha256") != latest.get("state_sha256"):
        raise Hold("RECEIPT_AND_LATEST_MISMATCH")
    findings = receipt.get("findings")
    if not isinstance(findings, list) or not all(type(x) is dict and
            isinstance(x.get("reason"), str) and isinstance(x.get("phase"), str)
            for x in findings):
        raise Hold("FINDINGS_SCHEMA_UNVERIFIED")
    reasons = {x["reason"] for x in findings if x["phase"] == EXPECTED_PHASE}
    preflight = receipt.get("maintenance", {}).get("p03_preflight")
    if not isinstance(preflight, dict) or preflight.get("schema") != "janus.autonomy.p03_preflight.v1":
        raise Hold("P03_PREFLIGHT_MISSING")
    if preflight.get("p03_acceptance") is not False or preflight.get("runtime_consumption_attested") is not False:
        raise Hold("P03_PREFLIGHT_AUTHORITY_ESCALATION")
    if preflight.get("status") not in ("P03_PREFLIGHT_BLOCKED", "P03_PREFLIGHT_CANDIDATE_ONLY",
                                      "HOLD_P03_SOURCE_INTEGRITY"):
        raise Hold("P03_PREFLIGHT_UNKNOWN_STATUS")
    snapshot = latest["state_sha256"]
    anchored = snapshot == checkpoint.get("last_verified_snapshot")
    p03_admitted = isinstance(checkpoint.get("accepted_phases"), dict) and isinstance(
        checkpoint["accepted_phases"].get(EXPECTED_PHASE), dict)
    # These lane names are fixed by reviewed source, never generated from an
    # untrusted model message. All external unobserved evidence fails closed.
    gates = {
        "checkpoint_matches_current": "MATCHES_LOCAL_BYTES_NOT_EXTERNAL_VERIFIED"
                                      if anchored else "HOLD_SNAPSHOT_DRIFT",
        "p03_phase_admitted": "HOLD_LOCAL_CLAIM_NOT_INDEPENDENTLY_ATTESTED"
                              if p03_admitted else "HOLD_NOT_ADMITTED",
        "beetle_telemetry_fresh": "HOLD_STALE" if {
             "BEETLE_DELIVERY_HEALTH_STALE", "BEETLE_ROUTING_GATE_STALE"
             } & reasons else "UNKNOWN_NEEDS_LIVE_RECHECK",
        "public_beetle_delivery": "HOLD_PENDING" if preflight.get("public_receiver_pending") else
                                   "CLAIMED_ZERO_PENDING_NOT_CONSUMED",
        "private_ack_replayed_independently": "HOLD_PRIVATE_AUTH_UNVERIFIED",
        "cloud_home_context_consumed": "HOLD_NO_RUNTIME_CONSUMPTION_WITNESS",
        "source_router_admitted": "HOLD_PRODUCER_ROUTING" if
                                  {"PRODUCER_ROUTING_HELD", "BEETLE_ROUTING_HELD"} & reasons else
                                  "UNKNOWN_NEEDS_LIVE_RECHECK",
        "fork_and_organ_effects": "DISABLED_AWAITING_EXTERNAL_REVIEW"
    }
    # A producer's claimed ACK cannot certify true private receiver replay.
    private_visibility = preflight.get("private_ack_visibility")
    if private_visibility not in ("UNAVAILABLE",
             "CLAIMED_IN_PRODUCER_TELEMETRY_NOT_INDEPENDENTLY_REPLAYED"):
        raise Hold("PRIVATE_ACK_PRODUCER_OVERCLAIM")
    if type(preflight.get("private_receiver_pending")) is not int:
        raise Hold("PRIVATE_PENDING_TYPE")
    if type(preflight.get("public_receiver_pending")) is not int:
        raise Hold("PUBLIC_PENDING_TYPE")
    if preflight["public_receiver_pending"] < 0 or preflight.get("private_receiver_pending", 0) < 0:
        raise Hold("NEGATIVE_PENDING")
    output = {
        "schema": SCHEMA,
        "status": "P03_RECOVERY_REVIEW_REQUIRED",
        "snapshot_sha256": snapshot,
        "checkpoint_verified_snapshot": checkpoint.get("last_verified_snapshot"),
        "source_receipt_sha256": receipt_digest,
        "observed_at_utc": receipt.get("observed_at_utc"),
        "snapshot_based_only": True,
        "live_github_recheck_performed": False,
        "phase": EXPECTED_PHASE,
        "p03_preflight_status": preflight["status"],
        "private_ack_producer_visibility": private_visibility,
        "public_pending": preflight["public_receiver_pending"],
        "private_pending": preflight.get("private_receiver_pending", 0),
        "source_holds": sorted(reasons),
        "gates": gates,
        "next_ordered_verifications": [
            "INDEPENDENT_REPLAY_PRIVATE_RECEIVER_ACK_NOT_PRODUCER_CLAIM",
            "INDEPENDENT_CLOUD_HOME_CONTEXT_CONSUMPTION_WITNESS",
            "REFRESH_SOURCE_COHORT_WITH_FRESHNESS_AND_HIGHEST_COMMIT",
            "REVIEWED_P03_PHASE_ADMISSION_AND_ANCHORED_CHECKPOINT",
            "SEPARATELY_REVIEW_OPERATOR_CAPABILITY_AND_ROLLBACK"
        ],
        "admission_granted": False,
        "dispatch_performed": False,
        "weights_changed": False,
        "fork_performed": False,
        "source_mutated": False,
        "independent_external_witness_completed": False,
        "self_report_is_not_health_authority": True,
    }
    output["sha256"] = hashlib.sha256(json.dumps(output,sort_keys=True,
                   separators=(",", ":"),ensure_ascii=False).encode("utf-8")).hexdigest()
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    latest, checkpoint, receipt, sha = read_evidence(args.root)
    result = evaluate(latest, checkpoint, receipt, sha)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    if args.out.exists():
        raise Hold("OUTPUT_ALREADY_EXISTS")
    args.out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"gates":result["gates"],
                      "source_sha256":result["source_receipt_sha256"],
                      "authority_delta":0},sort_keys=True))


if __name__ == "__main__":
    main()
