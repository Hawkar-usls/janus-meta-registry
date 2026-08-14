#!/usr/bin/env python3
"""JANUS Linear A SigLA word-class structural bijection audit v0.1.

Consumes only the immutable structural-capability Actions artifact. For the exactly 19 frozen
capability-positive pages it tests count parity and exact DOM fragment-reference identity between
popup span.word nodes and SVG a.word nodes. Literal transcription payload is never extracted.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import janus_linear_a_sigla_structural_schema_probe_v0_1 as structural

SPEC_PATH = "data/JANUS-LINEAR-A-SIGLA-WORD-UNIT-BIJECTION-AUDIT-SPEC-2026-08-14-v0.1.json"
PARENT_RESULT_NAME = "JANUS-LINEAR-A-SIGLA-STRUCTURAL-CAPABILITY-INVENTORY-RESULT-2026-08-14-v0.1.json"
EXPECTED_POSITIVE = 19


def find_unique(root: Path, filename: str) -> Path:
    matches = list(root.rglob(filename))
    if len(matches) != 1:
        raise SystemExit(f"ARTIFACT_FILE_RESOLUTION_FAIL:{filename}:{len(matches)}")
    return matches[0]


def ancestor_has_tag(node, tag: str, stop):
    cur = node.parent
    while cur is not None and cur is not stop:
        if cur.tag == tag:
            return True
        cur = cur.parent
    return False


def audit_snapshot(path: Path, bridge_key: str):
    parser = structural.TreeParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    nodes = list(structural.walk(parser.root))
    containers = [n for n in nodes if "document-view" in n.classes]
    if len(containers) != 1:
        raise SystemExit(f"DOCUMENT_VIEW_CONTAINER_COUNT_FAIL:{bridge_key}:{len(containers)}")
    container = containers[0]
    under = list(structural.walk(container))

    popup_words = [
        n for n in under
        if n.tag == "span" and {"popup", "word"}.issubset(set(n.classes))
    ]
    svg_word_anchors = [
        n for n in under
        if n.tag == "a" and "word" in n.classes and ancestor_has_tag(n, "svg", container)
    ]

    popup_ids = [n.attrs.get("id") or "" for n in popup_words]
    svg_hrefs = [n.attrs.get("href") or "" for n in svg_word_anchors]
    svg_fragments = [href[1:] if href.startswith("#") else "" for href in svg_hrefs]

    popup_id_full = bool(popup_ids) and all(popup_ids)
    svg_fragment_full = bool(svg_fragments) and all(svg_fragments)
    popup_id_unique = popup_id_full and len(set(popup_ids)) == len(popup_ids)
    svg_fragment_unique = svg_fragment_full and len(set(svg_fragments)) == len(svg_fragments)
    count_parity = len(popup_words) == len(svg_word_anchors) and len(popup_words) > 0
    exact_bijection = (
        count_parity
        and popup_id_unique
        and svg_fragment_unique
        and set(popup_ids) == set(svg_fragments)
    )

    return {
        "bridge_key": bridge_key,
        "snapshot_filename": path.name,
        "popup_word_count": len(popup_words),
        "svg_word_anchor_count": len(svg_word_anchors),
        "popup_left_count": sum(1 for n in popup_words if "popup-left" in n.classes),
        "popup_right_count": sum(1 for n in popup_words if "popup-right" in n.classes),
        "svg_even_count": sum(1 for n in svg_word_anchors if "even" in n.classes),
        "svg_odd_count": sum(1 for n in svg_word_anchors if "odd" in n.classes),
        "popup_ids": popup_ids,
        "svg_hrefs": svg_hrefs,
        "count_parity": count_parity,
        "popup_id_full_coverage": popup_id_full,
        "popup_id_unique": popup_id_unique,
        "svg_fragment_full_coverage": svg_fragment_full,
        "svg_fragment_unique": svg_fragment_unique,
        "exact_fragment_reference_bijection": exact_bijection,
        "literal_transcription_payload_extracted": False,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-root", required=True)
    ap.add_argument("--spec", default=SPEC_PATH)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    if spec.get("status") != "FROZEN_BEFORE_WORD_UNIT_BIJECTION_AUDIT":
        raise SystemExit("SPEC_STATUS_FAIL")
    if spec.get("scientific_claim_bearing") is not False:
        raise SystemExit("SPEC_CLAIM_FLAG_FAIL")
    if spec["parent_inventory"]["capability_positive_count"] != EXPECTED_POSITIVE:
        raise SystemExit("SPEC_POSITIVE_COUNT_FAIL")

    root = Path(args.artifact_root)
    parent_path = find_unique(root, PARENT_RESULT_NAME)
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    if parent.get("status") != "STRUCTURAL_CAPABILITY_INVENTORY_EXECUTED":
        raise SystemExit("PARENT_STATUS_FAIL")
    if parent.get("scientific_claim_bearing") is not False:
        raise SystemExit("PARENT_CLAIM_FLAG_FAIL")
    if parent.get("summary", {}).get("sample_size") != 32:
        raise SystemExit("PARENT_SAMPLE_SIZE_FAIL")
    if parent.get("summary", {}).get("word_class_present_count") != EXPECTED_POSITIVE:
        raise SystemExit("PARENT_POSITIVE_COUNT_FAIL")
    if parent.get("summary", {}).get("word_class_absent_count") != 13:
        raise SystemExit("PARENT_NEGATIVE_COUNT_FAIL")

    positive = [
        row for row in parent.get("documents", [])
        if row.get("structural_observables", {}).get("structural_family") == "WORD_CLASS_SPAN_AND_ANCHOR"
    ]
    if len(positive) != EXPECTED_POSITIVE:
        raise SystemExit(f"POSITIVE_POPULATION_FAIL:{len(positive)}")

    audits = []
    for row in positive:
        word = row.get("word_view") or {}
        if not word.get("adapter_contract", {}).get("pass"):
            raise SystemExit(f"PARENT_WORD_ADAPTER_NOT_PASS:{row['bridge_key']}")
        filename = word.get("snapshot_filename")
        if not filename:
            raise SystemExit(f"PARENT_SNAPSHOT_MISSING:{row['bridge_key']}")
        snap = find_unique(root, filename)
        audits.append(audit_snapshot(snap, row["bridge_key"]))

    count_parity_count = sum(1 for x in audits if x["count_parity"])
    popup_id_full_count = sum(1 for x in audits if x["popup_id_full_coverage"])
    svg_fragment_full_count = sum(1 for x in audits if x["svg_fragment_full_coverage"])
    exact_bijection_count = sum(1 for x in audits if x["exact_fragment_reference_bijection"])
    universal_exact = exact_bijection_count == EXPECTED_POSITIVE

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-SIGLA-WORD-UNIT-BIJECTION-AUDIT-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "title": "JANUS Linear A SigLA source-native word-class structural bijection audit result",
        "node_type": "technical_structural_bijection_audit_result",
        "status": "WORD_UNIT_BIJECTION_AUDIT_EXECUTED",
        "scientific_claim_bearing": False,
        "frozen_spec": {"path": SPEC_PATH},
        "source_artifact": spec["parent_inventory"],
        "population": {
            "frozen_capability_positive_documents": EXPECTED_POSITIVE,
            "audited_documents": [x["bridge_key"] for x in audits],
            "resampling_used": False,
            "replacement_used": False,
            "live_fetch_used": False,
            "mwenge_content_accessed": False,
        },
        "documents": audits,
        "summary": {
            "audited_document_count": EXPECTED_POSITIVE,
            "count_parity_document_count": count_parity_count,
            "popup_id_full_coverage_document_count": popup_id_full_count,
            "svg_fragment_full_coverage_document_count": svg_fragment_full_count,
            "exact_fragment_reference_bijection_document_count": exact_bijection_count,
            "universal_count_parity": count_parity_count == EXPECTED_POSITIVE,
            "universal_exact_fragment_reference_bijection": universal_exact,
        },
        "interpretation_boundary": {
            "structural_reference_bijection_is_linguistic_word_validation": False,
            "left_even_or_right_odd_mapping_inferred": False,
            "literal_transcription_payload_extracted": False,
            "statement": "Only source-native DOM structure and exact fragment-reference identity are tested. No independent linguistic segmentation claim is made.",
        },
        "epistemic_gate": {
            "word_class_structural_bijection_established": universal_exact,
            "content_payload_grammar_frozen": False,
            "cross_digitization_content_replication_established": False,
            "external_transcription_replication_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NO_PROMOTION",
        },
        "required_next": (
            [
                "Freeze the exact popup-id ↔ SVG href-fragment relation as the source-native structural unit relation for capability-positive SigLA pages.",
                "Probe popup descendant payload structure separately before extracting literal transcription strings.",
                "Validate the eventual payload grammar on a disjoint hash-selected SigLA-only subset before mwenge comparison.",
            ]
            if universal_exact
            else [
                "Do not freeze a universal word-unit relation from this sample.",
                "Predeclare structural subfamilies using only recorded non-content attributes, then validate them independently without posthoc repair.",
            ]
        ),
        "claim_ceiling": {
            "word_class_structural_bijection_established": universal_exact,
            "content_payload_grammar_frozen": False,
            "cross_digitization_content_replication_established": False,
            "external_transcription_replication_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "BLOCKED",
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
