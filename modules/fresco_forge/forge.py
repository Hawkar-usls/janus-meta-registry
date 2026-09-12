#!/usr/bin/env python3
"""JANUS Fresco Forge.

Turns canonical JSON records from the JANUS meta-registry into fresco images
with a local Diffusers Stable Diffusion pipeline. No hosted inference token is
required. Dedupe is content-addressed: SHA-256(canonical JSON) is the identity
of a generation request.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import torch
from diffusers import DPMSolverMultistepScheduler, StableDiffusionPipeline


GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v2.0-local-diffusers"
DEFAULT_MODEL = "dreamlike-art/dreamlike-photoreal-2.0"
DEFAULT_INPUT_ROOTS = ("registry",)
DEFAULT_OUTPUT_ROOT = "artifacts/janus-fresco-forge"
DEFAULT_STEPS = 20
DEFAULT_WIDTH = 512
DEFAULT_HEIGHT = 512

FRESCO_PREFIX = """Museum-grade narrative wall fresco based on the JSON source below.
Translate the record into a single coherent visual scene. Use the JSON as the semantic
source of truth: depict its entities, events, relationships, symbols, emotions,
chronology, tensions and contrasts rather than drawing software interfaces or text.

Visual language: monumental ancient/medieval fresco, aged lime plaster, mineral pigments,
subtle cracks and abrasion, hand-painted figures, architectural framing, solemn cinematic
composition, layered symbolic storytelling, dense meaningful details, expressive tears
and faces where the source implies grief or compassion, natural anatomy, believable hands,
historical material texture. No modern UI, no captions, no visible JSON, no logos."""

FRESCO_SUFFIX = """The final image should feel like a surviving historical fresco that
encodes the conceptual story of the source. Prefer meaningful symbolic detail over
decorative clutter."""

NEGATIVE_PROMPT = (
    "modern user interface, screenshot, JSON text, caption, watermark, logo, "
    "glossy 3d render, plastic skin, extra limbs, extra legs, extra fingers, "
    "duplicated people, deformed anatomy, malformed hands, illegible typography, "
    "nude, naked, explicit sexual content"
)


@dataclass(frozen=True)
class Candidate:
    path: Path
    relpath: str
    canonical_json: str
    source_sha256: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonicalize_json(path: Path) -> tuple[str, str]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = sha256_bytes(canonical.encode("utf-8"))
    return canonical, digest


def _scalar_text(value: object) -> str | None:
    if isinstance(value, str):
        value = " ".join(value.split())
        return value if value else None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return None


def visual_json_projection(canonical_json: str, max_chars: int = 3200) -> str:
    """Build a deterministic JSON-shaped visual projection.

    SD 1.5 has a short text encoder context. Feeding a huge registry record verbatim
    causes the tail to be silently discarded. We therefore keep the JSON-as-prompt
    contract while extracting scalar-bearing branches into a compact JSON object.
    The source hash and receipt still refer to the complete canonical JSON.
    """
    obj = json.loads(canonical_json)
    rows: list[tuple[str, str]] = []

    def walk(node: object, path: str) -> None:
        scalar = _scalar_text(node)
        if scalar is not None:
            rows.append((path or "value", scalar))
            return
        if isinstance(node, dict):
            for key, value in node.items():
                child = f"{path}.{key}" if path else str(key)
                walk(value, child)
        elif isinstance(node, list):
            for idx, value in enumerate(node):
                walk(value, f"{path}[{idx}]")

    walk(obj, "")
    projection: dict[str, str] = {}
    used = 2
    for path, value in rows:
        if len(value) > 360:
            value = value[:357] + "..."
        prospective = len(path) + len(value) + 8
        if used + prospective > max_chars:
            break
        projection[path] = value
        used += prospective

    return json.dumps(projection, ensure_ascii=False, separators=(",", ":"))


def build_prompt(canonical_json: str) -> tuple[str, str]:
    projected_json = visual_json_projection(canonical_json)
    prompt = (
        f"{FRESCO_PREFIX}\n\n"
        "SOURCE JSON VISUAL PROJECTION:\n"
        f"{projected_json}\n\n"
        f"{FRESCO_SUFFIX}"
    )
    return prompt, projected_json


def safe_stem(path: Path, limit: int = 72) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip("-._")
    if not stem:
        stem = "json-record"
    return stem[:limit]


def load_processed_hashes(ledger_path: Path) -> set[str]:
    processed: set[str] = set()
    if not ledger_path.exists():
        return processed

    for number, raw in enumerate(ledger_path.read_text(encoding="utf-8").splitlines(), 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"WARNING: malformed ledger line {number}: {exc}", file=sys.stderr)
            continue
        digest = row.get("source_sha256")
        if row.get("status") == "generated" and isinstance(digest, str):
            processed.add(digest)
    return processed


def collect_candidates(
    repo_root: Path,
    input_roots: Iterable[str],
    output_root: Path,
    processed: set[str],
    explicit_sources: Iterable[str] | None = None,
) -> list[Candidate]:
    paths: list[Path] = []

    if explicit_sources:
        for raw in explicit_sources:
            p = (repo_root / raw).resolve()
            try:
                p.relative_to(repo_root.resolve())
            except ValueError as exc:
                raise SystemExit(f"SOURCE_OUTSIDE_REPOSITORY:{raw}") from exc
            paths.append(p)
    else:
        for root_name in input_roots:
            root = (repo_root / root_name).resolve()
            if not root.exists():
                print(f"WARNING: input root does not exist: {root_name}", file=sys.stderr)
                continue
            paths.extend(root.rglob("*.json"))

    output_resolved = output_root.resolve()
    unique_paths = sorted({p.resolve() for p in paths}, key=lambda p: p.as_posix())
    seen_hashes = set(processed)
    candidates: list[Candidate] = []

    for path in unique_paths:
        if not path.is_file() or path.suffix.lower() != ".json":
            continue
        try:
            path.relative_to(output_resolved)
            continue
        except ValueError:
            pass

        try:
            relpath = path.relative_to(repo_root.resolve()).as_posix()
            canonical, digest = canonicalize_json(path)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            print(f"SKIP_INVALID_JSON {path}: {exc}", file=sys.stderr)
            continue

        if digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        candidates.append(Candidate(path, relpath, canonical, digest))

    return candidates


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def append_ledger(ledger_path: Path, payload: dict) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def create_pipeline(model: str) -> StableDiffusionPipeline:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    print(f"FRESCO_FORGE_DEVICE={device}")
    print(f"FRESCO_FORGE_MODEL={model}")

    pipe = StableDiffusionPipeline.from_pretrained(
        model,
        torch_dtype=dtype,
    )
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    pipe = pipe.to(device)

    if device == "cpu":
        pipe.enable_attention_slicing()
        pipe.enable_vae_slicing()

    return pipe


def generate_one(
    pipe: StableDiffusionPipeline,
    candidate: Candidate,
    repo_root: Path,
    output_root: Path,
    model: str,
    steps: int,
    width: int,
    height: int,
    seed: int,
) -> dict:
    prompt, projected_json = build_prompt(candidate.canonical_json)
    prompt_sha256 = sha256_bytes(prompt.encode("utf-8"))
    projection_sha256 = sha256_bytes(projected_json.encode("utf-8"))
    basename = f"{candidate.source_sha256[:16]}--{safe_stem(candidate.path)}"
    image_path = output_root / "images" / f"{basename}.png"
    receipt_path = output_root / "receipts" / f"{basename}.json"

    image_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    generator = torch.Generator(device=device).manual_seed(seed)
    start = time.monotonic()
    with torch.inference_mode():
        image = pipe(
            prompt=prompt,
            negative_prompt=NEGATIVE_PROMPT,
            num_inference_steps=steps,
            width=width,
            height=height,
            generator=generator,
        ).images[0]
    elapsed_seconds = round(time.monotonic() - start, 3)

    tmp_image = image_path.with_suffix(".tmp.png")
    image.save(tmp_image, format="PNG")
    tmp_image.replace(image_path)
    image_sha256 = sha256_bytes(image_path.read_bytes())

    receipt = {
        "schema": "janus.fresco_forge.receipt.v2",
        "generator": GENERATOR_VERSION,
        "status": "generated",
        "generated_at": utc_now(),
        "source_path": candidate.relpath,
        "source_sha256": candidate.source_sha256,
        "canonical_json_bytes": len(candidate.canonical_json.encode("utf-8")),
        "visual_projection_sha256": projection_sha256,
        "visual_projection_bytes": len(projected_json.encode("utf-8")),
        "prompt_sha256": prompt_sha256,
        "model": model,
        "backend": "local_diffusers",
        "device": device,
        "scheduler": pipe.scheduler.__class__.__name__,
        "steps": steps,
        "width": width,
        "height": height,
        "seed": seed,
        "elapsed_seconds": elapsed_seconds,
        "image_path": image_path.relative_to(repo_root).as_posix(),
        "receipt_path": receipt_path.relative_to(repo_root).as_posix(),
        "image_sha256": image_sha256,
    }
    write_json_atomic(receipt_path, receipt)
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=GENERATOR_VERSION)
    parser.add_argument("--repo-root", default=None, help="Repository root; auto-detected by default")
    parser.add_argument("--input-root", action="append", dest="input_roots", help="JSON root; repeatable")
    parser.add_argument("--source", action="append", help="Generate only this repository-relative JSON; repeatable")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--model", default=os.getenv("FRESCO_MODEL", DEFAULT_MODEL))
    parser.add_argument("--max-images", type=int, default=int(os.getenv("FRESCO_MAX_IMAGES", "1")))
    parser.add_argument("--steps", type=int, default=int(os.getenv("FRESCO_STEPS", str(DEFAULT_STEPS))))
    parser.add_argument("--width", type=int, default=int(os.getenv("FRESCO_WIDTH", str(DEFAULT_WIDTH))))
    parser.add_argument("--height", type=int, default=int(os.getenv("FRESCO_HEIGHT", str(DEFAULT_HEIGHT))))
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Discover/dedupe only; do not load the model")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_images < 1:
        raise SystemExit("--max-images must be >= 1")
    if args.steps < 1:
        raise SystemExit("--steps must be >= 1")
    if args.width % 8 or args.height % 8:
        raise SystemExit("--width and --height must be divisible by 8")

    auto_root = Path(__file__).resolve().parents[2]
    repo_root = Path(args.repo_root).resolve() if args.repo_root else auto_root
    output_root = (repo_root / args.output_root).resolve()
    ledger_path = output_root / "ledger.jsonl"
    input_roots = tuple(args.input_roots or DEFAULT_INPUT_ROOTS)

    processed = load_processed_hashes(ledger_path)
    candidates = collect_candidates(
        repo_root=repo_root,
        input_roots=input_roots,
        output_root=output_root,
        processed=processed,
        explicit_sources=args.source,
    )

    selected = candidates[: args.max_images]
    print(
        json.dumps(
            {
                "generator": GENERATOR_VERSION,
                "processed_hashes": len(processed),
                "new_unique_json": len(candidates),
                "selected": [
                    {"source_path": c.relpath, "source_sha256": c.source_sha256}
                    for c in selected
                ],
                "dry_run": args.dry_run,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.dry_run or not selected:
        return 0

    pipe = create_pipeline(args.model)
    generated = 0
    for idx, candidate in enumerate(selected):
        seed = args.seed if args.seed is not None else random.SystemRandom().randint(0, 2**32 - 1)
        if args.seed is not None:
            seed += idx
        print(f"GENERATING {candidate.relpath} sha256={candidate.source_sha256} seed={seed}")
        receipt = generate_one(
            pipe=pipe,
            candidate=candidate,
            repo_root=repo_root,
            output_root=output_root,
            model=args.model,
            steps=args.steps,
            width=args.width,
            height=args.height,
            seed=seed,
        )
        append_ledger(ledger_path, receipt)
        generated += 1
        print(
            f"GENERATED {receipt['image_path']} "
            f"sha256={receipt['image_sha256']} elapsed={receipt['elapsed_seconds']}s"
        )

    print(f"FRESCO_FORGE_GENERATED={generated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
