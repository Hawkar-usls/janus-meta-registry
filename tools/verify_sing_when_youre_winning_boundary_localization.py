#!/usr/bin/env python3
"""Verify JANUS Sing When You're Winning boundary-localized records.

This checker is intentionally narrow. It does not decide whether a human or image
really belongs to an identity class. It verifies that, once SOURCE/WORLD/RECEIPT
annotations are frozen, first-break labels and aggregate counts are internally
consistent and cannot be changed independently of the underlying booleans.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

ALLOWED_BREAKS = {"NONE", "SOURCE", "WORLD", "RECEIPT", "UNDETERMINED"}
ALLOWED_RELATIONS = {
    "SAME_REAL_SUBJECT_MULTIPLE_REPRESENTATIONS",
    "SAME_PERSISTENT_ENTITY_MULTIPLE_REPRESENTATIONS",
    "SHARED_GENETIC_OR_CLONE_LINEAGE",
    "MULTIVERSE_VARIANT_LINEAGE",
    "SHARED_ROLE_OR_MANTLE",
    "SAME_ACTOR_DIFFERENT_CHARACTERS",
    "DISTINCT_IDENTITIES",
    "REPLICATED_PROCESS_OR_PROGRAM_WITH_UNCLEAR_PERSISTENT_IDENTITY",
    "UNKNOWN_OR_INSUFFICIENT_PROVENANCE",
}


def derive_first_break(source: Optional[bool], world: Optional[bool], receipt: Optional[bool]) -> str:
    if source is None:
        return "UNDETERMINED"
    if source is False:
        return "SOURCE"
    if world is None:
        return "UNDETERMINED"
    if world is False:
        return "WORLD"
    if receipt is None:
        return "UNDETERMINED"
    if receipt is False:
        return "RECEIPT"
    return "NONE"


def require_bool_or_none(value: Any, field: str, case_id: str, errors: list[str]) -> None:
    if value is not None and not isinstance(value, bool):
        errors.append(f"{case_id}: {field} must be boolean or null")


def verify_case(case: Dict[str, Any], errors: list[str]) -> Dict[str, str]:
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        errors.append("case missing non-empty case_id")
        case_id = "<unknown>"

    relation = case.get("source_relation_type")
    if relation not in ALLOWED_RELATIONS:
        errors.append(f"{case_id}: unsupported source_relation_type={relation!r}")

    strict = case.get("source_strict_identity")
    lineage = case.get("source_lineage_shared")
    world = case.get("one_world")
    receipt = case.get("one_receipt")
    for field, value in (
        ("source_strict_identity", strict),
        ("source_lineage_shared", lineage),
        ("one_world", world),
        ("one_receipt", receipt),
    ):
        require_bool_or_none(value, field, case_id, errors)

    strict_break = derive_first_break(strict, world, receipt)
    lineage_break = derive_first_break(lineage, world, receipt)

    provided_strict = case.get("first_break_strict")
    provided_lineage = case.get("first_break_lineage")
    if provided_strict not in ALLOWED_BREAKS:
        errors.append(f"{case_id}: invalid first_break_strict={provided_strict!r}")
    elif provided_strict != strict_break:
        errors.append(
            f"{case_id}: first_break_strict={provided_strict} but derived={strict_break}"
        )

    if provided_lineage not in ALLOWED_BREAKS:
        errors.append(f"{case_id}: invalid first_break_lineage={provided_lineage!r}")
    elif provided_lineage != lineage_break:
        errors.append(
            f"{case_id}: first_break_lineage={provided_lineage} but derived={lineage_break}"
        )

    if case.get("role") == "TARGET_REFERENCE" and provided_strict != "NONE":
        errors.append(f"{case_id}: TARGET_REFERENCE must reproduce FULL_CHAIN or be explicitly reclassified")

    return {"strict": strict_break, "lineage": lineage_break}


def normalized_counts(counter: Counter[str]) -> Dict[str, int]:
    return {key: int(counter.get(key, 0)) for key in ("SOURCE", "WORLD", "RECEIPT", "NONE", "UNDETERMINED")}


def verify_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    errors: list[str] = []
    cases = doc.get("cases")
    if not isinstance(cases, list) or not cases:
        return {"ok": False, "errors": ["top-level cases must be a non-empty array"]}

    ids: set[str] = set()
    strict_control_breaks: Counter[str] = Counter()
    lineage_control_breaks: Counter[str] = Counter()
    target_count = 0

    for case in cases:
        if not isinstance(case, dict):
            errors.append("case entry must be an object")
            continue
        case_id = case.get("case_id")
        if isinstance(case_id, str):
            if case_id in ids:
                errors.append(f"duplicate case_id={case_id}")
            ids.add(case_id)

        derived = verify_case(case, errors)
        if case.get("role") == "TARGET_REFERENCE":
            target_count += 1
        else:
            strict_control_breaks[derived["strict"]] += 1
            lineage_control_breaks[derived["lineage"]] += 1

    if target_count != 1:
        errors.append(f"expected exactly one TARGET_REFERENCE, found {target_count}")

    expected_controls = len(cases) - target_count
    summary = doc.get("diagnostic_summary", {})
    if summary.get("controls_n") != expected_controls:
        errors.append(
            f"diagnostic_summary.controls_n={summary.get('controls_n')} but derived={expected_controls}"
        )

    derived_strict = normalized_counts(strict_control_breaks)
    derived_lineage = normalized_counts(lineage_control_breaks)
    if summary.get("strict_mode_first_break_counts") != derived_strict:
        errors.append(
            "diagnostic_summary.strict_mode_first_break_counts does not match derived counts: "
            + json.dumps(derived_strict, sort_keys=True)
        )
    if summary.get("lineage_mode_first_break_counts") != derived_lineage:
        errors.append(
            "diagnostic_summary.lineage_mode_first_break_counts does not match derived counts: "
            + json.dumps(derived_lineage, sort_keys=True)
        )

    return {
        "ok": not errors,
        "artifact_id": doc.get("artifact_id"),
        "cases": len(cases),
        "controls": expected_controls,
        "derived_strict_counts": derived_strict,
        "derived_lineage_counts": derived_lineage,
        "errors": errors,
    }


def main(argv: Iterable[str]) -> int:
    args = list(argv)
    if len(args) != 2:
        print(f"usage: {args[0]} <boundary-execution.json>", file=sys.stderr)
        return 2
    path = Path(args[1])
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [f"cannot load {path}: {exc}"]}, indent=2))
        return 2
    result = verify_document(doc)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
