#!/usr/bin/env python3
"""Fail-closed P0 acquisition-readiness gate for alternate-editorial Linear A sources.

This runner does not send requests, download books, inspect transcription content, or
assign L1/L2/L3. It only proves that acquisition routes are ready while source bytes
and R3B admission remain absent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RUNNER_ID = "JANUS-LINEAR-A-R3B-P0-ACQUISITION-READINESS-v1.0"
EXPECTED = [
    ("RILA_S1", "data/JANUS-LINEAR-A-R3B-0-RILA-S1-ACQUISITION-REQUEST-PACKET-2026-08-14-v0.1.json", "READY_FOR_REQUEST_NOT_YET_SENT"),
    ("CTLA_SECOND_EDITION_1994", "data/JANUS-LINEAR-A-R3B-0-CTLA-ACQUISITION-REQUEST-PACKET-2026-08-14-v0.1.json", "READY_FOR_PUBLISHER_REQUEST_NOT_YET_SENT"),
    ("TMT_1999", "data/JANUS-LINEAR-A-R3B-0-TMT-ACQUISITION-REQUEST-PACKET-2026-08-14-v0.1.json", "READY_FOR_REQUEST_NOT_YET_SENT"),
]
RANKING = ["RILA_S1", "CTLA_SECOND_EDITION_1994", "TMT_1999"]


def load(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"NOT_OBJECT:{path}")
    return obj


def validate_packet(source_id: str, obj: dict[str, Any], expected_status: str) -> list[str]:
    errors: list[str] = []
    if obj.get("status") != expected_status:
        errors.append(f"STATUS_MISMATCH:{source_id}:{obj.get('status')}:{expected_status}")
    source = obj.get("source")
    if isinstance(source, dict):
        observed = source.get("source_id")
        if observed != source_id:
            errors.append(f"SOURCE_ID_MISMATCH:{source_id}:{observed}")
    else:
        errors.append(f"SOURCE_OBJECT_MISSING:{source_id}")
    ceiling = obj.get("claim_ceiling")
    if not isinstance(ceiling, dict):
        return errors + [f"CLAIM_CEILING_MISSING:{source_id}"]
    request_fields = [k for k in ceiling if "request_sent" in k]
    if not request_fields:
        errors.append(f"REQUEST_SENT_FIELD_MISSING:{source_id}")
    for key in request_fields:
        if ceiling.get(key) is not False:
            errors.append(f"REQUEST_ALREADY_SENT:{source_id}:{key}")
    if ceiling.get("source_bytes_acquired") is not False:
        errors.append(f"SOURCE_BYTES_NOT_FALSE:{source_id}:{ceiling.get('source_bytes_acquired')}")
    if ceiling.get("R3B_0_receipt_admitted") is not False:
        errors.append(f"R3B0_ALREADY_ADMITTED:{source_id}")
    if ceiling.get("external_transcription_replication_established") is not False:
        errors.append(f"EXTERNAL_REPLICATION_ALREADY_ESTABLISHED:{source_id}")
    if ceiling.get("new_anchor") is not False:
        errors.append(f"ANCHOR_PROMOTED:{source_id}")
    if ceiling.get("decipherment") is not False:
        errors.append(f"DECIPHERMENT_PROMOTED:{source_id}")
    return errors


def readiness(repo_root: Path) -> dict[str, Any]:
    routes = []
    all_errors: list[str] = []
    for source_id, rel, status in EXPECTED:
        path = repo_root / rel
        if not path.exists():
            errors = [f"MISSING_PACKET:{rel}"]
            obj = {}
        else:
            try:
                obj = load(path)
                errors = validate_packet(source_id, obj, status)
            except Exception as exc:
                obj = {}
                errors = [f"READ_OR_VALIDATE_ERROR:{rel}:{type(exc).__name__}:{exc}"]
        routes.append({"source_id": source_id, "path": rel, "expected_status": status, "errors": errors})
        all_errors.extend(errors)

    digital_rel = "data/JANUS-LINEAR-A-R3B-0-RILA-S1-DIGITAL-EDITION-ROUTE-RECONCILIATION-2026-08-14-v0.1.json"
    digital_path = repo_root / digital_rel
    digital = load(digital_path) if digital_path.exists() else {}
    if digital.get("status") != "FULL_DIGITAL_EDITION_EXISTENCE_CONFIRMED_LOCAL_BYTES_NOT_ACQUIRED":
        all_errors.append(f"RILA_DIGITAL_ROUTE_STATUS_MISMATCH:{digital.get('status')}")
    if digital.get("claim_ceiling", {}).get("local_source_bytes_acquired") is not False:
        all_errors.append("RILA_DIGITAL_ROUTE_FALSE_BYTE_PROMOTION")
    if digital.get("claim_ceiling", {}).get("R3B_0_receipt_admitted") is not False:
        all_errors.append("RILA_DIGITAL_ROUTE_FALSE_R3B0_PROMOTION")

    consolidated_rel = "data/JANUS-LINEAR-A-R3B-0-P0-OUTREACH-READINESS-2026-08-14-v1.0.json"
    consolidated = load(repo_root / consolidated_rel)
    if consolidated.get("status") != "P0_ACQUISITION_ROUTES_READY_NO_REQUESTS_SENT_NO_SOURCE_BYTES_ACQUIRED":
        all_errors.append("CONSOLIDATED_STATUS_MISMATCH")
    observed_order = [r.get("source_id") for r in consolidated.get("routes", []) if isinstance(r, dict)]
    if observed_order != RANKING:
        all_errors.append(f"RANKING_MISMATCH:{observed_order}")
    state = consolidated.get("current_state", {})
    if state.get("requests_sent") != 0 or state.get("new_source_byte_receipts") != 0 or state.get("R3B_0_admitted_source_receipts") != 0:
        all_errors.append(f"CONSOLIDATED_STATE_NOT_ZERO:{state}")

    status = "P0_READY_FOR_LAWFUL_ACQUISITION_NO_BYTES" if not all_errors else "P0_READINESS_FAIL_CLOSED"
    return {
        "artifact_uuid": "JANUS-LINEAR-A-R3B-0-P0-ACQUISITION-READINESS-RESULT-2026-08-14-v1.0",
        "version": "v1.0",
        "node_type": "alternate_editorial_source_acquisition_readiness_result",
        "status": status,
        "runner_id": RUNNER_ID,
        "route_ranking": RANKING,
        "routes": routes,
        "RILA_digital_edition_route": {
            "path": digital_rel,
            "status": digital.get("status"),
            "full_digital_edition_existence_confirmed": digital.get("claim_ceiling", {}).get("full_digital_edition_existence_confirmed"),
            "local_source_bytes_acquired": digital.get("claim_ceiling", {}).get("local_source_bytes_acquired"),
        },
        "requests_sent": 0 if not all_errors else None,
        "source_bytes_acquired": 0 if not all_errors else None,
        "R3B_0_admitted_receipts": 0 if not all_errors else None,
        "scientific_content_inspected": False,
        "claim_ceiling": {
            "operational_readiness_only": True,
            "R3B_effect": "NONE",
            "external_transcription_replication_established": False,
            "new_anchor": False,
            "decipherment": False,
        },
        "errors": all_errors,
        "required_next": "Acquire one source lawfully, then stop parallel outreach where possible and run generic quarantine plus the frozen R3B-0 receipt before transcription-content inspection.",
    }


def self_test() -> dict[str, Any]:
    good = {
        "status": "READY_FOR_REQUEST_NOT_YET_SENT",
        "source": {"source_id": "RILA_S1"},
        "claim_ceiling": {"request_sent": False, "source_bytes_acquired": False, "R3B_0_receipt_admitted": False, "external_transcription_replication_established": False, "new_anchor": False, "decipherment": False},
    }
    assert validate_packet("RILA_S1", good, "READY_FOR_REQUEST_NOT_YET_SENT") == []
    bad = json.loads(json.dumps(good))
    bad["claim_ceiling"]["request_sent"] = True
    assert any("REQUEST_ALREADY_SENT" in e for e in validate_packet("RILA_S1", bad, "READY_FOR_REQUEST_NOT_YET_SENT"))
    bad2 = json.loads(json.dumps(good))
    bad2["claim_ceiling"]["R3B_0_receipt_admitted"] = True
    assert any("R3B0_ALREADY_ADMITTED" in e for e in validate_packet("RILA_S1", bad2, "READY_FOR_REQUEST_NOT_YET_SENT"))
    return {
        "runner_id": RUNNER_ID,
        "valid_unsent_route_pass": True,
        "sent_request_state_rejected": True,
        "false_R3B0_promotion_rejected": True,
        "scientific_content_inspected": False,
        "decipherment": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("self-test")
    p = sub.add_parser("readiness")
    p.add_argument("--repo-root", default=".")
    p.add_argument("--out")
    args = ap.parse_args()
    if args.cmd == "self-test":
        print(json.dumps(self_test(), ensure_ascii=False, indent=2, sort_keys=True)); return
    out = readiness(Path(args.repo_root))
    text = json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(text, end="")
    raise SystemExit(0 if out["status"] == "P0_READY_FOR_LAWFUL_ACQUISITION_NO_BYTES" else 1)


if __name__ == "__main__":
    main()
