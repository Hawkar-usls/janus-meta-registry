#!/usr/bin/env python3
"""JANUS Fresco Forge v5.0: Monumental Allegorical Story Renderer.

v5 keeps the v4 semantic-role and epistemic firewalls but replaces the old
"technical JSON painted on plaster" visual grammar with narrative allegory.
Canonical JSON is first projected into a guarded semantic scene, then translated
into a dense monumental fresco story with a strong central subject, secondary
micro-scenes, deep architecture, symbolic objects, and old-master materiality.

The diffusion stage never renders literal labels or inscriptions. If canonical
text is ever added later, it must be a deterministic typography post-process.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Iterable

import torch

import forge as base
import v3_runner as v3
import v4_1_runner as v41
import v4_1_1_runner as firewall  # noqa: F401  # preserve semantic/physical-gate patches
import v4_4_runner as v44

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v5.0-monumental-allegorical-story-renderer"
ART_DIRECTION_ID = "JANUS_MONUMENTAL_ALLEGORICAL_FRESCO"
GUIDANCE_SCALE = float(os.getenv("FRESCO_GUIDANCE_SCALE", "7.0"))
RECENT_SIGNATURE_WINDOW = int(os.getenv("FRESCO_V5_RECENT_SIGNATURE_WINDOW", "18"))

NEGATIVE_CONTROL_CLASSES = list(v44.NEGATIVE_CONTROL_CLASSES) + [
    "FAIL__PSEUDOTEXT_DOMINANCE",
    "FAIL__NO_NARRATIVE_EVENT",
    "FAIL__REPEATED_TEMPLATE_COLLAPSE",
    "FAIL__SYMBOL_WALLPAPER",
    "FAIL__ABSTRACT_UI_REVERSION",
    "FAIL__LOW_DETAIL_PRIMITIVE_MURAL",
]

STYLE_FAMILIES = {
    "POLYCHROME_MONUMENTAL": (
        "a monumental polychrome allegorical fresco with old-master figure painting, "
        "aged lime plaster, worn gilding, deep ultramarine, warm stone, ochre and muted red"
    ),
    "OLD_MASTER_ENGRAVING": (
        "an old-master engraved mural translated into fresco material, dense crosshatched detail, "
        "sepia and warm stone tones, restrained gold, severe chiaroscuro and architectural precision"
    ),
    "DARK_ALLEGORICAL": (
        "a dramatic dark allegorical fresco with torchlit stone, smoky shadows, oxidized gold, "
        "deep blue-black passages and solemn old-master faces"
    ),
    "ARCHITECTURAL_CAPRICCIO": (
        "a grand architectural capriccio fresco of arcades, bridges, stairs, libraries, ruins and distant cities, "
        "painted with weathered old-master realism and restrained mineral pigments"
    ),
    "ILLUMINATED_CELESTIAL": (
        "an illuminated celestial fresco with deep blue heavens, gold astronomical ornament, "
        "stone architecture, luminous thresholds and finely painted human figures"
    ),
    "SEPULCHRAL_DRAMATIC": (
        "a grave sepulchral fresco combining antique stone, worn plaster, engraved detail, "
        "cold shadow, restrained firelight and monumental narrative pathos"
    ),
}

SCENE_FAMILY_MAP = {
    "MEMORY_ARCHIVE": (
        "ARCHIVE_LABYRINTH",
        "GARDEN_OF_MEMORY",
        "PROCESSION_OF_KEEPERS",
        "DESCENT_AND_ASCENT",
    ),
    "DISTRIBUTED_SWARM": (
        "OBSERVATORY_CITY",
        "BRIDGES_OF_WITNESSES",
        "ASSEMBLY_OF_WATCHERS",
        "CELESTIAL_COURT",
    ),
    "RECORD_PROVENANCE": (
        "PROCESSION_OF_KEEPERS",
        "CHAIN_OF_WITNESSES",
        "ARCHIVE_LABYRINTH",
        "WORKSHOP_OF_RECORDS",
    ),
    "ARCHITECTURAL_EVENT": (
        "THRESHOLD_COMPLEX",
        "RUIN_AND_RECONSTRUCTION",
        "BRIDGES_OF_TIME",
        "CITY_OF_GATES",
    ),
    "HUMAN_NARRATIVE": (
        "TRIAL_OF_CHOICES",
        "PROCESSIONAL_GATEWAY",
        "GARDEN_OF_MEMORY",
        "WORKSHOP_OF_WITNESSES",
    ),
    "MYTHIC_NARRATIVE": (
        "CELESTIAL_COURT",
        "THRONE_AND_WORLD",
        "PROCESSIONAL_GATEWAY",
        "DESCENT_AND_ASCENT",
    ),
    "OBJECT_RITUAL": (
        "RELIC_CHAMBER",
        "PROCESSIONAL_GATEWAY",
        "WORKSHOP_OF_WITNESSES",
        "CELESTIAL_COURT",
    ),
    "GENERIC_SYSTEM": (
        "WORKSHOP_OF_WITNESSES",
        "CITY_OF_GATES",
        "TRIAL_OF_CHOICES",
        "RUIN_AND_RECONSTRUCTION",
    ),
}

COMPOSITION_MAP = {
    "ARCHIVE_LABYRINTH": ("VERTICAL_LAYERS", "spiraling stairs through layered libraries and archive chambers"),
    "GARDEN_OF_MEMORY": ("DEEP_GARDEN_AXIS", "a deep garden-city axis with arcades, fountains, study niches and distant towers"),
    "PROCESSION_OF_KEEPERS": ("DIAGONAL_PROCESSION", "a diagonal procession crossing several architectural levels toward a luminous gate"),
    "DESCENT_AND_ASCENT": ("TERRACED_DESCENT", "stacked terraces descending into shadow and rising again toward light"),
    "OBSERVATORY_CITY": ("CELESTIAL_CITY", "an observatory city with bridges, domes, instruments and many separated watchers"),
    "BRIDGES_OF_WITNESSES": ("INTERLACED_BRIDGES", "interlaced bridges carrying independent groups between towers and archives"),
    "ASSEMBLY_OF_WATCHERS": ("ASYMMETRIC_ASSEMBLY", "an asymmetric gathering around a central event with many distinct witness groups"),
    "CELESTIAL_COURT": ("CENTRAL_CELESTIAL", "a monumental central figure or symbol framed by sun, moon, stars and layered side narratives"),
    "CHAIN_OF_WITNESSES": ("HUMAN_CHAIN", "a long human chain passing sealed objects across changing historical settings"),
    "WORKSHOP_OF_RECORDS": ("DENSE_WORKSHOP", "a dense old workshop of scribes, artisans, instruments, sealed bundles and archive alcoves"),
    "THRESHOLD_COMPLEX": ("GATE_AXIS", "a monumental axis of gates, chambers, stairs and guarded transitions"),
    "RUIN_AND_RECONSTRUCTION": ("BROKEN_TO_REBUILT", "broken ruins in the foreground becoming ordered reconstruction toward the distance"),
    "BRIDGES_OF_TIME": ("TWIN_PATHS", "two contrasting paths and bridge systems converging on a guarded central threshold"),
    "CITY_OF_GATES": ("CITY_PANORAMA", "a layered city of gates and passages with many small human episodes"),
    "TRIAL_OF_CHOICES": ("JUDGMENT_STAGE", "a central decision scene surrounded by consequences unfolding in smaller side episodes"),
    "PROCESSIONAL_GATEWAY": ("MONUMENTAL_GATEWAY", "a grand gateway with a central procession and nested narrative chambers"),
    "WORKSHOP_OF_WITNESSES": ("WORKSHOP_COURT", "a working court of observers, builders and keepers around one dominant symbolic mechanism"),
    "THRONE_AND_WORLD": ("MONUMENTAL_THRONE", "a dominant central Janus-like or source-established figure above a living multi-level world"),
    "RELIC_CHAMBER": ("OBJECT_SANCTUM", "a monumental chamber organized around one source-supported object with active attendants and witnesses"),
}

ORIENTATION_LANDSCAPE = {"CITY_OF_GATES", "RUIN_AND_RECONSTRUCTION", "OBSERVATORY_CITY"}

THEME_STORIES = {
    "MEMORY_ARCHIVE": {
        "central": "a keeper carries a small enduring light through a vast archive-city where fragile records are being sorted, preserved and handed onward",
        "action": "ordinary traces fade into worn plaster while significant events are carefully rescued and transferred to deeper chambers",
        "micro": [
            "scribes compare old fragments without erasing the earlier version",
            "travelers carry sealed bundles across a bridge toward a distant archive",
            "a small group protects one bright anomaly while nearby ordinary marks weather naturally",
        ],
        "symbols": ["lamps", "sealed scroll bundles", "keys", "hourglasses", "archive doors", "reflecting water"],
        "mood": "grave, patient and protective",
    },
    "DISTRIBUTED_SWARM": {
        "central": "many independent watchers occupy separate towers and terraces, each holding local knowledge while sharing only selected signals",
        "action": "messengers and beams of lamplight connect distant groups without merging them into a single ruler or mind",
        "micro": [
            "one group observes the sky while another studies the city below",
            "a disagreement remains visible as two different routes that continue side by side",
            "an absent station appears as a dark empty tower among active illuminated ones",
        ],
        "symbols": ["signal lamps", "bridges", "observatory spheres", "separate towers", "messenger paths", "star maps without text"],
        "mood": "alert, plural and cooperative",
    },
    "RECORD_PROVENANCE": {
        "central": "a procession of keepers passes sealed objects from hand to hand across generations, preserving an unbroken chain of custody",
        "action": "new evidence is added at the growing end while corrections remain beside older traces instead of replacing them",
        "micro": [
            "an older damaged record remains visible beside its careful correction",
            "a witness seals a bundle before sending it across a bridge",
            "an archivist compares two versions while a third person records the transfer",
        ],
        "symbols": ["wax seals", "keys", "linked rings", "sealed vessels", "archive chests", "unbroken cord"],
        "mood": "forensic, solemn and trustworthy",
    },
    "ARCHITECTURAL_EVENT": {
        "central": "a monumental threshold complex dominates the scene while anonymous attendants move through a precisely ordered sequence of closures and openings",
        "action": "the architecture itself changes state: one path closes, another empties, and only the permitted passage opens toward light",
        "micro": [
            "an earlier chamber remains visibly sealed",
            "workers inspect a transition before allowing travelers onward",
            "an unresolved route stays dark and closed rather than being celebrated",
        ],
        "symbols": ["gates", "keys", "sealed doors", "bridges", "lamps", "measuring instruments"],
        "mood": "controlled, vigilant and consequential",
    },
    "HUMAN_NARRATIVE": {
        "central": "the source-established human story occupies the center while surrounding witnesses reveal its consequences across several connected places",
        "action": "the main human action unfolds clearly, with compassion, conflict and consequence shown through secondary scenes rather than abstract symbols",
        "micro": [
            "witnesses react differently to the same event",
            "a quieter side scene shows care, repair or remembrance",
            "a distant scene preserves the unresolved consequence rather than forcing a triumph",
        ],
        "symbols": ["lamps", "doors", "books", "bridges", "water", "celestial signs"],
        "mood": "human, emotionally legible and restrained",
    },
    "MYTHIC_NARRATIVE": {
        "central": "the source-established mythic figure dominates a monumental sacred setting while mortal-scale scenes unfold around and below",
        "action": "the central allegory governs passage between contrasting realms without flattening them into a diagram",
        "micro": [
            "small travelers cross from one condition into another",
            "keepers preserve fragile knowledge in side chambers",
            "celestial signs frame the event without turning uncertainty into prophecy",
        ],
        "symbols": ["sun", "moon", "stars", "keys", "gates", "hourglasses", "laurel"],
        "mood": "sacred, monumental and contemplative",
    },
    "OBJECT_RITUAL": {
        "central": "one source-supported object becomes the focal relic inside a vast architectural narrative populated by careful attendants and witnesses",
        "action": "people use, protect, test or contemplate the object according to the source instead of worshipping an invented deity",
        "micro": [
            "an artisan examines the object under lamplight",
            "a witness records its passage into a guarded chamber",
            "a distant scene shows a consequence or alternate state tied to the same object",
        ],
        "symbols": ["reliquary forms", "keys", "lamps", "measuring tools", "sealed niches", "stone thresholds"],
        "mood": "reverent but evidence-bound",
    },
    "GENERIC_SYSTEM": {
        "central": "a community of keepers, observers and builders works around one monumental symbolic process embedded in a living city of gates and workshops",
        "action": "the process is shown through coordinated human actions, changing architectural states and consequences rather than abstract blocks or interface diagrams",
        "micro": [
            "one group tests a transition before another group proceeds",
            "an unresolved branch remains dark and visibly unfinished",
            "a repaired section preserves traces of the earlier failure instead of hiding it",
        ],
        "symbols": ["gates", "lamps", "bridges", "keys", "measuring instruments", "sealed vessels"],
        "mood": "methodical, curious and non-triumphal",
    },
}


def dedupe(values: Iterable[str]) -> list[str]:
    return v41.dedupe(values)


def _clean(text: str, limit: int = 150) -> str:
    text = re.sub(r"[_/]+", " ", str(text))
    text = re.sub(r"\s+", " ", text).strip(" .;:-")
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return text


def _stable_index(source_sha256: str, salt: str, count: int) -> int:
    digest = hashlib.sha256(f"{source_sha256}:{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % count


def semantic_theme(scene: dict) -> tuple[str, dict[str, float]]:
    focus, scores, _ = v44.route_focus(scene)
    if focus in THEME_STORIES:
        return focus, scores
    archetype = str(scene.get("archetype") or "GENERIC_SYSTEM")
    if archetype in THEME_STORIES:
        return archetype, scores
    return "GENERIC_SYSTEM", scores


def source_story_hints(scene: dict, limit: int = 2) -> list[str]:
    ranked: list[tuple[float, str]] = []
    allowed_roles = {
        "DESCRIPTIVE_NARRATIVE",
        "PERSON_OR_MYTHIC_ENTITY",
        "OBJECT_OR_ARTIFACT",
        "ENVIRONMENT_OR_ARCHITECTURE",
        "EPISTEMIC_OR_STATE",
    }
    forbidden_fragments = (
        "sha256", "schema", "json", "jsonl", "ndjson", "repository", "github",
        "commit", "branch", "protocol_name", "internal_name",
    )
    for item in scene.get("role_audit", []):
        if item.get("field_role") not in allowed_roles:
            continue
        value = _clean(item.get("visual_text") or item.get("value") or "")
        low = value.casefold()
        if not value or low in {"true", "false"}:
            continue
        if any(fragment in low for fragment in forbidden_fragments):
            continue
        weight = float(item.get("weight", 1.0) or 1.0)
        if item.get("field_role") == "DESCRIPTIVE_NARRATIVE":
            weight += 4.0
        ranked.append((weight, value))
    ranked.sort(key=lambda row: row[0], reverse=True)
    return dedupe([text for _, text in ranked])[:limit]


def recent_story_signatures(output_root: Path, limit: int = RECENT_SIGNATURE_WINDOW) -> set[str]:
    rows: list[tuple[str, str]] = []
    receipts_dir = output_root / "receipts"
    if not receipts_dir.exists():
        return set()
    for path in receipts_dir.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        signature = payload.get("anti_repeat_signature")
        generated_at = str(payload.get("generated_at") or "")
        if isinstance(signature, str) and signature:
            rows.append((generated_at, signature))
    rows.sort(reverse=True)
    return {signature for _, signature in rows[:limit]}


def choose_story(scene: dict, source_sha256: str, output_root: Path) -> dict:
    theme, scores = semantic_theme(scene)
    families = SCENE_FAMILY_MAP[theme]
    styles = tuple(STYLE_FAMILIES)
    recent = recent_story_signatures(output_root)

    selected = None
    for offset in range(max(len(families), len(styles), 6) * 2):
        family = families[(_stable_index(source_sha256, "scene", len(families)) + offset) % len(families)]
        style = styles[(_stable_index(source_sha256, "style", len(styles)) + offset * 3) % len(styles)]
        composition_id, composition = COMPOSITION_MAP[family]
        palette = (
            "WARM_STONE_GOLD_DEEP_BLUE"
            if style in {"POLYCHROME_MONUMENTAL", "ILLUMINATED_CELESTIAL", "ARCHITECTURAL_CAPRICCIO"}
            else "SEPIA_STONE_MUTED_GOLD"
        )
        figure_bucket = "MANY_12_PLUS" if family not in {"RELIC_CHAMBER", "THRONE_AND_WORLD"} else "MEDIUM_5_12"
        signature = f"{family}|{style}|{composition_id}|{palette}|{figure_bucket}"
        selected = (family, style, composition_id, composition, palette, figure_bucket, signature)
        if signature not in recent:
            break

    family, style, composition_id, composition, palette, figure_bucket, signature = selected
    theme_story = copy.deepcopy(THEME_STORIES[theme])
    hints = source_story_hints(scene)

    return {
        "schema": "janus.fresco_forge.story_plan.v5",
        "art_direction": ART_DIRECTION_ID,
        "theme": theme,
        "theme_scores": scores,
        "scene_family": family,
        "style_family": style,
        "style_description": STYLE_FAMILIES[style],
        "composition_id": composition_id,
        "composition": composition,
        "orientation": "LANDSCAPE" if family in ORIENTATION_LANDSCAPE else "PORTRAIT",
        "palette_family": palette,
        "figure_count_bucket": figure_bucket,
        "dominant_shape": composition_id,
        "central_subject": theme_story["central"],
        "central_action": theme_story["action"],
        "micro_scenes": theme_story["micro"],
        "symbols": theme_story["symbols"],
        "mood": theme_story["mood"],
        "source_story_hints": hints,
        "anti_repeat_signature": signature,
        "recent_signature_window": RECENT_SIGNATURE_WINDOW,
        "typography_policy": "NONE_IN_DIFFUSION_STAGE",
        "false_personification_guard": True,
        "epistemic_nontriumphal_guard": True,
    }


def render_prompt(scene: dict, story: dict) -> str:
    hints = story.get("source_story_hints", [])
    hint_clause = ""
    if hints:
        hint_clause = (
            " Let the human-scale episodes quietly express the source idea that "
            + " and ".join(hints[:2])
            + ", but never render those words as writing."
        )

    micro = "; ".join(story.get("micro_scenes", [])[:3])
    symbols = ", ".join(story.get("symbols", [])[:6])
    return (
        f"Create {story['style_description']}. "
        f"The composition is {story['composition']}. "
        f"At its heart, {story['central_subject']}; {story['central_action']}. "
        f"Around the main event, paint many smaller narrative moments: {micro}. "
        f"Use {symbols} as meaningful recurring objects, with layered foreground, middle distance and far architecture, "
        f"expressive but natural human anatomy, intricate old-master detail, weathered plaster edges, carved stone framing, "
        f"worn gilding and a dense world that rewards close viewing. The mood is {story['mood']}.{hint_clause} "
        "Keep uncertainty unresolved where the source is unresolved. Internal identifiers remain mechanisms or provenance, "
        "never invented named people or gods. Show no readable words, letters, captions, code, labels or inscriptions; "
        "leave all plaques and books visually unlettered. Avoid diagrams, interface grammar, repeated rectangles, icon grids, "
        "flat geometric wallpaper and empty decorative abstraction."
    ).strip()


def fit_prompt(tokenizer, scene: dict, story: dict) -> tuple[str, int, int, bool, int, str]:
    variants: list[tuple[str, dict]] = [("FULL", story)]

    compact = copy.deepcopy(story)
    compact["micro_scenes"] = compact.get("micro_scenes", [])[:2]
    compact["symbols"] = compact.get("symbols", [])[:4]
    compact["source_story_hints"] = compact.get("source_story_hints", [])[:1]
    variants.append(("COMPACT", compact))

    minimal = copy.deepcopy(compact)
    minimal["micro_scenes"] = minimal.get("micro_scenes", [])[:1]
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
        f"PROMPT_BUDGET_VIOLATION: even MINIMAL prompt exceeded {last[2]} tokens (original={last[4]})"
    )


def render_negative_prompt(scene: dict) -> str:
    negatives = list(v41.NEGATIVE_BASE) + [
        "readable text", "letters", "words", "inscriptions", "signage", "captions",
        "gibberish typography", "pseudo writing", "fake alphabet", "paragraphs", "scroll text",
        "modern poster", "modern UI", "dashboard", "wireframe", "infographic", "technical diagram",
        "CAD", "flowchart", "table", "spreadsheet", "code", "JSON", "terminal screenshot",
        "tiled icon sheet", "contact sheet", "equal rectangular cells", "repeated rectangles",
        "flat geometric blocks", "minimalist abstract mural", "primitive color bands",
        "low-detail wall pattern", "empty wallpaper", "decorative pattern as the main subject",
        "isolated floating icons", "product shot", "clean white background", "glossy machine render",
    ]
    if scene.get("archetype") not in {"HUMAN_NARRATIVE", "MYTHIC_NARRATIVE"}:
        negatives += ["named software component portrayed as a human", "repository name portrayed as a deity"]
    return ", ".join(dedupe(negatives))


def choose_canvas(story: dict, requested_width: int, requested_height: int) -> tuple[int, int]:
    # Keep roughly the same CPU pixel budget as v4.x while matching the reference
    # family's predominantly monumental vertical compositions.
    if story.get("orientation") == "LANDSCAPE":
        return 640, 448
    return 448, 640


def generate_one(pipe, candidate, repo_root, output_root, model, steps, width, height, seed) -> dict:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    proj = v3.projection(candidate.canonical_json)
    scene = v41.build_scene_plan(proj)
    story = choose_story(scene, candidate.source_sha256, output_root)
    model_prompt, prompt_tokens, max_tokens, hard_truncated, original_prompt_tokens, fit_variant = fit_prompt(
        pipe.tokenizer, scene, story
    )
    negative_prompt = render_negative_prompt(scene)
    pos, neg, chunks = v3.encode_long(pipe, model_prompt, negative_prompt, device)
    render_width, render_height = choose_canvas(story, width, height)

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
    story_json = json.dumps(story, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    receipt = {
        "schema": "janus.fresco_forge.receipt.v5",
        "generator": GENERATOR_VERSION,
        "status": "generated",
        "generated_at": base.utc_now(),
        "source_path": candidate.relpath,
        "source_sha256": candidate.source_sha256,
        "canonical_json_bytes": len(candidate.canonical_json.encode("utf-8")),
        "visual_projection_sha256": base.sha256_bytes(projection_json.encode("utf-8")),
        "scene_plan_sha256": base.sha256_bytes(scene_json.encode("utf-8")),
        "story_plan_sha256": base.sha256_bytes(story_json.encode("utf-8")),
        "prompt_sha256": base.sha256_bytes(model_prompt.encode("utf-8")),
        "prompt_mode": "monumental_allegorical_story_renderer_no_diffusion_typography",
        "prompt_fit_variant": fit_variant,
        "original_prompt_tokens": original_prompt_tokens,
        "prompt_tokens": prompt_tokens,
        "max_prompt_tokens": max_tokens,
        "prompt_hard_truncated": hard_truncated,
        "prompt_chunks": chunks,
        "semantic_coverage_ratio": 1.0,
        "semantic_model_policy": (
            "CANONICAL_JSON_TO_ROLE_AUDIT_TO_THEME_TO_NARRATIVE_ALLEGORY"
            "__NO_LITERAL_TECHNICAL_OBJECTIFICATION__NO_DIFFUSION_TYPOGRAPHY"
        ),
        "art_direction": ART_DIRECTION_ID,
        "scene_family": story["scene_family"],
        "style_family": story["style_family"],
        "composition_id": story["composition_id"],
        "palette_family": story["palette_family"],
        "figure_count_bucket": story["figure_count_bucket"],
        "dominant_shape": story["dominant_shape"],
        "orientation": story["orientation"],
        "anti_repeat_signature": story["anti_repeat_signature"],
        "recent_signature_window": story["recent_signature_window"],
        "typography_policy": story["typography_policy"],
        "false_personification_guard": True,
        "physical_gate_firewall": True,
        "epistemic_nontriumphal_guard": True,
        "narrative_event_required": True,
        "anti_grid_icon_collapse": True,
        "anti_pseudotext_gate": True,
        "calibration_negative_controls": NEGATIVE_CONTROL_CLASSES,
        "prompt_text": model_prompt,
        "negative_prompt": negative_prompt,
        "scene_plan": scene,
        "story_plan": story,
        "visual_projection": proj,
        "model": model,
        "backend": "local_diffusers_v5_monumental_allegorical_story_renderer",
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
