#!/usr/bin/env python3
"""JANUS Linear A SigLA structural capability inventory v0.1.

Selects 32 bridge identities deterministically from the immutable R3A-2 artifact before any
network access, validates the frozen SigLA adapter contract per document, and inventories only
source-native DOM structural features. No mwenge transcription content is read or compared.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

import janus_linear_a_sigla_inventory_audit as inv
import janus_linear_a_sigla_structural_schema_probe_v0_1 as structural

SPEC_PATH = "data/JANUS-LINEAR-A-SIGLA-STRUCTURAL-CAPABILITY-INVENTORY-SPEC-2026-08-14-v0.1.json"
BRIDGE_RESULT_NAME = "JANUS-LINEAR-A-SIGLA-DOCUMENT-IDENTITY-BRIDGE-RESULT-2026-08-14-v0.1.json"
NAMESPACE = "R3A3D-STRUCTURAL-CAPABILITY-v0.1"
SAMPLE_SIZE = 32
REQUIRED_SCRIPTS = {"../../database.js", "../../sigilWeb.bc.js"}
REQUIRED_STYLESHEET = "../../style.css"
REQUIRED_CLASSES = {"document-metadata", "document-view"}


class ContractParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self.scripts = []
        self.stylesheets = []
        self.classes = set()
        self._anchor = None

    @staticmethod
    def norm(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        amap = dict(attrs)
        for cls in (amap.get("class") or "").split():
            if cls:
                self.classes.add(cls)
        if tag == "a":
            self._anchor = {"href": amap.get("href") or "", "parts": []}
        elif tag == "script":
            src = amap.get("src")
            if src:
                self.scripts.append(src)
        elif tag == "link":
            rel = {x.lower() for x in (amap.get("rel") or "").split()}
            href = amap.get("href")
            if "stylesheet" in rel and href:
                self.stylesheets.append(href)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._anchor is not None:
            self.anchors.append({
                "href": self._anchor["href"],
                "text": self.norm(" ".join(self._anchor["parts"])),
            })
            self._anchor = None

    def handle_data(self, data):
        if self._anchor is not None:
            self._anchor["parts"].append(data)


def parse_contract(body: bytes) -> ContractParser:
    p = ContractParser()
    p.feed(body.decode("utf-8", errors="replace"))
    return p


def find_unique(root: Path, filename: str) -> Path:
    matches = list(root.rglob(filename))
    if len(matches) != 1:
        raise SystemExit(f"ARTIFACT_FILE_RESOLUTION_FAIL:{filename}:{len(matches)}")
    return matches[0]


def score_key(key: str) -> str:
    return hashlib.sha256(f"{NAMESPACE}|{key}".encode("utf-8")).hexdigest()


def select_sample(pairs):
    ranked = sorted(
        (
            {
                "bridge_key": p["bridge_key"],
                "sigla_id": p["sigla_id"],
                "selection_hash": score_key(p["bridge_key"]),
            }
            for p in pairs
        ),
        key=lambda x: (x["selection_hash"], x["bridge_key"]),
    )
    return ranked[:SAMPLE_SIZE]


def root_contract(parser: ContractParser):
    anchors = [
        a for a in parser.anchors
        if a["text"] == "[word view]" and a["href"].endswith("index-word.html")
    ]
    return {
        "pass": len(anchors) >= 1,
        "word_view_anchor_count": len(anchors),
    }


def word_view_contract(parser: ContractParser):
    scripts = set(parser.scripts)
    styles = set(parser.stylesheets)
    reciprocal = [a for a in parser.anchors if a["text"] == "[sign view]"]
    missing_scripts = sorted(REQUIRED_SCRIPTS - scripts)
    missing_classes = sorted(REQUIRED_CLASSES - parser.classes)
    missing_style = REQUIRED_STYLESHEET not in styles
    ok = not missing_scripts and not missing_classes and not missing_style and bool(reciprocal)
    return {
        "pass": ok,
        "missing_required_scripts": missing_scripts,
        "missing_required_classes": missing_classes,
        "missing_required_stylesheet": missing_style,
        "reciprocal_sign_view_anchor_count": len(reciprocal),
    }


def structural_observables(body: bytes):
    parser = structural.TreeParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    nodes = list(structural.walk(parser.root))
    containers = [n for n in nodes if "document-view" in n.classes]
    result = {
        "document_view_container_count": len(containers),
        "unique_document_view": len(containers) == 1,
        "word_class_element_count": 0,
        "span_word_count": 0,
        "anchor_word_count": 0,
        "popup_left_word_count": 0,
        "popup_right_word_count": 0,
        "sure_reading_count": 0,
        "svg_descendant_anchor_word_count": 0,
        "word_class_relative_paths": {},
        "structural_family": "NO_UNIQUE_DOCUMENT_VIEW",
    }
    if len(containers) != 1:
        return result

    container = containers[0]
    under = list(structural.walk(container))
    word_nodes = [n for n in under if "word" in n.classes]
    result["word_class_element_count"] = len(word_nodes)
    result["span_word_count"] = sum(1 for n in word_nodes if n.tag == "span")
    result["anchor_word_count"] = sum(1 for n in word_nodes if n.tag == "a")
    result["popup_left_word_count"] = sum(
        1 for n in word_nodes if n.tag == "span" and {"popup", "popup-left", "word"}.issubset(set(n.classes))
    )
    result["popup_right_word_count"] = sum(
        1 for n in word_nodes if n.tag == "span" and {"popup", "popup-right", "word"}.issubset(set(n.classes))
    )
    result["sure_reading_count"] = sum(1 for n in under if "sure-reading" in n.classes)

    svg_nodes = [n for n in under if n.tag == "svg"]
    svg_anchor_word = 0
    for svg in svg_nodes:
        svg_anchor_word += sum(
            1 for n in structural.descendants(svg) if n.tag == "a" and "word" in n.classes
        )
    result["svg_descendant_anchor_word_count"] = svg_anchor_word

    path_counts = collections.Counter(structural.relative_path(n, container) for n in word_nodes)
    result["word_class_relative_paths"] = dict(sorted(path_counts.items()))

    spans = result["span_word_count"] > 0
    anchors = result["anchor_word_count"] > 0
    if spans and anchors:
        family = "WORD_CLASS_SPAN_AND_ANCHOR"
    elif spans:
        family = "WORD_CLASS_SPAN_ONLY"
    elif anchors:
        family = "WORD_CLASS_ANCHOR_ONLY"
    else:
        family = "NO_WORD_CLASS"
    result["structural_family"] = family
    return result


def snapshot_name(rank: int, bridge_key: str, kind: str) -> str:
    digest = hashlib.sha256(bridge_key.encode("utf-8")).hexdigest()[:12]
    return f"SIGLA-capability-{rank:02d}-{digest}-{kind}.html"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bridge-artifact-root", required=True)
    ap.add_argument("--spec", default=SPEC_PATH)
    ap.add_argument("--out", required=True)
    ap.add_argument("--snapshot-dir", required=True)
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    if spec.get("status") != "FROZEN_BEFORE_STRUCTURAL_CAPABILITY_INVENTORY":
        raise SystemExit("SPEC_STATUS_FAIL")
    if spec.get("scientific_claim_bearing") is not False:
        raise SystemExit("SPEC_CLAIM_FLAG_FAIL")
    if spec["sampling"]["namespace"] != NAMESPACE or spec["sampling"]["sample_size"] != SAMPLE_SIZE:
        raise SystemExit("SPEC_SAMPLING_FAIL")

    bridge_root = Path(args.bridge_artifact_root)
    bridge_path = find_unique(bridge_root, BRIDGE_RESULT_NAME)
    bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
    if bridge.get("artifact_uuid") != "JANUS-LINEAR-A-SIGLA-DOCUMENT-IDENTITY-BRIDGE-RESULT-2026-08-14-v0.1":
        raise SystemExit("BRIDGE_UUID_FAIL")
    matched = bridge.get("bridge", {}).get("matched_pairs") or []
    if len(matched) != 686:
        raise SystemExit(f"BRIDGE_PAIR_COUNT_FAIL:{len(matched)}")

    selected = select_sample(matched)
    if len(selected) != SAMPLE_SIZE:
        raise SystemExit("SAMPLE_SIZE_FAIL")

    snapshot_dir = Path(args.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    rows = []

    # IMPORTANT: no network operation occurs before `selected` is fully determined above.
    for rank, item in enumerate(selected, start=1):
        encoded = urllib.parse.quote(item["sigla_id"], safe="")
        root_url = f"https://sigla.phis.me/document/{encoded}/"
        root_status, root_final, root_type, root_body = inv.fetch_bytes(root_url)
        root_sha = hashlib.sha256(root_body).hexdigest()
        root_name = snapshot_name(rank, item["bridge_key"], "root")
        if root_body:
            (snapshot_dir / root_name).write_bytes(root_body)

        root_parser = parse_contract(root_body) if root_body else ContractParser()
        root_gate = root_contract(root_parser) if root_status == 200 and root_body else {
            "pass": False,
            "word_view_anchor_count": 0,
        }
        row = {
            **item,
            "rank": rank,
            "root": {
                "requested_url": root_url,
                "final_url": root_final,
                "http_status": root_status,
                "content_type": root_type,
                "content_length_bytes": len(root_body),
                "content_sha256": root_sha,
                "snapshot_filename": root_name if root_body else None,
                "adapter_contract": root_gate,
            },
            "word_view": None,
            "structural_observables": None,
        }

        if not root_gate["pass"]:
            rows.append(row)
            continue

        word_url = root_url + "index-word.html"
        word_status, word_final, word_type, word_body = inv.fetch_bytes(word_url)
        word_sha = hashlib.sha256(word_body).hexdigest()
        word_name = snapshot_name(rank, item["bridge_key"], "word-view")
        if word_body:
            (snapshot_dir / word_name).write_bytes(word_body)
        word_parser = parse_contract(word_body) if word_body else ContractParser()
        word_gate = word_view_contract(word_parser) if word_status == 200 and word_body else {
            "pass": False,
            "missing_required_scripts": sorted(REQUIRED_SCRIPTS),
            "missing_required_classes": sorted(REQUIRED_CLASSES),
            "missing_required_stylesheet": True,
            "reciprocal_sign_view_anchor_count": 0,
        }
        row["word_view"] = {
            "requested_url": word_url,
            "final_url": word_final,
            "http_status": word_status,
            "content_type": word_type,
            "content_length_bytes": len(word_body),
            "content_sha256": word_sha,
            "snapshot_filename": word_name if word_body else None,
            "adapter_contract": word_gate,
        }
        if word_gate["pass"]:
            row["structural_observables"] = structural_observables(word_body)
        rows.append(row)

    root_pass = sum(1 for x in rows if x["root"]["adapter_contract"]["pass"])
    word_attempted = [x for x in rows if x["word_view"] is not None]
    word_pass = sum(1 for x in word_attempted if x["word_view"]["adapter_contract"]["pass"])
    structural_rows = [x for x in rows if x["structural_observables"] is not None]
    unique_dv = sum(1 for x in structural_rows if x["structural_observables"]["unique_document_view"])
    word_class_present = sum(
        1 for x in structural_rows if x["structural_observables"]["word_class_element_count"] > 0
    )
    family_hist = collections.Counter(
        x["structural_observables"]["structural_family"] for x in structural_rows
    )
    path_doc_support = collections.Counter()
    for x in structural_rows:
        for path in x["structural_observables"]["word_class_relative_paths"]:
            path_doc_support[path] += 1

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-SIGLA-STRUCTURAL-CAPABILITY-INVENTORY-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "title": "JANUS Linear A SigLA structural capability inventory result",
        "node_type": "technical_structural_capability_inventory_result",
        "status": "STRUCTURAL_CAPABILITY_INVENTORY_EXECUTED",
        "scientific_claim_bearing": False,
        "frozen_spec": {"path": SPEC_PATH},
        "selection": {
            "namespace": NAMESPACE,
            "sample_size": SAMPLE_SIZE,
            "selected_before_live_fetch": True,
            "replacement_used": False,
            "documents": [
                {
                    "rank": x["rank"],
                    "bridge_key": x["bridge_key"],
                    "sigla_id": x["sigla_id"],
                    "selection_hash": x["selection_hash"],
                }
                for x in rows
            ],
        },
        "documents": rows,
        "summary": {
            "sample_size": SAMPLE_SIZE,
            "root_adapter_pass_count": root_pass,
            "root_adapter_fail_count": SAMPLE_SIZE - root_pass,
            "word_view_attempt_count": len(word_attempted),
            "word_view_adapter_pass_count": word_pass,
            "word_view_adapter_fail_count": len(word_attempted) - word_pass,
            "structurally_classified_count": len(structural_rows),
            "unique_document_view_count": unique_dv,
            "word_class_present_count": word_class_present,
            "word_class_absent_count": len(structural_rows) - word_class_present,
            "structural_family_histogram": dict(sorted(family_hist.items())),
            "word_class_relative_path_document_support": dict(sorted(path_doc_support.items())),
        },
        "interpretation_boundary": {
            "source_native_word_class_is_linguistic_validation": False,
            "inventory_is_content_replication": False,
            "statement": "This result measures technical prevalence of source-native DOM structures after a frozen adapter gate. It does not validate SigLA's linguistic segmentation and does not compare transcription content across sources.",
        },
        "epistemic_gate": {
            "structural_capability_inventory_established": True,
            "content_extraction_grammar_frozen": False,
            "cross_digitization_content_replication_established": False,
            "external_transcription_replication_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NO_PROMOTION",
        },
        "required_next": [
            "Use only predeclared inventory prevalence and path support to define an eligibility rule for any future source-native word-structure extractor.",
            "Freeze the extractor grammar before validating it on a second disjoint hash-selected SigLA-only subset.",
            "Do not compare with mwenge content until the extractor passes that independent interface-validation subset.",
        ],
        "claim_ceiling": {
            "structural_capability_inventory_established": True,
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
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
