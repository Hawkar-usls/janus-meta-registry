#!/usr/bin/env python3
"""JANUS Wedjat v0.8 — one-eye glyph reconfiguration control.

Question: if D011..D016 are treated only as six modern shape primitives, how
many other Egyptian Unicode/Gardiner glyphs can they approximate?

Modes deliberately separate a physically stricter interpretation from a
promiscuous upper bound:
  shared   all six parts keep one common scale; translation only
  free     each part may resize independently; false-positive upper bound
  split    disjoint subsets try to form two/three eye-family glyphs

This is a MODERN GLYPH CONTROL. It is not ancient paleography and does not
establish an ancient text, reading order, hidden message, binary, ASCII,
Python, or a historical six-piece puzzle.
"""
from __future__ import annotations
import argparse, itertools, json, unicodedata
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

D010 = 0x13080
PARTS = list(range(0x13081, 0x13087))
START, END = 0x13000, 0x1342F
EYE_FAMILY = list(range(0x13079, 0x13081))  # D004..D010 incl. D008A
MAXD = 96
SHARED_SCALES = np.linspace(.35, 1.50, 24)
FREE_SCALES = np.linspace(.10, 1.00, 10)
PARTITION_SCALES = np.linspace(.30, 1.30, 21)


def g(cp: int) -> str:
    return unicodedata.name(chr(cp)).replace("EGYPTIAN HIEROGLYPH ", "")


def raw(cp: int, font, n: int = 256) -> np.ndarray:
    im = Image.new("L", (n, n), 255)
    d = ImageDraw.Draw(im)
    b = d.textbbox((0, 0), chr(cp), font=font)
    d.text(((n-(b[2]-b[0]))//2-b[0], (n-(b[3]-b[1]))//2-b[1]),
           chr(cp), font=font, fill=0)
    m = (np.array(im) < 128).astype(np.uint8)
    y, x = np.where(m)
    return m[y.min():y.max()+1, x.min():x.max()+1]


def rs(m: np.ndarray, s: float) -> np.ndarray:
    h, w = m.shape
    return cv2.resize(m, (max(1, round(w*s)), max(1, round(h*s))),
                      interpolation=cv2.INTER_NEAREST).astype(np.uint8)


def norm(m: np.ndarray) -> np.ndarray:
    return rs(m, MAXD / max(m.shape))


def place(piece: np.ndarray, target: np.ndarray):
    H, W = target.shape
    h, w = piece.shape
    if h > H or w > W:
        return None
    z = cv2.matchTemplate(target.astype(np.float32),
                          piece.astype(np.float32), cv2.TM_CCORR)
    _, _, _, (x, y) = cv2.minMaxLoc(z)
    out = np.zeros_like(target)
    out[y:y+h, x:x+w] = piece
    return out > 0


def metrics(masks, target):
    if not masks:
        return {"f1": 0.0, "recall": 0.0, "precision": 0.0}
    u = np.logical_or.reduce(masks)
    q = target > 0
    ov, ua, ta = int((u & q).sum()), int(u.sum()), int(q.sum())
    return {"f1": 2*ov/(ua+ta), "recall": ov/ta,
            "precision": ov/ua if ua else 0.0}


def all_glyphs():
    out = []
    for cp in range(START, END+1):
        try:
            n = unicodedata.name(chr(cp))
        except ValueError:
            continue
        if n.startswith("EGYPTIAN HIEROGLYPH"):
            out.append(cp)
    return out


def shared(font):
    eye = raw(D010, font)
    base = MAXD / max(eye.shape)
    parts = {p: rs(raw(p, font), base) for p in PARTS}
    rows = []
    for cp in all_glyphs():
        t = norm(raw(cp, font))
        best = None
        for s in SHARED_SCALES:
            ms = []
            for p in PARTS:
                m = place(rs(parts[p], float(s)), t)
                if m is None:
                    ms = []
                    break
                ms.append(m)
            if not ms:
                continue
            z = metrics(ms, t)
            z["scale"] = float(s)
            if best is None or z["f1"] > best["f1"]:
                best = z
        if best:
            rows.append({"gardiner": g(cp), **best})
    rows.sort(key=lambda x: x["f1"], reverse=True)
    return rows


def free(font):
    parts = {p: norm(raw(p, font)) for p in PARTS}
    rows = []
    for cp in all_glyphs():
        t = norm(raw(cp, font))
        ms = []
        for p in PARTS:
            best = None
            for s in FREE_SCALES:
                m = place(rs(parts[p], float(s)), t)
                if m is None:
                    continue
                z = metrics([m], t)
                if best is None or z["f1"] > best[0]:
                    best = (z["f1"], m)
            if best is None:
                ms = []
                break
            ms.append(best[1])
        if ms:
            rows.append({"gardiner": g(cp), **metrics(ms, t)})
    rows.sort(key=lambda x: x["f1"], reverse=True)
    return rows


def partition_tables(font):
    eye = raw(D010, font)
    base = MAXD / max(eye.shape)
    parts = {p: rs(raw(p, font), base) for p in PARTS}
    tables = {}
    for cp in EYE_FAMILY:
        t = norm(raw(cp, font))
        per_scale = []
        for s in PARTITION_SCALES:
            placed = {p: place(rs(parts[p], float(s)), t) for p in PARTS}
            scores = {}
            for mask in range(1, 64):
                ms = [placed[PARTS[i]] for i in range(6) if mask >> i & 1]
                if any(m is None for m in ms):
                    continue
                scores[mask] = metrics(ms, t)["f1"]
            per_scale.append(scores)
        tables[cp] = per_scale
    return tables


def split(font, threshold=0.45):
    T = partition_tables(font)
    pairs = []
    for a, b in itertools.combinations(EYE_FAMILY, 2):
        best = None
        for si, s in enumerate(PARTITION_SCALES):
            for ma, fa in T[a][si].items():
                if fa < threshold:
                    continue
                for mb, fb in T[b][si].items():
                    if fb < threshold or ma & mb:
                        continue
                    q = (min(fa, fb), (fa+fb)/2, float(s), ma, mb, fa, fb)
                    if best is None or q > best:
                        best = q
        if best:
            pairs.append({"a": g(a), "b": g(b), "min_f1": best[0],
                          "mean_f1": best[1], "scale": best[2],
                          "mask_a": format(best[3], "06b"),
                          "mask_b": format(best[4], "06b"),
                          "f1_a": best[5], "f1_b": best[6]})
    pairs.sort(key=lambda x: (x["min_f1"], x["mean_f1"]), reverse=True)
    return pairs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", required=True)
    ap.add_argument("--mode", choices=["shared", "free", "split"], required=True)
    ap.add_argument("--threshold", type=float, default=.45)
    ap.add_argument("--out")
    a = ap.parse_args()
    font = ImageFont.truetype(a.font, 180)
    result = shared(font) if a.mode == "shared" else free(font) if a.mode == "free" else split(font, a.threshold)
    s = json.dumps(result, ensure_ascii=False, indent=2)
    if a.out:
        Path(a.out).write_text(s+"\n", encoding="utf-8")
    print(s)


if __name__ == "__main__":
    main()
