#!/usr/bin/env python3
"""Audit central-directory member names across every unique public upstream ZIP.

No archive member payload is read, extracted, imported, or executed. Exact Git
blob identity and byte length are verified before ZIP central-directory names
are inspected. The gate answers only name-level provenance questions.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

SPEC_PATH = "data/JANUS-LINEAR-A-R3C-3-ALL-PUBLIC-PACKAGE-MEMBER-NAME-AUDIT-SPEC-2026-08-14-v0.1.json"
HISTORY_PATH = "data/JANUS-LINEAR-A-R3C-3-UPSTREAM-GIT-PACKAGE-HISTORY-AUDIT-RESULT-2026-08-14-v0.1.json"
RUNNER_ID = "JANUS-LINEAR-A-R3C3-ALL-PUBLIC-PACKAGE-MEMBER-NAME-AUDIT-v0.1"


def git_blob(repo: Path, sha: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), "cat-file", "blob", sha])


def git_blob_sha1(data: bytes) -> str:
    h = hashlib.sha1()
    h.update(f"blob {len(data)}\0".encode("ascii"))
    h.update(data)
    return h.hexdigest()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def language_presence(names: list[str]) -> dict[str, list[str]]:
    lows = [n.lower() for n in names]
    out: dict[str, list[str]] = {}
    out["Ancient Egyptian"] = [names[i] for i, x in enumerate(lows) if "ancientegyptian" in x or "ancient_egyptian" in x or "ancient-egyptian" in x or "ancient egyptian" in x]
    out["Luwian"] = [names[i] for i, x in enumerate(lows) if "luwian" in x]
    out["Hittite"] = [names[i] for i, x in enumerate(lows) if "hittite" in x]
    out["Proto-Celtic"] = [names[i] for i, x in enumerate(lows) if "proto_celtic" in x or "proto-celtic" in x or "protoceltic" in x or "proto celtic" in x]
    uralic_re = re.compile(r"(?i)(^|[/_. -])uralic([/_. -]|$)")
    out["Uralic"] = [n for n in names if uralic_re.search(n)]
    return out


def method_resource_matches(names: list[str], fragments: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for frag in fragments:
        f = frag.lower()
        rows = [n for n in names if f in n.lower()]
        result[frag] = rows
    return result


def inspect_blob(repo: Path, row: dict[str, Any], method_fragments: list[str]) -> dict[str, Any]:
    blob_sha = row["git_blob_sha1"]
    data = git_blob(repo, blob_sha)
    if len(data) != row["bytes"]:
        raise ValueError(f"BYTE_COUNT_MISMATCH:{blob_sha}:{len(data)}:{row['bytes']}")
    observed_git_sha = git_blob_sha1(data)
    if observed_git_sha != blob_sha:
        raise ValueError(f"GIT_BLOB_SHA1_MISMATCH:{blob_sha}:{observed_git_sha}")
    with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
        infos = zf.infolist()
        names = [info.filename for info in infos]
        directories = sum(1 for info in infos if info.is_dir())
        regular = len(infos) - directories
        # Central-directory metadata only. Never zf.read()/open() any member.
        duplicate_names = len(names) - len(set(names))
    lang = language_presence(names)
    method = method_resource_matches(names, method_fragments)
    return {
        "git_blob_sha1": blob_sha,
        "expected_bytes": row["bytes"],
        "observed_bytes": len(data),
        "sha256": sha256(data),
        "known_paths": row["known_paths"],
        "zip_entry_count": len(names),
        "zip_regular_file_count": regular,
        "zip_directory_count": directories,
        "duplicate_member_name_count": duplicate_names,
        "fixed_language_member_name_presence": {
            k: {"present": bool(v), "matching_member_names": sorted(v)} for k, v in lang.items()
        },
        "Uralic_named_member_count": len(lang["Uralic"]),
        "method_resource_name_matches": {k: sorted(v) for k, v in method.items()},
        "member_payload_read": False,
        "members_extracted": False,
        "members_executed": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = json.loads(Path(SPEC_PATH).read_text(encoding="utf-8"))
    history = json.loads(Path(HISTORY_PATH).read_text(encoding="utf-8"))
    assert spec["status"] == "FROZEN_BEFORE_EXECUTION"
    assert history["status"] == spec["parent_history_audit"]["required_status"]
    assert history["summary"]["unique_zip_blob_count"] == spec["parent_history_audit"]["required_unique_zip_blob_count"] == 6
    assert spec["operations"]["read_member_payload"] is False
    assert spec["operations"]["extract_members"] is False
    assert spec["operations"]["execute_members"] is False

    repo = Path(args.repo)
    method_fragments = spec["fixed_name_tests"]["method_resource_fragments"]
    bundles = [inspect_blob(repo, row, method_fragments) for row in spec["public_zip_blob_universe"]]
    uralic_hits = [
        {"git_blob_sha1": b["git_blob_sha1"], "known_paths": b["known_paths"], "matching_member_names": b["fixed_language_member_name_presence"]["Uralic"]["matching_member_names"]}
        for b in bundles if b["Uralic_named_member_count"] > 0
    ]
    status = "URALIC_NAMED_MEMBER_FOUND_IN_PUBLIC_PACKAGE_HISTORY" if uralic_hits else "NO_URALIC_NAMED_MEMBER_IN_ANY_PUBLIC_PACKAGE_SNAPSHOT"

    language_snapshot_counts: dict[str, int] = {}
    for language in spec["fixed_name_tests"]["language_families"]:
        language_snapshot_counts[language] = sum(
            1 for b in bundles if b["fixed_language_member_name_presence"][language]["present"]
        )

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-3-ALL-PUBLIC-PACKAGE-MEMBER-NAME-AUDIT-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "all_public_package_central_directory_name_audit_result",
        "status": status,
        "runner_id": RUNNER_ID,
        "frozen_spec": SPEC_PATH,
        "parent_history_audit": HISTORY_PATH,
        "summary": {
            "unique_public_zip_blobs_expected": 6,
            "unique_public_zip_blobs_audited": len(bundles),
            "total_zip_entries_across_unique_blobs": sum(b["zip_entry_count"] for b in bundles),
            "Uralic_named_snapshot_count": len(uralic_hits),
            "Uralic_named_member_total": sum(b["Uralic_named_member_count"] for b in bundles),
            "fixed_language_snapshot_presence_counts": language_snapshot_counts,
            "all_git_blob_sha1_verified": True,
            "all_byte_counts_verified": True,
        },
        "bundles": bundles,
        "Uralic_named_hits": uralic_hits,
        "safety": {
            "archive_member_payload_read": False,
            "archive_members_extracted": False,
            "archive_members_executed": False,
            "full_member_name_inventory_persisted": False,
            "member_content_persisted": False,
        },
        "readiness_effect": {
            "all_public_package_member_name_universe_audited": True,
            "Uralic_named_member_presence_across_public_packages_established": True,
            "paper_exact_2024_input_receipt_admitted": False,
            "scientific_five_language_execution_permitted": False,
        },
        "claim_ceiling": {
            "all_public_package_member_name_universe_audited": True,
            "Uralic_named_member_presence_across_public_packages_established": True,
            "absence_of_Uralic_linguistic_data_proved": False,
            "paper_exact_2024_input_identity_established": False,
            "published_2024_matches_reproduced": False,
            "language_family_relationship_established": False,
            "R3B_effect": "NONE",
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "audited": len(bundles),
        "total_entries": result["summary"]["total_zip_entries_across_unique_blobs"],
        "uralic_snapshot_count": len(uralic_hits),
        "uralic_member_total": result["summary"]["Uralic_named_member_total"],
        "language_snapshot_counts": language_snapshot_counts,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
