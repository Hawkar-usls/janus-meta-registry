#!/usr/bin/env python3
"""JANUS Fresco Forge v4.3: Continuous Mural Composition Lock.

Preserves v4.1.1 semantic-role / physical-gate firewalls and the v4.2.1 ancient
visual grammar. v4.3 specifically blocks the observed tiled-icon/contact-sheet
collapse and forces non-human system scenes into one continuous asymmetric mural
field on a landscape canvas.
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
import v4_1_1_runner as firewall  # noqa: F401  # preserves role/physical-gate firewall
import v4_2_runner as v42

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v4.3-continuous-mural-lock"
GUIDANCE_SCALE = float(os.getenv("FRESCO_GUIDANCE_SCALE", "7.5"))

NEGATIVE_CONTROL_CLASSES = [
    "FAIL__3D_MACHINE_COLLAPSE",
    "FAIL__DIAGRAM_GEOMETRY_COLLAPSE",
    "FAIL__TILED_ICON_GRID_COLLAPSE",
]

CONTINUOUS_MURAL_NEGATIVE = [
    "grid", "tile grid", "tiled layout", "contact sheet", "icon sheet", "specimen board",
    "badge sheet", "repeated medallions", "repeated circular icons", "isolated circles",
    "checkerboard layout", "uniform 3x3 arrangement", "nine equal panels", "catalog layout",
    "sticker sheet", "white background", "blank background", "equal cells", "repeated badges",
]


def dedupe(values: Iterable[str]) -> list[str]:
    return v41.dedupe(values)


def is_swarm_scene(scene: dict) -> bool:
    corpus = v42.scene_corpus(scene)
    return (
        ("distributed" in corpus or "swarm" in corpus)
        and any(k in corpus for k in ("peer", "node", "collective", "organism", "local model", "beacon"))
    )


def continuous_system_translation(scene: dict) -> dict:
    if is_swarm_scene(scene):
        return {
            "central_visual_subject": (
                "one continuous ancient mural landscape containing several distinct beacon-like peer nodes, "
                "each different in shape and placement, all belonging to the same living distributed organism"
            ),
            "central_action": (
                "peer nodes keep local knowledge while selective observations and predictions travel between them "
                "as thin irregular hand-painted ribbons crossing the same cracked plaster field"
            ),
            "supporting_motifs": [
                "one peer may glow slightly brighter as a current candidate but has no throne, crown or central dominance",
                "stale or missing peers appear as dim gaps or faded places within the same mural landscape",
                "disagreement remains visible as differently colored ribbons that run beside one another without merging",
                "learning and rollback appear as small irregular traces embedded in the shared painted terrain",
            ],
            "main_symbols": [
                "unevenly spaced peer beacons", "shared continuous plaster field", "crossing signal ribbons", "faded absent positions",
            ],
            "human_presence": "none required; do not invent a ruler, portrait or human protagonist",
            "composition_bias": [
                "one continuous asymmetric mural scene across the entire frame",
                "nodes are irregularly spaced in one shared painted environment, never arranged in rows or columns",
                "no repeated circles, badges, medallions, tiles or equal compartments",
                "connections cross open mural space instead of forming a clean network diagram",
            ],
            "semantic_anchors": v42.source_semantic_anchors(scene),
        }

    translated = v42.translate_system_allegory(scene)
    translated["composition_bias"] = dedupe(list(translated.get("composition_bias", [])) + [
        "one continuous asymmetric mural scene across the entire frame",
        "irregular placement with no rows, columns, equal cells or repeated compartments",
        "all states share one connected painted plaster field",
    ])
    return translated


def build_translated_scene(scene: dict) -> dict:
    if scene.get("archetype") == "SYSTEM_ALLEGORY":
        translated = continuous_system_translation(scene)
    else:
        translated = v42.build_translated_scene(scene)
        translated["composition_bias"] = dedupe(list(translated.get("composition_bias", [])) + [
            "one continuous mural field across the full frame",
            "asymmetric placement rather than repeated equal panels",
            "no tiled, contact-sheet or specimen-board composition",
        ])
    translated["schema"] = "janus.fresco_forge.ancient_visual_translation.v4_3"
    translated["continuous_mural_lock"] = True
    return translated


def render_prompt(scene: dict, translated: dict) -> str:
    def join(items: Iterable[str], fallback: str) -> str:
        vals = dedupe(items)
        return "; ".join(vals) if vals else fallback

    style = (
        "ONE CONTINUOUS ANCIENT WALL FRESCO covering the entire frame. Cracked aged lime plaster painted by hand "
        "with worn ochre, iron red, soot black, terre verte and faded blue mineral pigments; pigment loss, stains, "
        "abrasion, irregular cracks, flat contours and imperfect brushwork. The whole frame is one shared plaster wall."
    )
    scene_text = (
        f"ARCHETYPE: {scene['archetype']}. SUBJECT: {translated['central_visual_subject']}. "
        f"ACTION: {translated['central_action']}. PEOPLE: {translated['human_presence']}. "
        f"MOTIFS: {join(translated.get('supporting_motifs', []), 'only source-supported motifs')}. "
        f"SYMBOLS: {join(translated.get('main_symbols', []), 'only source-supported symbols')}. "
        f"SOURCE MEANING: {join(translated.get('semantic_anchors', []), 'preserve source meaning without literal labels')}."
    )
    composition = (
        f"COMPOSITION: {join(translated.get('composition_bias', []), 'one asymmetric continuous mural')}. "
        "No grid, no tiles, no repeated medallions, no icon sheet, no contact sheet, no specimen board, no white background. "
        "Every subject is embedded in the same continuous cracked plaster field with open irregular space between elements. "
        "ROLE FIREWALL: internal names, repositories, protocols, workflow gates, adapters and states never become people or gods by name. "
        "Unresolved claims stay unresolved. No diagram, infographic, CAD, UI, product shot, glossy machine, readable code, JSON or modern labels."
    )
    return "\n".join([style, scene_text, composition]).strip()


def render_negative_prompt(scene: dict) -> str:
    negatives = list(v42.NO_MODERN_VISUAL_GRAMMAR) + list(CONTINUOUS_MURAL_NEGATIVE) + [
        "neutral gray background", "clean white background", "floating object", "modern machine",
        "mechanical product photography", "clean grid", "dashboard", "schematic", "modern arrows",
        "modern icons", "clean typography", "readable text", "readable code", "readable json", "logo",
        "watermark", "caption", "screenshot", "marble statue", "classical sculpture", "bodybuilder statue",
        "plastic skin", "perfect digital symmetry", "ray traced lighting", "abstract pattern", "striped textile",
        "decorative fabric", "ornamental bands", "geometric wallpaper", "pattern-only composition", "woven rug",
        "symmetrical icon matrix", "isolated circular tokens", "repeated identical objects",
    ]
    if not scene.get("human_figures"):
        negatives += ["central human hero", "central goddess", "central god", "mythic woman", "mythic man", "portrait composition"]
    if scene.get("archetype") != "ARCHITECTURAL_EVENT":
        negatives += ["architecture-only composition"]
    return ", ".join(dedupe(negatives))


def choose_canvas(scene: dict, requested_width: int, requested_height: int) -> tuple[int, int]:
    if scene.get("archetype") in {"SYSTEM_ALLEGORY", "ARCHITECTURAL_EVENT", "OBJECT_RITUAL"}:
        return 640, 448
    return requested_width, requested_height


def generate_one(pipe, candidate, repo_root, output_root, model, steps, width, height, seed) -> dict:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    proj = v3.projection(candidate.canonical_json)
    scene = v41.build_scene_plan(proj)
    translated = build_translated_scene(scene)
    raw_prompt = render_prompt(scene, translated)
    model_prompt, prompt_tokens, max_tokens, hard_truncated, original_prompt_tokens = v41.hard_cap_prompt(pipe.tokenizer, raw_prompt)
    negative_prompt = render_negative_prompt(scene)
    pos, neg, chunks = v3.encode_long(pipe, model_prompt, negative_prompt, device)
    render_width, render_height = choose_canvas(scene, width, height)

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
            width=render_width,
            height=render_height,
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
        "schema": "janus.fresco_forge.receipt.v4_3",
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
        "prompt_mode": "semantic_role_firewall_plus_continuous_mural_style_lock",
        "original_prompt_tokens": original_prompt_tokens,
        "prompt_tokens": prompt_tokens,
        "max_prompt_tokens": max_tokens,
        "prompt_hard_truncated": hard_truncated,
        "prompt_chunks": chunks,
        "semantic_coverage_ratio": 1.0,
        "semantic_model_policy": "ALL_NONTECHNICAL_SCALARS_TRACED__V4_1_1_FIREWALLS_PRESERVED__V4_3_CONTINUOUS_MURAL",
        "false_personification_guard": True,
        "physical_gate_firewall": True,
        "ancient_visual_grammar_lock": True,
        "no_modern_visual_grammar": True,
        "full_frame_plaster_surface": True,
        "continuous_mural_lock": True,
        "anti_grid_icon_collapse": True,
        "calibration_negative_controls": NEGATIVE_CONTROL_CLASSES,
        "scene_archetype": scene["archetype"],
        "prompt_text": model_prompt,
        "negative_prompt": negative_prompt,
        "scene_plan": scene,
        "translated_scene": translated,
        "visual_projection": proj,
        "model": model,
        "backend": "local_diffusers_v4_3_continuous_mural_chunked_clip",
        "device": device,
        "scheduler": pipe.scheduler.__class__.__name__,
        "steps": steps,
        "guidance_scale": GUIDANCE_SCALE,
        "requested_width": width,
        "requested_height": height,
        "width": render_width,
        "height": render_height,
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
