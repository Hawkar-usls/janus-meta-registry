# JANUS R1.5 — conservative GitHub Actions cost experiment

## Measurement and sources

The existing source-pinned is_fresh consumer took 303.373 ms per Python
probe (median), including 292.467 ms in the SHA-pinned, networkless Docker
checker. This is NOT the whole GitHub workflow cost. In earlier actual
Actions logs, the first checkout interval was approximately 7.217 seconds
and the pinned image-pull interval approximately 5.060 seconds; those
figures are between Actions log step-start headers, not billed runtime.

The pre-registered protocol is at
experiments/actions_cost_r15/PROTOCOL.json
(commit 77892bd8620f4dbcc37202164b06179226ea7a32), created BEFORE
any workflow change. Baseline source commit:
325f87bb06f765be3e34eb16553f6b7f202c03b0.
Baseline workflow git blob:
c3101ff4347cda8073ea8a20fb55faf490cddb30.
Observed original R1.4 run 42503712794, original consumer job 128801707140.

## Exact optimization

1. Checkout only the reviewed modules/autonomy_coder/ tree, the existing
   real consumer negative-control test and the public autonomy LATEST.json.
2. Checkout the immutable model state commit unchanged. The sparse tree
   contains STATE.json, MODULE_INDEX.json, and the FULL attempts/,
   receipts/, and self_modules/ evidence directories. There is NO loss
   of the catalog-wide source, bundle, author, and evaluator proof.
3. Fail closed unless the exact source HEAD and immutable state commit
   match and all required files and directories exist.
4. Cancel old PR versions of THIS workflow only (never schedule, main
   push or manual dispatch). Leave the original concurrency group.
5. Preserve Python 3.12, existing full negative controls, unchanged pinned
   Docker image and explicit pull, network-disabled least-privilege oracle,
   real source-bound receipt, no automatic production promotion.

## Acceptance and limits

Draft PR only. Original 270-case model validation, source SHAs, producer
receipt status, and zero runtime authority change must remain intact.
Measure actual checkout, Docker pull and completed job durations in logs.
Do not call an improvement proven until multiple comparable independent
run samples can be compared. Original GitHub Actions R1.4 included a
one-time dependent profile job, so 48s full-run wall-time is NOT a
single-job, billed-runner baseline.

No Docker cache, unauthenticated image, altered trusted source state,
reduced test coverage or loss of checksum verification. No changes to
Secret Persistence Guard (push+PR dual guards remain), HOME, SkinGPT,
Rowan, TIME-SAT E12C4/C023, private HRAiN, or scientific permissions.
Do not auto-merge.


## R1.5 correction: actual first fail-closed trial

The first draft PR run 42514829305 failed in the real consumer's
module_registry.verify call. It legitimately required the immutable
generated/retry_delay/*.py source, so a sparse state tree without
generated/ was **incomplete**. No runtime promotion or state change
occurred. The source-bound guard caught this before admission.

A separate, append-only amendment at
experiments/actions_cost_r15/AMENDMENT_001.json records the failure
and includes generated/ in the required state checkout. All original
attempts/, receipts/, self_modules/, MODULE_INDEX.json and STATE.json
checks remain mandatory. Do not retroactively rewrite PROTOCOL.json.
