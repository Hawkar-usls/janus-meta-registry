#!/usr/bin/env python3
"""Independent public source-bound GitHub Actions witness for JANUS REAL44.

Only GitHub API workflow-run/job/artifact metadata is read. Source bytes,
private repository names, private pins and encrypted manifests are NEVER read
or imported. Job success alone never attests cross-organ runtime consumption.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Callable

OWNER, REPO = "Hawkar-usls", "Janus_Genesis"
WORKFLOW = "JANUS Real 44 Cloud Materialization v2"
SCHEMA = "janus.nexus.real44.public_github_witness.v1"
REQUIRED_JOBS = ("offline-contract", "worker-a", "worker-b", "verdict")
ALLOWED_EVENTS = ("push", "schedule", "workflow_dispatch")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
ID = re.compile(r"^[1-9][0-9]{1,24}$")
API = "https://api.github.com/repos/Hawkar-usls/Janus_Genesis"


class WitnessHold(Exception):
    pass


def github_api(path: str) -> dict[str, Any]:
    if not path.startswith("/") or ".." in path or len(path) > 240:
        raise WitnessHold("UNSAFE_GITHUB_API_PATH")
    token = os.environ.get("GH_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "janus-real44-independent-source-witness-v1",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise WitnessHold("GITHUB_API_REDIRECT_FORBIDDEN")
    req = urllib.request.Request(API + path, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=20) as resp:
            raw = resp.read(500001)
        if len(raw) > 500000:
            raise WitnessHold("GITHUB_API_RESPONSE_OVERSIZE")
        value = json.loads(raw)
    except (OSError, ValueError, UnicodeError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise WitnessHold("GITHUB_API_UNAVAILABLE") from exc
    if not isinstance(value, dict):
        raise WitnessHold("GITHUB_API_OBJECT_REQUIRED")
    return value


def _exact_id(value: Any) -> int:
    if isinstance(value, bool) or not ID.fullmatch(str(value)):
        raise WitnessHold("RUN_ID_INVALID")
    return int(value)


def inspect(get: Callable[[str], dict[str, Any]] = github_api) -> dict[str, Any]:
    """Observe the newest completed trusted-main live run, never a PR canary."""
    rows = get("/actions/workflows/janus-real44-cloud-materialization-v2.yml/runs?per_page=20").get("workflow_runs")
    if not isinstance(rows, list):
        raise WitnessHold("RUN_LIST_UNAVAILABLE")
    accepted = []
    for row in rows:
        if (not isinstance(row, dict) or row.get("name") != WORKFLOW
                or row.get("head_branch") != "main"
                or row.get("event") not in ALLOWED_EVENTS
                or row.get("status") != "completed"):
            continue
        sha = row.get("head_sha")
        if not isinstance(sha, str) or not SHA40.fullmatch(sha):
            continue
        accepted.append(row)
    if not accepted:
        raise WitnessHold("NO_COMPLETED_TRUSTED_REAL44_RUN")
    latest = max(accepted, key=lambda x: _exact_id(x.get("id")))
    run = _exact_id(latest["id"])
    sha = latest["head_sha"]
    success = latest.get("conclusion") == "success"
    status = "HOLD_LATEST_RUN_NOT_SUCCESS"
    job_ids: dict[str, int] = {}
    artifact_proofs: dict[str, dict[str, Any]] = {}
    if success:
        jobs = get(f"/actions/runs/{run}/jobs?per_page=100").get("jobs")
        artifacts = get(f"/actions/runs/{run}/artifacts?per_page=100").get("artifacts")
        if not isinstance(jobs, list) or not isinstance(artifacts, list):
            raise WitnessHold("RUN_JOBS_OR_ARTIFACTS_UNAVAILABLE")
        for name in REQUIRED_JOBS:
            matched = [j for j in jobs if isinstance(j, dict) and j.get("name") == name]
            if len(matched) != 1 or matched[0].get("status") != "completed" or matched[0].get("conclusion") != "success":
                raise WitnessHold("REQUIRED_CLOUD_JOB_NOT_SUCCESS")
            job_ids[name] = _exact_id(matched[0].get("id"))
        for role, expected_name in (
            ("worker_a", f"janus-real44-cloud-worker-a-public-{run}"),
            ("worker_b", f"janus-real44-cloud-worker-b-public-{run}"),
            ("verdict", f"janus-real44-cloud-public-verdict-{run}"),
        ):
            matches = [a for a in artifacts if isinstance(a, dict) and a.get("name") == expected_name]
            if len(matches) != 1 or matches[0].get("expired") is True:
                raise WitnessHold("PUBLIC_VERDICT_ARTIFACT_NOT_AVAILABLE")
            digest = matches[0].get("digest")
            if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise WitnessHold("PUBLIC_ARTIFACT_DIGEST_INVALID")
            artifact_proofs[role] = {"artifact_id": _exact_id(matches[0].get("id")),
                                      "archive_digest": digest}
        status = "PASS_REAL44_GITHUB_PUBLIC_JOB_AND_ARCHIVE_EVIDENCE"

    report = {
        "schema": SCHEMA,
        "status": status,
        "repository": OWNER + "/" + REPO,
        "workflow": WORKFLOW,
        "source_branch": "main",
        "source_commit": sha,
        "source_run_id": run,
        "source_run_url": f"https://github.com/Hawkar-usls/Janus_Genesis/actions/runs/{run}",
        "event": latest["event"],
        "run_conclusion": latest["conclusion"],
        "job_ids": job_ids,
        "public_artifact_proofs": artifact_proofs,
        "source_scope": {
            "historical_top_level_git_trees": 44,
            "public": 41, "opaque_private": 3,
            "gitlink_recursive_submodule_contents": "NOT_MATERIALIZED",
            "owner_current_repository_inventory": "NOT_ASSESSED_BY_THIS_WITNESS",
        },
        "claim_ceiling": {
            "public_github_job_and_artifact_metadata_verified": success,
            "private_artifact_bytes_inspected": False,
            "private_source_metadata_collected": False,
            "actual_cross_organ_runtime_execution_attested": False,
            "full_issue_162_acceptance": False,
            "new_mutation_or_replay_authority": False,
            "rowan_credits_authorized": False,
            "source_writeback_authorized": False,
        },
        "trust_boundary": "INDEPENDENT_GITHUB_API_METADATA_ONLY_NOT_DECODED_SOURCE_OR_ORGAN_RUNTIME",
    }
    canonical = json.dumps(report, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":")).encode("utf-8")
    report["content_sha256"] = hashlib.sha256(canonical).hexdigest()
    return report


def persist(report: dict[str, Any], root: Path) -> tuple[Path, bool]:
    receipt_dir = root / "data/integrations/nexus_real44/receipts"
    latest = root / "data/integrations/nexus_real44/LATEST.json"
    run = _exact_id(report["source_run_id"])
    digest = str(report["content_sha256"])
    receipt = receipt_dir / f"REAL44-{run}-{digest[:16]}.json"
    body = (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    # Never import a rollback receipt into the authoritative source history.
    # Check this before creating any receipt, even on an initial API race.
    if latest.exists():
        previous = json.loads(latest.read_text(encoding="utf-8"))
        if _exact_id(previous.get("source_run_id")) > run:
            raise WitnessHold("RUN_SEQUENCE_ROLLBACK_HOLD")
    receipt_dir.mkdir(parents=True, exist_ok=True)
    if receipt.exists() and receipt.read_bytes() != body:
        raise WitnessHold("IMMUTABLE_RECEIPT_COLLISION")
    if not receipt.exists():
        receipt.write_bytes(body)
    latest.parent.mkdir(parents=True, exist_ok=True)
    marker = {
        "schema": "janus.nexus.real44.public_latest.v1",
        "source_run_id": run,
        "source_commit": report["source_commit"],
        "receipt_path": receipt.relative_to(root).as_posix(),
        "status": report["status"],
        "actual_cross_organ_runtime_execution_attested": False,
        "full_issue_162_acceptance": False,
    }
    new_bytes = (json.dumps(marker, indent=2, sort_keys=True) + "\n").encode("utf-8")
    changed = not latest.exists() or latest.read_bytes() != new_bytes
    if changed:
        latest.write_bytes(new_bytes)
    return receipt, changed


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    try:
        report = inspect()
        if args.root and not args.dry_run:
            target, changed = persist(report, args.root)
            print("REAL44_WITNESS_RECEIPT=" + target.name)
            print("REAL44_WITNESS_LATEST_CHANGED=" + str(changed).lower())
        print("REAL44_WITNESS_STATUS=" + report["status"])
        return 0
    except (WitnessHold, OSError, ValueError) as exc:
        code = str(exc) if isinstance(exc, WitnessHold) else "WITNESS_STORAGE_OR_API_HOLD"
        print("REAL44_WITNESS_HOLD=" + code, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
