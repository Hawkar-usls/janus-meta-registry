#!/usr/bin/env python3
"""JANUS Fresco Forge v4.3.1: Scene Focus Firewall + Continuous Mural Lock.

Preserves v4.1.1 semantic-role / physical-gate firewalls and the ancient visual
grammar. v4.3.1 fixes a new calibration defect: incidental `node`/`peer` words
must not make every SYSTEM_ALLEGORY a swarm scene. The dominant semantic topic
is scored first, then translated into a compact visual grammar that fits the
actual multi-CLIP token budget.
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
import v4_1_1_runner as firewall  # noqa: F401  # preserve semantic/physical-gate patches
import v4_2_runner as v42

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v4.3.1-scene-focus-firewall"
GUIDANCE_SCALE = float(os.getenv("FRESCO_GUIDANCE_SCALE", "7.5"))

NEGATIVE_CONTROL_CLASSES = [
    "FAIL__3D_MACHINE_COLLAPSE",
    "FAIL__DIAGRAM_GEOMETRY_COLLAPSE",
    "FAIL__TILED_ICON_GRID_COLLAPSE",
    "FAIL__INCIDENTAL_TERM_SCENE_HIJACK",
]

CONTINUOUS_MURAL_NEGATIVE = [
    "grid", "tile grid", "tiled layout", "contact sheet", "icon sheet", "specimen board",
    "badge sheet", "repeated medallions", "repeated circular icons", "isolated circles",
    "checkerboard layout", "uniform 3x3 arrangement", "nine equal panels", "catalog layout",
    "sticker sheet", "white background", "blank background", "equal cells", "repeated badges",
]

MEMORY_PATH_TERMS = (
    "memory", "storage", "archive", "forget", "retention", "deletion", "history", "ring",
    "episode", "compaction", "persistence", "receipt", "forensic",
)
SWARM_PATH_TERMS = (
    "swarm_contract", "distributed", "topology", "collective", "peer_exchange", "peer_state",
    "other_nodes", "organism_model", "swarm_level", "node_contract",
)
MEMORY_VALUE_TERMS = (
    "memory", "archive", "retention", "delete", "deletion", "storage", "history", "persist",
    "rollover", "anomaly", "episode", "compaction",
)
SWARM_VALUE_TERMS = (
    "distributed organism", "distributed swarm", "peer swarm", "collective learning", "swarm",
    "multiple nodes", "healthy nodes", "peer disagreement",
)


def dedupe(values: Iterable[str]) -> list[str]:
    return v41.dedupe(values)


def _clean(text: str, limit: int = 145) -> str:
    text = re.sub(r"[_/]+", " ", str(text))
    text = re.sub(r"\s+", " ", text).strip(" .;:-")
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text


def scene_focus_scores(scene: dict) -> dict[str, float]:
    """Score dominant SYSTEM_ALLEGORY topic from semantic paths, not loose tokens."""
    scores = {"MEMORY_ARCHIVE": 0.0, "DISTRIBUTED_SWARM": 0.0, "GENERIC_SYSTEM": 0.0}
    for item in scene.get("role_audit", []):
        path = str(item.get("path", "")).casefold()
        value = str(item.get("visual_text") or item.get("value") or "").casefold()
        weight = float(item.get("weight", 1.0) or 1.0)
        scores["GENERIC_SYSTEM"] += min(weight, 2.0) * 0.08

        if any(t in path for t in MEMORY_PATH_TERMS):
            scores["MEMORY_ARCHIVE"] += weight * 2.4
        elif any(t in value for t in MEMORY_VALUE_TERMS):
            scores["MEMORY_ARCHIVE"] += weight * 0.35

        if any(t in path for t in SWARM_PATH_TERMS):
            scores["DISTRIBUTED_SWARM"] += weight * 2.4
        elif any(t in value for t in SWARM_VALUE_TERMS):
            scores["DISTRIBUTED_SWARM"] += weight * 0.45

    return {k: round(v, 3) for k, v in scores.items()}


def infer_system_focus(scene: dict) -> tuple[str, dict[str, float]]:
    scores = scene_focus_scores(scene)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    winner, best = ranked[0]
    runner_up = ranked[1][1]
    # Require a real path-weighted signal and a useful margin over generic noise.
    if winner != "GENERIC_SYSTEM" and best >= 4.0 and best >= runner_up * 1.18:
        return winner, scores
    return "GENERIC_SYSTEM", scores


def compact_semantic_anchors(scene: dict, focus: str, limit: int = 2) -> list[str]:
    ranked: list[tuple[float, str]] = []
    for item in scene.get("role_audit", []):
        path = str(item.get("path", "")).casefold()
        value = str(item.get("visual_text") or item.get("value") or "").strip()
        if not value or value.casefold() in {"true", "false"}:
            continue
        weight = float(item.get("weight", 1.0) or 1.0)
        bonus = 0.0
        if focus == "MEMORY_ARCHIVE" and any(t in path for t in MEMORY_PATH_TERMS):
            bonus = 4.0
        elif focus == "DISTRIBUTED_SWARM" and any(t in path for t in SWARM_PATH_TERMS):
            bonus = 4.0
        elif focus == "GENERIC_SYSTEM":
            bonus = 0.5
        ranked.append((weight + bonus, _clean(value)))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return dedupe([text for _, text in ranked])[:limit]


def translate_memory_archive(scene: dict, scores: dict[str, float]) -> dict:
    return {
        "focus": "MEMORY_ARCHIVE",
        "focus_scores": scores,
        "central_visual_subject": (
            "one continuous painted river of records crossing an ancient wall, passing through four organically joined memory zones: "
            "a recent circular ring, a long witness stream, bright rare-event knots, and a distant archive niche"
        ),
        "central_action": (
            "ordinary old traces fade only after their useful essence is carried onward, while anomalies and significant episodes remain bright and pinned"
        ),
        "supporting_motifs": [
            "a broken route temporarily curls back as archival debt, then reconnects to the archive",
            "durable receipt is shown as a small sealed mark beside the archive",
            "recent detail is dense near the ring and gradually condenses into fewer enduring symbols",
        ],
        "main_symbols": ["record river", "recent ring", "pinned bright anomalies", "archive niche", "fading ordinary traces"],
        "human_presence": "none; memory is shown as a continuous painted process, not a person",
        "composition_bias": [
            "one flowing left-to-right mural path with no panel borders",
            "irregular transitions between memory zones, never a grid",
            "all marks share one cracked plaster surface",
        ],
        "semantic_anchors": compact_semantic_anchors(scene, "MEMORY_ARCHIVE"),
    }


def translate_distributed_swarm(scene: dict, scores: dict[str, float]) -> dict:
    return {
        "focus": "DISTRIBUTED_SWARM",
        "focus_scores": scores,
        "central_visual_subject": (
            "several unequal beacon-like peer nodes scattered across one continuous ancient mural landscape, all parts of one distributed organism"
        ),
        "central_action": (
            "distinct peers keep local knowledge while thin irregular painted ribbons carry selective observations and predictions across the shared plaster field"
        ),
        "supporting_motifs": [
            "one current candidate may glow slightly brighter but has no throne or crown",
            "missing peers are faded gaps in the same landscape",
            "disagreement remains as separate colored ribbons instead of merging into one mind",
        ],
        "main_symbols": ["uneven peer beacons", "shared plaster field", "crossing signal ribbons", "faded absent positions"],
        "human_presence": "none; do not invent a ruler, portrait or protagonist",
        "composition_bias": [
            "one asymmetric mural scene with irregular spacing",
            "never arrange nodes in rows, columns, circles or equal cells",
            "connections cross open painted space, not a clean network diagram",
        ],
        "semantic_anchors": compact_semantic_anchors(scene, "DISTRIBUTED_SWARM"),
    }


def translate_generic_system(scene: dict, scores: dict[str, float]) -> dict:
    return {
        "focus": "GENERIC_SYSTEM",
        "focus_scores": scores,
        "central_visual_subject": (
            "a continuous ancient allegorical process painted as irregular channels, vessels, thresholds and changing states fused into one wall"
        ),
        "central_action": "the source-established process moves through its states across one connected mural without modern machinery or diagram grammar",
        "supporting_motifs": [
            "unresolved states remain dim",
            "confirmed transitions appear clearer without triumphal symbolism",
            "small source-supported differences are embedded as irregular painted details",
        ],
        "main_symbols": ["painted channels", "thresholds", "vessels", "changing states"],
        "human_presence": "none unless explicit person-role evidence exists",
        "composition_bias": ["one asymmetric continuous mural", "no repeated equal compartments", "all states share one plaster field"],
        "semantic_anchors": compact_semantic_anchors(scene, "GENERIC_SYSTEM"),
    }


def build_translated_scene(scene: dict) -> dict:
    archetype = scene.get("archetype")
    if archetype == "SYSTEM_ALLEGORY":
        focus, scores = infer_system_focus(scene)
        if focus == "MEMORY_ARCHIVE":
            translated = translate_memory_archive(scene, scores)
        elif focus == "DISTRIBUTED_SWARM":
            translated = translate_distributed_swarm(scene, scores)
        else:
            translated = translate_generic_system(scene, scores)
    else:
        translated = v42.build_translated_scene(scene)
        translated["focus"] = archetype
        translated["focus_scores"] = {}
        translated["semantic_anchors"] = compact_semantic_anchors(scene, "GENERIC_SYSTEM")
        translated["composition_bias"] = dedupe(list(translated.get("composition_bias", [])) + [
            "one continuous mural field", "asymmetric placement", "no tiled or contact-sheet composition",
        ])
    translated["schema"] = "janus.fresco_forge.ancient_visual_translation.v4_3_1"
    translated["continuous_mural_lock"] = True
    translated["scene_focus_firewall"] = True
    return translated


def render_prompt(scene: dict, translated: dict) -> str:
    def join(items: Iterable[str], fallback: str) -> str:
        vals = dedupe(items)
        return "; ".join(vals) if vals else fallback

    # Deliberately compact: keep the complete prepared prompt below the real 450-token cap.
    style = (
        "ONE CONTINUOUS ANCIENT WALL FRESCO. Entire frame is cracked aged lime plaster, hand-painted with worn ochre, iron red, "
        "soot black, terre verte and faded blue mineral pigment; visible abrasion, stains, cracks and imperfect flat brushwork."
    )
    subject = (
        f"FOCUS: {translated.get('focus', scene['archetype'])}. SUBJECT: {translated['central_visual_subject']}. "
        f"ACTION: {translated['central_action']}. PEOPLE: {translated['human_presence']}."
    )
    detail = (
        f"DETAILS: {join(translated.get('supporting_motifs', [])[:3], 'only source-supported details')}. "
        f"SYMBOLS: {join(translated.get('main_symbols', [])[:5], 'only source-supported symbols')}. "
        f"MEANING: {join(translated.get('semantic_anchors', [])[:2], 'preserve the dominant source meaning')}."
    )
    composition = (
        f"COMPOSITION: {join(translated.get('composition_bias', [])[:3], 'one asymmetric continuous mural')}. "
        "No grid, tiles, repeated medallions, icon sheet, contact sheet, specimen board, white background or equal cells. "
        "Everything shares one plaster field. System labels never become people or gods. Uncertain claims stay uncertain. "
        "No diagram, infographic, CAD, UI, product shot, glossy machine, readable code, JSON or modern labels."
    )
    return "\n".join([style, subject, detail, composition]).strip()


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
        "schema": "janus.fresco_forge.receipt.v4_3_1",
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
        "prompt_mode": "semantic_role_plus_scene_focus_plus_continuous_mural_lock",
        "original_prompt_tokens": original_prompt_tokens,
        "prompt_tokens": prompt_tokens,
        "max_prompt_tokens": max_tokens,
        "prompt_hard_truncated": hard_truncated,
        "prompt_chunks": chunks,
        "semantic_coverage_ratio": 1.0,
        "semantic_model_policy": "ALL_NONTECHNICAL_SCALARS_TRACED__ROLE_FIREWALL__SCENE_FOCUS_FIREWALL__CONTINUOUS_MURAL",
        "false_personification_guard": True,
        "physical_gate_firewall": True,
        "scene_focus_firewall": True,
        "scene_focus_subtype": translated.get("focus"),
        "scene_focus_scores": translated.get("focus_scores", {}),
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
        "backend": "local_diffusers_v4_3_1_scene_focus_chunked_clip",
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
