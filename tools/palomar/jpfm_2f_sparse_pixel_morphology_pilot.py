#!/usr/bin/env python3
"""JPFM-2F-B sparse, plate-addressed, label-blind pixel morphology pilot.

This runner validates that a deterministic 64-source sample from the already
frozen JPFM-2F-A structural manifest can be measured directly from named public
POSS-I full-plate FITS files without downloading full image arrays.  It uses
Astropy/fsspec ImageHDU.section only.  No temporal, witness, nuclear, lunar,
geomagnetic, or UAP labels are available to this program.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from scipy import ndimage
from scipy.spatial import ConvexHull

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

SAMPLE_N = 64
PER_CLUSTER = 4
STAMP_PX = 161
HALF_STAMP = STAMP_PX // 2
SEARCH_RADIUS = 12
MEASURE_RADIUS = 10
BORDER = 12
REFERENCE_MAX = 12
FSSPEC_BLOCK_SIZE = 1024 * 1024

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "JANUS-JPFM-2F-B-sparse-pixel-pilot/1.0"})


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def get_bytes(url: str, timeout: int = 90) -> bytes:
    r = SESSION.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content


def require_hash(label: str, data: bytes, expected: str) -> None:
    got = sha256_bytes(data)
    if got != expected:
        raise RuntimeError(f"{label} sha256 mismatch: got={got} expected={expected}")


def load_inputs(manifest_path: Path):
    mgz = manifest_path.read_bytes()
    require_hash("blind structural manifest gzip", mgz, MANIFEST_GZ_SHA256)
    mcsv = gzip.decompress(mgz)
    require_hash("blind structural manifest csv", mcsv, MANIFEST_CSV_SHA256)
    manifest = pd.read_csv(io.BytesIO(mcsv))
    if len(manifest) != 122820 or manifest.src_id.duplicated().any():
        raise RuntimeError("blind manifest invariant failed")

    s0_gz = get_bytes(S0_URL)
    tiles_gz = get_bytes(TILES_URL)
    require_hash("S0 gzip", s0_gz, S0_GZ_SHA256)
    require_hash("tile manifest gzip", tiles_gz, TILES_GZ_SHA256)
    s0_csv = gzip.decompress(s0_gz)
    tiles_csv = gzip.decompress(tiles_gz)
    require_hash("S0 csv", s0_csv, S0_CSV_SHA256)
    require_hash("tile manifest csv", tiles_csv, TILES_CSV_SHA256)
    s0 = pd.read_csv(io.BytesIO(s0_csv))
    tiles = pd.read_csv(io.BytesIO(tiles_csv))
    if len(s0) != 122820 or len(tiles) != 31458:
        raise RuntimeError("public release row invariant failed")
    tile_map = tiles[["tile_id", "plate_id"]].drop_duplicates()
    if tile_map.tile_id.duplicated().any():
        raise RuntimeError("tile_id maps to multiple plates")
    s0 = s0.merge(tile_map, on="tile_id", how="left", validate="many_to_one")
    if s0.plate_id.isna().any():
        raise RuntimeError("S0 tile->plate join incomplete")
    return manifest, s0


def select_sample(manifest: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in range(16):
        g = manifest[manifest.structural_cluster.astype(int) == c].copy()
        if len(g) < PER_CLUSTER:
            raise RuntimeError(f"cluster {c} too small for pilot sample")
        g["src_id"] = g.src_id.astype(str)
        med = float(g.anomaly_score.median())
        g["median_distance"] = (g.anomaly_score.astype(float) - med).abs()
        typical = g.sort_values(["median_distance", "src_id"], kind="stable").head(2)
        used = set(typical.src_id)
        unusual = g[~g.src_id.isin(used)].sort_values(
            ["anomaly_score", "src_id"], ascending=[False, True], kind="stable"
        ).head(2)
        if len(unusual) != 2:
            raise RuntimeError(f"cluster {c}: failed to select two unusual rows")
        t = typical.copy(); t["sample_role"] = "typical"
        u = unusual.copy(); u["sample_role"] = "unusual"
        rows.extend([t, u])
    out = pd.concat(rows, ignore_index=True)
    if len(out) != SAMPLE_N or out.src_id.duplicated().any():
        raise RuntimeError("pilot sample invariant failed")
    return out.sort_values(["structural_cluster", "sample_role", "src_id"], kind="stable").reset_index(drop=True)


def robust_sigma(a) -> float:
    x = np.asarray(a, dtype=float)
    x = x[np.isfinite(x)]
    if not len(x):
        return float("nan")
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    sig = 1.4826 * mad
    if sig <= 0:
        sig = float(np.std(x))
    return sig if sig > 0 else 1.0


def border_values(arr: np.ndarray, width: int = BORDER) -> np.ndarray:
    h, w = arr.shape
    if h < 2 * width + 1 or w < 2 * width + 1:
        return arr.ravel()
    mask = np.zeros_like(arr, dtype=bool)
    mask[:width, :] = True; mask[-width:, :] = True
    mask[:, :width] = True; mask[:, -width:] = True
    return arr[mask]


def radial_profile(signal: np.ndarray, cy: float, cx: float, radius: int = MEASURE_RADIUS):
    yy, xx = np.indices(signal.shape, dtype=float)
    rr = np.hypot(xx - cx, yy - cy)
    edges = np.arange(0.0, radius + 0.5001, 0.5)
    prof = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (rr >= lo) & (rr < hi)
        vals = signal[m]
        prof.append(float(np.mean(vals)) if vals.size else 0.0)
    a = np.asarray(prof, dtype=float)
    mx = float(np.max(a)) if len(a) else 0.0
    return a / mx if mx > 0 else a


def measure_source(signal: np.ndarray, py: int, px: int, sigma_bg: float):
    y0 = max(0, py - MEASURE_RADIUS); y1 = min(signal.shape[0], py + MEASURE_RADIUS + 1)
    x0 = max(0, px - MEASURE_RADIUS); x1 = min(signal.shape[1], px + MEASURE_RADIUS + 1)
    sub = np.asarray(signal[y0:y1, x0:x1], dtype=float)
    if sub.shape[0] < 2 * MEASURE_RADIUS - 2 or sub.shape[1] < 2 * MEASURE_RADIUS - 2:
        return None
    sy, sx = np.indices(sub.shape, dtype=float)
    local_py, local_px = py - y0, px - x0
    rr0 = np.hypot(sx - local_px, sy - local_py)
    peak = float(sub[local_py, local_px])
    threshold = max(2.0 * sigma_bg, 0.03 * peak)
    weights = np.where((sub > threshold) & (rr0 <= MEASURE_RADIUS), sub, 0.0)
    sw = float(weights.sum())
    if not math.isfinite(sw) or sw <= 0:
        return None
    cx = float((weights * sx).sum() / sw)
    cy = float((weights * sy).sum() / sw)
    dx, dy = sx - cx, sy - cy
    cxx = float((weights * dx * dx).sum() / sw)
    cyy = float((weights * dy * dy).sum() / sw)
    cxy = float((weights * dx * dy).sum() / sw)
    vals, vecs = np.linalg.eigh(np.array([[cxx, cxy], [cxy, cyy]], dtype=float))
    vals = np.maximum(vals, 1e-8)
    lmin, lmax = float(vals[0]), float(vals[1])
    fwhm_minor = 2.354820045 * math.sqrt(lmin)
    fwhm_major = 2.354820045 * math.sqrt(lmax)
    fwhm = math.sqrt(fwhm_major * fwhm_minor)
    elongation = fwhm_major / fwhm_minor if fwhm_minor > 0 else float("nan")
    major_vec = vecs[:, 1]
    orientation = math.degrees(math.atan2(float(major_vec[1]), float(major_vec[0])))

    rr = np.hypot(sx - cx, sy - cy)
    f2 = float(sub[rr <= 2.0].clip(min=0).sum())
    f6 = float(sub[rr <= 6.0].clip(min=0).sum())
    concentration = f2 / f6 if f6 > 0 else float("nan")

    mask = (sub >= max(3.0 * sigma_bg, 0.30 * peak)) & (rr <= MEASURE_RADIUS)
    lab, _n = ndimage.label(mask)
    seed_y = int(np.clip(round(cy), 0, sub.shape[0] - 1)); seed_x = int(np.clip(round(cx), 0, sub.shape[1] - 1))
    target_label = int(lab[seed_y, seed_x])
    comp = (lab == target_label) if target_label > 0 else np.zeros_like(mask)
    area = int(comp.sum())
    perimeter_mask = comp & ~ndimage.binary_erosion(comp)
    perimeter = int(perimeter_mask.sum())
    circularity = (4.0 * math.pi * area / (perimeter * perimeter)) if perimeter > 0 else float("nan")
    boundary_yx = np.argwhere(perimeter_mask)
    convex_defect = float("nan")
    circle_dev = float("nan")
    if len(boundary_yx) >= 3:
        by = boundary_yx[:, 0].astype(float); bx = boundary_yx[:, 1].astype(float)
        br = np.hypot(bx - cx, by - cy)
        mean_r = float(np.mean(br))
        circle_dev = float(np.std(br) / mean_r) if mean_r > 0 else float("nan")
        try:
            hull = ConvexHull(np.column_stack([bx, by]))
            hull_area = float(hull.volume)
            pixel_area_proxy = float(area)
            convex_defect = max(0.0, min(1.0, (hull_area - pixel_area_proxy) / hull_area)) if hull_area > 0 else float("nan")
        except Exception:
            pass

    profile = radial_profile(sub.clip(min=0), cy, cx, MEASURE_RADIUS)
    return {
        "centroid_x_local": cx,
        "centroid_y_local": cy,
        "moment_fwhm_px": fwhm,
        "moment_fwhm_major_px": fwhm_major,
        "moment_fwhm_minor_px": fwhm_minor,
        "elongation": elongation,
        "orientation_deg": orientation,
        "core_concentration_r2_over_r6": concentration,
        "threshold_area_px": area,
        "circularity": circularity,
        "convex_defect_fraction": convex_defect,
        "circle_deviation": circle_dev,
        "profile": profile,
    }


def find_references(signal: np.ndarray, target_y: int, target_x: int, sigma_bg: float, target_peak: float):
    sm = ndimage.gaussian_filter(signal, 1.0)
    maxima = (sm == ndimage.maximum_filter(sm, size=7, mode="nearest"))
    threshold = 5.0 * sigma_bg
    maxima &= (signal >= threshold)
    edge = MEASURE_RADIUS + 2
    maxima[:edge, :] = False; maxima[-edge:, :] = False
    maxima[:, :edge] = False; maxima[:, -edge:] = False
    ys, xs = np.nonzero(maxima)
    candidates = []
    for y, x in zip(ys, xs):
        dist = math.hypot(float(x - target_x), float(y - target_y))
        if dist <= 2.0 * MEASURE_RADIUS:
            continue
        amp = float(signal[y, x])
        if target_peak <= 0 or not (0.5 * target_peak <= amp <= 2.0 * target_peak):
            continue
        candidates.append((dist, -amp, int(y), int(x)))
    candidates.sort()
    refs = []
    for _dist, _negamp, y, x in candidates:
        m = measure_source(signal, y, x, sigma_bg)
        if m is None:
            continue
        if not math.isfinite(m["moment_fwhm_px"]) or not math.isfinite(m["elongation"]):
            continue
        refs.append(m)
        if len(refs) >= REFERENCE_MAX:
            break
    return refs


def profile_diff(candidate: np.ndarray, refs: list[np.ndarray]):
    if len(refs) < 3:
        return float("nan")
    n = min([len(candidate)] + [len(x) for x in refs])
    cand = np.asarray(candidate[:n], dtype=float)
    ref = np.nanmean(np.vstack([np.asarray(x[:n], dtype=float) for x in refs]), axis=0)
    diff = cand - ref
    diff = np.where(ref <= 0.1, 0.0, diff)
    diff = diff * ref
    diff[:2] = 0.0
    return float(math.sqrt(float(np.sum(diff * diff)) / max(1, len(diff))))


def sparse_stamp(hdu, wcs: WCS, ra: float, dec: float):
    # World coordinates are used only as a locator into the named plate.  The
    # final source centre is recovered from the pixels inside this neighbourhood.
    xpred, ypred = wcs.world_to_pixel_values(float(ra), float(dec))
    if not (math.isfinite(xpred) and math.isfinite(ypred)):
        raise RuntimeError("full-plate WCS returned non-finite predicted pixel")
    ny, nx = hdu.shape
    x0 = max(0, int(math.floor(xpred)) - HALF_STAMP)
    x1 = min(nx, int(math.floor(xpred)) + HALF_STAMP + 1)
    y0 = max(0, int(math.floor(ypred)) - HALF_STAMP)
    y1 = min(ny, int(math.floor(ypred)) + HALF_STAMP + 1)
    arr = np.asarray(hdu.section[y0:y1, x0:x1], dtype=float)
    if arr.size == 0:
        raise RuntimeError("empty sparse section")
    return arr, float(xpred - x0), float(ypred - y0), (x0, y0)


def measure_stamp(arr: np.ndarray, pred_x: float, pred_y: float):
    bgvals = border_values(arr)
    bg = float(np.median(bgvals))
    sigma_bg = robust_sigma(bgvals)
    # POSS photographic negatives contain stars as lower photographic-density
    # values in the convention used by the upstream shape stage.  Subtracting
    # from the local background is equivalent to constant inversion + background subtraction.
    signal = np.clip(bg - arr, 0.0, None)
    sm = ndimage.gaussian_filter(signal, 1.0)
    sx0 = max(0, int(math.floor(pred_x)) - SEARCH_RADIUS)
    sx1 = min(arr.shape[1], int(math.floor(pred_x)) + SEARCH_RADIUS + 1)
    sy0 = max(0, int(math.floor(pred_y)) - SEARCH_RADIUS)
    sy1 = min(arr.shape[0], int(math.floor(pred_y)) + SEARCH_RADIUS + 1)
    if sx1 <= sx0 or sy1 <= sy0:
        raise RuntimeError("predicted pixel outside sparse stamp")
    local = sm[sy0:sy1, sx0:sx1]
    iy, ix = np.unravel_index(int(np.argmax(local)), local.shape)
    py, px = sy0 + int(iy), sx0 + int(ix)
    offset = math.hypot(float(px) - pred_x, float(py) - pred_y)
    target_peak = float(signal[py, px])
    peak_snr = target_peak / sigma_bg if sigma_bg > 0 else float("nan")
    cand = measure_source(signal, py, px, sigma_bg)
    refs = find_references(signal, py, px, sigma_bg, target_peak)
    out = {
        "background_median": bg,
        "background_robust_sigma": sigma_bg,
        "predicted_x_in_stamp": pred_x,
        "predicted_y_in_stamp": pred_y,
        "recenter_x_in_stamp": float(px),
        "recenter_y_in_stamp": float(py),
        "recenter_offset_px": offset,
        "peak_snr": peak_snr,
        "reference_count": int(len(refs)),
    }
    if cand is None:
        out["measurement_status"] = "SOURCE_MEASUREMENT_FAILED"
        return out
    out.update({k: v for k, v in cand.items() if k != "profile"})
    if refs:
        fwhms = [r["moment_fwhm_px"] for r in refs if math.isfinite(r["moment_fwhm_px"])]
        out["reference_median_fwhm_px"] = float(np.median(fwhms)) if fwhms else float("nan")
    else:
        out["reference_median_fwhm_px"] = float("nan")
    ref_fwhm = out["reference_median_fwhm_px"]
    out["fwhm_ratio"] = float(cand["moment_fwhm_px"] / ref_fwhm) if math.isfinite(ref_fwhm) and ref_fwhm > 0 else float("nan")
    out["profile_diff"] = profile_diff(cand["profile"], [r["profile"] for r in refs])
    out["measurement_status"] = "MEASURED"
    return out


def finite_fraction(df: pd.DataFrame, cols: list[str], subset_mask: pd.Series) -> float:
    sub = df.loc[subset_mask, cols]
    if len(sub) == 0:
        return 0.0
    ok = np.isfinite(sub.apply(pd.to_numeric, errors="coerce").to_numpy(float)).all(axis=1)
    return float(ok.mean())


def canonical_sha(obj) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-csv-gz", required=True, type=Path)
    args = ap.parse_args()
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_csv_gz.parent.mkdir(parents=True, exist_ok=True)

    print("[1/6] load + hash-gate frozen blind parent and public S0", flush=True)
    manifest, s0 = load_inputs(args.manifest)
    sample = select_sample(manifest)
    d = sample.merge(s0[["src_id", "tile_id", "object_id", "ra", "dec", "plate_id"]], on="src_id", how="left", validate="one_to_one")
    if d[["tile_id", "ra", "dec", "plate_id"]].isna().any().any():
        raise RuntimeError("sample join to public S0 incomplete")
    if len(d) != SAMPLE_N or d.structural_cluster.nunique() != 16:
        raise RuntimeError("sample structure invariant failed")

    print(f"[2/6] sparse plate-addressed pixel reads for {SAMPLE_N} sources", flush=True)
    rows = []
    plates = sorted(d.plate_id.astype(str).unique())
    done = 0
    for pi, plate in enumerate(plates, 1):
        url = IRSA_FMT.format(plate=plate)
        g = d[d.plate_id.astype(str) == plate].copy().sort_values("src_id")
        try:
            with fits.open(
                url,
                use_fsspec=True,
                lazy_load_hdus=True,
                fsspec_kwargs={"block_size": FSSPEC_BLOCK_SIZE, "cache_type": "readahead"},
            ) as hdul:
                hdu = hdul[0]
                wcs = WCS(hdu.header)
                for r in g.itertuples(index=False):
                    base = {
                        "src_id": str(r.src_id),
                        "structural_cluster": int(r.structural_cluster),
                        "sample_role": str(r.sample_role),
                        "structural_anomaly_score": float(r.anomaly_score),
                        "tile_id": str(r.tile_id),
                        "object_id": str(r.object_id),
                        "plate_id": plate,
                        "ra": float(r.ra),
                        "dec": float(r.dec),
                        "plate_url": url,
                    }
                    try:
                        arr, pred_x, pred_y, origin = sparse_stamp(hdu, wcs, float(r.ra), float(r.dec))
                        m = measure_stamp(arr, pred_x, pred_y)
                        base.update(m)
                        base["stamp_status"] = "OK"
                        base["stamp_shape_y"] = int(arr.shape[0]); base["stamp_shape_x"] = int(arr.shape[1])
                        base["stamp_origin_x"] = int(origin[0]); base["stamp_origin_y"] = int(origin[1])
                    except Exception as e:
                        base["stamp_status"] = "FAILED"
                        base["failure_reason"] = f"{type(e).__name__}:{e}"
                    rows.append(base)
                    done += 1
                    if done % 8 == 0 or done == SAMPLE_N:
                        print(f"[pixels] {done}/{SAMPLE_N}", flush=True)
        except Exception as e:
            for r in g.itertuples(index=False):
                rows.append({
                    "src_id": str(r.src_id), "structural_cluster": int(r.structural_cluster),
                    "sample_role": str(r.sample_role), "structural_anomaly_score": float(r.anomaly_score),
                    "tile_id": str(r.tile_id), "object_id": str(r.object_id), "plate_id": plate,
                    "ra": float(r.ra), "dec": float(r.dec), "plate_url": url,
                    "stamp_status": "FAILED_PLATE_OPEN", "failure_reason": f"{type(e).__name__}:{e}"
                })
                done += 1
        print(f"[plates] {pi}/{len(plates)}", flush=True)

    print("[3/6] evaluate predeclared measurement gates", flush=True)
    out = pd.DataFrame(rows).sort_values(["structural_cluster", "sample_role", "src_id"], kind="stable").reset_index(drop=True)
    if len(out) != SAMPLE_N or out.src_id.duplicated().any():
        raise RuntimeError("output row invariant failed")
    stamp_ok = out.stamp_status.astype(str).eq("OK")
    rec_offset = pd.to_numeric(out.get("recenter_offset_px"), errors="coerce")
    snr = pd.to_numeric(out.get("peak_snr"), errors="coerce")
    recovered = stamp_ok & (snr >= 5.0) & (rec_offset <= SEARCH_RADIUS)
    n_stamp_ok = int(stamp_ok.sum())
    n_recovered = int(recovered.sum())
    recovery_fraction = n_recovered / SAMPLE_N
    finite_morph = finite_fraction(out, ["moment_fwhm_px", "elongation"], recovered)
    recvals = rec_offset[recovered & np.isfinite(rec_offset)].to_numpy(float)
    rec_med = float(np.median(recvals)) if len(recvals) else float("nan")
    rec_p95 = float(np.quantile(recvals, 0.95)) if len(recvals) else float("nan")
    ref_count = pd.to_numeric(out.get("reference_count"), errors="coerce").fillna(0)
    ref_coverage = float((ref_count[recovered] >= 3).mean()) if n_recovered else 0.0

    transport_pass = (n_stamp_ok == SAMPLE_N)
    raw_pass = (
        recovery_fraction >= 0.80 and finite_morph >= 0.95 and
        math.isfinite(rec_med) and rec_med <= 4.0 and
        math.isfinite(rec_p95) and rec_p95 <= 10.0
    )
    ref_pass = ref_coverage >= 0.50
    if not transport_pass:
        outcome = "FAIL_CLOSED_TRANSPORT"
    elif not raw_pass:
        outcome = "FAIL_CLOSED_SOURCE_RECOVERY_OR_MORPHOLOGY"
    elif ref_pass:
        outcome = "PASS_SPARSE_PIXEL_TRANSPORT_AND_RAW_MORPHOLOGY__LOCAL_PSF_REFERENCE_FEASIBLE"
    else:
        outcome = "PASS_SPARSE_PIXEL_TRANSPORT_AND_RAW_MORPHOLOGY__LOCAL_PSF_REFERENCE_INSUFFICIENT"

    print("[4/6] freeze blind pixel sidecar", flush=True)
    csv_bytes = out.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    csv_sha = sha256_bytes(csv_bytes)
    with args.out_csv_gz.open("wb") as fout:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fout, mtime=0) as gz:
            gz.write(csv_bytes)
    gz_sha = sha256_bytes(args.out_csv_gz.read_bytes())

    print("[5/6] build result", flush=True)
    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-2F-B-SPARSE-PIXEL-MORPHOLOGY-PILOT-RUN-001",
        "experiment_id": "JPFM-2F-B-PILOT",
        "schema_version": "1.0",
        "date": pd.Timestamp.utcnow().date().isoformat(),
        "status": "EXECUTED",
        "outcome": outcome,
        "claim_ceiling": "SPARSE_PUBLIC_PIXEL_TRANSPORT_AND_MORPHOLOGY_MEASUREMENT_VALIDATION_ONLY__NO_EXTERNAL_LABEL_INFERENCE__NO_ORIGIN_CLAIM",
        "bindings": {
            "admission_path": "data/JANUS-PALOMAR-JPFM-2F-B-SPARSE-PIXEL-MORPHOLOGY-PILOT-ADMISSION-v1.0.json",
            "poss_repository": "jannefi/poss1-plate-slice",
            "poss_commit": POSS_COMMIT,
            "poss_release": REL,
            "structural_manifest_csv_sha256": MANIFEST_CSV_SHA256,
            "structural_manifest_gzip_sha256": MANIFEST_GZ_SHA256,
        },
        "sample": {
            "rows": SAMPLE_N,
            "clusters": 16,
            "per_cluster": PER_CLUSTER,
            "selection": "2 closest-to-cluster-median anomaly score + 2 largest anomaly score; src_id tie-break",
            "unique_plates": int(d.plate_id.nunique()),
        },
        "transport": {
            "method": "Astropy FITS use_fsspec=True + PrimaryHDU.section",
            "full_image_array_accessed": False,
            "plate_addressed": True,
            "stamp_size_px": STAMP_PX,
            "fsspec_block_size_bytes": FSSPEC_BLOCK_SIZE,
            "stamp_success": n_stamp_ok,
            "stamp_failure": int(SAMPLE_N - n_stamp_ok),
        },
        "measurement_gates": {
            "source_recovered": n_recovered,
            "source_recovery_fraction": recovery_fraction,
            "finite_fwhm_and_elongation_fraction_among_recovered": finite_morph,
            "recenter_offset_px_median": rec_med,
            "recenter_offset_px_p95": rec_p95,
            "local_reference_ge3_fraction_among_recovered": ref_coverage,
            "transport_pass_64_of_64": transport_pass,
            "raw_morphology_pass": raw_pass,
            "local_psf_reference_pass": ref_pass,
        },
        "metric_summary": {},
        "sidecar": {
            "path": str(args.out_csv_gz),
            "rows": SAMPLE_N,
            "csv_sha256": csv_sha,
            "gzip_sha256": gz_sha,
        },
        "external_label_firewall": {
            "date_or_external_labels_available_to_runner": False,
            "external_label_reveal_authorized": False,
        },
        "interpretive_boundary": {
            "raw_pixel_morphology": "Pilot-grade if raw morphology gate passes.",
            "local_psf_reference": "Image-local and not Gaia-vetted; even a feasibility PASS does not make it final stellar PSF evidence.",
            "next_gate_if_pass": "Engineer a larger/full label-blind pixel-morphology sidecar, add Gaia-vetted local PSF references, then freeze a new morphology clustering before external-label reveal."
        }
    }
    for col in [
        "recenter_offset_px", "peak_snr", "moment_fwhm_px", "elongation",
        "core_concentration_r2_over_r6", "circularity", "convex_defect_fraction",
        "circle_deviation", "reference_count", "fwhm_ratio", "profile_diff"
    ]:
        vals = pd.to_numeric(out.get(col), errors="coerce")
        a = vals[np.isfinite(vals)].to_numpy(float)
        if len(a):
            result["metric_summary"][col] = {
                "n_finite": int(len(a)),
                "median": float(np.median(a)),
                "p05": float(np.quantile(a, 0.05)),
                "p95": float(np.quantile(a, 0.95)),
                "min": float(np.min(a)),
                "max": float(np.max(a)),
            }
        else:
            result["metric_summary"][col] = {"n_finite": 0}
    result["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_sha(result)}
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("[6/6] outcome", outcome, flush=True)
    print("SIDE_CAR_CSV_SHA256", csv_sha, flush=True)
    print("RESULT_CANONICAL_SHA256", result["integrity"]["canonical_payload_sha256_without_integrity"], flush=True)
    print("RECOVERED", n_recovered, "RECENTER_MEDIAN", rec_med, "RECENTER_P95", rec_p95, "REF_GE3_FRAC", ref_coverage, flush=True)


if __name__ == "__main__":
    main()
