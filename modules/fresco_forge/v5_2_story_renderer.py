#!/usr/bin/env python3
"""JANUS Fresco Forge v5.2: reference-style monumental allegorical renderer.

v5.2 fixes the two observed v5 calibration failures:
- emblem/niche collapse with pseudo-text;
- isolated product/still-life object collapse.

The implementation deliberately reuses the proven v5.1 generation/receipt loop and
patches its story routing, concise prompt, negative prompt ordering, portrait canvas,
and quality gate.  The positive prompt is kept short enough for CLIP chunking to
preserve composition instead of letting object nouns dominate later chunks.

A lightweight torchvision COCO detector is used only as a fail-closed calibration
signal: when available, a render with no detected people plus a dominant non-person
object is quarantined rather than admitted to the canonical gallery.  The detector
is not treated as a semantic oracle and gracefully falls back to the existing PIL
complexity gate if its weights cannot be loaded.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import torch
from PIL import Image

import forge as base
import v3_runner as v3
import v4_1_runner as v41
import v5_story_renderer as v5
import v5_1_story_renderer as v51

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v5.2-reference-style-monumental-gate"
ART_DIRECTION_ID = "JANUS_MONUMENTAL_ALLEGORICAL_FRESCO_V5_2_REFERENCE_STYLE"
MIN_FIGURE_TARGET = max(12, int(os.getenv("FRESCO_V5_MIN_FIGURE_TARGET", "14")))
MIN_SECONDARY_GROUPS = max(3, int(os.getenv("FRESCO_V5_MIN_SECONDARY_GROUPS", "4")))

# Keep the visual DNA anchored to the user's reference family instead of switching
# between unrelated historical genres.
STYLE_LEAD = (
    "monumental vertical old-master allegorical wall fresco, Renaissance and neoclassical grandeur, "
    "antique engraving-level detail, weathered lime plaster, cracked painted surface, ornate carved stone frame, "
    "deep ultramarine, old gold, ivory stone, ochre, sepia and restrained crimson"
)

# These clauses intentionally describe only wanted visual content.  Object/still-life
# words live in the negative prompt, because even negated object nouns in the positive
# CLIP embedding can make SD1.x latch onto them.
TRIPARTITE_COMPOSITION = (
    "tripartite vertical composition: celestial upper register, crowded civic middle register, intimate human lower register; "
    "foreground, middle distance and far background are all inhabited; the central focus occupies less than one third of the frame"
)

NARRATIVE_CONTRACTS = {
    "ARCHIVE_LABYRINTH": "scholars, keepers and witnesses preserve memory across generations through comparison, teaching and guarded handoffs",
    "GARDEN_OF_MEMORY": "readers, gardeners, teachers and witnesses cultivate memory and pass knowledge between generations",
    "PROCESSION_OF_KEEPERS": "keepers and witnesses ascend through a ceremonial city in a coordinated procession of stewardship and continuity",
    "DESCENT_AND_ASCENT": "mourners descend through shadow while keepers, builders and children rise toward restoration and renewed civic life",
    "OBSERVATORY_CITY": "astronomers, map readers, signal keepers and apprentices observe together and share discoveries across a living city",
    "BRIDGES_OF_WITNESSES": "independent witness groups exchange verified signals across bridges while observers compare what each group can see",
    "ASSEMBLY_OF_WATCHERS": "many independent observers coordinate by gesture and light while preserving dissent, trust boundaries and collective vigilance",
    "CELESTIAL_COURT": "a silent celestial court of guardians, citizens and observers maintains disciplined order while visual signals continue without sound",
    "CHAIN_OF_WITNESSES": "successive groups of witnesses preserve continuity through human handoffs, comparison, correction and remembrance",
    "WORKSHOP_OF_RECORDS": "scribes, artisans, couriers and witnesses test, compare and preserve records inside a vast working archive",
    "THRESHOLD_COMPLEX": "guardians, travelers and witnesses negotiate several thresholds while closed and open paths remain visibly distinct",
    "RUIN_AND_RECONSTRUCTION": "mourners, builders, children and chroniclers transform ruin into renewed civic life without hiding the damage",
    "BRIDGES_OF_TIME": "people from contrasting generations cross connected bridges while guardians hold a shared threshold between past and future",
    "CITY_OF_GATES": "travelers, builders, scholars and gatekeepers inhabit a layered city where many paths converge without becoming identical",
    "TRIAL_OF_CHOICES": "a public court of witnesses, advisers and families confronts several consequences while uncertainty remains visible",
    "PROCESSIONAL_GATEWAY": "a large procession passes through nested civic gates while balcony witnesses and side groups preserve context and continuity",
    "WORKSHOP_OF_WITNESSES": "builders, test groups, observers and record keepers work around one shared event while retaining independent perspectives",
    "THRONE_AND_WORLD": "a monumental two-faced Janus-like guardian presides over a living city of scholars, families, pilgrims, builders and witnesses",
    "RELIC_CHAMBER": "artisans, scholars, witnesses and guardians study evidence together inside a vast hall, with human inquiry dominating the composition",
}

# Strong semantic routing from source role-audit text.  This prevents technical
# tokens such as ENTER, audio mute, membership, or an incidental object field from
# becoming the visual subject.
def _scene_text(scene: dict) -> str:
    parts: list[str] = []
    for row in scene.get("role_audit", []) or []:
        if not isinstance(row, dict):
            continue
        for key in ("path", "label", "value", "visual_text"):
            value = row.get(key)
            if value is not None:
                parts.append(str(value))
    for key in ("visual_subject", "central_action", "archetype"):
        if scene.get(key) is not None:
            parts.append(str(scene[key]))
    return " ".join(parts).lower()


def _route_family(scene: dict, fallback: str) -> str:
    text = _scene_text(scene)
    rules = [
        (("audio", "mute", "silence", "speaker_output"), "CELESTIAL_COURT"),
        (("trusted", "membership", "swarm", "quorum"), "ASSEMBLY_OF_WATCHERS"),
        (("memory", "archive", "ledger", "record", "provenance"), "ARCHIVE_LABYRINTH"),
        (("observer", "signal", "telemetry", "beacon", "watch"), "OBSERVATORY_CITY"),
        (("repair", "restore", "rebuild", "recovery", "resilien"), "RUIN_AND_RECONSTRUCTION"),
        (("gate", "threshold", "admission", "blocked"), "THRESHOLD_COMPLEX"),
        (("choice", "trial", "decision", "alternative"), "TRIAL_OF_CHOICES"),
        (("custody", "handoff", "chain", "witness"), "CHAIN_OF_WITNESSES"),
    ]
    for needles, family in rules:
        if any(needle in text for needle in needles):
            return family
    if fallback in NARRATIVE_CONTRACTS and fallback != "RELIC_CHAMBER":
        return fallback
    return "THRONE_AND_WORLD"


def choose_story(scene: dict, source_sha256: str, output_root: Path) -> dict:
    # Start from v5's deterministic anti-repeat story choice, then replace only the
    # visual interpretation layer.  Provenance and epistemic firewalls remain intact.
    story = v51.enrich_story(v5.choose_story(scene, source_sha256, output_root))
    family = _route_family(scene, str(story.get("scene_family") or ""))
    req = v51.FAMILY_REQUIREMENTS.get(
        family,
        {
            "figure_target": MIN_FIGURE_TARGET,
            "architecture": "grand arcades, layered stairs, bridges, galleries and a distant inhabited city",
            "groups": "scholars, keepers, witnesses, builders and travelers acting in separate groups",
        },
    )
    story["schema"] = "janus.fresco_forge.story_plan.v5_2"
    story["art_direction"] = ART_DIRECTION_ID
    story["scene_family"] = family
    story["figure_target"] = max(MIN_FIGURE_TARGET, int(req["figure_target"]))
    story["secondary_group_target"] = MIN_SECONDARY_GROUPS
    story["architecture_contract"] = req["architecture"]
    story["human_group_contract"] = req["groups"]
    story["narrative_contract"] = NARRATIVE_CONTRACTS.get(family, NARRATIVE_CONTRACTS["THRONE_AND_WORLD"])
    story["composition"] = TRIPARTITE_COMPOSITION
    story["composition_id"] = f"V5_2_TRIPARTITE__{family}"
    story["dominant_shape"] = "MONUMENTAL_VERTICAL_INHABITED_WORLD"
    story["orientation"] = "PORTRAIT"
    story["figure_count_bucket"] = "MANY_12_PLUS"
    story["typography_policy"] = "ZERO_TEXT_IN_DIFFUSION_STAGE"
    story["depth_layers"] = ["foreground", "middle_distance", "far_background"]
    story["full_frame_population_required"] = True
    story["monumental_frame_required"] = True
    story["quality_gate"] = "V5_2_PIL_PLUS_OPTIONAL_COCO_PERSON_OBJECT_GATE"
    story["anti_repeat_signature"] = "|".join(
        [
            family,
            str(story.get("style_family")),
            str(story.get("composition_id")),
            str(story.get("palette_family")),
            "MANY_12_PLUS",
        ]
    )
    return story


def mutate_story_for_retry(story: dict, attempt_index: int) -> dict:
    out = copy.deepcopy(story)
    if attempt_index <= 0:
        out["retry_density_boost"] = 0
        return out
    out["figure_target"] = min(28, int(out.get("figure_target", MIN_FIGURE_TARGET)) + 4 * attempt_index)
    out["secondary_group_target"] = min(6, int(out.get("secondary_group_target", MIN_SECONDARY_GROUPS)) + attempt_index)
    out["retry_density_boost"] = attempt_index
    if attempt_index == 1:
        out["narrative_contract"] += "; add more small human episodes on side stairs, balconies and distant bridges"
    else:
        out["narrative_contract"] += "; make the mural encyclopedic and densely populated from edge to edge with many simultaneous human actions"
    return out


def render_prompt(scene: dict, story: dict) -> str:
    # Deliberately concise: the core composition, people and architecture stay in
    # the first CLIP chunks rather than being diluted by long lists of source nouns.
    return (
        f"{STYLE_LEAD}. "
        f"{story['narrative_contract']}. "
        f"Show about {story['figure_target']} human figures in at least {story['secondary_group_target']} distinct groups: "
        f"{story['human_group_contract']}. "
        f"Architecture: {story['architecture_contract']}. "
        f"Composition: {TRIPARTITE_COMPOSITION}. "
        "Multiple simultaneous human actions, expressive faces and natural anatomy; monumental arches, stairs, bridges, galleries and distant structures; "
        "dense micro-scenes that reward close viewing; museum-scale sacred-civic mural, coherent perspective, richly painted old-master finish."
    ).strip()


def _emergency_prompt(story: dict) -> str:
    return (
        f"Monumental vertical old-master allegorical fresco on cracked plaster, deep blue and old gold. "
        f"A vast inhabited architectural world with {story['figure_target']} people in several groups. "
        f"{story['narrative_contract']}. {story['architecture_contract']}. "
        "Upper celestial register, crowded middle city, lower human register, foreground middle distance and far background, ornate frame, dense narrative detail."
    )


def fit_prompt(tokenizer, scene: dict, story: dict) -> tuple[str, int, int, bool, int, str]:
    raw = render_prompt(scene, story)
    model_prompt, prompt_tokens, max_tokens, hard_truncated, original_tokens = v41.hard_cap_prompt(tokenizer, raw)
    if not hard_truncated:
        return model_prompt, prompt_tokens, max_tokens, False, original_tokens, "V5_2_CONCISE"

    # Fail-safe should rarely be needed, but unlike v5.1 it does not crash the run.
    raw = _emergency_prompt(story)
    model_prompt, prompt_tokens, max_tokens, hard_truncated, original_tokens = v41.hard_cap_prompt(tokenizer, raw)
    if hard_truncated:
        raise RuntimeError(
            f"V5_2_PROMPT_BUDGET_VIOLATION: emergency prompt exceeded {max_tokens} tokens (original={original_tokens})"
        )
    return model_prompt, prompt_tokens, max_tokens, False, original_tokens, "V5_2_EMERGENCY_CONCISE"


def render_negative_prompt(scene: dict) -> str:
    # v3.encode_long keeps only one CLIP payload for negatives, so highest-value
    # collapse terms MUST come first and the whole string is intentionally short.
    return (
        "single object, product photo, still life, jar, cup, bottle, vase, vessel, urn, isolated relic, shelf display, "
        "empty background, blank wall, minimalist composition, poster, emblem, icon, no people, empty architecture, "
        "readable text, letters, words, inscription, label, caption, watermark, logo, pseudo text, gibberish typography, "
        "UI, diagram, infographic, grid, repeated rectangles, abstract wallpaper, deformed anatomy, extra limbs"
    )


def choose_canvas(story: dict, requested_width: int, requested_height: int) -> tuple[int, int]:
    # The reference family is overwhelmingly monumental and vertical.
    return 448, 640


# ---- Optional semantic calibration gate ------------------------------------
# Reuse v5.1 PIL metrics, then augment them with a small COCO detector already
# supported by the workflow's torchvision dependency.  Weight download failure
# never crashes the Forge; it merely disables this extra signal for that run.
_ORIGINAL_METRICS = v51.visual_complexity_metrics
_ORIGINAL_GATE = v51.quality_gate
_PERSON_DETECTOR = None
_PERSON_WEIGHTS = None
_PERSON_DETECTOR_ERROR: str | None = None


def _get_person_detector():
    global _PERSON_DETECTOR, _PERSON_WEIGHTS, _PERSON_DETECTOR_ERROR
    if _PERSON_DETECTOR is not None or _PERSON_DETECTOR_ERROR is not None:
        return _PERSON_DETECTOR, _PERSON_WEIGHTS
    try:
        from torchvision.models.detection import (
            FasterRCNN_MobileNet_V3_Large_320_FPN_Weights,
            fasterrcnn_mobilenet_v3_large_320_fpn,
        )

        weights = FasterRCNN_MobileNet_V3_Large_320_FPN_Weights.DEFAULT
        detector = fasterrcnn_mobilenet_v3_large_320_fpn(weights=weights, progress=True)
        detector.eval().to("cpu")
        _PERSON_DETECTOR = detector
        _PERSON_WEIGHTS = weights
    except Exception as exc:  # fail-soft calibration signal
        _PERSON_DETECTOR_ERROR = f"{type(exc).__name__}: {exc}"
    return _PERSON_DETECTOR, _PERSON_WEIGHTS


def _detection_metrics(image: Image.Image) -> dict:
    detector, weights = _get_person_detector()
    if detector is None or weights is None:
        return {
            "detector_available": False,
            "detector_error": _PERSON_DETECTOR_ERROR,
            "person_detections": None,
            "dominant_nonperson_area_ratio": None,
            "dominant_nonperson_label": None,
        }
    try:
        transform = weights.transforms()
        tensor = transform(image.convert("RGB"))
        with torch.inference_mode():
            out = detector([tensor])[0]
        categories = weights.meta.get("categories", [])
        width, height = image.size
        area = float(max(1, width * height))
        persons = 0
        dominant_ratio = 0.0
        dominant_label = None
        for label_t, score_t, box_t in zip(out["labels"], out["scores"], out["boxes"]):
            score = float(score_t.item())
            if score < 0.25:
                continue
            label = int(label_t.item())
            if label == 1:
                persons += 1
                continue
            if score < 0.35:
                continue
            x1, y1, x2, y2 = [float(x) for x in box_t.tolist()]
            ratio = max(0.0, x2 - x1) * max(0.0, y2 - y1) / area
            if ratio > dominant_ratio:
                dominant_ratio = ratio
                dominant_label = categories[label] if 0 <= label < len(categories) else str(label)
        return {
            "detector_available": True,
            "detector_error": None,
            "person_detections": persons,
            "dominant_nonperson_area_ratio": round(dominant_ratio, 4),
            "dominant_nonperson_label": dominant_label,
        }
    except Exception as exc:
        return {
            "detector_available": False,
            "detector_error": f"{type(exc).__name__}: {exc}",
            "person_detections": None,
            "dominant_nonperson_area_ratio": None,
            "dominant_nonperson_label": None,
        }


def visual_complexity_metrics(image: Image.Image) -> dict:
    metrics = dict(_ORIGINAL_METRICS(image))
    metrics.update(_detection_metrics(image))
    metrics["method"] = (
        "PIL_GRAYSCALE_ENTROPY_EDGE_TILE_PLUS_OPTIONAL_TORCHVISION_COCO_DETECTION"
        "__NO_OCR__DETECTOR_IS_ONLY_A_CALIBRATION_SIGNAL"
    )
    return metrics


def quality_gate(metrics: dict) -> list[str]:
    reasons = list(_ORIGINAL_GATE(metrics))
    empty = float(metrics.get("empty_field_ratio", 0.0))
    center = float(metrics.get("center_concentration", 0.0))

    # Tighten the purely visual gate after the photographed-container failure.
    if empty > 0.38 and "FAIL__EMPTY_FIELD_COLLAPSE" not in reasons:
        reasons.append("FAIL__EMPTY_FIELD_COLLAPSE")
    if center > 1.75 and empty > 0.18 and "FAIL__EMBLEM_COLLAPSE" not in reasons:
        reasons.append("FAIL__EMBLEM_COLLAPSE")

    if metrics.get("detector_available"):
        persons = int(metrics.get("person_detections") or 0)
        dominant = float(metrics.get("dominant_nonperson_area_ratio") or 0.0)
        if persons == 0:
            reasons.append("FAIL__NO_PERSON_DETECTED")
        if dominant > 0.22 and persons <= 1:
            reasons.append("FAIL__DOMINANT_OBJECT_COLLAPSE")

    return v41.dedupe(reasons)


# Wrap v5.1's proven writer so receipts accurately identify the active successor.
_ORIGINAL_GENERATE_ONE = v51.generate_one


def generate_one(pipe, candidate, repo_root, output_root, model, steps, width, height, seed) -> dict:
    receipt = _ORIGINAL_GENERATE_ONE(pipe, candidate, repo_root, output_root, model, steps, width, height, seed)
    receipt["schema"] = "janus.fresco_forge.receipt.v5_2"
    receipt["generator"] = GENERATOR_VERSION
    receipt["art_direction"] = ART_DIRECTION_ID
    receipt["prompt_mode"] = "v5_2_concise_reference_style_tripartite_human_world"
    receipt["backend"] = "local_diffusers_v5_2_reference_style_monumental_gate"
    receipt["visual_quality_gate"] = "V5_2_PIL_PLUS_OPTIONAL_TORCHVISION_COCO_PERSON_OBJECT_GATE"
    receipt["reference_style_contract"] = {
        "monumental_vertical": True,
        "multi_figure": True,
        "tripartite_registers": True,
        "architecture_world": True,
        "old_master_engraving_detail": True,
        "weathered_fresco_surface": True,
        "diffusion_text_forbidden": True,
        "object_first_composition_forbidden": True,
    }
    receipt_path = repo_root / receipt["receipt_path"]
    base.write_json_atomic(receipt_path, receipt)
    return receipt


# Patch the imported v5.1 module because its generate loop performs global lookups
# for these functions.  This retains its retry/quarantine logic without duplicating
# hundreds of proven lines.
v51.GENERATOR_VERSION = GENERATOR_VERSION
v51.ART_DIRECTION_ID = ART_DIRECTION_ID
v51.MIN_FIGURE_TARGET = MIN_FIGURE_TARGET
v51.MIN_SECONDARY_GROUPS = MIN_SECONDARY_GROUPS
v51.choose_story = choose_story
v51.mutate_story_for_retry = mutate_story_for_retry
v51.render_prompt = render_prompt
v51.fit_prompt = fit_prompt
v51.render_negative_prompt = render_negative_prompt
v51.choose_canvas = choose_canvas
v51.visual_complexity_metrics = visual_complexity_metrics
v51.quality_gate = quality_gate

base.GENERATOR_VERSION = GENERATOR_VERSION
base.create_pipeline = v3.create_pipeline
base.generate_one = generate_one

if __name__ == "__main__":
    raise SystemExit(base.main())
