#!/usr/bin/env python3
"""Transport-recovered annotations.js source identity reconciliation via GitHub REST.

Only repository/path/blob metadata and exact raw blob bytes are processed.
Annotation semantics and document identities are never parsed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import urllib.request
from pathlib import Path
from typing import Any

OWNER_REPO = "mwenge/lineara.xyz"
PATH = "annotations.js"
HISTORICAL_COMMIT = "568f452c7a5ec80fa292cb307ead2fc6f65d07fb"
CUTOFF = "2026-03-02T00:00:00Z"
PUBLISHED_BYTES = 2201442
PUBLISHED_PREFIX = "7ce1f87a"
OBS_BYTES = 2239932
OBS_SHA = "7ce1f87a98827d059a732cc00506c635b4d5f65b2d0e2f1592fc2b67827758cd"
OBS_GIT_BLOB = "db2661cc680f90120cb8a60d4e5b8a3e0c3e0092"


def api(url: str) -> Any:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "janus-proof-bot"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def contents_meta(commit: str) -> dict[str, Any]:
    return api(f"https://api.github.com/repos/{OWNER_REPO}/contents/{PATH}?ref={commit}")


def blob_bytes(blob_sha: str) -> bytes:
    data = api(f"https://api.github.com/repos/{OWNER_REPO}/git/blobs/{blob_sha}")
    if data.get("encoding") != "base64":
        raise ValueError(f"UNSUPPORTED_BLOB_ENCODING:{data.get('encoding')}")
    return base64.b64decode(data["content"], validate=False)


def make_blob_row(blob_sha: str, advertised_size: int | None) -> dict[str, Any]:
    raw = blob_bytes(blob_sha)
    sha = hashlib.sha256(raw).hexdigest()
    return {
        "git_blob_sha": blob_sha,
        "contents_api_size": advertised_size,
        "decoded_bytes": len(raw),
        "contents_api_size_matches_decoded": advertised_size == len(raw),
        "sha256": sha,
        "published_byte_match": len(raw) == PUBLISHED_BYTES,
        "published_sha256_prefix_match": sha.startswith(PUBLISHED_PREFIX),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    page1 = api(
        f"https://api.github.com/repos/{OWNER_REPO}/commits?path={PATH}&until={CUTOFF}&per_page=100&page=1"
    )
    page2 = api(
        f"https://api.github.com/repos/{OWNER_REPO}/commits?path={PATH}&until={CUTOFF}&per_page=100&page=2"
    )
    if not isinstance(page1, list) or not isinstance(page2, list):
        raise ValueError("PATH_HISTORY_API_NOT_LIST")
    complete = len(page2) == 0 and len(page1) < 100

    commits: list[dict[str, Any]] = []
    unique_blobs: dict[str, dict[str, Any]] = {}
    for row in page1:
        sha = row["sha"]
        date = row["commit"]["committer"]["date"]
        meta = contents_meta(sha)
        blob = meta["sha"]
        size = meta.get("size")
        commits.append({"commit": sha, "date": date, "git_blob_sha": blob, "size": size})
        if blob not in unique_blobs:
            unique_blobs[blob] = {"latest_path_commit": sha, "latest_path_commit_date": date, "size": size}

    revision_rows = []
    for blob, origin in unique_blobs.items():
        b = make_blob_row(blob, origin["size"])
        b.update(origin)
        revision_rows.append(b)

    hist_meta = contents_meta(HISTORICAL_COMMIT)
    hist_blob = hist_meta["sha"]
    historical = make_blob_row(hist_blob, hist_meta.get("size"))
    historical["commit"] = HISTORICAL_COMMIT

    exact_size = [r for r in revision_rows if r["published_byte_match"]]
    prefix = [r for r in revision_rows if r["published_sha256_prefix_match"]]
    both = [r for r in revision_rows if r["published_byte_match"] and r["published_sha256_prefix_match"]]
    latest = commits[0] if commits else None
    observed_canary = hist_blob == OBS_GIT_BLOB and historical["decoded_bytes"] == OBS_BYTES and historical["sha256"] == OBS_SHA
    latest_same = bool(latest and latest["git_blob_sha"] == hist_blob)

    if not complete:
        status = "SOURCE_IDENTITY_AMBIGUOUS_INCOMPLETE_PATH_HISTORY"
    elif observed_canary and historical["published_sha256_prefix_match"] and latest_same and not both:
        status = "HASH_LINEAGE_ADMITTED_BYTE_COUNT_CLASSIFIED_AS_PUBLISHED_METADATA_CONFLICT"
    elif both and not any(r["git_blob_sha"] == hist_blob for r in both):
        status = "SOURCE_IDENTITY_REJECTED"
    else:
        status = "SOURCE_IDENTITY_AMBIGUOUS"

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1E-ANNOTATION-SOURCE-IDENTITY-API-RECOVERY-RESULT-2026-08-14-v0.1.1",
        "version": "v0.1.1",
        "node_type": "source_identity_reconciliation_transport_recovery_result",
        "status": status,
        "parent_spec": "data/JANUS-LINEAR-A-R3C-1E-ANNOTATION-SOURCE-IDENTITY-RECONCILIATION-SPEC-2026-08-14-v0.1.json",
        "transport_recovery_spec": "data/JANUS-LINEAR-A-R3C-1E-ANNOTATION-SOURCE-IDENTITY-API-RECOVERY-SPEC-2026-08-14-v0.1.1.json",
        "published_receipt": {"bytes": PUBLISHED_BYTES, "sha256_prefix": PUBLISHED_PREFIX, "acquisition_date": "2026-03-01"},
        "historical_commit_observation": historical,
        "historical_observed_canary_match": observed_canary,
        "path_history": {
            "page1_count": len(page1),
            "page2_count": len(page2),
            "complete_under_frozen_pagination_rule": complete,
            "path_change_commit_count": len(commits),
            "unique_blob_count": len(revision_rows),
            "latest_path_change": latest,
            "latest_path_blob_same_as_historical": latest_same,
            "commits": commits,
            "unique_revisions": revision_rows,
            "revisions_matching_published_bytes": exact_size,
            "revisions_matching_published_sha256_prefix": prefix,
            "revisions_matching_both_published_fields": both,
        },
        "interpretation": {
            "hash_prefix_bits": 32,
            "hash_prefix_alone_treated_as_full_identity_proof": False,
            "repository_path_lineage_used": True,
            "published_byte_count_called_exact": False,
            "metadata_conflict_if_admitted": status == "HASH_LINEAGE_ADMITTED_BYTE_COUNT_CLASSIFIED_AS_PUBLISHED_METADATA_CONFLICT",
        },
        "firewall": {
            "annotation_semantics_parsed": False,
            "document_ids_parsed": False,
            "Briakos_419_target_used": False,
            "source_mutated": False,
        },
        "claim_ceiling": {
            "transport_recovery_only": True,
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
        "history_complete": complete,
        "path_commits": len(commits),
        "unique_blobs": len(revision_rows),
        "exact_size_candidates": len(exact_size),
        "prefix_candidates": len(prefix),
        "both_candidates": len(both),
        "historical": historical,
        "latest": latest,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
