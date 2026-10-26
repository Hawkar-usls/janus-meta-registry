#!/usr/bin/env python3
"""JANUS Rowan external prospective label custody: fail-closed signed precommitment.

The public JANUS repository must never hold raw labels, encrypted source with
mismanaged keys, secret commitment salt, or lab private signing keys.

This program checks public attestation metadata ONLY, authenticating a
detached Ed25519 signature against an OUT-OF-BAND pinned signer public-key
fingerprint. Cryptographic verification does not prove that the signer actually
holds unseen data, that their lab is independent, or that measurements exist.
An externally attested time anchor and prediction-before-unblind receipts
are separate prerequisites. This program NEVER unblinds.
"""
from __future__ import annotations
import argparse,base64,binascii,hashlib,json,re,sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA="janus.rowan.external_signed_unpublished_label_commitment.v2"
EXPECTED_FROZEN_INPUT_SHA256="9a44fd6c01afca2b21990b0f4364cb3dbf89ad61686295f55005f86001ce7b92"
H= re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_KEYS={
 "ddg","dtm","stability","measured_value","label","labels","labels_json",
 "raw_values","raw_labels","raw_outcomes","outcomes","decrypted_archive",
 "secret_salt","salt","private_key","private_signing_key","specimen_outcomes",
 "label_table","original_assay_values","raw_assay_csv","assay_numeric_values"
}
ALGORITHM="sha256:secret-256bit-salt+canonical-unpublished-raw-label-records:v1"
SIGNATURE_ALGO="Ed25519"

class CustodyHold(ValueError):
    pass

def hash_bytes(b: bytes)->str:return hashlib.sha256(b).hexdigest()

def canonical(value: Any)->bytes:
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")

def sha_ok(value):
    return isinstance(value,str) and bool(H.fullmatch(value))

def b64decode(s):
    if not isinstance(s,str):raise CustodyHold("BASE64_TYPE_INVALID")
    try:return base64.b64decode(s,validate=True)
    except (binascii.Error,ValueError):raise CustodyHold("BASE64_INVALID")

def no_raw_labels(value,path="root"):
    if isinstance(value,dict):
        for k,v in value.items():
            if k.lower() in FORBIDDEN_KEYS:
                raise CustodyHold("RAW_OUTCOME_KEY_FORBIDDEN_"+path+"."+k)
            no_raw_labels(v,path+"."+k)
    elif isinstance(value,list):
        for i,item in enumerate(value):no_raw_labels(item,path+"."+str(i))

def utc_timestamp(s):
    if not isinstance(s,str) or not s.endswith("Z"):
        raise CustodyHold("NON_UTC_OR_INVALID_TIMESTAMP")
    try:
        dt=datetime.fromisoformat(s[:-1]+"+00:00")
        if dt.utcoffset().total_seconds()!=0:raise ValueError()
        return dt
    except ValueError:raise CustodyHold("NON_UTC_OR_INVALID_TIMESTAMP")

def require_string(v,name):
    if not isinstance(v,str) or not v.strip() or len(v)>1024:
        raise CustodyHold("MISSING_OR_INVALID_"+name)
    return v

def payload(document):
    if type(document) is not dict or document.get("schema_id")!=SCHEMA:
        raise CustodyHold("INVALID_SCHEMA")
    body=document.get("signed_payload")
    sign=document.get("signature")
    if type(body) is not dict or type(sign) is not dict:
        raise CustodyHold("NO_SEPARATE_PAYLOAD_AND_SIGNATURE")
    no_raw_labels(body)
    if body.get("dataset_status")!="NEW_UNPUBLISHED_EXTERNAL_MEASUREMENTS":
        raise CustodyHold("PUBLIC_OR_OLD_LABELS_CANNOT_BE_PROSPECTIVE")
    if body.get("frozen_input_manifest_sha256")!=EXPECTED_FROZEN_INPUT_SHA256:
        raise CustodyHold("FROZEN_SAMPLE_IDENTITY_DRIFT")
    if not sha_ok(body.get("locked_study_protocol_sha256")):
        raise CustodyHold("UNPINNED_PROTOCOL_SHA")
    if not sha_ok(body.get("salted_plaintext_commitment_sha256")):
        raise CustodyHold("MISSING_PRIVATE_SALTED_COMMITMENT")
    if body.get("salted_commitment_method")!=ALGORITHM:
        raise CustodyHold("INSECURE_OR_UNRECOGNIZED_COMMITMENT_METHOD")
    count=body.get("measurements")
    if type(count) is not int or count!=200:
        raise CustodyHold("EXPERIMENT_SCOPE_NOT_200")
    if body.get("independent_organization") in (None,"JANUS","Hawkar-usls"):
        raise CustodyHold("MISSING_SEPARATE_LAB")
    for k in ("independent_organization","responsible_scientist","institutional_email",
              "independent_primary_assay_protocol_url",
              "censoring_and_exclusion_policy_sha256","deduplication_review_sha256",
              "independent_timestamp_attestation_url"):
        require_string(body.get(k),k)
    for k in ("censoring_and_exclusion_policy_sha256","deduplication_review_sha256"):
        if not sha_ok(body[k]):raise CustodyHold("NON_HASH_POLICY_"+k)
    if not body["institutional_email"].count("@")==1:raise CustodyHold("INVALID_INSTITUTIONAL_CONTACT")
    if body.get("custodian_HOLDS_unpublished_outcomes") is not True:
        raise CustodyHold("NO_UNPUBLISHED_EXTERNAL_CUSTODY")
    if body.get("JANUS_has_had_access_to_outcomes") is not False:
        raise CustodyHold("JANUS_EXPOSURE_POSSIBLE")
    if body.get("external_lab_HOLDS_secret_salt") is not True:
        raise CustodyHold("EXTERNAL_SECRET_SALT_NOT_ATTESTED")
    if body.get("consented_to_independent_blind_study") is not True:
        raise CustodyHold("NO_EXTERNAL_CONSENT")
    if body.get("original_assay_sign_and_units_reviewed") is not True:
        raise CustodyHold("UNIT_AND_SIGN_NOT_REVIEWED")
    before=utc_timestamp(body.get("precommit_utc"))
    if "prediction_freeze_utc" in body:
        frozen=utc_timestamp(body["prediction_freeze_utc"])
        if not before<frozen:raise CustodyHold("PRECOMMIT_AFTER_PREDICTIONS")
    # A URL is merely a claim; the independent anchor must be checked outside.
    if not body["independent_timestamp_attestation_url"].startswith("https://"):
        raise CustodyHold("TIMESTAMP_WITNESS_NOT_AN_HTTPS_LINK")
    if sign.get("algorithm")!=SIGNATURE_ALGO:
        raise CustodyHold("SIGNATURE_ALGO_NOT_ED25519")
    pub=b64decode(sign.get("public_key_raw_b64"))
    sig=b64decode(sign.get("detached_signature_b64"))
    if len(pub)!=32 or len(sig)!=64:
        raise CustodyHold("SIGNATURE_OR_KEY_LENGTH_INVALID")
    return body,pub,sig

def check_signed_commitment(document, trusted_public_key_fingerprint):
    body,pk,signature=payload(document)
    fp=hash_bytes(pk)
    if not sha_ok(trusted_public_key_fingerprint):
        raise CustodyHold("NO_OUT_OF_BAND_TRUSTED_KEY_PIN")
    if fp!=trusted_public_key_fingerprint:
        raise CustodyHold("EXTERNAL_KEY_NOT_PRE_REGISTERED_OUT_OF_BAND")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        raise CustodyHold("CRYPTOGRAPHIC_LIBRARY_MISSING")
    try:
        Ed25519PublicKey.from_public_bytes(pk).verify(signature,canonical(body))
    except InvalidSignature:raise CustodyHold("DETACHED_SIGNATURE_INVALID")
    return {
       "schema_id":"janus.rowan.external_signed_custodian_public_gate_receipt.v2",
       "state":"SIGNATURE_VALID_ONLY_NOT_INDEPENDENT_CUSTODY_OR_UNBLIND",
       "signature_algorithm":"Ed25519",
       "external_key_sha256":fp,
       "payload_canonical_sha256":hash_bytes(canonical(body)),
       "salted_commitment_sha256":body["salted_plaintext_commitment_sha256"],
       "frozen_manifest_sha256":EXPECTED_FROZEN_INPUT_SHA256,
       "lab_independence_verified_out_of_band":False,
       "external_time_anchor_independently_verified":False,
       "prediction_source_receipts_frozen":False,
       "source_archive_pdb_coordinate_gate_passed":False,
       "true_blind_established":False,
       "access_to_real_labels":False,
       "experimental_performance_claim":False,
       "unblinding_permitted":False,
       "production_model_promotion":False,
       "reason":"A mathematically valid signature by an out-of-band pinned key verifies document bytes, not assay custody, signer organizational independence, timestamp witness validity or prediction availability. External reviewer must attest all independently."
    }

def hold_receipt():
    return {
      "schema_id":"janus.rowan.external_signed_custodian_public_gate_receipt.v2",
      "state":"HOLD_NO_EXTERNAL_LAB_CONSENT_OR_SIGNED_COMMITMENT",
      "candidates_not_contracted":["Loschmidt Laboratories / FireProtDB","Kuhlman Lab / ThermoMPNN"],
      "signed_external_payload_received":False,
      "out_of_band_external_key_pinned":False,
      "external_independent_time_anchor_verified":False,
      "unpublished_labels_held_outside_JANUS":False,
      "no_public_fireprot_relabeling_as_prospective":True,
      "original_FireProt_archive_PDB_sha_checked":False,
      "genuine_prospective_validation_started":False,
      "model_forecasts_frozen_for_external_unblinding":False,
      "unblinding_permitted":False,
      "paid_rowan_jobs":0,
      "production_model_promotion":False
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--document",type=Path,default=None,help="Optional externally supplied public signed metadata JSON, never assay labels.")
    p.add_argument("--trusted-external-key-sha256",default=None)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    try:
        if a.out.exists():raise CustodyHold("IMMUTABLE_AUDIT_OUTPUT_EXISTS")
        if a.document is None and a.trusted_external_key_sha256 is None:
            receipt=hold_receipt()
        elif a.document is None:
            raise CustodyHold("SIGNED_ATTESTATION_MISSING")
        else:
            if a.document.stat().st_size>100000:
                raise CustodyHold("PUBLIC_METADATA_DOCUMENT_TOO_LARGE")
            doc=json.loads(a.document.read_text(encoding="utf-8"))
            receipt=check_signed_commitment(doc,a.trusted_external_key_sha256)
        a.out.parent.mkdir(parents=True,exist_ok=True)
        a.out.write_text(json.dumps(receipt,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
        print("ROWAN_CUSTODY_GATE="+receipt["state"])
        return 0 if receipt["state"].startswith("SIGNATURE_VALID") else 2
    except (OSError,CustodyHold,ValueError) as exc:
        print("ROWAN_CUSTODY_GATE=HOLD_"+str(exc))
        return 2
if __name__=="__main__":
    raise SystemExit(main())
