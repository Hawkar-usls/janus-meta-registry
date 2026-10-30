"""Adversarial offline controls; no model download and no provider calls."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "modules/autonomy_coder"))
import policy as p
import lifecycle as m
import checker

GOOD = "def retry_delay(attempt, cap):\n    return min(cap, 2 ** attempt)\n"
BAD = "def retry_delay(attempt, cap):\n    return 1\n"

def bundle(state=None):
    return {"schema": "janus.autonomous_coder.candidates.v1", "run_id": "123456-1",
        "base_state_sha256": p.digest(state or p.empty_state()), "task_id": "retry_delay", "code_commit": os.environ.get("GITHUB_SHA", "LOCAL"),
        "model": {"id": p.MODEL_ID, "revision": p.MODEL_REVISION, "weights_sha256": p.WEIGHTS_SHA256,
                  "attribution": "EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS"},
        "candidates": [{"index": i, "raw_response": s, "source": s, "source_sha256": p.source_digest(s)} for i, s in enumerate((BAD, GOOD))]}

def independent_check(source, task, **kwargs):
    # Test fixture stands in for the isolated oracle. Real Docker controls are
    # separately exercised by cloud contract CI with network disabled.
    if source == BAD:
        raise ValueError("behavior mismatch")
    return {"status": "PASS_PURE_FUNCTION_ONLY", "cases": 291, "value": 8}

class CoderTests(unittest.TestCase):
    def test_queue_is_ordered_and_unknown_tasks_are_not_admitted(self):
        state = p.empty_state()
        self.assertEqual(p.next_task(state), "retry_delay")
        state["accepted"]["arbitrary_shell"] = {}
        with self.assertRaises(ValueError):
            p.next_task(state)

    def test_model_identity_is_fixed_and_source_is_exact_model_text(self):
        b = bundle()
        p.validate_bundle(b)
        b["model"]["revision"] = "main"
        with self.assertRaises(ValueError):
            p.validate_bundle(b)
        b = bundle()
        b["candidates"][1]["source"] = BAD
        b["candidates"][1]["source_sha256"] = p.source_digest(BAD)
        with self.assertRaises(ValueError):
            p.validate_bundle(b)

    def test_side_effects_top_level_code_defaults_and_introspection_are_blocked(self):
        cases = ["import os\n" + GOOD, "print('x')\n" + GOOD,
            "def retry_delay(attempt, cap):\n    return open('/etc/passwd').read()\n",
            "def retry_delay(attempt, cap):\n    return attempt.__class__\n",
            "def retry_delay(attempt, cap):\n    return eval('1')\n",
            "def retry_delay(attempt, cap):\n    return retry_delay(attempt, cap)\n",
            "def retry_delay(attempt, cap=print('x')):\n    return 1\n",
            "@print('x')\n" + GOOD]
        for source in cases:
            with self.subTest(source=source), self.assertRaises((ValueError, SyntaxError)):
                p.validate_source(source, "retry_delay")

    def test_set_add_only_for_single_initialized_local_builtin_set(self):
        good = ("def stable_unique(values):\n"
                "    seen = set()\n"
                "    result = []\n"
                "    for value in values:\n"
                "        if value not in seen:\n"
                "            seen.add(value)\n"
                "            result.append(value)\n"
                "    return result\n")
        self.assertEqual(p.validate_source(good, "stable_unique"), good)
        unsafe = [
            "def stable_unique(values):\n    return values.add('x')\n",
            "def stable_unique(values):\n    seen = set()\n    seen = values\n    seen.add('x')\n    return []\n",
            "def stable_unique(values):\n    seen = set()\n    for seen in values:\n        seen.add('x')\n    return []\n",
            "def stable_unique(values):\n    seen = values\n    seen.add('x')\n    return []\n",
            "def stable_unique(values):\n    seen = set()\n    alias = seen.add\n    return []\n",
            "def stable_unique(values):\n    seen = set()\n    seen.add('a', 'b')\n    return []\n",
            "def stable_unique(values):\n    set = list\n    seen = set()\n    seen.add('x')\n    return []\n",
            "def stable_unique(values):\n    def set():\n        return values\n    seen = set()\n    seen.add('x')\n    return []\n",
        ]
        for source in unsafe:
            with self.subTest(source=source), self.assertRaises((ValueError, SyntaxError)):
                p.validate_source(source, "stable_unique")

    def test_container_has_no_network_credentials_or_host_write_mount(self):
        seen = []
        def runner(command, **kwargs):
            seen.extend(command)
            self.assertEqual(kwargs["timeout"], 15)
            return subprocess.CompletedProcess(command, 0, '{"status":"PASS_PURE_FUNCTION_ONLY","cases":291}', "")
        m.isolated_check(GOOD, "retry_delay", runner=runner)
        self.assertIn("none", seen)
        self.assertIn("--read-only", seen)
        self.assertIn("--memory", seen)
        self.assertNotIn("--privileged", seen)
        self.assertNotIn("--env", seen)
        self.assertTrue(all("readonly" in value for value in seen if "type=bind" in value))

    def test_timeout_and_behavior_failure_never_promote(self):
        def timed(*args, **kwargs):
            raise subprocess.TimeoutExpired("docker", 15)
        e = m.evaluate(bundle(), timed)
        self.assertTrue(all(v["status"] == "REJECTED" for v in e["variants"]))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "STATE.json").write_bytes(p.canonical(p.empty_state()))
            result = m.publish(root, bundle(), e)
            self.assertEqual(result["status"], "REJECTED_NO_PROMOTION")
            self.assertEqual(m.load(root / "STATE.json")["accepted"], {})
            self.assertTrue((root / "attempts/123456-1/CANDIDATES.json").exists())

    def test_independent_good_variant_is_preserved_and_consumed_exactly_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "STATE.json").write_bytes(p.canonical(p.empty_state()))
            b = bundle()
            e = m.evaluate(b, independent_check)
            self.assertEqual(e["variants"][0]["status"], "REJECTED")
            self.assertEqual(m.publish(root, b, e)["next_task"], "clamp")
            saved = (root / "STATE.json").read_bytes()
            self.assertEqual(m.publish(root, b, e)["status"], "ALREADY_PUBLISHED")
            self.assertEqual((root / "STATE.json").read_bytes(), saved)
            result = m.consume(root, call=[3, 30], check=independent_check)
            self.assertEqual(result["value"], 8)
            self.assertFalse(result["full_issue_162_acceptance"])
            state = json.loads(saved)
            (root / state["accepted"]["retry_delay"]["path"]).write_text(BAD)
            with self.assertRaisesRegex(ValueError, "CONSUMER_SOURCE_REBINDING"):
                m.consume(root, check=independent_check)

    def test_stale_state_and_rehashed_forged_verdict_are_held(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = p.empty_state()
            state["sequence"] = 3
            (root / "STATE.json").write_bytes(p.canonical(state))
            with self.assertRaisesRegex(ValueError, "STALE_AUTHOR_STATE"):
                m.publish(root, bundle(), m.evaluate(bundle(), independent_check))
            (root / "STATE.json").write_bytes(p.canonical(p.empty_state()))
            e = m.evaluate(bundle(), independent_check)
            e["variants"][1]["source_sha256"] = "f" * 64
            e["evaluation_sha256"] = p.digest({k:v for k,v in e.items() if k != "evaluation_sha256"})
            with self.assertRaisesRegex(ValueError, "VERDICT_REBINDING"):
                m.publish(root, bundle(), e)

    def test_oracle_includes_boundaries_and_independent_random_cases(self):
        for task in p.TASKS:
            a = checker.cases(task, "first independent seed")
            b = checker.cases(task, "second independent seed")
            self.assertGreaterEqual(len(a), 200)
            self.assertNotEqual(a, b)

    def test_clean_consumer_uses_exact_latest_run_and_new_task(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "STATE.json").write_bytes(p.canonical(p.empty_state()))
            first = bundle()
            m.publish(root, first, m.evaluate(first, independent_check))
            state = m.load(root / "STATE.json")
            second_source = "def clamp(value, low, high):\\n    return min(high, max(low, value))\\n".replace("\\n", "\n")
            second = bundle(state)
            second["run_id"] = "123457-1"
            second["task_id"] = "clamp"
            second["candidates"] = [
                {"index": i, "raw_response": second_source, "source": second_source,
                 "source_sha256": p.source_digest(second_source)} for i in range(2)]
            m.publish(root, second, m.evaluate(second, independent_check))
            with self.assertRaisesRegex(ValueError, "CONSUMER_RUN_MISMATCH"):
                m.consume(root, expected_run_id="123456-1", check=independent_check)
            got = m.consume(root, expected_run_id="123457-1", check=independent_check)
            self.assertEqual(got["task_id"], "clamp")
            self.assertEqual(got["source_sha256"], p.source_digest(second_source))

    def test_all_tasks_done_is_safe_idle_without_forged_new_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = p.empty_state()
            for task in p.TASKS:
                sha = "a"*64
                state["accepted"][task] = {
                    "source_sha256": sha, "path": f"generated/{task}/{sha}.py",
                    "run_id": "123456-1", "receipt_sha256": "b"*64,
                    "author_model": p.MODEL_ID}
            state["sequence"] = len(p.TASKS)
            (root / "STATE.json").write_bytes(p.canonical(state))
            idle = bundle(state)
            idle["run_id"] = "123460-1"
            idle["task_id"] = None
            idle["candidates"] = []
            result = m.publish(root, idle, m.evaluate(idle, independent_check))
            self.assertEqual(result["status"], "IDLE_ALL_ADMITTED_TASKS_DONE")
            self.assertFalse(result["changed"])
            self.assertEqual((root / "STATE.json").read_bytes(), p.canonical(state))
            self.assertFalse((root / "receipts/123460-1.json").exists())
            with self.assertRaisesRegex(ValueError, "CONSUMER_RUN_MISMATCH"):
                m.consume(root, expected_run_id="123460-1", check=independent_check)

    def test_cloud_clean_consumer_skips_only_truthful_idle(self):
        wf = (Path(__file__).resolve().parents[1] /
              ".github/workflows/janus-autonomous-coder.yml").read_text()
        self.assertIn("publish_status: ${{ steps.scope.outputs.publish_status }}", wf)
        self.assertIn("if: ${{ needs.publish.outputs.publish_status != 'IDLE_ALL_ADMITTED_TASKS_DONE' }}", wf)
        self.assertIn("UNRECOGNIZED_CODER_PUBLICATION_STATUS", wf)
        self.assertIn("--expected-run-id", wf)
        self.assertIn("github.run_attempt", wf)

    def test_rejected_new_run_cannot_reconsume_previous_success_as_new(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "STATE.json").write_bytes(p.canonical(p.empty_state()))
            first = bundle()
            m.publish(root, first, m.evaluate(first, independent_check))
            second = bundle(m.load(root / "STATE.json"))
            second["run_id"] = "123458-1"
            second["task_id"] = "clamp"
            bad_source = "def clamp(value, low, high):\\n    return 999\\n".replace("\\n", "\n")
            second["candidates"] = [
                {"index": i, "raw_response": bad_source, "source": bad_source,
                 "source_sha256": p.source_digest(bad_source)} for i in range(2)]
            def reject(*args, **kwargs):
                raise ValueError("behavior failed")
            result = m.publish(root, second, m.evaluate(second, reject))
            self.assertEqual(result["status"], "REJECTED_NO_PROMOTION")
            def never_check(*args, **kwargs):
                raise AssertionError("rejected run must not execute previous code")
            got = m.consume(root, expected_run_id="123458-1", check=never_check)
            self.assertEqual(got["status"], "WAIT_NO_NEW_ACCEPTED_EXTENSION")
            self.assertFalse(got["full_issue_162_acceptance"])

if __name__ == "__main__":
    unittest.main()
