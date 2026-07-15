# JANUS Latest Status — Read Before the Migration Handoff

> **Snapshot:** 2026-07-15
>
> **Purpose:** this small additive file supersedes only the *current-stage* portion of `JANUS_CHAT_MIGRATION_HANDOFF.md`. Read it first, then read the full handoff for mission, ethics, lineage, safety and claim boundaries.

## Current A18.44 state

```text
A18_44_OFFLINE_ACQUISITION_HARNESS_SYNTHETIC_VALIDATION=PASS
FIRST_BLOCKING_INVARIANT=NONE
REAL_ACQUISITION_ATTEMPTS_EXECUTED=0
CALIBRATION_EXECUTED=no
EVALUATION_EXECUTED=no
SCIENTIFIC_ENDPOINTS_COMPUTED=no
PRIOR_ART_SEARCHED=no
POOL_CONTACTED=no
MINER_LAUNCHED=no
LIVE_STARTED=no
```

The offline harness passed structural synthetic validation:

- acquisition-plan and fixed-schedule bindings: PASS;
- real acquisition disabled by package default: PASS;
- future authorization hash gate required: PASS;
- state machine, reset contract and single-domain binding: PASS;
- calibration/evaluation role contracts: PASS;
- authoritative horizon writer and exact-exposure ledger: PASS;
- reference integrity and outcome blindness: PASS;
- power-loss fault injection: PASS;
- security/privacy and deterministic rebuild: PASS;
- synthetic fixtures: `40/40`;
- package checksum set: `68/68` as reported by CODEX.

## Key hashes

```text
HARNESS_PACKAGE_SHA256=044ffa766d29f71e91abdff8c178d12d40f16a94a9e865efb21088043cd97a5b
VALIDATION_REPORT_SHA256=03fda803469653807c2c1f5663c7d103d23946cd2abf93d5624054f5cda6f414
PACKAGE_MANIFEST_SHA256=160e8976d3e816202e85a0b5e282cda1e261d97a0e48de7986ddf7f02689991c
SHA256SUMS_SHA256=4018d32b7a67d64607644bbe1c1d9d2b5ea192d31cf35377fa9efef217137de8
```

## Independent verification scope in the recording chat

The following uploaded files were independently byte-hashed and matched their canonical checksum entries:

- `README.md` — `2f855e7f22146585eed9efa729d694c32e158fff67f203df6782aeec3e29523d`;
- `fixtures/A18_44_V0_1_SYNTHETIC_VALIDATION_MATRIX.json` — `6adc5d6ac54c2b92a8279587ed9082c77e90d0f8177cafa32593ea6d0aa7dd27`;
- `manifests/A18_44_V0_1_HARNESS_PACKAGE_MANIFEST.json` — `160e8976d3e816202e85a0b5e282cda1e261d97a0e48de7986ddf7f02689991c`;
- `manifests/REAL_ACQUISITION_POLICY.json` — `7602fbb9a4b93179462642bd251ef64bbd49d7663896639d8a9868d434327181`;
- package `SHA256SUMS.txt` — `4018d32b7a67d64607644bbe1c1d9d2b5ea192d31cf35377fa9efef217137de8`.

Checks performed on the uploaded subset:

```text
JSON_PARSE=3/3
DUPLICATE_JSON_KEYS=0
UTF8_BOM_ABSENT=5/5
LF_ONLY=5/5
UPLOADED_PACKAGE_FILES_MATCH_SHA256SUMS=4/4
SHA256SUMS_SYNTAX=68/68
PACKAGE_MANIFEST_ENTRIES=67
PACKAGE_MANIFEST_VS_SHA256SUMS=67/67
SYNTHETIC_FIXTURE_IDS=40/40 UNIQUE
```

The remaining package bytes were not uploaded into the recording chat. Therefore the complete local `68/68` result and deterministic rebuild remain CODEX/operator-reported, while the subset above is independently byte-verified.

## Hard safety gate preserved

The uploaded real-acquisition policy records:

```text
package_default_mode=SYNTHETIC_VALIDATION_MODE
real_acquisition_allowed=false
future_authorization_sha256=null
pool_endpoints_present=false
miner_launchers_present=false
network_clients_present=false
scientific_endpoint_implementations_present=false
failure_decision=FAIL_CLOSED_BEFORE_SESSION_START
```

Synthetic validation has scientific weight zero. It does not establish A18.44 effectiveness.

## Exact next allowed stage

```text
A18_44_V0_1_OFFLINE_ACQUISITION_PILOT_AUTHORIZATION_FREEZE_ONLY
```

This next stage may freeze a narrowly bounded pilot authorization only. It must not start the pilot automatically.

The future pilot must remain operational validation, not calibration or evaluation evidence. It must not compute `W_H_EXEC`, `Delta_W`, `B_p`, `B_hard`, tail reduction, useful-exposure noninferiority or a hypothesis result.

Until a separate pilot authorization artifact is frozen and exact-hash verified:

```text
REAL_ACQUISITION_ALLOWED=false
REAL_ACQUISITION_ATTEMPTS_AUTHORIZED=0
```

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

After reading this file, continue with `JANUS_CHAT_MIGRATION_HANDOFF.md` and the newest A18.44 registry record.