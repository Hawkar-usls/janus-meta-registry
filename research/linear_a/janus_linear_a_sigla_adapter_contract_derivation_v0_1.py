#!/usr/bin/env python3
"""Derive a conservative SigLA source-adapter contract candidate from a frozen Actions artifact.

This is a non-scientific derivation stage. It never accesses mwenge transcription content and
never refetches SigLA. It reparses only the exact HTML snapshots stored in the immutable
word-view probe artifact, verifies them against the embedded probe JSON, and emits only
three-way structural intersections.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from html.parser import HTMLParser
from pathlib import Path

SPEC_PATH = "data/JANUS-LINEAR-A-SIGLA-SOURCE-ADAPTER-CONTRACT-DERIVATION-SPEC-2026-08-14-v0.1.json"
EXPECTED_PROBE_UUID = "JANUS-LINEAR-A-SIGLA-WORD-VIEW-INTERFACE-PROBE-RESULT-2026-08-14-v0.1"
EXPECTED_DOCUMENTS = ["ZA10b", "KNZb5", "KHWc2012"]
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


class FrozenWordViewParser(HTMLParser):
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


def parse_snapshot(path: Path):
    p = FrozenWordViewParser()
    p.feed(path.read_text(encoding="utf-8", errors="replace"))
    return {
        "anchors": p.anchors,
        "scripts": p.scripts,
        "stylesheets": p.stylesheets,
        "class_id_attributes": p.class_id_attributes,
        "tag_frequency": dict(sorted(p.tag_frequency.items())),
        "class_frequency": dict(sorted(p.class_frequency.items())),
        "data_attributes": p.data_attributes,
        "visible_marker_counts": marker_counts(p.text_blocks),
        "ordered_nonempty_visible_text_blocks": p.text_blocks,
    }


def find_unique(root: Path, filename: str) -> Path:
    matches = list(root.rglob(filename))
    if len(matches) != 1:
        raise SystemExit(f"ARTIFACT_FILE_RESOLUTION_FAIL:{filename}:{len(matches)}")
    return matches[0]


def intersection(sets):
    if not sets:
        return []
    out = set(sets[0])
    for s in sets[1:]:
        out &= set(s)
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-root", required=True)
    ap.add_argument("--spec", default=SPEC_PATH)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    if spec.get("status") != "FROZEN_BEFORE_ADAPTER_CONTRACT_DERIVATION":
        raise SystemExit("SPEC_STATUS_FAIL")
    if spec.get("scientific_claim_bearing") is not False:
        raise SystemExit("SPEC_CLAIM_FLAG_FAIL")

    root = Path(args.artifact_root)
    probe_path = find_unique(
        root,
        "JANUS-LINEAR-A-SIGLA-WORD-VIEW-INTERFACE-PROBE-RESULT-2026-08-14-v0.1.json",
    )
    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    if probe.get("artifact_uuid") != EXPECTED_PROBE_UUID:
        raise SystemExit("PROBE_UUID_FAIL")
    if probe.get("status") != "WORD_VIEW_INTERFACE_PROBE_EXECUTED_SUCCESS":
        raise SystemExit("PROBE_STATUS_FAIL")
    if probe.get("scientific_claim_bearing") is not False:
        raise SystemExit("PROBE_CLAIM_FLAG_FAIL")
    if probe.get("pre_fetch_gate", {}).get("all_three_root_hashes_exactly_match_parent_freeze") is not True:
        raise SystemExit("PROBE_ROOT_HASH_GATE_FAIL")

    pages = probe.get("pages") or []
    if [x.get("bridge_key") for x in pages] != EXPECTED_DOCUMENTS:
        raise SystemExit("PROBE_DOCUMENT_SET_FAIL")

    expected_roots = spec["derivation_input"]["expected_root_hashes"]
    reparsed = []
    for page in pages:
        key = page["bridge_key"]
        rr = page["root_refetch"]
        if rr.get("expected_sha256") != expected_roots[key]:
            raise SystemExit(f"ROOT_EXPECTED_SHA_FAIL:{key}")
        if rr.get("observed_sha256") != expected_roots[key] or rr.get("exact_hash_match") is not True:
            raise SystemExit(f"ROOT_OBSERVED_SHA_FAIL:{key}")

        word = page["word_view"]
        snap = find_unique(root, word["snapshot_filename"])
        observed = parse_snapshot(snap)
        for field in spec["predeclared_derivation_rules"]["recomputed_observables_must_equal_probe_result"]:
            if observed[field] != word[field]:
                raise SystemExit(f"REPARSE_MISMATCH:{key}:{field}")
        reparsed.append({"bridge_key": key, "snapshot": snap.name, "observed": observed})

    common_script_src = intersection([
        {x.get("src") for x in r["observed"]["scripts"] if x.get("src")}
        for r in reparsed
    ])
    common_stylesheet_href = intersection([
        {x.get("href") for x in r["observed"]["stylesheets"] if x.get("href")}
        for r in reparsed
    ])
    common_tag_names = intersection([
        set(r["observed"]["tag_frequency"].keys()) for r in reparsed
    ])
    common_class_names = intersection([
        set(r["observed"]["class_frequency"].keys()) for r in reparsed
    ])
    common_anchor_texts = intersection([
        {x.get("text") for x in r["observed"]["anchors"] if x.get("text")}
        for r in reparsed
    ])

    candidate = {
        "artifact_uuid": "JANUS-LINEAR-A-SIGLA-SOURCE-ADAPTER-CONTRACT-CANDIDATE-2026-08-14-v0.1",
        "version": "v0.1",
        "title": "JANUS Linear A SigLA source-adapter contract candidate derived from frozen word-view evidence",
        "node_type": "mechanically_derived_technical_contract_candidate",
        "status": "ADAPTER_CONTRACT_CANDIDATE_DERIVED_FROM_FROZEN_ARTIFACT",
        "scientific_claim_bearing": False,
        "derivation_spec": {"path": SPEC_PATH},
        "source_artifact": spec["immutable_actions_artifact"],
        "validation": {
            "embedded_probe_result_validated": True,
            "all_three_root_hashes_validated": True,
            "all_three_word_view_snapshots_reparsed": True,
            "all_predeclared_observables_equal_embedded_probe_result": True,
            "mwenge_content_accessed": False,
            "live_sigla_refetch_used": False,
            "documents": EXPECTED_DOCUMENTS,
        },
        "contract_candidate": {
            "word_view_relative_route": spec["derivation_input"]["word_view_relative_route"],
            "required_common_script_src": common_script_src,
            "required_common_stylesheet_href": common_stylesheet_href,
            "required_common_tag_names": common_tag_names,
            "required_common_class_names": common_class_names,
            "required_common_nonempty_anchor_texts": common_anchor_texts,
            "source_native_text_order_required": True,
            "fallback_guessing_forbidden": True,
            "derivation_rule": "THREE_WAY_EXACT_SET_INTERSECTION_ONLY",
        },
        "support_summary": {
            "sample_size": 3,
            "common_script_src_count": len(common_script_src),
            "common_stylesheet_href_count": len(common_stylesheet_href),
            "common_tag_name_count": len(common_tag_names),
            "common_class_name_count": len(common_class_names),
            "common_nonempty_anchor_text_count": len(common_anchor_texts),
        },
        "epistemic_gate": {
            "adapter_contract_candidate_derived": True,
            "sigla_source_adapter_contract_frozen": False,
            "cross_digitization_content_replication_established": False,
            "external_transcription_replication_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NO_PROMOTION",
        },
        "required_next": [
            "Inspect the mechanically derived candidate without adding posthoc invariants.",
            "Freeze a minimal fail-closed SigLA source-adapter contract v0.1 from this candidate.",
            "Only after adapter freeze, predeclare deterministic content-audit sampling and comparison observables over the 686 collision-free identity bridge pairs.",
        ],
        "claim_ceiling": {
            "adapter_contract_candidate_derived": True,
            "sigla_source_adapter_contract_frozen": False,
            "cross_digitization_content_replication_established": False,
            "external_transcription_replication_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "BLOCKED",
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(candidate["support_summary"], sort_keys=True))


if __name__ == "__main__":
    main()
