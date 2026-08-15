#!/usr/bin/env python3
"""JANUS Wedjat v0.4 — Eye-first internal mapping and spiral-position pilot.

Two deliberately separated lanes:

A. MODERN GLYPH MAPPING PERMUTATION CONTROL
   Render Unicode/Gardiner D011..D016 with one external Egyptian-hieroglyph font.
   Ask whether the conventional value assignment 1/2..1/64 is recoverable from
   simple geometry (ink area, bounding-box diagonal, skeleton length).  All 6!=720
   assignments are enumerated.  This is a modern-font control, not ancient paleography.

B. MUSEUM-IMAGE SPIRAL-POSITION CANARY
   On supplied local museum-image bytes, segment the object from its border background,
   detect a loop-like structure in a preregistered lower-left ROI, and record its
   normalized vertical position.  This is an exploratory canary only unless exact
   source-byte provenance and the full museum protocol gates are satisfied.

No result from this script establishes ancient binary, Python, sensory coding, or a
historical CSM->Wedjat derivation.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import platform
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.stats import spearmanr
from skimage.morphology import skeletonize

TARGETS = [0x13081, 0x13082, 0x13083, 0x13084, 0x13085, 0x13086]
VALUES = np.array([1/2, 1/4, 1/8, 1/16, 1/32, 1/64], dtype=float)

OBJECT_METADATA = {
    "555588": {"period": "Late Old Kingdom-Early Middle Kingdom", "date": "ca. 2150-1950 BCE", "mid_bce": 2050.0, "role": "frozen_corpus_early"},
    "551474": {"period": "New Kingdom", "date": "ca. 1386-1347 BCE", "mid_bce": 1366.5, "role": "external_calibration_canary"},
    "566845": {"period": "Third Intermediate Period or later", "date": "ca. 1080-664 BCE", "mid_bce": 872.0, "role": "frozen_corpus"},
    "558320": {"period": "Late Period", "date": "664-525 BCE", "mid_bce": 594.5, "role": "frozen_corpus"},
    "547767": {"period": "Ptolemaic Period", "date": "332-30 BCE", "mid_bce": 181.0, "role": "frozen_corpus"},
}

OFFICIAL_URLS = {
    "555588": "https://www.metmuseum.org/art/collection/search/555588",
    "551474": "https://www.metmuseum.org/art/collection/search/551474",
    "566845": "https://www.metmuseum.org/art/collection/search/566845",
    "558320": "https://www.metmuseum.org/art/collection/search/558320",
    "547767": "https://www.metmuseum.org/art/collection/search/547767",
}

KNOWN_MAIN_IMAGE_URLS = {
    "555588": "https://collectionapi.metmuseum.org/api/collection/v1/iiif/555588/2232938/main-image",
    "551474": "https://collectionapi.metmuseum.org/api/collection/v1/iiif/551474/1180492/main-image",
    "566845": "https://collectionapi.metmuseum.org/api/collection/v1/iiif/566845/1504865/main-image",
    "558320": "https://collectionapi.metmuseum.org/api/collection/v1/iiif/558320/1370485/main-image",
    "547767": "https://collectionapi.metmuseum.org/api/collection/v1/iiif/547767/1084242/main-image",
}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def render_glyph(cp: int, font: ImageFont.FreeTypeFont, canvas: int = 360) -> np.ndarray:
    im = Image.new("L", (canvas, canvas), 255)
    d = ImageDraw.Draw(im)
    ch = chr(cp)
    box = d.textbbox((0, 0), ch, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((canvas - w)//2 - box[0], (canvas - h)//2 - box[1]), ch, font=font, fill=0)
    return (np.array(im) < 128).astype(np.uint8)


def glyph_metrics(mask: np.ndarray) -> dict[str, float]:
    ys, xs = np.where(mask > 0)
    w = xs.max() - xs.min() + 1
    h = ys.max() - ys.min() + 1
    sk = skeletonize(mask > 0)
    return {
        "ink_area": float(mask.sum()),
        "bbox_diagonal": float(math.hypot(w, h)),
        "skeleton_length": float(sk.sum()),
    }


def proportional_log2_error(metric_values: np.ndarray, assigned_values: np.ndarray) -> float:
    """Fit metric ~= C*assigned_value and return mean squared residual in log2 space."""
    ly = np.log2(metric_values)
    lx = np.log2(assigned_values)
    intercept = float(np.mean(ly - lx))
    return float(np.mean((ly - (intercept + lx))**2))


def mapping_permutation_control(font_path: str, font_size: int) -> dict:
    font = ImageFont.truetype(font_path, font_size)
    metrics_by_name: dict[str, list[float]] = {"ink_area": [], "bbox_diagonal": [], "skeleton_length": []}
    per_glyph = []
    for cp in TARGETS:
        m = render_glyph(cp, font)
        gm = glyph_metrics(m)
        per_glyph.append({"codepoint": f"U+{cp:05X}", **gm})
        for k in metrics_by_name:
            metrics_by_name[k].append(gm[k])

    perms = list(itertools.permutations(VALUES.tolist()))
    tests = {}
    for name, vals in metrics_by_name.items():
        y = np.array(vals, dtype=float)
        hist = proportional_log2_error(y, VALUES)
        errors = np.array([proportional_log2_error(y, np.array(p, dtype=float)) for p in perms])
        rank = int(np.sum(errors < hist - 1e-12) + 1)
        p_le = float(np.sum(errors <= hist + 1e-12) / len(errors))
        best_idx = int(np.argmin(errors))
        rho, rho_p = spearmanr(np.arange(1, 7), y)
        tests[name] = {
            "historical_mapping_log2_mse": hist,
            "historical_mapping_rank_among_720_lower_is_better": rank,
            "fraction_of_permutations_as_good_or_better": p_le,
            "best_log2_mse": float(errors[best_idx]),
            "best_assignment_values_for_D011_to_D016": [float(x) for x in perms[best_idx]],
            "spearman_component_index_vs_metric": float(rho),
            "spearman_p_two_sided": float(rho_p),
        }
    return {"font_size": font_size, "per_glyph": per_glyph, "tests": tests}


def segment_object(path: str) -> tuple[np.ndarray, np.ndarray]:
    bgr = cv2.imread(path)
    if bgr is None:
        raise FileNotFoundError(path)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    border_n = max(5, int(min(h, w) * 0.05))
    border = np.concatenate([
        rgb[:border_n].reshape(-1, 3), rgb[-border_n:].reshape(-1, 3),
        rgb[:, :border_n].reshape(-1, 3), rgb[:, -border_n:].reshape(-1, 3)
    ], axis=0)
    bg = np.median(border, axis=0)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    bg_lab = cv2.cvtColor(np.uint8([[bg]]), cv2.COLOR_RGB2LAB).astype(np.float32)[0, 0]
    dist = np.linalg.norm(lab - bg_lab, axis=2)
    x = np.clip(dist, 0, 100)
    x8 = (x / max(x.max(), 1e-6) * 255).astype(np.uint8)
    thr, _ = cv2.threshold(x8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = (x8 > thr).astype(np.uint8)
    k = max(3, int(min(h, w) * 0.005)); k += (k % 2 == 0)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, ker, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, ker, iterations=1)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if n > 1:
        idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        mask = (labels == idx).astype(np.uint8)
    ys, xs = np.where(mask > 0)
    crop_img = bgr[ys.min():ys.max()+1, xs.min():xs.max()+1]
    crop_mask = mask[ys.min():ys.max()+1, xs.min():xs.max()+1]
    return crop_img, crop_mask


def circle_support(edge: np.ndarray, cx: int, cy: int, r: int, tol: float = 3.0) -> tuple[float, float]:
    dt = cv2.distanceTransform((1 - edge).astype(np.uint8), cv2.DIST_L2, 3)
    ang = np.linspace(0, 2*np.pi, 360, endpoint=False)
    xs = np.round(cx + r*np.cos(ang)).astype(int)
    ys = np.round(cy + r*np.sin(ang)).astype(int)
    good = (xs >= 0) & (xs < edge.shape[1]) & (ys >= 0) & (ys < edge.shape[0])
    vals = dt[ys[good], xs[good]]
    return float(np.mean(vals <= tol)), float(np.mean(vals))


def spiral_canary(path: str) -> dict:
    img, mask = segment_object(path)
    h, w = img.shape[:2]
    scale = 800.0 / w
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    rg = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    rm = cv2.resize(mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    H, W = rg.shape
    clahe = cv2.createCLAHE(2.0, (8, 8)).apply(rg)
    edge = (cv2.Canny(cv2.GaussianBlur(clahe, (5,5), 1), 50, 140) > 0).astype(np.uint8)
    edge *= cv2.dilate(rm, np.ones((5,5), np.uint8))

    # Frozen pilot ROI: lower-left part of the segmented Wedjat object.
    x0, x1 = int(0.03*W), int(0.38*W)
    y0, y1 = int(0.55*H), int(0.98*H)
    roi = cv2.GaussianBlur(rg[y0:y1, x0:x1], (5,5), 1.2)
    circles = cv2.HoughCircles(
        roi, cv2.HOUGH_GRADIENT, dp=1.1, minDist=12,
        param1=120, param2=14,
        minRadius=max(5, int(0.06*W)), maxRadius=int(0.18*W)
    )
    candidates = []
    if circles is not None:
        for x, y, r in np.round(circles[0]).astype(int):
            X, Y = int(x+x0), int(y+y0)
            if not (0 <= X < W and 0 <= Y < H):
                continue
            support, mean_edge_distance = circle_support(edge, X, Y, int(r), tol=3.0)
            candidates.append({
                "support": support,
                "mean_edge_distance_px": mean_edge_distance,
                "x_norm": X/W,
                "y_norm": Y/H,
                "radius_over_object_width": r/W,
            })
    candidates.sort(key=lambda z: (z["support"], -z["mean_edge_distance_px"]), reverse=True)
    best = candidates[0] if candidates else None
    return {
        "object_bbox_width_px": int(w), "object_bbox_height_px": int(h),
        "roi_norm": [0.03, 0.38, 0.55, 0.98],
        "radius_band_over_object_width": [0.06, 0.18],
        "presence_support_threshold": 0.5,
        "best_candidate": best,
        "loop_like_spiral_canary_present": bool(best and best["support"] >= 0.5),
    }


def exact_spearman_permutation_p(y: list[float]) -> dict:
    n = len(y)
    x = np.arange(n, dtype=float)
    obs = float(spearmanr(x, np.array(y)).statistic)
    vals = []
    for p in itertools.permutations(y):
        vals.append(float(spearmanr(x, np.array(p)).statistic))
    p = sum(abs(v) >= abs(obs) - 1e-12 for v in vals) / len(vals)
    return {"rho": obs, "exact_two_sided_permutation_p": float(p), "permutations": math.factorial(n)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", required=True)
    ap.add_argument("--font-size", type=int, default=220)
    ap.add_argument("--image", action="append", default=[], help="OBJECTID=PATH")
    ap.add_argument("--out")
    args = ap.parse_args()

    result = {
        "status": "EYE_INTERNAL_MAPPING_NEGATIVE_SPIRAL_DESCENT_EXPLORATORY_CANARY",
        "scope": "MODERN_GLYPH_MAPPING_CONTROL_PLUS_EXPLORATORY_MUSEUM_IMAGE_CANARY",
        "mapping_permutation_control": mapping_permutation_control(args.font, args.font_size),
        "museum_spiral_canary": {"objects": []},
        "claim_firewall": [
            "MODERN_GLYPH_GEOMETRY_IS_NOT_ANCIENT_PALEOGRAPHY",
            "MUSEUM_PILOT_IS_NOT_PRIMARY_PROTOCOL_EXECUTION",
            "NO_ANCIENT_BINARY_ASCII_OR_PYTHON_INTENT",
            "NO_CSM_TO_WEDJAT_HISTORICAL_DERIVATION_FROM_THIS_RESULT",
            "NO_SENSORY_MAPPING_PROMOTION",
        ],
        "environment": {
            "python": platform.python_version(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
        },
    }

    present_later = []
    for spec in args.image:
        oid, path = spec.split("=", 1)
        canary = spiral_canary(path)
        im = Image.open(path)
        item = {
            "met_object_id": oid,
            **OBJECT_METADATA.get(oid, {}),
            "official_url": OFFICIAL_URLS.get(oid),
            "known_main_image_url": KNOWN_MAIN_IMAGE_URLS.get(oid),
            "local_path_basename": os.path.basename(path),
            "local_byte_length": os.path.getsize(path),
            "local_sha256": sha256_file(path),
            "pixel_dimensions": [im.width, im.height],
            "provenance_note": "Local bytes were already present before this v0.4 execution and visually correspond to the cited Met object image; source-byte identity was not re-downloaded and re-hashed in this run.",
            "spiral_canary": canary,
        }
        result["museum_spiral_canary"]["objects"].append(item)
        if oid != "555588" and canary["loop_like_spiral_canary_present"] and canary["best_candidate"]:
            present_later.append((OBJECT_METADATA[oid]["mid_bce"], canary["best_candidate"]["y_norm"], oid))

    # Chronological direction among the four non-early pilot objects, oldest -> newest.
    if len(present_later) >= 3:
        ordered = sorted(present_later, key=lambda t: -t[0])
        ys = [x[1] for x in ordered]
        result["museum_spiral_canary"]["chronological_spiral_depth_test"] = {
            "ordered_oldest_to_newest": [{"met_object_id": x[2], "mid_bce": x[0], "spiral_y_norm": x[1]} for x in ordered],
            **exact_spearman_permutation_p(ys),
            "interpretation": "Exploratory directional canary only. A larger y means the detected lower-left loop sits lower in the object bounding box."
        }

    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    print(payload)

if __name__ == "__main__":
    main()
