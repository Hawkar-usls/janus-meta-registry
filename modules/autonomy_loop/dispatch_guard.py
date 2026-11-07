#!/usr/bin/env python3
"""Bounded, fail-closed GitHub Actions pacemaker for existing JANUS workflows.

This worker does not admit scientific results, install generated code or modify
runtime/source state. Its sole mutation is one explicitly approved same-repo
workflow_dispatch after trustworthy GitHub run-history and phase checks.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = "Hawkar-usls/janus-meta-registry"
SCHEMA = "janus.autonomy.bounded_wake_policy.v1"
LANES = {
    "janus-autonomy-roadmap-loop.yml": (
        "JANUS Autonomous Roadmap and Continuation", 120),
    "janus-self-writer-real-operational-consumer.yml": (
        "JANUS Self-Writer Real Operational Consumer", 480),
    "janus-autonomous-coder.yml": (
        "JANUS Autonomous Open-Weight Coder", 720),
}
ACTIVE = {"queued", "in_progress", "waiting", "pending", "requested"}
VALID_EVENTS = {"schedule", "workflow_dispatch", "workflow_run", "push"}
UTC_Z = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")


class Hold(ValueError):
    """An unverified prerequisite cannot grant dispatch authority."""


def iso_utc(value: str) -> datetime:
    if not isinstance(value, str) or UTC_Z.fullmatch(value) is None:
        raise Hold("INVALID_UTC_TIMESTAMP")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Hold("INVALID_UTC_TIMESTAMP") from exc
    if result.tzinfo is None:
        raise Hold("INVALID_UTC_TIMESTAMP")
    return result


def load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise Hold("INVALID_JSON_OBJECT")
    return data


def validate_policy(policy: dict, latest: dict, checkpoint: dict) -> list[dict]:
    if (policy.get("schema") != SCHEMA or policy.get("enabled") is not True
            or policy.get("authority_delta") != 0
            or policy.get("auto_merge") is not False
            or policy.get("paid_model_calls") is not False
            or policy.get("max_dispatches_per_tick") != 1
            or policy.get("github_api_page_size") != 10
            or policy.get("github_api_max_pages") != 10
            or policy.get("required_phases") != ["P0.2", "P0.3"]):
        raise Hold("UNTRUSTED_WAKE_POLICY")
    lanes = policy.get("lanes")
    if not isinstance(lanes, list) or len(lanes) != len(LANES):
        raise Hold("UNTRUSTED_WAKE_LANES")
    found = set()
    for lane in lanes:
        if not isinstance(lane, dict):
            raise Hold("UNTRUSTED_WAKE_LANE")
        workflow = lane.get("workflow")
        if workflow not in LANES or workflow in found:
            raise Hold("UNADMITTED_WORKFLOW_OR_DUPLICATE")
        found.add(workflow)
        name, minimum = LANES[workflow]
        if (lane.get("name") != name or
            type(lane.get("min_gap_minutes")) is not int or
            lane["min_gap_minutes"] < minimum or
            type(lane.get("priority")) is not int or
            lane["priority"] < 1 or
            lane.get("enabled") is not True):
            raise Hold("WAKE_SCOPE_OR_RATE_LIMIT_CHANGED")
    if found != set(LANES) or len({x["priority"] for x in lanes}) != len(lanes):
        raise Hold("WAKE_LANE_PRIORITY_INVALID")
    if (latest.get("schema") != "janus.autonomy.latest.v1"
            or latest.get("current_phase") not in ("P0.2", "P0.3")
            or latest.get("current_phase") != checkpoint.get("current_phase")
            or checkpoint.get("schema") != "janus.autonomy.checkpoint.v1"
            or checkpoint.get("authority_delta") != 0
            or checkpoint.get("unimplemented_handlers_do_not_count_as_done") is not True
            or latest.get("state_sha256") != checkpoint.get("last_verified_snapshot")
            or latest.get("full_issue_162_acceptance") is not False
            or latest.get("ecosystem_status") != "AUTONOMY_PARTIAL"):
        raise Hold("UNVERIFIED_AUTONOMY_CHECKPOINT")
    accepted = checkpoint.get("accepted_phases", {}).get(latest["current_phase"])
    if not isinstance(accepted, dict) or accepted.get("full_issue_162_acceptance") is not False:
        raise Hold("PHASE_ADMISSION_UNVERIFIED")
    return sorted(lanes, key=lambda x: x["priority"])


def validate_workflow_sources(root: Path) -> None:
    for workflow, (name, _) in LANES.items():
        file = root / ".github" / "workflows" / workflow
        if not file.is_file() or file.is_symlink():
            raise Hold("ADMITTED_WORKFLOW_MISSING")
        source = file.read_text(encoding="utf-8")
        if not source.startswith("name: " + name + "\n") or "\n  workflow_dispatch:" not in source:
            raise Hold("ADMITTED_WORKFLOW_CONTRACT_CHANGED")


class GitHub:
    def __init__(self, token: str, repository: str):
        if repository != REPOSITORY or not token:
            raise Hold("UNAUTHORIZED_REPOSITORY_OR_TOKEN")
        self.token = token
        self.repository = repository

    def request(self, path: str, *, method: str = "GET", payload: dict | None = None):
        url = "https://api.github.com/repos/" + self.repository + "/" + path
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method=method, headers={
            "Authorization": "Bearer " + self.token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "JANUS-BOUNDED-WAKE/1",
            **({"Content-Type": "application/json"} if body is not None else {}),
        })
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise Hold("GITHUB_RESPONSE_TOO_LARGE")
            if method == "POST":
                if response.status != 204:
                    raise Hold("GITHUB_DISPATCH_NOT_ACCEPTED")
                return None
            if response.status != 200:
                raise Hold("GITHUB_HISTORY_STATUS_UNVERIFIED")
            return json.loads(raw)

    def history(self, workflow: str) -> list[dict]:
        if workflow not in LANES:
            raise Hold("WORKFLOW_NOT_ALLOWLISTED")
        url_name = urllib.parse.quote(workflow, safe="")
        rows = []
        for page in range(1, 11):
            data = self.request(
                f"actions/workflows/{url_name}/runs?per_page=10&page={page}")
            if not isinstance(data, dict) or not isinstance(data.get("workflow_runs"), list):
                raise Hold("GITHUB_HISTORY_PAGE_UNAVAILABLE")
            batch = data["workflow_runs"]
            total = data.get("total_count")
            if len(batch) > 10 or type(total) is not int or total < 0:
                raise Hold("GITHUB_HISTORY_PAGE_INVALID")
            for run in batch:
                if not isinstance(run, dict):
                    raise Hold("GITHUB_RUN_INVALID")
                # Only the actual main-branch instance of this exact workflow counts.
                if run.get("head_branch") != "main":
                    continue
                if run.get("name") != LANES[workflow][0]:
                    raise Hold("GITHUB_WORKFLOW_IDENTITY_MISMATCH")
                if (type(run.get("id")) is not int or run["id"] < 1
                        or run.get("event") not in VALID_EVENTS
                        or run.get("status") not in ACTIVE | {"completed"}):
                    raise Hold("GITHUB_RUN_METADATA_INVALID")
                created = iso_utc(run.get("created_at"))
                updated = iso_utc(run.get("updated_at"))
                if updated < created:
                    raise Hold("GITHUB_RUN_TIMESTAMP_INCONSISTENT")
                if run["status"] == "completed" and run.get("conclusion") not in (
                    "success", "failure", "cancelled", "timed_out",
                    "skipped", "neutral", "action_required", "stale"):
                    raise Hold("GITHUB_RUN_CONCLUSION_UNKNOWN")
                rows.append({
                    "id": run["id"], "created": created, "updated": updated,
                    "event": run["event"], "status": run["status"],
                    "conclusion": run.get("conclusion"),
                    "url": run.get("html_url"),
                })
            if len(batch) < 10:
                if (page - 1) * 10 + len(batch) < total:
                    raise Hold("GITHUB_HISTORY_PAGINATION_INCOMPLETE")
                break
        if not rows:
            raise Hold("NO_TRUSTED_MAIN_RUN_HISTORY")
        if not any(r["status"] == "completed" and r["conclusion"] == "success" for r in rows):
            raise Hold("NO_PRIOR_TRUSTED_SUCCESS")
        return rows

    def dispatch(self, workflow: str) -> None:
        if workflow not in LANES:
            raise Hold("WORKFLOW_NOT_ALLOWLISTED")
        url_name = urllib.parse.quote(workflow, safe="")
        self.request(f"actions/workflows/{url_name}/dispatches",
                     method="POST", payload={"ref": "main"})


def evaluate(history: list[dict], lane: dict, now: datetime) -> dict:
    if not history or now.tzinfo is None:
        raise Hold("UNVERIFIED_OBSERVATION")
    future = [r for r in history if r["created"] > now.replace(microsecond=now.microsecond)
              and (r["created"] - now).total_seconds() > 90]
    if future:
        raise Hold("GITHUB_RUN_CLOCK_FUTURE")
    active = [r for r in history if r["status"] in ACTIVE]
    if active:
        age = max((now - x["created"]).total_seconds() for x in active)
        return {"status": "HOLD_POSSIBLY_STUCK_ACTIVE_RUN" if age > 7200
                else "HOLD_ACTIVE_RUN", "dispatch": False,
                "last_run_id": max(active, key=lambda r: r["created"])["id"]}
    latest = max(history, key=lambda r: r["updated"])
    age = (now - latest["updated"]).total_seconds()
    if age < -90:
        raise Hold("GITHUB_RUN_CLOCK_FUTURE")
    due = age >= lane["min_gap_minutes"] * 60
    return {
        "status": "WAKE_DUE" if due else "HOLD_RECENT_RUN",
        "dispatch": due,
        "last_run_id": latest["id"],
        "last_event": latest["event"],
        "minutes_since_attempt": max(0, int(age // 60)),
    }


def tick(api: GitHub, lanes: list[dict], now: datetime, *, dry_run: bool) -> dict:
    # Fetch and validate ALL enabled target histories before any dispatch.
    results = []
    for lane in lanes:
        history = api.history(lane["workflow"])
        state = evaluate(history, lane, now)
        results.append({"workflow": lane["workflow"], **state})
    due = next((x for x in results if x["dispatch"]), None)
    if due is None:
        status = "IDLE_ALL_LANES_GATED_OR_FRESH"
    elif dry_run:
        status = "DRY_RUN_WOULD_DISPATCH"
    else:
        # Re-read to catch concurrent trusted runs; never dispatch into a race.
        confirm = evaluate(api.history(due["workflow"]),
                           next(x for x in lanes if x["workflow"] == due["workflow"]), now)
        if not confirm["dispatch"] or confirm["last_run_id"] != due["last_run_id"]:
            status = "HOLD_RACE_NEW_RUN"
            due = None
        else:
            api.dispatch(due["workflow"])
            status = "DISPATCH_ACCEPTED_NOT_EXECUTION_PROVEN"
    return {
        "schema": "janus.autonomy.bounded_wake_receipt.v1",
        "timestamp_utc": now.isoformat().replace("+00:00", "Z"),
        "status": status,
        "selected_workflow": None if due is None else due["workflow"],
        "lanes": results,
        "authority_delta": 0,
        "new_paid_model_calls": False,
        "grants_code_admission": False,
        "auto_merge": False,
        "dispatch_is_success": False,
        "scientific_gate_changed": False,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    now = datetime.now(timezone.utc)
    result = None
    try:
        policy = load(args.root / "data/autonomy_loop/BOUNDED_WAKE_POLICY.json")
        latest = load(args.root / "data/autonomy_loop/LATEST.json")
        checkpoint = load(args.root / "data/autonomy_loop/CHECKPOINT.json")
        lanes = validate_policy(policy, latest, checkpoint)
        validate_workflow_sources(args.root)
        api = GitHub(os.environ.get("GH_TOKEN", ""),
                     os.environ.get("GITHUB_REPOSITORY", ""))
        result = tick(api, lanes, now, dry_run=args.dry_run)
        rc = 0
    except (Hold, OSError, ValueError, urllib.error.URLError) as exc:
        # Do not surface remote text, auth headers or credential-adjacent data.
        result = {
            "schema": "janus.autonomy.bounded_wake_receipt.v1",
            "timestamp_utc": now.isoformat().replace("+00:00", "Z"),
            "status": "HOLD_FAIL_CLOSED",
            "error_class": type(exc).__name__,
            "authority_delta": 0,
            "dispatch_is_success": False,
        }
        rc = 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    print("JANUS_AUTONOMY_BOUNDED_WAKE=" + result["status"])
    print("JANUS_AUTONOMY_DISPATCH_TARGET=" +
          str(result.get("selected_workflow") or "NONE"))
    print("JANUS_AUTONOMY_AUTHORITY_DELTA=0")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
