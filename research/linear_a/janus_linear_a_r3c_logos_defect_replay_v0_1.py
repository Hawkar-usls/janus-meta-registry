#!/usr/bin/env python3
"""Externally seeded logos D5/D6 conformance replay for JANUS R3C-2.

This is explicitly NOT a discovery program.  D5 and D6 were known from the
external logos project before this runner existed.  The runner asks only
whether the reported source-layer symptoms are mechanically present in the
frozen mwenge lineage and emits extra source-layer candidates separately.
"""
from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_common_v0_1 import load_lineara_map, normalize_alias

SOURCE_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
A319 = chr(0x1066B)
A319_NAME = unicodedata.name(A319, "UNKNOWN")

D5 = [
    ("IOZa12", ["JA-SA", "SA-RA-ME"]),
    ("IOZa16", ["JA-SA-SA-RA", "ME"]),
    ("KNZa10", ["JA-SA-SA-RA-MA", "NA"]),
    ("PKZa16", ["PU2", "RE-JA"]),
]
D6_DOCS = ["HT132", "HTZd155", "HTZd157+156"]


def transliterated(doc: dict[str, Any]) -> list[str]:
    values = doc.get("transliteratedWords", [])
    return [x for x in values if isinstance(x, str)] if isinstance(values, list) else []


def count_label(doc: dict[str, Any], label: str) -> int:
    target = normalize_alias(label)
    return sum(1 for x in transliterated(doc) if normalize_alias(x) == target)


def replay_d5(docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for doc_id, fragments in D5:
        doc = docs.get(doc_id)
        if doc is None:
            rows.append({"document": doc_id, "expected_fragments": fragments, "document_present": False, "all_fragments_present": False})
            continue
        values = [normalize_alias(x) for x in transliterated(doc)]
        expected = [normalize_alias(x) for x in fragments]
        positions: dict[str, list[int]] = {frag: [i for i, value in enumerate(values) if value == frag] for frag in expected}
        all_present = all(positions[frag] for frag in expected)
        ordered = False
        if all_present:
            ordered = any(i < j for i in positions[expected[0]] for j in positions[expected[1]])
        rows.append({
            "document": doc_id,
            "expected_fragments": fragments,
            "normalized_expected_fragments": expected,
            "document_present": True,
            "all_fragments_present": all_present,
            "fragments_in_source_order": ordered,
            "positions": positions,
            "source_values": transliterated(doc),
        })
    confirmed = sum(1 for row in rows if row.get("all_fragments_present") and row.get("fragments_in_source_order"))
    return {
        "classification": "EXTERNALLY_SEEDED_SOURCE_SYMPTOM_REPLAY_NOT_DISCOVERY",
        "cases": rows,
        "confirmed_case_count": confirmed,
        "expected_case_count": len(D5),
        "all_seeded_source_symptoms_confirmed": confirmed == len(D5),
        "editorial_continuation_relation_independently_proved_by_this_runner": False,
    }


def replay_d6(docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = []
    total_label = 0
    total_glyph = 0
    for doc_id in D6_DOCS:
        doc = docs.get(doc_id)
        if doc is None:
            rows.append({"document": doc_id, "document_present": False, "label_count": 0, "glyph_count": 0, "co_present": False})
            continue
        label_count = count_label(doc, "*904")
        parsed = str(doc.get("parsedInscription", ""))
        glyph_count = parsed.count(A319)
        total_label += label_count
        total_glyph += glyph_count
        rows.append({
            "document": doc_id,
            "document_present": True,
            "label_count": label_count,
            "glyph_count": glyph_count,
            "co_present": label_count > 0 and glyph_count > 0,
        })

    # Transparent all-corpus scan of the SAME symptom, not a search for new meaning.
    all_corpus_candidates = []
    for doc_id, doc in docs.items():
        lc = count_label(doc, "*904")
        gc = str(doc.get("parsedInscription", "")).count(A319)
        if lc or gc:
            all_corpus_candidates.append({"document": doc_id, "label_count": lc, "glyph_count": gc, "co_present": lc > 0 and gc > 0})
    all_corpus_candidates.sort(key=lambda r: r["document"])

    confirmed = sum(1 for row in rows if row.get("co_present"))
    return {
        "classification": "EXTERNALLY_SEEDED_GLYPH_LABEL_CONFLICT_SYMPTOM_REPLAY_NOT_DISCOVERY",
        "glyph": {"codepoint": "U+1066B", "unicode_name": A319_NAME, "character": A319},
        "source_label": "*904",
        "seeded_cases": rows,
        "seeded_documents_with_copresence": confirmed,
        "expected_seeded_documents": len(D6_DOCS),
        "seeded_all_confirmed": confirmed == len(D6_DOCS),
        "seeded_label_occurrences": total_label,
        "seeded_glyph_occurrences": total_glyph,
        "externally_reported_occurrences": 5,
        "all_corpus_same_symptom_candidates": all_corpus_candidates,
        "additional_candidate_interpretation": "CONTAMINATION_SENSITIVE_SOURCE_LAYER_ENUMERATION_ONLY",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    docs, meta = load_lineara_map(args.source)
    d5 = replay_d5(docs)
    d6 = replay_d6(docs)
    if d5["all_seeded_source_symptoms_confirmed"] and d6["seeded_all_confirmed"]:
        status = "CONFIRMED_EXTERNAL_REPLAY"
    elif d5["confirmed_case_count"] or d6["seeded_documents_with_copresence"]:
        status = "PARTIAL_EXTERNAL_REPLAY"
    else:
        status = "NOT_REPRODUCED"

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-2-LOGOS-DEFECT-CONFORMANCE-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "external_prior_art_conformance_result",
        "status": status,
        "source": {**meta, "repository": "mwenge/lineara.xyz", "commit": SOURCE_COMMIT},
        "external_prior_art": {
            "repository": "papadopouloskyriakos/logos",
            "commit": "aa799f74722a807c850a212bea9fc3a8fa38db21",
            "known_before_runner": True,
            "JANUS_blind_discovery_credit": False,
        },
        "D5": d5,
        "D6": d6,
        "hardening_recommendation": {
            "admit_source_continuation_relation_to_next_IR_version": bool(d5["confirmed_case_count"]),
            "admit_explicit_glyph_label_identity_conflict_to_next_IR_version": bool(d6["seeded_documents_with_copresence"]),
            "destructive_source_token_merge": False,
            "source_label_authoritatively_assigns_semantic_class": False,
            "unresolved_identity_conflict_should_fail_closed_in_class_conditioned_views": True,
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
    print(json.dumps({"status": status, "D5_confirmed": d5["confirmed_case_count"], "D6_confirmed_docs": d6["seeded_documents_with_copresence"], "source_sha256": meta["sha256"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
