#!/usr/bin/env python3
"""JANUS Linear A R3C source loader v0.4.

Adds JavaScript Map.set-compatible duplicate-key semantics to the already
frozen v0.3 source boundary and v0.2 literal normalization stack, while
retaining an explicit raw-entry duplicate provenance ledger.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_common_v0_1 import normalize_js_literal_subset, sha256_bytes
from janus_linear_a_r3c_source_loader_v0_3 import BOUNDARY_ID, extract_first_new_map_array

LOADER_ID = "JANUS-LINEAR-A-R3C-SOURCE-LOADER-v0.4"
MAP_REPLAY_ID = "JANUS-JS-MAP-SET-REPLAY-v0.4"


def canonical_value_sha(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def replay_map_entries(entries: list[Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    effective: dict[str, dict[str, Any]] = {}
    first_index: dict[str, int] = {}
    current_hash: dict[str, str] = {}
    duplicates: list[dict[str, Any]] = []

    for idx, entry in enumerate(entries):
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError(f"LINEARA_INVALID_MAP_ENTRY:{idx}")
        key, value = entry
        if not isinstance(key, str) or not isinstance(value, dict):
            raise ValueError(f"LINEARA_INVALID_MAP_ENTRY_TYPES:{idx}")
        value_hash = canonical_value_sha(value)
        if key in effective:
            duplicates.append({
                "key": key,
                "first_index": first_index[key],
                "replacement_index": idx,
                "prior_effective_payload_sha256": current_hash[key],
                "replacement_payload_sha256": value_hash,
                "effective_insertion_index_unchanged": True,
            })
            effective[key] = value
            current_hash[key] = value_hash
        else:
            first_index[key] = idx
            effective[key] = value
            current_hash[key] = value_hash

    return effective, {
        "map_replay_id": MAP_REPLAY_ID,
        "raw_entry_count": len(entries),
        "effective_key_count": len(effective),
        "duplicate_replacement_count": len(duplicates),
        "duplicate_ledger": duplicates,
        "effective_key_order_first10": list(effective)[:10],
        "effective_key_order_last10": list(effective)[-10:],
        "raw_source_entry_layer_preserved_by_file_identity": True,
        "silent_deduplication": False,
        "first_wins": False,
        "javascript_executed": False,
        "eval_used": False,
    }


def map_semantics_self_test() -> dict[str, Any]:
    entries = [
        ["A", {"v": 1}],
        ["B", {"v": 1}],
        ["A", {"v": 2}],
    ]
    effective, receipt = replay_map_entries(entries)
    assert list(effective) == ["A", "B"]
    assert effective["A"] == {"v": 2}
    assert effective["B"] == {"v": 1}
    assert receipt["raw_entry_count"] == 3
    assert receipt["effective_key_count"] == 2
    assert receipt["duplicate_replacement_count"] == 1
    d = receipt["duplicate_ledger"][0]
    assert d["key"] == "A"
    assert d["first_index"] == 0
    assert d["replacement_index"] == 2
    assert d["effective_insertion_index_unchanged"] is True
    return {
        "map_replay_id": MAP_REPLAY_ID,
        "effective_order": list(effective),
        "A_effective_value": effective["A"],
        "duplicate_ledger": receipt["duplicate_ledger"],
        "order_canary_pass": list(effective) == ["A", "B"],
        "replacement_canary_pass": effective["A"] == {"v": 2},
        "raw_and_effective_counts_pass": receipt["raw_entry_count"] == 3 and receipt["effective_key_count"] == 2,
        "javascript_executed": False,
        "eval_used": False,
    }


def load_lineara_map_v0_4(path: str | Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    p = Path(path)
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    payload, boundary = extract_first_new_map_array(text)
    normalized, transform = normalize_js_literal_subset(payload)
    try:
        entries = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "LINEARA_STRICT_JSON_PARSE_FAILED_AFTER_V0_4_STACK:"
            f"line={exc.lineno}:column={exc.colno}:pos={exc.pos}:message={exc.msg}"
        ) from exc
    if not isinstance(entries, list):
        raise ValueError("LINEARA_MAP_PAYLOAD_NOT_LIST")

    effective, map_receipt = replay_map_entries(entries)
    trailing = transform["trailing_comma_removals"]
    codepoints = transform["codepoint_escape_replacements"]
    meta = {
        "loader_id": LOADER_ID,
        "path": str(p),
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
        "source_entry_count": len(entries),
        "effective_document_count": len(effective),
        "boundary": boundary,
        "parse_view": {
            "transform_id": transform["transform_id"],
            "normalized_payload_characters": len(normalized),
            "normalized_payload_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "trailing_comma_removal_count": len(trailing),
            "trailing_comma_original_positions_within_extracted_payload": [r["original_payload_position"] for r in trailing],
            "codepoint_escape_replacement_count": len(codepoints),
            "codepoint_escape_original_positions_within_extracted_payload": [r["original_payload_position"] for r in codepoints],
            "strict_json_parse_success": True,
            "source_bytes_mutated": False,
            "javascript_executed": False,
            "eval_used": False,
        },
        "map_semantics": map_receipt,
    }
    return effective, meta


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--source")
    args = ap.parse_args()
    if args.self_test:
        print(json.dumps(map_semantics_self_test(), ensure_ascii=False, sort_keys=True))
        return
    if not args.source:
        raise SystemExit("--source required unless --self-test")
    docs, meta = load_lineara_map_v0_4(args.source)
    print(json.dumps({"meta": meta, "effective_document_count": len(docs)}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
