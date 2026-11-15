#!/usr/bin/env python3
"""Read-only cross-repository ESSENCE ancestry witness.

Validates GitHub-committed neural weights and baseline microcore catalogs in a
separate repository. It is NOT independent external-lab validation or proof
of forward gain, production promotion, or an executed service rollback.
"""
from __future__ import annotations
import argparse,base64,hashlib,json,os,re,urllib.request,urllib.error
from pathlib import Path
from urllib.parse import quote

SCHEMA="janus.essence.crossrepo_ancestry_witness/1.0"
DEMI="Hawkar-usls/Janus-Demiurge"
GEN="Hawkar-usls/Janus_Genesis"
META="Hawkar-usls/janus-meta-registry"
CP="sentinel/model/checkpoint.json"
PENDING="sentinel/model/pending-challenge.json"
MANIFEST=".janus/essence/manifest.json"
CANDIDATE=re.compile(r"^sentinel/model/candidates/[1-9][0-9]{0,19}\.json$")
HEX64=re.compile(r"^[0-9a-f]{64}$")

def require(test,code):
    if not test:raise ValueError(code)

def canonical(data):
    return json.dumps(data,sort_keys=True,ensure_ascii=False,
                      separators=(",",":"),allow_nan=False).encode()

def digest(data):
    return hashlib.sha256(canonical(data)).hexdigest()

def check_checkpoint(item):
    require(type(item) is dict and
            item.get("schema")=="janus.sentinel.transformer_checkpoint/1.0"
            and item.get("production_authority") is False
            and item.get("dispatch_authority") is False
            and item.get("model_type")=="CAUSAL_ATTENTION_SHARED_A_B"
            and type(item.get("weights")) is dict
            and 0<len(item["weights"])<=200
            and type(item.get("checkpoint_sha256")) is str
            and HEX64.fullmatch(item["checkpoint_sha256"])
            and digest({k:v for k,v in item.items()
                        if k!="checkpoint_sha256"})==item["checkpoint_sha256"],
            "INVALID_CHECKPOINT_OR_WEIGHTS_DIGEST")
    return item["checkpoint_sha256"]

def check_pending(obj):
    require(type(obj) is dict and
            obj.get("schema")=="janus.sentinel.precommitted_weight_challenge/1.0"
            and obj.get("production_authority") is False
            and obj.get("research_only") is True
            and CANDIDATE.fullmatch(obj.get("candidate_file",""))
            and str(obj.get("source_run_id"))==obj["candidate_file"].split("/")[-1][:-5]
            and HEX64.fullmatch(obj.get("candidate_checkpoint_sha256",""))
            and HEX64.fullmatch(obj.get("parent_checkpoint_sha256",""))
            and HEX64.fullmatch(obj.get("receipt_sha256",""))
            and digest({k:v for k,v in obj.items()
                        if k!="receipt_sha256"})==obj["receipt_sha256"],
            "INVALID_PRECOMMIT_LINEAGE")
    return obj

def check_manifest(obj,expected_repo):
    require(type(obj) is dict and
            obj.get("schema")=="janus.essence.microkernel/0.1"
            and obj.get("repository")==expected_repo
            and obj.get("enabled") is False
            and obj.get("activation")=="EXPLICIT_READONLY_TEST_ONLY"
            and obj.get("birth_policy")=="PROPOSAL_ONLY"
            and type(obj.get("capabilities")) is dict
            and all(v is False for v in obj["capabilities"].values())
            and 0<len(obj["capabilities"])<=16
            and type(obj.get("microkernels")) is list
            and 1<=len(obj["microkernels"])<=100,
            "FOREIGN_MICROCORE_MANIFEST_INVALID")
    identities=set()
    for x in obj["microkernels"]:
        require(type(x) is dict and type(x.get("id")) is str
                and x["id"] not in identities
                and type(x.get("generation")) is int
                and 0<=x["generation"]<=100
                and type(x.get("gene_sources")) is list
                and 1<=len(x["gene_sources"])<=20,
                "MICROCORE_PROVENANCE_INVALID")
        identities.add(x["id"])
    return {"repo":expected_repo,"manifest_sha256":digest(obj),
            "microcores":len(identities),
            "highest_generation":max(x["generation"] for x in obj["microkernels"])}

def validate(parent,pending,child,manifests):
    parent_sha=check_checkpoint(parent)
    check_pending(pending)
    child_sha=check_checkpoint(child)
    require(child.get("parent_checkpoint_sha256")==parent_sha
            and pending["parent_checkpoint_sha256"]==parent_sha
            and pending["candidate_checkpoint_sha256"]==child_sha
            and child_sha!=parent_sha
            and child.get("prospective_after_parent") is True
            and child.get("replaces_previous") is False
            and child.get("external_independent_validation") is False,
            "NEURAL_PARENT_CHILD_CHAIN_INVALID")
    cores=[check_manifest(manifests[r],r) for r in (DEMI,GEN,META)]
    return {
        "neural_lineage":"PASS_PARENT_CHILD_WEIGHTS_INTEGRITY_ONLY",
        "candidate_weights_sha256":child_sha,
        "parent_weights_sha256":parent_sha,
        "parent_snapshot_available_for_rollback":True,
        "rollback_actually_executed":False,
        "microcore_lineage":"PASS_BASELINE_MANIFEST_INTEGRITY_NOT_CHILD_PROOF",
        "microcores":cores,
        "verified_new_microcore_generation":False,
        "prospective_neural_gain_verified":False,
        "independent_external_quality_verified":False,
        "service_update_authorized":False,
        "automatic_production_promotion":False,
        "github_wide_outage_survivable":False,
    }

def fetch_json(repo,path,ref,token,opener=urllib.request.urlopen):
    require(repo in (DEMI,GEN,META) and
            ((repo==DEMI and ref=="sentinel-state" and path in (CP,PENDING))
             or (repo==DEMI and ref=="sentinel-state"
                 and CANDIDATE.fullmatch(path))
             or (ref=="main" and path==MANIFEST)),
            "UNAPPROVED_REMOTE_SOURCE")
    require(type(token) is str and 16<len(token)<4096,"TOKEN_REQUIRED")
    url=("https://api.github.com/repos/"+repo+"/contents/"+
         quote(path,safe="/")+"?ref="+ref)
    req=urllib.request.Request(url,headers={
          "Authorization":"Bearer "+token,
          "Accept":"application/vnd.github+json",
          "User-Agent":"JANUS-Ancestry-Witness/1.0"})
    with opener(req,timeout=15) as response:
        require(response.status==200,"GITHUB_SOURCE_NOT_HTTP_200")
        data=response.read(500001)
    require(len(data)<=500000,"GITHUB_SOURCE_TOO_LARGE")
    body=json.loads(data)
    require(type(body) is dict and body.get("type")=="file"
            and body.get("encoding")=="base64"
            and type(body.get("content")) is str,
            "GITHUB_CONTENT_NOT_FILE")
    raw=base64.b64decode(body["content"],validate=False)
    require(1<len(raw)<250000,"UNBOUNDED_GITHUB_JSON")
    return json.loads(raw,parse_constant=lambda _:
        (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))

def run(token,fetch=fetch_json):
    try:
        parent=fetch(DEMI,CP,"sentinel-state",token)
        pending=fetch(DEMI,PENDING,"sentinel-state",token)
        child=fetch(DEMI,pending["candidate_file"],"sentinel-state",token)
        manifests={repo:fetch(repo,MANIFEST,"main",token)
                   for repo in (DEMI,GEN,META)}
        verdict=validate(parent,pending,child,manifests)
        status="PASS_LINEAGE_INTEGRITY_WITH_PROSPECTIVE_AND_ROLLBACK_HOLD"
    except (ValueError,KeyError,TypeError,urllib.error.URLError,TimeoutError,
            OSError,json.JSONDecodeError,UnicodeError) as err:
        status="HOLD_SOURCE_UNAVAILABLE_OR_LINEAGE_INVALID"
        verdict={"error_type":type(err).__name__,
                 "production_authority":False,"verified_gain":False}
    result={"schema":SCHEMA,"status":status,"witness_repository":META,
            "data_only":True,"production_authority":False,
            "externally_independent_organization":False,"verdict":verdict}
    return dict(result,receipt_sha256=digest(result))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    item=run(os.environ.get("GH_READ_TOKEN",""))
    target=Path(a.out)
    require(not target.exists() and not target.is_symlink(),
            "NO_OVERWRITE_WITNESS")
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(item,indent=2,sort_keys=True)+"\n")
    print(item["status"],item["receipt_sha256"])
    out=os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        with open(out,"a") as f:
            f.write("### JANUS external-repository (NOT external-lab) ancestry witness\n")
            f.write("Status: "+item["status"]+"\n")
            f.write("No new weights promoted, no actual rollback, no proven external gain.\n")
if __name__=="__main__":
    main()
