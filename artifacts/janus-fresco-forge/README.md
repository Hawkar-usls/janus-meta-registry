# JANUS Fresco Forge artifacts

This directory is populated by `.github/workflows/janus-fresco-forge.yml`.

Generated layout:

```text
artifacts/janus-fresco-forge/
├── images/                # accepted canonical PNG frescoes
├── receipts/              # one provenance receipt per accepted image
├── calibration_failures/  # final failed attempt when v5.1 rejects visual collapse
└── ledger.jsonl           # append-only content-hash dedupe ledger
```

A JSON record is considered already rendered only when its canonical JSON SHA-256 appears in `ledger.jsonl` with `status = generated`. A `rejected_visual_collapse` row remains retryable on a later run.

## Active renderer

The active renderer is `modules/fresco_forge/v5_1_story_renderer.py`.

v5.1 keeps the `JANUS_MONUMENTAL_ALLEGORICAL_FRESCO` direction introduced by v5.0, but adds a mandatory monumental-density contract after the first v5 calibration output collapsed into an isolated emblem/still-life. Each story plan now requires a populated architectural world, foreground/middle-distance/background depth, multiple narrative groups, a minimum figure target, secondary scenes, full-frame composition and no reserved inscription zones.

The diffusion stage remains deliberately text-free: readable words, labels, inscriptions, code, pseudo-writing, banners and title strips are forbidden. Any future canonical typography must be added as a deterministic post-process rather than generated inside the image model.

v5.1 also adds a lightweight post-render visual complexity gate using PIL grayscale entropy, edge density, spatial concentration and empty-field heuristics. It explicitly does **not** claim OCR or person detection. Low-detail, empty-field or emblem-like outputs are retried with a denser composition and changed style/seed up to the configured attempt limit. If all attempts fail, the final candidate goes to `calibration_failures/` instead of the canonical `images/` gallery.

v5.0 and v4.x remain in the repository as frozen calibration history and negative controls for failures such as tiled/icon-grid collapse, technical-protocol objectification, pseudo-text, emblem collapse and low-detail abstract mural output.

Do not store `HF_TOKEN` or any other secret here.
