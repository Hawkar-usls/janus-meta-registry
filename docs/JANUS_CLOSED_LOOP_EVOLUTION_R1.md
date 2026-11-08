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
