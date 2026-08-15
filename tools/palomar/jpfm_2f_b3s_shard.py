#!/usr/bin/env python3
"""JPFM-2F-B3S: deterministic tile-shard execution of the frozen B3 same-64 morphology replay.

This file does not evaluate a global scientific outcome. Each invocation executes one
non-overlapping tile shard and emits a receipt + source sidecar. The aggregate runner
is the only component allowed to evaluate the preregistered B3 gates.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import gzip
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jpfm_2f_b2_tile_lineage_replay as b2
import jpfm_2f_b3_shape_compat_replay as b3

EXPECTED_SAMPLE_N = 64
EXPECTED_TILES = 52
FROZEN_SHARD_COUNT = 4
DETECTION_WORKERS = 10


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def stable_text_sha(values) -> str:
    text = "\n".join(str(v) for v in values) + "\n"
    return sha256_bytes(text.encode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--upstream-root", required=True, type=Path)
    ap.add_argument("--work-dir", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--shard-index", required=True, type=int)
    ap.add_argument("--shard-count", default=FROZEN_SHARD_COUNT, type=int)
    args = ap.parse_args()

    if args.shard_count != FROZEN_SHARD_COUNT:
        raise RuntimeError(f"frozen shard_count is {FROZEN_SHARD_COUNT}, got {args.shard_count}")
    if not 0 <= args.shard_index < args.shard_count:
        raise RuntimeError("invalid shard-index")

    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[B3S shard {args.shard_index}] [1/8] reconstruct frozen same-64 parent sample", flush=True)
    manifest, s0 = b2.load_inputs(args.manifest)
    full = b2.select_same_64(manifest)
    full = full.merge(
        s0[["src_id", "tile_id", "object_id", "ra", "dec", "plate_id"]],
        on="src_id", validate="one_to_one"
    )
    if len(full) != EXPECTED_SAMPLE_N or full.src_id.nunique() != EXPECTED_SAMPLE_N:
        raise RuntimeError("same-64 reconstruction failed")

    tile_ids = sorted(full.tile_id.astype(str).unique())
    if len(tile_ids) != EXPECTED_TILES:
        raise RuntimeError(f"expected {EXPECTED_TILES} distinct tiles, got {len(tile_ids)}")
    assignment = {tid: i % args.shard_count for i, tid in enumerate(tile_ids)}
    assigned_tiles = [tid for tid in tile_ids if assignment[tid] == args.shard_index]
    if len(assigned_tiles) != EXPECTED_TILES // args.shard_count:
        raise RuntimeError("unexpected deterministic shard tile count")
    sample = full[full.tile_id.astype(str).isin(assigned_tiles)].copy()
    if sample.empty or sample.src_id.duplicated().any():
        raise RuntimeError("invalid shard source subset")

    sample_src_ids = sorted(sample.src_id.astype(str))
    print(
        f"[B3S shard {args.shard_index}] rows={len(sample)} tiles={len(assigned_tiles)} "
        f"plates={sample.plate_id.nunique()}", flush=True
    )

    print(f"[B3S shard {args.shard_index}] [2/8] sparse exact tile reconstruction", flush=True)
    tiles_root = args.work_dir / "tiles"
    tile_replay = b2.reconstruct_tiles(sample, args.upstream_root, tiles_root)
    good_tiles = set(tile_replay.loc[tile_replay.tile_identity == "RECONSTRUCTED", "tile_id"].astype(str))
    sample["tile_identity_reconstructed"] = sample.tile_id.astype(str).isin(good_tiles)

    print(f"[B3S shard {args.shard_index}] [3/8] pass1 -> PSFEx -> pass2", flush=True)
    unique_replay = tile_replay.drop_duplicates("tile_id").to_dict("records")
    det = []
    with cf.ThreadPoolExecutor(max_workers=DETECTION_WORKERS) as ex:
        futs = [ex.submit(b2.run_detection_one, r, args.upstream_root, tiles_root) for r in unique_replay]
        for i, fut in enumerate(cf.as_completed(futs), 1):
            det.append(fut.result())
            if i % 4 == 0 or i == len(futs):
                print(f"[B3S shard {args.shard_index}] detection {i}/{len(futs)}", flush=True)
    det_df = pd.DataFrame(det)
    det_map = {
        str(r.tile_id): str(r.detection_status)
        for r in det_df.itertuples(index=False)
    } if len(det_df) else {}

    print(f"[B3S shard {args.shard_index}] [4/8] exact NUMBER/object lineage", flush=True)
    audit = b2.audit_sample_against_pass2(sample, tiles_root)
    audit["tile_identity_reconstructed"] = audit.tile_id.astype(str).isin(good_tiles)
    audit["tile_detection_status"] = audit.tile_id.astype(str).map(det_map).fillna("MISSING_DETECTION_RECEIPT")

    print(f"[B3S shard {args.shard_index}] [5/8] apply frozen OpenCV compatibility adapter", flush=True)
    patch_meta = b3.patch_shape_compat(args.upstream_root)

    print(f"[B3S shard {args.shard_index}] [6/8] repaired experimental shape stage", flush=True)
    shape, shape_exec = b2.run_upstream_shape(sample, args.upstream_root, args.work_dir, tiles_root)
    if len(shape):
        shape["src_id"] = shape.src_id.astype(str)
        keep = [c for c in shape.columns if c in {
            "src_id", "profile_diff", "circularity", "area", "shape_defect", "circle_deviation",
            "shape_confidence", "elongation", "stars_used", "shape_failed", "failure_reason",
            "reject_flag", "reject_reason"
        }]
        audit = audit.merge(shape[keep], on="src_id", how="left", validate="one_to_one")
    else:
        audit["shape_failed"] = 1
        audit["failure_reason"] = "SHAPE_STAGE_OUTPUT_MISSING"

    print(f"[B3S shard {args.shard_index}] [7/8] freeze shard sidecar", flush=True)
    audit["b3s_shard_index"] = int(args.shard_index)
    audit["b3s_shard_count"] = int(args.shard_count)
    audit = audit.sort_values(["structural_cluster", "sample_role", "src_id"], kind="stable").reset_index(drop=True)
    sidecar_csv = audit.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    sidecar_csv_sha = sha256_bytes(sidecar_csv)

    sidecar_name = f"JANUS-PALOMAR-JPFM-2F-B3S-SHARD-{args.shard_index}-SIDECAR-RUN-001.csv.gz"
    receipt_name = f"JANUS-PALOMAR-JPFM-2F-B3S-SHARD-{args.shard_index}-RECEIPT-RUN-001.json"
    sidecar_path = args.out_dir / sidecar_name
    receipt_path = args.out_dir / receipt_name
    with sidecar_path.open("wb") as fout:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fout, mtime=0) as gz:
            gz.write(sidecar_csv)
    sidecar_gz_sha = sha256_bytes(sidecar_path.read_bytes())

    exact = audit.exact_object_status.eq("EXACT_NUMBER_RECOVERED")
    exact_n = int(exact.sum())
    shape_failed = pd.to_numeric(audit.get("shape_failed"), errors="coerce").fillna(1).astype(int)
    shape_ok = int((exact & shape_failed.eq(0)).sum())
    raw_cols = ["pass2_fwhm_image", "pass2_elongation", "pass2_spread_model"]
    raw = audit.loc[exact, raw_cols].apply(pd.to_numeric, errors="coerce").to_numpy(float) if exact_n else np.empty((0, 3))
    raw_finite = int(np.isfinite(raw).all(axis=1).sum()) if exact_n else 0

    print(f"[B3S shard {args.shard_index}] [8/8] write non-global shard receipt", flush=True)
    receipt = {
        "artifact_id": f"JANUS-PALOMAR-JPFM-2F-B3S-SHARD-{args.shard_index}-RECEIPT-RUN-001",
        "experiment_id": "JPFM-2F-B3S",
        "schema_version": "1.0",
        "date": pd.Timestamp.utcnow().date().isoformat(),
        "status": "EXECUTED_SHARD_RECEIPT__NO_GLOBAL_OUTCOME",
        "claim_ceiling": "EXECUTION_SHARD_RECEIPT_ONLY__GLOBAL_B3_GATES_NOT_EVALUATED__EXTERNAL_LABELS_SEALED",
        "bindings": {
            "execution_plan_path": "data/JANUS-PALOMAR-JPFM-2F-B3S-SHARDED-EXECUTION-PLAN-v1.0.json",
            "B3_admission_path": "data/JANUS-PALOMAR-JPFM-2F-B3-SHAPE-COMPATIBILITY-REPLAY-ADMISSION-v1.0.json",
            "poss_commit": b2.POSS_COMMIT,
            "structural_manifest_csv_sha256": b2.MANIFEST_CSV_SHA256,
            "structural_manifest_gzip_sha256": b2.MANIFEST_GZ_SHA256
        },
        "shard": {
            "index": int(args.shard_index),
            "count": int(args.shard_count),
            "assignment_rule": "lexicographically sorted frozen tile_id ordinal mod 4",
            "assigned_tiles": assigned_tiles,
            "assigned_tiles_sha256": stable_text_sha(assigned_tiles),
            "source_rows": int(len(sample)),
            "source_ids_sha256": stable_text_sha(sample_src_ids),
            "distinct_tiles": int(len(assigned_tiles)),
            "distinct_plates": int(sample.plate_id.nunique())
        },
        "execution": {
            "tile_reconstructed": int(len(good_tiles)),
            "detection_tiles_pass": int((det_df.detection_status == "PASS").sum()) if len(det_df) else 0,
            "detection_status_census": {str(k): int(v) for k, v in det_df.detection_status.value_counts(dropna=False).items()} if len(det_df) else {},
            "exact_NUMBER_recovered": exact_n,
            "raw_pass2_morphology_finite": raw_finite,
            "shape_success_exact": shape_ok,
            "shape_returncode": int(shape_exec.get("returncode", -999)),
            "shape_stdout_tail": str(shape_exec.get("stdout_tail", ""))[-1000:],
            "shape_stderr_tail": str(shape_exec.get("stderr_tail", ""))[-1000:],
            "full_remote_plate_array_accessed": False
        },
        "compatibility_repair": patch_meta,
        "external_label_firewall": {
            "external_label_reveal_authorized": False,
            "date_or_external_environment_used": False
        },
        "sidecar": {
            "path": sidecar_name,
            "rows": int(len(audit)),
            "csv_sha256": sidecar_csv_sha,
            "gzip_sha256": sidecar_gz_sha
        }
    }
    receipt["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_sha(receipt)}
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(
        f"B3S_SHARD_DONE index={args.shard_index} rows={len(audit)} exact={exact_n} "
        f"shape_success={shape_ok} sidecar_csv_sha256={sidecar_csv_sha}", flush=True
    )


if __name__ == "__main__":
    main()
