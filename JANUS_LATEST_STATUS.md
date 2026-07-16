# JANUS Latest Status - Read Before the Migration Handoff

> **Snapshot:** 2026-07-16
>
> **Purpose:** this additive current-state overlay supersedes only the current-stage portion of `JANUS_CHAT_MIGRATION_HANDOFF.md`. Read it first, then read the long handoff for mission, ethics, lineage, safety and claim boundaries.
>
> **Evidence rule:** independently byte-verified evidence, operator/CODEX-reported evidence and inventory-only bindings must remain explicitly distinct.

## Current A18.44 state

```text
A18_44_OFFLINE_ACQUISITION_PILOT=PASS_AFTER_ATTEMPT_2
PILOT_INDEPENDENT_BYTE_AUDIT=PASS
CAMPAIGN_AUTHORIZATION_FREEZE=PASS

PILOT_ATTEMPTS_EXECUTED=2/2
CAMPAIGN_ATTEMPTS_EXECUTED=0/360
CAMPAIGN_IDENTITIES_CONSUMED=0
CAMPAIGN_EXECUTION_AUTHORIZED=false
CAMPAIGN_ATTEMPTS_AUTHORIZED=0
AUTHORIZATION_CONSUMED=false
SCIENTIFIC_WEIGHT=0

SCIENTIFIC_ENDPOINTS_COMPUTED=no
CALIBRATION_ANALYSIS_EXECUTED=no
EVALUATION_ANALYSIS_EXECUTED=no
PRIOR_ART_SEARCHED=no
POOL_CONTACTED=no
MINER_LAUNCHED=no
LIVE_STARTED=no
A18_44_SCIENTIFIC_EFFECT_PROVEN=no
```

Both non-campaign pilot attempts reached `SEALED_VALID`. The completed pilot is an operational evidence-integrity PASS. It is not an A18.44 scientific result.

## Independent Byte Audit

The independently produced audit JSON and text are preserved at:

- `reports/A18_44/JANUS_A18_44_INDEPENDENT_AUDIT_RESULT.json`
- `reports/A18_44/JANUS_A18_44_INDEPENDENT_AUDIT_RESULT.txt`

```text
AUDIT_ARCHIVE_SHA256=554146aee912812d776957b5aa0556ad11bb31c7f492abdf1c752679ba749fb6
AUDIT_ARCHIVE_SIZE_BYTES=1080245
ZIP_MEMBERS=405
ZIP_CRC=PASS
DUPLICATE_MEMBERS=0
UNSAFE_PATHS=0
ENCRYPTED_ENTRIES=0

TOP_LEVEL_CHECKSUMS=403/403
STRICT_JSON_FILES=121
STRICT_JSONL_CHAINS=211
STRICT_JSONL_RECORDS=3935
DUPLICATE_JSON_KEYS=0
HIGH_CONFIDENCE_SECRET_FINDINGS=0

AUDIT_BUNDLE_PAYLOAD_ROOT_SHA256=66397f48eb623dceaf7164593e0834c5c1afb3550c3ce6fa5a0d36383e6f1451
```

The attached JSON and text were cross-checked against each other and against the locally preserved ZIP hash and size before this registry update.

## Pilot Attempts

```text
Attempt 1
status: SEALED_VALID
session: a18_44_v0_1_pilot_session_001_86311f8a6972f1cb
reset:   a18_44_v0_1_pilot_reset_001_3fa2a880875743b9
entries: 122/122
references: 120/120
JSONL chains / records: 102 / 1902
unique batches / exact exposure: 88 / 8800000
terminal queues / commitments: 0 / 0
scientific weight: 0

Attempt 2
status: SEALED_VALID
session: a18_44_v0_1_pilot_session_002_e6e40635b96f84d7
reset:   a18_44_v0_1_pilot_reset_002_52b65bd284506f40
entries: 128/128
references: 126/126
JSONL chains / records: 108 / 2028
unique batches / exact exposure: 94 / 9400000
authoritative horizons: 10/10
terminal queues / commitments: 0 / 0
scientific weight: 0
```

The pilot identities remain permanently excluded from campaign `CALIBRATION`, `EVALUATION`, `TRAIN`, ranking, partitioning and confirmatory evidence.

## Verification Layers

**Independently byte-verified:** the 405-member export structure and CRC; 403 top-level checksums; both session seals and manifest-reference sets; 211 JSONL chains and 3935 records; post-pilot payload roots; and the recorded authorization, dry-run and execution-package lineage roots.

**Previously operator/CODEX-reported:** earlier stage records retain their original evidence labels. This audit is additive and does not rewrite or reinterpret those historical layers or any negative record.

**Inventory-only limitation:** the approved miner binary was intentionally absent from the audit archive. Only its recorded hash/path inventory was audited:

```text
APPROVED_MINER_SHA256_INVENTORY=c46feec0dd936a65bb8e6e074aaa952a0cd57b6925cfb4dd37aad2140d22e1d2
```

Power stability, OneDrive pause, no-second-writer and historical process-absence records are integrity-verified attestations; their physical conditions cannot be proven retrospectively from archive bytes alone.

## Campaign Authorization Freeze

The additive campaign governance layer passed without creating the campaign output root, authorizing an attempt or consuming an identity:

```text
TOTAL_CAMPAIGN_ATTEMPTS=360
CALIBRATION_ROLE_ATTEMPTS=320
EVALUATION_ROLE_ATTEMPTS=40
UNIQUE_SESSION_IDS=360/360
UNIQUE_RESET_IDS=360/360

EXECUTION_WINDOWS=36
MAX_ATTEMPTS_PER_WINDOW=10
NEGATIVE_FIXTURES=60/60
CHECKSUMS=13/13
ARCHIVE_REOPEN_AND_REHASH=PASS

AUTHORIZATION_ARTIFACT_SHA256=909da9b869a5e1bbf074f5b78cd02eaf68c679fbdad1becf3405be98b5d517b5
FREEZE_MANIFEST_SHA256=ace878d97818c890375b2a7d9b6898300858b7279384b76823baf9c87bf81692
FREEZE_PAYLOAD_ROOT_SHA256=4bdbbe9a70ee10bf18082485f25b1cf1b58b10fbefec383492454dca6dc0caaf
SHA256SUMS_SHA256=60e729d616f9c846b80a0b06375274319b03d5a82ac4f99b69e7718e2f158f4f
AUDIT_EXPORT_ZIP_SHA256=ac7802d28d3a1d362be4a738f25b47831b6a0fbe23b55c0bc6ebafaef2abad26
```

The fixed schedule remains in exact ordinal order. Every future operational window is limited to ten consecutive ordinals, requires a separate future hash-bound authorization and fresh safety/consent gates, and cannot transition automatically to the next window. An identity is consumed only by a durably recorded `PLANNED -> STARTED` transition; an interrupted identity after that boundary is quarantined and cannot be retried, replaced, resumed or reused.

## Campaign Hard Stop

The frozen 360-attempt campaign remains untouched. Governance is frozen, but execution is still unauthorized:

```text
campaign governance frozen = yes
campaign execution authorized = false
authorization consumed = false
campaign attempts authorized = 0
campaign attempts executed = 0/360
campaign identities consumed = 0
campaign output root created = no
optional stopping = forbidden
automatic continuation = forbidden
scientific endpoint computation = forbidden
```

## Exact Next Allowed Stage

```text
A18_44_V0_1_OFFLINE_ACQUISITION_CAMPAIGN_HASH_BOUND_ENABLEMENT_AND_DRY_RUN_VALIDATION_ONLY
```

This next stage is dry-run only. It may bind and test the frozen governance package, but must execute zero attempts, create no campaign output, consume no campaign identity, compute no scientific endpoint and never transition automatically into campaign execution.

## Claim Ceiling Remains Unchanged

Do not claim:

- that The Mercy Limit works;
- stale-work reduction or population-p99 coverage;
- wall-energy or thermal benefit;
- reduced wear or longer hardware life;
- live-runtime equivalence;
- mining advantage or profitability;
- novelty;
- product readiness.

The pilot and its independent audit establish operational evidence integrity only. The campaign freeze establishes governance readiness only. Continue with `JANUS_CHAT_MIGRATION_HANDOFF.md` and the newest A18.44 current-lineage successor.
