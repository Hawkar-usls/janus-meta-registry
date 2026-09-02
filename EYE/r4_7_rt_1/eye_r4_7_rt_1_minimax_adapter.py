#!/usr/bin/env python3
from __future__ import annotations
import argparse, functools, json, math, os
from pathlib import Path

INF=float("inf")
class ContractError(ValueError): pass

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def index_tests(model):
    causes=[x["id"] if isinstance(x,dict) else str(x) for x in model["cause_classes"]]
    tests={}
    for raw in model["tests"]:
        t=dict(raw); tid=str(t["id"])
        tests[tid]={
            "cost":float(t.get("cost",1)),
            "available":bool(t.get("available",True)),
            "usable":bool(t.get("decision_usable",True)),
            "depends_on":tuple(map(str,t.get("depends_on",[]))),
            "outcomes":{str(k):str(v) for k,v in t.get("outcome_by_cause",{}).items()}
        }
        if tests[tid]["available"] and tests[tid]["usable"] and set(tests[tid]["outcomes"])!=set(causes):
            raise ContractError(f"OUTCOME_MAP_MISMATCH:{tid}")
    return tuple(causes),tests

def partition(rem,tid,tests):
    out={}
    for c in rem:
        out.setdefault(tests[tid]["outcomes"][c],set()).add(c)
    return {o:frozenset(v) for o,v in sorted(out.items())}

def identified(rem):
    return len(rem)<=1

def unlocks(tid,acq,tests):
    return any(tid in t["depends_on"] and j not in acq and t["available"] and t["usable"] for j,t in tests.items())

def solve_minimax(model):
    if model.get("probability_semantics")!="NONE":
        raise ContractError("PROBABILITY_SEMANTICS_MUST_BE_NONE")
    causes,tests=index_tests(model)
    allc=frozenset(causes)
    max_states=int(model.get("requirements",{}).get("max_states",10000))
    counter={"n":0,"limit":False}
    choice={}
    @functools.lru_cache(None)
    def dp(rem_t,acq_t):
        counter["n"]+=1
        if counter["n"]>max_states:
            counter["limit"]=True
            return INF,None
        rem=frozenset(rem_t); acq=frozenset(acq_t)
        if identified(rem):
            return 0.0,{"terminal":True}
        best=(INF,None)
        for tid in sorted(tests):
            t=tests[tid]
            if tid in acq or not t["available"] or not t["usable"] or any(d not in acq for d in t["depends_on"]):
                continue
            parts=partition(rem,tid,tests)
            if len(parts)==1 and not unlocks(tid,acq,tests):
                continue
            nacq=frozenset(set(acq)|{tid})
            child_costs=[]; ok=True
            for sub in parts.values():
                c,_=dp(tuple(sorted(sub)),tuple(sorted(nacq)))
                if not math.isfinite(c):
                    ok=False; break
                child_costs.append(c)
            if not ok:
                continue
            worst=t["cost"]+max(child_costs,default=0.0)
            cand=(round(worst,12),tid)
            incumbent=(best[0],best[1] if best[1] is not None else "\uffff")
            if cand<incumbent:
                best=(cand[0],tid)
        if best[1] is None:
            return INF,None
        choice[(tuple(sorted(rem)),tuple(sorted(acq)))]=best[1]
        return best[0],{"test_id":best[1]}
    worst,root=dp(tuple(sorted(allc)),tuple())
    common={
        "schema":"janus.eye.r4_7_rt_1.minimax_policy_receipt.v1",
        "artifact_id":model.get("id"),
        "source_git_commit":os.getenv("GITHUB_SHA","LOCAL_OR_UNKNOWN"),
        "probability_semantics":"NONE",
        "authority":"EXACT_MINIMAX_POLICY_UNDER_DECLARED_DETERMINISTIC_PARTITIONS_ONLY__NO_PRIOR_OR_LIKELIHOOD_CLAIM"
    }
    if counter["limit"]:
        return {**common,"status":"UNKNOWN_RESOURCE_LIMIT","states_visited":counter["n"],"max_states":max_states}
    if root is None or not math.isfinite(worst):
        return {**common,"status":"NON_IDENTIFIABLE_UNDER_CURRENT_DETERMINISTIC_PARTITION_MODEL","states_visited":counter["n"]}
    node_ids={}; nodes=[]
    def walk(rem,acq):
        key=(tuple(sorted(rem)),tuple(sorted(acq)))
        if key in node_ids: return node_ids[key]
        nid=f"N{len(node_ids):04d}"; node_ids[key]=nid
        if identified(rem):
            nodes.append({"node_id":nid,"terminal":True,"remaining_causes":sorted(rem),"identified_cause_class":next(iter(rem))})
            return nid
        tid=choice[key]; nacq=frozenset(set(acq)|{tid}); branches=[]
        for outcome,sub in partition(rem,tid,tests).items():
            branches.append({"outcome":outcome,"remaining_causes":sorted(sub),"child_node_id":walk(sub,nacq)})
        nodes.append({"node_id":nid,"terminal":False,"remaining_causes":sorted(rem),"acquired_tests":sorted(acq),"next_test":tid,"immediate_unit_cost":tests[tid]["cost"],"branches":branches})
        return nid
    root_id=walk(allc,frozenset())
    return {**common,"status":"EXACT_MINIMAX_POLICY_FOUND","root_node_id":root_id,"root_next_test":root["test_id"],"worst_case_cost_to_identification":worst,"states_visited":counter["n"],"policy_nodes":sorted(nodes,key=lambda x:x["node_id"]),"firewalls":["DETERMINISTIC_PARTITION != EMPIRICAL_LIKELIHOOD","MINIMAX_POLICY != CAUSAL_TRUTH","NO_PRIORS_USED","NO_EXPECTED_INFORMATION_GAIN_CLAIM"]}

def route_outcome(contract,test_id,outcome):
    tests={t["id"]:t for t in contract["tests"]}
    if test_id not in tests:
        return {"status":"OUT_OF_CONTRACT","reason":"UNKNOWN_TEST","test_id":test_id,"outcome":outcome,"authority":"NO_POST_HOC_INTERPRETATION"}
    t=tests[test_id]
    allowed={x["outcome"]:x for x in t.get("outcome_space",[])}
    if outcome not in allowed:
        return {"status":"OUT_OF_CONTRACT","reason":"UNPREREGISTERED_OUTCOME","test_id":test_id,"outcome":outcome,"authority":"NO_POST_HOC_INTERPRETATION"}
    row=allowed[outcome]
    invalid=("INVALID" in outcome or "POST_HOC" in outcome or "NOT_EXCLUDED" in outcome)
    return {"status":"PROTOCOL_INVALID" if invalid else "CONTRACT_OUTCOME","test_id":test_id,"outcome":outcome,"interpretation":row["interpretation"],"falsifier_or_invalidity":row["falsifier_or_invalidity"],"next_test":row["next_test"],"cause_promotion_permitted":not invalid}

def validate_source(contract,source):
    if source.get("artifact_id")!=contract["source"]["artifact_id"]:
        raise ContractError("SOURCE_ARTIFACT_ID_MISMATCH")
    if source.get("status")!=contract["source"]["required_source_status"]:
        raise ContractError("SOURCE_STATUS_MISMATCH")
    gates={g["id"]:g for g in source.get("topa_gates",[])}
    expected={
      "TOPA-RT-H1":"PROSPECTIVE_PRE_EVENT_INFORMATION_GATE",
      "TOPA-RT-H2":"TEMPORAL_KERNEL_GATE",
      "TOPA-RT-H3":"DAT_VS_FORCE_MODEL_GATE",
      "TOPA-RT-H4":"CARRIER_IDENTITY_GATE",
      "TOPA-RT-H5":"UAP_BRIDGE_GATE"
    }
    ct={t["id"]:t for t in contract["tests"]}
    for gid,name in expected.items():
        if gid not in gates or gates[gid].get("name")!=name or ct[gid].get("source_name")!=name:
            raise ContractError(f"GATE_GROUNDING_MISMATCH:{gid}")
    uap=source.get("uap_relevance",{})
    if uap.get("direct_uap_tachyon_link_found") is not False:
        raise ContractError("H5_FIREWALL_SOURCE_CHANGED")
    if ct["TOPA-RT-H5"].get("available",False):
        raise ContractError("H5_MUST_REMAIN_UNAVAILABLE")
    return {
      "schema":"janus.eye.r4_7_rt_1.source_grounding_receipt.v1",
      "status":"PASS_SOURCE_GROUNDING",
      "source_artifact_id":source["artifact_id"],
      "source_status":source["status"],
      "gate_ids":sorted(expected),
      "h5_unavailable_while_direct_link_false":True,
      "source_git_commit":os.getenv("GITHUB_SHA","LOCAL_OR_UNKNOWN")
    }

def write_outputs(contract,model,source,outdir):
    outdir.mkdir(parents=True,exist_ok=True)
    receipt=solve_minimax(model)
    grounding=validate_source(contract,source)
    routes=[]
    for t in contract["tests"]:
        for row in t.get("outcome_space",[]):
            routes.append(route_outcome(contract,t["id"],row["outcome"]))
    firewall={
      "schema":"janus.eye.r4_7_rt_1.probability_firewall_receipt.v1",
      "status":"PASS_NO_ARCHIVAL_PROBABILITIES",
      "probability_policy":contract["probability_policy"],
      "r4_3_gate":contract["probability_policy"]["r4_3_gate"],
      "numeric_priors_or_likelihoods_declared":False,
      "source_git_commit":os.getenv("GITHUB_SHA","LOCAL_OR_UNKNOWN"),
      "firewalls":contract["firewalls"]
    }
    payloads={
      "minimax_policy_receipt.json":receipt,
      "policy_tree.json":{"schema":"janus.eye.r4_7_rt_1.policy_tree.v1","status":receipt.get("status"),"root_next_test":receipt.get("root_next_test"),"worst_case_cost_to_identification":receipt.get("worst_case_cost_to_identification"),"policy_nodes":receipt.get("policy_nodes",[]),"source_git_commit":receipt.get("source_git_commit")},
      "prospective_route_table.json":{"schema":"janus.eye.r4_7_rt_1.prospective_route_table.v1","status":"PREREGISTERED_OUTCOME_LANGUAGE","routes":routes,"out_of_contract_rule":contract["global_invalid_states"]["OUT_OF_CONTRACT"],"source_git_commit":os.getenv("GITHUB_SHA","LOCAL_OR_UNKNOWN")},
      "source_grounding_receipt.json":grounding,
      "probability_firewall_receipt.json":firewall
    }
    for name,payload in payloads.items():
        (outdir/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return payloads

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--contract",required=True)
    ap.add_argument("--model",required=True)
    ap.add_argument("--source",required=True)
    ap.add_argument("--output-dir",required=True)
    ap.add_argument("--route-test")
    ap.add_argument("--route-outcome")
    a=ap.parse_args()
    contract=load(a.contract)
    if a.route_test or a.route_outcome:
        if not (a.route_test and a.route_outcome): raise SystemExit("both --route-test and --route-outcome required")
        print(json.dumps(route_outcome(contract,a.route_test,a.route_outcome),ensure_ascii=False,sort_keys=True)); return 0
    payloads=write_outputs(contract,load(a.model),load(a.source),Path(a.output_dir))
    r=payloads["minimax_policy_receipt.json"]
    print(json.dumps({"status":r.get("status"),"root_next_test":r.get("root_next_test"),"worst_case_cost_to_identification":r.get("worst_case_cost_to_identification")},sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
