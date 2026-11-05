# JANUS — live roadmap

Automatically rebuilt from pinned public evidence.

Status: **AUTONOMY_PARTIAL** · observed 2026-11-05T18:55:44Z

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
    "attempt_count": 1726,
    "promotion_count": 61,
    "rejection_count": 1665,
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
    "sequence": 274,
    "source_main_sha": "d19db049b7e02eccd0b7e870c6dcf133f2c701ab"
  },
  "beetle_delivery": {
    "status": "WARN",
    "observed_at": "2026-11-05T11:36:29.988445Z",
    "health_age_minutes": 439,
    "health_clock": "VERIFIED_TIMESTAMP",
    "routing_gate_age_minutes": 439,
    "routing_gate_clock": "VERIFIED_TIMESTAMP",
    "max_health_age_minutes": 120,
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
  "forge": "SEARCHED_NO_NOVEL_FALLBACK_CANDIDATE",
  "p03_preflight": {
    "authority_delta": 0,
    "blockers": [
      "PUBLIC_RECEIVER_ACK_PENDING",
      "PRIVATE_ACK_AUTH_UNKNOWN"
    ],
    "full_issue_162_acceptance": false,
    "home_model_call_attested": false,
    "home_sequence": 274,
    "p03_acceptance": false,
    "pre_route_gate_allowed": true,
    "private_ack_visibility": "UNAVAILABLE",
    "private_receiver_pending": 1,
    "producer_after_route_pending": 14,
    "public_receiver_count": 18,
    "public_receiver_lagging": 13,
    "public_receiver_pending": 13,
    "runtime_consumption_attested": false,
    "schema": "janus.autonomy.p03_preflight.v1",
    "status": "P03_PREFLIGHT_BLOCKED"
  }
}
```

## Evidence-driven tasks

- **P0.2** ROWAN_GENERATION_DRIFT_AURA: 41944469012
- **P0.2** ROWAN_GENERATION_DRIFT_COUNCIL: 41944469012
- **P0.2** ROWAN_GENERATION_DRIFT_COORDINATION: 41944469012
- **P0.2** ROWAN_GENERATION_DRIFT_COSMOS: 41944469012
- **P0.2** AURA_CANONICAL_DIGEST_DRIFT: "aura"
- **P0.2** COUNCIL_CANONICAL_DIGEST_DRIFT: "council"
- **P0.3** BEETLE_DELIVERY_HEALTH_STALE: {"age_minutes": 439, "max_minutes": 120}
- **P0.3** BEETLE_ROUTING_GATE_STALE: {"age_minutes": 439, "max_minutes": 120}
- **P0.3** BEETLE_DELIVERY_PENDING: {"total_pending": 14, "receiver_states": {"PENDING": 13, "UP_TO_DATE": 5, "ACK_UNAVAILABLE": 1}}
- **P0.3** EXTERNAL_WITNESS_BEETLE_GENESIS_WATCHDOG: "SCHEDULE_SILENCE"
- **P0.3** EXTERNAL_WITNESS_SKINGPT_ACK: "UNKNOWN"
- **P0.4** PATCHES_WAITING: 38
- **P0.5** SCOUT_MODEL_SYNTHESIS_DEGRADED: {"snapshots": 17, "synthesis": 0, "expected": 17}
- **P2** SELF_WRITER_REVIEWED_TASKS_REMAINING: {"accepted": 9, "admitted": 10}
- **P3** RECENT_TRAINING_ALL_REJECTED: 64
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
