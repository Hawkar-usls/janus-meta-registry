# -*- coding: utf-8 -*-
"""JANUS // SET // ORDER FROM CHAOS R2

Algorithmic poster-to-ordered-line conversion derived from the earlier Angel
image-to-line/string-art experiment. It deliberately uses no image-generation
model: the supplied raster is transformed by deterministic image processing.

Stages:
  CHAOS -> ORDER_1 -> ORDER_2 -> ORDER_LOCK
"""
import cv2
import numpy as np
import random
import math
import json

MAX_DIM = 720
SEED = 1138


def extract_ordered_contours(image_path):
    img = cv2.imread(image_path)
    h0, w0 = img.shape[:2]
    scale = min(1.0, MAX_DIM / float(max(h0, w0)))
    img = cv2.resize(img, (int(w0 * scale), int(h0 * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blur = cv2.GaussianBlur(clahe, (3, 3), 0)
    edges = cv2.Canny(blur, 55, 145, L2gradient=True)

    _, bright = cv2.threshold(clahe, 190, 255, cv2.THRESH_BINARY)
    bright = cv2.morphologyEx(bright, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
    edges = cv2.bitwise_or(edges, bright)

    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    ordered = []
    for contour in contours:
        arc = cv2.arcLength(contour, False)
        if arc < 12:
            continue
        approx = cv2.approxPolyDP(contour, max(0.8, 0.003 * arc), False)
        points = approx.reshape(-1, 2)
        if len(points) < 2:
            continue
        _, _, bw, bh = cv2.boundingRect(approx)
        area = bw * bh
        score = arc * (1.0 + 0.0008 * area)
        ordered.append((score, arc, area, points))

    ordered.sort(key=lambda item: (-item[0], -item[1]))
    return img, ordered[:1400]


def render_stage(shape, entries, label, chaotic=False):
    h, w = shape[:2]
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    rng = random.Random(SEED)
    seq = list(entries)
    if chaotic:
        rng.shuffle(seq)

    for score, arc, area, points in seq:
        if chaotic:
            pts = points
            if len(pts) > 4:
                start = rng.randrange(0, max(1, len(pts) - 2))
                pts = pts[start:start + rng.randint(2, min(8, len(pts) - start))]
            color = (45, 33, 18)
        else:
            pts = points
            brightness = int(100 + 155 * min(1.0, math.log1p(max(1, score)) / 10.0))
            color = (int(brightness * 0.22), int(brightness * 0.66), brightness)
        cv2.polylines(canvas, [pts.astype(np.int32)], False, color, 1, cv2.LINE_AA)

    cv2.rectangle(canvas, (8, 8), (160, 34), (0, 0, 0), -1)
    cv2.putText(canvas, label, (14, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (40, 180, 240), 1, cv2.LINE_AA)
    return canvas


def convert(image_path, output_prefix):
    img, ordered = extract_ordered_contours(image_path)
    n = len(ordered)
    stages = [
        ('CHAOS', ordered[:max(120, n // 5)], True),
        ('ORDER_1', ordered[:max(240, n // 3)], False),
        ('ORDER_2', ordered[:max(500, 2 * n // 3)], False),
        ('ORDER_LOCK', ordered, False),
    ]
    panels = [render_stage(img.shape, subset, name, chaotic)
              for name, subset, chaotic in stages]
    panels[-1] = cv2.addWeighted((img.astype(np.float32) * 0.14).astype(np.uint8),
                                 1.0, panels[-1], 0.92, 0)

    h, w = img.shape[:2]
    sheet = np.zeros((h * 2, w * 2, 3), dtype=np.uint8)
    sheet[0:h, 0:w] = panels[0]
    sheet[0:h, w:2*w] = panels[1]
    sheet[h:2*h, 0:w] = panels[2]
    sheet[h:2*h, w:2*w] = panels[3]

    cv2.imwrite(output_prefix + '_CHAOS_TO_ORDER_R2.png', sheet,
                [cv2.IMWRITE_PNG_COMPRESSION, 9])
    cv2.imwrite(output_prefix + '_ORDER_LOCK_R2.png', panels[-1],
                [cv2.IMWRITE_PNG_COMPRESSION, 9])

    recipe = {
        'algorithm': 'ANGEL_DERIVED_CONTOUR_ORDER_R2',
        'stages': ['CHAOS', 'ORDER_1', 'ORDER_2', 'ORDER_LOCK'],
        'contours': [
            {
                'rank': i,
                'score': round(float(score), 5),
                'arc_length': round(float(arc), 3),
                'bbox_area': int(area),
                'points': points.tolist(),
            }
            for i, (score, arc, area, points) in enumerate(ordered)
        ]
    }
    with open(output_prefix + '_ordered_contours.json', 'w', encoding='utf-8') as fh:
        json.dump(recipe, fh, ensure_ascii=False, separators=(',', ':'))


if __name__ == '__main__':
    raise SystemExit('Import convert() and provide an input image plus output prefix.')
