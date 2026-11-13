# SAT_REPRODUCIBILITY_001 — falsifiable 3-SAT historical replay

**Status: DRAFT_NOT_FROZEN / no benchmark executed / no scientific claim admitted.**

Canonical machine-readable plan: [`data/sat_reproducibility/SAT_REPRODUCIBILITY_001.json`](../data/sat_reproducibility/SAT_REPRODUCIBILITY_001.json).

## Why this lane exists

An earlier engineering description of Janus-Demiurge claimed successes on random 3-SAT with **220, 225, 230, 235, 240 variables** on a consumer PC. There is **no verified source-bound public bundle** in this dossier containing the alleged original CNFs, seeds, proof/checking logs, solver binary and environment. Treat the claim as historical and **unverified**, not as already measured superiority. A new solver successfully solving similar-sized instances does not retroactively authenticate the old observations.

The recovered [NAS early-cores manifest](https://github.com/Hawkar-usls/Janus-Demiurge/blob/main/archaeology/nas_early_cores_20261031/README.md) anchors an original `janus_nas/microgpt.py` (NAS SHA-256 `10b7d4fbb1a498cf6c8ac30915059106b8eccc0b480d7f2098f3b6687170f0cd`). It is **reference-only**: not evidence that microgpt was used to solve these SAT instances, not production code, and its old pickle formats must **never be loaded**. Modern Demiurge's 17 Scout control-plane and Native Model progress are different questions.

Do not mix this SAT lane with Rowan P0.2, FULL autonomy, model champion promotion or any paid compute.

## Historical negative-evidence checkpoint (read-only)

The source-bound [Yaksa E-drive audit](../data/sat_reproducibility/HISTORICAL_SOURCE_AUDIT_20261101.json) records **100 actual `sat_duels.jsonl` rounds, from 9 to 108 variables** (100/100 lines read), alongside `sat_state.json` ending at 108 variables. Original file SHA-256 digests are in the audit; original files have not been copied or mutated.

The duel rows summarize agent competition (35 `speed`, 28 `draw`, 22 `solved`, 15 `max_sat`) and do **not** provide original CNFs, seeds or verified SAT assignments. They cannot substantiate a 220–240-variable benchmark. The local `experimental_sat_profile.py` describes assignment-occupancy profiling, and `janus_solver_integrated.py` describes a subset-sum experiment rather than a verified large random-3-SAT replay.

**Scope:** targeted inspection of the named files and a recursive name-filtered E-drive inventory, not a complete NAS/archive search or proof of historical nonexistence. This scoped failure to verify is preserved as a first-class negative finding.

## Pre-experiment experimental strata

A *proposed*, **not yet power-validated** 3-CNF design uses five variable sizes × three clause densities.

| Number of variables | Density m/n | L1 (open) | L2 (hidden) | L3 (independently hidden) |
| ---: | ---: | ---: | ---: | ---: |
| 220, 225, 230, 235, 240 (each) | 4.0, 4.267, 4.5 (each) | 20 per cell | 40 per cell | 40 per cell |
| **15 cells total** | | **300** | **600** | **600** |

**Total: 1,500 distinct CNFs proposed.** Pin the exact formula generator, its binary/source hash, variable selection, independent literal polarity, duplicate clause rejection, ratio rounding and unique instance SHA-256. The near-transition density is not a guarantee that all formulas are equally hard. Avoid leakage by checking **canonical CNF hashes and generator provenance**, not merely filenames. Only finalize these counts **after power and compute budget calculations**, before any heldout evaluation.

## Hypotheses and claims

### L1 — historical identity, correctness and reproduction

Historical identity requires the authentic solver, code/build SHA, environment description and original CNF/seed/measurement logs. If originals are missing, declare `HISTORICAL_ARTIFACT_INCOMPLETE` and separately test a modern reimplementation. *Never silently change the evaluated target.*

A solver can report **SAT** only with a satisfying assignment checked against the exact original DIMACS bytes. **UNSAT** requires a verified unsatisfiability proof from a pinned independent proof checker (for example, a supported DRAT/LRAT-style proof workflow, frozen before testing). A randomized incomplete local-search solver may report **SAT** or **UNKNOWN**, not UNSAT merely because it exhausted restarts. The expected equivalent result is a verified verdict, not an identical stochastic trace.

Record all 300 L1 instance outcomes and every crash/invalid response; no successful-only sample.

### L2 — competitiveness

Different tracks:

1. **Complete SAT/UNSAT track:** full-result comparison to pinned complete solvers (candidate baselines Kissat, CaDiCaL) only if the candidate satisfies the same completeness/proof contract.
2. **SAT-witness search track:** compare SAT-finding behavior to a pinned WalkSAT-family baseline on a protocol with independently certified satisfiable instances; avoid treating a genuine UNSAT instance as a failed proof of SAT-finding ability.

Do **not** aggregate a complete SAT/UNSAT PAR-2 with an incomplete search PAR-2 as though they evaluated the same task.

Primary endpoint: **PAR-2** using one predeclared timeout `T`, same machine, single specified thread/memory limit, and fixed startup accounting. A solved valid instance contributes actual wall clock seconds up to `T`; a timeout, crash or unsolved instance contributes `2*T`. A wrong answer triggers the correctness gate and invalidates a claimed pass, rather than being discarded.

Primary comparison: relative paired PAR-2 improvement over a single pinned baseline. **Provisional** meaningful margin: 5%. The one-sided practical-improvement claim passes only if the prespecified **95% confidence-interval lower bound** exceeds 5%, and correctness is intact. Predefine cluster bootstrap procedure, deterministic bootstrap seed, repetitions, instance blocks and analysis SHA before freeze; Wilcoxon signed rank may be a secondary descriptive test, but censored PAR-2 analysis remains primary. Treat alternative baselines and individual cells as exploratory unless multiplicity adjustment (e.g., Holm) was predeclared.

### L3 — self-improvement under independent holdout

Freeze before-training and after-training artifact hashes and *what physically changed*: weights, algorithmic heuristic, memory, routing, or mixture. Compare **at least three independent training RNG seeds** with **five inference RNG seeds per version**, pairing by CNF; repeated seeds do not inflate the independent sample size. Distinguish training cost from evaluation cost. Keep all checkpoints, including losers, and prevent champion selection from seeing the L3 holdout.

Primary endpoint is paired reduction of PAR-2 averaged across the predeclared version/seed policy on the **L3-only blind set**. Provisional improvement margin and conservative interval as in L2. No manual cherry-picking or optional stopping. Record noninferiority margins and per-stratum failure rules explicitly **before freezing**, not after looking at heldout outcomes. A longer training history alone is not evidence of better SAT solving.

## Executable verification boundary (synthetic fixtures only)

A strict, bounded [3-CNF and SAT-assignment checker](../tools/verify_sat_witness.py) provides the first offline scientific integrity primitive. It reads original DIMACS bytes and a separate JSON assignment, verifies their SHA-256 binding, checks all literals and all clauses, and **never executes historical solver or pickle weights**. Example future interface:

`python tools/verify_sat_witness.py --cnf original.cnf --witness candidate-sat-assignment.json`

The witness must have `schema=janus.sat_reproducibility.sat_witness.v1`, `verdict=SAT`, `instance_sha256` of the original CNF bytes, and a full `literals` array containing one signed literal for every variable. The verifier returns `VERIFIED_SAT_ASSIGNMENT_ONLY` or a nonzero error; it does **not** generate or accept UNSAT proofs. Real verifier binaries, UNSAT proof format and resource limits for the benchmark still need separate freeze.

Current [unit tests](../tests/test_sat_witness.py) use **synthetic three-variable formulas**, which prove a local checker contract and do not support historical 220–240-variable success claims.

## Chain of custody and freeze

**Fundamentum can review methodology but cannot count as independent custodian merely by being a different repository controlled by the same agents and credentials.** Require a separate principal with access controls that Demiurge, Scout workflows and their GitHub tokens cannot reach.

1. Independent custodian generates distinct private L2/L3 CNFs and seeds; binds them to a manifest containing content hashes, schema, counts, generator SHA, UTC and key fingerprint. A public commitment hash binds a private manifest; the private bundle and seeds stay off public branches and shared CI.
2. Before learning or scoring, publish the timestamped *public* commitment and prereg hash. Freeze candidate commit, binary, weights, model selection policy, resources, verifier, analysis script and baseline.
3. Custodian receives frozen artifacts in an isolated runner with no callbacks or credential access to the candidate. Evaluations return signed or verifiable raw receipts; don't expose blind inputs through logs, errors or artifact filenames.
4. Verify correctness and all result counts, then seal final raw scores. **Only after** immutable result receipts are stored, reveal the private test files and seeds, replay generator and commit hashes, and audit access logs. If independence cannot be substantiated, label `INTERNAL_HOLDOUT_ONLY`, never an independently blind pass.

**Freeze gate remains BLOCKED** until the generator/bench toolchain, hardware limits, baseline, power analysis, holdout custodian and commitment hashes are real, not placeholders. Merging this proposal is not itself a prereg freeze.

## Immutable positive and negative evidence

A production run receipt must capture experiment/prereg/instance/model/solver/commit/environment hashes; training and solver seeds; verdict, verification log SHA, runtime, timeout, memory, failure category and receipt SHA. Keep `INVALID_ASSIGNMENT`, `FALSE_UNSAT`, `PROOF_CHECK_FAILURE`, `TIMEOUT`, `MODEL_REGRESSION`, `LEAKAGE` and `PROTOCOL_VIOLATION` as accessible as success. Never rewrite history to remove rejected hypotheses; append amendment records with lineage and reason.

**No optional stopping; no after-the-fact metric switch; no use of blind results for further tuning.** If a protocol change is unavoidable, record it before further experiments and distinguish the amended family from the original.

## Verdicts and blocked claims

Emit separate `L1_REPRODUCIBILITY`, `L2_COMPETITIVENESS`, `L3_SELF_IMPROVEMENT` and `PROTOCOL_INTEGRITY` conclusions. Allowed outcome vocabulary includes `PASS`, `FAIL`, `INCONCLUSIVE`, `INVALID`, `NOT_TESTED`; L1 also uses `REPRODUCED`, `NOT_REPRODUCED` and `INCOMPLETE_EVIDENCE`.

A finite empirical benchmark **never** proves `P=NP`, general polynomial-time SAT or full JANUS autonomy.

## Review checklist before the first experiment

- [ ] Recovered original historical CNFs and original SAT runner identified, or scope restricted explicitly to new reimplementation.
- [ ] Full environment and test generator pinned; hash every binary and formula.
- [ ] Same-resource comparison and correctness proof checker confirmed.
- [ ] Bootstrap plan and power simulation frozen; practical margin and nondegradation thresholds committed.
- [ ] Independent custodian appointed outside Demiurge-controlled credentials.
- [ ] Public holdout commitment and sealed model/analysis hashes committed before test data access.
- [ ] AIFC-compatible receipts and negative-result indexing retained by Meta Registry.
- [ ] Independent review approves `PREREG_FROZEN` separately from merging this draft.

**Current decision: `DRAFT_NOT_FROZEN`; `L1=L2=L3=NOT_TESTED`.**
