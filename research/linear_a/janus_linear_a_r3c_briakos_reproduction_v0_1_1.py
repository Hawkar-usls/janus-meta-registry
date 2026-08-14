#!/usr/bin/env python3
"""Clean R3C-1 Briakos recovery wrapper v0.1.1.

This wrapper does not alter the previously frozen scientific method. It binds
that exact v0.1 runner to the separately admitted v0.4 source loader, executes
from exact source bytes, then appends recovery provenance to the result.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import janus_linear_a_r3c_briakos_reproduction_v0_1 as base
from janus_linear_a_r3c_source_loader_v0_4 import LOADER_ID, load_lineara_map_v0_4

PARSER_ADMISSION_ARTIFACT = "data/JANUS-LINEAR-A-R3C-1A-JS-MAP-SEMANTICS-PARSER-VALIDATION-RESULT-2026-08-14-v0.4.json"
FAILED_PREDECESSOR_RUN = 31800907720


def output_path_from_argv() -> Path:
    if "--output" not in sys.argv:
        raise SystemExit("--output required")
    i = sys.argv.index("--output")
    if i + 1 >= len(sys.argv):
        raise SystemExit("--output value missing")
    return Path(sys.argv[i + 1])


def assert_parser_admission() -> dict:
    d = json.loads(Path(PARSER_ADMISSION_ARTIFACT).read_text(encoding="utf-8"))
    if d.get("status") != "PARSER_V0_4_ADMITTED":
        raise SystemExit("PARSER_V0_4_NOT_ADMITTED_AT_RECOVERY_EXECUTION")
    if d.get("execution_firewall", {}).get("scientific_recovery_run_allowed") is not True:
        raise SystemExit("PARSER_V0_4_SCIENCE_FIREWALL_CLOSED")
    return d


def main() -> None:
    admission = assert_parser_admission()
    # Replace only the source-loading dependency. All metric functions, target
    # values, frozen profiles, thresholds and random seed remain base v0.1.
    base.load_lineara_map = load_lineara_map_v0_4
    out = output_path_from_argv()
    base.main()

    d = json.loads(out.read_text(encoding="utf-8"))
    d["artifact_uuid"] = "JANUS-LINEAR-A-R3C-1-BRIAKOS-REPRODUCTION-RESULT-2026-08-14-v0.1.1"
    d["version"] = "v0.1.1"
    d["recovery_lineage"] = {
        "scientific_method_runner": "research/linear_a/janus_linear_a_r3c_briakos_reproduction_v0_1.py",
        "scientific_method_changed_after_failed_run": False,
        "source_loader": "research/linear_a/janus_linear_a_r3c_source_loader_v0_4.py",
        "source_loader_id": LOADER_ID,
        "parser_admission_artifact": PARSER_ADMISSION_ARTIFACT,
        "parser_admission_status": admission["status"],
        "recovery_of_failed_workflow_run": FAILED_PREDECESSOR_RUN,
        "scientific_results_reused_from_failed_run": False,
        "execution_from_source_bytes_repeated": True,
    }
    d.setdefault("claim_ceiling", {})["clean_recovery_run"] = True
    d["claim_ceiling"]["failed_run_scientific_result_inherited"] = False
    out.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
