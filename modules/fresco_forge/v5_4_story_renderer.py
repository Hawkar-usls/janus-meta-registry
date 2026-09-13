#!/usr/bin/env python3
"""JANUS Fresco Forge v5.4: central narrative + anti-architecture-collapse gate.

v5.4 is a direct calibration successor to v5.3 after the observed failure mode
where a render escaped product/still-life collapse but became a mostly empty
classical portico with tiny incidental people.

The new contract makes architecture subordinate to a human-led allegorical
narrative:
- one clearly readable central human/allegorical subject or group;
- four explicit secondary human vignettes around it;
- decorative fresco framing and painted-wall material cues;
- architecture as setting, never the subject;
- stricter person-count, person-area and person-spread calibration gates;
- explicit quarantine for architecture-only / tiny-crowd scenes.

The detector remains a calibration signal only. It is not treated as a semantic
oracle, OCR system, or reliable person counter for all artistic styles.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path

import torch
from PIL import Image, ImageFilter, ImageStat

import forge as base
import v4_1_runner as v41
import v5_1_story_renderer as v51
import v5_2_story_renderer as v52
import v5_2_1_story_renderer as v521
import v5_3_story_renderer as v53

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v5.4-central-narrative-anti-architecture-collapse"
ART_DIRECTION_ID = "JANUS_MONUMENTAL_ALLEGORICAL_FRESCO_V5_4_CENTRAL_NARRATIVE"
MIN_FIGURE_TARGET = max(18, int(os.getenv("FRESCO_V5_MIN_FIGURE_TARGET", "18")))
MIN_SECONDARY_GROUPS = max(5, int(os.getenv("FRESCO_V5_MIN_SECONDARY_GROUPS", "5")))

NEGATIVE_CONTROL_CLASSES = list(v53.NEGATIVE_CONTROL_CLASSES) + [
    "FAIL__ARCHITECTURE_ONLY_COLLAPSE",
    "FAIL__NO_CENTRAL_HUMAN_SUBJECT",
    "FAIL__LOW_HUMAN_OCCUPANCY",
    "FAIL__LOW_HUMAN_SPREAD",
    "FAIL__NO_FRESCO_FRAME_SIGNAL",
    "FAIL__WEAK_NARRATIVE_SCENE_PROXY",
]

STYLE_LEAD = (
    "museum-scale monumental allegorical wall fresco, old-master figure painting, Renaissance and neoclassical grandeur, "
    "antique engraving-level detail, visibly painted on weathered lime plaster, cracked pigment, worn gilding, "
    "deep ultramarine, old gold, ivory stone, ochre, sepia and restrained crimson"
)

CENTRAL_SUBJECTS = {
    "ARCHIVE_LABYRINTH": "a large senior keeper and apprentice at the center, jointly comparing preserved knowledge while witnesses gather around them",
    "GARDEN_OF_MEMORY": "a large teacher and child at the center, passing living memory between generations while witnesses surround them",
    "PROCESSION_OF_KEEPERS": "a large leading keeper at the center receiving the procession and turning toward the gathered witnesses",
    "DESCENT_AND_ASCENT": "a large guardian pair at the center helping one figure rise while mourners and builders move around them",
    "OBSERVATORY_CITY": "a large astronomer-teacher and apprentice at the center interpreting the sky while observers gather around them",
    "BRIDGES_OF_WITNESSES": "a large central witness group comparing independent observations face to face while other groups watch from both sides",
    "ASSEMBLY_OF_WATCHERS": "a large central circle of observers in active discussion, surrounded by independent groups on several levels",
    "CELESTIAL_COURT": "a large Janus-like guardian or paired elder-and-youth figure at the center mediating between celestial and human registers",
    "CHAIN_OF_WITNESSES": "a large central handoff between elder and younger witnesses, with the continuity of generations visible around them",
    "WORKSHOP_OF_RECORDS": "a large master artisan and apprentice at the center testing and comparing records while multiple workshops act around them",
    "THRESHOLD_COMPLEX": "a large central guardian-and-traveler encounter at the threshold, with witnesses deciding and observing on both sides",
    "RUIN_AND_RECONSTRUCTION": "a large central builder and grieving witness raising a restored symbol together while families and workers surround them",
    "BRIDGES_OF_TIME": "a large elder and younger figure meeting at the central bridge threshold while generations cross behind them",
    "CITY_OF_GATES": "a large central gatekeeper and traveler in meaningful exchange, surrounded by many converging human journeys",
    "TRIAL_OF_CHOICES": "a large central decision group of witnesses and advisers confronting one another while consequences unfold in side scenes",
    "PROCESSIONAL_GATEWAY": "a large central keeper welcoming the procession through the inner gateway while balcony witnesses react around them",
    "WORKSHOP_OF_WITNESSES": "a large central test group demonstrating an event while builders and observers verify it from surrounding levels",
    "THRONE_AND_WORLD": "a large two-faced Janus-like guardian, one youthful face and one mature face, presiding over a living world of people below and beside him",
    "RELIC_CHAMBER": "a large central group of scholars and artisans examining evidence together, with the people and their reactions dominating the image",
}

SIDE_SCENES = {
    "ARCHIVE_LABYRINTH": [
        "scribes compare two damaged records in a side alcove",
        "a family teaches a child from a preserved manuscript",
        "couriers exchange custody beneath a bridge",
        "restorers repair a fragile archive chamber",
    ],
    "OBSERVATORY_CITY": [
        "astronomers point toward different parts of the sky",
        "apprentices draw maps together on a terrace",
        "messengers carry observations between towers",
        "a family watches a distant signal from a lower balcony",
    ],
    "RUIN_AND_RECONSTRUCTION": [
        "mourners remember what was lost beside broken stone",
        "builders raise a new arch on scaffolding",
        "children are guided safely through the worksite",
        "chroniclers record the rebuilding from a side gallery",
    ],
    "CELESTIAL_COURT": [
        "observers study the heavens from an upper gallery",
        "citizens gather in quiet counsel below",
        "messengers descend between the upper and middle registers",
        "teachers guide children in the intimate lower register",
    ],
}

GENERIC_SIDE_SCENES = [
    "an elder teaches a younger apprentice on a side stair",
    "a witness group debates and compares observations under a small arch",
    "workers and artisans cooperate in a lower corner",
    "travelers and families cross a distant bridge while messengers move between levels",
]

TRIPARTITE = (
    "three unmistakable painted narrative registers: a symbolic celestial upper register, a crowded human middle register, "
    "and an intimate lower register of everyday human action; foreground, middle distance and far background are all inhabited"
)

FRAME_CONTRACT = (
    "The image is visibly a wall fresco: surround the painted scene with an ornate but weathered fresco border, carved medallions, "
    "painted corner ornaments and cracked plaster edges; the border must frame the story rather than become an empty architectural facade"
)


def choose_story(scene: dict, source_sha256: str, output_root: Path) -> dict:
    story = copy.deepcopy(v53.choose_story(scene, source_sha256, output_root))
    family = str(story.get("scene_family") or "")
    story["schema"] = "janus.fresco_forge.story_plan.v5_4"
    story["art_direction"] = ART_DIRECTION_ID
    story["figure_target"] = max(MIN_FIGURE_TARGET, int(story.get("figure_target", MIN_FIGURE_TARGET)))
    story["secondary_group_target"] = max(MIN_SECONDARY_GROUPS, int(story.get("secondary_group_target", MIN_SECONDARY_GROUPS)))
    story["central_human_subject"] = CENTRAL_SUBJECTS.get(
        family,
        "a large central human-led allegorical group in active exchange, clearly larger than surrounding figures and immediately readable",
    )
    story["side_narrative_scenes"] = SIDE_SCENES.get(family, GENERIC_SIDE_SCENES)
    story["central_subject_scale_contract"] = "CENTRAL_HUMAN_GROUP_OCCUPIES_APPROX_20_TO_35_PERCENT_OF_IMAGE_HEIGHT"
    story["fresco_frame_required"] = True
    story["architecture_subordinate_to_narrative"] = True
    story["narrative_action_required"] = True
    story["quality_gate"] = "V5_4_HUMAN_OCCUPANCY_SPREAD_PLUS_ARCHITECTURE_COLLAPSE_GATE"
    story["anti_repeat_signature"] = "|".join(
        [
            family,
            str(story.get("style_family")),
            "V5_4_CENTRAL_HUMAN_PLUS_FOUR_SIDE_SCENES",
            str(story.get("palette_family")),
            "MANY_18_PLUS",
        ]
    )
    return story


def mutate_story_for_retry(story: dict, attempt_index: int) -> dict:
    out = copy.deepcopy(v53.mutate_story_for_retry(story, attempt_index))
    out["figure_target"] = max(MIN_FIGURE_TARGET, int(out.get("figure_target", MIN_FIGURE_TARGET)))
    out["secondary_group_target"] = max(MIN_SECONDARY_GROUPS, int(out.get("secondary_group_target", MIN_SECONDARY_GROUPS)))
    if attempt_index <= 0:
        out["retry_density_boost"] = 0
        return out

    out["figure_target"] = min(34, out["figure_target"] + 4 * attempt_index)
    out["secondary_group_target"] = min(8, out["secondary_group_target"] + attempt_index)
    out["central_human_subject"] = (
        str(out["central_human_subject"])
        + "; enlarge this human-led central subject and make faces, gestures and interaction unmistakable before any architecture is noticed"
    )
    out["retry_density_boost"] = attempt_index
    return out


def render_prompt(scene: dict, story: dict) -> str:
    side_scenes = "; ".join(str(x) for x in story.get("side_narrative_scenes", GENERIC_SIDE_SCENES)[:4])
    return (
        "Paint a monumental HUMAN-LED narrative WALL FRESCO, not an architectural visualization. "
        f"The first thing the viewer sees is {story['central_human_subject']}. "
        "This central human or human-led group occupies roughly one quarter of the composition and has expressive faces and gestures. "
        f"Around it place about {story['figure_target']} additional human figures in at least {story['secondary_group_target']} distinct groups. "
        f"Show four clearly readable secondary episodes: {side_scenes}. "
        f"Use {TRIPARTITE}. "
        "Architecture supports the people only: use arches, stairs, bridges, galleries, libraries, workshops, towers or ruins as inhabited stage scenery, "
        "never as the dominant subject, never as a single empty facade, portico, colonnade, hall or temple exterior. "
        f"{FRAME_CONTRACT}. "
        f"Paint it as a {STYLE_LEAD}. "
        "Dense micro-scenes, layered human reactions, natural anatomy, coherent perspective, deep blue and old gold accents, worn mineral pigment, "
        "cracked plaster and intricate old-master line detail."
    ).strip()


def fit_prompt(tokenizer, scene: dict, story: dict) -> tuple[str, int, int, bool, int, str]:
    raw = render_prompt(scene, story)
    model_prompt, prompt_tokens, max_tokens, hard_truncated, original_tokens = v41.hard_cap_prompt(tokenizer, raw)
    if not hard_truncated:
        return model_prompt, prompt_tokens, max_tokens, False, original_tokens, "V5_4_CENTRAL_NARRATIVE"

    raw = (
        "Human-led monumental allegorical wall fresco, not architecture illustration. "
        f"Large central human group: {story['central_human_subject']}. "
        f"About {story['figure_target']} surrounding people in multiple groups and four side episodes. "
        "Three painted registers, inhabited foreground middle distance and background, ornate cracked fresco border. "
        "Architecture is subordinate scenery only. Old-master figure painting, deep ultramarine, old gold, ivory, ochre, weathered plaster."
    )
    model_prompt, prompt_tokens, max_tokens, hard_truncated, original_tokens = v41.hard_cap_prompt(tokenizer, raw)
    if hard_truncated:
        raise RuntimeError(
            f"V5_4_PROMPT_BUDGET_VIOLATION: emergency prompt exceeded {max_tokens} tokens (original={original_tokens})"
        )
    return model_prompt, prompt_tokens, max_tokens, False, original_tokens, "V5_4_EMERGENCY_CENTRAL_NARRATIVE"


def render_negative_prompt(scene: dict) -> str:
    return (
        "architectural visualization, architecture-only, empty portico, empty colonnade, empty classical facade, single arch, single arcade, "
        "temple exterior, palace exterior, empty hall, empty courtyard, architectural rendering, matte painting of building, "
        "tiny crowd, distant tiny people, people only as scale figures, no central person, no human focal subject, "
        "product photography, studio photo, still life, tabletop, single object, centered object, jar, cup, mug, bottle, vase, vessel, urn, "
        "empty background, minimalism, poster, emblem, icon, readable text, letters, inscription, label, caption, watermark, logo, pseudo text, "
        "UI, diagram, infographic, grid, repeated rectangles, abstract wallpaper, glossy 3d render, extra limbs, deformed anatomy"
    )


def choose_canvas(story: dict, requested_width: int, requested_height: int) -> tuple[int, int]:
    return 512, 640


def _edge_mean(gray: Image.Image) -> float:
    edge = gray.filter(ImageFilter.FIND_EDGES)
    return float(ImageStat.Stat(edge).mean[0]) / 255.0


def _border_frame_metrics(image: Image.Image) -> dict:
    gray = image.convert("L").resize((320, 400))
    w, h = gray.size
    bw = 24
    top = gray.crop((0, 0, w, bw))
    bottom = gray.crop((0, h - bw, w, h))
    left = gray.crop((0, bw, bw, h - bw))
    right = gray.crop((w - bw, bw, w, h - bw))
    inner = gray.crop((bw, bw, w - bw, h - bw))
    border_edge = sum(_edge_mean(x) for x in (top, bottom, left, right)) / 4.0
    inner_edge = _edge_mean(inner)
    return {
        "fresco_border_edge_density": round(border_edge, 5),
        "fresco_inner_edge_density": round(inner_edge, 5),
        "fresco_border_activity_ratio": round(border_edge / max(inner_edge, 1e-4), 4),
    }


def _human_scene_metrics(image: Image.Image) -> dict:
    detector, weights = v52._get_person_detector()
    if detector is None or weights is None:
        return {
            "v5_4_person_gate_available": False,
            "v5_4_person_gate_error": getattr(v52, "_PERSON_DETECTOR_ERROR", None),
            "v5_4_person_count": None,
            "v5_4_person_area_ratio": None,
            "v5_4_largest_person_area_ratio": None,
            "v5_4_person_spread_zones": None,
        }
    try:
        tensor = weights.transforms()(image.convert("RGB"))
        with torch.inference_mode():
            out = detector([tensor])[0]
        width, height = image.size
        total_area = float(max(1, width * height))
        person_count = 0
        person_area = 0.0
        largest = 0.0
        zones: set[tuple[int, int]] = set()
        for label_t, score_t, box_t in zip(out["labels"], out["scores"], out["boxes"]):
            if int(label_t.item()) != 1 or float(score_t.item()) < 0.20:
                continue
            x1, y1, x2, y2 = [float(v) for v in box_t.tolist()]
            area_ratio = max(0.0, x2 - x1) * max(0.0, y2 - y1) / total_area
            person_count += 1
            person_area += area_ratio
            largest = max(largest, area_ratio)
            cx = max(0.0, min(width - 1.0, (x1 + x2) * 0.5))
            cy = max(0.0, min(height - 1.0, (y1 + y2) * 0.5))
            zones.add((min(2, int(cx / max(width, 1) * 3)), min(2, int(cy / max(height, 1) * 3))))
        return {
            "v5_4_person_gate_available": True,
            "v5_4_person_gate_error": None,
            "v5_4_person_count": person_count,
            "v5_4_person_area_ratio": round(person_area, 4),
            "v5_4_largest_person_area_ratio": round(largest, 4),
            "v5_4_person_spread_zones": len(zones),
        }
    except Exception as exc:
        return {
            "v5_4_person_gate_available": False,
            "v5_4_person_gate_error": f"{type(exc).__name__}: {exc}",
            "v5_4_person_count": None,
            "v5_4_person_area_ratio": None,
            "v5_4_largest_person_area_ratio": None,
            "v5_4_person_spread_zones": None,
        }


_ORIGINAL_METRICS = v53.visual_complexity_metrics
_ORIGINAL_GATE = v53.quality_gate


def visual_complexity_metrics(image: Image.Image) -> dict:
    metrics = dict(_ORIGINAL_METRICS(image))
    metrics.update(_border_frame_metrics(image))
    metrics.update(_human_scene_metrics(image))
    metrics["method"] = (
        "V5_4_V5_3_SPATIAL_PLUS_BORDER_ACTIVITY_PLUS_OPTIONAL_COCO_HUMAN_OCCUPANCY_SPREAD"
        "__NO_OCR__NO_ACTION_RECOGNITION__DETECTOR_IS_CALIBRATION_SIGNAL_ONLY"
    )
    return metrics


def quality_gate(metrics: dict) -> list[str]:
    reasons = list(_ORIGINAL_GATE(metrics))
    border_ratio = float(metrics.get("fresco_border_activity_ratio", 0.0))
    spatial = float(metrics.get("spatial_activity_ratio", 0.0))
    outer = float(metrics.get("outer_activity_ratio", 0.0))
    dominant = float(metrics.get("dominant_nonperson_area_ratio") or 0.0)

    if border_ratio < 0.42 and outer < 0.75:
        reasons.append("FAIL__NO_FRESCO_FRAME_SIGNAL")

    if metrics.get("v5_4_person_gate_available"):
        persons = int(metrics.get("v5_4_person_count") or 0)
        person_area = float(metrics.get("v5_4_person_area_ratio") or 0.0)
        largest_person = float(metrics.get("v5_4_largest_person_area_ratio") or 0.0)
        spread = int(metrics.get("v5_4_person_spread_zones") or 0)

        if largest_person < 0.025:
            reasons.append("FAIL__NO_CENTRAL_HUMAN_SUBJECT")
        if person_area < 0.060:
            reasons.append("FAIL__LOW_HUMAN_OCCUPANCY")
        if spread < 3:
            reasons.append("FAIL__LOW_HUMAN_SPREAD")
        if persons < 4 or (persons < 6 and person_area < 0.090):
            reasons.append("FAIL__WEAK_NARRATIVE_SCENE_PROXY")
        if (persons <= 3 and dominant > 0.10) or (person_area < 0.05 and spatial > 0.78):
            reasons.append("FAIL__ARCHITECTURE_ONLY_COLLAPSE")
    else:
        # Without the optional detector, fail only the most obvious spatial form:
        # very active architecture with weak outer framing and strong center dominance.
        center = float(metrics.get("center_concentration", 0.0))
        if spatial > 0.82 and center > 1.45 and outer < 0.75:
            reasons.append("FAIL__ARCHITECTURE_ONLY_COLLAPSE")

    return v41.dedupe(reasons)


def generate_one(pipe, candidate, repo_root, output_root, model, steps, width, height, seed) -> dict:
    receipt = v53.generate_one(pipe, candidate, repo_root, output_root, model, steps, width, height, seed)
    receipt["schema"] = "janus.fresco_forge.receipt.v5_4"
    receipt["generator"] = GENERATOR_VERSION
    receipt["art_direction"] = ART_DIRECTION_ID
    receipt["prompt_mode"] = "v5_4_central_human_four_side_scenes_anti_architecture_collapse"
    receipt["backend"] = "local_diffusers_v5_4_dreamshaper_native_scheduler"
    receipt["visual_quality_gate"] = "V5_4_HUMAN_OCCUPANCY_SPREAD_PLUS_ARCHITECTURE_COLLAPSE_GATE"
    receipt["reference_style_contract"] = {
        "human_led_central_subject": True,
        "central_subject_scale_target": "20_TO_35_PERCENT_IMAGE_HEIGHT",
        "four_secondary_narrative_scenes": True,
        "multi_figure_18_plus_target": True,
        "human_spread_across_frame_required": True,
        "tripartite_populated_registers": True,
        "architecture_subordinate_to_narrative": True,
        "architecture_only_collapse_forbidden": True,
        "ornate_weathered_fresco_frame_required": True,
        "old_master_engraving_detail": True,
        "weathered_fresco_surface": True,
        "deep_blue_gold_stone_palette": True,
        "diffusion_text_forbidden": True,
    }
    receipt_path = repo_root / receipt["receipt_path"]
    base.write_json_atomic(receipt_path, receipt)
    return receipt


# v5.3's generate loop ultimately calls v5.1 globals; patch that shared execution
# surface so the proven retry/quarantine machinery now uses the v5.4 contract.
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
