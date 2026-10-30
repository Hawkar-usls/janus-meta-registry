"""Independent Rex need admission to JANUS's PREEXISTING pure-code task policy.

Only pinned public GitHub bytes are fetched from four FIXED repository/path pairs.
Untrusted research text never affects the author prompt or task allowlist.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, HTTPRedirectHandler, build_opener
from policy import TASKS, canonical, digest, next_task, validate_state

HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
NEED_ID = re.compile(r"code_need_[0-9a-f]{20}\Z")
ROLES = {
    "research": ("Janus-Demiurge", "janus_model/state/JANUS_RESEARCH_SPINE.json"),
    "beetle": ("Janus-Demiurge", "data/beetle-runtime/CONTEXT.json"),
    "delivery": ("janus-lapis", "data/beetle-state/latest_delivery_health.json"),
    "coder": ("janus-meta-registry", "STATE.json"),
}
BEETLE_CAPS = {
    "may_generate_research_questions": True, "is_verified_evidence": False,
    "may_grant_mutation_authority": False, "is_direct_gradient_signal": False
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("REX_NEED_REDIRECT_DENIED")


def fetch_source(role, commit):
    if role not in ROLES or not isinstance(commit, str) or not HEX40.fullmatch(commit):
        raise ValueError("REX_NEED_UNPINNED_SOURCE")
    repo, path = ROLES[role]
    url = f"https://raw.githubusercontent.com/Hawkar-usls/{repo}/{commit}/{path}"
    req = Request(url, headers={"User-Agent": "janus-rex-independent-need-verifier"})
    with build_opener(NoRedirect()).open(req, timeout=15) as response:
        raw = response.read(200001)
    if len(raw) > 200000:
        raise ValueError("REX_NEED_SOURCE_TOO_LARGE")
    return raw


def inspect(need, active, fetch=fetch_source):
    validate_state(active)
    expected_authority = {
        "delta": 0, "code_admission": False, "runtime_import": False,
        "auto_merge": False, "paid_jobs": False
    }
    if (need.get("schema") != "janus.rex.research_code_need.v1" or
        need.get("status") != "PROPOSED_REVIEW_ONLY" or
        need.get("task_id") != "is_fresh" or
        need.get("need_kind") != "ACK_FRESHNESS_DIAGNOSTIC" or
        need.get("signature") != "def is_fresh(age, max_age)" or
        need.get("target_repository") != "Hawkar-usls/janus-meta-registry" or
        need.get("admission") != "INDEPENDENT_CODER_EVALUATOR_AND_HUMAN_REVIEW_REQUIRED" or
        need.get("claim_ceiling") != "DIAGNOSTIC_PURE_FUNCTION_ONLY_NOT_A_RECEIVER_REPAIR" or
        need.get("authority") != expected_authority):
        raise ValueError("REX_NEED_POLICY_REJECTED")
    need_id = need.get("need_id")
    body = {k: v for k, v in need.items() if k != "need_id"}
    if (not isinstance(need_id, str) or not NEED_ID.fullmatch(need_id) or
        need_id != "code_need_" + digest(body)[:20]):
        raise ValueError("REX_NEED_ID_REJECTED")
    pins, hashes = need.get("source_commits"), need.get("source_sha256")
    if (not isinstance(pins, dict) or not isinstance(hashes, dict) or
        set(pins) != set(ROLES) or set(hashes) != set(ROLES) or
        any(not isinstance(v, str) or not HEX40.fullmatch(v) for v in pins.values()) or
        any(not isinstance(v, str) or not HEX64.fullmatch(v) for v in hashes.values())):
        raise ValueError("REX_NEED_PINS_REJECTED")
    observed = {}
    for role in ROLES:
        raw = fetch(role, pins[role])
        if hashlib.sha256(raw).hexdigest() != hashes[role]:
            raise ValueError("REX_NEED_SOURCE_SHA_MISMATCH:" + role)
        observed[role] = json.loads(raw)
    research, beetle, health, prior = (observed[r] for r in ROLES)
    beetle_body = dict(beetle)
    beetle_sha = beetle_body.pop("context_sha256", None)
    ext = research.get("external_context") or {}
    if (beetle.get("schema") != "janus.beetle.runtime_context.v1" or
        beetle.get("status") != "TRIAGED_TO_RESEARCH_CONTEXT_NOT_VERIFIED" or
        beetle.get("target_repository") != "Hawkar-usls/Janus-Demiurge" or
        beetle.get("capabilities") != BEETLE_CAPS or
        beetle_sha != digest(beetle_body) or
        research.get("schema") != "janus.research_spine.v1" or
        research.get("status") != "READY" or
        (research.get("research_spine") or {}).get("beetle") != beetle or
        ext.get("beetle_processed_sequence") != need.get("beetle_sequence") or
        ext.get("beetle_processing_status") != beetle["status"] or
        need.get("beetle_context_sha256") != beetle_sha or
        need.get("research_context_sha256") != research.get("context_sha256") or
        (research.get("claim_ceiling") or {}).get("beetle_triage_is_model_learning") is not False or
        (research.get("improvement_policy") or {}).get("autonomous_merge") is not False):
        raise ValueError("REX_NEED_RESEARCH_REPLAY_REJECTED")
    rows = health.get("repositories")
    if (health.get("schema") != "janus.beetle.delivery_health.v1" or
        health.get("ack_semantics") != "INBOX_DURABLE_ONLY_NOT_RUNTIME_CONSUMPTION" or
        not isinstance(rows, dict) or
        any(not isinstance(v, dict) or type(v.get("pending")) is not int or v["pending"] < 0
            for v in rows.values()) or
        sum(v["pending"] for v in rows.values()) != health.get("total_pending")):
        raise ValueError("REX_NEED_DELIVERY_REPLAY_REJECTED")
    unknown = sorted(k for k, v in rows.items()
                     if v.get("status") == "ACK_UNAVAILABLE" and v["pending"] > 0)
    if (not unknown or unknown != need.get("ack_unavailable_receivers") or
        health["total_pending"] != need.get("delivery_pending")):
        raise ValueError("REX_NEED_HEALTH_SIGNAL_REJECTED")
    validate_state(prior)
    if prior["sequence"] != need.get("coder_state_sequence") or "is_fresh" in prior["accepted"]:
        raise ValueError("REX_NEED_CODER_PRIOR_REJECTED")
    if "is_fresh" in active["accepted"]:
        return {"status": "IDLE_NEED_ALREADY_SATISFIED", "task_id": None,
                "need_id": need_id, "authority_delta": 0}
    if next_task(active) != "is_fresh" or "is_fresh" not in TASKS:
        raise ValueError("REX_NEED_NOT_NEXT_PREADMITTED_TASK")
    return {"status": "VERIFIED_NEED_BOUND_TO_PREADMITTED_TASK",
            "task_id": "is_fresh", "need_id": need_id,
            "source_need_sha256": digest(need),
            "coder_state_sha256": digest(active), "authority_delta": 0,
            "code_authority_granted": False, "human_review_required": True}


def intake(root, state, fetch=fetch_source):
    receipts = sorted(Path(root).glob("code_need_*.json"))
    if len(receipts) > 128:
        raise ValueError("REX_NEED_QUEUE_TOO_LARGE")
    for path in reversed(receipts):
        if path.stat().st_size > 20000:
            raise ValueError("REX_NEED_FILE_TOO_LARGE")
        need = json.loads(path.read_bytes())
        if need.get("status") != "PROPOSED_REVIEW_ONLY":
            continue
        return inspect(need, state, fetch)
    return {"status": "IDLE_NO_REX_CODE_NEED", "task_id": None, "authority_delta": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rex-dir", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = intake(args.rex_dir, json.loads(args.state.read_bytes()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(canonical(result) + b"\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
