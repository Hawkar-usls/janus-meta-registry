#!/usr/bin/env python3
"""Independent exact-source witness for the bounded JANUS autonomy draft.

Only public GitHub PR/run/job metadata is read. This verifies receipt consistency,
not runtime isolation, scientific independence, service health or organ admission.
The historical receipt intentionally fails live verification if its draft/head is
changed. It must be superseded with another reviewed receipt, never auto-promoted.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPOSITORY = "Hawkar-usls/Janus"
WORKFLOW = ".github/workflows/janus-autonomy-observer-r1.yml"
STATE = Path(__file__).resolve().parents[1] / "data/autonomy_map/CURRENT_STATE.json"
SCHEMA = "janus.autonomy.map_r1.current_state.v1"
STATUS = "DRAFT_ENGINEERING_PASS__OBSERVATION_HOLD__ADMISSION_HOLD"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PR_URL = re.compile(r"https://github\.com/Hawkar-usls/Janus/pull/([1-9][0-9]{0,9})\Z")
MAX_BYTES = 2_000_000
FALSE_BOUNDARIES = ("action_authority", "external_code_executed", "self_promotion", "training_run",
                    "exams_used", "weights_changed", "full_autonomy_proven")
ZERO_BOUNDARIES = ("actual_forks_created", "new_repos", "authority_delta")


class Hold(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Hold(reason)


def object_value(value, reason):
    require(type(value) is dict, reason)
    return value


def valid_hash(value, pattern):
    return type(value) is str and pattern.fullmatch(value) is not None and set(value) != {"0"}


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def constant(_value):
        raise Hold("NONFINITE_JSON")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def job_projection(jobs):
    require(type(jobs) is list and 1 <= len(jobs) <= 20, "JOBS_BUDGET_OR_TYPE")
    projected, names = [], set()
    for job in jobs:
        object_value(job, "JOB_TYPE")
        name = job.get("name")
        require(type(name) is str and 0 < len(name) <= 160 and name not in names
                and all(char >= " " and char != "\x7f" for char in name), "JOB_NAME")
        require(job.get("conclusion") == "success", "JOB_NOT_SUCCESS")
        names.add(name)
        projected.append({"name": name, "conclusion": "success"})
    return sorted(projected, key=lambda item: item["name"])


def verify(state, *, get=None):
    object_value(state, "STATE_TYPE")
    require(state.get("schema") == SCHEMA, "STATE_SCHEMA")
    require(state.get("status") == STATUS, "STATUS_OVERCLAIM")
    source = object_value(state.get("source"), "SOURCE_TYPE")
    require(source.get("repository") == REPOSITORY, "SOURCE_REPOSITORY")
    require(valid_hash(source.get("base_commit"), HEX40), "BASE_COMMIT")
    require(valid_hash(source.get("commit_sha"), HEX40), "SOURCE_COMMIT")
    require(source["base_commit"] != source["commit_sha"], "NO_SOURCE_CHANGE")
    branch = source.get("branch")
    require(type(branch) is str and branch.startswith("research/bounded-autonomy-map-r1-")
            and len(branch) <= 200 and bool(re.fullmatch(r"[A-Za-z0-9_./-]+", branch))
            and ".." not in branch, "SOURCE_BRANCH")
    url = source.get("pr_url")
    match = PR_URL.fullmatch(url) if type(url) is str else None
    require(match is not None, "PR_URL")
    pr_number = int(match.group(1))
    ci = object_value(state.get("ci"), "CI_TYPE")
    run_id = ci.get("run_id")
    require(type(run_id) is int and 0 < run_id < 10 ** 15, "RUN_ID")
    require(ci.get("head_sha") == source["commit_sha"], "CI_SOURCE_HEAD_MISMATCH")
    require(ci.get("conclusion") == "success", "CI_NOT_SUCCESS")
    require(ci.get("url") == f"https://github.com/{REPOSITORY}/actions/runs/{run_id}", "CI_URL")
    recorded_jobs = job_projection(ci.get("jobs"))
    observation = object_value(state.get("observation"), "OBSERVATION_TYPE")
    for field in ("snapshot_sha256", "health_sha256"):
        require(valid_hash(observation.get(field), HEX64), "OBSERVATION_HASH:" + field)
    try:
        observed = datetime.fromisoformat(observation["observed_at"].replace("Z", "+00:00"))
        require(observed.tzinfo is not None, "OBSERVATION_TIMEZONE")
    except (KeyError, AttributeError, TypeError, ValueError):
        raise Hold("OBSERVATION_TIMESTAMP") from None
    count = observation.get("public_repository_count")
    require(type(count) is int and 1 <= count <= 100, "PUBLIC_REPOSITORY_COUNT")
    require(observation.get("owner_inventory_complete") is True, "OWNER_INVENTORY_INCOMPLETE")
    require(observation.get("repository_observations_complete") is False, "OBSERVATION_HOLD_ERASED")
    require(observation.get("integrity_gate") == "PASS" and observation.get("observation_gate") == "HOLD",
            "OBSERVATION_GATE_OVERCLAIM")
    boundaries = object_value(state.get("boundaries"), "BOUNDARIES_TYPE")
    for field in FALSE_BOUNDARIES:
        require(boundaries.get(field) is False, "BOUNDARY:" + field)
    for field in ZERO_BOUNDARIES:
        require(type(boundaries.get(field)) is int and boundaries[field] == 0, "BOUNDARY:" + field)
    if "map_layers" in state:
        require(type(state["map_layers"]) is list and len(state["map_layers"]) <= 20, "MAP_LAYERS")
    if get is not None:
        # All endpoint components are validated above; no URL is taken from data.
        pr = object_value(get(f"/repos/{REPOSITORY}/pulls/{pr_number}"), "LIVE_PR_TYPE")
        require(pr.get("state") == "open" and pr.get("draft") is True, "LIVE_PR_NOT_OPEN_DRAFT")
        head = object_value(pr.get("head"), "LIVE_PR_HEAD_TYPE")
        require(head.get("sha") == source["commit_sha"] and head.get("ref") == branch, "LIVE_PR_HEAD_CHANGED")
        require(object_value(head.get("repo"), "LIVE_HEAD_REPO_TYPE").get("full_name") == REPOSITORY,
                "LIVE_PR_FOREIGN_HEAD")
        base = object_value(pr.get("base"), "LIVE_PR_BASE_TYPE")
        require(object_value(base.get("repo"), "LIVE_BASE_REPO_TYPE").get("full_name") == REPOSITORY,
                "LIVE_PR_FOREIGN_BASE")
        run = object_value(get(f"/repos/{REPOSITORY}/actions/runs/{run_id}"), "LIVE_RUN_TYPE")
        require(run.get("id") == run_id and run.get("status") == "completed"
                and run.get("conclusion") == "success", "LIVE_RUN_NOT_SUCCESS")
        require(run.get("head_sha") == source["commit_sha"] and run.get("head_branch") == branch,
                "LIVE_RUN_HEAD_CHANGED")
        require(run.get("path") == WORKFLOW, "LIVE_WORKFLOW_MISMATCH")
        require(object_value(run.get("repository"), "LIVE_RUN_REPOSITORY_TYPE").get("full_name") == REPOSITORY,
                "LIVE_RUN_FOREIGN_REPOSITORY")
        result = object_value(get(f"/repos/{REPOSITORY}/actions/runs/{run_id}/jobs?per_page=100"), "LIVE_JOBS_TYPE")
        jobs = result.get("jobs")
        require(type(jobs) is list and type(result.get("total_count")) is int
                and result["total_count"] == len(jobs), "LIVE_JOBS_INCOMPLETE")
        for job in jobs:
            object_value(job, "LIVE_JOB_TYPE")
            require(job.get("status") == "completed" and job.get("head_sha") == source["commit_sha"],
                    "LIVE_JOB_NOT_COMPLETED_AT_HEAD")
        require(job_projection(jobs) == recorded_jobs, "LIVE_JOBS_CHANGED")
    return {"schema": "janus.autonomy.map_r1.witness.v1", "status": "PASS",
            "live_github_metadata_checked": get is not None,
            "source_commit": source["commit_sha"], "pr_number": pr_number, "run_id": run_id,
            "job_count": len(recorded_jobs), "observation_gate": "HOLD",
            "admission_gate": "HOLD", "action_authority": False,
            "scope": "EXACT_SOURCE_METADATA_CONSISTENCY_ONLY__NOT_RUNTIME_OR_SCIENTIFIC_PROOF"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Hold("REDIRECT_DENIED")


class PublicWitnessClient:
    def __init__(self, *, token=None):
        self.token = token
        self.requests_used = 0
        self.opener = build_opener(NoRedirect())

    def get(self, route):
        require(type(route) is str and bool(re.fullmatch(
            r"/repos/Hawkar-usls/Janus/(?:pulls/[1-9][0-9]{0,9}|actions/runs/[1-9][0-9]{0,14}(?:/jobs\?per_page=100)?)", route)),
            "ENDPOINT_DENIED")
        require(self.requests_used < 3, "REQUEST_BUDGET_EXHAUSTED")
        self.requests_used += 1
        url = "https://api.github.com" + route
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "JANUS-Autonomy-R1-Witness/1",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        try:
            with self.opener.open(Request(url, headers=headers, method="GET"), timeout=20) as response:
                require(response.geturl() == url, "RESPONSE_LOCATION_CHANGED")
                raw = response.read(MAX_BYTES + 1)
                require(len(raw) <= MAX_BYTES, "RESPONSE_TOO_LARGE")
                return strict_json(raw.decode("utf-8"))
        except HTTPError as error:
            raise Hold("GITHUB_HTTP_" + str(error.code)) from None
        except (OSError, TimeoutError, URLError):
            raise Hold("GITHUB_NETWORK_UNAVAILABLE") from None
        except (UnicodeError, json.JSONDecodeError):
            raise Hold("GITHUB_INVALID_JSON") from None


def synthetic_state():
    return {"schema": SCHEMA, "status": STATUS,
            "source": {"repository": REPOSITORY, "base_commit": "a" * 40,
                       "branch": "research/bounded-autonomy-map-r1-selftest", "commit_sha": "b" * 40,
                       "pr_url": "https://github.com/Hawkar-usls/Janus/pull/1"},
            "ci": {"run_id": 2, "head_sha": "b" * 40, "conclusion": "success",
                   "url": "https://github.com/Hawkar-usls/Janus/actions/runs/2",
                   "jobs": [{"name": "offline-contract", "conclusion": "success"}]},
            "observation": {"snapshot_sha256": "c" * 64, "health_sha256": "d" * 64,
                            "observed_at": "2026-11-23T18:00:00Z", "public_repository_count": 49,
                            "owner_inventory_complete": True, "repository_observations_complete": False,
                            "integrity_gate": "PASS", "observation_gate": "HOLD"},
            "boundaries": {**dict.fromkeys(FALSE_BOUNDARIES, False), **dict.fromkeys(ZERO_BOUNDARIES, 0)}}


def synthetic_live(state):
    sha, branch = state["source"]["commit_sha"], state["source"]["branch"]
    return {f"/repos/{REPOSITORY}/pulls/1": {"state": "open", "draft": True,
                "head": {"sha": sha, "ref": branch, "repo": {"full_name": REPOSITORY}},
                "base": {"repo": {"full_name": REPOSITORY}}},
            f"/repos/{REPOSITORY}/actions/runs/2": {"id": 2, "status": "completed", "conclusion": "success",
                "head_sha": sha, "head_branch": branch, "path": WORKFLOW, "repository": {"full_name": REPOSITORY}},
            f"/repos/{REPOSITORY}/actions/runs/2/jobs?per_page=100": {"total_count": 1,
                "jobs": [{"name": "offline-contract", "conclusion": "success", "status": "completed", "head_sha": sha}]}}


def self_test():
    good = synthetic_state()
    live = synthetic_live(good)
    require(verify(good)["status"] == "PASS", "SELFTEST_STRUCTURAL_PASS")
    require(verify(good, get=live.__getitem__)["live_github_metadata_checked"] is True, "SELFTEST_LIVE_PASS")
    count = 2
    mutations = [lambda x: x.update(status="FULL"), lambda x: x.update(source=[]),
                 lambda x: x["source"].update(repository="attacker/Janus"),
                 lambda x: x["source"].update(pr_url="https://evil.test/1"),
                 lambda x: x["ci"].update(head_sha="e" * 40), lambda x: x["ci"].update(run_id=True),
                 lambda x: x["ci"]["jobs"][0].update(conclusion="skipped"),
                 lambda x: x["observation"].update(observation_gate="PASS"),
                 lambda x: x["observation"].update(owner_inventory_complete=1),
                 lambda x: x["observation"].update(public_repository_count=True),
                 lambda x: x["observation"].update(snapshot_sha256="0" * 64)]
    mutations += [lambda x, key=key: x["boundaries"].update({key: True}) for key in FALSE_BOUNDARIES]
    mutations += [lambda x, key=key: x["boundaries"].update({key: False}) for key in ZERO_BOUNDARIES]
    for mutate in mutations:
        bad = copy.deepcopy(good)
        mutate(bad)
        try:
            verify(bad)
        except Hold:
            count += 1
        else:
            raise AssertionError("SELFTEST_FAIL_OPEN_RECEIPT")
    live_mutations = [lambda x: x[f"/repos/{REPOSITORY}/pulls/1"].update(draft=False),
                      lambda x: x[f"/repos/{REPOSITORY}/pulls/1"]["head"].update(sha="f" * 40),
                      lambda x: x[f"/repos/{REPOSITORY}/actions/runs/2"].update(path="untrusted.yml"),
                      lambda x: x[f"/repos/{REPOSITORY}/actions/runs/2"].update(conclusion="failure"),
                      lambda x: x[f"/repos/{REPOSITORY}/actions/runs/2/jobs?per_page=100"].update(total_count=2),
                      lambda x: x[f"/repos/{REPOSITORY}/actions/runs/2/jobs?per_page=100"]["jobs"][0].update(head_sha="f" * 40)]
    for mutate in live_mutations:
        bad = copy.deepcopy(live)
        mutate(bad)
        try:
            verify(good, get=bad.__getitem__)
        except Hold:
            count += 1
        else:
            raise AssertionError("SELFTEST_FAIL_OPEN_LIVE_METADATA")
    print(json.dumps({"self_test": "PASS", "positive_and_negative_controls": count,
                      "network_used": False}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=STATE)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--authenticated", action="store_true", help="Explicitly use GITHUB_TOKEN on fixed GitHub host")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
            if not args.live:
                return 0
        raw = args.file.read_bytes()
        require(len(raw) <= MAX_BYTES, "STATE_TOO_LARGE")
        state = strict_json(raw.decode("utf-8"))
        token = os.environ.get("GITHUB_TOKEN") if args.authenticated else None
        require(not args.authenticated or bool(token), "GITHUB_TOKEN_NOT_CONFIGURED")
        client = PublicWitnessClient(token=token) if args.live else None
        print(json.dumps(verify(state, get=client.get if client else None), sort_keys=True))
        return 0
    except (Hold, OSError, UnicodeError, json.JSONDecodeError) as error:
        # File/API text never becomes an instruction or arbitrary network target.
        reason = str(error) if isinstance(error, Hold) else type(error).__name__
        print(json.dumps({"status": "HOLD", "reason": reason, "action_authority": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
