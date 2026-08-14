#!/usr/bin/env python3
"""Reconcile Briakos annotations.js byte-count/hash-prefix receipt against Git history.

This program is source-identity only: it hashes raw blobs and never parses
annotation semantics, document IDs, or Briakos' 419 target.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

HISTORICAL_COMMIT = "568f452c7a5ec80fa292cb307ead2fc6f65d07fb"
PATH = "annotations.js"
PUBLISHED_BYTES = 2201442
PUBLISHED_SHA_PREFIX = "7ce1f87a"
OBSERVED_BYTES = 2239932
OBSERVED_SHA = "7ce1f87a98827d059a732cc00506c635b4d5f65b2d0e2f1592fc2b67827758cd"
OBSERVED_GIT_BLOB = "db2661cc680f90120cb8a60d4e5b8a3e0c3e0092"
ACQUISITION_CUTOFF = "2026-03-02T00:00:00Z"


def git(repo: Path, *args: str, binary: bool = False) -> str | bytes:
    out = subprocess.check_output(["git", "-C", str(repo), *args])
    return out if binary else out.decode("utf-8").strip()


def blob_info(repo: Path, blob: str) -> dict[str, Any]:
    raw = git(repo, "cat-file", "blob", blob, binary=True)
    assert isinstance(raw, bytes)
    return {
        "git_blob_sha": blob,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "published_byte_match": len(raw) == PUBLISHED_BYTES,
        "published_sha256_prefix_match": hashlib.sha256(raw).hexdigest().startswith(PUBLISHED_SHA_PREFIX),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    repo = Path(args.repo)

    historical_blob = str(git(repo, "rev-parse", f"{HISTORICAL_COMMIT}:{PATH}"))
    historical = blob_info(repo, historical_blob)
    historical["commit"] = HISTORICAL_COMMIT

    commits_text = str(git(repo, "log", "--format=%H\t%cI", f"--until={ACQUISITION_CUTOFF}", "--", PATH))
    commits = []
    for line in commits_text.splitlines():
        if not line.strip():
            continue
        sha, date = line.split("\t", 1)
        blob = str(git(repo, "rev-parse", f"{sha}:{PATH}"))
        commits.append({"commit": sha, "date": date, "git_blob_sha": blob})

    unique_blob_order: list[str] = []
    first_seen: dict[str, dict[str, str]] = {}
    for row in commits:
        b = row["git_blob_sha"]
        if b not in first_seen:
            unique_blob_order.append(b)
            first_seen[b] = {"commit": row["commit"], "date": row["date"]}

    revisions = []
    for blob in unique_blob_order:
        info = blob_info(repo, blob)
        info["latest_path_commit_at_or_before_cutoff"] = first_seen[blob]["commit"]
        info["latest_path_commit_date_at_or_before_cutoff"] = first_seen[blob]["date"]
        revisions.append(info)

    exact_size = [r for r in revisions if r["published_byte_match"]]
    prefix_matches = [r for r in revisions if r["published_sha256_prefix_match"]]
    both = [r for r in revisions if r["published_byte_match"] and r["published_sha256_prefix_match"]]

    latest_path_commit = commits[0] if commits else None
    historical_observed_match = (
        historical_blob == OBSERVED_GIT_BLOB
        and historical["bytes"] == OBSERVED_BYTES
        and historical["sha256"] == OBSERVED_SHA
    )
    latest_path_blob_same_as_historical = bool(latest_path_commit and latest_path_commit["git_blob_sha"] == historical_blob)

    if (
        historical_observed_match
        and historical["published_sha256_prefix_match"]
        and latest_path_blob_same_as_historical
        and not both
    ):
        status = "HASH_LINEAGE_ADMITTED_BYTE_COUNT_CLASSIFIED_AS_PUBLISHED_METADATA_CONFLICT"
    elif both and not any(r["git_blob_sha"] == historical_blob for r in both):
        status = "SOURCE_IDENTITY_REJECTED"
    else:
        status = "SOURCE_IDENTITY_AMBIGUOUS"

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1E-ANNOTATION-SOURCE-IDENTITY-RECONCILIATION-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "source_identity_reconciliation_result",
        "status": status,
        "frozen_spec": "data/JANUS-LINEAR-A-R3C-1E-ANNOTATION-SOURCE-IDENTITY-RECONCILIATION-SPEC-2026-08-14-v0.1.json",
        "published_receipt": {
            "bytes": PUBLISHED_BYTES,
            "sha256_prefix": PUBLISHED_SHA_PREFIX,
            "acquisition_date": "2026-03-01",
        },
        "historical_commit_observation": historical,
        "historical_observed_canary_match": historical_observed_match,
        "path_history": {
            "cutoff": ACQUISITION_CUTOFF,
            "path_change_commit_count": len(commits),
            "unique_blob_count": len(revisions),
            "latest_path_change": latest_path_commit,
            "latest_path_blob_same_as_historical_commit": latest_path_blob_same_as_historical,
            "unique_revisions": revisions,
            "revisions_matching_published_bytes": exact_size,
            "revisions_matching_published_sha256_prefix": prefix_matches,
            "revisions_matching_both_published_fields": both,
        },
        "interpretation": {
            "hash_prefix_match_is_only_32_bits": True,
            "hash_prefix_alone_treated_as_full_identity_proof": False,
            "lineage_evidence_added": True,
            "published_byte_count_called_exact": False,
            "classification": status,
        },
        "firewall": {
            "annotation_semantics_inspected": False,
            "document_ids_inspected": False,
            "Briakos_419_target_used": False,
            "source_mutated": False,
        },
        "claim_ceiling": {
            "hash_lineage_candidate_only": True,
            "full_Briakos_source_identity_from_prefix_alone": False,
            "Briakos_scope_inference": False,
            "R3B_effect": "NONE",
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "historical": historical,
        "latest_path_change": latest_path_commit,
        "unique_blob_count": len(revisions),
        "exact_size_candidate_count": len(exact_size),
        "prefix_match_count": len(prefix_matches),
        "both_count": len(both),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
