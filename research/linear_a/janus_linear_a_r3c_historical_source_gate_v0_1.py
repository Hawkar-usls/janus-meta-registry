#!/usr/bin/env python3
"""Fail-closed historical source identity gate for JANUS Linear A R3C-1A."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_BYTES = 1609122
EXPECTED_SHA256 = "b7b383b93db55b504eb00c552a8b18c19a588e83bba7ff0ab93ca32277d8bfe2"
EXPECTED_COMMIT = "568f452c7a5ec80fa292cb307ead2fc6f65d07fb"
EXPECTED_BLOB = "b58a0447c43d7e7a16ab523f425a91d7c8b1ef7d"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    p = Path(args.source)
    raw = p.read_bytes()
    observed_sha = hashlib.sha256(raw).hexdigest()
    observed_bytes = len(raw)
    admitted = observed_bytes == EXPECTED_BYTES and observed_sha == EXPECTED_SHA256
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1A-BRIAKOS-HISTORICAL-CORPUS-RECOVERY-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "historical_source_identity_admission_receipt",
        "status": "EXACT_HISTORICAL_BYTES_RECOVERED_FROM_GIT_LINEAGE" if admitted else "HISTORICAL_SOURCE_HASH_MISMATCH_BLOCK_SCIENTIFIC_REPLAY",
        "candidate": {
            "repository": "mwenge/lineara.xyz",
            "commit": EXPECTED_COMMIT,
            "git_blob_sha": EXPECTED_BLOB,
            "path": "LinearAInscriptions.js",
        },
        "published_identity": {
            "access_date": "2026-03-01",
            "bytes": EXPECTED_BYTES,
            "sha256": EXPECTED_SHA256,
        },
        "observed_identity": {
            "bytes": observed_bytes,
            "sha256": observed_sha,
        },
        "checks": {
            "byte_count_match": observed_bytes == EXPECTED_BYTES,
            "sha256_match": observed_sha == EXPECTED_SHA256,
            "exact_historical_bytes_admitted": admitted,
        },
        "selection_receipt": {
            "candidate_selected_by_path_history_and_time_before_hash_execution": True,
            "downstream_scientific_metrics_used_to_select_candidate": False,
            "nearest_metric_version_search_performed": False,
        },
        "execution_firewall": {
            "scientific_metric_replay_allowed": admitted,
            "rule": "If exact_historical_bytes_admitted is false, Briakos scientific metric replay MUST NOT execute in this workflow run."
        },
        "supersession": {
            "older_R3C_1_freeze_stated_exact_historical_bytes_obtained_false": True,
            "old_record_rewritten": False,
            "this_receipt_upgrades_that_fact_only_if_admitted": admitted,
        },
        "claim_ceiling": {
            "same_lineage_source_identity_only": True,
            "Briakos_scientific_results_reproduced": False,
            "R3B_effect": "NONE",
            "independent_transcription_replication": False,
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], **result["checks"]}, sort_keys=True))


if __name__ == "__main__":
    main()
