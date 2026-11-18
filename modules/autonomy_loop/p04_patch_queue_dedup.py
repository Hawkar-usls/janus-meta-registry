"""Conservative, lossless patch-queue identity audit for JANUS P0.4.

This is a READ-ONLY proposal index audit. It never supersedes, deletes,
applies, promotes, or automatically merges a patch. It intentionally refuses
to deduplicate entries without complete verified target identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

SCHEMA = "janus.patch_queue.index.v1"
REPORT_SCHEMA = "janus.autonomy.p04_nonlossy_dedup_audit.v1"
MAX_BYTES = 2_000_000
MAX_PROPOSALS = 5000
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}\Z")
REPO = re.compile(r"Hawkar-usls/[A-Za-z0-9_.-]{1,160}\Z")
MODULE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,159}\Z")
BRANCH = re.compile(r"janus-self/[A-Za-z0-9._/-]{1,180}\Z")
STATUS = re.compile(r"[A-Z][A-Z0-9_]{0,95}\Z")


class AuditHold(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise AuditHold(reason)


def canonical(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def audited_identity(row: dict) -> tuple[str, str, str, str] | None:
    fields = ("target_repository", "target_module_id", "target_branch", "patch_commit")
    values = tuple(row.get(name) for name in fields)
    # A partial target description is NOT evidence of a duplicate; the
    # current historical queue contains such intentionally incomplete rows.
    if not all(isinstance(v, str) for v in values):
        return None
    repo, module, branch, commit = values
    if not (REPO.fullmatch(repo) and MODULE.fullmatch(module) and
            BRANCH.fullmatch(branch) and SHA40.fullmatch(commit)):
        return None
    return values


def audit_index(raw: bytes) -> dict:
    require(isinstance(raw, bytes) and 0 < len(raw) <= MAX_BYTES, "INDEX_SIZE_HOLD")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise AuditHold("INDEX_JSON_HOLD") from exc
    require(isinstance(data, dict) and data.get("schema") == SCHEMA, "INDEX_SCHEMA_HOLD")
    proposals = data.get("proposals")
    require(isinstance(proposals, list) and len(proposals) <= MAX_PROPOSALS,
            "INDEX_PROPOSALS_HOLD")
    require(type(data.get("proposal_count")) is int and
            data["proposal_count"] == len(proposals), "INDEX_COUNT_HOLD")
    require(type(data.get("verified_count")) is int and
            0 <= data["verified_count"] <= len(proposals), "VERIFIED_COUNT_HOLD")
    require(type(data.get("blocked_count")) is int and
            0 <= data["blocked_count"] <= len(proposals), "BLOCKED_COUNT_HOLD")

    ids: set[str] = set()
    buckets: dict[tuple[str, str, str, str], list[str]] = {}
    unbound: list[str] = []
    verified = 0
    for row in proposals:
        require(isinstance(row, dict), "NONOBJECT_PROPOSAL_HOLD")
        pid = row.get("proposal_id")
        status = row.get("status")
        require(isinstance(pid, str) and IDENTIFIER.fullmatch(pid) is not None,
                "INVALID_PROPOSAL_ID_HOLD")
        require(pid not in ids, "DUPLICATE_PROPOSAL_ID_HOLD")
        ids.add(pid)
        require(isinstance(status, str) and STATUS.fullmatch(status) is not None,
                "INVALID_PROPOSAL_STATUS_HOLD")
        require(row.get("main_mutated") is not True and
                row.get("native_model_selected") is not True,
                "UNADMITTED_MAIN_OR_MODEL_MUTATION_HOLD")
        identity = audited_identity(row)
        if status == "VERIFY_PASS":
            verified += 1
            require(identity is not None and row.get("main_mutated") is False
                    and row.get("native_model_selected") is False,
                    "UNBOUND_VERIFIED_PATCH_HOLD")
        if identity is None:
            unbound.append(pid)
        else:
            buckets.setdefault(identity, []).append(pid)
    require(verified == data["verified_count"], "VERIFIED_ACCOUNTING_HOLD")

    duplicate_groups = []
    for identity, group in buckets.items():
        if len(group) > 1:
            duplicate_groups.append({
                "identity_commitment_sha256": digest(canonical(identity)),
                "proposal_ids": sorted(group),
                "entry_count": len(group),
                "action": "REVIEW_ONLY_PRESERVE_ALL",
            })
    duplicate_groups.sort(key=lambda r: r["identity_commitment_sha256"])
    return {
        "schema": REPORT_SCHEMA,
        "status": "NONLOSSY_AUDIT_ONLY_NOT_PHASE_ACCEPTANCE",
        "index_bytes_sha256": digest(raw),
        "proposal_count": len(proposals),
        "verified_count": verified,
        "identity_bound_count": sum(map(len, buckets.values())),
        "unbound_count": len(unbound),
        "unbound_proposal_ids": sorted(unbound),
        "duplicate_groups": duplicate_groups,
        "preserved_proposal_ids": sorted(ids),
        "original_rows_preserved": True,
        "source_files_modified": False,
        "superseded_attempts_deleted": False,
        "model_patch_admitted": False,
        "p04_acceptance": False,
        "full_issue_162_acceptance": False,
        "authority_delta": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    args = parser.parse_args()
    path = args.index
    require(path.is_file() and not path.is_symlink(), "INDEX_PATH_HOLD")
    print(json.dumps(audit_index(path.read_bytes()), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
