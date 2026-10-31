"""Independent read-only continuing-integrity witness for a real JANUS model-guided patch.

Fail closed on source, archive, exact cloud-run or permission drift.
No model source is executed, no merges/reverts are performed.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

REPO = "Hawkar-usls/janus-meta-registry"
SCHEMA = "janus.self_writer.repair_integrity_watch.v1"
ARCHIVE_COMMIT = "a80e8301dc5897b0b2779db94a74bf55a2020852"
INSTALL_COMMIT = "1245c05f0002cce3193e50d8a5edb7f37a6c2d87"
OLD_BLOB = "7a28b110fef7c7458372ba50c9e5d37224d4c0a0"
LIVE_BLOB = "c787f96523442cf314f2327bf57af658a06e1a47"
MODEL_FUNCTION_SHA = "812096e5305073344e3a4e19a46e3f888f42f2d1760ef81ae8ba5fb76c625405"
CODE = "modules/autonomy_coder/real_operational_consumer.py"
JOURNAL = "data/self_writer/JANUS_SELF_WRITER_REAL_REPAIR_001.json"
PASS_RUNS = {
    41181745142: ("da16db05cf07af3bd856c1fd63164cf5dc41d872",
                  "JANUS Self-Writer Typed Compilation of Real Model Proposal"),
    41181925683: ("032e79015af82d3f015f745f1e75edf45326c673",
                  "JANUS Self-Writer Real Operational Consumer"),
    41181981029: (INSTALL_COMMIT, "JANUS Self-Writer Real Operational Consumer"),
    41181981061: (INSTALL_COMMIT, "JANUS Secret Persistence Guard"),
    41182302141: ("3e650b0af542f3a3669eaf2202d92ab21dd4dc77",
                  "JANUS Self-Writer Real Repair Rollback Witness"),
}

def sha256(data):
    return hashlib.sha256(data).hexdigest()

def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def deny(reason):
    raise ValueError("SELF_WRITER_WITNESS_" + reason)

def verify_contents(source, evidence, archive_head):
    if archive_head != ARCHIVE_COMMIT:
        deny("ARCHIVE_COMMIT_MOVED")
    if git_blob(source) != LIVE_BLOB:
        deny("ACTIVE_SOURCE_CHANGED")
    model = evidence.get("model_proposal") or {}
    comp = evidence.get("typed_compilation") or {}
    install = evidence.get("installation") or {}
    revert = evidence.get("rollback") or {}
    limits = evidence.get("limits") or {}
    if (evidence.get("schema") != "janus.self_writer.real_operational_repair.v1"
        or evidence.get("record_id") != "JANUS_SELF_WRITER_REAL_REPAIR_001"
        or evidence.get("repository") != REPO
        or evidence.get("defect", {}).get("original_git_blob_sha") != OLD_BLOB
        or model.get("raw_source_admitted") is not False
        or model.get("model") != "Qwen/Qwen2.5-Coder-1.5B-Instruct"
        or comp.get("source_sha256") != MODEL_FUNCTION_SHA
        or comp.get("independent_variants_passed") != 2
        or comp.get("independent_cases_each") != 417
        or comp.get("raw_code_becomes_trusted_directly") is not False
        or install.get("merge_commit_sha") != INSTALL_COMMIT
        or install.get("postmerge_target_git_blob_sha") != LIVE_BLOB
        or install.get("model_can_modify_main_directly") is not False
        or install.get("authority_delta") != 0
        or revert.get("isolated_rehearsal") != "PASS_IN_READONLY_INDEPENDENT_GIT_WORKER"
        or revert.get("rehearsal_run_id") != 41182302141
        or revert.get("production_rollback_executed") is not False
        or revert.get("automatic_main_revert_enabled") is not False
        or limits.get("full_autonomy_status") != "PARTIAL"
        or limits.get("native_demiurge_authorship_proven") is not False
        or limits.get("p2_ten_independent_tasks_accepted") is not False):
        deny("UNTRUSTED_ARCHIVED_CLAIMS")
    exact = comp.get("source")
    if not isinstance(exact, str) or sha256(exact.encode()) != MODEL_FUNCTION_SHA:
        deny("COMPILER_OUTPUT_HASH")
    if source.count(exact.encode()) != 1:
        deny("COMPILED_FUNCTION_MISSING")
    variants = model.get("raw_variants")
    if not isinstance(variants, list) or len(variants) != 2:
        deny("REJECTED_RAW_VARIANTS_MISSING")
    for row in variants:
        raw = row.get("source")
        if (not isinstance(raw, str)
            or sha256(raw.encode()) != row.get("source_sha256")
            or row.get("original_verdict") != "REJECTED_BY_NO_IMPORT_AST"):
            deny("RAW_MODEL_OR_REJECTION_CHANGED")
    return {"live_source_blob": LIVE_BLOB, "model_function_sha256": MODEL_FUNCTION_SHA,
            "authority_delta": 0, "production_rollback_executed": False,
            "raw_model_source_admitted": False}

def verify_runs(results):
    for rid, (expected_sha, expected_name) in PASS_RUNS.items():
        run = results.get(rid)
        if not isinstance(run, dict):
            deny("MISSING_VERIFIED_RUN")
        if (run.get("id") != rid or run.get("name") != expected_name
            or run.get("status") != "completed" or run.get("conclusion") != "success"
            or run.get("head_sha") != expected_sha
            or (run.get("head_repository") or {}).get("full_name") != REPO):
            deny("INVALID_RUN_" + str(rid))
    return sorted(PASS_RUNS)

def fetch_run(rid, token):
    if not token:
        deny("NO_READONLY_GITHUB_TOKEN")
    url = f"https://api.github.com/repos/{REPO}/actions/runs/{rid}"
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "JANUS-Self-Writer-Independent-Witness",
    })
    with urllib.request.urlopen(req, timeout=15) as response:
        data = response.read(80001)
    if len(data) > 80000:
        deny("GH_RUN_PAYLOAD_TOO_LARGE")
    return json.loads(data)

def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()

def verify_git(root, archive):
    if git(archive, "rev-parse", "HEAD") != ARCHIVE_COMMIT:
        deny("ARCHIVE_NOT_PINNED")
    if subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", INSTALL_COMMIT, "HEAD"],
        check=False).returncode != 0:
        deny("INSTALLED_COMMIT_NOT_ANCESTOR")
    return git(root, "rev-parse", "HEAD")

def verify_main_archive(path, independently_pinned_bytes):
    """Since verified PR #395 merged, absent/changed main evidence is HOLD."""
    if not path.is_file():
        deny("MAIN_JOURNAL_MISSING")
    observed = path.read_bytes()
    if observed != independently_pinned_bytes:
        deny("MAIN_JOURNAL_NOT_SAME_AS_PINNED_EVIDENCE")
    return True

def audit(root, archive, run_loader):
    raw = (root / CODE).read_bytes()
    journal = (archive / JOURNAL).read_bytes()
    if not 0 < len(raw) <= 25000 or not 0 < len(journal) <= 25000:
        deny("OVERSIZED_INPUT")
    evidence = json.loads(journal)
    main_sha = verify_git(root, archive)
    data = verify_contents(raw, evidence, ARCHIVE_COMMIT)
    runs = verify_runs({rid: run_loader(rid) for rid in PASS_RUNS})
    canonical = root / JOURNAL
    journal_on_main = verify_main_archive(canonical, journal)
    return {
        "schema": SCHEMA, "status": "VERIFIED_EXISTING_PATCH__NOT_AUTONOMOUS_SELF_REPAIR",
        "observed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "main_head_sha": main_sha, "install_commit": INSTALL_COMMIT,
        "archive_commit": ARCHIVE_COMMIT, "evidence_sha256": sha256(journal),
        "evidence_on_main": journal_on_main,
        "github_runs_independently_checked": runs, **data,
        "native_demiurge_authored_patch": False, "full_autonomy": False,
        "host_executed_raw_model_code": False,
        "remote_write": False, "automatic_revert_permission": False,
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--main", type=Path, required=True)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    try:
        result = audit(a.main.resolve(), a.archive.resolve(),
                       lambda rid: fetch_run(rid, os.environ.get("GITHUB_TOKEN", "")))
    except (ValueError, OSError, TypeError, KeyError, subprocess.CalledProcessError,
            urllib.error.URLError) as exc:
        result = {"schema": SCHEMA, "status": "HOLD_FAIL_CLOSED",
                  "reason": str(exc)[:180], "remote_write": False,
                  "full_autonomy": False}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                     encoding="utf-8")
    print("JANUS_SELF_WRITER_INTEGRITY=" + result["status"])
    if result["status"] == "HOLD_FAIL_CLOSED":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
