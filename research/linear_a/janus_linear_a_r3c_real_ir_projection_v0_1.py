#!/usr/bin/env python3
"""R3C-2C: build seven minimal real-source IR projections and validate firewalls.

Four D5 projections preserve the two lineara transliteratedWords source groups
and the intervening newline separator as an unresolved boundary witness under
hardening v1.2.1. Three D6 projections preserve *904 source-label assertions
and U+1066B/A319 encoded-glyph assertions as unresolved v1.1 identity conflicts.

These are minimal source-span projections, not full-document transcriptions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

import janus_linear_a_transcription_ir_v1_0 as base
import janus_linear_a_transcription_ir_hardening_v1_1 as v11
import janus_linear_a_transcription_ir_hardening_v1_2_1 as v121
from janus_linear_a_r3c_source_loader_v0_4 import LOADER_ID, load_lineara_map_v0_4

SOURCE_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
SOURCE_BYTES = 1609137
SOURCE_SHA = "4da8e1f9693d30880ee505e56541fc189add70605bad88436c44a8e11a57764c"
ADAPTER_ID = "JANUS-LINEAR-A-R3C-REAL-SPAN-TO-IR-v0.1"
A319 = chr(0x1066B)

D5 = {
    "IOZa12": ["JA-SA", "SA-RA-ME"],
    "IOZa16": ["JA-SA-SA-RA", "ME"],
    "KNZa10": ["JA-SA-SA-RA-MA", "NA"],
    "PKZa16": ["PU₂", "RE-JA"],
}
D6 = ["HT132", "HTZd155", "HTZd157+156"]


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def transliterated(doc: dict[str, Any]) -> list[str]:
    values = doc.get("transliteratedWords") or []
    if not isinstance(values, list):
        return []
    return [x for x in values if isinstance(x, str)]


def source_base(doc_id: str, doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "ir_format": base.IR_FORMAT,
        "source": {
            "source_id": "MWENGE-LINEARA-XYZ-R3C-CURRENT",
            "source_family": "MWENGE_LINEARA_XYZ_JS_MAP",
            "edition_id": SOURCE_COMMIT,
            "independence_level": "L0_DERIVATIVE_TRANSFORM",
            "adapter_id": ADAPTER_ID,
            "native_identifier_scheme": "LINEARA_JS_MAP_KEY",
            "native_numeric_grammar_id": "NOT_USED_IN_MINIMAL_PROJECTION",
            "native_uncertainty_grammar_id": "NOT_USED_IN_MINIMAL_PROJECTION",
            "native_boundary_grammar_id": "TRANSLITERATEDWORDS_ARRAY_WITH_NEWLINE_SEPARATORS",
        },
        "document": {
            "document_id": f"MWENGE-R3C:{doc_id}",
            "source_document_id": doc_id,
            "artifact_class": str(doc.get("support", "UNKNOWN")),
            "site": doc.get("site"),
            "projection_scope": "MINIMAL_SOURCE_SPAN_NOT_FULL_DOCUMENT_TRANSCRIPTION",
        },
        "surfaces": [],
        "segments": [],
        "tokens": [],
        "groups": [],
        "relations": [],
        "disagreements": [],
        "provenance_receipt": {
            "source_files": [{
                "file_id": "F1",
                "filename": "LinearAInscriptions.js",
                "sha256": SOURCE_SHA,
                "bytes": SOURCE_BYTES,
                "mime_type": "application/javascript",
                "repository": "mwenge/lineara.xyz",
                "commit": SOURCE_COMMIT,
            }],
            "adapter": {
                "adapter_id": ADAPTER_ID,
                "source_loader_id": LOADER_ID,
                "mode": "MINIMAL_SOURCE_SPAN_PROJECTION",
            },
            "ingest_timestamp": "2026-08-14T18:02:00+03:00",
            "validation_state": "PENDING_CUMULATIVE_HARDENING_VALIDATION",
            "provenance_refs": [],
        },
        "claim_ceiling": {
            "full_document_transcription": False,
            "linguistic_wordhood": False,
            "new_anchor": False,
            "decipherment": False,
        },
    }


def add_prov(ir: dict[str, Any], ref_id: str, doc_id: str, source_record_id: str) -> None:
    ir["provenance_receipt"]["provenance_refs"].append({
        "ref_id": ref_id,
        "file_id": "F1",
        "source_record_id": f"document={doc_id};{source_record_id}",
        "source_url": f"https://github.com/mwenge/lineara.xyz/blob/{SOURCE_COMMIT}/LinearAInscriptions.js",
        "extraction_method": "STATIC_JS_MAP_V0_4_SOURCE_FIELD",
        "extractor_version": ADAPTER_ID,
    })


def make_sign_token(tid: str, raw: str, seq: int, gid: str, pref: str) -> dict[str, Any]:
    return {
        "token_id": tid,
        "source_raw": raw,
        "token_type": "SIGN",
        "sequence_index": seq,
        "source_sign_id": None,
        "source_reading_label": raw,
        "normalized_sign_id": None,
        "segment_id": None,
        "group_ids": [gid],
        "reading_status": "CERTAIN",
        "certainty": None,
        "alternatives": [],
        "numeric": None,
        "damage": None,
        "editorial": None,
        "provenance_refs": [pref],
    }


def add_next_relations(ir: dict[str, Any]) -> None:
    tokens = sorted(ir["tokens"], key=lambda t: t["sequence_index"])
    for i, (a, b) in enumerate(zip(tokens, tokens[1:])):
        ir["relations"].append({
            "relation_id": f"R{i}",
            "relation_type": "NEXT_TOKEN",
            "source_refs": [f"token:{a['token_id']}"],
            "target_refs": [f"token:{b['token_id']}"],
            "evidence_class": "SOURCE_NATIVE",
            "provenance_refs": sorted(set(a["provenance_refs"] + b["provenance_refs"])),
        })


def build_d5(doc_id: str, doc: dict[str, Any], parts: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    vals = transliterated(doc)
    p1, p2 = [nfc(x) for x in parts]
    pos1 = [i for i, x in enumerate(vals) if nfc(x) == p1]
    pos2 = [i for i, x in enumerate(vals) if nfc(x) == p2]
    ordered = [(i, j) for i in pos1 for j in pos2 if i < j]
    if not ordered:
        raise ValueError(f"D5_PART_ORDER_NOT_FOUND:{doc_id}:{parts}")
    i, j = ordered[0]
    between = vals[i + 1:j]
    if len(between) != 1 or between[0] != "\n":
        raise ValueError(f"D5_FROZEN_NEWLINE_WITNESS_MISMATCH:{doc_id}:{between!r}")

    ir = source_base(doc_id, doc)
    add_prov(ir, "P_DOC", doc_id, "source-object")
    add_prov(ir, "P_G1", doc_id, f"transliteratedWords[{i}]")
    add_prov(ir, "P_BOUNDARY", doc_id, f"transliteratedWords[{i+1}]")
    add_prov(ir, "P_G2", doc_id, f"transliteratedWords[{j}]")

    seq = 0
    g1_ids: list[str] = []
    for k, sign in enumerate(parts[0].split("-")):
        tid = f"T_G1_{k}"
        g1_ids.append(tid)
        ir["tokens"].append(make_sign_token(tid, sign, seq, "G1", "P_G1"))
        seq += 1
    boundary_tid = "T_BOUNDARY"
    ir["tokens"].append({
        "token_id": boundary_tid,
        "source_raw": between[0],
        "token_type": "SEPARATOR",
        "sequence_index": seq,
        "source_sign_id": None,
        "source_reading_label": None,
        "normalized_sign_id": None,
        "segment_id": None,
        "group_ids": [],
        "reading_status": "CERTAIN",
        "certainty": None,
        "alternatives": [],
        "numeric": None,
        "damage": None,
        "editorial": None,
        "provenance_refs": ["P_BOUNDARY"],
    })
    seq += 1
    g2_ids: list[str] = []
    for k, sign in enumerate(parts[1].split("-")):
        tid = f"T_G2_{k}"
        g2_ids.append(tid)
        ir["tokens"].append(make_sign_token(tid, sign, seq, "G2", "P_G2"))
        seq += 1

    ir["groups"] = [
        {
            "group_id": "G1", "group_type": "SOURCE_WORD", "member_token_ids": g1_ids,
            "source_group_raw": parts[0], "source_group_array_index": i,
            "derived": False, "provenance_refs": ["P_G1"],
        },
        {
            "group_id": "G2", "group_type": "SOURCE_WORD", "member_token_ids": g2_ids,
            "source_group_raw": parts[1], "source_group_array_index": j,
            "derived": False, "provenance_refs": ["P_G2"],
        },
    ]
    add_next_relations(ir)
    ir["janus_hardening_v1_1"] = {
        "profile_id": v11.PROFILE_ID,
        "cross_surface_continuations": [],
        "identity_conflict_bindings": [],
    }
    ir[v121.EXTENSION_FIELD] = {
        "profile_id": v121.PROFILE_ID,
        "cross_boundary_continuations": [{
            "continuation_id": "CB1",
            "continuation_type": v121.RELATION_TYPE,
            "source_group_ref": "group:G1",
            "target_group_ref": "group:G2",
            "boundary_class": "UNRESOLVED_SURFACE_OR_LINE",
            "boundary_witness_token_refs": [f"token:{boundary_tid}"],
            "boundary_resolution_claimed": False,
            "evidence_class": "MECHANICAL_EXACT",
            "provenance_refs": ["P_G1", "P_BOUNDARY", "P_G2"],
            "source_boundaries_preserved": True,
            "destructive_merge_performed": False,
            "linguistic_wordhood_claimed": False,
        }],
    }
    ir["provenance_receipt"]["validation_state"] = "SOURCE_D5_SPAN_PROJECTED"
    ir = base.seal_ir(ir)
    audit = {
        "document": doc_id,
        "source_part_indices": [i, j],
        "source_parts": parts,
        "boundary_source_item": between[0],
        "boundary_source_item_repr": repr(between[0]),
        "boundary_class": "UNRESOLVED_SURFACE_OR_LINE",
        "boundary_kind_promoted": False,
        "groups_preserved_separately": True,
        "linguistic_wordhood_claimed": False,
    }
    return ir, audit


def build_d6(doc_id: str, doc: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    vals = transliterated(doc)
    label_rows = [(i, w) for i, w in enumerate(vals) if "*904" in w]
    parsed = str(doc.get("parsedInscription", ""))
    glyph_positions = [i for i, ch in enumerate(parsed) if ch == A319]
    if not label_rows or not glyph_positions:
        raise ValueError(f"D6_SOURCE_SYMPTOM_MISSING:{doc_id}:labels={label_rows}:glyphs={glyph_positions}")

    ir = source_base(doc_id, doc)
    add_prov(ir, "P_DOC", doc_id, "source-object")
    label_token_ids: list[str] = []
    glyph_token_ids: list[str] = []
    seq = 0

    for n, (idx, word) in enumerate(label_rows):
        pref = f"P_LABEL_{n}"
        add_prov(ir, pref, doc_id, f"transliteratedWords[{idx}];substring=*904")
        tid = f"T_LABEL_{n}"
        gid = f"G_LABEL_{n}"
        label_token_ids.append(tid)
        ir["tokens"].append({
            "token_id": tid,
            "source_raw": word,
            "token_type": "LOGOGRAM_SOURCE_LABEL",
            "sequence_index": seq,
            "source_sign_id": None,
            "source_reading_label": "*904",
            "normalized_sign_id": None,
            "segment_id": None,
            "group_ids": [gid],
            "reading_status": "EDITORIAL",
            "certainty": None,
            "alternatives": [],
            "numeric": None,
            "damage": None,
            "editorial": {"source_layer": "transliteratedWords", "label_substring": "*904"},
            "provenance_refs": [pref],
        })
        ir["groups"].append({
            "group_id": gid,
            "group_type": "SOURCE_WORD",
            "member_token_ids": [tid],
            "source_group_raw": word,
            "source_group_array_index": idx,
            "derived": False,
            "provenance_refs": [pref],
        })
        seq += 1

    for n, pos in enumerate(glyph_positions):
        pref = f"P_GLYPH_{n}"
        add_prov(ir, pref, doc_id, f"parsedInscription;character-index={pos};codepoint=U+1066B")
        tid = f"T_GLYPH_{n}"
        gid = f"G_GLYPH_{n}"
        glyph_token_ids.append(tid)
        ir["tokens"].append({
            "token_id": tid,
            "source_raw": A319,
            "token_type": "SIGN",
            "sequence_index": seq,
            "source_sign_id": "A319",
            "source_reading_label": None,
            "normalized_sign_id": "A319",
            "segment_id": None,
            "group_ids": [gid],
            "reading_status": "CERTAIN",
            "certainty": None,
            "alternatives": [],
            "numeric": None,
            "damage": None,
            "editorial": None,
            "provenance_refs": [pref],
        })
        ir["groups"].append({
            "group_id": gid,
            "group_type": "SOURCE_SIGN_GROUP",
            "member_token_ids": [tid],
            "source_group_raw": A319,
            "source_character_index": pos,
            "derived": False,
            "provenance_refs": [pref],
        })
        seq += 1

    add_next_relations(ir)
    all_prov = [r["ref_id"] for r in ir["provenance_receipt"]["provenance_refs"] if r["ref_id"] != "P_DOC"]
    ir["disagreements"] = [{
        "disagreement_id": "D1",
        "disagreement_type": "SIGN_ID_CONFLICT",
        "status": "MECHANICALLY_LOCALIZED",
        "source_refs": [f"token:{tid}" for tid in label_token_ids],
        "target_refs": [f"token:{tid}" for tid in glyph_token_ids],
        "provenance_refs": all_prov,
        "source_label": "*904",
        "encoded_glyph_identity": "U+1066B/A319",
    }]
    ir["janus_hardening_v1_1"] = {
        "profile_id": v11.PROFILE_ID,
        "cross_surface_continuations": [],
        "identity_conflict_bindings": [{
            "conflict_binding_id": "IC1",
            "disagreement_ref": "disagreement:D1",
            "token_refs": [f"token:{tid}" for tid in label_token_ids + glyph_token_ids],
            "assertions": [
                {
                    "assertion_id": "ICA_SOURCE_LABEL",
                    "identity_system": "SOURCE_LABEL",
                    "identity_value": "*904",
                    "provenance_refs": [r["ref_id"] for r in ir["provenance_receipt"]["provenance_refs"] if r["ref_id"].startswith("P_LABEL_")],
                },
                {
                    "assertion_id": "ICA_ENCODED_GLYPH",
                    "identity_system": "ENCODED_GLYPH",
                    "identity_value": "U+1066B/A319",
                    "provenance_refs": [r["ref_id"] for r in ir["provenance_receipt"]["provenance_refs"] if r["ref_id"].startswith("P_GLYPH_")],
                },
            ],
            "resolution_state": "UNRESOLVED",
            "semantic_class_authority_granted": False,
            "source_identity_overwrite_performed": False,
            "provenance_refs": all_prov,
        }],
    }
    ir[v121.EXTENSION_FIELD] = {
        "profile_id": v121.PROFILE_ID,
        "cross_boundary_continuations": [],
    }
    ir["provenance_receipt"]["validation_state"] = "SOURCE_D6_CONFLICT_SPAN_PROJECTED"
    ir = base.seal_ir(ir)
    audit = {
        "document": doc_id,
        "label_source_items": [{"index": i, "word": w} for i, w in label_rows],
        "glyph_character_indices": glyph_positions,
        "label_token_count": len(label_token_ids),
        "glyph_token_count": len(glyph_token_ids),
        "resolution_state": "UNRESOLVED",
        "semantic_class_authority_granted": False,
        "source_identity_overwrite_performed": False,
    }
    return ir, audit


def base_view(doc_id: str) -> dict[str, Any]:
    return {
        "view_id": f"R3C-2C:{doc_id}:claim-view",
        "ontology_version": "v1.2.1",
        "eligible_token_types": ["SIGN"],
        "allowed_token_fields": ["source_sign_id", "sequence_index"],
        "candidate_namespace": f"JANUS-R3C-2C-{doc_id}",
        "raw_literal_use_explicitly_frozen": False,
        "explicit_nonsemantic_exceptions": [],
    }


def validate_projection(doc_id: str, kind: str, ir: dict[str, Any]) -> dict[str, Any]:
    base_errors = base.validate_ir(ir, require_hash=True)
    v11_errors = v11.validate_hardening_v1_1(ir, require_hash=True)
    v121_errors = v121.validate_hardening_v1_2_1(ir, require_hash=True)
    view0 = base_view(doc_id)
    negative_errors = v121.validate_scientific_view_v1_2_1(ir, view0)
    if kind == "D5":
        negative_expected = (
            any("BOUNDARY_CONTINUATION_POLICY_REQUIRED" in e for e in negative_errors)
            and any("UNRESOLVED_BOUNDARY_POLICY_REQUIRED" in e for e in negative_errors)
        )
        good_view = dict(view0)
        good_view["boundary_continuation_policy"] = v121.CLAIM_BOUNDARY_POLICY
        good_view["unresolved_boundary_policy"] = v121.CLAIM_UNRESOLVED_POLICY
    else:
        negative_expected = any("IDENTITY_CONFLICT_POLICY_REQUIRED" in e for e in negative_errors)
        good_view = dict(view0)
        good_view["identity_conflict_policy"] = v11.CLAIM_BEARING_CONFLICT_POLICY
    good_errors = v121.validate_scientific_view_v1_2_1(ir, good_view)
    passed = not base_errors and not v11_errors and not v121_errors and negative_expected and not good_errors
    return {
        "document": doc_id,
        "projection_kind": kind,
        "ir_sha256": ir.get("ir_sha256"),
        "base_v1_0_pass": not base_errors,
        "base_v1_0_errors": base_errors,
        "v1_1_pass": not v11_errors,
        "v1_1_errors": v11_errors,
        "v1_2_1_pass": not v121_errors,
        "v1_2_1_errors": v121_errors,
        "negative_claim_view_rejected_as_expected": negative_expected,
        "negative_claim_view_errors": negative_errors,
        "positive_fail_closed_claim_view_pass": not good_errors,
        "positive_claim_view_errors": good_errors,
        "projection_pass": passed,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--result", required=True)
    args = ap.parse_args()

    docs, source_meta = load_lineara_map_v0_4(args.source)
    source_ok = source_meta["bytes"] == SOURCE_BYTES and source_meta["sha256"] == SOURCE_SHA and source_meta["loader_id"] == LOADER_ID
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    audits: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []

    if not source_ok:
        raise SystemExit("EXACT_CURRENT_SOURCE_IDENTITY_NOT_ADMITTED")

    for doc_id, parts in D5.items():
        ir, audit = build_d5(doc_id, docs[doc_id], parts)
        validation = validate_projection(doc_id, "D5", ir)
        path = out_dir / f"JANUS-LINEAR-A-R3C-2C-D5-{doc_id}-IR-v0.1.json"
        path.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raw = path.read_bytes()
        outputs.append({"document": doc_id, "kind": "D5", "path": str(path), "file_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "ir_sha256": ir["ir_sha256"]})
        audits.append({"kind": "D5", **audit})
        validations.append(validation)

    for doc_id in D6:
        ir, audit = build_d6(doc_id, docs[doc_id])
        validation = validate_projection(doc_id, "D6", ir)
        path = out_dir / f"JANUS-LINEAR-A-R3C-2C-D6-{doc_id.replace('+','_PLUS_')}-IR-v0.1.json"
        path.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raw = path.read_bytes()
        outputs.append({"document": doc_id, "kind": "D6", "path": str(path), "file_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "ir_sha256": ir["ir_sha256"]})
        audits.append({"kind": "D6", **audit})
        validations.append(validation)

    passed = sum(1 for v in validations if v["projection_pass"])
    if passed == 7:
        status = "REAL_7_DOCUMENT_PROJECTION_PASS"
    elif passed:
        status = "PARTIAL_PROJECTION"
    else:
        status = "PROJECTION_FAILED"

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-2C-REAL-IR-PROJECTION-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "real_source_ir_projection_result",
        "status": status,
        "frozen_spec": "data/JANUS-LINEAR-A-R3C-2C-REAL-IR-PROJECTION-SPEC-2026-08-14-v0.1.json",
        "source": source_meta,
        "source_identity_admitted": source_ok,
        "projection_scope": "MINIMAL_SOURCE_SPAN_NOT_FULL_DOCUMENT_TRANSCRIPTION",
        "outputs": outputs,
        "source_audits": audits,
        "validations": validations,
        "summary": {
            "documents_expected": 7,
            "documents_projected": len(outputs),
            "projection_pass_count": passed,
            "D5_expected": 4,
            "D5_pass": sum(1 for v in validations if v["projection_kind"] == "D5" and v["projection_pass"]),
            "D6_expected": 3,
            "D6_pass": sum(1 for v in validations if v["projection_kind"] == "D6" and v["projection_pass"]),
            "all_ir_hashes_unique": len({o["ir_sha256"] for o in outputs}) == len(outputs),
            "source_groups_destructively_merged": False,
            "D5_boundary_kind_promoted": False,
            "D6_semantic_authority_granted": False,
        },
        "claim_ceiling": {
            "technical_source_span_projection_only": True,
            "full_document_transcription_claimed": False,
            "D5_boundary_kind_resolved": False,
            "D5_linguistic_wordhood_proved": False,
            "D6_A319_semantics_assigned": False,
            "JANUS_independent_D5_D6_discovery": False,
            "R3B_effect": "NONE",
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.result).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "passed": passed, "validations": validations}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
