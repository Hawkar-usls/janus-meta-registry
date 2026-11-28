"""Restore exact operator-pinned checkpoint on a fresh GitHub runner."""
import copy
import json
import os
import runpy
import tempfile
import zipfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
T=runpy.run_path(str(HERE.parent/"epistemic-verification-r1-3"/"trust_memory.py"))
enc,digest,open_store,stage,snapshot,token,key_fingerprint=(T[k] for k in ("enc","digest","open_store","stage","snapshot","token","key_fingerprint"))
NOW=T["NOW"]
ROOT=Path(os.environ["RUNNER_TEMP"])/"epistemic-r1-4b"
def require(x,reason):
    if not x: raise RuntimeError(reason)

def check_meta(anchor,run,artifact):
    if not anchor: return "ANCHOR_MISSING"
    a=anchor["source"]; f=anchor["artifact"]
    if (run.get("id"),run.get("run_attempt"),run.get("head_sha"),run.get("conclusion")) != (a["run_id"],a["attempt"],a["head_sha"],"success"):
        return "RUN_IDENTITY_HOLD"
    if (artifact.get("id"),artifact.get("name"),artifact.get("size_in_bytes"),artifact.get("digest"),artifact.get("expired")) != (f["id"],f["name"],f["size"],"sha256:"+f["sha256"],False):
        return "ARTIFACT_IDENTITY_HOLD"
    if artifact.get("workflow_run",{}).get("id")!=a["run_id"] or artifact["workflow_run"].get("head_sha")!=a["head_sha"]:
        return "ARTIFACT_IDENTITY_HOLD"
    return "OK"

def check_checkpoint(c,a):
    if not a: return "ANCHOR_MISSING"
    p=a["checkpoint"]
    if c.get("schema")!="janus.epistemic.r1_4a.checkpoint.v1": return "SCHEMA_HOLD"
    if c.get("source")!={k:a["source"][k] for k in ("run_id","attempt","head_sha")}: return "SOURCE_HOLD"
    if c.get("version")!=p["version"]: return "VERSION_HOLD"
    if c.get("parent_sha256")!=p["parent_sha256"]: return "PARENT_HOLD"
    if c.get("active_registry_revision")!=p["active_registry_revision"]: return "REGISTRY_REVISION_HOLD"
    if digest(enc(c))!=p["sha256"]: return "CHECKPOINT_DIGEST_HOLD"
    return "OK"

def main():
    a=json.loads((ROOT/"anchor.json").read_text())
    run=json.loads((ROOT/"run.json").read_text())
    artifact=json.loads((ROOT/"artifact.json").read_text())
    require(a["schema"]=="janus.epistemic.r1_4a.anchor.v1","ANCHOR_SCHEMA")
    require(int(os.environ["GITHUB_RUN_ID"])!=a["source"]["run_id"],"SAME_RUN")
    require(check_meta(a,run,artifact)=="OK","METADATA_HOLD")
    z=ROOT/"checkpoint.zip"
    require(z.stat().st_size==a["artifact"]["size"] and digest(z.read_bytes())==a["artifact"]["sha256"],"ZIP_DIGEST_HOLD")
    with zipfile.ZipFile(z) as f:
        require(f.namelist()==["checkpoint.json"],"ZIP_SCHEMA_HOLD")
        require(f.getinfo("checkpoint.json").file_size==a["checkpoint"]["bytes"]<=32768,"SIZE_HOLD")
        raw=f.read("checkpoint.json")
    require(digest(raw)==a["checkpoint"]["sha256"],"RAW_DIGEST_HOLD")
    c=json.loads(raw)
    require(enc(c)==raw and check_checkpoint(c,a)=="OK","CHECKPOINT_HOLD")
    require(c["production"] is False and c["knowledge_write"] is False and c["test_clock"]==NOW,"SCOPE_HOLD")
    require(c["snapshot_sha256"]==a["checkpoint"]["snapshot_sha256"]==digest(enc(c["snapshot"])),"SNAPSHOT_HOLD")
    require([x["revision"] for x in c["registries"]]==[1,2],"REGISTRY_ORDER_HOLD")
    require([digest(enc(x["body"])) for x in c["registries"]]==a["checkpoint"]["registry_hashes"]==[x["sha256"] for x in c["registries"]],"REGISTRY_HASH_HOLD")
    r1,r2=[x["body"] for x in c["registries"]]
    require(len(r1["keys"])==1 and len(r2["keys"])==2,"REGISTRY_SHAPE_HOLD")
    old,new=r2["keys"]
    require(old["key_id"]==r1["keys"][0]["key_id"] and old["revoked_at"]==NOW+10 and new["revoked_at"] is None,"ROTATION_HOLD")
    checks={}
    def test(name,observed,expected):
        checks[name]={"observed":observed,"expected":expected,"pass":observed==expected}
    test("missing_anchor",check_checkpoint(c,None),"ANCHOR_MISSING")
    wrong=copy.deepcopy(run);wrong["run_attempt"]+=1
    test("wrong_run_attempt",check_meta(a,wrong,artifact),"RUN_IDENTITY_HOLD")
    wrong=copy.deepcopy(artifact);wrong["id"]+=1
    test("wrong_artifact",check_meta(a,run,wrong),"ARTIFACT_IDENTITY_HOLD")
    for name,key,value,want in [
        ("older_version","version",0,"VERSION_HOLD"),
        ("wrong_parent","parent_sha256","f"*64,"PARENT_HOLD"),
        ("registry_rollback","active_registry_revision",0,"REGISTRY_REVISION_HOLD"),
        ("same_version_tamper","snapshot_sha256","f"*64,"CHECKPOINT_DIGEST_HOLD")]:
        wrong=copy.deepcopy(c);wrong[key]=value
        test(name,check_checkpoint(wrong,a),want)
    with tempfile.TemporaryDirectory() as d:
        root=Path(d);pubs={}
        require(set(c["public_keys"])=={old["key_id"],new["key_id"]},"KEY_SET_HOLD")
        for k,pem in c["public_keys"].items():
            require(len(pem)<1024 and pem.startswith("-----BEGIN PUBLIC KEY-----") and "PRIVATE KEY" not in pem,"PUBLIC_KEY_HOLD")
            path=root/(k+".pub");path.write_text(pem)
            require(key_fingerprint(path)==k,"KEY_PIN_HOLD");pubs[k]=path
        db=open_store(root/"fresh.sqlite")
        require(snapshot(db)=={"version":0,"receipts":[]},"NOT_FRESH")
        s,receipt=stage(db,c["accepted_envelope"],"2 = 2",r1,c["registries"][0]["sha256"],pubs,NOW,token(db))
        test("historical_receipt",s,"ACCEPTED_STAGED")
        test("restored_snapshot",snapshot(db)==c["snapshot"],True)
        require(all(x["pass"] for x in checks.values()),"RESTORE_HOLD")
        initial=token(db)
        def submit(name,env,claim,expected,want):
            before=token(db)
            status,rec=stage(db,env,claim,r2,c["registries"][1]["sha256"],pubs,NOW+20,expected)
            test(name,status,want)
            if want!="ACCEPTED_STAGED": test(name+"_unchanged",token(db)==before,True)
            return rec
        submit("revoked_key",c["accepted_envelope"],"2 = 2",initial,"KEY_REVOKED")
        submit("rotated_key_replay",c["fixtures"]["rotated_replay"],"2 = 2",initial,"REPLAY")
        broken=copy.deepcopy(c["fixtures"]["symbolic"]);broken["sha256"]="0"*64
        submit("altered_document",broken,"P = NP",initial,"DIGEST_INVALID")
        submit("stale_cas",c["fixtures"]["symbolic"],"P = NP",(0,initial[1]),"STATE_CAS_HOLD")
        symbolic=submit("new_symbolic",c["fixtures"]["symbolic"],"P = NP",initial,"ACCEPTED_STAGED")
        test("symbolic_truth",symbolic["truth_status"] if symbolic else None,"UNRESOLVED")
        false=submit("new_false",c["fixtures"]["false"],"2 = 3",token(db),"ACCEPTED_STAGED")
        test("false_truth",false["truth_status"] if false else None,"FALSE")
        final=snapshot(db);db.close()
    test("version_advance",final["version"],3)
    test("receipt_count",len(final["receipts"]),3)
    receipts=[json.loads(x[2]) for x in final["receipts"]]
    test("no_knowledge_admission",all(x["knowledge_admitted"] is False for x in receipts),True)
    successor={"schema":"janus.epistemic.r1_4a.successor.v1","source":{"run_id":int(os.environ["GITHUB_RUN_ID"]),"attempt":int(os.environ["GITHUB_RUN_ATTEMPT"]),"head_sha":os.environ["GITHUB_SHA"]},"parent_sha256":a["checkpoint"]["sha256"],"version":final["version"],"active_registry_revision":2,"registry_sha256":c["registries"][1]["sha256"],"snapshot":final,"snapshot_sha256":digest(enc(final)),"production":False,"knowledge_write":False}
    export={"schema":"janus.cortex.staging.preview.v1","parent_sha256":successor["parent_sha256"],"successor_sha256":digest(enc(successor)),"records":receipts,"active_cortex_write":False}
    result={"schema":"janus.epistemic.r1_4a.run_b.v1","status":"ENGINEERING_PASS" if all(x["pass"] for x in checks.values()) else "ENGINEERING_FAIL","source":successor["source"],"parent_run":a["source"]["run_id"],"artifact_id":a["artifact"]["id"],"checkpoint_sha256":a["checkpoint"]["sha256"],"successor_sha256":digest(enc(successor)),"version":final["version"],"registry_revision":2,"checks":checks,"passed":sum(x["pass"] for x in checks.values()),"total":len(checks),"active_cortex_write":False,"production":False}
    out=ROOT/"output";out.mkdir()
    for name,value in [("successor",successor),("cortex-staging",export),("result",result)]:
        (out/(name+".json")).write_bytes(enc(value))
    print(json.dumps(result,sort_keys=True))
    require(result["status"]=="ENGINEERING_PASS","CONTROLS_HOLD")
if __name__=="__main__":
    main()
