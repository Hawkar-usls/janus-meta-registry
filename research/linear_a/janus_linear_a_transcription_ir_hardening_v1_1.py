#!/usr/bin/env python3
"""Backward-compatible hardening profile for JANUS Linear A transcription IR v1.1.

The base wire format remains JANUS-LINEAR-TRANSCRIPTION-IR-v1.0. Documents that
opt in by declaring `janus_hardening_v1_1` receive two additive source-fidelity
features:

1. cross-surface continuation relations that preserve the original source groups;
2. explicit bindings between unresolved SIGN_ID_CONFLICT disagreements and the
   competing identity assertions that produced them.

No decipherment, semantic assignment, or automatic source-token merge occurs here.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import janus_linear_a_transcription_ir_v1_0 as base

PROFILE_ID = "JANUS-LINEAR-TRANSCRIPTION-IR-HARDENING-v1.1"
CONTINUATION_TYPE = "SOURCE_CONTINUATION_ACROSS_SURFACE"
ALLOWED_IDENTITY_SYSTEMS = {
    "SOURCE_LABEL",
    "SOURCE_SIGN_ID",
    "ENCODED_GLYPH",
    "EDITORIAL_SIGN_ID",
    "OTHER",
}
ALLOWED_CONFLICT_RESOLUTION = {"UNRESOLVED", "TECHNICAL_ONLY"}
CLAIM_BEARING_CONTINUATION_POLICY = "PRESERVE_SOURCE_BOUNDARIES_RELATION_ONLY"
CLAIM_BEARING_CONFLICT_POLICY = "EXCLUDE_CONFLICTED_TOKENS"


def _ids(items: Any, field: str) -> set[str]:
    if not isinstance(items, list):
        return set()
    return {x.get(field) for x in items if isinstance(x, dict) and isinstance(x.get(field), str)}


def _ref_id(ref: Any, kind: str) -> str | None:
    if not isinstance(ref, str) or not ref.startswith(kind + ":"):
        return None
    value = ref.split(":", 1)[1]
    return value or None


def _check_ref(ref: Any, kind: str, allowed: set[str], prefix: str, errors: list[str]) -> None:
    ident = _ref_id(ref, kind)
    if ident is None or ident not in allowed:
        errors.append(f"{prefix}:UNRESOLVED_{kind.upper()}_REF:{ref}")


def validate_hardening_v1_1(ir: dict[str, Any], *, require_hash: bool = True) -> list[str]:
    errors = base.validate_ir(ir, require_hash=require_hash)
    if errors:
        return ["V1_1_PARENT_V1_0_INVALID"] + errors

    ext = ir.get("janus_hardening_v1_1")
    if not isinstance(ext, dict):
        return ["V1_1_EXTENSION_MISSING_OR_NOT_OBJECT"]
    if ext.get("profile_id") != PROFILE_ID:
        errors.append(f"V1_1_PROFILE_ID_MISMATCH:{ext.get('profile_id')}")

    continuations = ext.get("cross_surface_continuations")
    conflicts = ext.get("identity_conflict_bindings")
    if not isinstance(continuations, list):
        errors.append("V1_1_CONTINUATIONS_NOT_LIST")
        continuations = []
    if not isinstance(conflicts, list):
        errors.append("V1_1_IDENTITY_CONFLICT_BINDINGS_NOT_LIST")
        conflicts = []

    surface_ids = _ids(ir.get("surfaces"), "surface_id")
    group_ids = _ids(ir.get("groups"), "group_id")
    token_ids = _ids(ir.get("tokens"), "token_id")
    disagreement_ids = _ids(ir.get("disagreements"), "disagreement_id")
    provenance_ids = _ids(ir.get("provenance_receipt", {}).get("provenance_refs"), "ref_id")
    disagreements = {
        d.get("disagreement_id"): d
        for d in ir.get("disagreements", [])
        if isinstance(d, dict) and isinstance(d.get("disagreement_id"), str)
    }

    continuation_ids: set[str] = set()
    for i, row in enumerate(continuations):
        prefix = f"V1_1_CONTINUATIONS[{i}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix}:NOT_OBJECT")
            continue
        for field in (
            "continuation_id", "continuation_type", "source_group_ref", "target_group_ref",
            "source_surface_ref", "target_surface_ref", "evidence_class", "provenance_refs",
            "source_boundaries_preserved", "destructive_merge_performed",
        ):
            if field not in row:
                errors.append(f"{prefix}:MISSING_REQUIRED:{field}")
        cid = row.get("continuation_id")
        if not isinstance(cid, str) or not cid:
            errors.append(f"{prefix}:INVALID_ID")
        elif cid in continuation_ids:
            errors.append(f"{prefix}:DUPLICATE_ID:{cid}")
        else:
            continuation_ids.add(cid)
        if row.get("continuation_type") != CONTINUATION_TYPE:
            errors.append(f"{prefix}:INVALID_TYPE:{row.get('continuation_type')}")
        _check_ref(row.get("source_group_ref"), "group", group_ids, prefix, errors)
        _check_ref(row.get("target_group_ref"), "group", group_ids, prefix, errors)
        _check_ref(row.get("source_surface_ref"), "surface", surface_ids, prefix, errors)
        _check_ref(row.get("target_surface_ref"), "surface", surface_ids, prefix, errors)
        if row.get("source_surface_ref") == row.get("target_surface_ref"):
            errors.append(f"{prefix}:DISTINCT_SURFACES_REQUIRED")
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
        if row.get("linguistic_wordhood_claimed", False) is not False:
            errors.append(f"{prefix}:LINGUISTIC_WORDHOOD_CLAIM_FORBIDDEN")

    binding_ids: set[str] = set()
    for i, row in enumerate(conflicts):
        prefix = f"V1_1_IDENTITY_CONFLICTS[{i}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix}:NOT_OBJECT")
            continue
        for field in (
            "conflict_binding_id", "disagreement_ref", "token_refs", "assertions",
            "resolution_state", "semantic_class_authority_granted", "provenance_refs",
        ):
            if field not in row:
                errors.append(f"{prefix}:MISSING_REQUIRED:{field}")
        bid = row.get("conflict_binding_id")
        if not isinstance(bid, str) or not bid:
            errors.append(f"{prefix}:INVALID_ID")
        elif bid in binding_ids:
            errors.append(f"{prefix}:DUPLICATE_ID:{bid}")
        else:
            binding_ids.add(bid)

        did = _ref_id(row.get("disagreement_ref"), "disagreement")
        if did is None or did not in disagreement_ids:
            errors.append(f"{prefix}:UNRESOLVED_DISAGREEMENT_REF:{row.get('disagreement_ref')}")
            disagreement = None
        else:
            disagreement = disagreements.get(did)
            if disagreement and disagreement.get("disagreement_type") != "SIGN_ID_CONFLICT":
                errors.append(f"{prefix}:BOUND_DISAGREEMENT_NOT_SIGN_ID_CONFLICT:{did}")

        refs = row.get("token_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{prefix}:TOKEN_REFS_EMPTY_OR_INVALID")
        else:
            for ref in refs:
                _check_ref(ref, "token", token_ids, prefix, errors)

        assertions = row.get("assertions")
        values: list[str] = []
        if not isinstance(assertions, list) or len(assertions) < 2:
            errors.append(f"{prefix}:AT_LEAST_TWO_ASSERTIONS_REQUIRED")
        else:
            assertion_ids: set[str] = set()
            for ai, assertion in enumerate(assertions):
                aprefix = f"{prefix}:ASSERTIONS[{ai}]"
                if not isinstance(assertion, dict):
                    errors.append(f"{aprefix}:NOT_OBJECT")
                    continue
                for field in ("assertion_id", "identity_system", "identity_value", "provenance_refs"):
                    if field not in assertion:
                        errors.append(f"{aprefix}:MISSING_REQUIRED:{field}")
                aid = assertion.get("assertion_id")
                if not isinstance(aid, str) or not aid:
                    errors.append(f"{aprefix}:INVALID_ID")
                elif aid in assertion_ids:
                    errors.append(f"{aprefix}:DUPLICATE_ID:{aid}")
                else:
                    assertion_ids.add(aid)
                if assertion.get("identity_system") not in ALLOWED_IDENTITY_SYSTEMS:
                    errors.append(f"{aprefix}:INVALID_IDENTITY_SYSTEM:{assertion.get('identity_system')}")
                value = assertion.get("identity_value")
                if not isinstance(value, str) or not value:
                    errors.append(f"{aprefix}:INVALID_IDENTITY_VALUE")
                else:
                    values.append(value)
                aprov = assertion.get("provenance_refs")
                if not isinstance(aprov, list) or not aprov:
                    errors.append(f"{aprefix}:MISSING_OR_EMPTY_PROVENANCE_REFS")
                else:
                    for ref in aprov:
                        if ref not in provenance_ids:
                            errors.append(f"{aprefix}:UNKNOWN_PROVENANCE_REF:{ref}")
            if len(set(values)) < 2:
                errors.append(f"{prefix}:ASSERTIONS_DO_NOT_PRESERVE_DISTINCT_IDENTITY_VALUES")

        resolution = row.get("resolution_state")
        if resolution not in ALLOWED_CONFLICT_RESOLUTION:
            errors.append(f"{prefix}:INVALID_RESOLUTION_STATE:{resolution}")
        if resolution == "UNRESOLVED" and row.get("semantic_class_authority_granted") is not False:
            errors.append(f"{prefix}:SEMANTIC_AUTHORITY_FORBIDDEN_FOR_UNRESOLVED_CONFLICT")
        if row.get("source_identity_overwrite_performed", False) is not False:
            errors.append(f"{prefix}:SOURCE_IDENTITY_OVERWRITE_FORBIDDEN")

        prov = row.get("provenance_refs")
        if not isinstance(prov, list) or not prov:
            errors.append(f"{prefix}:MISSING_OR_EMPTY_PROVENANCE_REFS")
        else:
            for ref in prov:
                if ref not in provenance_ids:
                    errors.append(f"{prefix}:UNKNOWN_PROVENANCE_REF:{ref}")

    return errors


def validate_scientific_view_v1_1(ir: dict[str, Any], view_spec: dict[str, Any]) -> list[str]:
    errors = validate_hardening_v1_1(ir, require_hash=True)
    if errors:
        return ["V1_1_SCIENTIFIC_VIEW_PARENT_INVALID"] + errors
    base_errors = base.validate_scientific_view(ir, view_spec)
    errors.extend(base_errors)
    ext = ir["janus_hardening_v1_1"]
    if ext.get("cross_surface_continuations"):
        if view_spec.get("continuation_policy") != CLAIM_BEARING_CONTINUATION_POLICY:
            errors.append(
                "V1_1_SCIENTIFIC_VIEW:CONTINUATION_POLICY_REQUIRED:"
                + CLAIM_BEARING_CONTINUATION_POLICY
            )
    unresolved = [
        row for row in ext.get("identity_conflict_bindings", [])
        if isinstance(row, dict) and row.get("resolution_state") == "UNRESOLVED"
    ]
    if unresolved and view_spec.get("identity_conflict_policy") != CLAIM_BEARING_CONFLICT_POLICY:
        errors.append(
            "V1_1_SCIENTIFIC_VIEW:IDENTITY_CONFLICT_POLICY_REQUIRED:"
            + CLAIM_BEARING_CONFLICT_POLICY
        )
    return errors


def make_hardened_fixture() -> dict[str, Any]:
    ir = copy.deepcopy(base.make_minimal_fixture())
    # Add a second physical surface and a source-native group on it.
    ir["surfaces"].append({
        "surface_id": "S2", "source_surface_label": "b", "provenance_refs": ["P1"]
    })
    ir["segments"].append({
        "segment_id": "L2", "segment_type": "LINE", "parent_segment_id": None,
        "surface_id": "S2", "source_label": "1", "sequence_index": 1,
        "provenance_refs": ["P1"],
    })
    ir["tokens"].append({
        "token_id": "T4", "source_raw": "𐙫", "token_type": "SIGN", "sequence_index": 3,
        "source_sign_id": "A319", "segment_id": "L2", "group_ids": ["G3"],
        "reading_status": "CERTAIN", "provenance_refs": ["P1"],
    })
    ir["groups"].append({
        "group_id": "G3", "group_type": "SOURCE_WORD", "member_token_ids": ["T4"],
        "derived": False, "provenance_refs": ["P1"],
    })
    ir["disagreements"].append({
        "disagreement_id": "D1", "disagreement_type": "SIGN_ID_CONFLICT",
        "status": "MECHANICALLY_LOCALIZED", "source_refs": ["token:T1"],
        "target_refs": ["token:T4"], "provenance_refs": ["P1"],
    })
    ir["janus_hardening_v1_1"] = {
        "profile_id": PROFILE_ID,
        "cross_surface_continuations": [
            {
                "continuation_id": "C1",
                "continuation_type": CONTINUATION_TYPE,
                "source_group_ref": "group:G1",
                "target_group_ref": "group:G3",
                "source_surface_ref": "surface:S1",
                "target_surface_ref": "surface:S2",
                "evidence_class": "EDITORIAL_ASSERTION",
                "provenance_refs": ["P1"],
                "source_boundaries_preserved": True,
                "destructive_merge_performed": False,
                "linguistic_wordhood_claimed": False,
            }
        ],
        "identity_conflict_bindings": [
            {
                "conflict_binding_id": "IC1",
                "disagreement_ref": "disagreement:D1",
                "token_refs": ["token:T1", "token:T4"],
                "assertions": [
                    {
                        "assertion_id": "ICA1", "identity_system": "SOURCE_LABEL",
                        "identity_value": "*904", "provenance_refs": ["P1"],
                    },
                    {
                        "assertion_id": "ICA2", "identity_system": "ENCODED_GLYPH",
                        "identity_value": "U+1066B/A319", "provenance_refs": ["P1"],
                    },
                ],
                "resolution_state": "UNRESOLVED",
                "semantic_class_authority_granted": False,
                "source_identity_overwrite_performed": False,
                "provenance_refs": ["P1"],
            }
        ],
    }
    return base.seal_ir(ir)


def self_test() -> dict[str, Any]:
    base_fixture = base.make_minimal_fixture()
    base_errors = base.validate_ir(base_fixture)
    assert not base_errors, base_errors

    good = make_hardened_fixture()
    good_errors = validate_hardening_v1_1(good)
    assert not good_errors, good_errors

    bad_same_surface = copy.deepcopy(good)
    bad_same_surface["janus_hardening_v1_1"]["cross_surface_continuations"][0]["target_surface_ref"] = "surface:S1"
    bad_same_surface = base.seal_ir(bad_same_surface)
    same_surface_errors = validate_hardening_v1_1(bad_same_surface)
    assert any("DISTINCT_SURFACES_REQUIRED" in e for e in same_surface_errors), same_surface_errors

    bad_merge = copy.deepcopy(good)
    bad_merge["janus_hardening_v1_1"]["cross_surface_continuations"][0]["destructive_merge_performed"] = True
    bad_merge = base.seal_ir(bad_merge)
    merge_errors = validate_hardening_v1_1(bad_merge)
    assert any("DESTRUCTIVE_MERGE_FORBIDDEN" in e for e in merge_errors), merge_errors

    bad_authority = copy.deepcopy(good)
    bad_authority["janus_hardening_v1_1"]["identity_conflict_bindings"][0]["semantic_class_authority_granted"] = True
    bad_authority = base.seal_ir(bad_authority)
    authority_errors = validate_hardening_v1_1(bad_authority)
    assert any("SEMANTIC_AUTHORITY_FORBIDDEN" in e for e in authority_errors), authority_errors

    view = {
        "view_id": "v1.1-fixture-view",
        "ontology_version": "v1.1",
        "eligible_token_types": ["SIGN"],
        "allowed_token_fields": ["source_sign_id", "sequence_index"],
        "candidate_namespace": "JANUS-V1.1-FIXTURE",
        "raw_literal_use_explicitly_frozen": False,
        "explicit_nonsemantic_exceptions": [],
    }
    no_policy_errors = validate_scientific_view_v1_1(good, view)
    assert any("CONTINUATION_POLICY_REQUIRED" in e for e in no_policy_errors), no_policy_errors
    assert any("IDENTITY_CONFLICT_POLICY_REQUIRED" in e for e in no_policy_errors), no_policy_errors

    view_ok = copy.deepcopy(view)
    view_ok["continuation_policy"] = CLAIM_BEARING_CONTINUATION_POLICY
    view_ok["identity_conflict_policy"] = CLAIM_BEARING_CONFLICT_POLICY
    view_ok_errors = validate_scientific_view_v1_1(good, view_ok)
    assert not view_ok_errors, view_ok_errors

    return {
        "profile_id": PROFILE_ID,
        "base_v1_0_fixture_still_valid": not base_errors,
        "valid_hardened_fixture_pass": not good_errors,
        "same_surface_continuation_rejected": any("DISTINCT_SURFACES_REQUIRED" in e for e in same_surface_errors),
        "destructive_merge_rejected": any("DESTRUCTIVE_MERGE_FORBIDDEN" in e for e in merge_errors),
        "unresolved_conflict_semantic_authority_rejected": any("SEMANTIC_AUTHORITY_FORBIDDEN" in e for e in authority_errors),
        "claim_view_without_continuation_policy_rejected": any("CONTINUATION_POLICY_REQUIRED" in e for e in no_policy_errors),
        "claim_view_without_conflict_policy_rejected": any("IDENTITY_CONFLICT_POLICY_REQUIRED" in e for e in no_policy_errors),
        "claim_view_with_fail_closed_policies_pass": not view_ok_errors,
        "javascript_executed": False,
        "decipherment_performed": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--validate", help="Path to a sealed base-v1.0 IR declaring v1.1 hardening")
    ap.add_argument("--view", help="Optional scientific view spec for --validate")
    args = ap.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), ensure_ascii=False, sort_keys=True))
        return
    if args.validate:
        ir = json.load(open(args.validate, encoding="utf-8"))
        errors = validate_hardening_v1_1(ir)
        if args.view:
            view = json.load(open(args.view, encoding="utf-8"))
            errors.extend(validate_scientific_view_v1_1(ir, view))
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, sort_keys=True))
        raise SystemExit(0 if not errors else 1)
    raise SystemExit("Use --self-test or --validate PATH")


if __name__ == "__main__":
    main()
