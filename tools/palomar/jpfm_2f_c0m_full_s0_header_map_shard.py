#!/usr/bin/env python3
"""JPFM-2F-C0M shard: header-only acquisition coordinates for a deterministic plate subset.

Each shard emits a non-global execution receipt and a gzip CSV sidecar. It never reads
remote plate image pixels and never evaluates the global C0M scientific/engineering outcome.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
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

GRID = 7
SIZE_ARCMIN = 60.0
SHARD_COUNT = 16
FSSPEC_BLOCK_SIZE = 64 * 1024


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def stable_sha(values) -> str:
    return sha256_bytes(("\n".join(str(v) for v in values) + "\n").encode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--upstream-root", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--shard-index", required=True, type=int)
    ap.add_argument("--shard-count", default=SHARD_COUNT, type=int)
    args = ap.parse_args()
    if args.shard_count != SHARD_COUNT or not 0 <= args.shard_index < SHARD_COUNT:
        raise RuntimeError("C0M frozen shard contract violation")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[C0M shard {args.shard_index}] [1/6] bind frozen public + structural cohorts", flush=True)
    structural, s0 = b2.load_inputs(args.manifest)
    keep_struct = ["src_id", "structural_cluster", "anomaly_score"]
    for c in keep_struct:
        if c not in structural.columns:
            raise RuntimeError(f"structural manifest missing {c}")
    structural_small = structural[keep_struct].copy()
    structural_small["src_id"] = structural_small.src_id.astype(str)
    s0["src_id"] = s0.src_id.astype(str)
    cohort = s0.merge(structural_small, on="src_id", how="left", validate="one_to_one")
    if len(cohort) != 122820 or cohort.src_id.nunique() != 122820:
        raise RuntimeError("C0M source binding row/uniqueness failure")
    if cohort[["structural_cluster", "anomaly_score", "plate_id"]].isna().any().any():
        raise RuntimeError("C0M structural/plate join incomplete")

    all_plates = sorted(cohort.plate_id.astype(str).unique())
    assignment = {p: i % SHARD_COUNT for i, p in enumerate(all_plates)}
    assigned_plates = [p for p in all_plates if assignment[p] == args.shard_index]
    shard = cohort[cohort.plate_id.astype(str).isin(assigned_plates)].copy()
    expected_tiles = sorted(shard.tile_id.astype(str).unique())
    if shard.empty or shard.src_id.duplicated().any():
        raise RuntimeError("C0M invalid shard cohort")
    print(
        f"[C0M shard {args.shard_index}] rows={len(shard)} plates={len(assigned_plates)} "
        f"active_tiles={len(expected_tiles)}", flush=True
    )

    print(f"[C0M shard {args.shard_index}] [2/6] load frozen CRPIX table", flush=True)
    sys.path.insert(0, str(args.upstream_root))
    from vasco.utils.tile_id import format_tile_id
    crpix = pd.read_csv(args.upstream_root / "data" / "plate_crpix_table.csv").rename(columns={"plate": "plate_id"})
    c_lookup = {str(r.plate_id): r for r in crpix.itertuples(index=False)}

    print(f"[C0M shard {args.shard_index}] [3/6] named-plate header-only tile models", flush=True)
    tile_models = {}
    plate_failures = []
    required_by_plate = {str(p): set(g.tile_id.astype(str)) for p, g in shard.groupby("plate_id")}
    for pi, plate in enumerate(assigned_plates, 1):
        targets = required_by_plate.get(plate, set())
        if not targets:
            plate_failures.append({"plate_id": plate, "reason": "ASSIGNED_PLATE_WITHOUT_SHARD_SOURCES"})
            continue
        crow = c_lookup.get(plate)
        if crow is None or str(crow.status) != "ok":
            plate_failures.append({"plate_id": plate, "reason": "MISSING_OR_NONOK_CRPIX"})
            continue
        dx, dy = float(crow.delta_x_px), float(crow.delta_y_px)
        try:
            with fits.open(
                b2.IRSA_FMT.format(plate=plate),
                use_fsspec=True,
                lazy_load_hdus=True,
                fsspec_kwargs={"block_size": FSSPEC_BLOCK_SIZE, "cache_type": "readahead"}
            ) as hdul:
                ph = hdul[0].header.copy()
                pw = WCS(ph)
                ny, nx = int(ph["NAXIS2"]), int(ph["NAXIS1"])
                raw_scale = float(ph["XPIXELSZ"]) / 1000.0 * float(ph["PLTSCALE"])
                tile_px = SIZE_ARCMIN * 60.0 / raw_scale
                tw = th = int(round(tile_px))

                def centres(span: int):
                    lo, hi = tile_px / 2.0, span - tile_px / 2.0
                    return np.linspace(lo, hi, GRID) if hi > lo else np.full(GRID, span / 2.0)

                grid = {}
                for py in centres(ny):
                    for px in centres(nx):
                        ra0, dec0 = [float(v) for v in pw.pixel_to_world_values(px, py)]
                        tid = format_tile_id(ra0 % 360.0, dec0)
                        sl_large, _ = overlap_slices((ny, nx), (th, tw), (float(py), float(px)), mode="trim")
                        if tid in grid:
                            raise RuntimeError(f"duplicate regenerated tile_id {tid} on {plate}")
                        grid[tid] = (sl_large[0], sl_large[1])
                missing = sorted(targets - set(grid))
                if missing:
                    plate_failures.append({"plate_id": plate, "reason": "ACTIVE_TILE_IDENTITY_MISSING", "count": len(missing), "sample": missing[:5]})
                    continue

                for tid in sorted(targets):
                    sl_y, sl_x = grid[tid]
                    hdr, rmed, rmax = b2.clean_tan_header_from_full(pw, ph, sl_y, sl_x, dx, dy)
                    w = WCS(hdr).celestial
                    scales = np.asarray(proj_plane_pixel_scales(w), dtype=float) * 3600.0
                    pixscale = float(np.sqrt(abs(scales[0] * scales[1])))
                    tile_models[tid] = {
                        "wcs": w,
                        "plate_id": plate,
                        "x_start": int(sl_x.start),
                        "y_start": int(sl_y.start),
                        "width": int(sl_x.stop - sl_x.start),
                        "height": int(sl_y.stop - sl_y.start),
                        "pixel_scale": pixscale,
                        "tan_refit_median_arcsec": rmed,
                        "tan_refit_max_arcsec": rmax,
                        "crpix_dx": dx,
                        "crpix_dy": dy
                    }
        except Exception as exc:
            plate_failures.append({"plate_id": plate, "reason": f"HEADER_WCS_ERROR:{type(exc).__name__}:{str(exc)[:120]}"})
        if pi % 8 == 0 or pi == len(assigned_plates):
            print(f"[C0M shard {args.shard_index}] headers {pi}/{len(assigned_plates)}", flush=True)

    print(f"[C0M shard {args.shard_index}] [4/6] predict all shard source pixels", flush=True)
    rows = []
    for r in shard.itertuples(index=False):
        tid = str(r.tile_id)
        m = tile_models.get(tid)
        base = {
            "src_id": str(r.src_id), "tile_id": tid, "object_id": int(r.object_id),
            "plate_id": str(r.plate_id), "ra": float(r.ra), "dec": float(r.dec),
            "structural_cluster": int(r.structural_cluster), "anomaly_score": float(r.anomaly_score)
        }
        if m is None:
            base["map_status"] = "TILE_MODEL_MISSING"
            rows.append(base)
            continue
        try:
            tx, ty = m["wcs"].world_to_pixel_values(float(r.ra), float(r.dec))
            tx, ty = float(tx), float(ty)
        except Exception as exc:
            base["map_status"] = f"WCS_TRANSFORM_ERROR:{type(exc).__name__}"
            rows.append(base)
            continue
        fx, fy = tx + m["x_start"], ty + m["y_start"]
        edge = min(tx, ty, (m["width"] - 1.0) - tx, (m["height"] - 1.0) - ty)
        base.update({
            "tile_x0": tx, "tile_y0": ty,
            "fullplate_x0": fx, "fullplate_y0": fy,
            "local_pixel_scale_arcsec": m["pixel_scale"],
            "tile_section_x_start_fullplate": m["x_start"],
            "tile_section_y_start_fullplate": m["y_start"],
            "tile_width_px": m["width"], "tile_height_px": m["height"],
            "distance_to_tile_edge_px": edge,
            "tan_refit_median_arcsec": m["tan_refit_median_arcsec"],
            "tan_refit_max_arcsec": m["tan_refit_max_arcsec"],
            "crpix_dx": m["crpix_dx"], "crpix_dy": m["crpix_dy"],
            "map_status": "HEADER_ONLY_MAPPED"
        })
        rows.append(base)
    out = pd.DataFrame(rows)
    out = out.sort_values("src_id", kind="stable").reset_index(drop=True)

    print(f"[C0M shard {args.shard_index}] [5/6] freeze shard sidecar", flush=True)
    csv_bytes = out.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    csv_sha = sha256_bytes(csv_bytes)
    sidecar_name = f"JANUS-PALOMAR-JPFM-2F-C0M-SHARD-{args.shard_index:02d}-SIDECAR-RUN-001.csv.gz"
    receipt_name = f"JANUS-PALOMAR-JPFM-2F-C0M-SHARD-{args.shard_index:02d}-RECEIPT-RUN-001.json"
    sp = args.out_dir / sidecar_name
    rp = args.out_dir / receipt_name
    with sp.open("wb") as fout:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fout, mtime=0) as z:
            z.write(csv_bytes)
    gz_sha = sha256_bytes(sp.read_bytes())

    mapped = out.map_status.eq("HEADER_ONLY_MAPPED") if "map_status" in out else pd.Series(False, index=out.index)
    finite_cols = ["tile_x0", "tile_y0", "fullplate_x0", "fullplate_y0", "local_pixel_scale_arcsec"]
    finite = out.loc[mapped, finite_cols].apply(pd.to_numeric, errors="coerce").to_numpy(float) if mapped.any() else np.empty((0, len(finite_cols)))
    finite_rows = int(np.isfinite(finite).all(axis=1).sum()) if len(finite) else 0
    edge = pd.to_numeric(out.loc[mapped, "distance_to_tile_edge_px"], errors="coerce") if mapped.any() else pd.Series(dtype=float)
    in_bounds = int((edge >= 0).sum()) if len(edge) else 0

    print(f"[C0M shard {args.shard_index}] [6/6] write non-global receipt", flush=True)
    receipt = {
        "artifact_id": f"JANUS-PALOMAR-JPFM-2F-C0M-SHARD-{args.shard_index:02d}-RECEIPT-RUN-001",
        "experiment_id": "JPFM-2F-C0M",
        "schema_version": "1.0",
        "date": pd.Timestamp.utcnow().date().isoformat(),
        "status": "EXECUTED_SHARD_RECEIPT__NO_GLOBAL_OUTCOME",
        "claim_ceiling": "HEADER_ONLY_ACQUISITION_MAPPING_SHARD_ONLY__NO_GLOBAL_OUTCOME__NO_PIXELS_READ__EXTERNAL_LABELS_SEALED",
        "shard": {
            "index": int(args.shard_index), "count": SHARD_COUNT,
            "assignment_rule": "lexicographically sorted frozen S0 plate_id ordinal mod 16",
            "assigned_plates": assigned_plates,
            "assigned_plates_sha256": stable_sha(assigned_plates),
            "source_rows": int(len(out)), "source_ids_unique": int(out.src_id.nunique()),
            "active_tiles_expected": int(len(expected_tiles)), "active_tile_models_built": int(len(tile_models))
        },
        "execution": {
            "plate_failures": plate_failures,
            "plate_failure_count": int(len(plate_failures)),
            "mapped_rows": int(mapped.sum()),
            "finite_prediction_rows": finite_rows,
            "in_tile_bounds_rows": in_bounds,
            "min_distance_to_tile_edge_px": float(edge.min()) if len(edge) else None,
            "remote_image_section_accessed": False,
            "remote_image_array_materialized": False
        },
        "bindings": {
            "poss_commit": b2.POSS_COMMIT,
            "stage_S0_csv_sha256": b2.S0_CSV_SHA256,
            "tile_manifest_csv_sha256": b2.TILES_CSV_SHA256,
            "structural_manifest_csv_sha256": b2.MANIFEST_CSV_SHA256
        },
        "external_label_firewall": {"external_label_reveal_authorized": False, "date_or_external_environment_used": False},
        "sidecar": {"path": sidecar_name, "rows": int(len(out)), "csv_sha256": csv_sha, "gzip_sha256": gz_sha}
    }
    receipt["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_sha(receipt)}
    rp.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"C0M_SHARD_DONE index={args.shard_index} rows={len(out)} mapped={int(mapped.sum())} "
        f"finite={finite_rows} in_bounds={in_bounds} csv_sha256={csv_sha}", flush=True
    )


if __name__ == "__main__":
    main()
