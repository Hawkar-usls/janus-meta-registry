#!/usr/bin/env python3
"""JANUS Record Drift full-surface runner v0.2.2.

Adds an operational scheduler-latency witness without changing R0-R10 record
classifications. For schedule events it separates:
  expected cron instant -> GitHub run object creation -> observer start.
This exists because GitHub documents that scheduled workflows may be delayed,
especially at the start of an hour.
"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import full_surface_runner as core

ROOT = Path(__file__).resolve().parents[2]
JDIR = ROOT / "registry" / "record_drift"
RUNNER = Path(__file__).resolve()


def exact_path_creation_commit(path):
    x = core.git(
        "log", "--diff-filter=A", "--format=%H", "-n", "1", "--", path,
        check=False,
    )
    return x or None


def parse_iso_z(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def github_run_metadata():
    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    token = os.environ.get("GITHUB_TOKEN")
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    if not (repo and run_id and token):
        return None, "missing_github_context_or_token"
    url = f"{api}/repos/{repo}/actions/runs/{run_id}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "JANUS-Record-Drift/0.2.2",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8")), None
    except Exception as exc:
        return None, f"{type(exc).__name__}:{exc}"


def scheduler_control(entry):
    event = os.environ.get("GITHUB_EVENT_NAME", "unknown")
    cron = os.environ.get("JANUS_CRON_UTC", "17 5 * * *")
    if event != "schedule":
        return {
            "state": "NOT_APPLICABLE",
            "trigger_event": event,
            "configured_cron_utc": cron,
            "reason": "only schedule-triggered runs have a preregistered cron instant",
        }

    meta, err = github_run_metadata()
    if not meta:
        return {
            "state": "CAPTURE_FAILED",
            "trigger_event": event,
            "configured_cron_utc": cron,
            "error": err,
        }

    fields = cron.split()
    if len(fields) != 5 or not fields[0].isdigit() or not fields[1].isdigit():
        return {
            "state": "CAPTURE_FAILED",
            "trigger_event": event,
            "configured_cron_utc": cron,
            "error": "runner supports fixed numeric minute/hour cron for latency witness",
        }

    created = parse_iso_z(meta["created_at"])
    run_started = parse_iso_z(meta["run_started_at"]) if meta.get("run_started_at") else None
    expected = created.replace(hour=int(fields[1]), minute=int(fields[0]), second=0, microsecond=0)
    if expected > created:
        # Defensive handling for a run materialized after UTC midnight for the prior day's cron.
        from datetime import timedelta
        expected -= timedelta(days=1)

    observer_start = parse_iso_z(entry["global_controls"]["C00_EXPERIMENT"]["actual_start_utc"])
    materialization_delay = (created - expected).total_seconds()
    run_start_after_created = (run_started - created).total_seconds() if run_started else None
    observer_after_created = (observer_start - created).total_seconds()

    if materialization_delay <= 300:
        cls = "S0_WITHIN_5_MIN"
    elif materialization_delay <= 1800:
        cls = "S1_SCHEDULE_DELAY_5_TO_30_MIN"
    elif materialization_delay <= 7200:
        cls = "S2_SCHEDULE_DELAY_30_TO_120_MIN"
    else:
        cls = "S3_SCHEDULE_DELAY_OVER_120_MIN"

    return {
        "state": "SUPPORTED_AND_CAPTURED",
        "trigger_event": event,
        "configured_cron_utc": cron,
        "expected_schedule_utc": expected.isoformat(),
        "run_created_at_utc": created.isoformat(),
        "run_started_at_utc": run_started.isoformat() if run_started else None,
        "observer_start_utc": observer_start.isoformat(),
        "scheduler_materialization_delay_seconds": materialization_delay,
        "runner_queue_after_creation_seconds": run_start_after_created,
        "observer_start_after_creation_seconds": observer_after_created,
        "operational_classification": cls,
        "record_drift_classification": "NOT_APPLICABLE",
        "claim_ceiling": "scheduler latency is an operational timing observation, not evidence that stored records changed",
    }


def newest_new_file(before):
    after = set(JDIR.glob("JANUS-RECORD-DRIFT-JOURNAL-*.json"))
    created = sorted(after - before)
    return created[-1] if created else None


def main():
    before = set(JDIR.glob("JANUS-RECORD-DRIFT-JOURNAL-*.json"))
    core.creation_commit = exact_path_creation_commit
    core.RUNNER = RUNNER
    core.main()
    out = newest_new_file(before)
    if out is None:
        raise RuntimeError("v0.2.2 could not locate newly generated journal")
    entry = json.loads(out.read_text(encoding="utf-8"))
    entry["version"] = "0.2.2-full-surface-scheduler-instrumented"
    entry["runner"] = "tools/record_drift/full_surface_runner_v0_2_2.py"
    entry.setdefault("global_controls", {})["C28_SCHEDULER_LATENCY"] = scheduler_control(entry)
    out.write_text(json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "journal": out.relative_to(ROOT).as_posix(),
        "C28_SCHEDULER_LATENCY": entry["global_controls"]["C28_SCHEDULER_LATENCY"],
    }, indent=2))


if __name__ == "__main__":
    main()
