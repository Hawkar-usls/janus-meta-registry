#!/usr/bin/env python3
"""JANUS Fresco Forge.

Turns canonical JSON records from the JANUS meta-registry into fresco images
through Hugging Face Inference Providers. Dedupe is content-addressed: the
SHA-256 of canonical JSON is the identity of a generation request.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from huggingface_hub import InferenceClient


GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v1.0"
DEFAULT_MODEL = "black-forest-labs/FLUX.1-schnell"
DEFAULT_PROVIDER = "auto"
DEFAULT_INPUT_ROOTS = ("registry",)
DEFAULT_OUTPUT_ROOT = "artifacts/janus-fresco-forge"

FRESCO_PREFIX = """Create one museum-grade narrative wall fresco from the JSON record below.
The JSON is the semantic source of truth: visually translate its entities, events,
relationships, tensions, symbols, emotions, chronology, and contrasts. Preserve the
meaning rather than drawing computer interfaces or literal JSON text.

Visual language: monumental ancient/medieval fresco, aged lime plaster, mineral pigments,
subtle cracks and abrasion, hand-painted figures, layered symbolic storytelling,
architectural framing, solemn cinematic composition, dense small details worth examining,
strong readable human emotion, natural anatomy, historically plausible material texture.
No modern UI, no captions, no visible JSON, no logos, no watermark."""

FRESCO_SUFFIX = """The final image must feel like a surviving historical fresco that encodes
the full conceptual story of the source record in visual form. Prefer meaningful symbolic
detail over decorative clutter."""

NEGATIVE_PROMPT = (
    "modern user interface, screenshot, JSON text, caption, watermark, logo, "
    "glossy 3d render, plastic skin, extra limbs, extra fingers, duplicated people, "
    "deformed anatomy, malformed hands, illegible typography"
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


def build_prompt(canonical_json: str) -> str:
    return (
        f"{FRESCO_PREFIX}\n\n"
        "SOURCE JSON (canonical form):\n"
        f"{canonical_json}\n\n"
        f"{FRESCO_SUFFIX}"
    )


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

        # Content-addressed dedupe also suppresses renamed/copied duplicates in one run.
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


def generate_one(
    client: InferenceClient,
    candidate: Candidate,
    repo_root: Path,
    output_root: Path,
    model: str,
    provider: str,
) -> dict:
    prompt = build_prompt(candidate.canonical_json)
    prompt_sha256 = sha256_bytes(prompt.encode("utf-8"))
    basename = f"{candidate.source_sha256[:16]}--{safe_stem(candidate.path)}"
    image_path = output_root / "images" / f"{basename}.png"
    receipt_path = output_root / "receipts" / f"{basename}.json"

    image_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    image = client.text_to_image(
        prompt,
        model=model,
        negative_prompt=NEGATIVE_PROMPT,
    )

    tmp_image = image_path.with_suffix(".tmp.png")
    image.save(tmp_image, format="PNG")
    tmp_image.replace(image_path)
    image_sha256 = sha256_bytes(image_path.read_bytes())

    generated_at = utc_now()
    receipt = {
        "schema": "janus.fresco_forge.receipt.v1",
        "generator": GENERATOR_VERSION,
        "status": "generated",
        "generated_at": generated_at,
        "source_path": candidate.relpath,
        "source_sha256": candidate.source_sha256,
        "canonical_json_bytes": len(candidate.canonical_json.encode("utf-8")),
        "prompt_sha256": prompt_sha256,
        "model": model,
        "provider": provider,
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
    parser.add_argument("--provider", default=os.getenv("FRESCO_PROVIDER", DEFAULT_PROVIDER))
    parser.add_argument("--max-images", type=int, default=int(os.getenv("FRESCO_MAX_IMAGES", "1")))
    parser.add_argument("--dry-run", action="store_true", help="Discover/dedupe only; never call Hugging Face")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_images < 1:
        raise SystemExit("--max-images must be >= 1")

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

    token = os.getenv("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN is required for generation; add it as a GitHub Actions secret")

    client = InferenceClient(provider=args.provider, api_key=token)
    generated = 0
    for candidate in selected:
        print(f"GENERATING {candidate.relpath} sha256={candidate.source_sha256}")
        receipt = generate_one(
            client=client,
            candidate=candidate,
            repo_root=repo_root,
            output_root=output_root,
            model=args.model,
            provider=args.provider,
        )
        append_ledger(ledger_path, receipt)
        generated += 1
        print(f"GENERATED {receipt['image_path']} sha256={receipt['image_sha256']}")

    print(f"FRESCO_FORGE_GENERATED={generated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
