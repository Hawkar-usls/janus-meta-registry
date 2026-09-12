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

Do not store `HF_TOKEN` or any other secret here.
