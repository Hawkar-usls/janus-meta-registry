#!/usr/bin/env python3
"""Trusted, non-authoritative archival of read-only JANUS witness evidence.

The collector is *not* an external witness and does not grant runtime/science authority.
Only the trusted Meta Registry workflow can commit its observations.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UTC = dt.timezone.utc
API = "https://api.github.com"
HOME_REPO = "Hawkar-usls/Janus_Genesis"
LAPIS_REPO = "Hawkar-usls/janus-lapis"
PRIVATE_REPO = "Hawkar-usls/SkinGPT"
ISSUE_URL = f"https://github.com/{LAPIS_REPO}/issues/21"
HOME_PATH = "state/habitat_cloud_home/STATE.json"
QUEUE_PATH = "data/beetle-state/mirrors/Hawkar-usls__SkinGPT/delivery.json"
ACK_PATH = "data/beetle-inbox/ACK.json"
HOME_BRANCH = "janus/habitat-cloud-state"
LINE_NAMES = {
    "beetle_producer": (LAPIS_REPO, "JANUS Universal Beetle hourly"),
    "beetle_local_receiver": (LAPIS_REPO, "JANUS Beetle Memory Receiver"),
    "beetle_genesis_watchdog": (LAPIS_REPO, "JANUS Beetle → Genesis durable delivery watchdog"),
    "genesis_home": (HOME_REPO, "JANUS Habitat Cloud HOME v1"),
    "genesis_receiver": (HOME_REPO, "JANUS Beetle Memory Receiver"),
}
HEX = re.compile(r"^[a-f0-9]{64}$")
SHA = re.compile(r"^[a-f0-9]{40}$")
HIGHWATER = re.compile(r"<!--\s*janus\.genesis\.home\.highwater\.v1\s*-->[\s\S]*?```json\s*([\s\S]*?)\s*```")
ACTIVE = {"queued", "in_progress", "pending", "waiting", "requested"}


def iso(now: dt.datetime) -> str:
    return now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(s: str) -> dt.datetime:
    if not isinstance(s, str):
        raise ValueError("missing UTC timestamp")
    d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("timestamp without timezone")
    return d.astimezone(UTC)


def json_sha(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def require_hex(value: object, pattern=HEX) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError("malformed digest")
    return value


def natural_int(value: object, minimum=0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError("invalid sequence")
    return value


class GitHub:
    def __init__(self, public_token: str, private_token: str | None = None):
        self.public_token = public_token
        self.private_token = private_token

    def get(self, path: str, *, private=False):
        token = self.private_token if private else self.public_token
        if private and not token:
            raise PermissionError("PRIVATE_READ_TOKEN_NOT_CONFIGURED")
        request = urllib.request.Request(API + path, headers={
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "janus-trusted-witness-importer/1.0",
            **({"Authorization": "Bearer " + token} if token else {}),
        })
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.load(response)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            # Never leak credentials, private bodies, or paths in exception logs.
            raise RuntimeError("GITHUB_API_UNAVAILABLE") from None

    def contents(self, repo: str, path: str, ref: str, *, private=False):
        import base64
        url = f"/repos/{repo}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(ref, safe='')}"
        obj = self.get(url, private=private)
        if obj.get("encoding") != "base64" or obj.get("type") != "file":
            raise ValueError("CONTENT_ENCODING_UNSUPPORTED")
        raw = base64.b64decode(obj["content"], validate=False)
        return json.loads(raw), require_hex(obj["sha"], SHA)


def validate_queue_ack(queue: dict, ack: dict) -> dict:
    if queue.get("schema") != "janus.beetle.delivery_queue.v1":
        raise ValueError("QUEUE_SCHEMA_INVALID")
    if queue.get("target_repository") != PRIVATE_REPO:
        raise ValueError("QUEUE_TARGET_INVALID")
    entries = queue.get("entries")
    if not isinstance(entries, list):
        raise ValueError("QUEUE_ENTRIES_INVALID")
    for i, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or natural_int(entry.get("sequence"), 1) != i:
            raise ValueError("QUEUE_SEQUENCE_INVALID")
        if not isinstance(entry.get("batch_id"), str) or not entry["batch_id"]:
            raise ValueError("QUEUE_BATCH_INVALID")
        require_hex(entry.get("sha256"))
        parse_iso(entry.get("created_at"))
    if natural_int(queue.get("next_sequence"), 1) != len(entries) + 1:
        raise ValueError("QUEUE_NEXT_SEQUENCE_INVALID")
    if ack.get("schema") != "janus.beetle.inbox_ack.v1" or ack.get("target_repository") != PRIVATE_REPO:
        raise ValueError("ACK_SCHEMA_OR_TARGET_INVALID")
    if ack.get("status") != "INBOX_DURABLE_UNVERIFIED__NOT_RUNTIME_CONSUMPTION":
        raise ValueError("ACK_STATUS_INVALID")
    if type(ack.get("scientific_authority_delta")) is not int or ack["scientific_authority_delta"] != 0:
        raise ValueError("ACK_AUTHORITY_INVALID")
    last = natural_int(ack.get("last_sequence"))
    if last > len(entries):
        raise ValueError("ACK_SEQUENCE_AHEAD_OF_QUEUE")
    if last:
        item = entries[last - 1]
        if ack.get("batch_id") != item["batch_id"] or ack.get("sha256") != item["sha256"]:
            raise ValueError("ACK_BATCH_OR_HASH_MISMATCH")
    pending = len(entries) - last
    # Do not reproduce private messages or packet bodies in registry.
    return {"status": "VERIFIED_DURABLE_INBOX_ACK" if pending == 0 else "ACK_PENDING",
            "last_sequence": last, "queue_sequence": len(entries), "next_sequence": len(entries) + 1,
            "pending": pending, "ack_batch_id": ack.get("batch_id") if last else None,
            "evidence_sha256": ack.get("sha256") if last else None,
            "oldest_unacked_created_at": entries[last]["created_at"] if pending else None}


def classify_ack(queue: dict, ack: dict, now: dt.datetime) -> dict:
    data = validate_queue_ack(queue, ack)
    if data["pending"]:
        age = (now - parse_iso(data["oldest_unacked_created_at"])).total_seconds() / 60
        data["oldest_unacked_minutes"] = round(age, 2)
        if age >= 360:
            data["status"] = "ACK_DELAY_OVER_360_MIN"
    return data


def classify_highwater(issue_body: str, state: dict, state_commit: str, commit_time: str, now: dt.datetime) -> dict:
    match = HIGHWATER.search(issue_body)
    if not match:
        raise ValueError("HIGHWATER_RECORD_ABSENT")
    anchor = json.loads(match.group(1))
    if anchor.get("schema") != "janus.genesis.home.highwater.v1" or anchor.get("source_repository") != HOME_REPO:
        raise ValueError("HIGHWATER_SCHEMA_INVALID")
    if state.get("schema") != "JANUS_HABITAT_CLOUD_HOME_STATE_V1":
        raise ValueError("HOME_SCHEMA_INVALID")
    current = natural_int(state.get("sequence"))
    sequence = natural_int(anchor.get("sequence"))
    home_receipt = require_hex(state.get("last_receipt_sha256"))
    anchor_receipt = require_hex(anchor.get("receipt_sha256"))
    pinned_commit = require_hex(anchor.get("home_commit_sha"), SHA)
    require_hex(state_commit, SHA)
    age = (now - parse_iso(commit_time)).total_seconds() / 60
    if current < sequence:
        status = "POSSIBLE_GENESIS_ROLLBACK"
    elif current > sequence:
        status = "HIGHWATER_ANCHOR_LAG" if age >= 60 else "ANCHOR_PENDING_WITHIN_GRACE"
    elif home_receipt == anchor_receipt and state_commit == pinned_commit:
        status = "ANCHOR_MATCH"
    else:
        status = "HIGHWATER_UNKNOWN"  # equal seq but inconsistent SHA/commit
    return {"status": status, "home_sequence": current, "anchor_sequence": sequence,
            "home_receipt_sha256": home_receipt, "anchor_receipt_sha256": anchor_receipt,
            "home_commit_sha": state_commit, "anchor_commit_sha": pinned_commit,
            "home_committed_at": commit_time, "home_commit_age_minutes": round(age, 2),
            "issue_url": ISSUE_URL, "home_commit_url": f"https://github.com/{HOME_REPO}/commit/{state_commit}"}


def classify_workflow(runs: list, repo: str, name: str, now: dt.datetime, get_jobs=None) -> dict:
    selected = [r for r in runs if r.get("name") == name and r.get("head_branch") == "main" and r.get("event") == "schedule"]
    success = sorted([r for r in selected if r.get("status") == "completed" and r.get("conclusion") == "success"],
                     key=lambda r: r.get("created_at", ""), reverse=True)
    active = sorted([r for r in selected if r.get("status") in ACTIVE],
                    key=lambda r: r.get("created_at", ""), reverse=True)
    ret = {"status": "UNKNOWN", "workflow": name, "repository": repo, "last_schedule_run": None,
           "active_schedule_run": active[0].get("html_url") if active else None}
    if name == "JANUS Beetle → Genesis durable delivery watchdog":
        anysuccess = sorted([r for r in runs if r.get("name") == name and r.get("head_branch") == "main" and
                             r.get("event") in {"push", "workflow_dispatch", "schedule"} and
                             r.get("status") == "completed" and r.get("conclusion") == "success"],
                            key=lambda r: r.get("created_at", ""), reverse=True)
        ret["last_any_success_main"] = {"run_url": anysuccess[0].get("html_url"),
                                        "event": anysuccess[0].get("event")} if anysuccess else None
    if not success:
        ret["reason"] = "NO_CONFIRMED_SCHEDULE_SUCCESS_IN_FETCHED_HISTORY"
        return ret
    latest = success[0]
    finished = None
    if get_jobs is not None:
        try:
            job_rows = get_jobs(latest["id"])
            if not isinstance(job_rows, list) or not job_rows:
                raise ValueError("NO_JOB_HISTORY")
            finished_rows = [parse_iso(j["completed_at"]) for j in job_rows
                             if j.get("completed_at") is not None]
            if not finished_rows:
                raise ValueError("NO_COMPLETED_JOB")
            finished = max(finished_rows)
        except (KeyError, ValueError, RuntimeError):
            pass
    ret["last_schedule_run"] = {"run_id": latest.get("id"), "run_url": latest.get("html_url"),
                                  "created_at": latest.get("created_at"),
                                  "completed_at": iso(finished) if finished else None}
    if finished is None:
        ret["reason"] = "COMPLETED_AT_UNVERIFIED"
        return ret
    age = (now - finished).total_seconds() / 60
    ret["age_minutes"] = round(age, 2)
    if active:
        running_age = max((now - parse_iso(r["created_at"])).total_seconds() / 60 for r in active)
        ret["active_schedule_age_minutes"] = round(running_age, 2)
        ret["status"] = "SCHEDULE_LONG_RUNNING" if running_age >= 360 else "SCHEDULE_ACTIVE"
    else:
        ret["status"] = "SCHEDULE_SILENCE" if age >= 360 else "SCHEDULE_OK"
    return ret


def get_runs(gh: GitHub, repo: str, now: dt.datetime) -> tuple[list, bool]:
    # Fetch at least the newest 100 where present. Continue pages to locate last
    # successes; cap resource use, and never turn incomplete history into silence.
    rows: list = []
    complete = False
    for page in range(1, 11):
        payload = gh.get(f"/repos/{repo}/actions/runs?per_page=100&page={page}")
        batch = payload.get("workflow_runs")
        if not isinstance(batch, list):
            raise ValueError("WORKFLOW_RUNS_INVALID")
        rows += batch
        if len(batch) < 100:
            complete = True
            break
        # All lines observed at least once as *successful scheduled* and a
        # reasonable lookback? Older history is not required beyond those.
        names = [name for r, name in LINE_NAMES.values() if r == repo]
        if all(any(x.get("name") == n and x.get("head_branch") == "main" and
                   x.get("event") == "schedule" and x.get("conclusion") == "success" and
                   x.get("status") == "completed" for x in rows) for n in names):
            complete = True
            break
    return rows, complete


def observe(gh: GitHub, now: dt.datetime) -> dict:
    observations: dict = {}
    for repo in (LAPIS_REPO, HOME_REPO):
        keys = [(key, name) for key, (r, name) in LINE_NAMES.items() if r == repo]
        try:
            runs, complete = get_runs(gh, repo, now)
            if not complete:
                raise ValueError("INCOMPLETE_RUN_HISTORY")
            def jobs(run_id):
                payload = gh.get(f"/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100")
                if payload.get("total_count", 0) > 100:
                    raise ValueError("INCOMPLETE_JOB_HISTORY")
                return payload.get("jobs", [])
            for key, name in keys:
                observations[key] = classify_workflow(runs, repo, name, now, jobs)
        except (RuntimeError, ValueError, KeyError, TypeError) as exc:
            for key, name in keys:
                observations[key] = {"status": "UNKNOWN", "workflow": name, "repository": repo,
                                     "reason": type(exc).__name__}
    try:
        issue = gh.get(f"/repos/{LAPIS_REPO}/issues/21")
        ref = gh.get(f"/repos/{HOME_REPO}/git/ref/heads/{HOME_BRANCH}")
        head = require_hex(ref["object"]["sha"], SHA)
        state, state_blob = gh.contents(HOME_REPO, HOME_PATH, head)
        commits = gh.get(f"/repos/{HOME_REPO}/commits?sha={head}&path={HOME_PATH}&per_page=1")
        if not isinstance(commits, list) or not commits:
            raise ValueError("HOME_COMMIT_NOT_FOUND")
        touched = require_hex(commits[0]["sha"], SHA)
        date = commits[0]["commit"]["committer"]["date"]
        observations["genesis_highwater"] = classify_highwater(issue["body"], state, touched, date, now)
        observations["genesis_highwater"]["home_state_blob_sha"] = state_blob
    except (RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        observations["genesis_highwater"] = {"status": "HIGHWATER_UNKNOWN", "reason": type(exc).__name__,
                                             "issue_url": ISSUE_URL}
    try:
        if not gh.private_token:
            observations["skingpt_ack"] = {"status": "UNKNOWN", "reason": "PRIVATE_READ_TOKEN_NOT_CONFIGURED"}
        else:
            queue, qb = gh.contents(LAPIS_REPO, QUEUE_PATH, "beetle-state")
            ack, ab = gh.contents(PRIVATE_REPO, ACK_PATH, "beetle-memory", private=True)
            observations["skingpt_ack"] = classify_ack(queue, ack, now)
            observations["skingpt_ack"].update({
                "sender_blob_sha": qb, "receiver_blob_sha": ab,
                "sender_url": f"https://github.com/{LAPIS_REPO}/blob/beetle-state/{QUEUE_PATH}",
                "receiver_url": f"https://github.com/{PRIVATE_REPO}/blob/beetle-memory/{ACK_PATH}"})
    except ValueError as exc:
        # Data was actually read, validated and contradicted; don't mistake
        # schema or hash failures for a transport outage.
        observations["skingpt_ack"] = {"status": "ACK_INCONSISTENT", "reason": str(exc)}
    except (RuntimeError, PermissionError, KeyError, TypeError) as exc:
        observations["skingpt_ack"] = {"status": "UNKNOWN", "reason": type(exc).__name__}
    return observations


ALERT_CLASSES = {"SCHEDULE_SILENCE", "SCHEDULE_LONG_RUNNING", "HIGHWATER_ANCHOR_LAG", "POSSIBLE_GENESIS_ROLLBACK",
                 "ACK_INCONSISTENT", "ACK_DELAY_OVER_360_MIN"}
NORMAL_CLASSES = {"SCHEDULE_OK", "VERIFIED_DURABLE_INBOX_ACK", "ANCHOR_MATCH"}
NEUTRAL_CLASSES = {"SCHEDULE_ACTIVE", "ACK_PENDING", "ANCHOR_PENDING_WITHIN_GRACE"}


def persist(root: Path, observed: dict, checked_at: dt.datetime, run_id: str, attempt: str,
            collector_sha: str) -> dict:
    if not run_id.isdecimal() or not attempt.isdecimal():
        raise ValueError("TRUSTED_RUN_ID_REQUIRED")
    if not SHA.fullmatch(collector_sha):
        raise ValueError("TRUSTED_COLLECTOR_SHA_REQUIRED")
    base = root / "data/witness_importer"
    date = checked_at.date().isoformat()
    loc = base / "observations" / date / f"{run_id}-{attempt}.json"
    latest = base / "LATEST.json"
    old = json.loads(latest.read_text(encoding="utf-8")) if latest.exists() else None
    previous = (old or {}).get("line_states", {})
    transitions = []
    updated = {}
    for key, detail in sorted(observed.items()):
        status = detail["status"]
        prev = previous.get(key, {})
        prior_status = prev.get("status")
        # UNKNOWN must not erase a previously confirmed fault or the high-water.
        if status in ("UNKNOWN", "HIGHWATER_UNKNOWN") or (status in NEUTRAL_CLASSES and prior_status in ALERT_CLASSES):
            updated[key] = {**prev, "last_observed_at": iso(checked_at), "last_observation_status": status} \
                if prev else {"status": status, "last_observed_at": iso(checked_at)}
            continue
        updated[key] = {"status": status, "last_observed_at": iso(checked_at)}
        if key == "genesis_highwater":
            updated[key]["max_home_sequence"] = max(detail.get("home_sequence", 0), prev.get("max_home_sequence", 0))
            updated[key]["max_anchor_sequence"] = max(detail.get("anchor_sequence", 0), prev.get("max_anchor_sequence", 0))
        if status in ALERT_CLASSES:
            if status != prior_status:
                transitions.append({"line": key, "from": prior_status, "to": status, "class": status,
                                    "occurred_at": iso(checked_at), "evidence": detail})
        elif prior_status in ALERT_CLASSES and status in NORMAL_CLASSES:
            transitions.append({"line": key, "from": prior_status, "to": status, "class": "RECOVERED",
                                "occurred_at": iso(checked_at), "evidence": detail})
    receipt = {"schema": "janus.external_witness.import_receipt.v1", "observed_at_utc": iso(checked_at),
               "collector": {"type": "TRUSTED_META_REGISTRY_IMPORTER_NOT_EXTERNAL_WITNESS",
                             "repository": "Hawkar-usls/janus-meta-registry", "run_id": run_id,
                             "run_attempt": attempt, "source_commit_sha": collector_sha},
               "observations": observed, "transitions": transitions,
               "authority": {"runtime_execution": False, "scientific_proof": False,
                             "command_authority": False, "scientific_authority_delta": 0}}
    receipt["receipt_sha256"] = json_sha({k: v for k, v in receipt.items() if k != "receipt_sha256"})
    if loc.exists():
        existing = json.loads(loc.read_text(encoding="utf-8"))
        if existing != receipt:
            raise ValueError("IMMUTABLE_RECEIPT_COLLISION")
        return {"wrote": False, "transitions": 0, "path": str(loc)}
    loc.parent.mkdir(parents=True, exist_ok=True)
    loc.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    new_latest = {"schema": "janus.external_witness.latest.v1", "last_observed_at_utc": iso(checked_at),
                  "last_receipt": loc.relative_to(root).as_posix(),
                  "last_receipt_sha256": receipt["receipt_sha256"], "line_states": updated}
    latest.write_text(json.dumps(new_latest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if transitions:
        tpath = base / "transitions" / date / f"{run_id}-{attempt}.json"
        tpath.parent.mkdir(parents=True, exist_ok=True)
        tpath.write_text(json.dumps({"schema": "janus.external_witness.transitions.v1", "events": transitions,
                                     "source_receipt_sha256": receipt["receipt_sha256"]},
                                    ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"wrote": True, "transitions": len(transitions), "path": str(loc)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    checked = dt.datetime.now(UTC)
    gh = GitHub(os.environ.get("GH_TOKEN", ""), os.environ.get("WITNESS_PRIVATE_READ_TOKEN"))
    observed = observe(gh, checked)
    outcome = persist(Path(args.root), observed, checked, os.environ.get("GITHUB_RUN_ID", ""),
                      os.environ.get("GITHUB_RUN_ATTEMPT", ""), os.environ.get("GITHUB_SHA", ""))
    # Only aggregate classes, never private text or credentials.
    print(json.dumps({"wrote": outcome["wrote"], "transitions": outcome["transitions"],
                      "statuses": {k: v["status"] for k, v in observed.items()}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())