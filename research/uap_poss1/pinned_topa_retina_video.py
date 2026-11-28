#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TOPA Retina Video Bridge v1.0

Transport-agnostic, evidence-preserving video acquisition and visual inspection
bridge for TOPA hunts.

Lineage:
- JANUS mod_retina.py: image -> base64 -> Gemini Vision
- JANUS Telegram Bot Hub: normalize grounded vision results, keep transport
  separate from perception

This implementation intentionally does NOT import Telegram transport, tokens,
runtime configuration, or live JANUS databases.

Core rule:
    SOURCE BYTES -> HASH -> FFPROBE -> DETERMINISTIC FRAME SAMPLES
    -> FRAME HASHES + PTS -> CONTACT SHEETS -> OPTIONAL RETINA ANALYSIS

Sampling/contact sheets are for visual access and QC. They are NOT a substitute
for full-rate detection when a scientific gate requires it.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".mts", ".m2ts", ".ts"
}

DEFAULT_RETINA_MODEL = os.environ.get("TOPA_RETINA_MODEL", "gemini-2.5-flash")
RETINA_API_KEY_ENV = "TOPA_RETINA_API_KEY"


class TopaVideoError(RuntimeError):
    pass


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def safe_slug(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip())
    return text.strip("-") or "video"


def run_checked(cmd: list[str], *, capture: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            check=True,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
    except FileNotFoundError as exc:
        raise TopaVideoError(f"Required executable not found: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise TopaVideoError(f"Command failed: {' '.join(cmd)}\n{detail[-4000:]}") from exc


def is_http_url(value: str) -> bool:
    try:
        return urllib.parse.urlparse(value).scheme in {"http", "https"}
    except Exception:
        return False


def is_google_drive_url(value: str) -> bool:
    host = urllib.parse.urlparse(value).netloc.lower()
    return host.endswith("drive.google.com") or host.endswith("docs.google.com")


def is_google_drive_folder(value: str) -> bool:
    return is_google_drive_url(value) and "/folders/" in value


def download_http(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "TOPA-Retina-Video/1.0 (+https://github.com/Hawkar-usls/TOPA)"},
    )
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out)
    return destination


def acquire_google_drive(url: str, out_dir: Path) -> list[Path]:
    """
    Public Google Drive acquisition through gdown.

    Folder UI is treated as discovery only. The resulting local filenames and
    content hashes become the reproducible acquisition snapshot.
    """
    try:
        import gdown  # type: ignore
    except ImportError as exc:
        raise TopaVideoError(
            "Google Drive source detected but gdown is not installed. "
            "Install with: python -m pip install gdown"
        ) from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    before = {p.resolve() for p in out_dir.rglob("*") if p.is_file()}

    if is_google_drive_folder(url):
        result = gdown.download_folder(
            url=url,
            output=str(out_dir),
            quiet=False,
            use_cookies=False,
            remaining_ok=True,
        )
        if result is None:
            raise TopaVideoError("gdown could not enumerate/download the public Drive folder")
    else:
        # A directory output lets gdown preserve the remote filename/extension.
        # Keeping the original extension matters because downstream video
        # detection must not depend on guessed MIME types.
        result = gdown.download(
            url=url,
            output=str(out_dir) + os.sep,
            quiet=False,
            fuzzy=True,
            use_cookies=False,
        )
        if result is None:
            raise TopaVideoError("gdown could not download the public Drive file")

    after = [p.resolve() for p in out_dir.rglob("*") if p.is_file()]
    created = [p for p in after if p not in before]
    return sorted(Path(p) for p in created)


def acquire_source(source: str, acquired_dir: Path) -> list[Path]:
    p = Path(source).expanduser()
    if p.exists():
        if p.is_file():
            return [p.resolve()]
        return sorted(x.resolve() for x in p.rglob("*") if x.is_file())

    if not is_http_url(source):
        raise TopaVideoError(f"Source does not exist and is not an HTTP(S) URL: {source}")

    if is_google_drive_url(source):
        return acquire_google_drive(source, acquired_dir / "google-drive")

    parsed = urllib.parse.urlparse(source)
    name = Path(parsed.path).name or "downloaded-video"
    target = acquired_dir / safe_slug(name)
    return [download_http(source, target).resolve()]


def iter_video_files(paths: Iterable[Path]) -> list[Path]:
    videos = [p for p in paths if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS]
    return sorted(videos)


def ffprobe(path: Path) -> dict[str, Any]:
    proc = run_checked([
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-of", "json", str(path)
    ])
    return json.loads(proc.stdout or "{}")


@dataclass
class FrameRecord:
    index: int
    file: str
    pts_time_s: float | None
    sha256: str
    bytes: int


SHOWINFO_RE = re.compile(r"\bn:\s*(\d+).*?\bpts_time:([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")


def extract_sample_frames(
    video: Path,
    frames_dir: Path,
    sample_every_s: float,
    max_frames: int,
    max_width: int,
) -> list[FrameRecord]:
    if sample_every_s <= 0:
        raise TopaVideoError("sample_every_s must be > 0")

    frames_dir.mkdir(parents=True, exist_ok=True)
    out_pattern = frames_dir / "frame-%08d.jpg"

    vf = (
        f"fps=1/{sample_every_s},"
        "showinfo,"
        f"scale={max_width}:-2:force_original_aspect_ratio=decrease"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "info", "-i", str(video),
        "-map", "0:v:0", "-an", "-sn", "-dn",
        "-vf", vf,
        "-q:v", "3",
    ]
    if max_frames > 0:
        cmd += ["-frames:v", str(max_frames)]
    cmd += ["-y", str(out_pattern)]

    try:
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise TopaVideoError("Required executable not found: ffmpeg") from exc
    if proc.returncode != 0:
        raise TopaVideoError(f"ffmpeg frame extraction failed:\n{proc.stderr[-4000:]}")

    pts_values: list[float] = []
    for line in (proc.stderr or "").splitlines():
        m = SHOWINFO_RE.search(line)
        if m:
            pts_values.append(float(m.group(2)))

    frame_files = sorted(frames_dir.glob("frame-*.jpg"))
    records: list[FrameRecord] = []
    for i, frame in enumerate(frame_files, start=1):
        pts = pts_values[i - 1] if i - 1 < len(pts_values) else None
        records.append(FrameRecord(
            index=i,
            file=frame.name,
            pts_time_s=pts,
            sha256=sha256_file(frame),
            bytes=frame.stat().st_size,
        ))
    return records


def build_contact_sheets(frames_dir: Path, output_dir: Path) -> list[Path]:
    first = frames_dir / "frame-00000001.jpg"
    if not first.exists():
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "contact-%04d.jpg"
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-framerate", "1", "-i", str(frames_dir / "frame-%08d.jpg"),
        "-vf", "scale=320:-2,tile=5x4:padding=2:margin=2",
        "-vsync", "vfr", "-q:v", "4", "-y", str(pattern),
    ]
    try:
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise TopaVideoError("Required executable not found: ffmpeg") from exc
    if proc.returncode != 0:
        raise TopaVideoError(f"ffmpeg contact-sheet generation failed:\n{proc.stderr[-4000:]}")
    return sorted(output_dir.glob("contact-*.jpg"))


def gemini_retina(frame: Path, prompt: str, model: str, api_key: str) -> dict[str, Any]:
    mime, _ = mimetypes.guess_type(str(frame))
    mime = mime or "image/jpeg"
    encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": encoded}},
            ]
        }],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(model, safe='-._')}:generateContent?key="
        f"{urllib.parse.quote(api_key, safe='')}"
    )
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        data = json.loads(response.read().decode("utf-8"))
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = {"raw_text": text}
    return parsed


def retina_prompt() -> str:
    return (
        "TOPA RETINA VISUAL INSPECTION. Analyze only what is visible in this frame. "
        "Do not infer paranormal or extraterrestrial origin. Return JSON with keys: "
        "summary, visible_objects, light_sources, tracks_or_streaks, optical_artifact_candidates, "
        "weather_or_sky_context, uncertainty, followup_needed. "
        "If the frame is insufficient, say so explicitly."
    )


def analyze_frames_with_retina(
    frames_dir: Path,
    records: list[FrameRecord],
    output_jsonl: Path,
    model: str,
    max_frames: int,
) -> int:
    api_key = os.environ.get(RETINA_API_KEY_ENV, "").strip()
    if not api_key:
        raise TopaVideoError(
            f"--retina requested but {RETINA_API_KEY_ENV} is not set"
        )
    selected = records[: max_frames if max_frames > 0 else len(records)]
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_jsonl.open("w", encoding="utf-8") as out:
        for rec in selected:
            frame = frames_dir / rec.file
            result: dict[str, Any]
            try:
                result = gemini_retina(frame, retina_prompt(), model, api_key)
                status = "OK"
            except Exception as exc:
                result = {"error": str(exc)}
                status = "ERROR"
            row = {
                "frame_index": rec.index,
                "pts_time_s": rec.pts_time_s,
                "frame_sha256": rec.sha256,
                "status": status,
                "model": model,
                "analysis": result,
                "world_truth": False,
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def load_source_manifest(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("sources", [])
    if not isinstance(raw, list):
        raise TopaVideoError("manifest.sources must be an array")
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            value = item.get("url") or item.get("path") or item.get("source")
            if value:
                out.append(str(value))
    if not out:
        raise TopaVideoError("manifest contains no usable sources")
    return out


def process_video(
    video: Path,
    source_label: str,
    run_root: Path,
    sample_every_s: float,
    max_frames: int,
    max_width: int,
    retina: bool,
    retina_model: str,
    retina_max: int,
) -> dict[str, Any]:
    digest = sha256_file(video)
    stem = safe_slug(video.stem)
    unit_dir = run_root / f"{stem}-{digest[:12]}"
    frames_dir = unit_dir / "frames"
    sheets_dir = unit_dir / "contact_sheets"
    unit_dir.mkdir(parents=True, exist_ok=True)

    probe = ffprobe(video)
    records = extract_sample_frames(
        video, frames_dir, sample_every_s, max_frames, max_width
    )
    sheets = build_contact_sheets(frames_dir, sheets_dir)

    frame_manifest = {
        "schema": "janus.topa.retina.frame-manifest.v1",
        "created_at_utc": utc_now(),
        "source_video": str(video),
        "source_label": source_label,
        "source_sha256": digest,
        "sampling": {
            "mode": "DETERMINISTIC_INTERVAL_SAMPLE_FOR_VISUAL_ACCESS_QC",
            "sample_every_s": sample_every_s,
            "max_frames": max_frames,
            "max_width": max_width,
            "full_rate_detection_implied": False,
        },
        "frames": [asdict(r) for r in records],
        "world_truth": False,
    }
    (unit_dir / "frame_manifest.json").write_text(
        json.dumps(frame_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    retina_count = 0
    if retina and records:
        retina_count = analyze_frames_with_retina(
            frames_dir,
            records,
            unit_dir / "retina_results.jsonl",
            retina_model,
            retina_max,
        )

    result = {
        "schema": "janus.topa.retina.video-unit.v1",
        "created_at_utc": utc_now(),
        "source_label": source_label,
        "local_path": str(video),
        "bytes": video.stat().st_size,
        "sha256": digest,
        "ffprobe": probe,
        "frame_sample_count": len(records),
        "contact_sheets": [str(p.relative_to(unit_dir)) for p in sheets],
        "retina_frames_analyzed": retina_count,
        "unit_dir": str(unit_dir),
        "claim_boundary": (
            "Successful decoding or visual recognition establishes only what was "
            "decoded/recognized in source-bound media; it does not establish cause."
        ),
        "world_truth": False,
    }
    (unit_dir / "video_manifest.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def self_test() -> int:
    payload = b"TOPA_RETINA_VIDEO_SELF_TEST\n"
    expected = hashlib.sha256(payload).hexdigest()
    if expected != "f917971a4c16d676dc0863b93045b023d3322c669ba3ddc40517fcd585086c8c":
        actual = hashlib.sha256(payload).hexdigest()
        print(f"TOPA_RETINA_VIDEO_SELF_TEST=FAIL digest={actual}")
        return 1
    print("TOPA_RETINA_VIDEO_SELF_TEST=PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evidence-preserving TOPA Retina bridge for local/HTTP/public Google Drive video."
    )
    parser.add_argument("source", nargs="?", help="local file/dir, HTTP(S) URL, public Google Drive URL, or manifest path")
    parser.add_argument("--manifest", action="store_true", help="treat SOURCE as JSON with a sources[] array")
    parser.add_argument("--out", default="topa_retina_run", help="output directory")
    parser.add_argument("--sample-every", type=float, default=10.0, help="visual-QC sample interval in seconds")
    parser.add_argument("--max-frames", type=int, default=0, help="cap sampled frames per video; 0 means no cap")
    parser.add_argument("--max-width", type=int, default=1280, help="sampled-frame maximum width")
    parser.add_argument("--retina", action="store_true", help="run optional Gemini Retina analysis on sampled frames")
    parser.add_argument("--retina-model", default=DEFAULT_RETINA_MODEL)
    parser.add_argument("--retina-max", type=int, default=64, help="maximum sampled frames sent to Retina per video")
    parser.add_argument("--self-test", action="store_true", help="run dependency-free internal self-test")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if not args.source:
        parser.error("SOURCE is required unless --self-test is used")

    run_root = Path(args.out).expanduser().resolve()
    acquired_dir = run_root / "acquired"
    run_root.mkdir(parents=True, exist_ok=True)

    sources = (
        load_source_manifest(Path(args.source).expanduser())
        if args.manifest
        else [args.source]
    )

    acquisition_rows: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []

    for source in sources:
        paths = acquire_source(source, acquired_dir)
        files = [p for p in paths if p.is_file()]
        row_files = []
        for p in sorted(files):
            item = {
                "path": str(p),
                "bytes": p.stat().st_size,
                "sha256": sha256_file(p),
                "is_video": p.suffix.lower() in VIDEO_EXTENSIONS,
            }
            row_files.append(item)
        acquisition_rows.append({
            "source": source,
            "acquired_at_utc": utc_now(),
            "files": row_files,
        })

        videos = iter_video_files(files)
        for video in videos:
            units.append(process_video(
                video=video,
                source_label=source,
                run_root=run_root / "videos",
                sample_every_s=args.sample_every,
                max_frames=args.max_frames,
                max_width=args.max_width,
                retina=args.retina,
                retina_model=args.retina_model,
                retina_max=args.retina_max,
            ))

    run_manifest = {
        "schema": "janus.topa.retina.video-run.v1",
        "created_at_utc": utc_now(),
        "sources": sources,
        "acquisition": acquisition_rows,
        "video_units": units,
        "video_count": len(units),
        "retina_enabled": bool(args.retina),
        "retina_model": args.retina_model if args.retina else None,
        "source_mutated": False,
        "raw_deleted": False,
        "sampling_is_full_rate_detection": False,
        "drive_folder_ui_is_provenance_authority": False,
        "claim_boundary": (
            "This bridge makes media reproducibly viewable and hash-bound. "
            "It does not classify unexplained content as extraordinary and does "
            "not replace the frozen K1 full-rate detection/classification gates."
        ),
        "world_truth": False,
    }
    (run_root / "RUN.json").write_text(
        json.dumps(run_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"TOPA_RETINA_VIDEO_RUN=COMPLETE videos={len(units)} out={run_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
