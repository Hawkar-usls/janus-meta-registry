# JANUS Fresco Forge

`JANUS Fresco Forge` is a content-addressed `JSON -> fresco` pipeline for the JANUS meta-registry.

## Current renderer: v4.2 Fresco Style Lock + Ancient Visual Grammar

v4.2 preserves the semantic-role and physical-gate firewalls from v4.1.1, then adds a separate artistic compiler layer.

The pipeline is explicitly staged:

```text
field role
    -> entity type
    -> scene archetype
    -> semantic visual translation
    -> fresco visual translator
    -> ancient visual grammar lock
    -> image generation
```

The v4.1.1 firewall answers **what the source means**. v4.2 answers **how that meaning may be expressed as an ancient wall fresco**.

A name is not a person merely because it resembles a mythic/person name. Fields such as `internal_name`, `protocol_name`, `repository`, `branch`, `path`, `gate`, `adapter`, `controller`, `state_machine`, `mapping`, and other system/provenance fields are never allowed to create a human or deity by name alone.

A workflow/control `gate` is also not physical architecture by itself. `ARCHITECTURAL_EVENT` requires real descriptive architectural evidence such as an airlock, hatch, chamber, threshold, door, decompression, or vacuum context.

## Scene archetypes

- `HUMAN_NARRATIVE` — explicit human actors dominate.
- `MYTHIC_NARRATIVE` — explicit mythic/deity entities dominate.
- `OBJECT_RITUAL` — a source-established object/artifact/ritual is central.
- `SYSTEM_ALLEGORY` — system mechanics are translated into non-human symbolic fresco imagery.
- `ARCHITECTURAL_EVENT` — real gates, chambers, airlocks, thresholds and transitions may dominate without inventing a protagonist.

## v4.2 ancient visual grammar

Technical semantics are never handed to the image model as modern visual grammar. `SYSTEM_ALLEGORY`, for example, is translated into flat wall-painted thresholds, channels, vessels, compartments, seals and narrative registers rather than a CAD-like mechanism or diagram.

Mandatory style lock:

- full-frame cracked lime-plaster wall surface;
- mineral pigments absorbed into aged intonaco;
- worn ochre, iron red, soot black, terre verte and faded blue;
- visible pigment loss, abrasion, age stains and crack networks;
- flat hand-painted contours and old mural spatial logic;
- irregular narrative registers and side scenes rather than modern grids;
- every visual subject remains embedded in the painted wall surface.

Modern visual grammar is forbidden by prompt and negative prompt, including:

- 3D/product/CAD renders;
- diagrams, flowcharts and infographics;
- UI/interface panels and vector graphics;
- glossy industrial machinery or product photography;
- isolated floating objects on neutral/studio backgrounds;
- clean geometric poster or blueprint compositions.

The known failure classes used for calibration are:

```text
FAIL__3D_MACHINE_COLLAPSE
FAIL__DIAGRAM_GEOMETRY_COLLAPSE
FAIL__INFOGRAPHIC_COLLAPSE
FAIL__FLOATING_OBJECT_COLLAPSE
```

## Contract

- Source corpus: `registry/**/*.json` by default.
- JSON is canonicalized and identified by `SHA-256(canonical_json)`.
- Equivalent JSON content is rendered at most once regardless of filename/key order.
- The complete canonical JSON remains the source of identity/provenance.
- Full scalar trace and semantic projection are preserved for audit.
- `semantic_coverage_ratio = 1.0` means the semantic record is traced/interpreted; it does **not** mean every scalar is pasted literally into the generative prompt.
- Field-role audit and chosen scene archetype are stored in every receipt.
- `false_personification_guard = true` and `physical_gate_firewall = true` remain mandatory.
- v4.2 adds `ancient_visual_grammar_lock = true`, `no_modern_visual_grammar = true`, and `full_frame_plaster_surface = true`.
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
    -> v4.1.1 semantic translation/firewalls
    -> v4.2 fresco visual translation
    -> ancient visual grammar lock
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
width              = 512
height             = 512
guidance_scale     = 8.5
max_prompt_chunks  = 6
workflow render cap= 1 image/run
```

## Receipt v4.2

Every successful render records:

- source path and canonical JSON SHA-256;
- full semantic projection/scalar trace;
- `semantic_coverage_ratio`;
- field-role audit and role counts;
- chosen `scene_archetype` and archetype scores;
- semantic `scene_plan`;
- `translated_scene` generated by the fresco visual translator;
- `false_personification_guard = true`;
- `physical_gate_firewall = true`;
- `ancient_visual_grammar_lock = true`;
- `no_modern_visual_grammar = true`;
- `full_frame_plaster_surface = true`;
- final hard-capped prompt and negative prompt;
- prompt token/chunk counts and truncation flag;
- model/backend/device/scheduler;
- steps, dimensions, guidance scale, seed and elapsed time;
- image path and image SHA-256.

Generated frescoes are visualization artifacts only. They are never evidence, proof, or a replacement for the underlying registry record.
