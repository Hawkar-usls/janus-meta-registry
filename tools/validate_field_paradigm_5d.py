#!/usr/bin/env python3
"""Read-only integrity check for JANUS FIELD PARADIGM 5D source-bound spiral.

This validates JSON syntax, source/pointer referential integrity, use of all
five canonical dimensions, and claim-status firewalls. It does NOT validate
the truth of scientific assertions or establish a P-vs-NP proof.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "registry" / "p_vs_np"
RAW = FOLDER / "sources" / "JANUS_FIELD_PARADIGM_USER_SUBMISSION_2026-10-28_v4.5.0-ALPHA_TRUNCATED.txt"
SOURCE = FOLDER / "JANUS_FIELD_PARADIGM_RECONSTRUCTED_SOURCE_2026-10-28_v4.5.0-ALPHA.json"
POINTERS = FOLDER / "JANUS_FIELD_PARADIGM_5D_JSON_POINTER_COVERAGE_2026-10-28_v1.0.json"
SPIRAL = FOLDER / "JANUS_FIELD_PARADIGM_TRUE_5D_TRANCEPTION_REVERSE_SPIRAL_2026-10-28_v5.0.json"


def json_pointer(root, pointer: str):
    assert pointer.startswith("/") and pointer != "/"
    value = root
    for segment in pointer.split("/")[1:]:
        segment = segment.replace("~1", "/").replace("~0", "~")
        value = value[int(segment)] if isinstance(value, list) else value[segment]
    return value


def verify():
    raw = RAW.read_bytes()
    source = json.loads(SOURCE.read_text(encoding="utf8"))
    pointers = json.loads(POINTERS.read_text(encoding="utf8"))
    spiral = json.loads(SPIRAL.read_text(encoding="utf8"))
    raw_sha = hashlib.sha256(raw).hexdigest()
    assert raw_sha == "f0009476e803558146d623a8440769c11fee8c064c5520de9c7533d777c5d286"
    assert source["janus_5d_ingestion_metadata"]["source_normalized_lf_sha256"] == raw_sha
    assert spiral["source"]["normalized_lf_sha256"] == raw_sha
    assert source["part_VIII_registry_data"]["revision_history"][-1]["changes"] is None
    assert len(pointers["nodes"]) == spiral["source"]["leaf_nodes"] == 1294
    assert len(spiral["INLINE_5D_BRANCHES_IN_LOGICAL_ANCHOR_ORDER"]) == 22
    names = set()
    for leaf in pointers["nodes"]:
        assert leaf["pointer"] not in names
        names.add(leaf["pointer"])
        val = json_pointer(source, leaf["pointer"])
        kind = "missing_null" if val is None else type(val).__name__
        assert kind == leaf["kind"] or (kind == "str" and leaf["kind"] == "string") or (
            kind == "int" and leaf["kind"] == "number"
        ) or (kind == "bool" and leaf["kind"] == "boolean")
    allowed = {"RETAIN", "SPLIT", "WEAKEN", "PROMOTE", "REPLACE", "KEEP_PARALLEL"}
    required = [
        "D1_FORWARD_BACK", "D2_LEFT_RIGHT", "D3_ASCEND_DIVE",
        "D4_EXPAND_CONTRACT", "D5_CLAIM_SOURCE"
    ]
    for item in spiral["INLINE_5D_BRANCHES_IN_LOGICAL_ANCHOR_ORDER"]:
        json_pointer(source, item["anchor_json_pointer"])
        assert item["RETURN_TO_PARENT_AS"] in allowed
        for key in required:
            assert isinstance(item[key], str) and len(item[key]) > 20
        assert len(item["replay_affected_downstream"]) >= 1
        for ptr in item["replay_affected_downstream"]:
            json_pointer(source, ptr)
        assert item["id"]
    assert spiral["EVIDENCE_AND_FIREWALL"]["CLAIM_CEILING"]["P_VS_NP"] == "OPEN"
    assert spiral["EVIDENCE_AND_FIREWALL"]["CLAIM_CEILING"]["UNIVERSAL_SOLVER"] == "NOT_CONSTRUCTED"
    assert spiral["TRANCEPTION_REVERSE"]["canonical"].startswith("JANUS 5D METHOD")
    assert len(spiral["PATH_HISTORY_SPIRAL"]) >= 3
    assert spiral["PATH_HISTORY_SPIRAL"][-1]["RETURN"].startswith("PLATEAU")
    assert spiral["HRaiN_STRUCTURE"]["runtime_executed"] is False
    assert spiral["iNaiHR_ASSOCIATIONS"]["runtime_executed"] is False
    return {
        "result": "PASS_INTEGRITY_ONLY_NOT_SCIENTIFIC_VERIFICATION",
        "source_lf_sha256": raw_sha,
        "indexed_leaf_nodes": len(pointers["nodes"]),
        "source_anchored_5d_micro_passes": len(spiral["INLINE_5D_BRANCHES_IN_LOGICAL_ANCHOR_ORDER"]),
        "scientific_ceiling": "P_VS_NP_OPEN",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True, indent=2))
