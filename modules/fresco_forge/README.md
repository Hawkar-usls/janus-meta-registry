# JANUS Fresco Forge

`JANUS Fresco Forge` is a content-addressed `JSON -> fresco` pipeline for the JANUS meta-registry.

## Contract

- Source corpus: `registry/**/*.json` by default.
- JSON is parsed and serialized into a canonical form (`sort_keys=True`, compact UTF-8 JSON).
- Identity is `SHA-256(canonical_json)`, not the filename.
- Equivalent JSON content is rendered at most once even if renamed, copied, or key order changes.
- The complete canonical JSON defines identity/provenance.
- A deterministic JSON-shaped visual projection is built from the record and used directly as the image prompt payload so oversized records do not become meaningless tokenizer truncation.
- Rendering runs locally inside GitHub Actions with Hugging Face Diffusers.
- Default model: `dreamlike-art/dreamlike-photoreal-2.0`.
- Scheduler: `DPMSolverMultistepScheduler`.
- No Hugging Face hosted-inference token is required for the public default model.
- Images: `artifacts/janus-fresco-forge/images/`.
- Receipts: `artifacts/janus-fresco-forge/receipts/`.
- Dedupe ledger: `artifacts/janus-fresco-forge/ledger.jsonl`.

## GitHub Actions

Workflow: `.github/workflows/janus-fresco-forge.yml`

Triggers:

- push to `main` changing `registry/**/*.json`;
- scheduled backlog sweep every 6 hours;
- manual `workflow_dispatch`.

The hosted GitHub job is CPU-only, so v2 intentionally caps a workflow run at **one image**. This prevents a manual value such as `10` from accidentally starting ten heavy Stable Diffusion renders in one runner.

The Hugging Face model cache is persisted with `actions/cache`, so after the first successful model download later runs should avoid re-downloading the full model when the cache is available.

## No `HF_TOKEN` required

v1 used Hugging Face Hosted Inference and therefore required the repository secret `HF_TOKEN`.

v2 uses the same style of local Diffusers generation as the historical JANUS generator:

```python
StableDiffusionPipeline.from_pretrained("dreamlike-art/dreamlike-photoreal-2.0")
```

The public model is downloaded to the runner and executed locally. A token is not part of the normal generation path.

## Dry-run

Discovery and dedupe without loading Stable Diffusion:

```bash
python modules/fresco_forge/forge.py --dry-run --max-images 5
```

## Render one exact registry record locally

```bash
python modules/fresco_forge/forge.py \
  --source registry/EXAMPLE.json \
  --max-images 1
```

## Runtime defaults

```text
model  = dreamlike-art/dreamlike-photoreal-2.0
steps  = 20
width  = 512
height = 512
```

These are CPU-safe GitHub defaults rather than maximum-quality workstation settings. A future GPU runner can increase resolution and steps without weakening the content-addressed no-repeat invariant.

## Provenance receipt

Every successful render records:

- source path and full canonical JSON SHA-256;
- visual-projection and final prompt SHA-256;
- model and local backend;
- device and scheduler;
- step count, image dimensions and random seed;
- elapsed generation time;
- image path and SHA-256.

Changing rendering parameters does not automatically regenerate a JSON already present in the ledger. Rerender/version semantics should be explicit rather than weakening dedupe.
