"""Offline synthetic trust-root verification; no source truth promotion."""
import base64
import hashlib
import json
import re
import runpy
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
R11 = runpy.run_path(str(HERE.parent / "epistemic-verification-r1-1" / "evidence_verifier.py"))
verify = R11["verify"]
canonical = R11["canonical"]
SCHEMA = "janus.test.signed-document.v1"
ISSUER = "JANUS_SYNTHETIC_TEST_ISSUER"
CONTEXT = "R1.2"
AUDIENCE = "JANUS_RESEARCH_ONLY"
FIELDS = {"schema", "issuer", "key_id", "context", "audience", "claim", "asserted_truth", "note"}

def enc(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")

def digest(b):
    return hashlib.sha256(b).hexdigest()

def openssl(*args):
    return subprocess.run(["openssl", *map(str,args)], capture_output=True, timeout=5, check=False)

def checked(*args):
    r = openssl(*args)
    if r.returncode:
        raise RuntimeError("OPENSSL_OPERATION_FAILED")
    return r.stdout

def key_fingerprint(pub):
    return digest(checked("pkey", "-pubin", "-in", pub, "-outform", "DER"))

def sign(doc, priv):
    data = enc(doc)
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp)/"message"
        f.write_bytes(data)
        sig = checked("pkeyutl", "-sign", "-inkey", priv, "-rawin", "-in", f)
    return {"document":doc, "sha256":digest(data), "signature":base64.b64encode(sig).decode("ascii")}

def authenticate(env, target, public_key, pinned_fingerprint):
    if type(env) is not dict or set(env) != {"document","sha256","signature"}:
        return "REJECTED_SCHEMA"
    doc = env["document"]
    if type(doc) is not dict or set(doc) != FIELDS:
        return "REJECTED_SCHEMA"
    if any(type(doc[k]) is not str or not 0 < len(doc[k]) <= (256 if k=="note" else 128)
           for k in FIELDS-{"asserted_truth"}) or type(doc["asserted_truth"]) is not bool:
        return "REJECTED_SCHEMA"
    if doc["schema"] != SCHEMA:
        return "REJECTED_SCHEMA"
    h, sig = env["sha256"], env["signature"]
    if type(h) is not str or not re.fullmatch("[0-9a-f]{64}",h) or type(sig) is not str or len(sig)!=88:
        return "REJECTED_SCHEMA"
    try:
        rawsig = base64.b64decode(sig,validate=True)
    except (ValueError, TypeError):
        return "REJECTED_SCHEMA"
    if len(rawsig)!=64 or base64.b64encode(rawsig).decode("ascii") != sig:
        return "REJECTED_SCHEMA"
    data = enc(doc)
    if len(data)>4096:
        return "REJECTED_SCHEMA"
    if digest(data)!=h:
        return "REJECTED_DIGEST"
    if doc["issuer"]!=ISSUER:
        return "REJECTED_ISSUER"
    if doc["key_id"]!=pinned_fingerprint or key_fingerprint(public_key)!=pinned_fingerprint:
        return "REJECTED_KEY_ID"
    if doc["context"]!=CONTEXT:
        return "REJECTED_CONTEXT"
    if doc["audience"]!=AUDIENCE:
        return "REJECTED_AUDIENCE"
    if target is None or canonical(verify(doc["claim"]))!=target:
        return "REJECTED_BINDING"
    with tempfile.TemporaryDirectory() as tmp:
        msg, sigfile = Path(tmp)/"message", Path(tmp)/"signature"
        msg.write_bytes(data)
        sigfile.write_bytes(rawsig)
        r=openssl("pkeyutl","-verify","-pubin","-inkey",public_key,"-rawin","-in",msg,"-sigfile",sigfile)
    return "AUTHENTICATED_TEST_ORIGIN" if r.returncode==0 else "REJECTED_SIGNATURE"

def assess(claim,env,pub,pin):
    baseline=verify(claim)
    return {"origin":authenticate(env,canonical(baseline),pub,pin),
            "truth":baseline["truth_status"],"action":baseline["epistemic_action"],
            "source_truth_promotion":False,"external_identity_verified":False,
            "freshness_verified":False}

def fixture(t,priv,other,pin):
    doc={"schema":SCHEMA,"issuer":ISSUER,"key_id":pin,"context":CONTEXT,"audience":AUDIENCE,
         "claim":t["claim"],"asserted_truth":True,"note":"synthetic report"}
    m=t["mutation"]
    if m=="valid_false": doc["asserted_truth"]=False
    if m=="signed_false_assertion": doc["asserted_truth"]=not bool(verify(t["claim"])["verified_evidence"]["result"])
    if m=="unknown_issuer": doc["issuer"]="UNKNOWN"
    if m=="unknown_key_id": doc["key_id"]="0"*64
    if m=="other_claim": doc["claim"]="3 = 3"
    if m=="other_operator": doc["claim"]="2 != 2"
    if m=="other_context": doc["context"]="OTHER"
    if m=="other_audience": doc["audience"]="OTHER"
    if m=="extra_verified_flag": doc["verified"]=True
    if m=="wrong_assertion_type": doc["asserted_truth"]=1
    if m=="invalid_claim": doc["claim"]="2 = 2"
    if m=="equivalent_operands": doc["claim"]="3 != 2"
    if m=="equivalent_zero": doc["claim"]="+0 = 0"
    if m=="wrong_schema_version": doc["schema"]="other.v2"
    if m=="oversize_document": doc["note"]="x"*300
    if m=="signed_unknown_proof": doc["note"]="I claim to have proved P equals NP"
    env=sign(doc,other if m=="wrong_key" else priv)
    if m=="tamper_body": env["document"]["note"]="altered"
    if m=="tamper_rehash":
        env["document"]["note"]="altered"
        env["sha256"]=digest(enc(env["document"]))
    if m=="changed_issuer_rehash":
        env["document"]["issuer"]="UNKNOWN"
        env["sha256"]=digest(enc(env["document"]))
    if m=="tamper_signature":
        raw=bytearray(base64.b64decode(env["signature"]))
        raw[0]^=1
        env["signature"]=base64.b64encode(raw).decode("ascii")
    if m=="bad_digest_format": env["sha256"]="BAD"
    if m=="bad_signature_encoding": env["signature"]="!"*88
    if m=="missing_signature": del env["signature"]
    if m=="malformed_envelope": env=None
    return env

def main():
    spec=json.loads((HERE/"precommit.json").read_text(encoding="utf-8"))
    rows=[]
    with tempfile.TemporaryDirectory() as tmp:
        priv,pub,other=[Path(tmp)/n for n in ("trusted.pem","trusted.pub","other.pem")]
        checked("genpkey","-algorithm","ED25519","-out",priv)
        checked("pkey","-in",priv,"-pubout","-out",pub)
        checked("genpkey","-algorithm","ED25519","-out",other)
        pin=key_fingerprint(pub)
        for t in spec["tests"]:
            env=fixture(t,priv,other,pin)
            r=assess(t["claim"],env,pub,pin)
            ok=all(r[k]==v for k,v in t["expected"].items())
            if t["mutation"]=="same_document_repeated":
                ok=ok and assess(t["claim"],env,pub,pin)==r
            ok=ok and r["source_truth_promotion"] is False and r["external_identity_verified"] is False and r["freshness_verified"] is False
            rows.append({"id":t["id"],"expected":t["expected"],"observed":r,"pass":ok})
    passed=sum(r["pass"] for r in rows)
    status="ENGINEERING_PASS" if passed==len(rows)==30 else "ENGINEERING_FAIL"
    print(json.dumps({"schema":"janus.epistemic_verification.r1_2.result.v1","status":status,
          "passed":passed,"total":len(rows),"test_public_key_sha256":pin,
          "openssl":checked("version").decode().strip(),"trust_scope":"EPHEMERAL_SYNTHETIC_TEST_ONLY",
          "production":False,"training":False,"knowledge_write":False,"rows":rows},indent=2))
    if status!="ENGINEERING_PASS":
        raise SystemExit(1)

if __name__=="__main__":
    main()
