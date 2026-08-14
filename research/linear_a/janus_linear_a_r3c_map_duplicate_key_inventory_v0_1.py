#!/usr/bin/env python3
"""Inventory duplicate keys in the first lineara source new Map iterable.

Diagnostic only. The array entries are parsed after frozen boundary/literal
normalization, but no duplicate-key resolution semantics are applied here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_common_v0_1 import normalize_js_literal_subset
from janus_linear_a_r3c_source_loader_v0_3 import extract_first_new_map_array


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def inspect(path: str) -> dict[str, Any]:
    p = Path(path)
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    payload, boundary = extract_first_new_map_array(text)
    normalized, transform = normalize_js_literal_subset(payload)
    entries = json.loads(normalized)
    if not isinstance(entries, list):
        raise ValueError("TOP_LEVEL_NOT_LIST")

    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    malformed = []
    for idx, entry in enumerate(entries):
        if not isinstance(entry, list) or len(entry) != 2 or not isinstance(entry[0], str):
            malformed.append({"index": idx, "type": type(entry).__name__})
            continue
        key, value = entry
        by_key[key].append({
            "index": idx,
            "value_sha256": canonical_hash(value),
            "value_type": type(value).__name__,
            "value_source_name": value.get("name") if isinstance(value, dict) else None,
            "value_names": value.get("names") if isinstance(value, dict) else None,
            "site": value.get("site") if isinstance(value, dict) else None,
            "support": value.get("support") if isinstance(value, dict) else None,
        })

    duplicates = []
    for key in sorted(by_key):
        occ = by_key[key]
        if len(occ) <= 1:
            continue
        hashes = [x["value_sha256"] for x in occ]
        duplicates.append({
            "key": key,
            "occurrence_count": len(occ),
            "occurrences": occ,
            "all_payloads_identical": len(set(hashes)) == 1,
            "distinct_payload_hash_count": len(set(hashes)),
            "first_index": occ[0]["index"],
            "last_index": occ[-1]["index"],
        })

    duplicate_occurrences_beyond_first = sum(d["occurrence_count"] - 1 for d in duplicates)
    return {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "source_entry_count": len(entries),
        "unique_key_count": len(by_key),
        "duplicate_key_count": len(duplicates),
        "duplicate_occurrences_beyond_first": duplicate_occurrences_beyond_first,
        "malformed_entry_count": len(malformed),
        "malformed_entries": malformed,
        "duplicates": duplicates,
        "boundary": boundary,
        "literal_transform": {
            "trailing_comma_removal_count": len(transform["trailing_comma_removals"]),
            "codepoint_escape_replacement_count": len(transform["codepoint_escape_replacements"]),
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--historical", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    h = inspect(args.historical)
    c = inspect(args.current)
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1A-MAP-DUPLICATE-KEY-INVENTORY-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "source_map_semantics_inventory",
        "status": "DUPLICATE_KEY_INVENTORY_COMPLETE",
        "historical": h,
        "current": c,
        "same_duplicate_key_set": [d["key"] for d in h["duplicates"]] == [d["key"] for d in c["duplicates"]],
        "same_duplicate_shape": [
            (d["key"], d["occurrence_count"], d["all_payloads_identical"])
            for d in h["duplicates"]
        ] == [
            (d["key"], d["occurrence_count"], d["all_payloads_identical"])
            for d in c["duplicates"]
        ],
        "semantics_applied": False,
        "safety": {
            "javascript_executed": False,
            "eval_used": False,
            "scientific_metrics_computed": False,
            "duplicate_resolution_performed": False
        },
        "claim_ceiling": {
            "diagnostic_only": True,
            "R3B_effect": "NONE",
            "new_anchor": False,
            "decipherment": False
        }
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
