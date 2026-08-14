#!/usr/bin/env python3
"""Corrective JANUS replay of logos D6 using the upstream substring predicate.

This fixes only JANUS' conformance predicate.  It does not alter source bytes,
logos prior art, or any decipherment claim.
"""
from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_source_loader_v0_4 import load_lineara_map_v0_4, LOADER_ID

EXPECTED_BYTES = 1609137
EXPECTED_SHA = "4da8e1f9693d30880ee505e56541fc189add70605bad88436c44a8e11a57764c"
A319 = chr(0x1066B)
LABEL = "*904"
SEEDED = ["HT132", "HTZd155", "HTZd157+156"]


def transliterated(doc: dict[str, Any]) -> list[str]:
    v = doc.get("transliteratedWords") or []
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def inspect_doc(doc_id: str, doc: dict[str, Any]) -> dict[str, Any]:
    words = transliterated(doc)
    label_words = [w for w in words if LABEL in w]
    glyph_text = str(doc.get("parsedInscription", ""))
    glyph_count = glyph_text.count(A319)
    return {
        "document": doc_id,
        "label_bearing_words": label_words,
        "label_bearing_word_count": len(label_words),
        "label_substring_occurrence_count": sum(w.count(LABEL) for w in label_words),
        "glyph_occurrence_count": glyph_count,
        "label_present": bool(label_words),
        "glyph_present": glyph_count > 0,
        "co_present": bool(label_words) and glyph_count > 0,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    docs, meta = load_lineara_map_v0_4(args.source)
    source_ok = meta["bytes"] == EXPECTED_BYTES and meta["sha256"] == EXPECTED_SHA and meta["loader_id"] == LOADER_ID

    rows = [inspect_doc(k, v) for k, v in docs.items()]
    label_rows = [r for r in rows if r["label_present"]]
    glyph_rows = [r for r in rows if r["glyph_present"]]
    both_rows = [r for r in rows if r["co_present"]]
    label_docs = sorted(r["document"] for r in label_rows)
    glyph_docs = sorted(r["document"] for r in glyph_rows)
    both_docs = sorted(r["document"] for r in both_rows)
    seeded_rows = [next((r for r in rows if r["document"] == d), {
        "document": d, "document_missing": True, "label_present": False, "glyph_present": False, "co_present": False
    }) for d in SEEDED]

    ht155 = next(r for r in seeded_rows if r["document"] == "HTZd155")
    seeded_all = all(r.get("co_present") for r in seeded_rows)
    set_equal = label_docs == glyph_docs
    if source_ok and seeded_all and set_equal:
        status = "CONFIRMED_EXTERNAL_REPLAY_CORRECTED"
    elif source_ok and any(r.get("co_present") for r in seeded_rows):
        status = "PARTIAL_EXTERNAL_REPLAY_AFTER_CORRECTION"
    elif source_ok:
        status = "NOT_REPRODUCED_AFTER_CORRECTION"
    else:
        status = "BLOCKED_SOURCE_IDENTITY_MISMATCH"

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-2A-LOGOS-D6-CORRECTIVE-REPLAY-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "corrective_external_prior_art_conformance_result",
        "status": status,
        "frozen_spec": "data/JANUS-LINEAR-A-R3C-2A-LOGOS-D6-CORRECTIVE-REPLAY-SPEC-2026-08-14-v0.1.json",
        "source": meta,
        "source_identity_admitted": source_ok,
        "external_prior_art": {
            "repository": "papadopouloskyriakos/logos",
            "commit": "aa799f74722a807c850a212bea9fc3a8fa38db21",
            "script": "scripts/audit_face_splits.py",
            "upstream_predicate_replayed": "any('*904' in (word or '') for word in transliteratedWords)",
            "JANUS_blind_discovery_credit": False,
        },
        "glyph": {
            "character": A319,
            "codepoint": "U+1066B",
            "unicode_name": unicodedata.name(A319, "UNKNOWN"),
        },
        "label": LABEL,
        "all_corpus": {
            "label_bearing_documents": label_docs,
            "glyph_bearing_documents": glyph_docs,
            "co_present_documents": both_docs,
            "label_and_glyph_document_sets_equal": set_equal,
            "label_bearing_document_count": len(label_docs),
            "glyph_bearing_document_count": len(glyph_docs),
            "co_present_document_count": len(both_docs),
            "label_substring_occurrences": sum(r["label_substring_occurrence_count"] for r in label_rows),
            "glyph_occurrences": sum(r["glyph_occurrence_count"] for r in glyph_rows),
            "rows": [r for r in rows if r["label_present"] or r["glyph_present"]],
        },
        "seeded": {
            "documents": SEEDED,
            "rows": seeded_rows,
            "all_3_copresent": seeded_all,
            "HTZd155_compound_word_canary": {
                "label_bearing_words": ht155.get("label_bearing_words", []),
                "contains_NA_MA_MA_TI_TI_904": any("NA-MA-MA-TI-TI-*904" in w for w in ht155.get("label_bearing_words", [])),
                "old_exact_equality_predicate_would_miss": not any(w == LABEL for w in ht155.get("label_bearing_words", [])),
            },
        },
        "occurrence_count_note": {
            "logos_commit_narrative_reported_occurrences": 5,
            "JANUS_current_exact_source_occurrences_are_observational": True,
            "occurrence_count_used_for_D6_document_set_confirmation": False,
            "rule": "The frozen corrective decision is document-set co-presence, matching the upstream script. Any occurrence-count mismatch is preserved separately and does not get normalized away."
        },
        "correction": {
            "parent_status": "PARTIAL_EXTERNAL_REPLAY",
            "parent_defect": "JANUS used exact whole-token equality for *904; upstream used substring containment.",
            "scientific_source_changed": False,
            "external_prior_art_changed": False,
            "source_parser_changed": False,
            "conformance_predicate_corrected": True,
        },
        "claim_ceiling": {
            "external_prior_art_replayed": True,
            "JANUS_independent_discovery": False,
            "R3B_effect": "NONE",
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "source_ok": source_ok,
        "label_docs": label_docs,
        "glyph_docs": glyph_docs,
        "seeded_all": seeded_all,
        "label_occurrences": result["all_corpus"]["label_substring_occurrences"],
        "glyph_occurrences": result["all_corpus"]["glyph_occurrences"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
