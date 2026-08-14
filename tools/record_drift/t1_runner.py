#!/usr/bin/env python3
from __future__ import annotations

import hashlib, json, subprocess, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "data" / "JANUS-RECORD-DRIFT-BASELINE-T0-v0.1.json"
PROTOCOL = ROOT / "data" / "JANUS-RECORD-DRIFT-OBSERVATORY-v0.1.json"
JDIR = ROOT / "registry" / "record_drift"


def git(*args, check=True):
    p = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if check and p.returncode:
        raise RuntimeError(p.stderr.strip())
    return p.stdout.strip()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob(commit, path):
    p = subprocess.run(["git", "rev-parse", f"{commit}:{path}"], cwd=ROOT, text=True, capture_output=True)
    return p.stdout.strip() if p.returncode == 0 else None


def git_bytes(commit, path):
    p = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=ROOT, capture_output=True)
    return p.stdout if p.returncode == 0 else None


def creation_commit(path):
    x = git("log", "--diff-filter=A", "--follow", "--format=%H", "-n", "1", "--", path, check=False)
    return x or None


def latest_journal():
    files = [p for p in JDIR.glob("JANUS-RECORD-DRIFT-JOURNAL-*.json") if "GENESIS" not in p.name]
    return sorted(files)[-1] if files else JDIR / "JANUS-RECORD-DRIFT-JOURNAL-GENESIS-v0.1.json"


def prior_external_hashes(path):
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {c["record_id"]: c["raw_sha256"] for c in obj.get("checks", []) if c.get("record_id", "").startswith("EXT-STATIC-") and c.get("raw_sha256")}


def check_previous_journal(path):
    rel = path.relative_to(ROOT).as_posix()
    cc = creation_commit(rel)
    cb = blob(cc, rel) if cc else None
    hb = blob("HEAD", rel)
    ok = bool(cc and cb and hb and cb == hb)
    return {
        "record_id": "JOURNAL-CHAIN", "path": rel,
        "creation_commit": cc, "creation_blob_sha": cb, "current_blob_sha": hb,
        "raw_sha256_current": sha(path.read_bytes()),
        "classification": "R0_STABLE" if ok else "R9_JOURNAL_CHAIN_BREAK",
        "status": "previous_journal_matches_creation_blob" if ok else "previous_journal_changed_or_unresolvable"
    }


def check_pinned(s):
    ob = blob(s["pinned_commit"], s["path"])
    raw = git_bytes(s["pinned_commit"], s["path"])
    exp = s.get("git_blob_sha")
    ok = ob is not None and raw is not None and (exp is None or exp == ob)
    return {
        "record_id": s["record_id"], "class": s["class"], "path": s["path"],
        "pinned_commit": s["pinned_commit"], "expected_git_blob_sha": exp,
        "observed_git_blob_sha": ob, "raw_sha256": sha(raw) if raw is not None else None,
        "classification": "R0_STABLE" if ok else "R4_UNDECLARED_REMOTE_CONTENT_DRIFT",
        "status": "pinned_identity_stable" if ok else "pinned_identity_mismatch_or_missing"
    }


def check_live(s):
    old = s["head_at_registration"]; new = git("rev-parse", "HEAD")
    a = blob(old, s["path"]); b = blob(new, s["path"])
    if a is None or b is None:
        cl, st = "R7_IDENTITY_DRIFT", "path_unresolvable"
    elif a == b:
        cl, st = "R0_STABLE", "path_content_unchanged"
    else:
        cl, st = "R3_DECLARED_SOURCE_REVISION", "path_changed_with_git_history"
    return {"record_id": s["record_id"], "class": s["class"], "path": s["path"], "T0_head": old, "Tn_head": new, "T0_blob_sha": a, "Tn_blob_sha": b, "classification": cl, "status": st}


def check_external(s, prior):
    req = urllib.request.Request(s["uri"], headers={"User-Agent": "JANUS-Record-Drift/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
        h = sha(raw); prev = prior.get(s["record_id"])
        if prev is None:
            cl, st = "R0_STABLE", "first_raw_capture_baseline_extended_no_drift_claim"
        elif prev == h:
            cl, st = "R0_STABLE", "raw_sha256_matches_previous_capture"
        else:
            cl, st = "R4_UNDECLARED_REMOTE_CONTENT_DRIFT", "raw_sha256_changed_requires_revision_check"
        return {"record_id": s["record_id"], "class": s["class"], "name": s["name"], "uri": s["uri"], "byte_length": len(raw), "raw_sha256_previous": prev, "raw_sha256": h, "classification": cl, "status": st}
    except Exception as e:
        return {"record_id": s["record_id"], "class": s["class"], "name": s["name"], "uri": s["uri"], "classification": "UNAVAILABLE_NOT_COUNTED", "status": f"retrieval_failed:{type(e).__name__}:{e}"}


def main():
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    prev = latest_journal(); priors = prior_external_hashes(prev)
    checks = [check_previous_journal(prev)]
    checked_aliases = set()
    for s in base["subjects"]:
        c = s["class"]
        if c in {"A_git_immutable", "C_registry_artifacts"}:
            checks.append(check_pinned(s))
        elif c == "B_git_live":
            checks.append(check_live(s))
        elif c == "D_test_results":
            key = (s["path"], s["pinned_commit"])
            if key in checked_aliases:
                checks.append({"record_id": s["record_id"], "class": c, "classification": "R0_STABLE", "status": "recursive_alias_already_checked"})
            else:
                checks.append(check_pinned(s)); checked_aliases.add(key)
        elif c == "F_external_static":
            checks.append(check_external(s, priors))
        elif c == "G_external_live":
            checks.append({"record_id": s["record_id"], "class": c, "classification": "NOT_ADMITTED_NOT_COUNTED", "status": s.get("status", "pool_open")})
    countable = [x for x in checks if str(x.get("classification", "")).startswith("R")]
    counts = {}
    for x in countable: counts[x["classification"]] = counts.get(x["classification"], 0) + 1
    now = datetime.now(timezone.utc); stamp = now.strftime("%Y%m%dT%H%M%SZ")
    out = JDIR / f"JANUS-RECORD-DRIFT-JOURNAL-{stamp}.json"
    entry = {
        "artifact_uuid": f"JANUS-RECORD-DRIFT-JOURNAL-{stamp}", "journal_id": "JANUS-RECORD-DRIFT-JOURNAL",
        "entry_id": stamp, "version": "0.1-runner", "observed_at_utc": now.isoformat(),
        "runner": "tools/record_drift/t1_runner.py", "protocol": PROTOCOL.relative_to(ROOT).as_posix(), "baseline": BASELINE.relative_to(ROOT).as_posix(),
        "previous_entry": {"path": prev.relative_to(ROOT).as_posix(), "sha256_as_observed_now": sha(prev.read_bytes())},
        "checks": checks,
        "summary": {"countable_checks": len(countable), "class_counts": counts, "R10_count": counts.get("R10_UNEXPLAINED_CONFIRMED_DRIFT", 0), "unexplained_confirmed_drift": counts.get("R10_UNEXPLAINED_CONFIRMED_DRIFT", 0) > 0},
        "claim_ceiling": {"ordinary_declared_changes_are_not_anomalies": True, "memory_or_display_difference_alone_is_not_raw_drift": True, "R10_requires_followup_exclusion_gate": True, "retrocausality_claim": False, "timeline_change_claim": False},
        "self_monitoring": {"this_entry_does_not_embed_its_own_final_hash": True, "next_run_must_verify_this_file_against_its_creation_commit_blob": True}
    }
    out.write_text(json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"journal": out.relative_to(ROOT).as_posix(), "summary": entry["summary"]}, indent=2))

if __name__ == "__main__":
    main()
