"""R1.3 precommitted challenge controls; DOES NOT execute benchmark on runner host."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "modules/autonomy_loop/r13_independent_retry_replay.py"
spec = importlib.util.spec_from_file_location("janus_r13_challenge", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

CANDIDATE = "def retry_delay(attempt, cap):\n    return min(cap, 2 ** attempt)\n"


class R13FrozenChallengeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        path = self.root / "candidate_modules/retry_delay/module.py"
        path.parent.mkdir(parents=True)
        path.write_text(CANDIDATE, encoding="utf-8")

    def test_challenge_pre_registered_before_first_benchmark(self):
        record, challenge_sha, cases, baseline, candidate = m.validate_inputs(self.root)
        self.assertEqual(record["fresh_case_count"], 24)
        self.assertEqual(len(cases), 24)
        self.assertEqual(len(set(cases)), 24)
        self.assertEqual(m.sha(candidate), m.CANDIDATE_SHA)
        self.assertEqual(m.sha(baseline), m.BASELINE_SHA)
        self.assertEqual(len(challenge_sha), 64)
        self.assertFalse(record["auto_merge"])
        self.assertFalse(record["network"])
        self.assertTrue(record["read_only"])
        self.assertTrue(record["result_does_not_prove_runtime_improvement"])

    def test_cases_exclude_original_training_and_holdout(self):
        _, _, cases, _, _ = m.validate_inputs(self.root)
        old = json.loads((m.FOLDER / "TRAIN_MANIFEST.json").read_text())["cases"]
        old += json.loads((m.FOLDER / "HOLDOUT_MANIFEST.json").read_text())["cases"]
        excluded = {(x["attempt"], x["cap"]) for x in old}
        self.assertTrue(all(x not in excluded for x in cases))
        self.assertTrue(all(0 <= a <= 12 and 1 <= c <= 900 for a,c in cases))

    def test_baseline_has_no_production_admission_even_if_behavior_matches(self):
        baseline = (m.FOLDER / "BASELINE.py").read_text()
        import sys
        sys.path.insert(0, str(ROOT / "modules/autonomy_coder"))
        from policy import validate_source
        with self.assertRaisesRegex(ValueError, "FORBIDDEN_CALL"):
            validate_source(baseline, "retry_delay")
        self.assertEqual(m.independently_check(m.load_function(baseline.encode(), "baseline")), 291)
        self.assertEqual(m.independently_check(m.load_function(CANDIDATE.encode(), "candidate")), 291)

    def test_reject_source_sha_drift(self):
        path = self.root / "candidate_modules/retry_delay/module.py"
        path.write_text(CANDIDATE.replace("2 ** attempt", "2 ** (attempt + 1)"))
        with self.assertRaisesRegex(m.Hold, "SOURCE_SHA_CHANGED"):
            m.validate_inputs(self.root)

    def test_reject_changed_preregistration_security(self):
        changed = json.loads(m.CHALLENGE_FILE.read_bytes())
        changed["auto_merge"] = True
        with tempfile.TemporaryDirectory() as folder:
            temporary = Path(folder) / "changed.json"
            temporary.write_text(json.dumps(changed))
            with patch.object(m, "CHALLENGE_FILE", temporary):
                with self.assertRaisesRegex(m.Hold, "CHALLENGE_POLICY_DRIFT"):
                    m.validate_inputs(self.root)

    def test_reject_unpinned_commit(self):
        with self.assertRaisesRegex(m.Hold, "UNPINNED_EXPERIMENT_COMMIT"):
            m.run(self.root, source_head="main", github_run_id="1")


if __name__ == "__main__":
    unittest.main()
