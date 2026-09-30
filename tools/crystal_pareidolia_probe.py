#!/usr/bin/env python3
"""Lightweight, annotation-free crystal pareidolia probe.

This tool does NOT determine whether a real face exists in a crystal. It measures
where a fixed computer-vision face detector fires on crystal imagery and how
those detections change under controlled image-space illumination transforms.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

import cv2
import numpy as np

USER_AGENT = "JANUS-Crystal-Pareidolia-Probe/0.1 (+https://github.com/Hawkar-usls/janus-meta-registry)"


@dataclass(frozen=True)
class Detection:
    variant: str
    x: int
    y: int
    w: int
    h: int
    width: int
    height: int

    def normalized_box(self) -> List[float]:
        return [
            round(self.x / self.width, 6),
            round(self.y / self.height, 6),
            round(self.w / self.width, 6),
            round(self.h / self.height, 6),
        ]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as r, dest.open("wb") as f:
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def resize_for_probe(image: np.ndarray, max_dim: int) -> np.ndarray:
    h, w = image.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    if scale == 1.0:
        return image
    return cv2.resize(
        image,
        (max(1, round(w * scale)), max(1, round(h * scale))),
        interpolation=cv2.INTER_AREA,
    )


def gamma_transform(image: np.ndarray, gamma: float) -> np.ndarray:
    if gamma <= 0:
        raise ValueError("gamma must be > 0")
    table = np.array(
        [((i / 255.0) ** gamma) * 255 for i in range(256)],
        dtype=np.uint8,
    )
    return cv2.LUT(image, table)


def directional_light(
    image: np.ndarray,
    direction: str,
    strength: float = 0.42,
) -> np.ndarray:
    """Image-space lighting proxy, not physical re-rendering."""
    h, w = image.shape[:2]
    if direction in {"left", "right"}:
        ramp = np.linspace(1.0 - strength, 1.0 + strength, w, dtype=np.float32)
        if direction == "left":
            ramp = ramp[::-1]
        field = np.tile(ramp[None, :], (h, 1))
    elif direction in {"top", "bottom"}:
        ramp = np.linspace(1.0 - strength, 1.0 + strength, h, dtype=np.float32)
        if direction == "top":
            ramp = ramp[::-1]
        field = np.tile(ramp[:, None], (1, w))
    else:
        raise ValueError(direction)
    out = image.astype(np.float32) * field[:, :, None]
    return np.clip(out, 0, 255).astype(np.uint8)


def variants(image: np.ndarray, mode: str = "image") -> List[Tuple[str, np.ndarray]]:
    if mode == "video":
        return [
            ("baseline", image),
            ("gamma_0.80", gamma_transform(image, 0.80)),
            ("gamma_1.25", gamma_transform(image, 1.25)),
        ]
    return [
        ("baseline", image),
        ("gamma_0.65", gamma_transform(image, 0.65)),
        ("gamma_0.85", gamma_transform(image, 0.85)),
        ("gamma_1.25", gamma_transform(image, 1.25)),
        ("gamma_1.55", gamma_transform(image, 1.55)),
        ("light_left", directional_light(image, "left")),
        ("light_right", directional_light(image, "right")),
        ("light_top", directional_light(image, "top")),
        ("light_bottom", directional_light(image, "bottom")),
    ]


def detect(
    image: np.ndarray,
    cascade: cv2.CascadeClassifier,
    variant: str,
) -> List[Detection]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Mild local contrast normalization makes the detector less dependent on a
    # single global exposure while still leaving the source geometry untouched.
    clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    h, w = gray.shape[:2]
    min_side = max(20, round(min(h, w) * 0.045))
    boxes = cascade.detectMultiScale(
        gray,
        scaleFactor=1.05,
        minNeighbors=3,
        minSize=(min_side, min_side),
        flags=cv2.CASCADE_SCALE_IMAGE,
    )
    return [
        Detection(variant, int(x), int(y), int(bw), int(bh), w, h)
        for (x, y, bw, bh) in boxes
    ]


def iou(a: Detection, b: Detection) -> float:
    # Compare in normalized coordinates so resized sources remain comparable.
    ax1, ay1, aw, ah = a.normalized_box()
    bx1, by1, bw, bh = b.normalized_box()
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx2, by2 = bx1 + bw, by1 + bh
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def cluster_detections(
    detections: Sequence[Detection],
    variant_count: int,
    threshold: float = 0.24,
) -> List[dict]:
    clusters: List[List[Detection]] = []
    for det in detections:
        best_idx = None
        best_iou = 0.0
        for idx, cluster in enumerate(clusters):
            score = max(iou(det, existing) for existing in cluster)
            if score >= threshold and score > best_iou:
                best_idx, best_iou = idx, score
        if best_idx is None:
            clusters.append([det])
        else:
            clusters[best_idx].append(det)

    out = []
    for idx, cluster in enumerate(clusters, start=1):
        variants_seen = sorted({d.variant for d in cluster})
        boxes = np.array(
            [d.normalized_box() for d in cluster],
            dtype=np.float64,
        )
        persistence = len(variants_seen) / max(1, variant_count)
        out.append(
            {
                "candidate_id": f"C{idx:03d}",
                "variants_seen": variants_seen,
                "variant_hits": len(variants_seen),
                "persistence": round(persistence, 6),
                "median_normalized_box": [
                    round(float(v), 6) for v in np.median(boxes, axis=0)
                ],
                "classification": (
                    "PERSISTENT_DETECTOR_CANDIDATE"
                    if len(variants_seen) >= 3 and persistence >= 0.34
                    else "LIGHT_SENSITIVE_DETECTOR_CANDIDATE"
                ),
            }
        )
    out.sort(key=lambda x: (-x["persistence"], x["candidate_id"]))
    return out


def analyze_image_array(
    image: np.ndarray,
    cascade: cv2.CascadeClassifier,
    max_dim: int,
    mode: str = "image",
) -> dict:
    image = resize_for_probe(image, max_dim)
    all_dets: List[Detection] = []
    per_variant = {}
    vlist = variants(image, mode=mode)
    for name, transformed in vlist:
        dets = detect(transformed, cascade, name)
        all_dets.extend(dets)
        per_variant[name] = {
            "count": len(dets),
            "boxes_normalized": [d.normalized_box() for d in dets],
        }
    clusters = cluster_detections(all_dets, len(vlist))
    return {
        "probe_resolution": [int(image.shape[1]), int(image.shape[0])],
        "variant_count": len(vlist),
        "detections_total": len(all_dets),
        "per_variant": per_variant,
        "candidate_clusters": clusters,
        "persistent_candidate_count": sum(
            c["classification"] == "PERSISTENT_DETECTOR_CANDIDATE"
            for c in clusters
        ),
        "interpretation_ceiling": "DETECTOR_RESPONSE_ONLY_NOT_EVIDENCE_OF_A_REAL_FACE",
    }


def analyze_image_source(
    source: dict,
    path: Path,
    cascade: cv2.CascadeClassifier,
    max_dim: int,
) -> dict:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError(f"Could not decode image: {path}")
    result = analyze_image_array(image, cascade, max_dim, mode="image")
    result["sha256"] = sha256_file(path)
    return result


def analyze_video_source(
    source: dict,
    path: Path,
    cascade: cv2.CascadeClassifier,
    max_dim: int,
    samples: int,
) -> dict:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not decode video: {path}")
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if frame_count <= 0:
        raise RuntimeError("Video frame count unavailable")
    indexes = sorted(
        set(np.linspace(0, frame_count - 1, max(1, samples), dtype=int).tolist())
    )
    frames = []
    any_detections = 0
    for idx in indexes:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        r = analyze_image_array(frame, cascade, max_dim, mode="video")
        any_detections += r["detections_total"]
        frames.append(
            {
                "frame_index": int(idx),
                "time_seconds": round(idx / fps, 4) if fps > 0 else None,
                **r,
            }
        )
    cap.release()
    return {
        "sha256": sha256_file(path),
        "frame_count": frame_count,
        "fps": round(fps, 6),
        "requested_samples": samples,
        "decoded_samples": len(frames),
        "sampled_frames": frames,
        "detections_total": any_detections,
        "interpretation_ceiling": "DETECTOR_RESPONSE_ONLY_NOT_EVIDENCE_OF_A_REAL_FACE",
    }


def resolve_sketchfab_preview(source: dict) -> Tuple[str, dict]:
    uid = source["model_uid"]
    data = fetch_json(f"https://api.sketchfab.com/v3/models/{uid}")
    images = data.get("thumbnails", {}).get("images", [])
    if not images:
        raise RuntimeError(f"Sketchfab model {uid} has no public thumbnail")
    best = max(
        images,
        key=lambda x: int(x.get("width", 0)) * int(x.get("height", 0)),
    )
    return best["url"], {
        "model_name": data.get("name"),
        "model_uid": uid,
        "viewer_url": source.get("page_url"),
        "thumbnail_width": best.get("width"),
        "thumbnail_height": best.get("height"),
        "geometry_analyzed": False,
        "geometry_note": (
            "Sketchfab geometry download requires authenticated Download API; "
            "CI analyzes the public model render only."
        ),
    }


def source_url_and_suffix(source: dict) -> Tuple[str, str, dict]:
    kind = source["kind"]
    if kind == "sketchfab_model_preview":
        url, meta = resolve_sketchfab_preview(source)
        suffix = Path(url.split("?", 1)[0]).suffix or ".jpg"
        return url, suffix, meta
    url = source["download_url"]
    suffix = Path(url.split("?", 1)[0]).suffix or (
        ".webm" if kind == "video" else ".img"
    )
    return url, suffix, {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-dim", type=int, default=960)
    ap.add_argument("--video-samples", type=int, default=8)
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        raise RuntimeError(f"Could not load OpenCV cascade: {cascade_path}")

    report = {
        "schema": "janus.crystal_pareidolia_probe.result.v1",
        "method": {
            "detector": "OpenCV haarcascade_frontalface_default.xml",
            "human_face_annotations_used": False,
            "max_probe_dimension": args.max_dim,
            "image_variants": [
                "baseline",
                "gamma 0.65/0.85/1.25/1.55",
                "directional image-space light proxy left/right/top/bottom",
            ],
            "video_variants": ["baseline", "gamma 0.80/1.25"],
            "claim_ceiling": (
                "A detector firing on a crystal is a pareidolia candidate, "
                "not evidence of a person/entity inside the crystal."
            ),
        },
        "sources": [],
    }

    with tempfile.TemporaryDirectory(prefix="janus-crystal-") as td:
        temp = Path(td)
        for i, source in enumerate(manifest["sources"], start=1):
            entry = {k: v for k, v in source.items() if k not in {"download_url"}}
            entry["status"] = "PENDING"
            try:
                url, suffix, extra = source_url_and_suffix(source)
                path = temp / f"source_{i}{suffix}"
                fetch(url, path)
                if source["kind"] in {"image", "sketchfab_model_preview"}:
                    analysis = analyze_image_source(
                        source,
                        path,
                        cascade,
                        args.max_dim,
                    )
                elif source["kind"] == "video":
                    analysis = analyze_video_source(
                        source,
                        path,
                        cascade,
                        args.max_dim,
                        args.video_samples,
                    )
                else:
                    raise ValueError(f"Unsupported source kind: {source['kind']}")
                entry.update(extra)
                entry["status"] = "ANALYZED"
                entry["analysis"] = analysis
            except Exception as exc:
                entry["status"] = "ERROR"
                entry["error"] = f"{type(exc).__name__}: {exc}"
            report["sources"].append(entry)

    analyzed = [s for s in report["sources"] if s["status"] == "ANALYZED"]
    errors = [s for s in report["sources"] if s["status"] == "ERROR"]
    report["summary"] = {
        "source_count": len(report["sources"]),
        "analyzed_count": len(analyzed),
        "error_count": len(errors),
        "result_semantics": "OBSERVATIONAL_DETECTOR_RESPONSE",
    }

    report_path = out_dir / "crystal_pareidolia_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    md = [
        "# Crystal pareidolia probe",
        "",
        f"Analyzed: **{len(analyzed)}/{len(report['sources'])}** sources; errors: **{len(errors)}**.",
        "",
        (
            "The detector runs without human face annotations. A hit is only a "
            "*face-like detector response* and does not establish a real face "
            "or entity in a crystal."
        ),
        "",
        "| Source | Kind | Status | Detector hits | Persistent clusters |",
        "|---|---|---:|---:|---:|",
    ]
    for s in report["sources"]:
        hits = "-"
        persistent = "-"
        if s["status"] == "ANALYZED":
            a = s["analysis"]
            hits = str(a.get("detections_total", 0))
            if s["kind"] == "video":
                persistent = str(
                    sum(
                        f.get("persistent_candidate_count", 0)
                        for f in a.get("sampled_frames", [])
                    )
                )
            else:
                persistent = str(a.get("persistent_candidate_count", 0))
        md.append(
            f"| {s['id']} | {s['kind']} | {s['status']} | {hits} | {persistent} |"
        )
    summary_path = out_dir / "SUMMARY.md"
    summary_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(summary_path.read_text(encoding="utf-8"))

    # Network/source errors fail CI because a partial run is not a valid receipt.
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
