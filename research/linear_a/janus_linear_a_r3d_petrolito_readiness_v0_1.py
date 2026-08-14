#!/usr/bin/env python3
"""Fail-closed readiness gate for recovery of the 2015 Petrolito et al. TEI-EpiDoc corpus."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

RUNNER_ID = "JANUS-LINEAR-A-R3D-PETROLITO-READINESS-v0.1"
ADMITTED_STATUS = "R3D_PETROLITO_SOURCE_BYTES_ACQUIRED"
SOURCE_ID = "PETROLITO_ET_AL_2015_LINEAR_A_DIGITAL_CORPUS"
DOI = "10.18653/v1/W15-3715"
ALLOWED_ROUTES = {"AUTHOR_OR_INSTITUTION_ORIGINAL_ARCHIVE", "WEB_ARCHIVE_BYTE_REPLAY", "VERIFIED_MIRROR_WITH_LINEAGE_PROOF"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_CONTENT_STATE = "IDENTITY_AND_BYTES_ONLY_SCIENTIFIC_CONTENT_NOT_SCORED"


def _valid_file(row: Any) -> bool:
    return (
        isinstance(row, dict)
        and isinstance(row.get("original_name"), str) and bool(row["original_name"])
        and isinstance(row.get("sha256"), str) and bool(HEX64.fullmatch(row["sha256"]))
        and isinstance(row.get("bytes"), int) and row["bytes"] >= 0
        and isinstance(row.get("mime_type"), str) and bool(row["mime_type"])
        and isinstance(row.get("encoding_or_binary_container"), str) and bool(row["encoding_or_binary_container"])
    )


def validate_receipt(obj: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["RECEIPT_NOT_OBJECT"]
    if obj.get("node_type") != "r3d_petrolito_source_acquisition_receipt":
        errors.append("NODE_TYPE_MISMATCH")
    if obj.get("status") != ADMITTED_STATUS:
        errors.append(f"STATUS_NOT_ADMITTED:{obj.get('status')}")
    source = obj.get("source_identity")
    if not isinstance(source, dict):
        errors.append("SOURCE_IDENTITY_NOT_OBJECT")
    else:
        if source.get("source_id") != SOURCE_ID:
            errors.append("SOURCE_ID_MISMATCH")
        if source.get("doi") != DOI:
            errors.append("SOURCE_DOI_MISMATCH")
    acq = obj.get("acquisition")
    if not isinstance(acq, dict):
        errors.append("ACQUISITION_NOT_OBJECT")
        acq = {}
    route = acq.get("route")
    if route not in ALLOWED_ROUTES:
        errors.append(f"ACQUISITION_ROUTE_INVALID:{route}")
    for field in ("timestamp", "source_or_snapshot_url"):
        if not isinstance(acq.get(field), str) or not acq.get(field):
            errors.append(f"ACQUISITION_MISSING:{field}")
    files = obj.get("original_container_or_files")
    if not isinstance(files, list) or not files:
        errors.append("ORIGINAL_FILES_MISSING_OR_NOT_LIST")
        files = []
    for i, row in enumerate(files):
        if not _valid_file(row):
            errors.append(f"ORIGINAL_FILE[{i}]_IDENTITY_INVALID")
    if route == "WEB_ARCHIVE_BYTE_REPLAY":
        for field in ("historical_snapshot_timestamp", "original_url", "replay_url"):
            if not isinstance(acq.get(field), str) or not acq.get(field):
                errors.append(f"WEB_ARCHIVE_MISSING:{field}")
        for i, row in enumerate(files):
            if isinstance(row, dict) and row.get("archive_wrapper_html") is True and row.get("counts_as_original_XML") is True:
                errors.append(f"WEB_ARCHIVE_WRAPPER_FALSE_SOURCE[{i}]")
    lineage = obj.get("lineage_evidence")
    if not isinstance(lineage, dict):
        errors.append("LINEAGE_EVIDENCE_NOT_OBJECT")
    else:
        if lineage.get("relationship_to_2015_corpus_established") is not True:
            errors.append("LINEAGE_TO_2015_CORPUS_NOT_ESTABLISHED")
        if not isinstance(lineage.get("evidence"), list) or not lineage.get("evidence"):
            errors.append("LINEAGE_EVIDENCE_EMPTY")
    if not isinstance(obj.get("license_or_access_basis"), str) or not obj.get("license_or_access_basis"):
        errors.append("LICENSE_OR_ACCESS_BASIS_MISSING")
    if obj.get("content_inspection_state") != REQUIRED_CONTENT_STATE:
        errors.append(f"CONTENT_INSPECTION_STATE_INVALID:{obj.get('content_inspection_state')}")
    ceiling = obj.get("claim_ceiling")
    if not isinstance(ceiling, dict):
        errors.append("CLAIM_CEILING_NOT_OBJECT")
    else:
        if ceiling.get("independence_class") != "L1_INDEPENDENT_DIGITIZATION_SHARED_TRANSCRIPTION_WITH_GORILA_EDITORIAL_CHECK":
            errors.append("CLAIM_CEILING_INDEPENDENCE_CLASS_INVALID")
        if ceiling.get("R3B_replication_credit") is not False:
            errors.append("CLAIM_CEILING_R3B_PROMOTION_FORBIDDEN")
        for key in ("new_anchor", "decipherment"):
            if ceiling.get(key) is not False:
                errors.append(f"CLAIM_CEILING_FORBIDDEN:{key}")
    return errors


def readiness(data_dir: Path) -> dict[str, Any]:
    rows = []
    admitted = []
    for path in sorted(data_dir.glob("JANUS-LINEAR-A-R3D-PETROLITO-ACQUISITION-RECEIPT-*.json")):
        if "CONTRACT" in path.name:
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            errors = validate_receipt(obj)
        except Exception as exc:
            obj = {}
            errors = [f"READ_OR_PARSE_ERROR:{type(exc).__name__}:{exc}"]
        row = {"path": str(path), "status": obj.get("status"), "errors": errors}
        rows.append(row)
        if not errors:
            admitted.append(row)
    if len(admitted) == 0:
        status = "BLOCKED_BYTES_NOT_RECOVERED"
    elif len(admitted) == 1:
        status = "READY_FOR_R3D_1_SOURCE_IDENTITY_AND_XML_INVENTORY"
    else:
        status = "BLOCKED_MULTIPLE_ADMITTED_RECEIPTS_REQUIRE_EXPLICIT_SELECTION"
    return {
        "artifact_uuid": "JANUS-LINEAR-A-R3D-PETROLITO-READINESS-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "historical_digital_corpus_recovery_readiness",
        "status": status,
        "runner_id": RUNNER_ID,
        "candidate_receipts": rows,
        "admitted_receipt_count": len(admitted),
        "scientific_content_scored": False,
        "source_adapter_executed": False,
        "independence_class_if_acquired": "L1_INDEPENDENT_DIGITIZATION_SHARED_TRANSCRIPTION_WITH_GORILA_EDITORIAL_CHECK",
        "R3B_replication_credit": False,
        "required_next": "Recover byte-bearing original/archive-replayed corpus files and complete the frozen acquisition receipt before XML schema inventory or content scoring.",
        "claim_ceiling": {"R3B_effect": "NONE", "new_anchor": False, "decipherment": False},
    }


def self_test() -> dict[str, Any]:
    good = {
        "node_type": "r3d_petrolito_source_acquisition_receipt",
        "status": ADMITTED_STATUS,
        "source_identity": {"source_id": SOURCE_ID, "doi": DOI},
        "acquisition": {"route": "AUTHOR_OR_INSTITUTION_ORIGINAL_ARCHIVE", "timestamp": "2026-08-14T19:00:00+03:00", "source_or_snapshot_url": "author://fixture"},
        "original_container_or_files": [{"original_name": "fixture.xml", "sha256": "a"*64, "bytes": 123, "mime_type": "application/xml", "encoding_or_binary_container": "UTF-8"}],
        "lineage_evidence": {"relationship_to_2015_corpus_established": True, "evidence": ["synthetic-fixture-only"]},
        "license_or_access_basis": "synthetic fixture",
        "content_inspection_state": REQUIRED_CONTENT_STATE,
        "claim_ceiling": {"independence_class": "L1_INDEPENDENT_DIGITIZATION_SHARED_TRANSCRIPTION_WITH_GORILA_EDITORIAL_CHECK", "R3B_replication_credit": False, "new_anchor": False, "decipherment": False},
    }
    assert validate_receipt(good) == []
    bad_wrapper = json.loads(json.dumps(good))
    bad_wrapper["acquisition"] = {"route": "WEB_ARCHIVE_BYTE_REPLAY", "timestamp": "2026", "source_or_snapshot_url": "archive://fixture", "historical_snapshot_timestamp": "20150101", "original_url": "http://old/fixture.xml", "replay_url": "https://archive/fixture.xml"}
    bad_wrapper["original_container_or_files"][0]["archive_wrapper_html"] = True
    bad_wrapper["original_container_or_files"][0]["counts_as_original_XML"] = True
    assert any("WRAPPER_FALSE_SOURCE" in e for e in validate_receipt(bad_wrapper))
    bad_r3b = json.loads(json.dumps(good))
    bad_r3b["claim_ceiling"]["R3B_replication_credit"] = True
    assert any("R3B_PROMOTION_FORBIDDEN" in e for e in validate_receipt(bad_r3b))
    return {
        "runner_id": RUNNER_ID,
        "valid_synthetic_receipt_pass": True,
        "web_archive_wrapper_false_source_rejected": True,
        "R3B_promotion_rejected": True,
        "scientific_content_scored": False,
        "decipherment": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("self-test")
    p = sub.add_parser("readiness")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--out")
    v = sub.add_parser("validate-receipt")
    v.add_argument("receipt")
    args = ap.parse_args()
    if args.cmd == "self-test":
        print(json.dumps(self_test(), ensure_ascii=False, indent=2, sort_keys=True)); return
    if args.cmd == "readiness":
        out = readiness(Path(args.data_dir))
        text = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.out: Path(args.out).write_text(text, encoding="utf-8")
        print(text, end=""); return
    obj = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    errors = validate_receipt(obj)
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
