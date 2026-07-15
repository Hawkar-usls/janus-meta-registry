# JANUS Latest Status — Read Before the Migration Handoff

> **Snapshot:** 2026-07-15
>
> **Purpose:** this small additive file supersedes only the *current-stage* portion of `JANUS_CHAT_MIGRATION_HANDOFF.md`. Read it first, then read the full handoff for mission, ethics, lineage, safety and claim boundaries.
>
> **Evidence rule:** never promote an operator/CODEX-reported result to independently byte-verified status unless the corresponding bytes were received and hashed.

## Current A18.44 state

```text
A18_44_OFFLINE_ACQUISITION_HARNESS_SYNTHETIC_VALIDATION=PASS
A18_44_OFFLINE_ACQUISITION_PILOT_AUTHORIZATION_FREEZE=PASS
PILOT_ATTEMPTS_FROZEN=2
PILOT_ATTEMPT_ORDINALS=1,2
CAMPAIGN_ATTEMPT_ORDINALS_CONSUMED=0
FIRST_BLOCKING_INVARIANT=NONE

PILOT_EXECUTED=no
REAL_ACQUISITION_ATTEMPTS_EXECUTED=0
CALIBRATION_EXECUTED=no
EVALUATION_EXECUTED=no
SCIENTIFIC_ENDPOINTS_COMPUTED=no
PRIOR_ART_SEARCHED=no
POOL_CONTACTED=no
MINER_LAUNCHED=no
LIVE_STARTED=no
```

The authorization freeze is governance only. It does not authorize execution and remains in status:

```text
FROZEN_AWAITING_SEPARATE_HASH_BINDING_STAGE
```

## Pilot identities

Exactly two non-campaign operational pilot identities are frozen:

```text
Attempt 1
role: PILOT_CALIBRATION_PATH_OPERATIONAL_VALIDATION
session: a18_44_v0_1_pilot_session_001_86311f8a6972f1cb
reset:   a18_44_v0_1_pilot_reset_001_3fa2a880875743b9
schedule entries: 10
scientific weight: 0

Attempt 2
role: PILOT_EVALUATION_PATH_OPERATIONAL_VALIDATION
session: a18_44_v0_1_pilot_session_002_e6e40635b96f84d7
reset:   a18_44_v0_1_pilot_reset_002_52b65bd284506f40
schedule entries: 10
scientific weight: 0
```

Both are permanently excluded from `CALIBRATION`, `EVALUATION`, `TRAIN`, confirmatory evidence, campaign ranking and campaign partitioning.

## Pilot authorization hashes

```text
AUTHORIZATION_ARTIFACT_SHA256=356eb15f54715c28843986267b060da51bdddfe8039bbc141a05ccaafe8e4a32
AUTHORIZATION_PAYLOAD_SHA256=21158b6e86dd144ff2f9e554898ee6e1faa3e7c8afe54a0ebd7f2fccd0b77f68
OPERATIONAL_CONTRACT_SHA256=737ab3593bfbe949b5ecfe6187d4e3e3245e6e52579afabaeba429002203b244
OPERATIONAL_CONTRACT_PAYLOAD_SHA256=721f08f8352daaeed8a34faa71b0c8165d482c8bfb7b8e461753d50e7edc95da
PILOT_ROSTER_SHA256=de16d243b78de83be35313c7872d48210292ad02de771cf1dcc0f7c2246a6ced
PILOT_ROSTER_PAYLOAD_SHA256=c0ee04a54255de66141a3827d2645a2923d95823d8f4e4a318154756be7e2112
VALIDATION_REPORT_SHA256=32b7d1fdd591cc485ee7e165696055fd42527897e6de0bcf10f4c733ce2c555e
FREEZE_MANIFEST_SHA256=1fe6046261129e6b037edab7b1dcb20069d9fc7897d7f09c120c2690e0aa7cf1
FREEZE_PAYLOAD_ROOT_SHA256=b8e83db500bfc68c0e5b0a46ae27edafa2223dae278c4a66760fdbbfd2b44d3f
SHA256SUMS_SHA256=50baccb696a32015243d547c25caaa4f67944b87d3f869c11487cdec7d91a3a7
```

Predecessor harness bindings remain:

```text
HARNESS_PACKAGE_PAYLOAD_ROOT_SHA256=044ffa766d29f71e91abdff8c178d12d40f16a94a9e865efb21088043cd97a5b
HARNESS_VALIDATION_REPORT_SHA256=03fda803469653807c2c1f5663c7d103d23946cd2abf93d5624054f5cda6f414
HARNESS_PACKAGE_MANIFEST_SHA256=160e8976d3e816202e85a0b5e282cda1e261d97a0e48de7986ddf7f02689991c
HARNESS_SHA256SUMS_SHA256=4018d32b7a67d64607644bbe1c1d9d2b5ea192d31cf35377fa9efef217137de8
```

## Independent verification in the recording chat

The five uploaded JSON artifacts and the checksum file were independently read and hashed.

```text
JSON_PARSE=5/5
DUPLICATE_JSON_KEYS=0
UTF8_BOM_ABSENT=6/6
LF_ONLY=6/6
UPLOADED_CHECKSUM_ENTRIES_MATCH=5/5
SHA256SUMS_ENTRIES=6
AUTHORIZATION_PAYLOAD_HASH_REPRODUCED=yes
OPERATIONAL_CONTRACT_PAYLOAD_HASH_REPRODUCED=yes
ROSTER_PAYLOAD_HASH_REPRODUCED=yes
FREEZE_PAYLOAD_ROOT_REPRODUCED=yes
SESSION_ID_DERIVATIONS=2/2
RESET_ID_DERIVATIONS=2/2
SESSION_SEED_DERIVATIONS=2/2
SCHEDULE_ENTRY_HASHES=20/20
SCHEDULE_LIST_HASHES=2/2
```

The freeze tooling file was not uploaded. Therefore the full local `CHECKSUMS=6/6` and `34/34` validation remain partly CODEX/operator-reported; five of six checksum-listed artifacts were independently byte-verified.

## Operational gates

The frozen contract requires:

- explicit operator consent immediately before each attempt;
- no automatic pilot start;
- no automatic start of attempt 2;
- no retries and no replacement identities;
- stable external power before each attempt;
- minimum free space before pilot: `422785844` bytes;
- append-only hash-linked records with durable flush;
- zero missing references;
- quarantine on interruption or indeterminate integrity;
- zero campaign identities consumed;
- no automatic continuation into the 360-attempt campaign.

The exact future whole-pilot execution phrase is stored in the private authorization artifact. Do not treat the freeze itself, a paraphrase, or a dry-run request as execution approval.

## Synced-root safety gate

The private pilot output root is beneath a OneDrive-synchronized Desktop path. Before any future execution authorization, the dry-run stage must fail closed unless all of the following are demonstrated:

- the root is fully local and contains no Files On-Demand placeholders;
- OneDrive synchronization is paused for the complete pilot window;
- no second device or process can write to the root;
- the root is absent or empty before the pilot;
- enough local free space is available;
- synchronization is resumed only after terminal sealing, inspection and checksums.

This is an additive safety restriction. It does not alter scientific acceptance criteria.

## Exact next allowed stage

```text
A18_44_V0_1_OFFLINE_ACQUISITION_PILOT_HASH_BOUND_ENABLEMENT_AND_DRY_RUN_VALIDATION_ONLY
```

This stage may create a derived executable package that binds the exact authorization artifact hash while preserving the sealed harness predecessor byte-for-byte.

It must remain dry-run only:

```text
PILOT_EXECUTION_ALLOWED=false
PILOT_ATTEMPTS_EXECUTED=0
AUTHORIZATION_CONSUMED=false
SCIENTIFIC_ENDPOINTS_COMPUTED=no
```

The dry run must validate package and authorization hashes, both identities, schedules, domain binding, reference integrity, output-root safety, free-space logic, power-gate behavior, process absence, campaign separation and fail-closed behavior.

It must not create or execute either pilot attempt, contact a pool, launch a miner, start live work, consume campaign identities or modify protected NAS services.

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

The pilot authorization freeze and future dry run are operational governance and engineering validation only. After reading this file, continue with `JANUS_CHAT_MIGRATION_HANDOFF.md` and the newest A18.44 registry record.
