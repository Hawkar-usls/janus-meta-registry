#!/usr/bin/env python3
"""Fail-closed JANUS public owner inventory + Contour contract auditor.

No private GitHub API access. Public owner discovery is not proof of runtime integration.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

MANIFEST=Path("agent-observatory/JANUS_CONTOUR_MANIFEST.json")
OWNER="Hawkar-usls"
ROLES={"CORE","ORGAN","SATELLITE","EXTERNAL"}
STATES={"SOURCE_BOUND_WITNESS_CONFIRMED","INTEGRATION_SURFACES_PRESENT","METADATA_ONLY","NOT_ASSESSED"}
class Hold(ValueError): pass

def require(ok,why):
    if not ok: raise Hold(why)

def verify(m, live_public=None):
    require(m.get("schema")=="janus.agent.observatory.contour-manifest.v2","WRONG_SCHEMA")
    inventory=m.get("repository_inventory")
    require(isinstance(inventory,list) and inventory,"MISSING_INVENTORY")
    names=[x.get("repo") for x in inventory]
    require(all(isinstance(n,str) and re.fullmatch(r"Hawkar-usls/[A-Za-z0-9_.-]+",n) for n in names),"BAD_REPO_ID")
    require(len(names)==len(set(names)),"DUPLICATE_INVENTORY")
    require(all(x.get("role") in ROLES and x.get("integration_state") in STATES and x.get("visibility")=="public" for x in inventory),"BAD_CLASSIFICATION")
    require(all(x.get("discovery_scope")==("NOT_IN_JANUS_CONTOUR" if x["role"]=="EXTERNAL" else "JANUS_CONTOUR_ELIGIBLE") for x in inventory),"EXTERNAL_ENROLLED")
    contour=m.get("repositories")
    eligible=[x["repo"] for x in inventory if x["role"]!="EXTERNAL"]
    require(isinstance(contour,list) and all(isinstance(x,dict) and x.get("class") for x in contour),"MISSING_CONTOUR")
    contour_names=[x["repo"] for x in contour]
    require(len(contour_names)==len(set(contour_names)),"DUPLICATE_CONTOUR")
    require(set(contour_names)==set(eligible),"ELIGIBLE_CONTOUR_MISMATCH")
    exclusions=m.get("private_or_nonpublic_exclusions")
    require(isinstance(exclusions,list) and len(exclusions)==len(set(exclusions))==3,"PRIVATE_EXCLUSIONS_DRIFT")
    require(not set(exclusions)&set(names),"PRIVATE_EXPOSED_IN_PUBLIC_INVENTORY")
    policy=m.get("inventory_policy",{})
    require(policy.get("owner")==OWNER and policy.get("private_names_must_not_enter_inventory") is True and policy.get("classification_does_not_grant_authority") is True,"POLICY_AUTHORITY_LEAK")
    require(policy.get("owner_repository_count")==len(names)+len(exclusions) and policy.get("public_repository_count")==len(names) and policy.get("private_repository_count")==len(exclusions),"TOTAL_COUNTS_DRIFT")
    require(policy.get("public_contour_count")==len(contour) and policy.get("public_external_count")==len(names)-len(contour),"CLASS_COUNTS_DRIFT")
    require(sum(x["integration_state"]=="SOURCE_BOUND_WITNESS_CONFIRMED" for x in inventory)==1,"OVERCLAIMED_WITNESSES")
    if live_public is not None:
        expected=set(names)
        current=set("Hawkar-usls/"+n for n in live_public)
        require(len(current)==len(live_public),"LIVE_OWNER_DUPLICATE")
        require(expected==current,"LIVE_PUBLIC_REPO_DRIFT missing="+",".join(sorted(current-expected))+" removed="+",".join(sorted(expected-current)))
    return {"schema":"janus.contour.inventory_audit.v1","status":"PASS" if live_public is not None else "PASS_SNAPSHOT_ONLY",
            "public_count":len(names),"private_exclusions_snapshot_count":len(exclusions),
            "contour_count":len(contour),"external_count":len(names)-len(contour),
            "live_public_reconciled":live_public is not None,
            "private_visibility_reverified_live":False,
            "authority":"DISCOVERY_ONLY_NOT_RUNTIME_INTEGRATION"}

def public_owner_repos():
    result=[]
    token=os.environ.get("GITHUB_TOKEN","")
    for page in range(1,15):
        url="https://api.github.com/users/"+OWNER+"/repos?per_page=100&type=owner&page="+str(page)
        headers={"Accept":"application/vnd.github+json","User-Agent":"JANUS-Contour-Inventory-Audit/2"}
        if token: headers["Authorization"]="Bearer "+token
        with urlopen(Request(url,headers=headers),timeout=30) as response:
            chunk=response.read(2_000_000)
        obj=json.loads(chunk)
        require(isinstance(obj,list),"LIVE_OWNER_API_INVALID")
        for item in obj:
            require(item.get("owner",{}).get("login","").lower()==OWNER.lower() and
                    item.get("private") is False,"LIVE_OWNER_NOT_PUBLIC")
            result.append(item["name"])
        if len(obj)<100: break
    else: raise Hold("PAGINATION_UNBOUNDED")
    return result

def self_test():
    m=json.loads(MANIFEST.read_text(encoding="utf-8"))
    live=[r["repo"].split("/",1)[1] for r in m["repository_inventory"]]
    assert verify(m,live)["status"]=="PASS"
    bad=json.loads(json.dumps(m));bad["repository_inventory"][0]["visibility"]="private"
    try:verify(bad,live);raise AssertionError("FAIL_OPEN_VISIBILITY")
    except Hold:pass
    bad=json.loads(json.dumps(m));bad["repository_inventory"][0]["role"]="EXTERNAL"
    try:verify(bad,live);raise AssertionError("FAIL_OPEN_CONTOUR")
    except Hold:pass
    bad=json.loads(json.dumps(m));bad["repositories"].append({"repo":"Hawkar-usls/not-owned","class":"CORE"})
    try:verify(bad,live);raise AssertionError("FAIL_OPEN_PHANTOM")
    except Hold:pass
    try:verify(m,live+["untracked-public"]);raise AssertionError("FAIL_OPEN_NEW_PUBLIC")
    except Hold:pass
    print("CONTOUR_ADVERSARIAL_TESTS=PASS")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--live",action="store_true")
    p.add_argument("--self-test",action="store_true")
    args=p.parse_args()
    try:
        if args.self_test:self_test()
        m=json.loads(MANIFEST.read_text(encoding="utf-8"))
        print(json.dumps(verify(m,public_owner_repos() if args.live else None),ensure_ascii=False,sort_keys=True))
    except (Hold,ValueError,OSError) as e:
        print("CONTOUR_INVENTORY=HOLD "+str(e),file=sys.stderr)
        raise SystemExit(2)
if __name__=="__main__":
    main()
