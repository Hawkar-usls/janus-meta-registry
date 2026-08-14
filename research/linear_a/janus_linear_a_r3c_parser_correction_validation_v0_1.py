#!/usr/bin/env python3
"""Validate the frozen trailing-comma-only lineara parser correction.

No scientific metric is computed here. The gate validates the transform itself
on synthetic canaries and on both exact frozen source versions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_common_v0_1 import load_lineara_map, parser_transform_self_test

HISTORICAL_SHA = "b7b383b93db55b504eb00c552a8b18c19a588e83bba7ff0ab93ca32277d8bfe2"
HISTORICAL_BYTES = 1609122


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
        "sample_document_ids_first10": list(docs)[:10],
        "KH104_present": "KH104" in docs,
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

    historical_identity_ok = (
        historical.get("status") == "PARSE_PASS"
        and historical.get("source", {}).get("bytes") == HISTORICAL_BYTES
        and historical.get("source", {}).get("sha256") == HISTORICAL_SHA
    )
    both_parse = historical.get("status") == "PARSE_PASS" and current.get("status") == "PARSE_PASS"
    transform_ok = bool(self_test.get("quoted_literal_preserved") and self_test.get("unsupported_identifier_failed_closed"))
    admitted = historical_identity_ok and both_parse and transform_ok

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1A-JS-TRAILING-COMMA-PARSER-CORRECTION-VALIDATION-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "parser_correction_validation_result",
        "status": "PARSER_CORRECTION_VALIDATED_ON_HISTORICAL_AND_CURRENT_SOURCE" if admitted else "PARSER_CORRECTION_NOT_ADMITTED",
        "frozen_transform_spec": "data/JANUS-LINEAR-A-R3C-1A-JS-TRAILING-COMMA-PARSER-CORRECTION-SPEC-2026-08-14-v0.1.json",
        "self_test": self_test,
        "historical": historical,
        "current": current,
        "checks": {
            "historical_exact_source_identity_preserved": historical_identity_ok,
            "historical_parse_success": historical.get("status") == "PARSE_PASS",
            "current_parse_success": current.get("status") == "PARSE_PASS",
            "synthetic_transform_canaries_pass": transform_ok,
            "parser_correction_admitted": admitted,
        },
        "execution_firewall": {
            "scientific_metrics_computed": False,
            "scientific_recovery_run_allowed": admitted,
            "javascript_executed": False,
            "eval_used": False,
        },
        "claim_ceiling": {
            "parser_validation_only": True,
            "Briakos_metrics_reproduced": False,
            "logos_D5_D6_scientific_replay_completed": False,
            "R3B_effect": "NONE",
            "independent_transcription_replication": False,
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": result["checks"], "historical_transform": historical.get("source", {}).get("parse_view"), "current_transform": current.get("source", {}).get("parse_view")}, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
