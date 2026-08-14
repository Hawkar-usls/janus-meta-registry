#!/usr/bin/env python3
"""JANUS Linear A source-agnostic transcription IR v1.0.

This module is deliberately not a Linear A decipherer and not a universal parser. It is the
lossless substrate that source-specific adapters must emit before any cross-source bridge or
scientific view is constructed.

Core guarantees:
- raw source literals are never overwritten by normalization;
- exact numerics use rational strings, never authoritative binary floats;
- approximate/uncertain numeric structures may not carry a false exact magnitude;
- all references are fail-closed;
- source-native grouping is representable without claiming linguistic wordhood;
- disagreements and cross-source bridge edges are additive and do not mutate source nodes;
- canonical IR hashing is deterministic;
- scientific views must explicitly whitelist token types and fields.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import unicodedata
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable

IR_FORMAT = "JANUS-LINEAR-TRANSCRIPTION-IR-v1.0"
CORE_ID = "JANUS-LINEAR-TRANSCRIPTION-IR-CORE-v1.0"

ALLOWED_INDEPENDENCE = {
    "L0_DERIVATIVE_TRANSFORM",
    "L1_INDEPENDENT_DIGITIZATION_SHARED_TRANSCRIPTION",
    "L2_ALTERNATE_EDITORIAL_CORPUS_SHARED_PRIMARY_TRADITION",
    "L3_INDEPENDENT_TRANSCRIPTION_BASELINE",
    "UNCLASSIFIED",
}

ALLOWED_SEGMENT_TYPES = {
    "PAGE", "SURFACE", "ZONE", "COLUMN", "ROW", "LINE", "REGISTER", "CELL",
    "FREEFORM_REGION", "UNKNOWN",
}

ALLOWED_TOKEN_TYPES = {
    "SIGN",
    "SIGN_UNCERTAIN",
    "SIGN_ALTERNATIVE_SET",
    "NUMERIC_EXACT",
    "NUMERIC_APPROX_OR_UNCERTAIN",
    "FRACTION_EXACT",
    "FRACTION_APPROX_OR_UNCERTAIN",
    "PUNCTUATION",
    "SEPARATOR",
    "DAMAGE",
    "GAP",
    "ILLEGIBLE",
    "EDITORIAL_MARK",
    "LIGATURE_OR_COMPOSITE",
    "LOGOGRAM_SOURCE_LABEL",
    "UNKNOWN_SOURCE_TOKEN",
    "MASK",
}

DEFAULT_NON_SEMANTIC_TOKEN_TYPES = {
    "NUMERIC_EXACT",
    "NUMERIC_APPROX_OR_UNCERTAIN",
    "FRACTION_EXACT",
    "FRACTION_APPROX_OR_UNCERTAIN",
    "PUNCTUATION",
    "SEPARATOR",
    "DAMAGE",
    "GAP",
    "ILLEGIBLE",
    "EDITORIAL_MARK",
    "MASK",
}

ALLOWED_GROUP_TYPES = {
    "SOURCE_WORD",
    "SOURCE_SIGN_GROUP",
    "SOURCE_NUMERIC_GROUP",
    "SOURCE_FORMULA_GROUP",
    "SOURCE_LINE_GROUP",
    "JANUS_DERIVED_SEQUENCE_WINDOW",
    "UNKNOWN",
}

ALLOWED_RELATION_TYPES = {
    "NEXT_TOKEN",
    "SAME_SOURCE_GROUP",
    "SAME_SPATIAL_CLUSTER",
    "ALTERNATIVE_OF",
    "DAMAGED_PART_OF",
    "DOCUMENT_IDENTITY_BRIDGE",
    "SURFACE_IDENTITY_BRIDGE",
    "TOKEN_IDENTITY_EXACT",
    "TOKEN_IDENTITY_COMPATIBLE",
    "TOKEN_IDENTITY_CONFLICT",
    "GROUP_BOUNDARY_AGREEMENT",
    "GROUP_BOUNDARY_CONFLICT",
    "NUMERIC_VALUE_AGREEMENT",
    "NUMERIC_VALUE_CONFLICT",
    "LAYOUT_ALIGNMENT",
}

ALLOWED_EVIDENCE_CLASSES = {
    "SOURCE_NATIVE",
    "MECHANICAL_EXACT",
    "MECHANICAL_COMPATIBLE",
    "EDITORIAL_ASSERTION",
    "HUMAN_VERIFIED",
    "INFERRED_FROZEN_RULE",
}

ALLOWED_DISAGREEMENT_TYPES = {
    "DOCUMENT_ID_COLLISION",
    "SURFACE_MAPPING_CONFLICT",
    "TOKEN_COUNT_CONFLICT",
    "SIGN_ID_CONFLICT",
    "READING_CONFLICT",
    "BOUNDARY_CONFLICT",
    "NUMERIC_TYPE_CONFLICT",
    "NUMERIC_VALUE_CONFLICT",
    "UNCERTAINTY_CONFLICT",
    "DAMAGE_CONFLICT",
    "ORDER_CONFLICT",
    "LAYOUT_CONFLICT",
    "SOURCE_OMISSION",
    "SOURCE_ADDITION",
    "UNRESOLVED",
}

ALLOWED_DISAGREEMENT_STATUS = {
    "OPEN",
    "MECHANICALLY_LOCALIZED",
    "EDITORIALLY_EXPLAINED",
    "RESOLVED_FOR_TECHNICAL_BRIDGE_ONLY",
    "NOT_RESOLVABLE_WITH_AVAILABLE_EVIDENCE",
}

ALLOWED_READING_STATUS = {
    "CERTAIN", "PROBABLE", "POSSIBLE", "UNCERTAIN", "DAMAGED", "RESTORED", "EDITORIAL", "UNKNOWN",
}

VULGAR_FRACTIONS = {
    "½": Fraction(1, 2), "⅓": Fraction(1, 3), "⅔": Fraction(2, 3), "¼": Fraction(1, 4),
    "¾": Fraction(3, 4), "⅕": Fraction(1, 5), "⅖": Fraction(2, 5), "⅗": Fraction(3, 5),
    "⅘": Fraction(4, 5), "⅙": Fraction(1, 6), "⅚": Fraction(5, 6), "⅛": Fraction(1, 8),
    "⅜": Fraction(3, 8), "⅝": Fraction(5, 8), "⅞": Fraction(7, 8),
}
SUPERSCRIPT_DIGITS = str.maketrans({
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5",
    "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
})
SUBSCRIPT_DIGITS = str.maketrans({
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5",
    "₆": "6", "₇": "7", "₈": "8", "₉": "9",
})
APPROX_PREFIXES = ("≈", "~", "∼")


def _is_mapping(value: Any) -> bool:
    return isinstance(value, dict)


def _is_list(value: Any) -> bool:
    return isinstance(value, list)


def _require(mapping: dict, fields: Iterable[str], prefix: str, errors: list[str]) -> None:
    for field in fields:
        if field not in mapping:
            errors.append(f"{prefix}:MISSING_REQUIRED:{field}")


def _unique_ids(items: list[dict], id_field: str, prefix: str, errors: list[str]) -> set[str]:
    seen: set[str] = set()
    for i, item in enumerate(items):
        value = item.get(id_field)
        if not isinstance(value, str) or not value:
            errors.append(f"{prefix}[{i}]:INVALID_OR_MISSING_ID:{id_field}")
            continue
        if value in seen:
            errors.append(f"{prefix}:DUPLICATE_ID:{value}")
        seen.add(value)
    return seen


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def ir_hash_payload(ir: dict) -> dict:
    payload = copy.deepcopy(ir)
    receipt = payload.get("provenance_receipt")
    if isinstance(receipt, dict):
        receipt.pop("ir_sha256", None)
    return payload


def compute_ir_sha256(ir: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(ir_hash_payload(ir))).hexdigest()


def seal_ir(ir: dict) -> dict:
    out = copy.deepcopy(ir)
    out.setdefault("provenance_receipt", {})["ir_sha256"] = compute_ir_sha256(out)
    return out


def parse_generic_unicode_rational(source_expression: str) -> dict | None:
    """Opt-in helper grammar; adapters must explicitly freeze use of this profile.

    Exact outputs are rational strings. Approximate markers are typed but exact_value is null.
    This helper intentionally does not decide whether the source *means* a token numerically;
    that remains the source adapter's responsibility.
    """
    raw = (source_expression or "").strip()
    if not raw:
        return None

    approx = False
    work = raw
    while work.startswith(APPROX_PREFIXES):
        approx = True
        work = work[1:].strip()

    fraction: Fraction | None = None
    if work in VULGAR_FRACTIONS:
        fraction = VULGAR_FRACTIONS[work]
    else:
        normalized = work.translate(SUPERSCRIPT_DIGITS).translate(SUBSCRIPT_DIGITS).replace("⁄", "/")
        normalized = normalized.replace(",", "")
        if re.fullmatch(r"[+-]?\d+", normalized):
            fraction = Fraction(int(normalized), 1)
        elif re.fullmatch(r"[+-]?\d+\.\d+", normalized):
            fraction = Fraction(normalized)
        else:
            m = re.fullmatch(r"([+-]?\d+)\s*/\s*(\d+)", normalized)
            if m and int(m.group(2)) != 0:
                fraction = Fraction(int(m.group(1)), int(m.group(2)))
            elif len(work) == 1:
                try:
                    numeric_value = unicodedata.numeric(work)
                except (TypeError, ValueError):
                    numeric_value = None
                if numeric_value is not None:
                    fraction = Fraction(numeric_value).limit_denominator(1000000)

    if fraction is None:
        return None

    if approx:
        return {
            "kind": "APPROX_OR_UNCERTAIN",
            "marker": raw[: len(raw) - len(work)].strip() or raw[0],
            "source_expression": raw,
            "exact_value": None,
            "bounded_interval": None,
        }
    return {
        "kind": "EXACT",
        "source_expression": raw,
        "numerator": str(fraction.numerator),
        "denominator": str(fraction.denominator),
        "canonical_fraction": f"{fraction.numerator}/{fraction.denominator}",
    }


def _validate_exact_numeric(token: dict, prefix: str, errors: list[str]) -> None:
    numeric = token.get("numeric")
    if not isinstance(numeric, dict):
        errors.append(f"{prefix}:EXACT_NUMERIC_MISSING_NUMERIC_OBJECT")
        return
    for field in ("numerator", "denominator", "canonical_fraction"):
        if field not in numeric:
            errors.append(f"{prefix}:EXACT_NUMERIC_MISSING:{field}")
    num = numeric.get("numerator")
    den = numeric.get("denominator")
    canon = numeric.get("canonical_fraction")
    if not isinstance(num, str) or not re.fullmatch(r"[+-]?\d+", num):
        errors.append(f"{prefix}:INVALID_NUMERATOR")
        return
    if not isinstance(den, str) or not re.fullmatch(r"[+-]?\d+", den):
        errors.append(f"{prefix}:INVALID_DENOMINATOR")
        return
    denominator = int(den)
    if denominator == 0:
        errors.append(f"{prefix}:ZERO_DENOMINATOR")
        return
    f = Fraction(int(num), denominator)
    expected = f"{f.numerator}/{f.denominator}"
    if canon != expected:
        errors.append(f"{prefix}:NONCANONICAL_RATIONAL:expected={expected}:observed={canon}")
    if "exact_value" in numeric and numeric.get("exact_value") not in (None, canon, expected):
        errors.append(f"{prefix}:BINARY_OR_ALTERNATE_EXACT_VALUE_FORBIDDEN")


def _validate_approx_numeric(token: dict, prefix: str, errors: list[str]) -> None:
    numeric = token.get("numeric")
    if not isinstance(numeric, dict):
        errors.append(f"{prefix}:APPROX_NUMERIC_MISSING_NUMERIC_OBJECT")
        return
    if numeric.get("exact_value") is not None:
        errors.append(f"{prefix}:APPROX_NUMERIC_FALSE_EXACT_VALUE")
    if not isinstance(numeric.get("source_expression"), str) or not numeric.get("source_expression"):
        errors.append(f"{prefix}:APPROX_NUMERIC_MISSING_SOURCE_EXPRESSION")
    interval = numeric.get("bounded_interval")
    if interval is not None:
        if not isinstance(interval, dict) or not {"lower", "upper"}.issubset(interval):
            errors.append(f"{prefix}:INVALID_BOUNDED_INTERVAL")


def _validate_bbox(value: Any, prefix: str, errors: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append(f"{prefix}:BBOX_NOT_OBJECT")
        return
    if not {"x", "y", "width", "height"}.issubset(value):
        errors.append(f"{prefix}:BBOX_MISSING_COMPONENT")
        return
    for name in ("x", "y", "width", "height"):
        if not isinstance(value[name], (int, float)):
            errors.append(f"{prefix}:BBOX_NONNUMERIC:{name}")
    if isinstance(value.get("width"), (int, float)) and value["width"] < 0:
        errors.append(f"{prefix}:BBOX_NEGATIVE_WIDTH")
    if isinstance(value.get("height"), (int, float)) and value["height"] < 0:
        errors.append(f"{prefix}:BBOX_NEGATIVE_HEIGHT")


def _resolve_ref(ref: str, namespaces: dict[str, set[str]]) -> bool:
    if not isinstance(ref, str) or ":" not in ref:
        return False
    kind, ident = ref.split(":", 1)
    return ident in namespaces.get(kind, set())


def validate_ir(ir: dict, *, require_hash: bool = True) -> list[str]:
    errors: list[str] = []
    if not isinstance(ir, dict):
        return ["IR_NOT_OBJECT"]
    if ir.get("ir_format") != IR_FORMAT:
        errors.append(f"IR_FORMAT_MISMATCH:{ir.get('ir_format')}")

    _require(ir, ["source", "document", "surfaces", "segments", "tokens", "groups", "relations", "disagreements", "provenance_receipt"], "IR", errors)

    source = ir.get("source")
    if not isinstance(source, dict):
        errors.append("SOURCE_NOT_OBJECT")
        source = {}
    else:
        _require(source, ["source_id", "source_family", "edition_id", "independence_level", "adapter_id", "native_identifier_scheme", "native_numeric_grammar_id", "native_uncertainty_grammar_id", "native_boundary_grammar_id"], "SOURCE", errors)
        if source.get("independence_level") not in ALLOWED_INDEPENDENCE:
            errors.append(f"SOURCE_INVALID_INDEPENDENCE_LEVEL:{source.get('independence_level')}")

    document = ir.get("document")
    if not isinstance(document, dict):
        errors.append("DOCUMENT_NOT_OBJECT")
        document = {}
    else:
        _require(document, ["document_id", "source_document_id", "artifact_class"], "DOCUMENT", errors)

    surfaces = ir.get("surfaces") if isinstance(ir.get("surfaces"), list) else []
    segments = ir.get("segments") if isinstance(ir.get("segments"), list) else []
    tokens = ir.get("tokens") if isinstance(ir.get("tokens"), list) else []
    groups = ir.get("groups") if isinstance(ir.get("groups"), list) else []
    relations = ir.get("relations") if isinstance(ir.get("relations"), list) else []
    disagreements = ir.get("disagreements") if isinstance(ir.get("disagreements"), list) else []
    if not isinstance(ir.get("surfaces"), list): errors.append("SURFACES_NOT_LIST")
    if not isinstance(ir.get("segments"), list): errors.append("SEGMENTS_NOT_LIST")
    if not isinstance(ir.get("tokens"), list): errors.append("TOKENS_NOT_LIST")
    if not isinstance(ir.get("groups"), list): errors.append("GROUPS_NOT_LIST")
    if not isinstance(ir.get("relations"), list): errors.append("RELATIONS_NOT_LIST")
    if not isinstance(ir.get("disagreements"), list): errors.append("DISAGREEMENTS_NOT_LIST")

    surface_ids = _unique_ids(surfaces, "surface_id", "SURFACES", errors)
    segment_ids = _unique_ids(segments, "segment_id", "SEGMENTS", errors)
    token_ids = _unique_ids(tokens, "token_id", "TOKENS", errors)
    group_ids = _unique_ids(groups, "group_id", "GROUPS", errors)
    relation_ids = _unique_ids(relations, "relation_id", "RELATIONS", errors)
    disagreement_ids = _unique_ids(disagreements, "disagreement_id", "DISAGREEMENTS", errors)

    receipt = ir.get("provenance_receipt")
    if not isinstance(receipt, dict):
        errors.append("PROVENANCE_RECEIPT_NOT_OBJECT")
        receipt = {}
    else:
        _require(receipt, ["source_files", "adapter", "ingest_timestamp", "validation_state"], "PROVENANCE_RECEIPT", errors)

    source_files = receipt.get("source_files") if isinstance(receipt.get("source_files"), list) else []
    provenance_refs = receipt.get("provenance_refs") if isinstance(receipt.get("provenance_refs"), list) else []
    if not isinstance(receipt.get("source_files"), list): errors.append("PROVENANCE_SOURCE_FILES_NOT_LIST")
    if not isinstance(receipt.get("provenance_refs", []), list): errors.append("PROVENANCE_REFS_NOT_LIST")
    file_ids = _unique_ids(source_files, "file_id", "SOURCE_FILES", errors)
    provenance_ids = _unique_ids(provenance_refs, "ref_id", "PROVENANCE_REFS", errors)

    for i, sf in enumerate(source_files):
        _require(sf, ["file_id", "filename", "sha256", "bytes", "mime_type"], f"SOURCE_FILES[{i}]", errors)
        sha = sf.get("sha256")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            errors.append(f"SOURCE_FILES[{i}]:INVALID_SHA256")
        if not isinstance(sf.get("bytes"), int) or sf.get("bytes", -1) < 0:
            errors.append(f"SOURCE_FILES[{i}]:INVALID_BYTE_LENGTH")

    for i, pref in enumerate(provenance_refs):
        _require(pref, ["ref_id", "file_id", "extraction_method"], f"PROVENANCE_REFS[{i}]", errors)
        if pref.get("file_id") not in file_ids:
            errors.append(f"PROVENANCE_REFS[{i}]:UNKNOWN_FILE:{pref.get('file_id')}")

    def check_provenance_refs(refs: Any, prefix: str) -> None:
        if not isinstance(refs, list) or not refs:
            errors.append(f"{prefix}:MISSING_OR_EMPTY_PROVENANCE_REFS")
            return
        for ref in refs:
            if ref not in provenance_ids:
                errors.append(f"{prefix}:UNKNOWN_PROVENANCE_REF:{ref}")

    for i, surface in enumerate(surfaces):
        check_provenance_refs(surface.get("provenance_refs"), f"SURFACES[{i}]")
        _validate_bbox(surface.get("bbox"), f"SURFACES[{i}]", errors)

    for i, segment in enumerate(segments):
        if segment.get("segment_type") not in ALLOWED_SEGMENT_TYPES:
            errors.append(f"SEGMENTS[{i}]:INVALID_SEGMENT_TYPE:{segment.get('segment_type')}")
        parent = segment.get("parent_segment_id")
        if parent is not None and parent not in segment_ids:
            errors.append(f"SEGMENTS[{i}]:UNKNOWN_PARENT_SEGMENT:{parent}")
        surface_id = segment.get("surface_id")
        if surface_id is not None and surface_id not in surface_ids:
            errors.append(f"SEGMENTS[{i}]:UNKNOWN_SURFACE:{surface_id}")
        check_provenance_refs(segment.get("provenance_refs"), f"SEGMENTS[{i}]")
        _validate_bbox(segment.get("bbox"), f"SEGMENTS[{i}]", errors)

    seen_sequence_indices: set[int] = set()
    for i, token in enumerate(tokens):
        prefix = f"TOKENS[{i}]"
        _require(token, ["token_id", "source_raw", "token_type", "sequence_index", "provenance_refs"], prefix, errors)
        token_type = token.get("token_type")
        if token_type not in ALLOWED_TOKEN_TYPES:
            errors.append(f"{prefix}:INVALID_TOKEN_TYPE:{token_type}")
        if not isinstance(token.get("source_raw"), str):
            errors.append(f"{prefix}:SOURCE_RAW_NOT_STRING")
        seq = token.get("sequence_index")
        if not isinstance(seq, int) or seq < 0:
            errors.append(f"{prefix}:INVALID_SEQUENCE_INDEX")
        elif seq in seen_sequence_indices:
            errors.append(f"TOKENS:DUPLICATE_SEQUENCE_INDEX:{seq}")
        else:
            seen_sequence_indices.add(seq)
        segment_id = token.get("segment_id")
        if segment_id is not None and segment_id not in segment_ids:
            errors.append(f"{prefix}:UNKNOWN_SEGMENT:{segment_id}")
        group_refs = token.get("group_ids", [])
        if group_refs is not None:
            if not isinstance(group_refs, list):
                errors.append(f"{prefix}:GROUP_IDS_NOT_LIST")
            else:
                for gid in group_refs:
                    if gid not in group_ids:
                        errors.append(f"{prefix}:UNKNOWN_GROUP:{gid}")
        check_provenance_refs(token.get("provenance_refs"), prefix)
        _validate_bbox(token.get("bbox"), prefix, errors)
        status = token.get("reading_status")
        if status is not None and status not in ALLOWED_READING_STATUS:
            errors.append(f"{prefix}:INVALID_READING_STATUS:{status}")
        if token_type in {"NUMERIC_EXACT", "FRACTION_EXACT"}:
            _validate_exact_numeric(token, prefix, errors)
        if token_type in {"NUMERIC_APPROX_OR_UNCERTAIN", "FRACTION_APPROX_OR_UNCERTAIN"}:
            _validate_approx_numeric(token, prefix, errors)
        if token_type == "SIGN_ALTERNATIVE_SET":
            alts = token.get("alternatives")
            if not isinstance(alts, list) or not alts:
                errors.append(f"{prefix}:ALTERNATIVE_SET_EMPTY")
            else:
                alt_ids: set[str] = set()
                for ai, alt in enumerate(alts):
                    aid = alt.get("alternative_id") if isinstance(alt, dict) else None
                    if not isinstance(aid, str) or not aid:
                        errors.append(f"{prefix}:ALTERNATIVE[{ai}]:MISSING_ID")
                    elif aid in alt_ids:
                        errors.append(f"{prefix}:DUPLICATE_ALTERNATIVE_ID:{aid}")
                    else:
                        alt_ids.add(aid)
                    if isinstance(alt, dict):
                        check_provenance_refs(alt.get("provenance_refs"), f"{prefix}:ALTERNATIVE[{ai}]")

    for i, group in enumerate(groups):
        prefix = f"GROUPS[{i}]"
        if group.get("group_type") not in ALLOWED_GROUP_TYPES:
            errors.append(f"{prefix}:INVALID_GROUP_TYPE:{group.get('group_type')}")
        members = group.get("member_token_ids")
        if not isinstance(members, list) or not members:
            errors.append(f"{prefix}:EMPTY_OR_INVALID_MEMBERS")
        else:
            for tid in members:
                if tid not in token_ids:
                    errors.append(f"{prefix}:UNKNOWN_TOKEN:{tid}")
        check_provenance_refs(group.get("provenance_refs"), prefix)
        derived = bool(group.get("derived", False))
        if derived and not group.get("derivation_spec_ref"):
            errors.append(f"{prefix}:DERIVED_GROUP_MISSING_DERIVATION_SPEC")
        if group.get("group_type") == "JANUS_DERIVED_SEQUENCE_WINDOW" and not derived:
            errors.append(f"{prefix}:JANUS_DERIVED_GROUP_NOT_MARKED_DERIVED")

    namespaces = {
        "surface": surface_ids,
        "segment": segment_ids,
        "token": token_ids,
        "group": group_ids,
        "relation": relation_ids,
        "disagreement": disagreement_ids,
        "document": {str(document.get("document_id"))} if document.get("document_id") else set(),
    }

    for i, relation in enumerate(relations):
        prefix = f"RELATIONS[{i}]"
        if relation.get("relation_type") not in ALLOWED_RELATION_TYPES:
            errors.append(f"{prefix}:INVALID_RELATION_TYPE:{relation.get('relation_type')}")
        if relation.get("evidence_class") not in ALLOWED_EVIDENCE_CLASSES:
            errors.append(f"{prefix}:INVALID_EVIDENCE_CLASS:{relation.get('evidence_class')}")
        for side in ("source_refs", "target_refs"):
            refs = relation.get(side)
            if not isinstance(refs, list) or not refs:
                errors.append(f"{prefix}:{side.upper()}_EMPTY_OR_INVALID")
                continue
            for ref in refs:
                if not _resolve_ref(ref, namespaces):
                    errors.append(f"{prefix}:UNRESOLVED_{side.upper()}:{ref}")
        prov = relation.get("provenance_refs")
        if prov is not None:
            check_provenance_refs(prov, prefix)

    for i, disagreement in enumerate(disagreements):
        prefix = f"DISAGREEMENTS[{i}]"
        if disagreement.get("disagreement_type") not in ALLOWED_DISAGREEMENT_TYPES:
            errors.append(f"{prefix}:INVALID_TYPE:{disagreement.get('disagreement_type')}")
        if disagreement.get("status") not in ALLOWED_DISAGREEMENT_STATUS:
            errors.append(f"{prefix}:INVALID_STATUS:{disagreement.get('status')}")
        for side in ("source_refs", "target_refs"):
            refs = disagreement.get(side)
            if not isinstance(refs, list):
                errors.append(f"{prefix}:{side.upper()}_NOT_LIST")
                continue
            for ref in refs:
                if not _resolve_ref(ref, namespaces):
                    errors.append(f"{prefix}:UNRESOLVED_{side.upper()}:{ref}")
        check_provenance_refs(disagreement.get("provenance_refs"), prefix)

    if require_hash:
        observed = receipt.get("ir_sha256") if isinstance(receipt, dict) else None
        if not isinstance(observed, str) or not re.fullmatch(r"[0-9a-f]{64}", observed):
            errors.append("PROVENANCE_RECEIPT:INVALID_OR_MISSING_IR_SHA256")
        else:
            expected = compute_ir_sha256(ir)
            if observed != expected:
                errors.append(f"PROVENANCE_RECEIPT:IR_SHA256_MISMATCH:expected={expected}:observed={observed}")

    return errors


def validate_scientific_view(ir: dict, view_spec: dict) -> list[str]:
    """Projection firewall between typed IR and a claim-bearing experiment."""
    errors = validate_ir(ir, require_hash=True)
    if errors:
        return ["SCIENTIFIC_VIEW_PARENT_IR_INVALID"] + errors
    if not isinstance(view_spec, dict):
        return ["SCIENTIFIC_VIEW_SPEC_NOT_OBJECT"]
    required = ["view_id", "ontology_version", "eligible_token_types", "allowed_token_fields"]
    _require(view_spec, required, "SCIENTIFIC_VIEW", errors)
    eligible = set(view_spec.get("eligible_token_types", []))
    allowed_fields = set(view_spec.get("allowed_token_fields", []))
    if not eligible:
        errors.append("SCIENTIFIC_VIEW:NO_ELIGIBLE_TOKEN_TYPES")
    unknown_types = eligible - ALLOWED_TOKEN_TYPES
    if unknown_types:
        errors.append(f"SCIENTIFIC_VIEW:UNKNOWN_TOKEN_TYPES:{sorted(unknown_types)}")
    nonsemantic_override = eligible & DEFAULT_NON_SEMANTIC_TOKEN_TYPES
    if nonsemantic_override:
        explicit = set(view_spec.get("explicit_nonsemantic_exceptions", []))
        if nonsemantic_override - explicit:
            errors.append(f"SCIENTIFIC_VIEW:NONSEMANTIC_TYPES_NOT_EXPLICITLY_EXCEPTED:{sorted(nonsemantic_override-explicit)}")
    forbidden_raw = {"source_raw", "source_reading_label"} & allowed_fields
    if forbidden_raw and not view_spec.get("raw_literal_use_explicitly_frozen", False):
        errors.append(f"SCIENTIFIC_VIEW:RAW_LITERAL_FIELDS_REQUIRE_EXPLICIT_FREEZE:{sorted(forbidden_raw)}")
    if not view_spec.get("candidate_namespace"):
        errors.append("SCIENTIFIC_VIEW:MISSING_CANDIDATE_NAMESPACE")
    return errors


def make_minimal_fixture() -> dict:
    source_bytes = b"fixture source bytes"
    ir = {
        "ir_format": IR_FORMAT,
        "source": {
            "source_id": "FIXTURE",
            "source_family": "TEST_ONLY",
            "edition_id": "fixture-v1",
            "independence_level": "UNCLASSIFIED",
            "adapter_id": "fixture-adapter-v1",
            "native_identifier_scheme": "fixture",
            "native_numeric_grammar_id": "GENERIC_UNICODE_RATIONAL_EXACT_v1",
            "native_uncertainty_grammar_id": "fixture-uncertainty-v1",
            "native_boundary_grammar_id": "fixture-boundary-v1",
        },
        "document": {
            "document_id": "DOC1",
            "source_document_id": "DOC1-native",
            "artifact_class": "TABLET",
        },
        "surfaces": [
            {"surface_id": "S1", "source_surface_label": "a", "provenance_refs": ["P1"]}
        ],
        "segments": [
            {"segment_id": "L1", "segment_type": "LINE", "parent_segment_id": None, "surface_id": "S1", "source_label": "1", "sequence_index": 0, "provenance_refs": ["P1"]}
        ],
        "tokens": [
            {
                "token_id": "T1", "source_raw": "AB01", "token_type": "SIGN", "sequence_index": 0,
                "source_sign_id": "AB01", "segment_id": "L1", "group_ids": ["G1"], "reading_status": "CERTAIN", "provenance_refs": ["P1"]
            },
            {
                "token_id": "T2", "source_raw": "¹⁄₅", "token_type": "FRACTION_EXACT", "sequence_index": 1,
                "segment_id": "L1", "group_ids": ["G2"], "numeric": {"numerator": "1", "denominator": "5", "canonical_fraction": "1/5"}, "provenance_refs": ["P1"]
            },
            {
                "token_id": "T3", "source_raw": "≈¹⁄₆", "token_type": "FRACTION_APPROX_OR_UNCERTAIN", "sequence_index": 2,
                "segment_id": "L1", "group_ids": ["G2"], "numeric": {"marker": "≈", "source_expression": "≈¹⁄₆", "bounded_interval": None, "exact_value": None}, "provenance_refs": ["P1"]
            },
        ],
        "groups": [
            {"group_id": "G1", "group_type": "SOURCE_WORD", "member_token_ids": ["T1"], "derived": False, "provenance_refs": ["P1"]},
            {"group_id": "G2", "group_type": "SOURCE_NUMERIC_GROUP", "member_token_ids": ["T2", "T3"], "derived": False, "provenance_refs": ["P1"]},
        ],
        "relations": [
            {"relation_id": "R1", "relation_type": "NEXT_TOKEN", "source_refs": ["token:T1"], "target_refs": ["token:T2"], "evidence_class": "SOURCE_NATIVE", "provenance_refs": ["P1"]},
            {"relation_id": "R2", "relation_type": "NEXT_TOKEN", "source_refs": ["token:T2"], "target_refs": ["token:T3"], "evidence_class": "SOURCE_NATIVE", "provenance_refs": ["P1"]},
        ],
        "disagreements": [],
        "provenance_receipt": {
            "source_files": [{"file_id": "F1", "filename": "fixture.txt", "sha256": hashlib.sha256(source_bytes).hexdigest(), "bytes": len(source_bytes), "mime_type": "text/plain", "page_count": None, "source_locator": "fixture://local"}],
            "provenance_refs": [{"ref_id": "P1", "file_id": "F1", "page": None, "line": 1, "bbox": None, "source_record_id": "fixture-record", "source_url": None, "extraction_method": "OTHER", "extractor_version": CORE_ID}],
            "adapter": {"adapter_id": "fixture-adapter-v1", "core_id": CORE_ID},
            "ingest_timestamp": "2026-08-14T14:55:00+03:00",
            "validation_state": "UNSEALED",
            "ir_sha256": None,
        },
    }
    sealed = seal_ir(ir)
    sealed["provenance_receipt"]["validation_state"] = "SEALED_VALIDATION_PENDING"
    # validation_state participates in the hash, so reseal after changing it.
    return seal_ir(sealed)


def self_test() -> dict:
    fixture = make_minimal_fixture()
    errors = validate_ir(fixture)
    if errors:
        raise AssertionError(errors)

    exact_cases = {
        "¹⁄₃": "1/3",
        "¹⁄₅": "1/5",
        "13/20": "13/20",
        "⅝": "5/8",
        "-2": "-2/1",
        "1.25": "5/4",
    }
    for raw, expected in exact_cases.items():
        parsed = parse_generic_unicode_rational(raw)
        assert parsed and parsed["kind"] == "EXACT", (raw, parsed)
        assert parsed["canonical_fraction"] == expected, (raw, parsed)
    approx = parse_generic_unicode_rational("≈¹⁄₆")
    assert approx and approx["kind"] == "APPROX_OR_UNCERTAIN"
    assert approx["exact_value"] is None

    bad = copy.deepcopy(fixture)
    bad["tokens"][2]["numeric"]["exact_value"] = "1/6"
    bad = seal_ir(bad)
    bad_errors = validate_ir(bad)
    assert any("APPROX_NUMERIC_FALSE_EXACT_VALUE" in e for e in bad_errors), bad_errors

    bad2 = copy.deepcopy(fixture)
    bad2["relations"][0]["target_refs"] = ["token:DOES_NOT_EXIST"]
    bad2 = seal_ir(bad2)
    bad2_errors = validate_ir(bad2)
    assert any("UNRESOLVED_TARGET_REFS" in e for e in bad2_errors), bad2_errors

    view = {
        "view_id": "fixture-scientific-view",
        "ontology_version": "v1",
        "eligible_token_types": ["SIGN"],
        "allowed_token_fields": ["normalized_sign_id", "source_sign_id", "sequence_index"],
        "candidate_namespace": "FIXTURE-CANDIDATE-v1",
        "raw_literal_use_explicitly_frozen": False,
        "explicit_nonsemantic_exceptions": [],
    }
    assert validate_scientific_view(fixture, view) == []

    blocked_view = copy.deepcopy(view)
    blocked_view["eligible_token_types"] = ["SIGN", "FRACTION_APPROX_OR_UNCERTAIN"]
    assert any("NONSEMANTIC_TYPES_NOT_EXPLICITLY_EXCEPTED" in e for e in validate_scientific_view(fixture, blocked_view))

    return {
        "core_id": CORE_ID,
        "fixture_ir_sha256": fixture["provenance_receipt"]["ir_sha256"],
        "valid_fixture_errors": 0,
        "numeric_exact_cases": len(exact_cases),
        "approx_false_exact_rejected": True,
        "broken_reference_rejected": True,
        "scientific_projection_firewall": True,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("path")

    p_seal = sub.add_parser("seal")
    p_seal.add_argument("path")
    p_seal.add_argument("--out", required=True)

    sub.add_parser("self-test")
    sub.add_parser("fixture")

    args = ap.parse_args()
    if args.cmd == "validate":
        ir = json.loads(Path(args.path).read_text(encoding="utf-8"))
        errors = validate_ir(ir)
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2, sort_keys=True))
        raise SystemExit(0 if not errors else 1)
    if args.cmd == "seal":
        ir = json.loads(Path(args.path).read_text(encoding="utf-8"))
        sealed = seal_ir(ir)
        Path(args.out).write_text(json.dumps(sealed, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(sealed["provenance_receipt"]["ir_sha256"])
        return
    if args.cmd == "self-test":
        print(json.dumps(self_test(), ensure_ascii=False, indent=2, sort_keys=True))
        return
    if args.cmd == "fixture":
        print(json.dumps(make_minimal_fixture(), ensure_ascii=False, indent=2, sort_keys=True))
        return


if __name__ == "__main__":
    main()
