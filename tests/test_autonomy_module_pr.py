"""Adversarial self-code handoff tests. Never import/execute model-generated code."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules/autonomy_coder"))
import policy as p
import lifecycle
import module_registry as registry
import integration_proposal as pr

COMMIT = "d" * 40
GOOD = "def retry_delay(attempt, cap):\n    return min(cap, 2 ** attempt)\n"


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.state = self.root / "state"
        self.repo = self.root / "code"
        self.state.mkdir()
        self.repo.mkdir()
        (self.state / "STATE.json").write_bytes(p.canonical(p.empty_state()))
        bundle = {
            "schema": "janus.autonomous_coder.candidates.v1",
            "run_id": "123456-1",
            "base_state_sha256": p.digest(p.empty_state()),
            "task_id": "retry_delay",
            "code_commit": os.environ.get("GITHUB_SHA", "LOCAL"),
            "model": {"id": p.MODEL_ID, "revision": p.MODEL_REVISION,
                      "weights_sha256": p.WEIGHTS_SHA256,
                      "attribution": "EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS"},
            "candidates": [
                {"index": i, "raw_response": GOOD, "source": GOOD,
                 "source_sha256": p.source_digest(GOOD)} for i in range(2)],
        }
        def check(source, task, **kwargs):
            return {"status": "PASS_PURE_FUNCTION_ONLY", "cases": 291}
        self.assertEqual(
            lifecycle.publish(self.state, bundle, lifecycle.evaluate(bundle, check))["status"],
            "PROMOTED_PURE_EXTENSION_ONLY")
        registry.build(self.state)

    def test_exact_model_bytes_to_review_only_branch_and_clean_replay(self):
        result = pr.prepare(self.repo, self.state, COMMIT, set())
        self.assertEqual(result["status"], "REVIEW_ONLY_PROPOSAL_PREPARED")
        self.assertEqual(result["task_id"], "retry_delay")
        self.assertEqual(result["authority_delta"], 0)
        self.assertEqual(result["candidate_paths"], [
            "candidate_modules/retry_delay/PROPOSAL.json",
            "candidate_modules/retry_delay/module.py"])
        copy = (self.repo / "candidate_modules/retry_delay/module.py").read_bytes()
        self.assertEqual(copy, GOOD.encode())
        proof = json.loads((self.repo / "candidate_modules/retry_delay/PROPOSAL.json").read_bytes())
        self.assertEqual(proof["source_state_commit"], COMMIT)
        self.assertEqual(proof["dependencies"], [])
        self.assertEqual(proof["permissions"], [])
        self.assertFalse(proof["auto_merge"])
        self.assertFalse(proof["install_into_runtime"])
        self.assertTrue(proof["review_required"])
        self.assertEqual(
            pr.verify_proposal(self.repo, self.state, COMMIT, "retry_delay")["status"],
            "REVIEW_ONLY_PROVENANCE_VERIFIED")

    def test_known_review_branch_skips_and_no_duplicate_changes(self):
        branch = pr.propose(self.state, "retry_delay", COMMIT)[0]
        before = (self.state / "STATE.json").read_bytes()
        result = pr.prepare(self.repo, self.state, COMMIT, {branch})
        self.assertEqual(result["status"], "IDLE_ALL_ACCEPTED_MODULES_ALREADY_PROPOSED")
        self.assertFalse(result["changed"])
        self.assertFalse((self.repo / "candidate_modules").exists())
        self.assertEqual((self.state / "STATE.json").read_bytes(), before)

    def test_second_prepare_does_not_mutate_existing_payload(self):
        pr.prepare(self.repo, self.state, COMMIT, set())
        source = self.repo / "candidate_modules/retry_delay/module.py"
        with self.assertRaisesRegex(ValueError, "INTEGRATION_CANDIDATE_ALREADY_EXISTS"):
            pr.prepare(self.repo, self.state, COMMIT, set())
        self.assertEqual(source.read_bytes(), GOOD.encode())

    def test_candidate_tampering_is_detected(self):
        pr.prepare(self.repo, self.state, COMMIT, set())
        target = self.repo / "candidate_modules/retry_delay/module.py"
        target.write_text("def retry_delay(attempt, cap):\n    return 99\n")
        with self.assertRaisesRegex(ValueError, "REVIEW_CANDIDATE_REBINDING"):
            pr.verify_proposal(self.repo, self.state, COMMIT, "retry_delay")

    def test_attacker_cannot_grant_install_permission_by_rehashing_manifest(self):
        pr.prepare(self.repo, self.state, COMMIT, set())
        target = self.repo / "candidate_modules/retry_delay/PROPOSAL.json"
        data = json.loads(target.read_bytes())
        data["install_into_runtime"] = True
        data["proposal_sha256"] = p.digest({k:v for k,v in data.items()
                                            if k != "proposal_sha256"})
        target.write_bytes(p.canonical(data) + b"\n")
        with self.assertRaisesRegex(ValueError, "REVIEW_CANDIDATE_REBINDING"):
            pr.verify_proposal(self.repo, self.state, COMMIT, "retry_delay")

    def test_forged_source_sha_or_receipt_is_never_proposed(self):
        state_path = self.state / "STATE.json"
        original = state_path.read_bytes()
        state = json.loads(original)
        state["accepted"]["retry_delay"]["source_sha256"] = "e"*64
        state_path.write_bytes(p.canonical(state))
        with self.assertRaises(ValueError):
            pr.prepare(self.repo, self.state, COMMIT, set())
        state_path.write_bytes(original)
        receipt = self.state / "receipts/123456-1.json"
        receipt.write_bytes(b'{"status":"PROMOTED_PURE_EXTENSION_ONLY"}\n')
        with self.assertRaises(ValueError):
            pr.prepare(self.repo, self.state, COMMIT, set())

    def test_rejects_wrong_commit_and_unknown_tasks(self):
        for commit in ("main", "a"*39, "a"*41, "../"*5):
            with self.subTest(commit=commit), self.assertRaises(ValueError):
                pr.propose(self.state, "retry_delay", commit)
        with self.assertRaisesRegex(ValueError, "UNREVIEWED_MODULE_TASK"):
            pr.propose(self.state, "shell_script", COMMIT)

    def test_independent_pr_diff_gate_rejects_extra_files_or_fork(self):
        branch = pr.propose(self.state, "retry_delay", COMMIT)[0]
        pull = {
            "state": "open", "merged": False,
            "base": {"ref": "main", "repo": {"full_name": "Hawkar-usls/janus-meta-registry"}},
            "head": {"ref": branch, "sha": COMMIT,
                     "repo": {"full_name": "Hawkar-usls/janus-meta-registry"}},
            "changed_files": 2,
        }
        files = [
            {"filename": "candidate_modules/retry_delay/module.py", "status": "added"},
            {"filename": "candidate_modules/retry_delay/PROPOSAL.json", "status": "added"},
        ]
        expected_repo = "Hawkar-usls/janus-meta-registry"
        self.assertEqual(pr.inspect_pr(pull, files, expected_repo)["task_id"], "retry_delay")
        forged = [dict(row) for row in files]
        forged[1]["filename"] = ".github/workflows/backdoor.yml"
        with self.assertRaisesRegex(ValueError, "REVIEW_PR_UNEXPECTED_FILES"):
            pr.inspect_pr(pull, forged, expected_repo)
        with self.assertRaisesRegex(ValueError, "REVIEW_PR_METADATA_OR_SCOPE_INVALID"):
            pr.inspect_pr({**pull, "changed_files": 3}, files, expected_repo)
        with self.assertRaisesRegex(ValueError, "REVIEW_PR_METADATA_OR_SCOPE_INVALID"):
            pr.inspect_pr({**pull, "head": {**pull["head"],
                          "repo": {"full_name": "other/fork"}}}, files, expected_repo)
        with self.assertRaisesRegex(ValueError, "REVIEW_PR_METADATA_OR_SCOPE_INVALID"):
            pr.inspect_pr({**pull, "merged": True}, files, expected_repo)
        with self.assertRaisesRegex(ValueError, "REVIEW_PR_UNEXPECTED_FILES"):
            pr.inspect_pr(pull, [{**files[0], "status": "modified"}, files[1]],
                          expected_repo)

    def test_generated_review_candidate_cannot_follow_symlink_into_repo(self):
        pr.prepare(self.repo, self.state, COMMIT, set())
        module_path = self.repo / "candidate_modules/retry_delay/module.py"
        module_path.unlink()
        outside = self.root / "outside.py"
        outside.write_text(GOOD)
        module_path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "STATE_PATH_ESCAPE"):
            pr.verify_proposal(self.repo, self.state, COMMIT, "retry_delay")

    def test_main_workflow_writes_only_exact_candidates_and_never_auto_merges(self):
        path = Path(__file__).resolve().parents[1] / ".github/workflows/janus-autonomous-module-pr.yml"
        wf = path.read_text()
        self.assertIn("pull-requests: write", wf)
        self.assertIn("github.event_name != 'pull_request'", wf)
        self.assertIn("janus/autonomous-code-state", wf)
        self.assertIn("integration_proposal.py prepare", wf)
        self.assertIn("integration_proposal.py verify", wf)
        self.assertIn("git merge-base --is-ancestor", wf)
        self.assertIn("git diff --cached --check", wf)
        self.assertIn("git push origin HEAD:refs/heads/", wf)
        self.assertNotIn("gh pr merge", wf)
        self.assertNotIn("--force", wf)
        self.assertNotIn("git push origin HEAD:main", wf)


if __name__ == "__main__":
    unittest.main()
