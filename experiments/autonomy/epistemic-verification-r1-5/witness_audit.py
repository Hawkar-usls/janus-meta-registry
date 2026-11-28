"""R1.5B1: separately triggered read-only audit of the exact v6 checkpoint."""
import copy
import json
import os
import runpy
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
C=runpy.run_path(str(HERE/"continuity.py"))
enc,digest,load_zip,reconstruct,snapshot=(C[k] for k in ("enc","digest","load_zip","reconstruct","snapshot"))
ROOT=Path(os.environ["RUNNER_TEMP"])/"r1-5b"
def need(x,reason):
    if not x: raise RuntimeError(reason)
def main():
    spec=json.loads((HERE/"r1-5b-precommit.json").read_text())
    p=spec["parent"]
    run=json.loads((ROOT/"run.json").read_text())
    art=json.loads((ROOT/"artifact.json").read_text())
    need(int(os.environ["GITHUB_RUN_ID"])!=p["run"],"SAME_RUN")
    need((run["id"],run["run_attempt"],run["head_sha"],run["conclusion"])==(p["run"],p["attempt"],p["head"],"success"),"RUN_BINDING")
    need(art["id"]==p["artifact"] and art["workflow_run"]["id"]==p["run"] and art["workflow_run"]["head_sha"]==p["head"] and art["digest"]=="sha256:"+p["zip_sha256"] and not art["expired"],"ARTIFACT_BINDING")
    members=load_zip(ROOT/"checkpoint.zip",p["zip_sha256"],["checkpoint.json","result.json","cortex-staging.json"])
    cp=members["checkpoint.json"];result=members["result.json"];export=members["cortex-staging.json"]
    def anchored(c):
        return c.get("version")==p["version"] and c.get("parent_sha256")==p["parent_sha256"] and digest(enc(c))==p["checkpoint_sha256"]
    need(anchored(cp),"CHECKPOINT_ANCHOR")
    need(cp["source"]==result["source"] and cp["source"]["run_id"]==p["run"] and cp["source"]["attempt"]==p["attempt"] and cp["source"]["head_sha"]==p["head"] and cp["source"]["job"]=="cycle3","SOURCE_BINDING")
    need(result["status"]=="ENGINEERING_PASS" and result["checkpoint_sha256"]==p["checkpoint_sha256"] and all(result["checks"].values()),"PARENT_REPORT")
    need(len(cp["history"])==6 and len(cp["pending"])==0 and cp["active_registry_revision"]==3,"HISTORY_BOUND")
    with tempfile.TemporaryDirectory() as d:
        db,_=reconstruct(cp,Path(d)); snap=snapshot(db);db.close()
    records=[json.loads(x[2]) for x in snap["receipts"]]
    need(snap==cp["snapshot"] and len(records)==6 and all(r["knowledge_admitted"] is False for r in records),"RECONSTRUCT")
    need(export["records"]==records and export["checkpoint_sha256"]==p["checkpoint_sha256"] and export["active_cortex_write"] is False,"STAGING")
    old=copy.deepcopy(cp);old["version"]=5
    altered=copy.deepcopy(cp);altered["snapshot"]["receipts"][0][2]="tampered"
    need(not anchored(old) and not anchored(altered),"NEGATIVE_CONTROL")
    report={"schema":"janus.epistemic.r1_5b.audit.v1","status":"ENGINEERING_PASS","run_id":int(os.environ["GITHUB_RUN_ID"]),"parent_run":p["run"],"artifact_id":p["artifact"],"zip_sha256":p["zip_sha256"],"checkpoint_sha256":p["checkpoint_sha256"],"version":6,"receipts":len(records),"checks":{"separate_run":True,"metadata_bound":True,"zip_bytes_verified":True,"checkpoint_hash_verified":True,"historical_signatures_reverified":True,"snapshot_reconstructed":True,"staging_export_matches":True,"older_version_rejected":True,"altered_snapshot_rejected":True,"no_knowledge_admission":True},"independent_trust_domain":False,"active_cortex_write":False,"production":False}
    print(json.dumps(report,sort_keys=True))
if __name__=="__main__":main()
