#!/usr/bin/env python3
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/JANUS-SING-WHEN-YOURE-WINNING-ENUMERATED-EVENT-MVP-SOURCE-FRAME-v0.1.json"
EXT = ROOT / "data/JANUS-SING-WHEN-YOURE-WINNING-ENUMERATED-EVENT-MVP-SOURCE-FRAME-EXTENSION-v0.2.json"


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def is_pending(record):
    status = str(record.get("source_count_status", ""))
    return record.get("visible_same_subject_instances") is None or "PENDING" in status


def main():
    base = load(BASE)
    ext = load(EXT)
    errors = []

    base_records = base.get("candidate_designs", [])
    ext_records = ext.get("new_candidates", [])
    all_records = base_records + ext_records

    if len(base_records) != 28:
        errors.append(f"base candidate count changed: {len(base_records)} != 28")
    if len(ext_records) != 15:
        errors.append(f"extension candidate count changed: {len(ext_records)} != 15")
    if len(all_records) != 43:
        errors.append(f"combined candidate count: {len(all_records)} != 43")

    frame_ids = [r.get("frame_id") for r in all_records]
    design_keys = [r.get("design_cluster_key") for r in all_records]
    if len(frame_ids) != len(set(frame_ids)):
        errors.append("duplicate frame_id detected")
    if len(design_keys) != len(set(design_keys)):
        dup = [k for k, n in Counter(design_keys).items() if n > 1]
        errors.append(f"duplicate design_cluster_key detected: {dup}")

    # Historical v0.1 summary has an arithmetic error. Preserve the old file and verify the explicit correction.
    base_pending = sum(is_pending(r) for r in base_records)
    if base_pending != 17:
        errors.append(f"recomputed v0.1 pending count changed: {base_pending} != 17")
    correction = ext.get("base_integrity_correction", {})
    if correction.get("recorded_in_v0_1") != 16:
        errors.append("v0.2 must preserve the historical recorded v0.1 pending count of 16")
    if correction.get("recomputed_from_v0_1_candidate_records") != 17:
        errors.append("v0.2 must record corrected v0.1 pending count = 17")
    if correction.get("content_effect") != "COUNT_ONLY_NO_CANDIDATE_RECLASSIFICATION":
        errors.append("base correction must remain count-only")

    ext_pending = sum(is_pending(r) for r in ext_records)
    resolved_source_negative = [r for r in ext_records if r.get("visible_same_subject_instances") == 1]
    if ext_pending != 14:
        errors.append(f"extension pending count: {ext_pending} != 14")
    if len(resolved_source_negative) != 1 or resolved_source_negative[0].get("frame_id") != "EMV-040":
        errors.append("expected exactly one resolved SOURCE-negative extension control: EMV-040")
    if resolved_source_negative and resolved_source_negative[0].get("source_physical_subject") is not False:
        errors.append("EMV-040 must record SOURCE_PHYSICAL_SUBJECT=false for one visible subject instance")

    for r in ext_records:
        if r.get("visible_same_subject_instances") is None and "PENDING" not in str(r.get("source_count_status", "")):
            errors.append(f"{r.get('frame_id')}: null source count without explicit pending status")
        if not r.get("source_url"):
            errors.append(f"{r.get('frame_id')}: missing source_url")
        if not r.get("design_cluster_key"):
            errors.append(f"{r.get('frame_id')}: missing design_cluster_key")
        if not r.get("stratum"):
            errors.append(f"{r.get('frame_id')}: missing stratum")

    state = ext.get("enumeration_state", {})
    if state.get("base_candidates") != 28 or state.get("new_candidates") != 15 or state.get("total_candidates") != 43:
        errors.append("enumeration_state counts inconsistent with frozen 28+15=43 frame")
    if state.get("enumeration_threshold_met") is not True:
        errors.append("40-candidate enumeration threshold must be marked met")
    if state.get("frame_closed") is not False:
        errors.append("frame must remain open before image and duplicate audits")

    combined = ext.get("combined_frame_counts", {})
    expected_total_pending = base_pending + ext_pending
    if combined.get("base_pending_corrected") != 17:
        errors.append("combined frame must use corrected base pending count 17")
    if combined.get("extension_pending") != ext_pending:
        errors.append("combined extension pending count mismatch")
    if combined.get("total_pending_image_source_audit") != expected_total_pending:
        errors.append(
            f"combined pending audit count mismatch: {combined.get('total_pending_image_source_audit')} != {expected_total_pending}"
        )
    if combined.get("frame_closed") is not False:
        errors.append("combined source frame must remain open")

    # Counterexamples and anti-rescue constraints from the base frame must remain visible.
    by_id = {r.get("frame_id"): r for r in all_records}
    lebron = by_id.get("EMV-001")
    sportsnet = by_id.get("EMV-013")
    if not lebron or lebron.get("visible_same_subject_instances") != 5:
        errors.append("EMV-001 LeBron exact-five counterexample missing or altered")
    if not lebron or "FULL_CHAIN" not in str(lebron.get("known_boundary_status")):
        errors.append("EMV-001 full-chain status must be preserved")
    if not sportsnet or "FULL_CHAIN" not in str(sportsnet.get("known_boundary_status")):
        errors.append("EMV-013 non-memorabilia full-chain counterexample must be preserved")

    effect = ext.get("scientific_effect", {})
    if effect.get("matched_genre_prevalence") != "UNKNOWN":
        errors.append("matched-genre prevalence must remain UNKNOWN")
    if effect.get("rarity_claim") != "BLOCKED":
        errors.append("rarity claim must remain BLOCKED")

    out = {
        "artifact_id": ext.get("artifact_id"),
        "base_candidates": len(base_records),
        "extension_candidates": len(ext_records),
        "total_candidates": len(all_records),
        "base_pending_recomputed": base_pending,
        "extension_pending": ext_pending,
        "total_pending": expected_total_pending,
        "unique_frame_ids": len(set(frame_ids)),
        "unique_design_keys": len(set(design_keys)),
        "enumeration_threshold_met": len(all_records) >= 40,
        "frame_closed": state.get("frame_closed"),
        "errors": errors,
        "ok": not errors
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
