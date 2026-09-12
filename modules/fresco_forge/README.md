# JANUS Fresco Forge

`JANUS Fresco Forge` is a content-addressed `JSON -> fresco` pipeline for the JANUS meta-registry.

## Current renderer: v4 scene-skeleton-first

v4 preserves the full-JSON provenance and semantic coverage introduced by v3, but changes how visual dominance is assigned.

The rule is:

> Every non-technical scalar is traced and interpreted, but the image is controlled by a scene skeleton: central figure -> central action -> secondary figures -> main symbols -> background motifs.

This prevents structural research vocabulary such as `matrix`, `segmentation`, `replication`, `control`, `epoch`, or `sealed` from collapsing the whole image into a textile, wallpaper, stripe field, or abstract pattern. Those concepts may still appear, but only as subordinate side registers, reliefs, veils, small comparison scenes, or distant symbols.

## Contract

- Source corpus: `registry/**/*.json` by default.
- JSON is parsed and serialized into canonical compact UTF-8 JSON (`sort_keys=True`).
- Identity is `SHA-256(canonical_json)`, not the filename.
- Equivalent JSON content is rendered at most once even if renamed, copied, or key order changes.
- The complete canonical JSON defines identity/provenance.
- v3 semantic projection traces every scalar and separates technical provenance from visual semantics.
- v4 keeps `semantic_coverage_ratio = 1.0` for the semantic projection while using a scene skeleton to decide what dominates the picture.
- The generative prompt is explicitly figurative: a dominant central person/mythic being, a central action, visible secondary figures, gestures, ritual interaction, and story-rich sacred objects.
- Anti-collapse guards explicitly reject empty halls, architecture-only scenes, abstract patterns, striped textiles, decorative fabrics, ornamental bands, geometric wallpaper, woven rugs, and pattern-only compositions.
- Rendering runs locally inside GitHub Actions with Hugging Face Diffusers.
- Default model: `dreamlike-art/dreamlike-photoreal-2.0`.
- Scheduler: `DPMSolverMultistepScheduler`.
- No Hugging Face hosted-inference token is required for the public default model.
- Images: `artifacts/janus-fresco-forge/images/`.
- Receipts: `artifacts/janus-fresco-forge/receipts/`.
- Dedupe ledger: `artifacts/janus-fresco-forge/ledger.jsonl`.

## Pipeline

```text
registry JSON
    -> canonical SHA-256 identity
    -> full scalar trace
    -> semantic projection
    -> v4 scene skeleton
    -> figurative narrative prompt
    -> chunked CLIP embeddings
    -> Stable Diffusion
    -> PNG + receipt + ledger
```

## GitHub Actions

Workflow: `.github/workflows/janus-fresco-forge.yml`

Triggers:

- push to `main` changing `registry/**/*.json`, `modules/fresco_forge/**`, or the workflow itself;
- scheduled backlog sweep every 6 hours;
- manual `workflow_dispatch`.

The hosted GitHub job is CPU-only and intentionally caps each run at **one image**.

The Hugging Face model cache is persisted with `actions/cache` so subsequent runs can reuse the public model download.

## No `HF_TOKEN` required

The current renderer uses local Diffusers generation:

```python
StableDiffusionPipeline.from_pretrained("dreamlike-art/dreamlike-photoreal-2.0")
```

The model is downloaded to the GitHub runner and executed locally. `HF_TOKEN` is not part of the normal generation path.

## Runtime defaults

```text
model                 = dreamlike-art/dreamlike-photoreal-2.0
steps                 = 20
width                 = 512
height                = 512
guidance_scale        = 8.0
max_prompt_chunks     = 6
workflow render cap   = 1 image/run
```

## Provenance receipt v4

Every successful render records, among other fields:

- source path and canonical JSON SHA-256;
- full v3 semantic projection and scalar trace;
- `semantic_coverage_ratio`;
- v4 `scene_skeleton` and its SHA-256;
- fitted figurative prompt and negative prompt;
- prompt token/chunk counts;
- model/backend/device/scheduler;
- step count, dimensions, guidance scale and random seed;
- elapsed generation time;
- image path and image SHA-256.

Generated frescoes are visualization artifacts only. They are never evidence, proof, or a replacement for the underlying registry record.

Changing rendering parameters does not automatically regenerate a source already present in the ledger. Rerender/version semantics remain explicit so the no-repeat invariant is not silently weakened.
