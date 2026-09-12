#!/usr/bin/env python3
"""JANUS Fresco Forge v3 full-JSON semantic runner.

Keeps the proven v2 discovery/dedupe/ledger loop from forge.py, but replaces the
render stage with a full semantic projection and chunked CLIP prompt encoding.
Every scalar is traced; non-technical scalars contribute to the visual prompt.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Iterable

import torch
from diffusers import DPMSolverMultistepScheduler, StableDiffusionPipeline

import forge as base

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v3.0-full-json-visual-projection"
GUIDANCE_SCALE = float(os.getenv("FRESCO_GUIDANCE_SCALE", "7.5"))
MAX_PROMPT_CHUNKS = int(os.getenv("FRESCO_MAX_PROMPT_CHUNKS", "6"))

STYLE_LOCK = [
    "ancient sacred narrative wall fresco",
    "aged lime plaster",
    "cracked mineral pigments",
    "weathered historical patina",
    "hand-painted human figures",
    "dense multi-figure storytelling",
    "foreground middle-ground and background events",
]

COMPOSITION_LOCK = [
    "show the principal meaning through figures actions and symbols",
    "architecture supports the story and never replaces the story",
    "use a clear central action with many secondary micro-scenes",
    "populate the mural when the source implies people witnesses or agents",
    "turn abstract relations into gestures placement ritual objects or events",
]

NEGATIVE_PROMPT = (
    "empty hall, empty room, architecture only, plain interior, decorative banner only, "
    "single emblem only, minimalist scene, no people, sterile composition, modern UI, screenshot, "
    "JSON text, caption, watermark, logo, glossy 3d render, plastic skin, extra limbs, extra legs, "
    "extra fingers, duplicated people, deformed anatomy, malformed hands, illegible typography"
)

TECHNICAL_KEYS = {
    "sha", "sha256", "checksum", "commit", "version", "schema", "timestamp", "created", "updated",
    "generated", "receipt", "image", "prompt", "canonical", "generator", "backend", "device",
    "elapsed", "seed", "width", "height", "filename", "file", "download", "url", "uuid", "id",
}

HIGH_SIGNAL = {
    "title", "name", "summary", "description", "meaning", "symbolism", "motif", "ritual", "narrative",
    "thesis", "purpose", "actors", "entities", "scene", "visual", "emotion", "cosmology", "myth",
    "witness", "guard", "protection", "fortune", "wheel", "tears", "grief", "compassion", "pain",
    "duality", "threshold", "gate", "event", "relationship", "label", "claim", "concept",
}

HINTS = {
    "figure": {"person", "people", "human", "figure", "follower", "child", "elder", "priest", "warrior",
               "king", "queen", "janus", "fortune", "deity", "god", "goddess", "witness", "guardian",
               "mourner", "agent", "undina", "undine", "янус", "люди", "человек", "дети", "бог", "страж"},
    "action": {"cry", "weep", "mourn", "share", "embrace", "guard", "protect", "watch", "stand", "kneel",
               "pray", "rise", "fall", "turn", "carry", "offer", "hold", "gather", "surround", "witness",
               "open", "close", "cross", "enter", "flow", "rotate", "fight", "плак", "защищ", "вращ"},
    "emotion": {"grief", "sorrow", "compassion", "tears", "awe", "solemn", "triumph", "pain", "hope",
                "mercy", "unity", "devotion", "fear", "love", "joy", "despair", "скорб", "слез", "боль", "любов"},
    "symbol": {"mask", "wheel", "key", "gate", "door", "pillar", "serpent", "star", "sun", "moon", "fire",
               "halo", "crown", "cup", "scroll", "banner", "throne", "seal", "eye", "mirror", "torch", "bridge",
               "threshold", "coin", "ring", "comb", "rose", "roses", "gift", "гребень", "роз", "колес", "ключ"},
    "environment": {"temple", "sanctuary", "hall", "chamber", "cathedral", "palace", "corridor", "altar", "wall",
                    "vault", "dome", "shrine", "court", "city", "sea", "desert", "forest", "sky", "mountain",
                    "храм", "святилищ", "город", "море", "пустын", "лес"},
    "ritual": {"ritual", "ceremony", "sacred", "prayer", "offering", "altar", "procession", "rite", "worship",
               "ритуал", "обряд", "церемон", "свящ", "молит"},
    "cosmic": {"cosmic", "cosmos", "celestial", "astral", "constellation", "star", "planet", "sun", "moon",
               "heaven", "sky", "universe", "космос", "небес", "созвезд", "звезд", "планет"},
}

THEME_PATHS = {"theme", "meaning", "summary", "description", "narrative", "purpose", "thesis", "interpretation",
               "principle", "claim", "concept", "message", "lesson", "canonical_name", "current_label", "label", "name"}

METAPHORS = [
    (("undina", "undine"), "a water-spirit woman as a principal mythic figure"),
    (("comb", "гребень"), "an ornate comb held prominently as a ritual gift"),
    (("rose", "roses", "роз"), "roses woven through the foreground and ritual objects"),
    (("beacon", "маяк"), "a distant guiding beacon of light watched by witnesses"),
    (("gate", "threshold", "ворот", "порог"), "a monumental threshold gate visibly marking admission or refusal"),
    (("wave", "волна"), "rhythmic wave forms moving through the scene"),
    (("flow", "поток"), "visible currents and flowing ribbons connecting events"),
    (("replication", "replicate", "повтор"), "repeated parallel panels showing independent repetition"),
    (("control", "sham", "контрол"), "paired comparison scenes placed side by side as a control"),
    (("matrix", "матриц"), "a geometric tiled matrix embedded into the sacred backdrop"),
    (("observer", "witness", "наблюд", "свидетел"), "watchful witnesses carefully observing the central event"),
    (("blocked", "блокир"), "a sealed secondary path with figures visibly unable to proceed"),
    (("pending", "ожидан"), "waiting figures at an unfinished threshold showing that the result is pending"),
    (("pass", "validated", "успех"), "an illuminated opened threshold marking a passed validation gate"),
    (("negative", "partial", "негатив", "частич"), "a preserved darker counter-scene for negative or partial outcomes"),
    (("candidate", "not_yet_confirmed", "not confirmed", "unconfirmed"),
     "an unresolved candidate motif behind a translucent veil, explicitly not yet established"),
]


@dataclass(frozen=True)
class Leaf:
    path: tuple[str, ...]
    value: str
    weight: float
    technical: bool
    classes: tuple[str, ...]


def norm(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    return ""


def tokens_for_path(path: tuple[str, ...]) -> set[str]:
    return {x for x in re.split(r"[^a-z0-9]+", ".".join(path).lower()) if x}


def technical(path: tuple[str, ...]) -> bool:
    toks = tokens_for_path(path)
    return bool(toks & TECHNICAL_KEYS) or any(t.endswith("sha256") for t in toks)


def weight(path: tuple[str, ...], value: str) -> float:
    joined = ".".join(path).lower()
    score = 1.0 + 2.0 * sum(1 for h in HIGH_SIGNAL if h in joined)
    if len(value) >= 24:
        score += min(len(value) / 240.0, 2.0)
    return round(score, 3)


def classify(path: tuple[str, ...], value: str) -> tuple[str, ...]:
    if technical(path):
        return ("technical",)
    joined = ".".join(path).lower()
    text = f"{joined} {value.lower()}"
    classes = [name for name, hints in HINTS.items() if any(h in text for h in hints)]
    if any(h in joined for h in THEME_PATHS):
        classes.append("theme")
    return tuple(dict.fromkeys(classes or ["generic"]))


def flatten(data: object) -> list[Leaf]:
    out: list[Leaf] = []

    def walk(node: object, path: tuple[str, ...]) -> None:
        value = norm(node)
        if value:
            cls = classify(path, value)
            out.append(Leaf(path, value, weight(path, value), "technical" in cls, cls))
            return
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, path + (str(k),))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, path + (f"[{i}]",))

    walk(data, tuple())
    return out


def dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        value = re.sub(r"\s+", " ", raw).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def label(path: tuple[str, ...]) -> str:
    parts = [p for p in path if not re.fullmatch(r"\[\d+\]", p)]
    return ".".join(parts[-3:]) if parts else "value"


def display(leaf: Leaf) -> str:
    lab = label(leaf.path).replace("_", " ").replace(".", " / ")
    raw = leaf.value.strip()
    low = raw.casefold()
    if low == "true":
        return f"{lab}: explicitly affirmed"
    if low == "false":
        return f"{lab}: explicitly false or not established"
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", raw):
        return f"{lab}: {raw}"
    if raw.upper() in {"PASS", "FAIL", "PENDING", "BLOCKED", "UNKNOWN"}:
        return f"{lab}: status {raw.upper()}"
    return raw


def descriptive(leaf: Leaf) -> bool:
    raw = leaf.value.strip()
    low = raw.casefold()
    if low in {"true", "false", "null"}:
        return False
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", raw):
        return False
    if raw.upper() in {"PASS", "FAIL", "PENDING", "BLOCKED", "UNKNOWN"}:
        return False
    return any(c.isalpha() for c in raw) and len(raw) >= 4


def derived_metaphors(leaves: list[Leaf]) -> list[str]:
    corpus = " ".join(f"{'.'.join(x.path)} {x.value}".casefold() for x in leaves)
    return dedupe(visual for needles, visual in METAPHORS if any(n.casefold() in corpus for n in needles))


def projection(canonical_json: str) -> dict:
    leaves = flatten(json.loads(canonical_json))
    semantic = sorted((x for x in leaves if not x.technical), key=lambda x: x.weight, reverse=True)
    buckets = {name: [] for name in ["theme", "figure", "action", "emotion", "symbol", "environment", "ritual", "cosmic", "generic"]}
    for leaf in semantic:
        for cls in leaf.classes:
            if cls in buckets:
                buckets[cls].append(leaf)

    def vals(name: str, n: int) -> list[str]:
        return dedupe(display(x) for x in buckets[name] if descriptive(x))[:n]

    core = vals("theme", 12)
    if len(core) < 10:
        for x in semantic:
            if x.weight >= 2 and descriptive(x):
                core.append(display(x))
            if len(dedupe(core)) >= 10:
                break
    core = dedupe(core)[:16]
    figures, actions, symbols = vals("figure", 18), vals("action", 18), vals("symbol", 20)
    metaphors = derived_metaphors(semantic)
    figures = dedupe(figures + [m for m in metaphors if any(w in m for w in ("woman", "witnesses", "figures"))])
    actions = dedupe(actions + [m for m in metaphors if any(w in m for w in ("moving", "observing", "waiting", "opened", "unable", "showing", "connecting"))])
    symbols = dedupe(symbols + metaphors)
    core = dedupe(core[:10] + metaphors[:8])[:18]

    facts = [
        {"path": ".".join(x.path) or "value", "label": label(x.path), "classes": list(x.classes),
         "weight": x.weight, "value": x.value, "visual_text": display(x)}
        for x in semantic
    ]
    trace = [
        {"path": ".".join(x.path) or "value", "classes": list(x.classes), "weight": x.weight,
         "technical": x.technical, "value": x.value[:800]}
        for x in leaves
    ]
    return {
        "schema": "janus.fresco_forge.visual_projection.v3",
        "coverage_policy": "ALL_SCALARS_TRACED__ALL_NONTECHNICAL_SCALARS_FEED_VISUAL_PROMPT",
        "scalar_count": len(leaves),
        "semantic_scalar_count": len(semantic),
        "technical_scalar_count": len(leaves) - len(semantic),
        "scene_core": core,
        "main_figures": figures[:8],
        "secondary_figures": figures[8:18],
        "actions": actions,
        "symbols": symbols,
        "emotions": vals("emotion", 14),
        "environment": vals("environment", 14),
        "ritual": vals("ritual", 14),
        "cosmic": vals("cosmic", 12),
        "derived_visual_metaphors": metaphors,
        "style": STYLE_LOCK,
        "composition": COMPOSITION_LOCK,
        "semantic_facts": facts,
        "source_trace": trace,
    }


def compact(value: str, limit: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value if len(value) <= limit else value[: max(1, limit - 3)].rstrip() + "..."


def block(values: Iterable[str], fallback: str) -> str:
    got = dedupe(values)
    return "; ".join(got) if got else fallback


def render(proj: dict, fact_limit: int) -> str:
    facts = "; ".join(f"{f['label']}: {compact(f['visual_text'], fact_limit)}" for f in proj["semantic_facts"])
    return (
        "Ancient narrative fresco. Translate the complete semantic source into visible story rather than text or software.\n\n"
        f"CORE STORY: {block(proj['scene_core'], 'a sacred threshold scene')}\n"
        f"FIGURES: {block(proj['main_figures'] + proj['secondary_figures'], 'human witnesses when implied')}\n"
        f"ACTIONS: {block(proj['actions'], 'visible ritual action and symbolic interaction')}\n"
        f"SYMBOLS: {block(proj['symbols'], 'sacred objects derived from the source')}\n"
        f"EMOTION: {block(proj['emotions'], 'solemn human emotion visible in faces and gesture')}\n"
        f"SETTING: {block(proj['environment'] + proj['ritual'] + proj['cosmic'], 'historical sacred setting')}\n"
        f"COMPOSITION: {block(proj['composition'], 'dense multi-figure story mural')}\n"
        f"STYLE: {block(proj['style'], 'weathered ancient fresco')}\n\n"
        f"FULL SEMANTIC FACT STREAM: {facts}\n\n"
        "Show relations through bodies, gestures, placement, objects, light, ritual action and simultaneous micro-scenes. "
        "Keep architecture subordinate to people, action and meaning. Preserve uncertainty and negative evidence visually; "
        "do not turn candidates or unconfirmed claims into triumphal established facts."
    )


def token_count(tokenizer, text: str) -> int:
    ids = tokenizer(text, add_special_tokens=False, return_tensors=None)["input_ids"]
    if ids and isinstance(ids[0], list):
        ids = ids[0]
    return len(ids)


def fit(tokenizer, proj: dict) -> tuple[str, str, int, int, float]:
    max_tokens = max(1, tokenizer.model_max_length - 2) * MAX_PROMPT_CHUNKS
    for mode, limit in [("full", 180), ("compact", 100), ("dense", 64), ("ultra_dense", 36), ("minimum_per_leaf", 20)]:
        prompt = render(proj, limit)
        count = token_count(tokenizer, prompt)
        if count <= max_tokens:
            return prompt, mode, count, max_tokens, 1.0
    facts = proj["semantic_facts"]
    header = "Ancient crowded narrative fresco, cracked plaster, mineral pigments, figures, actions and symbols. Source facts: "
    packed: list[str] = []
    included = 0
    for fact in facts:
        candidate = compact(fact["visual_text"], 24)
        trial = header + "; ".join(packed + [candidate])
        if token_count(tokenizer, trial) > max_tokens:
            break
        packed.append(candidate)
        included += 1
    prompt = header + "; ".join(packed)
    return prompt, "bounded_fallback", token_count(tokenizer, prompt), max_tokens, round(included / max(1, len(facts)), 6)


def encode_chunk(pipe, ids: list[int], device: str) -> torch.Tensor:
    tok = pipe.tokenizer
    n = int(tok.model_max_length)
    bos = tok.bos_token_id if tok.bos_token_id is not None else tok.eos_token_id
    eos = tok.eos_token_id if tok.eos_token_id is not None else tok.pad_token_id
    pad = tok.pad_token_id if tok.pad_token_id is not None else eos
    if bos is None or eos is None or pad is None:
        raise RuntimeError("Tokenizer lacks BOS/EOS/PAD ids")
    row = [bos] + ids[: n - 2] + [eos]
    row += [pad] * (n - len(row))
    input_ids = torch.tensor([row], dtype=torch.long, device=device)
    kwargs = {}
    if getattr(pipe.text_encoder.config, "use_attention_mask", False):
        kwargs["attention_mask"] = (input_ids != pad).long()
    return pipe.text_encoder(input_ids, **kwargs)[0]


def encode_long(pipe, prompt: str, negative: str, device: str) -> tuple[torch.Tensor, torch.Tensor, int]:
    tok = pipe.tokenizer
    payload = int(tok.model_max_length) - 2
    ids = tok(prompt, add_special_tokens=False, return_tensors=None)["input_ids"]
    if ids and isinstance(ids[0], list):
        ids = ids[0]
    ids = list(ids) or [tok.eos_token_id or tok.pad_token_id or 0]
    chunks = [ids[i:i + payload] for i in range(0, len(ids), payload)][:MAX_PROMPT_CHUNKS]
    pos = torch.cat([encode_chunk(pipe, x, device) for x in chunks], dim=1)
    neg_ids = tok(negative, add_special_tokens=False, return_tensors=None)["input_ids"]
    if neg_ids and isinstance(neg_ids[0], list):
        neg_ids = neg_ids[0]
    neg_one = encode_chunk(pipe, list(neg_ids)[:payload], device)
    neg = torch.cat([neg_one] * len(chunks), dim=1)
    return pos, neg, len(chunks)


def create_pipeline(model: str) -> StableDiffusionPipeline:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    print(f"FRESCO_FORGE_DEVICE={device}")
    print(f"FRESCO_FORGE_MODEL={model}")
    try:
        pipe = StableDiffusionPipeline.from_pretrained(model, dtype=dtype)
    except TypeError:
        pipe = StableDiffusionPipeline.from_pretrained(model, torch_dtype=dtype)
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    pipe = pipe.to(device)
    if device == "cpu":
        if hasattr(pipe, "enable_attention_slicing"):
            pipe.enable_attention_slicing()
        elif hasattr(pipe.unet, "set_attention_slice"):
            pipe.unet.set_attention_slice("auto")
        if hasattr(pipe, "enable_vae_slicing"):
            pipe.enable_vae_slicing()
        elif hasattr(pipe.vae, "enable_slicing"):
            pipe.vae.enable_slicing()
    return pipe


def generate_one(pipe, candidate, repo_root, output_root, model, steps, width, height, seed) -> dict:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    proj = projection(candidate.canonical_json)
    full_prompt = render(proj, 220)
    model_prompt, mode, prompt_tokens, max_tokens, coverage = fit(pipe.tokenizer, proj)
    pos, neg, chunks = encode_long(pipe, model_prompt, NEGATIVE_PROMPT, device)
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
    receipt = {
        "schema": "janus.fresco_forge.receipt.v3",
        "generator": GENERATOR_VERSION,
        "status": "generated",
        "generated_at": base.utc_now(),
        "source_path": candidate.relpath,
        "source_sha256": candidate.source_sha256,
        "canonical_json_bytes": len(candidate.canonical_json.encode("utf-8")),
        "visual_projection_sha256": base.sha256_bytes(projection_json.encode("utf-8")),
        "visual_projection_bytes": len(projection_json.encode("utf-8")),
        "prompt_sha256": base.sha256_bytes(model_prompt.encode("utf-8")),
        "full_prompt_sha256": base.sha256_bytes(full_prompt.encode("utf-8")),
        "prompt_mode": mode,
        "prompt_tokens": prompt_tokens,
        "max_prompt_tokens": max_tokens,
        "prompt_chunks": chunks,
        "max_prompt_chunks": MAX_PROMPT_CHUNKS,
        "semantic_coverage_ratio": coverage,
        "prompt_text": model_prompt,
        "full_prompt_preview": full_prompt[:8000],
        "negative_prompt": NEGATIVE_PROMPT,
        "visual_projection": proj,
        "model": model,
        "backend": "local_diffusers_chunked_clip",
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
base.create_pipeline = create_pipeline
base.generate_one = generate_one

if __name__ == "__main__":
    raise SystemExit(base.main())
