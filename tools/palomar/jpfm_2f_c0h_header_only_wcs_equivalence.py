#!/usr/bin/env python3
"""JPFM-2F-C0H: reproduce admitted C0 corrected tile-WCS predictions from headers only."""
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
from astropy.nddata.utils import overlap_slices
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jpfm_2f_b2_tile_lineage_replay as b2

EXPECTED_N = 64
EXPECTED_TILES = 52
GRID = 7
SIZE_ARCMIN = 60.0
FSSPEC_BLOCK_SIZE = 64 * 1024
XY_TOL_PX = 1e-6
SCALE_TOL_ARCSEC = 1e-9


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def qstats(vals) -> dict:
    a = pd.to_numeric(pd.Series(vals), errors="coerce").to_numpy(float)
    a = a[np.isfinite(a)]
    if not len(a):
        return {"n_finite": 0}
    return {
        "n_finite": int(len(a)),
        "min": float(np.min(a)),
        "median": float(np.median(a)),
        "p95": float(np.quantile(a, 0.95)),
        "max": float(np.max(a))
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--c0-result", required=True, type=Path)
    ap.add_argument("--c0-sidecar", required=True, type=Path)
    ap.add_argument("--upstream-root", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-sidecar-gz", required=True, type=Path)
    args = ap.parse_args()
    args.out_json.parent.mkdir(parents=True, exist_ok=True)

    print("[C0H 1/6] bind admitted C0 parent", flush=True)
    c0 = json.loads(args.c0_result.read_text(encoding="utf-8"))
    if c0.get("outcome") != "PASS_CORRECTED_TILE_WCS_DIRECT_PIXEL_LOCATOR":
        raise RuntimeError("C0H parent is not admitted C0 PASS")
    if c0.get("external_label_firewall", {}).get("external_label_reveal_authorized") is not False:
        raise RuntimeError("C0H parent firewall not sealed")
    c0_result_sha = sha256_bytes(args.c0_result.read_bytes())
    gz = args.c0_sidecar.read_bytes()
    if sha256_bytes(gz) != c0["sidecar"]["gzip_sha256"]:
        raise RuntimeError("C0 sidecar gzip binding mismatch")
    raw = gzip.decompress(gz)
    if sha256_bytes(raw) != c0["sidecar"]["csv_sha256"]:
        raise RuntimeError("C0 sidecar CSV binding mismatch")
    truth = pd.read_csv(io.BytesIO(raw))
    truth["src_id"] = truth.src_id.astype(str)
    needed_truth = ["src_id", "pred_x0", "pred_y0", "local_pixel_scale_arcsec"]
    missing = [c for c in needed_truth if c not in truth.columns]
    if missing:
        raise RuntimeError(f"C0 sidecar missing truth columns: {missing}")
    if len(truth) != EXPECTED_N or truth.src_id.nunique() != EXPECTED_N:
        raise RuntimeError("C0 truth sidecar sample invariant failed")

    print("[C0H 2/6] reconstruct frozen same-64 source/plate identities", flush=True)
    manifest, s0 = b2.load_inputs(args.manifest)
    sample = b2.select_same_64(manifest)
    sample = sample.merge(
        s0[["src_id", "tile_id", "object_id", "ra", "dec", "plate_id"]],
        on="src_id", validate="one_to_one"
    )
    sample["src_id"] = sample.src_id.astype(str)
    if len(sample) != EXPECTED_N or sample.tile_id.nunique() != EXPECTED_TILES:
        raise RuntimeError("C0H same64 invariants failed")
    if set(sample.src_id) != set(truth.src_id):
        raise RuntimeError("C0H source union differs from C0")
    sample = sample.merge(truth[needed_truth], on="src_id", validate="one_to_one")

    print("[C0H 3/6] regenerate corrected tile WCS from named plate headers only", flush=True)
    sys.path.insert(0, str(args.upstream_root))
    from vasco.utils.tile_id import format_tile_id

    crpix = pd.read_csv(args.upstream_root / "data" / "plate_crpix_table.csv").rename(columns={"plate": "plate_id"})
    c_lookup = {str(r.plate_id): r for r in crpix.itertuples(index=False)}
    required = sample[["plate_id", "tile_id"]].drop_duplicates()
    expected_by_plate = {str(p): set(g.tile_id.astype(str)) for p, g in required.groupby("plate_id")}
    tile_models = {}
    header_access_ok = True

    for pi, plate in enumerate(sorted(expected_by_plate), 1):
        targets = expected_by_plate[plate]
        url = b2.IRSA_FMT.format(plate=plate)
        try:
            with fits.open(
                url,
                use_fsspec=True,
                lazy_load_hdus=True,
                fsspec_kwargs={"block_size": FSSPEC_BLOCK_SIZE, "cache_type": "readahead"}
            ) as hdul:
                hdu = hdul[0]
                ph = hdu.header.copy()
                pw = WCS(ph)
                ny = int(ph["NAXIS2"]); nx = int(ph["NAXIS1"])
                scale = float(ph["XPIXELSZ"]) / 1000.0 * float(ph["PLTSCALE"])
                tile_px = SIZE_ARCMIN * 60.0 / scale
                tw = th = int(round(tile_px))
                def centres(span: int):
                    lo, hi = tile_px / 2.0, span - tile_px / 2.0
                    return np.linspace(lo, hi, GRID) if hi > lo else np.full(GRID, span / 2.0)
                grid = {}
                for py in centres(ny):
                    for px in centres(nx):
                        ra, dec = [float(v) for v in pw.pixel_to_world_values(px, py)]
                        tid = format_tile_id(ra % 360.0, dec)
                        sl_large, _ = overlap_slices((ny, nx), (th, tw), (float(py), float(px)), mode="trim")
                        grid[tid] = (sl_large[0], sl_large[1])
                if targets - set(grid):
                    header_access_ok = False
                    continue
                crow = c_lookup.get(plate)
                if crow is None or str(crow.status) != "ok":
                    header_access_ok = False
                    continue
                dx, dy = float(crow.delta_x_px), float(crow.delta_y_px)
                for tid in sorted(targets):
                    sl_y, sl_x = grid[tid]
                    hdr, rmed, rmax = b2.clean_tan_header_from_full(pw, ph, sl_y, sl_x, dx, dy)
                    twcs = WCS(hdr).celestial
                    scales = np.asarray(proj_plane_pixel_scales(twcs), dtype=float) * 3600.0
                    pixscale = float(np.sqrt(abs(scales[0] * scales[1])))
                    tile_models[tid] = {
                        "wcs": twcs,
                        "pixel_scale_arcsec": pixscale,
                        "sl_x_start": int(sl_x.start),
                        "sl_y_start": int(sl_y.start),
                        "tan_refit_median_arcsec": rmed,
                        "tan_refit_max_arcsec": rmax,
                        "plate_id": plate
                    }
        except Exception:
            header_access_ok = False
        print(f"[C0H header] {pi}/{len(expected_by_plate)} {plate}", flush=True)

    tile_identity_pass = header_access_ok and len(tile_models) == EXPECTED_TILES and set(tile_models) == set(sample.tile_id.astype(str))

    print("[C0H 4/6] score header-only predictions against frozen C0 predictions", flush=True)
    rows = []
    for r in sample.itertuples(index=False):
        tid = str(r.tile_id)
        rec = {
            "src_id": str(r.src_id),
            "tile_id": tid,
            "plate_id": str(r.plate_id),
            "object_id": int(r.object_id),
            "structural_cluster": int(r.structural_cluster),
            "sample_role": str(r.sample_role),
            "s0_ra": float(r.ra),
            "s0_dec": float(r.dec),
            "c0_pred_x0": float(r.pred_x0),
            "c0_pred_y0": float(r.pred_y0),
            "c0_pixel_scale_arcsec": float(r.local_pixel_scale_arcsec)
        }
        model = tile_models.get(tid)
        if model is None:
            rec["status"] = "TILE_MODEL_MISSING"
            rows.append(rec)
            continue
        try:
            x, y = model["wcs"].world_to_pixel_values(float(r.ra), float(r.dec))
            x, y = float(x), float(y)
        except Exception as exc:
            rec["status"] = f"WCS_TRANSFORM_ERROR:{type(exc).__name__}"
            rows.append(rec)
            continue
        rec["header_pred_x0"] = x
        rec["header_pred_y0"] = y
        rec["header_pixel_scale_arcsec"] = float(model["pixel_scale_arcsec"])
        rec["tile_section_x_start_fullplate"] = int(model["sl_x_start"])
        rec["tile_section_y_start_fullplate"] = int(model["sl_y_start"])
        rec["fullplate_pred_x0"] = x + float(model["sl_x_start"])
        rec["fullplate_pred_y0"] = y + float(model["sl_y_start"])
        rec["xy_equivalence_error_px"] = math.hypot(x - float(r.pred_x0), y - float(r.pred_y0))
        rec["pixel_scale_error_arcsec"] = abs(float(model["pixel_scale_arcsec"]) - float(r.local_pixel_scale_arcsec))
        rec["status"] = "HEADER_ONLY_PREDICTION"
        rows.append(rec)

    audit = pd.DataFrame(rows)
    ok = audit.status.eq("HEADER_ONLY_PREDICTION")
    coverage_pass = int(ok.sum()) == EXPECTED_N
    xyerr = pd.to_numeric(audit.loc[ok, "xy_equivalence_error_px"], errors="coerce").to_numpy(float)
    serr = pd.to_numeric(audit.loc[ok, "pixel_scale_error_arcsec"], errors="coerce").to_numpy(float)
    equivalence_pass = len(xyerr) == EXPECTED_N and bool(np.isfinite(xyerr).all()) and float(np.max(xyerr)) <= XY_TOL_PX
    scale_pass = len(serr) == EXPECTED_N and bool(np.isfinite(serr).all()) and float(np.max(serr)) <= SCALE_TOL_ARCSEC

    if not tile_identity_pass:
        outcome = "FAIL_CLOSED_HEADER_OR_TILE_IDENTITY"
    elif not (coverage_pass and equivalence_pass and scale_pass):
        outcome = "FAIL_CLOSED_HEADER_ONLY_WCS_EQUIVALENCE"
    else:
        outcome = "PASS_HEADER_ONLY_TILE_WCS_EQUIVALENCE"

    print("[C0H 5/6] freeze equivalence sidecar", flush=True)
    audit = audit.sort_values(["structural_cluster", "sample_role", "src_id"], kind="stable").reset_index(drop=True)
    csv_bytes = audit.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    csv_sha = sha256_bytes(csv_bytes)
    with args.out_sidecar_gz.open("wb") as fout:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fout, mtime=0) as z:
            z.write(csv_bytes)
    gz_sha = sha256_bytes(args.out_sidecar_gz.read_bytes())

    print("[C0H 6/6] write result", flush=True)
    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-2F-C0H-HEADER-ONLY-TILE-WCS-EQUIVALENCE-RUN-001",
        "experiment_id": "JPFM-2F-C0H",
        "schema_version": "1.0",
        "date": pd.Timestamp.utcnow().date().isoformat(),
        "status": "EXECUTED",
        "outcome": outcome,
        "claim_ceiling": "HEADER_ONLY_WCS_ENGINEERING_EQUIVALENCE_ONLY__NO_MORPHOLOGY_OR_EXTERNAL_LABEL_INFERENCE",
        "bindings": {
            "admission_path": "data/JANUS-PALOMAR-JPFM-2F-C0H-HEADER-ONLY-TILE-WCS-EQUIVALENCE-ADMISSION-v1.0.json",
            "c0_result_path": str(args.c0_result),
            "c0_result_file_sha256": c0_result_sha,
            "c0_result_canonical_sha256": c0["integrity"]["canonical_payload_sha256_without_integrity"],
            "c0_sidecar_csv_sha256": c0["sidecar"]["csv_sha256"],
            "c0_sidecar_gzip_sha256": c0["sidecar"]["gzip_sha256"],
            "poss_commit": b2.POSS_COMMIT
        },
        "sample": {"rows": EXPECTED_N, "distinct_tiles": EXPECTED_TILES, "same_as_C0": True},
        "gates": {
            "plate_header_access_and_tile_identity": {"pass": bool(tile_identity_pass), "header_only_tile_models": int(len(tile_models))},
            "prediction_coverage": {"pass": bool(coverage_pass), "rows": int(ok.sum())},
            "xy_equivalence": {"pass": bool(equivalence_pass), "tolerance_px": XY_TOL_PX, "error_px": qstats(audit.get("xy_equivalence_error_px", pd.Series(dtype=float)))},
            "pixel_scale_equivalence": {"pass": bool(scale_pass), "tolerance_arcsec_per_px": SCALE_TOL_ARCSEC, "error_arcsec_per_px": qstats(audit.get("pixel_scale_error_arcsec", pd.Series(dtype=float)))}
        },
        "transport_contract": {
            "remote_named_plate_headers_opened": int(len(expected_by_plate)),
            "remote_image_section_accessed": False,
            "remote_image_array_materialized": False,
            "full_plate_prediction_coordinates_exported_for_next_stamp_gate": True
        },
        "external_label_firewall": {"external_label_reveal_authorized": False, "date_or_external_environment_used": False},
        "sidecar": {"path": str(args.out_sidecar_gz), "rows": int(len(audit)), "csv_sha256": csv_sha, "gzip_sha256": gz_sha},
        "next_gate": "JPFM_2F_C1_NAMED_PLATE_SPARSE_STAMP_TRANSPORT_AND_DIRECT_MORPHOLOGY" if outcome == "PASS_HEADER_ONLY_TILE_WCS_EQUIVALENCE" else "HEADER_ONLY_WCS_NOT_ADMITTED"
    }
    result["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_sha(result)}
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("OUTCOME", outcome, flush=True)
    print("MAX_XY_EQUIV_ERROR_PX", float(np.max(xyerr)) if len(xyerr) else None, flush=True)
    print("RESULT_CANONICAL_SHA256", result["integrity"]["canonical_payload_sha256_without_integrity"], flush=True)


if __name__ == "__main__":
    main()
