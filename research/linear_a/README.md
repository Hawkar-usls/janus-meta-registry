# JANUS Linear A research pipeline

This directory contains the executable research code used by the JANUS Linear A program. It is intentionally separated from `data/`, which stores persistent machine-readable specifications, immutable result summaries, falsification audits, reconciliations, claim ceilings, canonical state, and roadmaps.

## Current canonical state

Current recovery/source-of-truth node:

- `data/JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.2.json`

Current representation baseline:

- `data/JANUS-LINEAR-A-TYPED-TOKEN-CORRECTIVE-REPLAY-RESULT-2026-08-14-v0.6.2.json`

v0.7 reconciliation:

- `data/JANUS-LINEAR-A-V0.7-DUAL-IMPLEMENTATION-RECONCILIATION-2026-08-14-v1.0.json`

Historical states and receipts are never deleted. New canonical states supersede them only for current inference.

## Repository layout

- `research/linear_a/` — executable parsers, statistical runners, null operators, corrective replay code, and independent implementations.
- `data/` — frozen execution specifications, immutable results, failure audits, reconciliation nodes, canonical state, machine-readable roadmaps, and Connection candidates.
- `.github/workflows/` — actual execution wiring; GitHub Actions artifacts are receipts, not the permanent scientific registry.

## Frozen source corpus

Primary execution freezes:

- repository: `mwenge/lineara.xyz`
- commit: `43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a`
- `LinearAInscriptions.js` blob: `ef41c58802a3135f295072ba60fc0df39450a10c`
- numeric inventory: `items_analysis/numbers.txt`
- numeric inventory blob: `a17b8922297795a90ea6761f32f6ea020b733a6d`

No result may silently switch corpus versions.

## Historical analysis stages

### v0.1 — blind full-corpus structural analysis

`janus_linear_a_full_corpus.py`

### v0.2 — candidate-specific true held-out replication

`janus_linear_a_candidate_holdout.py`

### v0.3 — post-reveal survivor decomposition

`janus_linear_a_survivor_decomposition.py`

### v0.4 — A100-102 / VIR-family quantitative subtype audit

`janus_linear_a_vir_subtype.py`

### v0.5 — known-family-subtracted cross-region numeric search

`janus_linear_a_known_subtracted.py`

### v0.6 — record-boundary / formula-slot cross-region search

`janus_linear_a_record_role.py`

These historical runners remain preserved even when later representation corrections supersede their pre-correction receipts for current inference.

## Representation corrections

### v0.6.1 — punctuation boundary policy

Files:

- `janus_linear_a_parser_policy_v0_6_1.py`
- `janus_linear_a_corrective_replay_v0_6_1.py`

Trigger: a statistically strong `*900` record-role survivor was revealed to be Aegean word-separator punctuation rather than a semantic Linear A token.

Correction: `*900`, `*901`, `*902`, and `*903` are excluded before hashing, scoring, null generation, numeric adjacency, and row geometry. Historical receipts remain preserved.

Audit:

- `data/JANUS-LINEAR-A-PARSER-BOUNDARY-CANARY-AUDIT-2026-08-14-v1.0.json`

### v0.6.2 — typed-token semantic candidate universe

Files:

- `janus_linear_a_token_typing_policy_v0_6_2.py`
- `janus_linear_a_corrective_replay_v0_6_2.py`

Typed classes:

- `PUNCTUATION`
- `NUMERIC_EXACT`
- `NUMERIC_APPROX_OR_UNCERTAIN`
- `SEMANTIC_CANDIDATE`

Only `SEMANTIC_CANDIDATE` may receive semantic word/suffix identity hashes. The corrective scan found 121 numeric-literal occurrences missed by the historical hard-coded fraction map across `¹⁄₅`, `¹⁄₃`, `≈¹⁄₆`, and `≈¹⁄₄`.

Audit:

- `data/JANUS-LINEAR-A-NUMERIC-LITERAL-TYPE-LEAK-AUDIT-2026-08-14-v1.0.json`

Authoritative typed replay:

- run `31788159539`
- artifact digest `sha256:24b42bedf2caa82d5fe0475d9268be2e6a54711181d0c53c8aabcd447f18a506`

Current representation-level conclusion:

- known personnel/accounting controls remain recoverable after cleanup;
- no novel numeric or record-role cross-region survivor remains;
- `NEW_ANCHOR_ESTABLISHED = false`;
- `DECIPHERMENT_ESTABLISHED = false`.

## v0.7 — dual independent local-relation implementations

Two materially different v0.7 implementations now coexist intentionally. Neither is deleted or silently privileged. Their relationship is recorded in:

- `data/JANUS-LINEAR-A-V0.7-DUAL-IMPLEMENTATION-RECONCILIATION-2026-08-14-v1.0.json`

### v0.7 implementation A — screen/confirm + MASK geometry

Runner:

- `janus_linear_a_formula_transition_v0_7.py`

Workflow:

- `.github/workflows/janus-linear-a-formula-transition-v0-7.yml`

Method:

- local `TT` and `T-N-T` motifs;
- deterministic `HT_SCREEN → HT_CONFIRM → NON_HT_REPLICATION`;
- `CONTROL_INCLUDED` and `NOVELTY_MASKED` channels;
- known `VIR* / KU-RO / KI-RO / PO-TO-KU-RO / GRA` positions are preserved as fixed `MASK` geometry in the novelty channel;
- within-document semantic identity shuffle;
- Bonferroni on confirmation and replication;
- semantic reveal only after scoring.

Execution:

- run `31789138925`
- artifact digest `sha256:d6587a682f561cd42d4badc7b54899a2c144ebc4759b14e8f3b353eefb0a4ef2`

Result:

- known-control `SA·RA₂ → GRA` confirms across two disjoint HT partitions (`p_Bonf ≈ 0.00080`);
- it is not evaluable in non-HT under frozen support minima;
- novelty-masked channel has zero screen-eligible local `TT/TNT` motifs;
- no novel cross-region survivor.

Permanent result:

- `data/JANUS-LINEAR-A-FORMULA-TRANSITION-NEIGHBORHOOD-RESULT-2026-08-14-v0.7.json`

### v0.7 implementation B — word-only triple-null max-T

Runner:

- `janus_linear_a_formula_transition.py`

Workflow:

- `.github/workflows/janus-linear-a-formula-transition-v0.7.yml`

Frozen spec:

- `data/JANUS-LINEAR-A-FORMULA-TRANSITION-EXECUTION-SPEC-2026-08-14-v0.7.json`

Method:

- `WORD_ONLY` semantic representation;
- six directed relation templates: `ADJACENT_TT`, `NUMERIC_BRIDGE_TNT`, `PRE_NUMERIC_BIGRAM_TTN`, `POST_NUMERIC_BIGRAM_NTT`, `ROW_PREFIX_TT`, `ROW_SUFFIX_TT`;
- HT discovery, non-HT replication only after locked selection;
- three destructive nulls: within-row identity shuffle, within-document identity shuffle, and predecessor/successor endpoint rewire;
- max-T family-wise discovery control under all three nulls;
- semantic reveal only after discovery/replication state is frozen.

Execution:

- run `31789134447`
- artifact digest `sha256:106ce6f79633504e3c4913fea98497191a04465dc865ca39991a422fbbcad92f`

Result:

- 27 HT-eligible semantic endpoints;
- 79 scored nonzero directed hypotheses;
- 0 pass all three max-T nulls;
- 0 locked for non-HT replication;
- no novel cross-region survivor.

Permanent result:

- `data/JANUS-LINEAR-A-FORMULA-TRANSITION-RESULT-2026-08-14-v0.7.json`

### Reconciled v0.7 conclusion

The implementations disagree at the intermediate candidate level because they intentionally use different hypothesis families, partitions, known-control geometry, null models, and multiplicity rules. They agree at the claim ceiling:

- `NO_NOVEL_V0_7_CROSS_REGION_SURVIVOR`
- `NEW_ANCHOR_ESTABLISHED = false`
- `DECIPHERMENT_ESTABLISHED = false`

This is **implementation-level convergence on a negative novelty conclusion**, not external replication, because both consume the same frozen transcription corpus.

## Current promotion gate

A new anchor requires:

`TYPED CANDIDATE UNIVERSE → BLIND CANDIDATE/RELATION → RELATION-DESTROYING NULL SEPARATION → INDEPENDENT INTERNAL CONFIRMATION → CROSS-PARTITION REPLICATION → BEHAVIORAL CONSTRAINT → MORPHOLOGICAL/LEXICAL CONSISTENCY → INDEPENDENT TRANSCRIPTION/PARSER → INDEPENDENT IMPLEMENTATION`

A green CI job proves only that the declared computation completed under its programmed claim ceiling.

## Persistent evidence discipline

Every substantial experiment should have:

1. executable code in `research/linear_a/`;
2. a frozen execution spec in `data/` before claim-bearing execution when feasible;
3. an actual CI run and artifact digest;
4. an immutable result JSON in `data/`;
5. explicit separation of PASS, FAIL, NOT_EVALUABLE, KNOWN_CONTROL, REPRESENTATION_FAILURE, and NO_PROMOTION;
6. a canonical-state update only after result verification;
7. a roadmap branch that was declared independently of the observed semantic label whenever possible.

Negative results and representation failures are scientific state, not cleanup noise.

## Roadmap from canonical v2.2

Canonical roadmap:

- `data/JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.2.json`

Current sequence:

1. **R0 — DONE:** typed candidate ontology v0.6.2.
2. **R1 — DONE / RECONCILED NEGATIVE:** dual v0.7 local relation implementations; no novel cross-region survivor.
3. **R2 — NEXT:** v0.8 higher-order typed neighborhoods / formula specialization.
4. **R3 — BLOCKING EXTERNAL REPLICATION CLAIM:** independent transcription/parser source.
5. **R4 — REQUIRED FOR FUTURE POSITIVE SURVIVOR:** independent implementation replay.
6. **R5 — BLOCKED:** behavioral, alternative-segmentation, morphology, and lexical competition until a replicated structural survivor exists.
7. **R6 — BLOCKED:** decipherment claim.

### v0.8 design contract

v0.8 must inherit the strongest controls from both v0.7 implementations:

- disjoint `HT_SCREEN → HT_CONFIRM → NON_HT` partitions;
- known controls preserved as fixed `MASK` geometry where deletion would fabricate adjacency;
- `WORD_ONLY` primary semantic representation;
- higher-order targets tested uniformly, not selected from v0.7 near-signals;
- complementary structure-preserving nulls, including row/document shuffles and graph/template endpoint rewiring;
- max-T or equivalent family-wise discovery control;
- post-score semantic reveal;
- explicit `NOT_EVALUABLE` versus `FAILED_REPLICATION` semantics;
- no threshold relaxation because v0.7 was negative.

Predeclared v0.8 target families should include:

- directed `T-T-T` trigrams;
- `T-N(bucket)-T` motifs with frozen numeric buckets;
- MASK-aware row-boundary predecessor/successor signatures;
- candidate-level in-neighbor/out-neighbor specialization.
