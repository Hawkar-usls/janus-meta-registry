"""Offline evidence replay and fail-closed tests; never calls the Rowan API."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("structural", HERE / "bbc1_status_import.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def sample():
    return {
        "schema": m.SCHEMA, "source_kind": "REAL_PROVIDER_READ_ONLY_STATUS",
        "case_order": ["wildtype", "K5A"],
        "entries": [
            {"arm": "wildtype", "status": "ROWAN_RESULT_RETURNED_NO_FITNESS_CLAIM",
             "provider_uuid_hash": "a"*16, "provider_credits_charged": 4.66,
             "credit_cap": 10, "charge_over_cap_review": False,
             "ptm": .927, "avg_lddt": .963},
            {"arm": "K5A", "status": "ROWAN_RESULT_RETURNED_NO_FITNESS_CLAIM",
             "provider_uuid_hash": "b"*16, "provider_credits_charged": 4.81,
             "credit_cap": 10, "charge_over_cap_review": False,
             "ptm": .927, "avg_lddt": .973},
        ],
        "paired_confidence_deltas_not_fitness": {
            "K5A_minus_wildtype_ptm": 0.0, "K5A_minus_wildtype_avg_lddt": 0.01},
        "tranception_model_run": False, "protein_fitness_validated": False,
        "experimental_assay_independent_review": "OPEN",
        "provider_spend_by_collector": False,
    }


def run(i):
    return {"id": i, "head_sha": "c"*40, "path": m.WORKFLOW_FILE,
            "event": "schedule", "head_branch": "main", "conclusion": "success"}


class StructuralArchiveTests(unittest.TestCase):
    def test_replay_and_science_boundary(self):
        v = m.validate(sample())
        self.assertEqual(len(v["cases"]), 2)
        self.assertFalse(v["science_gates"]["protein_fitness_validated"])
        self.assertFalse(v["science_gates"]["new_provider_jobs_authorized"])
        self.assertEqual(v["paired_confidence_deltas_not_fitness"]
                         ["K5A_minus_wildtype_avg_lddt"], .01)

    def test_extra_private_fields_rejected(self):
        v = sample(); v["api_key"] = "secret"
        with self.assertRaises(m.EvidenceHold): m.validate(v)

    def test_nonfinite_scores_rejected(self):
        for bad in (float("nan"), float("inf"), -0.1, 1.01, True):
            v = sample(); v["entries"][0]["ptm"] = bad
            with self.assertRaises(m.EvidenceHold): m.validate(v)

    def test_credit_alert_cannot_be_concealed(self):
        v = sample(); v["entries"][1]["provider_credits_charged"] = 22.0
        with self.assertRaisesRegex(m.EvidenceHold, "CREDIT_ALERT_CONTRADICTION"):
            m.validate(v)
        v["entries"][1]["charge_over_cap_review"] = True
        self.assertTrue(m.validate(v)["billing_alert"])

    def test_wrong_paired_delta_rejected(self):
        v = sample(); v["paired_confidence_deltas_not_fitness"]["K5A_minus_wildtype_ptm"] = .4
        with self.assertRaisesRegex(m.EvidenceHold, "PAIRED_SCORE_REPLAY_MISMATCH"):
            m.validate(v)

    def test_fitness_lie_rejected(self):
        v = sample(); v["protein_fitness_validated"] = True
        with self.assertRaises(m.EvidenceHold): m.validate(v)

    def test_durable_idempotent_and_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            retrieve=lambda _:(sample(),hashlib.sha256(m.canonical(sample())).hexdigest())
            self.assertEqual(m.update(root,[run(200),run(100)],retrieve,2)["new_receipts"],2)
            self.assertEqual(m.update(root,[run(200),run(100)],retrieve)["new_receipts"],0)
            receipt=next((root/m.ROOT_REL/"receipts").glob("*200*"))
            receipt.write_text(receipt.read_text()+"\n")
            with self.assertRaisesRegex(m.EvidenceHold, "INTEGRITY_HOLD"):
                m.update(root,[run(201)],retrieve)

    def test_new_lane_never_rewrites_s2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); canon=root/"data/rowan/CANONICAL_STATE.json"
            canon.parent.mkdir(parents=True)
            canon.write_text('{"unrelated":true}\n')
            v=m.update(root,[run(40681221109)],lambda _:(sample(),"f"*64))
            self.assertEqual(v["new_receipts"],1)
            self.assertEqual(canon.read_text(),'{"unrelated":true}\n')
            latest=json.loads((root/m.ROOT_REL/"LATEST.json").read_text())
            self.assertEqual(latest["latest_source_run"],40681221109)

    def test_rollback_history_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=lambda _:(sample(),"e"*64)
            m.update(Path(tmp),[run(200)],r)
            with self.assertRaises(m.EvidenceHold): m.update(Path(tmp),[run(199)],r)

    def test_only_approved_main_workflow_runs(self):
        original=m.github
        m.github=lambda _:{"workflow_runs":[run(200),dict(run(201),head_branch="fork"),
            dict(run(202),event="pull_request"),dict(run(203),path="attacker.yml"),
            dict(run(204),head_sha="bad")]}
        try: self.assertEqual([v["id"] for v in m.source_runs()],[200])
        finally: m.github=original

    def test_no_billing_surface(self):
        text=(HERE/"bbc1_status_import.py").read_text()
        for forbidden in ("ROWAN_API_KEY","submit_protein_cofolding_workflow(",
                          "import rowan\n"):
            self.assertNotIn(forbidden,text)


if __name__ == "__main__":
    unittest.main()
