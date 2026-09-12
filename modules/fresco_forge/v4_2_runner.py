#!/usr/bin/env python3
"""JANUS Fresco Forge v4.2: Fresco Style Lock + Ancient Visual Grammar.

Preserves the v4.1.1 semantic-role / physical-gate firewalls, then translates the
resolved scene archetype into an explicitly ancient wall-painting visual grammar.
The generator must not express technical semantics as modern diagrams, CAD-like
geometry, product renders, or isolated 3D machines.
"""
from __future__ import annotations

import json
import os
import time
from typing import Iterable

import torch

import forge as base
import v3_runner as v3
import v4_1_runner as v41
import v4_1_1_runner as firewall  # noqa: F401  # importing applies the v4.1.1 firewall patch

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v4.2-fresco-style-lock"
GUIDANCE_SCALE = float(os.getenv("FRESCO_GUIDANCE_SCALE", "8.5"))

ANCIENT_FRESCO_STYLE_LOCK = [
    "a surviving fragment of an ancient narrative wall fresco",
    "the entire frame is a hand-painted cracked lime-plaster wall surface",
    "mineral pigments absorbed into aged intonaco",
    "worn ochre, iron red, soot black, terre verte and faded blue pigments",
    "visible pigment loss, abrasion, age stains and irregular crack networks",
    "flat painted forms with hand-drawn contours rather than sculptural volume",
    "old mural spatial logic and narrative registers rather than modern perspective",
    "weathered historical patina and visibly imperfect brushwork",
]

NO_MODERN_VISUAL_GRAMMAR = [
    "3d render", "product render", "product shot", "cad model", "technical illustration",
    "diagram", "flowchart", "infographic", "ui panel", "interface mockup", "vector graphic",
    "clean geometric poster", "glossy hard-surface object", "industrial design",
    "sci-fi machine render", "photoreal hardware", "modern sculpture", "plastic material",
    "studio background", "showroom lighting", "isolated floating object", "blueprint",
]

WALL_EMBEDDING_RULES = [
    "fill the whole image with painted plaster and mural surface; no blank studio background",
    "embed every subject inside the wall painting with surrounding pigment, cracks and mural borders",
    "use side registers, painted compartments or symbolic framing instead of floating standalone objects",
    "the result must read immediately as an old wall painting even before its subject is interpreted",
]


def dedupe(values: Iterable[str]) -> list[str]:
    return v41.dedupe(values)


def translate_system_allegory(scene: dict) -> dict:
    return {
        "central_visual_subject": (
            "an ancient wall-painted symbolic process made of flat painted thresholds, channels, vessels, "
            "compartments and linked seals; these are pictorial symbols, never a modern machine"
        ),
        "central_action": (
            "the symbolic process unfolds across successive fresco registers as controlled passage, closure, "
            "transfer and validation between painted compartments"
        ),
        "supporting_motifs": [
            "small side-register scenes show earlier and later process states",
            "failed or unresolved states remain as dim sealed painted compartments",
            "successful transitions appear as brighter opened thresholds",
            "flow is suggested by old hand-painted ribbons or streams rather than diagram arrows",
            "linked stages are separated by irregular fresco borders rather than a clean grid",
        ],
        "human_presence": "none required unless explicit person-role evidence exists in the scene plan",
        "composition_bias": [
            "narrative fresco registers dominate over geometry",
            "symbolic process imagery must stay flat and hand-painted",
            "do not center one isolated machine-like object",
        ],
    }


def translate_architectural_event(scene: dict) -> dict:
    source_subject = scene.get("visual_subject", "")
    source_action = scene.get("central_action", "")
    return {
        "central_visual_subject": (
            "an ancient wall-painted threshold scene with chambers, doors, passages and controlled openings, "
            "all rendered as flat historical mural architecture on damaged plaster; " + source_subject
        ),
        "central_action": (
            "show the ordered transition as a painted mural sequence rather than an engineering render: " + source_action
        ),
        "supporting_motifs": [
            "side registers depict before and after states",
            "sealed spaces are darker and visually quiet",
            "opened thresholds are brighter and active",
            "architectural forms use simplified ancient mural perspective, not realistic 3D visualization",
        ],
        "human_presence": (
            "only explicitly evidenced people may appear; anonymous tiny attendants may appear only if already allowed by the scene plan"
        ),
        "composition_bias": [
            "architecture remains visibly painted into plaster",
            "no freestanding CAD-like hatch, device or product object",
            "use old wall-painting perspective and irregular painted outlines",
        ],
    }


def translate_object_ritual(scene: dict) -> dict:
    return {
        "central_visual_subject": (
            "the source-established object or artifact embedded in an ancient wall-fresco scene, painted flat on plaster "
            "with symbolic context rather than isolated like a catalog product"
        ),
        "central_action": scene.get("central_action") or "the object participates in the exact functional or ritual relationship established by the source",
        "supporting_motifs": [
            "painted ritual or symbolic borders derived only from source-supported motifs",
            "small contextual side scenes only when supported by the source",
        ],
        "human_presence": "optional only when explicit person-role evidence exists",
        "composition_bias": [
            "never use a product-shot composition",
            "keep the object fused to the damaged plaster surface and surrounding mural field",
        ],
    }


def translate_people(scene: dict) -> dict:
    return {
        "central_visual_subject": scene.get("visual_subject", "the source-established central figure"),
        "central_action": scene.get("central_action", "the source-established action"),
        "supporting_motifs": scene.get("supporting_actions", [])[:6],
        "human_presence": (
            "use exactly the explicitly established human or mythic roles from the semantic scene plan; do not invent additional named figures"
        ),
        "composition_bias": [
            "figures are hand-painted fresco figures with flat modeled drapery and irregular ancient contours",
            "avoid statue, sculpture, portrait-photo and glossy skin aesthetics",
        ],
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

    translated["schema"] = "janus.fresco_forge.ancient_visual_translation.v4_2"
    translated["source_archetype"] = archetype
    translated["style_lock"] = list(ANCIENT_FRESCO_STYLE_LOCK)
    translated["wall_embedding_rules"] = list(WALL_EMBEDDING_RULES)
    return translated


def render_prompt(scene: dict, translated: dict) -> str:
    def join(items: Iterable[str], fallback: str) -> str:
        vals = dedupe(items)
        return "; ".join(vals) if vals else fallback

    style_intro = (
        "ANCIENT FRESCO STYLE LOCK — THIS OVERRIDES MODERN VISUAL GRAMMAR. "
        "Create a surviving fragment of an ancient narrative wall fresco. "
        "The entire image is painted directly into cracked aged lime plaster with mineral pigments. "
        "Use worn ochre, iron red, soot black, terre verte and faded blue, pigment loss, abrasion, stains, "
        "irregular crack networks, imperfect brushwork and flat hand-painted contours. "
        "Everything must look physically fused to the plaster wall, never like a clean 3D render or modern illustration."
    )

    scene_block = f"""SCENE ARCHETYPE: {scene['archetype']}.
CENTRAL PAINTED SUBJECT: {translated['central_visual_subject']}.
CENTRAL PAINTED ACTION: {translated['central_action']}.
HUMAN PRESENCE RULE: {translated['human_presence']}.
SUPPORTING FRESCO MOTIFS: {join(translated.get('supporting_motifs', []), 'only source-supported secondary motifs')}.
SOURCE SYMBOLS TO PRESERVE SEMANTICALLY: {join(scene.get('main_symbols', []), 'only objects implied by the source')}.
COMPOSITION: {join(translated.get('composition_bias', []), 'ancient narrative mural composition')}; {join(WALL_EMBEDDING_RULES, 'full-frame wall fresco')}.
SEMANTIC FIREWALL: system names, repositories, protocols, workflow gates, adapters, controllers and state-machine labels never become humans or gods by name alone; a person appears only from explicit person-role evidence; unresolved claims remain visually unresolved."""

    ending = (
        "Ancient visual grammar only: narrative registers, irregular painted compartments, symbolic side-scenes, "
        "flat mural architecture and weathered pigments. Never translate technical semantics into modern diagrams, "
        "infographics, CAD geometry, UI, product photography, glossy machinery or isolated objects on a neutral background. "
        "No readable code, no literal JSON, no modern labels."
    )
    return "\n\n".join([style_intro, scene_block, ending]).strip()


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

    # build_scene_plan resolves the infer_scene_archetype function monkeypatched by
    # v4_1_1_runner on import, preserving the physical-gate firewall unchanged.
    scene = v41.build_scene_plan(proj)
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
        "schema": "janus.fresco_forge.receipt.v4_2",
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
        "prompt_mode": "semantic_role_firewall_plus_fresco_style_lock",
        "original_prompt_tokens": original_prompt_tokens,
        "prompt_tokens": prompt_tokens,
        "max_prompt_tokens": max_tokens,
        "prompt_hard_truncated": hard_truncated,
        "prompt_chunks": chunks,
        "semantic_coverage_ratio": 1.0,
        "semantic_model_policy": "ALL_NONTECHNICAL_SCALARS_TRACED__V4_1_1_ROLE_FIREWALL_PRESERVED__V4_2_ANCIENT_VISUAL_TRANSLATION",
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
        "backend": "local_diffusers_v4_2_fresco_style_lock_chunked_clip",
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
