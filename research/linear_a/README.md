# JANUS Linear A research pipeline

This directory contains the executable research code used by the JANUS Linear A program. It is intentionally separated from `data/`, which stores persistent, machine-readable registry state, results, decision history, claim ceilings, and roadmaps.

## Frozen source corpus

Primary execution currently freezes:

- repository: `mwenge/lineara.xyz`
- commit: `43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a`

No result may silently switch corpus versions. A new corpus version requires a new receipt and provenance record.

## Executable stages

### v0.1 — full-corpus blind structural analysis

File: `janus_linear_a_full_corpus.py`

Purpose:

- parse the frozen corpus;
- hash token identities before scoring;
- test token/suffix association with numeric behavior;
- run matched destructive nulls;
- keep scholarly meaning hidden until scoring is frozen.

### v0.2 — candidate-specific true held-out replication

File: `janus_linear_a_candidate_holdout.py`

Purpose:

- split documents deterministically into train/test;
- perform candidate discovery only on train;
- freeze candidate identity and effect direction before test;
- test only locked candidates on unseen documents.

### v0.3 — post-reveal survivor decomposition

File: `janus_linear_a_survivor_decomposition.py`

Purpose:

- audit whether statistical survivors are merely rediscoveries of known accounting/personnel structures;
- remove known `KU-RO`, `KI-RO`, `PO-TO-KU-RO` explanations from `RO`;
- verify Unicode/sign representation integrity for `VIR+[?]`;
- block novelty claims when a known explanation absorbs the signal.

### v0.4 — A100-102 versus VIR-family subtype audit

File: `janus_linear_a_vir_subtype.py`

Purpose:

- test whether `A100-102 / 𐙇` has a distinct quantitative profile relative to other VIR/personnel variants;
- preserve region structure in the permutation null;
- keep the claim ceiling at exploratory quantitative connection only.

### v0.5 — known-family-subtracted cross-region search

File: `janus_linear_a_known_subtracted.py`

Purpose:

- subtract already explained `VIR*`, `KU-RO`, `KI-RO`, `PO-TO-KU-RO`, and `RO` families before discovery;
- discover on HT only;
- replicate on non-HT regions;
- explicitly classify this as cross-region replication rather than pristine holdout because earlier stages touched the full corpus.

### v0.6 — record-boundary / formula-slot cross-region search

File: `janus_linear_a_record_role.py`

Purpose:

- move beyond raw numeric magnitude into structural/document roles;
- test `ROW_INITIAL`, `ROW_FINAL`, `PRE_NUMERIC`, `POST_NUMERIC`, `DOC_INITIAL`, `DOC_FINAL`, `NONNUMERIC_ONLY_ROW`, and `SOLE_TOKEN_ROW` roles;
- subtract previously explained `VIR*`, `KU-RO`, `KI-RO`, `PO-TO-KU-RO`, `RO`, and `GRA` families before scoring;
- use within-document anonymous-identity shuffling that preserves document membership, candidate counts, numeric slots, and row geometry;
- use max-T across candidate × role tests on HT and Bonferroni-controlled replication on non-HT.

## CI execution

Workflow: `.github/workflows/janus-linear-a-full-corpus.yml`

The workflow executes the frozen pipeline and uploads execution receipts under `artifacts/` as GitHub Actions artifacts. These CI artifacts are execution evidence, not the permanent research registry.

## Persistent registry layer

Persistent state belongs in `data/`.

Each registry state artifact should record, at minimum:

- code path and code commit;
- corpus repository and frozen corpus commit;
- GitHub Actions run ID and artifact digest when available;
- test family and null operator;
- selected candidates and post-reveal identity only after scoring;
- positive and negative gate outcomes;
- novelty/falsification classification;
- claim ceiling;
- next required falsification step;
- roadmap and blocked promotion conditions.

Negative results must be preserved. A failed null, failed replication, known-anchor rediscovery, or representation defect is part of the scientific state and must not be erased by later runs.

## Promotion gate

A genuinely new Linear A anchor requires:

`BLIND CANDIDATE → NULL SEPARATION → ≥2 PARTITIONS → HELD-OUT SUCCESS → BEHAVIORAL CONSTRAINT → MORPHOLOGICAL/LEXICAL CONSISTENCY`

A green CI job proves only that the declared computation completed and its receipt satisfied the programmed claim ceiling. It does not by itself establish a decipherment, new lexical value, or linguistic meaning.

## Planned next stages

The current high-value roadmap is:

1. complete and register v0.6 record-role execution;
2. if v0.6 produces survivors, run post-score novelty and alternative-segmentation audits before any semantic interpretation;
3. if v0.6 produces no survivor, move to formula-transition and neighborhood-role discovery rather than relaxing thresholds;
4. add a fresh transcription/parser source for genuinely independent replication;
5. run independent implementation replay;
6. only after a structural survivor clears those controls, test morphological families and competing lexical/grammatical explanations.
