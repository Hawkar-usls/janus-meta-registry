"""Offline adversarial tests: a green CI run is not proof of improvement."""
import copy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).parents[1] / "modules/autonomy_loop/proof_of_improvement.py"
spec = importlib.util.spec_from_file_location("janus_improvement_screen", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture():
    protocol = {
        "schema": m.PROTOCOL_SCHEMA,
        "task_id": "safe_retry_patch",
        "baseline_sha256": "a" * 64,
        "train_manifest_sha256": "1" * 64,
        "holdout_manifest_sha256": "2" * 64,
        "case_ids": [f"frozen-case-{i:02d}" for i in range(8)],
        "metric": "latency_ms",
        "direction": "lower",
        "minimum_mean_gain": 2.0,
        "max_regressions": 0,
        "authority_delta": 0,
        "allow_auto_merge": False,
    }
    measurement = {
        "schema": m.MEASUREMENT_SCHEMA,
        "protocol_sha256": m.digest(protocol),
        "candidate_sha256": "b" * 64,
        "evaluator_commit": "c" * 40,
        "case_rows": [
            {"case_id": case, "baseline": 20.0, "candidate": 10.0}
            for case in protocol["case_ids"]
        ],
        "authority_delta": 0,
    }
    return protocol, measurement


class ImprovementScreenTests(unittest.TestCase):
    def test_positive_comparison_is_not_production_or_independent_proof(self):
        spec, run = fixture()
        result = m.screen(spec, run)
        self.assertEqual(result["status"], "ELIGIBLE_FOR_INDEPENDENT_REPLAY")
        self.assertEqual(result["mean_paired_gain"], 10.0)
        self.assertEqual(result["case_count"], 8)
        self.assertFalse(result["independent_replay_attested"])
        self.assertFalse(result["runtime_consumption_attested"])
        self.assertFalse(result["production_promotion"])
        self.assertFalse(result["allow_auto_merge"])
        self.assertEqual(result["authority_delta"], 0)
        signed = dict(result)
        signed.pop("verdict_sha256")
        self.assertEqual(result["verdict_sha256"], m.digest(signed))

    def test_frozen_case_order_controls_arithmetic_not_input_order(self):
        spec, run = fixture()
        before = m.screen(spec, run)
        run["case_rows"].reverse()
        after = m.screen(spec, run)
        self.assertEqual(after["mean_paired_gain"], before["mean_paired_gain"])
        self.assertEqual(after["status"], before["status"])

    def test_identical_or_too_small_gain_does_not_pass(self):
        spec, run = fixture()
        for item in run["case_rows"]:
            item["candidate"] = item["baseline"]
        self.assertEqual(m.screen(spec, run)["status"],
                         "REJECTED_NO_MEASURED_IMPROVEMENT")
        for item in run["case_rows"]:
            item["candidate"] = item["baseline"] - 1
        self.assertEqual(m.screen(spec, run)["status"],
                         "REJECTED_NO_MEASURED_IMPROVEMENT")

    def test_regression_rejects_even_positive_average(self):
        spec, run = fixture()
        run["case_rows"][0]["candidate"] = 21.0
        value = m.screen(spec, run)
        self.assertGreater(value["mean_paired_gain"], 0)
        self.assertEqual(value["regressions"], 1)
        self.assertEqual(value["status"], "REJECTED_NO_MEASURED_IMPROVEMENT")

    def test_higher_is_better_metric_is_supported(self):
        spec, run = fixture()
        spec["direction"] = "higher"
        spec["metric"] = "quality_score"
        run["protocol_sha256"] = m.digest(spec)
        for item in run["case_rows"]:
            item["baseline"], item["candidate"] = item["candidate"], item["baseline"]
        self.assertEqual(m.screen(spec, run)["status"],
                         "ELIGIBLE_FOR_INDEPENDENT_REPLAY")

    def test_protocol_sha_mutation_or_case_rebinding_is_denied(self):
        spec, run = fixture()
        bad = copy.deepcopy(spec)
        bad["minimum_mean_gain"] = 999
        with self.assertRaisesRegex(m.EvidenceHold, "PROTOCOL_REBINDING"):
            m.screen(bad, run)
        run["case_rows"][0]["case_id"] = "another-case"
        with self.assertRaisesRegex(m.EvidenceHold, "HOLDOUT_CASE_REBINDING"):
            m.screen(spec, run)

    def test_duplicate_missing_or_extra_cases_denied(self):
        spec, run = fixture()
        run["case_rows"][0]["case_id"] = run["case_rows"][1]["case_id"]
        with self.assertRaisesRegex(m.EvidenceHold, "DUPLICATE"):
            m.screen(spec, run)
        spec, run = fixture()
        run["case_rows"].pop()
        with self.assertRaisesRegex(m.EvidenceHold, "INCOMPLETE"):
            m.screen(spec, run)
        spec, run = fixture()
        spec["case_ids"][0] = spec["case_ids"][1]
        run["protocol_sha256"] = m.digest(spec)
        with self.assertRaisesRegex(m.EvidenceHold, "FROZEN_CASE_SET"):
            m.screen(spec, run)

    def test_nonfinite_boolean_and_oversize_values_are_denied(self):
        for value in (float("nan"), float("inf"), True, 10 ** 20, -float("inf")):
            spec, run = fixture()
            run["case_rows"][0]["candidate"] = value
            with self.subTest(value=str(value)):
                with self.assertRaisesRegex(m.EvidenceHold, "NONFINITE"):
                    m.screen(spec, run)

    def test_training_holdout_digest_collision_is_denied(self):
        spec, run = fixture()
        spec["train_manifest_sha256"] = spec["holdout_manifest_sha256"]
        run["protocol_sha256"] = m.digest(spec)
        with self.assertRaisesRegex(m.EvidenceHold, "TRAIN_HOLDOUT"):
            m.screen(spec, run)

    def test_no_authority_no_auto_merge_and_no_identity_candidate(self):
        spec, run = fixture()
        for field, value in (("authority_delta", 1), ("allow_auto_merge", True)):
            bad = dict(spec)
            bad[field] = value
            run["protocol_sha256"] = m.digest(bad)
            with self.subTest(field=field):
                with self.assertRaises(m.EvidenceHold):
                    m.screen(bad, run)
        spec, run = fixture()
        run["authority_delta"] = 1
        with self.assertRaisesRegex(m.EvidenceHold, "AUTHORITY_PROMOTION"):
            m.screen(spec, run)
        spec, run = fixture()
        run["candidate_sha256"] = spec["baseline_sha256"]
        with self.assertRaisesRegex(m.EvidenceHold, "SAME_CODE"):
            m.screen(spec, run)

    def test_forged_evaluator_and_short_case_set_denied(self):
        spec, run = fixture()
        run["evaluator_commit"] = "not-a-commit"
        with self.assertRaisesRegex(m.EvidenceHold, "UNPINNED"):
            m.screen(spec, run)
        spec, run = fixture()
        spec["case_ids"] = spec["case_ids"][:3]
        run["case_rows"] = run["case_rows"][:3]
        run["protocol_sha256"] = m.digest(spec)
        with self.assertRaisesRegex(m.EvidenceHold, "FROZEN_CASE_SET"):
            m.screen(spec, run)


if __name__ == "__main__":
    unittest.main()
