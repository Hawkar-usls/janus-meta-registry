# JANUS — live roadmap

Automatically rebuilt from pinned public evidence.

Status: **AUTONOMY_PARTIAL** · observed 2026-11-04T08:03:09Z

Current phase: **P0.2**

A successful collector is not proof of useful work or full autonomy.

| Order | Phase | State | Objective |
|---|---|---|---|
| 1 | P0.1 | DONE | [One verified source-pinned status snapshot](https://github.com/Hawkar-usls/janus-meta-registry/issues/364) |
| 2 | P0.2 | ACTIVE_RECHECK | [One Rowan generation through AURA, council, Cosmos and witnesses](https://github.com/Hawkar-usls/janus-meta-registry/issues/365) |
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
    "attempt_count": 1697,
    "promotion_count": 61,
    "rejection_count": 1636,
    "checkpoint_sha256": "fc767adb812ac3bea54c44cbccfa9680941f95e2c8a77120559b41da044d9463",
    "last_training_status": "REJECTED",
    "retained_history_count": 64,
    "retained_history_rejected": 64
  },
  "self_writer": {
    "status": "SOURCE_BOUND_ISOLATED_MODULE_METADATA_ONLY",
    "attempt_sequence": 24,
    "accepted_pure_modules": 9,
    "admitted_task_ceiling": 10,
    "not_native_janus_model": true,
    "trusted_main_auto_update": false,
    "full_p2_acceptance": false
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
    "sequence": 262,
    "source_main_sha": "cd628ee23326d6130cfae6898814775a881c23e4"
  },
  "beetle_delivery": {
    "status": "WARN",
    "observed_at": "2026-11-04T02:44:36.345039Z",
    "total_pending": 13,
    "receiver_states": {
      "PENDING": 12,
      "UP_TO_DATE": 6,
      "ACK_UNAVAILABLE": 1
    },
    "routing_allowed": false,
    "routing_reason": "HOLD_DELIVERY_BACKPRESSURE",
    "runtime_consumption_attested": false
  },
  "native_decision": "NO_ACTION",
  "forge": "SEARCHED_NO_NOVEL_FALLBACK_CANDIDATE"
}
```

## Evidence-driven tasks

- **P0.2** ROWAN_GENERATION_DRIFT_COORDINATION: 41703422824
- **P0.2** ROWAN_GENERATION_DRIFT_COSMOS: 41703422824
- **P0.3** BEETLE_DELIVERY_PENDING: {"total_pending": 13, "receiver_states": {"PENDING": 12, "UP_TO_DATE": 6, "ACK_UNAVAILABLE": 1}}
- **P0.3** BEETLE_ROUTING_HELD: "HOLD_DELIVERY_BACKPRESSURE"
- **P0.3** EXTERNAL_WITNESS_SKINGPT_ACK: "UNKNOWN"
- **P0.4** PATCHES_WAITING: 38
- **P0.5** SCOUT_MODEL_SYNTHESIS_DEGRADED: {"snapshots": 17, "synthesis": 0, "expected": 17}
- **P2** SELF_WRITER_REVIEWED_TASKS_REMAINING: {"accepted": 9, "admitted": 10}
- **P3** RECENT_TRAINING_ALL_REJECTED: 64
- **P0.2** WORKFLOW_NOT_SUCCESS_COSMOS_WITNESS: {"conclusion": "failure", "created_at": "2026-11-04T08:02:28Z", "event": "schedule", "head_sha": "829c1bf3d3d8d050e6a8e9e738c2d49d61703559", "repository": "Hawkar-usls/Janus-Cosmos", "run_attempt": 1, "run_id": 41796463637, "status": "OBSERVED", "url": "https://github.com/Hawkar-usls/Janus-Cosmos/actions/runs/41796463637", "workflow": "cosmos-rowan-ecosystem-witness.yml"}
- **P0.2** WORKFLOW_NOT_SUCCESS_CROSS_ORGAN_WITNESS: {"conclusion": "failure", "created_at": "2026-11-04T06:58:17Z", "event": "schedule", "head_sha": "28775d9040c759419099d7570af3e23890f3a501", "repository": "Hawkar-usls/janus-meta-registry", "run_attempt": 1, "run_id": 41789030091, "status": "OBSERVED", "url": "https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/41789030091", "workflow": "janus-cross-organ-source-witness.yml"}
- **P0.2** WORKFLOW_NOT_SUCCESS_ROWAN_WITNESS: {"conclusion": "failure", "created_at": "2026-11-04T06:53:31Z", "event": "workflow_run", "head_sha": "28775d9040c759419099d7570af3e23890f3a501", "repository": "Hawkar-usls/janus-meta-registry", "run_attempt": 1, "run_id": 41788519989, "status": "OBSERVED", "url": "https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/41788519989", "workflow": "janus-rowan-ecosystem-sync-witness.yml"}

## Owner-directed self-assembly (registered, not executable)

Owner directive: [JANUS SELF-ASSEMBLY #440](https://github.com/Hawkar-usls/janus-meta-registry/issues/440).
Next admissible phase: **P0.2**.
Machine-readable directive: [SELF_ASSEMBLY_TASK.json](SELF_ASSEMBLY_TASK.json).
The scheduled observer reads this directive as data; it is not a new handler, permission, model task or proof of useful work.

## Continuation

Read CHECKPOINT.json and LATEST.json before action. Preserve all prior receipts.
Roadmap text grants no authority. Unknown or unimplemented execution stays WAIT/HOLD.
No paid Rowan studies, arbitrary code execution, source-history deletion or automatic main merge are admitted.
