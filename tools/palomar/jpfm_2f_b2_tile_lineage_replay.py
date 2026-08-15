#!/usr/bin/env python3
"""JPFM-2F-B2: replay exact public tile/object pixel lineage for the frozen 64-source sample."""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import gzip
import hashlib
import io
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.nddata.utils import overlap_slices
from astropy.wcs import WCS
from astropy.wcs.utils import fit_wcs_from_points
import astropy.units as u

POSS_COMMIT = "4005e200541b321ead3d6608f0162a14430ef1c2"
BASE = f"https://raw.githubusercontent.com/jannefi/poss1-plate-slice/{POSS_COMMIT}"
REL = "results/s0-642-20260814"
S0_URL = f"{BASE}/{REL}/stage_S0.csv.gz"
TILES_URL = f"{BASE}/{REL}/tile_manifest.csv.gz"
IRSA_FMT = "https://irsa.ipac.caltech.edu/data/DSS/images/dss1red/dss1red_{plate}.fits"

S0_GZ_SHA256 = "f19cf987756c62a68f55a472992d860e73ae63b3a4664189092b0e1fda77f7bb"
S0_CSV_SHA256 = "2ff92f2210acb387ef9ef4b88d561595d3883e9aab27065042627272b96590f0"
TILES_GZ_SHA256 = "a1652db2d15470a9e8630a1a2ac3a055e49be65880ca615126a9aaa8cc2da02d"
TILES_CSV_SHA256 = "5dcb90dc5d98550e5a60246aced2b097922a267c69e81f27d45d16a288142a99"
MANIFEST_CSV_SHA256 = "34b0ccde7c3683d07626774e52dac0a197451f729242204e59aae81397bdbc2e"
MANIFEST_GZ_SHA256 = "166f5e6621ed2b065b7981b3c8208670f3c989b1394bd559c9005ab1fa6d07d9"
B1_RESULT_CANONICAL_SHA256 = "6d6a5e88f2ddee01c79c6c28e2f40547edc4b3f020ef5b63bba32748d7c06f2e"

SAMPLE_N = 64
GRID = 7
SIZE_ARCMIN = 60.0
FSSPEC_BLOCK_SIZE = 1024 * 1024
DETECTION_WORKERS = 4

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "JANUS-JPFM-2F-B2-tile-lineage-replay/1.0"})


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def require_hash(label: str, b: bytes, expected: str) -> None:
    got = sha256_bytes(b)
    if got != expected:
        raise RuntimeError(f"{label} sha256 mismatch: {got} != {expected}")


def get_bytes(url: str) -> bytes:
    r = SESSION.get(url, timeout=120)
    r.raise_for_status()
    return r.content


def load_inputs(manifest_path: Path):
    mgz = manifest_path.read_bytes()
    require_hash("blind manifest gzip", mgz, MANIFEST_GZ_SHA256)
    mcsv = gzip.decompress(mgz)
    require_hash("blind manifest csv", mcsv, MANIFEST_CSV_SHA256)
    manifest = pd.read_csv(io.BytesIO(mcsv))
    if len(manifest) != 122820 or manifest.src_id.duplicated().any():
        raise RuntimeError("blind manifest invariant failed")

    s0_gz, tile_gz = get_bytes(S0_URL), get_bytes(TILES_URL)
    require_hash("S0 gzip", s0_gz, S0_GZ_SHA256)
    require_hash("tile manifest gzip", tile_gz, TILES_GZ_SHA256)
    s0_csv, tile_csv = gzip.decompress(s0_gz), gzip.decompress(tile_gz)
    require_hash("S0 csv", s0_csv, S0_CSV_SHA256)
    require_hash("tile manifest csv", tile_csv, TILES_CSV_SHA256)
    s0 = pd.read_csv(io.BytesIO(s0_csv))
    tiles = pd.read_csv(io.BytesIO(tile_csv))
    if len(s0) != 122820 or len(tiles) != 31458:
        raise RuntimeError("public release invariant failed")
    tile_map = tiles[["tile_id", "plate_id"]].drop_duplicates()
    if tile_map.tile_id.duplicated().any():
        raise RuntimeError("tile_id maps to multiple plates")
    s0 = s0.merge(tile_map, on="tile_id", how="left", validate="many_to_one")
    if s0.plate_id.isna().any():
        raise RuntimeError("S0 tile->plate join incomplete")
    return manifest, s0


def select_same_64(manifest: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in range(16):
        g = manifest[manifest.structural_cluster.astype(int) == c].copy()
        g["src_id"] = g.src_id.astype(str)
        med = float(g.anomaly_score.median())
        g["median_distance"] = (g.anomaly_score.astype(float) - med).abs()
        typical = g.sort_values(["median_distance", "src_id"], kind="stable").head(2)
        used = set(typical.src_id)
        unusual = g[~g.src_id.isin(used)].sort_values(
            ["anomaly_score", "src_id"], ascending=[False, True], kind="stable"
        ).head(2)
        t = typical.copy(); t["sample_role"] = "typical"
        q = unusual.copy(); q["sample_role"] = "unusual"
        rows.extend([t, q])
    out = pd.concat(rows, ignore_index=True)
    if len(out) != SAMPLE_N or out.src_id.nunique() != SAMPLE_N:
        raise RuntimeError("frozen sample reconstruction failed")
    return out.sort_values(["structural_cluster", "sample_role", "src_id"], kind="stable").reset_index(drop=True)


def clean_tan_header_from_full(pw: WCS, ph: fits.Header, sl_y: slice, sl_x: slice, crpix_dx: float, crpix_dy: float):
    ny = int(sl_y.stop - sl_y.start); nx = int(sl_x.stop - sl_x.start)
    fx, fy = np.meshgrid(np.linspace(0, nx - 1, 25), np.linspace(0, ny - 1, 25))
    fx, fy = fx.ravel(), fy.ravel()
    full_x = fx + float(sl_x.start); full_y = fy + float(sl_y.start)
    sky = pw.pixel_to_world(full_x, full_y)
    ctr = pw.pixel_to_world(float(sl_x.start) + (nx - 1) / 2.0, float(sl_y.start) + (ny - 1) / 2.0)
    fw = fit_wcs_from_points((fx, fy), sky, proj_point=ctr, projection="TAN", sip_degree=None)
    resid = fw.pixel_to_world(fx, fy).separation(sky).arcsec
    hdr = fw.to_header(relax=True)
    cd = {}
    for i in (1, 2):
        d = hdr.get(f"CDELT{i}", 1.0)
        for j in (1, 2):
            cd[(i, j)] = d * hdr.get(f"PC{i}_{j}", 1.0 if i == j else 0.0)
    for i in (1, 2):
        for j in (1, 2):
            hdr[f"CD{i}_{j}"] = cd[(i, j)]
            hdr.remove(f"PC{i}_{j}", ignore_missing=True)
        hdr.remove(f"CDELT{i}", ignore_missing=True)
        hdr.remove(f"CUNIT{i}", ignore_missing=True)
    for k in ("REGION", "PLTLABEL", "PLATEID", "DATE-OBS", "SURVEY", "EQUINOX"):
        if k in ph:
            hdr[k] = ph[k]
    if crpix_dx or crpix_dy:
        hdr["CRPIX1"] = hdr["CRPIX1"] - crpix_dx
        hdr["CRPIX2"] = hdr["CRPIX2"] - crpix_dy
        hdr["VASCOCPX"] = (f"{crpix_dx:+.4f},{crpix_dy:+.4f}", "per-plate CRPIX correction")
    return fits.Header(hdr), float(np.median(resid)), float(np.max(resid))


def reconstruct_tiles(sample: pd.DataFrame, upstream_root: Path, tiles_root: Path):
    sys.path.insert(0, str(upstream_root))
    from vasco.utils.tile_id import format_tile_id

    crpix = pd.read_csv(upstream_root / "data" / "plate_crpix_table.csv")
    crpix = crpix.rename(columns={"plate": "plate_id"})
    c_lookup = {str(r.plate_id): r for r in crpix.itertuples(index=False)}
    required = sample[["plate_id", "tile_id"]].drop_duplicates().copy()
    expected_by_plate = {p: set(g.tile_id.astype(str)) for p, g in required.groupby("plate_id")}
    records = []

    for pi, plate in enumerate(sorted(expected_by_plate), 1):
        targets = expected_by_plate[plate]
        url = IRSA_FMT.format(plate=plate)
        with fits.open(
            url, use_fsspec=True, lazy_load_hdus=True,
            fsspec_kwargs={"block_size": FSSPEC_BLOCK_SIZE, "cache_type": "readahead"}
        ) as hdul:
            hdu = hdul[0]
            ph = hdu.header
            pw = WCS(ph)
            ny, nx = hdu.shape
            scale = float(ph["XPIXELSZ"]) / 1000.0 * float(ph["PLTSCALE"])
            tile_px = SIZE_ARCMIN * 60.0 / scale
            tw = th = int(round(tile_px))
            def centres(span):
                lo, hi = tile_px / 2.0, span - tile_px / 2.0
                return np.linspace(lo, hi, GRID) if hi > lo else np.full(GRID, span / 2.0)
            cx, cy = centres(nx), centres(ny)
            grid = {}
            for py in cy:
                for px in cx:
                    ra, dec = [float(v) for v in pw.pixel_to_world_values(px, py)]
                    tid = format_tile_id(ra % 360.0, dec)
                    grid[tid] = (float(px), float(py), ra % 360.0, dec)
            missing = targets - set(grid)
            if missing:
                for tid in sorted(missing):
                    records.append({"plate_id": plate, "tile_id": tid, "tile_identity": "MISSING_FROM_REGENERATED_GRID"})
                print(f"[tile-id] {plate}: missing {len(missing)} target tile(s)", flush=True)
                continue
            if plate not in c_lookup:
                raise RuntimeError(f"{plate}: missing CRPIX row")
            crow = c_lookup[plate]
            if str(crow.status) != "ok":
                raise RuntimeError(f"{plate}: unusable CRPIX status {crow.status}")
            dx, dy = float(crow.delta_x_px), float(crow.delta_y_px)
            for tid in sorted(targets):
                px, py, ra, dec = grid[tid]
                sl_large, _sl_small = overlap_slices((ny, nx), (th, tw), (py, px), mode="trim")
                sl_y, sl_x = sl_large
                arr = np.asarray(hdu.section[sl_y, sl_x])
                if arr.size == 0:
                    records.append({"plate_id": plate, "tile_id": tid, "tile_identity": "EMPTY_SECTION"})
                    continue
                hdr, rmed, rmax = clean_tan_header_from_full(pw, ph, sl_y, sl_x, dx, dy)
                tdir = tiles_root / tid
                raw = tdir / "raw"; raw.mkdir(parents=True, exist_ok=True)
                name = f"dss1-red_{ra:.3f}_{dec:.3f}_{SIZE_ARCMIN:.0f}arcmin.fits"
                out = raw / name
                fits.PrimaryHDU(arr.astype(np.int16), header=hdr).writeto(out, overwrite=True)
                records.append({
                    "plate_id": plate, "tile_id": tid, "tile_identity": "RECONSTRUCTED",
                    "tile_fits": str(out), "shape_y": int(arr.shape[0]), "shape_x": int(arr.shape[1]),
                    "tan_refit_median_arcsec": rmed, "tan_refit_max_arcsec": rmax,
                    "crpix_dx": dx, "crpix_dy": dy,
                })
        print(f"[plate-replay] {pi}/{len(expected_by_plate)} {plate}", flush=True)
    return pd.DataFrame(records)


def find_object_hdu(ldac: Path):
    hdul = fits.open(ldac, memmap=False)
    for hdu in hdul:
        if getattr(hdu, "data", None) is None or not hasattr(hdu, "columns"):
            continue
        names = list(hdu.columns.names or [])
        if "NUMBER" in names:
            return hdul, hdu
    hdul.close()
    raise RuntimeError(f"no object table with NUMBER in {ldac}")


def scalarize(v):
    if isinstance(v, np.ndarray):
        if v.size == 1:
            return v.ravel()[0].item()
        return None
    if isinstance(v, np.generic):
        return v.item()
    return v


def export_pass2_csv(ldac: Path, out_csv: Path):
    hdul, obj = find_object_hdu(ldac)
    wanted = [
        "NUMBER", "FLAGS", "X_IMAGE", "Y_IMAGE", "XWIN_IMAGE", "YWIN_IMAGE",
        "ELONGATION", "FWHM_IMAGE", "ALPHA_J2000", "DELTA_J2000",
        "ALPHAWIN_J2000", "DELTAWIN_J2000", "FLUX_AUTO", "MAG_AUTO",
        "CLASS_STAR", "ELLIPTICITY", "SPREAD_MODEL", "SPREADERR_MODEL", "SNR_WIN"
    ]
    cols = [c for c in wanted if c in obj.columns.names]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for row in obj.data:
            w.writerow({c: scalarize(row[c]) for c in cols})
    n = len(obj.data)
    hdul.close()
    return n, cols


def run_detection_one(tile_row: dict, upstream_root: Path, tiles_root: Path):
    tid = tile_row["tile_id"]
    if tile_row.get("tile_identity") != "RECONSTRUCTED":
        return {"tile_id": tid, "detection_status": "SKIPPED_TILE_NOT_RECONSTRUCTED"}
    sys.path.insert(0, str(upstream_root))
    from vasco.pipeline_split import run_pass1, run_psfex, run_pass2
    tdir = tiles_root / tid
    fits_files = sorted((tdir / "raw").glob("*.fits"))
    if len(fits_files) != 1:
        return {"tile_id": tid, "detection_status": "FAIL_FITS_COUNT"}
    try:
        p1, _ = run_pass1(fits_files[0], tdir, config_root=str(upstream_root / "configs"))
        psf = run_psfex(p1, tdir, config_root=str(upstream_root / "configs"))
        p2 = run_pass2(fits_files[0], tdir, psf, config_root=str(upstream_root / "configs"))
        n, cols = export_pass2_csv(p2, tdir / "catalogs" / "sextractor_pass2.csv")
        return {"tile_id": tid, "detection_status": "PASS", "pass2_rows": int(n), "pass2_columns": cols}
    except Exception as e:
        return {"tile_id": tid, "detection_status": "FAIL", "detection_error": f"{type(e).__name__}:{e}"[:500]}


def audit_sample_against_pass2(sample: pd.DataFrame, tiles_root: Path):
    rows = []
    for r in sample.itertuples(index=False):
        rec = {
            "src_id": str(r.src_id), "tile_id": str(r.tile_id), "object_id": int(r.object_id),
            "plate_id": str(r.plate_id), "structural_cluster": int(r.structural_cluster),
            "sample_role": str(r.sample_role), "structural_anomaly_score": float(r.anomaly_score),
            "s0_ra": float(r.ra), "s0_dec": float(r.dec),
        }
        p = tiles_root / str(r.tile_id) / "catalogs" / "sextractor_pass2.csv"
        if not p.exists():
            rec["exact_object_status"] = "PASS2_CATALOG_MISSING"; rows.append(rec); continue
        cat = pd.read_csv(p)
        if "NUMBER" not in cat.columns:
            rec["exact_object_status"] = "NUMBER_COLUMN_MISSING"; rows.append(rec); continue
        number = pd.to_numeric(cat.NUMBER, errors="coerce")
        hit = cat[number == int(r.object_id)]
        if len(hit) != 1:
            rec["exact_object_status"] = f"NUMBER_MATCH_COUNT_{len(hit)}"; rows.append(rec); continue
        q = hit.iloc[0]
        rec["exact_object_status"] = "EXACT_NUMBER_RECOVERED"
        for c in ("XWIN_IMAGE", "YWIN_IMAGE", "FWHM_IMAGE", "ELONGATION", "SPREAD_MODEL", "SPREADERR_MODEL", "SNR_WIN", "FLUX_AUTO", "MAG_AUTO"):
            rec[f"pass2_{c.lower()}"] = float(q[c]) if c in q.index and pd.notna(q[c]) else float("nan")
        ra_col = "ALPHAWIN_J2000" if "ALPHAWIN_J2000" in q.index else "ALPHA_J2000"
        de_col = "DELTAWIN_J2000" if "DELTAWIN_J2000" in q.index else "DELTA_J2000"
        if ra_col in q.index and de_col in q.index and pd.notna(q[ra_col]) and pd.notna(q[de_col]):
            pra, pde = float(q[ra_col]), float(q[de_col])
            rec["pass2_ra"] = pra; rec["pass2_dec"] = pde
            rec["pass2_to_s0_sep_arcsec"] = float(SkyCoord(pra*u.deg,pde*u.deg).separation(SkyCoord(float(r.ra)*u.deg,float(r.dec)*u.deg)).arcsec)
        rows.append(rec)
    return pd.DataFrame(rows)


def run_upstream_shape(sample: pd.DataFrame, upstream_root: Path, work_dir: Path, tiles_root: Path):
    run_dir = work_dir / "shape_run"; stages = run_dir / "stages"; stages.mkdir(parents=True, exist_ok=True)
    inp = stages / "stage_B2_INPUT.csv"
    sample[["src_id", "ra", "dec"]].to_csv(inp, index=False)
    cmd = [
        sys.executable, str(upstream_root / "scripts" / "stage_shape_post.py"),
        "--run-dir", str(run_dir), "--input-glob", "stages/stage_B2_INPUT.csv",
        "--stage", "B2", "--tiles-root", str(tiles_root), "--workers", "4"
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    flags = stages / "stage_B2_SHAPE_flags.csv"
    if not flags.exists():
        return pd.DataFrame(), {"returncode": proc.returncode, "stdout_tail": proc.stdout[-2000:], "stderr_tail": proc.stderr[-2000:]}
    return pd.read_csv(flags), {"returncode": proc.returncode, "stdout_tail": proc.stdout[-2000:], "stderr_tail": proc.stderr[-2000:]}


def frac_true(mask) -> float:
    a = np.asarray(mask, dtype=bool)
    return float(a.mean()) if len(a) else 0.0


def finite_mask(df: pd.DataFrame, cols):
    return np.isfinite(df[list(cols)].apply(pd.to_numeric, errors="coerce").to_numpy(float)).all(axis=1)


def canonical_sha(obj):
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


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

    print("[1/8] hash-gate frozen sample parents", flush=True)
    manifest, s0 = load_inputs(args.manifest)
    sample = select_same_64(manifest)
    sample = sample.merge(s0[["src_id", "tile_id", "object_id", "ra", "dec", "plate_id"]], on="src_id", validate="one_to_one")
    if len(sample) != 64 or sample.tile_id.isna().any():
        raise RuntimeError("sample/S0 join failed")

    print("[2/8] regenerate exact named tiles by sparse full-plate sections", flush=True)
    tiles_root = args.work_dir / "tiles"
    tile_replay = reconstruct_tiles(sample, args.upstream_root, tiles_root)
    req_tiles = sample.tile_id.nunique()
    good_tiles = set(tile_replay.loc[tile_replay.tile_identity == "RECONSTRUCTED", "tile_id"].astype(str))
    sample["tile_identity_reconstructed"] = sample.tile_id.astype(str).isin(good_tiles)
    tile_identity_rows = int(sample.tile_identity_reconstructed.sum())

    print("[3/8] replay pass1 -> PSFEx -> pass2", flush=True)
    unique_replay = tile_replay.drop_duplicates("tile_id").to_dict("records")
    det = []
    with cf.ThreadPoolExecutor(max_workers=DETECTION_WORKERS) as ex:
        futs = [ex.submit(run_detection_one, r, args.upstream_root, tiles_root) for r in unique_replay]
        for i, fut in enumerate(cf.as_completed(futs), 1):
            det.append(fut.result())
            if i % 8 == 0 or i == len(futs):
                print(f"[detection] {i}/{len(futs)}", flush=True)
    det_df = pd.DataFrame(det)
    det_pass_tiles = int((det_df.detection_status == "PASS").sum()) if len(det_df) else 0
    detection_fraction = det_pass_tiles / req_tiles if req_tiles else 0.0

    print("[4/8] exact NUMBER lineage audit", flush=True)
    audit = audit_sample_against_pass2(sample, tiles_root)
    exact = audit.exact_object_status.eq("EXACT_NUMBER_RECOVERED")
    exact_n = int(exact.sum()); exact_frac = exact_n / SAMPLE_N
    seps = pd.to_numeric(audit.loc[exact, "pass2_to_s0_sep_arcsec"] if "pass2_to_s0_sep_arcsec" in audit else pd.Series(dtype=float), errors="coerce")
    sep_finite = seps[np.isfinite(seps)]
    sep_le10_frac = float((sep_finite <= 10.0).mean()) if len(sep_finite) else 0.0
    sep_median = float(np.median(sep_finite)) if len(sep_finite) else float("nan")
    sep_p95 = float(np.quantile(sep_finite, .95)) if len(sep_finite) else float("nan")
    morph_cols = ["pass2_fwhm_image", "pass2_elongation", "pass2_spread_model"]
    pass2_morph_frac = frac_true(finite_mask(audit.loc[exact], morph_cols)) if exact_n else 0.0

    print("[5/8] execute pinned upstream shape stage from recovered centroids", flush=True)
    shape, shape_exec = run_upstream_shape(sample, args.upstream_root, args.work_dir, tiles_root)
    if len(shape):
        shape["src_id"] = shape.src_id.astype(str)
        shape_small = shape[[c for c in shape.columns if c in {
            "src_id","profile_diff","circularity","area","shape_defect","circle_deviation",
            "shape_confidence","elongation","stars_used","shape_failed","failure_reason",
            "reject_flag","reject_reason"
        }]].copy()
        audit = audit.merge(shape_small, on="src_id", how="left", validate="one_to_one")
    else:
        audit["shape_failed"] = 1
        audit["failure_reason"] = "SHAPE_STAGE_OUTPUT_MISSING"
    shape_failed = pd.to_numeric(audit.get("shape_failed"), errors="coerce").fillna(1).astype(int)
    shape_success_exact = exact & shape_failed.eq(0)
    shape_success_frac_exact = float(shape_success_exact.sum() / exact_n) if exact_n else 0.0

    print("[6/8] evaluate frozen gates", flush=True)
    tile_identity_pass = tile_identity_rows == SAMPLE_N
    transport_pass = len(good_tiles) == req_tiles
    detection_pass = detection_fraction >= 0.95
    object_pass = exact_frac >= 0.90
    sep_pass = sep_le10_frac >= 0.90
    pass2_morph_pass = pass2_morph_frac >= 0.95
    shape_pass = shape_success_frac_exact >= 0.90
    if not tile_identity_pass:
        outcome = "FAIL_CLOSED_TILE_IDENTITY"
    elif not transport_pass:
        outcome = "FAIL_CLOSED_TRANSPORT"
    elif not detection_pass:
        outcome = "FAIL_CLOSED_DETECTION_REPLAY"
    elif not (object_pass and sep_pass):
        outcome = "FAIL_CLOSED_OBJECT_ID_LINEAGE"
    elif not (pass2_morph_pass and shape_pass):
        outcome = "FAIL_CLOSED_MORPHOLOGY_REPLAY"
    else:
        outcome = "PASS_TILE_LINEAGE_REPLAY_AND_PIXEL_MORPHOLOGY_PILOT"

    print("[7/8] freeze replay sidecar", flush=True)
    audit = audit.sort_values(["structural_cluster", "sample_role", "src_id"], kind="stable").reset_index(drop=True)
    sidecar_csv = audit.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    sidecar_csv_sha = sha256_bytes(sidecar_csv)
    with args.out_sidecar_gz.open("wb") as fout:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fout, mtime=0) as gz:
            gz.write(sidecar_csv)
    sidecar_gz_sha = sha256_bytes(args.out_sidecar_gz.read_bytes())

    print("[8/8] write result", flush=True)
    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-2F-B2-TILE-LINEAGE-REPLAY-RUN-001",
        "experiment_id": "JPFM-2F-B2", "schema_version": "1.0",
        "date": pd.Timestamp.utcnow().date().isoformat(), "status": "EXECUTED", "outcome": outcome,
        "claim_ceiling": "UPSTREAM_TILE_AND_OBJECT_PIXEL_LINEAGE_REPLAY_VALIDATION_ONLY__EXTERNAL_LABELS_SEALED__NO_CAUSAL_OR_ORIGIN_CLAIM",
        "bindings": {
            "admission_path": "data/JANUS-PALOMAR-JPFM-2F-B2-TILE-LINEAGE-REPLAY-ADMISSION-v1.0.json",
            "poss_commit": POSS_COMMIT, "poss_release": REL,
            "structural_manifest_csv_sha256": MANIFEST_CSV_SHA256,
            "structural_manifest_gzip_sha256": MANIFEST_GZ_SHA256,
            "B1_result_canonical_sha256": B1_RESULT_CANONICAL_SHA256,
        },
        "sample": {"rows": SAMPLE_N, "distinct_tiles": int(req_tiles), "distinct_plates": int(sample.plate_id.nunique()), "same_as_B1": True},
        "tile_replay": {
            "sample_rows_with_exact_tile_identity": tile_identity_rows,
            "required_distinct_tiles": int(req_tiles), "reconstructed_distinct_tiles": int(len(good_tiles)),
            "tile_identity_pass": tile_identity_pass, "transport_pass": transport_pass,
            "full_remote_plate_array_accessed": False,
            "tile_refit_median_arcsec": float(pd.to_numeric(tile_replay.get("tan_refit_median_arcsec"), errors="coerce").median()),
            "tile_refit_max_arcsec": float(pd.to_numeric(tile_replay.get("tan_refit_max_arcsec"), errors="coerce").max()),
        },
        "detection_replay": {
            "tiles_pass": det_pass_tiles, "tiles_required": int(req_tiles), "pass_fraction": detection_fraction,
            "gate_pass": detection_pass,
            "status_census": {str(k): int(v) for k,v in det_df.detection_status.value_counts(dropna=False).items()} if len(det_df) else {},
        },
        "object_lineage": {
            "exact_NUMBER_recovered": exact_n, "exact_NUMBER_fraction": exact_frac, "gate_pass": object_pass,
            "pass2_to_S0_sep_arcsec_median": sep_median, "pass2_to_S0_sep_arcsec_p95": sep_p95,
            "pass2_to_S0_sep_le10_fraction": sep_le10_frac, "sky_consistency_gate_pass": sep_pass,
            "status_census": {str(k): int(v) for k,v in audit.exact_object_status.value_counts(dropna=False).items()},
        },
        "pixel_morphology": {
            "finite_FWHM_ELONGATION_SPREAD_fraction_among_exact": pass2_morph_frac,
            "pass2_raw_morphology_gate_pass": pass2_morph_pass,
            "upstream_shape_success_fraction_among_exact": shape_success_frac_exact,
            "upstream_shape_gate_pass": shape_pass,
            "shape_returncode": int(shape_exec.get("returncode", -999)),
            "profile_diff_finite": int(np.isfinite(pd.to_numeric(audit.get("profile_diff"), errors="coerce")).sum()) if "profile_diff" in audit else 0,
            "circularity_finite": int(np.isfinite(pd.to_numeric(audit.get("circularity"), errors="coerce")).sum()) if "circularity" in audit else 0,
        },
        "external_label_firewall": {"external_label_reveal_authorized": False, "date_or_external_environment_used_for_selection": False},
        "sidecar": {"path": str(args.out_sidecar_gz), "rows": int(len(audit)), "csv_sha256": sidecar_csv_sha, "gzip_sha256": sidecar_gz_sha},
        "next_gate": (
            "BUILD_LARGER_OR_FULL_LABEL_BLIND_PIXEL_MORPHOLOGY_SIDECAR" if outcome == "PASS_TILE_LINEAGE_REPLAY_AND_PIXEL_MORPHOLOGY_PILOT"
            else "REPAIR_PIXEL_LINEAGE_WITHOUT_RELAXING_FROZEN_B2_THRESHOLDS"
        ),
    }
    result["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_sha(result)}
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("OUTCOME", outcome, flush=True)
    print("EXACT_NUMBER", exact_n, "SEP_LE10_FRAC", sep_le10_frac, "SHAPE_SUCCESS_EXACT", shape_success_frac_exact, flush=True)
    print("SIDECAR_CSV_SHA256", sidecar_csv_sha, flush=True)
    print("RESULT_CANONICAL_SHA256", result["integrity"]["canonical_payload_sha256_without_integrity"], flush=True)


if __name__ == "__main__":
    main()
