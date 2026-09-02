#!/usr/bin/env python3
from __future__ import annotations
import argparse, copy, importlib.util, json, math, os
from pathlib import Path

class ModelError(ValueError): pass

def load_r44():
    path = Path(__file__).resolve().parents[1] / "r4_4" / "eye_r4_4_robust_witness_planner.py"
    spec = importlib.util.spec_from_file_location("eye_r4_4", path)
    if spec is None or spec.loader is None: raise RuntimeError("R4_4_IMPORT_FAILED")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def norm_dist(d,label):
    out={str(k):float(v) for k,v in dict(d).items()}
    if not out or any((not math.isfinite(v) or v<0) for v in out.values()): raise ModelError(f"BAD_DISTRIBUTION:{label}")
    s=sum(out.values())
    if s<=0 or abs(s-1.0)>1e-9: raise ModelError(f"PROBABILITIES_MUST_SUM_1:{label}:{s}")
    return out

def parse_base(d):
    causes={}; total=0.0
    for raw in d.get("cause_classes",[]):
        x={"id":raw} if isinstance(raw,str) else dict(raw); cid=str(x.get("id","")).strip(); target=str(x.get("target_class",cid)).strip(); prior=float(x.get("prior",1.0))
        if not cid or cid in causes or not target or prior<=0 or not math.isfinite(prior): raise ModelError(f"BAD_CAUSE:{cid}")
        causes[cid]={"target_class":target,"prior":prior}; total+=prior
    if len(causes)<2: raise ModelError("NEED_2_CAUSES")
    for c in causes.values(): c["prior"]/=total
    tests={}
    for raw in d.get("tests",[]):
        x=dict(raw); tid=str(x.get("id","")).strip()
        if not tid or tid in tests: raise ModelError(f"BAD_TEST:{tid}")
        rows=dict(x.get("likelihood_by_cause",{})); base={}
        if rows:
            if set(rows)!=set(causes): raise ModelError(f"LIKELIHOOD_MAP_MISMATCH:{tid}")
            tmp={c:norm_dist(rows[c],f"{tid}:{c}") for c in causes}; outcomes=sorted(set().union(*(set(v) for v in tmp.values())))
            for c in causes: base[c]={o:tmp[c].get(o,0.0) for o in outcomes}
        tests[tid]={"cost":float(x.get("cost",1.0)),"base":base}
    return causes,tests

def build_candidate(d,candidate,causes,tests):
    c=dict(candidate); mid=str(c.get("id","")).strip(); provenance=str(c.get("provenance","")).strip()
    if not mid: raise ModelError("BAD_CANDIDATE_ID")
    if not provenance: raise ModelError(f"MISSING_CANDIDATE_PROVENANCE:{mid}")
    priors={k:v["prior"] for k,v in causes.items()}
    if "prior_by_cause" in c:
        priors=norm_dist(c["prior_by_cause"],f"{mid}:priors")
        if set(priors)!=set(causes): raise ModelError(f"CANDIDATE_PRIOR_MISMATCH:{mid}")
    likes={tid:{cause:dict(row) for cause,row in t["base"].items()} for tid,t in tests.items()}
    for tid,rows in dict(c.get("likelihood_overrides",{})).items():
        if tid not in tests: raise ModelError(f"CANDIDATE_UNKNOWN_TEST:{mid}:{tid}")
        if set(rows)!=set(causes): raise ModelError(f"CANDIDATE_LIKELIHOOD_CAUSE_MISMATCH:{mid}:{tid}")
        tmp={cause:norm_dist(rows[cause],f"{mid}:{tid}:{cause}") for cause in causes}; outcomes=sorted(set().union(*(set(v) for v in tmp.values())))
        for cause in causes: likes[tid][cause]={o:tmp[cause].get(o,0.0) for o in outcomes}
    return {"id":mid,"provenance":provenance,"weight":float(c.get("weight",1.0)),"prior_by_cause":priors,"likelihoods":likes,"likelihood_overrides":copy.deepcopy(c.get("likelihood_overrides",{}))}

def posterior_target(belief,causes):
    out={}
    for c,p in belief.items(): out[causes[c]["target_class"]]=out.get(causes[c]["target_class"],0.0)+p
    return out

def predictive(belief,tid,cand,causes):
    likes=cand["likelihoods"].get(tid,{}); outcomes=sorted(set().union(*(set(likes.get(c,{})) for c in causes)))
    return {o:sum(belief[c]*likes.get(c,{}).get(o,0.0) for c in causes) for o in outcomes}

def update(belief,tid,outcome,cand,causes):
    likes=cand["likelihoods"].get(tid,{}); vals={c:belief[c]*likes.get(c,{}).get(outcome,0.0) for c in causes}; z=sum(vals.values())
    return None if z<=0 else {c:v/z for c,v in vals.items()}

def evaluate_policy(receipt,d,cand,causes,tests):
    if receipt.get("status")!="EXACT_ROBUST_POLICY_FOUND": return {"status":"POLICY_NOT_EVALUABLE","policy_status":receipt.get("status")}
    nodes={n["node_id"]:n for n in receipt.get("policy_nodes",[])}; root=receipt.get("root_node_id")
    if root not in nodes: raise ModelError("POLICY_ROOT_MISSING")
    threshold=float(receipt.get("confidence_threshold",d.get("requirements",{}).get("confidence_threshold",0.95))); minp=float(d.get("requirements",{}).get("min_outcome_probability",0.0))
    acc={"success":0.0,"wrong":0.0,"unresolved":0.0,"out_of_support":0.0,"expected_cost":0.0}
    def rec(nid,b,path_prob,cost):
        node=nodes[nid]
        if node.get("terminal"):
            tp=posterior_target(b,causes); best,conf=max(tp.items(),key=lambda kv:(kv[1],kv[0])); nominal=node.get("identified_target_class")
            if conf+1e-12>=threshold and best==nominal: acc["success"]+=path_prob
            elif conf+1e-12>=threshold and best!=nominal: acc["wrong"]+=path_prob
            else: acc["unresolved"]+=path_prob
            acc["expected_cost"]+=path_prob*cost; return
        tid=node.get("next_test")
        if tid not in tests or tid not in cand["likelihoods"]: acc["out_of_support"]+=path_prob; acc["expected_cost"]+=path_prob*cost; return
        branch={x["outcome"]:x["child_node_id"] for x in node.get("branches",[])}; pred=predictive(b,tid,cand,causes); tcost=tests[tid]["cost"]; used=0.0
        for o,p in pred.items():
            if p<=minp: continue
            used+=p
            if o not in branch: acc["out_of_support"]+=path_prob*p; acc["expected_cost"]+=path_prob*p*(cost+tcost); continue
            nb=update(b,tid,o,cand,causes)
            if nb is None: acc["out_of_support"]+=path_prob*p; acc["expected_cost"]+=path_prob*p*(cost+tcost); continue
            rec(branch[o],nb,path_prob*p,cost+tcost)
        if used<1-1e-9:
            missing=max(0.0,1.0-used); acc["out_of_support"]+=path_prob*missing; acc["expected_cost"]+=path_prob*missing*(cost+tcost)
    rec(root,dict(cand["prior_by_cause"]),1.0,0.0)
    hard=acc["wrong"]+acc["unresolved"]+acc["out_of_support"]; baseline=float(receipt.get("worst_model_expected_cost",receipt.get("robust_cost",0.0)) or 0.0); over=max(0.0,acc["expected_cost"]-baseline)
    return {"status":"EVALUATED","candidate_id":cand["id"],"success_probability":round(acc["success"],12),"wrong_confident_probability":round(acc["wrong"],12),"unresolved_probability":round(acc["unresolved"],12),"out_of_policy_support_probability":round(acc["out_of_support"],12),"hard_failure_probability":round(hard,12),"expected_cost_under_candidate":round(acc["expected_cost"],12),"baseline_robust_cost":round(baseline,12),"cost_overrun":round(over,12)}

def solve(d,source="MODEL"):
    if "base_problem" not in d: raise ModelError("MISSING_BASE_PROBLEM")
    base=copy.deepcopy(d["base_problem"]); causes,tests=parse_base(base); env=dict(d.get("uncertainty_envelope",{})); vertices=list(env.get("vertex_models",[]))
    if not vertices: raise ModelError("NEED_FINITE_VERTEX_MODELS")
    ids=[]
    for v in vertices:
        mid=str(dict(v).get("id","")).strip()
        if not mid or mid in ids: raise ModelError(f"BAD_OR_DUPLICATE_VERTEX:{mid}")
        ids.append(mid); build_candidate(base,v,causes,tests)
    cfg=dict(d.get("requirements",{})); max_rounds=int(cfg.get("max_expansion_rounds",8)); max_vertices=int(cfg.get("max_vertices",256)); hard_eps=float(cfg.get("hard_failure_epsilon",1e-9)); cost_tol=float(cfg.get("cost_overrun_tolerance",1e-9))
    common={"schema":"janus.eye.r4_5.expansion_receipt.v1","artifact_id":d.get("id",source),"source_git_commit":os.getenv("GITHUB_SHA","LOCAL_OR_UNKNOWN")}
    if len(vertices)>max_vertices: return {**common,"status":"UNKNOWN_RESOURCE_LIMIT","reason":"VERTEX_COUNT_EXCEEDS_CEILING","vertex_count":len(vertices),"max_vertices":max_vertices,"authority":"NO_ENVELOPE_COVERAGE_CLAIM"}
    r44=load_r44(); current=copy.deepcopy(base); existing={str(m.get("id")) for m in current.get("model_set",[])}; remaining=[dict(v) for v in vertices if str(v.get("id")) not in existing]; rounds=[]; current_receipt=r44.solve(current,source)
    if current_receipt.get("status")!="EXACT_ROBUST_POLICY_FOUND": return {**common,"status":"BASELINE_NOT_ROBUSTLY_SOLVABLE","baseline_status":current_receipt.get("status"),"rounds":[],"authority":"NO_ADVERSARIAL_EXPANSION_CLAIM","firewalls":["BASELINE_NON_IDENTIFIABLE != ADVERSARIAL_BREAK","MODEL_SET != TRUE_WORLD"]}
    for round_i in range(max_rounds+1):
        evaluations=[]
        for raw in remaining: evaluations.append((raw,evaluate_policy(current_receipt,current,build_candidate(base,raw,causes,tests),causes,tests)))
        breakers=[]
        for raw,ev in evaluations:
            if ev.get("status")=="EVALUATED" and (ev["hard_failure_probability"]>hard_eps or ev["cost_overrun"]>cost_tol): breakers.append(((ev["hard_failure_probability"],ev["cost_overrun"],ev["expected_cost_under_candidate"],str(raw.get("id"))),raw,ev))
        if not breakers:
            return {**common,"status":"NO_ADMISSIBLE_BREAKER_FOUND_IN_FINITE_ENVELOPE","exact_finite_vertex_search_completed":True,"initial_model_count":len(base.get("model_set",[])),"final_model_count":len(current.get("model_set",[])),"expanded_model_ids":[x["selected_vertex_id"] for x in rounds],"rounds":rounds,"remaining_vertex_count":len(remaining),"final_r4_4_status":current_receipt.get("status"),"final_root_next_test":current_receipt.get("root_next_test"),"final_robust_cost":current_receipt.get("robust_cost"),"authority":"NO_BREAKER_FOUND_ONLY_WITHIN_DECLARED_FINITE_VERTEX_ENVELOPE__NOT_CONTINUOUS_ROBUSTNESS","firewalls":["FINITE_VERTEX_COVERAGE != CONTINUOUS_ENVELOPE_COVERAGE","NO_BREAKER_FOUND != TRUE_WORLD_ROBUSTNESS","MODEL_SET != TRUE_WORLD","ADVERSARIAL_VERTEX != OBSERVED_WORLD"]}
        if round_i>=max_rounds: return {**common,"status":"UNKNOWN_RESOURCE_LIMIT","reason":"MAX_EXPANSION_ROUNDS_REACHED_WITH_BREAKERS_REMAINING","rounds":rounds,"remaining_breaker_count":len(breakers),"authority":"NO_CONVERGENCE_CLAIM"}
        _,selected,sev=max(breakers,key=lambda x:x[0]); current.setdefault("model_set",[]).append(copy.deepcopy(selected)); remaining=[v for v in remaining if str(v.get("id"))!=str(selected.get("id"))]; replanned=r44.solve(current,source)
        rounds.append({"round":round_i+1,"selected_vertex_id":selected.get("id"),"selected_vertex_provenance":selected.get("provenance"),"breaker_evaluation":sev,"pre_root_next_test":current_receipt.get("root_next_test"),"pre_robust_cost":current_receipt.get("robust_cost"),"post_r4_4_status":replanned.get("status"),"post_root_next_test":replanned.get("root_next_test"),"post_robust_cost":replanned.get("robust_cost")}); current_receipt=replanned; st=replanned.get("status")
        if st=="MODEL_SET_TOO_WIDE_FOR_COMMON_ROBUST_IDENTIFICATION": return {**common,"status":"MODEL_SET_EXPLODES_UNDER_ADVERSARIAL_EXPANSION","rounds":rounds,"authority":"FAILURE_ONLY_WITHIN_DECLARED_FINITE_VERTEX_ENVELOPE"}
        if st=="ROBUST_NON_IDENTIFIABLE_UNDER_DECLARED_MODEL_SET": return {**common,"status":"ROBUST_NON_IDENTIFIABLE_AFTER_ADVERSARIAL_EXPANSION","rounds":rounds,"authority":"NON_IDENTIFIABILITY_ONLY_WITHIN_EXPANDED_DECLARED_FINITE_MODEL_SET"}
        if st=="UNKNOWN_RESOURCE_LIMIT": return {**common,"status":"UNKNOWN_RESOURCE_LIMIT","reason":"R4_4_REPLAN_RESOURCE_LIMIT","rounds":rounds}
        if st!="EXACT_ROBUST_POLICY_FOUND": return {**common,"status":"R4_4_REPLAN_TERMINATED","r4_4_status":st,"rounds":rounds}
    raise AssertionError("UNREACHABLE")

def write_outputs(model_path,receipt,outdir):
    outdir.mkdir(parents=True,exist_ok=True); payloads={"adversarial_expansion_receipt.json":receipt,"breaker_trace.json":{"schema":"janus.eye.r4_5.breaker_trace.v1","artifact_id":receipt.get("artifact_id"),"status":receipt.get("status"),"rounds":receipt.get("rounds",[]),"source_git_commit":receipt.get("source_git_commit")},"expansion_summary.json":{"schema":"janus.eye.r4_5.expansion_summary.v1","artifact_id":receipt.get("artifact_id"),"status":receipt.get("status"),"expanded_model_ids":receipt.get("expanded_model_ids",[r.get("selected_vertex_id") for r in receipt.get("rounds",[])]),"final_root_next_test":receipt.get("final_root_next_test"),"final_robust_cost":receipt.get("final_robust_cost"),"source_model":str(model_path),"source_git_commit":receipt.get("source_git_commit"),"epistemic_ceiling":receipt.get("authority")}}
    for name,payload in payloads.items(): (outdir/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--input",required=True); ap.add_argument("--output-dir",required=True); a=ap.parse_args(); p=Path(a.input); receipt=solve(json.loads(p.read_text(encoding="utf-8")),p.stem); write_outputs(p,receipt,Path(a.output_dir)); print(json.dumps({"status":receipt.get("status"),"expanded":receipt.get("expanded_model_ids",[r.get("selected_vertex_id") for r in receipt.get("rounds",[])]),"final_root_next_test":receipt.get("final_root_next_test")},sort_keys=True))
if __name__=="__main__": main()
