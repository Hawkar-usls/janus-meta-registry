# JANUS — live roadmap

Automatically rebuilt from pinned public evidence.

Status: **AUTONOMY_PARTIAL** · observed 2026-11-01T08:11:28Z

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
    "attempt_count": 1628,
    "promotion_count": 61,
    "rejection_count": 1567,
    "checkpoint_sha256": "fc767adb812ac3bea54c44cbccfa9680941f95e2c8a77120559b41da044d9463",
    "last_training_status": "REJECTED",
    "retained_history_count": 64,
    "retained_history_rejected": 64
  },
  "self_writer": {
    "status": "SOURCE_BOUND_ISOLATED_MODULE_METADATA_ONLY",
    "attempt_sequence": 17,
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
    "sequence": 233,
    "source_main_sha": "cd628ee23326d6130cfae6898814775a881c23e4"
  },
  "beetle_delivery": {
    "status": "WARN",
    "observed_at": "2026-11-01T01:30:17.476589Z",
    "total_pending": 14,
    "receiver_states": {
      "PENDING": 13,
      "UP_TO_DATE": 5,
      "ACK_UNAVAILABLE": 1
    },
    "routing_allowed": true,
    "routing_reason": "ROUTING_ALLOWED",
    "runtime_consumption_attested": false
  },
  "native_decision": "NO_ACTION",
  "forge": "SEARCHED_NO_NOVEL_FALLBACK_CANDIDATE"
}
```

## Evidence-driven tasks

- **P0.3** BEETLE_DELIVERY_PENDING: {"total_pending": 14, "receiver_states": {"PENDING": 13, "UP_TO_DATE": 5, "ACK_UNAVAILABLE": 1}}
- **P0.3** EXTERNAL_WITNESS_SKINGPT_ACK: "UNKNOWN"
- **P0.4** PATCHES_WAITING: 38
- **P0.5** SCOUT_MODEL_SYNTHESIS_DEGRADED: {"snapshots": 17, "synthesis": 0, "expected": 17}
- **P2** SELF_WRITER_REVIEWED_TASKS_REMAINING: {"accepted": 9, "admitted": 10}
- **P3** RECENT_TRAINING_ALL_REJECTED: 64
- **P0.2** WORKFLOW_NOT_SUCCESS_CROSS_ORGAN_WITNESS: {"repository": "Hawkar-usls/janus-meta-registry", "workflow": "janus-cross-organ-source-witness.yml", "status": "OBSERVED", "run_id": 41285229179, "run_attempt": 1, "event": "workflow_run", "conclusion": "failure", "head_sha": "7843a945fdba51d9979ddab040dd26edc3894663", "created_at": "2026-11-01T07:33:05Z", "url": "https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/41285229179"}
- **P0.2** WORKFLOW_NOT_SUCCESS_ROWAN_WITNESS: {"repository": "Hawkar-usls/janus-meta-registry", "workflow": "janus-rowan-ecosystem-sync-witness.yml", "status": "OBSERVED", "run_id": 41285229293, "run_attempt": 1, "event": "workflow_run", "conclusion": "failure", "head_sha": "7843a945fdba51d9979ddab040dd26edc3894663", "created_at": "2026-11-01T07:33:05Z", "url": "https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/41285229293"}

## Continuation

Read CHECKPOINT.json and LATEST.json before action. Preserve all prior receipts.
Roadmap text grants no authority. Unknown or unimplemented execution stays WAIT/HOLD.
No paid Rowan studies, arbitrary code execution, source-history deletion or automatic main merge are admitted.
