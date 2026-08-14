#!/usr/bin/env python3
"""Corrective wrapper for historical four-language stress test v0.1.1.

Reuses the frozen v0.1 scientific implementation and its original seed
namespace. Only archive member path/full SHA identities are corrected from the
persisted immutable inventory. The v0.1 run failed before observed scoring.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import janus_linear_a_r3c3_historical_four_language_stress_v0_1 as v01

CORRECTED_SPEC = "data/JANUS-LINEAR-A-R3C-3-HISTORICAL-FOUR-LANGUAGE-STRESS-TEST-SPEC-2026-08-14-v0.1.1.json"
FAILED_RECEIPT = "data/JANUS-LINEAR-A-R3C-3-HISTORICAL-FOUR-LANGUAGE-STRESS-FAILED-RUN-RECEIPT-2026-08-14-v0.1.json"
RUNNER_ID = "JANUS-LINEAR-A-R3C3-HISTORICAL-FOUR-LANGUAGE-STRESS-v0.1.1"


def execute(bundle: Path, out: Path) -> dict:
    spec = json.loads(Path(CORRECTED_SPEC).read_text(encoding="utf-8"))
    failed = json.loads(Path(FAILED_RECEIPT).read_text(encoding="utf-8"))
    assert spec["status"] == "FROZEN_AFTER_V0_1_PRE_SCORING_FAILURE_BEFORE_CORRECTIVE_EXECUTION"
    assert failed["status"] == "FAILED_BEFORE_SCIENTIFIC_SCORING_INPUT_MEMBER_IDENTITY_ERROR"
    assert failed["failure"]["failure_before_any_observed_metric"] is True
    assert failed["failure"]["failure_before_any_null_permutation"] is True
    assert spec["permutation_protocol"]["seed_namespace"] == v01.SPEC_ID
    assert spec["lineage"]["scientific_semantics_changed"] is False

    # v0.1 implementation checks a frozen-status literal. Create a transient
    # compatibility view of the already-persisted corrective spec, changing
    # status only; no scientific field is modified. Seed namespace remains the
    # original v0.1 global constant inside the reused implementation.
    effective = json.loads(json.dumps(spec))
    effective["status"] = "FROZEN_BEFORE_EXECUTION"
    with tempfile.TemporaryDirectory(prefix="janus-r3c3-v011-") as td:
        compat = Path(td) / "effective-spec.json"
        raw_result = Path(td) / "raw-result.json"
        compat.write_text(json.dumps(effective, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        old_spec_path = v01.SPEC_PATH
        try:
            v01.SPEC_PATH = str(compat)
            result = v01.execute(bundle, raw_result)
        finally:
            v01.SPEC_PATH = old_spec_path

    result["artifact_uuid"] = "JANUS-LINEAR-A-R3C-3-HISTORICAL-FOUR-LANGUAGE-STRESS-TEST-RESULT-2026-08-14-v0.1.1"
    result["version"] = "v0.1.1"
    result["runner_id"] = RUNNER_ID
    result["frozen_spec"] = CORRECTED_SPEC
    result["correction_lineage"] = {
        "base_runner": "research/linear_a/janus_linear_a_r3c3_historical_four_language_stress_v0_1.py",
        "base_seed_namespace": v01.SPEC_ID,
        "failed_parent_run": 31828373876,
        "failed_run_receipt": FAILED_RECEIPT,
        "only_member_path_and_full_sha_identities_corrected": True,
        "scientific_semantics_changed": False,
        "observed_metrics_inherited": False,
        "null_statistics_inherited": False,
        "decision_inherited": False,
    }
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("self-test")
    run = sub.add_parser("execute")
    run.add_argument("bundle")
    run.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cmd == "self-test":
        base = v01.self_test()
        spec = json.loads(Path(CORRECTED_SPEC).read_text(encoding="utf-8"))
        failed = json.loads(Path(FAILED_RECEIPT).read_text(encoding="utf-8"))
        assert spec["permutation_protocol"]["seed_namespace"] == v01.SPEC_ID
        assert failed["failure"]["failure_before_any_observed_metric"] is True
        print(json.dumps({**base, "corrective_seed_namespace_preserved": True, "parent_pre_scoring_failure_verified": True}, sort_keys=True))
        return
    result = execute(Path(args.bundle), Path(args.out))
    print(json.dumps({
        "status": result["status"],
        "linear_a_rows": result["linear_a_input"]["row_count"],
        "top_observed": result["top_observed_cells"][:5],
        "both": result["cells_clearing_both_nulls_after_max12_FWER"],
        "one": result["cells_clearing_exactly_one_null_after_max12_FWER"],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
