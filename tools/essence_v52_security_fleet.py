#!/usr/bin/env python3
"""Read-only ESSENCE v5.2 GitHub Actions security hygiene census.

Scans *public* repository workflow YAML pinned to each repository commit. It
reports suspicious configurations for review, NOT confirmed exploitability.
Never runs target code or reads secret values; file path and line only.
Private repositories require a separate authorized scan; excluded explicitly.
"""
from __future__ import annotations
import argparse
from collections import Counter
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

OWNER = "Hawkar-usls"
API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
SCHEMA = "janus.essence.github_actions_security_census/5.2"
SHA40 = re.compile(r"^[a-f0-9]{40}$")
MAX_REPOS = 100
MAX_FILES_PER_REPO = 600
MAX_WORKFLOWS = 2000
# Public audit excludes private repositories and must not disclose private names.
PRIVATE_EXCLUDED_COUNT = 3
RULES = {
    "ACTION_REF_NOT_SHA_PINNED": "medium",
    "PULL_REQUEST_TARGET_REVIEW": "high",
    "WORKFLOW_RUN_WITH_WRITE_SCOPE": "high",
    "WRITE_ALL_PERMISSION": "high",
    "CONTENTS_WRITE_SCOPE": "medium",
    "REMOTE_SCRIPT_PIPE_TO_SHELL": "high",
    "UNTRUSTED_EVENT_EXPRESSION": "high",
    "EXPLICIT_PERSIST_GITHUB_TOKEN": "medium",
    "SECRET_REFERENCE_INSIDE_RUN": "medium",
}
UNTRUSTED = (
    "github.event.pull_request.title",
    "github.event.pull_request.body",
    "github.event.issue.title",
    "github.event.issue.body",
    "github.event.comment.body",
    "github.head_ref",
)
UNSAFE_EVENT = "$" + "{{"

def read(url, limit=800_000):
    if not (url.startswith(API + "/") or url.startswith(RAW + "/")):
        raise ValueError("FOREIGN_URL_FORBIDDEN")
    headers = {"User-Agent": "JANUS-ESSENCE-V52-READONLY-SECURITY-CENSUS"}
    if url.startswith(API + "/"):
        headers["Accept"] = "application/vnd.github+json"
        token = os.getenv("GH_TOKEN")
        if token:
            headers["Authorization"] = "Bearer " + token
    try:
        with urlopen(Request(url, headers=headers), timeout=18) as response:
            raw = response.read(limit + 1)
    except HTTPError as ex:
        if ex.code == 404:
            return None
        raise RuntimeError("GITHUB_API_STATUS_" + str(ex.code)) from None
    if len(raw) > limit:
        raise ValueError("SCAN_RESOURCE_TOO_LARGE")
    return raw

def api(path, limit=800_000):
    raw = read(API + path, limit)
    return None if raw is None else json.loads(raw.decode("utf-8"))

def public_inventory():
    data = api("/users/" + OWNER + "/repos?type=owner&per_page=100&page=1", 1_900_000)
    if not isinstance(data, list) or len(data) >= MAX_REPOS:
        raise ValueError("INVENTORY_INCOMPLETE_PAGINATION")
    output = []
    for item in data:
        if item.get("owner", {}).get("login") != OWNER or item.get("private"):
            continue
        output.append((item["name"], item["default_branch"]))
    return sorted(output)

def inventory_one(entry):
    name, branch = entry
    if "/" in name or ".." in name or "/" in branch or len(name) > 130 or len(branch) > 130:
        raise ValueError("UNSAFE_REPO_OR_BRANCH")
    repo = OWNER + "/" + name
    ref = api("/repos/" + repo + "/git/ref/heads/" + quote(branch, safe=""), 15_000)
    sha = ref["object"]["sha"]
    if not SHA40.fullmatch(sha):
        raise ValueError("UNTRUSTED_REPO_HEAD")
    path = "/repos/" + repo + "/contents/.github/workflows?ref=" + sha
    directory = api(path, 1_000_000)
    if directory is None:
        return {"repo": repo, "sha": sha, "files": [], "status": "NO_WORKFLOWS"}
    if not isinstance(directory, list) or len(directory) > MAX_FILES_PER_REPO:
        raise ValueError("WORKFLOW_DIRECTORY_INCOMPLETE")
    paths = [x["path"] for x in directory
             if x.get("type") == "file" and x.get("path", "").endswith((".yml", ".yaml"))]
    return {"repo": repo, "sha": sha, "files": sorted(paths), "status": "PINNED_WORKFLOWS"}

def classify(source):
    """Yield (line, rule) only; no source excerpts or secret values."""
    lines = source.splitlines()
    workflow_run = any(re.match(r"^\s*workflow_run\s*:", line) for line in lines)
    any_write = any(re.match(r"^\s*(contents|actions|pull-requests|issues|checks)\s*:\s*write\s*(?:#.*)?$", line)
                    for line in lines) or any("permissions: write-all" in line for line in lines)
    for idx, line in enumerate(lines, 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if re.match(r"^(?:-\s*)?uses\s*:", s):
            value = s.split(":", 1)[1].strip().split()[0]
            if "@" in value and not value.startswith("docker://"):
                ref = value.rsplit("@", 1)[1]
                if not SHA40.fullmatch(ref):
                    yield idx, "ACTION_REF_NOT_SHA_PINNED"
        if re.match(r"^pull_request_target\s*:", s):
            yield idx, "PULL_REQUEST_TARGET_REVIEW"
        if re.match(r"^workflow_run\s*:", s) and any_write:
            yield idx, "WORKFLOW_RUN_WITH_WRITE_SCOPE"
        if re.search(r"\bpermissions\s*:\s*write-all\b", s):
            yield idx, "WRITE_ALL_PERMISSION"
        if re.match(r"^contents\s*:\s*write\b", s):
            yield idx, "CONTENTS_WRITE_SCOPE"
        if re.search(r"\b(?:curl|wget)\b.+\|\s*(?:ba)?sh\b", s):
            yield idx, "REMOTE_SCRIPT_PIPE_TO_SHELL"
        if UNSAFE_EVENT in s and any(x in s for x in UNTRUSTED):
            yield idx, "UNTRUSTED_EVENT_EXPRESSION"
        if re.match(r"^persist-credentials\s*:\s*true\b", s):
            yield idx, "EXPLICIT_PERSIST_GITHUB_TOKEN"
        if UNSAFE_EVENT + " secrets." in s and ("echo " in s or "printf " in s):
            yield idx, "SECRET_REFERENCE_INSIDE_RUN"

def inspect_file(item):
    repo, sha, path = item
    if not SHA40.fullmatch(sha) or not path.startswith(".github/workflows/"):
        raise ValueError("UNSAFE_WORKFLOW_SOURCE")
    encoded = "/".join(quote(part, safe="") for part in path.split("/"))
    raw = read(RAW + "/" + repo + "/" + sha + "/" + encoded, 240_000)
    if raw is None:
        raise ValueError("PINNED_WORKFLOW_NOT_FOUND")
    content = raw.decode("utf-8", errors="strict")
    findings = [{"repository": repo, "source_commit": sha, "path": path,
                 "line": lineno, "rule": rule, "severity": RULES[rule]}
                for lineno, rule in classify(content)]
    return findings

def run_live():
    repos = public_inventory()
    entries, problems = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        jobs = {pool.submit(inventory_one, x): x[0] for x in repos}
        for job in concurrent.futures.as_completed(jobs):
            try:
                entries.append(job.result())
            except Exception as ex:
                problems.append({"repo": OWNER + "/" + jobs[job],
                                 "phase": "inventory", "error_type": type(ex).__name__})
    sources = [(e["repo"], e["sha"], p) for e in entries for p in e["files"]]
    if len(sources) > MAX_WORKFLOWS:
        raise ValueError("GLOBAL_WORKFLOW_LIMIT_REACHED")
    findings = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        jobs = {pool.submit(inspect_file, item): item for item in sources}
        for job in concurrent.futures.as_completed(jobs):
            try:
                findings.extend(job.result())
            except Exception as ex:
                repo, _sha, path = jobs[job]
                problems.append({"repo": repo, "path": path, "phase": "file",
                                 "error_type": type(ex).__name__})
    count = Counter(x["rule"] for x in findings)
    summary = {
        "public_repo_count": len(repos),
        "repo_inventory_pinned": len(entries),
        "workflow_files_planned": len(sources),
        "workflow_files_read": len(sources) - sum(p["phase"] == "file" for p in problems),
        "private_repo_count_excluded": PRIVATE_EXCLUDED_COUNT,
        "potential_findings_for_review": len(findings),
        "unique_repos_flagged": len({x["repository"] for x in findings}),
        "rules": dict(sorted(count.items())),
        "unreadable_or_incomplete_items": len(problems),
    }
    result = {
        "schema": SCHEMA,
        "status": "PARTIAL_NEEDS_RESCAN" if problems else "PUBLIC_SCAN_FINISHED_REVIEW_REQUIRED",
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "scope": "PUBLIC_OWNER_REPO_WORKFLOW_STATIC_HYGIENE_ONLY",
        "public_source_pinned_per_repository": True,
        "private_repository_count_not_scanned": PRIVATE_EXCLUDED_COUNT,
        "vulnerability_exploitability_confirmed": False,
        "private_files_or_secret_values_exposed": False,
        "code_from_other_repositories_executed": False,
        "risk_treatment": "CANDIDATE_FINDINGS_NEED_MANUAL_TRIAGE",
        "summary": summary,
        "repository_inventory": sorted(entries, key=lambda v:v["repo"]),
        "findings": sorted(findings, key=lambda x:(x["repository"],x["path"],x["line"],x["rule"])),
        "errors": sorted(problems, key=lambda p:(p["repo"],p.get("path", ""))),
    }
    result["receipt_sha256"] = hashlib.sha256(
        json.dumps(result,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)
        .encode("utf-8")).hexdigest()
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--live", action="store_true")
    p.add_argument("--out")
    args = p.parse_args()
    if args.selftest:
        assert list(classify("on:\n  pull_request_target:\npermissions: write-all\n")) == [
            (2, "PULL_REQUEST_TARGET_REVIEW"), (3, "WRITE_ALL_PERMISSION")]
        print("ESSENCE_SECURITY_SCANNER_SELFTEST_PASS")
    if args.live:
        report = run_live()
        if args.out:
            target=Path(args.out)
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+"\n",
                              encoding="utf-8")
        print(json.dumps({"status":report["status"], **report["summary"],
                          "receipt_sha256":report["receipt_sha256"]},sort_keys=True))
        if report["status"].startswith("PARTIAL"):
            raise SystemExit(2)

if __name__ == "__main__":
    main()
