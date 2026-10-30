import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj
m = load("maintenance", ROOT/"modules/autonomy_loop/maintenance.py")
c = load("coordination_tests", ROOT/"modules/rowan_observer/test_coordination.py")
w = load("witness_tests", ROOT/"modules/rowan_observer/test_ecosystem_sync_witness.py")

class CohortClient:
    def __init__(self):
        data, raw = w.mock_inputs()
        self.rows = {}
        for name, location in w.m.URLS.items():
            _, repo, _, path = location.split("/", 3)
            body = raw.get(name)
            if body is None:
                body = data[name].encode() if isinstance(data[name], str) else m.encode(data[name])
            self.rows[(repo, path)] = body
        self.rows[("janus-meta-registry", data["pointer"]["receipt_path"])] = raw["receipt"]
        self.rows[("Janus-Cosmos", data["cosmos"]["receipt_path"])] = raw["cosmos_receipt"]
    def pin(self, *args):
        return "a"*40
    def raw_file(self, repo, commit, path):
        body = self.rows[(repo, path)]
        return body, hashlib.sha256(body).hexdigest(), hashlib.sha1(b"blob "+str(len(body)).encode()+b"\0"+body).hexdigest()

class MaintenanceTests(unittest.TestCase):
    def test_coordination_update_is_idempotent_and_create_only(self):
        meta, aura, council = c.sample()
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            data = {"canonical": meta, "aura": aura, "council": council}
            first = m.reconcile(root, data, c.m.clean)
            path = root/first["receipt_path"]
            content = path.read_bytes()
            again = m.reconcile(root, data, c.m.clean)
            self.assertEqual(first["status"], "UPDATED_COORDINATION")
            self.assertEqual(again["status"], "IDLE_COORDINATION_CURRENT")
            self.assertEqual(path.read_bytes(), content)
            self.assertFalse(again["source_code_changed"])
    def test_rollback_and_source_drift_stop_before_writing(self):
        meta, aura, council = c.sample()
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            base = root/"data/rowan/coordination"
            base.mkdir(parents=True)
            latest = base/"LATEST_COORDINATION_STATE.json"
            latest.write_bytes(m.encode({"meta_canonical_run": 99999}))
            with self.assertRaisesRegex(m.Hold, "ROLLBACK"):
                m.reconcile(root, {"canonical": meta, "aura": aura, "council": council}, c.m.clean)
            self.assertFalse((base/"receipts").exists())
        council["sources"]["meta_registry"]["canonical_run"] = 1
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(c.m.Hold):
                m.reconcile(Path(root), {"canonical": meta, "aura": aura, "council": council}, c.m.clean)
    def test_full_cohort_is_replayed_without_science_promotion(self):
        client = CohortClient()
        proof = m.full_cohort(ROOT, client)
        result = m.verify_cohort(ROOT, client, proof)
        self.assertEqual(result["status"], "PASS_SOURCE_COHORT_ONLY")
        self.assertIs(result["full_issue_162_acceptance"], False)
        self.assertFalse(proof["runtime_execution_attested"])
    def test_tampered_content_and_unapproved_source_rejected(self):
        client = CohortClient()
        proof = m.full_cohort(ROOT, client)
        bad = copy.deepcopy(proof)
        bad["sources"]["aura"]["repository"] = "Hawkar-usls/PRIVATE_SOURCE"
        with self.assertRaisesRegex(m.Hold, "UNAPPROVED"):
            m.verify_cohort(ROOT, client, bad)
        source = proof["sources"]["aura"]
        client.rows[("aura-oracle-tg", source["path"])] = b"{}"
        with self.assertRaisesRegex(m.Hold, "EXACT_BYTES"):
            m.verify_cohort(ROOT, client, proof)
    def test_no_handler_action_before_verified_previous_phase(self):
        with tempfile.TemporaryDirectory() as root:
            result = m.execute(root, object(), {}, {})
            self.assertEqual(result["status"], "WAIT_P01_ACCEPTANCE")
            self.assertEqual(list(Path(root).iterdir()), [])
if __name__ == "__main__":
    unittest.main()
