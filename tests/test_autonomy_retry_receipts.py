"""Recheck R1.2 immutable GitHub measurements without network, Docker or secrets."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "modules/autonomy_loop/verify_retry_receipts.py"
spec = importlib.util.spec_from_file_location("janus_retry_receipt_verify", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
FOLDER = ROOT / "experiments/closed_loop_retry_delay_r1"


def fixtures():
    paths = sorted((FOLDER / "receipts").glob("github-run-*.json"))
    return (
        [json.loads(p.read_text()) for p in paths],
        json.loads((FOLDER / "PROTOCOL.json").read_text()),
        (FOLDER / "BASELINE.py").read_bytes(),
        json.loads((FOLDER / "TRAIN_MANIFEST.json").read_text()),
        json.loads((FOLDER / "HOLDOUT_MANIFEST.json").read_text()),
    )


def check(record, protocol, baseline, train, holdout):
    return m.verify(record, protocol=protocol, baseline=baseline,
                    training=train, holdout=holdout)


class RetryReceiptIntegrityTests(unittest.TestCase):
    def test_all_durable_receipts_replay_safely(self):
        rows = m.verify_all()
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(len({x["github_run_id"] for x in rows}), len(rows))
        for row in rows:
            self.assertEqual(row["status"], "PASS_SOURCE_BOUND_SCREEN_REPLAY_ONLY")
            self.assertFalse(row["independent_timing_replay_attested"])
            self.assertFalse(row["production_baseline_attested"])
            self.assertFalse(row["runtime_consumption_attested"])
            self.assertEqual(row["authority_delta"], 0)

    def test_forged_better_latency_is_rejected_even_if_positive(self):
        records, p, b, t, h = fixtures()
        forged = copy.deepcopy(records[0])
        forged["trial"]["measurement"]["case_rows"][0]["candidate"] = 0.000001
        with self.assertRaisesRegex(m.Hold, "TRIAL_DIGEST_CHANGED"):
            check(forged, p, b, t, h)

    def test_rebinding_candidate_source_is_rejected(self):
        records, p, b, t, h = fixtures()
        forged = copy.deepcopy(records[0])
        forged["trial"]["candidate_source_sha256"] = "f" * 64
        with self.assertRaisesRegex(m.Hold, "TRIAL_SCOPE_CHANGED"):
            check(forged, p, b, t, h)

    def test_mutated_screen_or_result_metadata_rejected(self):
        records, p, b, t, h = fixtures()
        forged = copy.deepcopy(records[0])
        forged["screen"]["status"] = "ELIGIBLE_FOR_PRODUCTION"
        with self.assertRaisesRegex(m.Hold, "SCREEN_REPLAY_MISMATCH"):
            check(forged, p, b, t, h)
        forged = copy.deepcopy(records[0])
        forged["source_run"]["status"] = "in_progress"
        with self.assertRaisesRegex(m.Hold, "RUN_PROVENANCE_INVALID"):
            check(forged, p, b, t, h)

    def test_fake_artifact_or_other_run_rejected(self):
        records, p, b, t, h = fixtures()
        forged = copy.deepcopy(records[0])
        forged["source_artifact"]["archive_sha256"] = "sha256:bad"
        with self.assertRaisesRegex(m.Hold, "ARTIFACT_PROVENANCE_INVALID"):
            check(forged, p, b, t, h)
        forged = copy.deepcopy(records[0])
        forged["source_run"]["id"] += 1
        with self.assertRaises(m.Hold):
            check(forged, p, b, t, h)

    def test_same_train_holdout_or_changed_baseline_rejected(self):
        records, p, b, t, h = fixtures()
        with self.assertRaisesRegex(m.Hold, "BASELINE_SOURCE_REBOUND"):
            check(records[0], p, b + b"#changed\n", t, h)
        broken = copy.deepcopy(h)
        broken["cases"][0]["cap"] = t["cases"][0]["cap"]
        with self.assertRaisesRegex(m.Hold, "MANIFEST_REBOUND"):
            check(records[0], p, b, t, broken)

    def test_authority_escalation_does_not_pass(self):
        records, p, b, t, h = fixtures()
        for field, value in [("runtime_install", True),
                             ("auto_merge", True),
                             ("independent_replay_attested", True),
                             ("production_baseline_attested", True),
                             ("scientific_promotion", True),
                             ("authority_delta", 1)]:
            forged = copy.deepcopy(records[0])
            forged["review"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(m.Hold, "REVIEW_AUTHORITY_CHANGED"):
                check(forged, p, b, t, h)

    def test_broken_protocol_sha_and_missing_case_rejected(self):
        records, p, b, t, h = fixtures()
        bad = dict(p)
        bad["minimum_mean_gain"] = 999
        with self.assertRaises(m.Hold):
            check(records[0], bad, b, t, h)
        bad = copy.deepcopy(h)
        bad["cases"].pop()
        with self.assertRaises(m.Hold):
            check(records[0], p, b, t, bad)


if __name__ == "__main__":
    unittest.main()
