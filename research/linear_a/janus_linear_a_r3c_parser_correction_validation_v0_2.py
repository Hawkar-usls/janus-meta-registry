#!/usr/bin/env python3
"""Validate frozen JANUS JS literal-subset parser correction v0.2.

Parser-only gate. No Briakos metrics and no logos scientific conformance tests
are evaluated here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_common_v0_1 import (
    PARSE_TRANSFORM_ID,
    load_lineara_map,
    parser_transform_self_test,
)

HISTORICAL_SHA = "b7b383b93db55b504eb00c552a8b18c19a588e83bba7ff0ab93ca32277d8bfe2"
HISTORICAL_BYTES = 1609122
CURRENT_SHA = "4da8e1f9693d30880ee505e56541fc189add70605bad88436c44a8e11a57764c"
CURRENT_BYTES = 1609137


def inspect(path: str, role: str) -> dict[str, Any]:
    try:
        docs, meta = load_lineara_map(path)
    except Exception as exc:
        return {
            "role": role,
            "status": "PARSE_FAILED",
            "exception_type": type(exc).__name__,
            "exception": str(exc),
        }
    return {
        "role": role,
        "status": "PARSE_PASS",
        "source": meta,
        "document_count": len(docs),
        "KH104_present": "KH104" in docs,
        "KNZg57b_present": "KNZg57b" in docs,
        "KNZg57b_words_contains_U+1076B": (
            chr(0x1076B) in docs.get("KNZg57b", {}).get("words", [])
            if isinstance(docs.get("KNZg57b", {}).get("words", []), list)
            else False
        ),
    }


def parse_view_checks(item: dict[str, Any], *, expected_sha: str, expected_bytes: int) -> dict[str, bool]:
    source = item.get("source", {})
    view = source.get("parse_view", {})
    return {
        "parse_pass": item.get("status") == "PARSE_PASS",
        "source_sha_match": source.get("sha256") == expected_sha,
        "source_bytes_match": source.get("bytes") == expected_bytes,
        "transform_id_match": view.get("transform_id") == PARSE_TRANSFORM_ID,
        "strict_json_parse_success": view.get("strict_json_parse_success") is True,
        "source_bytes_mutated_false": view.get("source_bytes_mutated") is False,
        "javascript_executed_false": view.get("javascript_executed") is False,
        "eval_used_false": view.get("eval_used") is False,
        "one_codepoint_escape_replaced": view.get("codepoint_escape_replacement_count") == 1,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--historical", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    self_test = parser_transform_self_test()
    historical = inspect(args.historical, "BRIAKOS_HISTORICAL_EXACT_SOURCE")
    current = inspect(args.current, "JANUS_CURRENT_FROZEN_MWENGE_SOURCE")
    hchecks = parse_view_checks(historical, expected_sha=HISTORICAL_SHA, expected_bytes=HISTORICAL_BYTES)
    cchecks = parse_view_checks(current, expected_sha=CURRENT_SHA, expected_bytes=CURRENT_BYTES)

    self_test_required = [
        "active_codepoint_escape_decoded_to_U+1076B",
        "doubled_backslash_literal_preserved",
        "quoted_literal_preserved",
        "unsupported_identifier_failed_closed",
        "invalid_or_surrogate_codepoint_failed_closed",
    ]
    self_test_pass = all(self_test.get(k) is True for k in self_test_required)
    historical_semantic_canary = historical.get("KNZg57b_words_contains_U+1076B") is True
    current_semantic_canary = current.get("KNZg57b_words_contains_U+1076B") is True
    all_checks = all(hchecks.values()) and all(cchecks.values()) and self_test_pass and historical_semantic_canary and current_semantic_canary

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1A-JS-LITERAL-SUBSET-PARSER-CORRECTION-VALIDATION-RESULT-2026-08-14-v0.2",
        "version": "v0.2",
        "node_type": "parser_correction_validation_result",
        "status": "PARSER_V0_2_ADMITTED" if all_checks else "PARSER_V0_2_NOT_ADMITTED",
        "frozen_spec": "data/JANUS-LINEAR-A-R3C-1A-JS-LITERAL-SUBSET-PARSER-CORRECTION-SPEC-2026-08-14-v0.2.json",
        "parent_negative_validation": "data/JANUS-LINEAR-A-R3C-1A-JS-TRAILING-COMMA-PARSER-CORRECTION-VALIDATION-RESULT-2026-08-14-v0.1.json",
        "transform_id": PARSE_TRANSFORM_ID,
        "self_test": self_test,
        "historical": historical,
        "current": current,
        "checks": {
            "self_test_pass": self_test_pass,
            "historical": hchecks,
            "current": cchecks,
            "historical_KNZg57b_U+1076B_canary": historical_semantic_canary,
            "current_KNZg57b_U+1076B_canary": current_semantic_canary,
            "parser_v0_2_admitted": all_checks,
        },
        "execution_firewall": {
            "scientific_metrics_computed": False,
            "scientific_recovery_run_allowed": all_checks,
            "javascript_executed": False,
            "eval_used": False,
        },
        "history": {
            "v0_1_negative_preserved": True,
            "v0_1_result_rewritten": False,
            "first_failed_scientific_run_reused": False,
        },
        "claim_ceiling": {
            "parser_validation_only": True,
            "Briakos_metrics_reproduced": False,
            "logos_D5_D6_replay_completed": False,
            "R3B_effect": "NONE",
            "independent_transcription_replication": False,
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "checks": result["checks"],
        "historical_parse_view": historical.get("source", {}).get("parse_view"),
        "current_parse_view": current.get("source", {}).get("parse_view"),
    }, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
