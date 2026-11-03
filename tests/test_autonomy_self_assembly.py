"""Contract: owner-directed JANUS self-assembly is traceable data, never authority."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest

from test_autonomy_loop import m, snapshot


class SelfAssemblyDirectiveTests(unittest.TestCase):
    def test_registered_directive_is_source_bound_and_read_only(self):
        record = snapshot()
        with tempfile.TemporaryDirectory() as td:
            pointer = m.persist(td, record)
            path = Path(td) / "data/autonomy_loop/SELF_ASSEMBLY_TASK.json"
            self.assertTrue(path.is_file())
            task = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(task["schema"], "janus.autonomy.self_assembly_task.v1")
            self.assertEqual(task["issue"], "https://github.com/Hawkar-usls/janus-meta-registry/issues/440")
            self.assertEqual(task["source_snapshot_sha256"], pointer["state_sha256"])
            self.assertEqual(task["source_observation_id"], record["observation_id"])
            self.assertEqual(task["current_phase"], "P0.1")
            self.assertEqual(task["next_reviewed_objective"], "VERIFY_SOURCE_PINNED_SNAPSHOT")
            self.assertEqual(task["execution_state"], "REGISTERED_NOT_EXECUTION_ATTESTED")
            self.assertEqual(task["admission"], "EXISTING_REVIEWED_HANDLER_ONLY_OR_WAIT_HOLD")
            self.assertEqual(task["authority_delta"], 0)
            self.assertIs(task["auto_merge"], False)
            self.assertIs(task["new_paid_jobs"], False)
            self.assertIs(task["full_autonomy_proven"], False)
            roadmap = (Path(td) / "data/autonomy_loop/ROADMAP.md").read_text(encoding="utf-8")
            self.assertIn("issues/440", roadmap)
            self.assertIn("registered, not executable", roadmap)
            self.assertIn("P0.1", roadmap)

    def test_next_phase_is_derived_not_granted_by_issue_text(self):
        record = snapshot({"accepted_phases": {
            "P0.1": {"status": "PASS_STATUS_CAPTURE_ONLY"},
            "P0.2": {"status": "PASS_SOURCE_COHORT_ONLY", "canonical_run": 123}
        }})
        self.assertEqual(record["current_phase"], "P0.3")
        task = m.self_assembly_task(record)
        self.assertEqual(task["current_phase"], "P0.3")
        self.assertEqual(task["next_reviewed_objective"],
                         "VERIFY_BEETLE_ACK_AND_CLOUD_HOME_HANDOFF")
        self.assertFalse(task["full_autonomy_proven"])

    def test_unadmitted_phase_is_hold(self):
        record = snapshot()
        record["current_phase"] = "UNREVIEWED_EXPANSION"
        with self.assertRaises(m.Hold):
            m.self_assembly_task(record)

    def test_blockers_are_sorted_and_deduplicated(self):
        record = snapshot()
        record["findings"] = [
            {"phase": "P0.1", "reason": "SOURCE_UNKNOWN_B"},
            {"phase": "P0.1", "reason": "SOURCE_UNKNOWN_A"},
            {"phase": "P0.1", "reason": "SOURCE_UNKNOWN_A"},
            {"phase": "P2", "reason": "UNRELATED"},
        ]
        task = m.self_assembly_task(record)
        self.assertEqual(task["current_phase_blockers"],
                         ["SOURCE_UNKNOWN_A", "SOURCE_UNKNOWN_B"])


if __name__ == "__main__":
    unittest.main()
