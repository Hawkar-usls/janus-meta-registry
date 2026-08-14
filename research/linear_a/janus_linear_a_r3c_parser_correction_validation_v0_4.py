#!/usr/bin/env python3
"""Validate JANUS R3C parser/source-loader v0.4.

This is still parser/source-semantics validation only. It proves that exact
source bytes can be converted into a JavaScript Map-compatible effective view
while preserving duplicate provenance. No predecessor scientific metric is run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_common_v0_1 import parser_transform_self_test
from janus_linear_a_r3c_source_loader_v0_3 import boundary_self_test
from janus_linear_a_r3c_source_loader_v0_4 import (
    LOADER_ID,
    MAP_REPLAY_ID,
    canonical_value_sha,
    load_lineara_map_v0_4,
    map_semantics_self_test,
)

HISTORICAL = {
    "bytes": 1609122,
    "sha256": "b7b383b93db55b504eb00c552a8b18c19a588e83bba7ff0ab93ca32277d8bfe2",
}
CURRENT = {
    "bytes": 1609137,
    "sha256": "4da8e1f9693d30880ee505e56541fc189add70605bad88436c44a8e11a57764c",
}
EXPECTED_KH101_EFFECTIVE_SHA = "099b64a36cafc6a068357c6a39f73714f056aee4062f1b72853873814557bde9"
EXPECTED_KH101_PRIOR_SHA = "99645381318ef3ed4d80946510dac6703af1db5ae559507fd1e63e7985796a97"


def inspect(path: str, role: str) -> dict[str, Any]:
    try:
        docs, meta = load_lineara_map_v0_4(path)
    except Exception as exc:
        return {"role": role, "status": "PARSE_FAILED", "exception_type": type(exc).__name__, "exception": str(exc)}
    kh = docs.get("KH101")
    kn_words = docs.get("KNZg57b", {}).get("words", [])
    return {
        "role": role,
        "status": "PARSE_PASS",
        "source": meta,
        "effective_document_count": len(docs),
        "KH101_effective_payload_sha256": canonical_value_sha(kh) if isinstance(kh, dict) else None,
        "KH101_effective_insertion_index": list(docs).index("KH101") if "KH101" in docs else None,
        "KNZg57b_words_contains_U+1076B": isinstance(kn_words, list) and chr(0x1076B) in kn_words,
    }


def source_checks(item: dict[str, Any], expected: dict[str, Any]) -> dict[str, bool]:
    src = item.get("source", {})
    view = src.get("parse_view", {})
    sem = src.get("map_semantics", {})
    dup = sem.get("duplicate_ledger", [])
    d0 = dup[0] if len(dup) == 1 else {}
    return {
        "parse_pass": item.get("status") == "PARSE_PASS",
        "source_bytes_exact": src.get("bytes") == expected["bytes"],
        "source_sha256_exact": src.get("sha256") == expected["sha256"],
        "loader_id": src.get("loader_id") == LOADER_ID,
        "strict_json_parse_success": view.get("strict_json_parse_success") is True,
        "raw_source_entry_count_1722": src.get("source_entry_count") == 1722,
        "effective_document_count_1721": src.get("effective_document_count") == 1721,
        "map_replay_id": sem.get("map_replay_id") == MAP_REPLAY_ID,
        "one_duplicate_replacement": sem.get("duplicate_replacement_count") == 1,
        "duplicate_key_KH101": d0.get("key") == "KH101",
        "duplicate_first_index": d0.get("first_index") == 1234,
        "duplicate_replacement_index": d0.get("replacement_index") == 1698,
        "duplicate_prior_hash": d0.get("prior_effective_payload_sha256") == EXPECTED_KH101_PRIOR_SHA,
        "duplicate_replacement_hash": d0.get("replacement_payload_sha256") == EXPECTED_KH101_EFFECTIVE_SHA,
        "effective_KH101_hash": item.get("KH101_effective_payload_sha256") == EXPECTED_KH101_EFFECTIVE_SHA,
        "effective_insertion_position_preserved": item.get("KH101_effective_insertion_index") == 1234,
        "U+1076B_canary": item.get("KNZg57b_words_contains_U+1076B") is True,
        "raw_layer_preserved": sem.get("raw_source_entry_layer_preserved_by_file_identity") is True,
        "silent_deduplication_false": sem.get("silent_deduplication") is False,
        "source_not_mutated": view.get("source_bytes_mutated") is False,
        "javascript_not_executed": view.get("javascript_executed") is False,
        "eval_not_used": view.get("eval_used") is False,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--historical", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    literal_canary = parser_transform_self_test()
    boundary_canary = boundary_self_test()
    map_canary = map_semantics_self_test()
    h = inspect(args.historical, "BRIAKOS_HISTORICAL_EXACT_SOURCE")
    c = inspect(args.current, "JANUS_CURRENT_FROZEN_MWENGE_SOURCE")
    hchecks = source_checks(h, HISTORICAL)
    cchecks = source_checks(c, CURRENT)

    canaries_pass = all([
        literal_canary.get("unsupported_identifier_failed_closed") is True,
        literal_canary.get("invalid_or_surrogate_codepoint_failed_closed") is True,
        literal_canary.get("doubled_backslash_literal_preserved") is True,
        boundary_canary.get("first_map_only") is True,
        boundary_canary.get("string_containing_fake_terminator_preserved") is True,
        map_canary.get("order_canary_pass") is True,
        map_canary.get("replacement_canary_pass") is True,
        map_canary.get("raw_and_effective_counts_pass") is True,
    ])
    admitted = canaries_pass and all(hchecks.values()) and all(cchecks.values())

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1A-JS-MAP-SEMANTICS-PARSER-VALIDATION-RESULT-2026-08-14-v0.4",
        "version": "v0.4",
        "node_type": "parser_source_semantics_validation_result",
        "status": "PARSER_V0_4_ADMITTED" if admitted else "PARSER_V0_4_NOT_ADMITTED",
        "frozen_spec": "data/JANUS-LINEAR-A-R3C-1A-JS-MAP-DUPLICATE-SEMANTICS-SPEC-2026-08-14-v0.4.json",
        "parent_negative_validations": [
            "data/JANUS-LINEAR-A-R3C-1A-JS-TRAILING-COMMA-PARSER-CORRECTION-VALIDATION-RESULT-2026-08-14-v0.1.json",
            "data/JANUS-LINEAR-A-R3C-1A-JS-LITERAL-SUBSET-PARSER-CORRECTION-VALIDATION-RESULT-2026-08-14-v0.2.json",
            "data/JANUS-LINEAR-A-R3C-1A-MAP-BOUNDARY-PARSER-CORRECTION-VALIDATION-RESULT-2026-08-14-v0.3.json"
        ],
        "self_tests": {
            "literal": literal_canary,
            "boundary": boundary_canary,
            "map_semantics": map_canary,
            "all_pass": canaries_pass
        },
        "historical": h,
        "current": c,
        "checks": {
            "historical": hchecks,
            "current": cchecks,
            "parser_v0_4_admitted": admitted
        },
        "execution_firewall": {
            "scientific_metrics_computed": False,
            "scientific_recovery_run_allowed": admitted,
            "javascript_executed": False,
            "eval_used": False
        },
        "history": {
            "v0_1_negative_preserved": True,
            "v0_2_negative_preserved": True,
            "v0_3_negative_preserved": True,
            "failed_scientific_run_31800907720_reused": False
        },
        "claim_ceiling": {
            "parser_validation_only": True,
            "Briakos_metrics_reproduced": False,
            "logos_D5_D6_replay_completed": False,
            "R3B_effect": "NONE",
            "independent_transcription_replication": False,
            "new_anchor": False,
            "decipherment": False
        }
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": result["checks"]}, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
