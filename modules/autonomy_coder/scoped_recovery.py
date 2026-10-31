"""Bounded, evidence-attested self-writer recovery proposal.

This is NOT arbitrary autonomous code generation. When previously accepted
production source drifts, propose restoring EXACT known-good Git bytes.
An independent reviewer and human-controlled merge are mandatory.
Never imports or runs raw model output and has no GitHub write API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

REPO = "Hawkar-usls/janus-meta-registry"
TARGET = "modules/autonomy_coder/real_operational_consumer.py"
JOURNAL = "data/self_writer/JANUS_SELF_WRITER_REAL_REPAIR_001.json"
INSTALL = "1245c05f0002cce3193e50d8a5edb7f37a6c2d87"
ARCHIVE = "a80e8301dc5897b0b2779db94a74bf55a2020852"
# The old PR head is not necessarily fetched in a clean post-squash clone.
# Pin the archived FILE bytes independently of branch object availability.
ARCHIVE_FILE_BLOB = "62d67d0bd1a83475c08ecb0bd40589034ce45071"
GOOD_BLOB = "c787f96523442cf314f2327bf57af658a06e1a47"
FUNCTION_SHA = "812096e5305073344e3a4e19a46e3f888f42f2d1760ef81ae8ba5fb76c625405"
SCHEMA = "janus.self_writer.scoped_recovery_plan.v1"
HEX40 = re.compile(r"[a-f0-9]{40}\Z")


class Hold(ValueError):
    pass


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args], timeout=15)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def exact_archive(root: Path, *, git_read=git) -> tuple[bytes, bytes, dict]:
    """Verify independent archive and installed historical source before use."""
    good = git_read(root, "show", INSTALL + ":" + TARGET)
    if git_blob(good) != GOOD_BLOB or len(good) > 24_000:
        raise Hold("TRUSTED_INSTALL_SOURCE_MISMATCH")
    actual = (root / JOURNAL).read_bytes()
    if (not actual or len(actual) > 25_000 or
            git_blob(actual) != ARCHIVE_FILE_BLOB):
        raise Hold("CANONICAL_ARCHIVE_ABSENT_OR_TAMPERED")
    try:
        pin = git_read(root, "show", ARCHIVE + ":" + JOURNAL)
    except subprocess.CalledProcessError:
        # Squash merges can leave the original PR head outside fetch refs.
        # Never trust a fallback by path or mutable branch: the fixed Git
        # blob hash must match the original independently archived bytes.
        pin = actual
    if (not pin or len(pin) > 25_000 or
            git_blob(pin) != ARCHIVE_FILE_BLOB or actual != pin):
        raise Hold("CANONICAL_ARCHIVE_ABSENT_OR_TAMPERED")
    evidence = json.loads(pin)
    if (
        evidence.get("schema") != "janus.self_writer.real_operational_repair.v1"
        or evidence.get("record_id") != "JANUS_SELF_WRITER_REAL_REPAIR_001"
        or evidence.get("repository") != REPO
        or evidence.get("installation", {}).get("merge_commit_sha") != INSTALL
        or evidence.get("installation", {}).get("postmerge_target_git_blob_sha") != GOOD_BLOB
        or evidence.get("installation", {}).get("model_can_modify_main_directly") is not False
        or evidence.get("typed_compilation", {}).get("source_sha256") != FUNCTION_SHA
        or evidence.get("model_proposal", {}).get("raw_source_admitted") is not False
        or evidence.get("rollback", {}).get("isolated_rehearsal") !=
           "PASS_IN_READONLY_INDEPENDENT_GIT_WORKER"
        or evidence.get("rollback", {}).get("production_rollback_executed") is not False
        or evidence.get("limits", {}).get("full_autonomy_status") != "PARTIAL"
    ):
        raise Hold("SOURCE_CERTIFICATE_INVALID")
    if subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor",
                       INSTALL, "HEAD"], check=False, timeout=15).returncode != 0:
        raise Hold("INSTALL_NOT_IN_ACTIVE_HISTORY")
    source = evidence["typed_compilation"]["source"]
    if (not isinstance(source, str) or digest(source.encode()) != FUNCTION_SHA
        or good.count(source.encode()) != 1):
        raise Hold("KNOWN_GOOD_MODEL_INTENT_NOT_EXACT")
    return good, pin, evidence


def assess(current: bytes, good: bytes, head: str, proof_sha: str) -> dict:
    if not isinstance(head, str) or not HEX40.fullmatch(head):
        raise Hold("INVALID_PARENT_SHA")
    if not isinstance(proof_sha, str) or len(proof_sha) != 64:
        raise Hold("INVALID_CERTIFICATE_SHA")
    if git_blob(good) != GOOD_BLOB:
        raise Hold("RESTORE_TARGET_NOT_SIGNED_SOURCE")
    if len(current) > 24_000 or not current:
        raise Hold("LIVE_SOURCE_UNSAFE")
    base = {
        "schema": SCHEMA,
        "target_repository": REPO,
        "only_allowed_path": TARGET,
        "main_head_sha": head,
        "current_source_blob": git_blob(current),
        "trusted_installed_source_blob": GOOD_BLOB,
        "historical_install_commit": INSTALL,
        "independent_archive_commit": ARCHIVE,
        "archive_content_sha256": proof_sha,
        "new_code_written_by_model": False,
        "repair_kind": "RESTORE_EXACT_PREVIOUSLY_VERIFIED_CODE_ONLY",
        "human_review_required": True,
        "independent_ci_required": True,
        "auto_merge": False,
        "production_modified": False,
        "production_rollback_executed": False,
        "new_provider_jobs": False,
        "new_rowan_credits": False,
        "authority_delta": 0,
        "full_autonomy": False,
    }
    if current == good:
        return {**base, "status": "IDLE_KNOWN_GOOD"}
    return {**base, "status": "SCOPED_RESTORE_PR_ELIGIBLE",
            "candidate_branch": "janus/recover-repair001-" + git_blob(current)[:16],
            "patch_files": [TARGET],
            "changed_source_will_not_be_executed": True,
            "candidate_source_sha256": digest(good)}


def evaluate(root: Path) -> tuple[dict, bytes | None]:
    if (root / ".git").is_dir() is False:
        raise Hold("EXPECTED_REAL_GIT_CHECKOUT")
    head = git(root, "rev-parse", "HEAD").decode().strip()
    trusted, raw_cert, _ = exact_archive(root)
    source = (root / TARGET).read_bytes()
    decision = assess(source, trusted, head, digest(raw_cert))
    return decision, trusted if decision["status"] == "SCOPED_RESTORE_PR_ELIGIBLE" else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--candidate", type=Path)
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        result, trusted = evaluate(args.root.resolve())
        if args.candidate and trusted is not None:
            args.candidate.parent.mkdir(parents=True, exist_ok=True)
            args.candidate.write_bytes(trusted)
    except (Hold, OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        result = {"schema": SCHEMA, "status": "HOLD_FAIL_CLOSED",
                  "reason": str(exc)[:140], "auto_merge": False,
                  "production_modified": False, "authority_delta": 0,
                  "full_autonomy": False}
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("JANUS_SCOPED_RECOVERY=" + result["status"])
    return 1 if result["status"] == "HOLD_FAIL_CLOSED" else 0


if __name__ == "__main__":
    sys.exit(main())
