#!/usr/bin/env python3
"""JPFM-2F-B3: same frozen 64-source replay with one OpenCV shape-layout compatibility repair."""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Import B2 as the frozen transport/tile/detection/object-lineage implementation.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jpfm_2f_b2_tile_lineage_replay as b2

SAMPLE_N = 64
DETECTION_WORKERS = 10

OLD_DEFECT_LINE = "sum_depth = sum(defects[i, 0][3] / 256.0 for i in range(defects.shape[0]))"
NEW_DEFECT_BLOCK = """defect_arr = np.asarray(defects)\n                        if defect_arr.ndim < 1 or defect_arr.shape[-1] != 4:\n                            raise ValueError(f\"unexpected convexityDefects shape: {defect_arr.shape}\")\n                        defect_rows = defect_arr.reshape(-1, 4)\n                        sum_depth = sum(float(row[3]) / 256.0 for row in defect_rows)"""


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canonical_sha(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def patch_shape_compat(upstream_root: Path):
    p = upstream_root / "scripts" / "stage_shape_post.py"
    original = p.read_text(encoding="utf-8")
    if original.count(OLD_DEFECT_LINE) != 1:
        raise RuntimeError("frozen upstream shape source does not contain exactly one expected defect expression")
    repaired = original.replace(OLD_DEFECT_LINE, NEW_DEFECT_BLOCK, 1)
    p.write_text(repaired, encoding="utf-8")
    return {
        "path": str(p),
        "original_sha256": sha256_bytes(original.encode("utf-8")),
        "repaired_sha256": sha256_bytes(repaired.encode("utf-8")),
        "old_expression_occurrences": 1,
        "metric_formula_changed": False,
    }


def finite_fraction(df: pd.DataFrame, cols: list[str], mask: pd.Series) -> float:
    if int(mask.sum()) == 0:
        return 0.0
    x = df.loc[mask, cols].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    return float(np.isfinite(x).all(axis=1).mean())


def quantiles(series):
    a = pd.to_numeric(series, errors="coerce").to_numpy(float)
    a = a[np.isfinite(a)]
    if not len(a):
        return {"n_finite": 0}
    return {
        "n_finite": int(len(a)),
        "min": float(np.min(a)), "p05": float(np.quantile(a, .05)),
        "median": float(np.median(a)), "p95": float(np.quantile(a, .95)),
        "max": float(np.max(a)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--upstream-root", required=True, type=Path)
    ap.add_argument("--work-dir", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-sidecar-gz", required=True, type=Path)
    args = ap.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)

    print("[1/8] reconstruct exact same frozen 64-source sample", flush=True)
    manifest, s0 = b2.load_inputs(args.manifest)
    sample = b2.select_same_64(manifest)
    sample = sample.merge(s0[["src_id", "tile_id", "object_id", "ra", "dec", "plate_id"]], on="src_id", validate="one_to_one")
    if len(sample) != SAMPLE_N or sample.src_id.nunique() != SAMPLE_N:
        raise RuntimeError("B3 frozen sample reconstruction failed")

    print("[2/8] sparse replay exact named tiles", flush=True)
    tiles_root = args.work_dir / "tiles"
    tile_replay = b2.reconstruct_tiles(sample, args.upstream_root, tiles_root)
    req_tiles = int(sample.tile_id.nunique())
    good_tiles = set(tile_replay.loc[tile_replay.tile_identity == "RECONSTRUCTED", "tile_id"].astype(str))
    sample["tile_identity_reconstructed"] = sample.tile_id.astype(str).isin(good_tiles)
    tile_identity_rows = int(sample.tile_identity_reconstructed.sum())
    tile_identity_pass = tile_identity_rows == SAMPLE_N and len(good_tiles) == req_tiles

    print(f"[3/8] pass1 -> PSFEx -> pass2 with {DETECTION_WORKERS} independent tile workers", flush=True)
    unique_replay = tile_replay.drop_duplicates("tile_id").to_dict("records")
    det = []
    with cf.ThreadPoolExecutor(max_workers=DETECTION_WORKERS) as ex:
        futs = [ex.submit(b2.run_detection_one, r, args.upstream_root, tiles_root) for r in unique_replay]
        for i, fut in enumerate(cf.as_completed(futs), 1):
            det.append(fut.result())
            if i % 10 == 0 or i == len(futs):
                print(f"[detection] {i}/{len(futs)}", flush=True)
    det_df = pd.DataFrame(det)
    det_pass_tiles = int((det_df.detection_status == "PASS").sum()) if len(det_df) else 0
    detection_fraction = det_pass_tiles / req_tiles if req_tiles else 0.0
    detection_pass = detection_fraction >= 0.95

    print("[4/8] exact pass2 NUMBER/object lineage audit", flush=True)
    audit = b2.audit_sample_against_pass2(sample, tiles_root)
    exact = audit.exact_object_status.eq("EXACT_NUMBER_RECOVERED")
    exact_n = int(exact.sum()); exact_frac = exact_n / SAMPLE_N
    object_pass = exact_frac >= 0.90
    sep = pd.to_numeric(audit.get("pass2_to_s0_sep_arcsec"), errors="coerce")
    sep_exact = sep[exact & np.isfinite(sep)].to_numpy(float)
    sep_le10_frac = float((sep_exact <= 10.0).mean()) if len(sep_exact) else 0.0
    sep_pass = sep_le10_frac >= 0.90
    raw_morph_frac = finite_fraction(audit, ["pass2_fwhm_image", "pass2_elongation", "pass2_spread_model"], exact)
    raw_morph_pass = raw_morph_frac >= 0.95

    print("[5/8] apply only preregistered OpenCV defect-array compatibility adapter", flush=True)
    patch_meta = patch_shape_compat(args.upstream_root)

    print("[6/8] execute repaired upstream experimental shape stage", flush=True)
    shape, shape_exec = b2.run_upstream_shape(sample, args.upstream_root, args.work_dir, tiles_root)
    if len(shape):
        shape["src_id"] = shape.src_id.astype(str)
        keep_cols = [c for c in shape.columns if c in {
            "src_id", "profile_diff", "circularity", "area", "shape_defect", "circle_deviation",
            "shape_confidence", "elongation", "stars_used", "shape_failed", "failure_reason",
            "reject_flag", "reject_reason"
        }]
        audit = audit.merge(shape[keep_cols], on="src_id", how="left", validate="one_to_one")
    else:
        audit["shape_failed"] = 1
        audit["failure_reason"] = "SHAPE_STAGE_OUTPUT_MISSING"
    shape_failed = pd.to_numeric(audit.get("shape_failed"), errors="coerce").fillna(1).astype(int)
    shape_success_exact = exact & shape_failed.eq(0)
    shape_success_frac = float(shape_success_exact.sum() / exact_n) if exact_n else 0.0
    shape_pass = shape_success_frac >= 0.90

    print("[7/8] evaluate frozen B3 gates", flush=True)
    if not (tile_identity_pass and detection_pass):
        outcome = "FAIL_CLOSED_TILE_OR_DETECTION_REPLAY"
    elif not (object_pass and sep_pass):
        outcome = "FAIL_CLOSED_OBJECT_LINEAGE"
    elif not raw_morph_pass:
        outcome = "FAIL_CLOSED_RAW_MORPHOLOGY"
    elif not shape_pass:
        outcome = "FAIL_CLOSED_SHAPE_COMPATIBILITY_REPAIR"
    else:
        outcome = "PASS_SHAPE_COMPATIBILITY_REPLAY__PIXEL_MORPHOLOGY_PILOT_ADMITTED"

    print("[8/8] freeze B3 sidecar and result", flush=True)
    audit = audit.sort_values(["structural_cluster", "sample_role", "src_id"], kind="stable").reset_index(drop=True)
    sidecar_csv = audit.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    sidecar_csv_sha = sha256_bytes(sidecar_csv)
    with args.out_sidecar_gz.open("wb") as fout:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fout, mtime=0) as gz:
            gz.write(sidecar_csv)
    sidecar_gz_sha = sha256_bytes(args.out_sidecar_gz.read_bytes())

    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-2F-B3-SHAPE-COMPATIBILITY-REPLAY-RUN-001",
        "experiment_id": "JPFM-2F-B3", "schema_version": "1.0",
        "date": pd.Timestamp.utcnow().date().isoformat(), "status": "EXECUTED", "outcome": outcome,
        "claim_ceiling": "OPEN_CV_COMPATIBILITY_REPAIRED_PIXEL_MORPHOLOGY_PILOT_ONLY__EXTERNAL_LABELS_SEALED__NO_CAUSAL_OR_ORIGIN_CLAIM",
        "bindings": {
            "admission_path": "data/JANUS-PALOMAR-JPFM-2F-B3-SHAPE-COMPATIBILITY-REPLAY-ADMISSION-v1.0.json",
            "corrective_audit_path": "data/JANUS-PALOMAR-JPFM-2F-B2-SHAPE-COMPAT-CORRECTIVE-AUDIT-v1.0.json",
            "poss_commit": b2.POSS_COMMIT,
            "structural_manifest_csv_sha256": b2.MANIFEST_CSV_SHA256,
            "structural_manifest_gzip_sha256": b2.MANIFEST_GZ_SHA256,
        },
        "sample": {"rows": SAMPLE_N, "distinct_tiles": req_tiles, "distinct_plates": int(sample.plate_id.nunique()), "same_as_B1_B2": True},
        "operational": {"detection_workers": DETECTION_WORKERS, "scientific_tile_job_semantics_changed": False, "full_remote_plate_array_accessed": False},
        "compatibility_repair": patch_meta,
        "tile_and_detection": {
            "tile_identity_rows": tile_identity_rows, "tile_identity_pass": tile_identity_pass,
            "reconstructed_distinct_tiles": int(len(good_tiles)), "required_distinct_tiles": req_tiles,
            "detection_tiles_pass": det_pass_tiles, "detection_pass_fraction": detection_fraction,
            "detection_gate_pass": detection_pass,
            "detection_status_census": {str(k): int(v) for k, v in det_df.detection_status.value_counts(dropna=False).items()} if len(det_df) else {},
        },
        "object_lineage": {
            "exact_NUMBER_recovered": exact_n, "exact_NUMBER_fraction": exact_frac, "exact_NUMBER_gate_pass": object_pass,
            "pass2_to_S0_sep_le10_fraction": sep_le10_frac, "sky_consistency_gate_pass": sep_pass,
            "pass2_to_S0_sep_arcsec": quantiles(sep[exact]),
        },
        "raw_pass2_morphology": {
            "finite_FWHM_ELONGATION_SPREAD_fraction_among_exact": raw_morph_frac,
            "gate_pass": raw_morph_pass,
            "FWHM_IMAGE_px": quantiles(audit.loc[exact, "pass2_fwhm_image"]),
            "ELONGATION": quantiles(audit.loc[exact, "pass2_elongation"]),
            "SPREAD_MODEL": quantiles(audit.loc[exact, "pass2_spread_model"]),
            "SNR_WIN": quantiles(audit.loc[exact, "pass2_snr_win"]),
        },
        "repaired_shape_stage": {
            "returncode": int(shape_exec.get("returncode", -999)),
            "shape_success_exact": int(shape_success_exact.sum()),
            "shape_success_fraction_among_exact": shape_success_frac,
            "gate_pass": shape_pass,
            "failure_reason_census": {str(k): int(v) for k, v in audit.loc[exact & ~shape_success_exact, "failure_reason"].fillna("MISSING").value_counts().items()} if exact_n else {},
            "profile_diff": quantiles(audit.get("profile_diff", pd.Series(dtype=float))),
            "circularity": quantiles(audit.get("circularity", pd.Series(dtype=float))),
            "shape_defect": quantiles(audit.get("shape_defect", pd.Series(dtype=float))),
            "circle_deviation": quantiles(audit.get("circle_deviation", pd.Series(dtype=float))),
            "stars_used": quantiles(audit.get("stars_used", pd.Series(dtype=float))),
        },
        "external_label_firewall": {"external_label_reveal_authorized": False, "date_or_external_environment_used": False},
        "sidecar": {"path": str(args.out_sidecar_gz), "rows": int(len(audit)), "csv_sha256": sidecar_csv_sha, "gzip_sha256": sidecar_gz_sha},
        "next_gate": (
            "JPFM_2F_C_LABEL_BLIND_PIXEL_MORPHOLOGY_SIDECAR_SCALEOUT" if outcome == "PASS_SHAPE_COMPATIBILITY_REPLAY__PIXEL_MORPHOLOGY_PILOT_ADMITTED"
            else "REPAIR_REMAINING_MEASUREMENT_FAILURE_WITHOUT_EXTERNAL_LABEL_REVEAL"
        ),
    }
    result["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_sha(result)}
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("OUTCOME", outcome, flush=True)
    print("EXACT_NUMBER", exact_n, "RAW_MORPH_FRAC", raw_morph_frac, "SHAPE_SUCCESS", int(shape_success_exact.sum()), flush=True)
    print("SIDECAR_CSV_SHA256", sidecar_csv_sha, flush=True)
    print("RESULT_CANONICAL_SHA256", result["integrity"]["canonical_payload_sha256_without_integrity"], flush=True)


if __name__ == "__main__":
    main()
