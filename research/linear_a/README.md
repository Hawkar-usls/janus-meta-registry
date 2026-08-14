# JANUS Linear A research pipeline

This directory contains the executable research code used by the JANUS Linear A program. It is intentionally separated from `data/`, which stores persistent, machine-readable registry state, immutable result summaries, failure audits, claim ceilings, and roadmaps.

## Current canonical state

Current persistent research state:

- `data/JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.0.json`

Current authoritative execution result:

- `data/JANUS-LINEAR-A-TYPED-TOKEN-CORRECTIVE-REPLAY-RESULT-2026-08-14-v0.6.2.json`

Historical execution receipts and failure audits are never deleted. New canonical states supersede them only for current inference.

## Frozen source corpus

Primary execution currently freezes:

- repository: `mwenge/lineara.xyz`
- commit: `43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a`
- numeric inventory: `items_analysis/numbers.txt`

No result may silently switch corpus versions. A new corpus version requires a new receipt and provenance record.

## Executable stages

### v0.1 — full-corpus blind structural analysis

File: `janus_linear_a_full_corpus.py`

Purpose:

- parse the frozen corpus;
- hash eligible token identities before scoring;
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

- test whether statistical survivors are merely rediscoveries of known accounting/personnel structures;
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

## Corrective representation policies

The v0.1-v0.6 algorithms remain preserved as historical code. Two later corrective policies replayed the full chain rather than silently rewriting earlier receipts.

### v0.6.1 — punctuation-aware parser policy

Files:

- `janus_linear_a_parser_policy_v0_6_1.py`
- `janus_linear_a_corrective_replay_v0_6_1.py`

Trigger:

- pre-filter v0.6 produced a highly significant cross-region `*900` record-role survivor;
- post-score identity reveal showed that `*900` maps to Aegean word-separator punctuation, not a semantic Linear A token.

Correction:

- remove `*900`, `*901`, `*902`, and `*903` before hashing, scoring, null generation, numeric adjacency, and row geometry;
- retain `*904`, which belongs to the Linear A sign repertoire in the frozen corpus.

Observed punctuation filtered in the frozen reading-spec data: 468 occurrences.

Permanent audit:

- `data/JANUS-LINEAR-A-PARSER-BOUNDARY-CANARY-AUDIT-2026-08-14-v1.0.json`

### v0.6.2 — typed-token candidate universe

Files:

- `janus_linear_a_token_typing_policy_v0_6_2.py`
- `janus_linear_a_corrective_replay_v0_6_2.py`

Trigger:

- after punctuation correction, `¹⁄₅` became the strongest v0.6.1 train structural candidate;
- the frozen corpus numeric inventory identifies `¹⁄₅` as numeric, proving that the legacy fraction parser had allowed a numeric literal into semantic candidate space.

Typed candidate classes:

- `PUNCTUATION`
- `NUMERIC_EXACT`
- `NUMERIC_APPROX_OR_UNCERTAIN`
- `SEMANTIC_CANDIDATE`

Only `SEMANTIC_CANDIDATE` may receive word/suffix identity hashes.

The v0.6.2 scan found 121 numeric-literal occurrences that the historical hard-coded fraction map had missed across four forms: `¹⁄₅`, `¹⁄₃`, `≈¹⁄₆`, and `≈¹⁄₄`.

Permanent audit:

- `data/JANUS-LINEAR-A-NUMERIC-LITERAL-TYPE-LEAK-AUDIT-2026-08-14-v1.0.json`

Authoritative typed replay:

- GitHub Actions run `31788159539`
- artifact digest `sha256:24b42bedf2caa82d5fe0475d9268be2e6a54711181d0c53c8aabcd447f18a506`

## Current scientific state after v0.6.2

The typed-token replay preserves the strongest known-structure controls while removing representation canaries:

- candidate-specific true held-out v0.2.2 still yields three statistical survivors: `VIR+[?]` as word, `VIR+[?]` as suffix, and suffix `RO`;
- post-reveal v0.3.2 blocks those survivors as new anchors because they resolve to known personnel/accounting structure or unresolved sign identity;
- v0.4.2 does not establish an A100-102 quantitative subtype;
- v0.5.2 produces zero new known-family-subtracted cross-region numeric survivors;
- v0.6.2 produces zero new record-role cross-region survivors.

Therefore:

- `NEW_ANCHOR_ESTABLISHED = false`
- `DECIPHERMENT_ESTABLISHED = false`
- current promotion = `BLOCKED`

## CI execution

Historical/full workflow:

- `.github/workflows/janus-linear-a-full-corpus.yml`

Corrective workflows:

- `.github/workflows/janus-linear-a-punctuation-corrective-replay.yml`
- `.github/workflows/janus-linear-a-typed-token-corrective-replay.yml`

GitHub Actions artifacts are execution evidence, not the permanent research registry. Permanent `data/` nodes store exact run IDs, head SHAs, artifact IDs/digests, scientific outcomes, and claim ceilings.

## Persistent registry layer

Persistent state belongs in `data/`.

Every substantial execution or correction should record, at minimum:

- code path and code commit;
- corpus repository and frozen corpus commit;
- GitHub Actions run ID and artifact digest;
- parser/token ontology version;
- test family and null operator;
- selected candidates and post-reveal identity only after scoring;
- positive and negative gate outcomes;
- novelty/falsification classification;
- claim ceiling;
- next required falsification step;
- roadmap and blocked promotion conditions.

Negative results must be preserved. A failed null, failed replication, known-anchor rediscovery, parser/type defect, or representation failure is part of the scientific state and must not be erased by later runs.

## Promotion gate

A genuinely new Linear A anchor requires:

`TYPED CANDIDATE UNIVERSE → BLIND CANDIDATE → NULL SEPARATION → ≥2 PARTITIONS → HELD-OUT SUCCESS → BEHAVIORAL CONSTRAINT → MORPHOLOGICAL/LEXICAL CONSISTENCY`

A green CI job proves only that the declared computation completed and its receipt satisfied the programmed claim ceiling. It does not by itself establish a decipherment, new lexical value, or linguistic meaning.

## Roadmap

Canonical roadmap is maintained in `data/JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.0.json`.

Current sequence:

1. **R0 — DONE:** freeze `JANUS-LINA-TOKEN-TYPING-POLICY-v0.6.2` as mandatory ontology before blind scoring.
2. **R1 — NEXT:** v0.7 formula-transition / directed predecessor-successor / semantic-neighborhood discovery using HT-only discovery and non-HT cross-region replication.
3. **R2:** alternative segmentation replay for any survivor.
4. **R3:** fresh independently curated transcription/parser source for genuinely external replication.
5. **R4:** independent implementation replay.
6. **R5:** morphology/lexical competition only after a structural survivor clears the above controls.
7. **R6:** decipherment remains blocked until multiple independently replicated anchors and grammar-level predictive success exist.

For v0.7, semantic reveal remains forbidden until candidate relation, direction, null family, and replication test have been frozen.
