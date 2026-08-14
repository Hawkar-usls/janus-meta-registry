#!/usr/bin/env python3
"""JANUS Linear A typed-token corrective replay v0.6.2.

Replays v0.1-v0.6 after two representation corrections:
1) Aegean punctuation/control markers *900-*903 are removed before candidate construction.
2) Generic exact/approximate numeric literals are typed as numeric and cannot receive
   semantic word/suffix identity hashes.

Historical pre-filter and punctuation-only receipts are retained. This replay supersedes
them only for current inferential use. No new-anchor or decipherment claim can be emitted.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import janus_linear_a_full_corpus as full

# Preserve the historical numeric parser so the typing audit can measure what it missed.
if not hasattr(full, "_JANUS_V061_ORIGINAL_PARSE_NUMERIC_PIECE"):
    full._JANUS_V061_ORIGINAL_PARSE_NUMERIC_PIECE = full.parse_numeric_piece

import janus_linear_a_token_typing_policy_v0_6_2 as typing_policy

# Patch shared parser functions before downstream modules are imported/executed.
full.parse_numeric_piece = typing_policy.parse_exact_numeric_literal
full.parse_inscription = typing_policy.corrected_parse_inscription

import janus_linear_a_candidate_holdout as holdout
import janus_linear_a_survivor_decomposition as decomposition
import janus_linear_a_vir_subtype as vir_subtype
import janus_linear_a_known_subtracted as known_subtracted
import janus_linear_a_record_role as record_role

record_role.parse_layout = typing_policy.corrected_parse_layout

REPLAY_ID = "JANUS-LINEAR-A-TYPED-TOKEN-CORRECTIVE-REPLAY-v0.6.2"
CORRECTION_REASONS = [
    "AEGEAN_PUNCTUATION_WAS_PRESENT_IN_PRE_FILTER_CANDIDATE_AND_ROLE_GEOMETRY",
    "NUMERIC_LITERALS_NOT_COVERED_BY_THE_LEGACY_HARDCODED_FRACTION_MAP_ENTERED_SEMANTIC_CANDIDATE_SPACE",
]

STAGE_SPECS = [
    ("v0.1.2", full, "JANUS-LINEAR-A-FULL-CORPUS-RUN-2026-08-14-TYPED-TOKEN-v0.1.2.json", ["--permutations", "5000", "--seed", "260814025"]),
    ("v0.2.2", holdout, "JANUS-LINEAR-A-CANDIDATE-HOLDOUT-2026-08-14-TYPED-TOKEN-v0.2.2.json", ["--permutations", "5000", "--seed", "260814125"]),
    ("v0.3.2", decomposition, "JANUS-LINEAR-A-SURVIVOR-DECOMPOSITION-2026-08-14-TYPED-TOKEN-v0.3.2.json", ["--permutations", "5000", "--seed", "260814225"]),
    ("v0.4.2", vir_subtype, "JANUS-LINEAR-A-VIR-SUBTYPE-2026-08-14-TYPED-TOKEN-v0.4.2.json", ["--permutations", "20000", "--seed", "260814325"]),
    ("v0.5.2", known_subtracted, "JANUS-LINEAR-A-KNOWN-SUBTRACTED-CROSS-REGION-2026-08-14-TYPED-TOKEN-v0.5.2.json", ["--train-permutations", "5000", "--test-permutations", "10000", "--seed", "260814425"]),
    ("v0.6.2", record_role, "JANUS-LINEAR-A-RECORD-ROLE-CROSS-REGION-2026-08-14-TYPED-TOKEN-v0.6.2.json", ["--train-permutations", "5000", "--test-permutations", "10000", "--seed", "260814525"]),
]


def call_main(module, argv):
    old_argv = sys.argv
    sys.argv = [str(getattr(module, "__file__", module.__name__))] + list(argv)
    try:
        module.main()
    finally:
        sys.argv = old_argv


def annotate(path: Path, stage: str, numeric_scan: dict) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    original_uuid = data.get("artifact_uuid")
    original_version = data.get("version")
    data["original_artifact_uuid_before_typed_token_annotation"] = original_uuid
    data["original_version_before_typed_token_annotation"] = original_version
    data["artifact_uuid"] = f"{original_uuid}-TYPED-TOKEN-{stage}" if original_uuid else f"{REPLAY_ID}-{stage}"
    if original_version:
        data["version"] = f"{original_version}+TYPED_TOKEN_{stage}"
    data["typed_token_corrective_replay"] = {
        "replay_id": REPLAY_ID,
        "stage": stage,
        "correction_reasons": CORRECTION_REASONS,
        "typing_policy": typing_policy.policy_manifest(),
        "numeric_typing_scan": numeric_scan,
        "historical_pre_filter_receipts_retained": True,
        "punctuation_only_v0_6_1_receipts_retained": True,
        "current_receipt_authoritative_for_inference": True,
    }
    data.setdefault("source", {})["token_typing_policy_id"] = typing_policy.POLICY_ID
    gate = data.get("epistemic_gate", {})
    if gate.get("new_anchor_established") is not False:
        raise SystemExit(f"CLAIM_CEILING_FAIL:{stage}:new_anchor_established")
    if gate.get("decipherment_established") is not False:
        raise SystemExit(f"CLAIM_CEILING_FAIL:{stage}:decipherment_established")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def compact(stage: str, data: dict) -> dict:
    gate = data.get("epistemic_gate", {})
    out = {
        "stage": stage,
        "artifact_uuid": data.get("artifact_uuid"),
        "status": data.get("status"),
        "new_anchor_established": gate.get("new_anchor_established"),
        "decipherment_established": gate.get("decipherment_established"),
        "promotion": gate.get("promotion"),
    }
    for key in (
        "blind_numeric_candidate_gate_pass",
        "candidate_specific_heldout_gate_pass",
        "heldout_survivor_count",
        "RO_promotable_as_new_anchor",
        "VIR_promotable_as_new_anchor",
        "quantitative_subtype_candidate",
        "cross_region_survivor_count",
        "record_role_candidate_exists",
    ):
        if key in gate:
            out[key] = gate[key]
    return out


def selected_reveals(record_receipt: dict) -> list:
    out = []
    for family_key in ("word_family", "suffix_family"):
        family = record_receipt.get(family_key, {})
        for row in family.get("cross_region_results", []):
            out.append({
                "family": family.get("family"),
                "candidate_id": row.get("candidate_id"),
                "revealed_label": row.get("revealed_label"),
                "role": row.get("role"),
                "train_fwer_p": row.get("train_fwer_p"),
                "test_bonferroni_p": row.get("test_bonferroni_p"),
                "replication_pass": row.get("replication_pass"),
            })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args()

    corpus = Path(args.corpus)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    punctuation_scan = typing_policy.p61.scan_marker_counts(corpus)
    numeric_scan = typing_policy.scan_numeric_typing(corpus)

    receipts = []
    full_data = None
    record_data = None
    for stage, module, filename, extra_args in STAGE_SPECS:
        out_path = out_dir / filename
        call_main(module, ["--corpus", str(corpus), "--out", str(out_path)] + extra_args)
        data = annotate(out_path, stage, numeric_scan)
        receipts.append({"stage": stage, "path": str(out_path), "outcome": compact(stage, data)})
        if stage == "v0.1.2":
            full_data = data
        if stage == "v0.6.2":
            record_data = data

    manifest = {
        "artifact_uuid": "JANUS-LINEAR-A-TYPED-TOKEN-CORRECTIVE-REPLAY-MANIFEST-2026-08-14-v0.6.2",
        "version": "v0.6.2",
        "status": "TYPED_TOKEN_CORRECTIVE_REPLAY_EXECUTED",
        "replay_id": REPLAY_ID,
        "source": {
            "repository": "mwenge/lineara.xyz",
            "frozen_commit": full.CORPUS_COMMIT,
            "LinearAInscriptions_js_blob_sha": full.CORPUS_BLOB,
            "numeric_inventory_reference": "items_analysis/numbers.txt"
        },
        "typing_policy": typing_policy.policy_manifest(),
        "punctuation_scan": punctuation_scan,
        "numeric_typing_scan": numeric_scan,
        "reason_for_replay": {
            "punctuation_predecessor": "*900 / U+10101 was a strong pre-filter v0.6 record-role survivor and was falsified as punctuation.",
            "numeric_predecessor": "After punctuation correction, ¹⁄₅ became the strongest v0.6.1 train structural candidate; frozen corpus numbers.txt classifies ¹⁄₅ as numeric.",
            "classification": "REPRESENTATION_TYPE_BOUNDARY_REPAIR",
            "supersedes_for_current_inference": [
                "PRE_FILTER_v0.1-v0.6",
                "PUNCTUATION_ONLY_CORRECTIVE_REPLAY_v0.6.1"
            ]
        },
        "receipts": receipts,
        "full_corpus_counts": (full_data or {}).get("corpus_counts"),
        "final_record_role_state": compact("v0.6.2", record_data or {}),
        "final_record_role_selected_reveals": selected_reveals(record_data or {}),
        "epistemic_gate": {
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "BLOCKED_PENDING_TYPED_TOKEN_RESULT_INTERPRETATION"
        }
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "manifest": str(manifest_path),
        "punctuation_occurrences_filtered": punctuation_scan["total_filtered_occurrences"],
        "legacy_missed_numeric_occurrences": numeric_scan["legacy_missed_occurrences"],
        "legacy_missed_numeric_unique_tokens": numeric_scan["legacy_missed_unique_tokens"],
        "final_record_role_survivors": (record_data or {}).get("epistemic_gate", {}).get("cross_region_survivor_count"),
        "new_anchor_established": False,
        "decipherment_established": False
    }, sort_keys=True))


if __name__ == "__main__":
    main()
