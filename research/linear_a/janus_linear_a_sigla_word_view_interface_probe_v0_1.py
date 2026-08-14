#!/usr/bin/env python3
"""JANUS Linear A SigLA word-view interface probe v0.1.

Non-scientific source-interface reconnaissance for the already frozen three-document
sample. This stage does NOT compare SigLA transcription content with mwenge and does
NOT derive word sequences. It verifies the frozen document-root hashes first, then
records only predeclared DOM/route observables from SigLA's native word view.
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

SPEC_PATH = "data/JANUS-LINEAR-A-SIGLA-WORD-VIEW-INTERFACE-PROBE-SPEC-2026-08-14-v0.1.json"
SPEC_COMMIT = "c22982cfc34fe1525011aadf3a1f801e50b7e55f"

MARKERS = (
    "word",
    "words",
    "sign",
    "signs",
    "syllabogram",
    "logogram",
    "fraction",
    "numeral",
)


class WordViewParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self.scripts = []
        self.stylesheets = []
        self.class_id_attributes = []
        self.data_attributes = []
        self.tag_frequency = collections.Counter()
        self.class_frequency = collections.Counter()
        self.text_blocks = []
        self._anchor = None

    @staticmethod
    def _norm_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        self.tag_frequency[tag] += 1
        amap = dict(attrs)

        classes = [c for c in (amap.get("class") or "").split() if c]
        for cls in classes:
            self.class_frequency[cls] += 1

        if "class" in amap or "id" in amap:
            self.class_id_attributes.append({
                "tag": tag,
                "class": amap.get("class"),
                "id": amap.get("id"),
            })

        for key, value in attrs:
            if key.lower().startswith("data-"):
                self.data_attributes.append({"tag": tag, "name": key, "value": value})

        if tag == "a":
            self._anchor = {"href": amap.get("href"), "text_parts": []}
        elif tag == "script":
            self.scripts.append({"src": amap.get("src"), "type": amap.get("type")})
        elif tag == "link":
            rel = amap.get("rel") or ""
            rel_tokens = {x.lower() for x in rel.split()}
            if "stylesheet" in rel_tokens:
                self.stylesheets.append({
                    "href": amap.get("href"),
                    "rel": rel,
                    "type": amap.get("type"),
                })

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._anchor is not None:
            text = self._norm_text(" ".join(self._anchor["text_parts"]))
            self.anchors.append({"href": self._anchor["href"], "text": text})
            self._anchor = None

    def handle_data(self, data):
        normalized = self._norm_text(data)
        if normalized:
            self.text_blocks.append(normalized)
        if self._anchor is not None:
            self._anchor["text_parts"].append(data)


def marker_counts(text_blocks):
    text = " ".join(text_blocks)
    return {
        marker: len(re.findall(rf"\b{re.escape(marker)}\b", text, flags=re.I))
        for marker in MARKERS
    }


def safe_name(rank: int, bridge_key: str, kind: str) -> str:
    suffix = hashlib.sha256(bridge_key.encode("utf-8")).hexdigest()[:12]
    return f"SIGLA-word-view-probe-{rank:02d}-{suffix}-{kind}.html"


def load_and_validate_spec(path: str):
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    if spec.get("status") != "FROZEN_BEFORE_WORD_VIEW_PROBE_EXECUTION":
        raise SystemExit("SPEC_STATUS_FAIL")
    if spec.get("scientific_claim_bearing") is not False:
        raise SystemExit("SPEC_SCIENTIFIC_CLAIM_FLAG_FAIL")
    sample = spec.get("sample") or []
    if len(sample) != 3:
        raise SystemExit(f"SPEC_SAMPLE_SIZE_FAIL:{len(sample)}")
    if spec.get("route_contract", {}).get("word_view_relative") != "index-word.html":
        raise SystemExit("SPEC_WORD_VIEW_ROUTE_FAIL")
    return spec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default=SPEC_PATH)
    ap.add_argument("--out", required=True)
    ap.add_argument("--snapshot-dir", required=True)
    args = ap.parse_args()

    spec = load_and_validate_spec(args.spec)
    snapshot_dir = Path(args.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    pages = []
    for rank, item in enumerate(spec["sample"], start=1):
        sigla_id = item["sigla_id"]
        bridge_key = item["bridge_key"]
        expected_root_sha = item["root_page_sha256"]
        encoded = urllib.parse.quote(sigla_id, safe="")
        root_url = f"https://sigla.phis.me/document/{encoded}/"

        root_status, root_final, root_type, root_body = inv.fetch_bytes(root_url)
        root_sha = hashlib.sha256(root_body).hexdigest()
        if root_status != 200:
            raise SystemExit(f"ROOT_HTTP_FAIL:{bridge_key}:{root_status}")
        if root_sha != expected_root_sha:
            raise SystemExit(
                f"ROOT_HASH_FAIL:{bridge_key}:expected={expected_root_sha}:observed={root_sha}"
            )

        root_name = safe_name(rank, bridge_key, "root-refetch")
        (snapshot_dir / root_name).write_bytes(root_body)

        word_url = root_url + "index-word.html"
        status, final_url, content_type, body = inv.fetch_bytes(word_url)
        if status != 200 or not body:
            raise SystemExit(f"WORD_VIEW_FETCH_FAIL:{bridge_key}:{status}:{len(body)}")

        word_name = safe_name(rank, bridge_key, "word-view")
        (snapshot_dir / word_name).write_bytes(body)

        parser = WordViewParser()
        parser.feed(body.decode("utf-8", errors="replace"))

        pages.append({
            "rank": rank,
            "bridge_key": bridge_key,
            "sigla_id": sigla_id,
            "root_refetch": {
                "requested_url": root_url,
                "final_url": root_final,
                "http_status": root_status,
                "content_type": root_type,
                "content_length_bytes": len(root_body),
                "expected_sha256": expected_root_sha,
                "observed_sha256": root_sha,
                "exact_hash_match": True,
                "snapshot_filename": root_name,
            },
            "word_view": {
                "requested_url": word_url,
                "final_url": final_url,
                "http_status": status,
                "content_type": content_type,
                "content_length_bytes": len(body),
                "content_sha256": hashlib.sha256(body).hexdigest(),
                "snapshot_filename": word_name,
                "anchors": parser.anchors,
                "scripts": parser.scripts,
                "stylesheets": parser.stylesheets,
                "class_id_attributes": parser.class_id_attributes,
                "tag_frequency": dict(sorted(parser.tag_frequency.items())),
                "class_frequency": dict(sorted(parser.class_frequency.items())),
                "data_attributes": parser.data_attributes,
                "visible_marker_counts": marker_counts(parser.text_blocks),
                "ordered_nonempty_visible_text_blocks": parser.text_blocks,
            },
        })

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-SIGLA-WORD-VIEW-INTERFACE-PROBE-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "status": "WORD_VIEW_INTERFACE_PROBE_EXECUTED_SUCCESS",
        "scientific_claim_bearing": False,
        "frozen_spec": {"path": SPEC_PATH, "commit": SPEC_COMMIT},
        "pre_fetch_gate": {
            "all_three_root_hashes_exactly_match_parent_freeze": True,
            "failure_policy": "FAIL_CLOSED_AND_REQUIRE_NEW_INTERFACE_FREEZE",
        },
        "sample_reused_without_resampling": True,
        "pages": pages,
        "epistemic_gate": {
            "word_view_interface_probe_established": True,
            "sigla_source_adapter_contract_frozen": False,
            "cross_digitization_content_replication_established": False,
            "external_transcription_replication_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NO_PROMOTION",
        },
        "required_next": [
            "Freeze a SigLA source-adapter contract using only observables recorded by this probe.",
            "Require the adapter to fail closed if the frozen route/DOM contract is absent or changes.",
            "Only after adapter freeze, predeclare a separate content-audit sample and comparison observables.",
            "Do not treat SigLA agreement as external transcription replication because SigLA remains an L1 shared-GORILA transcription source.",
        ],
        "claim_ceiling": {
            "word_view_interface_probe_established": True,
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
        "word_view_interface_probe_established": True,
        "documents": [x["bridge_key"] for x in pages],
        "root_hashes_match": [x["root_refetch"]["exact_hash_match"] for x in pages],
        "word_view_hashes": [x["word_view"]["content_sha256"] for x in pages],
        "anchor_counts": [len(x["word_view"]["anchors"]) for x in pages],
        "text_block_counts": [len(x["word_view"]["ordered_nonempty_visible_text_blocks"]) for x in pages],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
