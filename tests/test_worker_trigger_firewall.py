"""Offline no-provider regression gates for GitHub worker derivative-trigger fan-out.

Tests the documented exclusion contracts; does not simulate GitHub scheduler or
assert a specific count of saved Actions minutes.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DERIVED = (
    "EYE/generated/",
    "EYE/r2/generated/",
    "EYE/r3/generated/",
    "assets/hrain-full-memory/",
    "assets/hrain-registry-index.json",
    "assets/site-feed.json",
    "data/autonomy_loop/",
    "data/JANUS-NEURAL-LINK/",
)
FLOW = ROOT / ".github/workflows"

PATH_FILTERED = (
    "eye-meta-registry-train.yml",
    "eye-r2-novel-bridge-miner.yml",
    "eye-r3-hidden-machine-miner.yml",
    "janus-site-autonomous-curator.yml",
    "connection-full-registry-discovery.yml",
    "connection-full-registry-discovery-v02.yml",
    "connection-full-registry-discovery-v021.yml",
)
IGNORED_PUSH = "janus-neural-link-archive.yml"


def event_section(workflow: str) -> str:
    text = (FLOW / workflow).read_text(encoding="utf-8")
    if "\non:\n" not in text:
        raise AssertionError("missing event section: " + workflow)
    event = text.split("\non:\n", 1)[1]
    return event.split("\npermissions:\n", 1)[0].split("\nconcurrency:\n", 1)[0].split("\njobs:\n", 1)[0]


class WorkerDerivativeTriggerFirewall(unittest.TestCase):
    def test_derived_only_push_is_excluded_from_broad_workers(self):
        for workflow in PATH_FILTERED:
            with self.subTest(workflow=workflow):
                event = event_section(workflow)
                self.assertIn("push:", event)
                self.assertIn("paths:", event)
                for path in DERIVED:
                    self.assertIn("      - '!"+path+"**'" if False else
                                  "      - '!"+path+("**" if path.endswith("/") else "")+"'", event)

    def test_source_file_changes_remain_admitted(self):
        for workflow in PATH_FILTERED:
            with self.subTest(workflow=workflow):
                event = event_section(workflow)
                self.assertTrue(any(token in event for token in (
                    "      - '**'", "      - '**/*.json'")))
                self.assertIn("workflow_dispatch:", event) if workflow.startswith("eye-") or workflow.startswith("connection-") else self.assertIn("pull_request:", event)

    def test_site_has_same_guards_for_pr_and_push(self):
        event = event_section("janus-site-autonomous-curator.yml")
        self.assertEqual(event.count("      - '!EYE/generated/**'"), 2)
        self.assertEqual(event.count("      - '!assets/hrain-full-memory/**'"), 2)
        self.assertIn("      - '**/*.md'", event)
        self.assertIn("      - '**/*.py'", event)

    def test_neural_archive_keeps_both_fallback_wakes(self):
        text = (FLOW / IGNORED_PUSH).read_text(encoding="utf-8")
        event = event_section(IGNORED_PUSH)
        self.assertIn("cron: '*/5 * * * *'", text)
        self.assertIn("workflow_run:", event)
        self.assertIn("workflows: ['JANUS Native Proposal Relay']", event)
        self.assertIn("paths-ignore:", event)
        for derived in DERIVED:
            path = derived + ("**" if derived.endswith("/") else "")
            self.assertIn("      - '"+path+"'", event)

    def test_security_guard_is_never_filtered(self):
        text = (FLOW / "janus-secret-persistence-guard.yml").read_text()
        self.assertIn("  pull_request:", text)
        self.assertIn("  push:", text)
        self.assertIn("contents: read", text)
        self.assertNotIn("paths-ignore:", text)

    def test_hraIn_current_catalog_not_weakened(self):
        text = (FLOW / "janus-hrain-full-memory.yml").read_text()
        self.assertIn("  push:", text)
        self.assertIn("paths-ignore:", text)
        self.assertIn("- 'assets/hrain-full-memory/**'", text)
        self.assertIn("coverage_complete", text)
        self.assertIn("needs: contract", text)

    def test_eye_indexer_excludes_derivative_outputs_but_keeps_source(self):
        path = ROOT / "EYE/training/train_eye_registry.py"
        spec = importlib.util.spec_from_file_location("eye_trainer_derivative_firewall", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            source = root / "data/rowan/CANONICAL_STATE.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"canonical":true}')
            for derived in DERIVED:
                p = root / derived
                if derived.endswith("/"):
                    p = p / "derived.json"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('{"derivative":true}')
            files = {p.relative_to(root).as_posix() for p in module.iter_files(root)}
            self.assertIn("data/rowan/CANONICAL_STATE.json", files)
            for derived in ("EYE/generated/derived.json",
                            "EYE/r2/generated/derived.json",
                            "EYE/r3/generated/derived.json",
                            "assets/hrain-full-memory/derived.json",
                            "assets/hrain-registry-index.json",
                            "assets/site-feed.json",
                            "data/autonomy_loop/derived.json"):
                self.assertNotIn(derived, files)

    def test_downstream_r2_r3_have_separate_provenance_firewall(self):
        for source in ("EYE/r2/eye_r2_novel_bridge_miner.py",
                       "EYE/r3/eye_r3_hidden_machine_miner.py"):
            s = (ROOT / source).read_text()
            self.assertIn("EYE/r3/generated/", s)
            self.assertIn("assets/site-feed.json", s)
            self.assertIn("data/autonomy_loop/", s)

    def test_no_provider_or_autoscaling_authority_in_trigger_patch(self):
        w = (FLOW / "janus-worker-trigger-firewall.yml").read_text()
        for forbidden in ("workflow_run:", "repository_dispatch:",
                          "gh workflow run", "GITHUB_TOKEN:", "contents: write",
                          "pull_request_target:"):
            self.assertNotIn(forbidden, w)
        self.assertIn("contents: read", w)


if __name__ == "__main__":
    unittest.main()
