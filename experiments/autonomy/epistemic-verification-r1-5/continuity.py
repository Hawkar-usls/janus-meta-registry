"""Bounded R1.5A migration and automatic fresh-job inheritance. Synthetic only."""
import copy
import json
import os
import runpy
import tempfile
import zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
T=runpy.run_path(str(HERE.parent/"epistemic-verification-r1-3"/"trust_memory.py"))
enc,digest,sign,checked,key_fingerprint,open_store,stage,snapshot,token=(T[k] for k in ("enc","digest","sign","checked","key_fingerprint","open_store","stage","snapshot","token"))
NOW=T["NOW"]
SCHEMA="janus.epistemic.r1_5a.checkpoint.v1"
ROOT=Path(os.environ["RUNNER_TEMP"])/"r1-5a"
def need(x,reason):
    if not x: raise RuntimeError(reason)
def load_zip(path,sha,names):
    raw=path.read_bytes()
    need(len(raw)<=131072 and digest(raw)==sha,"ZIP_DIGEST")
    with zipfile.ZipFile(path) as z:
        need(set(z.namelist())==set(names) and len(z.namelist())==len(names),"ZIP_MEMBERS")
        out={}
        for n in names:
            need(z.getinfo(n).file_size<=65536,"MEMBER_SIZE")
            b=z.read(n); p=json.loads(b)
            need(enc(p)==b,"CANONICAL")
            out[n]=p
    return out
def source():
    return {"run_id":int(os.environ["GITHUB_RUN_ID"]),"attempt":int(os.environ["GITHUB_RUN_ATTEMPT"]),"head_sha":os.environ["GITHUB_SHA"],"job":os.environ["GITHUB_JOB"]}
def reconstruct(cp,root):
    need(cp["schema"]==SCHEMA and cp["production"] is False and cp["knowledge_write"] is False,"SCOPE")
    regs=cp["registries"]
    need([r["revision"] for r in regs]==[1,2,3],"REGISTRY_ORDER")
    need(all(digest(enc(r["body"]))==r["sha256"] for r in regs),"REGISTRY_HASH")
    need(cp["active_registry_revision"]==3,"REGISTRY_ROLLBACK")
    pubs={}
    for k,pem in cp["public_keys"].items():
        need(len(k)==64 and all(x in "0123456789abcdef" for x in k) and len(pem)<1024 and pem.startswith("-----BEGIN PUBLIC KEY-----") and "PRIVATE KEY" not in pem,"PUBLIC_KEY")
        p=root/(k+".pub");p.write_text(pem)
        need(key_fingerprint(p)==k,"KEY_PIN");pubs[k]=p
    need(set(pubs)=={x["key_id"] for r in regs for x in r["body"]["keys"]},"KEY_SET")
    db=open_store(root/"stage.sqlite")
    need(snapshot(db)=={"version":0,"receipts":[]},"FRESH_STORE")
    last_time=-1;last_rev=0
    for row in cp["history"]:
        rev=row["revision"];now=row["accepted_at"]
        need(rev in (1,2,3) and rev>=last_rev and now>=last_time,"HISTORY_ORDER")
        last_rev=rev;last_time=now
        reg=regs[rev-1]
        status,receipt=stage(db,row["envelope"],row["claim"],reg["body"],reg["sha256"],pubs,now,token(db))
        need(status=="ACCEPTED_STAGED" and receipt["knowledge_admitted"] is False,"HISTORY_VERIFY")
    need(snapshot(db)==cp["snapshot"] and digest(enc(snapshot(db)))==cp["snapshot_sha256"] and cp["version"]==snapshot(db)["version"],"SNAPSHOT_MISMATCH")
    return db,pubs

def migration():
    a=load_zip(ROOT/"a.zip","27d4aaa759afbfd42e27dc47030dfac73a8df3405f8f2453f91a5de57f489eb1",["checkpoint.json"])["checkpoint.json"]
    b=load_zip(ROOT/"b.zip","39fbacd94e494a0c1eacff2b9f39460f4e733d84ddbb47f96d7221592e7a4450",["successor.json","cortex-staging.json","result.json"])
    s=b["successor.json"];r=b["result.json"];e=b["cortex-staging.json"]
    need(digest(enc(a))=="6b14e0630c3873b5f8f0f1911f972f07bab9035856cc3a22e1263f92f2b92b19","A_HASH")
    need(digest(enc(s))=="74d40c51a6992ff2f06c4db5bedb103912f4bcf548115e65b64cc9595d7addc7","B_HASH")
    need(s["parent_sha256"]==digest(enc(a)) and s["version"]==3 and s["active_registry_revision"]==2,"B_LINK")
    need(r["passed"]==r["total"]==24 and r["successor_sha256"]==digest(enc(s)) and all(x["pass"] for x in r["checks"].values()),"B_RESULT")
    need(e["successor_sha256"]==digest(enc(s)) and e["active_cortex_write"] is False and e["records"]==[json.loads(x[2]) for x in s["snapshot"]["receipts"]],"B_EXPORT")
    need(s["registry_sha256"]==a["registries"][1]["sha256"] and digest(enc(s["snapshot"]))==s["snapshot_sha256"],"B_REGISTRY")
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);priv=root/"test.pem";pub=root/"test.pub"
        checked("genpkey","-algorithm","ED25519","-out",priv)
        checked("pkey","-in",priv,"-pubout","-out",pub)
        kid=key_fingerprint(pub)
        regs=copy.deepcopy(a["registries"]);reg3=copy.deepcopy(regs[1]["body"])
        for k in reg3["keys"]:
            if k["revoked_at"] is None: k["revoked_at"]=NOW+30
        reg3["keys"].append({"issuer":T["ISSUER"],"key_id":kid,"not_before":NOW+25,"not_after":NOW+600,"revoked_at":None})
        regs.append({"revision":3,"body":reg3,"sha256":digest(enc(reg3))})
        hist=[{"envelope":a["accepted_envelope"],"claim":"2 = 2","revision":1,"accepted_at":NOW},
              {"envelope":a["fixtures"]["symbolic"],"claim":"P = NP","revision":2,"accepted_at":NOW+20},
              {"envelope":a["fixtures"]["false"],"claim":"2 = 3","revision":2,"accepted_at":NOW+20}]
        pending=[]
        for i,claim in enumerate(("7 != 8","NP = P","9 = 10"),4):
            doc={"schema":T["SCHEMA"],"issuer":T["ISSUER"],"key_id":kid,"context":T["CONTEXT"],"audience":T["AUDIENCE"],"claim":claim,"asserted_truth":True,"nonce":str(i)*32,"issued_at":NOW+30,"expires_at":NOW+200}
            pending.append({"envelope":sign(doc,priv),"claim":claim,"revision":3,"accepted_at":NOW+i*10})
        cp={"schema":SCHEMA,"source":source(),"version":3,"parent_sha256":digest(enc(s)),
            "registries":regs,"active_registry_revision":3,"public_keys":{**a["public_keys"],kid:pub.read_text()},
            "history":hist,"pending":pending,"snapshot":s["snapshot"],"snapshot_sha256":s["snapshot_sha256"],"production":False,"knowledge_write":False}
        db,_=reconstruct(cp,root);db.close()
    publish(cp,{"legacy_zip_bytes_verified":True,"legacy_version_3_reconstructed":True,"legacy_export_verified":True})

def cycle(n):
    pin=os.environ["PARENT_CHECKPOINT"]
    cp=load_zip(ROOT/"parent.zip",os.environ["PARENT_ZIP"],["checkpoint.json","result.json","cortex-staging.json"])["checkpoint.json"]
    need(digest(enc(cp))==pin and cp["version"]==n+2 and len(cp["pending"])==4-n,"PARENT_PIN")
    need(cp["source"]["run_id"]==source()["run_id"] and cp["source"]["job"]!=source()["job"],"JOB_BINDING")
    checks={}
    with tempfile.TemporaryDirectory() as d:
        db,pubs=reconstruct(cp,Path(d)); before=token(db);row=cp["pending"][0];reg=cp["registries"][2]
        # If this is the first advance, use a correctly signed pending doc with a stale CAS.
        # Later advances also test replay of a prior accepted revision-3 receipt.
        bad=copy.deepcopy(row["envelope"]);bad["sha256"]="0"*64
        status,_=stage(db,bad,row["claim"],reg["body"],reg["sha256"],pubs,row["accepted_at"],before)
        checks["tampered_rejected_unchanged"]=status=="DIGEST_INVALID" and token(db)==before
        status,_=stage(db,row["envelope"],row["claim"],reg["body"],reg["sha256"],pubs,row["accepted_at"],(before[0]-1,before[1]))
        checks["stale_cas_unchanged"]=status=="STATE_CAS_HOLD" and token(db)==before
        status,receipt=stage(db,row["envelope"],row["claim"],reg["body"],reg["sha256"],pubs,row["accepted_at"],before)
        checks["new_receipt"]=status=="ACCEPTED_STAGED" and receipt["knowledge_admitted"] is False
        checks["truth_preserved"]=receipt is not None and receipt["truth_status"]==("TRUE","UNRESOLVED","FALSE")[n-1]
        after=token(db)
        status,_=stage(db,row["envelope"],row["claim"],reg["body"],reg["sha256"],pubs,row["accepted_at"],after)
        checks["replay_unchanged"]=status=="REPLAY" and token(db)==after
        if n>1:
            old=cp["history"][-1]
            status,_=stage(db,old["envelope"],old["claim"],reg["body"],reg["sha256"],pubs,row["accepted_at"],after)
            checks["inherited_replay_unchanged"]=status=="REPLAY" and token(db)==after
        snap=snapshot(db);db.close()
    cp["parent_sha256"]=pin;cp["source"]=source();cp["version"]=snap["version"]
    cp["snapshot"]=snap;cp["snapshot_sha256"]=digest(enc(snap));cp["history"].append(cp["pending"].pop(0))
    checks["version_advance"]=cp["version"]==n+3
    with tempfile.TemporaryDirectory() as d:
        db,_=reconstruct(cp,Path(d));db.close()
    checks["self_contained_restore"]=True
    publish(cp,checks)

def publish(cp,checks):
    raw=enc(cp);need(len(raw)<=65536 and b"PRIVATE KEY" not in raw,"EXPORT_BOUND")
    records=[json.loads(x[2]) for x in cp["snapshot"]["receipts"]]
    checks["no_knowledge_admission"]=all(x["knowledge_admitted"] is False for x in records)
    need(all(checks.values()),"CONTROL_FAIL")
    out=ROOT/"output";out.mkdir()
    sha=digest(raw)
    result={"schema":"janus.epistemic.r1_5a.result.v1","status":"ENGINEERING_PASS","source":source(),"version":cp["version"],"parent_sha256":cp["parent_sha256"],"checkpoint_sha256":sha,"checks":checks,"production":False,"active_cortex_write":False}
    export={"schema":"janus.cortex.staging.preview.v1","checkpoint_sha256":sha,"records":records,"active_cortex_write":False}
    for name,data in (("checkpoint",cp),("result",result),("cortex-staging",export)):
        (out/(name+".json")).write_bytes(enc(data))
    print(json.dumps(result,sort_keys=True))
    with open(os.environ["GITHUB_OUTPUT"],"a") as f: f.write("checkpoint_sha="+sha+"\n")
if __name__=="__main__":
    n=int(os.environ["CYCLE"])
    migration() if n==0 else cycle(n)
