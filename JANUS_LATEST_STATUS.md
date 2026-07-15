# JANUS Latest Status — Read Before the Migration Handoff

> **Snapshot:** 2026-07-15
>
> **Purpose:** this additive file supersedes only the current-stage portion of `JANUS_CHAT_MIGRATION_HANDOFF.md`. Read it first, then read the long handoff for mission, ethics, lineage, safety and claim boundaries.
>
> **Evidence rule:** never promote an operator/CODEX-reported result to independently byte-verified status unless the corresponding bytes were received and hashed.

## Current A18.44 state

```text
A18_44_OFFLINE_ACQUISITION_HARNESS_SYNTHETIC_VALIDATION=PASS
A18_44_OFFLINE_ACQUISITION_PILOT_AUTHORIZATION_FREEZE=PASS
A18_44_PILOT_HASH_BOUND_ENABLEMENT_AND_DRY_RUN=PASS

DRY_RUN_ONLY=true
PILOT_EXECUTION_ALLOWED=false
AUTHORIZATION_CONSUMED=false
PILOT_ATTEMPTS_EXECUTED=0
CAMPAIGN_ATTEMPTS_CONSUMED=0
FIRST_BLOCKING_INVARIANT=NONE

CALIBRATION_EXECUTED=no
EVALUATION_EXECUTED=no
SCIENTIFIC_ENDPOINTS_COMPUTED=no
PRIOR_ART_SEARCHED=no
POOL_CONTACTED=no
MINER_LAUNCHED=no
LIVE_STARTED=no
```

The dry-run derived package bound the exact pilot authorization while preserving execution disabled. The pilot has not started.

## Dry-run gate result

```text
SEALED_HARNESS_BINDINGS=PASS
SEALED_HARNESS_MODIFIED=no
AUTHORIZATION_BINDINGS=PASS
AUTHORIZATION_HASH_BOUND=PASS
ROSTER_BINDINGS=PASS
OPERATIONAL_CONTRACT_BINDINGS=PASS

OPERATOR_PHRASE_GATE=PASS
ATTEMPT_1_CONSENT_GATE=PASS
ATTEMPT_2_CONSENT_GATE=PASS
POWER_GATE=PASS
CAPACITY_GATE=PASS
SYNCED_ROOT_GATE=PASS
PROCESS_ABSENCE_GATE=PASS
CAMPAIGN_SEPARATION=PASS
SCIENTIFIC_ENDPOINT_PROHIBITION=PASS
NEGATIVE_FIXTURES=40/40
CHECKSUMS=67/67
```

## Dry-run package hashes

```text
DERIVED_PACKAGE_PAYLOAD_ROOT_SHA256=6fac128ed448e14d06c2db6a6a3612ec91815fbdc1e81503fb826c7489544f79
DERIVED_PACKAGE_MANIFEST_SHA256=b3b69b00775e423cbee621da32739e9d85d5d4b0e1239aa084d5e698201bebff
DRY_RUN_VALIDATION_REPORT_SHA256=a02b6c76895f13fe6fed08bcfc0540bc18c79217afc60f40cc9d73ccb2ba0096
SHA256SUMS_SHA256=27f564b6d5a0d4e012037d6c402c7b8a15a9b9ced3b3a4cd6ce13c989dfc1137
```

Verification level: **operator/CODEX-reported**. The dry-run package bytes were not uploaded into the recording chat and therefore have not been independently byte-audited here.

## Frozen pilot identities

Exactly two non-campaign operational identities remain frozen:

```text
Attempt 1
role: PILOT_CALIBRATION_PATH_OPERATIONAL_VALIDATION
session: a18_44_v0_1_pilot_session_001_86311f8a6972f1cb
reset:   a18_44_v0_1_pilot_reset_001_3fa2a880875743b9
scientific weight: 0

Attempt 2
role: PILOT_EVALUATION_PATH_OPERATIONAL_VALIDATION
session: a18_44_v0_1_pilot_session_002_e6e40635b96f84d7
reset:   a18_44_v0_1_pilot_reset_002_52b65bd284506f40
scientific weight: 0
```

They remain permanently excluded from `CALIBRATION`, `EVALUATION`, `TRAIN`, campaign ranking, partitioning and confirmatory evidence.

## Synced-root readiness

The output root is classified as:

```text
SYNCHRONIZED_ROOT
```

The dry-run found the safety gate enforceable, but:

```text
OneDrive pause attestation = absent
FUTURE_EXECUTION_READINESS = false
```

Observed free space was `271360577536` bytes, but this is not future execution evidence. It must be remeasured immediately before each attempt.

Before execution, require:

- the root fully local with no Files On-Demand placeholders;
- OneDrive synchronization paused for the complete pilot window;
- hash-bound pause attestation;
- no second-device or second-process writer;
- output root absent or empty;
- stable external power and no pending shutdown/restart;
- explicit operator consent immediately before each attempt;
- synchronization resumed only after sealing, inspection and checksums.

## Exact next allowed stage

```text
A18_44_V0_1_OFFLINE_ACQUISITION_PILOT_EXECUTION_ONLY_AWAITING_EXACT_OPERATOR_PHRASE
```

This is now the first stage that may execute real offline pilot attempts, but only after the exact frozen operator phrase and all immediate gates pass.

Execution boundaries:

```text
maximum pilot attempts = 2
execution order = 1 then 2
no retries
no replacement identities
no automatic attempt-2 start
no campaign attempt consumption
no automatic campaign continuation
scientific weight = 0
```

The exact whole-pilot phrase is stored in the private authorization artifact. A paraphrase, this status file, or a prior approval must not be treated as execution consent.

## Claim ceiling remains unchanged

Do not claim:

- that The Mercy Limit works;
- stale-work reduction;
- population-p99 coverage;
- wall-energy or thermal benefit;
- reduced wear or longer hardware life;
- live-runtime equivalence;
- mining advantage or profitability;
- novelty;
- product readiness.

The dry-run PASS establishes only that the hash-bound execution gates behaved correctly while the door remained closed. Continue with `JANUS_CHAT_MIGRATION_HANDOFF.md` and the newest A18.44 registry record.
