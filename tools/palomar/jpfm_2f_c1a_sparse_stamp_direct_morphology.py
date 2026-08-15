#!/usr/bin/env python3
"""JPFM-2F-C1A: exact named-plate sparse-stamp direct morphology on frozen same-64.

This runner is conditional on admitted C0M. Acquisition centers are frozen before pixels
are read. Diagnostic centroids never alter stamp centers or non-moment feature apertures.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from astropy.io import fits
from astropy.nddata import Cutout2D
from scipy.stats import spearmanr

POSS_COMMIT = "4005e200541b321ead3d6608f0162a14430ef1c2"
IRSA_FMT = "https://irsa.ipac.caltech.edu/data/DSS/images/dss1red/dss1red_{plate}.fits"
STAMP_SIZE = 81
HALF = 40
FSSPEC_BLOCK_SIZE = 64 * 1024
INVERT_MAX = 65535.0


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
        "n_finite": int(len(a)), "min": float(np.min(a)),
        "p05": float(np.quantile(a, .05)), "median": float(np.median(a)),
        "p95": float(np.quantile(a, .95)), "max": float(np.max(a))
    }


def finite_spearman(x, y) -> dict:
    x = pd.to_numeric(pd.Series(x), errors="coerce").to_numpy(float)
    y = pd.to_numeric(pd.Series(y), errors="coerce").to_numpy(float)
    m = np.isfinite(x) & np.isfinite(y)
    if int(m.sum()) < 3:
        return {"n": int(m.sum()), "rho": None, "pvalue": None}
    res = spearmanr(x[m], y[m])
    return {"n": int(m.sum()), "rho": float(res.statistic), "pvalue": float(res.pvalue)}


def robust_background(inv: np.ndarray, cx: float, cy: float):
    yy, xx = np.indices(inv.shape, dtype=float)
    rr = np.hypot(xx - cx, yy - cy)
    outer = (rr >= 18.0) & (rr <= 38.0)
    vals = inv[outer]
    vals = vals[np.isfinite(vals)]
    if not len(vals):
        return float("nan"), float("nan"), outer
    med = float(np.median(vals))
    mad = float(np.median(np.abs(vals - med)))
    sigma = 1.4826 * mad
    return med, sigma, outer


def direct_contour_metrics(raw: np.ndarray, center_xy):
    out = {
        "stamp_circularity": float("nan"),
        "stamp_contour_area": float("nan"),
        "stamp_shape_defect": float("nan"),
        "stamp_circle_deviation": float("nan")
    }
    try:
        cut = Cutout2D(raw, position=center_xy, size=21).data.astype(float)
    except Exception:
        return out
    image_uint8 = np.empty(cut.shape, dtype=np.uint8)
    cv2.normalize(cut, image_uint8, 0, 255, cv2.NORM_MINMAX, cv2.CV_8U)
    circularity = area = shape_defect = circle_deviation = float("nan")
    for t in (21, 45):
        _, thresh = cv2.threshold(image_uint8, t, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            ar = cv2.contourArea(contour)
            perimeter = cv2.arcLength(contour, True)
            if ar <= 7.0 or perimeter <= 0.0:
                continue
            circularity = (4.0 * math.pi * ar) / (perimeter ** 2)
            area = ar
            epsilon = 0.01 * perimeter
            approx = cv2.approxPolyDP(contour, epsilon, True)
            if len(approx) >= 4:
                try:
                    hull = cv2.convexHull(approx, returnPoints=False)
                    defects = cv2.convexityDefects(approx, hull)
                    if defects is not None:
                        d = np.asarray(defects)
                        if d.ndim >= 1 and d.shape[-1] == 4:
                            rows = d.reshape(-1, 4)
                            sum_depth = float(np.sum(rows[:, 3].astype(float) / 256.0))
                            _x, _y, w, h = cv2.boundingRect(approx)
                            denom = max(w, h)
                            if denom > 0:
                                shape_defect = sum_depth / denom
                except (cv2.error, ValueError, IndexError):
                    pass
            try:
                (xc, yc), radius = cv2.minEnclosingCircle(contour)
                if radius > 0:
                    dist = [math.hypot(float(pt[0][0]) - xc, float(pt[0][1]) - yc) / radius for pt in contour]
                    if dist:
                        circle_deviation = float(np.std(dist))
            except Exception:
                pass
    out.update({
        "stamp_circularity": circularity,
        "stamp_contour_area": area,
        "stamp_shape_defect": shape_defect,
        "stamp_circle_deviation": circle_deviation
    })
    return out


def measure_stamp(raw: np.ndarray, cx: float, cy: float) -> dict:
    inv = INVERT_MAX - raw.astype(float)
    bg, sigma, outer = robust_background(inv, cx, cy)
    yy, xx = np.indices(inv.shape, dtype=float)
    rr = np.hypot(xx - cx, yy - cy)
    signal = np.maximum(inv - bg, 0.0) if math.isfinite(bg) else np.full(inv.shape, np.nan)

    def flux(radius: float) -> float:
        m = rr <= radius
        vals = signal[m]
        return float(np.nansum(vals)) if np.isfinite(vals).any() else float("nan")

    f2, f3, f5, f7, f10 = [flux(r) for r in (2.0, 3.0, 5.0, 7.0, 10.0)]
    if math.isfinite(bg) and math.isfinite(sigma) and sigma > 0:
        central_peak = float(np.nanmax(inv[rr <= 5.0]))
        peak_snr = (central_peak - bg) / sigma
    else:
        peak_snr = float("nan")

    moment_mask = rr <= 10.0
    w = signal[moment_mask]
    mx = xx[moment_mask]; my = yy[moment_mask]
    centroid_dx = centroid_dy = fwhm = ellipticity = orientation = float("nan")
    wsum = float(np.nansum(w)) if np.isfinite(w).any() else 0.0
    if wsum > 0 and np.isfinite(w).all():
        xc = float(np.sum(w * mx) / wsum)
        yc = float(np.sum(w * my) / wsum)
        centroid_dx, centroid_dy = xc - cx, yc - cy
        dx, dy = mx - xc, my - yc
        cov = np.array([
            [float(np.sum(w * dx * dx) / wsum), float(np.sum(w * dx * dy) / wsum)],
            [float(np.sum(w * dx * dy) / wsum), float(np.sum(w * dy * dy) / wsum)]
        ])
        vals, vecs = np.linalg.eigh(cov)
        vals = np.maximum(vals, 0.0)
        minor, major = float(vals[0]), float(vals[1])
        fwhm = 2.354820045 * math.sqrt((major + minor) / 2.0)
        if major > 0:
            ellipticity = 1.0 - math.sqrt(max(0.0, min(1.0, minor / major)))
            v = vecs[:, 1]
            orientation = math.degrees(math.atan2(float(v[1]), float(v[0]))) % 180.0

    lap = cv2.Laplacian(inv, cv2.CV_64F, ksize=3)
    outer_lap = lap[outer]
    outer_lap = outer_lap[np.isfinite(outer_lap)]
    if len(outer_lap):
        lap_med = float(np.median(outer_lap))
        lap_mad = float(np.median(np.abs(outer_lap - lap_med)))
    else:
        lap_mad = float("nan")
    if math.isfinite(bg) and math.isfinite(sigma) and sigma > 0:
        outer_vals = inv[outer]
        outlier_frac = float(np.mean(np.abs(outer_vals - bg) > 5.0 * sigma))
    else:
        outlier_frac = float("nan")

    out = {
        "stamp_background_median": bg,
        "stamp_background_robust_sigma": sigma,
        "stamp_peak_snr": peak_snr,
        "stamp_flux_r5": f5,
        "stamp_flux_r10": f10,
        "stamp_concentration_r2_r5": f2 / f5 if f5 > 0 else float("nan"),
        "stamp_concentration_r3_r7": f3 / f7 if f7 > 0 else float("nan"),
        "stamp_moment_centroid_dx_px": centroid_dx,
        "stamp_moment_centroid_dy_px": centroid_dy,
        "stamp_moment_centroid_offset_px": math.hypot(centroid_dx, centroid_dy) if math.isfinite(centroid_dx) and math.isfinite(centroid_dy) else float("nan"),
        "stamp_moment_fwhm_proxy_px": fwhm,
        "stamp_moment_ellipticity": ellipticity,
        "stamp_moment_orientation_deg": orientation,
        "stamp_outer_laplacian_mad": lap_mad,
        "stamp_outer_5mad_outlier_fraction": outlier_frac
    }
    out.update(direct_contour_metrics(raw, (cx, cy)))
    return out


def select_same64_from_map(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in range(16):
        g = df[pd.to_numeric(df.structural_cluster, errors="coerce") == c].copy()
        g["src_id"] = g.src_id.astype(str)
        med = float(pd.to_numeric(g.anomaly_score, errors="coerce").median())
        g["_meddist"] = (pd.to_numeric(g.anomaly_score, errors="coerce") - med).abs()
        typical = g.sort_values(["_meddist", "src_id"], kind="stable").head(2)
        used = set(typical.src_id)
        unusual = g[~g.src_id.isin(used)].sort_values(["anomaly_score", "src_id"], ascending=[False, True], kind="stable").head(2)
        t = typical.copy(); t["sample_role"] = "typical"
        u = unusual.copy(); u["sample_role"] = "unusual"
        rows.extend([t, u])
    out = pd.concat(rows, ignore_index=True)
    if len(out) != 64 or out.src_id.astype(str).nunique() != 64:
        raise RuntimeError("C1A same64 reconstruction failed")
    return out.sort_values(["structural_cluster", "sample_role", "src_id"], kind="stable").reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--c0m-result", required=True, type=Path)
    ap.add_argument("--c0m-map", required=True, type=Path)
    ap.add_argument("--b3s-result", required=True, type=Path)
    ap.add_argument("--b3s-sidecar", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-sidecar-gz", required=True, type=Path)
    args = ap.parse_args(); args.out_json.parent.mkdir(parents=True, exist_ok=True)

    print("[C1A 1/7] bind admitted C0M and B3S parents", flush=True)
    c0m = json.loads(args.c0m_result.read_text(encoding="utf-8"))
    if c0m.get("outcome") != "PASS_FULL_S0_HEADER_ONLY_ACQUISITION_MAP_FROZEN":
        raise RuntimeError("C1A blocked: C0M parent not admitted PASS")
    if c0m["external_label_firewall"]["external_label_reveal_authorized"] is not False:
        raise RuntimeError("C1A blocked: C0M firewall open")
    map_gz = args.c0m_map.read_bytes(); map_raw = gzip.decompress(map_gz)
    if sha256_bytes(map_gz) != c0m["manifest"]["gzip_sha256"] or sha256_bytes(map_raw) != c0m["manifest"]["csv_sha256"]:
        raise RuntimeError("C1A C0M map hash mismatch")
    amap = pd.read_csv(io.BytesIO(map_raw)); amap["src_id"] = amap.src_id.astype(str)
    if len(amap) != 122820 or amap.src_id.nunique() != 122820:
        raise RuntimeError("C1A C0M full map invariant failed")

    b3s = json.loads(args.b3s_result.read_text(encoding="utf-8"))
    if b3s.get("outcome") != "PASS_SHAPE_COMPATIBILITY_REPLAY__PIXEL_MORPHOLOGY_PILOT_ADMITTED":
        raise RuntimeError("C1A B3S parent not admitted PASS")
    bgz = args.b3s_sidecar.read_bytes(); braw = gzip.decompress(bgz)
    if sha256_bytes(bgz) != b3s["sidecar"]["gzip_sha256"] or sha256_bytes(braw) != b3s["sidecar"]["csv_sha256"]:
        raise RuntimeError("C1A B3S sidecar hash mismatch")
    bdf = pd.read_csv(io.BytesIO(braw)); bdf["src_id"] = bdf.src_id.astype(str)

    print("[C1A 2/7] reconstruct exact pre-morphology same64", flush=True)
    sample = select_same64_from_map(amap)
    if set(sample.src_id) != set(bdf.src_id):
        raise RuntimeError("C1A reconstructed same64 differs from B3S frozen sample")

    print("[C1A 3/7] exact named-plate 81x81 sparse transport", flush=True)
    rows = []
    for pi, (plate, g) in enumerate(sample.groupby("plate_id", sort=True), 1):
        url = IRSA_FMT.format(plate=str(plate))
        try:
            with fits.open(
                url, use_fsspec=True, lazy_load_hdus=True,
                fsspec_kwargs={"block_size": FSSPEC_BLOCK_SIZE, "cache_type": "readahead"}
            ) as hdul:
                hdu = hdul[0]
                ny, nx = hdu.shape
                for r in g.itertuples(index=False):
                    x, y = float(r.fullplate_x0), float(r.fullplate_y0)
                    ix, iy = int(np.rint(x)), int(np.rint(y))
                    x0, x1 = ix - HALF, ix + HALF + 1
                    y0, y1 = iy - HALF, iy + HALF + 1
                    base = {
                        "src_id": str(r.src_id), "tile_id": str(r.tile_id), "object_id": int(r.object_id),
                        "plate_id": str(r.plate_id), "structural_cluster": int(r.structural_cluster),
                        "sample_role": str(r.sample_role), "anomaly_score": float(r.anomaly_score),
                        "frozen_fullplate_x0": x, "frozen_fullplate_y0": y,
                        "slice_x0": x0, "slice_y0": y0
                    }
                    if x0 < 0 or y0 < 0 or x1 > nx or y1 > ny:
                        base["transport_status"] = "STAMP_EDGE_OR_TRANSPORT_FAILURE"
                        rows.append(base); continue
                    try:
                        raw = np.asarray(hdu.section[y0:y1, x0:x1], dtype=float)
                    except Exception as exc:
                        base["transport_status"] = f"STAMP_TRANSPORT_ERROR:{type(exc).__name__}"
                        rows.append(base); continue
                    if raw.shape != (STAMP_SIZE, STAMP_SIZE):
                        base["transport_status"] = f"STAMP_SHAPE_{raw.shape}"
                        rows.append(base); continue
                    cx, cy = x - x0, y - y0
                    base.update({
                        "stamp_center_x": cx, "stamp_center_y": cy,
                        "stamp_center_rounding_dx": x - ix, "stamp_center_rounding_dy": y - iy,
                        "transport_status": "EXACT_NAMED_PLATE_81PX_STAMP"
                    })
                    base.update(measure_stamp(raw, cx, cy))
                    rows.append(base)
        except Exception as exc:
            for r in g.itertuples(index=False):
                rows.append({
                    "src_id": str(r.src_id), "tile_id": str(r.tile_id), "object_id": int(r.object_id),
                    "plate_id": str(r.plate_id), "structural_cluster": int(r.structural_cluster),
                    "sample_role": str(r.sample_role), "anomaly_score": float(r.anomaly_score),
                    "frozen_fullplate_x0": float(r.fullplate_x0), "frozen_fullplate_y0": float(r.fullplate_y0),
                    "transport_status": f"PLATE_OPEN_ERROR:{type(exc).__name__}"
                })
        if pi % 8 == 0 or pi == sample.plate_id.nunique():
            print(f"[C1A transport] plates {pi}/{sample.plate_id.nunique()}", flush=True)

    print("[C1A 4/7] bind report-only B3S crosschecks", flush=True)
    out = pd.DataFrame(rows); out["src_id"] = out.src_id.astype(str)
    bkeep = [c for c in [
        "src_id", "pass2_fwhm_image", "pass2_elongation", "profile_diff",
        "circularity", "shape_defect", "circle_deviation"
    ] if c in bdf.columns]
    out = out.merge(bdf[bkeep], on="src_id", how="left", validate="one_to_one", suffixes=("", "_b3s"))
    out = out.sort_values(["structural_cluster", "sample_role", "src_id"], kind="stable").reset_index(drop=True)

    print("[C1A 5/7] evaluate frozen measurement gates", flush=True)
    transport = out.transport_status.eq("EXACT_NAMED_PLATE_81PX_STAMP")
    transport_pass = int(transport.sum()) == 64
    peak = pd.to_numeric(out.get("stamp_peak_snr"), errors="coerce")
    central_good = np.isfinite(peak) & (peak >= 5.0)
    central_signal_pass = float(central_good.mean()) >= 0.95
    cent = pd.to_numeric(out.get("stamp_moment_centroid_offset_px"), errors="coerce")
    cent_finite = np.isfinite(cent)
    cent_primary = float((cent_finite & (cent <= 4.0)).mean()) >= 0.95
    cent_tail = bool(cent_finite.all()) and bool((cent <= 8.0).all())
    localization_pass = cent_primary and cent_tail
    mf = pd.to_numeric(out.get("stamp_moment_fwhm_proxy_px"), errors="coerce")
    me = pd.to_numeric(out.get("stamp_moment_ellipticity"), errors="coerce")
    moment_cov = float((np.isfinite(mf) & np.isfinite(me)).mean())
    moment_pass = moment_cov >= 0.95
    circ = pd.to_numeric(out.get("stamp_circularity"), errors="coerce")
    cdev = pd.to_numeric(out.get("stamp_circle_deviation"), errors="coerce")
    contour_cov = float((np.isfinite(circ) & np.isfinite(cdev)).mean())
    contour_pass = contour_cov >= 0.90
    bs = pd.to_numeric(out.get("stamp_background_robust_sigma"), errors="coerce")
    lm = pd.to_numeric(out.get("stamp_outer_laplacian_mad"), errors="coerce")
    of = pd.to_numeric(out.get("stamp_outer_5mad_outlier_fraction"), errors="coerce")
    texture_pass = bool((np.isfinite(bs) & np.isfinite(lm) & np.isfinite(of)).all())

    if not transport_pass:
        outcome = "FAIL_CLOSED_SPARSE_STAMP_TRANSPORT"
    elif not (central_signal_pass and localization_pass):
        outcome = "FAIL_CLOSED_CENTRAL_SIGNAL_OR_LOCALIZATION"
    elif not (moment_pass and contour_pass and texture_pass):
        outcome = "FAIL_CLOSED_DIRECT_MORPHOLOGY_COVERAGE"
    else:
        outcome = "PASS_NAMED_PLATE_SPARSE_STAMP_DIRECT_MORPHOLOGY_PILOT"

    print("[C1A 6/7] freeze direct-morphology sidecar", flush=True)
    csv_bytes = out.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    csv_sha = sha256_bytes(csv_bytes)
    with args.out_sidecar_gz.open("wb") as fout:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fout, mtime=0) as z:
            z.write(csv_bytes)
    gz_sha = sha256_bytes(args.out_sidecar_gz.read_bytes())

    print("[C1A 7/7] write result", flush=True)
    centroid_offset = pd.to_numeric(out.get("stamp_moment_centroid_offset_px"), errors="coerce")
    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-2F-C1A-NAMED-PLATE-SPARSE-STAMP-DIRECT-MORPHOLOGY-RUN-001",
        "experiment_id": "JPFM-2F-C1A", "schema_version": "1.0",
        "date": pd.Timestamp.utcnow().date().isoformat(), "status": "EXECUTED", "outcome": outcome,
        "claim_ceiling": "SPARSE_NAMED_PLATE_TRANSPORT_AND_DIRECT_MORPHOLOGY_MEASUREMENT_VALIDATION_ONLY__NEW_STAMP_FEATURES_NOT_CALIBRATED_AS_PHYSICAL_CLASSES__EXTERNAL_LABELS_SEALED__NO_ORIGIN_CLAIM",
        "bindings": {
            "admission_path": "data/JANUS-PALOMAR-JPFM-2F-C1A-NAMED-PLATE-SPARSE-STAMP-DIRECT-MORPHOLOGY-ADMISSION-v1.0.json",
            "C0M_result_path": str(args.c0m_result), "C0M_result_file_sha256": sha256_bytes(args.c0m_result.read_bytes()),
            "C0M_manifest_csv_sha256": c0m["manifest"]["csv_sha256"], "C0M_manifest_gzip_sha256": c0m["manifest"]["gzip_sha256"],
            "B3S_result_path": str(args.b3s_result), "B3S_result_canonical_sha256": b3s["integrity"]["canonical_payload_sha256_without_integrity"],
            "B3S_sidecar_csv_sha256": b3s["sidecar"]["csv_sha256"], "poss_commit": POSS_COMMIT
        },
        "sample": {"rows": 64, "distinct_plates": int(sample.plate_id.nunique()), "same_as_B1_B2_B3_B3S_C0_C0H": True},
        "transport": {
            "exact_81px_named_plate_stamps": int(transport.sum()), "gate_pass": bool(transport_pass),
            "stamp_size_px": STAMP_SIZE, "full_remote_plate_array_accessed": False,
            "nearest_source_search_used": False, "peak_recentering_used": False, "plate_substitution_used": False
        },
        "gates": {
            "central_signal": {"pass": bool(central_signal_pass), "finite_snr_ge5_fraction": float(central_good.mean()), "stamp_peak_snr": qstats(peak)},
            "diagnostic_centroid": {"pass": bool(localization_pass), "le4_fraction": float((cent_finite & (cent <= 4.0)).mean()), "all_le8": bool(cent_tail), "offset_px": qstats(centroid_offset)},
            "moment_feature_coverage": {"pass": bool(moment_pass), "finite_fraction": moment_cov},
            "contour_feature_coverage": {"pass": bool(contour_pass), "finite_circularity_and_circle_deviation_fraction": contour_cov, "finite_shape_defect": int(np.isfinite(pd.to_numeric(out.get('stamp_shape_defect'), errors='coerce')).sum())},
            "outer_texture_coverage": {"pass": bool(texture_pass), "finite_rows": int((np.isfinite(bs) & np.isfinite(lm) & np.isfinite(of)).sum())}
        },
        "direct_feature_summary": {
            "stamp_moment_fwhm_proxy_px": qstats(mf), "stamp_moment_ellipticity": qstats(me),
            "stamp_concentration_r2_r5": qstats(out.get("stamp_concentration_r2_r5")),
            "stamp_concentration_r3_r7": qstats(out.get("stamp_concentration_r3_r7")),
            "stamp_circularity": qstats(circ), "stamp_shape_defect": qstats(out.get("stamp_shape_defect")),
            "stamp_circle_deviation": qstats(cdev), "stamp_outer_laplacian_mad": qstats(lm),
            "stamp_outer_5mad_outlier_fraction": qstats(of)
        },
        "report_only_B3S_crosschecks": {
            "moment_fwhm_proxy_vs_pass2_FWHM_IMAGE_spearman": finite_spearman(mf, out.get("pass2_fwhm_image")),
            "moment_ellipticity_vs_pass2_ELONGATION_spearman": finite_spearman(me, out.get("pass2_elongation")),
            "stamp_circularity_minus_B3S_circularity": qstats(circ - pd.to_numeric(out.get("circularity"), errors="coerce")),
            "stamp_circle_deviation_minus_B3S": qstats(cdev - pd.to_numeric(out.get("circle_deviation"), errors="coerce")),
            "rule": "REPORT_ONLY__NOT_A_PASS_FAIL_GATE__NO_RETUNING"
        },
        "explicit_non_equivalences": {
            "stamp_moment_fwhm_proxy_px": "NOT_SEXTRACTOR_FWHM_IMAGE",
            "stamp_moment_ellipticity": "NOT_SEXTRACTOR_ELLIPTICITY_OR_ELONGATION",
            "profile_diff": "NOT_MEASURED_BY_DIRECT_81PX_STAMP_PATH"
        },
        "external_label_firewall": {"external_label_reveal_authorized": False, "date_or_external_environment_used": False},
        "sidecar": {"path": str(args.out_sidecar_gz), "rows": int(len(out)), "csv_sha256": csv_sha, "gzip_sha256": gz_sha},
        "next_gate": "JPFM_2F_C1B_LARGE_BLIND_SPARSE_STAMP_MORPHOLOGY_RELEASE" if outcome == "PASS_NAMED_PLATE_SPARSE_STAMP_DIRECT_MORPHOLOGY_PILOT" else "DIRECT_STAMP_MEASUREMENT_PATH_NOT_ADMITTED"
    }
    result["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_sha(result)}
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("OUTCOME", outcome, flush=True)
    print("TRANSPORT", int(transport.sum()), "PEAK_GE5_FRAC", float(central_good.mean()), "MOMENT_COV", moment_cov, "CONTOUR_COV", contour_cov, flush=True)
    print("SIDECAR_CSV_SHA256", csv_sha, flush=True)
    print("RESULT_CANONICAL_SHA256", result["integrity"]["canonical_payload_sha256_without_integrity"], flush=True)


if __name__ == "__main__":
    main()
