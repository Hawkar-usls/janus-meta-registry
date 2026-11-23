"""P0.3 recovery matrix: trusted source receipt, no new authority and adversarial holds."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from modules.autonomy_loop import p03_recovery_matrix as m

ROOT=Path(__file__).resolve().parents[1]


class P03RecoveryMatrixTests(unittest.TestCase):
    def test_actual_snapshot_read_only_replay(self):
        latest, checkpoint, receipt, raw_sha=m.read_evidence(ROOT)
        result=m.evaluate(latest,checkpoint,receipt,raw_sha)
        self.assertEqual(result["status"],"P03_RECOVERY_REVIEW_REQUIRED")
        self.assertEqual(result["phase"],"P0.3")
        self.assertEqual(result["gates"]["checkpoint_matches_current"],"HOLD_SNAPSHOT_DRIFT")
        self.assertEqual(result["gates"]["p03_phase_admitted"],"HOLD_NOT_ADMITTED")
        self.assertEqual(result["public_pending"],0)
        self.assertEqual(result["private_pending"],2)
        self.assertEqual(result["gates"]["private_ack_replayed_independently"],
                         "HOLD_PRIVATE_AUTH_UNVERIFIED")
        self.assertEqual(result["gates"]["cloud_home_context_consumed"],
                         "HOLD_NO_RUNTIME_CONSUMPTION_WITNESS")
        self.assertTrue(result["source_receipt_sha256"]==latest["receipt_sha256"])
        for key in ("admission_granted","dispatch_performed","fork_performed","source_mutated",
                    "weights_changed","independent_external_witness_completed"):
            self.assertFalse(result[key],key)

    def test_checkpoint_rewrite_cannot_be_accepted_as_runtime_witness(self):
        latest, checkpoint, receipt, sha=m.read_evidence(ROOT)
        fake=copy.deepcopy(checkpoint)
        fake["last_verified_snapshot"]=latest["state_sha256"]
        fake.setdefault("accepted_phases",{})["P0.3"]={"status":"PASS"}
        report=m.evaluate(latest,fake,receipt,sha)
        self.assertEqual(report["gates"]["checkpoint_matches_current"],"PASS")
        self.assertEqual(report["gates"]["p03_phase_admitted"],"PASS")
        self.assertEqual(report["gates"]["cloud_home_context_consumed"],
                         "HOLD_NO_RUNTIME_CONSUMPTION_WITNESS")
        self.assertFalse(report["admission_granted"])

    def test_private_producer_claim_never_independently_replays(self):
        latest,checkpoint,receipt,sha=m.read_evidence(ROOT)
        fake=copy.deepcopy(receipt)
        p=fake["maintenance"]["p03_preflight"]
        p["private_ack_visibility"]="CLAIMED_IN_PRODUCER_TELEMETRY_NOT_INDEPENDENTLY_REPLAYED"
        p["private_receiver_pending"]=0
        report=m.evaluate(latest,checkpoint,fake,sha)
        self.assertEqual(report["gates"]["private_ack_replayed_independently"],
                         "HOLD_PRIVATE_AUTH_UNVERIFIED")
        self.assertFalse(report["admission_granted"])

    def test_untrusted_p03_acceptance_or_runtime_claim_is_rejected(self):
        latest,checkpoint,receipt,sha=m.read_evidence(ROOT)
        for key in ("p03_acceptance","runtime_consumption_attested"):
            x=copy.deepcopy(receipt)
            x["maintenance"]["p03_preflight"][key]=True
            with self.subTest(key=key),self.assertRaisesRegex(m.Hold,"AUTHORITY_ESCALATION"):
                m.evaluate(latest,checkpoint,x,sha)

    def test_false_producer_private_ack_pass_is_rejected(self):
        latest,checkpoint,receipt,sha=m.read_evidence(ROOT)
        x=copy.deepcopy(receipt)
        x["maintenance"]["p03_preflight"]["private_ack_visibility"]="INDEPENDENTLY_VERIFIED"
        with self.assertRaisesRegex(m.Hold,"PRODUCER_OVERCLAIM"):
            m.evaluate(latest,checkpoint,x,sha)

    def test_no_state_or_checkpoint_mutation(self):
        a=hashlib.sha256((ROOT/m.POINTER).read_bytes()).hexdigest()
        b=hashlib.sha256((ROOT/m.CHECKPOINT).read_bytes()).hexdigest()
        args=m.read_evidence(ROOT)
        m.evaluate(*args)
        self.assertEqual(a,hashlib.sha256((ROOT/m.POINTER).read_bytes()).hexdigest())
        self.assertEqual(b,hashlib.sha256((ROOT/m.CHECKPOINT).read_bytes()).hexdigest())

    def test_tamper_receipt_bytes_fails_closed(self):
        latest,_,_,_=m.read_evidence(ROOT)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"data/autonomy_loop/receipts").mkdir(parents=True)
            (root/m.POINTER).write_bytes((ROOT/m.POINTER).read_bytes())
            (root/m.CHECKPOINT).write_bytes((ROOT/m.CHECKPOINT).read_bytes())
            relative=latest["receipt_path"]
            (root/relative).write_bytes((ROOT/relative).read_bytes()+b" ")
            with self.assertRaisesRegex(m.Hold,"DIGEST_MISMATCH"):
                m.read_evidence(root)

    def test_untrusted_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"data/autonomy_loop").mkdir(parents=True)
            pointer=json.loads((ROOT/m.POINTER).read_text())
            pointer["receipt_path"]="../private/secret.txt"
            (root/m.POINTER).write_text(json.dumps(pointer))
            (root/m.CHECKPOINT).write_bytes((ROOT/m.CHECKPOINT).read_bytes())
            with self.assertRaisesRegex(m.Hold,"UNTRUSTED_RECEIPT_PATH"):
                m.read_evidence(root)

    def test_duplicate_json_field_and_nonfinite_number_are_rejected(self):
        for raw in (b'{"a":1,"a":2}',b'{"x":NaN}',b'{"x":Infinity}'):
            with self.assertRaises(m.Hold):
                m.decode_strict(raw)

    def test_missing_or_garbled_snapshots_fail_closed(self):
        latest,checkpoint,receipt,sha=m.read_evidence(ROOT)
        with self.assertRaisesRegex(m.Hold,"INVALID_EVIDENCE_DIGEST"):
            m.evaluate(latest,checkpoint,receipt,"0")
        x=copy.deepcopy(receipt)
        x["findings"]=[{"phase":"P0.3","reason":False}]
        with self.assertRaisesRegex(m.Hold,"FINDINGS_SCHEMA_UNVERIFIED"):
            m.evaluate(latest,checkpoint,x,sha)


if __name__ == "__main__":
    unittest.main()
