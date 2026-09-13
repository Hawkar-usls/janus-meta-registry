#!/usr/bin/env python3
"""JANUS Fresco Forge v5.3: strict monumental narrative fresco gate.

This successor keeps the v5.2 semantic routing and the v5.2.1 model-native
DreamShaper scheduler, but hardens the actual image contract after the observed
v5.0 product/still-life collapse.

Core changes:
- composition-first positive prompt: crowded human mural before style/object terms;
- no source object/symbol nouns in the positive prompt;
- stronger product-photo / still-life / text negatives;
- 4:5 512x640 canvas for wider architectural storytelling;
- full-frame spatial occupancy metrics in addition to v5.2 detector metrics;
- stricter quarantine when a render is center-heavy, sparse, or person-poor.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

import forge as base
import v4_1_runner as v41
import v5_1_story_renderer as v51
import v5_2_story_renderer as v52
import v5_2_1_story_renderer as v521

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v5.3-strict-monumental-narrative"
ART_DIRECTION_ID = "JANUS_MONUMENTAL_ALLEGORICAL_FRESCO_V5_3_STRICT"
MIN_FIGURE_TARGET = max(16, int(os.getenv("FRESCO_V5_MIN_FIGURE_TARGET", "16")))
MIN_SECONDARY_GROUPS = max(4, int(os.getenv("FRESCO_V5_MIN_SECONDARY_GROUPS", "4")))

NEGATIVE_CONTROL_CLASSES = list(v51.NEGATIVE_CONTROL_CLASSES) + [
    "FAIL__LOW_SPATIAL_COVERAGE",
    "FAIL__LOW_OUTER_FRAME_ACTIVITY",
    "FAIL__INSUFFICIENT_HUMAN_SCENE",
    "FAIL__DOMINANT_OBJECT_COLLAPSE_V5_3",
]

STYLE_LEAD = (
    "museum-scale old-master allegorical wall fresco, Renaissance and neoclassical monumental grandeur, "
    "antique engraving-level detail translated into weathered lime plaster, ornate carved stone framing, "
    "deep ultramarine, old gold, ivory stone, ochre, sepia and restrained crimson"
)

FAMILY_OPENERS = {
    "ARCHIVE_LABYRINTH": (
        "A vast inhabited archive city fills the image, with scholars, guardians, couriers and apprentices "
        "moving through libraries, bridges, galleries and spiral stairs"
    ),
    "GARDEN_OF_MEMORY": (
        "A terraced garden-city fills the image, with readers, teachers, gardeners, families and witnesses "
        "moving through colonnades, fountains, bridges and study courts"
    ),
    "PROCESSION_OF_KEEPERS": (
        "A large human procession fills several architectural levels, while witnesses and keepers occupy "
        "balconies, stairs, side courts and distant bridges"
    ),
    "DESCENT_AND_ASCENT": (
        "Many people move through a vast descending and ascending city, with mourners, builders, witnesses "
        "and children distributed across shadowed and luminous architectural levels"
    ),
    "OBSERVATORY_CITY": (
        "A living observatory city fills the frame, with astronomers, apprentices, signal keepers, families "
        "and messengers distributed across towers, domes, terraces and bridges"
    ),
    "BRIDGES_OF_WITNESSES": (
        "Several independent groups of witnesses inhabit an immense bridge-city, comparing observations "
        "across towers, galleries, stairs and civic courts"
    ),
    "ASSEMBLY_OF_WATCHERS": (
        "A great civic assembly fills the frame, with many independent observers, guardians, families and "
        "messengers spread across arcades, balconies, stairs and distant plazas"
    ),
    "CELESTIAL_COURT": (
        "A silent celestial-civic court fills the frame, with many robed guardians, citizens, observers and "
        "apprentices arranged through a luminous upper vault, crowded middle galleries and a human lower court"
    ),
    "CHAIN_OF_WITNESSES": (
        "Successive human groups fill a long architectural world, handing responsibility and memory across "
        "courts, bridges, galleries and changing historical levels"
    ),
    "WORKSHOP_OF_RECORDS": (
        "A vast inhabited workshop-archive fills the image, with scribes, artisans, couriers, apprentices and "
        "witnesses working simultaneously across multiple rooms and galleries"
    ),
    "THRESHOLD_COMPLEX": (
        "A monumental complex of many gates fills the frame, inhabited by guardians, travelers, families and "
        "witnesses on stairs, bridges, balconies and deep courts"
    ),
    "RUIN_AND_RECONSTRUCTION": (
        "A vast ruined city under reconstruction fills the image, with mourners, builders, children, chroniclers "
        "and witnesses acting across scaffolds, arches, stairs and renewed civic spaces"
    ),
    "BRIDGES_OF_TIME": (
        "Several generations of people fill connected bridge systems between old and renewed cities, while "
        "guardians, families and witnesses inhabit every architectural level"
    ),
    "CITY_OF_GATES": (
        "A densely inhabited city of monumental gates fills the image, with travelers, scholars, builders, "
        "families and keepers moving through many converging paths"
    ),
    "TRIAL_OF_CHOICES": (
        "A public allegorical court fills the image, with witnesses, advisers, families and citizens occupying "
        "multiple galleries while different consequences unfold in side scenes"
    ),
    "PROCESSIONAL_GATEWAY": (
        "A monumental nested gateway fills the image with a large procession, balcony witnesses, families, "
        "keepers and travelers distributed through several architectural registers"
    ),
    "WORKSHOP_OF_WITNESSES": (
        "A vast working court fills the frame, with builders, observers, test groups, families and record keepers "
        "performing different actions across workshops, galleries and platforms"
    ),
    "THRONE_AND_WORLD": (
        "A monumental two-faced Janus-like guardian presides over a densely inhabited civic world of scholars, "
        "families, pilgrims, builders and witnesses spread through many architectural levels"
    ),
    "RELIC_CHAMBER": (
        "A vast scholarly hall fills the image, where many artisans, historians, guardians, apprentices and "
        "witnesses investigate together across side workshops, galleries and deep courts"
    ),
}

TRIPARTITE = (
    "three populated registers: a luminous celestial upper register, a crowded architectural middle register, "
    "and an intimate human lower register; foreground, middle distance and far background are all active"
)


def choose_story(scene: dict, source_sha256: str, output_root: Path) -> dict:
    story = copy.deepcopy(v52.choose_story(scene, source_sha256, output_root))
    story["schema"] = "janus.fresco_forge.story_plan.v5_3"
    story["art_direction"] = ART_DIRECTION_ID
    story["figure_target"] = max(MIN_FIGURE_TARGET, int(story.get("figure_target", MIN_FIGURE_TARGET)))
    story["secondary_group_target"] = max(
        MIN_SECONDARY_GROUPS, int(story.get("secondary_group_target", MIN_SECONDARY_GROUPS))
    )
    story["orientation"] = "PORTRAIT_4_5"
    story["dominant_shape"] = "FULL_FRAME_INHABITED_ARCHITECTURAL_WORLD"
    story["figure_count_bucket"] = "MANY_16_PLUS"
    story["typography_policy"] = "ZERO_TEXT_IN_DIFFUSION_STAGE"
    story["quality_gate"] = "V5_3_SPATIAL_OCCUPANCY_PLUS_OPTIONAL_COCO_GATE"
    story["anti_repeat_signature"] = "|".join(
        [
            str(story.get("scene_family")),
            str(story.get("style_family")),
            "V5_3_FULL_FRAME_TRIPARTITE",
            str(story.get("palette_family")),
            "MANY_16_PLUS",
        ]
    )
    return story


def mutate_story_for_retry(story: dict, attempt_index: int) -> dict:
    out = copy.deepcopy(v52.mutate_story_for_retry(story, attempt_index))
    if attempt_index <= 0:
        out["retry_density_boost"] = 0
        return out

    out["figure_target"] = min(32, max(MIN_FIGURE_TARGET, int(out.get("figure_target", MIN_FIGURE_TARGET))) + 5 * attempt_index)
    out["secondary_group_target"] = min(
        7, max(MIN_SECONDARY_GROUPS, int(out.get("secondary_group_target", MIN_SECONDARY_GROUPS))) + attempt_index
    )
    out["architecture_contract"] = (
        str(out.get("architecture_contract") or "")
        + "; extend architecture into every edge and corner with inhabited side galleries, stairs, bridges and distant courts"
    )
    out["retry_density_boost"] = attempt_index
    return out


def render_prompt(scene: dict, story: dict) -> str:
    family = str(story.get("scene_family") or "")
    opener = FAMILY_OPENERS.get(
        family,
        "A densely inhabited monumental civic world fills the entire frame, with many people acting across several architectural levels",
    )
    return (
        f"Crowded monumental narrative fresco with about {story['figure_target']} human figures across the entire frame. "
        f"{opener}. "
        f"{story['narrative_contract']}. "
        f"{TRIPARTITE}. "
        f"Architecture includes {story['architecture_contract']}. "
        f"Arrange at least {story['secondary_group_target']} visibly separate human groups performing different actions. "
        "Fill the corners and borders with inhabited architecture, side episodes, distant figures and landscape depth. "
        f"Paint it as a {STYLE_LEAD}. "
        "Expressive natural faces and anatomy, coherent perspective, layered scale, dense micro-scenes, worn gilding, "
        "cracked plaster and intricate old-master line detail."
    ).strip()


def fit_prompt(tokenizer, scene: dict, story: dict) -> tuple[str, int, int, bool, int, str]:
    raw = render_prompt(scene, story)
    model_prompt, prompt_tokens, max_tokens, hard_truncated, original_tokens = v41.hard_cap_prompt(tokenizer, raw)
    if hard_truncated:
        raw = (
            f"Crowded monumental allegorical fresco with {story['figure_target']} people filling the whole frame. "
            f"{FAMILY_OPENERS.get(str(story.get('scene_family') or ''), 'A densely inhabited civic world fills every region of the image')}. "
            f"{TRIPARTITE}. {story['architecture_contract']}. "
            "Several distinct human groups, deep perspective, arches, stairs, bridges, distant city, ornate weathered fresco frame, "
            "old-master engraving detail, deep blue, old gold, ivory stone and ochre."
        )
        model_prompt, prompt_tokens, max_tokens, hard_truncated, original_tokens = v41.hard_cap_prompt(tokenizer, raw)
        if hard_truncated:
            raise RuntimeError(
                f"V5_3_PROMPT_BUDGET_VIOLATION: emergency prompt exceeded {max_tokens} tokens "
                f"(original={original_tokens})"
            )
        return model_prompt, prompt_tokens, max_tokens, False, original_tokens, "V5_3_EMERGENCY_COMPOSITION_FIRST"
    return model_prompt, prompt_tokens, max_tokens, False, original_tokens, "V5_3_COMPOSITION_FIRST"


def render_negative_prompt(scene: dict) -> str:
    return (
        "product photography, studio photo, macro closeup, tabletop, still life, single object, centered object, "
        "jar, cup, mug, bottle, vase, vessel, urn, container, shelf display, museum specimen, isolated relic, "
        "empty background, blank wall, minimalism, poster, emblem, icon, no people, empty architecture, "
        "readable text, letters, words, inscription, label, caption, watermark, logo, pseudo text, gibberish typography, "
        "UI, diagram, infographic, grid, repeated rectangles, abstract wallpaper, glossy 3d render, extra limbs"
    )


def choose_canvas(story: dict, requested_width: int, requested_height: int) -> tuple[int, int]:
    return 512, 640


def _edge_mean(gray: Image.Image) -> float:
    edge = gray.filter(ImageFilter.FIND_EDGES)
    return float(ImageStat.Stat(edge).mean[0]) / 255.0


def _tile_activity_metrics(image: Image.Image) -> dict:
    gray = image.convert("L").resize((288, 360))
    active = 0
    outer_active = 0
    outer_count = 0
    tile_rows = []
    for y in range(3):
        row = []
        for x in range(3):
            tile = gray.crop((x * 96, y * 120, (x + 1) * 96, (y + 1) * 120))
            stat = ImageStat.Stat(tile)
            variance = float(stat.var[0])
            edge = _edge_mean(tile)
            is_active = variance >= 135.0 or edge >= 0.045
            row.append(
                {
                    "variance": round(variance, 3),
                    "edge_density": round(edge, 5),
                    "active": is_active,
                }
            )
            if is_active:
                active += 1
            if not (x == 1 and y == 1):
                outer_count += 1
                if is_active:
                    outer_active += 1
        tile_rows.append(row)
    return {
        "spatial_activity_ratio": round(active / 9.0, 4),
        "outer_activity_ratio": round(outer_active / max(outer_count, 1), 4),
        "active_tiles_3x3": active,
        "tile_activity_3x3": tile_rows,
    }


_ORIGINAL_METRICS = v52.visual_complexity_metrics
_ORIGINAL_GATE = v52.quality_gate


def visual_complexity_metrics(image: Image.Image) -> dict:
    metrics = dict(_ORIGINAL_METRICS(image))
    metrics.update(_tile_activity_metrics(image))
    metrics["method"] = (
        "V5_3_PIL_ENTROPY_EDGE_TILE_SPATIAL_OCCUPANCY_PLUS_OPTIONAL_TORCHVISION_COCO"
        "__NO_OCR__DETECTOR_IS_CALIBRATION_SIGNAL_ONLY"
    )
    return metrics


def quality_gate(metrics: dict) -> list[str]:
    reasons = list(_ORIGINAL_GATE(metrics))
    spatial = float(metrics.get("spatial_activity_ratio", 0.0))
    outer = float(metrics.get("outer_activity_ratio", 0.0))
    center = float(metrics.get("center_concentration", 0.0))
    empty = float(metrics.get("empty_field_ratio", 0.0))

    if spatial < 0.67:
        reasons.append("FAIL__LOW_SPATIAL_COVERAGE")
    if outer < 0.625:
        reasons.append("FAIL__LOW_OUTER_FRAME_ACTIVITY")
    if center > 1.60 and (outer < 0.75 or empty > 0.12):
        reasons.append("FAIL__DOMINANT_OBJECT_COLLAPSE_V5_3")

    if metrics.get("detector_available"):
        persons = int(metrics.get("person_detections") or 0)
        dominant = float(metrics.get("dominant_nonperson_area_ratio") or 0.0)
        if persons == 0:
            reasons.append("FAIL__INSUFFICIENT_HUMAN_SCENE")
        elif persons == 1 and (dominant > 0.12 or spatial < 0.78):
            reasons.append("FAIL__INSUFFICIENT_HUMAN_SCENE")
        if dominant > 0.16 and persons <= 1:
            reasons.append("FAIL__DOMINANT_OBJECT_COLLAPSE_V5_3")

    return v41.dedupe(reasons)


def generate_one(pipe, candidate, repo_root, output_root, model, steps, width, height, seed) -> dict:
    receipt = v51.generate_one(pipe, candidate, repo_root, output_root, model, steps, width, height, seed)
    receipt["schema"] = "janus.fresco_forge.receipt.v5_3"
    receipt["generator"] = GENERATOR_VERSION
    receipt["art_direction"] = ART_DIRECTION_ID
    receipt["prompt_mode"] = "v5_3_composition_first_full_frame_monumental_narrative"
    receipt["backend"] = "local_diffusers_v5_3_dreamshaper_native_scheduler"
    receipt["visual_quality_gate"] = "V5_3_SPATIAL_OCCUPANCY_PLUS_OPTIONAL_COCO_GATE"
    receipt["reference_style_contract"] = {
        "monumental_vertical_4_5": True,
        "multi_figure_16_plus_target": True,
        "tripartite_populated_registers": True,
        "architecture_fills_frame": True,
        "old_master_engraving_detail": True,
        "weathered_fresco_surface": True,
        "deep_blue_gold_stone_palette": True,
        "diffusion_text_forbidden": True,
        "object_first_composition_forbidden": True,
        "product_photo_collapse_forbidden": True,
    }
    receipt_path = repo_root / receipt["receipt_path"]
    base.write_json_atomic(receipt_path, receipt)
    return receipt


v51.GENERATOR_VERSION = GENERATOR_VERSION
v51.ART_DIRECTION_ID = ART_DIRECTION_ID
v51.MIN_FIGURE_TARGET = MIN_FIGURE_TARGET
v51.MIN_SECONDARY_GROUPS = MIN_SECONDARY_GROUPS
v51.NEGATIVE_CONTROL_CLASSES = NEGATIVE_CONTROL_CLASSES
v51.choose_story = choose_story
v51.mutate_story_for_retry = mutate_story_for_retry
v51.render_prompt = render_prompt
v51.fit_prompt = fit_prompt
v51.render_negative_prompt = render_negative_prompt
v51.choose_canvas = choose_canvas
v51.visual_complexity_metrics = visual_complexity_metrics
v51.quality_gate = quality_gate

base.GENERATOR_VERSION = GENERATOR_VERSION
base.create_pipeline = v521.create_pipeline
base.generate_one = generate_one

if __name__ == "__main__":
    raise SystemExit(base.main())
