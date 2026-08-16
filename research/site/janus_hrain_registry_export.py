#!/usr/bin/env python3
"""Export a bounded read-only JANUS Meta Registry graph for HRaiN.

This is a navigation/index projection over current public registry objects discovered
by the active site curator policy. It is not a replacement for source JSON, current-
authority records, or scientific evidence. HRaiN consumes this file read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from janus_site_curator import (
    DEFAULT_POLICY,
    GITHUB_BLOB,
    REPOSITORY,
    ROOT,
    SITE_BASE,
    classify_surface,
    git,
    latest_paths,
    lineage_key,
    object_metadata,
)

DEFAULT_OUTPUT = ROOT / "assets/hrain-registry-index.json"

SURFACE_LABELS = {
    "antifuck": "JANUS ANTIFUCK",
    "linear-a": "Linear A",
    "wedjat": "Wedjat / Eye of Horus",
    "scoby-skingpt": "SCOBY / SkinGPT",
    "aifc": "AIFC",
    "fundamentum": "Janus-Fundamentum",
    "gamarjoba-gen-ancvale": "GAMARJOBA GEN_ANCVALE",
    "other": "Other / cross-project",
}


def node_id_for_path(path: str) -> str:
    return "obj:" + hashlib.sha256(path.encode("utf-8")).hexdigest()[:20]


def build_index(policy: dict[str, Any]) -> dict[str, Any]:
    head_sha = git("rev-parse", "HEAD")
    head_time = git("show", "-s", "--format=%cI", "HEAD")
    max_bytes = int(policy["inputs"]["maximum_file_bytes_for_metadata"])

    objects: list[dict[str, Any]] = []
    for rel, commit_sha, modified_at in latest_paths(policy):
        path = ROOT / rel
        raw = path.read_bytes()
        text = raw[:max_bytes].decode("utf-8", errors="replace")
        title, status, gate, summary = object_metadata(path, text)
        surface, site_path = classify_surface(rel, title, policy)
        obj = {
            "id": node_id_for_path(rel),
            "label": title,
            "emoji": "◈",
            "type": "default",
            "surface": surface,
            "lineageKey": lineage_key(rel, policy),
            "path": rel,
            "sourceUrl": GITHUB_BLOB + rel,
            "sourceSha256": hashlib.sha256(raw).hexdigest(),
            "commitSha": commit_sha,
            "modifiedAt": modified_at,
            "readOnly": True,
        }
        if site_path:
            obj["surfaceUrl"] = SITE_BASE + site_path
        if status:
            obj["status"] = status
        if gate:
            obj["gate"] = gate
        if summary:
            obj["summary"] = summary
        objects.append(obj)

    surfaces = [rule["surface"] for rule in policy["surface_rules"]] + ["other"]
    used_surfaces = [surface for surface in surfaces if any(o["surface"] == surface for o in objects)]

    root_id = "registry:janus-meta-registry"
    nodes: list[dict[str, Any]] = [
        {
            "id": root_id,
            "label": "JANUS Meta Registry",
            "emoji": "🏛️",
            "type": "info",
            "parentId": None,
            "readOnly": True,
            "sourceUrl": "https://github.com/Hawkar-usls/janus-meta-registry",
            "summary": "Read-only HRaiN projection of current public JANUS Meta Registry objects.",
        }
    ]
    links: list[dict[str, str]] = []

    for surface in used_surfaces:
        surface_id = f"surface:{surface}"
        nodes.append(
            {
                "id": surface_id,
                "label": SURFACE_LABELS.get(surface, surface),
                "emoji": "⌘" if surface == "other" else "◇",
                "type": "info",
                "parentId": root_id,
                "readOnly": True,
                "surface": surface,
            }
        )
        links.append({"source": root_id, "target": surface_id})

        for obj in objects:
            if obj["surface"] != surface:
                continue
            node = dict(obj)
            node["parentId"] = surface_id
            nodes.append(node)
            links.append({"source": surface_id, "target": node["id"]})

    return {
        "schema": "janus.hrain.registry_graph_index.v1_0",
        "status": "AUTO_GENERATED_READ_ONLY_ACTIVE_REGISTRY_PROJECTION",
        "generatedAt": head_time,
        "sourceCommit": head_sha,
        "repository": REPOSITORY,
        "sourcePolicy": "data/JANUS-SITE-CURATOR-POLICY-v1.2.json",
        "objectCount": len(objects),
        "nodeCount": len(nodes),
        "linkCount": len(links),
        "nodes": nodes,
        "links": links,
        "claimCeiling": [
            "HRAIN_GRAPH != REGISTRY_AUTHORITY",
            "REGISTRY_INDEX != SOURCE_OBJECT",
            "ACTIVE_PROJECTION != COMPLETE_HISTORICAL_DATABASE_DUMP",
            "GRAPH_POSITION != EVIDENCE_STRENGTH",
            "READ_ONLY_PRESENTATION != WRITE_AUTHORITY",
        ],
    }


def validate(index: dict[str, Any]) -> None:
    assert index["schema"] == "janus.hrain.registry_graph_index.v1_0"
    assert index["status"] == "AUTO_GENERATED_READ_ONLY_ACTIVE_REGISTRY_PROJECTION"
    assert index["objectCount"] > 0
    assert index["nodeCount"] == len(index["nodes"])
    assert index["linkCount"] == len(index["links"])
    assert index["nodes"][0]["id"] == "registry:janus-meta-registry"
    ids = {node["id"] for node in index["nodes"]}
    assert len(ids) == len(index["nodes"])
    for link in index["links"]:
        assert link["source"] in ids and link["target"] in ids
    for node in index["nodes"]:
        assert node.get("readOnly") is True
    assert "HRAIN_GRAPH != REGISTRY_AUTHORITY" in index["claimCeiling"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    policy_path = args.policy if args.policy.is_absolute() else ROOT / args.policy
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    index = build_index(policy)
    validate(index)

    if not args.validate_only:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"JANUS_HRAIN_INDEX_SOURCE_COMMIT={index['sourceCommit']}")
    print(f"JANUS_HRAIN_INDEX_OBJECTS={index['objectCount']}")
    print(f"JANUS_HRAIN_INDEX_NODES={index['nodeCount']}")
    print(f"JANUS_HRAIN_INDEX_LINKS={index['linkCount']}")
    print("JANUS_HRAIN_INDEX_READ_ONLY=TRUE")
    print("JANUS_HRAIN_INDEX=PASS")


if __name__ == "__main__":
    main()
