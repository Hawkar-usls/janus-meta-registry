"""Offline candidate preflight fixtures, including an actual public JANUS PR."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
p = ROOT / "modules/autonomy_loop/candidate_preflight.py"
spec = importlib.util.spec_from_file_location("closed_loop_candidate_preflight", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# Exact public PR #379 review metadata, pinned to head
# 2652dd70d8f65385316cd309d4a74db2b948dc46.
# This fixture verifies integrity/AST and NEVER executes the candidate.
REAL_RETRY_DELAY = "def retry_delay(attempt, cap):\n    return min(cap, 2 ** attempt)\n"
REAL_PROPOSAL = json.loads("""
{
  "author_model":"Qwen/Qwen2.5-Coder-0.5B-Instruct",
  "author_run_id":"41093576816-1",
  "authority_delta":0,
  "auto_merge":false,
  "candidate_path":"candidate_modules/retry_delay/module.py",
  "dependencies":[],
  "full_issue_162_acceptance":false,
  "independently_verified_cases":291,
  "install_into_runtime":false,
  "main_code_mutations":0,
  "module_id":"janus.pure.retry_delay.v1",
  "permissions":[],
  "proposal_sha256":"a2d2a4ba32d29cb58c3b8472dc3b44656e208f66030c8a491fa287dd01ecba3e",
  "review_required":true,
  "schema":"janus.autonomous_coder.integration_proposal.v1",
  "security_scope":"QUARANTINED_PURE_MODULE_REVIEW_ONLY",
  "source_branch":"janus/autonomous-code-state",
  "source_module_manifest_sha256":"0d3e9b72bd0a24f6d36783bfe25ee4bdb66427f342b27c3f9f0fd4866d7b8a26",
  "source_receipt_sha256":"68846618446795828b36285cce4808c7358c24f4c2fe202ad83b96a0cde33d21",
  "source_sha256":"a45bf9b5814e432a89334e46f8acac63a9fa1d2846dc393ed21e6dd6695b2611",
  "source_state_commit":"38ac28921496a106d345bca937cca14bf9789f9d",
  "task_id":"retry_delay"
}
""")
REAL_COMMIT = "2652dd70d8f65385316cd309d4a74db2b948dc46"


def queued():
    # Synthetic small queue to exercise rules; production index is not modified.
    return {
        "schema": "janus.patch_queue.index.v1",
        "proposal_count": 3,
        "verified_count": 1,
        "blocked_count": 0,
        "proposals": [
            {
                "proposal_id": "jpatch-hrain-canary-001",
                "target_repository": "Hawkar-usls/Hrain",
                "main_mutated": False,
                "status": "VERIFY_PASS",
            },
            {
                "proposal_id": "jpatch-private-wait-001",
                "repository": "Hawkar-usls/Hrain",
                "status": "WAITING_FOR_TARGET_BRANCH",
            },
            {
                "proposal_id": "jpatch-private-wait-002",
                "repository": "Hawkar-usls/Hrain",
                "status": "WAITING_FOR_TARGET_BRANCH",
            },
        ],
    }


class CandidatePreflightTests(unittest.TestCase):
    def test_pinned_public_review_source_can_only_enter_isolated_replay(self):
        report = m.preflight(REAL_PROPOSAL, REAL_RETRY_DELAY, source_commit=REAL_COMMIT)
        self.assertEqual(report["status"], "READY_FOR_ISOLATED_BEHAVIOR_REPLAY_ONLY")
        self.assertEqual(report["task_id"], "retry_delay")
        self.assertEqual(report["source_commit"], REAL_COMMIT)
        self.assertEqual(report["source_sha256"], REAL_PROPOSAL["source_sha256"])
        self.assertEqual(report["prior_claimed_verified_cases"], 291)
        self.assertFalse(report["executed_now"])
        self.assertFalse(report["independent_replay_attested"])
        self.assertFalse(report["improvement_attested"])
        self.assertFalse(report["runtime_consumption_attested"])
        self.assertFalse(report["auto_merge"])
        unsigned = dict(report)
        unsigned.pop("receipt_sha256")
        self.assertEqual(report["receipt_sha256"], m.digest(unsigned))

    def test_any_changed_source_is_denied(self):
        with self.assertRaisesRegex(m.Hold, "CANDIDATE_SOURCE_CHANGED"):
            m.preflight(REAL_PROPOSAL,
                        REAL_RETRY_DELAY.replace("2 ** attempt", "1 + attempt"),
                        source_commit=REAL_COMMIT)

    def test_altered_proposal_is_denied_even_when_metadata_looks_ok(self):
        for field, value in (
            ("source_state_commit", "f" * 40),
            ("source_receipt_sha256", "f" * 64),
            ("source_module_manifest_sha256", "f" * 64),
            ("independently_verified_cases", 999),
            ("author_model", "AnotherModel"),
        ):
            bad = copy.deepcopy(REAL_PROPOSAL)
            bad[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(m.Hold, "PROPOSAL_DIGEST_MISMATCH"):
                    m.preflight(bad, REAL_RETRY_DELAY, source_commit=REAL_COMMIT)

    def test_no_auto_merge_runtime_install_or_scope_escalation(self):
        for field, value in (
            ("authority_delta", True),
            ("auto_merge", True),
            ("install_into_runtime", True),
            ("main_code_mutations", 1),
            ("full_issue_162_acceptance", True),
            ("permissions", ["contents:write"]),
            ("dependencies", ["requests"]),
            ("candidate_path", "modules/autonomy_loop/runtime.py"),
            ("security_scope", "TRUSTED_RUNTIME"),
        ):
            bad = copy.deepcopy(REAL_PROPOSAL)
            bad[field] = value
            with self.subTest(field=field):
                with self.assertRaises(m.Hold):
                    m.preflight(bad, REAL_RETRY_DELAY, source_commit=REAL_COMMIT)

    def test_unpinned_commit_and_insufficient_prior_tests_fail_closed(self):
        with self.assertRaisesRegex(m.Hold, "SOURCE_COMMIT_UNPINNED"):
            m.preflight(REAL_PROPOSAL, REAL_RETRY_DELAY, source_commit="main")
        bad = copy.deepcopy(REAL_PROPOSAL)
        bad["independently_verified_cases"] = 199
        with self.assertRaisesRegex(m.Hold, "INSUFFICIENT_PRIOR_CASES"):
            m.preflight(bad, REAL_RETRY_DELAY, source_commit=REAL_COMMIT)

    def test_unreviewed_task_rejected_even_with_self_consistent_digest(self):
        bad = copy.deepcopy(REAL_PROPOSAL)
        bad["task_id"] = "hidden"
        bad["module_id"] = "janus.pure.hidden.v1"
        bad["candidate_path"] = "candidate_modules/hidden/module.py"
        src = "def hidden(attempt, cap):\n    return min(cap, 2 ** attempt)\n"
        import hashlib
        bad["source_sha256"] = hashlib.sha256(src.encode()).hexdigest()
        unsigned = {k:v for k,v in bad.items() if k != "proposal_sha256"}
        bad["proposal_sha256"] = m.digest(unsigned)
        with self.assertRaisesRegex(m.Hold, "CANDIDATE_AST_NOT_ADMITTED"):
            m.preflight(bad, src, source_commit=REAL_COMMIT)

    def test_waiting_queues_are_not_safe_candidates(self):
        report = m.triage_queue(queued())
        self.assertEqual(report["status"], "HOLD_NO_SAFE_QUEUE_CANDIDATE")
        self.assertEqual(report["counts"]["waiting_for_target_branch"], 2)
        self.assertEqual(report["counts"]["verified_not_in_safe_repo"], 1)
        self.assertEqual(report["counts"]["verified_safe_repo"], 0)
        self.assertEqual(report["safe_proposal_ids"], [])
        self.assertTrue(report["no_target_branch_created"])
        self.assertTrue(report["no_private_repo_access"])
        self.assertTrue(report["no_dispatch"])

    def test_only_explicit_same_repository_verification_is_reviewable(self):
        index = queued()
        index["proposals"][0]["target_repository"] = m.SAFE_REPOSITORY
        index["proposals"][0]["main_mutated"] = False
        report = m.triage_queue(index)
        self.assertEqual(report["status"], "REVIEW_SAFE_CANDIDATES_ONLY")
        self.assertEqual(report["safe_proposal_ids"], ["jpatch-hrain-canary-001"])
        self.assertEqual(report["authority_delta"], 0)

    def test_tampered_counts_unknown_status_and_duplicates_fail_closed(self):
        for field,value in (
            ("proposal_count", 4),
            ("verified_count", 2),
            ("schema", "not-our-schema"),
            ("blocked_count", -1),
        ):
            index = queued()
            index[field] = value
            with self.subTest(field=field):
                with self.assertRaises(m.Hold):
                    m.triage_queue(index)
        index = queued()
        index["proposals"][1]["status"] = "NEW_UNKNOWN"
        with self.assertRaisesRegex(m.Hold, "UNKNOWN_QUEUE_STATUS"):
            m.triage_queue(index)
        index = queued()
        index["proposals"][2]["proposal_id"] = index["proposals"][1]["proposal_id"]
        with self.assertRaisesRegex(m.Hold, "DUPLICATE"):
            m.triage_queue(index)

    def test_untrusted_verified_patch_cannot_be_preapproved(self):
        index = queued()
        index["proposals"][0]["target_repository"] = m.SAFE_REPOSITORY
        index["proposals"][0]["main_mutated"] = True
        with self.assertRaisesRegex(m.Hold, "UNTRUSTED_VERIFIED_PATCH"):
            m.triage_queue(index)


if __name__ == "__main__":
    unittest.main()
