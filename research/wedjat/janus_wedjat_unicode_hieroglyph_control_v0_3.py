#!/usr/bin/env python3
"""JANUS Wedjat v0.3 — modern Unicode hieroglyph negative-control probe.

Purpose
-------
Test whether the six modern Gardiner/Unicode Wedjat fraction glyphs D011..D016
show a geometric halving ladder, or unusual morphology, when compared against
all other glyphs in the Unicode Egyptian Hieroglyphs block U+13000..U+1342F.

This is explicitly a MODERN FONT CONTROL. It is not a paleographic test and it
must not be used as evidence that an ancient scribe encoded binary, ASCII, Python,
or that Unicode glyph shapes reproduce ancient hieratic sign forms.

Dependencies: Pillow, numpy, opencv-python, scipy, scikit-image.
The font file is supplied externally with --font and is never embedded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import unicodedata
from pathlib import Path
from fractions import Fraction

import cv2
import numpy as np
import PIL
from PIL import Image, ImageDraw, ImageFont
import scipy
from scipy.spatial.distance import cdist
from scipy.stats import spearmanr
import skimage
from skimage.morphology import skeletonize

BLOCK_START = 0x13000
BLOCK_END_EXCLUSIVE = 0x13430
D010 = 0x13080
TARGET = list(range(0x13081, 0x13087))
EXCLUDE_FROM_CONTROLS = set(range(0x13080, 0x13087))
FRACTIONS = ["1/2", "1/4", "1/8", "1/16", "1/32", "1/64"]
IDEAL = np.array([1 / 2, 1 / 4, 1 / 8, 1 / 16, 1 / 32, 1 / 64], dtype=float)
RITTER_EXPERT_DIAGNOSTIC_SCORES = np.array([1, 0, 0, 2, 2, 0], dtype=float)
ADJACENT_FRACTION_CONTROLS = {0x1308C: Fraction(2, 3), 0x1308D: Fraction(3, 4)}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def render(cp: int, font: ImageFont.FreeTypeFont, font_size: int, canvas: int = 320) -> np.ndarray | None:
    im = Image.new("L", (canvas, canvas), 255)
    d = ImageDraw.Draw(im)
    ch = chr(cp)
    bb = d.textbbox((0, 0), ch, font=font)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    x = (canvas - w) // 2 - bb[0]
    y = (canvas - h) // 2 - bb[1]
    d.text((x, y), ch, font=font, fill=0)
    mask = np.asarray(im) < 128
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]


def normmask(mask: np.ndarray, n: int = 64) -> np.ndarray:
    h, w = mask.shape
    scale = min((n - 8) / w, (n - 8) / h)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    resized = cv2.resize(mask.astype(np.uint8), (nw, nh), interpolation=cv2.INTER_NEAREST) > 0
    out = np.zeros((n, n), dtype=np.uint8)
    x = (n - nw) // 2
    y = (n - nh) // 2
    out[y : y + nh, x : x + nw] = resized
    return out


def hole_count(mask: np.ndarray) -> int:
    m = mask.astype(np.uint8) * 255
    _, hierarchy = cv2.findContours(m, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return 0
    return int(sum(1 for h in hierarchy[0] if h[3] != -1))


def describe(mask: np.ndarray) -> dict:
    h, w = mask.shape
    area = float(mask.sum())
    m = mask.astype(np.uint8)
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    perimeter = sum(cv2.arcLength(c, True) for c in contours)
    sk = skeletonize(mask)
    skn = sk.astype(np.uint8)
    neighbors = cv2.filter2D(skn, -1, np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT) - skn
    endpoints = int(np.logical_and(sk, neighbors == 1).sum())
    junction_pixels = int(np.logical_and(sk, neighbors >= 3).sum())
    components = max(0, cv2.connectedComponents(m)[0] - 1)
    holes = hole_count(mask)

    hu = cv2.HuMoments(cv2.moments(m)).flatten()
    hu = np.array([-np.sign(x) * math.log10(abs(x)) if x != 0 else 0.0 for x in hu])

    nm = normmask(mask)
    px = nm.sum(0).astype(float)
    py = nm.sum(1).astype(float)
    if px.sum():
        px /= px.sum()
    if py.sum():
        py /= py.sum()
    px8 = np.array([x.sum() for x in np.array_split(px, 8)])
    py8 = np.array([x.sum() for x in np.array_split(py, 8)])

    complexity = endpoints + 2 * holes + 0.25 * junction_pixels + 0.5 * components + perimeter / math.sqrt(area)

    return {
        "bbox_w": int(w),
        "bbox_h": int(h),
        "bbox_diag": float(math.hypot(w, h)),
        "ink_area": area,
        "aspect": float(w / h),
        "ink_density": float(area / (w * h)),
        "perimeter_norm": float(perimeter / math.sqrt(area)),
        "skeleton_length": float(sk.sum()),
        "skeleton_norm": float(sk.sum() / math.sqrt(area)),
        "endpoints": endpoints,
        "junction_pixels": junction_pixels,
        "components": int(components),
        "holes": holes,
        "complexity_score": float(complexity),
        "hu": hu.tolist(),
        "projection": np.r_[px8, py8].tolist(),
    }


def ladder_score(vals: np.ndarray) -> float:
    vals = np.asarray(vals, dtype=float)
    vals = vals / vals[0]
    ideal = IDEAL / IDEAL[0]
    return float(np.mean((np.log2(vals) - np.log2(ideal)) ** 2))


def fit_lambda(vals: np.ndarray) -> tuple[float, float]:
    vals = np.asarray(vals, dtype=float)
    k = np.arange(6)
    y = np.log(vals)
    slope, intercept = np.polyfit(k, y, 1)
    pred = intercept + slope * k
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return float(math.exp(slope)), float(r2)


def binary_fraction_probe(frac: Fraction, bits: int = 24) -> dict:
    den = frac.denominator
    finite = den > 0 and (den & (den - 1)) == 0
    n = frac.numerator // frac.denominator
    rem = frac.numerator % frac.denominator
    seen = {}
    seq = []
    repeat_from = None
    for i in range(bits):
        if rem == 0:
            break
        if rem in seen:
            repeat_from = seen[rem]
            break
        seen[rem] = i
        rem *= 2
        bit = rem // frac.denominator
        rem %= frac.denominator
        seq.append(str(bit))
    return {
        "fraction": f"{frac.numerator}/{frac.denominator}",
        "finite_binary": finite,
        "binary_integer_part": str(n),
        "binary_fraction_digits": "".join(seq),
        "repeat_from_index": repeat_from,
    }


def code(cp: int) -> str:
    return f"U+{cp:05X}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", default="/usr/share/fonts/truetype/noto/NotoSansEgyptianHieroglyphs-Regular.ttf")
    ap.add_argument("--font-size", type=int, default=220)
    ap.add_argument("--random-sets", type=int, default=50000)
    ap.add_argument("--cohesion-sets", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=20260815)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()

    font_path = Path(args.font)
    if not font_path.exists():
        raise SystemExit(f"Font not found: {font_path}. Supply an Egyptian hieroglyph font with --font.")
    font = ImageFont.truetype(str(font_path), args.font_size)

    records = []
    masks = {}
    for cp in range(BLOCK_START, BLOCK_END_EXCLUSIVE):
        m = render(cp, font, args.font_size)
        if m is None:
            continue
        masks[cp] = m
        r = describe(m)
        r["cp"] = cp
        records.append(r)

    cps = [r["cp"] for r in records]
    idx = {cp: i for i, cp in enumerate(cps)}
    by = {r["cp"]: r for r in records}
    control_idx = [i for i, cp in enumerate(cps) if cp not in EXCLUDE_FROM_CONTROLS]

    vectors = []
    for r in records:
        vectors.append([
            math.log(r["aspect"]), r["ink_density"], r["perimeter_norm"], r["skeleton_norm"],
            r["endpoints"], r["junction_pixels"], r["components"], r["holes"],
            *r["hu"], *r["projection"],
        ])
    X = np.asarray(vectors, dtype=float)
    med = np.median(X, axis=0)
    mad = np.median(np.abs(X - med), axis=0)
    mad[mad < 1e-9] = 1.0
    Z = (X - med) / (1.4826 * mad)
    Zn = Z[control_idx]

    d_all = cdist(Zn, Zn)
    np.fill_diagonal(d_all, np.inf)
    all_nn = d_all.min(axis=1)
    nearest = {}
    for cp in TARGET:
        d = cdist(Z[idx[cp]][None, :], Zn)[0]
        order = np.argsort(d)[:10]
        nearest_distance = float(d[order[0]])
        nearest[code(cp)] = {
            "nearest_distance": nearest_distance,
            "nearest_distance_percentile_among_control_nn": float((all_nn <= nearest_distance).mean() * 100),
            "nearest_unrelated": [
                {
                    "codepoint": code(cps[control_idx[j]]),
                    "name": unicodedata.name(chr(cps[control_idx[j]]), "UNKNOWN"),
                    "distance": float(d[j]),
                }
                for j in order
            ],
        }

    complexity_scores = np.array([r["complexity_score"] for r in records])
    complexity = {
        code(cp): {
            "fraction_annotation": frac,
            "score": float(by[cp]["complexity_score"]),
            "percentile_in_1072_glyph_block": float((complexity_scores <= by[cp]["complexity_score"]).mean() * 100),
        }
        for cp, frac in zip(TARGET, FRACTIONS)
    }

    rng = np.random.default_rng(args.seed)
    controls = np.array(control_idx)
    random_rows = np.empty((args.random_sets, 6), dtype=int)
    for i in range(args.random_sets):
        random_rows[i] = rng.choice(controls, size=6, replace=False)

    geometry = {}
    for feature in ["ink_area", "bbox_diag", "skeleton_length"]:
        vals = np.array([by[cp][feature] for cp in TARGET], dtype=float)
        observed = ladder_score(vals)
        lam, r2 = fit_lambda(vals)
        all_vals = np.array([r[feature] for r in records], dtype=float)
        null = np.array([ladder_score(all_vals[row]) for row in random_rows])
        geometry[feature] = {
            "target_values_D011_to_D016": vals.tolist(),
            "lambda_hat": lam,
            "r2_log_linear": r2,
            "dyadic_log2_mse": observed,
            "null_random_ordered_six_glyph_sets": int(args.random_sets),
            "empirical_p_random_set_as_dyadic_or_better": float((1 + np.sum(null <= observed)) / (args.random_sets + 1)),
            "null_median_mse": float(np.median(null)),
            "null_p05_mse": float(np.quantile(null, 0.05)),
            "null_p01_mse": float(np.quantile(null, 0.01)),
        }

    target_z = Z[[idx[cp] for cp in TARGET]]
    target_pairwise = cdist(target_z, target_z)
    target_cohesion = float(target_pairwise[np.triu_indices(6, 1)].mean())
    null_cohesion = np.empty(args.cohesion_sets)
    for i in range(args.cohesion_sets):
        sel = rng.choice(control_idx, size=6, replace=False)
        d = cdist(Z[sel], Z[sel])
        null_cohesion[i] = d[np.triu_indices(6, 1)].mean()

    modern_percentiles = np.array([complexity[code(cp)]["percentile_in_1072_glyph_block"] for cp in TARGET])
    rho, rho_p = spearmanr(modern_percentiles, RITTER_EXPERT_DIAGNOSTIC_SCORES)

    result = {
        "experiment": "JANUS-WEDJAT-UNICODE-HIEROGLYPH-CONTROL-v0.3",
        "status": "EXECUTED_MODERN_GLYPH_NEGATIVE_CONTROL",
        "scope": "MODERN_UNICODE_FONT_CONTROL_ONLY_NOT_PALEOGRAPHIC_GROUND_TRUTH",
        "input": {
            "unicode_block": ["U+13000", "U+1342F"],
            "rendered_glyph_count": len(records),
            "full_wedjat": "U+13080 / D010",
            "targets": [code(cp) for cp in TARGET],
            "fraction_annotations": FRACTIONS,
            "font_family_requested": "Noto Sans Egyptian Hieroglyphs",
            "font_path_local": str(font_path),
            "font_sha256": sha256_file(font_path),
            "font_size": args.font_size,
            "seed": args.seed,
        },
        "environment": {
            "python": platform.python_version(),
            "pillow": PIL.__version__,
            "numpy": np.__version__,
            "opencv": cv2.__version__,
            "scipy": scipy.__version__,
            "scikit_image": skimage.__version__,
        },
        "target_metrics": {
            code(cp): {
                "name": unicodedata.name(chr(cp), "UNKNOWN"),
                "fraction_annotation": frac,
                **{k: v for k, v in by[cp].items() if k not in {"cp", "hu", "projection"}},
            }
            for cp, frac in zip(TARGET, FRACTIONS)
        },
        "dyadic_geometry_against_other_hieroglyphs": geometry,
        "morphological_complexity": complexity,
        "nearest_unrelated_hieroglyph_controls": nearest,
        "adjacent_fraction_hieroglyph_controls": {
            code(cp): {
                "name": unicodedata.name(chr(cp), "UNKNOWN"),
                **binary_fraction_probe(frac),
            }
            for cp, frac in ADJACENT_FRACTION_CONTROLS.items()
        },
        "target_family_cohesion": {
            "mean_pairwise_robust_z_distance": target_cohesion,
            "null_random_six_glyph_sets": int(args.cohesion_sets),
            "empirical_p_random_set_as_cohesive_or_more": float((1 + np.sum(null_cohesion <= target_cohesion)) / (args.cohesion_sets + 1)),
            "null_median_distance": float(np.median(null_cohesion)),
        },
        "ritter_posthoc_sanity_check": {
            "historical_expert_categories_D011_to_D016": ["MEDIUM", "LOW", "LOW", "HIGH", "HIGH", "LOW"],
            "encoded_scores": RITTER_EXPERT_DIAGNOSTIC_SCORES.tolist(),
            "modern_font_complexity_percentiles": modern_percentiles.tolist(),
            "spearman_rho": float(rho),
            "two_sided_p": float(rho_p),
            "status": "POST_HOC_SMALL_N_SANITY_CHECK_NOT_CONFIRMATORY",
        },
        "claim_firewall": [
            "NO_ANCIENT_BINARY_INTENT",
            "NO_ANCIENT_PYTHON_OR_ASCII_INTENT",
            "MODERN_FONT_SHAPES_ARE_NOT_HISTORICAL_HIERATIC_GROUND_TRUTH",
            "UNICODE_CONTROL_CANNOT_CONFIRM_OR_REFUTE_ANCIENT_SIGN_GENEALOGY_BY_ITSELF",
            "PRIMARY_PALEOGRAPHIC_GATE_STILL_REQUIRES_DATED_DOCUMENT_IMAGES_AND_SHA256_SEALING",
        ],
    }

    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "rendered_glyph_count": len(records),
        "font_sha256": result["input"]["font_sha256"],
        "dyadic_geometry": geometry,
        "complexity": complexity,
        "family_cohesion": result["target_family_cohesion"],
        "ritter_posthoc": result["ritter_posthoc_sanity_check"],
        "nearest_top1": {k: v["nearest_unrelated"][0] for k, v in nearest.items()},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
