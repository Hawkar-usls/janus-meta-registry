"""Source-pinned observation and persistent roadmap; no model-supplied commands."""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import importlib.util
import os
from pathlib import Path
import re
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from datetime import datetime, timezone

SCHEMA = "janus.autonomy.snapshot.v1"
OWNER = "Hawkar-usls"
ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path("data/autonomy_loop")
SHA = re.compile(r"^[0-9a-f]{40}$")
HEX = re.compile(r"^[0-9a-f]{64}$")
MAX_BYTES = 2_000_000
SPECS = {
    "canonical": ("janus-meta-registry", "main", "data/rowan/CANONICAL_STATE.json"),
    "pipeline": ("janus-meta-registry", "main", "data/rowan/health/PIPELINE_STATE.json"),
    "coordination": ("janus-meta-registry", "main", "data/rowan/coordination/LATEST_COORDINATION_STATE.json"),
    "real44": ("janus-meta-registry", "main", "data/integrations/nexus_real44/LATEST.json"),
    "external_witness": ("janus-meta-registry", "main", "data/witness_importer/LATEST.json"),
    "aura": ("aura-oracle-tg", "main", "research/rowan/LATEST_HYPOTHESES.json"),
    "council": ("Janus-Demiurge", "main", "research/rowan/LATEST_COUNCIL.json"),
    "native_model": ("Janus-Demiurge", "main", "janus_model/state/JANUS_MODEL_STATE.json"),
    "native_decision": ("Janus-Demiurge", "main", "janus_model/state/JANUS_LATEST_DECISION.json"),
    "scouts": ("Janus-Demiurge", "main", "scout_swarm/state/SCOUT_SWARM_STATUS-v1.json"),
    "feedback": ("Janus-Demiurge", "main", "janus_model/state/JANUS_VERIFIED_OUTCOME_MEMORY.json"),
    "home": ("Janus_Genesis", "janus/habitat-cloud-state", "state/habitat_cloud_home/STATE.json"),
    "beetle_delivery": ("janus-lapis", "beetle-state", "data/beetle-state/latest_delivery_health.json"),
    "beetle_gate": ("janus-lapis", "beetle-state", "data/beetle-state/latest_routing_gate.json"),
    "genesis_current": ("Janus_Genesis", "main", "protocol/JANUS_REAL44_CLOUD_MATERIALIZATION-v2.0.json"),
    "cosmos": ("Janus-Cosmos", "main", "data/integrations/rowan/LATEST.json"),
    "patch_queue": ("janus-meta-registry", "janus/native-self-memory-modular-organism-v1", "JANUS/PATCHES/INDEX.json"),
    "self_writer_state": ("janus-meta-registry", "janus/autonomous-code-state", "STATE.json"),
    "self_module_index": ("janus-meta-registry", "janus/autonomous-code-state", "MODULE_INDEX.json"),
    "forge": ("Janus-Demiurge", "janus/autonomous-keymaster-lockpick", "janus_model/autonomous-keymaster/KEYMASTER_AUTONOMOUS_FORGE_LATEST.json"),
}
WORKFLOWS = {
    "rowan_witness": ("janus-meta-registry", "janus-rowan-ecosystem-sync-witness.yml"),
    "cross_organ_witness": ("janus-meta-registry", "janus-cross-organ-source-witness.yml"),
    "cosmos_witness": ("Janus-Cosmos", "cosmos-rowan-ecosystem-witness.yml"),
    "beetle_producer": ("janus-lapis", "universal-beetle-hourly.yml"),
    "home_schedule": ("Janus_Genesis", "janus-habitat-cloud-home-v1.yml"),
}
# Admission is fixed in reviewed code, never in issue/model prose.
PHASES = [
    ("P0.1", "One verified source-pinned status snapshot", "https://github.com/Hawkar-usls/janus-meta-registry/issues/364"),
    ("P0.2", "One Rowan generation through AURA, council, Cosmos and witnesses", "https://github.com/Hawkar-usls/janus-meta-registry/issues/365"),
    ("P0.3", "Beetle delivery and current Cloud HOME", "https://github.com/Hawkar-usls/Janus_Genesis/issues/164"),
    ("P0.4", "Deduplicate patch queue and preserve superseded attempts", ""),
    ("P0.5", "Separate snapshots, model synthesis, useful work and idle", ""),
    ("P0.6", "Restore local Habitat adapter without recreating HOME", ""),
    ("P1", "One frozen cloud G1-G20 acceptance", "https://github.com/Hawkar-usls/Janus_Genesis/issues/162"),
    ("P2", "Ten distinct independently verified code tasks", ""),
    ("P3", "Measured learning improvement on protected tasks", ""),
    ("P4", "Seven then thirty days of recovered unattended work", ""),
    ("P5", "Independent scientific or user/field validation", ""),
]

class Hold(ValueError):
    pass

def canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()

def digest(obj):
    return hashlib.sha256(canon(obj)).hexdigest()

def encode(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False).encode() + b"\n"

def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Hold("PUBLIC_API_REDIRECT_DENIED")

class PublicGitHub:
    def __init__(self):
        self.opener = build_opener(NoRedirect())
        self.pins = {}
    def get(self, repo, path):
        allowed = {s[0] for s in SPECS.values()} | {w[0] for w in WORKFLOWS.values()} | {"Hrain", "iNaiHR", "TOPA", "Janus", "janus-lapis"}
        if repo not in allowed or not path.startswith("/") or ".." in path:
            raise Hold("SOURCE_NOT_ALLOWLISTED")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "JANUS-Autonomy-Loop/1"}
        token = os.environ.get("GH_TOKEN", "")
        if token:
            headers["Authorization"] = "Bearer " + token
        req = Request("https://api.github.com/repos/" + OWNER + "/" + repo + path, headers=headers)
        with self.opener.open(req, timeout=25) as response:
            raw = response.read(MAX_BYTES + 1)
        if not raw or len(raw) > MAX_BYTES:
            raise Hold("SOURCE_SIZE_REJECTED")
        return json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(Hold("NONFINITE_JSON")))
    def pin(self, repo, ref):
        key = (repo, ref)
        if key not in self.pins:
            obj = self.get(repo, "/git/ref/heads/" + quote(ref, safe="/"))
            sha = obj.get("object", {}).get("sha")
            if not isinstance(sha, str) or not SHA.fullmatch(sha):
                raise Hold("INVALID_REF_SHA")
            self.pins[key] = sha
        return self.pins[key]
    def raw_file(self, repo, commit, path):
        if not SHA.fullmatch(commit):
            raise Hold("UNPINNED_FILE_READ")
        result = self.get(repo, "/contents/" + quote(path, safe="/") + "?ref=" + commit)
        if result.get("type") != "file" or result.get("encoding") != "base64":
            raise Hold("NOT_A_JSON_FILE")
        raw = base64.b64decode(result.get("content", "").replace("\n", ""), validate=True)
        if not 0 < len(raw) <= MAX_BYTES:
            raise Hold("FILE_SIZE_REJECTED")
        blob_sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if blob_sha != result.get("sha"):
            raise Hold("GIT_BLOB_DIGEST_MISMATCH")
        return raw, hashlib.sha256(raw).hexdigest(), blob_sha
    def file(self, repo, commit, path):
        raw, sha, blob_sha = self.raw_file(repo, commit, path)
        data = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(Hold("NONFINITE_JSON")))
        if not isinstance(data, dict):
            raise Hold("SOURCE_NOT_OBJECT")
        return data, sha, blob_sha

MAX_REPLAY_ATTEMPTS = 16

def verify_workflow_observation(client, repo, obs):
    """Verify exact attempt, including legacy pre-attempt snapshots.

    The unqualified Actions run status can change on retry. Never mutate
    historical evidence to match the newer success/failure.
    """
    rid = obs.get("run_id")
    if type(rid) is not int or rid <= 0:
        raise Hold("INDEPENDENT_WORKFLOW_ID_INVALID")
    expected = {"id": rid, "event": obs.get("event"),
                "conclusion": obs.get("conclusion"), "head_sha": obs.get("head_sha"),
                "created_at": obs.get("created_at"), "html_url": obs.get("url")}
    def matches(actual):
        return all(actual.get(k) == value for k, value in expected.items())
    attempt = obs.get("run_attempt")
    if attempt is not None:
        if type(attempt) is not int or not 1 <= attempt <= MAX_REPLAY_ATTEMPTS:
            raise Hold("INDEPENDENT_WORKFLOW_ATTEMPT_INVALID")
        actual = client.get(repo, "/actions/runs/" + str(rid) +
                            "/attempts/" + str(attempt))
        if (actual.get("run_attempt") != attempt or
            actual.get("status") != "completed" or not matches(actual)):
            raise Hold("INDEPENDENT_WORKFLOW_ATTEMPT_REPLAY_MISMATCH")
        return
    # Historical signed snapshots have no attempt ID. Preserve their
    # original conclusion and find a UNIQUE exact historical occurrence.
    latest = client.get(repo, "/actions/runs/" + str(rid))
    if matches(latest):
        return
    count = latest.get("run_attempt")
    if type(count) is not int or not 1 <= count <= MAX_REPLAY_ATTEMPTS:
        raise Hold("INDEPENDENT_LEGACY_RUN_ATTEMPTS_UNVERIFIABLE")
    candidates = []
    for n in range(1, count + 1):
        old = client.get(repo, "/actions/runs/" + str(rid) + "/attempts/" + str(n))
        if old.get("run_attempt") != n or old.get("id") != rid:
            raise Hold("INDEPENDENT_LEGACY_RUN_ATTEMPT_REBIND")
        if old.get("status") == "completed" and matches(old):
            candidates.append(n)
    if len(candidates) != 1:
        raise Hold("INDEPENDENT_WORKFLOW_REPLAY_MISMATCH")


def collect(client):
    sources = {}
    errors = {}
    # Freeze every ref before any body. One ref cannot silently supply two HEADs.
    for repo, ref, _ in SPECS.values():
        try:
            client.pin(repo, ref)
        except (OSError, ValueError, KeyError) as exc:
            errors[(repo, ref)] = type(exc).__name__
    for name, (repo, ref, path) in SPECS.items():
        info = {"repository": OWNER + "/" + repo, "ref": ref, "path": path}
        try:
            if (repo, ref) in errors:
                raise Hold("REF_UNAVAILABLE")
            sha = client.pin(repo, ref)
            data, raw_sha, blob_sha = client.file(repo, sha, path)
            info.update(status="OBSERVED", commit_sha=sha, content_sha256=raw_sha,
                        blob_sha=blob_sha, data=data)
        except (OSError, ValueError, KeyError) as exc:
            info.update(status="UNKNOWN", error_class=type(exc).__name__)
        sources[name] = info
    workflows = {}
    for name, (repo, workflow) in WORKFLOWS.items():
        info = {"repository": OWNER + "/" + repo, "workflow": workflow}
        try:
            result = client.get(repo, "/actions/workflows/" + workflow +
                                "/runs?branch=main&status=completed&per_page=1")
            runs = result.get("workflow_runs", [])
            if len(runs) != 1:
                raise Hold("NO_COMPLETED_RUN")
            run = runs[0]
            # GitHub can re-run the same run_id; the mutable top-level
            # conclusion may later change. Bind a completed exact ATTEMPT,
            # so an independent verifier replays immutable run evidence.
            attempt = run.get("run_attempt")
            if type(attempt) is not int or not 1 <= attempt <= MAX_REPLAY_ATTEMPTS:
                raise Hold("WORKFLOW_RUN_ATTEMPT_UNPINNED")
            exact = client.get(repo, "/actions/runs/" + str(run["id"]) +
                               "/attempts/" + str(attempt))
            if (exact.get("run_attempt") != attempt or
                exact.get("id") != run["id"] or
                exact.get("status") != "completed" or
                exact.get("event") != run["event"] or
                exact.get("head_sha") != run["head_sha"] or
                exact.get("html_url") != run["html_url"] or
                exact.get("conclusion") != run["conclusion"]):
                # Run-list created_at is the FIRST attempt's timestamp,
                # while exact attempt created_at moves when a run is retried.
                raise Hold("WORKFLOW_ATTEMPT_MOVED_DURING_COLLECTION")
            info.update(status="OBSERVED", run_id=run["id"],
                        run_attempt=attempt, event=exact["event"],
                        conclusion=exact["conclusion"], head_sha=exact["head_sha"],
                        created_at=exact["created_at"], url=exact["html_url"])
        except (OSError, ValueError, KeyError) as exc:
            info.update(status="UNKNOWN", error_class=type(exc).__name__)
        workflows[name] = info
    return sources, workflows

def summarize(sources, workflows, observed_at, code_sha, previous=None, action=None):
    findings = []
    def add(phase, reason, evidence):
        findings.append({"id": phase + ":" + reason, "phase": phase,
                         "reason": reason, "evidence": evidence})
    def data(name):
        source = sources.get(name, {})
        if source.get("status") != "OBSERVED":
            add("P0.1", "SOURCE_UNKNOWN_" + name.upper(), name)
            return {}
        return source.get("data", {})
    d = {name: data(name) for name in SPECS}
    canonical = d["canonical"]
    run = canonical.get("latest_durable_external_run")
    bindings = {
        "canonical": run,
        "aura": d["aura"].get("source", {}).get("upstream_run"),
        "council": d["council"].get("sources", {}).get("meta_registry", {}).get("canonical_run"),
        "coordination": d["coordination"].get("meta_canonical_run"),
        "cosmos": d["cosmos"].get("canonical_rowan_run"),
    }
    valid_run = type(run) is int and run > 0
    if not valid_run:
        add("P0.2", "CANONICAL_RUN_UNKNOWN", bindings)
    for name, actual in bindings.items():
        if not valid_run or actual != run:
            add("P0.2", "ROWAN_GENERATION_DRIFT_" + name.upper(), actual)
    if d["aura"].get("source", {}).get("state_sha256") != digest(canonical):
        add("P0.2", "AURA_CANONICAL_DIGEST_DRIFT", "aura")
    council_meta = d["council"].get("sources", {}).get("meta_registry", {})
    if council_meta.get("sha256") != digest(canonical):
        add("P0.2", "COUNCIL_CANONICAL_DIGEST_DRIFT", "council")
    if d["council"].get("sources", {}).get("aura_oracle", {}).get("packet_sha256") != digest(d["aura"]):
        add("P0.2", "COUNCIL_AURA_DIGEST_DRIFT", "council")
    source_head = sources.get("genesis_current", {}).get("commit_sha")
    if not source_head or d["home"].get("source_main_sha") != source_head:
        add("P0.3", "HOME_SOURCE_HEAD_DIFFERS", d["home"].get("source_main_sha"))
    delivery = d["beetle_delivery"]
    gate = d["beetle_gate"]
    receivers = delivery.get("repositories", {})
    valid_delivery = (delivery.get("schema") == "janus.beetle.delivery_health.v1" and
                      delivery.get("ack_semantics") == "INBOX_DURABLE_ONLY_NOT_RUNTIME_CONSUMPTION" and
                      isinstance(receivers, dict) and bool(receivers) and
                      all(isinstance(row, dict) and type(row.get("pending")) is int and row["pending"] >= 0
                          for row in receivers.values()) and
                      type(delivery.get("total_pending")) is int and
                      delivery["total_pending"] == sum(row["pending"] for row in receivers.values()))
    if not valid_delivery:
        add("P0.3", "BEETLE_DELIVERY_HEALTH_UNVERIFIED", "schema_or_pending_totals")
    receiver_states = {}
    if valid_delivery:
        for row in receivers.values():
            status = row.get("status", "UNKNOWN")
            status = status if isinstance(status, str) and status in {"UP_TO_DATE", "PENDING", "STALE", "ACK_CONFLICT", "ACK_UNAVAILABLE", "AWAITING_ACK"} else "UNKNOWN"
            receiver_states[status] = receiver_states.get(status, 0) + 1
        if delivery["total_pending"]:
            add("P0.3", "BEETLE_DELIVERY_PENDING", {"total_pending": delivery["total_pending"],
                                                    "receiver_states": receiver_states})
    valid_gate = (gate.get("schema") == "janus.beetle.producer_routing_gate.v1" and
                  type(gate.get("routing_allowed")) is bool and
                  gate.get("ack_semantics") == "INBOX_DURABLE_ONLY_NOT_RUNTIME_CONSUMPTION")
    if not valid_gate:
        add("P0.3", "BEETLE_ROUTING_GATE_UNVERIFIED", "schema_or_routing_decision")
    elif not gate["routing_allowed"]:
        add("P0.3", "BEETLE_ROUTING_HELD", gate.get("reason", "UNKNOWN"))
    for line, info in d["external_witness"].get("line_states", {}).items():
        if info.get("status") not in ("SCHEDULE_OK", "ANCHOR_MATCH"):
            add("P0.3", "EXTERNAL_WITNESS_" + line.upper(), info.get("status"))
    queue = d["patch_queue"]
    waiting = sum(p.get("status") == "WAITING_FOR_TARGET_BRANCH" for p in queue.get("proposals", []))
    if waiting:
        add("P0.4", "PATCHES_WAITING", waiting)
    scouts = d["scouts"]
    synthesis = scouts.get("agents_model_synthesis_ok")
    expected = scouts.get("agents_expected")
    if type(synthesis) is not int or type(expected) is not int or synthesis < expected:
        add("P0.5", "SCOUT_MODEL_SYNTHESIS_DEGRADED",
            {"snapshots": scouts.get("agents_snapshot_observed"), "synthesis": synthesis, "expected": expected})
    # A self-generated module is observable only as source-bound metadata.
    # It is not evidence of adoption by Genesis or of full P2 autonomy.
    writer = d["self_writer_state"]
    catalog = d["self_module_index"]
    accepted = writer.get("accepted")
    modules = catalog.get("modules")
    unsigned_catalog = {k: v for k, v in catalog.items() if k != "index_sha256"}
    valid_modules = (
        writer.get("schema") == "janus.autonomous_coder.state.v1" and
        writer.get("authority_delta") == 0 and
        writer.get("universal_code_writer_proven") is False and
        type(writer.get("sequence")) is int and writer["sequence"] >= 0 and
        isinstance(accepted, dict) and len(accepted) <= 10 and
        catalog.get("schema") == "janus.autonomous_coder.module_index.v1" and
        catalog.get("index_sha256") == digest(unsigned_catalog) and
        catalog.get("state_sequence") == writer.get("sequence") and
        catalog.get("accepted_count") == len(accepted) and
        catalog.get("installation_scope") == "ISOLATED_STATE_BRANCH_ONLY" and
        catalog.get("model_authorship") == "EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS" and
        catalog.get("runtime_auto_import") is False and
        catalog.get("new_permissions") == 0 and
        catalog.get("authority_delta") == 0 and
        catalog.get("full_issue_162_acceptance") is False and
        isinstance(modules, dict) and set(modules) == set(accepted) and
        sources.get("self_writer_state", {}).get("commit_sha") ==
        sources.get("self_module_index", {}).get("commit_sha"))
    if valid_modules:
        for task, entry in accepted.items():
            row = modules[task]
            if (not isinstance(entry, dict) or not isinstance(row, dict) or
                row.get("module_id") != "janus.pure." + task + ".v1" or
                row.get("path") != "self_modules/" + task + "/module.py" or
                row.get("manifest_path") != "self_modules/" + task + "/MODULE.json" or
                row.get("source_sha256") != entry.get("source_sha256") or
                row.get("receipt_sha256") != entry.get("receipt_sha256") or
                row.get("run_id") != entry.get("run_id") or
                not isinstance(row.get("module_manifest_sha256"), str) or
                not HEX.fullmatch(row["module_manifest_sha256"])):
                valid_modules = False
                break
    if not valid_modules:
        add("P2", "SELF_MODULE_CATALOG_UNVERIFIED", "source_binding_or_schema")
    elif len(modules) < 10:
        add("P2", "SELF_WRITER_REVIEWED_TASKS_REMAINING",
            {"accepted": len(modules), "admitted": 10})
    self_writer_metrics = {
        "status": "SOURCE_BOUND_ISOLATED_MODULE_METADATA_ONLY" if valid_modules else "UNVERIFIED",
        "attempt_sequence": writer.get("sequence") if valid_modules else None,
        "accepted_pure_modules": len(modules) if valid_modules else None,
        "admitted_task_ceiling": 10,
        "not_native_janus_model": True,
        "trusted_main_auto_update": False,
        "full_p2_acceptance": False}
    model = d["native_model"]
    history = model.get("history", [])
    rejected = sum(row.get("status") == "REJECTED" for row in history)
    if len(history) >= 16 and rejected == len(history):
        add("P3", "RECENT_TRAINING_ALL_REJECTED", len(history))
    for name, obs in sorted(workflows.items()):
        if obs.get("status") != "OBSERVED" or obs.get("conclusion") != "success":
            phase = "P0.3" if name in ("beetle_producer", "home_schedule") else "P0.2"
            add(phase, "WORKFLOW_NOT_SUCCESS_" + name.upper(), obs)
    completed = dict((previous or {}).get("accepted_phases", {}))
    if set(completed) - {p[0] for p in PHASES}:
        raise Hold("UNKNOWN_ACCEPTANCE_PHASE")
    if set(completed) - {"P0.1", "P0.2"}:
        raise Hold("UNIMPLEMENTED_PHASE_ACCEPTANCE")
    if "P0.2" in completed and ("P0.1" not in completed or completed["P0.2"].get("status") != "PASS_SOURCE_COHORT_ONLY"):
        raise Hold("INVALID_PHASE_ACCEPTANCE")
    if completed and completed["P0.1"].get("status") != "PASS_STATUS_CAPTURE_ONLY":
        raise Hold("INVALID_PHASE_ACCEPTANCE")
    current = next((p[0] for p in PHASES if p[0] not in completed), None)
    # A historical PASS is evidence for its exact Rowan generation only.
    # Even if all current consumers have converged, P0.2 remains in recheck
    # until a fresh independently replayed cohort is admitted to CHECKPOINT.
    historical_run = completed.get("P0.2", {}).get("canonical_run")
    reopened = "P0.2" in completed and (
        historical_run != run or any(
            f["phase"] == "P0.2" and
            ("GENERATION_DRIFT" in f["reason"] or "DIGEST_DRIFT" in f["reason"])
            for f in findings))
    if reopened:
        current = "P0.2"
    plan = [{"order": i + 1, "phase": pid, "objective": objective, "issue": issue,
             "state": "ACTIVE_RECHECK" if pid == current and pid in completed else "DONE" if pid in completed else "ACTIVE" if pid == current else "WAITING_FOR_PREVIOUS",
             "tasks": [f for f in findings if f["phase"] == pid]}
            for i, (pid, objective, issue) in enumerate(PHASES)]
    model_metrics = {key: model.get(key) for key in ("attempt_count", "promotion_count", "rejection_count", "checkpoint_sha256", "last_training_status")}
    model_metrics.update(retained_history_count=len(history), retained_history_rejected=rejected)
    record = {
        "schema": SCHEMA, "observed_at_utc": observed_at, "code_sha": code_sha,
        "ecosystem_status": "AUTONOMY_PARTIAL", "full_issue_162_acceptance": False,
        "authority": {"delta": 0, "model_output_is_authority": False, "source_writeback_default": "DENY",
                      "paid_rowan_jobs": 0, "scientific_claim_promotion": False},
        "source_scope": "PUBLIC_STATUS_METADATA_ONLY", "sources": {
            key: {k: v for k, v in val.items() if k != "data"} for key, val in sources.items()},
        "workflows": workflows, "rowan_generations": bindings, "findings": findings,
        "metrics": {"native_model": model_metrics,
                    "self_writer": self_writer_metrics,
                    "scouts": {"snapshots": scouts.get("agents_snapshot_observed"), "model_synthesis": synthesis, "expected": expected},
                    "patch_queue": {"proposals": queue.get("proposal_count"), "verified": queue.get("verified_count"), "waiting": waiting},
                    "home": {"sequence": d["home"].get("sequence"), "source_main_sha": d["home"].get("source_main_sha")},
                    "beetle_delivery": {"status": delivery.get("status") if valid_delivery else "UNVERIFIED",
                                        "observed_at": delivery.get("at"),
                                        "total_pending": delivery.get("total_pending") if valid_delivery else None,
                                        "receiver_states": receiver_states,
                                        "routing_allowed": gate.get("routing_allowed") if valid_gate else None,
                                        "routing_reason": gate.get("reason") if valid_gate else "UNVERIFIED",
                                        "runtime_consumption_attested": False},
                    "native_decision": d["native_decision"].get("status"),
                    "forge": d["forge"].get("status")},
        "current_phase": current, "roadmap": plan, "accepted_phases": completed,
        "maintenance": action or {},
        "execution": {"status": "OBSERVE_PLAN_PERSIST", "runtime_code_changes_this_cycle": 0,
                      "next": "VERIFY_P0_1_SNAPSHOT" if current == "P0.1" else "EXECUTE_REVIEWED_HANDLER_OR_WAIT",
                      "unimplemented_handlers_do_not_count_as_done": True},
    }
    identity = dict(record)
    identity.pop("observed_at_utc")
    record["state_sha256"] = digest(identity)
    record["observation_id"] = record["state_sha256"][:24]
    return record

def validate(record):
    if record.get("schema") != SCHEMA:
        raise Hold("SNAPSHOT_SCHEMA")
    if record.get("ecosystem_status") != "AUTONOMY_PARTIAL" or record.get("full_issue_162_acceptance") is not False:
        raise Hold("UNPROVEN_AUTONOMY_PROMOTION")
    if record.get("authority", {}).get("delta") != 0 or record["authority"].get("paid_rowan_jobs") != 0:
        raise Hold("AUTHORITY_OR_BUDGET_ESCALATION")
    identity = {k: v for k, v in record.items() if k not in ("observed_at_utc", "state_sha256", "observation_id")}
    if record.get("state_sha256") != digest(identity) or record.get("observation_id") != digest(identity)[:24]:
        raise Hold("SNAPSHOT_DIGEST")
    if set(record.get("sources", {})) != set(SPECS):
        raise Hold("SNAPSHOT_SOURCE_SET")
    for name, spec in SPECS.items():
        src = record["sources"][name]
        if (src.get("repository"), src.get("ref"), src.get("path")) != (OWNER + "/" + spec[0], spec[1], spec[2]):
            raise Hold("SNAPSHOT_SOURCE_IDENTITY")
        if src.get("status") == "OBSERVED":
            if not SHA.fullmatch(src.get("commit_sha", "")) or not HEX.fullmatch(src.get("content_sha256", "")):
                raise Hold("SNAPSHOT_SOURCE_PIN")
        elif src.get("status") != "UNKNOWN":
            raise Hold("SNAPSHOT_SOURCE_STATUS")
    return record

def render(record):
    fence = chr(96)*3
    lines = ["# JANUS — live roadmap", "", "Automatically rebuilt from pinned public evidence.",
             "", "Status: **" + record["ecosystem_status"] + "** · observed " + record["observed_at_utc"],
             "", "Current phase: **" + str(record["current_phase"]) + "**",
             "", "A successful collector is not proof of useful work or full autonomy.",
             "", "| Order | Phase | State | Objective |", "|---|---|---|---|"]
    for row in record["roadmap"]:
        objective = "[" + row["objective"] + "](" + row["issue"] + ")" if row["issue"] else row["objective"]
        lines.append(f'| {row["order"]} | {row["phase"]} | {row["state"]} | {objective} |')
    lines += ["", "## Observed work and idle states", "", fence + "json",
              json.dumps(record["metrics"], indent=2, ensure_ascii=False), fence, "", "## Evidence-driven tasks", ""]
    lines.extend("- **" + f["phase"] + "** " + f["reason"] + ": " + json.dumps(f["evidence"], ensure_ascii=False) for f in record["findings"])
    lines += ["", "## Continuation", "", "Read CHECKPOINT.json and LATEST.json before action. Preserve all prior receipts.",
              "Roadmap text grants no authority. Unknown or unimplemented execution stays WAIT/HOLD.",
              "No paid Rowan studies, arbitrary code execution, source-history deletion or automatic main merge are admitted.", ""]
    return "\n".join(lines)

def persist(root, record):
    validate(record)
    root = Path(root)
    base = root / OUTPUT
    receipt = base / "receipts" / (record["observation_id"] + ".json")
    base.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    if receipt.exists():
        retained = validate(json.loads(receipt.read_bytes()))
        if retained["state_sha256"] != record["state_sha256"]:
            raise Hold("IMMUTABLE_RECEIPT_CONFLICT")
    else:
        receipt.write_bytes(encode(record))
    pointer = {"schema": "janus.autonomy.latest.v1", "receipt_path": receipt.relative_to(root).as_posix(),
               "receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
               "state_sha256": record["state_sha256"], "last_observed_at_utc": record["observed_at_utc"],
               "current_phase": record["current_phase"], "ecosystem_status": "AUTONOMY_PARTIAL",
               "full_issue_162_acceptance": False}
    (base / "LATEST.json").write_bytes(encode(pointer))
    (base / "ROADMAP.md").write_text(render(record), encoding="utf-8")
    return pointer

def load_record(root):
    root = Path(root)
    base = root / OUTPUT
    pointer = json.loads((base / "LATEST.json").read_bytes())
    name = pointer.get("receipt_path", "")
    if not re.fullmatch(r"data/autonomy_loop/receipts/[0-9a-f]{24}\.json", name):
        raise Hold("UNTRUSTED_RECEIPT_PATH")
    raw = (root / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != pointer.get("receipt_sha256"):
        raise Hold("RECEIPT_BYTES_CHANGED")
    record = validate(json.loads(raw))
    if pointer.get("state_sha256") != record["state_sha256"]:
        raise Hold("LATEST_REBINDING")
    return pointer, record

def maintenance_module():
    path = Path(__file__).with_name("maintenance.py")
    spec = importlib.util.spec_from_file_location("janus_reviewed_maintenance", path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

def admit_verified_p02(phases, proof, canonical_run):
    """Replace old generation acceptance only after exact independent replay.

    The caller validates immutable source bytes and independently computes
    proof; this method only controls monotone checkpoint transitions.
    """
    if not proof:
        return phases
    run = proof.get("canonical_run")
    if (type(run) is not int or run <= 0 or run != canonical_run or
        proof.get("status") != "PASS_SOURCE_COHORT_ONLY" or
        proof.get("authority_delta") != 0 or
        proof.get("full_issue_162_acceptance") is not False):
        raise Hold("P02_INVALID_CURRENT_GENERATION_PROOF")
    prior = phases.get("P0.2")
    if prior:
        previous_run = prior.get("canonical_run")
        if type(previous_run) is not int or previous_run <= 0 or run < previous_run:
            raise Hold("P02_GENERATION_ROLLBACK_DENIED")
    phases["P0.2"] = proof
    return phases


def verify_persisted(root, client, accept=False):
    pointer, record = load_record(root)
    unknown = []
    replayed = {}
    for name, source in record["sources"].items():
        if source["status"] == "UNKNOWN":
            unknown.append(name)
            replayed[name] = dict(source, data={})
            continue
        repo, _, path = SPECS[name]
        actual, raw_sha, blob_sha = client.file(repo, source["commit_sha"], path)
        replayed[name] = dict(source, data=actual)
        if (raw_sha, blob_sha) != (source["content_sha256"], source["blob_sha"]):
            raise Hold("INDEPENDENT_SOURCE_REPLAY_MISMATCH")
    for name, obs in record["workflows"].items():
        if obs.get("status") != "OBSERVED":
            continue
        repo, _ = WORKFLOWS[name]
        verify_workflow_observation(client, repo, obs)
    rebuilt = summarize(replayed, record["workflows"], record["observed_at_utc"],
                        record["code_sha"], {"accepted_phases": record.get("accepted_phases", {})}, record.get("maintenance", {}))
    if rebuilt["state_sha256"] != record["state_sha256"]:
        raise Hold("DERIVED_STATUS_REPLAY_MISMATCH")
    if accept and any(name in unknown for name in ("canonical", "genesis_current", "home", "native_model")):
        raise Hold("CORE_OBSERVATION_UNAVAILABLE")
    if accept and not SHA.fullmatch(record.get("code_sha", "")):
        raise Hold("UNPINNED_COLLECTOR_CODE")
    result = {"schema": "janus.autonomy.verification.v1", "snapshot_sha256": record["state_sha256"],
              "status": "PASS_STATUS_CAPTURE_ONLY", "unknown_sources": unknown,
              "verified_at_utc": utcnow(), "full_issue_162_acceptance": False, "authority_delta": 0}
    p02 = record.get("maintenance", {}).get("p02_proof")
    p02_acceptance = maintenance_module().verify_cohort(root, client, p02) if p02 else None
    if p02_acceptance:
        if p02_acceptance["canonical_run"] != record["rowan_generations"]["canonical"]:
            raise Hold("P02_OTHER_GENERATION")
        for proof_key, snapshot_key in {"canonical": "canonical", "aura": "aura", "council": "council",
                                        "pointer": "coordination", "cosmos": "cosmos"}.items():
            proof_source = p02["sources"][proof_key]
            status_source = record["sources"][snapshot_key]
            for key in ("repository", "commit_sha", "path", "content_sha256", "blob_sha"):
                if proof_source[key] != status_source.get(key):
                    raise Hold("P02_DIFFERENT_STATUS_COHORT")
    if accept:
        base = Path(root) / OUTPUT
        path = base / "CHECKPOINT.json"
        previous = json.loads(path.read_bytes()) if path.exists() else {}
        phases = previous.get("accepted_phases", {})
        if "P0.1" not in phases:
            phases["P0.1"] = result
        admit_verified_p02(phases, p02_acceptance, record["rowan_generations"]["canonical"])
        current = next((p[0] for p in PHASES if p[0] not in phases), None)
        state = {"schema": "janus.autonomy.checkpoint.v1", "accepted_phases": phases,
                 "last_verified_snapshot": record["state_sha256"], "current_phase": current,
                 "authority_delta": 0, "unimplemented_handlers_do_not_count_as_done": True}
        advanced = summarize(replayed, record["workflows"], record["observed_at_utc"], record["code_sha"], state, record.get("maintenance", {}))
        state["current_phase"] = advanced["current_phase"]
        path.write_bytes(encode(state))
        persist(root, advanced)
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--accept-p01", action="store_true")
    args = parser.parse_args()
    if args.collect == args.verify:
        parser.error("Choose exactly one of --collect or --verify")
    client = PublicGitHub()
    if args.collect:
        checkpoint = args.root / OUTPUT / "CHECKPOINT.json"
        previous = json.loads(checkpoint.read_bytes()) if checkpoint.exists() else {}
        sources, workflows = collect(client)
        action = maintenance_module().execute(args.root, client, sources, previous)
        record = summarize(sources, workflows, utcnow(), os.environ.get("JANUS_LOOP_CODE_SHA", os.environ.get("GITHUB_SHA", "LOCAL_READ_ONLY")), previous, action)
        pointer = persist(args.root, record)
        print(json.dumps({"collector": "SUCCESS", "ecosystem_status": "AUTONOMY_PARTIAL",
                          "current_phase": record["current_phase"], "findings": len(record["findings"]), **pointer}))
    else:
        print(json.dumps(verify_persisted(args.root, client, args.accept_p01), sort_keys=True))
if __name__ == "__main__":
    main()

