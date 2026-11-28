"""Synthetic trust registry and transactional receipt staging; research only."""
import base64
import copy
import json
import re
import runpy
import sqlite3
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
R12 = runpy.run_path(str(HERE.parent / "epistemic-verification-r1-2" / "provenance_verifier.py"))
enc, digest, sign, checked, openssl, key_fingerprint = [R12[k] for k in ("enc","digest","sign","checked","openssl","key_fingerprint")]
verify, canonical = R12["verify"], R12["canonical"]
NOW = 1700001000
ISSUER, CONTEXT, AUDIENCE = "SYNTHETIC_ISSUER", "R1.3", "JANUS_STAGING_ONLY"
SCHEMA = "janus.test.timed-document.v1"
FIELDS = {"schema","issuer","key_id","context","audience","claim","asserted_truth","nonce","issued_at","expires_at"}

def open_store(path):
    db = sqlite3.connect(path, isolation_level=None, timeout=5)
    db.execute("CREATE TABLE IF NOT EXISTS meta (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL)")
    db.execute("INSERT OR IGNORE INTO meta VALUES (1,0)")
    db.execute("CREATE TABLE IF NOT EXISTS receipts (issuer TEXT, nonce TEXT, body TEXT NOT NULL, PRIMARY KEY(issuer,nonce))")
    return db

def snapshot(db):
    return {"version":db.execute("SELECT version FROM meta WHERE id=1").fetchone()[0],
            "receipts":[list(r) for r in db.execute("SELECT issuer,nonce,body FROM receipts ORDER BY issuer,nonce")]}

def token(db):
    s=snapshot(db)
    return (s["version"],digest(enc(s)))

def verify_doc(env,claim,registry,pin,public_keys,now):
    if digest(enc(registry)) != pin:
        return "REGISTRY_INTEGRITY_HOLD",None
    if type(env) is not dict or set(env)!={"document","sha256","signature"}:
        return "SCHEMA_INVALID",None
    doc=env["document"]
    if type(doc) is not dict or set(doc)!=FIELDS:
        return "SCHEMA_INVALID",None
    stringfields=FIELDS-{"issued_at","expires_at","asserted_truth"}
    if any(type(doc[k]) is not str or not 0<len(doc[k])<=128 for k in stringfields):
        return "SCHEMA_INVALID",None
    if (doc["schema"]!=SCHEMA or type(doc["asserted_truth"]) is not bool
        or type(doc["issued_at"]) is not int or type(doc["expires_at"]) is not int
        or not re.fullmatch("[0-9a-f]{32}",doc["nonce"])
        or not re.fullmatch("[0-9a-f]{64}",doc["key_id"])
        or not 0<doc["expires_at"]-doc["issued_at"]<=300):
        return "SCHEMA_INVALID",None
    h,sig=env["sha256"],env["signature"]
    if type(h) is not str or not re.fullmatch("[0-9a-f]{64}",h) or type(sig) is not str or len(sig)!=88:
        return "SCHEMA_INVALID",None
    try:
        raw=base64.b64decode(sig,validate=True)
    except (TypeError,ValueError):
        return "SCHEMA_INVALID",None
    if len(raw)!=64 or base64.b64encode(raw).decode("ascii")!=sig:
        return "SCHEMA_INVALID",None
    data=enc(doc)
    if digest(data)!=h:
        return "DIGEST_INVALID",None
    entry=next((k for k in registry["keys"] if k["issuer"]==doc["issuer"] and k["key_id"]==doc["key_id"]),None)
    if entry is None:
        return "KEY_UNKNOWN",None
    pub=public_keys.get(doc["key_id"])
    if pub is None or key_fingerprint(pub)!=entry["key_id"]:
        return "KEY_UNKNOWN",None
    with tempfile.TemporaryDirectory() as tmp:
        msg,sf=Path(tmp)/"message",Path(tmp)/"signature"
        msg.write_bytes(data)
        sf.write_bytes(raw)
        res=openssl("pkeyutl","-verify","-pubin","-inkey",pub,"-rawin","-in",msg,"-sigfile",sf)
    if res.returncode!=0:
        return "SIGNATURE_INVALID",None
    if entry["revoked_at"] is not None and now>=entry["revoked_at"]:
        return "KEY_REVOKED",None
    if now<entry["not_before"]:
        return "KEY_NOT_YET_VALID",None
    if now>=entry["not_after"]:
        return "KEY_EXPIRED",None
    if not entry["not_before"]<=doc["issued_at"]<entry["not_after"]:
        return "ISSUED_OUTSIDE_KEY_WINDOW",None
    if doc["issued_at"]>now:
        return "DOCUMENT_FUTURE",None
    if now-doc["issued_at"]>300:
        return "DOCUMENT_STALE",None
    if now>=doc["expires_at"]:
        return "DOCUMENT_EXPIRED",None
    target=canonical(verify(claim))
    if doc["context"]!=CONTEXT or doc["audience"]!=AUDIENCE or target is None or canonical(verify(doc["claim"]))!=target:
        return "BINDING_INVALID",None
    return "VERIFIED_FOR_STAGING",{"issuer":doc["issuer"],"nonce":doc["nonce"],
        "key_id":doc["key_id"],"document_sha256":h,"claim":doc["claim"],
        "asserted_truth":doc["asserted_truth"],"truth_status":verify(claim)["truth_status"],
        "origin":"AUTHENTICATED_SYNTHETIC_TEST_ORIGIN","knowledge_admitted":False}

def stage(db,env,claim,registry,pin,public_keys,now,expected):
    status,receipt=verify_doc(env,claim,registry,pin,public_keys,now)
    if status!="VERIFIED_FOR_STAGING":
        return status,None
    db.execute("BEGIN IMMEDIATE")
    try:
        current=token(db)
        if expected[0]!=current[0]:
            db.execute("ROLLBACK")
            return "STATE_CAS_HOLD",None
        if expected[1]!=current[1]:
            db.execute("ROLLBACK")
            return "STATE_INTEGRITY_HOLD",None
        if db.execute("SELECT 1 FROM receipts WHERE issuer=? AND nonce=?",(receipt["issuer"],receipt["nonce"])).fetchone():
            db.execute("ROLLBACK")
            return "REPLAY",None
        db.execute("INSERT INTO receipts VALUES (?,?,?)",(receipt["issuer"],receipt["nonce"],enc(receipt).decode("ascii")))
        changed=db.execute("UPDATE meta SET version=version+1 WHERE id=1 AND version=?",(expected[0],)).rowcount
        if changed!=1:
            db.execute("ROLLBACK")
            return "STATE_CAS_HOLD",None
        db.execute("COMMIT")
        return "ACCEPTED_STAGED",receipt
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise

def main():
    spec=json.loads((HERE/"precommit.json").read_text())
    rows=[]
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        keys={}
        for name in ("old","new","future","expired","other"):
            priv,pub=root/(name+".pem"),root/(name+".pub")
            checked("genpkey","-algorithm","ED25519","-out",priv)
            checked("pkey","-in",priv,"-pubout","-out",pub)
            keys[name]=(priv,pub,key_fingerprint(pub))
        windows={"old":(NOW-600,NOW+600,NOW-10),"new":(NOW-200,NOW+600,None),
                 "future":(NOW+1,NOW+600,None),"expired":(NOW-600,NOW-1,None)}
        reg={"schema":"janus.synthetic.trust.v1","keys":[{"issuer":ISSUER,"key_id":keys[n][2],
              "not_before":w[0],"not_after":w[1],"revoked_at":w[2]} for n,w in windows.items()]}
        pin=digest(enc(reg))
        pubs={v[2]:v[1] for v in keys.values()}
        def document(name="new",claim="2 = 2",nonce="1"*32,**changes):
            d={"schema":SCHEMA,"issuer":ISSUER,"key_id":keys[name][2],"context":CONTEXT,
               "audience":AUDIENCE,"claim":claim,"asserted_truth":True,"nonce":nonce,
               "issued_at":NOW-30,"expires_at":NOW+90}
            d.update(changes)
            return sign(d,keys[name][0])
        for t in spec["tests"]:
            case=t["case_name"]
            path=root/(t["id"]+".sqlite")
            db=open_store(path)
            expected=token(db)
            env=document()
            target="2 = 2"
            registry=reg
            fixture_pin=pin
            preliminary=[]
            if case=="old_key_after_rotation":
                # Pre-rotation receipt accepted under separately pinned prior registry.
                prior=copy.deepcopy(reg)
                prior["keys"][0]["revoked_at"]=None
                prior["keys"]=[prior["keys"][0]]
                old_env=document("old",nonce="2"*32,issued_at=NOW-60)
                prior_status,_=stage(db,old_env,target,prior,digest(enc(prior)),pubs,NOW-20,expected)
                preliminary.append(prior_status=="ACCEPTED_STAGED")
                expected=token(db)
                env=document("old")
            if case in ("unknown_key",): env=document("other")
            if case=="unknown_issuer": env=document(issuer="UNKNOWN")
            if case=="wrong_signer": env=sign(env["document"],keys["other"][0])
            if case in ("tamper_nonce","tamper_time"):
                env["document"]["nonce" if case=="tamper_nonce" else "issued_at"]="2"*32 if case=="tamper_nonce" else NOW-31
                env["sha256"]=digest(enc(env["document"]))
            if case=="tamper_digest": env["sha256"]="0"*64
            if case=="stale":
                # T10: valid key at issuance; stale takes precedence over expired.
                registry=copy.deepcopy(reg)
                next(k for k in registry["keys"] if k["key_id"]==keys["new"][2])["not_before"]=NOW-600
                fixture_pin=digest(enc(registry))
                env=document(issued_at=NOW-301,expires_at=NOW-1)
            if case=="future": env=document(issued_at=NOW+1)
            if case=="expired": env=document(expires_at=NOW-1)
            if case=="key_not_yet_valid": env=document("future")
            if case=="key_expired": env=document("expired")
            if case=="issued_before_key": env=document(issued_at=NOW-250,expires_at=NOW+40)
            if case=="issued_after_revocation": env=document("old",issued_at=NOW-5)
            if case=="revocation_retroactive": env=document("old",issued_at=NOW-60)
            if case in ("replay","nonce_reuse_other_claim","restart_replay","cas_stale","state_tamper"):
                first,_=stage(db,env,target,reg,pin,pubs,NOW,expected)
                preliminary.append(first=="ACCEPTED_STAGED")
                if case!="cas_stale": expected=token(db)
                if case=="nonce_reuse_other_claim":
                    target="2 = 3"
                    env=document(claim=target)
                if case=="restart_replay":
                    db.close()
                    db=open_store(path)
                    preliminary.append(token(db)==expected)
                if case=="state_tamper":
                    db.execute("UPDATE receipts SET body='tampered'")
            if case=="wrong_context": env=document(context="OTHER")
            if case=="wrong_audience": env=document(audience="OTHER")
            if case=="wrong_claim": env=document(claim="3 = 3")
            if case=="registry_tamper":
                registry=copy.deepcopy(reg)
                registry["keys"][0]["revoked_at"]=None
                env=document("old")
            if case=="failed_then_valid":
                broken=copy.deepcopy(env)
                broken["sha256"]="0"*64
                before=token(db)
                failed,_=stage(db,broken,target,reg,pin,pubs,NOW,expected)
                preliminary.append(failed=="DIGEST_INVALID" and token(db)==before)
            if case=="signed_symbolic":
                target="P = NP"
                env=document(claim=target)
            if case=="signed_false":
                target="2 = 3"
                env=document(claim=target,asserted_truth=True)
            if case=="bad_nonce": env=document(nonce="bad")
            if case=="bad_time_type": env=document(issued_at=True)
            if case=="bad_lifetime": env=document(expires_at=NOW+400)
            before=snapshot(db)
            status,receipt=stage(db,env,target,registry,fixture_pin,pubs,NOW,expected)
            after=snapshot(db)
            accepted=status=="ACCEPTED_STAGED"
            mutation_ok=(after["version"]==before["version"]+1 and len(after["receipts"])==len(before["receipts"])+1) if accepted else after==before
            receipt_ok=(receipt is not None and receipt["truth_status"]==verify(target)["truth_status"] and receipt["knowledge_admitted"] is False) if accepted else receipt is None
            ok=status==t["expected"] and mutation_ok and receipt_ok and all(preliminary)
            rows.append({"id":t["id"],"case":case,"expected":t["expected"],"observed":status,
                "mutation_ok":mutation_ok,"receipt_ok":receipt_ok,"preliminary":preliminary,
                "truth_status":receipt["truth_status"] if receipt else None,"pass":ok})
            db.close()
    passed=sum(r["pass"] for r in rows)
    status="ENGINEERING_PASS" if passed==len(rows)==32 else "ENGINEERING_FAIL"
    print(json.dumps({"schema":"janus.epistemic_verification.r1_3.result.v1","status":status,
       "passed":passed,"total":len(rows),"registry_sha256":pin,"public_key_fingerprints":{k:v[2] for k,v in keys.items()},
       "test_clock":NOW,"sqlite":sqlite3.sqlite_version,"trust_scope":"SYNTHETIC_LOCAL_STAGING_ONLY",
       "production":False,"training":False,"knowledge_write":False,"rows":rows},indent=2))
    if status!="ENGINEERING_PASS":
        raise SystemExit(1)

if __name__=="__main__":
    main()
