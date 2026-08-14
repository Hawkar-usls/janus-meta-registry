#!/usr/bin/env python3
"""JANUS Linear A punctuation-filtered corrective replay v0.6.1.

The pre-filter v0.1-v0.6 runners are preserved as historical code. This orchestrator applies
`janus_linear_a_parser_policy_v0_6_1` at runtime, replays the same declared statistical
algorithms, writes distinct corrected receipts, and emits a manifest binding the replay to
its parser correction.

A corrected replay can invalidate, preserve, or change earlier candidates. It cannot by
itself establish decipherment or a new lexical anchor.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import janus_linear_a_full_corpus as full
import janus_linear_a_parser_policy_v0_6_1 as policy

# Patch the shared v0.1 parser before importing downstream modules that reference it.
full.parse_inscription = policy.corrected_parse_inscription

import janus_linear_a_candidate_holdout as holdout
import janus_linear_a_survivor_decomposition as decomposition
import janus_linear_a_vir_subtype as vir_subtype
import janus_linear_a_known_subtracted as known_subtracted
import janus_linear_a_record_role as record_role

# v0.6 has its own layout parser because row geometry is part of the evidence channel.
record_role.parse_layout = policy.corrected_parse_layout

REPLAY_ID = "JANUS-LINEAR-A-CORRECTIVE-REPLAY-v0.6.1"
CORRECTION_REASON = "AEGEAN_PUNCTUATION_WAS_PRESENT_IN_PRE_FILTER_CANDIDATE_AND_ROLE_GEOMETRY"

STAGE_SPECS = [
    {
        "stage": "v0.1.1",
        "module": full,
        "filename": "JANUS-LINEAR-A-FULL-CORPUS-RUN-2026-08-14-PUNCTUATION-FILTERED-v0.1.1.json",
        "args": ["--permutations", "5000", "--seed", "260814025"],
    },
    {
        "stage": "v0.2.1",
        "module": holdout,
        "filename": "JANUS-LINEAR-A-CANDIDATE-HOLDOUT-2026-08-14-PUNCTUATION-FILTERED-v0.2.1.json",
        "args": ["--permutations", "5000", "--seed", "260814125"],
    },
    {
        "stage": "v0.3.1",
        "module": decomposition,
        "filename": "JANUS-LINEAR-A-SURVIVOR-DECOMPOSITION-2026-08-14-PUNCTUATION-FILTERED-v0.3.1.json",
        "args": ["--permutations", "5000", "--seed", "260814225"],
    },
    {
        "stage": "v0.4.1",
        "module": vir_subtype,
        "filename": "JANUS-LINEAR-A-VIR-SUBTYPE-2026-08-14-PUNCTUATION-FILTERED-v0.4.1.json",
        "args": ["--permutations", "20000", "--seed", "260814325"],
    },
    {
        "stage": "v0.5.1",
        "module": known_subtracted,
        "filename": "JANUS-LINEAR-A-KNOWN-SUBTRACTED-CROSS-REGION-2026-08-14-PUNCTUATION-FILTERED-v0.5.1.json",
        "args": [
            "--train-permutations", "5000",
            "--test-permutations", "10000",
            "--seed", "260814425",
        ],
    },
    {
        "stage": "v0.6.1",
        "module": record_role,
        "filename": "JANUS-LINEAR-A-RECORD-ROLE-CROSS-REGION-2026-08-14-PUNCTUATION-FILTERED-v0.6.1.json",
        "args": [
            "--train-permutations", "5000",
            "--test-permutations", "10000",
            "--seed", "260814525",
        ],
    },
]


def call_main(module, argv):
    old_argv = sys.argv
    sys.argv = [str(getattr(module, "__file__", module.__name__))] + list(argv)
    try:
        module.main()
    finally:
        sys.argv = old_argv


def annotate_receipt(path: Path, stage: str, marker_counts: dict) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    original_uuid = data.get("artifact_uuid")
    original_version = data.get("version")
    data["original_artifact_uuid_before_corrective_annotation"] = original_uuid
    data["original_version_before_corrective_annotation"] = original_version
    data["artifact_uuid"] = f"{original_uuid}-PUNCTUATION-FILTERED-{stage}" if original_uuid else f"{REPLAY_ID}-{stage}"
    if original_version:
        data["version"] = f"{original_version}+PUNCTUATION_FILTER_{stage}"
    data["corrective_replay"] = {
        "replay_id": REPLAY_ID,
        "stage": stage,
        "correction_reason": CORRECTION_REASON,
        "parser_policy": policy.parser_policy_manifest(),
        "marker_counts_in_frozen_corpus_before_filter": marker_counts,
        "pre_filter_receipts_retained_as_historical_evidence": True,
        "pre_filter_receipts_authoritative_for_post_correction_inference": False,
        "corrected_receipt_authoritative_for_current_inference": True,
    }
    data.setdefault("source", {})["parser_policy_id"] = policy.PARSER_POLICY_ID
    gate = data.get("epistemic_gate", {})
    if gate.get("new_anchor_established") is not False:
        raise SystemExit(f"CLAIM_CEILING_FAIL:{stage}:new_anchor_established")
    if gate.get("decipherment_established") is not False:
        raise SystemExit(f"CLAIM_CEILING_FAIL:{stage}:decipherment_established")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def compact_outcome(stage: str, data: dict) -> dict:
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

    marker_counts = policy.scan_marker_counts(corpus)
    receipts = []
    for spec in STAGE_SPECS:
        out_path = out_dir / spec["filename"]
        argv = ["--corpus", str(corpus), "--out", str(out_path)] + spec["args"]
        call_main(spec["module"], argv)
        data = annotate_receipt(out_path, spec["stage"], marker_counts)
        receipts.append({
            "stage": spec["stage"],
            "path": str(out_path),
            "outcome": compact_outcome(spec["stage"], data),
        })

    last = receipts[-1]["outcome"]
    manifest = {
        "artifact_uuid": "JANUS-LINEAR-A-PUNCTUATION-CORRECTIVE-REPLAY-MANIFEST-2026-08-14-v0.6.1",
        "version": "v0.6.1",
        "status": "CORRECTIVE_REPLAY_EXECUTED",
        "replay_id": REPLAY_ID,
        "source": {
            "repository": "mwenge/lineara.xyz",
            "frozen_commit": full.CORPUS_COMMIT,
            "LinearAInscriptions_js_blob_sha": full.CORPUS_BLOB,
        },
        "parser_policy": policy.parser_policy_manifest(),
        "marker_counts_in_frozen_corpus_before_filter": marker_counts,
        "reason_for_replay": {
            "pre_filter_v0_6_survivor": "*900 / U+10101",
            "post_score_identity": "AEGEAN WORD SEPARATOR DOT",
            "classification": "PARSER_BOUNDARY_CANARY_REDISCOVERY",
            "consequence": "Pre-filter receipts remain historical evidence but are superseded for inferential use by punctuation-filtered replay receipts.",
        },
        "receipts": receipts,
        "final_record_role_state": last,
        "epistemic_gate": {
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "BLOCKED_PENDING_CORRECTED_RECEIPT_INTERPRETATION",
        },
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "manifest": str(manifest_path),
        "filtered_occurrences": marker_counts["total_filtered_occurrences"],
        "stages_replayed": len(receipts),
        "final_record_role_survivors": last.get("cross_region_survivor_count"),
        "new_anchor_established": False,
        "decipherment_established": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
