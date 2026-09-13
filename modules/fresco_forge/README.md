# JANUS Fresco Forge

`JANUS Fresco Forge` is a content-addressed `JSON -> fresco` visualization pipeline for the JANUS meta-registry.

## Current renderer: v4.3.1 Scene Focus Firewall + Continuous Mural Lock

The current pipeline separates four different questions instead of letting keywords directly control the picture:

```text
field role
    -> entity type
    -> scene archetype
    -> dominant scene focus
    -> ancient visual translation
    -> continuous mural composition lock
    -> image generation
```

The layers have independent responsibilities:

- v4.1.1 semantic-role firewall: system/internal names do not become people or gods by name alone;
- v4.1.1 physical-gate firewall: workflow/control `gate` does not become physical architecture without real architectural context;
- v4.3.1 scene-focus firewall: incidental words such as `node`, `peer`, `memory`, `gate`, or `archive` do not hijack the whole scene; path-weighted semantic evidence determines the dominant topic;
- ancient visual grammar: technical semantics are translated into painted symbols rather than CAD/UI/product imagery;
- continuous mural lock: the frame is one asymmetric wall painting, never an icon grid/contact sheet/specimen board.

## Scene archetypes

- `HUMAN_NARRATIVE` — explicit human actors dominate.
- `MYTHIC_NARRATIVE` — explicit mythic/deity entities dominate.
- `OBJECT_RITUAL` — a source-established object/artifact/ritual is central.
- `SYSTEM_ALLEGORY` — system semantics are translated into non-human symbolic fresco imagery.
- `ARCHITECTURAL_EVENT` — real airlocks, hatches, chambers, thresholds, doors, decompression, or vacuum context may dominate without inventing a protagonist.

## SYSTEM_ALLEGORY focus subtypes

v4.3.1 currently distinguishes at least:

- `MEMORY_ARCHIVE` — memory/storage/retention/deletion/archive semantics dominate;
- `DISTRIBUTED_SWARM` — distributed/swarm/collective topology semantics dominate;
- `GENERIC_SYSTEM` — no specialized system focus has enough path-weighted evidence.

Focus scoring primarily uses semantic JSON paths and their weights. Loose mentions in secondary prose receive only small evidence. This prevents a memory-policy JSON from becoming a swarm picture merely because it mentions forwarding data to a peer.

### MEMORY_ARCHIVE visual grammar

Memory policy becomes one continuous painted record-river: recent ring -> long witness stream -> bright pinned rare-event knots -> archive. Ordinary old traces may fade only after useful information has moved onward; anomalies and significant episodes remain visible. Reconnection/archival debt can appear as a temporarily folded-back route that later reaches the archive. No personification is required.

### DISTRIBUTED_SWARM visual grammar

A swarm becomes unequal peer beacons scattered through one continuous mural environment, with selective signal ribbons across the same plaster field. No throne, monarch, central brain, rows, columns, medallion grid, or icon sheet is allowed.

## Continuous mural lock

Mandatory composition rules:

- one continuous asymmetric mural scene;
- one shared cracked plaster field across the full frame;
- irregular spacing and open painted space;
- no tiled layout, contact sheet, icon sheet, specimen board, sticker sheet, equal-cell matrix, or repeated medallions;
- system/architectural/object scenes render on a landscape `640x448` canvas;
- guidance scale is `7.5` to reduce over-constrained symmetric repetition.

## Ancient visual grammar

Mandatory positive grammar:

- cracked aged lime plaster across the full frame;
- mineral pigments, worn ochre, iron red, soot black, terre verte, faded blue;
- abrasion, age stains, pigment loss, irregular cracks and imperfect flat brushwork;
- visual subjects physically embedded in the painted wall.

Modern visual grammar is suppressed in positive and negative prompts: 3D/product/CAD renders, diagrams, flowcharts, infographics, UI, glossy machinery, floating objects, modern icon grids, and clean geometric posters.

Observed calibration failures remain explicit negative controls:

```text
FAIL__3D_MACHINE_COLLAPSE
FAIL__DIAGRAM_GEOMETRY_COLLAPSE
FAIL__TILED_ICON_GRID_COLLAPSE
FAIL__INCIDENTAL_TERM_SCENE_HIJACK
```

## Contract

- Source corpus: `registry/**/*.json` by default.
- JSON identity: `SHA-256(canonical_json)`.
- Equivalent content is rendered at most once regardless of filename/key order.
- Full scalar trace and semantic projection remain in the receipt for audit.
- `semantic_coverage_ratio = 1.0` means all nontechnical source semantics are traced/interpreted; it does not mean raw JSON is pasted into the image prompt.
- The generative prompt uses only a compact set of dominant semantic anchors and is hard-capped to the actual multi-chunk CLIP budget.
- `false_personification_guard = true`.
- `physical_gate_firewall = true`.
- `scene_focus_firewall = true`.
- `ancient_visual_grammar_lock = true`.
- `no_modern_visual_grammar = true`.
- `full_frame_plaster_surface = true`.
- `continuous_mural_lock = true`.
- `anti_grid_icon_collapse = true`.
- Rendering runs locally in GitHub Actions using Hugging Face Diffusers.
- Default model: `dreamlike-art/dreamlike-photoreal-2.0`.
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
    -> v4.3.1 path-weighted scene-focus inference
    -> compact ancient visual translation
    -> continuous mural composition lock
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

## Runtime defaults

```text
model               = dreamlike-art/dreamlike-photoreal-2.0
steps               = 20
human canvas        = 512x512
system canvas       = 640x448
guidance_scale      = 7.5
max_prompt_chunks   = 6
workflow render cap = 1 image/run
```

Generated frescoes are visualization artifacts only. They are never evidence, proof, or a replacement for the underlying registry record.
