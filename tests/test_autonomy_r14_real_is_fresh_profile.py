"""Offline contract of the real JANUS is_fresh end-to-end profile."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "modules/autonomy_loop/r14_profile_real_consumer.py"
spec = importlib.util.spec_from_file_location("janus_real_consumer_profile", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
PROTOCOL_FILE = ROOT / "experiments/closed_loop_is_fresh_r14/PROTOCOL.json"


class RealIsFreshProfileTests(unittest.TestCase):
    def test_preregistered_contract_still_matches_unmodified_main(self):
        m.validate_protocol(json.loads(PROTOCOL_FILE.read_bytes()))
        self.assertEqual(m.git_blob_sha(m.CONSUMER.read_bytes()), m.SOURCE_BLOB_SHA)

    def test_not_production_promotion_or_new_task(self):
        policy = json.loads(PROTOCOL_FILE.read_bytes())
        self.assertFalse(policy["claims"]["candidate_improvement_proven"])
        self.assertFalse(policy["claims"]["auto_merge"])
        self.assertFalse(policy["claims"]["production_promotion"])
        self.assertEqual(policy["claims"]["code_authority_delta"], 0)
        self.assertEqual(policy["module"], "is_fresh")
        self.assertEqual(policy["execution"]["repeat_probes"], 3)

    def test_admission_or_identity_tamper_holds(self):
        original = json.loads(PROTOCOL_FILE.read_bytes())
        for path, val in (
            (("claims", "auto_merge"), True),
            (("claims", "code_authority_delta"), 1),
            (("claims", "candidate_improvement_proven"), True),
            (("execution", "no_paid_models"), False),
            (("execution", "repeat_probes"), 80),
            (("baseline_commit",), "0" * 40),
            (("state_commit",), "0" * 40),
        ):
            altered = copy.deepcopy(original)
            p = altered
            for member in path[:-1]:
                p = p[member]
            p[path[-1]] = val
            with self.subTest(path=path), self.assertRaises(m.EvidenceHold):
                m.validate_protocol(altered)

    def test_broken_source_fails_before_execution(self):
        data = json.loads(PROTOCOL_FILE.read_bytes())
        with patch.object(m, "git_blob_sha", return_value="0" * 40):
            with self.assertRaisesRegex(m.EvidenceHold, "CONSUMER_SOURCE_NOT_MAIN_BASELINE"):
                m.validate_protocol(data)

    def test_synthetic_stage_telemetry_never_proves_acceleration(self):
        # Offline fake check: test only the instrumentation and receipt
        # boundaries, not performance or actual Docker execution.
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "state"
            state.mkdir()
            latest = root / "LATEST.json"
            (state / "MODULE_INDEX.json").write_text(json.dumps({
                "model_authorship": "EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS",
                "runtime_auto_import": False, "authority_delta": 0,
                "modules": {"is_fresh": {"source_sha256": m.MODEL_SOURCE_SHA}},
            }))
            mod = state / "self_modules/is_fresh"
            mod.mkdir(parents=True)
            (mod / "module.py").write_text(
                "def is_fresh(age, max_age):\n    return 0 <= age <= max_age\n")
            (mod / "MODULE.json").write_text(json.dumps({
                "module_id":"janus.pure.is_fresh.v1",
                "source_sha256":m.MODEL_SOURCE_SHA,
                "author_model":"Qwen/Qwen2.5-Coder-0.5B-Instruct",
                "not_native_janus_model":True,"import_into_trusted_main":False,
                "permissions":[],"authority_delta":0,"review_required_for_integration":True
            }))
            latest.write_text(json.dumps({
                "schema":"janus.autonomy.latest.v1",
                "ecosystem_status":"AUTONOMY_PARTIAL",
                "last_observed_at_utc":"2026-11-08T12:00:00Z",
            }))
            def no_docker(source, task, *, call, seed):
                self.assertEqual(task, "is_fresh")
                return {"status":"PASS_PURE_FUNCTION_ONLY","cases":270,
                        "value": 0 <= call[0] <= call[1]}
            with patch.object(m.consumer.module_registry, "verify", return_value={}):
                with patch.object(m, "isolated_check", side_effect=no_docker):
                    result = m.probe_snapshot(
                        state, latest,
                        fixed_now=datetime(2026,11,8,12,30,tzinfo=timezone.utc),
                        idx=0)
            self.assertEqual(result["behavioral_cases"], 270)
            self.assertEqual(result["model_source_sha256"], m.MODEL_SOURCE_SHA)
            self.assertEqual(result["status"], "FRESH_SOURCE_DIAGNOSTIC_ONLY")
            self.assertGreater(result["total_ms"], 0)
            self.assertGreater(result["networkless_docker_oracle_ms"], 0)


if __name__ == "__main__":
    unittest.main()
