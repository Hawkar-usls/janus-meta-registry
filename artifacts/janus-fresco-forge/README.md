# JANUS Fresco Forge artifacts

This directory is populated by `.github/workflows/janus-fresco-forge.yml`.

Generated layout:

```text
artifacts/janus-fresco-forge/
├── images/       # generated PNG frescoes
├── receipts/     # one provenance receipt per image
└── ledger.jsonl  # append-only content-hash dedupe ledger
```

A JSON record is considered already rendered when its canonical JSON SHA-256 appears in `ledger.jsonl` with `status = generated`.

## Active renderer

The active renderer is `modules/fresco_forge/v5_story_renderer.py`.

v5 uses the `JANUS_MONUMENTAL_ALLEGORICAL_FRESCO` art direction: canonical JSON is first passed through the existing semantic-role and epistemic firewalls, then translated into a dense narrative allegory with a strong central subject, many secondary story moments, layered architecture, symbolic objects, old-master material detail and anti-repeat scene/style metadata.

The diffusion stage is deliberately text-free: readable words, labels, inscriptions, code and pseudo-writing are forbidden. Any future canonical typography must be added as a deterministic post-process rather than generated inside the image model.

v4.x renderers remain in the repository as frozen calibration history and negative controls for failures such as tiled/icon-grid collapse, technical-protocol objectification and low-detail abstract mural output.

Do not store `HF_TOKEN` or any other secret here.
