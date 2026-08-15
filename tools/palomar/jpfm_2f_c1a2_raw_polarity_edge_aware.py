#!/usr/bin/env python3
"""JPFM-2F-C1A2: raw-positive, edge-aware corrective sparse-stamp morphology pilot."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from astropy.io import fits
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jpfm_2f_c1a_sparse_stamp_direct_morphology as c1a

IRSA_FMT = c1a.IRSA_FMT
STAMP_SIZE = 81
HALF = 40
FSSPEC_BLOCK_SIZE = 64 * 1024


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


def raw_background(raw: np.ndarray, cx: float, cy: float):
    yy, xx = np.indices(raw.shape, dtype=float)
    rr = np.hypot(xx - cx, yy - cy)
    outer = (rr >= 18.0) & (rr <= 38.0)
    vals = raw[outer]
    vals = vals[np.isfinite(vals)]
    if not len(vals):
        return float("nan"), float("nan"), outer
    med = float(np.median(vals))
    mad = float(np.median(np.abs(vals - med)))
    return med, 1.4826 * mad, outer


def measure_raw_stamp(raw: np.ndarray, cx: float, cy: float) -> dict:
    raw = raw.astype(float)
    bg, sigma, outer = raw_background(raw, cx, cy)
    yy, xx = np.indices(raw.shape, dtype=float)
    rr = np.hypot(xx - cx, yy - cy)
    signal = np.maximum(raw - bg, 0.0) if math.isfinite(bg) else np.full(raw.shape, np.nan)

    def flux(radius: float) -> float:
        vals = signal[rr <= radius]
        return float(np.nansum(vals)) if np.isfinite(vals).any() else float("nan")

    f2, f3, f5, f7, f10 = [flux(r) for r in (2.0, 3.0, 5.0, 7.0, 10.0)]
    if math.isfinite(bg) and math.isfinite(sigma) and sigma > 0:
        peak = float(np.nanmax(raw[rr <= 5.0]))
        raw_peak_snr = (peak - bg) / sigma
    else:
        raw_peak_snr = float("nan")

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

    lap = cv2.Laplacian(raw, cv2.CV_64F, ksize=3)
    outer_lap = lap[outer]
    outer_lap = outer_lap[np.isfinite(outer_lap)]
    if len(outer_lap):
        lap_med = float(np.median(outer_lap))
        lap_mad = float(np.median(np.abs(outer_lap - lap_med)))
    else:
        lap_mad = float("nan")
    if math.isfinite(bg) and math.isfinite(sigma) and sigma > 0:
        outer_vals = raw[outer]
        outlier_frac = float(np.mean(np.abs(outer_vals - bg) > 5.0 * sigma))
    else:
        outlier_frac = float("nan")

    out = {
        "stamp_raw_background_median": bg,
        "stamp_raw_background_robust_sigma": sigma,
        "stamp_raw_peak_snr": raw_peak_snr,
        "stamp_raw_flux_r5": f5,
        "stamp_raw_flux_r10": f10,
        "stamp_raw_concentration_r2_r5": f2 / f5 if f5 > 0 else float("nan"),
        "stamp_raw_concentration_r3_r7": f3 / f7 if f7 > 0 else float("nan"),
        "stamp_raw_moment_centroid_dx_px": centroid_dx,
        "stamp_raw_moment_centroid_dy_px": centroid_dy,
        "stamp_raw_moment_centroid_offset_px": math.hypot(centroid_dx, centroid_dy) if math.isfinite(centroid_dx) and math.isfinite(centroid_dy) else float("nan"),
        "stamp_raw_moment_fwhm_proxy_px": fwhm,
        "stamp_raw_moment_ellipticity": ellipticity,
        "stamp_raw_moment_orientation_deg": orientation,
        "stamp_outer_laplacian_mad": lap_mad,
        "stamp_outer_5mad_outlier_fraction": outlier_frac
    }
    out.update(c1a.direct_contour_metrics(raw, (cx, cy)))
    return out


def load_bound_gzip(path: Path, csv_sha: str, gz_sha: str) -> pd.DataFrame:
    gz = path.read_bytes()
    if sha256_bytes(gz) != gz_sha:
        raise RuntimeError(f"gzip binding mismatch: {path}")
    raw = gzip.decompress(gz)
    if sha256_bytes(raw) != csv_sha:
        raise RuntimeError(f"CSV binding mismatch: {path}")
    return pd.read_csv(io.BytesIO(raw))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--c0m-result", required=True, type=Path)
    ap.add_argument("--c0m-map", required=True, type=Path)
    ap.add_argument("--b3s-result", required=True, type=Path)
    ap.add_argument("--b3s-sidecar", required=True, type=Path)
    ap.add_argument("--c1a-result", required=True, type=Path)
    ap.add_argument("--c1a-sidecar", required=True, type=Path)
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-sidecar-gz", required=True, type=Path)
    args = ap.parse_args(); args.out_json.parent.mkdir(parents=True, exist_ok=True)

    print("[C1A2 1/8] bind immutable parents", flush=True)
    c0m = json.loads(args.c0m_result.read_text(encoding="utf-8"))
    b3s = json.loads(args.b3s_result.read_text(encoding="utf-8"))
    c1a_res = json.loads(args.c1a_result.read_text(encoding="utf-8"))
    if c0m.get("outcome") != "PASS_FULL_S0_HEADER_ONLY_ACQUISITION_MAP_FROZEN":
        raise RuntimeError("C1A2 blocked: C0M not PASS")
    if b3s.get("outcome") != "PASS_SHAPE_COMPATIBILITY_REPLAY__PIXEL_MORPHOLOGY_PILOT_ADMITTED":
        raise RuntimeError("C1A2 blocked: B3S not PASS")
    if c1a_res.get("outcome") != "FAIL_CLOSED_SPARSE_STAMP_TRANSPORT":
        raise RuntimeError("C1A2 corrective parent outcome mismatch")
    if any(x.get("external_label_firewall", {}).get("external_label_reveal_authorized") is not False for x in (c0m, b3s, c1a_res)):
        raise RuntimeError("parent firewall violation")

    amap = load_bound_gzip(args.c0m_map, c0m["manifest"]["csv_sha256"], c0m["manifest"]["gzip_sha256"])
    amap["src_id"] = amap.src_id.astype(str)
    bdf = load_bound_gzip(args.b3s_sidecar, b3s["sidecar"]["csv_sha256"], b3s["sidecar"]["gzip_sha256"])
    bdf["src_id"] = bdf.src_id.astype(str)
    old = load_bound_gzip(args.c1a_sidecar, c1a_res["sidecar"]["csv_sha256"], c1a_res["sidecar"]["gzip_sha256"])
    old["src_id"] = old.src_id.astype(str)

    print("[C1A2 2/8] reconstruct exact frozen same64", flush=True)
    sample = c1a.select_same64_from_map(amap)
    if len(sample) != 64 or sample.src_id.nunique() != 64 or set(sample.src_id) != set(bdf.src_id) or set(sample.src_id) != set(old.src_id):
        raise RuntimeError("same64 denominator mismatch")

    print("[C1A2 3/8] pre-pixel geometric eligibility from named plate headers", flush=True)
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
                pending = []
                for r in g.itertuples(index=False):
                    x, y = float(r.fullplate_x0), float(r.fullplate_y0)
                    ix, iy = int(np.rint(x)), int(np.rint(y))
                    x0, x1 = ix - HALF, ix + HALF + 1
                    y0, y1 = iy - HALF, iy + HALF + 1
                    rec = {
                        "src_id": str(r.src_id), "tile_id": str(r.tile_id), "object_id": int(r.object_id),
                        "plate_id": str(r.plate_id), "structural_cluster": int(r.structural_cluster),
                        "sample_role": str(r.sample_role), "anomaly_score": float(r.anomaly_score),
                        "frozen_fullplate_x0": x, "frozen_fullplate_y0": y,
                        "plate_naxis1": int(nx), "plate_naxis2": int(ny),
                        "slice_x0": x0, "slice_x1": x1, "slice_y0": y0, "slice_y1": y1
                    }
                    eligible = x0 >= 0 and y0 >= 0 and x1 <= nx and y1 <= ny
                    rec["prepixel_eligibility"] = "GEOMETRICALLY_ELIGIBLE_81PX" if eligible else "GEOMETRIC_EDGE_INELIGIBLE_81PX"
                    if not eligible:
                        rec["transport_status"] = "NOT_ATTEMPTED_GEOMETRIC_EDGE_INELIGIBLE"
                        rows.append(rec)
                    else:
                        pending.append((rec, x, y, x0, x1, y0, y1))
                for rec, x, y, x0, x1, y0, y1 in pending:
                    try:
                        raw = np.asarray(hdu.section[y0:y1, x0:x1], dtype=float)
                    except Exception as exc:
                        rec["transport_status"] = f"ELIGIBLE_STAMP_TRANSPORT_ERROR:{type(exc).__name__}"
                        rows.append(rec); continue
                    if raw.shape != (STAMP_SIZE, STAMP_SIZE):
                        rec["transport_status"] = f"ELIGIBLE_STAMP_SHAPE_{raw.shape}"
                        rows.append(rec); continue
                    cx, cy = x - x0, y - y0
                    rec.update({
                        "stamp_center_x": cx, "stamp_center_y": cy,
                        "transport_status": "EXACT_NAMED_PLATE_81PX_STAMP"
                    })
                    rec.update(measure_raw_stamp(raw, cx, cy))
                    rows.append(rec)
        except Exception as exc:
            for r in g.itertuples(index=False):
                rows.append({
                    "src_id": str(r.src_id), "tile_id": str(r.tile_id), "object_id": int(r.object_id),
                    "plate_id": str(r.plate_id), "structural_cluster": int(r.structural_cluster),
                    "sample_role": str(r.sample_role), "anomaly_score": float(r.anomaly_score),
                    "frozen_fullplate_x0": float(r.fullplate_x0), "frozen_fullplate_y0": float(r.fullplate_y0),
                    "prepixel_eligibility": "ELIGIBILITY_HEADER_ACCESS_FAILURE",
                    "transport_status": f"PLATE_OPEN_ERROR:{type(exc).__name__}"
                })
        if pi % 8 == 0 or pi == sample.plate_id.nunique():
            print(f"[C1A2 plate] {pi}/{sample.plate_id.nunique()}", flush=True)

    print("[C1A2 4/8] exact full-denominator integrity", flush=True)
    out = pd.DataFrame(rows); out["src_id"] = out.src_id.astype(str)
    if len(out) != 64 or out.src_id.nunique() != 64 or set(out.src_id) != set(sample.src_id):
        raise RuntimeError("C1A2 full 64-row denominator integrity failure")

    print("[C1A2 5/8] bind report-only upstream and failed-C1A crosschecks", flush=True)
    bkeep = [c for c in ["src_id", "pass2_fwhm_image", "pass2_elongation", "circularity", "shape_defect", "circle_deviation"] if c in bdf.columns]
    okeep = [c for c in ["src_id", "stamp_peak_snr", "stamp_moment_fwhm_proxy_px", "stamp_moment_ellipticity"] if c in old.columns]
    out = out.merge(bdf[bkeep], on="src_id", how="left", validate="one_to_one")
    out = out.merge(old[okeep], on="src_id", how="left", validate="one_to_one", suffixes=("", "_c1a"))
    out = out.sort_values(["structural_cluster", "sample_role", "src_id"], kind="stable").reset_index(drop=True)

    print("[C1A2 6/8] evaluate frozen corrective gates", flush=True)
    elig_state = out.prepixel_eligibility.astype(str)
    eligible = elig_state.eq("GEOMETRICALLY_ELIGIBLE_81PX")
    ineligible = elig_state.eq("GEOMETRIC_EDGE_INELIGIBLE_81PX")
    eligibility_deterministic = bool((eligible | ineligible).all())
    eligible_n = int(eligible.sum()); ineligible_n = int(ineligible.sum())
    transported = out.transport_status.astype(str).eq("EXACT_NAMED_PLATE_81PX_STAMP")
    eligible_transport_pass = eligible_n > 0 and int((eligible & transported).sum()) == eligible_n and int((~eligible & transported).sum()) == 0

    raw_snr = pd.to_numeric(out.get("stamp_raw_peak_snr"), errors="coerce")
    raw_signal_good = eligible & np.isfinite(raw_snr) & (raw_snr >= 5.0)
    raw_signal_frac = float(raw_signal_good.sum() / eligible_n) if eligible_n else 0.0
    raw_signal_pass = raw_signal_frac >= 0.95

    cent = pd.to_numeric(out.get("stamp_raw_moment_centroid_offset_px"), errors="coerce")
    cent_finite = eligible & np.isfinite(cent)
    cent_le4_frac = float((cent_finite & (cent <= 4.0)).sum() / eligible_n) if eligible_n else 0.0
    cent_primary = cent_le4_frac >= 0.95
    cent_tail = eligible_n > 0 and int((cent_finite & (cent <= 8.0)).sum()) == eligible_n
    centroid_pass = cent_primary and cent_tail

    mf = pd.to_numeric(out.get("stamp_raw_moment_fwhm_proxy_px"), errors="coerce")
    me = pd.to_numeric(out.get("stamp_raw_moment_ellipticity"), errors="coerce")
    moment_finite = eligible & np.isfinite(mf) & np.isfinite(me)
    moment_cov = float(moment_finite.sum() / eligible_n) if eligible_n else 0.0
    moment_pass = moment_cov >= 0.95

    circ = pd.to_numeric(out.get("stamp_circularity"), errors="coerce")
    cdev = pd.to_numeric(out.get("stamp_circle_deviation"), errors="coerce")
    contour_finite = eligible & np.isfinite(circ) & np.isfinite(cdev)
    contour_cov = float(contour_finite.sum() / eligible_n) if eligible_n else 0.0
    contour_pass = contour_cov >= 0.90

    bs = pd.to_numeric(out.get("stamp_raw_background_robust_sigma"), errors="coerce")
    lm = pd.to_numeric(out.get("stamp_outer_laplacian_mad"), errors="coerce")
    of = pd.to_numeric(out.get("stamp_outer_5mad_outlier_fraction"), errors="coerce")
    texture_finite = eligible & np.isfinite(bs) & np.isfinite(lm) & np.isfinite(of)
    texture_pass = eligible_n > 0 and int(texture_finite.sum()) == eligible_n

    if not eligibility_deterministic:
        outcome = "FAIL_CLOSED_DENOMINATOR_OR_ELIGIBILITY"
    elif not eligible_transport_pass:
        outcome = "FAIL_CLOSED_ELIGIBLE_SPARSE_TRANSPORT"
    elif not (raw_signal_pass and centroid_pass):
        outcome = "FAIL_CLOSED_RAW_CENTRAL_SIGNAL_OR_LOCALIZATION"
    elif not (moment_pass and contour_pass and texture_pass):
        outcome = "FAIL_CLOSED_RAW_DIRECT_MORPHOLOGY_COVERAGE"
    else:
        outcome = "PASS_RAW_POLARITY_EDGE_AWARE_DIRECT_MORPHOLOGY_PILOT"

    print("[C1A2 7/8] freeze corrective sidecar", flush=True)
    csv_bytes = out.to_csv(index=False, lineterminator="\n", float_format="%.12g").encode("utf-8")
    csv_sha = sha256_bytes(csv_bytes)
    with args.out_sidecar_gz.open("wb") as fout:
        with gzip.GzipFile(filename="", mode="wb", fileobj=fout, mtime=0) as z:
            z.write(csv_bytes)
    gz_sha = sha256_bytes(args.out_sidecar_gz.read_bytes())

    print("[C1A2 8/8] write result", flush=True)
    old_snr = pd.to_numeric(out.get("stamp_peak_snr"), errors="coerce")
    result = {
        "artifact_id": "JANUS-PALOMAR-JPFM-2F-C1A2-RAW-POLARITY-EDGE-AWARE-DIRECT-MORPHOLOGY-RUN-001",
        "experiment_id": "JPFM-2F-C1A2", "schema_version": "1.0",
        "date": pd.Timestamp.utcnow().date().isoformat(), "status": "EXECUTED", "outcome": outcome,
        "claim_ceiling": "CORRECTIVE_SPARSE_STAMP_MEASUREMENT_VALIDATION_ONLY__GEOMETRIC_EDGE_ROWS_RETAINED__DIRECT_FEATURES_NOT_PHYSICAL_CLASSES__EXTERNAL_LABELS_SEALED__NO_ORIGIN_CLAIM",
        "bindings": {
            "admission_path": "data/JANUS-PALOMAR-JPFM-2F-C1A2-RAW-POLARITY-EDGE-AWARE-DIRECT-MORPHOLOGY-ADMISSION-v1.0.json",
            "corrective_audit_path": "data/JANUS-PALOMAR-JPFM-2F-C1A-CORRECTIVE-AUDIT-v1.0.json",
            "C0M_result_canonical_sha256": c0m["integrity"]["canonical_payload_sha256_without_integrity"],
            "C0M_manifest_csv_sha256": c0m["manifest"]["csv_sha256"],
            "B3S_result_canonical_sha256": b3s["integrity"]["canonical_payload_sha256_without_integrity"],
            "C1A_result_canonical_sha256": c1a_res["integrity"]["canonical_payload_sha256_without_integrity"],
            "C1A_sidecar_csv_sha256": c1a_res["sidecar"]["csv_sha256"]
        },
        "denominator_and_eligibility": {
            "full_rows": 64, "full_src_ids_unique": int(out.src_id.nunique()),
            "eligibility_deterministic": bool(eligibility_deterministic),
            "geometrically_eligible_81px": eligible_n,
            "geometric_edge_ineligible_81px": ineligible_n,
            "edge_ineligible_src_ids": sorted(out.loc[ineligible, "src_id"].astype(str).tolist())
        },
        "transport": {
            "eligible_exact_named_plate_81px_stamps": int((eligible & transported).sum()),
            "eligible_denominator": eligible_n, "gate_pass": bool(eligible_transport_pass),
            "full_remote_plate_array_accessed": False, "nearest_source_search_used": False,
            "peak_recentering_used": False, "plate_substitution_used": False
        },
        "gates": {
            "central_raw_signal": {"pass": bool(raw_signal_pass), "raw_snr_ge5_fraction_of_eligible": raw_signal_frac, "stamp_raw_peak_snr_eligible": qstats(raw_snr[eligible])},
            "diagnostic_raw_centroid": {"pass": bool(centroid_pass), "le4_fraction_of_eligible": cent_le4_frac, "all_eligible_le8": bool(cent_tail), "offset_px_eligible": qstats(cent[eligible])},
            "raw_moment_feature_coverage": {"pass": bool(moment_pass), "finite_fraction_of_eligible": moment_cov},
            "contour_feature_coverage": {"pass": bool(contour_pass), "finite_circularity_and_circle_deviation_fraction_of_eligible": contour_cov, "finite_shape_defect_eligible": int((eligible & np.isfinite(pd.to_numeric(out.get('stamp_shape_defect'), errors='coerce'))).sum())},
            "outer_texture_coverage": {"pass": bool(texture_pass), "finite_rows_of_eligible": int(texture_finite.sum())}
        },
        "raw_direct_feature_summary_eligible": {
            "stamp_raw_moment_fwhm_proxy_px": qstats(mf[eligible]),
            "stamp_raw_moment_ellipticity": qstats(me[eligible]),
            "stamp_raw_concentration_r2_r5": qstats(pd.to_numeric(out.get('stamp_raw_concentration_r2_r5'), errors='coerce')[eligible]),
            "stamp_raw_concentration_r3_r7": qstats(pd.to_numeric(out.get('stamp_raw_concentration_r3_r7'), errors='coerce')[eligible]),
            "stamp_circularity": qstats(circ[eligible]), "stamp_circle_deviation": qstats(cdev[eligible]),
            "stamp_outer_laplacian_mad": qstats(lm[eligible]), "stamp_outer_5mad_outlier_fraction": qstats(of[eligible])
        },
        "report_only_crosschecks": {
            "raw_moment_fwhm_proxy_vs_pass2_FWHM_IMAGE_spearman": finite_spearman(mf[eligible], pd.to_numeric(out.loc[eligible, 'pass2_fwhm_image'], errors='coerce')),
            "raw_moment_ellipticity_vs_pass2_ELONGATION_spearman": finite_spearman(me[eligible], pd.to_numeric(out.loc[eligible, 'pass2_elongation'], errors='coerce')),
            "raw_peak_snr_minus_failed_C1A_inverted_peak_snr": qstats((raw_snr - old_snr)[eligible]),
            "stamp_circularity_minus_B3S": qstats((circ - pd.to_numeric(out.get('circularity'), errors='coerce'))[eligible]),
            "stamp_circle_deviation_minus_B3S": qstats((cdev - pd.to_numeric(out.get('circle_deviation'), errors='coerce'))[eligible]),
            "rule": "REPORT_ONLY__NOT_A_PASS_FAIL_GATE__NO_RETUNING"
        },
        "external_label_firewall": {"external_label_reveal_authorized": False, "date_or_external_environment_used": False},
        "sidecar": {"path": str(args.out_sidecar_gz), "rows": int(len(out)), "csv_sha256": csv_sha, "gzip_sha256": gz_sha},
        "next_gate": "JPFM_2F_C1B_LARGE_BLIND_SPARSE_STAMP_MORPHOLOGY_RELEASE" if outcome == "PASS_RAW_POLARITY_EDGE_AWARE_DIRECT_MORPHOLOGY_PILOT" else "CORRECTIVE_DIRECT_STAMP_PATH_NOT_ADMITTED"
    }
    result["integrity"] = {"canonical_payload_sha256_without_integrity": canonical_sha(result)}
    args.out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("OUTCOME", outcome, flush=True)
    print("ELIGIBLE", eligible_n, "EDGE_INELIGIBLE", ineligible_n, "TRANSPORTED_ELIGIBLE", int((eligible & transported).sum()), flush=True)
    print("RAW_SNR_GE5_FRAC", raw_signal_frac, "CENTROID_LE4_FRAC", cent_le4_frac, "MOMENT_COV", moment_cov, "CONTOUR_COV", contour_cov, flush=True)
    print("SIDECAR_CSV_SHA256", csv_sha, flush=True)
    print("RESULT_CANONICAL_SHA256", result["integrity"]["canonical_payload_sha256_without_integrity"], flush=True)


if __name__ == "__main__":
    main()
