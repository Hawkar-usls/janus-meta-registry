#!/usr/bin/env python3
"""R3C-1E identity-only bridge between annotations.js and inscription keys.

Semantic annotation content is parsed only as necessary to validate the static JSON array;
selection uses top-level item.name exclusively.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_source_loader_v0_4 import load_lineara_map_v0_4, LOADER_ID

INS_BYTES = 1609122
INS_SHA = "b7b383b93db55b504eb00c552a8b18c19a588e83bba7ff0ab93ca32277d8bfe2"
ANN_BYTES = 2201442
ANN_SHA_PREFIX = "7ce1f87a"
BRIAKOS_SITES = {
    "Haghia Triada": 185,
    "Khania": 103,
    "Zakros": 44,
    "Phaistos": 41,
    "Knossos": 11,
}


def sha_lines(values: list[str]) -> str:
    return hashlib.sha256(("\n".join(values) + "\n").encode("utf-8")).hexdigest()


def load_annotation_identities(path: str | Path) -> tuple[list[str], dict[str, Any]]:
    p = Path(path)
    raw = p.read_bytes()
    text = raw.decode("utf-8")
    marker = "var wordAnnotations"
    marker_at = text.find(marker)
    if marker_at < 0:
        raise ValueError("WORD_ANNOTATIONS_MARKER_NOT_FOUND")
    start = text.find("[", marker_at + len(marker))
    end = text.rfind("]")
    if start < 0 or end < start:
        raise ValueError("WORD_ANNOTATIONS_ARRAY_BOUNDARY_NOT_FOUND")
    payload = text[start:end + 1]
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        raise ValueError(f"ANNOTATIONS_STRICT_JSON_FAILED:{e.lineno}:{e.colno}:{e.msg}") from e
    if not isinstance(data, list):
        raise ValueError("ANNOTATIONS_TOP_LEVEL_NOT_LIST")
    names: list[str] = []
    malformed: list[dict[str, Any]] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            malformed.append({"index": i, "type": type(item).__name__})
            continue
        names.append(item["name"])
    counts = Counter(names)
    duplicates = [{"name": k, "count": n} for k, n in sorted(counts.items()) if n > 1]
    full_sha = hashlib.sha256(raw).hexdigest()
    meta = {
        "bytes": len(raw),
        "sha256": full_sha,
        "published_byte_match": len(raw) == ANN_BYTES,
        "published_sha256_prefix_match": full_sha.startswith(ANN_SHA_PREFIX),
        "marker_source_offset": marker_at,
        "json_payload_characters": len(payload),
        "top_level_item_count": len(data),
        "valid_identity_item_count": len(names),
        "unique_identity_count": len(counts),
        "duplicate_identity_count": len(duplicates),
        "duplicate_identities": duplicates,
        "malformed_item_count": len(malformed),
        "malformed_items": malformed,
        "identity_set_sha256_sorted": sha_lines(sorted(counts)),
        "identity_order_sha256": sha_lines(names),
    }
    return names, meta


def fingerprint(ids: list[str], docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sites = Counter(str(docs[k].get("site", "")) for k in ids)
    supports = Counter(str(docs[k].get("support", "")) for k in ids)
    named_matches = {k: sites.get(k, 0) == n for k, n in BRIAKOS_SITES.items()}
    named_sum = sum(sites.get(k, 0) for k in BRIAKOS_SITES)
    other = len(ids) - named_sum
    active_sites = [k for k, n in sites.items() if n > 0]
    full_match = (
        len(ids) == 419
        and len(active_sites) == 15
        and all(named_matches.values())
        and other == 35
    )
    return {
        "document_count": len(ids),
        "site_count": len(active_sites),
        "site_histogram": sites.most_common(),
        "support_histogram": supports.most_common(),
        "named_site_matches": named_matches,
        "named_site_sum": named_sum,
        "other_site_document_count": other,
        "Briakos_full_419_site_fingerprint_match": full_match,
        "intersection_id_set_sha256_sorted": sha_lines(sorted(ids)),
        "intersection_id_order_sha256": sha_lines(ids),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inscriptions", required=True)
    ap.add_argument("--annotations", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    docs, ins_meta = load_lineara_map_v0_4(args.inscriptions)
    ins_ok = ins_meta["bytes"] == INS_BYTES and ins_meta["sha256"] == INS_SHA and ins_meta["loader_id"] == LOADER_ID
    ann_names, ann_meta = load_annotation_identities(args.annotations)
    ann_ok = ann_meta["published_byte_match"] and ann_meta["published_sha256_prefix_match"]

    ann_unique_order = list(dict.fromkeys(ann_names))
    ann_set = set(ann_unique_order)
    doc_set = set(docs)
    intersection = [k for k in ann_unique_order if k in doc_set]
    annotation_only = sorted(ann_set - doc_set)
    inscription_only = sorted(doc_set - ann_set)
    fp = fingerprint(intersection, docs)

    if not ins_ok or not ann_ok:
        status = "SOURCE_IDENTITY_BLOCKED"
    elif ann_meta["duplicate_identity_count"] == 0 and fp["Briakos_full_419_site_fingerprint_match"]:
        status = "EXACT_IDENTITY_SCOPE_CANDIDATE"
    elif intersection:
        status = "IDENTITY_LAYER_RELATED_BUT_NOT_SCOPE"
    else:
        status = "NO_IDENTITY_OVERLAP"

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1E-ANNOTATION-IDENTITY-BRIDGE-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "identity_only_source_bridge_result",
        "status": status,
        "frozen_spec": "data/JANUS-LINEAR-A-R3C-1E-ANNOTATION-IDENTITY-BRIDGE-SPEC-2026-08-14-v0.1.json",
        "inscriptions": ins_meta,
        "inscription_source_identity_admitted": ins_ok,
        "annotations": ann_meta,
        "annotation_source_identity_admitted": ann_ok,
        "bridge": {
            "matching": "exact annotation top-level item.name == effective inscription key",
            "semantic_tag_values_used_for_selection": False,
            "transliteratedWord_values_used_for_selection": False,
            "annotation_unique_identity_count": len(ann_set),
            "inscription_effective_identity_count": len(doc_set),
            "intersection_count": len(intersection),
            "annotation_only_count": len(annotation_only),
            "annotation_only_ids": annotation_only,
            "inscription_only_count": len(inscription_only),
            "inscription_only_ids": inscription_only,
            "intersection_fingerprint": fp,
        },
        "grading": {
            "identity_uniqueness_pass": ann_meta["duplicate_identity_count"] == 0,
            "intersection_equals_419": len(intersection) == 419,
            "site_fingerprint_match": fp["Briakos_full_419_site_fingerprint_match"],
            "Briakos_usage_of_this_bridge_claimed": False,
        },
        "claim_ceiling": {
            "source_native_manifest_candidate_only": True,
            "Briakos_parser_reconstructed": False,
            "R3B_effect": "NONE",
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "ins_ok": ins_ok,
        "ann_ok": ann_ok,
        "ann_bytes": ann_meta["bytes"],
        "ann_sha": ann_meta["sha256"],
        "ann_unique": len(ann_set),
        "intersection": len(intersection),
        "site_match": fp["Briakos_full_419_site_fingerprint_match"],
        "site_histogram": fp["site_histogram"],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
