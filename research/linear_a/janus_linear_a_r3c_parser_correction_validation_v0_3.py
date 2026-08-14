#!/usr/bin/env python3
"""Validate frozen JANUS R3C source loader/parser v0.3.

Parser-only admission. No predecessor scientific metric is computed here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_common_v0_1 import PARSE_TRANSFORM_ID, parser_transform_self_test
from janus_linear_a_r3c_source_loader_v0_3 import (
    BOUNDARY_ID,
    LOADER_ID,
    boundary_self_test,
    load_lineara_map_v0_3,
)

HISTORICAL = {
    "bytes": 1609122,
    "sha256": "b7b383b93db55b504eb00c552a8b18c19a588e83bba7ff0ab93ca32277d8bfe2",
}
CURRENT = {
    "bytes": 1609137,
    "sha256": "4da8e1f9693d30880ee505e56541fc189add70605bad88436c44a8e11a57764c",
}


def inspect(path: str, role: str) -> dict[str, Any]:
    try:
        docs, meta = load_lineara_map_v0_3(path)
    except Exception as exc:
        return {"role": role, "status": "PARSE_FAILED", "exception_type": type(exc).__name__, "exception": str(exc)}
    words = docs.get("KNZg57b", {}).get("words", [])
    return {
        "role": role,
        "status": "PARSE_PASS",
        "source": meta,
        "document_count": len(docs),
        "first10_document_ids": list(docs)[:10],
        "KH104_present": "KH104" in docs,
        "KNZg57b_present": "KNZg57b" in docs,
        "KNZg57b_words_contains_U+1076B": isinstance(words, list) and chr(0x1076B) in words,
    }


def source_checks(item: dict[str, Any], expected: dict[str, Any]) -> dict[str, bool]:
    src = item.get("source", {})
    boundary = src.get("boundary", {})
    view = src.get("parse_view", {})
    return {
        "parse_pass": item.get("status") == "PARSE_PASS",
        "source_bytes_exact": src.get("bytes") == expected["bytes"],
        "source_sha256_exact": src.get("sha256") == expected["sha256"],
        "loader_id": src.get("loader_id") == LOADER_ID,
        "boundary_id": boundary.get("boundary_id") == BOUNDARY_ID,
        "terminator_exact": boundary.get("terminator") == ");",
        "global_rfind_not_used": boundary.get("rfind_global_terminator_used") is False,
        "literal_transform_id": view.get("transform_id") == PARSE_TRANSFORM_ID,
        "strict_json_parse_success": view.get("strict_json_parse_success") is True,
        "one_codepoint_replacement": view.get("codepoint_escape_replacement_count") == 1,
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

    boundary_canary = boundary_self_test()
    literal_canary = parser_transform_self_test()
    historical = inspect(args.historical, "BRIAKOS_HISTORICAL_EXACT_SOURCE")
    current = inspect(args.current, "JANUS_CURRENT_FROZEN_MWENGE_SOURCE")
    hchecks = source_checks(historical, HISTORICAL)
    cchecks = source_checks(current, CURRENT)

    boundary_canary_pass = all([
        boundary_canary.get("first_map_only") is True,
        boundary_canary.get("string_containing_fake_terminator_preserved") is True,
        boundary_canary.get("escaped_quote_preserved") is True,
        boundary_canary.get("javascript_executed") is False,
        boundary_canary.get("eval_used") is False,
    ])
    literal_canary_pass = all([
        literal_canary.get("active_codepoint_escape_decoded_to_U+1076B") is True,
        literal_canary.get("doubled_backslash_literal_preserved") is True,
        literal_canary.get("unsupported_identifier_failed_closed") is True,
        literal_canary.get("invalid_or_surrogate_codepoint_failed_closed") is True,
    ])
    semantic_canaries = {
        "historical_KNZg57b_U+1076B": historical.get("KNZg57b_words_contains_U+1076B") is True,
        "current_KNZg57b_U+1076B": current.get("KNZg57b_words_contains_U+1076B") is True,
    }
    admitted = boundary_canary_pass and literal_canary_pass and all(hchecks.values()) and all(cchecks.values()) and all(semantic_canaries.values())

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1A-MAP-BOUNDARY-PARSER-CORRECTION-VALIDATION-RESULT-2026-08-14-v0.3",
        "version": "v0.3",
        "node_type": "parser_correction_validation_result",
        "status": "PARSER_V0_3_ADMITTED" if admitted else "PARSER_V0_3_NOT_ADMITTED",
        "frozen_boundary_spec": "data/JANUS-LINEAR-A-R3C-1A-MAP-BOUNDARY-PARSER-CORRECTION-SPEC-2026-08-14-v0.3.json",
        "parent_negative_validations": [
            "data/JANUS-LINEAR-A-R3C-1A-JS-TRAILING-COMMA-PARSER-CORRECTION-VALIDATION-RESULT-2026-08-14-v0.1.json",
            "data/JANUS-LINEAR-A-R3C-1A-JS-LITERAL-SUBSET-PARSER-CORRECTION-VALIDATION-RESULT-2026-08-14-v0.2.json"
        ],
        "loader_id": LOADER_ID,
        "boundary_id": BOUNDARY_ID,
        "literal_transform_id": PARSE_TRANSFORM_ID,
        "boundary_self_test": boundary_canary,
        "literal_self_test": literal_canary,
        "historical": historical,
        "current": current,
        "checks": {
            "boundary_canary_pass": boundary_canary_pass,
            "literal_canary_pass": literal_canary_pass,
            "historical": hchecks,
            "current": cchecks,
            "semantic_canaries": semantic_canaries,
            "parser_v0_3_admitted": admitted,
        },
        "observations_not_selection_criteria": {
            "historical_document_count": historical.get("document_count"),
            "current_document_count": current.get("document_count"),
            "document_count_used_to_choose_boundary": False,
        },
        "execution_firewall": {
            "scientific_metrics_computed": False,
            "scientific_recovery_run_allowed": admitted,
            "javascript_executed": False,
            "eval_used": False,
        },
        "history": {
            "v0_1_negative_preserved": True,
            "v0_2_negative_preserved": True,
            "failed_scientific_run_31800907720_reused": False,
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
    print(json.dumps({"status": result["status"], "checks": result["checks"], "observations": result["observations_not_selection_criteria"]}, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
