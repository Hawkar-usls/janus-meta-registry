#!/usr/bin/env python3
"""Build the deterministic FULL_CURRENT Meta Registry catalog for HRAiN.

This exporter is deliberately different from the existing active projection:
`janus_hrain_registry_export.py` selects a small current/active working set,
whereas this module accounts for every tracked blob in the current repository
snapshot. The only omitted blobs are files under the generated output prefix
itself, preventing recursive self-indexing.

The catalog grants no scientific, claim, command, delete, or write authority.
It is a read-only address/provenance layer that lets HRAiN lazily fetch exact
objects when they are needed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "Hawkar-usls/janus-meta-registry"
DEFAULT_OUTPUT = ROOT / "assets/hrain-full-memory"
CONTRACT_PATH = ROOT / "data/JANUS-HRAIN-FULL-MEMORY-CONTRACT-v1.0.json"
DEFAULT_SHARD_SIZE = 200
GENERATED_PREFIX = "assets/hrain-full-memory/"


@dataclass(frozen=True)
class TrackedBlob:
    mode: str
    git_blob_sha: str
    stage: str
    path: str


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tracked_blobs() -> list[TrackedBlob]:
    """Return all tracked stage-0 blobs in deterministic path order."""
    output = git("ls-files", "-s", "-z")
    blobs: list[TrackedBlob] = []
    for record in output.split("\0"):
        if not record:
            continue
        meta, path = record.split("\t", 1)
        mode, blob_sha, stage = meta.split(" ", 2)
        if stage != "0":
            raise RuntimeError(f"UNMERGED_INDEX_ENTRY:{path}:{stage}")
        blobs.append(TrackedBlob(mode=mode, git_blob_sha=blob_sha, stage=stage, path=path))
    return sorted(blobs, key=lambda item: item.path)


def memory_class(path: str) -> str:
    p = path.lower()
    if p.startswith("data/") or p.startswith("registry/"):
        return "REGISTRY_OBJECT"
    if p.startswith("research/") and not p.startswith("research/site/"):
        return "RESEARCH_OBJECT"
    if p.startswith("docs/") or p.endswith(".md") or p.endswith(".txt"):
        return "DOCUMENT"
    if p.startswith(".janus/"):
        return "SYSTEM_CONTRACT"
    if p.startswith(".github/"):
        return "AUTOMATION"
    if p.startswith("assets/") or p.endswith(".html") or p.endswith(".css"):
        return "PRESENTATION_ASSET"
    if p.startswith("research/site/") or p.endswith((".py", ".js", ".mjs", ".sh", ".ps1", ".bat", ".cmd")):
        return "TOOLING"
    return "OTHER_TRACKED_BLOB"


def namespace(path: str) -> str:
    parts = Path(path).parts
    if not parts:
        return "root"
    if len(parts) == 1:
        return "root"
    return parts[0]


def extension(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return suffix if suffix else "<none>"


def object_record(blob: TrackedBlob, source_commit: str) -> dict[str, Any]:
    file_path = ROOT / blob.path
    raw = file_path.read_bytes()
    encoded_path = quote(blob.path, safe="/")
    return {
        "path": blob.path,
        "git_blob_sha": blob.git_blob_sha,
        "sha256": sha256_bytes(raw),
        "size_bytes": len(raw),
        "extension": extension(blob.path),
        "memory_class": memory_class(blob.path),
        "namespace": namespace(blob.path),
        "github_url": f"https://github.com/{REPOSITORY}/blob/{source_commit}/{encoded_path}",
        "raw_url": f"https://raw.githubusercontent.com/{REPOSITORY}/{source_commit}/{encoded_path}",
        "read_only": True,
        "scientific_authority_granted": False,
    }


def split_shards(items: list[dict[str, Any]], shard_size: int) -> list[list[dict[str, Any]]]:
    if shard_size <= 0:
        raise ValueError("SHARD_SIZE_MUST_BE_POSITIVE")
    return [items[i : i + shard_size] for i in range(0, len(items), shard_size)]


def write_json(path: Path, value: Any) -> str:
    data = canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha256_bytes(data)


def build_catalog(output_root: Path = DEFAULT_OUTPUT, shard_size: int = DEFAULT_SHARD_SIZE) -> dict[str, Any]:
    source_commit = git("rev-parse", "HEAD")
    source_time = git("show", "-s", "--format=%cI", "HEAD")
    all_blobs = tracked_blobs()

    excluded = [item for item in all_blobs if item.path.startswith(GENERATED_PREFIX)]
    included = [item for item in all_blobs if not item.path.startswith(GENERATED_PREFIX)]
    records = [object_record(item, source_commit) for item in included]

    if output_root.exists():
        shutil.rmtree(output_root)
    shards_dir = output_root / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)

    class_counts: dict[str, int] = {}
    namespace_counts: dict[str, int] = {}
    extension_counts: dict[str, int] = {}
    total_bytes = 0
    for item in records:
        class_counts[item["memory_class"]] = class_counts.get(item["memory_class"], 0) + 1
        namespace_counts[item["namespace"]] = namespace_counts.get(item["namespace"], 0) + 1
        extension_counts[item["extension"]] = extension_counts.get(item["extension"], 0) + 1
        total_bytes += int(item["size_bytes"])

    shard_manifests: list[dict[str, Any]] = []
    for index, objects in enumerate(split_shards(records, shard_size)):
        shard_name = f"{index:04d}.json"
        shard_payload = {
            "schema": "janus.hrain.full_memory_shard.v1",
            "status": "READ_ONLY_FULL_CURRENT_MEMORY_SHARD",
            "source_repository": REPOSITORY,
            "source_commit": source_commit,
            "shard_index": index,
            "object_count": len(objects),
            "objects": objects,
            "authority": {
                "read_only": True,
                "delete_allowed": False,
                "source_mutation_allowed": False,
                "scientific_authority_granted": False,
            },
        }
        shard_sha256 = write_json(shards_dir / shard_name, shard_payload)
        shard_manifests.append(
            {
                "index": index,
                "path": f"assets/hrain-full-memory/shards/{shard_name}",
                "object_count": len(objects),
                "first_path": objects[0]["path"] if objects else None,
                "last_path": objects[-1]["path"] if objects else None,
                "sha256": shard_sha256,
            }
        )

    manifest: dict[str, Any] = {
        "schema": "janus.hrain.full_memory_manifest.v1",
        "status": "FULL_CURRENT_TRACKED_TREE_CATALOG",
        "source_repository": REPOSITORY,
        "source_commit": source_commit,
        "generated_at": source_time,
        "contract": "data/JANUS-HRAIN-FULL-MEMORY-CONTRACT-v1.0.json",
        "mode": "FULL_CURRENT",
        "historical_lineage_included": False,
        "coverage": {
            "tracked_blob_count": len(all_blobs),
            "cataloged_blob_count": len(records),
            "generated_self_export_exclusion_count": len(excluded),
            "generated_self_export_prefix": GENERATED_PREFIX,
            "coverage_complete": len(all_blobs) == len(records) + len(excluded),
            "excluded_paths": [item.path for item in excluded],
        },
        "statistics": {
            "cataloged_bytes": total_bytes,
            "memory_class_counts": dict(sorted(class_counts.items())),
            "namespace_counts": dict(sorted(namespace_counts.items())),
            "extension_counts": dict(sorted(extension_counts.items())),
        },
        "sharding": {
            "ordering": "PATH_ASC",
            "objects_per_shard": shard_size,
            "shard_count": len(shard_manifests),
            "shards": shard_manifests,
        },
        "authority": {
            "read_only": True,
            "delete_allowed": False,
            "source_mutation_allowed": False,
            "scientific_authority_granted": False,
            "claim_promotion_authority_granted": False,
        },
        "laws": [
            "FULL_CURRENT != COMPLETE_GIT_HISTORY",
            "HRAIN_GRAPH != REGISTRY_AUTHORITY",
            "CATALOG_PRESENCE != SCIENTIFIC_VALIDITY",
            "TERMINAL_MEMORY_READOUT_MUST_PASS_THROUGH_HRAIN",
        ],
    }
    manifest["catalog_digest"] = sha256_bytes(canonical_bytes({
        "source_commit": source_commit,
        "coverage": manifest["coverage"],
        "statistics": manifest["statistics"],
        "shards": shard_manifests,
    }))
    write_json(output_root / "manifest.json", manifest)
    return manifest


def validate_catalog(output_root: Path, manifest: dict[str, Any]) -> None:
    coverage = manifest["coverage"]
    assert coverage["coverage_complete"] is True
    assert coverage["tracked_blob_count"] == coverage["cataloged_blob_count"] + coverage["generated_self_export_exclusion_count"]
    assert manifest["historical_lineage_included"] is False
    assert manifest["authority"]["read_only"] is True
    assert manifest["authority"]["delete_allowed"] is False
    assert manifest["authority"]["source_mutation_allowed"] is False
    assert manifest["authority"]["scientific_authority_granted"] is False

    observed_count = 0
    observed_paths: list[str] = []
    for shard in manifest["sharding"]["shards"]:
        path = ROOT / shard["path"] if output_root == DEFAULT_OUTPUT else output_root / "shards" / Path(shard["path"]).name
        data = path.read_bytes()
        assert sha256_bytes(data) == shard["sha256"]
        payload = json.loads(data)
        assert payload["source_commit"] == manifest["source_commit"]
        assert payload["object_count"] == len(payload["objects"])
        observed_count += payload["object_count"]
        observed_paths.extend(item["path"] for item in payload["objects"])

    assert observed_count == coverage["cataloged_blob_count"]
    assert observed_paths == sorted(observed_paths)
    assert len(observed_paths) == len(set(observed_paths))
    for required in (
        "PROJECT_STATUS.json",
        "JANUS_CONTEXT_ANCHOR.md",
        "data/JANUS-HRAIN-META-REGISTRY-BRIDGE-v1.1.json",
        "research/site/janus_hrain_registry_export.py",
    ):
        assert required in observed_paths, required


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--shard-size", type=int, default=DEFAULT_SHARD_SIZE)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = ROOT / output_root
    manifest = build_catalog(output_root=output_root, shard_size=args.shard_size)
    if args.validate:
        validate_catalog(output_root, manifest)
    print(json.dumps({
        "terminal": "JANUS_HRAIN_FULL_CURRENT_MEMORY_CATALOG_BUILT",
        "source_commit": manifest["source_commit"],
        "catalog_digest": manifest["catalog_digest"],
        "tracked_blob_count": manifest["coverage"]["tracked_blob_count"],
        "cataloged_blob_count": manifest["coverage"]["cataloged_blob_count"],
        "excluded_self_export_count": manifest["coverage"]["generated_self_export_exclusion_count"],
        "shard_count": manifest["sharding"]["shard_count"],
        "coverage_complete": manifest["coverage"]["coverage_complete"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
