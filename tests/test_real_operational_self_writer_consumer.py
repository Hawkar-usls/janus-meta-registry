"""Adversarial real operational self-writer consumer tests; no network or Docker."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules/autonomy_coder"))
import real_operational_consumer as c

SOURCE = "def is_fresh(age, max_age):\n    return 0 <= age <= max_age\n"
NOW = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)


class RealOperationalConsumerTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.state = self.root / "state"
        self.latest = self.root / "LATEST.json"
        folder = self.state / "self_modules/is_fresh"
        folder.mkdir(parents=True)
        (folder / "module.py").write_bytes(SOURCE.encode())
        self.assertEqual(hashlib.sha256(SOURCE.encode()).hexdigest(),
                         c.EXPECTED_SOURCE_SHA256)
        (folder / "MODULE.json").write_text(json.dumps({
            "module_id": "janus.pure.is_fresh.v1",
            "source_sha256": c.EXPECTED_SOURCE_SHA256,
            "author_model": "Qwen/Qwen2.5-Coder-0.5B-Instruct",
            "not_native_janus_model": True,
            "import_into_trusted_main": False,
            "permissions": [],
            "authority_delta": 0,
            "review_required_for_integration": True,
        }))
        (self.state / "MODULE_INDEX.json").write_text(json.dumps({
            "model_authorship": "EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS",
            "runtime_auto_import": False, "authority_delta": 0,
            "modules": {"is_fresh": {"source_sha256": c.EXPECTED_SOURCE_SHA256}},
        }))
        self.set_age(120)
        self.mock_verify = patch.object(c.module_registry, "verify", return_value={
            "status": "VERIFIED_ISOLATED_MODULE_CATALOG"
        })
        self.mock_verify.start()
        self.addCleanup(self.mock_verify.stop)

    def set_age(self, seconds):
        observed = NOW - timedelta(seconds=seconds)
        self.latest.write_text(json.dumps({
            "schema": "janus.autonomy.latest.v1",
            "ecosystem_status": "AUTONOMY_PARTIAL",
            "last_observed_at_utc": observed.isoformat().replace("+00:00", "Z")
        }))

    def fake_check(self, source, task, *, call, seed):
        self.assertEqual(source, SOURCE)
        self.assertEqual(task, "is_fresh")
        self.assertEqual(seed, "janus-real-operational-freshness-20261031")
        self.assertEqual(call[1], 3600)
        self.assertTrue(-10000 <= call[0] <= 10000)
        return {"status": "PASS_PURE_FUNCTION_ONLY", "cases": 270,
                "value": 0 <= call[0] <= call[1]}

    def run_probe(self, check=None):
        return c.probe(self.state, self.latest, now=NOW, check=check or self.fake_check)

    def test_real_model_authored_freshness_candidate_is_consumable(self):
        r = self.run_probe()
        self.assertEqual(r["status"], "FRESH_SOURCE_DIAGNOSTIC_ONLY")
        self.assertEqual(r["model_authorship"],
                         "EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS")
        self.assertFalse(r["installed_into_trusted_runtime"])
        self.assertEqual(r["authority_delta"], 0)
        self.assertEqual(r["behavioral_cases"], 270)

    def test_expired_and_future_snapshot_hard_hold(self):
        for age in (3601, 12000, 1000000, -1, -500000):
            with self.subTest(age=age):
                self.set_age(age)
                r = self.run_probe()
                self.assertEqual(r["status"], "STALE_SOURCE_DIAGNOSTIC_ONLY")
                self.assertEqual(r["age_seconds"], age)
        self.set_age(3600)
        self.assertEqual(self.run_probe()["status"], "FRESH_SOURCE_DIAGNOSTIC_ONLY")

    def test_actual_model_compiled_helper_byte_identity(self):
        source = (Path(__file__).resolve().parents[1] /
                  "modules/autonomy_coder/real_operational_consumer.py").read_text()
        start = source.index("def floor_age_us(delta_us):")
        end = source.index("\n\ndef _timestamp", start)
        compiled_bytes = (source[start:end].rstrip("\n") + "\n").encode()
        self.assertEqual(
            hashlib.sha256(compiled_bytes).hexdigest(),
            "812096e5305073344e3a4e19a46e3f888f42f2d1760ef81ae8ba5fb76c625405"
        )
        for offset_us in (-10**16-1, -1500000, -500000, -1, 0, 1,
                          999999, 1000000, 1500000, 10**16+1):
            self.assertEqual(c.floor_age_us(offset_us), offset_us // 1000000)

    def test_real_future_subsecond_bug_fixed_and_exact_expiry_boundary(self):
        # Original production accepted a future +0.5s timestamp as age 0
        # because int(-0.5)==0. This is a real observed code defect.
        cases_us = (
            -1500000, -999999, -500000, -1, 0, 1, 500000, 1000000,
            3599999999, 3600000000, 3600000001, 3600500000,
            3601000000, 100000000000,
        )
        for age_us in cases_us:
            with self.subTest(age_us=age_us):
                observed = NOW - timedelta(microseconds=age_us)
                self.latest.write_text(json.dumps({
                    "schema": "janus.autonomy.latest.v1",
                    "ecosystem_status": "AUTONOMY_PARTIAL",
                    "last_observed_at_utc": observed.isoformat().replace("+00:00", "Z")
                }))
                result = self.run_probe()
                self.assertEqual(result["age_seconds"], age_us // 1000000)
                is_fresh = 0 <= age_us <= 3600 * 1000000
                self.assertEqual(result["status"],
                                 "FRESH_SOURCE_DIAGNOSTIC_ONLY" if is_fresh
                                 else "STALE_SOURCE_DIAGNOSTIC_ONLY")
                self.assertEqual(result["authority_delta"], 0)
                self.assertFalse(result["source_writeback"])

    def test_model_source_tampering_is_detected_before_execution(self):
        (self.state / "self_modules/is_fresh/module.py").write_text(
            "def is_fresh(age, max_age):\n    return True\n")
        with self.assertRaisesRegex(ValueError, "MODEL_SOURCE_TAMPERED"):
            self.run_probe()

    def test_model_index_authority_escalation_denied(self):
        p = self.state / "MODULE_INDEX.json"
        s = json.loads(p.read_text())
        s["runtime_auto_import"] = True
        p.write_text(json.dumps(s))
        with self.assertRaisesRegex(ValueError, "UNTRUSTED_MODULE_INDEX"):
            self.run_probe()

    def test_oracle_lies_or_returns_non_boolean(self):
        def lied(source, task, **kwargs):
            return {"status": "PASS_PURE_FUNCTION_ONLY", "cases": 270,
                    "value": False}
        with self.assertRaisesRegex(ValueError, "DISAGREES_WITH_CONTRACT"):
            self.run_probe(lied)
        def malformed(source, task, **kwargs):
            return {"status": "PASS_PURE_FUNCTION_ONLY", "value": 1}
        with self.assertRaisesRegex(ValueError, "UNVERIFIED_MODEL_RESULT"):
            self.run_probe(malformed)

    def test_no_timestamp_or_malformed_snapshot_denied(self):
        self.latest.write_text('{"schema":"janus.autonomy.latest.v1","ecosystem_status":"AUTONOMY_PARTIAL"}')
        with self.assertRaisesRegex(ValueError, "TIMESTAMP_NOT_UTC"):
            self.run_probe()
        self.set_age(10)
        d = json.loads(self.latest.read_text())
        d["ecosystem_status"] = "AUTONOMY_FULL_UNPROVEN"
        self.latest.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_OBSERVATION"):
            self.run_probe()


if __name__ == "__main__":
    unittest.main()
