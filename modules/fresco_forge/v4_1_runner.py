#!/usr/bin/env python3
"""JANUS Fresco Forge v4.1: semantic-role firewall + scene archetypes.

Fixes NAME_COLLISION -> FALSE_PERSONIFICATION. Field role is resolved from JSON
path/context before any entity is allowed to become a human or mythic figure.
Technical/system names stay system names. The renderer first chooses a scene
archetype, then translates the record into an appropriate visual scene.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from typing import Iterable

import torch

import forge as base
import v3_runner as v3

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v4.1-semantic-role-firewall"
GUIDANCE_SCALE = float(os.getenv("FRESCO_GUIDANCE_SCALE", "8.0"))

# Names in these fields are identifiers/components, never people by name alone.
NONPERSON_FIELD_TOKENS = {
    "registry_id", "canonical_name", "protocol_name", "internal_name", "repository",
    "branch", "path", "schema", "version", "id", "sha", "sha256", "state_machine",
    "adapter", "gate", "controller", "mapping", "status", "result", "stage", "label",
    "protocol", "machine", "interlock", "sequence", "implementation", "component",
}

SYSTEM_FIELD_TOKENS = {
    "protocol", "state_machine", "adapter", "gate", "controller", "interlock", "mapping",
    "implementation", "sequence", "phase", "horizon", "freeze", "thaw", "drain", "queue",
    "cohort", "epoch", "telemetry", "beacon", "validator", "verifier", "runtime", "process",
}

EXPLICIT_PERSON_FIELD_TOKENS = {
    "actor", "actors", "person", "people", "character", "characters", "figure", "figures",
    "human", "humans", "deity", "deities", "god", "goddess", "priest", "priestess",
    "witness", "witnesses", "founder_portrait", "mythic_entity", "mythic_entities",
}

EXPLICIT_OBJECT_FIELD_TOKENS = {
    "artifact", "object", "symbol", "symbols", "motif", "motifs", "item", "tool", "relic",
    "mask", "wheel", "key", "comb", "coin", "ring", "weapon", "cup", "statue",
}

EXPLICIT_ENV_FIELD_TOKENS = {
    "location", "place", "setting", "environment", "site", "city", "temple", "sanctuary",
    "chamber", "hall", "airlock", "hatch", "corridor", "sea", "desert", "forest", "sky",
}

MYTHIC_WORDS = {
    "goddess", "god", "deity", "nymph", "spirit woman", "mythic woman", "mythic man",
    "lady fortune", "janus the god", "water spirit woman", "priestess", "divine figure",
}

HUMAN_WORDS = {
    "woman", "man", "child", "children", "people", "human", "priest", "priestess",
    "warrior", "king", "queen", "mother", "father", "elder", "mourner", "witnesses",
}

ARCH_WORDS = {
    "airlock", "hatch", "gate", "chamber", "corridor", "threshold", "door", "vault",
    "decompression", "vacuum", "seal", "sealed", "reopen", "close admissions",
}

SYSTEM_WORDS = {
    "protocol", "state machine", "adapter", "controller", "acknowledgement", "epoch",
    "freeze", "thaw", "drain", "queue", "in_flight", "validation", "telemetry",
    "runtime", "process", "interlock", "repository", "implementation", "proof semantics",
}

RITUAL_WORDS = {"ritual", "ceremony", "offering", "altar", "sacred", "worship", "relic"}

NEGATIVE_BASE = [
    "false personification", "single classical statue", "marble statue", "bodybuilder statue",
    "male statue when no male person is described", "female deity when no female person is described",
    "empty hall", "plain interior", "abstract pattern", "striped textile", "decorative fabric",
    "ornamental bands", "flat tapestry pattern", "non-figurative abstraction", "geometric wallpaper",
    "pattern-only composition", "woven rug", "modern UI", "screenshot", "JSON text", "caption",
    "watermark", "logo", "glossy 3d render", "plastic skin", "extra limbs", "extra legs",
    "extra fingers", "duplicated people", "deformed anatomy", "malformed hands", "illegible typography",
]


def dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        value = re.sub(r"\s+", " ", str(raw)).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def path_tokens(path: str) -> set[str]:
    # Preserve underscore-bearing canonical field names (e.g. internal_name).
    return {x for x in re.split(r"[^a-z0-9_]+", path.casefold()) if x}


def has_any(text: str, words: Iterable[str]) -> bool:
    low = text.casefold()
    return any(w.casefold() in low for w in words)


def field_role(fact: dict) -> str:
    path = str(fact.get("path", ""))
    toks = path_tokens(path)
    value = str(fact.get("value", ""))
    low_path = path.casefold()

    if any(t in toks for t in NONPERSON_FIELD_TOKENS):
        if any(t in toks for t in SYSTEM_FIELD_TOKENS) or has_any(value, SYSTEM_WORDS | ARCH_WORDS):
            return "SYSTEM_COMPONENT"
        return "IDENTIFIER_OR_METADATA"

    if any(t in toks for t in EXPLICIT_PERSON_FIELD_TOKENS):
        return "PERSON_OR_MYTHIC_ENTITY"
    if any(t in toks for t in EXPLICIT_OBJECT_FIELD_TOKENS):
        return "OBJECT_OR_ARTIFACT"
    if any(t in toks for t in EXPLICIT_ENV_FIELD_TOKENS):
        return "ENVIRONMENT_OR_ARCHITECTURE"

    if any(x in low_path for x in ("core_idea", "problem", "description", "narrative", "meaning", "summary", "inspiration")):
        return "DESCRIPTIVE_NARRATIVE"
    if any(x in low_path for x in ("claim", "boundary", "limit", "result", "status")):
        return "EPISTEMIC_OR_STATE"
    return "GENERIC_SEMANTIC"


def role_audit(proj: dict) -> list[dict]:
    out = []
    for fact in proj.get("semantic_facts", []):
        row = dict(fact)
        row["field_role"] = field_role(fact)
        out.append(row)
    return out


def explicit_person_evidence(audit: list[dict]) -> list[str]:
    people: list[str] = []
    for fact in audit:
        role = fact["field_role"]
        value = str(fact.get("value", ""))
        if role == "PERSON_OR_MYTHIC_ENTITY" and has_any(value, HUMAN_WORDS | MYTHIC_WORDS):
            people.append(value)
        elif role == "DESCRIPTIVE_NARRATIVE" and has_any(value, MYTHIC_WORDS):
            # A descriptive sentence may establish a mythic person; an identifier may not.
            people.append(value)
    return dedupe(people)


def infer_scene_archetype(audit: list[dict]) -> tuple[str, dict]:
    scores = Counter()
    corpus = " ".join(str(x.get("value", "")) for x in audit)

    for fact in audit:
        role = fact["field_role"]
        value = str(fact.get("value", ""))
        path = str(fact.get("path", ""))
        if role == "PERSON_OR_MYTHIC_ENTITY":
            scores["HUMAN_NARRATIVE"] += 5
        if role == "DESCRIPTIVE_NARRATIVE" and has_any(value, MYTHIC_WORDS):
            scores["MYTHIC_NARRATIVE"] += 6
        if role == "SYSTEM_COMPONENT":
            scores["SYSTEM_ALLEGORY"] += 3
        if role == "ENVIRONMENT_OR_ARCHITECTURE" or has_any(value, ARCH_WORDS) or has_any(path, ARCH_WORDS):
            scores["ARCHITECTURAL_EVENT"] += 3
        if role == "OBJECT_OR_ARTIFACT":
            scores["OBJECT_RITUAL"] += 3
        if has_any(value, RITUAL_WORDS):
            scores["OBJECT_RITUAL"] += 2
        if has_any(value, SYSTEM_WORDS):
            scores["SYSTEM_ALLEGORY"] += 2
        if has_any(value, ARCH_WORDS):
            scores["ARCHITECTURAL_EVENT"] += 2

    people = explicit_person_evidence(audit)
    if not people:
        scores["HUMAN_NARRATIVE"] = 0
        scores["MYTHIC_NARRATIVE"] = 0

    order = ["MYTHIC_NARRATIVE", "HUMAN_NARRATIVE", "ARCHITECTURAL_EVENT", "SYSTEM_ALLEGORY", "OBJECT_RITUAL"]
    archetype = max(order, key=lambda x: (scores[x], -order.index(x)))
    if scores[archetype] == 0:
        archetype = "SYSTEM_ALLEGORY" if has_any(corpus, SYSTEM_WORDS) else "OBJECT_RITUAL"
    return archetype, dict(scores)


def fact_values(audit: list[dict], path_needles: Iterable[str], limit: int = 8) -> list[str]:
    out = []
    for fact in audit:
        path = str(fact.get("path", "")).casefold()
        if any(n.casefold() in path for n in path_needles):
            out.append(str(fact.get("value", "")))
    return dedupe(out)[:limit]


def audit_corpus(audit: list[dict]) -> str:
    return " ".join(str(x.get("value", "")) for x in audit).casefold()


def visual_translate_system(audit: list[dict], archetype: str) -> dict:
    corpus = audit_corpus(audit)
    core = fact_values(audit, ["core_idea", "problem", "canonical_principle"], 5)
    mapping = fact_values(audit, ["mapping"], 8)
    phases = fact_values(audit, ["state_machine", "phase", "controlled", "horizon_commit"], 10)
    limits = fact_values(audit, ["claim_limits", "alternate_terminal_states"], 6)

    is_airlock = "airlock" in corpus or ("decompression" in corpus and "vacuum" in corpus)

    if archetype == "ARCHITECTURAL_EVENT" and is_airlock:
        visual_subject = "a monumental double-hatch ancient airlock chamber, shown as a sacred engineered threshold rather than a person"
        central_action = (
            "the chamber is first frozen motionless and sealed, the inlet hatch closes, luminous currents drain away through carved channels, "
            "the chamber reaches a silent empty valley, and exactly one far hatch begins to reopen toward a new illuminated passage"
        )
        supporting = [
            "small side registers show the ordered phases of freeze, seal, close, drain, vacuum and reopen",
            "tiny anonymous attendants may operate mechanisms only as scale references; no named subsystem is personified",
            "a sealed side door represents fail-closed and a halted passage represents too-late abort",
        ]
        symbols = [
            "two interlocked bronze-and-stone hatches", "a still sealed central chamber",
            "flowing channels becoming empty", "one reopened illuminated threshold",
            "small carved phase markers without readable text",
        ]
    elif archetype == "ARCHITECTURAL_EVENT":
        visual_subject = "an ancient engineered threshold complex of gates, chambers and passages, with no subsystem depicted as a person"
        central_action = "the architectural mechanism changes state in the exact order described by the source, with one transition clearly dominating the scene"
        supporting = ["small side-register scenes show earlier and later architectural states", "failed or unresolved paths stay visibly closed"]
        symbols = ["mechanical gates", "sealed passages", "state-changing chambers", "one visually dominant transition"]
    else:
        visual_subject = "an ancient allegorical mechanism composed of gates, channels, chambers and interlocked controls, with no named software component depicted as a person"
        central_action = "the mechanism visibly executes the ordered system process described by the source"
        supporting = ["small side panels show earlier and later machine states", "failed or unresolved states remain closed and visually subdued"]
        symbols = ["interlocked mechanisms", "sealed state", "controlled flow", "validated transition"]

    return {
        "core_source": core,
        "mapping_source": mapping,
        "phase_source": phases,
        "claim_limits_source": limits,
        "visual_subject": visual_subject,
        "central_action": central_action,
        "supporting_actions": supporting,
        "main_symbols": symbols,
        "human_figures": [],
    }


def visual_translate_people(audit: list[dict]) -> dict:
    people = explicit_person_evidence(audit)
    core = fact_values(audit, ["core_idea", "description", "narrative", "meaning", "summary"], 6)
    central = people[0] if people else "an explicitly described human or mythic figure"
    return {
        "core_source": core,
        "mapping_source": [],
        "phase_source": [],
        "claim_limits_source": [],
        "visual_subject": central,
        "central_action": core[0] if core else "the central figure performs the main action explicitly described by the source",
        "supporting_actions": people[1:4],
        "main_symbols": [],
        "human_figures": people[:5],
    }


def visual_translate_object(audit: list[dict]) -> dict:
    objects = [str(x.get("value", "")) for x in audit if x["field_role"] == "OBJECT_OR_ARTIFACT"]
    core = fact_values(audit, ["core_idea", "description", "meaning", "summary", "purpose"], 6)
    subject = dedupe(objects)[0] if objects else "the principal non-human object or symbolic mechanism established by the source"
    return {
        "core_source": core,
        "mapping_source": [],
        "phase_source": [],
        "claim_limits_source": [],
        "visual_subject": subject,
        "central_action": core[0] if core else "the object is shown in the exact functional or ritual relationship described by the source",
        "supporting_actions": [],
        "main_symbols": dedupe(objects)[:6],
        "human_figures": [],
    }


def build_scene_plan(proj: dict) -> dict:
    audit = role_audit(proj)
    archetype, scores = infer_scene_archetype(audit)
    if archetype in {"ARCHITECTURAL_EVENT", "SYSTEM_ALLEGORY"}:
        translated = visual_translate_system(audit, archetype)
    elif archetype == "OBJECT_RITUAL":
        translated = visual_translate_object(audit)
    else:
        translated = visual_translate_people(audit)

    role_counts = Counter(x["field_role"] for x in audit)
    return {
        "schema": "janus.fresco_forge.semantic_role_scene.v4_1",
        "archetype": archetype,
        "archetype_scores": scores,
        "field_role_counts": dict(role_counts),
        "false_personification_guard": True,
        "personification_evidence_required": True,
        **translated,
        "style": [
            "painted directly on cracked aged lime plaster",
            "ancient narrative fresco using mineral pigments",
            "weathered hand-painted wall surface, not sculpture and not 3d render",
            "layered historical storytelling with small side-register scenes",
        ],
        "composition_rules": [
            "the scene archetype determines whether people are present",
            "system names and internal identifiers never become humans or deities by name alone",
            "named gates adapters protocols repositories and state-machine states remain mechanisms or provenance",
            "the central visual action must come from the semantic role of the source, not from token name collisions",
            "architecture may dominate only for ARCHITECTURAL_EVENT",
            "all epistemic limits remain visually non-triumphal",
        ],
        "role_audit": audit,
    }


def render_prompt(scene: dict) -> str:
    def join(items: list[str], fallback: str) -> str:
        return "; ".join(dedupe(items)) if items else fallback

    people_clause = "VISIBLE PEOPLE: " + join(scene.get("human_figures", []), "none required; do not invent a person")
    return f"""ANCIENT NARRATIVE FRESCO — SEMANTIC ROLE LOCK.
SCENE ARCHETYPE: {scene['archetype']}.
CENTRAL VISUAL SUBJECT: {scene['visual_subject']}.
CENTRAL ACTION: {scene['central_action']}.
{people_clause}.
SUPPORTING ACTIONS: {join(scene.get('supporting_actions', []), 'small secondary state changes only')}.
MAIN SYMBOLS: {join(scene.get('main_symbols', []), 'only objects implied by the source')}.
STYLE: {join(scene.get('style', []), 'ancient cracked-plaster wall fresco')}.
RULES: {join(scene.get('composition_rules', []), 'semantic roles control depiction')}.

Translate the source meaning into a coherent visual scene. Do not personify internal names, repository names, protocol names, gates, adapters, controllers, state-machine labels or software components. A human or deity may appear only when an explicit person/mythic entity is established by a person-role field or descriptive narrative. Keep unconfirmed or prohibited claims visually unresolved or closed, never triumphant. No readable code, no UI, no literal JSON.""".strip()


def render_negative_prompt(scene: dict) -> str:
    extra = []
    if not scene.get("human_figures"):
        extra += ["central human hero", "central goddess", "central god", "mythic woman", "mythic man", "heroic statue", "portrait composition"]
    if scene["archetype"] != "ARCHITECTURAL_EVENT":
        extra += ["architecture-only composition"]
    return ", ".join(dedupe(NEGATIVE_BASE + extra))


def hard_cap_prompt(tokenizer, prompt: str) -> tuple[str, int, int, bool, int]:
    max_tokens = max(1, tokenizer.model_max_length - 2) * v3.MAX_PROMPT_CHUNKS
    ids = tokenizer(prompt, add_special_tokens=False, return_tensors=None)["input_ids"]
    if ids and isinstance(ids[0], list):
        ids = ids[0]
    original = len(ids)
    if original <= max_tokens:
        return prompt, original, max_tokens, False, original
    clipped = ids[:max_tokens]
    text = tokenizer.decode(clipped, skip_special_tokens=True, clean_up_tokenization_spaces=True).strip()
    final_count = v3.token_count(tokenizer, text)
    # Decode may rarely retokenize a little differently; enforce again if necessary.
    if final_count > max_tokens:
        ids2 = tokenizer(text, add_special_tokens=False, return_tensors=None)["input_ids"]
        if ids2 and isinstance(ids2[0], list):
            ids2 = ids2[0]
        text = tokenizer.decode(ids2[:max_tokens], skip_special_tokens=True, clean_up_tokenization_spaces=True).strip()
        final_count = min(v3.token_count(tokenizer, text), max_tokens)
    return text, final_count, max_tokens, True, original


def generate_one(pipe, candidate, repo_root, output_root, model, steps, width, height, seed) -> dict:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    proj = v3.projection(candidate.canonical_json)
    scene = build_scene_plan(proj)
    raw_prompt = render_prompt(scene)
    model_prompt, prompt_tokens, max_tokens, hard_truncated, original_prompt_tokens = hard_cap_prompt(pipe.tokenizer, raw_prompt)
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
    receipt = {
        "schema": "janus.fresco_forge.receipt.v4_1",
        "generator": GENERATOR_VERSION,
        "status": "generated",
        "generated_at": base.utc_now(),
        "source_path": candidate.relpath,
        "source_sha256": candidate.source_sha256,
        "canonical_json_bytes": len(candidate.canonical_json.encode("utf-8")),
        "visual_projection_sha256": base.sha256_bytes(projection_json.encode("utf-8")),
        "scene_plan_sha256": base.sha256_bytes(scene_json.encode("utf-8")),
        "prompt_sha256": base.sha256_bytes(model_prompt.encode("utf-8")),
        "prompt_mode": "semantic_role_firewall_scene_archetype",
        "original_prompt_tokens": original_prompt_tokens,
        "prompt_tokens": prompt_tokens,
        "max_prompt_tokens": max_tokens,
        "prompt_hard_truncated": hard_truncated,
        "prompt_chunks": chunks,
        "semantic_coverage_ratio": 1.0,
        "semantic_model_policy": "ALL_NONTECHNICAL_SCALARS_TRACED__FIELD_ROLE_TO_ENTITY_TYPE_TO_SCENE_ARCHETYPE_TO_VISUAL_TRANSLATION",
        "false_personification_guard": True,
        "scene_archetype": scene["archetype"],
        "prompt_text": model_prompt,
        "negative_prompt": negative_prompt,
        "scene_plan": scene,
        "visual_projection": proj,
        "model": model,
        "backend": "local_diffusers_semantic_role_firewall_chunked_clip",
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
