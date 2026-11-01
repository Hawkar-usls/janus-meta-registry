"""Ed25519 external-custodian receipt gate. NO auto-approved custodian exists.

A signed receipt is accepted only against a key previously approved as an
independent external evaluator in the Meta Registry. Never accept a public
key from the receipt itself or from researcher-controlled CI artifacts.
A signature authenticates the owner of an approved key, not scientific truth.
"""
import argparse
import base64
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

PROTOCOL="JANUS_LOGOS_R14_EXTERNAL_RECEIPT_ED25519_v1"

def _iso(value):
    if type(value)!=str:raise ValueError("UTC timestamp must be string")
    dt=datetime.fromisoformat(value.replace("Z","+00:00"))
    if dt.tzinfo is None:raise ValueError("Timestamp missing timezone")
    return dt.astimezone(timezone.utc)

def verify_receipt(registration,receipt_bytes,sig_base64):
    if not isinstance(registration,dict) or registration.get("status")!="INDEPENDENT_CUSTODIAN_APPROVED":
        raise ValueError("BLOCKED_NO_APPROVED_EXTERNAL_CUSTODIAN")
    pub=registration.get("public_key_ed25519_pem")
    digest=registration.get("public_key_sha256")
    if type(pub)!=str or "BEGIN PUBLIC KEY" not in pub or type(digest)!=str:
        raise ValueError("Unregistered custodian key")
    if hashlib.sha256(pub.encode("utf-8")).hexdigest()!=digest:
        raise ValueError("Pre-approved key fingerprint mismatch")
    if not registration.get("verified_identity") or not registration.get("approval_commit"):
        raise ValueError("Human-verified external affiliation and prior registry approval required")
    key=load_pem_public_key(pub.encode("utf-8"))
    if not isinstance(key,Ed25519PublicKey):raise ValueError("Only Ed25519 signatures accepted")
    try:key.verify(base64.b64decode(sig_base64,validate=True),receipt_bytes)
    except Exception as e:raise ValueError("Invalid custodian signature") from e
    doc=json.loads(receipt_bytes)
    if type(doc)!=dict or doc.get("receipt_schema")!="JANUS_LOGOS_R14_EVALUATOR_RECEIPT_v1":
        raise ValueError("Unexpected receipt format")
    if doc.get("signature_protocol")!=PROTOCOL or doc.get("custodian_id")!=registration.get("custodian_id"):
        raise ValueError("Receipt from another custodian or protocol")
    if (doc.get("status")!="EXTERNAL_EVALUATOR_SIGNED" or
        doc.get("three_distinct_real_domains_certified_by_custodian") is not True or
        doc.get("independent_external_evaluation_verified") is not True):
        raise ValueError("Custodian has not attested independent external evidence")
    if _iso(doc.get("executed_utc"))<=_iso(registration.get("approved_utc")):
        raise ValueError("External evaluation predates trust registration")
    rows=doc.get("scores")
    if type(rows)!=list or len(rows)!=3:raise ValueError("Expected three independently sourced domains")
    if len({r.get("physical_domain") for r in rows})!=3 or len({r.get("domain_id") for r in rows})!=3:
        raise ValueError("Reused domain cannot establish cross-domain transfer")
    counts=0
    for row in rows:
        if not isinstance(row,dict) or any(k in row for k in
          ("test_y","test","raw_labels","private_data","test_inputs")):
            raise ValueError("Forbidden sealed labels in receipt")
        if row.get("candidate_decision")=="ABSTAIN":
            if row.get("pass_5pct_with_positive_lower_ci") is not False:
                raise ValueError("Abstention mislabeled as PASS")
        elif row.get("candidate_decision")=="PROPOSE":
            gain=row.get("relative_rmse_gain");ci=row.get("paired_bootstrap_ci95")
            if not isinstance(gain,(int,float)) or not isinstance(ci,list) or len(ci)!=2:
                raise ValueError("Missing paired scientific uncertainty")
            if not all(isinstance(x,(int,float)) and __import__("math").isfinite(x) for x in [gain,*ci]):
                raise ValueError("Nonfinite score")
            if row.get("pass_5pct_with_positive_lower_ci") != (gain>=0.05 and ci[0]>0):
                raise ValueError("Untrue reported scientific success")
        else:raise ValueError("Unrecognized candidate decision")
        counts+=int(row["pass_5pct_with_positive_lower_ci"])
    if doc.get("passed_domain_count")!=counts or doc.get("scientific_success_gate_met")!=(counts==3):
        raise ValueError("Reported global gate inconsistent with signed metrics")
    if doc.get("production_model_promotion_allowed") is not False:
        raise ValueError("External experiment cannot grant production authority")
    return {"integrity":"VALID_PREAPPROVED_EXTERNAL_ED25519_SIGNATURE",
            "independent_custodian_id":registration["custodian_id"],
            "external_scientific_result":"PASS_3_OF_3" if counts==3 else f"FAIL_{counts}_OF_3",
            "production_model_promotion_allowed":False,
            "scientific_limit":"NOT_PROOF_OF_DIVINE_AUTHORED_UNIVERSE_OR_P_EQUALS_NP"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registration",required=True)
    p.add_argument("--receipt",required=True)
    p.add_argument("--sig-base64-file",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    reg=json.loads(Path(a.registration).read_text(encoding="utf-8"))
    result=verify_receipt(reg,Path(a.receipt).read_bytes(),
                          Path(a.sig_base64_file).read_text().strip())
    Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result))
if __name__=="__main__":main()
