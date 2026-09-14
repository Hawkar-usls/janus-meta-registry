#!/usr/bin/env python3
"""Deterministic compact EGY reverse-decoder KG harvest with HRAiN overlay.

The frozen 488 JSON inventory is the only evidence-bearing corpus. HRAiN is a
read-only coverage/navigation overlay and cannot promote lineage or scores.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

EXPECTED_COUNT = 488
EXPECTED_INVENTORY_SHA256 = "8bb549471d3fdeefb2c450717083b5f7094167a532d2d1274c88f82dc41a44c2"
INVENTORY_ID = "JANUS-EGY-REVERSE-MEMETIC-DECODER-RELEVANT-JSON-INVENTORY-2026-09-14-v1.0"
PREREG_ID = "JANUS-EGY-REVERSE-DECODER-KNOWLEDGE-GRAPH-HARVEST-PREREG-2026-09-14-v1.0"
AMENDMENT_ID = "JANUS-EGY-REVERSE-DECODER-KNOWLEDGE-GRAPH-HARVEST-AMENDMENT-2026-09-14-v1.1"
HRAIN_AMENDMENT_ID = "JANUS-EGY-REVERSE-DECODER-KG-HRAIN-OVERLAY-AMENDMENT-2026-09-14-v1.2"
SCHEMA = "janus.egy.reverse_decoder.knowledge_graph.v1_0"
LAYERS = [
    "ANCIENT_ORIGIN_SOURCE",
    "RITUAL_FUNCTION_SEMANTICS",
    "VISUAL_MATRIX_FORM_GLYPH",
    "HISTORICAL_MUTATION_LINE",
    "MODERN_MEME_CONTEXT",
    "CRI_HASH_METRIC_LAYER",
    "CONFOUNDER_NEGATIVE_CONTROL",
]
LAYER_RULES = {
    "ANCIENT_ORIGIN_SOURCE": [
        "source", "primary", "ancient", "papyrus", "pyramid text", "coffin text",
        "book of the dead", "book of two ways", "tomb", "nome", "provenance",
        "citation", "witness", "accession", "museum", "excavation", "edition",
    ],
    "RITUAL_FUNCTION_SEMANTICS": [
        "function", "semantic", "role", "ritual", "purpose", "protection",
        "restoration", "judgement", "judgment", "rebirth", "regeneration",
        "order", "balance", "transformation", "mortuary",
    ],
    "VISUAL_MATRIX_FORM_GLYPH": [
        "shape", "visual", "image", "iconograph", "glyph", "hieroglyph",
        "geometry", "pose", "gesture", "anatom", "silhouette", "form", "marking",
    ],
    "HISTORICAL_MUTATION_LINE": [
        "mutation", "transmission", "lineage", "bridge", "chronology", "sequence",
        "reencod", "re-encod", "transform", "reception", "intermediate", "drift",
        "retention", "inherit", "descendant",
    ],
    "MODERN_MEME_CONTEXT": [
        "modern", "meme", "digital", "south park", "pop culture", "fandom",
        "tattoo", "cyber", "internet", "revival", "masonic", "providence", "unicode",
        "audience", "repost", "social media",
    ],
    "CRI_HASH_METRIC_LAYER": [
        "lrs", "les", "cri", "retention score", "retention_score", "confidence",
        "checksum", "sha256", "sha-256", "hash", "score", "index", "metric",
    ],
    "CONFOUNDER_NEGATIVE_CONTROL": [
        "confound", "control", "negative", "false", "speculative", "not established",
        "not_established", "analogy", "decorative", "revival", "pareidolia",
        "coincidence", "unsupported", "rejected", "open hypothesis",
    ],
}
PROVENANCE_TOKENS = [
    "source", "citation", "reference", "provenance", "museum", "accession",
    "papyrus", "tomb", "edition", "plate", "page", "publication", "url", "doi",
    "spell", "utterance", "archive", "excavation", "catalog", "facsimile",
]
DEPENDENCY_POINTER_TOKENS = [
    "parent", "supersed", "depend", "reference", "source", "artifact", "commit",
    "file", "receipt", "input", "output", "next_gate", "crosslink",
]
ANCIENT_LAYERS = {
    "ANCIENT_ORIGIN_SOURCE", "RITUAL_FUNCTION_SEMANTICS", "VISUAL_MATRIX_FORM_GLYPH"
}
ARTIFACT_RE = re.compile(r"\bJANUS-[A-Za-z0-9][A-Za-z0-9._-]{5,}")
COMMIT_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{40}(?![0-9a-fA-F])")
FILE_RE = re.compile(
    r"(?:(?:data|research|assets|EYE|registry|tools)/[A-Za-z0-9_./-]+\.json|[A-Za-z0-9_.-]+\.json)"
)
DEITIES = {
    "osiris", "isis", "horus", "anubis", "thoth", "seth", "sobek", "sekhmet",
    "bastet", "hathor", "neith", "nephthys", "atum", "ptah", "khnum", "khonsu", "khepri",
}
SYMBOLS = {
    "wedjat", "udjat", "eye of horus", "scarab", "djed", "tyet", "ankh",
    "shen ring", "was scepter", "heka scepter", "nekhakha", "feather of maat",
}
TEXTS = {
    "pyramid text", "coffin text", "book of the dead", "book of dead",
    "book of two ways", "amduat",
}
LOCATIONS = {
    "dendera", "abydos", "saqqara", "giza", "mendes", "djedet", "heliopolis",
    "memphis", "thebes", "luxor", "edfu", "karnak",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def pointer_escape(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def iter_leaves(value: Any, pointer: str = ""):
    if isinstance(value, dict):
        for key in sorted(value):
            yield from iter_leaves(value[key], pointer + "/" + pointer_escape(str(key)))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from iter_leaves(child, pointer + f"/{i}")
    else:
        yield pointer or "/", value


def scalar_text(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def classify_layers(pointer: str, value: Any) -> list[str]:
    text = (pointer + " " + scalar_text(value)).lower()
    return [
        layer for layer in LAYERS
        if any(token in text for token in LAYER_RULES[layer])
    ]


def is_provenance_anchor(pointer: str, value: Any) -> bool:
    text = (pointer + " " + scalar_text(value)).lower()
    if any(token in text for token in PROVENANCE_TOKENS):
        return True
    return bool(re.search(
        r"https?://|doi:|\b(?:BM|CG|JE)\s*\d{2,}|\bP\.?\s*[A-Za-z]+\s*\d+",
        text, re.I,
    ))


def dependency_pointer(pointer: str) -> bool:
    low = pointer.lower()
    return any(token in low for token in DEPENDENCY_POINTER_TOKENS)


def entity_category(term: str) -> str:
    t = term.lower()
    if t in DEITIES:
        return "DEITY"
    if t in SYMBOLS:
        return "SYMBOL"
    if t in TEXTS:
        return "TEXT_CORPUS"
    if t in LOCATIONS:
        return "LOCATION"
    return "CONCEPT_OR_TERM"


def les_prelabel(text: str) -> str:
    low = text.lower()
    neg = ["not established", "not_established", "no direct", "unsupported", "rejected"]
    if ("direct lineage" in low or "direct transmission" in low) and any(x in low for x in neg):
        return "NEGATED_DIRECT_LINEAGE"
    if "source family" in low or "family resemblance" in low or "family-level" in low:
        return "FAMILY_CLAIM_PRESENT"
    if "direct lineage" in low or "direct transmission" in low or "direct source" in low:
        return "DIRECT_CLAIM_PRESENT"
    return "UNASSESSED"


class GraphBuilder:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}

    def add_node(self, node_id: str, node_type: str, **attrs: Any) -> None:
        node = {"node_id": node_id, "node_type": node_type, **attrs}
        old = self.nodes.get(node_id)
        if old is not None and canonical_bytes(old) != canonical_bytes(node):
            raise RuntimeError(f"CONFLICTING_NODE_ID:{node_id}")
        self.nodes[node_id] = node

    def add_edge(self, source: str, target: str, edge_type: str, **attrs: Any) -> None:
        basis = {"source": source, "target": target, "edge_type": edge_type, **attrs}
        edge_id = "edge:" + sha256_bytes(canonical_bytes(basis))[:24]
        edge = {"edge_id": edge_id, **basis}
        old = self.edges.get(edge_id)
        if old is not None and canonical_bytes(old) != canonical_bytes(edge):
            raise RuntimeError(f"CONFLICTING_EDGE_ID:{edge_id}")
        self.edges[edge_id] = edge

    def sorted_nodes(self) -> list[dict[str, Any]]:
        return [self.nodes[k] for k in sorted(self.nodes)]

    def sorted_edges(self) -> list[dict[str, Any]]:
        return sorted(self.edges.values(), key=lambda e: (
            e["source"], e["edge_type"], e["target"], e["edge_id"]
        ))


def artifact_relation(pointer: str) -> str:
    low = pointer.lower()
    if "supersed" in low:
        return "SUPERSEDES_ARTIFACT"
    if "parent" in low:
        return "PARENT_ARTIFACT"
    if "depend" in low:
        return "DEPENDS_ON_ARTIFACT"
    return "REFERENCES_ARTIFACT"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_hrain_full(manifest_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    manifest = load_json(manifest_path)
    if manifest.get("schema") != "janus.hrain.full_memory_manifest.v1":
        raise RuntimeError("HRAIN_FULL_SCHEMA_MISMATCH")
    if manifest.get("authority", {}).get("scientific_authority_granted") is not False:
        raise RuntimeError("HRAIN_FULL_AUTHORITY_CEILING_BROKEN")
    objects: dict[str, dict[str, Any]] = {}
    for shard in manifest["sharding"]["shards"]:
        shard_path = manifest_path.parent / "shards" / Path(shard["path"]).name
        raw = shard_path.read_bytes()
        if sha256_bytes(raw) != shard["sha256"]:
            raise RuntimeError(f"HRAIN_SHARD_SHA_MISMATCH:{shard_path.name}")
        payload = json.loads(raw)
        if payload.get("source_commit") != manifest.get("source_commit"):
            raise RuntimeError(f"HRAIN_SHARD_COMMIT_MISMATCH:{shard_path.name}")
        for obj in payload.get("objects", []):
            path = obj["path"]
            if path in objects:
                raise RuntimeError(f"HRAIN_DUPLICATE_PATH:{path}")
            objects[path] = obj
    if len(objects) != manifest["coverage"]["cataloged_blob_count"]:
        raise RuntimeError("HRAIN_FULL_COUNT_MISMATCH")
    if manifest["coverage"].get("coverage_complete") is not True:
        raise RuntimeError("HRAIN_FULL_COVERAGE_INCOMPLETE")
    return manifest, objects


def load_hrain_active(index_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    index = load_json(index_path)
    if index.get("schema") != "janus.hrain.registry_graph_index.v1_0":
        raise RuntimeError("HRAIN_ACTIVE_SCHEMA_MISMATCH")
    mutation = index.get("mutationPolicy", {})
    if mutation.get("interfaceWriteAuthority") is not False:
        raise RuntimeError("HRAIN_ACTIVE_WRITE_AUTHORITY_BROKEN")
    if mutation.get("interfaceDeleteAuthority") is not False:
        raise RuntimeError("HRAIN_ACTIVE_DELETE_AUTHORITY_BROKEN")
    by_path = {
        node["path"]: node for node in index.get("nodes", []) if node.get("path")
    }
    return index, by_path


def summarize_file_layers(data: Any) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    agg: dict[str, dict[str, Any]] = {}
    for layer in LAYERS:
        agg[layer] = {
            "tuples": [], "pointers": [], "representatives": [],
            "provenance_pointers": [], "prelabels": Counter(),
        }
    dependencies: list[dict[str, Any]] = []
    for pointer, value in iter_leaves(data):
        text = scalar_text(value)
        value_sha = sha256_bytes(canonical_bytes(value))
        for layer in classify_layers(pointer, value):
            bucket = agg[layer]
            bucket["tuples"].append((pointer, value_sha))
            bucket["pointers"].append(pointer)
            bucket["representatives"].append({
                "pointer": pointer,
                "value_sha256": value_sha,
                "preview": text[:320],
            })
            if is_provenance_anchor(pointer, value):
                bucket["provenance_pointers"].append(pointer)
            bucket["prelabels"][les_prelabel(text)] += 1
        if dependency_pointer(pointer) and isinstance(value, str):
            dependencies.extend(extract_dependencies(pointer, value))
    return finalize_layer_summaries(agg), dependencies


def finalize_layer_summaries(agg: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for layer, bucket in agg.items():
        tuples = sorted(bucket["tuples"])
        if not tuples:
            continue
        pointers = sorted(set(bucket["pointers"]))
        reps = sorted(bucket["representatives"], key=lambda x: (x["pointer"], x["value_sha256"]))
        provenance = sorted(set(bucket["provenance_pointers"]))
        if layer in ANCIENT_LAYERS:
            prov_status = "SOURCE_BOUND_CANDIDATE" if provenance else "UNVERIFIED_SPECULATION"
        else:
            prov_status = "NOT_APPLICABLE_TO_THIS_LAYER"
        out[layer] = {
            "matching_leaf_count": len(tuples),
            "pointer_value_hash_sha256": sha256_bytes(canonical_bytes(tuples)),
            "first_20_json_pointers": pointers[:20],
            "first_5_representative_fragments": reps[:5],
            "provenance_anchor_count": len(provenance),
            "first_20_provenance_pointers": provenance[:20],
            "provenance_status": prov_status,
            "lexical_les_prelabels": dict(sorted(bucket["prelabels"].items())),
            "LRS": "LOCKED_UNSCORED",
            "LES": "UNASSESSED_BY_HARVEST",
            "CRI": "LOCKED_NOT_COMPUTED",
        }
    return out


def extract_dependencies(pointer: str, text: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for artifact in sorted(set(ARTIFACT_RE.findall(text))):
        found.append({
            "kind": "ARTIFACT", "target": artifact,
            "edge_type": artifact_relation(pointer), "pointer": pointer,
        })
    for commit in sorted(set(COMMIT_RE.findall(text))):
        found.append({
            "kind": "COMMIT", "target": commit.lower(),
            "edge_type": "REFERENCES_COMMIT", "pointer": pointer,
        })
    for file_ref in sorted(set(FILE_RE.findall(text))):
        found.append({
            "kind": "FILE", "target": file_ref,
            "edge_type": "REFERENCES_FILE", "pointer": pointer,
        })
    return found


def node_id(prefix: str, value: str) -> str:
    return prefix + ":" + sha256_bytes(value.encode("utf-8"))[:24]


def path_term_hits(path: str, terms: list[str]) -> list[str]:
    low = path.lower().replace("_", " ").replace("-", " ")
    return sorted({term for term in terms if len(term) >= 4 and term.lower() in low})


def build_graph(
    repo_root: Path,
    inventory_path: Path,
    hrain_manifest_path: Path,
    hrain_active_path: Path,
    expected_hrain_commit: str,
) -> dict[str, Any]:
    inventory_raw = inventory_path.read_bytes()
    if sha256_bytes(inventory_raw) != EXPECTED_INVENTORY_SHA256:
        raise RuntimeError("FROZEN_INVENTORY_SHA256_MISMATCH")
    inventory = json.loads(inventory_raw)
    if inventory.get("artifact_id") != INVENTORY_ID:
        raise RuntimeError("FROZEN_INVENTORY_ID_MISMATCH")
    entries = inventory.get("entries", [])
    if len(entries) != EXPECTED_COUNT:
        raise RuntimeError(f"FROZEN_INVENTORY_COUNT_MISMATCH:{len(entries)}")

    hrain_manifest, hrain_objects = load_hrain_full(hrain_manifest_path)
    hrain_active, hrain_active_by_path = load_hrain_active(hrain_active_path)
    if hrain_manifest.get("source_commit") != expected_hrain_commit:
        raise RuntimeError("HRAIN_FULL_SOURCE_COMMIT_MISMATCH")
    if hrain_active.get("sourceCommit") != expected_hrain_commit:
        raise RuntimeError("HRAIN_ACTIVE_SOURCE_COMMIT_MISMATCH")

    graph = GraphBuilder()
    for position, layer in enumerate(LAYERS, start=1):
        graph.add_node(
            f"layer:{layer}", "SCHEMA_LAYER",
            label=layer, position=position,
            scientific_authority=False,
        )
    graph.add_node(
        "control:egyptian_revival", "CONTROL_CLASS",
        label="Egyptian Revival / decorative borrowing",
        edge_semantics="SPURIOUS_REVIVAL_CANDIDATE_ONLY",
        scientific_authority=False,
    )
    full_catalog_node = f"hrain:full:{expected_hrain_commit}"
    graph.add_node(
        full_catalog_node, "HRAIN_FULL_MEMORY_SNAPSHOT",
        source_commit=expected_hrain_commit,
        catalog_digest=hrain_manifest.get("catalog_digest"),
        coverage=hrain_manifest.get("coverage"),
        scientific_authority=False,
    )
    active_node = f"hrain:active:{expected_hrain_commit}"
    graph.add_node(
        active_node, "HRAIN_ACTIVE_REGISTRY_SNAPSHOT",
        source_commit=expected_hrain_commit,
        object_count=hrain_active.get("objectCount"),
        scientific_authority=False,
    )

    source_paths: set[str] = set()
    layer_summary_counts: Counter[str] = Counter()
    provenance_status_counts: Counter[str] = Counter()
    dependency_counts: Counter[str] = Counter()
    hrain_catalog_match_count = 0
    hrain_active_match_count = 0
    revival_candidate_count = 0

    for entry in sorted(entries, key=lambda x: x["path"]):
        rel = entry["path"]
        source_paths.add(rel)
        source_file = repo_root / rel
        raw = source_file.read_bytes()
        observed_sha = sha256_bytes(raw)
        if observed_sha != entry["sha256"]:
            raise RuntimeError(f"FROZEN_SOURCE_SHA256_MISMATCH:{rel}")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"FROZEN_SOURCE_PARSE_FAIL:{rel}:{exc.__class__.__name__}") from exc
        hrain_obj = hrain_objects.get(rel)
        if hrain_obj is None:
            raise RuntimeError(f"FROZEN_SOURCE_MISSING_FROM_HRAIN:{rel}")
        if hrain_obj.get("sha256") != observed_sha:
            raise RuntimeError(f"FROZEN_SOURCE_HRAIN_SHA_MISMATCH:{rel}")
        hrain_catalog_match_count += 1
        src_id = node_id("source", rel)
        graph.add_node(
            src_id, "SOURCE_FILE",
            path=rel,
            sha256=observed_sha,
            bytes=len(raw),
            inventory_tier=entry.get("primary_tier"),
            artifact_id=entry.get("artifact_id"),
            schema=entry.get("schema"),
            status=entry.get("status"),
            hrain_memory_class=hrain_obj.get("memory_class"),
            hrain_namespace=hrain_obj.get("namespace"),
            scientific_authority="SOURCE_OBJECT_ONLY",
        )
        graph.add_edge(
            src_id, full_catalog_node, "HRAIN_CATALOG_MATCH",
            sha256_match=True,
            memory_class=hrain_obj.get("memory_class"),
            namespace=hrain_obj.get("namespace"),
            authority="COVERAGE_AND_PROVENANCE_ONLY",
        )
        active_obj = hrain_active_by_path.get(rel)
        if active_obj:
            hrain_active_match_count += 1
            surface = active_obj.get("surface") or "other"
            surface_id = f"hrain:surface:{surface}"
            graph.add_node(surface_id, "HRAIN_SURFACE", label=surface, scientific_authority=False)
            graph.add_edge(src_id, surface_id, "HRAIN_ACTIVE_SURFACE_MEMBER", authority="NAVIGATION_ONLY")
            lineage_key = active_obj.get("lineageKey")
            if lineage_key:
                lineage_id = node_id("hrain-lineage", lineage_key)
                graph.add_node(
                    lineage_id, "HRAIN_REGISTRY_LINEAGE_KEY",
                    lineage_key=lineage_key,
                    scientific_authority=False,
                )
                graph.add_edge(
                    src_id, lineage_id, "HRAIN_REGISTRY_LINEAGE_KEY",
                    authority="REGISTRY_NAVIGATION_ONLY__NOT_CULTURAL_LINEAGE",
                )
            graph.add_edge(
                src_id, active_node, "HRAIN_ACTIVE_PROJECTION_MEMBER",
                authority="NAVIGATION_ONLY",
            )

        for term in sorted(set(entry.get("matched_terms", []))):
            term_id = node_id("entity", term.lower())
            graph.add_node(
                term_id, "ENTITY", label=term.lower(),
                category=entity_category(term), scientific_authority=False,
            )
            graph.add_edge(
                src_id, term_id, "MENTIONS_ENTITY",
                basis_source="FROZEN_INVENTORY_MATCH", authority="LEXICAL_ONLY",
            )
        layer_summaries, dependencies = summarize_file_layers(data)
        for layer, summary in sorted(layer_summaries.items()):
            summary_id = node_id("summary", rel + "|" + layer)
            graph.add_node(
                summary_id, "LAYER_EVIDENCE_SUMMARY",
                source_path=rel,
                source_sha256=observed_sha,
                layer=layer,
                **summary,
            )
            graph.add_edge(
                src_id, summary_id, "HAS_LAYER_EVIDENCE_SUMMARY",
                authority="SOURCE_DERIVED_SUMMARY",
            )
            graph.add_edge(
                summary_id, f"layer:{layer}", "SUMMARIZES_SCHEMA_LAYER",
                authority="CLASSIFICATION_ONLY",
            )
            layer_summary_counts[layer] += 1
            provenance_status_counts[summary["provenance_status"]] += 1

        serialized_low = raw.decode("utf-8", errors="replace").lower()
        if "egyptian revival" in serialized_low:
            revival_candidate_count += 1
            graph.add_edge(
                src_id, "control:egyptian_revival", "SPURIOUS_REVIVAL_CANDIDATE",
                authority="CONTROL_ROUTING_ONLY__NOT_LINEAGE_EVIDENCE",
            )
        for dep in dependencies:
            kind = dep["kind"]
            target = dep["target"]
            if kind == "ARTIFACT":
                target_id = node_id("artifact-ref", target)
                graph.add_node(target_id, "ARTIFACT_REFERENCE", value=target, scientific_authority=False)
            elif kind == "COMMIT":
                target_id = f"commit:{target}"
                graph.add_node(target_id, "COMMIT_REFERENCE", value=target, scientific_authority=False)
            else:
                target_id = node_id("file-ref", target)
                graph.add_node(target_id, "FILE_REFERENCE", value=target, scientific_authority=False)
            graph.add_edge(
                src_id, target_id, dep["edge_type"],
                pointer=dep["pointer"],
                authority="EXPLICIT_REFERENCE_ONLY__NOT_CULTURAL_LINEAGE",
            )
            dependency_counts[dep["edge_type"]] += 1

    if hrain_catalog_match_count != EXPECTED_COUNT:
        raise RuntimeError("HRAIN_CATALOG_MATCH_COUNT_MISMATCH")

    discovery_candidates: list[dict[str, Any]] = []
    vocabulary = [str(x).lower() for x in inventory.get("scan_vocabulary", [])]
    for rel, obj in sorted(hrain_objects.items()):
        if rel in source_paths:
            continue
        hits = path_term_hits(rel, vocabulary)
        if not hits:
            continue
        candidate_id = node_id("hrain-candidate", rel)
        graph.add_node(
            candidate_id, "HRAIN_PATH_DISCOVERY_CANDIDATE",
            path=rel,
            sha256=obj.get("sha256"),
            memory_class=obj.get("memory_class"),
            namespace=obj.get("namespace"),
            matched_path_terms=hits,
            status="DISCOVERY_ONLY__NOT_EVIDENCE",
            scientific_authority=False,
        )
        graph.add_edge(
            full_catalog_node, candidate_id, "HRAIN_PATH_DISCOVERY_CANDIDATE",
            authority="DISCOVERY_ONLY__REQUIRES_SEPARATE_ADMISSION_GATE",
        )
        discovery_candidates.append({"path": rel, "matched_path_terms": hits})

    nodes = graph.sorted_nodes()
    edges = graph.sorted_edges()
    node_type_counts = Counter(node["node_type"] for node in nodes)
    edge_type_counts = Counter(edge["edge_type"] for edge in edges)
    source_tier_counts = Counter(entry.get("primary_tier") for entry in entries)
    graph_core_sha = sha256_bytes(canonical_bytes({"nodes": nodes, "edges": edges}))

    summary = {
        "verified_source_count": EXPECTED_COUNT,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "source_tier_counts": dict(sorted(source_tier_counts.items())),
        "layer_summary_counts": dict(sorted(layer_summary_counts.items())),
        "provenance_status_counts": dict(sorted(provenance_status_counts.items())),
        "dependency_edge_counts": dict(sorted(dependency_counts.items())),
        "hrain_catalog_match_count": hrain_catalog_match_count,
        "hrain_active_projection_match_count": hrain_active_match_count,
        "hrain_path_discovery_candidate_count": len(discovery_candidates),
        "egyptian_revival_candidate_count": revival_candidate_count,
        "graph_core_sha256": graph_core_sha,
    }
    return {
        "schema": SCHEMA,
        "artifact_id": "JANUS-EGY-REVERSE-DECODER-KNOWLEDGE-GRAPH-2026-09-14-v1.0",
        "status": "HARVEST_PASS__PROVENANCE_CARRIED__HRAIN_OVERLAY_BOUND__CULTURAL_LINEAGE_AND_SCORING_LOCKED",
        "method_lineage": {
            "prereg": PREREG_ID,
            "compact_amendment": AMENDMENT_ID,
            "hrain_overlay_amendment": HRAIN_AMENDMENT_ID,
        },
        "source_inventory": {
            "artifact_id": INVENTORY_ID,
            "sha256": EXPECTED_INVENTORY_SHA256,
            "count": EXPECTED_COUNT,
        },
        "hrain_overlay": {
            "source_commit": expected_hrain_commit,
            "full_manifest_sha256": sha256_bytes(hrain_manifest_path.read_bytes()),
            "full_catalog_digest": hrain_manifest.get("catalog_digest"),
            "active_index_sha256": sha256_bytes(hrain_active_path.read_bytes()),
            "authority": "READ_ONLY_ASSOCIATIVE_AND_COVERAGE_OVERLAY",
            "path_discovery_candidates": discovery_candidates,
        },
        "scoring_locks": {
            "LRS": "LOCKED_NOT_COMPUTED",
            "LES": "LOCKED_NOT_COMPUTED",
            "CRI": "LOCKED_NOT_COMPUTED",
            "reverse_prediction": "LOCKED",
        },
        "authority_firewalls": [
            "HRAIN_GRAPH != REGISTRY_AUTHORITY",
            "GRAPH_POSITION != EVIDENCE_STRENGTH",
            "SEMANTIC_SUGGESTION != REGISTRY_FACT",
            "CATALOG_PRESENCE != SCIENTIFIC_VALIDITY",
            "DERIVATIVE_MEMORY_EXPORT != FRESH_WORLD_EVIDENCE",
            "HRAIN_ASSOCIATION_NE_CULTURAL_LINEAGE",
            "CO_OCCURRENCE_NE_LINEAGE",
            "EXPLICIT_REFERENCE_NE_HISTORICAL_TRANSMISSION",
        ],
        "summary": summary,
        "nodes": nodes,
        "edges": edges,
    }


def write_output(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--hrain-full-manifest", type=Path, required=True)
    parser.add_argument("--hrain-active-index", type=Path, required=True)
    parser.add_argument("--expected-hrain-source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = build_graph(
        repo_root=args.repo_root.resolve(),
        inventory_path=args.inventory.resolve(),
        hrain_manifest_path=args.hrain_full_manifest.resolve(),
        hrain_active_path=args.hrain_active_index.resolve(),
        expected_hrain_commit=args.expected_hrain_source_commit,
    )
    write_output(args.output.resolve(), payload)
    receipt = {
        "status": payload["status"],
        **payload["summary"],
        "output_sha256": sha256_bytes(args.output.resolve().read_bytes()),
        "output_bytes": args.output.resolve().stat().st_size,
    }
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
