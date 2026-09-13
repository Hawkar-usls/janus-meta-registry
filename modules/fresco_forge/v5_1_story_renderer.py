#!/usr/bin/env python3
"""JANUS Fresco Forge v5.1: Monumental Density + Visual Collapse Gates.

v5.1 is a calibration successor to v5.0. It keeps the semantic-role and
epistemic firewalls while hardening the visual contract after the first v5
calibration render collapsed into an isolated emblem/still-life with pseudo-text.

The renderer now requires a populated architectural world, multiple narrative
groups, layered depth, a strong central event, and no reserved inscription zones.
A lightweight image-complexity gate rejects low-detail/emblem-like outputs and
retries with a denser composition. It does not claim OCR or human detection.
"""
from __future__ import annotations

import copy
import json
import math
import os
import time
from pathlib import Path
from typing import Iterable

import torch
from PIL import Image, ImageFilter, ImageStat

import forge as base
import v3_runner as v3
import v4_1_runner as v41
import v4_1_1_runner as firewall  # noqa: F401
import v5_story_renderer as v5

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v5.1-monumental-density-gates"
ART_DIRECTION_ID = "JANUS_MONUMENTAL_ALLEGORICAL_FRESCO_V5_1"
GUIDANCE_SCALE = float(os.getenv("FRESCO_GUIDANCE_SCALE", "7.2"))
MAX_RENDER_ATTEMPTS = max(1, int(os.getenv("FRESCO_V5_MAX_RENDER_ATTEMPTS", "3")))
MIN_FIGURE_TARGET = max(7, int(os.getenv("FRESCO_V5_MIN_FIGURE_TARGET", "10")))
MIN_SECONDARY_GROUPS = max(2, int(os.getenv("FRESCO_V5_MIN_SECONDARY_GROUPS", "3")))

NEGATIVE_CONTROL_CLASSES = list(v5.NEGATIVE_CONTROL_CLASSES) + [
    "FAIL__EMBLEM_COLLAPSE",
    "FAIL__INSUFFICIENT_NARRATIVE_DENSITY",
    "FAIL__NO_ARCHITECTURAL_WORLD",
    "FAIL__NO_SECONDARY_NARRATIVE",
    "FAIL__EMPTY_FIELD_COLLAPSE",
    "FAIL__PSEUDOTEXT_BAND_RISK",
]

FORBIDDEN_COMPOSITIONS = (
    "isolated object study",
    "still life",
    "single shelf",
    "small shrine",
    "single niche",
    "single emblem",
    "icon on blank field",
    "poster layout",
    "museum specimen",
    "product shot",
    "single centered object",
)

FAMILY_REQUIREMENTS = {
    "ARCHIVE_LABYRINTH": {
        "figure_target": 14,
        "architecture": "vast stacked libraries, arcades, bridges, spiral stairs, archive chambers and a distant illuminated city",
        "groups": "scribes comparing fragments, carriers moving sealed bundles, witnesses guarding an anomaly, travelers crossing a bridge",
    },
    "GARDEN_OF_MEMORY": {
        "figure_target": 13,
        "architecture": "terraced gardens, colonnades, fountains, study alcoves, bridges and distant towers",
        "groups": "readers, gardeners, witnesses, messengers and small groups preserving fragile objects",
    },
    "PROCESSION_OF_KEEPERS": {
        "figure_target": 16,
        "architecture": "several levels of stairs, monumental arches, bridges, archive courts and a luminous gate",
        "groups": "keepers in procession, witnesses at landings, archivists below, messengers crossing side bridges",
    },
    "DESCENT_AND_ASCENT": {
        "figure_target": 15,
        "architecture": "stacked terraces descending into shadow and rising through arches toward a bright upper city",
        "groups": "descending mourners, ascending keepers, observers on balconies and restorers in side chambers",
    },
    "OBSERVATORY_CITY": {
        "figure_target": 15,
        "architecture": "a panoramic observatory city of towers, domes, star courts, bridges, stairs and distant civic halls",
        "groups": "separate skywatchers, signal keepers, map readers, messengers and witnesses on multiple terraces",
    },
    "BRIDGES_OF_WITNESSES": {
        "figure_target": 14,
        "architecture": "interlaced bridges between towers, libraries, gatehouses and elevated courts",
        "groups": "independent witness groups, messengers, observers and keepers exchanging selected signals",
    },
    "ASSEMBLY_OF_WATCHERS": {
        "figure_target": 16,
        "architecture": "a vast civic court with arcades, stairs, balconies, side chambers and a distant city",
        "groups": "several distinct assemblies, dissenting witnesses, observers, record keepers and travelers",
    },
    "CELESTIAL_COURT": {
        "figure_target": 14,
        "architecture": "a monumental celestial court with vaulted arches, observatory galleries, terraces and distant towers",
        "groups": "astronomers, witnesses, keepers, pilgrims and messengers distributed across several levels",
    },
    "CHAIN_OF_WITNESSES": {
        "figure_target": 18,
        "architecture": "a long sequence of linked courts, bridges, stairs and archive halls across changing historical layers",
        "groups": "witnesses passing sealed objects, archivists checking handoffs, messengers and observers at each transition",
    },
    "WORKSHOP_OF_RECORDS": {
        "figure_target": 13,
        "architecture": "a deep multi-room workshop of arches, archive alcoves, galleries, stairs and distant halls",
        "groups": "scribes, artisans, seal keepers, couriers and witnesses working in separate clusters",
    },
    "THRESHOLD_COMPLEX": {
        "figure_target": 12,
        "architecture": "a monumental complex of gates, chambers, stairways, bridges, sealed passages and deep perspective",
        "groups": "attendants inspecting transitions, travelers waiting, witnesses observing, keepers securing closed routes",
    },
    "RUIN_AND_RECONSTRUCTION": {
        "figure_target": 18,
        "architecture": "broken monumental ruins transitioning into rebuilt arches, scaffoldings, bridges and a restored distant city",
        "groups": "mourners, builders, chroniclers, stone workers, children and witnesses distributed across the site",
    },
    "BRIDGES_OF_TIME": {
        "figure_target": 14,
        "architecture": "two contrasting bridge systems, towers, gatehouses, stairways and a central guarded threshold",
        "groups": "travelers on opposing paths, observers, keepers and messengers at converging levels",
    },
    "CITY_OF_GATES": {
        "figure_target": 17,
        "architecture": "a layered panoramic city of monumental gates, arcades, towers, bridges, stairs and inner courts",
        "groups": "travelers, gate keepers, observers, builders and archivists acting in many small scenes",
    },
    "TRIAL_OF_CHOICES": {
        "figure_target": 14,
        "architecture": "a grand judgment court with colonnades, stairs, side galleries and contrasting distant landscapes",
        "groups": "a central decision group, witnesses, mourners, advisers and people living out different consequences",
    },
    "PROCESSIONAL_GATEWAY": {
        "figure_target": 16,
        "architecture": "a gigantic gateway with nested courts, layered staircases, side chapels, bridges and a distant city",
        "groups": "a central procession, witnesses on balconies, keepers at side doors and travelers in lower courts",
    },
    "WORKSHOP_OF_WITNESSES": {
        "figure_target": 15,
        "architecture": "a vast working court with arches, workshops, stairways, galleries and observation platforms",
        "groups": "builders, observers, test groups, record keepers and witnesses working around one central event",
    },
    "THRONE_AND_WORLD": {
        "figure_target": 12,
        "architecture": "a monumental throne or Janus-like gateway above a living multi-level city of arcades, stairs and side chambers",
        "groups": "keepers, pilgrims, scholars, witnesses and children inhabiting smaller narrative registers below",
    },
    "RELIC_CHAMBER": {
        "figure_target": 10,
        "architecture": "a vast relic hall with multiple arches, stairs, side workshops, witness galleries and distant courts",
        "groups": "artisans testing the object, witnesses observing, archivists recording passage and keepers guarding side chambers",
    },
}

STYLE_CORE = (
    "JANUS monumental allegorical fresco: a museum-scale old-master narrative mural, "
    "dense multi-figure storytelling, Renaissance and neoclassical allegorical grandeur, "
    "antique engraving-level detail translated into weathered fresco material, layered architecture, "
    "deep spatial world-building, expressive natural figures, cracked lime plaster, worn stone, muted gilding, "
    "deep ultramarine, ochre, ivory, sepia and restrained crimson"
)

NO_TEXT_CLAUSE = (
    "Absolutely no readable text and no text-shaped decoration: no letters, words, inscriptions, captions, "
    "labels, banners, title strips, plaques, scroll writing, decorative calligraphy, pseudo-alphabet or glyph rows. "
    "Books, tablets, plaques and scrolls must be closed, blank, turned away, or too small to show writing. "
    "Do not reserve empty horizontal zones at the top or bottom for titles."
)

DENSITY_CLAUSE = (
    "Fill the frame edge to edge with a coherent inhabited world. The central event must occupy only part of the image; "
    "surround it with foreground, middle distance and far background, at least three separate human groups, "
    "secondary episodes, deep architecture, routes, stairs, bridges and distant structures. "
    "The viewer should discover new meaningful actions on repeated inspection."
)

ANTI_EMBLEM_CLAUSE = (
    "This must not become an emblem, icon, still life, shelf display, isolated relic, single niche, centered object study, "
    "poster, diagram or decorative symbol sheet. Avoid blank parchment-like fields and empty walls around a small subject."
)


def dedupe(values: Iterable[str]) -> list[str]:
    return v41.dedupe(values)


def enrich_story(story: dict) -> dict:
    out = copy.deepcopy(story)
    family = str(out.get("scene_family") or "")
    req = FAMILY_REQUIREMENTS.get(
        family,
        {
            "figure_target": MIN_FIGURE_TARGET,
            "architecture": "grand layered arches, stairs, bridges, galleries and a distant city or landscape",
            "groups": "keepers, observers, witnesses and travelers acting in several distinct groups",
        },
    )
    out["schema"] = "janus.fresco_forge.story_plan.v5_1"
    out["art_direction"] = ART_DIRECTION_ID
    out["figure_target"] = max(MIN_FIGURE_TARGET, int(req["figure_target"]))
    out["secondary_group_target"] = MIN_SECONDARY_GROUPS
    out["architecture_contract"] = req["architecture"]
    out["human_group_contract"] = req["groups"]
    out["depth_layers"] = ["foreground", "middle_distance", "far_background"]
    out["monumental_frame_required"] = True
    out["full_frame_population_required"] = True
    out["forbidden_compositions"] = list(FORBIDDEN_COMPOSITIONS)
    out["typography_policy"] = "NO_TEXT_NO_RESERVED_TEXT_ZONES"
    out["quality_gate"] = "V5_1_LIGHTWEIGHT_VISUAL_COMPLEXITY_GATE"
    return out


def choose_story(scene: dict, source_sha256: str, output_root: Path) -> dict:
    return enrich_story(v5.choose_story(scene, source_sha256, output_root))


def mutate_story_for_retry(story: dict, attempt_index: int) -> dict:
    out = copy.deepcopy(story)
    if attempt_index <= 0:
        return out

    style_keys = tuple(v5.STYLE_FAMILIES)
    try:
        start = style_keys.index(out["style_family"])
    except (ValueError, KeyError):
        start = 0
    style_key = style_keys[(start + attempt_index) % len(style_keys)]
    out["style_family"] = style_key
    out["style_description"] = v5.STYLE_FAMILIES[style_key]
    out["figure_target"] = min(22, int(out.get("figure_target", MIN_FIGURE_TARGET)) + attempt_index * 3)
    out["composition"] = (
        str(out.get("composition") or "")
        + "; expand the world laterally and vertically, use multiple architectural levels, "
        + "overlapping figure groups and long sight lines so no single object can dominate the frame"
    )
    out["micro_scenes"] = dedupe(
        list(out.get("micro_scenes", []))
        + [
            "a side group exchanges knowledge under an arch while another group crosses a distant bridge",
            "small witnesses and workers occupy balconies, stairs and a far court to create layered human scale",
        ]
    )
    out["retry_density_boost"] = attempt_index
    return out


def render_prompt(scene: dict, story: dict) -> str:
    hints = story.get("source_story_hints", [])
    hint_clause = ""
    if hints:
        hint_clause = (
            "Let the actions and relationships quietly express the source meaning of "
            + " and ".join(hints[:2])
            + ", but never render those words as writing. "
        )

    micro = "; ".join(story.get("micro_scenes", [])[:4])
    symbols = ", ".join(story.get("symbols", [])[:6])
    return (
        f"{STYLE_CORE}. "
        f"Use this internal variant: {story['style_description']}. "
        f"Build {story['composition']}. "
        f"Architecture must include {story['architecture_contract']}. "
        f"The central event is this: {story['central_subject']}; {story['central_action']}. "
        f"Populate the mural with roughly {story['figure_target']} human-scale figures arranged in at least "
        f"{story['secondary_group_target']} distinct narrative groups: {story['human_group_contract']}. "
        f"Secondary episodes include: {micro}. "
        f"Recurring symbolic objects may include {symbols}, but symbols must stay subordinate to people, actions and architecture. "
        f"{DENSITY_CLAUSE} {hint_clause}"
        f"The mood is {story['mood']}. Keep unresolved claims visibly unresolved and non-triumphal. "
        "Internal system names remain mechanisms, processes or provenance and never become invented named humans or deities. "
        f"{NO_TEXT_CLAUSE} {ANTI_EMBLEM_CLAUSE}"
    ).strip()


def fit_prompt(tokenizer, scene: dict, story: dict) -> tuple[str, int, int, bool, int, str]:
    variants: list[tuple[str, dict]] = [("FULL", story)]

    compact = copy.deepcopy(story)
    compact["micro_scenes"] = compact.get("micro_scenes", [])[:3]
    compact["symbols"] = compact.get("symbols", [])[:4]
    compact["source_story_hints"] = compact.get("source_story_hints", [])[:1]
    variants.append(("COMPACT", compact))

    minimal = copy.deepcopy(compact)
    minimal["micro_scenes"] = minimal.get("micro_scenes", [])[:2]
    minimal["symbols"] = minimal.get("symbols", [])[:3]
    minimal["source_story_hints"] = []
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
        f"PROMPT_BUDGET_VIOLATION: even MINIMAL v5.1 prompt exceeded {last[2]} tokens "
        f"(original={last[4]})"
    )


def render_negative_prompt(scene: dict) -> str:
    negatives = [
        v5.render_negative_prompt(scene),
        "isolated object", "single centered object", "still life", "shelf display", "small shrine",
        "single niche", "emblem", "icon on blank background", "poster composition", "museum specimen",
        "empty wall", "blank parchment", "large empty background", "minimal composition",
        "single vase", "single vessel", "single altar object", "object study",
        "text banner", "title strip", "caption strip", "writing area", "inscription panel",
        "readable text", "letters", "words", "pseudo text", "gibberish text", "decorative script",
        "logo", "watermark", "label", "glyph row", "fake alphabet",
        "diagram", "infographic", "dashboard", "technical schematic", "UI", "icon grid",
    ]
    return ", ".join(dedupe(negatives))


def _entropy(gray: Image.Image) -> float:
    hist = gray.histogram()
    total = float(sum(hist)) or 1.0
    value = 0.0
    for count in hist:
        if count:
            p = count / total
            value -= p * math.log2(p)
    return value


def _edge_mean(gray: Image.Image) -> float:
    edge = gray.filter(ImageFilter.FIND_EDGES)
    return float(ImageStat.Stat(edge).mean[0]) / 255.0


def _region(gray: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    w, h = gray.size
    left = max(0, min(w - 1, int(box[0] * w)))
    top = max(0, min(h - 1, int(box[1] * h)))
    right = max(left + 1, min(w, int(box[2] * w)))
    bottom = max(top + 1, min(h, int(box[3] * h)))
    return gray.crop((left, top, right, bottom))


def visual_complexity_metrics(image: Image.Image) -> dict:
    gray = image.convert("L").resize((256, 256))
    entropy = _entropy(gray)
    edge_density = _edge_mean(gray)

    center = _region(gray, (0.25, 0.20, 0.75, 0.80))
    outer_regions = [
        _region(gray, (0.00, 0.00, 0.25, 1.00)),
        _region(gray, (0.75, 0.00, 1.00, 1.00)),
        _region(gray, (0.25, 0.00, 0.75, 0.20)),
        _region(gray, (0.25, 0.80, 0.75, 1.00)),
    ]
    center_edge = _edge_mean(center)
    outer_edge = sum(_edge_mean(region) for region in outer_regions) / len(outer_regions)
    center_concentration = center_edge / max(outer_edge, 1e-4)

    empty_tiles = 0
    tile_count = 0
    for y in range(4):
        for x in range(4):
            tile = gray.crop((x * 64, y * 64, (x + 1) * 64, (y + 1) * 64))
            stat = ImageStat.Stat(tile)
            variance = float(stat.var[0])
            tile_edge = _edge_mean(tile)
            tile_count += 1
            if variance < 110.0 and tile_edge < 0.055:
                empty_tiles += 1
    empty_field_ratio = empty_tiles / max(tile_count, 1)

    top_edge = _edge_mean(_region(gray, (0.08, 0.00, 0.92, 0.15)))
    bottom_edge = _edge_mean(_region(gray, (0.08, 0.82, 0.92, 1.00)))
    middle_edge = _edge_mean(_region(gray, (0.08, 0.20, 0.92, 0.78)))
    caption_band_edge_ratio = max(top_edge, bottom_edge) / max(middle_edge, 1e-4)

    return {
        "entropy_bits": round(entropy, 4),
        "edge_density": round(edge_density, 5),
        "center_edge_density": round(center_edge, 5),
        "outer_edge_density": round(outer_edge, 5),
        "center_concentration": round(center_concentration, 4),
        "empty_field_ratio": round(empty_field_ratio, 4),
        "caption_band_edge_ratio": round(caption_band_edge_ratio, 4),
        "method": "PIL_GRAYSCALE_ENTROPY_EDGE_TILE_HEURISTIC__NO_OCR_NO_PERSON_DETECTION",
    }


def quality_gate(metrics: dict) -> list[str]:
    reasons: list[str] = []
    entropy = float(metrics["entropy_bits"])
    edge_density = float(metrics["edge_density"])
    empty = float(metrics["empty_field_ratio"])
    center = float(metrics["center_concentration"])
    caption_ratio = float(metrics["caption_band_edge_ratio"])

    if entropy < 5.65 or edge_density < 0.050:
        reasons.append("FAIL__LOW_DETAIL_PRIMITIVE_MURAL")
    if empty > 0.50:
        reasons.append("FAIL__EMPTY_FIELD_COLLAPSE")
    if center > 2.25 and empty > 0.30:
        reasons.append("FAIL__EMBLEM_COLLAPSE")
    if caption_ratio > 1.85 and empty > 0.25:
        reasons.append("FAIL__PSEUDOTEXT_BAND_RISK")
    return dedupe(reasons)


def choose_canvas(story: dict, requested_width: int, requested_height: int) -> tuple[int, int]:
    return v5.choose_canvas(story, requested_width, requested_height)


def _render_attempt(
    pipe,
    scene: dict,
    story: dict,
    device: str,
    steps: int,
    width: int,
    height: int,
    seed: int,
) -> tuple[Image.Image, dict]:
    model_prompt, prompt_tokens, max_tokens, hard_truncated, original_prompt_tokens, fit_variant = fit_prompt(
        pipe.tokenizer, scene, story
    )
    negative_prompt = render_negative_prompt(scene)
    pos, neg, chunks = v3.encode_long(pipe, model_prompt, negative_prompt, device)
    render_width, render_height = choose_canvas(story, width, height)

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
    metrics = visual_complexity_metrics(image)
    failures = quality_gate(metrics)
    attempt_meta = {
        "seed": seed,
        "elapsed_seconds": elapsed,
        "prompt_text": model_prompt,
        "negative_prompt": negative_prompt,
        "prompt_fit_variant": fit_variant,
        "original_prompt_tokens": original_prompt_tokens,
        "prompt_tokens": prompt_tokens,
        "max_prompt_tokens": max_tokens,
        "prompt_hard_truncated": hard_truncated,
        "prompt_chunks": chunks,
        "width": render_width,
        "height": render_height,
        "visual_metrics": metrics,
        "gate_failures": failures,
        "quality_gate_pass": not failures,
        "style_family": story.get("style_family"),
        "figure_target": story.get("figure_target"),
        "retry_density_boost": story.get("retry_density_boost", 0),
    }
    return image, attempt_meta


def generate_one(pipe, candidate, repo_root, output_root, model, steps, width, height, seed) -> dict:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    proj = v3.projection(candidate.canonical_json)
    scene = v41.build_scene_plan(proj)
    base_story = choose_story(scene, candidate.source_sha256, output_root)

    attempts: list[dict] = []
    accepted_image = None
    accepted_story = None
    accepted_meta = None

    for attempt_index in range(MAX_RENDER_ATTEMPTS):
        story = mutate_story_for_retry(base_story, attempt_index)
        attempt_seed = (int(seed) + attempt_index * 104729) % (2**32)
        image, attempt_meta = _render_attempt(
            pipe=pipe,
            scene=scene,
            story=story,
            device=device,
            steps=steps,
            width=width,
            height=height,
            seed=attempt_seed,
        )
        attempt_meta["attempt_index"] = attempt_index + 1
        attempts.append(attempt_meta)
        accepted_image = image
        accepted_story = story
        accepted_meta = attempt_meta
        if attempt_meta["quality_gate_pass"]:
            break

    passed = bool(accepted_meta and accepted_meta["quality_gate_pass"])

    basename = f"{candidate.source_sha256[:16]}--{base.safe_stem(candidate.path)}"
    if passed:
        image_path = output_root / "images" / f"{basename}.png"
        receipt_path = output_root / "receipts" / f"{basename}.json"
        status = "generated"
    else:
        image_path = output_root / "calibration_failures" / f"{basename}.png"
        receipt_path = output_root / "calibration_failures" / f"{basename}.json"
        status = "rejected_visual_collapse"

    image_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = image_path.with_suffix(".tmp.png")
    accepted_image.save(tmp, format="PNG")
    tmp.replace(image_path)

    projection_json = json.dumps(proj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    scene_json = json.dumps(scene, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    story_json = json.dumps(accepted_story, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    receipt = {
        "schema": "janus.fresco_forge.receipt.v5_1",
        "generator": GENERATOR_VERSION,
        "status": status,
        "generated_at": base.utc_now(),
        "source_path": candidate.relpath,
        "source_sha256": candidate.source_sha256,
        "canonical_json_bytes": len(candidate.canonical_json.encode("utf-8")),
        "visual_projection_sha256": base.sha256_bytes(projection_json.encode("utf-8")),
        "scene_plan_sha256": base.sha256_bytes(scene_json.encode("utf-8")),
        "story_plan_sha256": base.sha256_bytes(story_json.encode("utf-8")),
        "prompt_sha256": base.sha256_bytes(accepted_meta["prompt_text"].encode("utf-8")),
        "prompt_mode": "v5_1_monumental_density_contract_plus_visual_complexity_retry_gate",
        "semantic_coverage_ratio": 1.0,
        "semantic_model_policy": (
            "CANONICAL_JSON_TO_ROLE_AUDIT_TO_MONUMENTAL_STORY"
            "__MINIMUM_HUMAN_GROUPS__ARCHITECTURAL_WORLD__NO_DIFFUSION_TYPOGRAPHY"
        ),
        "art_direction": ART_DIRECTION_ID,
        "scene_family": accepted_story["scene_family"],
        "style_family": accepted_story["style_family"],
        "composition_id": accepted_story["composition_id"],
        "palette_family": accepted_story["palette_family"],
        "figure_count_bucket": accepted_story["figure_count_bucket"],
        "figure_target": accepted_story["figure_target"],
        "secondary_group_target": accepted_story["secondary_group_target"],
        "dominant_shape": accepted_story["dominant_shape"],
        "orientation": accepted_story["orientation"],
        "anti_repeat_signature": accepted_story["anti_repeat_signature"],
        "recent_signature_window": accepted_story["recent_signature_window"],
        "typography_policy": accepted_story["typography_policy"],
        "architecture_contract": accepted_story["architecture_contract"],
        "depth_layers": accepted_story["depth_layers"],
        "full_frame_population_required": True,
        "monumental_frame_required": True,
        "false_personification_guard": True,
        "physical_gate_firewall": True,
        "epistemic_nontriumphal_guard": True,
        "narrative_event_required": True,
        "anti_grid_icon_collapse": True,
        "anti_pseudotext_prompt_gate": True,
        "visual_quality_gate": "PIL_LIGHTWEIGHT_COMPLEXITY_HEURISTIC__NO_OCR_NO_PERSON_DETECTION",
        "visual_quality_gate_pass": passed,
        "render_attempts": attempts,
        "retries_used": max(0, len(attempts) - 1),
        "final_visual_metrics": accepted_meta["visual_metrics"],
        "final_gate_failures": accepted_meta["gate_failures"],
        "calibration_negative_controls": NEGATIVE_CONTROL_CLASSES,
        "prompt_text": accepted_meta["prompt_text"],
        "negative_prompt": accepted_meta["negative_prompt"],
        "prompt_fit_variant": accepted_meta["prompt_fit_variant"],
        "original_prompt_tokens": accepted_meta["original_prompt_tokens"],
        "prompt_tokens": accepted_meta["prompt_tokens"],
        "max_prompt_tokens": accepted_meta["max_prompt_tokens"],
        "prompt_hard_truncated": accepted_meta["prompt_hard_truncated"],
        "prompt_chunks": accepted_meta["prompt_chunks"],
        "scene_plan": scene,
        "story_plan": accepted_story,
        "visual_projection": proj,
        "model": model,
        "backend": "local_diffusers_v5_1_monumental_density_gates",
        "device": device,
        "scheduler": pipe.scheduler.__class__.__name__,
        "steps": steps,
        "guidance_scale": GUIDANCE_SCALE,
        "requested_width": width,
        "requested_height": height,
        "width": accepted_meta["width"],
        "height": accepted_meta["height"],
        "seed": accepted_meta["seed"],
        "elapsed_seconds": round(sum(float(x["elapsed_seconds"]) for x in attempts), 3),
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
