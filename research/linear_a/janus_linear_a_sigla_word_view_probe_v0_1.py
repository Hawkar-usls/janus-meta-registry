#!/usr/bin/env python3
"""JANUS Linear A SigLA native word-view probe v0.1.

Technical, non-claim-bearing probe. Reuses the exact three documents selected by the
preceding content-independent interface probe and freezes the observed SigLA word-view
DOM/assets before any scientific content parser is written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

import janus_linear_a_sigla_inventory_audit as inv

SPEC_PATH = "data/JANUS-LINEAR-A-SIGLA-WORD-VIEW-PROBE-SPEC-2026-08-14-v0.1.json"
SPEC_COMMIT = "d3a89d918f1fa74acbdc8596ebb18cbb27ffc57b"
SAMPLE = [
    {"bridge_key": "ZA10b", "sigla_id": "ZA 10b", "mwenge_id": "ZA10b"},
    {"bridge_key": "KNZb5", "sigla_id": "KN Zb 5", "mwenge_id": "KNZb5"},
    {"bridge_key": "KHWc2012", "sigla_id": "KH Wc 2012", "mwenge_id": "KHWc2012"},
]


class WordViewParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self.images = []
        self.scripts = []
        self.links = []
        self.text_parts = []
        self._anchor = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        amap = dict(attrs)
        if tag == "a":
            self._anchor = {"href": amap.get("href"), "title": amap.get("title"), "class": amap.get("class"), "text_parts": []}
        elif tag == "img":
            self.images.append({"src": amap.get("src"), "alt": amap.get("alt"), "title": amap.get("title"), "class": amap.get("class")})
        elif tag == "script":
            self.scripts.append({"src": amap.get("src"), "type": amap.get("type")})
        elif tag == "link":
            self.links.append({"href": amap.get("href"), "rel": amap.get("rel"), "type": amap.get("type")})

    def handle_data(self, data):
        if not data:
            return
        self.text_parts.append(data)
        if self._anchor is not None:
            self._anchor["text_parts"].append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._anchor is not None:
            row = dict(self._anchor)
            row["text"] = re.sub(r"\s+", " ", " ".join(row.pop("text_parts"))).strip()
            self.anchors.append(row)
            self._anchor = None


def relevant_anchors(rows):
    keys = ("sequence", "word", "sign", "attestation", "search", "index", "document")
    out = []
    for row in rows:
        blob = " ".join(str(row.get(k) or "") for k in ("href", "text", "title", "class")).lower()
        if any(k in blob for k in keys) or (row.get("text") and "-" in row["text"]):
            out.append(row)
    return out


def safe_name(rank: int, key: str) -> str:
    return f"SIGLA-word-view-{rank:02d}-{hashlib.sha256(key.encode()).hexdigest()[:12]}.html"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--snapshot-dir", required=True)
    args = ap.parse_args()

    snap = Path(args.snapshot_dir)
    snap.mkdir(parents=True, exist_ok=True)

    db_status, db_final, db_type, db_body = inv.fetch_bytes("https://sigla.phis.me/database.js")
    if db_status != 200 or not db_body:
        raise SystemExit(f"DATABASE_JS_FETCH_FAIL:{db_status}:{len(db_body)}")

    pages = []
    for rank, item in enumerate(SAMPLE, start=1):
        encoded = urllib.parse.quote(item["sigla_id"], safe="")
        requested = f"https://sigla.phis.me/document/{encoded}/index-word.html"
        status, final_url, content_type, body = inv.fetch_bytes(requested)
        if status != 200 or not body:
            raise SystemExit(f"WORD_VIEW_FETCH_FAIL:{item['bridge_key']}:{status}:{len(body)}")
        filename = safe_name(rank, item["bridge_key"])
        (snap / filename).write_bytes(body)
        parser = WordViewParser()
        parser.feed(body.decode("utf-8", errors="replace"))
        visible = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()
        sign_view = [a for a in parser.anchors if "sign view" in (a.get("text") or "").lower()]
        word_count_match = re.search(r"\b(\d+)\s+words?\b", visible, flags=re.I)
        if not sign_view or not word_count_match:
            raise SystemExit(f"WORD_VIEW_CONTRACT_FAIL:{item['bridge_key']}:sign_view={len(sign_view)}:word_count={bool(word_count_match)}")
        pages.append({
            **item,
            "rank": rank,
            "requested_url": requested,
            "final_url": final_url,
            "http_status": status,
            "content_type": content_type,
            "content_length_bytes": len(body),
            "content_sha256": hashlib.sha256(body).hexdigest(),
            "snapshot_filename": filename,
            "reported_word_count": int(word_count_match.group(1)),
            "anchors": parser.anchors,
            "relevant_anchors": relevant_anchors(parser.anchors),
            "images": parser.images,
            "scripts": parser.scripts,
            "links": parser.links,
            "visible_text": visible,
        })

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-SIGLA-WORD-VIEW-PROBE-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "status": "TECHNICAL_WORD_VIEW_PROBE_EXECUTED",
        "scientific_claim_bearing": False,
        "frozen_spec": {"path": SPEC_PATH, "commit": SPEC_COMMIT},
        "database_js": {
            "requested_url": "https://sigla.phis.me/database.js",
            "final_url": db_final,
            "http_status": db_status,
            "content_type": db_type,
            "bytes": len(db_body),
            "sha256": hashlib.sha256(db_body).hexdigest(),
            "prefix_utf8": db_body[:500].decode("utf-8", errors="replace"),
        },
        "sample_reuse": SAMPLE,
        "pages": pages,
        "epistemic_gate": {
            "technical_word_view_contract_established": True,
            "cross_digitization_content_replication_established": False,
            "external_transcription_replication_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NO_PROMOTION",
        },
        "required_next": [
            "Derive a fail-closed SigLA-native content parser only from recorded word-view/database observables.",
            "Freeze a deterministic scientific sample before content scoring.",
            "Run blind structural-role discovery with identity/function reveal only after scoring.",
        ],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "database_js_sha256": result["database_js"]["sha256"],
        "database_js_bytes": result["database_js"]["bytes"],
        "pages": [
            {
                "bridge_key": p["bridge_key"],
                "word_count": p["reported_word_count"],
                "anchor_count": len(p["anchors"]),
                "relevant_anchor_count": len(p["relevant_anchors"]),
                "image_count": len(p["images"]),
                "sha256": p["content_sha256"],
            }
            for p in pages
        ],
        "technical_word_view_contract_established": True,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
