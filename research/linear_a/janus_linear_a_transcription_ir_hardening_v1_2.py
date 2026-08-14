#!/usr/bin/env python3
"""Additive v1.2 hardening for source continuation across typed/unresolved boundaries.

v1.2 does not rewrite the admitted v1.1 profile. A v1.2 document must first be
a valid sealed v1.0 IR and a valid v1.1 hardening document. It then may carry
`SOURCE_CONTINUATION_ACROSS_BOUNDARY` relations with boundary class SURFACE,
LINE, or UNRESOLVED_SURFACE_OR_LINE.
"""
from __future__ import annotations

import argparse
import copy
import json
from typing import Any

import janus_linear_a_transcription_ir_v1_0 as base
import janus_linear_a_transcription_ir_hardening_v1_1 as v11

PROFILE_ID = "JANUS-LINEAR-TRANSCRIPTION-IR-HARDENING-v1.2"
RELATION_TYPE = "SOURCE_CONTINUATION_ACROSS_BOUNDARY"
BOUNDARY_CLASSES = {"SURFACE", "LINE", "UNRESOLVED_SURFACE_OR_LINE"}
UNRESOLVED_WITNESS_TOKEN_TYPES = {"SEPARATOR", "PUNCTUATION", "EDITORIAL_MARK", "GAP", "DAMAGE", "UNKNOWN"}
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


def _validate_ref(ref: Any, kind: str, allowed: set[str], prefix: str, errors: list[str], *, required: bool = True) -> str | None:
    if ref is None and not required:
        return None
    ident = _ref_id(ref, kind)
    if ident is None or ident not in allowed:
        errors.append(f"{prefix}:UNRESOLVED_{kind.upper()}_REF:{ref}")
        return None
    return ident


def validate_hardening_v1_2(ir: dict[str, Any], *, require_hash: bool = True) -> list[str]:
    parent_errors = v11.validate_hardening_v1_1(ir, require_hash=require_hash)
    if parent_errors:
        return ["V1_2_PARENT_V1_1_INVALID"] + parent_errors

    errors: list[str] = []
    ext = ir.get("janus_hardening_v1_2")
    if not isinstance(ext, dict):
        return ["V1_2_EXTENSION_MISSING_OR_NOT_OBJECT"]
    if ext.get("profile_id") != PROFILE_ID:
        errors.append(f"V1_2_PROFILE_ID_MISMATCH:{ext.get('profile_id')}")

    rows = ext.get("cross_boundary_continuations")
    if not isinstance(rows, list):
        errors.append("V1_2_CROSS_BOUNDARY_CONTINUATIONS_NOT_LIST")
        rows = []

    group_ids = _ids(ir.get("groups"), "group_id")
    token_ids = _ids(ir.get("tokens"), "token_id")
    surface_ids = _ids(ir.get("surfaces"), "surface_id")
    segment_ids = _ids(ir.get("segments"), "segment_id")
    provenance_ids = _ids(ir.get("provenance_receipt", {}).get("provenance_refs"), "ref_id")
    token_by_id = {
        t.get("token_id"): t for t in ir.get("tokens", [])
        if isinstance(t, dict) and isinstance(t.get("token_id"), str)
    }
    segment_by_id = {
        s.get("segment_id"): s for s in ir.get("segments", [])
        if isinstance(s, dict) and isinstance(s.get("segment_id"), str)
    }

    seen: set[str] = set()
    for i, row in enumerate(rows):
        prefix = f"V1_2_CONTINUATIONS[{i}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix}:NOT_OBJECT")
            continue
        for field in (
            "continuation_id", "continuation_type", "source_group_ref", "target_group_ref",
            "boundary_class", "boundary_witness_token_refs", "evidence_class", "provenance_refs",
            "source_boundaries_preserved", "destructive_merge_performed", "linguistic_wordhood_claimed",
        ):
            if field not in row:
                errors.append(f"{prefix}:MISSING_REQUIRED:{field}")

        cid = row.get("continuation_id")
        if not isinstance(cid, str) or not cid:
            errors.append(f"{prefix}:INVALID_ID")
        elif cid in seen:
            errors.append(f"{prefix}:DUPLICATE_ID:{cid}")
        else:
            seen.add(cid)
        if row.get("continuation_type") != RELATION_TYPE:
            errors.append(f"{prefix}:INVALID_TYPE:{row.get('continuation_type')}")

        sg = _validate_ref(row.get("source_group_ref"), "group", group_ids, prefix, errors)
        tg = _validate_ref(row.get("target_group_ref"), "group", group_ids, prefix, errors)
        if sg is not None and tg is not None and sg == tg:
            errors.append(f"{prefix}:DISTINCT_GROUPS_REQUIRED")

        boundary_class = row.get("boundary_class")
        if boundary_class not in BOUNDARY_CLASSES:
            errors.append(f"{prefix}:INVALID_BOUNDARY_CLASS:{boundary_class}")

        witness_refs = row.get("boundary_witness_token_refs")
        if not isinstance(witness_refs, list):
            errors.append(f"{prefix}:BOUNDARY_WITNESS_REFS_NOT_LIST")
            witness_refs = []
        witness_ids: list[str] = []
        for ref in witness_refs:
            ident = _validate_ref(ref, "token", token_ids, prefix, errors)
            if ident is not None:
                witness_ids.append(ident)

        if row.get("evidence_class") not in base.ALLOWED_EVIDENCE_CLASSES:
            errors.append(f"{prefix}:INVALID_EVIDENCE_CLASS:{row.get('evidence_class')}")
        prov = row.get("provenance_refs")
        if not isinstance(prov, list) or not prov:
            errors.append(f"{prefix}:MISSING_OR_EMPTY_PROVENANCE_REFS")
        else:
            for ref in prov:
                if ref not in provenance_ids:
                    errors.append(f"{prefix}:UNKNOWN_PROVENANCE_REF:{ref}")

        if row.get("source_boundaries_preserved") is not True:
            errors.append(f"{prefix}:SOURCE_BOUNDARIES_MUST_BE_PRESERVED")
        if row.get("destructive_merge_performed") is not False:
            errors.append(f"{prefix}:DESTRUCTIVE_MERGE_FORBIDDEN")
        if row.get("linguistic_wordhood_claimed") is not False:
            errors.append(f"{prefix}:LINGUISTIC_WORDHOOD_CLAIM_FORBIDDEN")

        if boundary_class == "SURFACE":
            s1 = _validate_ref(row.get("source_surface_ref"), "surface", surface_ids, prefix, errors)
            s2 = _validate_ref(row.get("target_surface_ref"), "surface", surface_ids, prefix, errors)
            if s1 is not None and s2 is not None and s1 == s2:
                errors.append(f"{prefix}:SURFACE_REQUIRES_DISTINCT_SURFACES")
            if row.get("boundary_resolution_claimed", True) is not True:
                errors.append(f"{prefix}:SURFACE_CLASS_REQUIRES_RESOLVED_BOUNDARY")

        elif boundary_class == "LINE":
            seg1 = _validate_ref(row.get("source_segment_ref"), "segment", segment_ids, prefix, errors)
            seg2 = _validate_ref(row.get("target_segment_ref"), "segment", segment_ids, prefix, errors)
            if seg1 is not None and seg2 is not None:
                if seg1 == seg2:
                    errors.append(f"{prefix}:LINE_REQUIRES_DISTINCT_SEGMENTS")
                else:
                    s1 = segment_by_id.get(seg1, {}).get("surface_id")
                    s2 = segment_by_id.get(seg2, {}).get("surface_id")
                    if s1 is not None and s2 is not None and s1 != s2:
                        errors.append(f"{prefix}:LINE_SEGMENTS_MUST_SHARE_SOURCE_SURFACE")
            line_meta = row.get("source_line_metadata_provenance_refs")
            line_meta_ok = isinstance(line_meta, list) and bool(line_meta) and all(ref in provenance_ids for ref in line_meta)
            if not witness_ids and not line_meta_ok:
                errors.append(f"{prefix}:LINE_REQUIRES_BOUNDARY_WITNESS_OR_SOURCE_LINE_METADATA")
            if row.get("boundary_resolution_claimed", True) is not True:
                errors.append(f"{prefix}:LINE_CLASS_REQUIRES_RESOLVED_BOUNDARY")

        elif boundary_class == "UNRESOLVED_SURFACE_OR_LINE":
            if not witness_ids:
                errors.append(f"{prefix}:UNRESOLVED_BOUNDARY_REQUIRES_WITNESS_TOKEN")
            for tid in witness_ids:
                token_type = token_by_id.get(tid, {}).get("token_type")
                if token_type not in UNRESOLVED_WITNESS_TOKEN_TYPES:
                    errors.append(f"{prefix}:INVALID_UNRESOLVED_WITNESS_TOKEN_TYPE:{tid}:{token_type}")
            for field, kind, allowed in (
                ("source_surface_ref", "surface", surface_ids),
                ("target_surface_ref", "surface", surface_ids),
                ("source_segment_ref", "segment", segment_ids),
                ("target_segment_ref", "segment", segment_ids),
            ):
                if row.get(field) is not None:
                    _validate_ref(row.get(field), kind, allowed, prefix, errors, required=False)
            if row.get("boundary_resolution_claimed", False) is not False:
                errors.append(f"{prefix}:UNRESOLVED_BOUNDARY_CANNOT_CLAIM_RESOLUTION")

    return errors


def validate_scientific_view_v1_2(ir: dict[str, Any], view_spec: dict[str, Any]) -> list[str]:
    errors = validate_hardening_v1_2(ir, require_hash=True)
    if errors:
        return ["V1_2_SCIENTIFIC_VIEW_PARENT_INVALID"] + errors
    errors.extend(v11.validate_scientific_view_v1_1(ir, view_spec))
    rows = ir["janus_hardening_v1_2"].get("cross_boundary_continuations", [])
    if rows and view_spec.get("boundary_continuation_policy") != CLAIM_BOUNDARY_POLICY:
        errors.append(f"V1_2_SCIENTIFIC_VIEW:BOUNDARY_CONTINUATION_POLICY_REQUIRED:{CLAIM_BOUNDARY_POLICY}")
    unresolved = any(isinstance(r, dict) and r.get("boundary_class") == "UNRESOLVED_SURFACE_OR_LINE" for r in rows)
    if unresolved and view_spec.get("unresolved_boundary_policy") != CLAIM_UNRESOLVED_POLICY:
        errors.append(f"V1_2_SCIENTIFIC_VIEW:UNRESOLVED_BOUNDARY_POLICY_REQUIRED:{CLAIM_UNRESOLVED_POLICY}")
    return errors


def make_fixture() -> dict[str, Any]:
    ir = v11.make_hardened_fixture()
    # Make inherited v1.1 relations empty for a clean continuation-v1.2 fixture;
    # this remains a valid v1.1 document and keeps conflict semantics independently tested by v1.1.
    ir["janus_hardening_v1_1"]["cross_surface_continuations"] = []
    ir["janus_hardening_v1_1"]["identity_conflict_bindings"] = []
    # Add a source-native separator witness that is not merged into either source word group.
    next_index = max(t.get("sequence_index", 0) for t in ir["tokens"]) + 1
    ir["tokens"].append({
        "token_id": "TB1",
        "source_raw": "\\n",
        "token_type": "SEPARATOR",
        "sequence_index": next_index,
        "source_sign_id": None,
        "segment_id": None,
        "group_ids": [],
        "reading_status": "CERTAIN",
        "provenance_refs": ["P1"],
    })
    groups = [g["group_id"] for g in ir["groups"] if isinstance(g, dict) and isinstance(g.get("group_id"), str)]
    if len(groups) < 2:
        raise AssertionError("fixture needs two groups")
    ir["janus_hardening_v1_2"] = {
        "profile_id": PROFILE_ID,
        "cross_boundary_continuations": [
            {
                "continuation_id": "CB1",
                "continuation_type": RELATION_TYPE,
                "source_group_ref": f"group:{groups[0]}",
                "target_group_ref": f"group:{groups[1]}",
                "boundary_class": "UNRESOLVED_SURFACE_OR_LINE",
                "boundary_witness_token_refs": ["token:TB1"],
                "boundary_resolution_claimed": False,
                "evidence_class": "MECHANICALLY_LOCALIZED",
                "provenance_refs": ["P1"],
                "source_boundaries_preserved": True,
                "destructive_merge_performed": False,
                "linguistic_wordhood_claimed": False,
            }
        ],
    }
    return base.seal_ir(ir)


def self_test() -> dict[str, Any]:
    inherited = v11.make_hardened_fixture()
    inherited["janus_hardening_v1_2"] = {"profile_id": PROFILE_ID, "cross_boundary_continuations": []}
    inherited = base.seal_ir(inherited)
    inherited_errors = validate_hardening_v1_2(inherited)
    assert not inherited_errors, inherited_errors

    good = make_fixture()
    good_errors = validate_hardening_v1_2(good)
    assert not good_errors, good_errors

    no_witness = copy.deepcopy(good)
    no_witness["janus_hardening_v1_2"]["cross_boundary_continuations"][0]["boundary_witness_token_refs"] = []
    no_witness = base.seal_ir(no_witness)
    no_witness_errors = validate_hardening_v1_2(no_witness)
    assert any("UNRESOLVED_BOUNDARY_REQUIRES_WITNESS_TOKEN" in e for e in no_witness_errors)

    sign_witness = copy.deepcopy(good)
    sign_token = next(t["token_id"] for t in sign_witness["tokens"] if t.get("token_type") == "SIGN")
    sign_witness["janus_hardening_v1_2"]["cross_boundary_continuations"][0]["boundary_witness_token_refs"] = [f"token:{sign_token}"]
    sign_witness = base.seal_ir(sign_witness)
    sign_witness_errors = validate_hardening_v1_2(sign_witness)
    assert any("INVALID_UNRESOLVED_WITNESS_TOKEN_TYPE" in e for e in sign_witness_errors)

    surface_bad = copy.deepcopy(good)
    r = surface_bad["janus_hardening_v1_2"]["cross_boundary_continuations"][0]
    r["boundary_class"] = "SURFACE"
    r["source_surface_ref"] = "surface:S1"
    r["target_surface_ref"] = "surface:S1"
    r["boundary_resolution_claimed"] = True
    surface_bad = base.seal_ir(surface_bad)
    surface_errors = validate_hardening_v1_2(surface_bad)
    assert any("SURFACE_REQUIRES_DISTINCT_SURFACES" in e for e in surface_errors)

    line_bad = copy.deepcopy(good)
    r = line_bad["janus_hardening_v1_2"]["cross_boundary_continuations"][0]
    r["boundary_class"] = "LINE"
    r["source_segment_ref"] = "segment:L1"
    r["target_segment_ref"] = "segment:L1"
    r["boundary_resolution_claimed"] = True
    line_bad = base.seal_ir(line_bad)
    line_errors = validate_hardening_v1_2(line_bad)
    assert any("LINE_REQUIRES_DISTINCT_SEGMENTS" in e for e in line_errors)

    same_group = copy.deepcopy(good)
    r = same_group["janus_hardening_v1_2"]["cross_boundary_continuations"][0]
    r["target_group_ref"] = r["source_group_ref"]
    same_group = base.seal_ir(same_group)
    same_group_errors = validate_hardening_v1_2(same_group)
    assert any("DISTINCT_GROUPS_REQUIRED" in e for e in same_group_errors)

    bad_merge = copy.deepcopy(good)
    bad_merge["janus_hardening_v1_2"]["cross_boundary_continuations"][0]["destructive_merge_performed"] = True
    bad_merge = base.seal_ir(bad_merge)
    merge_errors = validate_hardening_v1_2(bad_merge)
    assert any("DESTRUCTIVE_MERGE_FORBIDDEN" in e for e in merge_errors)

    bad_wordhood = copy.deepcopy(good)
    bad_wordhood["janus_hardening_v1_2"]["cross_boundary_continuations"][0]["linguistic_wordhood_claimed"] = True
    bad_wordhood = base.seal_ir(bad_wordhood)
    wordhood_errors = validate_hardening_v1_2(bad_wordhood)
    assert any("LINGUISTIC_WORDHOOD_CLAIM_FORBIDDEN" in e for e in wordhood_errors)

    view = {
        "view_id": "v1.2-fixture-view",
        "ontology_version": "v1.2",
        "eligible_token_types": ["SIGN"],
        "allowed_token_fields": ["source_sign_id", "sequence_index"],
        "candidate_namespace": "JANUS-V1.2-FIXTURE",
        "raw_literal_use_explicitly_frozen": False,
        "explicit_nonsemantic_exceptions": [],
    }
    no_policy_errors = validate_scientific_view_v1_2(good, view)
    assert any("BOUNDARY_CONTINUATION_POLICY_REQUIRED" in e for e in no_policy_errors)
    assert any("UNRESOLVED_BOUNDARY_POLICY_REQUIRED" in e for e in no_policy_errors)

    boundary_only = copy.deepcopy(view)
    boundary_only["boundary_continuation_policy"] = CLAIM_BOUNDARY_POLICY
    missing_unresolved_errors = validate_scientific_view_v1_2(good, boundary_only)
    assert any("UNRESOLVED_BOUNDARY_POLICY_REQUIRED" in e for e in missing_unresolved_errors)

    view_ok = copy.deepcopy(boundary_only)
    view_ok["unresolved_boundary_policy"] = CLAIM_UNRESOLVED_POLICY
    view_ok_errors = validate_scientific_view_v1_2(good, view_ok)
    assert not view_ok_errors, view_ok_errors

    v11_regression = v11.self_test()
    return {
        "profile_id": PROFILE_ID,
        "inherited_v1_1_with_empty_v1_2_pass": not inherited_errors,
        "valid_unresolved_separator_witness_pass": not good_errors,
        "unresolved_without_witness_rejected": any("UNRESOLVED_BOUNDARY_REQUIRES_WITNESS_TOKEN" in e for e in no_witness_errors),
        "unresolved_sign_witness_rejected": any("INVALID_UNRESOLVED_WITNESS_TOKEN_TYPE" in e for e in sign_witness_errors),
        "surface_without_distinct_surfaces_rejected": any("SURFACE_REQUIRES_DISTINCT_SURFACES" in e for e in surface_errors),
        "line_without_distinct_segments_rejected": any("LINE_REQUIRES_DISTINCT_SEGMENTS" in e for e in line_errors),
        "same_group_rejected": any("DISTINCT_GROUPS_REQUIRED" in e for e in same_group_errors),
        "destructive_merge_rejected": any("DESTRUCTIVE_MERGE_FORBIDDEN" in e for e in merge_errors),
        "linguistic_wordhood_claim_rejected": any("LINGUISTIC_WORDHOOD_CLAIM_FORBIDDEN" in e for e in wordhood_errors),
        "view_without_boundary_policy_rejected": any("BOUNDARY_CONTINUATION_POLICY_REQUIRED" in e for e in no_policy_errors),
        "view_without_unresolved_policy_rejected": any("UNRESOLVED_BOUNDARY_POLICY_REQUIRED" in e for e in missing_unresolved_errors),
        "view_with_fail_closed_policies_pass": not view_ok_errors,
        "v1_1_regression_self_test_pass": all(v is True for k, v in v11_regression.items() if k not in {"profile_id"}),
        "v1_1_regression": v11_regression,
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
        errors = validate_hardening_v1_2(ir)
        if args.view:
            view = json.load(open(args.view, encoding="utf-8"))
            errors.extend(validate_scientific_view_v1_2(ir, view))
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, sort_keys=True))
        raise SystemExit(0 if not errors else 1)
    raise SystemExit("Use --self-test or --validate PATH")


if __name__ == "__main__":
    main()
