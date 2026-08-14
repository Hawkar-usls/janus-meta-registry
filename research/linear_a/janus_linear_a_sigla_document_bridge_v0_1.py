#!/usr/bin/env python3
"""JANUS Linear A R3A-2 document identity bridge v0.1.

Frozen transform: remove only ASCII SPACE U+0020 from SigLA IDs after URL decode/NFC/trim.
Mwenge IDs receive NFC/trim only. No semantic, palaeographic, side/orientation, or manual
mapping is permitted in this version.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_sigla_inventory_audit as inv

SPEC_PATH = "data/JANUS-LINEAR-A-SIGLA-DOCUMENT-IDENTITY-BRIDGE-SPEC-2026-08-14-v0.1.json"
SPEC_COMMIT = "0dad57a21d2d864e4c81ac8b0e9f1004497d1ca6"
FROZEN_SIGLA_SHA256 = "c1d25f91dccf334c3cf24b52c1e4a279970cebd3f5c6f377569de076360170cd"
FROZEN_SIGLA_COUNT = 802
FROZEN_MWENGE_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"


def sigla_bridge_key(raw: str) -> str:
    s = unicodedata.normalize("NFC", urllib.parse.unquote(raw or "")).strip()
    return s.replace(" ", "")


def mwenge_bridge_key(raw: str) -> str:
    return unicodedata.normalize("NFC", raw or "").strip()


def map_by_key(values, transform):
    out = defaultdict(list)
    for raw in values:
        out[transform(raw)].append(raw)
    return out


def prefix(raw: str) -> str:
    return inv.prefix_of(raw)


def deterministic_sample(values, n=50):
    return sorted(values)[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mwenge-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sigla-url", default=inv.DEFAULT_SIGLA_URL)
    ap.add_argument("--save-sigla-snapshot")
    args = ap.parse_args()

    status, final_url, content_type, body = inv.fetch_bytes(args.sigla_url)
    if status != 200 or not body:
        raise SystemExit(f"B1_SNAPSHOT_FETCH_FAIL:status={status}:bytes={len(body)}")
    sigla_sha = hashlib.sha256(body).hexdigest()
    if sigla_sha != FROZEN_SIGLA_SHA256:
        raise SystemExit(f"B1_SNAPSHOT_HASH_FAIL:expected={FROZEN_SIGLA_SHA256}:actual={sigla_sha}")

    if args.save_sigla_snapshot:
        p = Path(args.save_sigla_snapshot)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)

    parser = inv.SigLABrowseParser()
    parser.feed(body.decode("utf-8", errors="replace"))
    sigla_ids = sorted({x for h in parser.document_hrefs if (x := inv.extract_sigla_id_from_href(h))})
    if len(sigla_ids) != FROZEN_SIGLA_COUNT:
        raise SystemExit(f"B2_COUNT_FAIL:expected={FROZEN_SIGLA_COUNT}:actual={len(sigla_ids)}")

    mwenge_ids = inv.inventory_mwenge(Path(args.mwenge_root))
    if len(mwenge_ids) < 1500:
        raise SystemExit(f"MWENGE_COUNT_FAIL:{len(mwenge_ids)}")

    smap = map_by_key(sigla_ids, sigla_bridge_key)
    mmap = map_by_key(mwenge_ids, mwenge_bridge_key)
    scoll = {k: sorted(set(v)) for k, v in smap.items() if len(set(v)) > 1}
    mcoll = {k: sorted(set(v)) for k, v in mmap.items() if len(set(v)) > 1}

    common_keys = set(smap) & set(mmap)
    collision_free_keys = sorted(k for k in common_keys if k not in scoll and k not in mcoll)
    matched_pairs = [
        {"bridge_key": k, "sigla_id": smap[k][0], "mwenge_id": mmap[k][0]}
        for k in collision_free_keys
    ]

    matched_sigla = {x["sigla_id"] for x in matched_pairs}
    matched_mwenge = {x["mwenge_id"] for x in matched_pairs}
    sigla_only = sorted(set(sigla_ids) - matched_sigla)
    mwenge_only = sorted(set(mwenge_ids) - matched_mwenge)

    matched_prefixes_sigla = Counter(prefix(x["sigla_id"]) for x in matched_pairs)
    unmatched_prefixes_sigla = Counter(prefix(x) for x in sigla_only)
    matched_prefixes_mwenge = Counter(prefix(x["mwenge_id"]) for x in matched_pairs)
    unmatched_prefixes_mwenge = Counter(prefix(x) for x in mwenge_only)

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-SIGLA-DOCUMENT-IDENTITY-BRIDGE-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "status": "DOCUMENT_IDENTITY_BRIDGE_EXECUTED",
        "frozen_spec": {"path": SPEC_PATH, "commit": SPEC_COMMIT},
        "sources": {
            "SIGLA": {
                "url": final_url,
                "http_status": status,
                "content_type": content_type,
                "content_sha256": sigla_sha,
                "document_count": len(sigla_ids),
            },
            "MWENGE": {
                "frozen_commit": FROZEN_MWENGE_COMMIT,
                "item_count": len(mwenge_ids),
            },
        },
        "transform": {
            "name": "SIGLA_REMOVE_ASCII_SPACES_ONLY",
            "sigla": ["URL_DECODE", "UNICODE_NFC", "TRIM", "REMOVE_U+0020"],
            "mwenge": ["UNICODE_NFC", "TRIM"],
            "posthoc_extension_used": False,
        },
        "bridge": {
            "common_transformed_key_count_including_collisions": len(common_keys),
            "collision_free_one_to_one_match_count": len(matched_pairs),
            "sigla_match_fraction": len(matched_pairs) / len(sigla_ids) if sigla_ids else None,
            "mwenge_match_fraction": len(matched_pairs) / len(mwenge_ids) if mwenge_ids else None,
            "sigla_transform_collision_count": len(scoll),
            "mwenge_transform_collision_count": len(mcoll),
            "matched_pairs": matched_pairs,
            "sigla_only_count": len(sigla_only),
            "mwenge_only_count": len(mwenge_only),
            "sigla_only_ids": sigla_only,
            "mwenge_only_ids": mwenge_only,
            "sigla_transform_collisions": scoll,
            "mwenge_transform_collisions": mcoll,
        },
        "prefix_distributions": {
            "SIGLA_MATCHED": dict(sorted(matched_prefixes_sigla.items())),
            "SIGLA_UNMATCHED": dict(sorted(unmatched_prefixes_sigla.items())),
            "MWENGE_MATCHED": dict(sorted(matched_prefixes_mwenge.items())),
            "MWENGE_UNMATCHED": dict(sorted(unmatched_prefixes_mwenge.items())),
        },
        "deterministic_samples": {
            "matched_pairs": matched_pairs[:50],
            "sigla_only": deterministic_sample(sigla_only),
            "mwenge_only": deterministic_sample(mwenge_only),
            "sigla_collisions": dict(list(sorted(scoll.items()))[:20]),
            "mwenge_collisions": dict(list(sorted(mcoll.items()))[:20]),
        },
        "epistemic_gate": {
            "document_identity_bridge_established_for_collision_free_matches": True,
            "bridge_is_complete_for_all_sigla_documents": len(matched_pairs) == len(sigla_ids) and not scoll,
            "cross_digitization_content_replication_established": False,
            "external_transcription_replication_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NO_PROMOTION",
        },
        "required_next": [
            "Persist this exact collision-free mapping before content-level document selection.",
            "Select overlapping content-audit documents deterministically from the persisted bridge rather than by interesting transcription content.",
            "Treat all SIGLA-only residues as unresolved; any second bridge transform requires a new frozen spec.",
            "Do not convert a/b to r/v or otherwise infer side/orientation equivalence from identifiers alone.",
        ],
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "sigla_documents": len(sigla_ids),
        "mwenge_items": len(mwenge_ids),
        "bridge_matches": len(matched_pairs),
        "sigla_match_fraction": result["bridge"]["sigla_match_fraction"],
        "sigla_collisions": len(scoll),
        "mwenge_collisions": len(mcoll),
        "external_transcription_replication_established": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
