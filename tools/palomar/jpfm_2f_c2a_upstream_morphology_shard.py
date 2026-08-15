#!/usr/bin/env python3
"""JPFM-2F-C2A shard: pinned upstream morphology + tile-local stellar normalization.

Each invocation handles a deterministic, non-overlapping subset of the frozen 360 tiles.
It emits only a shard execution receipt and source sidecar; global measurement/inference
outcomes are reserved for the aggregate runner.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import gzip
import hashlib
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jpfm_2f_b2_tile_lineage_replay as b2
import jpfm_2f_b3_shape_compat_replay as b3

EXPECTED_ROWS = 512
EXPECTED_TILES = 360
EXPECTED_PLATES = 234
SHARD_COUNT = 16
DETECTION_WORKERS = 10
SAMPLE_CSV_SHA = "a3656b181648e5abf933859199b5712e945b932610fffdd6c810785cff341b21"
SAMPLE_GZ_SHA = "3d4c7513b4add64324fddeedd04e9379b415f729fb36a76d977b871845638ca7"
SAMPLE_FREEZE_CANONICAL_SHA = "e4e5c8e13be97f4c54a12fc1cc217a5ed1fdcba763795aa47dc0d921b3d8d958"
REF_MIN = 20
REF_CLASS_STAR_MIN = 0.8
REF_SNR_MIN = 20.0


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def stable_text_sha(values) -> str:
    return sha256_bytes(("\n".join(str(v) for v in values) + "\n").encode("utf-8"))


def load_frozen_sample(path: Path) -> pd.DataFrame:
    gz = path.read_bytes()
    if sha256_bytes(gz) != SAMPLE_GZ_SHA:
        raise RuntimeError("C2A frozen sample gzip hash mismatch")
    raw = gzip.decompress(gz)
    if sha256_bytes(raw) != SAMPLE_CSV_SHA:
        raise RuntimeError("C2A frozen sample CSV hash mismatch")
    df = pd.read_csv(io.BytesIO(raw))
    df["src_id"] = df.src_id.astype(str)
    if len(df) != EXPECTED_ROWS or df.src_id.nunique() != EXPECTED_ROWS:
        raise RuntimeError("C2A frozen sample row/unique invariant failed")
    if df.tile_id.nunique() != EXPECTED_TILES or df.plate_id.nunique() != EXPECTED_PLATES:
        raise RuntimeError("C2A frozen sample topology invariant failed")
    return df


def numeric(s):
    return pd.to_numeric(s, errors="coerce")


def percentile_midrank(arr: np.ndarray, x: float) -> float:
    arr = arr[np.isfinite(arr)]
    if not len(arr) or not math.isfinite(x):
        return float("nan")
    return float((np.sum(arr < x) + 0.5 * np.sum(arr == x)) / len(arr))


def add_local_reference_normalization(audit: pd.DataFrame, tiles_root: Path) -> pd.DataFrame:
    out = audit.copy()
    newcols = [
        "local_reference_star_count",
        "local_FWHM_IMAGE_median", "local_FWHM_IMAGE_robust_sigma", "local_FWHM_IMAGE_z", "local_FWHM_IMAGE_percentile", "local_sharpness_z",
        "local_ELONGATION_median", "local_ELONGATION_robust_sigma", "local_ELONGATION_z", "local_ELONGATION_percentile",
        "local_SPREAD_MODEL_median", "local_SPREAD_MODEL_robust_sigma", "local_SPREAD_MODEL_z", "local_SPREAD_MODEL_percentile"
    ]
    for c in newcols:
        out[c] = np.nan

    for tid, idx in out.groupby("tile_id", sort=False).groups.items():
        cat = tiles_root / str(tid) / "catalogs" / "sextractor_pass2.csv"
        if not cat.exists() or cat.stat().st_size == 0:
            continue
        try:
            p = pd.read_csv(cat)
        except Exception:
            continue
        required = ["NUMBER", "FLAGS", "CLASS_STAR", "SNR_WIN", "FWHM_IMAGE", "ELONGATION", "SPREAD_MODEL"]
        if any(c not in p.columns for c in required):
            continue
        for c in required:
            p[c] = numeric(p[c])
        finite3 = np.isfinite(p[["FWHM_IMAGE", "ELONGATION", "SPREAD_MODEL"]].to_numpy(float)).all(axis=1)
        base_ref = (
            p["FLAGS"].eq(0)
            & (p["CLASS_STAR"] >= REF_CLASS_STAR_MIN)
            & (p["SNR_WIN"] >= REF_SNR_MIN)
            & finite3
        )
        for row_idx in list(idx):
            oid = numeric(pd.Series([out.at[row_idx, "object_id"]])).iloc[0]
            cand = p[p["NUMBER"].eq(oid)]
            if len(cand) != 1:
                continue
            ref = p[base_ref & ~p["NUMBER"].eq(oid)].copy()
            nref = int(len(ref))
            out.at[row_idx, "local_reference_star_count"] = nref
            if nref < REF_MIN:
                continue
            mapping = {
                "FWHM_IMAGE": "pass2_fwhm_image",
                "ELONGATION": "pass2_elongation",
                "SPREAD_MODEL": "pass2_spread_model"
            }
            for feat, cand_col in mapping.items():
                arr = ref[feat].to_numpy(float)
                med = float(np.median(arr))
                mad = float(np.median(np.abs(arr - med)))
                rsig = 1.4826 * mad
                x = float(out.at[row_idx, cand_col]) if pd.notna(out.at[row_idx, cand_col]) else float("nan")
                prefix = f"local_{feat}"
                out.at[row_idx, prefix + "_median"] = med
                out.at[row_idx, prefix + "_robust_sigma"] = rsig
                out.at[row_idx, prefix + "_percentile"] = percentile_midrank(arr, x)
                if math.isfinite(x) and math.isfinite(rsig) and rsig > 0:
                    out.at[row_idx, prefix + "_z"] = (x - med) / rsig
            z = out.at[row_idx, "local_FWHM_IMAGE_z"]
            if pd.notna(z):
                out.at[row_idx, "local_sharpness_z"] = -float(z)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True, type=Path)
    ap.add_argument("--upstream-root", required=True, type=Path)
    ap.add_argument("--work-dir", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--shard-index", required=True, type=int)
    ap.add_argument("--shard-count", default=SHARD_COUNT, type=int)
    args = ap.parse_args()
    if args.shard_count != SHARD_COUNT or not 0 <= args.shard_index < SHARD_COUNT:
        raise RuntimeError("C2A frozen shard contract violation")
    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[C2A shard {args.shard_index}] [1/9] bind exact frozen 512-source sample", flush=True)
    full = load_frozen_sample(args.sample)
    tile_ids = sorted(full.tile_id.astype(str).unique())
    assignment = {tid: i % SHARD_COUNT for i, tid in enumerate(tile_ids)}
    assigned_tiles = [tid for tid in tile_ids if assignment[tid] == args.shard_index]
    expected_n_tiles = 23 if args.shard_index < 8 else 22
    if len(assigned_tiles) != expected_n_tiles:
        raise RuntimeError(f"C2A shard {args.shard_index} tile count {len(assigned_tiles)} != {expected_n_tiles}")
    sample = full[full.tile_id.astype(str).isin(assigned_tiles)].copy()
    if sample.empty or sample.src_id.duplicated().any():
        raise RuntimeError("C2A invalid shard sample")
    print(f"[C2A shard {args.shard_index}] rows={len(sample)} tiles={len(assigned_tiles)} plates={sample.plate_id.nunique()}", flush=True)

    print(f"[C2A shard {args.shard_index}] [2/9] exact named-tile reconstruction", flush=True)
    tiles_root = args.work_dir / "tiles"
    tile_replay = b2.reconstruct_tiles(sample, args.upstream_root, tiles_root)
    good_tiles = set(tile_replay.loc[tile_replay.tile_identity == "RECONSTRUCTED", "tile_id"].astype(str))

    print(f"[C2A shard {args.shard_index}] [3/9] pinned pass1 -> PSFEx -> pass2", flush=True)
    unique_replay = tile_replay.drop_duplicates("tile_id").to_dict("records")
    det = []
    with cf.ThreadPoolExecutor(max_workers=DETECTION_WORKERS) as ex:
        futs = [ex.submit(b2.run_detection_one, r, args.upstream_root, tiles_root) for r in unique_replay]
        for i, fut in enumerate(cf.as_completed(futs), 1):
            det.append(fut.result())
            if i % 5 == 0 or i == len(futs):
                print(f"[C2A shard {args.shard_index}] detection {i}/{len(futs)}", flush=True)
    det_df = pd.DataFrame(det)
    det_map = {str(r.tile_id): str(r.detection_status) for r in det_df.itertuples(index=False)} if len(det_df) else {}

    print(f"[C2A shard {args.shard_index}] [4/9] exact NUMBER/object lineage", flush=True)
    audit = b2.audit_sample_against_pass2(sample, tiles_root)
    audit["tile_identity_reconstructed"] = audit.tile_id.astype(str).isin(good_tiles)
    audit["tile_detection_status"] = audit.tile_id.astype(str).map(det_map).fillna("MISSING_DETECTION_RECEIPT")

    print(f"[C2A shard {args.shard_index}] [5/9] tile-local high-confidence-star normalization", flush=True)
    audit = add_local_reference_normalization(audit, tiles_root)

    print(f"[C2A shard {args.shard_index}] [6/9] apply frozen B3S shape compatibility adapter", flush=True)
    patch_meta = b3.patch_shape_compat(args.upstream_root)

    print(f"[C2A shard {args.shard_index}] [7/9] compatibility-fixed upstream shape/profile stage", flush=True)
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

    print(f"[C2A shard {args.shard_index}] [8/9] freeze non-global source sidecar", flush=True)
    audit["c2a_shard_index"] = int(args.shard_index)
    audit["c2a_shard_count"] = SHARD_COUNT
    audit = audit.sort_values(["structural_cluster", "sample_role", "src_id"], kind="stable").reset_index(drop=True)
    csv_bytes = audit.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    csv_sha = sha256_bytes(csv_bytes)
    sidecar_name = f"JANUS-PALOMAR-JPFM-2F-C2A-SHARD-{args.shard_index:02d}-SIDECAR-RUN-001.csv.gz"
    receipt_name = f"JANUS-PALOMAR-JPFM-2F-C2A-SHARD-{args.shard_index:02d}-RECEIPT-RUN-001.json"
    sp = args.out_dir / sidecar_name
    rp = args.out_dir / receipt_name
    with sp.open("wb") as fout:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fout, mtime=0) as z:
            z.write(csv_bytes)
    gz_sha = sha256_bytes(sp.read_bytes())

    exact = audit.exact_object_status.astype(str).eq("EXACT_NUMBER_RECOVERED")
    exact_n = int(exact.sum())
    raw_cols = ["pass2_fwhm_image", "pass2_elongation", "pass2_spread_model"]
    raw = audit.loc[exact, raw_cols].apply(pd.to_numeric, errors="coerce").to_numpy(float) if exact_n else np.empty((0, 3))
    raw_finite = int(np.isfinite(raw).all(axis=1).sum()) if exact_n else 0
    norm_cols = ["local_FWHM_IMAGE_z", "local_ELONGATION_z", "local_SPREAD_MODEL_z"]
    norm = audit.loc[exact, norm_cols].apply(pd.to_numeric, errors="coerce").to_numpy(float) if exact_n else np.empty((0, 3))
    norm_finite = int(np.isfinite(norm).all(axis=1).sum()) if exact_n else 0
    shape_failed = pd.to_numeric(audit.get("shape_failed"), errors="coerce").fillna(1).astype(int)
    shape_ok = int((exact & shape_failed.eq(0)).sum())

    print(f"[C2A shard {args.shard_index}] [9/9] write execution receipt without global inference", flush=True)
    receipt = {
        "artifact_id": f"JANUS-PALOMAR-JPFM-2F-C2A-SHARD-{args.shard_index:02d}-RECEIPT-RUN-001",
        "experiment_id": "JPFM-2F-C2A",
        "schema_version": "1.0",
        "date": pd.Timestamp.utcnow().date().isoformat(),
        "status": "EXECUTED_SHARD_RECEIPT__NO_GLOBAL_OUTCOME_OR_INFERENCE",
        "claim_ceiling": "C2A_EXECUTION_SHARD_ONLY__GLOBAL_MORPHOLOGY_INFERENCE_FORBIDDEN_HERE__EXTERNAL_LABELS_SEALED",
        "bindings": {
            "admission_path": "data/JANUS-PALOMAR-JPFM-2F-C2A-STRATIFIED-UPSTREAM-MORPHOLOGY-REPLAY-ADMISSION-v1.0.json",
            "sample_freeze_canonical_sha256": SAMPLE_FREEZE_CANONICAL_SHA,
            "sample_csv_sha256": SAMPLE_CSV_SHA,
            "sample_gzip_sha256": SAMPLE_GZ_SHA,
            "poss_commit": b2.POSS_COMMIT
        },
        "shard": {
            "index": int(args.shard_index), "count": SHARD_COUNT,
            "assignment_rule": "lexicographically sorted frozen tile_id ordinal mod 16",
            "assigned_tiles": assigned_tiles,
            "assigned_tiles_sha256": stable_text_sha(assigned_tiles),
            "source_rows": int(len(audit)), "source_ids_unique": int(audit.src_id.astype(str).nunique()),
            "source_ids_sha256": stable_text_sha(sorted(audit.src_id.astype(str))),
            "distinct_tiles": int(len(assigned_tiles)), "distinct_plates": int(sample.plate_id.nunique())
        },
        "execution": {
            "tile_reconstructed": int(len(good_tiles)),
            "detection_tiles_pass": int((det_df.detection_status == "PASS").sum()) if len(det_df) else 0,
            "detection_status_census": {str(k): int(v) for k, v in det_df.detection_status.value_counts(dropna=False).items()} if len(det_df) else {},
            "exact_NUMBER_recovered": exact_n,
            "raw_upstream_morphology_finite": raw_finite,
            "local_normalized_primary_features_finite": norm_finite,
            "shape_success_exact": shape_ok,
            "shape_returncode": int(shape_exec.get("returncode", -999)),
            "full_remote_plate_array_accessed": False
        },
        "local_reference_contract": {
            "FLAGS": 0,
            "CLASS_STAR_min": REF_CLASS_STAR_MIN,
            "SNR_WIN_min": REF_SNR_MIN,
            "minimum_reference_stars": REF_MIN,
            "target_NUMBER_excluded": True
        },
        "compatibility_repair": patch_meta,
        "external_label_firewall": {"external_label_reveal_authorized": False, "date_or_external_environment_used": False},
        "sidecar": {"path": sidecar_name, "rows": int(len(audit)), "csv_sha256": csv_sha, "gzip_sha256": gz_sha}
    }
    receipt["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_sha(receipt)}
    rp.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"C2A_SHARD_DONE index={args.shard_index} rows={len(audit)} exact={exact_n} raw_finite={raw_finite} norm_finite={norm_finite} shape_ok={shape_ok}", flush=True)


if __name__ == "__main__":
    main()
