#!/usr/bin/env python3
"""JANUS Rowan pipeline watchdog: cross-check durable science source and mirrors.

No Rowan token, no provider calls or workflow dispatch. All check results are
observation-only and cannot authorize new studies, billing or model promotion.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import subprocess

BASE = Path("data/rowan")
WORKFLOW_ENDPOINT = (
    "repos/Hawkar-usls/Janus/actions/workflows/"
    "rowan-bbc1-stratified-pilot.yml/runs?per_page=30&branch=main"
)
GRACE_HOURS = 12
PILOT_STALL_HOURS = 36
FROZEN_CAP = 8
SCHEMA = "janus.rowan.pipeline_integrity_state.v1"

class WatchdogHold(ValueError):
    pass

def _time(value):
    if not isinstance(value, str):
        raise WatchdogHold("INVALID_RUN_TIMESTAMP")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WatchdogHold("BAD_RUN_TIMESTAMP") from exc

def _id(x):
    if type(x) is not int or x <= 0:
        raise WatchdogHold("BAD_RUN_ID")
    return x

def load(path):
    path = Path(path)
    if path.stat().st_size > 100000:
        raise WatchdogHold("JSON_OVERSIZE")
    return json.loads(path.read_text(encoding="utf-8"))

def _matching_receipts(root, state):
    run_id = _id(state.get("latest_durable_external_run"))
    digest = state.get("underlying_state_is_derived_from")
    if not isinstance(digest, str) or len(digest) != 64:
        raise WatchdogHold("SOURCE_HASH_INVALID")
    found = []
    for p in sorted((root / BASE / "receipts").glob(f"ROWAN-S2-{run_id}-*.json")):
        x = load(p)
        src = x.get("source", {})
        if (src.get("run_id") == run_id and
            src.get("source_artifact_sha256") == digest and
            x.get("calibration", {}).get("eight_mutants_with_provider_results") ==
                state.get("last_completed_mutants")):
            found.append(hashlib.sha256(p.read_bytes()).hexdigest()[:20])
    if not found:
        raise WatchdogHold("CANONICAL_RECEIPT_NOT_REPRODUCIBLE")
    return sorted(found)

def _topa_status(root):
    models = sorted((root / BASE / "learned").glob("SHADOW-BBC1-*.json"))
    reviews = sorted((root / BASE / "topa").glob("TOPA-SHADOW-*.json"))
    if not models or not reviews:
        return "MISSING_SHADOW_AUDIT"
    valid = set()
    for p in reviews:
        report = load(p)
        if (report.get("schema_id") == "janus.topa.independent_shadow_replay.v1"
                and report.get("audit") == "PASS_INDEPENDENT_WITHIN_ASSAY_REPLAY"
                and report.get("promotion_gate") == "SHADOW_ONLY"
                and report.get("fundamental_model_weights_updated") is False):
            valid.add(report.get("model_file_sha256"))
    return ("PASS_INDEPENDENT_NUMERICAL_REPLAY"
            if all(hashlib.sha256(p.read_bytes()).hexdigest() in valid for p in models)
            else "MODEL_OR_REPLAY_UNATTESTED")

def evaluate(root, runs, *, now=None, previous=None):
    root = Path(root)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise WatchdogHold("TIMEZONE_REQUIRED")
    state = load(root / BASE / "CANONICAL_STATE.json")
    if state.get("schema_id") != "janus.rowan.observer_state.v1":
        raise WatchdogHold("CANONICAL_SCHEMA_DRIFT")
    archived_id = _id(state.get("latest_durable_external_run"))
    completed = state.get("last_completed_mutants")
    if type(completed) is not int or not 0 <= completed <= FROZEN_CAP:
        raise WatchdogHold("PILOT_PROGRESS_INVALID")
    if state.get("autonomous_spend_authority") != "ONLY_FROZEN_EIGHT_MUTANT_S2_WITH_EXISTING_WEEKLY_BUDGET":
        raise WatchdogHold("SPENDING_AUTHORITY_DRIFT")
    if state.get("new_unreviewed_studies") != "PROPOSAL_ONLY_NOT_AUTO_EXECUTED":
        raise WatchdogHold("SCIENTIFIC_AUTHORITY_DRIFT")
    if previous and type(previous.get("completed_mutants")) is int and previous["completed_mutants"] > completed:
        raise WatchdogHold("PROGRESS_REGRESSION")
    attested = _matching_receipts(root, state)
    if not isinstance(runs, list) or len(runs) > 30:
        raise WatchdogHold("RUN_LIST_INVALID")
    allowed = [r for r in runs if isinstance(r, dict) and r.get("head_branch") == "main"
               and r.get("event") in ("schedule", "workflow_dispatch")
               and r.get("status") == "completed"]
    success = [r for r in allowed if r.get("conclusion") == "success"]
    if not success:
        raise WatchdogHold("NO_SUCCESSFUL_PILOT_SOURCE")
    success.sort(key=lambda x: _id(x.get("id")), reverse=True)
    latest = success[0]
    newest_id = _id(latest["id"])
    hours = max(0.0, (now - _time(latest.get("created_at"))).total_seconds() / 3600)
    if newest_id < archived_id:
        raise WatchdogHold("GITHUB_RUN_HISTORY_BEHIND_ARCHIVE")
    status = "ARCHIVE_CURRENT" if newest_id == archived_id else (
        "ARCHIVE_LAG_OVER_12H" if hours > GRACE_HOURS else "ARCHIVE_PENDING_WITHIN_GRACE")
    pilot = ("EIGHT_CASES_ATTESTED"
             if completed == FROZEN_CAP
             else ("PILOT_STALLED_OVER_36H" if hours > PILOT_STALL_HOURS else "PILOT_ACTIVE"))
    failures = [r for r in allowed if r.get("conclusion") == "failure" and _id(r.get("id")) > newest_id]
    failure_status = "REPEATED_POST_SUCCESS_FAILURES" if len(failures) >= 2 else (
        "ONE_POST_SUCCESS_FAILURE" if failures else "NO_UNRECOVERED_FAILURE")
    alerts = state.get("budget_guard_alert_mutations")
    if not isinstance(alerts, list):
        raise WatchdogHold("INVALID_BUDGET_ALERTS")
    council_file = root / BASE / "coordination" / "LATEST_COORDINATION_STATE.json"
    if council_file.exists():
        council = load(council_file)
        cid = council.get("meta_canonical_run")
        if type(cid) is not int or cid > archived_id:
            raise WatchdogHold("COUNCIL_SOURCE_RUN_INCONSISTENT")
        council_status = ("COUNCIL_CURRENT" if cid == archived_id else
                          ("COUNCIL_LAG_OVER_12H" if hours > GRACE_HOURS
                           else "COUNCIL_PENDING_WITHIN_GRACE"))
    else:
        council_status = "COUNCIL_MISSING"
    topa = _topa_status(root)
    severity = ("ACTION_REQUIRED" if (status == "ARCHIVE_LAG_OVER_12H"
                 or pilot == "PILOT_STALLED_OVER_36H"
                 or failure_status == "REPEATED_POST_SUCCESS_FAILURES"
                 or council_status in ("COUNCIL_LAG_OVER_12H", "COUNCIL_MISSING")
                 or topa != "PASS_INDEPENDENT_NUMERICAL_REPLAY" or bool(alerts))
                else "MONITORING")
    return {
        "schema_id": SCHEMA,
        "latest_completed_source_run": newest_id,
        "latest_archived_source_run": archived_id,
        "completed_mutants": completed,
        "archived_receipt_sha256_prefixes": attested,
        "archive_status": status,
        "pilot_status": pilot,
        "workflow_failure_status": failure_status,
        "coordination_status": council_status,
        "independent_TOPA_shadow_status": topa,
        "credit_cap_violations": sorted(str(x)[:20] for x in alerts),
        "severity": severity,
        "science_gates": {
            "wetlab_independent_validation": "OPEN",
            "assay_units_and_replicates": "UNVERIFIED",
            "outcome_stratified_bias": "NOT_ELIMINATED",
            "new_computation_authorized_by_watchdog": False,
            "new_billing_authorized_by_watchdog": False,
            "model_production_promotion": False,
        },
    }

def github_runs():
    p = subprocess.run(["gh", "api", "--method", "GET", WORKFLOW_ENDPOINT],
                       capture_output=True, text=True, timeout=40)
    if p.returncode != 0:
        raise WatchdogHold("GITHUB_RUN_ENDPOINT_UNAVAILABLE")
    result = json.loads(p.stdout)
    return result.get("workflow_runs")

def run(root="."):
    root = Path(root)
    dest = root / BASE / "health" / "PIPELINE_STATE.json"
    previous = load(dest) if dest.exists() else None
    report = evaluate(root, github_runs(), previous=previous)
    dest.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(report, sort_keys=True, indent=2).encode("utf-8") + b"\n"
    if not dest.exists() or dest.read_bytes() != raw:
        dest.write_bytes(raw)
    fingerprint = hashlib.sha256(raw).hexdigest()
    immutable = dest.parent / "receipts" / (
        f"ROWAN-PIPELINE-{report['latest_archived_source_run']}-{fingerprint[:16]}.json")
    immutable.parent.mkdir(parents=True, exist_ok=True)
    if immutable.exists() and immutable.read_bytes() != raw:
        raise WatchdogHold("HEALTH_RECEIPT_IMMUTABILITY_DRIFT")
    if not immutable.exists():
        immutable.write_bytes(raw)
    print("ROWAN_WATCHDOG=" + report["severity"])
    print("ROWAN_WATCHDOG_ARCHIVE=" + report["archive_status"])
    print("ROWAN_WATCHDOG_PILOT=" + report["pilot_status"])
    print("ROWAN_WATCHDOG_TOPA=" + report["independent_TOPA_shadow_status"])
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(run())
    except (WatchdogHold, OSError, ValueError, subprocess.SubprocessError):
        print("ROWAN_WATCHDOG=PROVENANCE_OR_NETWORK_HOLD")
        raise SystemExit(2)
