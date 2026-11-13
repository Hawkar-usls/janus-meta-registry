"""Read-only JANUS candidate triage and strict reviewed-source preflight.

This stage never executes source, contacts GitHub, dispatches workflows or
asserts a measured improvement. Only a separate networkless sandbox can test
behavior, followed by a source-pinned independent replay for a gain claim.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re

SCHEMA = "janus.closed_loop.candidate_preflight.v1"
QUEUE_SCHEMA = "janus.closed_loop.patch_queue_triage.v1"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SAFE_REPOSITORY = "Hawkar-usls/janus-meta-registry"
MAX_SOURCE_BYTES = 4096


class Hold(ValueError):
    """Untrusted candidate metadata; no execution or adoption authority."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _allowed_source(source, task):
    """Reuse existing, independently reviewed AST gate; never exec source."""
    module = Path(__file__).resolve().parents[1] / "autonomy_coder" / "policy.py"
    if not module.is_file():
        raise Hold("REVIEWED_SOURCE_POLICY_MISSING")
    spec = importlib.util.spec_from_file_location("janus_cl_reviewed_policy", module)
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    try:
        policy.validate_source(source, task)
    except (SyntaxError, ValueError, TypeError) as exc:
        raise Hold("CANDIDATE_AST_NOT_ADMITTED") from exc


def preflight(proposal, source, *, source_commit):
    """Validate an exact source review proposal; classify, never install."""
    if not isinstance(proposal, dict) or not isinstance(source, str):
        raise Hold("SOURCE_OR_PROPOSAL_TYPE")
    if not isinstance(source_commit, str) or not SHA40.fullmatch(source_commit):
        raise Hold("SOURCE_COMMIT_UNPINNED")
    if not 0 < len(source.encode("utf-8")) <= MAX_SOURCE_BYTES:
        raise Hold("SOURCE_SIZE")
    task = proposal.get("task_id")
    if not isinstance(task, str) or not re.fullmatch(r"[a-z][a-z_]{2,63}", task):
        raise Hold("TASK_UNREVIEWED")
    for name in ("source_sha256", "source_receipt_sha256",
                 "source_module_manifest_sha256", "proposal_sha256"):
        value = proposal.get(name)
        if not isinstance(value, str) or not SHA256.fullmatch(value):
            raise Hold("INVALID_PROVENANCE_SHA")
    if not isinstance(proposal.get("source_state_commit"), str) or \
            not SHA40.fullmatch(proposal["source_state_commit"]):
        raise Hold("UNPINNED_SOURCE_STATE")
    if (proposal.get("schema") != "janus.autonomous_coder.integration_proposal.v1" or
            proposal.get("source_branch") != "janus/autonomous-code-state" or
            proposal.get("candidate_path") != f"candidate_modules/{task}/module.py" or
            proposal.get("module_id") != f"janus.pure.{task}.v1" or
            proposal.get("security_scope") != "QUARANTINED_PURE_MODULE_REVIEW_ONLY" or
            proposal.get("review_required") is not True or
            proposal.get("auto_merge") is not False or
            proposal.get("install_into_runtime") is not False or
            proposal.get("full_issue_162_acceptance") is not False or
            proposal.get("main_code_mutations") != 0 or
            proposal.get("authority_delta") != 0 or
            proposal.get("permissions") != [] or
            proposal.get("dependencies") != []):
        raise Hold("PROPOSAL_SCOPE_OR_AUTHORITY")
    if type(proposal.get("main_code_mutations")) is not int or \
            type(proposal.get("authority_delta")) is not int:
        raise Hold("PROPOSAL_AUTHORITY_TYPE")
    if (not isinstance(proposal.get("independently_verified_cases"), int) or
            type(proposal["independently_verified_cases"]) is not int or
            proposal["independently_verified_cases"] < 200):
        raise Hold("INSUFFICIENT_PRIOR_CASES")
    unsigned = {k: v for k, v in proposal.items() if k != "proposal_sha256"}
    if digest(unsigned) != proposal["proposal_sha256"]:
        raise Hold("PROPOSAL_DIGEST_MISMATCH")
    source_sha = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if source_sha != proposal["source_sha256"]:
        raise Hold("CANDIDATE_SOURCE_CHANGED")
    _allowed_source(source, task)
    result = {
        "schema": SCHEMA,
        "status": "READY_FOR_ISOLATED_BEHAVIOR_REPLAY_ONLY",
        "task_id": task,
        "source_commit": source_commit,
        "source_sha256": source_sha,
        "proposal_sha256": proposal["proposal_sha256"],
        "author_run_id": proposal.get("author_run_id"),
        "prior_claimed_verified_cases": proposal["independently_verified_cases"],
        "executed_now": False,
        "improvement_attested": False,
        "independent_replay_attested": False,
        "runtime_consumption_attested": False,
        "auto_merge": False,
        "authority_delta": 0,
    }
    result["receipt_sha256"] = digest(result)
    return result


def triage_queue(index):
    """Reject unavailable target branches; never treat their counts as work."""
    if (not isinstance(index, dict) or
            index.get("schema") != "janus.patch_queue.index.v1" or
            not isinstance(index.get("proposals"), list)):
        raise Hold("QUEUE_UNTRUSTED")
    proposals = index["proposals"]
    if len(proposals) > 500 or index.get("proposal_count") != len(proposals):
        raise Hold("QUEUE_COUNT_MISMATCH")
    ids = set()
    counts = {"waiting_for_target_branch": 0,
              "verified_not_in_safe_repo": 0,
              "verified_safe_repo": 0}
    safe = []
    for entry in proposals:
        if not isinstance(entry, dict):
            raise Hold("QUEUE_ENTRY_INVALID")
        key = entry.get("proposal_id")
        if not isinstance(key, str) or not re.fullmatch(r"jpatch-[a-z0-9-]{6,100}", key) or key in ids:
            raise Hold("QUEUE_ID_INVALID_OR_DUPLICATE")
        ids.add(key)
        status = entry.get("status")
        if status == "WAITING_FOR_TARGET_BRANCH":
            counts["waiting_for_target_branch"] += 1
        elif status == "VERIFY_PASS":
            repo = entry.get("target_repository") or entry.get("repository")
            if repo == SAFE_REPOSITORY:
                if entry.get("main_mutated") is not False:
                    raise Hold("UNTRUSTED_VERIFIED_PATCH_METADATA")
                counts["verified_safe_repo"] += 1
                safe.append(key)
            else:
                counts["verified_not_in_safe_repo"] += 1
        else:
            raise Hold("UNKNOWN_QUEUE_STATUS")
    if (index.get("verified_count") !=
            counts["verified_safe_repo"] + counts["verified_not_in_safe_repo"] or
            type(index.get("blocked_count")) is not int or index["blocked_count"] < 0):
        raise Hold("QUEUE_STATUS_COUNTS_MISMATCH")
    result = {
        "schema": QUEUE_SCHEMA,
        "status": "REVIEW_SAFE_CANDIDATES_ONLY" if safe else "HOLD_NO_SAFE_QUEUE_CANDIDATE",
        "counts": counts,
        "safe_proposal_ids": sorted(safe),
        "no_target_branch_created": True,
        "no_dispatch": True,
        "no_private_repo_access": True,
        "no_runtime_install": True,
        "authority_delta": 0,
    }
    result["digest_sha256"] = digest(result)
    return result
