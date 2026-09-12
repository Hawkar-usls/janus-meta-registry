# JANUS Fresco Forge

`JANUS Fresco Forge` is a content-addressed `JSON -> prompt -> image` pipeline for the JANUS meta-registry.

## Contract

- Source corpus: `registry/**/*.json` by default.
- JSON is parsed and serialized into a canonical form (`sort_keys=True`, compact UTF-8 JSON).
- Identity is `SHA-256(canonical_json)`, not the filename.
- The same semantic JSON content is therefore rendered at most once even if it is renamed or copied.
- The canonical JSON is embedded directly in the image prompt as the semantic source of truth.
- Rendering is performed through Hugging Face `InferenceClient.text_to_image`.
- Default model: `black-forest-labs/FLUX.1-schnell`.
- Default provider: `auto`.
- Images are stored under `artifacts/janus-fresco-forge/images/`.
- Per-image provenance receipts are stored under `artifacts/janus-fresco-forge/receipts/`.
- The append-only dedupe ledger is `artifacts/janus-fresco-forge/ledger.jsonl`.

## GitHub Actions

Workflow: `.github/workflows/janus-fresco-forge.yml`

Triggers:

- every push to `main` that changes `registry/**/*.json`;
- scheduled backlog sweep every 6 hours;
- manual `workflow_dispatch` with a configurable `max_images` budget.

Automatic push runs render at most one new unique JSON. Scheduled runs render at most three. This protects inference credits while the historical registry backlog is being consumed.

## Required secret

Create a repository Actions secret named:

```text
HF_TOKEN
```

The token must be authorized for Hugging Face Inference Providers. Never commit the token to the repository.

## Local discovery test

No token or network call is made in dry-run mode:

```bash
python modules/fresco_forge/forge.py --dry-run --max-images 5
```

## Render one exact registry record

```bash
HF_TOKEN=... python modules/fresco_forge/forge.py \
  --source registry/EXAMPLE.json \
  --max-images 1
```

## Change model/provider

Use environment variables without changing the dedupe identity:

```bash
FRESCO_MODEL=black-forest-labs/FLUX.1-schnell \
FRESCO_PROVIDER=auto \
HF_TOKEN=... \
python modules/fresco_forge/forge.py
```

Changing the model does **not** intentionally regenerate already-ledgered JSON. If model-version rerenders are desired later, add an explicit rerender ledger/version policy rather than weakening the no-repeat invariant.
