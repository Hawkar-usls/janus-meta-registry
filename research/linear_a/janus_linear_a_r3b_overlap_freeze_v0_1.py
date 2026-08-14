#!/usr/bin/env python3
"""JANUS Linear A R3B-1 alternate-editorial overlap freeze v0.1.

This gate is intentionally content-blind. It binds an acquired alternate editorial source to the
existing 686-document identity universe, rejects transcription-bearing inventory fields, records
collisions/unresolved IDs, and deterministically reserves an adapter-validation pool while sealing
all remaining overlap as a scientific holdout.

It does NOT parse Linear A signs, read transcription strings, score candidates, or establish
external replication.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SPEC_PATH = "data/JANUS-LINEAR-A-R3B-1-ALTERNATE-EDITORIAL-OVERLAP-FREEZE-SPEC-2026-08-14-v0.1.json"
SPEC_COMMIT = "56067bd6d3e04eab63fe0666aeeab0290b0e0d74"
RECEIPT_CONTRACT_PATH = "data/JANUS-LINEAR-A-R3B-0-ACQUISITION-RECEIPT-MACHINE-CONTRACT-2026-08-14-v0.1.json"
RECEIPT_CONTRACT_COMMIT = "f8829d55e78aba89f8f291a559d468c70bccac3d"
REFERENCE_BINDING_PATH = "data/JANUS-LINEAR-A-R3B-1-REFERENCE-IDENTITY-UNIVERSE-BINDING-2026-08-14-v0.1.json"
REFERENCE_BINDING_COMMIT = "b76fd6e161fd3e5041c2ed1ab2220449bc1069a0"
REFERENCE_BRIDGE_PATH = "data/JANUS-LINEAR-A-SIGLA-DOCUMENT-IDENTITY-BRIDGE-RESULT-2026-08-14-v0.1.json"
REFERENCE_BRIDGE_COMMIT = "9f09b84856324ecd94ea48356fd8d880a6b95256"
NAMESPACE = "JANUS-R3B1-ALTERNATE-EDITORIAL-OVERLAP-v0.1"
MIN_OVERLAP = 10

ADMITTED_RECEIPT_STATUSES = {
    "ACQUIRED_BYTES_FROZEN_PROVENANCE_PENDING",
    "ACQUIRED_BYTES_FROZEN_L0_DERIVATIVE",
    "ACQUIRED_BYTES_FROZEN_L1",
    "ACQUIRED_BYTES_FROZEN_L2",
    "ACQUIRED_BYTES_FROZEN_L3_CANDIDATE_PENDING_OVERLAP_AUDIT",
}

FORBIDDEN_FIELD_FRAGMENTS = (
    "transcription",
    "reading",
    "transliteration",
    "sequence",
    "sign_id",
    "signs",
    "word",
    "token",
    "gloss",
    "meaning",
    "candidate",
    "ku-ro",
    "si",
)

ALLOWED_DOCUMENT_FIELDS = {
    "source_document_id",
    "bridge_key",
    "bridge_evidence",
    "site",
    "artifact_class",
    "surface_labels",
    "page_refs",
    "catalogue_id",
    "bibliographic_locator",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_acquisition_receipt(receipt: dict, contract: dict) -> tuple[list[str], str | None]:
    errors: list[str] = []
    for field in contract["required_top_level"]:
        if field not in receipt:
            errors.append(f"RECEIPT_MISSING_TOP_LEVEL:{field}")
    status = receipt.get("status")
    if status not in ADMITTED_RECEIPT_STATUSES:
        errors.append(f"RECEIPT_STATUS_NOT_ADMITTED:{status}")

    identity = receipt.get("source_identity")
    if not isinstance(identity, dict):
        errors.append("RECEIPT_SOURCE_IDENTITY_NOT_OBJECT")
        identity = {}
    for field in contract["source_identity_required"]:
        if field not in identity:
            errors.append(f"RECEIPT_SOURCE_IDENTITY_MISSING:{field}")

    acquisition = receipt.get("acquisition")
    if not isinstance(acquisition, dict):
        errors.append("RECEIPT_ACQUISITION_NOT_OBJECT")
        acquisition = {}
    for field in contract["acquisition_required"]:
        if field not in acquisition:
            errors.append(f"RECEIPT_ACQUISITION_MISSING:{field}")
    if acquisition.get("route_type") not in set(contract["allowed_route_types"]):
        errors.append(f"RECEIPT_ROUTE_TYPE_INVALID:{acquisition.get('route_type')}")

    files = receipt.get("acquired_files")
    if not isinstance(files, list) or not files:
        errors.append("RECEIPT_ACQUIRED_FILES_EMPTY_OR_INVALID")
        files = []
    seen_ids: set[str] = set()
    seen_sha: set[str] = set()
    binding_rows = []
    for i, row in enumerate(files):
        if not isinstance(row, dict):
            errors.append(f"RECEIPT_FILE[{i}]_NOT_OBJECT")
            continue
        for field in contract["file_required"]:
            if field not in row:
                errors.append(f"RECEIPT_FILE[{i}]_MISSING:{field}")
        fid = row.get("file_id")
        if not isinstance(fid, str) or not fid:
            errors.append(f"RECEIPT_FILE[{i}]_INVALID_FILE_ID")
        elif fid in seen_ids:
            errors.append(f"RECEIPT_DUPLICATE_FILE_ID:{fid}")
        else:
            seen_ids.add(fid)
        sha = row.get("sha256")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            errors.append(f"RECEIPT_FILE[{i}]_INVALID_SHA256")
        elif sha in seen_sha:
            errors.append(f"RECEIPT_DUPLICATE_FILE_SHA256:{sha}")
        else:
            seen_sha.add(sha)
        size = row.get("bytes")
        if not isinstance(size, int) or size < 0:
            errors.append(f"RECEIPT_FILE[{i}]_INVALID_BYTES")
        binding_rows.append({
            "file_id": fid,
            "sha256": sha,
            "bytes": size,
            "original_received_bytes": row.get("original_received_bytes"),
        })

    coverage = receipt.get("coverage")
    if not isinstance(coverage, dict):
        errors.append("RECEIPT_COVERAGE_NOT_OBJECT")
        coverage = {}
    for field in contract["coverage_required"]:
        if field not in coverage:
            errors.append(f"RECEIPT_COVERAGE_MISSING:{field}")

    provenance = receipt.get("provenance_classification")
    if not isinstance(provenance, dict):
        errors.append("RECEIPT_PROVENANCE_CLASSIFICATION_NOT_OBJECT")
        provenance = {}
    for field in contract["provenance_classification_required"]:
        if field not in provenance:
            errors.append(f"RECEIPT_PROVENANCE_MISSING:{field}")

    usage = receipt.get("usage_constraints")
    if not isinstance(usage, dict):
        errors.append("RECEIPT_USAGE_CONSTRAINTS_NOT_OBJECT")
        usage = {}
    for field in contract["usage_constraints_required"]:
        if field not in usage:
            errors.append(f"RECEIPT_USAGE_MISSING:{field}")

    if receipt.get("content_access_state") != contract["content_access_state_required_value"]:
        errors.append("RECEIPT_CONTENT_ACCESS_STATE_FAIL")

    dataset_binding = None
    if not errors:
        binding_rows.sort(key=lambda x: x["file_id"])
        dataset_binding = sha256_json(binding_rows)
    return errors, dataset_binding


def audit_inventory_content_firewall(inventory: dict) -> list[str]:
    violations: list[str] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                low = str(key).lower()
                for frag in FORBIDDEN_FIELD_FRAGMENTS:
                    if frag in low:
                        violations.append(f"{path}.{key}:FORBIDDEN_FIELD_FRAGMENT:{frag}")
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for i, child in enumerate(value):
                walk(child, f"{path}[{i}]")

    walk(inventory, "inventory")
    return sorted(set(violations))


def validate_identity_inventory(inventory: dict, receipt: dict) -> list[str]:
    errors: list[str] = []
    for field in ("source_id", "edition_id", "content_firewall", "documents"):
        if field not in inventory:
            errors.append(f"INVENTORY_MISSING_TOP_LEVEL:{field}")
    if inventory.get("content_firewall") != "TRANSCRIPTION_CONTENT_NOT_INSPECTED_OR_INCLUDED":
        errors.append("INVENTORY_CONTENT_FIREWALL_VALUE_FAIL")
    identity = receipt.get("source_identity", {})
    if inventory.get("source_id") != identity.get("source_id"):
        errors.append("INVENTORY_SOURCE_ID_MISMATCH")
    if inventory.get("edition_id") != identity.get("edition_id"):
        errors.append("INVENTORY_EDITION_ID_MISMATCH")
    documents = inventory.get("documents")
    if not isinstance(documents, list):
        errors.append("INVENTORY_DOCUMENTS_NOT_LIST")
        return errors
    seen_source_ids: set[str] = set()
    for i, row in enumerate(documents):
        if not isinstance(row, dict):
            errors.append(f"INVENTORY_DOCUMENT[{i}]_NOT_OBJECT")
            continue
        unknown = set(row) - ALLOWED_DOCUMENT_FIELDS
        if unknown:
            errors.append(f"INVENTORY_DOCUMENT[{i}]_UNKNOWN_FIELDS:{sorted(unknown)}")
        sid = row.get("source_document_id")
        if not isinstance(sid, str) or not sid:
            errors.append(f"INVENTORY_DOCUMENT[{i}]_INVALID_SOURCE_DOCUMENT_ID")
        elif sid in seen_source_ids:
            errors.append(f"INVENTORY_DUPLICATE_SOURCE_DOCUMENT_ID:{sid}")
        else:
            seen_source_ids.add(sid)
    errors.extend(audit_inventory_content_firewall(inventory))
    return errors


def load_reference_universe(reference_bridge_path: str | Path, binding: dict) -> dict[str, dict]:
    bridge = _load(reference_bridge_path)
    if bridge.get("status") != "DOCUMENT_IDENTITY_BRIDGE_EXECUTED_SUCCESS":
        raise ValueError("REFERENCE_BRIDGE_STATUS_FAIL")
    rows = bridge.get("bridge", {}).get("matched_pairs")
    if not isinstance(rows, list):
        raise ValueError("REFERENCE_BRIDGE_MATCHED_PAIRS_NOT_LIST")
    expected = binding["source_identity_bridge"]["expected_collision_free_pair_count"]
    if len(rows) != expected:
        raise ValueError(f"REFERENCE_BRIDGE_COUNT_FAIL:{len(rows)}:{expected}")
    out: dict[str, dict] = {}
    for row in rows:
        projected = {k: row.get(k) for k in ("bridge_key", "sigla_id", "mwenge_id")}
        key = projected["bridge_key"]
        if not isinstance(key, str) or not key:
            raise ValueError("REFERENCE_BRIDGE_INVALID_KEY")
        if key in out:
            raise ValueError(f"REFERENCE_BRIDGE_DUPLICATE_KEY:{key}")
        out[key] = projected
    return out


def selection_hash(dataset_binding: str, source_id: str, edition_id: str, bridge_key: str) -> str:
    text = f"{NAMESPACE}|{dataset_binding}|{source_id}|{edition_id}|{bridge_key}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def freeze_overlap(receipt: dict, inventory: dict, reference: dict[str, dict], *, dataset_binding: str) -> dict:
    by_key: dict[str, list[dict]] = defaultdict(list)
    unresolved = []
    nonoverlap = []
    for row in inventory["documents"]:
        key = row.get("bridge_key")
        if not isinstance(key, str) or not key:
            unresolved.append({
                "source_document_id": row.get("source_document_id"),
                "reason": "MISSING_OR_UNRESOLVED_BRIDGE_KEY",
            })
            continue
        by_key[key].append(row)

    collisions = []
    collision_keys: set[str] = set()
    for key, rows in sorted(by_key.items()):
        if len(rows) > 1:
            collision_keys.add(key)
            collisions.append({
                "bridge_key": key,
                "source_document_ids": sorted(r["source_document_id"] for r in rows),
                "reason": "MULTIPLE_ALTERNATE_SOURCE_DOCUMENTS_SHARE_BRIDGE_KEY",
            })

    overlap = []
    for key, rows in sorted(by_key.items()):
        if key in collision_keys:
            continue
        row = rows[0]
        if key not in reference:
            nonoverlap.append({
                "source_document_id": row["source_document_id"],
                "bridge_key": key,
                "reason": "NOT_IN_FROZEN_JANUS_REFERENCE_UNIVERSE",
            })
            continue
        score = selection_hash(
            dataset_binding,
            receipt["source_identity"]["source_id"],
            receipt["source_identity"]["edition_id"],
            key,
        )
        overlap.append({
            "source_document_id": row["source_document_id"],
            "bridge_key": key,
            "selection_hash": score,
            "bridge_evidence": row.get("bridge_evidence"),
            "site": row.get("site"),
            "artifact_class": row.get("artifact_class"),
            "surface_labels": row.get("surface_labels"),
            "page_refs": row.get("page_refs"),
            "catalogue_id": row.get("catalogue_id"),
            "bibliographic_locator": row.get("bibliographic_locator"),
            "reference_identity": reference[key],
        })

    overlap.sort(key=lambda x: (x["selection_hash"], x["bridge_key"], x["source_document_id"]))
    n = len(overlap)
    if n < MIN_OVERLAP:
        return {
            "status": "BLOCKED_OVERLAP_BELOW_TECHNICAL_MINIMUM",
            "collision_free_overlap_count": n,
            "minimum_required": MIN_OVERLAP,
            "collisions": collisions,
            "unresolved": unresolved,
            "nonoverlap": nonoverlap,
            "ordered_overlap": overlap,
            "adapter_validation": [],
            "scientific_holdout": [],
        }

    validation_count = max(3, math.floor(0.20 * n))
    adapter_validation = overlap[:validation_count]
    scientific_holdout = overlap[validation_count:]
    for row in adapter_validation:
        row["partition"] = "ADAPTER_VALIDATION"
    for row in scientific_holdout:
        row["partition"] = "SCIENTIFIC_HOLDOUT"

    return {
        "status": "OVERLAP_FROZEN_READY_FOR_R3B_2_ADAPTER_SPEC",
        "collision_free_overlap_count": n,
        "minimum_required": MIN_OVERLAP,
        "adapter_validation_count": len(adapter_validation),
        "scientific_holdout_count": len(scientific_holdout),
        "collisions": collisions,
        "unresolved": unresolved,
        "nonoverlap": nonoverlap,
        "ordered_overlap": overlap,
        "adapter_validation": adapter_validation,
        "scientific_holdout": scientific_holdout,
    }


def execute(receipt_path: str, inventory_path: str, reference_path: str, out_path: str) -> dict:
    spec = _load(SPEC_PATH)
    contract = _load(RECEIPT_CONTRACT_PATH)
    binding = _load(REFERENCE_BINDING_PATH)
    receipt = _load(receipt_path)
    inventory = _load(inventory_path)

    receipt_errors, dataset_binding = validate_acquisition_receipt(receipt, contract)
    inventory_errors = validate_identity_inventory(inventory, receipt)
    firewall_violations = audit_inventory_content_firewall(inventory)

    base = {
        "artifact_uuid": "JANUS-LINEAR-A-R3B-1-ALTERNATE-EDITORIAL-OVERLAP-FREEZE-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "title": "JANUS Linear A R3B-1 alternate editorial overlap freeze result",
        "node_type": "precontent_overlap_freeze_result",
        "scientific_claim_bearing": False,
        "frozen_spec": {"path": SPEC_PATH, "commit": SPEC_COMMIT},
        "receipt_contract": {"path": RECEIPT_CONTRACT_PATH, "commit": RECEIPT_CONTRACT_COMMIT},
        "reference_binding": {"path": REFERENCE_BINDING_PATH, "commit": REFERENCE_BINDING_COMMIT},
        "reference_bridge": {"path": str(reference_path), "commit": REFERENCE_BRIDGE_COMMIT},
        "source": receipt.get("source_identity"),
        "acquired_file_sha256": sorted(x.get("sha256") for x in receipt.get("acquired_files", []) if isinstance(x, dict) and x.get("sha256")),
        "dataset_binding_sha256": dataset_binding,
        "identity_inventory_sha256": sha256_json(inventory),
        "content_firewall": {
            "required_value_present": inventory.get("content_firewall") == "TRANSCRIPTION_CONTENT_NOT_INSPECTED_OR_INCLUDED",
            "forbidden_field_violation_count": len(firewall_violations),
            "violations": firewall_violations,
            "transcription_content_loaded_by_runner": False,
            "mwenge_or_sigla_transcription_loaded_by_runner": False,
        },
    }

    if receipt_errors:
        result = {
            **base,
            "status": "BLOCKED_NO_ACQUIRED_SOURCE_RECEIPT",
            "receipt_validation_errors": receipt_errors,
            "inventory_validation_errors": inventory_errors,
            "overlap": None,
        }
    elif inventory_errors:
        state = "BLOCKED_CONTENT_FIREWALL_VIOLATION" if firewall_violations or inventory.get("content_firewall") != "TRANSCRIPTION_CONTENT_NOT_INSPECTED_OR_INCLUDED" else "BLOCKED_IDENTITY_INVENTORY_MISSING"
        result = {
            **base,
            "status": state,
            "receipt_validation_errors": [],
            "inventory_validation_errors": inventory_errors,
            "overlap": None,
        }
    else:
        reference = load_reference_universe(reference_path, binding)
        frozen = freeze_overlap(receipt, inventory, reference, dataset_binding=dataset_binding or "")
        result = {
            **base,
            "status": frozen["status"],
            "receipt_validation_errors": [],
            "inventory_validation_errors": [],
            "reference_universe_count": len(reference),
            "overlap": frozen,
        }

    ready = result["status"] == "OVERLAP_FROZEN_READY_FOR_R3B_2_ADAPTER_SPEC"
    result["epistemic_gate"] = {
        "R3B_1_overlap_frozen": ready,
        "R3B_2_adapter_spec_admitted": ready,
        "alternate_editorial_transcription_content_inspected": False,
        "external_transcription_replication_established": False,
        "new_anchor_established": False,
        "decipherment_established": False,
        "promotion": "NO_PROMOTION",
    }
    result["required_next"] = (
        [
            "Freeze R3B-2 source-specific notation/tokenization/layout grammar using documentation and only the ADAPTER_VALIDATION pool.",
            "Implement the acquired source adapter into JANUS-LINEAR-TRANSCRIPTION-IR-v1.0.",
            "Keep SCIENTIFIC_HOLDOUT inaccessible during adapter development and parser correction.",
        ]
        if ready
        else [
            "Do not inspect alternate-source transcription content to repair this gate.",
            "Satisfy the exact acquisition/identity-only prerequisites or preserve the blocked state.",
        ]
    )
    result["claim_ceiling"] = {
        "overlap_frozen": ready,
        "alternate_editorial_adapter_validated": False,
        "external_transcription_replication_established": False,
        "new_anchor_established": False,
        "decipherment_established": False,
        "promotion": "BLOCKED",
    }
    Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def readiness(registry_root: str | Path, out_path: str) -> dict:
    root = Path(registry_root)
    candidates = []
    for path in sorted((root / "data").glob("JANUS-LINEAR-A-R3B-0-SOURCE-ACQUISITION-RECEIPT-*.json")):
        try:
            d = _load(path)
        except Exception:
            continue
        if d.get("status") in ADMITTED_RECEIPT_STATUSES:
            candidates.append({"path": str(path.relative_to(root)), "status": d.get("status"), "source_id": d.get("source_identity", {}).get("source_id")})
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3B-1-READINESS-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "title": "JANUS Linear A R3B-1 readiness result",
        "node_type": "precontent_gate_readiness_result",
        "status": "BLOCKED_NO_ACQUIRED_SOURCE_RECEIPT" if not candidates else "ACQUIRED_SOURCE_RECEIPT_PRESENT_R3B1_INPUT_INVENTORY_REQUIRED",
        "scientific_claim_bearing": False,
        "frozen_spec": {"path": SPEC_PATH, "commit": SPEC_COMMIT},
        "admitted_acquisition_receipts": candidates,
        "admitted_acquisition_receipt_count": len(candidates),
        "transcription_content_inspected": False,
        "overlap_documents_frozen": False,
        "required_next": (
            "Acquire and freeze exact RILA-S1, CTLA, TMT or other alternate-editorial source bytes under R3B-0."
            if not candidates
            else "Create an identity-only document inventory under the frozen content firewall and execute R3B-1."
        ),
        "claim_ceiling": {
            "R3B_1_spec_frozen": True,
            "source_bytes_acquired": bool(candidates),
            "overlap_frozen": False,
            "external_transcription_replication_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "BLOCKED",
        },
    }
    Path(out_path).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def self_test() -> dict:
    contract = _load(RECEIPT_CONTRACT_PATH)
    reference = {f"D{i:02d}": {"bridge_key": f"D{i:02d}", "sigla_id": f"S{i:02d}", "mwenge_id": f"M{i:02d}"} for i in range(20)}
    receipt = {
        "artifact_uuid": "TEST-RECEIPT",
        "version": "v0",
        "status": "ACQUIRED_BYTES_FROZEN_L2",
        "source_identity": {
            "source_id": "TEST-L2",
            "canonical_title": "Fixture",
            "edition_id": "fixture-edition",
            "publication_year": 2000,
            "editors": ["Fixture"],
            "publisher_or_repository": "Fixture",
        },
        "acquisition": {
            "timestamp": "2026-08-14T15:00:00+03:00",
            "route_type": "library_scan",
            "source_locator": "fixture://source",
            "access_class": "test",
        },
        "acquired_files": [{
            "file_id": "F1",
            "filename": "fixture.pdf",
            "sha256": hashlib.sha256(b"fixture").hexdigest(),
            "bytes": 7,
            "mime_type": "application/pdf",
            "original_received_bytes": True,
            "page_count": 10,
        }],
        "coverage": {
            "complete_or_partial": "complete",
            "page_ranges": ["1-10"],
            "transcription_pages_present": True,
            "apparatus_or_uncertainty_notes_present": True,
            "sign_index_or_concordance_present": True,
            "photographs_or_drawings_present": False,
        },
        "provenance_classification": {
            "independence_level": "L2_ALTERNATE_EDITORIAL_CORPUS_SHARED_PRIMARY_TRADITION",
            "relationship_to_GORILA": "fixture",
            "relationship_to_Younger_or_mwenge": "none",
            "relationship_to_SigLA": "none",
            "known_import_or_copy_dependencies": [],
            "classification_evidence": ["fixture"],
        },
        "usage_constraints": {
            "license_or_access_terms": "test",
            "source_bytes_redistributable": False,
            "derived_hashes_and_annotations_may_be_committed": True,
        },
        "content_access_state": "CONTENT_NOT_USED_FOR_JANUS_CANDIDATE_COMPARISON_BEFORE_R3B1_FREEZE",
        "claim_ceiling": {},
    }
    inventory = {
        "source_id": "TEST-L2",
        "edition_id": "fixture-edition",
        "content_firewall": "TRANSCRIPTION_CONTENT_NOT_INSPECTED_OR_INCLUDED",
        "documents": [
            {"source_document_id": f"ALT-{i:02d}", "bridge_key": f"D{i:02d}", "bridge_evidence": "catalogue-id"}
            for i in range(20)
        ],
    }
    receipt_errors, binding = validate_acquisition_receipt(receipt, contract)
    assert not receipt_errors, receipt_errors
    assert binding
    inventory_errors = validate_identity_inventory(inventory, receipt)
    assert not inventory_errors, inventory_errors
    frozen = freeze_overlap(receipt, inventory, reference, dataset_binding=binding)
    assert frozen["status"] == "OVERLAP_FROZEN_READY_FOR_R3B_2_ADAPTER_SPEC"
    assert frozen["collision_free_overlap_count"] == 20
    assert frozen["adapter_validation_count"] == 4
    assert frozen["scientific_holdout_count"] == 16
    assert set(x["bridge_key"] for x in frozen["adapter_validation"]).isdisjoint(set(x["bridge_key"] for x in frozen["scientific_holdout"]))

    poisoned = copy.deepcopy(inventory)
    poisoned["documents"][0]["transcription"] = "AB01-AB02"
    poison_errors = validate_identity_inventory(poisoned, receipt)
    assert any("FORBIDDEN_FIELD_FRAGMENT:transcription" in x for x in poison_errors), poison_errors

    collision = copy.deepcopy(inventory)
    collision["documents"][1]["bridge_key"] = collision["documents"][0]["bridge_key"]
    collision_errors = validate_identity_inventory(collision, receipt)
    assert not collision_errors, collision_errors
    frozen_collision = freeze_overlap(receipt, collision, reference, dataset_binding=binding)
    assert frozen_collision["collision_free_overlap_count"] == 18
    assert len(frozen_collision["collisions"]) == 1

    return {
        "runner": "JANUS-R3B1-OVERLAP-FREEZE-v0.1",
        "receipt_contract_validated": True,
        "identity_content_firewall_rejects_transcription": True,
        "deterministic_partition_20_documents": {"adapter_validation": 4, "scientific_holdout": 16},
        "collision_exclusion_preserved": True,
        "scientific_content_used": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_exec = sub.add_parser("execute")
    p_exec.add_argument("--receipt", required=True)
    p_exec.add_argument("--inventory", required=True)
    p_exec.add_argument("--reference", default=REFERENCE_BRIDGE_PATH)
    p_exec.add_argument("--out", required=True)

    p_ready = sub.add_parser("readiness")
    p_ready.add_argument("--registry-root", default=".")
    p_ready.add_argument("--out", required=True)

    sub.add_parser("self-test")
    args = ap.parse_args()
    if args.cmd == "execute":
        result = execute(args.receipt, args.inventory, args.reference, args.out)
        print(json.dumps({"status": result["status"], "overlap_frozen": result["claim_ceiling"]["overlap_frozen"]}, sort_keys=True))
        raise SystemExit(0 if result["status"] in {"OVERLAP_FROZEN_READY_FOR_R3B_2_ADAPTER_SPEC", "BLOCKED_OVERLAP_BELOW_TECHNICAL_MINIMUM"} else 2)
    if args.cmd == "readiness":
        result = readiness(args.registry_root, args.out)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return
    print(json.dumps(self_test(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
