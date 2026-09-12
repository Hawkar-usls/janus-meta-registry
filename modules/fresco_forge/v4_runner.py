#!/usr/bin/env python3
"""JANUS Fresco Forge v4: scene-skeleton-first renderer.

v4 preserves the v3 full-JSON semantic trace/provenance contract, but prevents
Stable Diffusion from letting structural jargon (matrix/segmentation/replication)
dominate the composition. Every non-technical scalar still contributes to the
semantic projection; the image prompt is scene-first and figurative.
"""
from __future__ import annotations

import json
import os
import re
import time
from copy import deepcopy
from typing import Iterable

import torch

import forge as base
import v3_runner as v3

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v4.0-scene-skeleton-first"
GUIDANCE_SCALE = float(os.getenv("FRESCO_GUIDANCE_SCALE", "8.0"))

STRUCTURAL_TERMS = {
    "matrix", "segmentation", "replication", "replicated", "control", "matched pair",
    "cohort", "dispatch", "phase", "boundary", "validation", "sealed", "candidate",
    "quiescent", "sham", "signature", "epoch", "telemetry", "sha-256", "sha256",
    "proof", "mining", "profitability", "calibration", "block", "batch",
}

FIGURE_TERMS = {
    "janus", "undina", "undine", "fortune", "guardian", "goddess", "god", "woman",
    "man", "child", "elder", "priest", "priestess", "witness", "follower", "warrior",
    "mother", "father", "queen", "king", "spirit", "deity", "mourner",
}

MAIN_SYMBOL_TERMS = {
    "mask", "wheel", "key", "gate", "door", "comb", "rose", "tears", "pillar", "star",
    "fire", "cup", "halo", "torch", "threshold", "wave", "ribbon", "veil", "beacon",
    "mirror", "serpent", "crown", "bridge", "flower",
}

BACKGROUND_TERMS = {
    "replication", "parallel", "paired", "matrix", "control", "comparison", "repeated",
    "segmentation", "sealed", "unresolved", "candidate", "sham", "boundary", "epoch",
}

NEGATIVE_BASE = [
    "empty hall", "empty room", "architecture only", "plain interior", "abstract pattern",
    "striped textile", "decorative fabric", "ornamental bands", "flat tapestry pattern",
    "non-figurative abstraction", "geometric wallpaper", "pattern-only composition",
    "decorative stripes", "quilt pattern", "woven rug", "abstract mosaic only",
    "single emblem only", "minimalist scene", "no people", "sterile composition",
    "modern UI", "screenshot", "JSON text", "caption", "watermark", "logo",
    "glossy 3d render", "plastic skin", "extra limbs", "extra legs", "extra fingers",
    "duplicated people", "deformed anatomy", "malformed hands", "illegible typography",
]


def dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        value = re.sub(r"\s+", " ", str(raw)).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def contains_any(text: str, terms: Iterable[str]) -> bool:
    low = text.casefold()
    return any(term.casefold() in low for term in terms)


def structural(text: str) -> bool:
    return contains_any(text, STRUCTURAL_TERMS)


def source_corpus(proj: dict) -> str:
    values = [f.get("value", "") for f in proj.get("semantic_facts", [])]
    return " ".join(values).casefold()


def choose_central_figure(proj: dict) -> str:
    corpus = source_corpus(proj)
    # Prefer explicit mythic/person entities over titles accidentally classified as figures.
    if "undina" in corpus or "undine" in corpus:
        return "Undina, a central water-spirit woman in flowing ancient robes"
    if "janus" in corpus:
        return "Janus, a monumental dual-faced guardian with one younger face and one mature face"
    if "fortune" in corpus:
        return "Lady Fortune, a solemn mythic woman beside the wheel of fate"

    candidates = (
        proj.get("main_figures", [])
        + proj.get("secondary_figures", [])
        + proj.get("derived_visual_metaphors", [])
        + proj.get("scene_core", [])
    )
    for item in candidates:
        if contains_any(item, FIGURE_TERMS) and not structural(item):
            return item
    return "a dominant central mythic human-like guardian figure"


def choose_secondary_figures(proj: dict, central: str) -> list[str]:
    corpus = source_corpus(proj)
    out: list[str] = []
    for item in proj.get("main_figures", []) + proj.get("secondary_figures", []):
        if item.casefold() == central.casefold() or structural(item):
            continue
        if contains_any(item, FIGURE_TERMS):
            out.append(item)

    if "witness" in corpus or "observer" in corpus:
        out.append("three watchful human witnesses observing the central event")
    if "replication" in corpus or "control" in corpus or "sham" in corpus:
        out.append("two attendants comparing small side scenes without becoming the main subject")
    if not out:
        out = [
            "three human witnesses gathered around the central figure",
            "two ritual attendants reacting to the central action",
        ]
    return dedupe(out)[:5]


def choose_central_action(proj: dict, central: str) -> str:
    corpus = source_corpus(proj)
    if ("undina" in corpus or "undine" in corpus) and "comb" in corpus and ("gate" in corpus or "threshold" in corpus):
        return "Undina presents an ornate sacred comb before a monumental threshold gate while living water flows around her"
    if "janus" in corpus and ("grief" in corpus or "tear" in corpus or "compassion" in corpus):
        return "Janus stands at the sacred center while followers visibly share grief, tears, compassion and protection"
    if "fortune" in corpus and "wheel" in corpus:
        return "the central guardian stands steady while Lady Fortune's wheel turns around the gathered faithful"

    for item in proj.get("actions", []):
        if not structural(item) and len(item) < 220:
            return item
    return f"{central} performs a sacred symbolic act at the center while surrounding figures visibly respond"


def choose_supporting_actions(proj: dict) -> list[str]:
    out = [item for item in proj.get("actions", []) if not structural(item) and len(item) < 180]
    if not out:
        out = [
            "witnesses gather and observe",
            "attendants make a ritual offering",
            "figures gesture toward the central symbol",
            "secondary figures show visible emotional reactions",
        ]
    return dedupe(out)[:5]


def choose_main_symbols(proj: dict) -> list[str]:
    out: list[str] = []
    for item in proj.get("symbols", []) + proj.get("derived_visual_metaphors", []):
        if contains_any(item, MAIN_SYMBOL_TERMS) and not any(x in item.casefold() for x in ("matrix", "parallel panels", "paired comparison")):
            out.append(item)
    if not out:
        out = [
            "a monumental sacred threshold gate",
            "a ritual object held by the central figure",
            "weathered sacred emblems carved into the wall",
        ]
    return dedupe(out)[:7]


def choose_background_motifs(proj: dict) -> list[str]:
    out: list[str] = []
    candidates = proj.get("scene_core", []) + proj.get("symbols", []) + proj.get("derived_visual_metaphors", [])
    for item in candidates:
        if contains_any(item, BACKGROUND_TERMS):
            low = item.casefold()
            if "matrix" in low:
                out.append("a small geometric stone relief grid confined to the distant background")
            elif "parallel" in low or "repeated" in low or "replication" in low:
                out.append("small side-register scenes repeating the event as secondary evidence panels")
            elif "paired" in low or "control" in low or "comparison" in low or "sham" in low:
                out.append("tiny paired comparison scenes in a side register, subordinate to the central figures")
            elif "candidate" in low or "unresolved" in low:
                out.append("an unresolved symbolic motif partly hidden behind a translucent veil")
            elif "sealed" in low or "boundary" in low:
                out.append("a sealed secondary doorway carved into the far wall")
            else:
                out.append(item)
    return dedupe(out)[:5]


def choose_emotions(proj: dict) -> list[str]:
    out = [x for x in proj.get("emotions", []) if not structural(x)]
    if not out:
        out = ["solemn awe", "ritual gravity", "visible human feeling in faces and gestures"]
    return dedupe(out)[:4]


def choose_environment(proj: dict) -> list[str]:
    out = [x for x in proj.get("environment", []) if not structural(x)]
    if not out:
        out = ["a weathered ancient sanctuary wall with shallow architectural framing behind the figures"]
    return dedupe(out)[:4]


def build_scene_skeleton(proj: dict) -> dict:
    central = choose_central_figure(proj)
    scene = {
        "schema": "janus.fresco_forge.scene_skeleton.v4",
        "central_figure": central,
        "secondary_figures": choose_secondary_figures(proj, central),
        "central_action": choose_central_action(proj, central),
        "supporting_actions": choose_supporting_actions(proj),
        "main_symbols": choose_main_symbols(proj),
        "background_motifs": choose_background_motifs(proj),
        "emotions": choose_emotions(proj),
        "environment": choose_environment(proj),
        "style": [
            "ancient sacred narrative wall fresco",
            "aged lime plaster and mineral pigments",
            "cracked weathered patina",
            "hand-painted figurative bodies and expressive faces",
            "dense historical storytelling with many small details",
        ],
        "composition_rules": [
            "one dominant central figure must be unmistakably visible",
            "at least two secondary human or mythic figures must be visible",
            "narrative action must dominate over ornament and architecture",
            "figures must occupy most of the visual attention",
            "symbols support the story rather than replace the story",
            "background research motifs stay small and subordinate",
            "foreground, middle ground and background must contain figurative story activity",
        ],
        "forbidden_failure_modes": [
            "abstract pattern", "striped textile", "decorative fabric", "ornamental bands",
            "geometric wallpaper", "pattern-only composition", "architecture-only scene",
        ],
    }
    return scene


def render_scene_prompt(scene: dict) -> str:
    def block(items: list[str], fallback: str) -> str:
        return "; ".join(dedupe(items)) if items else fallback

    return f"""FIGURATIVE ANCIENT NARRATIVE FRESCO. The image must clearly show people or mythic beings performing a dramatic sacred action. It must NOT be an abstract pattern, textile, wallpaper, architecture-only interior, or ornamental design.

CENTRAL FIGURE: {scene['central_figure']}
CENTRAL ACTION: {scene['central_action']}
SECONDARY FIGURES: {block(scene['secondary_figures'], 'human witnesses and attendants')}
SUPPORTING ACTIONS: {block(scene['supporting_actions'], 'witnessing, offering, gathering and visible reaction')}
MAIN SYMBOLS: {block(scene['main_symbols'], 'sacred threshold objects')}
EMOTION: {block(scene['emotions'], 'solemn human emotion')}
SETTING: {block(scene['environment'], 'an ancient sacred wall setting')}
BACKGROUND MOTIFS ONLY: {block(scene['background_motifs'], 'subtle secondary symbolic details')}
STYLE: {block(scene['style'], 'weathered ancient figurative fresco')}
COMPOSITION RULES: {block(scene['composition_rules'], 'central figurative narrative dominates')}

Render visible bodies, faces, hands, gestures, ritual interaction, sacred objects and many small story details. Keep the central figure and central action immediately readable. Structural ideas such as replication, matrices, comparisons, segmentation, controls, epochs, validation states or uncertainty may appear only as tiny side-register scenes, reliefs, veils or distant symbols; they must never become the main composition. Preserve uncertainty visually without turning unconfirmed claims into triumphal established facts. Ancient cracked plaster, mineral pigment, hand-painted historical mural, richly detailed figurative storytelling.""".strip()


def render_negative_prompt(scene: dict) -> str:
    return ", ".join(dedupe(NEGATIVE_BASE + scene.get("forbidden_failure_modes", [])))


def fit_scene_prompt(tokenizer, scene: dict) -> tuple[str, str, int, int]:
    max_tokens = max(1, tokenizer.model_max_length - 2) * v3.MAX_PROMPT_CHUNKS
    prompt = render_scene_prompt(scene)
    count = v3.token_count(tokenizer, prompt)
    if count <= max_tokens:
        return prompt, "scene_skeleton_full", count, max_tokens

    compact_scene = deepcopy(scene)
    compact_scene["secondary_figures"] = compact_scene["secondary_figures"][:3]
    compact_scene["supporting_actions"] = compact_scene["supporting_actions"][:3]
    compact_scene["main_symbols"] = compact_scene["main_symbols"][:5]
    compact_scene["background_motifs"] = compact_scene["background_motifs"][:3]
    compact_scene["composition_rules"] = compact_scene["composition_rules"][:5]
    prompt = render_scene_prompt(compact_scene)
    count = v3.token_count(tokenizer, prompt)
    if count <= max_tokens:
        return prompt, "scene_skeleton_compact", count, max_tokens

    lean = deepcopy(compact_scene)
    lean["secondary_figures"] = lean["secondary_figures"][:2]
    lean["supporting_actions"] = lean["supporting_actions"][:2]
    lean["main_symbols"] = lean["main_symbols"][:4]
    lean["background_motifs"] = lean["background_motifs"][:2]
    lean["emotions"] = lean["emotions"][:2]
    lean["environment"] = lean["environment"][:2]
    prompt = render_scene_prompt(lean)
    return prompt, "scene_skeleton_lean", v3.token_count(tokenizer, prompt), max_tokens


def generate_one(pipe, candidate, repo_root, output_root, model, steps, width, height, seed) -> dict:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    proj = v3.projection(candidate.canonical_json)
    scene = build_scene_skeleton(proj)
    model_prompt, mode, prompt_tokens, max_tokens = fit_scene_prompt(pipe.tokenizer, scene)
    negative_prompt = render_negative_prompt(scene)
    pos, neg, chunks = v3.encode_long(pipe, model_prompt, negative_prompt, device)

    basename = f"{candidate.source_sha256[:16]}--{base.safe_stem(candidate.path)}"
    image_path = output_root / "images" / f"{basename}.png"
    receipt_path = output_root / "receipts" / f"{basename}.json"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    generator = torch.Generator(device=device).manual_seed(seed)
    start = time.monotonic()
    with torch.inference_mode():
        image = pipe(
            prompt_embeds=pos,
            negative_prompt_embeds=neg,
            num_inference_steps=steps,
            guidance_scale=GUIDANCE_SCALE,
            width=width,
            height=height,
            generator=generator,
        ).images[0]
    elapsed = round(time.monotonic() - start, 3)

    tmp = image_path.with_suffix(".tmp.png")
    image.save(tmp, format="PNG")
    tmp.replace(image_path)
    projection_json = json.dumps(proj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    scene_json = json.dumps(scene, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    receipt = {
        "schema": "janus.fresco_forge.receipt.v4",
        "generator": GENERATOR_VERSION,
        "status": "generated",
        "generated_at": base.utc_now(),
        "source_path": candidate.relpath,
        "source_sha256": candidate.source_sha256,
        "canonical_json_bytes": len(candidate.canonical_json.encode("utf-8")),
        "visual_projection_sha256": base.sha256_bytes(projection_json.encode("utf-8")),
        "visual_projection_bytes": len(projection_json.encode("utf-8")),
        "scene_skeleton_sha256": base.sha256_bytes(scene_json.encode("utf-8")),
        "prompt_sha256": base.sha256_bytes(model_prompt.encode("utf-8")),
        "prompt_mode": mode,
        "prompt_tokens": prompt_tokens,
        "max_prompt_tokens": max_tokens,
        "prompt_chunks": chunks,
        "max_prompt_chunks": v3.MAX_PROMPT_CHUNKS,
        "semantic_coverage_ratio": 1.0,
        "semantic_model_policy": "ALL_NONTECHNICAL_SCALARS_TRACED_AND_INTERPRETED__SCENE_SKELETON_CONTROLS_VISUAL_DOMINANCE",
        "prompt_text": model_prompt,
        "negative_prompt": negative_prompt,
        "scene_skeleton": scene,
        "visual_projection": proj,
        "model": model,
        "backend": "local_diffusers_scene_skeleton_chunked_clip",
        "device": device,
        "scheduler": pipe.scheduler.__class__.__name__,
        "steps": steps,
        "guidance_scale": GUIDANCE_SCALE,
        "width": width,
        "height": height,
        "seed": seed,
        "elapsed_seconds": elapsed,
        "image_path": image_path.relative_to(repo_root).as_posix(),
        "receipt_path": receipt_path.relative_to(repo_root).as_posix(),
        "image_sha256": base.sha256_bytes(image_path.read_bytes()),
    }
    base.write_json_atomic(receipt_path, receipt)
    return receipt


base.GENERATOR_VERSION = GENERATOR_VERSION
base.create_pipeline = v3.create_pipeline
base.generate_one = generate_one

if __name__ == "__main__":
    raise SystemExit(base.main())
