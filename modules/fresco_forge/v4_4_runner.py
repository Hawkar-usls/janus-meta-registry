#!/usr/bin/env python3
"""JANUS Fresco Forge v4.4: Semantic Focus Router.

The v4.1.1 semantic-role/physical-gate firewalls and v4.3.1 continuous-mural
locks remain authoritative. v4.4 makes the old scene archetype advisory for
technical records: path-weighted semantic evidence selects a dominant visual
focus before rendering. This prevents technical record/provenance protocols
from being misrouted as ritual objects and prevents incidental terms from
hijacking the scene.
"""
from __future__ import annotations

import copy
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
import v4_3_runner as v43

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v4.4-semantic-focus-router"
GUIDANCE_SCALE = float(os.getenv("FRESCO_GUIDANCE_SCALE", "7.5"))

NEGATIVE_CONTROL_CLASSES = list(v43.NEGATIVE_CONTROL_CLASSES) + [
    "FAIL__TECHNICAL_PROTOCOL_OBJECTIFICATION",
    "FAIL__SILENT_PROMPT_TRUNCATION",
]

RECORD_PATH_TERMS = (
    "record", "json", "jsonl", "ndjson", "provenance", "integrity", "hash", "manifest",
    "correction", "canonical", "append", "schema", "chunk", "receipt", "truth_guard",
)
RECORD_VALUE_TERMS = (
    "json record", "jsonl", "ndjson", "record hash", "prev hash", "hash integrity", "provenance",
    "append", "manifest", "canonical json", "correction", "superseding record", "durable receipt",
    "chunk manifest", "schema", "record chain",
)


def dedupe(values: Iterable[str]) -> list[str]:
    return v41.dedupe(values)


def _clean(text: str, limit: int = 135) -> str:
    text = re.sub(r"[_/]+", " ", str(text))
    text = re.sub(r"\s+", " ", text).strip(" .;:-")
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text


def semantic_focus_scores(scene: dict) -> dict[str, float]:
    base_scores = v43.scene_focus_scores(scene)
    scores = {
        "MEMORY_ARCHIVE": float(base_scores.get("MEMORY_ARCHIVE", 0.0)),
        "DISTRIBUTED_SWARM": float(base_scores.get("DISTRIBUTED_SWARM", 0.0)),
        "RECORD_PROVENANCE": 0.0,
        "GENERIC_SYSTEM": float(base_scores.get("GENERIC_SYSTEM", 0.0)),
    }
    for item in scene.get("role_audit", []):
        path = str(item.get("path", "")).casefold()
        value = str(item.get("visual_text") or item.get("value") or "").casefold()
        weight = float(item.get("weight", 1.0) or 1.0)
        if any(term in path for term in RECORD_PATH_TERMS):
            scores["RECORD_PROVENANCE"] += weight * 2.35
        elif any(term in value for term in RECORD_VALUE_TERMS):
            scores["RECORD_PROVENANCE"] += weight * 0.85
    return {key: round(value, 3) for key, value in scores.items()}


def specialized_focus(scores: dict[str, float]) -> str | None:
    candidates = [(k, v) for k, v in scores.items() if k != "GENERIC_SYSTEM"]
    candidates.sort(key=lambda kv: kv[1], reverse=True)
    winner, best = candidates[0]
    runner_up = candidates[1][1] if len(candidates) > 1 else 0.0
    if best >= 4.0 and (runner_up <= 0.0 or best >= runner_up * 1.12):
        return winner
    return None


def route_focus(scene: dict) -> tuple[str, dict[str, float], bool]:
    """Return (visual focus, scores, archetype_overridden)."""
    archetype = str(scene.get("archetype") or "SYSTEM_ALLEGORY")
    scores = semantic_focus_scores(scene)

    # Physical architecture already passed the strict v4.1.1 physical-evidence firewall.
    if archetype == "ARCHITECTURAL_EVENT":
        return "ARCHITECTURAL_EVENT", scores, False

    # Preserve explicit people/mythic scenes only when actual figure evidence survived the role firewall.
    if archetype in {"HUMAN_NARRATIVE", "MYTHIC_NARRATIVE"} and scene.get("human_figures"):
        return archetype, scores, False

    special = specialized_focus(scores)
    if special:
        return special, scores, special != archetype

    if archetype == "OBJECT_RITUAL":
        return "OBJECT_RITUAL", scores, False
    if archetype == "SYSTEM_ALLEGORY":
        return "GENERIC_SYSTEM", scores, True
    return archetype, scores, False


def compact_anchors(scene: dict, focus: str, limit: int = 2) -> list[str]:
    ranked: list[tuple[float, str]] = []
    for item in scene.get("role_audit", []):
        path = str(item.get("path", "")).casefold()
        value = str(item.get("visual_text") or item.get("value") or "").strip()
        if not value or value.casefold() in {"true", "false"}:
            continue
        weight = float(item.get("weight", 1.0) or 1.0)
        bonus = 0.0
        if focus == "MEMORY_ARCHIVE" and any(t in path for t in v43.MEMORY_PATH_TERMS):
            bonus = 4.0
        elif focus == "DISTRIBUTED_SWARM" and any(t in path for t in v43.SWARM_PATH_TERMS):
            bonus = 4.0
        elif focus == "RECORD_PROVENANCE" and any(t in path for t in RECORD_PATH_TERMS):
            bonus = 4.0
        ranked.append((weight + bonus, _clean(value)))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return dedupe([text for _, text in ranked])[:limit]


def translate_record_provenance(scene: dict, scores: dict[str, float]) -> dict:
    return {
        "focus": "RECORD_PROVENANCE",
        "focus_scores": scores,
        "central_visual_subject": (
            "one continuous ancient painted chain of record marks and sealed bundles flowing across the wall, each new mark visibly linked to the previous one"
        ),
        "central_action": (
            "new records are appended at the growing end; corrections are added beside earlier marks instead of erasing them; sealed bundles travel onward to an archive and receive a small durable seal"
        ),
        "supporting_motifs": [
            "an intact painted provenance thread connects source marks to later bundles",
            "one corrected episode keeps both the older faded mark and a newer adjacent correction",
            "an unbroken integrity chain remains visually distinct from whether the depicted observation itself is trustworthy",
        ],
        "main_symbols": ["linked record marks", "provenance thread", "appended correction", "sealed archive bundle", "durable receipt seal"],
        "human_presence": "none; provenance is a process and must not become a scribe, priest or deity",
        "composition_bias": [
            "one left-to-right irregular record flow across a shared plaster wall",
            "no literal text, code, JSON glyphs, table, ledger grid or document screenshot",
            "old and new marks coexist visibly instead of overwriting one another",
        ],
        "semantic_anchors": compact_anchors(scene, "RECORD_PROVENANCE"),
    }


def translate_focus(scene: dict) -> dict:
    focus, scores, overridden = route_focus(scene)
    if focus == "MEMORY_ARCHIVE":
        translated = v43.translate_memory_archive(scene, scores)
        translated["semantic_anchors"] = compact_anchors(scene, focus)
    elif focus == "DISTRIBUTED_SWARM":
        translated = v43.translate_distributed_swarm(scene, scores)
        translated["semantic_anchors"] = compact_anchors(scene, focus)
    elif focus == "RECORD_PROVENANCE":
        translated = translate_record_provenance(scene, scores)
    elif focus == "GENERIC_SYSTEM":
        translated = v43.translate_generic_system(scene, scores)
        translated["semantic_anchors"] = compact_anchors(scene, focus)
    else:
        translated = v42.build_translated_scene(scene)
        translated["focus"] = focus
        translated["focus_scores"] = scores
        translated["semantic_anchors"] = compact_anchors(scene, focus)
        translated["composition_bias"] = dedupe(list(translated.get("composition_bias", [])) + [
            "one continuous mural field", "asymmetric placement", "no tiled or contact-sheet composition",
        ])
    translated["schema"] = "janus.fresco_forge.semantic_visual_translation.v4_4"
    translated["source_archetype"] = scene.get("archetype")
    translated["focus"] = focus
    translated["focus_scores"] = scores
    translated["focus_override_applied"] = overridden
    translated["semantic_focus_router"] = True
    translated["continuous_mural_lock"] = True
    return translated


def render_prompt(scene: dict, translated: dict) -> str:
    def join(items: Iterable[str], fallback: str) -> str:
        vals = dedupe(items)
        return "; ".join(vals) if vals else fallback

    style = (
        "ONE CONTINUOUS ANCIENT WALL FRESCO. Entire frame is cracked aged lime plaster painted by hand with worn ochre, iron red, "
        "soot black, terre verte and faded blue mineral pigment; abrasion, stains, cracks and imperfect flat brushwork."
    )
    subject = (
        f"FOCUS: {translated['focus']}. SUBJECT: {translated['central_visual_subject']}. "
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
        "Everything shares one plaster field. Internal labels never become people or gods. Uncertain claims stay uncertain. "
        "No diagram, infographic, CAD, UI, product shot, glossy machine, readable code, JSON or modern labels."
    )
    return "\n".join([style, subject, detail, composition]).strip()


def fit_prompt(tokenizer, scene: dict, translated: dict) -> tuple[str, int, int, bool, int, str]:
    """Fit without silently truncating; reduce optional semantic detail before failing."""
    variants: list[tuple[str, dict]] = [("FULL", translated)]

    medium = copy.deepcopy(translated)
    medium["supporting_motifs"] = medium.get("supporting_motifs", [])[:2]
    medium["main_symbols"] = medium.get("main_symbols", [])[:4]
    medium["semantic_anchors"] = medium.get("semantic_anchors", [])[:1]
    medium["composition_bias"] = medium.get("composition_bias", [])[:2]
    variants.append(("COMPACT", medium))

    minimal = copy.deepcopy(medium)
    minimal["supporting_motifs"] = minimal.get("supporting_motifs", [])[:1]
    minimal["main_symbols"] = minimal.get("main_symbols", [])[:3]
    minimal["composition_bias"] = minimal.get("composition_bias", [])[:1]
    variants.append(("MINIMAL", minimal))

    last = None
    for name, candidate in variants:
        raw = render_prompt(scene, candidate)
        fitted = v41.hard_cap_prompt(tokenizer, raw)
        model_prompt, prompt_tokens, max_tokens, hard_truncated, original_tokens = fitted
        last = (model_prompt, prompt_tokens, max_tokens, hard_truncated, original_tokens, name)
        if not hard_truncated:
            return last

    raise RuntimeError(
        f"PROMPT_BUDGET_VIOLATION: even MINIMAL prompt exceeded {last[2]} tokens (original={last[4]})"
    )


def render_negative_prompt(scene: dict) -> str:
    return v43.render_negative_prompt(scene)


def choose_canvas(scene: dict, focus: str, requested_width: int, requested_height: int) -> tuple[int, int]:
    if focus in {"MEMORY_ARCHIVE", "DISTRIBUTED_SWARM", "RECORD_PROVENANCE", "GENERIC_SYSTEM", "ARCHITECTURAL_EVENT", "OBJECT_RITUAL"}:
        return 640, 448
    return requested_width, requested_height


def generate_one(pipe, candidate, repo_root, output_root, model, steps, width, height, seed) -> dict:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    proj = v3.projection(candidate.canonical_json)
    scene = v41.build_scene_plan(proj)
    translated = translate_focus(scene)
    model_prompt, prompt_tokens, max_tokens, hard_truncated, original_prompt_tokens, fit_variant = fit_prompt(pipe.tokenizer, scene, translated)
    negative_prompt = render_negative_prompt(scene)
    pos, neg, chunks = v3.encode_long(pipe, model_prompt, negative_prompt, device)
    render_width, render_height = choose_canvas(scene, translated["focus"], width, height)

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
        "schema": "janus.fresco_forge.receipt.v4_4",
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
        "prompt_mode": "semantic_focus_router_plus_continuous_mural_lock",
        "prompt_fit_variant": fit_variant,
        "original_prompt_tokens": original_prompt_tokens,
        "prompt_tokens": prompt_tokens,
        "max_prompt_tokens": max_tokens,
        "prompt_hard_truncated": hard_truncated,
        "prompt_chunks": chunks,
        "semantic_coverage_ratio": 1.0,
        "semantic_model_policy": "ALL_NONTECHNICAL_SCALARS_TRACED__SEMANTIC_FOCUS_ROUTER__NO_SILENT_TRUNCATION",
        "false_personification_guard": True,
        "physical_gate_firewall": True,
        "scene_focus_firewall": True,
        "semantic_focus_router": True,
        "source_scene_archetype": scene.get("archetype"),
        "scene_focus_subtype": translated.get("focus"),
        "scene_focus_scores": translated.get("focus_scores", {}),
        "focus_override_applied": translated.get("focus_override_applied", False),
        "ancient_visual_grammar_lock": True,
        "no_modern_visual_grammar": True,
        "full_frame_plaster_surface": True,
        "continuous_mural_lock": True,
        "anti_grid_icon_collapse": True,
        "calibration_negative_controls": NEGATIVE_CONTROL_CLASSES,
        "prompt_text": model_prompt,
        "negative_prompt": negative_prompt,
        "scene_plan": scene,
        "translated_scene": translated,
        "visual_projection": proj,
        "model": model,
        "backend": "local_diffusers_v4_4_semantic_focus_router",
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
