#!/usr/bin/env python3
"""JANUS Linear A R3A-1 SigLA cross-digitization inventory audit.

This is a source/provenance and document-inventory comparison only. It does not compare
transcribed sign values and therefore cannot establish transcription replication.

Frozen spec:
  data/JANUS-LINEAR-A-SIGLA-CROSS-DIGITIZATION-INVENTORY-SPEC-2026-08-14-v1.0.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path

SPEC_PATH = "data/JANUS-LINEAR-A-SIGLA-CROSS-DIGITIZATION-INVENTORY-SPEC-2026-08-14-v1.0.json"
SPEC_COMMIT = "776c79480a022d4f9a1fffaea31fb0123460dc55"
DEFAULT_SIGLA_URL = "https://sigla.phis.me/browse.html"
FROZEN_MWENGE_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"


class SigLABrowseParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.document_hrefs: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        parsed = urllib.parse.urlparse(href)
        path = parsed.path
        if "/document/" in path or path.startswith("document/"):
            self.document_hrefs.append(href)

    def handle_data(self, data):
        if data:
            self.text_parts.append(data)


def fetch_bytes(url: str, timeout: int = 60):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "JANUS-Linear-A-R3A-inventory-audit/1.0 (+https://github.com/Hawkar-usls/janus-meta-registry)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        status = getattr(resp, "status", None) or resp.getcode()
        final_url = resp.geturl()
        content_type = resp.headers.get("Content-Type")
    return status, final_url, content_type, body


def extract_sigla_id_from_href(href: str) -> str | None:
    path = urllib.parse.urlparse(href).path
    marker = "/document/"
    if marker in path:
        tail = path.split(marker, 1)[1]
    elif path.startswith("document/"):
        tail = path[len("document/"):]
    else:
        return None
    tail = tail.strip("/")
    if not tail:
        return None
    # Browse links should point at the document root. If an index file ever appears here,
    # strip only that explicit trailing web-file component, not epigraphic punctuation.
    parts = tail.split("/")
    doc = parts[0]
    if doc.lower().startswith("index"):
        return None
    return urllib.parse.unquote(doc)


def normalize_id(raw: str) -> str:
    text = unicodedata.normalize("NFC", urllib.parse.unquote(raw or "")).strip()
    return re.sub(r"\s+", " ", text)


def prefix_of(doc_id: str) -> str:
    s = normalize_id(doc_id)
    m = re.match(r"^([A-Za-z]+(?:\(\?\))?)", s)
    if m:
        return m.group(1).upper()
    m = re.match(r"^([^\d\s]+)", s)
    return m.group(1) if m else "UNKNOWN"


def collisions(values: list[str]):
    rev = defaultdict(list)
    for raw in values:
        rev[normalize_id(raw)].append(raw)
    return {k: sorted(set(v)) for k, v in rev.items() if len(set(v)) > 1}


def inventory_mwenge(root: Path):
    items = sorted((root / "items").glob("*.html"))
    return [p.stem for p in items]


def deterministic_sample(values, n=40):
    return sorted(values)[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mwenge-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sigla-url", default=DEFAULT_SIGLA_URL)
    ap.add_argument("--save-sigla-snapshot")
    args = ap.parse_args()

    status, final_url, content_type, body = fetch_bytes(args.sigla_url)
    if status != 200 or not body:
        raise SystemExit(f"G1_FETCH_FAIL:status={status}:bytes={len(body)}")

    if args.save_sigla_snapshot:
        snap = Path(args.save_sigla_snapshot)
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_bytes(body)

    html = body.decode("utf-8", errors="replace")
    parser = SigLABrowseParser()
    parser.feed(html)
    sigla_ids = sorted({x for h in parser.document_hrefs if (x := extract_sigla_id_from_href(h))})
    visible_text = " ".join(parser.text_parts)
    stated = None
    m = re.search(r"There\s+are\s+(\d+)\s+documents\s+in\s+the\s+corpus", visible_text, flags=re.I)
    if m:
        stated = int(m.group(1))

    if len(sigla_ids) < 700:
        raise SystemExit(f"G2_PARSE_FAIL:distinct_sigla_ids={len(sigla_ids)}")
    if stated is not None and stated != len(sigla_ids):
        raise SystemExit(f"G2_PARSE_FAIL:stated={stated}:extracted={len(sigla_ids)}")

    mwenge_root = Path(args.mwenge_root)
    mwenge_ids = inventory_mwenge(mwenge_root)
    if len(mwenge_ids) < 1500:
        raise SystemExit(f"G3_BASELINE_FAIL:item_count={len(mwenge_ids)}")

    sigla_set = set(sigla_ids)
    mwenge_set = set(mwenge_ids)
    raw_overlap = sigla_set & mwenge_set

    sigla_norm_map = defaultdict(list)
    mwenge_norm_map = defaultdict(list)
    for x in sigla_ids:
        sigla_norm_map[normalize_id(x)].append(x)
    for x in mwenge_ids:
        mwenge_norm_map[normalize_id(x)].append(x)
    sigla_norm = set(sigla_norm_map)
    mwenge_norm = set(mwenge_norm_map)
    norm_overlap = sigla_norm & mwenge_norm
    sigla_collisions = {k: sorted(set(v)) for k, v in sigla_norm_map.items() if len(set(v)) > 1}
    mwenge_collisions = {k: sorted(set(v)) for k, v in mwenge_norm_map.items() if len(set(v)) > 1}

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-SIGLA-CROSS-DIGITIZATION-INVENTORY-RESULT-2026-08-14-v1.0",
        "version": "v1.0",
        "status": "CROSS_DIGITIZATION_INVENTORY_AUDIT_EXECUTED",
        "frozen_spec": {"path": SPEC_PATH, "commit": SPEC_COMMIT},
        "sources": {
            "SIGLA": {
                "requested_url": args.sigla_url,
                "final_url": final_url,
                "http_status": status,
                "content_type": content_type,
                "content_length_bytes": len(body),
                "content_sha256": hashlib.sha256(body).hexdigest(),
                "stated_document_count": stated,
                "extracted_document_count": len(sigla_ids),
                "independence_layer": "INDEPENDENT_DIGITIZATION_SHARED_GORILA_TRANSCRIPTION",
            },
            "MWENGE": {
                "repository": "mwenge/lineara.xyz",
                "frozen_commit": FROZEN_MWENGE_COMMIT,
                "item_html_count": len(mwenge_ids),
                "independence_layer": "CURRENT_BASELINE",
            },
        },
        "comparison": {
            "raw_exact_overlap_count": len(raw_overlap),
            "raw_exact_overlap_fraction_of_sigla": len(raw_overlap) / len(sigla_ids) if sigla_ids else None,
            "raw_exact_overlap_fraction_of_mwenge": len(raw_overlap) / len(mwenge_ids) if mwenge_ids else None,
            "conservative_normalized_overlap_count": len(norm_overlap),
            "conservative_normalized_overlap_fraction_of_sigla": len(norm_overlap) / len(sigla_norm) if sigla_norm else None,
            "conservative_normalized_overlap_fraction_of_mwenge": len(norm_overlap) / len(mwenge_norm) if mwenge_norm else None,
            "sigla_only_raw_count": len(sigla_set - mwenge_set),
            "mwenge_only_raw_count": len(mwenge_set - sigla_set),
            "sigla_only_normalized_count": len(sigla_norm - mwenge_norm),
            "mwenge_only_normalized_count": len(mwenge_norm - sigla_norm),
            "sigla_normalization_collision_count": len(sigla_collisions),
            "mwenge_normalization_collision_count": len(mwenge_collisions),
        },
        "prefix_distributions": {
            "SIGLA": dict(sorted(Counter(prefix_of(x) for x in sigla_ids).items())),
            "MWENGE": dict(sorted(Counter(prefix_of(x) for x in mwenge_ids).items())),
        },
        "deterministic_samples": {
            "raw_exact_overlap": deterministic_sample(raw_overlap),
            "sigla_only_raw": deterministic_sample(sigla_set - mwenge_set),
            "mwenge_only_raw": deterministic_sample(mwenge_set - sigla_set),
            "normalized_overlap": deterministic_sample(norm_overlap),
            "sigla_only_normalized": deterministic_sample(sigla_norm - mwenge_norm),
            "mwenge_only_normalized": deterministic_sample(mwenge_norm - sigla_norm),
            "sigla_normalization_collisions": dict(list(sorted(sigla_collisions.items()))[:20]),
            "mwenge_normalization_collisions": dict(list(sorted(mwenge_collisions.items()))[:20]),
        },
        "interpretation_guard": {
            "normalized_ids_are_identity_bridge": False,
            "reason": "The frozen normalization intentionally does not remove source-specific spacing or infer epigraphic equivalence. Low overlap may therefore reflect naming syntax rather than document disagreement and must motivate a separately frozen bridge spec.",
            "normalization_collision_blocks_one_to_one_bridge": bool(sigla_collisions or mwenge_collisions),
        },
        "epistemic_gate": {
            "cross_digitization_inventory_audit_established": True,
            "cross_digitization_content_replication_established": False,
            "external_transcription_replication_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NO_PROMOTION",
        },
        "required_next": [
            "Freeze an explicit source-to-source document identity bridge based on naming syntax and bibliographic/document metadata, not semantic readings.",
            "Do not use conservative normalized overlap as a transcription agreement statistic.",
            "After bridge freeze, fetch a predeclared overlapping document subset from SigLA and compare word/sign boundary representation with a SigLA-specific parser.",
            "Continue CTLA/TMT/RILA acquisition in parallel for genuine transcription-layer independence.",
        ],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "sigla_documents": len(sigla_ids),
        "sigla_stated": stated,
        "mwenge_items": len(mwenge_ids),
        "raw_overlap": len(raw_overlap),
        "normalized_overlap": len(norm_overlap),
        "sigla_sha256": hashlib.sha256(body).hexdigest(),
        "external_transcription_replication_established": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
