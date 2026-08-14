#!/usr/bin/env python3
"""JANUS Linear A SigLA technical interface probe v0.1.

Non-scientific interface reconnaissance. Three document pages are selected deterministically
from the frozen 686-pair bridge before any document content is fetched. The probe records only
HTTP/DOM/interface observables needed to freeze a later source adapter.
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
import janus_linear_a_sigla_document_bridge_v0_1 as bridge

SPEC_PATH = "data/JANUS-LINEAR-A-SIGLA-INTERFACE-PROBE-SPEC-2026-08-14-v0.1.json"
SPEC_COMMIT = "30ac55582efabda0ebbcbed87e66d2fdfe50c286"
NAMESPACE = "R3A3-INTERFACE-PROBE-v0.1"
SAMPLE_SIZE = 3
FROZEN_SIGLA_SHA256 = "c1d25f91dccf334c3cf24b52c1e4a279970cebd3f5c6f377569de076360170cd"


class InterfaceParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self.scripts = []
        self.forms = []
        self.links = []
        self.data_attributes = []
        self.text_parts = []
        self._anchor = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        amap = dict(attrs)
        for k, v in attrs:
            if k.lower().startswith("data-"):
                self.data_attributes.append({"tag": tag, "name": k, "value": v})
        if tag == "a":
            self._anchor = {"href": amap.get("href"), "text_parts": []}
        elif tag == "script":
            self.scripts.append({"src": amap.get("src"), "type": amap.get("type")})
        elif tag == "form":
            self.forms.append({"action": amap.get("action"), "method": amap.get("method")})
        elif tag == "link":
            self.links.append({"href": amap.get("href"), "rel": amap.get("rel"), "type": amap.get("type")})

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._anchor is not None:
            text = re.sub(r"\s+", " ", " ".join(self._anchor["text_parts"])).strip()
            self.anchors.append({"href": self._anchor["href"], "text": text})
            self._anchor = None

    def handle_data(self, data):
        if not data:
            return
        self.text_parts.append(data)
        if self._anchor is not None:
            self._anchor["text_parts"].append(data)


def score_key(key: str) -> str:
    return hashlib.sha256(f"{NAMESPACE}|{key}".encode("utf-8")).hexdigest()


def reconstruct_bridge(sigla_ids, mwenge_ids):
    smap = bridge.map_by_key(sigla_ids, bridge.sigla_bridge_key)
    mmap = bridge.map_by_key(mwenge_ids, bridge.mwenge_bridge_key)
    scoll = {k for k, v in smap.items() if len(set(v)) > 1}
    mcoll = {k for k, v in mmap.items() if len(set(v)) > 1}
    keys = sorted(k for k in set(smap) & set(mmap) if k not in scoll and k not in mcoll)
    return [
        {"bridge_key": k, "sigla_id": smap[k][0], "mwenge_id": mmap[k][0]}
        for k in keys
    ]


def select_sample(pairs):
    ranked = sorted(
        ({**p, "selection_hash": score_key(p["bridge_key"])} for p in pairs),
        key=lambda x: (x["selection_hash"], x["bridge_key"]),
    )
    return ranked[:SAMPLE_SIZE]


def candidate_interface_values(parsed: InterfaceParser):
    keywords = ("word", "json", "data", "api", "document", "sign", "index")
    rows = []
    for kind, vals, fields in (
        ("anchor", parsed.anchors, ("href", "text")),
        ("script", parsed.scripts, ("src", "type")),
        ("form", parsed.forms, ("action", "method")),
        ("link", parsed.links, ("href", "rel", "type")),
    ):
        for row in vals:
            blob = " ".join(str(row.get(f) or "") for f in fields).lower()
            if any(k in blob for k in keywords):
                rows.append({"kind": kind, **row})
    return rows


def visible_marker_counts(text: str):
    compact = re.sub(r"\s+", " ", text)
    return {
        "word view": len(re.findall(r"word\s+view", compact, flags=re.I)),
        "sign view": len(re.findall(r"sign\s+view", compact, flags=re.I)),
        "signs": len(re.findall(r"\bsigns\b", compact, flags=re.I)),
        "words": len(re.findall(r"\bwords\b", compact, flags=re.I)),
    }


def safe_snapshot_name(rank: int, bridge_key: str) -> str:
    h = hashlib.sha256(bridge_key.encode()).hexdigest()[:12]
    return f"SIGLA-interface-probe-{rank:02d}-{h}.html"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mwenge-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--snapshot-dir", required=True)
    ap.add_argument("--sigla-browse-url", default=inv.DEFAULT_SIGLA_URL)
    args = ap.parse_args()

    # Freeze/select from browse inventory before any document page fetch.
    status, final_url, content_type, browse_body = inv.fetch_bytes(args.sigla_browse_url)
    if status != 200:
        raise SystemExit(f"BROWSE_FETCH_FAIL:{status}")
    browse_sha = hashlib.sha256(browse_body).hexdigest()
    if browse_sha != FROZEN_SIGLA_SHA256:
        raise SystemExit(f"BROWSE_SNAPSHOT_HASH_FAIL:{browse_sha}")
    bp = inv.SigLABrowseParser()
    bp.feed(browse_body.decode("utf-8", errors="replace"))
    sigla_ids = sorted({x for h in bp.document_hrefs if (x := inv.extract_sigla_id_from_href(h))})
    mwenge_ids = inv.inventory_mwenge(Path(args.mwenge_root))
    pairs = reconstruct_bridge(sigla_ids, mwenge_ids)
    if len(pairs) != 686:
        raise SystemExit(f"BRIDGE_RECONSTRUCTION_FAIL:{len(pairs)}")
    selected = select_sample(pairs)

    snapshot_dir = Path(args.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    for rank, item in enumerate(selected, start=1):
        encoded = urllib.parse.quote(item["sigla_id"], safe="")
        requested = f"https://sigla.phis.me/document/{encoded}/"
        st, fin, ctype, body = inv.fetch_bytes(requested)
        if st != 200 or not body:
            raise SystemExit(f"DOCUMENT_FETCH_FAIL:{item['bridge_key']}:{st}:{len(body)}")
        filename = safe_snapshot_name(rank, item["bridge_key"])
        (snapshot_dir / filename).write_bytes(body)
        parsed = InterfaceParser()
        parsed.feed(body.decode("utf-8", errors="replace"))
        visible = " ".join(parsed.text_parts)
        pages.append({
            **item,
            "rank": rank,
            "requested_url": requested,
            "final_url": fin,
            "http_status": st,
            "content_type": ctype,
            "content_length_bytes": len(body),
            "content_sha256": hashlib.sha256(body).hexdigest(),
            "snapshot_filename": filename,
            "anchors": parsed.anchors,
            "scripts": parsed.scripts,
            "forms": parsed.forms,
            "links": parsed.links,
            "data_attributes": parsed.data_attributes,
            "candidate_interface_values": candidate_interface_values(parsed),
            "visible_marker_counts": visible_marker_counts(visible),
        })

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-SIGLA-INTERFACE-PROBE-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "status": "TECHNICAL_INTERFACE_PROBE_EXECUTED",
        "scientific_claim_bearing": False,
        "frozen_spec": {"path": SPEC_PATH, "commit": SPEC_COMMIT},
        "browse_snapshot_sha256": browse_sha,
        "reconstructed_bridge_pair_count": len(pairs),
        "sample_rule": {
            "namespace": NAMESPACE,
            "sample_size": SAMPLE_SIZE,
            "selection": "smallest SHA256(namespace|'|'|bridge_key) before document fetch",
        },
        "selected_documents": pages,
        "epistemic_gate": {
            "technical_interface_probe_established": True,
            "cross_digitization_content_replication_established": False,
            "external_transcription_replication_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NO_PROMOTION",
        },
        "required_next": [
            "Inspect only the observed interface values and freeze an adapter contract; do not infer unobserved routes.",
            "If word-view or JSON/data endpoints are observed consistently, freeze their exact route grammar before content sampling.",
            "Create a separate R3A-3 content sampling specification after the adapter contract is frozen.",
        ],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "bridge_pairs": len(pairs),
        "sample": [{"bridge_key": x["bridge_key"], "hash": x["selection_hash"]} for x in selected],
        "page_hashes": [x["content_sha256"] for x in pages],
        "technical_interface_probe_established": True,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
