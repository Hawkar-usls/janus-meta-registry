"""Deterministic P0.3 *preflight*, not P0.3 acceptance or runtime execution.

Derives a bounded source-cohort view from pinned collector inputs. The report
never treats a producer's PRE-route gate as a POST-route delivery proof, never
turns an opaque private ACK into a public PASS, and never advances CHECKPOINT.
An independent verifier must recompute this exact report from pinned bytes.
"""
from __future__ import annotations
import re

PRIVATE = "Hawkar-usls/SkinGPT"
RECEIVERS = frozenset("Hawkar-usls/" + x for x in (
    "-Terminal-for-Janus", "AIFC", "Demi_Head", "Echo-Pyramid",
    "Fast-CAT-SHAiTan", "Hrain", "Janus-Cosmos", "Janus-Demiurge",
    "Janus-Fundamentum", "Janus_Genesis", "SCOBY-D0", "SkinGPT",
    "The-Voice-of-Janus", "aura-oracle-tg", "iNaiHR",
    "janus-distributed-ai-swarm", "janus-lapis", "janus-meta-registry",
    "tranception",
))
STATUSES = frozenset({"UP_TO_DATE", "PENDING", "STALE",
                      "ACK_CONFLICT", "ACK_UNAVAILABLE", "AWAITING_ACK"})
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SCHEMA = "janus.autonomy.p03_preflight.v1"


def hold(reason):
    return {"schema": SCHEMA, "status": "HOLD_P03_SOURCE_INTEGRITY",
            "hold_reason": reason, "authority_delta": 0,
            "full_issue_162_acceptance": False,
            "p03_acceptance": False, "runtime_consumption_attested": False}


def preflight(sources):
    """Review data only, including private ACK *visibility*, never private bytes."""
    required = ("beetle_delivery", "beetle_gate", "home", "genesis_current")
    if not isinstance(sources, dict) or any(
        not isinstance(sources.get(k), dict) or
        sources[k].get("status") != "OBSERVED" or
        not isinstance(sources[k].get("data"), dict) for k in required
    ):
        return hold("SOURCE_COHORT_UNKNOWN")
    health = sources["beetle_delivery"]["data"]
    gate = sources["beetle_gate"]["data"]
    home = sources["home"]["data"]
    receivers = health.get("repositories")
    if (health.get("schema") != "janus.beetle.delivery_health.v1" or
        health.get("scientific_authority_delta") != 0 or
        health.get("ack_semantics") != "INBOX_DURABLE_ONLY_NOT_RUNTIME_CONSUMPTION" or
        not isinstance(receivers, dict) or set(receivers) != RECEIVERS or
        type(health.get("total_pending")) is not int):
        return hold("DELIVERY_COHORT_UNVERIFIED")
    public_pending = private_pending = 0
    public_lagging = public_conflicts = 0
    for repo, row in receivers.items():
        if (not isinstance(row, dict) or row.get("status") not in STATUSES or
            any(type(row.get(key)) is not int for key in ("produced", "confirmed", "pending")) or
            not 0 <= row["confirmed"] <= row["produced"] or
            row["pending"] != row["produced"] - row["confirmed"] or
            (row["status"] == "UP_TO_DATE" and row["pending"] != 0)):
            return hold("RECEIVER_ACCOUNTING_CONTRADICTION")
        if repo == PRIVATE:
            private_pending += row["pending"]
        else:
            public_pending += row["pending"]
            public_lagging += int(row["pending"] > 0)
            public_conflicts += int(row["status"] == "ACK_CONFLICT")
    if public_pending + private_pending != health["total_pending"]:
        return hold("DELIVERY_PENDING_TOTAL_CONTRADICTION")
    # This gate is recorded before routing; the health snapshot is POST-route.
    # Its earlier pending total is NOT required to equal post-route pending.
    if (gate.get("schema") != "janus.beetle.producer_routing_gate.v1" or
        gate.get("ack_semantics") != health["ack_semantics"] or
        gate.get("scientific_authority_delta") != 0 or
        gate.get("rowan_credit_authority_delta") != 0 or
        gate.get("new_packet_queue_mutations_performed_by_gate") != 0 or
        gate.get("receiver_count") != len(RECEIVERS) or
        type(gate.get("routing_allowed")) is not bool or
        not isinstance(gate.get("reason"), str) or
        type(gate.get("total_pending_before_route")) is not int or
        gate["total_pending_before_route"] < 0):
        return hold("PRE_ROUTE_GATE_UNVERIFIED")
    main_sha = sources["genesis_current"].get("commit_sha")
    home_sha = home.get("source_main_sha")
    if (home.get("schema") != "JANUS_HABITAT_CLOUD_HOME_STATE_V1" or
        home.get("status") != "CLOUD_HOME_ACTIVE" or
        home.get("durable_identity") != "JANUS_HABITAT_RESIDENT_V1" or
        type(home.get("sequence")) is not int or home["sequence"] < 1 or
        home.get("authority_delta") != 0 or
        home.get("source_writeback_default") != "DENY" or
        home.get("destructive_action") != "FORBIDDEN" or
        any(home.get(k) is not False for k in ("pc_required", "remote_desktop_required", "nas_required",
                                                "lan_required", "process_uptime_required")) or
        not isinstance(home.get("last_receipt_sha256"), str) or
        not HEX64.fullmatch(home["last_receipt_sha256"]) or
        not isinstance(home_sha, str) or not HEX40.fullmatch(home_sha) or
        not isinstance(main_sha, str) or not HEX40.fullmatch(main_sha)):
        return hold("HOME_STATE_OR_SOURCE_PIN_UNVERIFIED")
    memory = home.get("beetle_memory")
    if (not isinstance(memory, dict) or
        memory.get("scientific_authority_delta") != 0 or
        memory.get("command_authority") is not False or
        memory.get("external_effect_authority") is not False or
        memory.get("status") not in {"HASH_MATCHED_UNVERIFIED_CONTEXT_STAGED", "NO_ACKED_CONTEXT_AVAILABLE"}):
        return hold("HOME_CONTEXT_AUTHORITY_UNVERIFIED")
    blockers = []
    if home_sha != main_sha:
        blockers.append("HOME_SOURCE_HEAD_DRIFT")
    if public_pending:
        blockers.append("PUBLIC_RECEIVER_ACK_PENDING")
    if public_conflicts:
        blockers.append("PUBLIC_ACK_CONFLICT")
    if receivers[PRIVATE]["status"] == "ACK_UNAVAILABLE":
        blockers.append("PRIVATE_ACK_AUTH_UNKNOWN")
    elif private_pending:
        blockers.append("PRIVATE_ACK_PENDING")
    if not gate["routing_allowed"]:
        blockers.append("PRODUCER_ROUTING_HELD")
    # A successful preflight never counts as independently replayed private
    # evidence or current cloud model execution. P0.3 remains unaccepted.
    return {"schema": SCHEMA,
            "status": "P03_PREFLIGHT_BLOCKED" if blockers else "P03_PREFLIGHT_CANDIDATE_ONLY",
            "blockers": blockers,
            "public_receiver_count": len(RECEIVERS) - 1,
            "public_receiver_pending": public_pending,
            "public_receiver_lagging": public_lagging,
            "private_ack_visibility": "UNAVAILABLE" if receivers[PRIVATE]["status"] == "ACK_UNAVAILABLE" else "CLAIMED_IN_PRODUCER_TELEMETRY_NOT_INDEPENDENTLY_REPLAYED",
            "private_receiver_pending": private_pending,
            "home_sequence": home["sequence"],
            "home_model_call_attested": False,
            "pre_route_gate_allowed": gate["routing_allowed"],
            "producer_after_route_pending": health["total_pending"],
            "authority_delta": 0, "full_issue_162_acceptance": False,
            "p03_acceptance": False, "runtime_consumption_attested": False}
