#!/usr/bin/env python3
"""JANUS Linear A SigLA strict word ordinal bijection audit v0.1.

Tests only exact source-native ordinal syntax: popup ids `word-N` versus SVG word-anchor
routes ending in `index-word-N.html`. The same frozen 19 capability-positive snapshots are
reparsed; no live source, mwenge content, or transcription payload is accessed.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import janus_linear_a_sigla_structural_schema_probe_v0_1 as structural

SPEC_PATH = "data/JANUS-LINEAR-A-SIGLA-WORD-ORDINAL-BIJECTION-AUDIT-SPEC-2026-08-14-v0.1.json"
PARENT_PATH = "data/JANUS-LINEAR-A-SIGLA-WORD-UNIT-BIJECTION-AUDIT-RESULT-2026-08-14-v0.1.json"
EXPECTED_DOCS = 19
POPUP_RE = re.compile(r"^word-([0-9]+)$")
SVG_HREF_RE = re.compile(r"(?:^|/)index-word-([0-9]+)\.html$")


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


def parse_ordinals(snapshot: Path, bridge_key: str):
    parser = structural.TreeParser()
    parser.feed(snapshot.read_text(encoding="utf-8", errors="replace"))
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
    svg_words = [
        n for n in under
        if n.tag == "a" and "word" in n.classes and ancestor_has_tag(n, "svg", container)
    ]

    popup_ids = [n.attrs.get("id") or "" for n in popup_words]
    svg_hrefs = [n.attrs.get("href") or "" for n in svg_words]
    popup_matches = [POPUP_RE.fullmatch(x) for x in popup_ids]
    svg_matches = [SVG_HREF_RE.search(x) for x in svg_hrefs]

    popup_full = bool(popup_ids) and all(m is not None for m in popup_matches)
    svg_full = bool(svg_hrefs) and all(m is not None for m in svg_matches)
    popup_ordinals = [m.group(1) for m in popup_matches if m is not None]
    svg_ordinals = [m.group(1) for m in svg_matches if m is not None]

    popup_unique = popup_full and len(set(popup_ordinals)) == len(popup_ordinals)
    svg_unique = svg_full and len(set(svg_ordinals)) == len(svg_ordinals)
    set_equal = popup_unique and svg_unique and set(popup_ordinals) == set(svg_ordinals)
    sequence_equal = popup_full and svg_full and popup_ordinals == svg_ordinals
    expected = [str(i) for i in range(len(popup_ordinals))]
    zero_based = (
        popup_full
        and svg_full
        and popup_ordinals == expected
        and svg_ordinals == expected
    )
    strict_bijection = set_equal and sequence_equal and zero_based

    return {
        "bridge_key": bridge_key,
        "snapshot_filename": snapshot.name,
        "popup_ids": popup_ids,
        "svg_hrefs": svg_hrefs,
        "popup_ordinal_sequence": popup_ordinals,
        "svg_ordinal_sequence": svg_ordinals,
        "popup_regex_full_coverage": popup_full,
        "svg_href_regex_full_coverage": svg_full,
        "popup_ordinal_unique": popup_unique,
        "svg_ordinal_unique": svg_unique,
        "ordinal_set_bijection": set_equal,
        "document_order_sequence_equality": sequence_equal,
        "zero_based_contiguity": zero_based,
        "strict_ordinal_bijection": strict_bijection,
        "literal_transcription_payload_extracted": False,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-root", required=True)
    ap.add_argument("--spec", default=SPEC_PATH)
    ap.add_argument("--parent", default=PARENT_PATH)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    if spec.get("status") != "FROZEN_BEFORE_WORD_ORDINAL_BIJECTION_AUDIT":
        raise SystemExit("SPEC_STATUS_FAIL")
    if spec.get("scientific_claim_bearing") is not False:
        raise SystemExit("SPEC_CLAIM_FLAG_FAIL")

    parent = json.loads(Path(args.parent).read_text(encoding="utf-8"))
    if parent.get("status") != "WORD_UNIT_BIJECTION_AUDIT_EXECUTED":
        raise SystemExit("PARENT_STATUS_FAIL")
    summary = parent.get("summary", {})
    if summary.get("audited_document_count") != EXPECTED_DOCS:
        raise SystemExit("PARENT_DOC_COUNT_FAIL")
    if summary.get("count_parity_document_count") != EXPECTED_DOCS:
        raise SystemExit("PARENT_COUNT_PARITY_FAIL")
    if summary.get("exact_fragment_reference_bijection_document_count") != 0:
        raise SystemExit("PARENT_FRAGMENT_STATE_FAIL")

    root = Path(args.artifact_root)
    audits = []
    for row in parent.get("documents", []):
        filename = row.get("snapshot_filename")
        if not filename:
            raise SystemExit(f"PARENT_SNAPSHOT_FILENAME_FAIL:{row.get('bridge_key')}")
        snap = find_unique(root, filename)
        audited = parse_ordinals(snap, row["bridge_key"])
        # Reparse integrity: the exact raw id/href lists must reproduce the parent audit.
        if audited["popup_ids"] != row.get("popup_ids"):
            raise SystemExit(f"PARENT_POPUP_REPARSE_MISMATCH:{row['bridge_key']}")
        if audited["svg_hrefs"] != row.get("svg_hrefs"):
            raise SystemExit(f"PARENT_SVG_REPARSE_MISMATCH:{row['bridge_key']}")
        audits.append(audited)

    if len(audits) != EXPECTED_DOCS:
        raise SystemExit(f"AUDIT_POPULATION_FAIL:{len(audits)}")

    def count(field):
        return sum(1 for x in audits if x[field])

    strict_count = count("strict_ordinal_bijection")
    universal = strict_count == EXPECTED_DOCS
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-SIGLA-WORD-ORDINAL-BIJECTION-AUDIT-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "title": "JANUS Linear A SigLA strict word ordinal structural bijection audit result",
        "node_type": "technical_structural_bijection_audit_result",
        "status": "WORD_ORDINAL_BIJECTION_AUDIT_EXECUTED",
        "scientific_claim_bearing": False,
        "frozen_spec": {"path": SPEC_PATH},
        "parent_result": {
            "path": PARENT_PATH,
            "commit": spec["parent_bijection_result"]["commit"],
        },
        "population": {
            "audited_document_count": EXPECTED_DOCS,
            "documents": [x["bridge_key"] for x in audits],
            "resampling_used": False,
            "replacement_used": False,
            "live_fetch_used": False,
            "mwenge_content_accessed": False,
        },
        "documents": audits,
        "summary": {
            "audited_document_count": EXPECTED_DOCS,
            "popup_regex_full_coverage_count": count("popup_regex_full_coverage"),
            "svg_href_regex_full_coverage_count": count("svg_href_regex_full_coverage"),
            "popup_ordinal_unique_count": count("popup_ordinal_unique"),
            "svg_ordinal_unique_count": count("svg_ordinal_unique"),
            "ordinal_set_bijection_count": count("ordinal_set_bijection"),
            "document_order_sequence_equality_count": count("document_order_sequence_equality"),
            "zero_based_contiguity_count": count("zero_based_contiguity"),
            "strict_ordinal_bijection_count": strict_count,
            "universal_strict_ordinal_bijection": universal,
        },
        "technical_relation": {
            "relation": "popup id word-N ↔ SVG href suffix index-word-N.html",
            "ordinal_capture_only": True,
            "normalization_used": [],
            "linguistic_validation": False,
        },
        "epistemic_gate": {
            "word_ordinal_structural_bijection_established": universal,
            "content_payload_grammar_frozen": False,
            "cross_digitization_content_replication_established": False,
            "external_transcription_replication_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NO_PROMOTION",
        },
        "required_next": (
            [
                "Freeze word-N ↔ index-word-N.html as the technical source-native unit-reference relation for capability-positive SigLA pages.",
                "Require this relation as a parser-integrity gate before claim-bearing SigLA word-role scoring.",
                "Probe index-word-N.html and popup payload structure separately before literal transcription extraction.",
            ]
            if universal
            else [
                "Do not freeze a universal ordinal unit-reference relation.",
                "Retain exact failures and predeclare structural subfamilies without posthoc ordinal repair.",
            ]
        ),
        "claim_ceiling": {
            "word_ordinal_structural_bijection_established": universal,
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
