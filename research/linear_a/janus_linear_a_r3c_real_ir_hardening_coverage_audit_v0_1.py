#!/usr/bin/env python3
"""R3C-2B real-source coverage audit for admitted IR hardening v1.1.

This runner does NOT infer physical faces from newline separators. It asks a
narrower question: does the exact current lineara.xyz source mechanically carry
enough boundary identity to instantiate v1.1's SOURCE_CONTINUATION_ACROSS_SURFACE
without adding information? D6 is checked separately for direct representation
as an unresolved source-label/glyph identity conflict.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_source_loader_v0_4 import LOADER_ID, load_lineara_map_v0_4

EXPECTED_BYTES = 1609137
EXPECTED_SHA = "4da8e1f9693d30880ee505e56541fc189add70605bad88436c44a8e11a57764c"
A319 = chr(0x1066B)

D5 = {
    "IOZa12": {"joined": "JA-SA-SA-RA-ME", "parts": ["JA-SA", "SA-RA-ME"]},
    "IOZa16": {"joined": "JA-SA-SA-RA-ME", "parts": ["JA-SA-SA-RA", "ME"]},
    "KNZa10": {"joined": "JA-SA-SA-RA-MA-NA", "parts": ["JA-SA-SA-RA-MA", "NA"]},
    "PKZa16": {"joined": "PU₂-RE", "parts": ["PU₂", "RE-JA"]},
}
D6 = ["HT132", "HTZd155", "HTZd157+156"]
BOUNDARY_KEY_RE = re.compile(r"(?:face|surface|side|line)", re.IGNORECASE)
SURFACE_KEY_RE = re.compile(r"(?:face|surface|side)", re.IGNORECASE)
LINE_KEY_RE = re.compile(r"line", re.IGNORECASE)


def transliterated(doc: dict[str, Any]) -> list[str]:
    values = doc.get("transliteratedWords") or []
    return [x if isinstance(x, str) else repr(x) for x in values] if isinstance(values, list) else []


def recursive_boundary_fields(value: Any, path: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if BOUNDARY_KEY_RE.search(str(key)):
                rows.append({"path": child_path, "field_name": str(key), "value": child})
            rows.extend(recursive_boundary_fields(child, child_path))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            rows.extend(recursive_boundary_fields(child, f"{path}[{i}]"))
    return rows


def lists_containing_part(value: Any, part: str) -> list[str]:
    hits: list[str] = []
    def walk(v: Any, path: str) -> None:
        if isinstance(v, list):
            if any(isinstance(x, str) and unicodedata.normalize("NFC", x) == part for x in v):
                hits.append(path)
            for i, child in enumerate(v):
                walk(child, f"{path}[{i}]")
        elif isinstance(v, dict):
            for key, child in v.items():
                walk(child, f"{path}.{key}" if path else str(key))
    walk(value, "")
    return hits


def explicit_structured_boundary_binding(doc: dict[str, Any], parts: list[str]) -> dict[str, Any]:
    """Find only explicit structured boundary containers that separately bind parts.

    A positive SURFACE result requires a field whose own name carries face/surface/side
    semantics and whose structured children place the two parts in two distinct child
    containers. The same rule with a field name containing 'line' yields LINE.
    Flat transliteratedWords plus a '\\n' token is deliberately insufficient.
    """
    candidates = recursive_boundary_fields(doc)
    surface_hits: list[dict[str, Any]] = []
    line_hits: list[dict[str, Any]] = []
    for row in candidates:
        value = row["value"]
        if not isinstance(value, (list, dict)):
            continue
        part_paths = [lists_containing_part(value, part) for part in parts]
        if not all(part_paths):
            continue
        # Require evidence that the parts are represented under different direct-ish paths,
        # not merely both found in the same flat list.
        distinct = any(a != b for a in part_paths[0] for b in part_paths[1])
        if not distinct:
            continue
        evidence = {
            "field_path": row["path"],
            "field_name": row["field_name"],
            "part_paths": part_paths,
            "distinct_structured_paths": True,
        }
        if SURFACE_KEY_RE.search(row["field_name"]):
            surface_hits.append(evidence)
        if LINE_KEY_RE.search(row["field_name"]):
            line_hits.append(evidence)
    return {"surface_hits": surface_hits, "line_hits": line_hits}


def positions(values: list[str], target: str) -> list[int]:
    target = unicodedata.normalize("NFC", target)
    return [i for i, value in enumerate(values) if unicodedata.normalize("NFC", value) == target]


def audit_d5(doc_id: str, spec: dict[str, Any], docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    doc = docs.get(doc_id)
    if doc is None:
        return {
            "document": doc_id,
            "document_present": False,
            "source_symptom_confirmed": False,
            "boundary_classification": "NO_MECHANICAL_BOUNDARY_EVIDENCE",
            "v1_1_directly_projectable": False,
        }
    vals = transliterated(doc)
    parts = [unicodedata.normalize("NFC", p) for p in spec["parts"]]
    pos = {part: positions(vals, part) for part in parts}
    ordered_pairs = [(i, j) for i in pos[parts[0]] for j in pos[parts[1]] if i < j]
    if ordered_pairs:
        i, j = ordered_pairs[0]
        between = vals[i + 1:j]
    else:
        i = j = None
        between = []
    newline_between = any(isinstance(x, str) and (x == "\n" or "\n" in x) for x in between)
    structured = explicit_structured_boundary_binding(doc, parts)
    if structured["surface_hits"]:
        classification = "EXPLICIT_DISTINCT_SURFACES_IN_SOURCE"
    elif structured["line_hits"]:
        classification = "EXPLICIT_SAME_SURFACE_DISTINCT_LINES_IN_SOURCE"
    elif ordered_pairs and newline_between:
        classification = "NEWLINE_OR_LINE_BREAK_ONLY_BOUNDARY_KIND_UNRESOLVED"
    else:
        classification = "NO_MECHANICAL_BOUNDARY_EVIDENCE"
    symptom = bool(ordered_pairs)
    return {
        "document": doc_id,
        "document_present": True,
        "site": doc.get("site"),
        "support": doc.get("support"),
        "source_object_field_names": sorted(str(k) for k in doc.keys()),
        "upstream_joined_form": spec["joined"],
        "fixed_lineage_parts": spec["parts"],
        "transliteratedWords": vals,
        "part_positions": pos,
        "first_ordered_part_pair": [i, j] if ordered_pairs else None,
        "items_between_parts": between,
        "newline_between_parts": newline_between,
        "boundary_named_fields": recursive_boundary_fields(doc),
        "explicit_structured_boundary_binding": structured,
        "source_symptom_confirmed": symptom,
        "boundary_classification": classification,
        "v1_1_directly_projectable": classification == "EXPLICIT_DISTINCT_SURFACES_IN_SOURCE",
        "why_not_direct_if_false": None if classification == "EXPLICIT_DISTINCT_SURFACES_IN_SOURCE" else (
            "v1.1 requires distinct source_surface_ref values; this source observation does not mechanically establish distinct physical surfaces."
        ),
    }


def audit_d6(doc_id: str, docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    doc = docs.get(doc_id)
    if doc is None:
        return {"document": doc_id, "document_present": False, "directly_projectable_v1_1": False}
    vals = transliterated(doc)
    label_words = [w for w in vals if "*904" in w]
    parsed = str(doc.get("parsedInscription", ""))
    glyph_count = parsed.count(A319)
    label_values = sorted(set(label_words))
    assertions = [
        {"identity_system": "SOURCE_LABEL", "identity_values": label_values},
        {"identity_system": "ENCODED_GLYPH", "identity_values": ["U+1066B/A319"] if glyph_count else []},
    ]
    directly = bool(label_words) and glyph_count > 0 and len({"SOURCE_LABEL", "ENCODED_GLYPH"}) == 2
    return {
        "document": doc_id,
        "document_present": True,
        "site": doc.get("site"),
        "support": doc.get("support"),
        "label_bearing_words": label_words,
        "label_substring_occurrences": sum(w.count("*904") for w in label_words),
        "A319_glyph_occurrences": glyph_count,
        "source_symptom_confirmed": bool(label_words) and glyph_count > 0,
        "preservable_identity_assertions": assertions,
        "resolution_state": "UNRESOLVED",
        "semantic_class_authority_granted": False,
        "source_identity_overwrite_performed": False,
        "required_claim_view_identity_conflict_policy": "EXCLUDE_CONFLICTED_TOKENS",
        "directly_projectable_v1_1": directly,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    docs, meta = load_lineara_map_v0_4(args.source)
    source_ok = meta["bytes"] == EXPECTED_BYTES and meta["sha256"] == EXPECTED_SHA and meta["loader_id"] == LOADER_ID
    d5 = [audit_d5(doc_id, spec, docs) for doc_id, spec in D5.items()]
    d6 = [audit_d6(doc_id, docs) for doc_id in D6]

    d5_symptoms = all(row.get("source_symptom_confirmed") for row in d5)
    d6_symptoms = all(row.get("source_symptom_confirmed") for row in d6)
    d5_all_direct = all(row.get("v1_1_directly_projectable") for row in d5)
    d6_all_direct = all(row.get("directly_projectable_v1_1") for row in d6)

    if not source_ok or not d5_symptoms or not d6_symptoms:
        status = "SOURCE_CASE_MISMATCH"
    elif d6_all_direct and d5_all_direct:
        status = "V1_1_COVERS_ALL_REAL_D5_D6"
    elif d6_all_direct and not d5_all_direct:
        status = "V1_1_D6_COVERED_D5_BOUNDARY_COVERAGE_GAP"
    else:
        status = "D6_COVERAGE_GAP"

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-2B-REAL-IR-HARDENING-COVERAGE-AUDIT-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "real_source_hardening_coverage_audit_result",
        "status": status,
        "frozen_spec": "data/JANUS-LINEAR-A-R3C-2B-REAL-IR-HARDENING-COVERAGE-AUDIT-SPEC-2026-08-14-v0.1.json",
        "source": meta,
        "source_identity_admitted": source_ok,
        "hardening_profile_under_audit": "JANUS-LINEAR-TRANSCRIPTION-IR-HARDENING-v1.1",
        "D5": {
            "external_prior_art": True,
            "JANUS_blind_discovery_credit": False,
            "cases": d5,
            "all_4_source_split_symptoms_confirmed": d5_symptoms,
            "all_4_directly_projectable_by_surface_only_v1_1": d5_all_direct,
            "classification_counts": dict(__import__("collections").Counter(row["boundary_classification"] for row in d5)),
        },
        "D6": {
            "external_prior_art": True,
            "JANUS_blind_discovery_credit": False,
            "cases": d6,
            "all_3_source_conflicts_confirmed": d6_symptoms,
            "all_3_directly_projectable_by_v1_1_conflict_binding": d6_all_direct,
        },
        "coverage_interpretation": {
            "v1_1_invalidated_if_gap": False,
            "v1_1_scope_if_gap": "Valid admitted SURFACE-specific capability but incomplete for the full real D5 phenomenon if exact source boundary kind is line-only or unresolved.",
            "surface_from_newline_inferred": False,
            "line_from_absent_surface_metadata_inferred": False,
            "next_extension_if_gap": "Freeze additive v1.2 SOURCE_CONTINUATION_ACROSS_BOUNDARY with explicit SURFACE, LINE, or UNRESOLVED_SURFACE_OR_LINE boundary class; do not rewrite v1.1.",
        },
        "claim_ceiling": {
            "real_source_coverage_audit_only": True,
            "linguistic_wordhood_newly_discovered": False,
            "JANUS_independent_D5_D6_discovery": False,
            "R3B_effect": "NONE",
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "source_ok": source_ok,
        "D5_symptoms": d5_symptoms,
        "D5_direct": d5_all_direct,
        "D5_classifications": [r["boundary_classification"] for r in d5],
        "D6_symptoms": d6_symptoms,
        "D6_direct": d6_all_direct,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
