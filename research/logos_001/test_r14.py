"""R1.4 scientific sovereignty and anti-fake-external-result tests."""
import base64
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/"r14_external"))
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from r14_submission import produce_predictions,validate_domain_input
from r14_external_receipt_gate import verify_receipt
from r14_public_smoke import fixture,participant_outputs,custodian_smoke

class R14ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.public=fixture()
        cls.proposals=participant_outputs()

    def test_public_smoke_never_is_blind_evidence(self):
        r=custodian_smoke(self.proposals)
        self.assertEqual(r["status"],"UNSIGNED_DRAFT_NOT_EXTERNAL_PROOF")
        self.assertEqual(r["independent_external_evaluation_verified"],False)
        self.assertEqual(r["three_distinct_real_domains_certified_by_custodian"],False)
        self.assertFalse(r["production_model_promotion_allowed"])
        self.assertEqual(len(r["scores"]),3)

    def test_test_labels_never_reach_participant(self):
        d=self.public["domains"][0]
        request={"domain_id":d["domain_id"],"train":d["train"],"validation":d["validation"],"test_x":[x for x,y in d["test"]]}
        y=produce_predictions(request)
        self.assertEqual(y["scientific_claim"],"UNSCORED_EXTERNAL_HOLDOUT")
        self.assertEqual(y["n_test"],len(d["test"]))
        self.assertFalse(y["production_model_promotion_allowed"])
        bad=copy.deepcopy(request)
        bad["test_y"]=[y for x,y in d["test"]]
        with self.assertRaises(ValueError):produce_predictions(bad)
        bad=copy.deepcopy(request)
        bad["test"]=d["test"]
        with self.assertRaises(ValueError):produce_predictions(bad)

    def test_test_inputs_cannot_overlap_training_groups(self):
        d=self.public["domains"][0]
        request={"domain_id":d["domain_id"],"train":d["train"],"validation":d["validation"],"test_x":[x for x,y in d["test"]]}
        request["test_x"][0]=d["train"][0][0]
        with self.assertRaises(ValueError):validate_domain_input(request)

    def test_missing_external_key_never_passes(self):
        repo=Path(__file__).resolve().parents[2]
        p=repo/"data"/"JANUS-LOGOS-001-R14-CUSTODIAN-REGISTRATION-v1.0.json"
        reg=json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(reg["status"],"NOT_APPOINTED")
        with self.assertRaisesRegex(ValueError,"BLOCKED_NO_APPROVED_EXTERNAL_CUSTODIAN"):
            verify_receipt(reg,b"{}",base64.b64encode(b"bad").decode())

    def test_ed25519_tamper_detection_with_TEST_ONLY_generated_key(self):
        """Ephemeral self-issued fixture key is NOT an approved real custodian."""
        key=Ed25519PrivateKey.generate()
        pem=key.public_key().public_bytes(Encoding.PEM,PublicFormat.SubjectPublicKeyInfo).decode("ascii")
        reg={"status":"INDEPENDENT_CUSTODIAN_APPROVED",
             "custodian_id":"TEST_ONLY_NOT_A_REAL_INDEPENDENT_EVALUATOR",
             "public_key_ed25519_pem":pem,"public_key_sha256":hashlib.sha256(pem.encode()).hexdigest(),
             "verified_identity":True,"approval_commit":"SYNTHETIC_FIXTURE_ONLY",
             "approved_utc":"2026-10-01T00:00:00Z"}
        rows=[{"domain_id":f"fixture_{i}","physical_domain":f"synthetic_{i}",
               "candidate_decision":"ABSTAIN","pass_5pct_with_positive_lower_ci":False} for i in range(3)]
        receipt={"receipt_schema":"JANUS_LOGOS_R14_EVALUATOR_RECEIPT_v1",
                 "signature_protocol":"JANUS_LOGOS_R14_EXTERNAL_RECEIPT_ED25519_v1",
                 "custodian_id":reg["custodian_id"],
                 "executed_utc":"2026-11-01T00:00:00Z",
                 "status":"EXTERNAL_EVALUATOR_SIGNED",
                 "three_distinct_real_domains_certified_by_custodian":True,
                 "independent_external_evaluation_verified":True,
                 "scores":rows,"passed_domain_count":0,
                 "scientific_success_gate_met":False,
                 "production_model_promotion_allowed":False}
        data=json.dumps(receipt,sort_keys=True,separators=(",",":")).encode()
        sig=base64.b64encode(key.sign(data)).decode()
        self.assertEqual(verify_receipt(reg,data,sig)["external_scientific_result"],"FAIL_0_OF_3")
        with self.assertRaises(ValueError):verify_receipt(reg,data+b" ",sig)
        z=copy.deepcopy(reg);z["public_key_sha256"]="0"*64
        with self.assertRaises(ValueError):verify_receipt(z,data,sig)

    def test_synthetic_fixture_does_not_claim_real_science(self):
        for d in self.public["domains"]:
            self.assertIn("SYNTHETIC_FIXTURE_",d["physical_domain"])
            self.assertEqual(d["provider_reference"],"PUBLIC_SYNTHETIC_TEST_NOT_INDEPENDENT")

if __name__=="__main__":unittest.main()
