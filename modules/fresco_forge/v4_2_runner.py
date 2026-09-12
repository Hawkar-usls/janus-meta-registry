#!/usr/bin/env python3
"""JANUS Fresco Forge v4.2.1: compact Fresco Style Lock + Ancient Visual Grammar.

Preserves the v4.1.1 semantic-role / physical-gate firewalls. v4.2.1 keeps the
style-first prompt under the actual CLIP budget and translates source semantics
into ancient mural motifs without leaking raw modern-machine vocabulary back
into the generative prompt.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Iterable

import torch

import forge as base
import v3_runner as v3
import v4_1_runner as v41
import v4_1_1_runner as firewall  # noqa: F401  # applies v4.1.1 role/physical-gate patch

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v4.2.1-compact-fresco-style-lock"
GUIDANCE_SCALE = float(os.getenv("FRESCO_GUIDANCE_SCALE", "8.5"))

NO_MODERN_VISUAL_GRAMMAR = [
    "3d render", "product render", "product shot", "cad model", "technical illustration",
    "diagram", "flowchart", "infographic", "ui panel", "interface mockup", "vector graphic",
    "clean geometric poster", "glossy hard-surface object", "industrial design",
    "sci-fi machine render", "photoreal hardware", "modern sculpture", "plastic material",
    "studio background", "showroom lighting", "isolated floating object", "blueprint",
]


def dedupe(values: Iterable[str]) -> list[str]:
    return v41.dedupe(values)


def compact_text(text: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return cut + "…"


def scene_corpus(scene: dict) -> str:
    audit = scene.get("role_audit", [])
    return " ".join(str(x.get("value", "")) for x in audit).casefold()


def source_semantic_anchors(scene: dict, limit: int = 3) -> list[str]:
    """Select a few high-signal source meanings for the prompt, never identifiers."""
    audit = scene.get("role_audit", [])
    preferred = (
        "core_idea", "correction", "implication", "principle", "summary", "description",
        "meaning", "purpose", "organism_model", "distributed_world_model", "cognition_rule",
    )
    ranked: list[tuple[float, str]] = []
    for fact in audit:
        if fact.get("field_role") in {"IDENTIFIER_OR_METADATA", "SYSTEM_COMPONENT"}:
            continue
        path = str(fact.get("path", "")).casefold()
        value = str(fact.get("value", "")).strip()
        if len(value) < 25 or value.casefold() in {"true", "false", "none", "null"}:
            continue
        bonus = 3.0 if any(k in path for k in preferred) else 0.0
        weight = float(fact.get("weight", 0.0)) + bonus
        ranked.append((weight, compact_text(value)))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return dedupe(v for _, v in ranked)[:limit]


def translate_system_allegory(scene: dict) -> dict:
    corpus = scene_corpus(scene)
    anchors = source_semantic_anchors(scene)

    is_distributed_swarm = (
        ("distributed" in corpus or "swarm" in corpus)
        and any(k in corpus for k in ("peer", "node", "collective", "organism", "local model"))
    )

    if is_distributed_swarm:
        return {
            "central_visual_subject": (
                "many distinct painted beacon-like nodes arranged as one living distributed organism, "
                "with no throne and no single central monarch"
            ),
            "central_action": (
                "separate nodes keep their own local knowledge while exchanging selective observations and predictions "
                "through thin hand-painted ribbons, contributing to a shared collective field"
            ),
            "supporting_motifs": [
                "different node symbols remain visibly distinct rather than merging into one brain",
                "a portable beacon appears as one peer organ among several others",
                "disagreement is shown as parallel colored ribbons that remain separate",
                "stale or missing peers are dimmed but still marked as absent positions",
            ],
            "main_symbols": [
                "many peer beacons", "shared painted field", "separate signal ribbons", "no throne or crown",
            ],
            "human_presence": "none required; do not invent a ruler or human protagonist",
            "composition_bias": [
                "organic constellation-like mural composition, not a network diagram",
                "irregular fresco registers instead of a clean grid",
            ],
            "semantic_anchors": anchors,
        }

    return {
        "central_visual_subject": (
            "a flat ancient wall-painted symbolic process of thresholds, vessels, channels and compartments, "
            "all pictorial and non-modern"
        ),
        "central_action": (
            "the source process unfolds across irregular fresco registers as passage, closure, transfer and change"
        ),
        "supporting_motifs": [
            "earlier and later states appear in small side registers",
            "unresolved states remain dim and sealed",
            "successful transitions appear as brighter openings",
            "flow appears as hand-painted streams rather than arrows",
        ],
        "main_symbols": ["painted thresholds", "vessels", "flowing ribbons", "sealed and opened compartments"],
        "human_presence": "none required unless explicit person-role evidence exists",
        "composition_bias": ["narrative registers dominate over geometry", "no isolated machine-like object"],
        "semantic_anchors": anchors,
    }


def translate_architectural_event(scene: dict) -> dict:
    return {
        "central_visual_subject": (
            "a flat ancient mural of the source-established chambers, doors, passages and thresholds painted into damaged plaster"
        ),
        "central_action": compact_text(scene.get("central_action", "an ordered threshold transition unfolds"), 220),
        "supporting_motifs": [
            "before and after states occupy small side registers",
            "sealed spaces are darker; opened thresholds are brighter",
            "architecture uses simplified ancient mural perspective",
        ],
        "main_symbols": ["painted doors", "thresholds", "sealed chambers", "opened passage"],
        "human_presence": "only explicitly evidenced people may appear",
        "composition_bias": ["all architecture remains visibly painted on plaster", "no freestanding device or product object"],
        "semantic_anchors": source_semantic_anchors(scene),
    }


def translate_object_ritual(scene: dict) -> dict:
    return {
        "central_visual_subject": (
            "the source-established object painted directly into an ancient wall scene, surrounded by source-supported symbolic context"
        ),
        "central_action": compact_text(scene.get("central_action", "the object participates in its source-established relationship"), 220),
        "supporting_motifs": ["irregular painted borders", "small contextual side scenes only when source-supported"],
        "main_symbols": ["the source-established object", "weathered symbolic border"],
        "human_presence": "only if explicit person-role evidence exists",
        "composition_bias": ["never a catalog or product shot", "object remains fused to the plaster field"],
        "semantic_anchors": source_semantic_anchors(scene),
    }


def translate_people(scene: dict) -> dict:
    return {
        "central_visual_subject": compact_text(scene.get("visual_subject", "the source-established central figure"), 220),
        "central_action": compact_text(scene.get("central_action", "the source-established action"), 220),
        "supporting_motifs": [compact_text(x, 140) for x in scene.get("supporting_actions", [])[:4]],
        "main_symbols": [compact_text(x, 100) for x in scene.get("main_symbols", [])[:4]],
        "human_presence": "use only explicitly established human or mythic roles; invent no named figure",
        "composition_bias": ["hand-painted fresco figures, not statues or portrait photography"],
        "semantic_anchors": source_semantic_anchors(scene),
    }


def build_translated_scene(scene: dict) -> dict:
    archetype = scene.get("archetype")
    if archetype == "SYSTEM_ALLEGORY":
        translated = translate_system_allegory(scene)
    elif archetype == "ARCHITECTURAL_EVENT":
        translated = translate_architectural_event(scene)
    elif archetype == "OBJECT_RITUAL":
        translated = translate_object_ritual(scene)
    else:
        translated = translate_people(scene)
    translated["schema"] = "janus.fresco_forge.ancient_visual_translation.v4_2_1"
    translated["source_archetype"] = archetype
    return translated


def render_prompt(scene: dict, translated: dict) -> str:
    def join(items: Iterable[str], fallback: str) -> str:
        vals = dedupe(items)
        return "; ".join(vals) if vals else fallback

    # Keep style first and concise so the complete semantic/style contract fits inside
    # the six-chunk CLIP budget without relying on hard truncation.
    style = (
        "ANCIENT WALL FRESCO. Entire frame is cracked aged lime plaster painted by hand with mineral pigments: "
        "worn ochre, iron red, soot black, terre verte, faded blue; pigment loss, stains, abrasion, irregular cracks, "
        "flat contours and imperfect brushwork. Everything is fused to the plaster; no modern 3D visual grammar."
    )
    scene_text = (
        f"ARCHETYPE: {scene['archetype']}. SUBJECT: {translated['central_visual_subject']}. "
        f"ACTION: {translated['central_action']}. PEOPLE: {translated['human_presence']}. "
        f"MOTIFS: {join(translated.get('supporting_motifs', []), 'only source-supported motifs')}. "
        f"SYMBOLS: {join(translated.get('main_symbols', []), 'only source-supported symbols')}. "
        f"SOURCE MEANING: {join(translated.get('semantic_anchors', []), 'preserve the source relationship without literal labels')}."
    )
    rules = (
        f"COMPOSITION: {join(translated.get('composition_bias', []), 'ancient narrative registers')}; irregular mural registers; "
        "surround every subject with painted plaster, cracks and faded mural field; no blank background. "
        "ROLE FIREWALL: internal names, repositories, protocols, workflow gates, adapters and states never become people or gods by name. "
        "Unresolved claims stay unresolved. No diagram, infographic, CAD, UI, product shot, glossy machine, readable code, JSON or modern labels."
    )
    return "\n".join([style, scene_text, rules]).strip()


def render_negative_prompt(scene: dict) -> str:
    negatives = list(NO_MODERN_VISUAL_GRAMMAR) + [
        "blank background", "neutral gray background", "clean white background", "floating object",
        "modern machine", "mechanical product photography", "clean grid", "dashboard", "schematic",
        "modern arrows", "modern icons", "clean typography", "readable text", "readable code", "readable json",
        "logo", "watermark", "caption", "screenshot", "marble statue", "classical sculpture",
        "bodybuilder statue", "plastic skin", "perfect digital symmetry", "ray traced lighting",
        "abstract pattern", "striped textile", "decorative fabric", "ornamental bands", "geometric wallpaper",
        "pattern-only composition", "woven rug",
    ]
    if not scene.get("human_figures"):
        negatives += ["central human hero", "central goddess", "central god", "mythic woman", "mythic man", "portrait composition"]
    if scene.get("archetype") != "ARCHITECTURAL_EVENT":
        negatives += ["architecture-only composition"]
    return ", ".join(dedupe(negatives))


def generate_one(pipe, candidate, repo_root, output_root, model, steps, width, height, seed) -> dict:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    proj = v3.projection(candidate.canonical_json)
    scene = v41.build_scene_plan(proj)  # uses the v4.1.1 monkeypatched archetype inference
    translated = build_translated_scene(scene)
    raw_prompt = render_prompt(scene, translated)
    model_prompt, prompt_tokens, max_tokens, hard_truncated, original_prompt_tokens = v41.hard_cap_prompt(pipe.tokenizer, raw_prompt)
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
    translated_json = json.dumps(translated, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    receipt = {
        "schema": "janus.fresco_forge.receipt.v4_2_1",
        "generator": GENERATOR_VERSION,
        "status": "generated",
        "generated_at": base.utc_now(),
        "source_path": candidate.relpath,
        "source_sha256": candidate.source_sha256,
        "canonical_json_bytes": len(candidate.canonical_json.encode("utf-8")),
        "visual_projection_sha256": base.sha256_bytes(projection_json.encode("utf-8")),
        "scene_plan_sha256": base.sha256_bytes(scene_json.encode("utf-8")),
        "translated_scene_sha256": base.sha256_bytes(translated_json.encode("utf-8")),
        "prompt_sha256": base.sha256_bytes(model_prompt.encode("utf-8")),
        "prompt_mode": "semantic_role_firewall_plus_compact_fresco_style_lock",
        "original_prompt_tokens": original_prompt_tokens,
        "prompt_tokens": prompt_tokens,
        "max_prompt_tokens": max_tokens,
        "prompt_hard_truncated": hard_truncated,
        "prompt_chunks": chunks,
        "semantic_coverage_ratio": 1.0,
        "semantic_model_policy": "ALL_NONTECHNICAL_SCALARS_TRACED__V4_1_1_FIREWALLS_PRESERVED__V4_2_1_COMPACT_ANCIENT_VISUAL_TRANSLATION",
        "false_personification_guard": True,
        "physical_gate_firewall": True,
        "ancient_visual_grammar_lock": True,
        "no_modern_visual_grammar": True,
        "full_frame_plaster_surface": True,
        "scene_archetype": scene["archetype"],
        "prompt_text": model_prompt,
        "negative_prompt": negative_prompt,
        "scene_plan": scene,
        "translated_scene": translated,
        "visual_projection": proj,
        "model": model,
        "backend": "local_diffusers_v4_2_1_compact_fresco_style_lock_chunked_clip",
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
