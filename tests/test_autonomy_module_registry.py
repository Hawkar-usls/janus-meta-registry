"""The autonomous author may add pure modules but cannot install itself into main."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules/autonomy_coder"))
import lifecycle as lifecycle
import module_registry as registry
import policy as policy


def candidate_bundle(state, task="retry_delay", run_id="123456-1", source=None):
    if source is None:
        source = "def retry_delay(attempt, cap):\n    return min(cap, 2 ** attempt)\n"
    return {
        "schema": "janus.autonomous_coder.candidates.v1",
        "run_id": run_id, "base_state_sha256": policy.digest(state),
        "task_id": task, "code_commit": os.environ.get("GITHUB_SHA", "LOCAL"),
        "model": {
            "id": policy.MODEL_ID, "revision": policy.MODEL_REVISION,
            "weights_sha256": policy.WEIGHTS_SHA256,
            "attribution": "EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS"},
        "candidates": [
            {"index": i, "raw_response": source, "source": source,
             "source_sha256": policy.source_digest(source)} for i in range(2)]
    }


def test_checker(source, task, **kwargs):
    return {"status": "PASS_PURE_FUNCTION_ONLY", "cases": 301, "value": 8}


class ModuleRegistryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "STATE.json").write_bytes(policy.canonical(policy.empty_state()))

    def accept(self, task="retry_delay", run_id="123456-1", source=None):
        b = candidate_bundle(json.loads((self.root / "STATE.json").read_bytes()),
                             task=task, run_id=run_id, source=source)
        verdict = lifecycle.evaluate(b, test_checker)
        result = lifecycle.publish(self.root, b, verdict)
        self.assertEqual(result["status"], "PROMOTED_PURE_EXTENSION_ONLY")
        return b

    def test_verified_generation_creates_true_module_and_index(self):
        self.accept()
        receipt = registry.build(self.root)
        self.assertEqual(receipt["modules"], 1)
        self.assertEqual(receipt["authority_delta"], 0)
        self.assertEqual(registry.verify(self.root, "123456-1")["modules"], 1)
        index = json.loads((self.root / "MODULE_INDEX.json").read_bytes())
        manifest = json.loads((self.root / "self_modules/retry_delay/MODULE.json").read_bytes())
        source = (self.root / "self_modules/retry_delay/module.py").read_bytes()
        original = (self.root / "generated/retry_delay" /
                    (manifest["source_sha256"] + ".py")).read_bytes()
        self.assertEqual(source, original)
        self.assertFalse(manifest["import_into_trusted_main"])
        self.assertTrue(manifest["review_required_for_integration"])
        self.assertEqual(manifest["permissions"], [])
        self.assertEqual(index["installation_scope"], "ISOLATED_STATE_BRANCH_ONLY")
        self.assertEqual(registry.build(self.root), receipt)

    def test_second_new_module_preserves_first_and_updates_catalog(self):
        self.accept()
        registry.build(self.root)
        old = (self.root / "self_modules/retry_delay/MODULE.json").read_bytes()
        self.accept("clamp", "123457-1",
                    "def clamp(value, low, high):\n    return max(low, min(high, value))\n")
        result = registry.build(self.root)
        self.assertEqual(result["modules"], 2)
        self.assertEqual(result["state_sequence"], 2)
        self.assertEqual((self.root / "self_modules/retry_delay/MODULE.json").read_bytes(), old)
        self.assertEqual(registry.verify(self.root, "123457-1")["modules"], 2)
        with self.assertRaisesRegex(ValueError, "MODULE_LATEST_RUN_MISMATCH"):
            registry.verify(self.root, "123456-1")

    def test_tampered_module_and_index_are_rejected_without_execution(self):
        self.accept()
        registry.build(self.root)
        path = self.root / "self_modules/retry_delay/module.py"
        path.write_text("def retry_delay(attempt, cap):\n    return 999\n")
        with self.assertRaisesRegex(ValueError, "MODULE_PACKAGE_REBINDING"):
            registry.verify(self.root)
        with self.assertRaisesRegex(ValueError, "IMMUTABLE_MODULE_CONFLICT"):
            registry.build(self.root)
        path.write_text("def retry_delay(attempt, cap):\n    return min(cap, 2 ** attempt)\n")
        index = self.root / "MODULE_INDEX.json"
        obj = json.loads(index.read_bytes())
        obj["runtime_auto_import"] = True
        index.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, "MODULE_INDEX_REBINDING"):
            registry.verify(self.root)

    def test_forged_model_candidates_and_weak_evaluation_are_denied(self):
        self.accept()
        bundle = self.root / "attempts/123456-1/CANDIDATES.json"
        original = bundle.read_bytes()
        forged = json.loads(original)
        forged["candidates"][0]["raw_response"] = "def retry_delay(attempt, cap):\n    return 42\n"
        bundle.write_text(json.dumps(forged))
        with self.assertRaisesRegex(ValueError, "CANDIDATE_REBINDING"):
            registry.build(self.root)
        bundle.write_bytes(original)
        receipt = self.root / "receipts/123456-1.json"
        result = json.loads(receipt.read_bytes())
        result["evaluation"]["variants"][0]["cases"] = 1
        receipt.write_text(json.dumps(result))
        with self.assertRaisesRegex(ValueError, "MODULE_RECEIPT_BYTES_CHANGED"):
            registry.build(self.root)

    def test_rejected_new_cycle_does_not_claim_old_module_is_new(self):
        self.accept()
        registry.build(self.root)
        state = json.loads((self.root / "STATE.json").read_bytes())
        bad = "def clamp(value, low, high):\n    return 999\n"
        bundle = candidate_bundle(state, "clamp", "123457-1", bad)
        def reject(*args, **kwargs):
            raise ValueError("bad")
        result = lifecycle.publish(self.root, bundle, lifecycle.evaluate(bundle, reject))
        self.assertEqual(result["status"], "REJECTED_NO_PROMOTION")
        self.assertEqual(registry.build(self.root)["modules"], 1)
        self.assertEqual(registry.verify(self.root, "123457-1")["modules"], 1)
        self.assertFalse((self.root / "self_modules/clamp/module.py").exists())

    def test_state_branch_scope_contract(self):
        wf = (Path(__file__).resolve().parents[1] /
              ".github/workflows/janus-autonomous-coder.yml").read_text()
        self.assertIn("module_registry.py build", wf)
        self.assertIn("module_registry.py verify", wf)
        self.assertIn("self_modules", wf)
        self.assertIn("MODULE_INDEX.json", wf)
        self.assertIn("MODULE_LATEST_RUN_MISMATCH", Path(registry.__file__).read_text())
        self.assertIn("git push origin HEAD:janus/autonomous-code-state", wf)
        self.assertNotIn("git push origin HEAD:main", wf)


if __name__ == "__main__":
    unittest.main()
