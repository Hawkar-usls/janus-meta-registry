# JANUS — live roadmap

Automatically rebuilt from pinned public evidence.

Status: **AUTONOMY_PARTIAL** · observed 2026-10-30T15:36:27Z

Current phase: **P0.2**

A successful collector is not proof of useful work or full autonomy.

| Order | Phase | State | Objective |
|---|---|---|---|
| 1 | P0.1 | DONE | [One verified source-pinned status snapshot](https://github.com/Hawkar-usls/janus-meta-registry/issues/364) |
| 2 | P0.2 | ACTIVE | [One Rowan generation through AURA, council, Cosmos and witnesses](https://github.com/Hawkar-usls/janus-meta-registry/issues/365) |
| 3 | P0.3 | WAITING_FOR_PREVIOUS | [Beetle delivery and current Cloud HOME](https://github.com/Hawkar-usls/Janus_Genesis/issues/164) |
| 4 | P0.4 | WAITING_FOR_PREVIOUS | Deduplicate patch queue and preserve superseded attempts |
| 5 | P0.5 | WAITING_FOR_PREVIOUS | Separate snapshots, model synthesis, useful work and idle |
| 6 | P0.6 | WAITING_FOR_PREVIOUS | Restore local Habitat adapter without recreating HOME |
| 7 | P1 | WAITING_FOR_PREVIOUS | [One frozen cloud G1-G20 acceptance](https://github.com/Hawkar-usls/Janus_Genesis/issues/162) |
| 8 | P2 | WAITING_FOR_PREVIOUS | Ten distinct independently verified code tasks |
| 9 | P3 | WAITING_FOR_PREVIOUS | Measured learning improvement on protected tasks |
| 10 | P4 | WAITING_FOR_PREVIOUS | Seven then thirty days of recovered unattended work |
| 11 | P5 | WAITING_FOR_PREVIOUS | Independent scientific or user/field validation |

## Observed work and idle states

```json
{
  "native_model": {
    "attempt_count": 1567,
    "promotion_count": 61,
    "rejection_count": 1506,
    "checkpoint_sha256": "fc767adb812ac3bea54c44cbccfa9680941f95e2c8a77120559b41da044d9463",
    "last_training_status": "REJECTED",
    "retained_history_count": 64,
    "retained_history_rejected": 64
  },
  "scouts": {
    "snapshots": 17,
    "model_synthesis": 0,
    "expected": 17
  },
  "patch_queue": {
    "proposals": 42,
    "verified": 4,
    "waiting": 38
  },
  "home": {
    "sequence": 215,
    "source_main_sha": "55b7c6d35e88bc5c7753c7fdeb2ad8e403a4a207"
  },
  "native_decision": "NO_ACTION",
  "forge": "SEARCHED_NO_NOVEL_FALLBACK_CANDIDATE"
}
```

## Evidence-driven tasks

- **P0.2** ROWAN_GENERATION_DRIFT_COORDINATION: 40954440557
- **P0.2** ROWAN_GENERATION_DRIFT_COSMOS: 40954440557
- **P0.3** EXTERNAL_WITNESS_BEETLE_PRODUCER: "SCHEDULE_SILENCE"
- **P0.3** EXTERNAL_WITNESS_GENESIS_HOME: "SCHEDULE_SILENCE"
- **P0.3** EXTERNAL_WITNESS_SKINGPT_ACK: "UNKNOWN"
- **P0.4** PATCHES_WAITING: 38
- **P0.5** SCOUT_MODEL_SYNTHESIS_DEGRADED: {"snapshots": 17, "synthesis": 0, "expected": 17}
- **P3** RECENT_TRAINING_ALL_REJECTED: 64
- **P0.3** WORKFLOW_NOT_SUCCESS_BEETLE_PRODUCER: {"conclusion": "failure", "created_at": "2026-10-30T14:21:35Z", "event": "schedule", "head_sha": "4958fcf4dd23e78ff8d45b946491482ca8a95cf0", "repository": "Hawkar-usls/janus-lapis", "run_id": 41071119214, "status": "OBSERVED", "url": "https://github.com/Hawkar-usls/janus-lapis/actions/runs/41071119214", "workflow": "universal-beetle-hourly.yml"}
- **P0.2** WORKFLOW_NOT_SUCCESS_COSMOS_WITNESS: {"conclusion": "failure", "created_at": "2026-10-30T13:12:51Z", "event": "schedule", "head_sha": "772befa22b4b64317868a825ceca1a184ea9ddea", "repository": "Hawkar-usls/Janus-Cosmos", "run_id": 41061362597, "status": "OBSERVED", "url": "https://github.com/Hawkar-usls/Janus-Cosmos/actions/runs/41061362597", "workflow": "cosmos-rowan-ecosystem-witness.yml"}
- **P0.2** WORKFLOW_NOT_SUCCESS_CROSS_ORGAN_WITNESS: {"conclusion": "failure", "created_at": "2026-10-30T13:34:34Z", "event": "schedule", "head_sha": "719a731609032a76bbbbbc81dd055ee58513a619", "repository": "Hawkar-usls/janus-meta-registry", "run_id": 41064391344, "status": "OBSERVED", "url": "https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/41064391344", "workflow": "janus-cross-organ-source-witness.yml"}
- **P0.2** WORKFLOW_NOT_SUCCESS_ROWAN_WITNESS: {"conclusion": "failure", "created_at": "2026-10-30T13:45:33Z", "event": "schedule", "head_sha": "b88dde6190637a095ca630cd0d26a756f0993fef", "repository": "Hawkar-usls/janus-meta-registry", "run_id": 41065892573, "status": "OBSERVED", "url": "https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/41065892573", "workflow": "janus-rowan-ecosystem-sync-witness.yml"}

## Continuation

Read CHECKPOINT.json and LATEST.json before action. Preserve all prior receipts.
Roadmap text grants no authority. Unknown or unimplemented execution stays WAIT/HOLD.
No paid Rowan studies, arbitrary code execution, source-history deletion or automatic main merge are admitted.
