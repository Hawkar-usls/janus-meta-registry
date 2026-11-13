#!/usr/bin/env python3
"""ESSENCE v1.4 Github-only fleet readiness audit; no production model changes.

Audits the live default branch of all repos in a frozen owner's repository
inventory. Downloads only public source/data from immutable Git commit refs;
NEVER executes downloaded repo code. Runs this repository's already-reviewed,
Git-blob-pinned ESSENCE v0.1 kernel on each repo's manifest+fixture. Checks
forgery and privilege-denial controls, recent native v1.3 CI run states and
presence of more advanced research-only gates.

An audit passing is NOT automatic learning or permission to change weights.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/".janus"/"essence"))
import kernel

SCHEMA="janus.essence.fleet_readiness_audit/1.4"
OWNER="Hawkar-usls"
BASE_KERNEL_BLOB="de5199978fbafcbda836b77da370943f7ea2514e"
MODULE_V13_BLOB="1c48b223c8ef64a78506a39b147f881b00022e77"
PEER_V13_BLOB="6a08b366fe1556186a9681e51102d51e241e981d"
SKETCH_LIMIT=50_000
DENIED={"network","shell","repo_write","workflow_dispatch","secrets","hardware"}
ROLES={"sensing","memory","planning","verification","recovery","coding"}
KNOWN_NAMES=tuple(sorted((
 "Hrain","aura-oracle-tg","Simptomat","iNaiHR","BFain","-Terminal-for-Janus",
 "Janus-Cosmos","SLOT","SSlot","DIVINE_REALM","Janus",
 "Janus_Genesis","RadioPlayerV3","player","janus-meta-registry","clawdbot",
 "M5Unit-ENV","AI-Cardputer-adv-A-Portable-AI-Assistant","arduino-ide",
 "Cardputer-Game-Station-Emulators","Arduino-AI-Chat-Library","emoji",
 "Janus-Demiurge","xiaozhi-esp32","ATOM-ELITE-1989---M5stack-ATOMS3R-2026-",
 "vcmi","ATOM-RPG","janus-first-followers-club-",
 "janus-distributed-ai-swarm","janus-io-public","tranception",
 "janus-lapis","ESP32-TWAI-CAN","Janus-Fundamentum","AIFC",
 "Hawkar-usls","Fast-CAT-SHAiTan","SCOBY-D0","lineara.xyz",
 "Linear-A-decipherment-programme","Demi_Head","The-Voice-of-Janus",
 "Echo-Pyramid","TOPA","Janus-HELIOS","JANUS-MACHINE-MARKET",
 "HotdRemake_ArcadePlugin","neuromorphic-vision-sensor"
)))
assert len(KNOWN_NAMES)==48 and len(set(KNOWN_NAMES))==48

def canonical(obj):
    return json.dumps(obj,sort_keys=True,ensure_ascii=False,
                      separators=(",",":"),allow_nan=False).encode("utf-8")

def digest(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()

def git_blob(raw):
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def json_strict(raw):
    return json.loads(raw.decode("utf-8"),
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))

def http(url,*,api=False,max_bytes=SKETCH_LIMIT):
    if not url.startswith(("https://api.github.com/","https://raw.githubusercontent.com/")):
        raise ValueError("FOREIGN_HTTP_HOST_DENIED")
    headers={"User-Agent":"janus-essence-v14-github-only-fleet-auditor",
             "Accept":"application/vnd.github+json" if api else "application/octet-stream"}
    if api and os.environ.get("GH_TOKEN"):
        headers["Authorization"]="Bearer "+os.environ["GH_TOKEN"]
        headers["X-GitHub-Api-Version"]="2022-11-28"
    request=Request(url,headers=headers)
    try:
        with urlopen(request,timeout=17) as reply:
            payload=reply.read(max_bytes+1)
    except HTTPError as ex:
        if ex.code==404:
            return None
        raise RuntimeError("GITHUB_HTTP_"+str(ex.code)) from None
    except (URLError,TimeoutError) as ex:
        raise RuntimeError("GITHUB_NETWORK_UNAVAILABLE") from ex
    if len(payload)>max_bytes:
        raise ValueError("GITHUB_RESULT_TOO_LARGE")
    return payload

def api(path,max_bytes=250000):
    raw=http("https://api.github.com"+path,api=True,max_bytes=max_bytes)
    return None if raw is None else json_strict(raw)

def github_raw(repo,sha,path):
    if not repo.startswith(OWNER+"/") or not re.fullmatch(r"[a-f0-9]{40}",sha):
        raise ValueError("UNTRUSTED_SOURCE_LOCATOR")
    url=("https://raw.githubusercontent.com/"+repo+"/"+sha+
         "/"+"/".join(quote(p,safe="") for p in path.split("/")))
    return http(url)

def live_inventory():
    data=api("/users/"+OWNER+"/repos?per_page=100&page=1&type=owner",
             max_bytes=1_700_000)
    if not isinstance(data,list):
        raise RuntimeError("PUBLIC_REPOSITORY_LIST_UNAVAILABLE")
    if len(data)>=100:
        raise RuntimeError("REPO_INVENTORY_PAGINATION_REQUIRED")
    values={item["name"]:item for item in data if item.get("owner",{}).get("login")==OWNER}
    return values

def latest_workflow(repo,workflow):
    name=quote(workflow,safe="")
    try:
        runs=api("/repos/"+repo+"/actions/workflows/"+name+
                 "/runs?branch=main&per_page=2",max_bytes=85000)
        entries=runs.get("workflow_runs",[]) if isinstance(runs,dict) else []
        if not entries:
            return "NOT_OBSERVED"
        entry=next((run for run in entries if run.get("status")=="completed"),entries[0])
        status=entry.get("status")
        if status!="completed":return "PENDING"
        return "PASS" if entry.get("conclusion")=="success" else "FAIL_OR_CANCELLED"
    except Exception:
        return "UNVERIFIED"

def audit_one(name,item):
    repo=OWNER+"/"+name
    info={"repository":repo,"default_branch":item.get("default_branch"),
          "audited_commit":None,"baseline_contract":"UNVERIFIED",
          "baseline_kernel_blob":"UNVERIFIED",
          "microkernels":0,"replay_integrity":False,
          "security_mutations_held":False,
          "module_v13":"NOT_INSTALLED",
          "module_v13_ci":"NOT_OBSERVED",
          "peer_v13":"NOT_INSTALLED",
          "peer_v13_ci":"NOT_OBSERVED",
          "real_algorithm_v12":"NOT_INSTALLED",
          "signed_model_gate_v10":"NOT_INSTALLED",
          "trained_checkpoint_verified":False,
          "external_blind_model_gain_verified":False,
          "live_rollback_verified":False,
          "self_learning_prod_authorized":False,
          "inspection_errors":[]}
    try:
        branch=item.get("default_branch")
        if not isinstance(branch,str) or len(branch)>100:
            raise ValueError("UNTRUSTED_DEFAULT_BRANCH")
        head=api("/repos/"+repo+"/git/ref/heads/"+quote(branch,safe=""),max_bytes=15000)
        sha=head["object"]["sha"]
        if not re.fullmatch(r"[a-f0-9]{40}",sha):
            raise ValueError("UNTRUSTED_GITHUB_HEAD")
        info["audited_commit"]=sha
    except Exception as ex:
        info["inspection_errors"].append("HEAD_"+str(ex)[:90])
        return info
    def retrieve(path):
        try:return github_raw(repo,sha,path)
        except Exception as ex:
            info["inspection_errors"].append("FETCH_"+path.split("/")[-1]+"_"+str(ex)[:75])
            return None
    manifest_raw=retrieve(".janus/essence/manifest.json")
    fixture_raw=retrieve(".janus/essence/fixture.json")
    info["fixture_origin"]="REPOSITORY_LOCAL"
    if fixture_raw is None:
        # Explicit, public, pinned central fallback to test contract without
        # falsely claiming the target repo is self-contained.
        trusted=(ROOT/".janus"/"essence"/"fixture.json").read_bytes()
        if git_blob(trusted)!="a4bd3a81efb453219ea5bc2e08227191e84d90b0":
            raise ValueError("CENTRAL_FALLBACK_FIXTURE_CHANGED")
        fixture_raw=trusted
        info["fixture_origin"]="PUBLIC_META_REGISTRY_FALLBACK_NOT_REPO_LOCAL"
    kernel_raw=retrieve(".janus/essence/kernel.py")
    if kernel_raw is not None:
        info["baseline_kernel_blob"]=git_blob(kernel_raw)
    if (kernel_raw is not None and git_blob(kernel_raw)==BASE_KERNEL_BLOB
            and manifest_raw is not None and fixture_raw is not None):
        try:
            manifest=json_strict(manifest_raw)
            fixture=json_strict(fixture_raw)
            cells=kernel.validate_manifest(manifest,expected_repo=repo)
            report=kernel.evaluate(manifest,fixture,explicit_readonly=True,
                                   propose_child="coding",expected_repo=repo)
            if not kernel.verify_report(report):
                raise ValueError("REPORT_REPLAY_FALSE")
            info["microkernels"]=len(cells)
            info["baseline_contract"]="PASS_REPLAY_SYNTHETIC"
            info["replay_integrity"]=True
            # Verify legacy shell/repo-write escalation and forged-receipt holds
            m=copy.deepcopy(manifest)
            m["capabilities"]["repo_write"]=True
            try:kernel.validate_manifest(m,expected_repo=repo)
            except (ValueError,PermissionError):rights_denied=True
            else:rights_denied=False
            t=copy.deepcopy(report)
            t["receipts"][0]["result"]={"forged":"true"}
            try:kernel.verify_report(t)
            except (ValueError,PermissionError):replay_denied=True
            else:replay_denied=False
            cross=False
            try:kernel.validate_manifest(manifest,expected_repo=OWNER+"/__WRONG__")
            except (ValueError,PermissionError):cross=True
            info["security_mutations_held"]=rights_denied and replay_denied and cross
            if not info["security_mutations_held"]:
                info["inspection_errors"].append("SAFETY_NEGATIVE_CONTROL_FAILED")
        except Exception as ex:
            info["baseline_contract"]="FAILED"
            info["inspection_errors"].append("BASELINE_"+str(ex)[:150])
    elif manifest_raw is None or fixture_raw is None or kernel_raw is None:
        info["baseline_contract"]="MISSING_FILE"
    else:
        info["baseline_contract"]="KERNEL_SOURCE_MISMATCH_HOLD"
    module_raw=retrieve(".janus/essence/module_governor_v13.py")
    if module_raw is not None:
        info["module_v13"]="SOURCE_PINNED" if git_blob(module_raw)==MODULE_V13_BLOB else "SOURCE_DIFFERENT"
        if info["module_v13"]=="SOURCE_PINNED":
            info["module_v13_ci"]=latest_workflow(repo,"essence-module-organogenesis-v13.yml")
    peer_raw=retrieve(".janus/essence/peer_inbox_v13.py")
    if peer_raw is not None:
        info["peer_v13"]="SOURCE_PINNED" if git_blob(peer_raw)==PEER_V13_BLOB else "SOURCE_DIFFERENT"
        if info["peer_v13"]=="SOURCE_PINNED":
            info["peer_v13_ci"]=latest_workflow(repo,"essence-peer-inbox-v13.yml")
    real_raw=retrieve(".janus/essence/real_algorithm_gate_v12.py")
    if real_raw is not None:
        info["real_algorithm_v12"]="CODE_PRESENT_NOT_EXTERNAL_BLIND_PROOF"
    admission_raw=retrieve("tools/essence_model_admission_v10.py")
    if admission_raw is not None:
        info["signed_model_gate_v10"]="CODE_PRESENT_NOT_SIGNED_APPROVAL"
    return info

def validate_internal_test():
    base={
       "schema":kernel.SCHEMA,"repository":OWNER+"/test-placeholder",
       "enabled":False,"activation":"EXPLICIT_READONLY_TEST_ONLY",
       "capabilities":{x:False for x in DENIED},"birth_policy":"PROPOSAL_ONLY",
       "microkernels":[{"id":f"cell-{i}","role":role,"generation":0,
                        "gene_sources":[]} for i,role in enumerate(sorted(ROLES))]}
    fixture={"kind":"SYNTHETIC_FIXTURE","id":"fleet-v14-negative-test",
             "metrics":{"signal_quality":.7,"memory_pressure":.2}}
    kernel.validate_manifest(base,expected_repo=base["repository"])
    report=kernel.evaluate(base,fixture,explicit_readonly=True,
                           propose_child="coding",expected_repo=base["repository"])
    assert kernel.verify_report(report)
    assert report["status"]=="PASS_WITH_OPERATIONAL_HOLD"
    assert report["action_authority"] is False
    changed=copy.deepcopy(base);changed["capabilities"]["shell"]=True
    try:kernel.validate_manifest(changed,expected_repo=base["repository"])
    except ValueError:pass
    else:raise AssertionError("UNSAFE_RIGHTS_MUTATION_ACCEPTED")
    changed=copy.deepcopy(report);changed["receipts"][0]["previous_sha256"]="f"*64
    try:kernel.verify_report(changed)
    except ValueError:pass
    else:raise AssertionError("BROKEN_RECEIPT_ACCEPTED")
    return True

def run_fleet():
    # The local repo code is canonical and audited, not downloaded and executed.
    local=(ROOT/".janus"/"essence"/"kernel.py").read_bytes()
    if git_blob(local)!=BASE_KERNEL_BLOB:
        raise ValueError("LOCAL_AUDITED_KERNEL_NOT_PINNED")
    validate_internal_test()
    live=live_inventory()
    observed=set(live)
    planned=set(KNOWN_NAMES)
    entries={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(audit_one,name,live[name]):name for name in sorted(observed&planned)}
        for future in concurrent.futures.as_completed(futures):
            name=futures[future]
            try:entries[name]=future.result()
            except Exception as ex:
                entries[name]={"repository":OWNER+"/"+name,
                   "baseline_contract":"UNVERIFIED","inspection_errors":["WORKER_"+str(ex)[:120]]}
    ordered=[entries[x] for x in sorted(entries)]
    count=lambda func:sum(bool(func(x)) for x in ordered)
    stats={
        "github_repo_count_current":len(live),
        "planned_snapshot_count":len(KNOWN_NAMES),
        "audited_repo_count":len(ordered),
        "missing_public_since_snapshot":sorted(planned-observed),
        "new_since_snapshot":sorted(observed-planned),
        "baseline_synthetic_replay_pass":count(lambda x:x.get("baseline_contract")=="PASS_REPLAY_SYNTHETIC"),
        "baseline_provenance_and_mutation_pass":count(lambda x:x.get("security_mutations_held") is True),
        "module_v13_source_pinned":count(lambda x:x.get("module_v13")=="SOURCE_PINNED"),
        "module_v13_latest_ci_success":count(lambda x:x.get("module_v13_ci")=="PASS"),
        "peer_v13_source_pinned":count(lambda x:x.get("peer_v13")=="SOURCE_PINNED"),
        "peer_v13_latest_ci_success":count(lambda x:x.get("peer_v13_ci")=="PASS"),
        "real_algorithm_gate_code_found":count(lambda x:x.get("real_algorithm_v12")=="CODE_PRESENT_NOT_EXTERNAL_BLIND_PROOF"),
        "signed_model_admission_code_found":count(lambda x:x.get("signed_model_gate_v10")=="CODE_PRESENT_NOT_SIGNED_APPROVAL"),
        "genuine_trained_checkpoint_evidence_confirmed":0,
        "genuine_external_blind_model_gain_confirmed":0,
        "live_model_rollback_verified":0,
        "automatic_production_model_changes_authorized":0,
        "source_fetch_or_validation_issue_repos":count(lambda x:bool(x.get("inspection_errors"))),
        "self_contained_fixtures":count(lambda x:x.get("fixture_origin")=="REPOSITORY_LOCAL"),
        "central_fallback_fixtures":count(lambda x:x.get("fixture_origin")=="PUBLIC_META_REGISTRY_FALLBACK_NOT_REPO_LOCAL")
    }
    base_pass=(len(ordered)==len(KNOWN_NAMES)==len(live)
               and stats["baseline_provenance_and_mutation_pass"]==len(ordered))
    status=("PASS_PUBLIC_BASELINES_WITH_FIXTURE_GAPS_MODEL_HOLD" if base_pass
            and stats["central_fallback_fixtures"]>0
            else ("PASS_ALL_PUBLIC_BASELINES_MODEL_HOLD" if base_pass
                  else "PARTIAL_OR_FAILED_BASELINE_FLEET_AUDIT_HOLD"))
    report={
        "schema":SCHEMA,
        "read_only":True,
        "scope":"ALL_48_PUBLIC_GITHUB_OWNER_REPOS_AT_RUN_TIME",
        "other_connected_nonpublic_repositories_audited_here":False,
        "run_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "status":status,
        "canonical_kernel_blob":BASE_KERNEL_BLOB,
        "github_repository_identity":OWNER,
        "remote_source_execution":False,
        "credentials_collected":False,
        "nas_access":False,
        "test_data_kind":"CURRENT_REPO_SYNTHETIC_FIXTURE_AND_STATIC_PROVENANCE",
        "external_independent_blind_test":False,
        "actual_model_training":False,
        "production_model_change":False,
        "statistics":stats,
        "repositories":ordered,
        "model_admission_obstacles":[
          "A_CANDIDATE_MUST_TRAIN_ON_REAL_PINNED_CHECKPOINT_WITH_REPRODUCIBLE_DATA",
          "KEEP_TEST_HOLDOUT_SEPARATE_AND_EXTERNALLY_BLINDED",
          "COMPARE_QUALITY_MEMORY_CPU_COST_AND_REGRESSIONS_ACROSS_NEW_COHORTS",
          "ESTABLISH_TWO_INDEPENDENT_AUTHENTICATED_EVALUATOR_SIGNATURES",
          "TEST_GENUINE_CHECKPOINT_ROLLBACK_AND_LIMITED_CANARY",
          "REVIEW_AND_APPROVE_EACH_PRODUCTION_CHANGE_WITH_HUMAN_AUDIT"
        ]}
    report["receipt_sha256"]=digest(report)
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live",action="store_true")
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--out")
    o=p.parse_args()
    if o.selftest:
        validate_internal_test()
        print("ESSENCE_FLEET_INTERNAL_NEGATIVE_CONTROLS_PASS")
    if not o.live:return
    result=run_fleet()
    if o.out:
        path=Path(o.out)
        if path.exists():raise FileExistsError("NO_AUDIT_RECEIPT_OVERWRITE")
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],**result["statistics"],
                      "receipt_sha256":result["receipt_sha256"]},sort_keys=True))
    # Emit CI failure when a baseline is missing or forgeable: don't hide gaps.
    if result["status"]=="PARTIAL_OR_FAILED_BASELINE_FLEET_AUDIT_HOLD":
        raise SystemExit(2)

if __name__=="__main__":
    main()
