# JANUS Linear A research pipeline

This directory contains the executable research code used by the JANUS Linear A program. It is intentionally separated from `data/`, which stores persistent, machine-readable registry state, immutable result summaries, failure audits, claim ceilings, and roadmaps.

## Current canonical state

Current persistent research state:

- `data/JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.1.json`

Current representation baseline:

- `data/JANUS-LINEAR-A-TYPED-TOKEN-CORRECTIVE-REPLAY-RESULT-2026-08-14-v0.6.2.json`

Latest relation-level execution result:

- `data/JANUS-LINEAR-A-FORMULA-TRANSITION-NEIGHBORHOOD-RESULT-2026-08-14-v0.7.json`

Historical execution receipts and failure audits are never deleted. New canonical states supersede them only for current inference.

## Frozen source corpus

Primary execution currently freezes:

- repository: `mwenge/lineara.xyz`
- commit: `43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a`
- `LinearAInscriptions.js` blob: `ef41c58802a3135f295072ba60fc0df39450a10c`
- numeric inventory: `items_analysis/numbers.txt`
- numeric inventory blob: `a17b8922297795a90ea6761f32f6ea020b733a6d`

No result may silently switch corpus versions. A new corpus version requires a new receipt and provenance record.

## Executable stages

### v0.1 — full-corpus blind structural analysis

File: `janus_linear_a_full_corpus.py`

Parses the frozen corpus, hashes eligible identities before scoring, tests token/suffix association with numeric behavior, runs destructive nulls, and delays semantic reveal until scoring is frozen.

### v0.2 — candidate-specific true held-out replication

File: `janus_linear_a_candidate_holdout.py`

Separates train-only discovery from locked unseen-document testing. This stage remains an important infrastructure control because it successfully rediscovers known personnel/accounting structure without making a novelty claim.

### v0.3 — post-reveal survivor decomposition

File: `janus_linear_a_survivor_decomposition.py`

Tests whether statistical survivors are already explained by known accounting/personnel structures and blocks novelty when a known explanation absorbs the signal.

### v0.4 — A100-102 versus VIR-family subtype audit

File: `janus_linear_a_vir_subtype.py`

Tests a predeclared quantitative subtype hypothesis under region-preserving nulls. The hypothesis did not pass its predeclared gate.

### v0.5 — known-family-subtracted cross-region numeric search

File: `janus_linear_a_known_subtracted.py`

Removes already explained dominant families before HT discovery and non-HT cross-region replication. No novel cross-region numeric survivor remained after the typed corrective replay.

### v0.6 — record-boundary / formula-slot cross-region search

File: `janus_linear_a_record_role.py`

Tests row/document roles such as `ROW_INITIAL`, `ROW_FINAL`, `PRE_NUMERIC`, `POST_NUMERIC`, `DOC_INITIAL`, `DOC_FINAL`, `NONNUMERIC_ONLY_ROW`, and `SOLE_TOKEN_ROW` with within-document identity shuffling. No novel record-role survivor remained after typed cleanup.

## Corrective representation policies

The v0.1-v0.6 algorithms remain preserved as historical code. Corrective policies replayed the full chain rather than silently rewriting earlier receipts.

### v0.6.1 — punctuation-aware parser policy

Files:

- `janus_linear_a_parser_policy_v0_6_1.py`
- `janus_linear_a_corrective_replay_v0_6_1.py`

Trigger: a highly significant `*900` record-role survivor was revealed to be Aegean punctuation rather than a semantic token.

Correction: exclude `*900`, `*901`, `*902`, and `*903` before hashing, scoring, null generation, numeric adjacency, and row geometry while retaining `*904`, which belongs to the Linear A sign repertoire.

Permanent audit:

- `data/JANUS-LINEAR-A-PARSER-BOUNDARY-CANARY-AUDIT-2026-08-14-v1.0.json`

### v0.6.2 — typed-token candidate universe

Files:

- `janus_linear_a_token_typing_policy_v0_6_2.py`
- `janus_linear_a_corrective_replay_v0_6_2.py`

Trigger: after punctuation correction, `¹⁄₅` became a top structural candidate even though the frozen numeric inventory identifies it as a numeral.

Typed classes:

- `PUNCTUATION`
- `NUMERIC_EXACT`
- `NUMERIC_APPROX_OR_UNCERTAIN`
- `SEMANTIC_CANDIDATE`

Only `SEMANTIC_CANDIDATE` may receive semantic identity hashes. The corrective scan found 121 previously missed numeric-literal occurrences across `¹⁄₅`, `¹⁄₃`, `≈¹⁄₆`, and `≈¹⁄₄`.

Permanent audit:

- `data/JANUS-LINEAR-A-NUMERIC-LITERAL-TYPE-LEAK-AUDIT-2026-08-14-v1.0.json`

Authoritative typed replay:

- GitHub Actions run `31788159539`
- artifact digest `sha256:24b42bedf2caa82d5fe0475d9268be2e6a54711181d0c53c8aabcd447f18a506`

## v0.7 — formula-transition / neighborhood-role discovery

File: `janus_linear_a_formula_transition_v0_7.py`

Workflow:

- `.github/workflows/janus-linear-a-formula-transition-v0-7.yml`

Purpose:

- move from single-token role tests to local relation tests;
- test `TT` directed adjacency and `T-N-T` semantic-token / numeric-slot / semantic-token motifs;
- use `HT_SCREEN → HT_CONFIRM → NON_HT_REPLICATION` rather than one HT partition for both generation and confirmation;
- run a `CONTROL_INCLUDED` channel and a `NOVELTY_MASKED` channel;
- preserve known-family positions as fixed `MASK` geometry rather than deleting them and creating artificial adjacency;
- use `WITHIN_DOCUMENT_SEMANTIC_IDENTITY_SHUFFLE`, preserving document-local marginals and token-type geometry while destroying identity↔neighborhood coupling;
- reveal semantic labels only after scoring.

Execution:

- GitHub Actions run `31789138925`
- artifact ID `9214757238`
- artifact digest `sha256:d6587a682f561cd42d4badc7b54899a2c144ebc4759b14e8f3b353eefb0a4ef2`
- workflow conclusion: `success`

Result:

- control screen: 3 selected motifs;
- control independent HT confirmation: 1 survivor, `SA·RA₂ → GRA`, Bonferroni `p ≈ 0.00080`;
- that survivor was **not evaluable** in non-HT under the frozen minimum occurrence/document/region gate, so this is not classified as a failed replication p-value;
- novelty-masked screen: 0 eligible motifs after the frozen `VIR* / KU-RO / KI-RO / PO-TO-KU-RO / GRA` mask;
- novelty-masked confirmation/replication: 0 survivors.

Scientific classification:

- `VALID_NEGATIVE_FOR_TESTED_LOCAL_TT_TNT_ONTOLOGY`
- `NEW_ANCHOR_ESTABLISHED = false`
- `DECIPHERMENT_ESTABLISHED = false`
- promotion remains `BLOCKED`.

Permanent result:

- `data/JANUS-LINEAR-A-FORMULA-TRANSITION-NEIGHBORHOOD-RESULT-2026-08-14-v0.7.json`

## Current scientific state

The strongest admissible state is deliberately narrower than decipherment:

- known personnel/accounting structure can be rediscovered under blind and held-out controls;
- parser punctuation and numeric-literal canaries have been identified and corrected through full replays;
- no novel numeric, record-role, or local `TT/TNT` formula survivor currently clears the declared gates;
- one known-control adjacency motif is confirmed across two HT partitions but lacks sufficient non-HT support for evaluation;
- no new lexical anchor is established;
- no decipherment claim is admissible.

## CI execution

Historical/full workflow:

- `.github/workflows/janus-linear-a-full-corpus.yml`

Corrective workflows:

- `.github/workflows/janus-linear-a-punctuation-corrective-replay.yml`
- `.github/workflows/janus-linear-a-typed-token-corrective-replay.yml`

Relation workflow:

- `.github/workflows/janus-linear-a-formula-transition-v0-7.yml`

GitHub Actions artifacts are execution evidence, not the permanent research registry. Permanent `data/` nodes store exact run IDs, head SHAs, artifact IDs/digests, scientific outcomes, and claim ceilings.

## Persistent registry layer

Every substantial execution or correction should record, at minimum:

- code path and code commit;
- corpus repository and frozen corpus commit;
- GitHub Actions run ID and artifact digest;
- parser/token ontology version;
- test family and null operator;
- partition discipline;
- selected candidates and post-reveal identity only after scoring;
- positive, negative, failed, and non-evaluable gate outcomes separately;
- novelty/falsification classification;
- claim ceiling;
- next required falsification step;
- roadmap and blocked promotion conditions.

Negative results must be preserved. A failed null, failed replication, non-evaluable replication, known-anchor rediscovery, parser/type defect, or representation failure is part of the scientific state and must not be erased by later runs.

## Promotion gate

A genuinely new Linear A anchor requires:

`TYPED CANDIDATE UNIVERSE → BLIND CANDIDATE/RELATION → RELATION-DESTROYING NULL → INDEPENDENT CONFIRMATION → CROSS-PARTITION REPLICATION → BEHAVIORAL CONSTRAINT → MORPHOLOGICAL/LEXICAL CONSISTENCY → INDEPENDENT TRANSCRIPTION/PARSER → INDEPENDENT IMPLEMENTATION`

A green CI job proves only that the declared computation completed and its receipt satisfied the programmed claim ceiling. It does not by itself establish a decipherment, new lexical value, or linguistic meaning.

## Roadmap

Canonical roadmap is maintained in:

- `data/JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.1.json`

Current sequence:

1. **R0 — DONE:** typed candidate ontology v0.6.2.
2. **R1 — DONE / VALID NEGATIVE:** v0.7 local `TT/TNT` formula-transition discovery.
3. **R2 — NEXT:** v0.8 longer formula neighborhoods and numeric-bucket-conditioned motifs, with no lowering of v0.7 error-control thresholds.
4. **R3 — BLOCKING EXTERNAL REPLICATION CLAIM:** independent transcription/parser source.
5. **R4 — BLOCKING PROMOTION BEYOND STRUCTURAL CANDIDATE:** independent implementation replay.
6. **R5 — BLOCKED:** behavioral, morphology, alternative-segmentation, and lexical competition until a replicated structural survivor exists.
7. **R6 — BLOCKED:** decipherment until multiple independently replicated lexical anchors and grammar-level predictive success exist.

For v0.8, semantic reveal remains forbidden until motif ontology, numeric buckets, relation direction, null family, selection thresholds, and replication tests have been frozen.
