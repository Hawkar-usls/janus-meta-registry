#!/usr/bin/env python3
"""Diagnostic-only wrapper around the frozen R3C-2C real projection runner.

The wrapper executes each fixed D5/D6 build independently on the same exact
source, catches exceptions, and if a build succeeds records cumulative
validator outputs. It never writes or promotes an IR projection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import janus_linear_a_r3c_real_ir_projection_v0_1 as proj
from janus_linear_a_r3c_source_loader_v0_4 import LOADER_ID, load_lineara_map_v0_4


def attempt(doc_id: str, kind: str, fn) -> dict[str, Any]:
    row: dict[str, Any] = {"document": doc_id, "kind": kind, "projection_written": False}
    try:
        ir, source_audit = fn()
    except Exception as exc:
        row.update({
            "build_status": "EXCEPTION",
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "validation_attempted": False,
        })
        return row
    row["build_status"] = "BUILT_IN_MEMORY"
    row["ir_sha256_in_memory"] = ir.get("ir_sha256")
    row["source_audit"] = source_audit
    try:
        validation = proj.validate_projection(doc_id, kind, ir)
    except Exception as exc:
        row.update({
            "validation_attempted": True,
            "validation_status": "EXCEPTION",
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        })
        return row
    row.update({
        "validation_attempted": True,
        "validation_status": "COMPLETED",
        "validation": validation,
    })
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    source_path = Path(args.source)
    raw = source_path.read_bytes()
    docs, meta = load_lineara_map_v0_4(source_path)
    source_ok = (
        len(raw) == proj.SOURCE_BYTES
        and hashlib.sha256(raw).hexdigest() == proj.SOURCE_SHA
        and meta["loader_id"] == LOADER_ID
    )

    rows: list[dict[str, Any]] = []
    for doc_id, parts in proj.D5.items():
        rows.append(attempt(doc_id, "D5", lambda d=doc_id, p=parts: proj.build_d5(d, docs[d], p)))
    for doc_id in proj.D6:
        rows.append(attempt(doc_id, "D6", lambda d=doc_id: proj.build_d6(d, docs[d])))

    build_exceptions = [r for r in rows if r["build_status"] == "EXCEPTION"]
    validation_exceptions = [r for r in rows if r.get("validation_status") == "EXCEPTION"]
    validation_completed = [r for r in rows if r.get("validation_status") == "COMPLETED"]
    validation_nonpass = [
        r for r in validation_completed
        if not r.get("validation", {}).get("projection_pass", False)
    ]

    if not source_ok:
        status = "SOURCE_IDENTITY_MISMATCH"
    elif build_exceptions:
        status = "BUILD_EXCEPTION_LOCALIZED"
    elif validation_exceptions:
        status = "VALIDATION_EXCEPTION_LOCALIZED"
    elif validation_nonpass:
        status = "VALIDATION_NONPASS_LOCALIZED"
    else:
        status = "DIAGNOSTIC_ALL_7_WOULD_VALIDATE"

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-2C-REAL-IR-PROJECTION-DIAGNOSTIC-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "diagnostic_only_projection_failure_localization",
        "status": status,
        "failed_parent_run": 31812442667,
        "failed_parent_receipt": "data/JANUS-LINEAR-A-R3C-2C-REAL-IR-PROJECTION-FAILED-RUN-RECEIPT-2026-08-14-v0.1.json",
        "frozen_projection_spec_unchanged": "data/JANUS-LINEAR-A-R3C-2C-REAL-IR-PROJECTION-SPEC-2026-08-14-v0.1.json",
        "source": {
            **meta,
            "raw_bytes_rechecked": len(raw),
            "raw_sha256_rechecked": hashlib.sha256(raw).hexdigest(),
            "identity_admitted": source_ok,
        },
        "documents": rows,
        "summary": {
            "documents_expected": 7,
            "documents_attempted": len(rows),
            "build_exception_count": len(build_exceptions),
            "validation_exception_count": len(validation_exceptions),
            "validation_nonpass_count": len(validation_nonpass),
            "validation_completed_count": len(validation_completed),
            "projection_files_written": 0,
        },
        "firewall": {
            "failed_run_result_inherited": False,
            "projection_result_promoted": False,
            "IR_projection_files_persisted": False,
            "frozen_projection_template_modified": False,
            "source_mutated": False,
            "javascript_executed": False,
            "eval_used": False,
        },
        "claim_ceiling": {
            "diagnostic_only": True,
            "real_projection_admitted": False,
            "D5_boundary_kind_resolved": False,
            "D6_semantics_assigned": False,
            "R3B_effect": "NONE",
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "source_ok": source_ok,
        "summary": result["summary"],
        "exceptions": [
            {"document": r["document"], "kind": r["kind"], "type": r.get("exception_type"), "message": r.get("exception_message")}
            for r in rows if r.get("exception_type")
        ],
        "nonpasses": [
            {"document": r["document"], "kind": r["kind"], "validation": r.get("validation")}
            for r in validation_nonpass
        ],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
