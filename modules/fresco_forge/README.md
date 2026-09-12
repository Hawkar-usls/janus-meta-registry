# JANUS Fresco Forge

`JANUS Fresco Forge` is a content-addressed `JSON -> fresco` pipeline for the JANUS meta-registry.

## Current renderer: v4.1 Semantic Role Firewall

v4.1 fixes `NAME_COLLISION -> FALSE_PERSONIFICATION`.

The visual compiler is now explicitly staged:

```text
field role -> entity type -> scene archetype -> visual translation
```

A name is not a person merely because it resembles a mythic/person name. Fields such as `internal_name`, `protocol_name`, `repository`, `branch`, `path`, `gate`, `adapter`, `controller`, `state_machine`, `mapping`, and other system/provenance fields are never allowed to create a human or deity by name alone.

A person or mythic figure requires explicit role evidence: a person/actor/character/deity field or descriptive narrative that actually establishes a human/mythic entity.

## Scene archetypes

The renderer chooses the visual grammar before composing the prompt:

- `HUMAN_NARRATIVE` — explicit human actors dominate.
- `MYTHIC_NARRATIVE` — explicit mythic/deity entities dominate.
- `OBJECT_RITUAL` — a real object/artifact/ritual is central.
- `SYSTEM_ALLEGORY` — system mechanics become non-human visual mechanisms.
- `ARCHITECTURAL_EVENT` — gates, chambers, airlocks, thresholds and transitions may be the central scene without inventing a protagonist.

For example, a JSON containing `UNDINA_TIMESHIFT_AIRLOCK` as an `internal_name` is treated as a system identifier. It does not imply a water-spirit woman. If the source is about an airlock protocol, the visual translation is an airlock/chamber event unless the JSON separately establishes a real mythic character.

## Contract

- Source corpus: `registry/**/*.json` by default.
- JSON is canonicalized and identified by `SHA-256(canonical_json)`.
- Equivalent JSON content is rendered at most once regardless of filename/key order.
- The complete canonical JSON remains the source of identity/provenance.
- Full scalar trace and semantic projection are preserved for audit.
- `semantic_coverage_ratio = 1.0` means the semantic record is traced/interpreted; it does **not** mean every scalar is pasted literally into the generative prompt.
- v4.1 stores a field-role audit and chosen scene archetype in every receipt.
- Structural/technical names stay mechanisms/provenance unless explicit person evidence exists.
- Prompt length is hard-capped to the actual multi-chunk CLIP budget; the recorded prompt cannot exceed the model budget silently.
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
    -> visual translation
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
guidance_scale     = 8.0
max_prompt_chunks  = 6
workflow render cap= 1 image/run
```

## Receipt v4.1

Every successful render records:

- source path and canonical JSON SHA-256;
- full semantic projection/scalar trace;
- `semantic_coverage_ratio`;
- field-role audit and role counts;
- chosen `scene_archetype` and archetype scores;
- `false_personification_guard = true`;
- semantic scene plan;
- final hard-capped prompt and negative prompt;
- prompt token/chunk counts and truncation flag;
- model/backend/device/scheduler;
- steps, dimensions, guidance scale, seed and elapsed time;
- image path and image SHA-256.

Generated frescoes are visualization artifacts only. They are never evidence, proof, or a replacement for the underlying registry record.
