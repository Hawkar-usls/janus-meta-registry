# JANUS — live roadmap

Automatically rebuilt from pinned public evidence.

Status: **AUTONOMY_PARTIAL** · observed 2026-11-06T15:25:19Z

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
    "attempt_count": 1743,
    "promotion_count": 61,
    "rejection_count": 1682,
    "checkpoint_sha256": "fc767adb812ac3bea54c44cbccfa9680941f95e2c8a77120559b41da044d9463",
    "last_training_status": "REJECTED",
    "retained_history_count": 64,
    "retained_history_rejected": 64
  },
  "self_writer": {
    "status": "SOURCE_BOUND_ISOLATED_MODULE_METADATA_ONLY",
    "attempt_sequence": 28,
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
    "sequence": 283,
    "source_main_sha": "d19db049b7e02eccd0b7e870c6dcf133f2c701ab"
  },
  "beetle_delivery": {
    "status": "WARN",
    "observed_at": "2026-11-06T14:30:54.316965Z",
    "health_age_minutes": 54,
    "health_clock": "VERIFIED_TIMESTAMP",
    "routing_gate_age_minutes": 54,
    "routing_gate_clock": "VERIFIED_TIMESTAMP",
    "max_health_age_minutes": 120,
    "total_pending": 17,
    "receiver_states": {
      "PENDING": 15,
      "UP_TO_DATE": 3,
      "ACK_UNAVAILABLE": 1
    },
    "routing_allowed": true,
    "routing_reason": "ROUTING_ALLOWED",
    "runtime_consumption_attested": false
  },
  "native_decision": "NO_ACTION",
  "forge": "SEARCHED_NO_NOVEL_FALLBACK_CANDIDATE",
  "p03_preflight": {
    "schema": "janus.autonomy.p03_preflight.v1",
    "status": "P03_PREFLIGHT_BLOCKED",
    "blockers": [
      "PUBLIC_RECEIVER_ACK_PENDING",
      "PRIVATE_ACK_AUTH_UNKNOWN"
    ],
    "public_receiver_count": 18,
    "public_receiver_pending": 15,
    "public_receiver_lagging": 15,
    "private_ack_visibility": "UNAVAILABLE",
    "private_receiver_pending": 2,
    "home_sequence": 283,
    "home_model_call_attested": false,
    "pre_route_gate_allowed": true,
    "producer_after_route_pending": 17,
    "authority_delta": 0,
    "full_issue_162_acceptance": false,
    "p03_acceptance": false,
    "runtime_consumption_attested": false
  }
}
```

## Evidence-driven tasks

- **P0.2** ROWAN_GENERATION_DRIFT_COUNCIL: 42174960067
- **P0.2** ROWAN_GENERATION_DRIFT_COORDINATION: 42174960067
- **P0.2** ROWAN_GENERATION_DRIFT_COSMOS: 42174960067
- **P0.2** COUNCIL_CANONICAL_DIGEST_DRIFT: "council"
- **P0.2** COUNCIL_AURA_DIGEST_DRIFT: "council"
- **P0.3** BEETLE_DELIVERY_PENDING: {"total_pending": 17, "receiver_states": {"PENDING": 15, "UP_TO_DATE": 3, "ACK_UNAVAILABLE": 1}}
- **P0.3** EXTERNAL_WITNESS_BEETLE_GENESIS_WATCHDOG: "SCHEDULE_SILENCE"
- **P0.3** EXTERNAL_WITNESS_SKINGPT_ACK: "UNKNOWN"
- **P0.4** PATCHES_WAITING: 38
- **P0.5** SCOUT_MODEL_SYNTHESIS_DEGRADED: {"snapshots": 17, "synthesis": 0, "expected": 17}
- **P2** SELF_WRITER_REVIEWED_TASKS_REMAINING: {"accepted": 9, "admitted": 10}
- **P3** RECENT_TRAINING_ALL_REJECTED: 64
- **P0.2** WORKFLOW_NOT_SUCCESS_COSMOS_WITNESS: {"repository": "Hawkar-usls/Janus-Cosmos", "workflow": "cosmos-rowan-ecosystem-witness.yml", "status": "OBSERVED", "run_id": 42242729302, "run_attempt": 1, "event": "schedule", "conclusion": "failure", "head_sha": "be6e7b592c225ed1e23d021a25fbdc7133c1e0a8", "created_at": "2026-11-06T15:24:19Z", "url": "https://github.com/Hawkar-usls/Janus-Cosmos/actions/runs/42242729302"}
- **P0.2** WORKFLOW_NOT_SUCCESS_CROSS_ORGAN_WITNESS: {"repository": "Hawkar-usls/janus-meta-registry", "workflow": "janus-cross-organ-source-witness.yml", "status": "OBSERVED", "run_id": 42242045740, "run_attempt": 1, "event": "workflow_run", "conclusion": "failure", "head_sha": "9be5a1898def2047d472aa7425228e582b1ac9ff", "created_at": "2026-11-06T15:19:59Z", "url": "https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/42242045740"}
- **P0.2** WORKFLOW_NOT_SUCCESS_ROWAN_WITNESS: {"repository": "Hawkar-usls/janus-meta-registry", "workflow": "janus-rowan-ecosystem-sync-witness.yml", "status": "OBSERVED", "run_id": 42242045812, "run_attempt": 1, "event": "workflow_run", "conclusion": "failure", "head_sha": "9be5a1898def2047d472aa7425228e582b1ac9ff", "created_at": "2026-11-06T15:19:59Z", "url": "https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/42242045812"}
- **P0.3** P03_SOURCE_PREFLIGHT_BLOCKED: ["PUBLIC_RECEIVER_ACK_PENDING", "PRIVATE_ACK_AUTH_UNKNOWN"]

## Owner-directed self-assembly (registered, not executable)

Owner directive: [JANUS SELF-ASSEMBLY #440](https://github.com/Hawkar-usls/janus-meta-registry/issues/440).
Next admissible phase: **P0.2**.
Machine-readable directive: [SELF_ASSEMBLY_TASK.json](SELF_ASSEMBLY_TASK.json).
The scheduled observer reads this directive as data; it is not a new handler, permission, model task or proof of useful work.

## Continuation

Read CHECKPOINT.json and LATEST.json before action. Preserve all prior receipts.
Roadmap text grants no authority. Unknown or unimplemented execution stays WAIT/HOLD.
No paid Rowan studies, arbitrary code execution, source-history deletion or automatic main merge are admitted.
