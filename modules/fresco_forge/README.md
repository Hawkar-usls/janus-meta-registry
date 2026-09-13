# JANUS Fresco Forge

`JANUS Fresco Forge` is a content-addressed `JSON -> fresco` pipeline for the JANUS meta-registry.

## Current renderer: v4.3 Continuous Mural Composition Lock

v4.3 preserves the semantic-role and physical-gate firewalls from v4.1.1 and the compact ancient visual grammar from v4.2.1, then adds a composition firewall against tiled/icon-sheet collapse.

The pipeline is explicitly staged:

```text
field role
    -> entity type
    -> scene archetype
    -> semantic visual translation
    -> ancient fresco visual translation
    -> continuous mural composition lock
    -> image generation
```

The v4.1.1 firewall answers **what the source means**. v4.2.1 answers **how that meaning is expressed in ancient fresco grammar**. v4.3 answers **how the entire frame must remain one continuous mural rather than a grid of repeated icons or isolated objects**.

A name is not a person merely because it resembles a mythic/person name. Fields such as `internal_name`, `protocol_name`, `repository`, `branch`, `path`, `gate`, `adapter`, `controller`, `state_machine`, `mapping`, and other system/provenance fields are never allowed to create a human or deity by name alone.

A workflow/control `gate` is also not physical architecture by itself. `ARCHITECTURAL_EVENT` requires real descriptive architectural evidence such as an airlock, hatch, chamber, threshold, door, decompression, or vacuum context.

## Scene archetypes

- `HUMAN_NARRATIVE` — explicit human actors dominate.
- `MYTHIC_NARRATIVE` — explicit mythic/deity entities dominate.
- `OBJECT_RITUAL` — a source-established object/artifact/ritual is central.
- `SYSTEM_ALLEGORY` — system mechanics are translated into non-human symbolic fresco imagery.
- `ARCHITECTURAL_EVENT` — real gates, chambers, airlocks, thresholds and transitions may dominate without inventing a protagonist.

## v4.3 continuous mural lock

Every render is required to be one connected wall painting across the full frame. The generator must not split the scene into a contact sheet, icon board, specimen grid, repeated medallions, equal cells, or isolated badges.

Mandatory composition rules:

- one continuous asymmetric mural scene;
- one shared cracked plaster field across the entire frame;
- irregular spacing and open painted space between elements;
- no rows/columns of repeated equal subjects;
- no tiled layout, contact sheet, icon sheet, specimen board, sticker sheet, or 3x3 matrix;
- distributed/swarm systems become one shared mural environment with uneven peer nodes connected by painted ribbons;
- absent/stale nodes become faded gaps or dim positions inside the same mural, not separate icons;
- system/architectural/object scenes render on a landscape `640x448` canvas to reduce square-grid bias;
- guidance scale is reduced to `7.5` to avoid over-constrained symmetric repetition.

## Ancient visual grammar

Technical semantics are never handed to the image model as modern visual grammar. Mandatory style lock:

- full-frame cracked lime-plaster wall surface;
- mineral pigments absorbed into aged intonaco;
- worn ochre, iron red, soot black, terre verte and faded blue;
- visible pigment loss, abrasion, age stains and crack networks;
- flat hand-painted contours and old mural spatial logic;
- every visual subject remains embedded in the painted wall surface.

Modern visual grammar is forbidden by prompt and negative prompt, including 3D/product/CAD renders, diagrams, flowcharts, infographics, UI panels, glossy machinery, isolated floating objects, modern icon grids, and clean geometric posters.

The observed calibration failures are explicitly preserved as negative controls:

```text
FAIL__3D_MACHINE_COLLAPSE
FAIL__DIAGRAM_GEOMETRY_COLLAPSE
FAIL__TILED_ICON_GRID_COLLAPSE
```

## Contract

- Source corpus: `registry/**/*.json` by default.
- JSON is canonicalized and identified by `SHA-256(canonical_json)`.
- Equivalent JSON content is rendered at most once regardless of filename/key order.
- Full scalar trace and semantic projection are preserved for audit.
- `semantic_coverage_ratio = 1.0` means the semantic record is traced/interpreted; it does **not** mean every scalar is pasted literally into the generative prompt.
- `false_personification_guard = true` and `physical_gate_firewall = true` remain mandatory.
- `ancient_visual_grammar_lock = true`, `no_modern_visual_grammar = true`, `full_frame_plaster_surface = true`, `continuous_mural_lock = true`, and `anti_grid_icon_collapse = true` are mandatory for v4.3.
- Prompt length is hard-capped to the actual multi-chunk CLIP budget.
- Rendering runs locally in GitHub Actions with Hugging Face Diffusers.
- Default model: `dreamlike-art/dreamlike-photoreal-2.0`.
- Scheduler: `DPMSolverMultistepScheduler`.
- No hosted-inference `HF_TOKEN` is required for the public default model.

## Pipeline

```text
registry JSON
    -> canonical SHA-256 identity
    -> full scalar trace
    -> semantic projection
    -> field-role audit
    -> entity typing
    -> scene-archetype inference
    -> v4.1.1 semantic firewalls
    -> v4.2.1 compact ancient visual translation
    -> v4.3 continuous mural composition lock
    -> hard-capped chunked CLIP prompt
    -> Stable Diffusion
    -> PNG + receipt + ledger
```

## Outputs

```text
artifacts/janus-fresco-forge/images/
artifacts/janus-fresco-forge/receipts/
artifacts/janus-fresco-forge/ledger.jsonl
```

## GitHub Actions

Workflow: `.github/workflows/janus-fresco-forge.yml`

Triggers:

- push to `main` changing `registry/**/*.json`, `modules/fresco_forge/**`, or the workflow itself;
- scheduled backlog sweep every 6 hours;
- manual `workflow_dispatch`.

The hosted GitHub job is CPU-only and intentionally caps each run at **one image**.

## Runtime defaults

```text
model              = dreamlike-art/dreamlike-photoreal-2.0
steps              = 20
human canvas       = 512x512
system canvas      = 640x448
guidance_scale     = 7.5
max_prompt_chunks  = 6
workflow render cap= 1 image/run
```

## Receipt v4.3

Every successful render records source/provenance, full semantic projection, field-role audit, scene archetype, translated scene, final prompt/negative prompt, token budget, rendering settings, plus:

```text
false_personification_guard = true
physical_gate_firewall = true
ancient_visual_grammar_lock = true
no_modern_visual_grammar = true
full_frame_plaster_surface = true
continuous_mural_lock = true
anti_grid_icon_collapse = true
```

Generated frescoes are visualization artifacts only. They are never evidence, proof, or a replacement for the underlying registry record.
