"""Reproduce and prevent a real JANUS self-writer → autonomy wake gap.

The genuine model-authored freshness consumer reported STALE in cloud run
41145475823; the original roadmap workflow was NOT subscribed to its
completion. The repair must retain the exact previous source/authority gates.
No model output is trusted as a shell command, credential or permission.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/janus-autonomy-roadmap-loop.yml"
MODEL_CONSUMER = ROOT / ".github/workflows/janus-self-writer-real-operational-consumer.yml"
NAME = "JANUS Self-Writer Real Operational Consumer"


def admitted_completed_wakers(text):
    found = re.search(r"^\s*workflows:\s*\[([^\n]+)\]", text, re.M)
    if not found:
        raise ValueError("AUTONOMY_WORKFLOW_RUN_MISSING")
    return frozenset(re.findall(r'["\']([^"\']+)["\']', found.group(1)))


class RealSelfWriterWakeRepairTests(unittest.TestCase):
    def setUp(self):
        self.src = WORKFLOW.read_text(encoding="utf-8")
        self.consumer = MODEL_CONSUMER.read_text(encoding="utf-8")

    def test_reproduces_pre_fix_missing_event_subscription(self):
        # The old roadmap subscribed only to Rowan and Beetle, despite a
        # genuine successful self-writer observation from main.
        historical = self.src.replace('"' + NAME + '", ', '').replace(
            ', "' + NAME + '"', '')
        self.assertNotIn(NAME, admitted_completed_wakers(historical))
        self.assertIn(NAME, admitted_completed_wakers(self.src))

    def test_exact_cloud_consumer_identity_and_bounded_wake(self):
        self.assertRegex(self.consumer, r"(?m)^name:\s*" + re.escape(NAME) + r"$")
        allow = admitted_completed_wakers(self.src)
        self.assertEqual(allow, frozenset({
            "JANUS Rowan Durable Observer", "JANUS Beetle Memory Receiver", NAME,
            "JANUS Rowan AURA Demiurge autonomous council reconciliation"
        }))
        self.assertIn("types: [completed]", self.src)
        self.assertIn("branches: [main]", self.src)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", self.src)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", self.src)
        self.assertIn("github.event.workflow_run.head_repository.full_name == github.repository", self.src)
        self.assertIn("github.event.workflow_run.event != 'pull_request'", self.src)
        self.assertIn("github.event_name != 'pull_request'", self.src)

    def test_council_completion_wakes_current_p02_recheck_without_cross_repo_dispatch(self):
        council_name = "JANUS Rowan AURA Demiurge autonomous council reconciliation"
        council = ROOT / ".github/workflows/rowan-coordination-autonomous-reconcile.yml"
        text = council.read_text(encoding="utf-8")
        self.assertIn("name: " + council_name, text)
        self.assertIn(council_name, admitted_completed_wakers(self.src))
        self.assertIn('"' + council_name + '") ;;', self.src)
        self.assertIn("github.event.workflow_run.event != 'pull_request'", self.src)
        event = self.src.split("\n  push:\n", 1)[1].split("\n  pull_request:\n", 1)[0]
        self.assertIn("'data/rowan/CANONICAL_STATE.json'", event)
        self.assertIn("'data/rowan/coordination/LATEST_COORDINATION_STATE.json'", event)
        self.assertNotIn("data/autonomy_loop/", event)
        self.assertNotIn("repository_dispatch:", self.src)

    def test_no_model_assigned_permissions_or_live_fix_fabrication(self):
        self.assertIn("permissions:\n  contents: read", self.src)
        self.assertIn("permissions:\n      contents: write", self.src)
        self.assertIn("JANUS_AUTONOMY_WAKE_AUTHORITY_DELTA=0", self.src)
        self.assertIn("JANUS_AUTONOMY_WAKE_SOURCE=$UPSTREAM_NAME", self.src)
        self.assertIn('test "$UPSTREAM_CONCLUSION" = success', self.src)
        self.assertIn('test "$UPSTREAM_BRANCH" = main', self.src)
        self.assertIn("git pull --ff-only origin main", self.src)
        self.assertIn("git rebase --abort || true", self.src)
        self.assertNotIn("git push --force", self.src)
        self.assertNotIn("git reset --hard", self.src)
        self.assertNotIn("curl -X POST", self.src)

    def test_no_trigger_loop_back_to_writer_via_metadata_only(self):
        # Roadmap's save only writes its own existing metadata allowlist.
        self.assertIn("git add -- data/autonomy_loop/ data/rowan/coordination/", self.src)
        self.assertIn("git add -- data/autonomy_loop/", self.src)
        self.assertIn("cron: '19 * * * *'", self.src)
        self.assertIn("cron: '07 */6 * * *'", self.consumer)
        self.assertIn("paths:\n      - 'modules/autonomy_coder/real_operational_consumer.py'", self.consumer)
        # Nothing treats a stale flag as authenticated permission to update
        # source code or to forge a fresh LATEST snapshot.
        self.assertNotIn("SELF_WRITER_STALE_FORCE_PASS", self.src)
        self.assertNotIn("on: [workflow_run, workflow_run]", self.src)


if __name__ == "__main__":
    unittest.main()
