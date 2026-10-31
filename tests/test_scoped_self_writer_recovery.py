"""Adversarial offline tests for bounded automatic incident-to-review-PR planning."""
import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "modules/autonomy_coder"))
import scoped_recovery as s


class ScopedRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good = subprocess.check_output(
            ["git", "-C", str(ROOT), "show", s.INSTALL + ":" + s.TARGET])

    def test_exact_signed_known_good_source_is_idle_no_pr(self):
        # The contract MUST pass even if current production is regressed.
        # Otherwise the recovery workflow's prerequisite job would fail,
        # preventing the incident detector and clean repair from ever running.
        self.assertEqual(s.git_blob(self.good), s.GOOD_BLOB)
        decision = s.assess(self.good, self.good, "a" * 40, "b" * 64)
        self.assertEqual(decision["status"], "IDLE_KNOWN_GOOD")
        self.assertFalse(decision["auto_merge"])
        self.assertFalse(decision["production_modified"])
        self.assertFalse(decision["full_autonomy"])
        self.assertNotIn("candidate_branch", decision)

    def test_regression_does_not_poison_healthy_contract(self):
        from unittest.mock import patch
        altered = self.good + b"# simulated drift, never on main\\n"
        self.assertNotEqual(s.git_blob(altered), s.GOOD_BLOB)
        with patch.object(Path, "read_bytes", side_effect=AssertionError(
                "Healthy contract must not inspect mutable production source")):
            decision = s.assess(self.good, self.good, "b"*40, "c"*64)
        self.assertEqual(decision["status"], "IDLE_KNOWN_GOOD")
        simulated = s.assess(altered, self.good, "b"*40, "c"*64)
        self.assertEqual(simulated["status"], "SCOPED_RESTORE_PR_ELIGIBLE")
        self.assertFalse(simulated["auto_merge"])

    def test_one_byte_source_drift_creates_only_known_good_review_candidate(self):
        bad = self.good.replace(b"def floor_age_us(delta_us):",
                                b"def floor_age_us(delta_us): # forged", 1)
        self.assertNotEqual(bad, self.good)
        plan = s.assess(bad, self.good, "f" * 40, "d" * 64)
        self.assertEqual(plan["status"], "SCOPED_RESTORE_PR_ELIGIBLE")
        self.assertEqual(plan["patch_files"], [s.TARGET])
        self.assertEqual(plan["trusted_installed_source_blob"], s.GOOD_BLOB)
        self.assertEqual(plan["candidate_source_sha256"], hashlib.sha256(self.good).hexdigest())
        self.assertTrue(plan["human_review_required"])
        self.assertFalse(plan["auto_merge"])
        self.assertEqual(plan["authority_delta"], 0)
        self.assertFalse(plan["new_code_written_by_model"])
        self.assertEqual(plan["candidate_branch"],
                         "janus/recover-repair001-" + s.git_blob(bad)[:16])

    def test_untrusted_install_or_head_is_denied(self):
        for fake in [b"def floor_age_us(delta_us):\n    return 1\n",
                     self.good + b"\n"]:
            with self.subTest(fake=fake[:30]):
                with self.assertRaisesRegex(s.Hold, "RESTORE_TARGET_NOT_SIGNED_SOURCE"):
                    s.assess(b"bad", fake, "a" * 40, "b" * 64)
        with self.assertRaisesRegex(s.Hold, "INVALID_PARENT_SHA"):
            s.assess(b"bad", self.good, "not-a-commit", "b" * 64)

    def test_archive_on_real_main_and_pinned_git(self):
        good, archive, evidence = s.exact_archive(ROOT)
        self.assertEqual(good, self.good)
        self.assertEqual(evidence["record_id"], "JANUS_SELF_WRITER_REAL_REPAIR_001")
        self.assertEqual((ROOT / s.JOURNAL).read_bytes(), archive)
        self.assertFalse(evidence["model_proposal"]["raw_source_admitted"])

    def test_archive_tampering_is_hold_even_if_current_code_is_good(self):
        with TemporaryDirectory() as name:
            root = Path(name)
            path = root / s.JOURNAL
            path.parent.mkdir(parents=True)
            path.write_bytes(b'{"forged":true}\n')
            def fake_git(_root, *args):
                return self.good if args[1].startswith(s.INSTALL) else b'{"legit":true}\n'
            with self.assertRaisesRegex(s.Hold, "CANONICAL_ARCHIVE_ABSENT_OR_TAMPERED"):
                s.exact_archive(root, git_read=fake_git)

    def test_no_model_writer_runtime_or_direct_main_push(self):
        source = (ROOT / "modules/autonomy_coder/scoped_recovery.py").read_text()
        self.assertNotIn("git push", source)
        self.assertNotIn('"auto_merge": True', source)
        self.assertNotIn("openai.api", source.lower())
        self.assertNotIn("rowan_api_key", source.lower())
        self.assertNotIn("subprocess.run([source", source)
        self.assertIn("RESTORE_EXACT_PREVIOUSLY_VERIFIED_CODE_ONLY", source)


if __name__ == "__main__":
    unittest.main()
