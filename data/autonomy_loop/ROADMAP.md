# JANUS — live roadmap

Automatically rebuilt from pinned public evidence.

Status: **AUTONOMY_PARTIAL** · observed 2026-11-05T07:30:44Z

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
    "attempt_count": 1719,
    "promotion_count": 61,
    "rejection_count": 1658,
    "checkpoint_sha256": "fc767adb812ac3bea54c44cbccfa9680941f95e2c8a77120559b41da044d9463",
    "last_training_status": "REJECTED",
    "retained_history_count": 64,
    "retained_history_rejected": 64
  },
  "self_writer": {
    "status": "SOURCE_BOUND_ISOLATED_MODULE_METADATA_ONLY",
    "attempt_sequence": 26,
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
    "sequence": 271,
    "source_main_sha": "40c7a0fa025965e162b6dca9047b6654cb674d20"
  },
  "beetle_delivery": {
    "status": "WARN",
    "observed_at": "2026-11-05T03:45:49.032462Z",
    "health_age_minutes": 224,
    "health_clock": "VERIFIED_TIMESTAMP",
    "routing_gate_age_minutes": 224,
    "routing_gate_clock": "VERIFIED_TIMESTAMP",
    "max_health_age_minutes": 120,
    "total_pending": 14,
    "receiver_states": {
      "PENDING": 13,
      "UP_TO_DATE": 5,
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

- **P0.2** ROWAN_GENERATION_DRIFT_COSMOS: 41899410078
- **P0.3** BEETLE_DELIVERY_HEALTH_STALE: {"age_minutes": 224, "max_minutes": 120}
- **P0.3** BEETLE_ROUTING_GATE_STALE: {"age_minutes": 224, "max_minutes": 120}
- **P0.3** BEETLE_DELIVERY_PENDING: {"total_pending": 14, "receiver_states": {"PENDING": 13, "UP_TO_DATE": 5, "ACK_UNAVAILABLE": 1}}
- **P0.3** BEETLE_ROUTING_HELD: "HOLD_DELIVERY_BACKPRESSURE"
- **P0.3** EXTERNAL_WITNESS_SKINGPT_ACK: "UNKNOWN"
- **P0.4** PATCHES_WAITING: 38
- **P0.5** SCOUT_MODEL_SYNTHESIS_DEGRADED: {"snapshots": 17, "synthesis": 0, "expected": 17}
- **P2** SELF_WRITER_REVIEWED_TASKS_REMAINING: {"accepted": 9, "admitted": 10}
- **P3** RECENT_TRAINING_ALL_REJECTED: 64
- **P0.2** WORKFLOW_NOT_SUCCESS_COSMOS_WITNESS: {"conclusion": "failure", "created_at": "2026-11-05T02:49:58Z", "event": "workflow_run", "head_sha": "19d2130bdb5e86f72b73780632424bdd77c44073", "repository": "Hawkar-usls/Janus-Cosmos", "run_attempt": 1, "run_id": 41957725966, "status": "OBSERVED", "url": "https://github.com/Hawkar-usls/Janus-Cosmos/actions/runs/41957725966", "workflow": "cosmos-rowan-ecosystem-witness.yml"}
- **P0.2** WORKFLOW_NOT_SUCCESS_CROSS_ORGAN_WITNESS: {"conclusion": "failure", "created_at": "2026-11-05T07:24:30Z", "event": "schedule", "head_sha": "6d19b66a71f93f61dca140eb02a68ad326154a7b", "repository": "Hawkar-usls/janus-meta-registry", "run_attempt": 1, "run_id": 41987017318, "status": "OBSERVED", "url": "https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/41987017318", "workflow": "janus-cross-organ-source-witness.yml"}
- **P0.2** WORKFLOW_NOT_SUCCESS_ROWAN_WITNESS: {"conclusion": "failure", "created_at": "2026-11-05T06:31:48Z", "event": "workflow_run", "head_sha": "d91e9fa693086504a894a79ab432978fcd942bb9", "repository": "Hawkar-usls/janus-meta-registry", "run_attempt": 1, "run_id": 41981019823, "status": "OBSERVED", "url": "https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/41981019823", "workflow": "janus-rowan-ecosystem-sync-witness.yml"}

## Owner-directed self-assembly (registered, not executable)

Owner directive: [JANUS SELF-ASSEMBLY #440](https://github.com/Hawkar-usls/janus-meta-registry/issues/440).
Next admissible phase: **P0.2**.
Machine-readable directive: [SELF_ASSEMBLY_TASK.json](SELF_ASSEMBLY_TASK.json).
The scheduled observer reads this directive as data; it is not a new handler, permission, model task or proof of useful work.

## Continuation

Read CHECKPOINT.json and LATEST.json before action. Preserve all prior receipts.
Roadmap text grants no authority. Unknown or unimplemented execution stays WAIT/HOLD.
No paid Rowan studies, arbitrary code execution, source-history deletion or automatic main merge are admitted.
