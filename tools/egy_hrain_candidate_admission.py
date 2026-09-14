#!/usr/bin/env python3
"""Deterministic admission gate for the 57 frozen HRAiN Egyptian candidates.

Three frozen filters are applied in order: token boundary, schema alignment,
and explicit provenance anchoring to the 49-file epigraphic core. No semantic
scores, lineage scores, network enrichment, or human judgement are performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

EXPECTED_GRAPH_SHA256 = "0341959f56f21bd265a5c14fc3fc1e95352dc7c4d196c2a2064c683a94693c2b"
EXPECTED_INVENTORY_SHA256 = "8bb549471d3fdeefb2c450717083b5f7094167a532d2d1274c88f82dc41a44c2"
EXPECTED_PREREG_SHA256 = "74c6be4f105f51e114dca950103e1e7ea5c2b221e6504b43630635ff707e434e"
EXPECTED_CANDIDATE_COUNT = 57
EXPECTED_CANDIDATE_LIST_SHA256 = "d38ab08f5af988da995930c9233027f4ce61ff56df473bea59c7c3b24db0657e"
EXPECTED_EPIGRAPHY_COUNT = 49
EXPECTED_EPIGRAPHY_CORE_SHA256 = "4898e9fe307e4892f762ed45a209c0f308b8e01e82ff2b25b7ecfbd38b7e8ffa"
STRUCTURED_KEYS = {
    "visual_matrix", "paleography", "unicode_control", "museum_id", "museum",
    "accession", "source_ledger", "primary_sources", "source_type",
    "primary_witnesses", "hieroglyph", "hieroglyphic", "glyph", "iconography",
    "epigraphy", "transliteration", "translation", "text_witness",
    "source_provenance",
}
POINTER_TOKENS = {
    "source", "provenance", "reference", "citation", "parent", "dependency",
    "evidence", "witness", "museum", "input", "artifact",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def load_verified_json(path: Path, expected_sha256: str) -> Any:
    raw = path.read_bytes()
    observed = sha256_bytes(raw)
    if observed != expected_sha256:
        raise RuntimeError(f"SHA256_MISMATCH:{path}:{observed}")
    return json.loads(raw)

def normalized_tokens(text: str) -> list[str]:
    return [tok for tok in re.split(r"[^a-z0-9]+", text.lower()) if tok]


def contains_contiguous_sequence(haystack: list[str], needle: list[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(haystack[i:i + width] == needle for i in range(len(haystack) - width + 1))


def boundary_matches(path: str, frozen_terms: Iterable[str]) -> list[str]:
    path_tokens = normalized_tokens(path)
    passed: list[str] = []
    for term in sorted(set(str(t) for t in frozen_terms)):
        term_tokens = normalized_tokens(term)
        if contains_contiguous_sequence(path_tokens, term_tokens):
            passed.append(term)
    return passed


def normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")


def iter_keys(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield normalize_key(str(key))
            yield from iter_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_keys(child)


def schema_hits(value: Any) -> list[str]:
    return sorted(set(iter_keys(value)) & STRUCTURED_KEYS)

def pointer_escape(part: str) -> str:
    return part.replace("~", "~0").replace("/", "~1")


def iter_string_leaves(value: Any, pointer: str = ""):
    if isinstance(value, dict):
        for key in sorted(value):
            next_pointer = pointer + "/" + pointer_escape(str(key))
            yield from iter_string_leaves(value[key], next_pointer)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_string_leaves(child, pointer + f"/{index}")
    elif isinstance(value, str):
        yield pointer or "/", value


def pointer_is_provenance_field(pointer: str) -> bool:
    return bool(set(normalized_tokens(pointer)) & POINTER_TOKENS)


def exact_anchor_hits(value: Any, core: list[dict[str, Any]]) -> list[dict[str, str]]:
    hits: set[tuple[str, str, str]] = set()
    for pointer, text in iter_string_leaves(value):
        if not pointer_is_provenance_field(pointer):
            continue
        for item in core:
            path = item["path"]
            artifact_id = item.get("artifact_id")
            if path and path in text:
                hits.add((pointer, "PATH", path))
            if artifact_id and artifact_id in text:
                hits.add((pointer, "ARTIFACT_ID", artifact_id))
    return [
        {"pointer": p, "anchor_type": t, "anchor": a}
        for p, t, a in sorted(hits)
    ]

def build_epigraphy_core(inventory: dict[str, Any]) -> list[dict[str, Any]]:
    entries = [
        item for item in inventory.get("entries", [])
        if item.get("primary_tier") == "SOURCE_PROVENANCE_EPIGRAPHY"
    ]
    core = [
        {
            "path": item["path"],
            "sha256": item["sha256"],
            "artifact_id": item.get("artifact_id"),
        }
        for item in sorted(entries, key=lambda x: x["path"])
    ]
    if len(core) != EXPECTED_EPIGRAPHY_COUNT:
        raise RuntimeError(f"EPIGRAPHY_CORE_COUNT_MISMATCH:{len(core)}")
    digest = sha256_bytes(canonical_bytes(core))
    if digest != EXPECTED_EPIGRAPHY_CORE_SHA256:
        raise RuntimeError(f"EPIGRAPHY_CORE_DIGEST_MISMATCH:{digest}")
    return core


def frozen_candidates(graph: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    candidates = graph.get("hrain_overlay", {}).get("path_discovery_candidates", [])
    if len(candidates) != EXPECTED_CANDIDATE_COUNT:
        raise RuntimeError(f"CANDIDATE_COUNT_MISMATCH:{len(candidates)}")
    digest = sha256_bytes(canonical_bytes(candidates))
    if digest != EXPECTED_CANDIDATE_LIST_SHA256:
        raise RuntimeError(f"CANDIDATE_LIST_DIGEST_MISMATCH:{digest}")
    sha_by_path = {
        node["path"]: node["sha256"]
        for node in graph.get("nodes", [])
        if node.get("node_type") == "HRAIN_PATH_DISCOVERY_CANDIDATE"
    }
    if set(sha_by_path) != {item["path"] for item in candidates}:
        raise RuntimeError("CANDIDATE_NODE_SET_MISMATCH")
    return sorted(candidates, key=lambda x: x["path"]), sha_by_path

def classify_candidate(
    repo_root: Path,
    candidate: dict[str, Any],
    expected_sha256: str,
    core: list[dict[str, Any]],
) -> dict[str, Any]:
    rel = candidate["path"]
    path = repo_root / rel
    if not path.is_file():
        raise RuntimeError(f"CANDIDATE_FILE_MISSING:{rel}")
    raw = path.read_bytes()
    observed_sha = sha256_bytes(raw)
    if observed_sha != expected_sha256:
        raise RuntimeError(f"CANDIDATE_SHA256_MISMATCH:{rel}:{observed_sha}")

    exact_terms = boundary_matches(rel, candidate.get("matched_path_terms", []))
    result: dict[str, Any] = {
        "path": rel,
        "sha256": observed_sha,
        "frozen_matched_path_terms": sorted(candidate.get("matched_path_terms", [])),
        "boundary_check": {
            "status": "PASS" if exact_terms else "FAIL",
            "exact_terms": exact_terms,
        },
        "schema_alignment": {"status": "NOT_RUN"},
        "provenance_anchor": {"status": "NOT_RUN", "anchors": []},
    }
    if not exact_terms:
        result["final_status"] = "DISQUALIFIED_NOISE"
        return result
    if path.suffix.lower() != ".json":
        result["schema_alignment"] = {
            "status": "FAIL",
            "reason": "NON_JSON_CANDIDATE",
            "structured_key_hits": [],
        }
        result["final_status"] = "DISCOVERY_ONLY_SCHEMA_MISMATCH"
        return result

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        result["schema_alignment"] = {
            "status": "FAIL",
            "reason": f"INVALID_JSON:{exc.__class__.__name__}",
            "structured_key_hits": [],
        }
        result["final_status"] = "DISCOVERY_ONLY_SCHEMA_MISMATCH"
        return result

    key_hits = schema_hits(payload)
    result["schema_alignment"] = {
        "status": "PASS" if key_hits else "FAIL",
        "reason": "STRUCTURED_KEY_PRESENT" if key_hits else "NO_REQUIRED_STRUCTURED_KEY",
        "structured_key_hits": key_hits,
    }
    if not key_hits:
        result["final_status"] = "DISCOVERY_ONLY_SCHEMA_MISMATCH"
        return result
    anchors = exact_anchor_hits(payload, core)
    result["provenance_anchor"] = {
        "status": "PASS" if anchors else "FAIL",
        "anchors": anchors,
    }
    if not anchors:
        result["final_status"] = "DISCOVERY_ONLY_NO_CORE_PROVENANCE"
        return result

    result["final_status"] = "ADMITTED_TO_EVIDENCE_CORPUS"
    return result


def git_head(repo_root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo_root,
        text=True, encoding="utf-8",
    ).strip()


def build_result(repo_root: Path) -> dict[str, Any]:
    graph_path = repo_root / "data/JANUS-EGY-REVERSE-DECODER-KNOWLEDGE-GRAPH-2026-09-14-v1.0.json"
    inventory_path = repo_root / "data/JANUS-EGY-REVERSE-MEMETIC-DECODER-RELEVANT-JSON-INVENTORY-2026-09-14-v1.0.json"
    prereg_path = repo_root / "data/JANUS-EGY-HRAIN-DISCOVERY-CANDIDATE-ADMISSION-PREREG-2026-09-14-v1.0.json"
    graph = load_verified_json(graph_path, EXPECTED_GRAPH_SHA256)
    inventory = load_verified_json(inventory_path, EXPECTED_INVENTORY_SHA256)
    load_verified_json(prereg_path, EXPECTED_PREREG_SHA256)
    core = build_epigraphy_core(inventory)
    candidates, sha_by_path = frozen_candidates(graph)
    results = [
        classify_candidate(repo_root, candidate, sha_by_path[candidate["path"]], core)
        for candidate in candidates
    ]
    status_counts = Counter(item["final_status"] for item in results)
    admitted = [item["path"] for item in results if item["final_status"] == "ADMITTED_TO_EVIDENCE_CORPUS"]
    explicit_edges = []
    for item in results:
        if item["final_status"] != "ADMITTED_TO_EVIDENCE_CORPUS":
            continue
        for anchor in item["provenance_anchor"]["anchors"]:
            explicit_edges.append({
                "source_candidate": item["path"],
                "edge_type": "EXPLICIT_PROVENANCE_ANCHOR",
                "target_anchor_type": anchor["anchor_type"],
                "target_anchor": anchor["anchor"],
                "pointer": anchor["pointer"],
                "authority": "ADMISSION_ONLY__NOT_DIRECT_CULTURAL_LINEAGE",
            })
    explicit_edges = sorted(
        explicit_edges,
        key=lambda x: (
            x["source_candidate"], x["target_anchor_type"],
            x["target_anchor"], x["pointer"],
        ),
    )
    apparatus_sha = sha256_bytes(Path(__file__).read_bytes())
    result_core = {
        "candidate_results": results,
        "explicit_provenance_edges": explicit_edges,
    }
    return {
        "schema": "janus.egy.hrain.discovery_candidate_admission.result.v1_0",
        "artifact_id": "JANUS-EGY-HRAIN-DISCOVERY-CANDIDATE-ADMISSION-RESULT-2026-09-14-v1.0",
        "created_date": "2026-09-14",
        "status": "PASS__ALL_FROZEN_CANDIDATES_CLASSIFIED__SCORING_LOCKED",
        "apparatus": {
            "path": "tools/egy_hrain_candidate_admission.py",
            "sha256": apparatus_sha,
            "git_head": git_head(repo_root),
        },
        "frozen_inputs": {
            "graph_sha256": EXPECTED_GRAPH_SHA256,
            "inventory_sha256": EXPECTED_INVENTORY_SHA256,
            "prereg_sha256": EXPECTED_PREREG_SHA256,
            "candidate_count": EXPECTED_CANDIDATE_COUNT,
            "candidate_list_sha256": EXPECTED_CANDIDATE_LIST_SHA256,
            "epigraphy_core_count": EXPECTED_EPIGRAPHY_COUNT,
            "epigraphy_core_sha256": EXPECTED_EPIGRAPHY_CORE_SHA256,
        },
        "summary": {
            "status_counts": dict(sorted(status_counts.items())),
            "admitted_count": len(admitted),
            "admitted_paths": admitted,
            "explicit_provenance_edge_count": len(explicit_edges),
            "result_core_sha256": sha256_bytes(canonical_bytes(result_core)),
        },
        "scoring_locks": {
            "LRS": "LOCKED_NOT_COMPUTED",
            "LES": "LOCKED_NOT_COMPUTED",
            "CRI": "LOCKED_NOT_COMPUTED",
            "reverse_prediction": "LOCKED",
            "semantic_operator_promotion": "LOCKED",
        },
        "authority_firewalls": [
            "HRAIN_DISCOVERY_CANDIDATE != EVIDENCE",
            "TOKEN_MATCH != ENTITY_IDENTITY",
            "SCHEMA_ALIGNMENT != HISTORICAL_TRUTH",
            "EXPLICIT_PROVENANCE_REFERENCE != DIRECT_CULTURAL_LINEAGE",
            "ZERO_ADMISSIONS_IS_A_VALID_RESULT",
        ],
        "candidate_results": results,
        "explicit_provenance_edges": explicit_edges,
    }


def write_result(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def self_test() -> None:
    assert boundary_matches("x/crisis-report.json", ["isis"]) == []
    assert boundary_matches("x/input-trace.json", ["inpu"]) == []
    assert boundary_matches("x/erratum-note.json", ["atum"]) == []
    assert boundary_matches("research/egypt/osiris-note.json", ["egypt", "osiris"]) == ["egypt", "osiris"]
    payload = {"source_ledger": [{"museum_id": "X", "reference": "data/CORE.json"}]}
    assert set(schema_hits(payload)) == {"museum_id", "source_ledger"}
    core = [{"path": "data/CORE.json", "sha256": "0" * 64, "artifact_id": "JANUS-CORE"}]
    hits = exact_anchor_hits(payload, core)
    assert hits and hits[0]["anchor"] == "data/CORE.json"

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/JANUS-EGY-HRAIN-DISCOVERY-CANDIDATE-ADMISSION-RESULT-2026-09-14-v1.0.json"),
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("SELF_TEST_PASS")
        return 0
    repo_root = args.repo_root.resolve()
    output = args.output if args.output.is_absolute() else repo_root / args.output
    payload = build_result(repo_root)
    write_result(output, payload)
    receipt = {
        "status": payload["status"],
        **payload["summary"],
        "output_sha256": sha256_bytes(output.read_bytes()),
        "output_bytes": output.stat().st_size,
    }
    print(json.dumps(receipt, ensure_ascii=True, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
