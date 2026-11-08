# JANUS Closed-Loop Evolution — R1 (review-only)

## Scope

This first change is an offline Proof-of-Improvement screen. It is not an
autonomous code deployment mechanism. It does not dispatch GitHub Actions,
make API calls, read private sources, mutate queues, change scientific
authority, use paid models, or allow automatic merging.

The existing modules/autonomy_coder/ lifecycle remains the reviewed
candidate-authoring mechanism. The new screen is designed to sit after
candidate isolation and before any independent replay or approval.

## Evidence contract

Freeze a protocol before collecting measurements, in a reviewed commit:

- schema: janus.closed_loop.improvement_protocol.v1
- task_id, metric, direction (lower or higher)
- SHA-256 of baseline source, training manifest, and holdout manifest
- Exact ordered list of 8–256 distinct holdout case IDs
- Positive minimum_mean_gain, zero permitted regressions
- authority_delta=0, allow_auto_merge=false

A separately produced measurement file must contain:

- schema: janus.closed_loop.improvement_measurement.v1
- protocol_sha256 bound to the frozen protocol
- SHA-256 of the candidate source and a 40-hex evaluator commit reference
- Exactly one paired baseline/candidate score for each frozen case
- authority_delta=0

Run with no network, credentials, or runtime side effects:

    python modules/autonomy_loop/proof_of_improvement.py frozen.json measured.json

Exit codes: 0 eligible for independent replay; 1 no measured improvement;
2 invalid or unbound evidence. The verdict includes canonical SHA-256
bindings and explicit independent_replay_attested=false,
runtime_consumption_attested=false, production_promotion=false,
allow_auto_merge=false.

These SHA values provide integrity bindings, not signatures. Distinct
training and holdout manifest hashes alone do not prove disjointness.
Likewise, a declared evaluator commit does not prove independent execution.
A trusted, source-pinned independent witness must re-run the frozen cases,
establish chronology and dataset separation, and check the actual candidate
before any review of adoption.

## Definition of done for R1

- Adversarial offline tests reject corrupted provenance, incomplete/repeated
  holdout cases, NaN/Infinity, regressions, false gain, authority escalation
  and self-comparisons.
- An eligible comparison still grants zero execution or merge authority.
- No change to the live production schedule or JANUS HOME/SkinGPT routing.

## Later bounded integration (not implemented by this PR)

1. Register a pre-committed protocol and baseline for one existing safe
   patch from the verified backlog (no private source or holdout leakage).
2. Run the patch in the existing pinned, networkless Coder sandbox.
3. Run a source-pinned independent evaluator on the same frozen cases.
4. Persist immutable measurement and replay receipts in Meta Registry, with
   failed and negative outcomes included.
5. Offer a draft PR only after replay passes; enforce existing human/scope
   approvals, CAS and rollback before runtime adoption.
6. Track measured benefit, runner-minutes per accepted patch, time to
   recovery, rollback rate, and unattended cycles.

E12C4, Rowan, SkinGPT, HOME, C023, and scientific holdout gates are unchanged.


## R1.1 — source-bound candidate triage (review-only)

The existing patch queue has 42 proposals. At the observed 2026-11-08
snapshot, four were VERIFY_PASS but targeted Hrain/iNaiHR; another 38
were WAITING_FOR_TARGET_BRANCH in Hrain. These 38 are **not ready-to-run**
patches. The index's blocked_count is a separate counter and does not
represent the number of missing branches. No private HRAiN access or
automatic creation of missing target branches is authorized by this change.

An existing, non-private candidate was selected for a preflight only:
PR #379 at reviewed head 2652dd70d8f65385316cd309d4a74db2b948dc46,
candidate_modules/retry_delay/module.py, source SHA-256
a45bf9b5814e432a89334e46f8acac63a9fa1d2846dc393ed21e6dd6695b2611.
The proposal reports 291 independently verified cases from its historical
authoring process; this R1.1 preflight does **not** independently confirm
those historical runs.

modules/autonomy_loop/candidate_preflight.py now checks the reviewed source's
actual SHA-256 against the proposal, verifies the source-bound proposal digest,
applies the existing strict AST admission policy, forbids authority escalation,
and emits only READY_FOR_ISOLATED_BEHAVIOR_REPLAY_ONLY. It also classifies
the public queue without dispatching workflows or touching Hrain.

All such verdicts explicitly keep independent_replay_attested=false and
improvement_attested=false. Neither a valid source fingerprint nor a green
historical PR is a measured improvement. The next required steps remain a
frozen baseline/holdout, actual isolated replay, and independent evidence
replay before any possible runtime review.


## R1.2 — completed reference microbenchmarks (2026-11-08)

The measurement protocol was committed at
4e688f25c96590e1b70062bc336d84aba728e49e **before** the first trial.
Frozen sources: BASELINE.py SHA-256
1a76285172a0891f910b94d7dad51d111a82faf36a84c386dd88b14005e94da0;
candidate PR #379 commit 2652dd70d8f65385316cd309d4a74db2b948dc46,
source SHA-256 a45bf9b5814e432a89334e46f8acac63a9fa1d2846dc393ed21e6dd6695b2611.
The baseline uses min(cap, pow(2, attempt)); the candidate uses
min(cap, 2 ** attempt). **The baseline is a frozen reference, not a
verified current JANUS production implementation.**

Three separate GitHub Actions PR jobs used the existing pinned Coder Python
image, networkless, read-only, no-new-privileges, with a CPU and memory bound.
Each checked the established 291-case oracle for both versions, 91 frozen
training cases, an eight-case disjoint holdout, and eight paired timing
measurements (median over five rounds of 40,000 calls per arm per case).

| Run ID | Reference us/call | Candidate us/call | Difference | Regressions |
| --- | ---: | ---: | ---: | ---: |
| 42480998405 | 0.212325 | 0.202253 | -4.74% | 0 |
| 42481202400 | 0.117771 | 0.114528 | -2.75% | 0 |
| 42481453000 | 0.179658 | 0.172082 | -4.22% | 0 |

All three screens reported ELIGIBLE_FOR_INDEPENDENT_REPLAY, **not**
INDEPENDENTLY_REPLAYED, PRODUCTION_IMPROVED, or AUTO_MERGE_ELIGIBLE.
Run-to-run latencies varied substantially, so this is an exploratory
reference microbenchmark, not a reliable end-to-end performance improvement.

Each run's full trial, raw paired values, input SHA references, screen verdict,
Actions run/job IDs, and artifact archive digest is durably stored **as a new,
never-overwritten JSON file** in
experiments/closed_loop_retry_delay_r1/receipts/github-run-<RUN_ID>.json.

Replay integrity offline with no GitHub token:

    python modules/autonomy_loop/verify_retry_receipts.py

This verifier checks the frozen protocol, exact input SHA bindings, disjoint
train/holdout pairs, paired-screen arithmetic, immutable trial/verdict digests,
run/artifact metadata, and non-escalation. It **does not rerun CPU timing** or
independently attest the original worker; those must be checked separately by
a different independently governed evaluator before any claim of adopted
runtime optimization.

The temporary PR-only benchmark job was removed from the proposed workflow
after these three trials, restoring the existing production workflow unchanged.
No main merge, runtime change, model promotion, private data access, paid model
invocation, or scientific authority change was made.


## R1.3 — separate timeit implementation and neutral timing control

The alternate measurement policy was immutably preregistered at
0f6cc28fa20ce5e484440afdbadbef57e430c2ef **before** the R1.3
GitHub Actions run. This is a separate implementation within the same
repository/organization, **not** an external blind independent evaluation.

- R1.3 run: https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/42482603402
- Source PR head: 2ec50e0aede9ebc4331abfe4f5e45020dd5fb5de
- GitHub PR-event checkout **synthetic merge** SHA: 02ebf0f5a4c693e5250cd7e40d2a67c833cef0e6
- The two SHAs are intentionally distinct; GitHub commit metadata confirms
  that the synthetic merge includes the PR head as part of its merge message.
- Source artifact archive SHA-256:
  0b5f0d3baeb6ecdfcd66a3b52fdf20c59f3e83efbfd56483108013ba42e40c01
- Trial report SHA-256: 5caadddd01a4b7912fd95ac726ea8e132588b51ed39800efbb30e71a33df540e

The separate implementation uses Python's timeit, 24 newly generated
challenge inputs disjoint from the *R1.2 comparison's* training/holdout
manifest, seven repetitions of 30,000 operations per case, alternating
execution order, and a same-function-versus-itself neutral timing control.

| R1.3 source | Mean microseconds/call |
| --- | ---: |
| Frozen pow(2, attempt) reference | 0.170690 |
| Qwen-authored 2 ** attempt candidate | 0.165693 |
| Difference | 0.004997 (2.93%) |
| Mean absolute same-function neutral control difference | 0.002811 |

All 24 measured pairs favoured the candidate; in 5/24, the same-function
neutral difference was at least the observed candidate/reference gain.
The reported gain is too small to infer production benefit from these
measurements alone.

**Critical applicability fact:** the current reviewed JANUS Coder AST
admission policy rejects pow() calls. The R1.2/R1.3 frozen reference
is therefore not an admissible generated Coder module. The actual
source-pinned real_operational_consumer.py uses the model-authored
is_fresh module, not retry_delay. This experiment provides **zero proof**
that retry_delay changes the performance of the live operational path.

The 24 paired raw timing arrays, control arrays, preregistration binding,
GitHub source run/job and artifact archive digest are preserved in
experiments/closed_loop_retry_delay_r13/receipts/github-run-42482603402.json.
A separately maintained, offline **arithmetic** replayer is available at:

    python modules/autonomy_loop/verify_r13_receipt.py

It recalculates medians/means, checks challenge input regeneration,
identities and authority boundaries, and rejects forged raw timings
even if an attacker changes the report's own digest. It does **not**
produce an independent physical timing run or an externally signed witness.

The final no-production-admission assessment is stored in
experiments/closed_loop_retry_delay_r13/ASSESSMENT.json.

The one-time benchmarking GitHub Actions job was retired and the original
workflow restored byte-for-byte. Do **not** use this experiment to
auto-merge PR #379 or claim an autonomous, runtime-relevant improvement.
The next justified performance study must use the **actual** operational
consumer and its current production baseline with independent acceptance,
and should optimize runner startup/overhead before nanosecond-scale helpers.
