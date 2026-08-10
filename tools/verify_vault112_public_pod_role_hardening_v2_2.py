#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

REQ = {
    "logical_ref_formid", "winning_file", "base_signature", "base_fixed_formid",
    "base_editorid", "base_name", "ref_editorid", "ref_name", "position_x",
    "position_y", "position_z", "initially_disabled", "enable_parent_raw",
    "owner_raw", "ref_script_raw", "base_script_raw", "base_model_raw", "full_path",
}

JAMES_MONITOR_BASE = "00031190"

# Public-derived base-role evidence. These labels constrain post-export
# classification only. They do NOT establish a specific placed REFR as James's
# pod without the authoritative Fallout3.esm all-REFR export.
POD_BASE_ROLES = {
    "0002A45B": "PLAYER_EXPLICIT_BASE",
    "000B364C": "DAD_SCRIPT_BOUND_BASE_CANDIDATE",
    "000572D6": "DAD_NAMED_BASE_CANDIDATE",
    "000B06D4": "BROKEN_EXPLICIT_BASE",
}
DAD_ROLE_BASES = {"000B364C", "000572D6"}
EXCLUDED_FROM_JAMES_BY_ROLE = {"0002A45B", "000B06D4"}

PUBLIC_DERIVED_PROVENANCE = {
    "source": "TaleOfTwoWastelands/TaleOfTwoWastelands",
    "snapshot_commit": "105d6f3264bf1112c132c27322e7176fb656cd70",
    "authority": "PUBLIC_DERIVED_BASE_ROLE_EVIDENCE_NOT_VANILLA_PLACEMENT_PROOF",
    "records": [
        {
            "vanilla_base_formid": "0002A45B",
            "ttw_formid": "0602A45B",
            "editorid": "MQ04PlayerPodActivator",
            "ttw_path": "TaleOfTwoWastelands/Activators/MQ04PlayerPodActivator.xml",
            "observed_script": "MQ04PlayerPodShellScript",
            "role": "PLAYER_EXPLICIT_BASE",
        },
        {
            "vanilla_base_formid": "000B364C",
            "ttw_formid": "060B364C",
            "editorid": "TLpod01",
            "ttw_path": "TaleOfTwoWastelands/Activators/TLpod01.xml",
            "observed_script": "MQ04DadPodScript",
            "role": "DAD_SCRIPT_BOUND_BASE_CANDIDATE",
        },
        {
            "vanilla_base_formid": "000572D6",
            "ttw_formid": "060572D6",
            "editorid": "MQ04PodDad",
            "ttw_path": "TaleOfTwoWastelands/Activators/MQ04PodDad.xml",
            "observed_script": "MQ04NonPlayerPodScript",
            "role": "DAD_NAMED_BASE_CANDIDATE",
        },
        {
            "vanilla_base_formid": "000B06D4",
            "ttw_formid": "060B06D4",
            "editorid": "TLpodBroken",
            "ttw_path": "TaleOfTwoWastelands/Activators/TLpodBroken.xml",
            "role": "BROKEN_EXPLICIT_BASE",
        },
    ],
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_tsv(path: Path) -> tuple[list[dict[str, str]], set[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f, delimiter="\t")
        return list(r), set(r.fieldnames or [])


def check_columns(actual: set[str]) -> None:
    missing = sorted(REQ - actual)
    if missing:
        raise ValueError(f"missing columns: {missing}")


def pfloat(v: str, field: str) -> float:
    try:
        x = float(str(v).strip())
    except Exception as exc:
        raise ValueError(f"{field} must be numeric, got {v!r}") from exc
    if not math.isfinite(x):
        raise ValueError(f"{field} must be finite")
    return x


def formid(row: dict[str, str], field: str = "logical_ref_formid") -> str:
    return str(row.get(field, "")).strip().upper()


def xyz(row: dict[str, str]) -> tuple[float, float, float]:
    rid = formid(row) or "?"
    return (
        pfloat(row.get("position_x", ""), f"{rid}.position_x"),
        pfloat(row.get("position_y", ""), f"{rid}.position_y"),
        pfloat(row.get("position_z", ""), f"{rid}.position_z"),
    )


def distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def summarize(row: dict[str, str]) -> dict:
    base = formid(row, "base_fixed_formid")
    return {
        "refid": formid(row),
        "base_formid": base,
        "base_role": POD_BASE_ROLES.get(base, "UNCLASSIFIED"),
        "base_signature": str(row.get("base_signature", "")).strip().upper(),
        "base_editorid": row.get("base_editorid", ""),
        "base_name": row.get("base_name", ""),
        "ref_editorid": row.get("ref_editorid", ""),
        "ref_name": row.get("ref_name", ""),
        "base_script_raw": row.get("base_script_raw", ""),
        "ref_script_raw": row.get("ref_script_raw", ""),
        "initially_disabled": row.get("initially_disabled", ""),
        "enable_parent_raw": row.get("enable_parent_raw", ""),
    }


def _rank_from(anchor: dict[str, str], candidates: list[dict[str, str]]) -> list[tuple[float, dict[str, str]]]:
    return sorted(
        ((distance(xyz(anchor), xyz(c)), c) for c in candidates),
        key=lambda x: (x[0], formid(x[1])),
    )


def audit(rows: list[dict[str, str]]) -> dict:
    if not rows:
        raise ValueError("all-refs export is empty")

    seen: set[str] = set()
    for row in rows:
        rid = formid(row)
        if not rid:
            raise ValueError("row missing logical_ref_formid")
        if rid in seen:
            raise ValueError(f"duplicate logical RefID: {rid}")
        seen.add(rid)
        xyz(row)

    monitors = [r for r in rows if formid(r, "base_fixed_formid") == JAMES_MONITOR_BASE]
    pod_rows = [r for r in rows if formid(r, "base_fixed_formid") in POD_BASE_ROLES]
    dad_role_rows = [r for r in pod_rows if formid(r, "base_fixed_formid") in DAD_ROLE_BASES]
    player_rows = [r for r in pod_rows if formid(r, "base_fixed_formid") == "0002A45B"]
    broken_rows = [r for r in pod_rows if formid(r, "base_fixed_formid") == "000B06D4"]

    bindings = []
    for mon in monitors:
        all_ranked = _rank_from(mon, pod_rows)
        dad_ranked = _rank_from(mon, dad_role_rows)

        nearest_any = None
        if all_ranked:
            d, row = all_ranked[0]
            base = formid(row, "base_fixed_formid")
            nearest_any = summarize(row)
            nearest_any.update({
                "distance_units": d,
                "excluded_from_james_by_role": base in EXCLUDED_FROM_JAMES_BY_ROLE,
            })

        dad_candidates = []
        for d, row in dad_ranked:
            item = summarize(row)
            item.update({
                "distance_units": d,
                "placement_identity_proven_by_public_role_evidence": False,
                "james_pod_instance_proven": False,
            })
            dad_candidates.append(item)

        if not dad_candidates:
            classification = "NO_ROLE_BOUND_DAD_POD_PLACEMENT_IN_INPUT"
            unique_role_bound_candidate = False
            exact_james_pod_refid = None
            nearest_dad_tie = False
        elif len(dad_candidates) == 1:
            classification = "SINGLE_DAD_ROLE_PLACEMENT_CANDIDATE_NOT_YET_INSTANCE_PROOF"
            unique_role_bound_candidate = True
            exact_james_pod_refid = None
            nearest_dad_tie = False
        else:
            nearest_dad_tie = abs(dad_candidates[0]["distance_units"] - dad_candidates[1]["distance_units"]) < 1e-6
            classification = (
                "MULTIPLE_DAD_ROLE_PLACEMENTS_DISTANCE_TIE_PRESERVED"
                if nearest_dad_tie
                else "MULTIPLE_DAD_ROLE_PLACEMENTS_REQUIRE_PRIMARY_INSTANCE_BINDING"
            )
            unique_role_bound_candidate = False
            exact_james_pod_refid = None

        proximity_conflict = bool(
            nearest_any and nearest_any["base_formid"] in EXCLUDED_FROM_JAMES_BY_ROLE
        )

        bindings.append({
            "monitor_refid": formid(mon),
            "nearest_any_known_pod": nearest_any,
            "nearest_any_would_conflict_with_role_if_used_as_james": proximity_conflict,
            "dad_role_candidates": dad_candidates,
            "dad_role_candidate_count": len(dad_candidates),
            "nearest_dad_distance_tie": nearest_dad_tie,
            "classification": classification,
            "unique_role_bound_candidate": unique_role_bound_candidate,
            "exact_james_pod_refid": exact_james_pod_refid,
            "role_evidence_proves_exact_placement": False,
            "proximity_proves_exact_placement": False,
        })

    return {
        "schema": "janus.fo3.vault112_public_pod_role_hardening_audit.v2_2",
        "input_row_count": len(rows),
        "james_monitor_ref_count": len(monitors),
        "known_pod_ref_count": len(pod_rows),
        "dad_role_pod_ref_count": len(dad_role_rows),
        "player_pod_ref_count": len(player_rows),
        "broken_pod_ref_count": len(broken_rows),
        "public_derived_provenance": PUBLIC_DERIVED_PROVENANCE,
        "pod_base_roles": POD_BASE_ROLES,
        "monitor_role_bound_bindings": bindings,
        "admission": {
            "blind_all_refr_export_remains_authoritative_input_requirement": True,
            "public_derived_role_evidence_can_exclude_player_or_broken_pod_from_james_candidate": True,
            "public_derived_role_evidence_can_prove_exact_james_placed_ref": False,
            "distance_alone_can_prove_james_pod": False,
            "james_specific_persisted_memory_state": "NOT_ESTABLISHED",
            "persisted_james_state_candidate": "BLOCKED_PENDING_PRIMARY_ESM_INSTANCE_AND_STATE_BINDING",
        },
        "claim_ceiling": {
            "PLAYER_POD_BASE_EQUALS_JAMES_POD_BY_PROXIMITY": False,
            "BROKEN_POD_BASE_EQUALS_JAMES_POD_BY_PROXIMITY": False,
            "DAD_ROLE_BASE_EQUALS_EXACT_JAMES_PLACED_REF": False,
            "TTW_DERIVED_XML_EQUALS_VANILLA_ALL_REFR_DUMP": False,
            "BASE_SCRIPT_BINDING_EQUALS_PLACED_INSTANCE_BINDING": False,
            "ROLE_BOUND_CANDIDATE_EQUALS_PERSISTED_MEMORY_STATE": False,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("all_refs_tsv", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    rows, cols = read_tsv(args.all_refs_tsv)
    check_columns(cols)
    result = audit(rows)
    result["input"] = {"path": str(args.all_refs_tsv), "sha256": sha256(args.all_refs_tsv)}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
