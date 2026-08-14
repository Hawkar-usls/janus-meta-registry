#!/usr/bin/env python3
"""Technical recovery runner for frozen R3C-2C scientific projection v0.1.

This module deliberately reuses every scientific builder/validator from v0.1.
It corrects only output bookkeeping: sealed IR hashes live at
provenance_receipt.ir_sha256, not at the IR top level.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import janus_linear_a_r3c_real_ir_projection_v0_1 as parent

RUNNER_ID = "JANUS-LINEAR-A-R3C-REAL-IR-PROJECTION-RUNNER-v0.1.1"
CORRECTION_RECEIPT = "data/JANUS-LINEAR-A-R3C-2C-RUNNER-OUTPUT-PATH-CORRECTION-2026-08-14-v0.1.1.json"
FAILED_PARENT_RUN = 31812442667
DIAGNOSTIC = "data/JANUS-LINEAR-A-R3C-2C-REAL-IR-PROJECTION-DIAGNOSTIC-RESULT-2026-08-14-v0.1.json"


def sealed_hash(ir: dict) -> str:
    value = ir.get("provenance_receipt", {}).get("ir_sha256")
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("SEALED_IR_HASH_MISSING_FROM_PROVENANCE_RECEIPT")
    return value


def validation_with_canonical_hash(doc_id: str, kind: str, ir: dict) -> dict:
    row = parent.validate_projection(doc_id, kind, ir)
    row["ir_sha256"] = sealed_hash(ir)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--result", required=True)
    args = ap.parse_args()

    docs, source_meta = parent.load_lineara_map_v0_4(args.source)
    source_ok = (
        source_meta["bytes"] == parent.SOURCE_BYTES
        and source_meta["sha256"] == parent.SOURCE_SHA
        and source_meta["loader_id"] == parent.LOADER_ID
    )
    if not source_ok:
        raise SystemExit("EXACT_CURRENT_SOURCE_IDENTITY_NOT_ADMITTED")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    audits, validations, outputs = [], [], []

    for doc_id, parts in parent.D5.items():
        ir, audit = parent.build_d5(doc_id, docs[doc_id], parts)
        validation = validation_with_canonical_hash(doc_id, "D5", ir)
        path = out_dir / f"JANUS-LINEAR-A-R3C-2C-D5-{doc_id}-IR-v0.1.json"
        path.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raw = path.read_bytes()
        outputs.append({
            "document": doc_id,
            "kind": "D5",
            "path": str(path),
            "file_sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "ir_sha256": sealed_hash(ir),
        })
        audits.append({"kind": "D5", **audit})
        validations.append(validation)

    for doc_id in parent.D6:
        ir, audit = parent.build_d6(doc_id, docs[doc_id])
        validation = validation_with_canonical_hash(doc_id, "D6", ir)
        path = out_dir / f"JANUS-LINEAR-A-R3C-2C-D6-{doc_id.replace('+','_PLUS_')}-IR-v0.1.json"
        path.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raw = path.read_bytes()
        outputs.append({
            "document": doc_id,
            "kind": "D6",
            "path": str(path),
            "file_sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "ir_sha256": sealed_hash(ir),
        })
        audits.append({"kind": "D6", **audit})
        validations.append(validation)

    passed = sum(1 for row in validations if row["projection_pass"])
    status = "REAL_7_DOCUMENT_PROJECTION_PASS" if passed == 7 else ("PARTIAL_PROJECTION" if passed else "PROJECTION_FAILED")
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-2C-REAL-IR-PROJECTION-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "real_source_ir_projection_result",
        "status": status,
        "frozen_spec": "data/JANUS-LINEAR-A-R3C-2C-REAL-IR-PROJECTION-SPEC-2026-08-14-v0.1.json",
        "recovery": {
            "runner_id": RUNNER_ID,
            "technical_correction_receipt": CORRECTION_RECEIPT,
            "failed_parent_run": FAILED_PARENT_RUN,
            "diagnostic": DIAGNOSTIC,
            "scientific_projection_template_modified": False,
            "validator_semantics_modified": False,
            "hash_algorithm_modified": False,
        },
        "source": source_meta,
        "source_identity_admitted": source_ok,
        "projection_scope": "MINIMAL_SOURCE_SPAN_NOT_FULL_DOCUMENT_TRANSCRIPTION",
        "outputs": outputs,
        "source_audits": audits,
        "validations": validations,
        "summary": {
            "documents_expected": 7,
            "documents_projected": len(outputs),
            "projection_pass_count": passed,
            "D5_expected": 4,
            "D5_pass": sum(1 for v in validations if v["projection_kind"] == "D5" and v["projection_pass"]),
            "D6_expected": 3,
            "D6_pass": sum(1 for v in validations if v["projection_kind"] == "D6" and v["projection_pass"]),
            "all_ir_hashes_present": all(isinstance(o["ir_sha256"], str) and len(o["ir_sha256"]) == 64 for o in outputs),
            "all_ir_hashes_unique": len({o["ir_sha256"] for o in outputs}) == len(outputs),
            "source_groups_destructively_merged": False,
            "D5_boundary_kind_promoted": False,
            "D6_semantic_authority_granted": False,
        },
        "claim_ceiling": {
            "technical_source_span_projection_only": True,
            "full_document_transcription_claimed": False,
            "D5_boundary_kind_resolved": False,
            "D5_linguistic_wordhood_proved": False,
            "D6_A319_semantics_assigned": False,
            "JANUS_independent_D5_D6_discovery": False,
            "R3B_effect": "NONE",
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.result).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "passed": passed, "hashes_present": result["summary"]["all_ir_hashes_present"]}, sort_keys=True))


if __name__ == "__main__":
    main()
