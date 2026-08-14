#!/usr/bin/env python3
"""JANUS Linear A SigLA frozen word-view structural schema probe v0.1.

This technical stage consumes only the immutable Actions artifact from the prior word-view
probe. It derives DOM structural signatures under the unique `.document-view` container.
It does not fetch SigLA, access mwenge transcription content, or assign linguistic meaning.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path

SPEC_PATH = "data/JANUS-LINEAR-A-SIGLA-WORD-VIEW-STRUCTURAL-SCHEMA-PROBE-SPEC-2026-08-14-v0.1.json"
PROBE_RESULT_NAME = "JANUS-LINEAR-A-SIGLA-WORD-VIEW-INTERFACE-PROBE-RESULT-2026-08-14-v0.1.json"
EXPECTED_DOCS = ["ZA10b", "KNZb5", "KHWc2012"]
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
}
SKIP_TEXT_TAGS = {"script", "style"}
SELECTOR_RE = re.compile(r"(?:^|/)index-[0-9]+\.html(?:$|[?#])")


class Node:
    __slots__ = ("tag", "attrs", "parent", "children", "texts")

    def __init__(self, tag: str, attrs=None, parent=None):
        self.tag = tag.lower()
        self.attrs = dict(attrs or [])
        self.parent = parent
        self.children = []
        self.texts = []

    @property
    def classes(self):
        return tuple(sorted(x for x in (self.attrs.get("class") or "").split() if x))

    def component(self):
        return self.tag + "".join(f".{c}" for c in self.classes)


class TreeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("__root__")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag.lower() not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        normalized = re.sub(r"\s+", " ", data).strip()
        if normalized and self.stack[-1].tag not in SKIP_TEXT_TAGS:
            self.stack[-1].texts.append(normalized)


def walk(node):
    yield node
    for child in node.children:
        yield from walk(child)


def descendants(node):
    for child in node.children:
        yield child
        yield from descendants(child)


def find_unique_file(root: Path, filename: str) -> Path:
    matches = list(root.rglob(filename))
    if len(matches) != 1:
        raise SystemExit(f"ARTIFACT_FILE_RESOLUTION_FAIL:{filename}:{len(matches)}")
    return matches[0]


def relative_path(node: Node, container: Node) -> str:
    parts = []
    cur = node
    while cur is not None:
        parts.append(cur.component())
        if cur is container:
            return ">".join(reversed(parts))
        cur = cur.parent
    raise RuntimeError("NODE_OUTSIDE_CONTAINER")


def visible_text_stats(node: Node):
    leaf_count = 0
    char_count = 0
    for n in walk(node):
        if n.tag in SKIP_TEXT_TAGS:
            continue
        for text in n.texts:
            leaf_count += 1
            char_count += len(text)
    return leaf_count, char_count


def descendant_shape_stats(node: Node):
    anchor_count = 0
    selector_count = 0
    svg_count = 0
    image_count = 0
    for n in descendants(node):
        if n.tag == "a":
            anchor_count += 1
            href = n.attrs.get("href") or ""
            if SELECTOR_RE.search(href):
                selector_count += 1
        elif n.tag == "svg":
            svg_count += 1
        elif n.tag in {"img", "image"}:
            image_count += 1
    return anchor_count, selector_count, svg_count, image_count


def page_structure(snapshot: Path, bridge_key: str):
    parser = TreeParser()
    parser.feed(snapshot.read_text(encoding="utf-8", errors="replace"))
    all_nodes = list(walk(parser.root))
    containers = [n for n in all_nodes if "document-view" in n.classes]
    if len(containers) != 1:
        raise SystemExit(f"DOCUMENT_VIEW_CONTAINER_COUNT_FAIL:{bridge_key}:{len(containers)}")
    container = containers[0]

    aggregate = {}
    sibling_counts = collections.Counter()
    for n in walk(container):
        path = relative_path(n, container)
        depth = path.count(">")
        text_leaves, text_chars = visible_text_stats(n)
        anchors, selector_anchors, svgs, images = descendant_shape_stats(n)
        child_multiset = collections.Counter(c.component() for c in n.children)

        row = aggregate.setdefault(path, {
            "occurrence_count": 0,
            "maximum_relative_depth": depth,
            "visible_text_leaf_count": 0,
            "visible_text_character_count": 0,
            "anchor_descendant_count": 0,
            "index_N_anchor_descendant_count": 0,
            "svg_descendant_count": 0,
            "img_or_image_descendant_count": 0,
            "direct_child_signature_multiset": collections.Counter(),
        })
        row["occurrence_count"] += 1
        row["maximum_relative_depth"] = max(row["maximum_relative_depth"], depth)
        row["visible_text_leaf_count"] += text_leaves
        row["visible_text_character_count"] += text_chars
        row["anchor_descendant_count"] += anchors
        row["index_N_anchor_descendant_count"] += selector_anchors
        row["svg_descendant_count"] += svgs
        row["img_or_image_descendant_count"] += images
        row["direct_child_signature_multiset"].update(child_multiset)

        for child in n.children:
            sibling_counts[(path, child.component())] += 1

    serial = {}
    for path, row in aggregate.items():
        row = dict(row)
        row["direct_child_signature_multiset"] = dict(sorted(row["direct_child_signature_multiset"].items()))
        serial[path] = row

    return {
        "bridge_key": bridge_key,
        "snapshot_filename": snapshot.name,
        "document_view_component": container.component(),
        "relative_paths": dict(sorted(serial.items())),
        "sibling_signatures": [
            {"parent_relative_path": p, "child_component": c, "occurrence_count": count}
            for (p, c), count in sorted(sibling_counts.items())
        ],
    }


def common_keys(page_maps):
    common = set(page_maps[0])
    for m in page_maps[1:]:
        common &= set(m)
    return sorted(common)


def candidate_priority(family: str):
    return {
        "COMMON_SELECTOR_BEARING_PATH": 0,
        "COMMON_REPEATED_PATH": 1,
        "COMMON_PATH": 2,
    }[family]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-root", required=True)
    ap.add_argument("--spec", default=SPEC_PATH)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    if spec.get("status") != "FROZEN_BEFORE_STRUCTURAL_SCHEMA_PROBE":
        raise SystemExit("SPEC_STATUS_FAIL")
    if spec.get("scientific_claim_bearing") is not False:
        raise SystemExit("SPEC_CLAIM_FLAG_FAIL")

    root = Path(args.artifact_root)
    probe_path = find_unique_file(root, PROBE_RESULT_NAME)
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    if probe.get("status") != "WORD_VIEW_INTERFACE_PROBE_EXECUTED_SUCCESS":
        raise SystemExit("PARENT_PROBE_STATUS_FAIL")
    if probe.get("scientific_claim_bearing") is not False:
        raise SystemExit("PARENT_PROBE_CLAIM_FLAG_FAIL")
    pages = probe.get("pages") or []
    if [x.get("bridge_key") for x in pages] != EXPECTED_DOCS:
        raise SystemExit("PARENT_PROBE_DOCUMENT_ORDER_FAIL")

    page_results = []
    for page in pages:
        word = page["word_view"]
        snapshot = find_unique_file(root, word["snapshot_filename"])
        page_results.append(page_structure(snapshot, page["bridge_key"]))

    maps = [x["relative_paths"] for x in page_results]
    common_paths = common_keys(maps)
    candidates = []
    for path in common_paths:
        rows = [m[path] for m in maps]
        counts = [r["occurrence_count"] for r in rows]
        selectors = [r["index_N_anchor_descendant_count"] for r in rows]
        depth = max(r["maximum_relative_depth"] for r in rows)

        families = ["COMMON_PATH"]
        if any(c >= 2 for c in counts):
            families.append("COMMON_REPEATED_PATH")
        if all(s >= 1 for s in selectors):
            families.append("COMMON_SELECTOR_BEARING_PATH")

        for family in families:
            candidates.append({
                "family": family,
                "relative_path": path,
                "relative_depth": depth,
                "occurrence_counts": dict(zip(EXPECTED_DOCS, counts)),
                "index_N_anchor_descendant_counts": dict(zip(EXPECTED_DOCS, selectors)),
                "visible_text_leaf_counts": dict(zip(
                    EXPECTED_DOCS,
                    [r["visible_text_leaf_count"] for r in rows],
                )),
            })

    candidates.sort(key=lambda x: (
        candidate_priority(x["family"]),
        -x["relative_depth"],
        x["relative_path"],
    ))

    sibling_sets = []
    sibling_maps = []
    for pr in page_results:
        smap = {
            (x["parent_relative_path"], x["child_component"]): x["occurrence_count"]
            for x in pr["sibling_signatures"]
        }
        sibling_maps.append(smap)
        sibling_sets.append(set(smap))
    common_sibling = set(sibling_sets[0])
    for s in sibling_sets[1:]:
        common_sibling &= s
    common_sibling_rows = [
        {
            "parent_relative_path": parent,
            "child_component": child,
            "occurrence_counts": {
                doc: sibling_maps[i][(parent, child)] for i, doc in enumerate(EXPECTED_DOCS)
            },
        }
        for parent, child in sorted(common_sibling)
    ]

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-SIGLA-WORD-VIEW-STRUCTURAL-SCHEMA-PROBE-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "title": "JANUS Linear A SigLA frozen word-view structural schema probe result",
        "node_type": "technical_structural_schema_probe_result",
        "status": "STRUCTURAL_SCHEMA_PROBE_EXECUTED_SUCCESS",
        "scientific_claim_bearing": False,
        "frozen_spec": {"path": SPEC_PATH},
        "source_artifact": spec["immutable_input"],
        "validation": {
            "live_sigla_fetch_used": False,
            "mwenge_content_accessed": False,
            "document_view_container_count_per_page": {d: 1 for d in EXPECTED_DOCS},
            "documents": EXPECTED_DOCS,
        },
        "page_structures": page_results,
        "common_relative_path_count": len(common_paths),
        "mechanical_candidates": candidates,
        "common_sibling_signatures": common_sibling_rows,
        "interpretation_boundary": {
            "candidate_is_word_boundary": False,
            "candidate_is_sign_boundary": False,
            "candidate_is_morpheme_boundary": False,
            "statement": "Candidates are DOM-structural recurrences only. No linguistic unit identity is assigned by this gate.",
        },
        "epistemic_gate": {
            "structural_schema_probe_established": True,
            "content_extraction_grammar_frozen": False,
            "cross_digitization_content_replication_established": False,
            "external_transcription_replication_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NO_PROMOTION",
        },
        "required_next": [
            "Inspect only the mechanically ranked structural candidates and freeze the smallest extraction grammar justified by source-native structure.",
            "Validate the frozen extraction grammar on a fresh deterministic hash-selected SigLA-only interface-validation subset before any mwenge comparison.",
            "Keep punctuation, numeric, fraction and uncertainty structure source-native until a separate normalization gate is frozen.",
        ],
        "claim_ceiling": {
            "structural_schema_probe_established": True,
            "content_extraction_grammar_frozen": False,
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
    print(json.dumps({
        "common_relative_path_count": len(common_paths),
        "candidate_count": len(candidates),
        "top_candidates": candidates[:10],
        "common_sibling_signature_count": len(common_sibling_rows),
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
