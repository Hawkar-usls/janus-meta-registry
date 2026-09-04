#!/usr/bin/env python3
"""JANUS CRISTAL: skeptical multispectral pattern/semantic probe.

The program searches crystal imagery for machine-detected text-like, formula-like,
code-like and grid/periodic structures. It is intentionally hostile to post-hoc
"decoding": a candidate is never a message merely because OCR returned symbols.
Direct experimental modalities and synthetic proxies are reported separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import cv2
import numpy as np

UA = "JANUS-Cristal/1.0 (+https://github.com/Hawkar-usls/janus-meta-registry)"
TOKEN_RE = re.compile(r"[A-Z0-9][A-Z0-9_+\-*/=^<>()[\]{}.:]{1,23}")
FORMULA_RE = re.compile(r"(?=.*\d)(?=.*[=+\-*/^])[A-Z0-9_+\-*/=^<>()[\]{}.:]{3,24}")
CODE_HINTS = ("IF", "FOR", "WHILE", "DEF", "INT", "HEX", "0X", "==", "->", "::", "{}", "[]")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dst: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r, dst.open("wb") as w:
        shutil.copyfileobj(r, w)


def resize(image: np.ndarray, max_dim: int) -> np.ndarray:
    h, w = image.shape[:2]
    s = min(1.0, max_dim / max(h, w))
    if s == 1.0:
        return image
    return cv2.resize(image, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA)


def normalize_text(s: str) -> str:
    s = s.upper().replace(" ", "").replace("|", "I")
    return "".join(ch for ch in s if ch.isalnum() or ch in "_+-*/=^<>()[].{}:")[:24]


def classify_token(tok: str) -> str:
    if FORMULA_RE.fullmatch(tok):
        return "FORMULA_LIKE_OCR_TOKEN"
    if any(h in tok for h in CODE_HINTS) or sum(c in "_{}[]():<>" for c in tok) >= 2:
        return "CODE_LIKE_OCR_TOKEN"
    if tok.isalpha() and len(tok) >= 3:
        return "WORD_LIKE_OCR_TOKEN"
    return "SYMBOL_SEQUENCE_OCR_TOKEN"


def preprocess_variants(image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(2.0, (8, 8)).apply(gray)
    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adaptive = cv2.adaptiveThreshold(
        clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 7
    )
    edges = cv2.Canny(clahe, 70, 150)
    return [
        ("gray", gray),
        ("clahe", clahe),
        ("otsu", otsu),
        ("otsu_invert", 255 - otsu),
        ("adaptive", adaptive),
        ("edges", edges),
    ]


def spectral_proxy_variants(image: np.ndarray) -> List[Tuple[str, np.ndarray]]:
    """Uncalibrated stress tests. These are NOT physical re-illuminations."""
    b, g, r = cv2.split(image)
    neon = cv2.merge([
        (b.astype(np.float32) * 0.08).astype(np.uint8),
        (g.astype(np.float32) * 0.42).astype(np.uint8),
        np.clip(r.astype(np.float32) * 1.15, 0, 255).astype(np.uint8),
    ])
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    l, a, bb = cv2.split(lab)
    l = cv2.createCLAHE(1.5, (8, 8)).apply(l)
    solar = cv2.cvtColor(cv2.merge([l, a, bb]), cv2.COLOR_LAB2BGR)
    m1 = np.float32([[1, 0, 2], [0, 1, 0]])
    m2 = np.float32([[1, 0, -2], [0, 1, 0]])
    q1 = cv2.warpAffine(image, m1, (image.shape[1], image.shape[0]), borderMode=cv2.BORDER_REFLECT)
    q2 = cv2.warpAffine(image, m2, (image.shape[1], image.shape[0]), borderMode=cv2.BORDER_REFLECT)
    quartz_once = cv2.addWeighted(image, 0.72, q1, 0.28, 0)
    quartz_twice = cv2.addWeighted(quartz_once, 0.72, q2, 0.28, 0)
    return [
        ("solar_broadband_control_PROXY", solar),
        ("neon_redorange_PROXY", neon),
        ("quartz_filter_once_PROXY", quartz_once),
        ("quartz_filter_twice_PROXY", quartz_twice),
    ]


def tesseract_tokens(gray: np.ndarray, min_conf: float = 45.0) -> List[dict]:
    if shutil.which("tesseract") is None:
        raise RuntimeError("tesseract binary is required")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = Path(f.name)
    try:
        cv2.imwrite(str(tmp), gray)
        cmd = [
            "tesseract", str(tmp), "stdout", "--psm", "11", "-l", "eng", "tsv",
            "-c", "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_+-*/=^<>()[].{}:"
        ]
        p = subprocess.run(
            cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, timeout=30
        )
        if p.returncode != 0:
            return []
        rows = p.stdout.splitlines()
        out = []
        h, w = gray.shape[:2]
        for row in rows[1:]:
            cols = row.split("\t")
            if len(cols) < 12:
                continue
            text = normalize_text(cols[11])
            try:
                conf = float(cols[10])
                x, y, bw, bh = map(int, cols[6:10])
            except ValueError:
                continue
            if conf < min_conf or not TOKEN_RE.fullmatch(text):
                continue
            out.append({
                "token": text,
                "class": classify_token(text),
                "confidence": round(conf, 2),
                "box_norm": [round(x / w, 5), round(y / h, 5), round(bw / w, 5), round(bh / h, 5)],
            })
        return out
    finally:
        tmp.unlink(missing_ok=True)


def block_shuffle(gray: np.ndarray, block: int = 48, seed: int = 1138) -> np.ndarray:
    rng = np.random.default_rng(seed)
    h, w = gray.shape
    ph = int(math.ceil(h / block) * block)
    pw = int(math.ceil(w / block) * block)
    pad = cv2.copyMakeBorder(gray, 0, ph - h, 0, pw - w, cv2.BORDER_REFLECT)
    tiles = [
        pad[y:y + block, x:x + block].copy()
        for y in range(0, ph, block) for x in range(0, pw, block)
    ]
    rng.shuffle(tiles)
    out = np.empty_like(pad)
    i = 0
    for y in range(0, ph, block):
        for x in range(0, pw, block):
            out[y:y + block, x:x + block] = tiles[i]
            i += 1
    return out[:h, :w]


def entropy_u8(gray: np.ndarray) -> float:
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    p = hist / max(1.0, hist.sum())
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def fft_periodicity(gray: np.ndarray) -> dict:
    small = cv2.resize(gray, (256, 256), interpolation=cv2.INTER_AREA).astype(np.float32)
    small -= small.mean()
    mag = np.abs(np.fft.fftshift(np.fft.fft2(small)))
    cy = cx = 128
    mag[cy - 5:cy + 6, cx - 5:cx + 6] = 0
    flat = mag.ravel()
    if flat.size == 0 or float(flat.mean()) == 0:
        return {"peak_to_mean": 0.0, "classification": "NO_PERIODIC_PEAK"}
    ratio = float(np.partition(flat, -10)[-10:].mean() / flat.mean())
    return {
        "peak_to_mean": round(ratio, 4),
        "classification": "STRONG_PERIODIC_STRUCTURE" if ratio >= 20 else "WEAK_OR_BROADBAND_STRUCTURE",
    }


def analyze_semantics(image: np.ndarray, allow_proxies: bool, min_conf: float) -> dict:
    image = resize(image, 1200)
    variants = preprocess_variants(image)
    if allow_proxies:
        for name, proxy in spectral_proxy_variants(image):
            variants.append((name, cv2.cvtColor(proxy, cv2.COLOR_BGR2GRAY)))
    by_token: Dict[str, List[dict]] = defaultdict(list)
    per_variant = []
    for name, gray in variants:
        if gray.ndim == 3:
            gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
        toks = tesseract_tokens(gray, min_conf=min_conf)
        per_variant.append({"variant": name, "tokens": toks})
        for t in toks:
            by_token[t["token"]].append({"variant": name, **t})
    base_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    control = block_shuffle(base_gray)
    control_tokens = tesseract_tokens(control, min_conf=min_conf)
    persistent = []
    for tok, hits in by_token.items():
        real_variants = sorted({h["variant"] for h in hits if not h["variant"].endswith("_PROXY")})
        all_variants = sorted({h["variant"] for h in hits})
        if len(real_variants) >= 2:
            persistent.append({
                "token": tok,
                "class": hits[0]["class"],
                "direct_transform_hits": len(real_variants),
                "direct_transforms": real_variants,
                "all_transform_hits": len(all_variants),
                "max_confidence": max(h["confidence"] for h in hits),
                "status": "OCR_PERSISTENT_CANDIDATE_NOT_MESSAGE",
            })
    persistent.sort(key=lambda x: (-x["direct_transform_hits"], -x["max_confidence"], x["token"]))
    return {
        "variants": per_variant,
        "unique_tokens": len(by_token),
        "persistent_candidates": persistent,
        "persistent_candidate_count": len(persistent),
        "negative_control": {
            "method": "deterministic 48px block shuffle",
            "tokens": control_tokens,
            "token_count": len(control_tokens),
        },
        "structure": {
            "entropy_bits": round(entropy_u8(base_gray), 4),
            "fft": fft_periodicity(base_gray),
        },
        "claim_ceiling": "OCR_OR_PERIODICITY_ONLY; NOT_AN_EMBEDDED_MESSAGE_OR_ALGORITHM",
    }


def image_difference(a: np.ndarray, b: np.ndarray) -> dict:
    a = resize(a, 1000)
    b = resize(b, 1000)
    h = min(a.shape[0], b.shape[0])
    w = min(a.shape[1], b.shape[1])
    a = cv2.resize(a, (w, h))
    b = cv2.resize(b, (w, h))
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    corr = float(np.corrcoef(ga.ravel(), gb.ravel())[0, 1]) if ga.std() > 0 and gb.std() > 0 else 0.0
    delta = cv2.absdiff(ga, gb)
    return {
        "pixel_correlation_unregistered": round(corr, 6),
        "mean_absolute_delta": round(float(delta.mean()), 4),
        "visible_edge_density": round(float((cv2.Canny(ga, 70, 150) > 0).mean()), 6),
        "uv_edge_density": round(float((cv2.Canny(gb, 70, 150) > 0).mean()), 6),
        "interpretation": "SAME_SPECIMEN_MODALITY_DIFFERENCE; camera/exposure/alignment confounds remain",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-ocr-confidence", type=float, default=45.0)
    args = ap.parse_args()
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "janus.cristal.multispectral_probe.result.v1",
        "artifact_name": "Janus Cristal",
        "method": {
            "semantic_search": ["word-like OCR", "formula-like OCR", "code-like OCR", "symbol sequences", "FFT periodicity"],
            "negative_control": "deterministic block shuffle",
            "no_post_hoc_cipher_search": True,
            "direct_and_proxy_modalities_kept_separate": True,
        },
        "sources": [],
        "paired_comparisons": [],
    }
    loaded = {}
    with tempfile.TemporaryDirectory(prefix="janus-cristal-") as td:
        td = Path(td)
        for i, s in enumerate(manifest["sources"], 1):
            e = {k: v for k, v in s.items() if k != "download_url"}
            try:
                p = td / f"s{i}{Path(s['download_url'].split('?', 1)[0]).suffix or '.img'}"
                fetch(s["download_url"], p)
                img = cv2.imread(str(p), cv2.IMREAD_COLOR)
                if img is None:
                    raise RuntimeError("image decode failed")
                loaded[s["id"]] = img
                e["sha256"] = sha256_file(p)
                e["dimensions"] = [int(img.shape[1]), int(img.shape[0])]
                e["status"] = "ANALYZED"
                if s.get("semantic_scan", True):
                    e["semantic_analysis"] = analyze_semantics(
                        img, bool(s.get("allow_spectral_proxies", False)), args.min_ocr_confidence
                    )
                else:
                    gray = cv2.cvtColor(resize(img, 1200), cv2.COLOR_BGR2GRAY)
                    e["semantic_analysis"] = {
                        "status": "DISABLED_TO_AVOID_AUTHOR_ANNOTATION_CONTAMINATION",
                        "structure": {
                            "entropy_bits": round(entropy_u8(gray), 4),
                            "fft": fft_periodicity(gray),
                        },
                    }
            except Exception as ex:
                e["status"] = "ERROR"
                e["error"] = f"{type(ex).__name__}: {ex}"
            report["sources"].append(e)
        for pair in manifest.get("pairs", []):
            if pair["a"] in loaded and pair["b"] in loaded:
                report["paired_comparisons"].append({
                    "pair_id": pair["id"],
                    **image_difference(loaded[pair["a"]], loaded[pair["b"]]),
                })
    seen = defaultdict(set)
    for s in report["sources"]:
        sa = s.get("semantic_analysis", {})
        for c in sa.get("persistent_candidates", []):
            seen[c["token"]].add(s["id"])
    cross = [
        {"token": t, "sources": sorted(ids), "source_count": len(ids), "status": "CROSS_SOURCE_OCR_CANDIDATE_NOT_MESSAGE"}
        for t, ids in seen.items() if len(ids) >= 2
    ]
    cross.sort(key=lambda x: (-x["source_count"], x["token"]))
    report["cross_source_candidates"] = cross
    report["global_interpretation"] = {
        "message_claim": "BLOCKED",
        "formula_claim": "BLOCKED",
        "code_or_algorithm_claim": "BLOCKED",
        "reason": "A claim requires pre-registered encoding plus persistence across independent raw modalities and negative-control separation.",
        "rules": [
            "OCR_TOKEN != MESSAGE",
            "FORMULA_LIKE != ENCODED_FORMULA",
            "CODE_LIKE != ALGORITHM",
            "PATTERN != INTENT",
            "NO_POST_HOC_CIPHER_SEARCH",
        ],
    }
    errors = [s for s in report["sources"] if s["status"] == "ERROR"]
    (out / "JANUS-CRISTAL-result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Janus Cristal — CI receipt", "",
        f"Sources analyzed: {len(report['sources']) - len(errors)}/{len(report['sources'])}",
        f"Source errors: {len(errors)}", "",
        "| Source | Modality | OCR candidates persistent across direct transforms |",
        "|---|---|---:|",
    ]
    for s in report["sources"]:
        sem = s.get("semantic_analysis", {})
        n = sem.get("persistent_candidate_count", "disabled")
        lines.append(f"| {s['id']} | {s.get('modality', '?')} | {n} |")
    lines += [
        "", f"Cross-source repeated OCR candidates: **{len(cross)}**", "",
        "> OCR / formula-like / code-like output is detector behavior, not evidence of an embedded message.",
    ]
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
