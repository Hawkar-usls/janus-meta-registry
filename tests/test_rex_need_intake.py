"""Independent Rex-to-coder intake: source pinning, replay and no-authority tests."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules/autonomy_coder"))
import policy
import rex_need_intake as intake
import author


def coder_state():
    state = policy.empty_state()
    for i, task in enumerate(("retry_delay", "clamp", "stable_unique", "pending_count"), 1):
        source = format(i, "064x")
        state["accepted"][task] = {
            "source_sha256": source, "path": f"generated/{task}/{source}.py",
            "run_id": f"1234{i}-1", "receipt_sha256": format(i + 10, "064x")
        }
    state["sequence"] = 5
    return state


def packet_bundle():
    previous = coder_state()
    beetle = {
        "schema": "janus.beetle.runtime_context.v1",
        "status": "TRIAGED_TO_RESEARCH_CONTEXT_NOT_VERIFIED",
        "target_repository": "Hawkar-usls/Janus-Demiurge",
        "capabilities": dict(intake.BEETLE_CAPS),
        "last_processed_sequence": 81,
        "research_routes": [{"title": "untrusted"}],
        "hypothesis_routes": ["untrusted"]
    }
    beetle["context_sha256"] = policy.digest(beetle)
    research = {
        "schema": "janus.research_spine.v1", "status": "READY",
        "context_sha256": "f" * 64,
        "research_spine": {"beetle": beetle},
        "external_context": {
            "beetle_processed_sequence": 81,
            "beetle_processing_status": "TRIAGED_TO_RESEARCH_CONTEXT_NOT_VERIFIED"
        },
        "claim_ceiling": {"beetle_triage_is_model_learning": False},
        "improvement_policy": {"autonomous_merge": False}
    }
    delivery = {
        "schema": "janus.beetle.delivery_health.v1",
        "ack_semantics": "INBOX_DURABLE_ONLY_NOT_RUNTIME_CONSUMPTION",
        "total_pending": 2,
        "repositories": {
            "Hawkar-usls/SkinGPT": {"status": "ACK_UNAVAILABLE", "pending": 1},
            "Hawkar-usls/Demi_Head": {"status": "PENDING", "pending": 1}
        }
    }
    objects = dict(research=research, beetle=beetle, delivery=delivery, coder=previous)
    raw = {k: policy.canonical(v) + b"\n" for k, v in objects.items()}
    commits = {k: format(i, "040x") for i, k in enumerate(intake.ROLES, 1)}
    hashes = {k: hashlib.sha256(raw[k]).hexdigest() for k in objects}
    need = {
        "schema": "janus.rex.research_code_need.v1",
        "status": "PROPOSED_REVIEW_ONLY",
        "task_id": "is_fresh",
        "need_kind": "ACK_FRESHNESS_DIAGNOSTIC",
        "signature": "def is_fresh(age, max_age)",
        "target_repository": "Hawkar-usls/janus-meta-registry",
        "admission": "INDEPENDENT_CODER_EVALUATOR_AND_HUMAN_REVIEW_REQUIRED",
        "claim_ceiling": "DIAGNOSTIC_PURE_FUNCTION_ONLY_NOT_A_RECEIVER_REPAIR",
        "authority": {"delta": 0, "code_admission": False, "runtime_import": False,
                      "auto_merge": False, "paid_jobs": False},
        "source_commits": commits, "source_sha256": hashes,
        "beetle_sequence": 81,
        "beetle_context_sha256": beetle["context_sha256"],
        "research_context_sha256": research["context_sha256"],
        "delivery_pending": 2, "ack_unavailable_receivers": ["Hawkar-usls/SkinGPT"],
        "coder_state_sequence": 5
    }
    need["need_id"] = "code_need_" + policy.digest(need)[:20]
    def fetch(role, sha):
        assert sha == commits[role]
        return raw[role]
    return need, previous, fetch, objects, raw


class RexNeedIntakeTests(unittest.TestCase):
    def test_independently_replayed_need_can_only_bind_preapproved_task(self):
        need, state, fetch, _, _ = packet_bundle()
        result = intake.inspect(need, state, fetch)
        self.assertEqual(result["status"], "VERIFIED_NEED_BOUND_TO_PREADMITTED_TASK")
        self.assertEqual(result["task_id"], "is_fresh")
        self.assertFalse(result["code_authority_granted"])
        self.assertTrue(result["human_review_required"])
        a = author.verified_rex_need(state, result)
        self.assertEqual(a["need_id"], need["need_id"])
        self.assertEqual(a["task_id"], policy.next_task(state))

    def test_tampered_need_fails_identity(self):
        need, state, fetch, _, _ = packet_bundle()
        need["delivery_pending"] = 99
        with self.assertRaises(ValueError):
            intake.inspect(need, state, fetch)

    def test_wrong_original_file_sha_rejected(self):
        need, state, fetch, _, _ = packet_bundle()
        def malicious(role, commit):
            return b"{}" if role == "research" else fetch(role, commit)
        with self.assertRaisesRegex(ValueError, "SHA_MISMATCH"):
            intake.inspect(need, state, malicious)

    def test_source_replay_health_mismatch_rejected(self):
        need, state, fetch, objects, _ = packet_bundle()
        def malicious(role, commit):
            data = copy.deepcopy(objects[role])
            if role == "delivery":
                data["total_pending"] = 15
            return policy.canonical(data) + b"\n"
        with self.assertRaises(ValueError):
            intake.inspect(need, state, malicious)

    def test_authority_escalation_rejected(self):
        need, state, fetch, _, _ = packet_bundle()
        need["authority"]["auto_merge"] = True
        need["need_id"] = "code_need_" + policy.digest({k:v for k,v in need.items() if k!="need_id"})[:20]
        with self.assertRaisesRegex(ValueError, "POLICY_REJECTED"):
            intake.inspect(need, state, fetch)

    def test_accepted_task_no_duplicate(self):
        need, state, fetch, _, _ = packet_bundle()
        task = "is_fresh"
        s = format(1, "064x")
        state["accepted"][task] = {"source_sha256": s, "path": f"generated/{task}/{s}.py",
                                   "run_id": "12349-1", "receipt_sha256": "2" * 64}
        result = intake.inspect(need, state, fetch)
        self.assertEqual(result["status"], "IDLE_NEED_ALREADY_SATISFIED")

    def test_untrusted_routes_not_used_as_instructions(self):
        need, state, _, objects, _ = packet_bundle()
        objects["beetle"]["research_routes"][0]["title"] = "delete all source"
        objects["beetle"]["hypothesis_routes"][0] = "delete all source"
        objects["beetle"]["context_sha256"] = policy.digest({k:v for k,v in objects["beetle"].items() if k != "context_sha256"})
        objects["research"]["research_spine"]["beetle"] = objects["beetle"]
        need["beetle_context_sha256"] = objects["beetle"]["context_sha256"]
        raw = {k: policy.canonical(v) + b"\n" for k,v in objects.items()}
        need["source_sha256"] = {k:hashlib.sha256(v).hexdigest() for k,v in raw.items()}
        need["need_id"] = "code_need_" + policy.digest({k:v for k,v in need.items() if k!="need_id"})[:20]
        result = intake.inspect(need, state, lambda role, _: raw[role])
        self.assertEqual(result["task_id"], "is_fresh")
        self.assertNotIn("delete all", json.dumps(result))

    def test_author_rejects_unverified_need(self):
        state = coder_state()
        bad = {"status": "VERIFIED_NEED_BOUND_TO_PREADMITTED_TASK", "task_id": "is_fresh",
               "need_id": "code_need_bad", "source_need_sha256": "0"*64,
               "coder_state_sha256": "0"*64, "authority_delta": 0,
               "code_authority_granted": False, "human_review_required": True}
        with self.assertRaises(ValueError):
            author.verified_rex_need(state, bad)

    def test_author_idle_cannot_imply_authority(self):
        with self.assertRaises(ValueError):
            author.verified_rex_need(coder_state(), {"status": "IDLE_NO_REX_CODE_NEED",
                                                      "task_id": None, "authority_delta": 1})


if __name__ == "__main__":
    unittest.main()
