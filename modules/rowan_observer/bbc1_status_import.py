#!/usr/bin/env python3
"""Durably archive *sanitized* BBC1 WT/K5A provider-status artifacts.

Separate namespace from the canonical eight-mutant S2 evidence stream.
Read-only: this module never imports the Rowan SDK, calls its provider, spends
credits, promotes structural confidence into protein fitness, or edits S2 state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

SOURCE_REPO = "Hawkar-usls/Janus"
WORKFLOW_FILE = ".github/workflows/rowan-bbc1-budgeted-autopilot.yml"
ARTIFACT_PREFIX = "bbc1-rowan-public-safe-status-"
ROOT_REL = Path("data/rowan/bbc1_structural_status")
SCHEMA = "janus.rowan.bbc1.provider_structural_status.v2"
MAX_BYTES = 80000
MAX_RUNS = 50
CREDIT_CAP = 10
SHA = re.compile(r"[a-f0-9]{40}\Z")
DIGEST = re.compile(r"[a-f0-9]{64}\Z")
UUID_HASH = re.compile(r"[a-f0-9]{16}\Z")
ALLOWED = frozenset({
    "NOT_SUBMITTED", "PENDING_OR_FAILED",
    "ROWAN_RESULT_RETURNED_NO_FITNESS_CLAIM",
    "RESULT_UNREADABLE_REQUIRES_MANUAL_REVIEW",
})


class EvidenceHold(ValueError):
    pass


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")


def fail(predicate, code):
    if not predicate:
        raise EvidenceHold(code)


def finite(value, low, high, *, nullable=False):
    if nullable and value is None:
        return None
    fail(type(value) in (int, float) and math.isfinite(value)
         and low <= value <= high, "INVALID_NUMERIC_PROVIDER_FIELD")
    return float(value)


def validate(payload):
    """Recalculate paired values; only accept the strict public-safe schema."""
    fail(type(payload) is dict, "PAYLOAD_NOT_OBJECT")
    expected = {
        "schema", "source_kind", "case_order", "entries",
        "paired_confidence_deltas_not_fitness", "tranception_model_run",
        "protein_fitness_validated", "experimental_assay_independent_review",
        "provider_spend_by_collector",
    }
    fail(set(payload) == expected, "UNEXPECTED_PAYLOAD_FIELDS")
    fail(payload["schema"] == SCHEMA and
         payload["source_kind"] == "REAL_PROVIDER_READ_ONLY_STATUS",
         "SOURCE_SCHEMA_OR_KIND_DRIFT")
    fail(payload["case_order"] == ["wildtype", "K5A"] and
         type(payload["entries"]) is list and len(payload["entries"]) == 2,
         "CASE_IDENTITY_DRIFT")
    fail(payload["tranception_model_run"] is False and
         payload["protein_fitness_validated"] is False and
         payload["provider_spend_by_collector"] is False and
         payload["experimental_assay_independent_review"] == "OPEN",
         "UNAUTHORIZED_SCIENCE_OR_BILLING_CLAIM")
    clean = []
    for arm, raw in zip(("wildtype", "K5A"), payload["entries"]):
        fail(type(raw) is dict and raw.get("arm") == arm and
             raw.get("status") in ALLOWED, "PROVIDER_ROW_IDENTITY_DRIFT")
        status = raw["status"]
        if status == "NOT_SUBMITTED":
            fail(set(raw) == {"arm", "status"}, "UNEXPECTED_UNSUBMITTED_FIELDS")
            clean.append({"arm": arm, "status": status})
            continue
        expected_row = {
            "arm", "status", "provider_uuid_hash",
            "provider_credits_charged", "credit_cap", "charge_over_cap_review",
        }
        if status == "ROWAN_RESULT_RETURNED_NO_FITNESS_CLAIM":
            expected_row.update(("ptm", "avg_lddt"))
        fail(set(raw) == expected_row, "PROVIDER_ROW_FIELDS_DRIFT")
        fail(raw["credit_cap"] == CREDIT_CAP and
             type(raw["credit_cap"]) is int, "CREDIT_CAP_DRIFT")
        uid = raw["provider_uuid_hash"]
        fail(type(uid) is str and (uid == "MISSING" or UUID_HASH.fullmatch(uid)),
             "INVALID_WORKFLOW_ID_DIGEST")
        charge = finite(raw["provider_credits_charged"], 0, 100000,
                        nullable=True)
        should_alert = charge is not None and charge > CREDIT_CAP
        fail(type(raw["charge_over_cap_review"]) is bool and
             raw["charge_over_cap_review"] is should_alert,
             "CREDIT_ALERT_CONTRADICTION")
        item = {"arm": arm, "status": status, "provider_uuid_hash": uid,
                "provider_credits_charged": charge, "credit_cap": CREDIT_CAP,
                "charge_over_cap_review": should_alert}
        if status == "ROWAN_RESULT_RETURNED_NO_FITNESS_CLAIM":
            item["ptm"] = finite(raw["ptm"], 0, 1, nullable=True)
            item["avg_lddt"] = finite(raw["avg_lddt"], 0, 1, nullable=True)
        clean.append(item)
    paired = payload["paired_confidence_deltas_not_fitness"]
    fail(type(paired) is dict and
         set(paired) <= {"K5A_minus_wildtype_ptm",
                         "K5A_minus_wildtype_avg_lddt"}, "PAIRED_FIELDS_DRIFT")
    reconstructed = {}
    if all(r["status"] == "ROWAN_RESULT_RETURNED_NO_FITNESS_CLAIM"
           for r in clean):
        for field in ("ptm", "avg_lddt"):
            if clean[0][field] is not None and clean[1][field] is not None:
                reconstructed["K5A_minus_wildtype_" + field] = round(
                    clean[1][field] - clean[0][field], 6)
    fail(set(paired) == set(reconstructed), "PAIRED_SCORES_MISSING_OR_EXTRA")
    for key, value in reconstructed.items():
        fail(abs(finite(paired[key], -1, 1) - value) <= 0.000002,
             "PAIRED_SCORE_REPLAY_MISMATCH")
    return {
        "schema_id": "janus.rowan.bbc1.structural_status_archive.v1",
        "source_schema": SCHEMA,
        "cases": clean,
        "paired_confidence_deltas_not_fitness": reconstructed,
        "billing_alert": any(r.get("charge_over_cap_review", False) for r in clean),
        "source_kind": "REAL_PROVIDER_READ_ONLY_STATUS",
        "science_gates": {
            "structural_confidence_is_fitness": False,
            "experimental_assay_independent_review": "OPEN",
            "protein_fitness_validated": False,
            "tranception_model_run": False,
            "new_provider_jobs_authorized": False,
            "new_spend_authorized": False,
        },
    }


def github(endpoint):
    result = subprocess.run(["gh", "api", "--method", "GET", endpoint],
                            text=True, capture_output=True, timeout=35)
    fail(result.returncode == 0, "GITHUB_SOURCE_API_UNAVAILABLE")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise EvidenceHold("GITHUB_SOURCE_JSON_INVALID") from exc


def source_runs():
    # Restrict to the known-good workflow-scoped endpoint used by S2 Observer.
    endpoint = (f"repos/{SOURCE_REPO}/actions/workflows/"
                f"{WORKFLOW_FILE.rsplit('/', 1)[-1]}/runs"
                f"?branch=main&status=completed&per_page=100")
    data = github(endpoint)
    fail(type(data) is dict and type(data.get("workflow_runs")) is list,
         "SOURCE_RUN_LIST_INVALID")
    return sorted([
        r for r in data["workflow_runs"]
        if type(r) is dict and r.get("path") == WORKFLOW_FILE
        and r.get("head_branch") == "main"
        and r.get("conclusion") == "success"
        and r.get("event") in ("schedule", "workflow_dispatch")
        and type(r.get("id")) is int and r["id"] > 0
        and type(r.get("head_sha")) is str
        and SHA.fullmatch(r["head_sha"])
    ], key=lambda r: r["id"], reverse=True)[:MAX_RUNS]


def artifact(run_id):
    meta = github(f"repos/{SOURCE_REPO}/actions/runs/{run_id}/artifacts?per_page=100")
    fail(type(meta) is dict and type(meta.get("artifacts")) is list,
         "SOURCE_ARTIFACT_LIST_INVALID")
    name = ARTIFACT_PREFIX + str(run_id)
    matches = [a for a in meta["artifacts"] if a.get("name") == name
               and a.get("expired") is False]
    fail(len(matches) == 1, "UNIQUE_UNEXPIRED_ARTIFACT_REQUIRED")
    with TemporaryDirectory(prefix="rowan-bbc1-status-") as tmp:
        p = subprocess.run(
            ["gh", "run", "download", str(run_id), "--repo", SOURCE_REPO,
             "--name", name, "--dir", tmp],
            text=True, capture_output=True, timeout=70)
        fail(p.returncode == 0, "ARTIFACT_DOWNLOAD_FAILED")
        files = [x for x in Path(tmp).rglob("*") if x.is_file()]
        fail(len(files) == 1 and files[0].suffix == ".json"
             and 0 < files[0].stat().st_size <= MAX_BYTES,
             "ARTIFACT_SHAPE_OR_SIZE_INVALID")
        raw = files[0].read_bytes()
    try:
        return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceHold("ARTIFACT_JSON_INVALID") from exc


def previous(root):
    p = root / ROOT_REL / "LATEST.json"
    if not p.exists():
        return 0
    fail(p.stat().st_size <= MAX_BYTES, "PREVIOUS_LATEST_OVERSIZED")
    saved = json.loads(p.read_text(encoding="utf-8"))
    rid = saved.get("latest_source_run")
    name = saved.get("latest_receipt")
    digest = saved.get("latest_receipt_sha256")
    fail(saved.get("schema_id") == "janus.rowan.bbc1.structural_status_latest.v1"
         and type(rid) is int and rid > 0
         and type(name) is str and name.startswith("ROWAN-BBC1-WT-K5A-")
         and "/" not in name and "\\" not in name
         and type(digest) is str and DIGEST.fullmatch(digest),
         "PREVIOUS_CHECKPOINT_INVALID")
    receipt = root / ROOT_REL / "receipts" / name
    fail(receipt.is_file() and hashlib.sha256(receipt.read_bytes()).hexdigest() == digest,
         "PREVIOUS_RECEIPT_INTEGRITY_HOLD")
    r = json.loads(receipt.read_text(encoding="utf-8"))
    fail(r.get("source", {}).get("run_id") == rid, "PREVIOUS_SOURCE_MISMATCH")
    return rid


def update(root, runs, retrieve=artifact, limit=12):
    root = Path(root).resolve()
    checkpoint = previous(root)
    if runs and runs[0]["id"] < checkpoint:
        raise EvidenceHold("SOURCE_HISTORY_BEHIND_DURABLE_CHECKPOINT")
    current = sorted([r for r in runs if r["id"] > checkpoint][:limit],
                     key=lambda r: r["id"])
    if not current:
        return {"status": "IDEMPOTENT_NO_CHANGE", "new_receipts": 0,
                "latest_source_run": checkpoint}
    # Validate the entire selected batch before writing any durable evidence.
    receipts = []
    for r in current:
        payload, raw_digest = retrieve(r["id"])
        data = validate(payload)
        data["source"] = {
            "repo": SOURCE_REPO,
            "workflow_file": WORKFLOW_FILE,
            "run_id": r["id"],
            "run_link": f"https://github.com/{SOURCE_REPO}/actions/runs/{r['id']}",
            "head_sha": r["head_sha"],
            "artifact_sha256": raw_digest,
            "collection_only": True,
        }
        receipts.append(data)
    folder = root / ROOT_REL / "receipts"
    folder.mkdir(parents=True, exist_ok=True)
    last_name = last_digest = None
    for item in receipts:
        raw = json.dumps(item, ensure_ascii=False, sort_keys=True,
                         indent=2, allow_nan=False).encode() + b"\n"
        digest = hashlib.sha256(raw).hexdigest()
        name = f"ROWAN-BBC1-WT-K5A-{item['source']['run_id']}-{digest[:16]}.json"
        destination = folder / name
        fail(not destination.exists() or destination.read_bytes() == raw,
             "IMMUTABLE_RECEIPT_COLLISION")
        if not destination.exists():
            destination.write_bytes(raw)
        last_name, last_digest = name, digest
    latest = {
        "schema_id": "janus.rowan.bbc1.structural_status_latest.v1",
        "latest_source_run": receipts[-1]["source"]["run_id"],
        "latest_receipt": last_name,
        "latest_receipt_sha256": last_digest,
        "source_artifact_sha256": receipts[-1]["source"]["artifact_sha256"],
        "science_authority": "STRUCTURAL_STATUS_ONLY_NOT_FITNESS",
        "new_provider_jobs_authorized": False,
        "new_spend_authorized": False,
    }
    (root / ROOT_REL / "LATEST.json").write_bytes(
        json.dumps(latest, ensure_ascii=False, sort_keys=True, indent=2).encode()+b"\n")
    return {"status": "ARCHIVED_SOURCE_ATTESTED", "new_receipts": len(receipts),
            "latest_source_run": latest["latest_source_run"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.limit <= MAX_RUNS:
        raise SystemExit("BAD_LIMIT")
    try:
        status = update(Path(args.root), source_runs(), limit=args.limit)
        print("ROWAN_BBC1_STRUCTURAL_ARCHIVE=" + status["status"])
        print("ROWAN_BBC1_STRUCTURAL_NEW_RECEIPTS=" + str(status["new_receipts"]))
        print("ROWAN_BBC1_STRUCTURAL_SOURCE_RUN=" + str(status["latest_source_run"]))
        return 0
    except EvidenceHold as exc:
        allowed = str(exc)
        safe = allowed if re.fullmatch(r"[A-Z][A-Z0-9_]{2,95}", allowed) else "UNCLASSIFIED_HOLD"
        print("ROWAN_BBC1_STRUCTURAL_ARCHIVE=EVIDENCE_HOLD")
        print("ROWAN_BBC1_STRUCTURAL_HOLD_CODE=" + safe)
        return 2
    except (OSError, ValueError, subprocess.SubprocessError):
        print("ROWAN_BBC1_STRUCTURAL_ARCHIVE=IO_OR_INPUT_HOLD")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
