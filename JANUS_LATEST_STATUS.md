# JANUS Latest Status - Read Before the Migration Handoff

> **Snapshot:** 2026-07-17
>
> **Purpose:** this additive current-state overlay supersedes only the current-stage portion of `JANUS_CHAT_MIGRATION_HANDOFF.md`. Read it first, then read the long handoff for mission, ethics, lineage, safety and claim boundaries.
>
> **Evidence rule:** independently byte-verified evidence, operator/CODEX-reported evidence and inventory-only bindings must remain explicitly distinct.

## Current A18.44 state

```text
A18_44_OFFLINE_ACQUISITION_PILOT=PASS_AFTER_ATTEMPT_2
PILOT_INDEPENDENT_BYTE_AUDIT=PASS
CAMPAIGN_AUTHORIZATION_FREEZE=PASS
CAMPAIGN_AUTHORIZATION_FREEZE_INDEPENDENT_AUDIT=PASS
CAMPAIGN_HASH_BOUND_DRY_RUN=PASS
CAMPAIGN_HASH_BOUND_DRY_RUN_INDEPENDENT_AUDIT=PASS
WINDOW_01_EXECUTION_AUTHORIZATION_FREEZE=PASS
WINDOW_01_AUTHORIZATION_FREEZE_INDEPENDENT_AUDIT=PASS
WINDOW_01_HASH_BOUND_EXECUTION_PACKAGE_DRY_RUN=LOCAL_PASS
WINDOW_01_PACKAGE_DRY_RUN_INDEPENDENT_AUDIT=EVIDENCE_INSUFFICIENT
WINDOW_01_PACKAGE_DRY_RUN_FIXTURE_COVERAGE_REPAIR=PASS_LOCAL_AWAITING_INDEPENDENT_AUDIT

PILOT_ATTEMPTS_EXECUTED=2/2
WINDOW_01_ATTEMPTS_EXECUTED=0/10
CAMPAIGN_ATTEMPTS_EXECUTED=0/360
CAMPAIGN_IDENTITIES_CONSUMED=0
WINDOW_01_EXECUTION_AUTHORIZED=false
WINDOW_01_ATTEMPTS_AUTHORIZED=0
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

## Campaign Freeze Audit and Dry Run

The independently produced campaign-freeze audit result was ingested from the
operator message and its substantive claims were independently revalidated
against the immutable local freeze package and 14-member audit ZIP. The two
declared attachment byte streams were not mounted locally; the registry
therefore preserves explicit operator-message transcriptions and does not
claim they are byte-identical attachment copies.

```text
INDEPENDENT_FREEZE_AUDIT=PASS
LOCAL_BYTE_REVALIDATION=PASS
FREEZE_AUDIT_ZIP_SHA256=ac7802d28d3a1d362be4a738f25b47831b6a0fbe23b55c0bc6ebafaef2abad26
FREEZE_PAYLOAD_ROOT_SHA256=4bdbbe9a70ee10bf18082485f25b1cf1b58b10fbefec383492454dca6dc0caaf
CAMPAIGN_IDENTITY_ROOT_SHA256=405e83aa8486a84ffc7cadc16d634d228fb947ded416f5de9b4af554efbae189
WINDOW_POLICY_ROOT_SHA256=96264f94159f7f76638946d7a7a43e1bafaf7c09a804841335ffe7a26a4b6e73
```

The exact dry-run-only stage then passed without creating campaign evidence:

```text
DRY_RUN_PACKAGE_PAYLOAD_ROOT_SHA256=e684e04cb00aee46f04cdc0add1e7cde464201f6845710fcadbc3351c34df6b8
DRY_RUN_PACKAGE_MANIFEST_SHA256=24298c40c5d76637a33f466b4ebb5e10d6f3f13c41e110cfe009393257120e19
DRY_RUN_VALIDATION_REPORT_SHA256=acc9c2dd344ce303fbedb484720113c39c7126883c29df3878b0c415f83c8a38
DRY_RUN_SHA256SUMS_SHA256=d16df294a018d801540ff1b1d4251626eb16099a2ffa978f2f211bfeb9aadbfc
DRY_RUN_AUDIT_ZIP_SHA256=c20fde6a98c522632beef14f61553f83991494d25e5bcf08c094dbd587980524

NEGATIVE_FIXTURES=79/79
CHECKSUMS=17/17
ARCHIVE_REOPEN_AND_REHASH=PASS
ARCHIVE_VERIFICATION_WORKSPACE_REMOVED=yes

CAMPAIGN_EXECUTION_AUTHORIZED=false
AUTHORIZATION_CONSUMED=false
CAMPAIGN_ATTEMPTS_AUTHORIZED=0
CAMPAIGN_ATTEMPTS_EXECUTED=0/360
CAMPAIGN_IDENTITIES_CONSUMED=0
CAMPAIGN_OUTPUT_ROOT_CREATED=no
SCIENTIFIC_ENDPOINTS_COMPUTED=no
```

The independent dry-run audit attachments were mounted locally and ingested
byte-for-byte. Their SHA-256 values match the expected bindings, and every
substantive audit value was reproduced from the immutable local dry-run package
and ZIP.

## Window 01 Authorization Freeze

The fixed Window 01 roster is now frozen exactly to campaign ordinals 1 through
10. The roster contains nine calibration-role identities and one
evaluation-role identity, all copied from the sealed 360-attempt schedule and
campaign identity binding.

```text
WINDOW_NUMBER=1
WINDOW_FIRST_ORDINAL=1
WINDOW_LAST_ORDINAL=10
WINDOW_ATTEMPT_COUNT=10
WINDOW_01_IDENTITY_BINDING=PASS_10_OF_10
WINDOW_01_ORDER_BINDING=PASS_ORDINALS_1_THROUGH_10
WINDOW_01_SAFETY_GATES=22/22
WINDOW_01_NEGATIVE_FIXTURES=94/94
WINDOW_01_CHECKSUMS=18/18

WINDOW_01_FREEZE_PAYLOAD_ROOT_SHA256=dd831c888271face8ee7bd99aec03ea19aecf836c8f4c1576ff74cfbe215c433
WINDOW_01_FREEZE_MANIFEST_SHA256=7e137f959cf8b2b8db195bc4a9f7952f66b2a1d2d5770be427ef8b8b554d47ae
WINDOW_01_AUTHORIZATION_ARTIFACT_SHA256=ea5ca1fd73b1f1378a6924a230f8c9b8a15d7bd18b03fe537bfc4521a3347a6d
WINDOW_01_IDENTITY_ROSTER_SHA256=fc56462e156c9814d433e66a4c761eb7f11444260a14953c19c25669837e0aed
WINDOW_01_VALIDATION_REPORT_SHA256=a3615a11a2a7ed138b120427b5737a17d3da26422e6bbb659d768085eb46edd3
WINDOW_01_SHA256SUMS_SHA256=4d734dd9ae76b9cf0d5e828464de1c799408f2437ef18c767058d3b3c6838641
WINDOW_01_AUDIT_ZIP_SHA256=8e3c2cf93f3d00de70a27635381507239ea0012827876466b63a820533620feb
ARCHIVE_REOPEN_AND_REHASH=PASS
ARCHIVE_VERIFICATION_WORKSPACE_REMOVED=yes

WINDOW_01_EXECUTION_AUTHORIZED=false
WINDOW_01_ATTEMPTS_AUTHORIZED=0
WINDOW_01_ATTEMPTS_EXECUTED=0/10
CAMPAIGN_ATTEMPTS_EXECUTED=0/360
CAMPAIGN_IDENTITIES_CONSUMED=0
CAMPAIGN_OUTPUT_ROOT_CREATED=no
SCIENTIFIC_ENDPOINTS_COMPUTED=no
```

The freeze requires a separate future whole-window authorization and fresh
consent before each attempt. It allows no automatic first start, next-attempt
transition, retry, resume, replacement, identity reuse, outcome-based
continuation, optional stopping or Window 02 transition. No attempt execution
phrase exists in this layer.

## Window 01 Independent Audit and Package Dry Run

The independent Window 01 authorization-freeze audit attachments were mounted
locally and ingested byte-for-byte. Their declared ZIP, payload-root, manifest,
checksum, roster and policy values were reproduced against the immutable local
freeze before the package dry run was built.

```text
INDEPENDENT_WINDOW_01_FREEZE_AUDIT=PASS
ATTACHMENT_BYTES_LOCALLY_MOUNTED=yes
LOCAL_WINDOW_01_FREEZE_BYTE_REVALIDATION=PASS
INDEPENDENT_AUDIT_JSON_SHA256=9548a1a49c071180e4b79a262e65554688f1c483d65fe95b351b6cc8919d64df
INDEPENDENT_AUDIT_TEXT_SHA256=7516310bbd9b4aa1bd11bfae6d00f244bc5aa9e84f45e247c2bae73610f92ab5
WINDOW_01_FREEZE_AUDIT_ZIP_SHA256=8e3c2cf93f3d00de70a27635381507239ea0012827876466b63a820533620feb
```

The derived package contains pure validators, contract definitions and
synthetic negative fixtures only. It has no transition writer, no attempt-start
authority and no campaign output path.

```text
WINDOW_01_PACKAGE_DRY_RUN=PASS
PACKAGE_PAYLOAD_ROOT_SHA256=9d6aed4c344a1b18b67557ba3263db255d96c6e901d8260d3c9e67ec10fb7ba3
PACKAGE_MANIFEST_SHA256=29ebb676e6a3e9499bd7cb9296dcfdbac50e8520c2a9eb134fff30dde263316d
DRY_RUN_VALIDATION_REPORT_SHA256=ea145703e9b52ea6e1f28c6a7677e43f4f8af92ba30d391af31a9fa690458e3e
SHA256SUMS_SHA256=ba3cc3b173f932edb3239dc93a38bbed7a4cd80df63f68d47cb97e9aa0574890
AUDIT_EXPORT_ZIP_SHA256=373a42f1c38d674455c5af82fd1a5e84ce5c9ef35c0f87d0ffecf6fa41162963

MANIFEST_FILES=25/25
CHECKSUMS=26/26
NEGATIVE_FIXTURES=142/142
SAFETY_GATES=22/22
ARCHIVE_REOPEN_AND_REHASH=PASS
ARCHIVE_VERIFICATION_WORKSPACE_REMOVED=yes

DRY_RUN_ONLY=true
WINDOW_01_EXECUTION_ALLOWED=false
WINDOW_01_EXECUTION_AUTHORIZED=false
WINDOW_01_ATTEMPTS_AUTHORIZED=0
WINDOW_01_ATTEMPTS_EXECUTED=0/10
CAMPAIGN_ATTEMPTS_EXECUTED=0/360
CAMPAIGN_IDENTITIES_CONSUMED=0
CAMPAIGN_OUTPUT_ROOT_CREATED=no
SCIENTIFIC_ENDPOINTS_COMPUTED=no
```

The read-only environment observation is labeled
`NOT_FUTURE_EXECUTION_EVIDENCE`. It cannot establish future power, sync,
process, storage or operator-consent readiness.

## Window 01 Fixture Coverage Audit And Repair

The independently produced package audit was ingested byte-for-byte. It
confirmed archive integrity and the non-execution state, but found that only
55 of the 142 reported negative fixtures invoked included validator logic.
The remaining 87 records assigned their decisions declaratively, below the
frozen minimum of 100 executable fixtures.

```text
WINDOW_01_PACKAGE_DRY_RUN_INDEPENDENT_AUDIT=EVIDENCE_INSUFFICIENT
REPORTED_NEGATIVE_FIXTURE_RECORDS=142
VALIDATOR_BACKED_FIXTURES=55
DECLARATION_ONLY_FIXTURES=87
REQUIRED_EXECUTABLE_FIXTURES=100
FIRST_BLOCKING_INVARIANT=NEGATIVE_FIXTURE_EXECUTION_COVERAGE_BELOW_REQUIRED_MINIMUM

INDEPENDENT_AUDIT_JSON_SHA256=b3eeba525e72c7b138ec668685c450764706d0e0b4ac73d0020490a99bdbc01f
INDEPENDENT_AUDIT_TEXT_SHA256=0908449fc14e310c19e791ec8e20cfda74c20055a9e985e25426143d30fbaf1d
```

The predecessor package remains byte-identical negative methodological
evidence. A separate additive repair now invokes pure validator functions for
every counted fixture and records each callable, canonical input hash, returned
decision and return hash.

```text
WINDOW_01_PACKAGE_DRY_RUN_FIXTURE_COVERAGE_REPAIR=PASS_LOCAL_AWAITING_INDEPENDENT_AUDIT
EXECUTABLE_NEGATIVE_FIXTURES=160
DECLARATION_ONLY_FIXTURES=0
NEGATIVE_FIXTURES=160/160
FIXTURE_EXECUTION_COUNT=0
FIXTURE_IDENTITY_CONSUMPTION_COUNT=0
CHECKSUMS=16/16
ARCHIVE_MEMBERS=17/17

PACKAGE_PAYLOAD_ROOT_SHA256=00edd648c1b64c29bea7d4113bad373b3f05372ffc8a14eb23494a19fa22b5ab
PACKAGE_MANIFEST_SHA256=649bcec38e1346894a995096edb7991d9251624d20753b4b37e4536f81ea3285
VALIDATION_REPORT_SHA256=589398a280616a6073173f0afdd8ec39551b6cc91a95942f82c10f98f673562b
SHA256SUMS_SHA256=e2cfdfc54cef616d2ab5bb54590386b07b9326aa37c5c0904f916b90b12b5aee
AUDIT_EXPORT_ZIP_SHA256=d0d58c01580810efbdaa5441edf58f4c6a5a19511c1ea69ed45feed11244d69c
ARCHIVE_REOPEN_AND_REHASH=PASS
ARCHIVE_VERIFICATION_WORKSPACE_REMOVED=yes
DETERMINISTIC_REBUILD=PASS
```

This is a local repair PASS, not yet an independent audit PASS. Window 01
execution remains unauthorized and blocked.

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
A18_44_V0_1_OFFLINE_ACQUISITION_CAMPAIGN_WINDOW_01_PACKAGE_DRY_RUN_FIXTURE_COVERAGE_REPAIR_INDEPENDENT_AUDIT_ONLY
```

This next stage may independently audit only the additive repair package. It
must not authorize Window 01, start ordinal 1, consume an identity, create
campaign output, infer readiness from dry-run probes or compute a scientific
endpoint.

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

## Window 01 Authorization And Fresh Safety Freeze

The repaired Window 01 dry-run package received an independent byte audit PASS. The attached JSON and text were ingested byte-for-byte from the locally mounted files:

```text
INDEPENDENT_FIXTURE_COVERAGE_REPAIR_AUDIT=PASS
AUDIT_JSON_SHA256=a2dc8e788a0e6cecf8685556524ffbe3dde8cc32099440ff2f38f20360bed79d
AUDIT_TEXT_SHA256=f738758fc3f2c2b75658f1d1b91148892ffbdeb5112e8a3745ea7b9a7a102791
AUDITED_ARCHIVE_SHA256=d0d58c01580810efbdaa5441edf58f4c6a5a19511c1ea69ed45feed11244d69c
EXECUTABLE_NEGATIVE_FIXTURES=160/160
DECLARATION_ONLY_FIXTURES=0
FIXTURE_EXECUTION_COUNT=0
FIXTURE_IDENTITY_CONSUMPTION_COUNT=0
```

The predecessor independent audit `EVIDENCE_INSUFFICIENT` finding remains immutable negative methodological evidence. The later repair and PASS audit are additive layers and do not rewrite it.

The future Window 01 authorization and fresh physical-safety attestation policy is now frozen:

```text
FREEZE_STATUS=PASS
FREEZE_PAYLOAD_ROOT_SHA256=a560a539b4b1bc433d5dff88820c46cc530dcd80ba1bf517098d926c1491d596
FREEZE_MANIFEST_SHA256=882af148dc029ee1bce8fafb928d8b92236907661fdea16a618e0e78e24af484
SHA256SUMS_SHA256=5f2dcd12b28f7423154feb35810cadd06feb739b9a848f5592350c91adb43783
AUDIT_EXPORT_ZIP_SHA256=7df6d74f0cb764c4ed3acf3c858430037beb8bf0a7ed8452b48ca5e1e6a6fdda
FRESH_SAFETY_ATTESTATION_CONTRACT=PASS
WHOLE_WINDOW_AUTHORIZATION_CONTRACT=PASS
PER_ATTEMPT_CONSENT_CONTRACT=PASS
```

Fresh consent must bind the exact session, reset identity, campaign ordinal, current Window 01 authorization hash and current physical-safety snapshot hash. Any gate change invalidates consent. Historical and current read-only observations are `NOT_FUTURE_EXECUTION_EVIDENCE`.

```text
WINDOW_01_EXECUTION_ALLOWED=false
WINDOW_01_EXECUTION_AUTHORIZED=false
WINDOW_01_ATTEMPTS_AUTHORIZED=0
WINDOW_01_ATTEMPTS_EXECUTED=0/10
CAMPAIGN_ATTEMPTS_EXECUTED=0/360
CAMPAIGN_IDENTITIES_CONSUMED=0
CAMPAIGN_OUTPUT_ROOT_CREATED=no
ATTEMPT_START_PHRASE_CREATED=no
SCIENTIFIC_ENDPOINTS_COMPUTED=no
```

Exact next allowed stage:

```text
A18_44_V0_1_OFFLINE_ACQUISITION_CAMPAIGN_WINDOW_01_EXECUTION_AUTHORIZATION_AND_FRESH_PHYSICAL_SAFETY_ATTESTATION_HASH_BOUND_ENABLEMENT_AND_DRY_RUN_VALIDATION_ONLY
```

That stage remains dry-run only. It may not authorize or start ordinal 1, consume an identity, create campaign output or compute a scientific endpoint.

## Window 01 Authorization And Safety Hash-Bound Dry Run

The authorization/fresh-safety governance freeze received an independent byte audit PASS. Its attached JSON and text were ingested byte-for-byte and revalidated locally:

```text
INDEPENDENT_AUTHORIZATION_SAFETY_FREEZE_AUDIT=PASS
AUDIT_JSON_SHA256=b534ea611a0278173503f87e5ac3984fa65f729e8a4dfee9029cd07cdf8c1dca
AUDIT_TEXT_SHA256=f9a3dd24d71aaa7156954aaa1883a0638c01837a236253b200f532618e84f819
AUDITED_FREEZE_ARCHIVE_SHA256=7df6d74f0cb764c4ed3acf3c858430037beb8bf0a7ed8452b48ca5e1e6a6fdda
ARCHIVE_MEMBERS=25/25
STRICT_JSON=18/18
SHA256SUMS=24/24
MANIFEST_FILES=23/23
GOVERNANCE_FIXTURES=81/81
```

The new additive hash-bound package validates synthetic samples only. Every counted negative fixture invoked the included pure validator and reproduced its canonical input and return hashes:

```text
WINDOW_01_HASH_BOUND_ENABLEMENT_DRY_RUN=PASS
EXECUTABLE_NEGATIVE_FIXTURES=213
DECLARATION_ONLY_FIXTURES=0
NEGATIVE_FIXTURES=213/213
POSITIVE_CONTROLS=6/6
CHECKSUMS=34/34
STRICT_JSON=23/23
DETERMINISTIC_FILE_SET=36/36
DETERMINISTIC_BYTE_DIFFS=0

PACKAGE_PAYLOAD_ROOT_SHA256=241492701e4dcc5026e7755a5eacb2a4f2afc72e11ef2640fb3909784bc46083
PACKAGE_MANIFEST_SHA256=55f7bbf7372e2ee5ed5016cd6e01120b30145e951a6e7f695d74574137369f51
SHA256SUMS_SHA256=54abcd410a35b58077993247dcd0d756d366a62751dc3b4708cc1bde4cab770e
AUDIT_EXPORT_ZIP_SHA256=0c563c8dfb10aea125b6b72948521a2254859a89452bdac75690b3f7bca2b063
```

All synthetic samples are explicitly non-authoritative and carry `NOT_FUTURE_EXECUTION_EVIDENCE`. The package contains no capable execution phrase, network or subprocess path, attempt directory, miner launch, pool contact, outcome inspection or endpoint calculation.

```text
WINDOW_01_EXECUTION_ALLOWED=false
WINDOW_01_EXECUTION_AUTHORIZED=false
WINDOW_01_ATTEMPTS_AUTHORIZED=0
WINDOW_01_ATTEMPTS_EXECUTED=0/10
CAMPAIGN_EXECUTION_AUTHORIZED=false
AUTHORIZATION_CONSUMED=false
CAMPAIGN_ATTEMPTS_EXECUTED=0/360
CAMPAIGN_IDENTITIES_CONSUMED=0
CAMPAIGN_OUTPUT_ROOT_CREATED=no
ATTEMPT_START_PHRASE_CREATED=no
SCIENTIFIC_ENDPOINTS_COMPUTED=no
```

Exact next allowed stage:

```text
A18_44_V0_1_OFFLINE_ACQUISITION_CAMPAIGN_WINDOW_01_WHOLE_WINDOW_AUTHORIZATION_ARTIFACT_FREEZE_ONLY
```

That next stage requires separate operator authorization. It may freeze a whole-window authorization artifact but must not start ordinal 1 or consume a campaign identity automatically.
