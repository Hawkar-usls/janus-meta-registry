#!/usr/bin/env python3
"""Corrected additive v1.2.1 hardening for typed/unresolved continuation boundaries.

This profile is cumulative: a document must already validate as base IR v1.0
plus hardening v1.1. v1.2.1 adds SOURCE_CONTINUATION_ACROSS_BOUNDARY while
preserving the exact base-v1.0 token/evidence taxonomies.
"""
from __future__ import annotations

import argparse
import copy
import json
from typing import Any

import janus_linear_a_transcription_ir_v1_0 as base
import janus_linear_a_transcription_ir_hardening_v1_1 as v11

PROFILE_ID = "JANUS-LINEAR-TRANSCRIPTION-IR-HARDENING-v1.2.1"
EXTENSION_FIELD = "janus_hardening_v1_2_1"
RELATION_TYPE = "SOURCE_CONTINUATION_ACROSS_BOUNDARY"
BOUNDARY_CLASSES = {"SURFACE", "LINE", "UNRESOLVED_SURFACE_OR_LINE"}
UNRESOLVED_WITNESS_TOKEN_TYPES = {
    "SEPARATOR", "PUNCTUATION", "DAMAGE", "GAP", "ILLEGIBLE",
    "EDITORIAL_MARK", "UNKNOWN_SOURCE_TOKEN", "MASK",
}
CLAIM_BOUNDARY_POLICY = "PRESERVE_BOUNDARY_CLASS_AND_SOURCE_GROUPS"
CLAIM_UNRESOLVED_POLICY = "NO_BOUNDARY_KIND_PROMOTION"


def _ids(items: Any, field: str) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {x.get(field) for x in items if isinstance(x, dict) and isinstance(x.get(field), str)}


def _ref_id(ref: Any, kind: str) -> str | None:
    if not isinstance(ref, str) or not ref.startswith(kind + ":"):
        return None
    ident = ref.split(":", 1)[1]
    return ident or None


def _validate_ref(
    ref: Any,
    kind: str,
    allowed: set[str],
    prefix: str,
    errors: list[str],
    *,
    required: bool = True,
) -> str | None:
    if ref is None and not required:
        return None
    ident = _ref_id(ref, kind)
    if ident is None or ident not in allowed:
        errors.append(f"{prefix}:UNRESOLVED_{kind.upper()}_REF:{ref}")
        return None
    return ident


def validate_hardening_v1_2_1(ir: dict[str, Any], *, require_hash: bool = True) -> list[str]:
    parent = v11.validate_hardening_v1_1(ir, require_hash=require_hash)
    if parent:
        return ["V1_2_1_PARENT_V1_1_INVALID"] + parent

    errors: list[str] = []
    ext = ir.get(EXTENSION_FIELD)
    if not isinstance(ext, dict):
        return ["V1_2_1_EXTENSION_MISSING_OR_NOT_OBJECT"]
    if ext.get("profile_id") != PROFILE_ID:
        errors.append(f"V1_2_1_PROFILE_ID_MISMATCH:{ext.get('profile_id')}")
    rows = ext.get("cross_boundary_continuations")
    if not isinstance(rows, list):
        errors.append("V1_2_1_CROSS_BOUNDARY_CONTINUATIONS_NOT_LIST")
        rows = []

    group_ids = _ids(ir.get("groups"), "group_id")
    token_ids = _ids(ir.get("tokens"), "token_id")
    surface_ids = _ids(ir.get("surfaces"), "surface_id")
    segment_ids = _ids(ir.get("segments"), "segment_id")
    provenance_ids = _ids(ir.get("provenance_receipt", {}).get("provenance_refs"), "ref_id")
    tokens = {
        t.get("token_id"): t for t in ir.get("tokens", [])
        if isinstance(t, dict) and isinstance(t.get("token_id"), str)
    }
    segments = {
        s.get("segment_id"): s for s in ir.get("segments", [])
        if isinstance(s, dict) and isinstance(s.get("segment_id"), str)
    }

    seen: set[str] = set()
    for i, row in enumerate(rows):
        p = f"V1_2_1_CONTINUATIONS[{i}]"
        if not isinstance(row, dict):
            errors.append(f"{p}:NOT_OBJECT")
            continue
        required_fields = (
            "continuation_id", "continuation_type", "source_group_ref", "target_group_ref",
            "boundary_class", "boundary_witness_token_refs", "evidence_class", "provenance_refs",
            "source_boundaries_preserved", "destructive_merge_performed", "linguistic_wordhood_claimed",
        )
        for field in required_fields:
            if field not in row:
                errors.append(f"{p}:MISSING_REQUIRED:{field}")

        cid = row.get("continuation_id")
        if not isinstance(cid, str) or not cid:
            errors.append(f"{p}:INVALID_ID")
        elif cid in seen:
            errors.append(f"{p}:DUPLICATE_ID:{cid}")
        else:
            seen.add(cid)

        if row.get("continuation_type") != RELATION_TYPE:
            errors.append(f"{p}:INVALID_TYPE:{row.get('continuation_type')}")
        sg = _validate_ref(row.get("source_group_ref"), "group", group_ids, p, errors)
        tg = _validate_ref(row.get("target_group_ref"), "group", group_ids, p, errors)
        if sg is not None and tg is not None and sg == tg:
            errors.append(f"{p}:DISTINCT_GROUPS_REQUIRED")

        boundary_class = row.get("boundary_class")
        if boundary_class not in BOUNDARY_CLASSES:
            errors.append(f"{p}:INVALID_BOUNDARY_CLASS:{boundary_class}")

        witness_refs = row.get("boundary_witness_token_refs")
        if not isinstance(witness_refs, list):
            errors.append(f"{p}:BOUNDARY_WITNESS_REFS_NOT_LIST")
            witness_refs = []
        witness_ids: list[str] = []
        for ref in witness_refs:
            ident = _validate_ref(ref, "token", token_ids, p, errors)
            if ident is not None:
                witness_ids.append(ident)

        if row.get("evidence_class") not in base.ALLOWED_EVIDENCE_CLASSES:
            errors.append(f"{p}:INVALID_EVIDENCE_CLASS:{row.get('evidence_class')}")
        prov = row.get("provenance_refs")
        if not isinstance(prov, list) or not prov:
            errors.append(f"{p}:MISSING_OR_EMPTY_PROVENANCE_REFS")
        else:
            for ref in prov:
                if ref not in provenance_ids:
                    errors.append(f"{p}:UNKNOWN_PROVENANCE_REF:{ref}")

        if row.get("source_boundaries_preserved") is not True:
            errors.append(f"{p}:SOURCE_BOUNDARIES_MUST_BE_PRESERVED")
        if row.get("destructive_merge_performed") is not False:
            errors.append(f"{p}:DESTRUCTIVE_MERGE_FORBIDDEN")
        if row.get("linguistic_wordhood_claimed") is not False:
            errors.append(f"{p}:LINGUISTIC_WORDHOOD_CLAIM_FORBIDDEN")

        if boundary_class == "SURFACE":
            s1 = _validate_ref(row.get("source_surface_ref"), "surface", surface_ids, p, errors)
            s2 = _validate_ref(row.get("target_surface_ref"), "surface", surface_ids, p, errors)
            if s1 is not None and s2 is not None and s1 == s2:
                errors.append(f"{p}:SURFACE_REQUIRES_DISTINCT_SURFACES")
            if row.get("boundary_resolution_claimed") is not True:
                errors.append(f"{p}:SURFACE_CLASS_REQUIRES_RESOLUTION_TRUE")

        elif boundary_class == "LINE":
            seg1 = _validate_ref(row.get("source_segment_ref"), "segment", segment_ids, p, errors)
            seg2 = _validate_ref(row.get("target_segment_ref"), "segment", segment_ids, p, errors)
            if seg1 is not None and seg2 is not None:
                if seg1 == seg2:
                    errors.append(f"{p}:LINE_REQUIRES_DISTINCT_SEGMENTS")
                else:
                    surf1 = segments.get(seg1, {}).get("surface_id")
                    surf2 = segments.get(seg2, {}).get("surface_id")
                    if surf1 is not None and surf2 is not None and surf1 != surf2:
                        errors.append(f"{p}:LINE_SEGMENTS_MUST_SHARE_SOURCE_SURFACE")
            line_meta = row.get("source_line_metadata_provenance_refs")
            line_meta_ok = isinstance(line_meta, list) and bool(line_meta) and all(x in provenance_ids for x in line_meta)
            if not witness_ids and not line_meta_ok:
                errors.append(f"{p}:LINE_REQUIRES_BOUNDARY_WITNESS_OR_SOURCE_LINE_METADATA")
            if row.get("boundary_resolution_claimed") is not True:
                errors.append(f"{p}:LINE_CLASS_REQUIRES_RESOLUTION_TRUE")

        elif boundary_class == "UNRESOLVED_SURFACE_OR_LINE":
            if not witness_ids:
                errors.append(f"{p}:UNRESOLVED_BOUNDARY_REQUIRES_WITNESS_TOKEN")
            for tid in witness_ids:
                ttype = tokens.get(tid, {}).get("token_type")
                if ttype not in UNRESOLVED_WITNESS_TOKEN_TYPES:
                    errors.append(f"{p}:INVALID_UNRESOLVED_WITNESS_TOKEN_TYPE:{tid}:{ttype}")
            for field, kind, allowed in (
                ("source_surface_ref", "surface", surface_ids),
                ("target_surface_ref", "surface", surface_ids),
                ("source_segment_ref", "segment", segment_ids),
                ("target_segment_ref", "segment", segment_ids),
            ):
                if row.get(field) is not None:
                    _validate_ref(row.get(field), kind, allowed, p, errors, required=False)
            if row.get("boundary_resolution_claimed") is not False:
                errors.append(f"{p}:UNRESOLVED_BOUNDARY_REQUIRES_RESOLUTION_FALSE")

    return errors


def validate_scientific_view_v1_2_1(ir: dict[str, Any], view: dict[str, Any]) -> list[str]:
    errors = validate_hardening_v1_2_1(ir, require_hash=True)
    if errors:
        return ["V1_2_1_SCIENTIFIC_VIEW_PARENT_INVALID"] + errors
    errors.extend(v11.validate_scientific_view_v1_1(ir, view))
    rows = ir[EXTENSION_FIELD].get("cross_boundary_continuations", [])
    if rows and view.get("boundary_continuation_policy") != CLAIM_BOUNDARY_POLICY:
        errors.append(f"V1_2_1_SCIENTIFIC_VIEW:BOUNDARY_CONTINUATION_POLICY_REQUIRED:{CLAIM_BOUNDARY_POLICY}")
    unresolved = any(
        isinstance(row, dict) and row.get("boundary_class") == "UNRESOLVED_SURFACE_OR_LINE"
        for row in rows
    )
    if unresolved and view.get("unresolved_boundary_policy") != CLAIM_UNRESOLVED_POLICY:
        errors.append(f"V1_2_1_SCIENTIFIC_VIEW:UNRESOLVED_BOUNDARY_POLICY_REQUIRED:{CLAIM_UNRESOLVED_POLICY}")
    return errors


def make_fixture() -> dict[str, Any]:
    ir = v11.make_hardened_fixture()
    # Keep the admitted v1.1 profile but empty its optional relation collections so
    # this fixture isolates v1.2.1 continuation semantics.
    ir["janus_hardening_v1_1"]["cross_surface_continuations"] = []
    ir["janus_hardening_v1_1"]["identity_conflict_bindings"] = []
    next_index = max(t.get("sequence_index", 0) for t in ir["tokens"]) + 1
    ir["tokens"].append({
        "token_id": "TB1",
        "source_raw": "\n",
        "token_type": "SEPARATOR",
        "sequence_index": next_index,
        "source_sign_id": None,
        "segment_id": None,
        "group_ids": [],
        "reading_status": "CERTAIN",
        "provenance_refs": ["P1"],
    })
    group_ids = [g["group_id"] for g in ir["groups"] if isinstance(g, dict) and isinstance(g.get("group_id"), str)]
    if len(group_ids) < 2:
        raise AssertionError("fixture needs at least two groups")
    ir[EXTENSION_FIELD] = {
        "profile_id": PROFILE_ID,
        "cross_boundary_continuations": [{
            "continuation_id": "CB1",
            "continuation_type": RELATION_TYPE,
            "source_group_ref": f"group:{group_ids[0]}",
            "target_group_ref": f"group:{group_ids[1]}",
            "boundary_class": "UNRESOLVED_SURFACE_OR_LINE",
            "boundary_witness_token_refs": ["token:TB1"],
            "boundary_resolution_claimed": False,
            "evidence_class": "MECHANICAL_EXACT",
            "provenance_refs": ["P1"],
            "source_boundaries_preserved": True,
            "destructive_merge_performed": False,
            "linguistic_wordhood_claimed": False,
        }],
    }
    return base.seal_ir(ir)


def _v11_regression_pass(result: dict[str, Any]) -> bool:
    positive = [
        "base_v1_0_fixture_still_valid",
        "valid_hardened_fixture_pass",
        "same_surface_continuation_rejected",
        "destructive_merge_rejected",
        "unresolved_conflict_semantic_authority_rejected",
        "claim_view_without_continuation_policy_rejected",
        "claim_view_without_conflict_policy_rejected",
        "claim_view_with_fail_closed_policies_pass",
    ]
    return (
        all(result.get(k) is True for k in positive)
        and result.get("javascript_executed") is False
        and result.get("decipherment_performed") is False
    )


def self_test() -> dict[str, Any]:
    inherited = v11.make_hardened_fixture()
    inherited[EXTENSION_FIELD] = {"profile_id": PROFILE_ID, "cross_boundary_continuations": []}
    inherited = base.seal_ir(inherited)
    inherited_errors = validate_hardening_v1_2_1(inherited)
    assert not inherited_errors, inherited_errors

    good = make_fixture()
    good_errors = validate_hardening_v1_2_1(good)
    assert not good_errors, good_errors

    no_witness = copy.deepcopy(good)
    no_witness[EXTENSION_FIELD]["cross_boundary_continuations"][0]["boundary_witness_token_refs"] = []
    no_witness = base.seal_ir(no_witness)
    no_witness_errors = validate_hardening_v1_2_1(no_witness)
    assert any("UNRESOLVED_BOUNDARY_REQUIRES_WITNESS_TOKEN" in e for e in no_witness_errors)

    sign_witness = copy.deepcopy(good)
    sign_tid = next(t["token_id"] for t in sign_witness["tokens"] if t.get("token_type") == "SIGN")
    sign_witness[EXTENSION_FIELD]["cross_boundary_continuations"][0]["boundary_witness_token_refs"] = [f"token:{sign_tid}"]
    sign_witness = base.seal_ir(sign_witness)
    sign_errors = validate_hardening_v1_2_1(sign_witness)
    assert any("INVALID_UNRESOLVED_WITNESS_TOKEN_TYPE" in e for e in sign_errors)

    surface_bad = copy.deepcopy(good)
    r = surface_bad[EXTENSION_FIELD]["cross_boundary_continuations"][0]
    r.update({
        "boundary_class": "SURFACE",
        "source_surface_ref": "surface:S1",
        "target_surface_ref": "surface:S1",
        "boundary_resolution_claimed": True,
    })
    surface_bad = base.seal_ir(surface_bad)
    surface_errors = validate_hardening_v1_2_1(surface_bad)
    assert any("SURFACE_REQUIRES_DISTINCT_SURFACES" in e for e in surface_errors)

    line_bad = copy.deepcopy(good)
    r = line_bad[EXTENSION_FIELD]["cross_boundary_continuations"][0]
    r.update({
        "boundary_class": "LINE",
        "source_segment_ref": "segment:L1",
        "target_segment_ref": "segment:L1",
        "boundary_resolution_claimed": True,
    })
    line_bad = base.seal_ir(line_bad)
    line_errors = validate_hardening_v1_2_1(line_bad)
    assert any("LINE_REQUIRES_DISTINCT_SEGMENTS" in e for e in line_errors)

    same_group = copy.deepcopy(good)
    r = same_group[EXTENSION_FIELD]["cross_boundary_continuations"][0]
    r["target_group_ref"] = r["source_group_ref"]
    same_group = base.seal_ir(same_group)
    same_group_errors = validate_hardening_v1_2_1(same_group)
    assert any("DISTINCT_GROUPS_REQUIRED" in e for e in same_group_errors)

    merge_bad = copy.deepcopy(good)
    merge_bad[EXTENSION_FIELD]["cross_boundary_continuations"][0]["destructive_merge_performed"] = True
    merge_bad = base.seal_ir(merge_bad)
    merge_errors = validate_hardening_v1_2_1(merge_bad)
    assert any("DESTRUCTIVE_MERGE_FORBIDDEN" in e for e in merge_errors)

    wordhood_bad = copy.deepcopy(good)
    wordhood_bad[EXTENSION_FIELD]["cross_boundary_continuations"][0]["linguistic_wordhood_claimed"] = True
    wordhood_bad = base.seal_ir(wordhood_bad)
    wordhood_errors = validate_hardening_v1_2_1(wordhood_bad)
    assert any("LINGUISTIC_WORDHOOD_CLAIM_FORBIDDEN" in e for e in wordhood_errors)

    view = {
        "view_id": "v1.2.1-fixture-view",
        "ontology_version": "v1.2.1",
        "eligible_token_types": ["SIGN"],
        "allowed_token_fields": ["source_sign_id", "sequence_index"],
        "candidate_namespace": "JANUS-V1.2.1-FIXTURE",
        "raw_literal_use_explicitly_frozen": False,
        "explicit_nonsemantic_exceptions": [],
    }
    no_policy_errors = validate_scientific_view_v1_2_1(good, view)
    assert any("BOUNDARY_CONTINUATION_POLICY_REQUIRED" in e for e in no_policy_errors)
    assert any("UNRESOLVED_BOUNDARY_POLICY_REQUIRED" in e for e in no_policy_errors)

    boundary_only = copy.deepcopy(view)
    boundary_only["boundary_continuation_policy"] = CLAIM_BOUNDARY_POLICY
    missing_unresolved_errors = validate_scientific_view_v1_2_1(good, boundary_only)
    assert any("UNRESOLVED_BOUNDARY_POLICY_REQUIRED" in e for e in missing_unresolved_errors)

    view_ok = copy.deepcopy(boundary_only)
    view_ok["unresolved_boundary_policy"] = CLAIM_UNRESOLVED_POLICY
    view_ok_errors = validate_scientific_view_v1_2_1(good, view_ok)
    assert not view_ok_errors, view_ok_errors

    v11_result = v11.self_test()
    v11_pass = _v11_regression_pass(v11_result)
    assert v11_pass, v11_result

    return {
        "profile_id": PROFILE_ID,
        "inherited_v1_1_with_empty_v1_2_1_pass": not inherited_errors,
        "valid_unresolved_separator_witness_pass": not good_errors,
        "unresolved_without_witness_rejected": any("UNRESOLVED_BOUNDARY_REQUIRES_WITNESS_TOKEN" in e for e in no_witness_errors),
        "unresolved_SIGN_witness_rejected": any("INVALID_UNRESOLVED_WITNESS_TOKEN_TYPE" in e for e in sign_errors),
        "surface_same_surface_rejected": any("SURFACE_REQUIRES_DISTINCT_SURFACES" in e for e in surface_errors),
        "line_same_segment_rejected": any("LINE_REQUIRES_DISTINCT_SEGMENTS" in e for e in line_errors),
        "same_group_rejected": any("DISTINCT_GROUPS_REQUIRED" in e for e in same_group_errors),
        "destructive_merge_rejected": any("DESTRUCTIVE_MERGE_FORBIDDEN" in e for e in merge_errors),
        "linguistic_wordhood_claim_rejected": any("LINGUISTIC_WORDHOOD_CLAIM_FORBIDDEN" in e for e in wordhood_errors),
        "view_without_boundary_policy_rejected": any("BOUNDARY_CONTINUATION_POLICY_REQUIRED" in e for e in no_policy_errors),
        "view_without_unresolved_policy_rejected": any("UNRESOLVED_BOUNDARY_POLICY_REQUIRED" in e for e in missing_unresolved_errors),
        "view_with_fail_closed_policies_pass": not view_ok_errors,
        "v1_1_regression_self_test_pass": v11_pass,
        "v1_1_regression": v11_result,
        "javascript_executed": False,
        "decipherment_performed": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--validate")
    ap.add_argument("--view")
    args = ap.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), ensure_ascii=False, sort_keys=True))
        return
    if args.validate:
        ir = json.load(open(args.validate, encoding="utf-8"))
        errors = validate_hardening_v1_2_1(ir)
        if args.view:
            view = json.load(open(args.view, encoding="utf-8"))
            errors.extend(validate_scientific_view_v1_2_1(ir, view))
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, sort_keys=True))
        raise SystemExit(0 if not errors else 1)
    raise SystemExit("Use --self-test or --validate PATH")


if __name__ == "__main__":
    main()
