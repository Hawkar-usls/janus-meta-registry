#!/usr/bin/env python3
"""JPFM-2F-C0: validate direct S0 -> corrected tile WCS pixel localization.

Execution is explicitly conditional on an admitted B3S parent. No source search,
peak recentering, morphology thresholding, or external temporal labels are used.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from astropy.io import fits
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jpfm_2f_b2_tile_lineage_replay as b2

EXPECTED_N = 64
EXPECTED_TILES = 52
PRIMARY_PX = 3.0
TAIL_PX = 8.0
PRIMARY_FRAC = 0.95


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def quantiles(vals) -> dict:
    a = pd.to_numeric(pd.Series(vals), errors="coerce").to_numpy(float)
    a = a[np.isfinite(a)]
    if not len(a):
        return {"n_finite": 0}
    return {
        "n_finite": int(len(a)),
        "min": float(np.min(a)),
        "p05": float(np.quantile(a, 0.05)),
        "median": float(np.median(a)),
        "p95": float(np.quantile(a, 0.95)),
        "max": float(np.max(a))
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--parent-result", required=True, type=Path)
    ap.add_argument("--parent-sidecar", required=True, type=Path)
    ap.add_argument("--upstream-root", required=True, type=Path)
    ap.add_argument("--work-dir", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-sidecar-gz", required=True, type=Path)
    args = ap.parse_args()
    args.work_dir.mkdir(parents=True, exist_ok=True)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)

    print("[C0 1/7] parent admission gate", flush=True)
    parent = json.loads(args.parent_result.read_text(encoding="utf-8"))
    required_parent = "PASS_SHAPE_COMPATIBILITY_REPLAY__PIXEL_MORPHOLOGY_PILOT_ADMITTED"
    if parent.get("outcome") != required_parent:
        raise RuntimeError(f"C0 blocked: parent outcome {parent.get('outcome')!r} != required PASS")
    if parent.get("external_label_firewall", {}).get("external_label_reveal_authorized") is not False:
        raise RuntimeError("C0 blocked: parent external-label firewall not sealed")
    parent_result_sha = sha256_bytes(args.parent_result.read_bytes())

    pgz = args.parent_sidecar.read_bytes()
    if sha256_bytes(pgz) != parent["sidecar"]["gzip_sha256"]:
        raise RuntimeError("parent sidecar gzip hash mismatch")
    praw = gzip.decompress(pgz)
    if sha256_bytes(praw) != parent["sidecar"]["csv_sha256"]:
        raise RuntimeError("parent sidecar CSV hash mismatch")
    truth = pd.read_csv(io.BytesIO(praw))
    truth["src_id"] = truth.src_id.astype(str)
    if len(truth) != EXPECTED_N or truth.src_id.nunique() != EXPECTED_N:
        raise RuntimeError("parent truth sidecar is not exact 64-source set")

    print("[C0 2/7] reconstruct frozen same-64 S0 sample", flush=True)
    manifest, s0 = b2.load_inputs(args.manifest)
    sample = b2.select_same_64(manifest)
    sample = sample.merge(
        s0[["src_id", "tile_id", "object_id", "ra", "dec", "plate_id"]],
        on="src_id", validate="one_to_one"
    )
    sample["src_id"] = sample.src_id.astype(str)
    if len(sample) != EXPECTED_N or sample.tile_id.nunique() != EXPECTED_TILES:
        raise RuntimeError("C0 frozen sample invariants failed")
    if set(sample.src_id) != set(truth.src_id):
        raise RuntimeError("C0 parent truth src_id union differs from frozen same64")

    truth_cols = ["src_id", "exact_object_status", "pass2_xwin_image", "pass2_ywin_image"]
    missing = [c for c in truth_cols if c not in truth.columns]
    if missing:
        raise RuntimeError(f"C0 missing parent truth columns: {missing}")
    t = truth[truth_cols].copy()
    t["truth_x0"] = pd.to_numeric(t.pass2_xwin_image, errors="coerce") - 1.0
    t["truth_y0"] = pd.to_numeric(t.pass2_ywin_image, errors="coerce") - 1.0
    sample = sample.merge(t[["src_id", "exact_object_status", "truth_x0", "truth_y0"]], on="src_id", validate="one_to_one")
    truth_ok = (
        sample.exact_object_status.astype(str).eq("EXACT_NUMBER_RECOVERED")
        & np.isfinite(sample.truth_x0.to_numpy(float))
        & np.isfinite(sample.truth_y0.to_numpy(float))
    )
    truth_lineage_pass = bool(truth_ok.all())

    print("[C0 3/7] reconstruct exact corrected tiles only", flush=True)
    tiles_root = args.work_dir / "tiles"
    tile_replay = b2.reconstruct_tiles(sample, args.upstream_root, tiles_root)
    good_tiles = set(tile_replay.loc[tile_replay.tile_identity == "RECONSTRUCTED", "tile_id"].astype(str))
    tile_reconstruction_pass = len(good_tiles) == EXPECTED_TILES and sample.tile_id.astype(str).isin(good_tiles).all()

    print("[C0 4/7] direct frozen S0 sky -> corrected tile WCS pixels", flush=True)
    wcs_cache = {}
    rows = []
    for r in sample.itertuples(index=False):
        rec = {
            "src_id": str(r.src_id),
            "tile_id": str(r.tile_id),
            "object_id": int(r.object_id),
            "plate_id": str(r.plate_id),
            "structural_cluster": int(r.structural_cluster),
            "sample_role": str(r.sample_role),
            "s0_ra": float(r.ra),
            "s0_dec": float(r.dec),
            "truth_x0": float(r.truth_x0) if math.isfinite(float(r.truth_x0)) else float("nan"),
            "truth_y0": float(r.truth_y0) if math.isfinite(float(r.truth_y0)) else float("nan"),
            "exact_object_status": str(r.exact_object_status)
        }
        tid = str(r.tile_id)
        fits_files = sorted((tiles_root / tid / "raw").glob("*.fits"))
        if len(fits_files) != 1:
            rec["locator_status"] = "TILE_FITS_MISSING_OR_AMBIGUOUS"
            rows.append(rec)
            continue
        if tid not in wcs_cache:
            with fits.open(fits_files[0], memmap=False) as hdul:
                w = WCS(hdul[0].header).celestial
            scales = np.asarray(proj_plane_pixel_scales(w), dtype=float) * 3600.0
            local_scale = float(np.sqrt(abs(scales[0] * scales[1]))) if len(scales) >= 2 else float("nan")
            wcs_cache[tid] = (w, local_scale)
        w, local_scale = wcs_cache[tid]
        try:
            px, py = w.world_to_pixel_values(float(r.ra), float(r.dec))
            px, py = float(px), float(py)
        except Exception as exc:
            rec["locator_status"] = f"WCS_TRANSFORM_ERROR:{type(exc).__name__}"
            rows.append(rec)
            continue
        rec["pred_x0"] = px
        rec["pred_y0"] = py
        rec["local_pixel_scale_arcsec"] = local_scale
        if not (math.isfinite(px) and math.isfinite(py)):
            rec["locator_status"] = "NONFINITE_PREDICTION"
            rows.append(rec)
            continue
        if not (math.isfinite(rec["truth_x0"]) and math.isfinite(rec["truth_y0"])):
            rec["locator_status"] = "NONFINITE_TRUTH"
            rows.append(rec)
            continue
        dx = px - rec["truth_x0"]
        dy = py - rec["truth_y0"]
        off = math.hypot(dx, dy)
        rec["dx_px"] = dx
        rec["dy_px"] = dy
        rec["offset_px"] = off
        rec["offset_arcsec_proxy"] = off * local_scale if math.isfinite(local_scale) else float("nan")
        rec["locator_status"] = "DIRECT_WCS_PREDICTION"
        rows.append(rec)

    audit = pd.DataFrame(rows)
    locator_ok = audit.locator_status.eq("DIRECT_WCS_PREDICTION")
    coverage_pass = int(locator_ok.sum()) == EXPECTED_N

    print("[C0 5/7] evaluate preregistered locator gates", flush=True)
    offsets = pd.to_numeric(audit.loc[locator_ok, "offset_px"], errors="coerce").to_numpy(float)
    offsets = offsets[np.isfinite(offsets)]
    primary_frac = float((offsets <= PRIMARY_PX).mean()) if len(offsets) else 0.0
    max_px = float(np.max(offsets)) if len(offsets) else float("inf")
    primary_pass = primary_frac >= PRIMARY_FRAC
    tail_pass = len(offsets) == EXPECTED_N and max_px <= TAIL_PX

    if not tile_reconstruction_pass:
        outcome = "FAIL_CLOSED_TILE_RECONSTRUCTION"
    elif not truth_lineage_pass:
        outcome = "FAIL_CLOSED_TRUTH_LINEAGE"
    elif not (coverage_pass and primary_pass and tail_pass):
        outcome = "FAIL_CLOSED_PIXEL_LOCATOR_ACCURACY"
    else:
        outcome = "PASS_CORRECTED_TILE_WCS_DIRECT_PIXEL_LOCATOR"

    print("[C0 6/7] freeze locator sidecar", flush=True)
    audit = audit.sort_values(["structural_cluster", "sample_role", "src_id"], kind="stable").reset_index(drop=True)
    sidecar_csv = audit.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    sidecar_csv_sha = sha256_bytes(sidecar_csv)
    with args.out_sidecar_gz.open("wb") as fout:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fout, mtime=0) as gz:
            gz.write(sidecar_csv)
    sidecar_gz_sha = sha256_bytes(args.out_sidecar_gz.read_bytes())

    print("[C0 7/7] write result", flush=True)
    per_cluster = []
    for c, g in audit.groupby("structural_cluster"):
        per_cluster.append({
            "cluster": int(c),
            "rows": int(len(g)),
            "offset_px": quantiles(g.offset_px if "offset_px" in g else pd.Series(dtype=float))
        })
    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-2F-C0-CORRECTED-TILE-WCS-LOCATOR-RUN-001",
        "experiment_id": "JPFM-2F-C0",
        "schema_version": "1.0",
        "date": pd.Timestamp.utcnow().date().isoformat(),
        "status": "EXECUTED",
        "outcome": outcome,
        "claim_ceiling": "PIXEL_LOCATOR_ENGINEERING_VALIDATION_ONLY__NO_EXTERNAL_LABEL_INFERENCE__NO_ORIGIN_OR_CAUSAL_CLAIM",
        "bindings": {
            "admission_path": "data/JANUS-PALOMAR-JPFM-2F-C0-CORRECTED-TILE-WCS-LOCATOR-ADMISSION-v1.0.json",
            "parent_result_path": str(args.parent_result),
            "parent_result_file_sha256": parent_result_sha,
            "parent_result_canonical_sha256": parent.get("integrity", {}).get("canonical_payload_sha256_without_integrity"),
            "parent_sidecar_csv_sha256": parent["sidecar"]["csv_sha256"],
            "parent_sidecar_gzip_sha256": parent["sidecar"]["gzip_sha256"],
            "poss_commit": b2.POSS_COMMIT,
            "structural_manifest_csv_sha256": b2.MANIFEST_CSV_SHA256,
            "structural_manifest_gzip_sha256": b2.MANIFEST_GZ_SHA256
        },
        "sample": {
            "rows": EXPECTED_N,
            "distinct_tiles": EXPECTED_TILES,
            "same_as_B1_B2_B3_B3S": True
        },
        "gates": {
            "tile_reconstruction": {
                "pass": bool(tile_reconstruction_pass),
                "reconstructed_distinct_tiles": int(len(good_tiles)),
                "required_distinct_tiles": EXPECTED_TILES
            },
            "truth_lineage": {
                "pass": bool(truth_lineage_pass),
                "exact_and_finite_rows": int(truth_ok.sum())
            },
            "locator_coverage": {
                "pass": bool(coverage_pass),
                "finite_direct_predictions": int(locator_ok.sum())
            },
            "primary_accuracy": {
                "threshold_px": PRIMARY_PX,
                "required_fraction": PRIMARY_FRAC,
                "observed_fraction": primary_frac,
                "pass": bool(primary_pass)
            },
            "catastrophic_tail": {
                "threshold_px": TAIL_PX,
                "observed_max_px": max_px if math.isfinite(max_px) else None,
                "pass": bool(tail_pass)
            }
        },
        "offsets": {
            "pixel": quantiles(audit.offset_px if "offset_px" in audit else pd.Series(dtype=float)),
            "arcsec_proxy": quantiles(audit.offset_arcsec_proxy if "offset_arcsec_proxy" in audit else pd.Series(dtype=float)),
            "per_structural_cluster": per_cluster
        },
        "locator_contract": {
            "nearest_source_search_used": False,
            "pixel_peak_recentering_used": False,
            "pass1_psfex_pass2_used_for_prediction": False,
            "truth_pass2_used_only_after_prediction_for_scoring": True,
            "full_remote_plate_array_accessed": False
        },
        "external_label_firewall": {
            "external_label_reveal_authorized": False,
            "date_or_external_environment_used": False
        },
        "sidecar": {
            "path": str(args.out_sidecar_gz),
            "rows": int(len(audit)),
            "csv_sha256": sidecar_csv_sha,
            "gzip_sha256": sidecar_gz_sha
        },
        "next_gate": (
            "JPFM_2F_C1_LABEL_BLIND_PIXEL_MORPHOLOGY_SIDECAR_SCALEOUT"
            if outcome == "PASS_CORRECTED_TILE_WCS_DIRECT_PIXEL_LOCATOR"
            else "DIRECT_LOCATOR_NOT_ADMITTED__RETAIN_EXACT_DETECTION_LINEAGE_FOR_SCALEOUT_DESIGN"
        )
    }
    result["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_sha(result)}
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("OUTCOME", outcome, flush=True)
    print("LOCATOR_PRIMARY_FRAC", primary_frac, "MAX_OFFSET_PX", max_px, flush=True)
    print("SIDECAR_CSV_SHA256", sidecar_csv_sha, flush=True)
    print("RESULT_CANONICAL_SHA256", result["integrity"]["canonical_payload_sha256_without_integrity"], flush=True)


if __name__ == "__main__":
    main()
