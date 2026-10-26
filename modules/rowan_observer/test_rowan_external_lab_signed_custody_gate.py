"""Synthetic-only negative and positive Ed25519 tests, no real secrets or labels."""
from __future__ import annotations
import base64,importlib.util,copy,json,unittest
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat

script=Path(__file__).with_name("rowan_external_lab_signed_custody_gate.py")
spec=importlib.util.spec_from_file_location("rowan_external_lab_signed_custody_gate",script)
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
def fixture():
    key=Ed25519PrivateKey.generate() # ephemeral test-only key, never persisted
    public=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    body={
      "dataset_status":"NEW_UNPUBLISHED_EXTERNAL_MEASUREMENTS",
      "frozen_input_manifest_sha256":g.EXPECTED_FROZEN_INPUT_SHA256,
      "locked_study_protocol_sha256":"a"*64,
      "salted_plaintext_commitment_sha256":"b"*64,
      "salted_commitment_method":g.ALGORITHM,
      "measurements":200,
      "independent_organization":"TEST LAB — SYNTHETIC ONLY",
      "responsible_scientist":"SYNTHETIC TEST KEY HOLDER",
      "institutional_email":"test@example.invalid",
      "independent_primary_assay_protocol_url":"https://example.invalid/protocol",
      "censoring_and_exclusion_policy_sha256":"c"*64,
      "deduplication_review_sha256":"d"*64,
      "independent_timestamp_attestation_url":"https://example.invalid/witness",
      "custodian_HOLDS_unpublished_outcomes":True,
      "JANUS_has_had_access_to_outcomes":False,
      "external_lab_HOLDS_secret_salt":True,
      "consented_to_independent_blind_study":True,
      "original_assay_sign_and_units_reviewed":True,
      "precommit_utc":"2026-10-26T07:00:00Z",
      "prediction_freeze_utc":"2026-10-27T07:00:00Z"
    }
    def sign(payload):
        return {"schema_id":g.SCHEMA,"signed_payload":payload,
                "signature":{"algorithm":"Ed25519",
                             "public_key_raw_b64":base64.b64encode(public).decode(),
                             "detached_signature_b64":base64.b64encode(key.sign(g.canonical(payload))).decode()}}
    return body,sign,g.hash_bytes(public)

class LabCustodyTests(unittest.TestCase):
    def test_initial_state_correctly_holds(self):
        a=g.hold_receipt()
        self.assertFalse(a["unblinding_permitted"])
        self.assertFalse(a["signed_external_payload_received"])
    def test_signature_valid_still_not_a_scientific_pass(self):
        body,sign,fp=fixture()
        r=g.check_signed_commitment(sign(body),fp)
        self.assertEqual(r["state"],"SIGNATURE_VALID_ONLY_NOT_INDEPENDENT_CUSTODY_OR_UNBLIND")
        self.assertFalse(r["unblinding_permitted"])
        self.assertFalse(r["external_time_anchor_independently_verified"])
    def test_out_of_band_pin_absent_holds(self):
        body,sign,fp=fixture()
        with self.assertRaisesRegex(g.CustodyHold,"NO_OUT_OF_BAND_TRUSTED_KEY_PIN"):
            g.check_signed_commitment(sign(body),None)
    def test_wrong_key_pin_holds(self):
        body,sign,fp=fixture()
        with self.assertRaisesRegex(g.CustodyHold,"EXTERNAL_KEY_NOT_PRE_REGISTERED"):
            g.check_signed_commitment(sign(body),"0"*64)
    def test_tampered_signed_document_fails(self):
        body,sign,fp=fixture()
        signed=sign(body)
        signed["signed_payload"]["responsible_scientist"]="NOT THE SIGNED PERSON"
        with self.assertRaisesRegex(g.CustodyHold,"DETACHED_SIGNATURE_INVALID"):
            g.check_signed_commitment(signed,fp)
    def test_source_manifest_change_holds(self):
        body,sign,fp=fixture()
        body["frozen_input_manifest_sha256"]="0"*64
        with self.assertRaisesRegex(g.CustodyHold,"FROZEN_SAMPLE_IDENTITY_DRIFT"):
            g.check_signed_commitment(sign(body),fp)
    def test_published_old_labels_not_prospective(self):
        body,sign,fp=fixture()
        body["dataset_status"]="EXISTING_PUBLIC_FIREPROT_VALUES"
        with self.assertRaisesRegex(g.CustodyHold,"PUBLIC_OR_OLD_LABELS"):
            g.check_signed_commitment(sign(body),fp)
    def test_public_raw_labels_key_rejected(self):
        body,sign,fp=fixture()
        body["raw_labels"]=[1.1,2.2]
        with self.assertRaisesRegex(g.CustodyHold,"RAW_OUTCOME_KEY_FORBIDDEN"):
            g.check_signed_commitment(sign(body),fp)
    def test_weak_no_secret_salt_rejected(self):
        body,sign,fp=fixture()
        body["salted_commitment_method"]="SHA256(public numeric scores)"
        with self.assertRaisesRegex(g.CustodyHold,"INSECURE_OR_UNRECOGNIZED"):
            g.check_signed_commitment(sign(body),fp)
    def test_bad_timestamp_order_holds(self):
        body,sign,fp=fixture()
        body["prediction_freeze_utc"]="2026-10-25T23:00:00Z"
        with self.assertRaisesRegex(g.CustodyHold,"PRECOMMIT_AFTER_PREDICTIONS"):
            g.check_signed_commitment(sign(body),fp)
    def test_not_independent_lab_consent_holds(self):
        body,sign,fp=fixture()
        body["consented_to_independent_blind_study"]=False
        with self.assertRaisesRegex(g.CustodyHold,"NO_EXTERNAL_CONSENT"):
            g.check_signed_commitment(sign(body),fp)
    def test_wrong_size_holds(self):
        body,sign,fp=fixture()
        body["measurements"]=20
        with self.assertRaisesRegex(g.CustodyHold,"EXPERIMENT_SCOPE_NOT_200"):
            g.check_signed_commitment(sign(body),fp)
    def test_no_signed_metadata_is_not_bad_signature_success(self):
        with self.assertRaisesRegex(g.CustodyHold,"INVALID_SCHEMA"):
            g.check_signed_commitment({"schema_id":"wrong"},None)
if __name__=="__main__":unittest.main()
