#!/usr/bin/env python3
"""Fresh R3C-1E annotation identity bridge recovery v0.1.1.

Execution is allowed only after source reconciliation and parser admission.
Document selection uses annotation top-level `name` only; annotation tags and
word content do not participate in the bridge.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_annotation_parser_validation_v0_1 import extract_array
from janus_linear_a_r3c_common_v0_1 import normalize_js_trailing_commas
from janus_linear_a_r3c_source_loader_v0_4 import LOADER_ID, load_lineara_map_v0_4

INS_BYTES = 1609122
INS_SHA = "b7b383b93db55b504eb00c552a8b18c19a588e83bba7ff0ab93ca32277d8bfe2"
ANN_BYTES_OBS = 2239932
ANN_SHA_OBS = "7ce1f87a98827d059a732cc00506c635b4d5f65b2d0e2f1592fc2b67827758cd"
SOURCE_STATUS = "HASH_LINEAGE_ADMITTED_BYTE_COUNT_CLASSIFIED_AS_PUBLISHED_METADATA_CONFLICT"
PARSER_STATUS = "ANNOTATION_PARSER_ADMITTED"
BRIAKOS_SITES = {
    "Haghia Triada": 185,
    "Khania": 103,
    "Zakros": 44,
    "Phaistos": 41,
    "Knossos": 11,
}


def sha_lines(values: list[str]) -> str:
    return hashlib.sha256(("\n".join(values) + "\n").encode("utf-8")).hexdigest()


def load_annotation_names(path: str | Path) -> tuple[list[str], dict[str, Any]]:
    p = Path(path)
    raw = p.read_bytes()
    source_ok = len(raw) == ANN_BYTES_OBS and hashlib.sha256(raw).hexdigest() == ANN_SHA_OBS
    payload, boundary = extract_array(raw.decode("utf-8"))
    normalized, removals = normalize_js_trailing_commas(payload)
    data = json.loads(normalized)
    if not isinstance(data, list):
        raise ValueError("ANNOTATION_TOP_LEVEL_NOT_LIST")
    names: list[str] = []
    malformed: list[int] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            malformed.append(i)
            continue
        names.append(item["name"])
    counts = Counter(names)
    duplicates = [{"name": k, "count": n} for k, n in sorted(counts.items()) if n > 1]
    return names, {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "observed_hash_lineage_candidate_match": source_ok,
        "boundary": boundary,
        "trailing_comma_removal_count": len(removals),
        "strict_json_parse_success": True,
        "top_level_item_count": len(data),
        "valid_identity_item_count": len(names),
        "unique_identity_count": len(counts),
        "duplicate_identity_count": len(duplicates),
        "duplicate_identities": duplicates,
        "malformed_identity_item_count": len(malformed),
        "malformed_identity_item_indices": malformed,
        "identity_order_sha256": sha_lines(names),
        "identity_set_sha256_sorted": sha_lines(sorted(counts)),
    }


def fingerprint(intersection: list[str], docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sites = Counter(str(docs[k].get("site", "")) for k in intersection)
    supports = Counter(str(docs[k].get("support", "")) for k in intersection)
    named = {k: sites.get(k, 0) for k in BRIAKOS_SITES}
    named_matches = {k: named[k] == v for k, v in BRIAKOS_SITES.items()}
    named_sum = sum(named.values())
    other = len(intersection) - named_sum
    site_count = sum(1 for n in sites.values() if n)
    full_match = len(intersection) == 419 and site_count == 15 and all(named_matches.values()) and other == 35
    return {
        "document_count": len(intersection),
        "site_count": site_count,
        "site_histogram": sites.most_common(),
        "support_histogram": supports.most_common(),
        "Briakos_named_site_observed": named,
        "Briakos_named_site_matches": named_matches,
        "Briakos_other_ten_sites_combined_observed": other,
        "Briakos_full_419_site_fingerprint_match": full_match,
        "intersection_id_order_sha256": sha_lines(intersection),
        "intersection_id_set_sha256_sorted": sha_lines(sorted(intersection)),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inscriptions", required=True)
    ap.add_argument("--annotations", required=True)
    ap.add_argument("--source-reconciliation", required=True)
    ap.add_argument("--parser-validation", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    source_receipt = json.load(open(args.source_reconciliation, encoding="utf-8"))
    parser_receipt = json.load(open(args.parser_validation, encoding="utf-8"))
    if source_receipt.get("status") != SOURCE_STATUS:
        raise SystemExit("SOURCE_RECONCILIATION_PREREQUISITE_NOT_ADMITTED")
    if parser_receipt.get("status") != PARSER_STATUS:
        raise SystemExit("ANNOTATION_PARSER_PREREQUISITE_NOT_ADMITTED")

    docs, ins_meta = load_lineara_map_v0_4(args.inscriptions)
    ins_ok = ins_meta["bytes"] == INS_BYTES and ins_meta["sha256"] == INS_SHA and ins_meta["loader_id"] == LOADER_ID
    ann_names, ann_meta = load_annotation_names(args.annotations)
    ann_ok = ann_meta["observed_hash_lineage_candidate_match"] and ann_meta["strict_json_parse_success"]

    ann_unique_order = list(dict.fromkeys(ann_names))
    ann_set = set(ann_unique_order)
    doc_set = set(docs)
    intersection = [x for x in ann_unique_order if x in doc_set]
    ann_only = sorted(ann_set - doc_set)
    ins_only = sorted(doc_set - ann_set)
    fp = fingerprint(intersection, docs)
    uniqueness = ann_meta["duplicate_identity_count"] == 0 and ann_meta["malformed_identity_item_count"] == 0

    if not ins_ok or not ann_ok:
        status = "BLOCKED_RECOVERY_SOURCE_OR_PARSER_IDENTITY"
    elif uniqueness and fp["Briakos_full_419_site_fingerprint_match"]:
        status = "SOURCE_NATIVE_IDENTITY_MANIFEST_CANDIDATE_MATCHES_BRIAKOS_FINGERPRINT"
    else:
        status = "ANNOTATION_IDENTITY_LAYER_DOES_NOT_RECONSTRUCT_BRIAKOS_CORPUS"

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1E-ANNOTATION-IDENTITY-BRIDGE-RECOVERY-RESULT-2026-08-14-v0.1.1",
        "version": "v0.1.1",
        "node_type": "identity_only_source_bridge_recovery_result",
        "status": status,
        "frozen_recovery_spec": "data/JANUS-LINEAR-A-R3C-1E-ANNOTATION-IDENTITY-BRIDGE-RECOVERY-SPEC-2026-08-14-v0.1.1.json",
        "recovery_lineage": {
            "failed_run": 31809205198,
            "failed_run_scientific_result_inherited": False,
            "fresh_execution": True,
            "source_reconciliation_status": source_receipt["status"],
            "parser_validation_status": parser_receipt["status"],
            "document_selection_rule_changed_from_v0_1": False,
        },
        "inscriptions": ins_meta,
        "inscription_source_admitted": ins_ok,
        "annotations": ann_meta,
        "annotation_hash_lineage_candidate_admitted": ann_ok,
        "published_annotation_byte_count_exact_match_claimed": False,
        "bridge": {
            "rule": "exact annotation top-level item.name == admitted effective inscription key",
            "annotation_semantic_tags_used_for_selection": False,
            "annotation_transliteratedWord_used_for_selection": False,
            "annotation_word_glyphs_used_for_selection": False,
            "annotation_unique_identity_count": len(ann_set),
            "inscription_effective_identity_count": len(doc_set),
            "intersection_count": len(intersection),
            "annotation_only_count": len(ann_only),
            "annotation_only_ids": ann_only,
            "inscription_only_count": len(ins_only),
            "inscription_only_ids": ins_only,
            "fingerprint": fp,
        },
        "grading": {
            "annotation_identity_uniqueness_pass": uniqueness,
            "intersection_equals_419": len(intersection) == 419,
            "site_fingerprint_match": fp["Briakos_full_419_site_fingerprint_match"],
            "Briakos_usage_of_annotation_intersection_claimed": False,
            "posthoc_subset_search_performed": False,
        },
        "claim_ceiling": {
            "source_native_manifest_candidate_only": True,
            "Briakos_parser_reconstructed": False,
            "Briakos_annotation_bridge_usage_proved": False,
            "published_byte_count_exact_source_proved": False,
            "R3B_effect": "NONE",
            "independent_transcription_replication": False,
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "ann_unique": len(ann_set),
        "intersection": len(intersection),
        "duplicates": ann_meta["duplicate_identity_count"],
        "site_match": fp["Briakos_full_419_site_fingerprint_match"],
        "site_histogram": fp["site_histogram"],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
