"""R1.4A synthetic cross-run checkpoint producer. No live memory access."""
import json
import os
import runpy
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
T = runpy.run_path(str(HERE.parent / "epistemic-verification-r1-3" / "trust_memory.py"))
enc, digest, sign, checked, key_fingerprint, open_store, stage, snapshot, token = (
    T[k] for k in ("enc","digest","sign","checked","key_fingerprint","open_store","stage","snapshot","token"))
NOW = T["NOW"]
ISSUER, CONTEXT, AUDIENCE, SCHEMA = (T[k] for k in ("ISSUER","CONTEXT","AUDIENCE","SCHEMA"))

def source():
    return {"run_id":int(os.environ["GITHUB_RUN_ID"]),
            "attempt":int(os.environ["GITHUB_RUN_ATTEMPT"]),
            "head_sha":os.environ["GITHUB_SHA"]}

def main():
    out=Path(os.environ["RUNNER_TEMP"])/"epistemic-r1-4a-checkpoint"
    out.mkdir(exist_ok=False)
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        keys={}
        for name in ("old","new"):
            priv,pub=root/(name+".pem"),root/(name+".pub")
            checked("genpkey","-algorithm","ED25519","-out",priv)
            checked("pkey","-in",priv,"-pubout","-out",pub)
            keys[name]=(priv,pub,key_fingerprint(pub))
        pubs={v[2]:v[1] for v in keys.values()}
        def entry(name,revoked):
            return {"issuer":ISSUER,"key_id":keys[name][2],"not_before":NOW-200,
                    "not_after":NOW+600,"revoked_at":revoked}
        reg1={"schema":"janus.synthetic.trust.v1","keys":[entry("old",None)]}
        reg2={"schema":"janus.synthetic.trust.v1","keys":[entry("old",NOW+10),entry("new",None)]}
        def doc(key,claim,nonce):
            return sign({"schema":SCHEMA,"issuer":ISSUER,"key_id":keys[key][2],"context":CONTEXT,
                         "audience":AUDIENCE,"claim":claim,"asserted_truth":True,
                         "nonce":nonce*32,"issued_at":NOW-10,"expires_at":NOW+200},keys[key][0])
        original=doc("old","2 = 2","1")
        db=open_store(root/"staging.sqlite")
        verdict,receipt=stage(db,original,"2 = 2",reg1,digest(enc(reg1)),pubs,NOW,token(db))
        if verdict!="ACCEPTED_STAGED" or receipt["truth_status"]!="TRUE" or receipt["knowledge_admitted"] is not False:
            raise RuntimeError("A_STAGE_HOLD")
        snap=snapshot(db)
        db.close()
        if snap["version"]!=1 or len(snap["receipts"])!=1:
            raise RuntimeError("A_STATE_HOLD")
        cp={"schema":"janus.epistemic.r1_4a.checkpoint.v1","source":source(),
            "version":1,"parent_sha256":"0"*64,"test_clock":NOW,
            "registries":[{"revision":1,"body":reg1,"sha256":digest(enc(reg1))},
                          {"revision":2,"body":reg2,"sha256":digest(enc(reg2))}],
            "active_registry_revision":1,"public_keys":{k:p.read_text() for k,p in pubs.items()},
            "snapshot":snap,"snapshot_sha256":digest(enc(snap)),
            "accepted_envelope":original,"fixtures":{"rotated_replay":doc("new","2 = 2","1"),
            "symbolic":doc("new","P = NP","2"),"false":doc("new","2 = 3","3")},
            "production":False,"knowledge_write":False}
        raw=enc(cp)
        if len(raw)>32768 or b"PRIVATE KEY" in raw:
            raise RuntimeError("A_EXPORT_HOLD")
        (out/"checkpoint.json").write_bytes(raw)
        print(json.dumps({"schema":"janus.epistemic.r1_4a.run_a.v1","status":"CHECKPOINT_READY",
            "source":cp["source"],"checkpoint_sha256":digest(raw),"checkpoint_bytes":len(raw),
            "snapshot_sha256":cp["snapshot_sha256"],"version":1,"registry_revision":1,
            "receipt_count":len(snap["receipts"]),"registry_hashes":[x["sha256"] for x in cp["registries"]],
            "private_keys_exported":False,"production":False,"knowledge_write":False},sort_keys=True))
if __name__=="__main__":
    main()
