"""R1.3 read-only arithmetic replay tests, with simulated hostile receipts."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "janus_r13_receipt_replay",
    ROOT / "modules/autonomy_loop/verify_r13_receipt.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class R13ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        target = self.root / "experiments"
        target.mkdir()
        for name in ("closed_loop_retry_delay_r1", "closed_loop_retry_delay_r13"):
            shutil.copytree(ROOT / "experiments" / name, target / name)
        self.path = target / "closed_loop_retry_delay_r13/receipts/github-run-42482603402.json"

    def record(self):
        return json.loads(self.path.read_text())

    def write(self, obj):
        self.path.write_text(json.dumps(obj, indent=2) + "\n")

    def rehash_report(self, obj):
        trial = obj["report"]
        trial["report_sha256"] = m.sha(m.canon(
            {k:v for k,v in trial.items() if k != "report_sha256"}))

    def test_preserved_source_and_24_pairs_recalculate_exactly(self):
        result = m.verify(self.root)
        self.assertEqual(result["status"], "PASS_RECORDED_VALUES_ONLY")
        self.assertEqual(result["challenge_case_count"], 24)
        self.assertEqual(result["github_run_id"], 42482603402)
        self.assertFalse(result["production_baseline"])
        self.assertFalse(result["independent_timing_execution_reproduced"])
        self.assertFalse(result["external_blind"])
        self.assertEqual(result["authority_delta"], 0)

    def test_forged_raw_speedup_with_updated_report_digest_rejected(self):
        record = self.record()
        for i in range(7):
            record["report"]["pairs"][0]["raw_timeit_us_per_op"]["baseline"][i] += 1.0
        self.rehash_report(record)
        self.write(record)
        with self.assertRaisesRegex(m.Hold, "MEDIAN_REPLAY_CHANGED"):
            m.verify(self.root)

    def test_forged_neutral_control_with_updated_report_digest_rejected(self):
        record = self.record()
        record["report"]["pairs"][0]["neutral_abs_difference_us_per_op"] = 0.0
        self.rehash_report(record)
        self.write(record)
        with self.assertRaisesRegex(m.Hold, "PAIR_ARITHMETIC_CHANGED"):
            m.verify(self.root)

    def test_forged_external_validation_or_production_baseline_rejected(self):
        for field in ("externally_independent_blind", "reference_is_production_baseline",
                      "runtime_consumption_attested", "production_promotion", "auto_merge"):
            record = self.record()
            record["report"][field] = True
            self.rehash_report(record)
            self.write(record)
            with self.subTest(field=field), self.assertRaisesRegex(m.Hold, "TRIAL_IDENTITY_OR_DIGEST"):
                m.verify(self.root)
            self.write(json.loads((ROOT / "experiments/closed_loop_retry_delay_r13/receipts/github-run-42482603402.json").read_text()))

    def test_reordered_challenge_or_fake_source_sha_rejected(self):
        record = self.record()
        record["report"]["pairs"][0],record["report"]["pairs"][1]=(
            record["report"]["pairs"][1],record["report"]["pairs"][0])
        self.rehash_report(record)
        self.write(record)
        with self.assertRaisesRegex(m.Hold, "CHALLENGE_ORDER_CHANGED"):
            m.verify(self.root)
        record = self.record()
        record["preregistration"]["source_sha256"] = "f" * 64
        self.write(record)
        with self.assertRaisesRegex(m.Hold, "SOURCE_PREREGISTRATION"):
            m.verify(self.root)

    def test_mutated_preregistered_policy_or_artifact_metadata_rejected(self):
        file = self.root / "experiments/closed_loop_retry_delay_r13/CHALLENGE_PROTOCOL.json"
        p = json.loads(file.read_text())
        p["auto_merge"] = True
        file.write_text(json.dumps(p))
        with self.assertRaisesRegex(m.Hold, "CHALLENGE_POLICY_CHANGED"):
            m.verify(self.root)
        shutil.copyfile(ROOT / "experiments/closed_loop_retry_delay_r13/CHALLENGE_PROTOCOL.json", file)
        record = self.record()
        record["source_artifact"]["sha256"] = "sha256:bad"
        self.write(record)
        with self.assertRaisesRegex(m.Hold, "ARTIFACT_METADATA"):
            m.verify(self.root)

    def test_incomplete_raw_timing_rejected(self):
        record = self.record()
        record["report"]["pairs"][0]["raw_timeit_us_per_op"]["baseline"].pop()
        self.rehash_report(record)
        self.write(record)
        with self.assertRaisesRegex(m.Hold, "BAD_RAW_TIMER_VALUES"):
            m.verify(self.root)


if __name__ == "__main__":
    unittest.main()
