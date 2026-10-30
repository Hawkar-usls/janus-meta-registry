"""Fail-closed handoff from isolated self-writer module to a review-only GitHub PR.

The only admitted payload is exact existing model-authored pure function source
plus deterministic, zero-authority provenance metadata. No tests/imports of
model code run on the trusted publisher and no PR is automatically merged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from module_registry import exact, proven, verify as verify_module_catalog
from policy import TASKS, canonical, digest, source_digest, validate_state
from lifecycle import load, safe_path

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
PROPOSAL_SCHEMA = "janus.autonomous_coder.integration_proposal.v1"
PREFIX = "janus/review-pure-"


def propose(state_root, task, state_commit):
    if not isinstance(state_commit, str) or not HEX40.fullmatch(state_commit):
        raise ValueError("SOURCE_COMMIT_UNTRUSTED")
    if task not in TASKS:
        raise ValueError("UNREVIEWED_MODULE_TASK")
    verify_module_catalog(state_root)
    state = validate_state(load(safe_path(state_root, "STATE.json")))
    entry = state["accepted"].get(task)
    if not isinstance(entry, dict):
        raise ValueError("MODULE_NOT_ACCEPTED")
    raw, expected_manifest = proven(state_root, task, entry)
    immutable = json.loads(exact(state_root, "self_modules/" + task + "/MODULE.json"))
    if (immutable != expected_manifest or
            exact(state_root, "self_modules/" + task + "/module.py", 4096) != raw):
        raise ValueError("ISOLATED_MODULE_PACKAGE_REBINDING")
    data = {
        "schema": PROPOSAL_SCHEMA,
        "task_id": task,
        "module_id": expected_manifest["module_id"],
        "source_state_commit": state_commit,
        "source_branch": "janus/autonomous-code-state",
        "source_sha256": entry["source_sha256"],
        "author_run_id": entry["run_id"],
        "author_model": expected_manifest["author_model"],
        "source_receipt_sha256": entry["receipt_sha256"],
        "source_module_manifest_sha256": hashlib.sha256(
            canonical(expected_manifest) + b"\n").hexdigest(),
        "independently_verified_cases": expected_manifest["evaluated_cases"],
        "candidate_path": "candidate_modules/" + task + "/module.py",
        "review_required": True,
        "auto_merge": False,
        "install_into_runtime": False,
        "dependencies": [],
        "permissions": [],
        "main_code_mutations": 0,
        "authority_delta": 0,
        "full_issue_162_acceptance": False,
        "security_scope": "QUARANTINED_PURE_MODULE_REVIEW_ONLY",
    }
    data["proposal_sha256"] = digest(data)
    branch = PREFIX + task + "-" + entry["source_sha256"]
    return branch, data, raw


def _artifacts(task, proposal, raw):
    folder = "candidate_modules/" + task
    return {
        folder + "/module.py": raw,
        folder + "/PROPOSAL.json": canonical(proposal) + b"\n",
    }


def select(state_root, state_commit, reviewed_branches):
    if not isinstance(reviewed_branches, (set, frozenset)):
        raise ValueError("REVIEWED_BRANCH_SET")
    verify_module_catalog(state_root)
    state = validate_state(load(safe_path(state_root, "STATE.json")))
    for task in TASKS:
        if task not in state["accepted"]:
            continue
        branch, proposal, raw = propose(state_root, task, state_commit)
        if branch not in reviewed_branches:
            return branch, proposal, raw
    return None


def prepare(repo_root, state_root, state_commit, reviewed_branches):
    item = select(state_root, state_commit, reviewed_branches)
    if item is None:
        return {"status": "IDLE_ALL_ACCEPTED_MODULES_ALREADY_PROPOSED",
                "changed": False, "authority_delta": 0}
    branch, proposal, raw = item
    artifacts = _artifacts(proposal["task_id"], proposal, raw)
    for filename, content in artifacts.items():
        path = safe_path(repo_root, filename)
        if path.exists():
            raise ValueError("INTEGRATION_CANDIDATE_ALREADY_EXISTS")
        if len(content) > 150_000:
            raise ValueError("INTEGRATION_PROPOSAL_SIZE")
    for filename, content in artifacts.items():
        path = safe_path(repo_root, filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return {"status": "REVIEW_ONLY_PROPOSAL_PREPARED", "changed": True,
            "branch": branch, "task_id": proposal["task_id"],
            "candidate_paths": sorted(artifacts),
            "source_sha256": proposal["source_sha256"],
            "source_state_commit": state_commit,
            "authority_delta": 0}


def verify_proposal(repo_root, state_root, state_commit, task):
    branch, proposal, raw = propose(state_root, task, state_commit)
    for filename, content in _artifacts(task, proposal, raw).items():
        if exact(repo_root, filename) != content:
            raise ValueError("REVIEW_CANDIDATE_REBINDING")
    return {
        "status": "REVIEW_ONLY_PROVENANCE_VERIFIED",
        "branch": branch,
        "task_id": task,
        "source_sha256": proposal["source_sha256"],
        "source_state_commit": state_commit,
        "authority_delta": 0,
        "auto_merge": False,
        "runtime_adoption_proven": False,
    }


def inspect_pr(pull, files, expected_repo):
    """Check two-file, same-repo, not-merged review PR before any state fetch."""
    if (not isinstance(pull, dict) or not isinstance(files, list) or
            pull.get("state") != "open" or
            pull.get("merged") is True or
            pull.get("base", {}).get("ref") != "main" or
            pull.get("base", {}).get("repo", {}).get("full_name") != expected_repo or
            pull.get("head", {}).get("repo", {}).get("full_name") != expected_repo or
            pull.get("changed_files") != 2 or len(files) != 2):
        raise ValueError("REVIEW_PR_METADATA_OR_SCOPE_INVALID")
    branch = pull["head"].get("ref")
    commit = pull["head"].get("sha")
    if (not isinstance(branch, str) or not branch.startswith(PREFIX) or
            not isinstance(commit, str) or not HEX40.fullmatch(commit)):
        raise ValueError("REVIEW_PR_HEAD_UNTRUSTED")
    m = re.fullmatch(r"janus/review-pure-([a-z_]+)-([0-9a-f]{64})", branch)
    if m is None or m.group(1) not in TASKS:
        raise ValueError("REVIEW_PR_BRANCH_UNREVIEWED")
    task, sha = m.groups()
    wanted = {
        "candidate_modules/" + task + "/PROPOSAL.json",
        "candidate_modules/" + task + "/module.py",
    }
    if ({f.get("filename") for f in files if isinstance(f, dict)} != wanted or
            any(not isinstance(f, dict) or f.get("status") != "added" for f in files)):
        raise ValueError("REVIEW_PR_UNEXPECTED_FILES")
    return {"task_id": task, "head_sha": commit,
            "source_sha256": sha, "branch": branch, "changed_files": 2}


def inspect_branch(branch, change_rows):
    """Strict review-branch fallback when repository Actions cannot create PRs."""
    if not isinstance(branch, str):
        raise ValueError("REVIEW_BRANCH_UNTRUSTED")
    match = re.fullmatch(r"janus/review-pure-([a-z_]+)-([0-9a-f]{64})", branch)
    if match is None or match.group(1) not in TASKS:
        raise ValueError("REVIEW_BRANCH_UNTRUSTED")
    if not isinstance(change_rows, list) or len(change_rows) != 2:
        raise ValueError("REVIEW_BRANCH_EXTRA_CHANGES")
    task, source_sha = match.groups()
    want = {"candidate_modules/" + task + "/module.py",
            "candidate_modules/" + task + "/PROPOSAL.json"}
    observed = set()
    for row in change_rows:
        if (not isinstance(row, (list, tuple)) or len(row) != 2 or
                row[0] != "A" or row[1] not in want):
            raise ValueError("REVIEW_BRANCH_UNEXPECTED_DIFF")
        observed.add(row[1])
    if observed != want:
        raise ValueError("REVIEW_BRANCH_MISSING_PAYLOAD")
    return {"branch": branch, "task_id": task, "source_sha256": source_sha,
            "changed_files": 2}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "verify"))
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--state-commit", required=True)
    parser.add_argument("--reviewed-branches", type=Path)
    parser.add_argument("--task")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        if args.reviewed_branches is None or args.task is not None:
            raise ValueError("PREPARE_ARGS")
        raw = args.reviewed_branches.read_bytes()
        if len(raw) > 300_000:
            raise ValueError("REVIEWED_BRANCHES_TOO_LARGE")
        names = {line.strip() for line in raw.decode().splitlines() if line.strip()}
        if any(not re.fullmatch(r"[a-zA-Z0-9/_-]{1,150}", name)
               for name in names):
            raise ValueError("REVIEWED_BRANCH_INVALID")
        result = prepare(args.repo_root, args.state_root, args.state_commit, names)
    else:
        if args.reviewed_branches is not None or args.task not in TASKS:
            raise ValueError("VERIFY_ARGS")
        result = verify_proposal(args.repo_root, args.state_root,
                                 args.state_commit, args.task)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(canonical(result) + b"\n")
    print(json.dumps(result, sort_keys=True))
    if args.mode == "prepare" and os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write("proposal_status=" + result["status"] + "\n")
            if result.get("changed"):
                stream.write("proposal_branch=" + result["branch"] + "\n")
                stream.write("proposal_task=" + result["task_id"] + "\n")


if __name__ == "__main__":
    main()
