#!/usr/bin/env python3
from __future__ import annotations
import argparse, functools, json, math, os
from pathlib import Path

INF=float('inf')
class ModelError(ValueError): pass

def norm_dist(d,label):
    out={str(k):float(v) for k,v in dict(d).items()}
    if not out: raise ModelError(f'EMPTY_DISTRIBUTION:{label}')
    if any((not math.isfinite(v) or v<0) for v in out.values()): raise ModelError(f'BAD_PROBABILITY:{label}')
    s=sum(out.values())
    if s<=0: raise ModelError(f'ZERO_MASS:{label}')
    if abs(s-1.0)>1e-9: raise ModelError(f'PROBABILITIES_MUST_SUM_1:{label}:{s}')
    return out

def parse(d):
    causes={}; total=0.0
    for x in d.get('cause_classes',[]):
        x={'id':x} if isinstance(x,str) else dict(x)
        cid=str(x.get('id','')).strip(); target=str(x.get('target_class',cid)).strip(); prior=float(x.get('prior',1.0))
        if not cid or cid in causes: raise ModelError(f'BAD_CAUSE:{cid}')
        if not target: raise ModelError(f'BAD_TARGET:{cid}')
        if prior<=0 or not math.isfinite(prior): raise ModelError(f'BAD_PRIOR:{cid}')
        causes[cid]={'target_class':target,'prior':prior}; total+=prior
    if len(causes)<2: raise ModelError('NEED_2_CAUSES')
    for c in causes.values(): c['prior']/=total
    tests={}
    for x in d.get('tests',[]):
        x=dict(x); tid=str(x.get('id','')).strip(); cost=float(x.get('cost',1.0)); available=bool(x.get('available',True)); usable=bool(x.get('decision_usable',True)); calibrated=bool(x.get('calibrated',False))
        if not tid or tid in tests: raise ModelError(f'BAD_TEST:{tid}')
        if cost<0 or not math.isfinite(cost): raise ModelError(f'BAD_COST:{tid}')
        raw=dict(x.get('likelihood_by_cause',{})); likes={}
        if available and usable:
            if not calibrated: raise ModelError(f'UNCALIBRATED_DECISION_TEST:{tid}')
            if set(raw)!=set(causes): raise ModelError(f'LIKELIHOOD_MAP_MISMATCH:{tid}')
            for c in causes: likes[c]=norm_dist(raw[c],f'{tid}:{c}')
            outcomes=sorted(set().union(*(set(v) for v in likes.values())))
            for c in causes: likes[c]={o:likes[c].get(o,0.0) for o in outcomes}
        else:
            outcomes=sorted(set().union(*(set(v) for v in raw.values()))) if raw else []
            for c,row in raw.items(): likes[str(c)]=norm_dist(row,f'{tid}:{c}')
        tests[tid]={
            'cost':cost,'available':available,'usable':usable,'calibrated':calibrated,
            'depends_on':tuple(map(str,x.get('depends_on',[]))),
            'failure_domains':frozenset(map(str,x.get('failure_domains',[]))),
            'likelihoods':likes,'outcomes':tuple(outcomes)
        }
    for tid,t in tests.items():
        if any(dep not in tests for dep in t['depends_on']): raise ModelError(f'UNKNOWN_DEP:{tid}')
    acquired=frozenset(map(str,d.get('already_acquired',[])))
    if acquired-set(tests): raise ModelError(f'UNKNOWN_ACQUIRED:{sorted(acquired-set(tests))}')
    r=dict(d.get('requirements',{}))
    defaults={
        'confidence_threshold':0.95,'max_decision_tests':14,'max_states':250000,
        'require_failure_domain_disjoint_path':False,'allow_prior_only_identification':False,
        'min_outcome_probability':0.0,'belief_round_digits':12,
        'objective':'expected_cost_then_worst_case_then_test_id','stress_success_threshold':0.95
    }
    for k,v in defaults.items(): r.setdefault(k,v)
    for k in ('max_decision_tests','max_states','belief_round_digits'): r[k]=int(r[k])
    for k in ('confidence_threshold','min_outcome_probability','stress_success_threshold'): r[k]=float(r[k])
    if not (0.5<r['confidence_threshold']<=1): raise ModelError('BAD_CONFIDENCE_THRESHOLD')
    if not (0<=r['min_outcome_probability']<1): raise ModelError('BAD_MIN_OUTCOME_PROB')
    if not (0<=r['stress_success_threshold']<=1): raise ModelError('BAD_STRESS_THRESHOLD')
    return causes,tests,acquired,r

def canon_belief(b,causes,digits):
    vals=[max(0.0,float(b.get(c,0.0))) for c in sorted(causes)]; s=sum(vals)
    if s<=0: raise ModelError('ZERO_POSTERIOR_MASS')
    vals=[v/s for v in vals]; vals=[round(v,digits) for v in vals]; s=sum(vals)
    if s<=0: raise ModelError('ZERO_ROUNDED_POSTERIOR_MASS')
    return tuple(round(v/s,digits) for v in vals)

def belief_dict(bt,causes): return {c:bt[i] for i,c in enumerate(sorted(causes))}

def target_posterior(bt,causes):
    out={}
    for c,p in belief_dict(bt,causes).items(): out[causes[c]['target_class']]=out.get(causes[c]['target_class'],0.0)+p
    return dict(sorted(out.items()))

def terminal_info(bt,causes,r,evidence_n):
    tp=target_posterior(bt,causes); target,conf=max(tp.items(),key=lambda kv:(kv[1],kv[0])); prior_block=(evidence_n<=0 and not r['allow_prior_only_identification'])
    return {'terminal':bool(conf+1e-12>=r['confidence_threshold'] and not prior_block),'identified_target_class':target,'confidence':conf,'risk':1.0-conf,'target_posterior':tp,'prior_only_blocked':prior_block}

def evidence_count(acq,tests): return sum(1 for t in acq if tests[t]['available'] and tests[t]['usable'] and tests[t]['calibrated'])

def available(tid,acq,used_fd,tests,r):
    t=tests[tid]
    if tid in acq or not t['available'] or not t['usable'] or not t['calibrated'] or any(dep not in acq for dep in t['depends_on']): return False
    if r['require_failure_domain_disjoint_path'] and (not t['failure_domains'] or not used_fd.isdisjoint(t['failure_domains'])): return False
    return True

def next_fd(used,tid,tests,r): return frozenset(set(used)|set(tests[tid]['failure_domains'])) if r['require_failure_domain_disjoint_path'] else frozenset()

def predictive(bt,tid,causes,tests):
    b=belief_dict(bt,causes); t=tests[tid]
    return {o:p for o in t['outcomes'] if (p:=sum(b[c]*t['likelihoods'][c].get(o,0.0) for c in causes))>0}

def posterior(bt,tid,outcome,causes,tests,r):
    b=belief_dict(bt,causes); vals={c:b[c]*tests[tid]['likelihoods'][c].get(outcome,0.0) for c in causes}; z=sum(vals.values())
    if z<=0: return None
    return canon_belief({c:v/z for c,v in vals.items()},causes,r['belief_round_digits'])

def entropy_targets(bt,causes): return -sum(p*math.log2(p) for p in target_posterior(bt,causes).values() if p>0)

def rank(bt,acq,used,causes,tests,r):
    base=entropy_targets(bt,causes); rows=[]
    for tid in sorted(tests):
        if not available(tid,acq,used,tests,r): continue
        post_h=0.0; expected_risk=0.0; outp={}
        for o,p in predictive(bt,tid,causes,tests).items():
            if p<r['min_outcome_probability']: continue
            nb=posterior(bt,tid,o,causes,tests,r)
            if nb is None: continue
            outp[o]=p; post_h+=p*entropy_targets(nb,causes); expected_risk+=p*terminal_info(nb,causes,{**r,'allow_prior_only_identification':True},1)['risk']
        gain=base-post_h; cost=tests[tid]['cost']; gpc='INF' if cost==0 and gain>0 else (gain/cost if cost else 0.0)
        rows.append({'test_id':tid,'cost':cost,'expected_information_gain_bits':round(gain,12),'expected_posterior_risk':round(expected_risk,12),'gain_per_cost':gpc,'outcome_probabilities':{k:round(v,12) for k,v in outp.items()},'unlocks':sorted(x for x,t in tests.items() if tid in t['depends_on'])})
    def key(x): return (-(1e100 if x['gain_per_cost']=='INF' else x['gain_per_cost']),x['expected_posterior_risk'],-x['expected_information_gain_bits'],x['cost'],x['test_id'])
    return sorted(rows,key=key)

def solve(d,source='MODEL'):
    causes,tests,acq0,r=parse(d); prior_bt=canon_belief({c:causes[c]['prior'] for c in causes},causes,r['belief_round_digits'])
    decisions=sum(1 for t,x in tests.items() if x['available'] and x['usable'] and x['calibrated'] and t not in acq0)
    common={'schema':'janus.eye.r4_3.stochastic_policy_receipt.v1','artifact_id':d.get('id',source),'source_git_commit':os.getenv('GITHUB_SHA','LOCAL_OR_UNKNOWN'),'confidence_threshold':r['confidence_threshold']}
    if decisions>r['max_decision_tests']:
        return {**common,'status':'UNKNOWN_RESOURCE_LIMIT','reason':'DECISION_TEST_COUNT_EXCEEDS_EXACT_CEILING','decision_test_count':decisions,'max_decision_tests':r['max_decision_tests'],'authority':'NO_POLICY_OPTIMALITY_CLAIM'}
    counter={'n':0,'limit':False}; policy={}
    @functools.lru_cache(None)
    def dp(bt,acq_t,fd_t):
        counter['n']+=1
        if counter['n']>r['max_states']: counter['limit']=True; return INF,INF,None
        acq=frozenset(acq_t); used=frozenset(fd_t); term=terminal_info(bt,causes,r,evidence_count(acq,tests))
        if term['terminal']: return 0.0,0.0,{'terminal':True}
        best=(INF,INF,None); rec=None
        for tid in sorted(tests):
            if not available(tid,acq,used,tests,r): continue
            branches=[]; ef=0.0; wf=0.0; ok=True; nacq=frozenset(set(acq)|{tid}); nfd=next_fd(used,tid,tests,r)
            for o,p in sorted(predictive(bt,tid,causes,tests).items()):
                if p<r['min_outcome_probability']: continue
                nb=posterior(bt,tid,o,causes,tests,r)
                if nb is None: continue
                ce,cw,_=dp(nb,tuple(sorted(nacq)),tuple(sorted(nfd)))
                if not math.isfinite(ce): ok=False; break
                ef+=p*ce; wf=max(wf,cw); branches.append((o,p,nb))
            if not branches or not ok: continue
            et=tests[tid]['cost']+ef; wt=tests[tid]['cost']+wf; cand=(round(et,12),round(wt,12),tid)
            if cand<best: best=cand; rec={'test_id':tid,'expected':et,'worst':wt,'branches':branches}
        key=(bt,tuple(sorted(acq)),tuple(sorted(used)))
        if rec is not None: policy[key]=rec; return best[0],best[1],rec
        return INF,INF,None
    expected,worst,root=dp(prior_bt,tuple(sorted(acq0)),tuple())
    if counter['limit']:
        return {**common,'status':'UNKNOWN_RESOURCE_LIMIT','reason':'STATE_COUNT_EXCEEDS_EXACT_CEILING','states_visited':counter['n'],'max_states':r['max_states'],'authority':'NO_POLICY_OPTIMALITY_CLAIM'}
    root_term=terminal_info(prior_bt,causes,r,evidence_count(acq0,tests))
    if root_term['terminal']:
        node={'node_id':'N0000','terminal':True,'acquired_tests':sorted(acq0),'posterior_by_cause':belief_dict(prior_bt,causes),'posterior_by_target':root_term['target_posterior'],'identified_target_class':root_term['identified_target_class'],'confidence':round(root_term['confidence'],12),'risk':round(root_term['risk'],12)}
        return {**common,'status':'BASELINE_ALREADY_CONFIDENT','exact_policy_search_completed':True,'root_node_id':'N0000','root_next_test':None,'expected_cost_to_confident_identification':0.0,'worst_case_cost_to_confident_identification':0.0,'states_visited':counter['n'],'policy_node_count':1,'policy_nodes':[node],'root_greedy_next_test_ranking':rank(prior_bt,acq0,frozenset(),causes,tests,r),'authority':'CONFIDENCE_THRESHOLD_MET_BY_DECLARED_BASELINE_MODEL','firewalls':['PRIOR != EVIDENCE','BASELINE_CONFIDENCE != CAUSAL_TRUTH']}
    if root is None or not math.isfinite(expected):
        return {**common,'status':'NON_IDENTIFIABLE_UNDER_CURRENT_STOCHASTIC_MODEL','exact_policy_search_completed':True,'states_visited':counter['n'],'root_posterior_by_cause':belief_dict(prior_bt,causes),'root_posterior_by_target':root_term['target_posterior'],'root_risk':root_term['risk'],'root_greedy_next_test_ranking':rank(prior_bt,acq0,frozenset(),causes,tests,r),'authority':'STOCHASTIC_NON_IDENTIFIABILITY_UNDER_DECLARED_LIKELIHOOD_PRIOR_AND_THRESHOLD_MODEL_ONLY','firewalls':['NON_IDENTIFIABLE != FALSE','LIKELIHOOD_MODEL != TRUE_WORLD','PRIOR != EVIDENCE','SOFT_UNCALIBRATED_TEST != PROBABILITY_MODEL','GREEDY_RANKING != POLICY_PROOF']}
    node_ids={}; nodes=[]
    def walk(bt,acq,used):
        key=(bt,tuple(sorted(acq)),tuple(sorted(used)))
        if key in node_ids: return node_ids[key]
        nid=f'N{len(node_ids):04d}'; node_ids[key]=nid; term=terminal_info(bt,causes,r,evidence_count(acq,tests))
        if term['terminal']:
            nodes.append({'node_id':nid,'terminal':True,'acquired_tests':sorted(acq),'posterior_by_cause':{k:round(v,12) for k,v in belief_dict(bt,causes).items()},'posterior_by_target':{k:round(v,12) for k,v in term['target_posterior'].items()},'identified_target_class':term['identified_target_class'],'confidence':round(term['confidence'],12),'risk':round(term['risk'],12)}); return nid
        rec=policy[key]; tid=rec['test_id']; nacq=frozenset(set(acq)|{tid}); nfd=next_fd(used,tid,tests,r); branches=[]
        for o,p,nb in rec['branches']:
            branches.append({'outcome':o,'probability':round(p,12),'child_node_id':walk(nb,nacq,nfd),'posterior_by_target':{k:round(v,12) for k,v in target_posterior(nb,causes).items()}})
        nodes.append({'node_id':nid,'terminal':False,'acquired_tests':sorted(acq),'posterior_by_cause':{k:round(v,12) for k,v in belief_dict(bt,causes).items()},'posterior_by_target':{k:round(v,12) for k,v in target_posterior(bt,causes).items()},'current_risk':round(term['risk'],12),'next_test':tid,'immediate_cost':tests[tid]['cost'],'expected_total_cost_from_state':round(rec['expected'],12),'worst_case_total_cost_from_state':round(rec['worst'],12),'branches':branches}); return nid
    root_id=walk(prior_bt,acq0,frozenset())
    receipt={**common,'status':'EXACT_STOCHASTIC_POLICY_FOUND','exact_policy_search_completed':True,'objective':r['objective'],'root_node_id':root_id,'root_next_test':root['test_id'],'expected_cost_to_confident_identification':round(expected,12),'worst_case_cost_to_confident_identification':round(worst,12),'states_visited':counter['n'],'policy_node_count':len(nodes),'policy_nodes':sorted(nodes,key=lambda x:x['node_id']),'root_greedy_next_test_ranking':rank(prior_bt,acq0,frozenset(),causes,tests,r),'authority':'EXACT_OPTIMAL_POLICY_UNDER_DECLARED_STOCHASTIC_LIKELIHOOD_PRIOR_THRESHOLD_MODEL__NOT_CAUSAL_TRUTH','firewalls':['STOCHASTIC_POLICY != CAUSAL_TRUTH','PRIOR != EVIDENCE','LIKELIHOOD != OBSERVED_FREQUENCY_WITHOUT_CALIBRATION','POSTERIOR_CONFIDENCE != FREQUENTIST_GUARANTEE','EXPECTED_COST_OPTIMUM != WORST_CASE_OPTIMUM','SOFT_UNCALIBRATED_TEST != PROBABILITY_MODEL','GREEDY_NEXT_TEST != OPTIMAL_POLICY','NON_IDENTIFIABLE != FALSE']}
    receipt['stress_test']=stress_policy(receipt,d,causes,tests,r)
    return receipt

def scenario_model(scenario,causes,tests):
    priors={c:causes[c]['prior'] for c in causes}
    if 'prior_by_cause' in scenario:
        raw=norm_dist(scenario['prior_by_cause'],f"stress:{scenario.get('id','scenario')}:priors")
        if set(raw)!=set(causes): raise ModelError('STRESS_PRIOR_MISMATCH')
        priors=raw
    likes={t:{c:dict(tests[t]['likelihoods'].get(c,{})) for c in causes} for t in tests}
    for tid,rows in dict(scenario.get('likelihood_overrides',{})).items():
        if tid not in tests: raise ModelError(f'STRESS_UNKNOWN_TEST:{tid}')
        if set(rows)!=set(causes): raise ModelError(f'STRESS_LIKELIHOOD_CAUSE_MISMATCH:{tid}')
        tmp={c:norm_dist(rows[c],f"stress:{scenario.get('id','scenario')}:{tid}:{c}") for c in causes}; outs=sorted(set().union(*(set(v) for v in tmp.values())))
        for c in causes: likes[tid][c]={o:tmp[c].get(o,0.0) for o in outs}
    return priors,likes

def stress_policy(receipt,d,causes,tests,r):
    scenarios=list(d.get('stress_scenarios',[]))
    if not scenarios: return {'schema':'janus.eye.r4_3.stress_test_receipt.v1','status':'NO_STRESS_SCENARIOS_DECLARED','scenarios':[]}
    nodes={n['node_id']:n for n in receipt.get('policy_nodes',[])}; root=receipt.get('root_node_id'); rows=[]
    for sc in scenarios:
        sid=str(sc.get('id','scenario')); priors,likes=scenario_model(sc,causes,tests); start=canon_belief(priors,causes,r['belief_round_digits']); acc={'success':0.0,'wrong':0.0,'unresolved':0.0,'uncovered':0.0,'cost':0.0}
        def rec(nid,bt,path_prob,cost_so_far):
            node=nodes[nid]
            if node['terminal']:
                tp=target_posterior(bt,causes); best,conf=max(tp.items(),key=lambda kv:(kv[1],kv[0])); nominal=node['identified_target_class']
                if best==nominal and conf+1e-12>=r['confidence_threshold']: acc['success']+=path_prob
                elif conf+1e-12>=r['confidence_threshold']: acc['wrong']+=path_prob
                else: acc['unresolved']+=path_prob
                acc['cost']+=path_prob*cost_so_far; return
            tid=node['next_test']; b=belief_dict(bt,causes); outs=sorted(set().union(*(set(likes[tid][c]) for c in causes))); branch_by_out={x['outcome']:x for x in node['branches']}
            for o in outs:
                p=sum(b[c]*likes[tid][c].get(o,0.0) for c in causes)
                if p<=0: continue
                if o not in branch_by_out:
                    acc['uncovered']+=path_prob*p; acc['cost']+=path_prob*p*(cost_so_far+tests[tid]['cost']); continue
                vals={c:b[c]*likes[tid][c].get(o,0.0) for c in causes}; z=sum(vals.values()); nb=canon_belief({c:v/z for c,v in vals.items()},causes,r['belief_round_digits'])
                rec(branch_by_out[o]['child_node_id'],nb,path_prob*p,cost_so_far+tests[tid]['cost'])
        rec(root,start,1.0,0.0)
        row={'id':sid,'success_probability':round(acc['success'],12),'wrong_confident_probability':round(acc['wrong'],12),'unresolved_probability':round(acc['unresolved'],12),'out_of_nominal_support_probability':round(acc['uncovered'],12),'expected_cost_under_scenario':round(acc['cost'],12)}
        row['passes_stress_success_threshold']=bool(row['success_probability']+1e-12>=r['stress_success_threshold'] and row['wrong_confident_probability']<=1e-12 and row['out_of_nominal_support_probability']<=1e-12); rows.append(row)
    ok=all(x['passes_stress_success_threshold'] for x in rows)
    return {'schema':'janus.eye.r4_3.stress_test_receipt.v1','status':'PASS_ALL_DECLARED_STRESS_SCENARIOS' if ok else 'MODEL_UNCERTAIN_UNDER_DECLARED_STRESS_SCENARIOS','stress_success_threshold':r['stress_success_threshold'],'scenarios':rows,'firewalls':['STRESS_PASS != TRUE_WORLD_CALIBRATION','STRESS_FAIL != CAUSE_FALSE','OUT_OF_SUPPORT != NEGATIVE_EVIDENCE']}

def write_outputs(model_path,receipt,outdir):
    outdir.mkdir(parents=True,exist_ok=True)
    payloads={
      'stochastic_policy_receipt.json':receipt,
      'policy_tree.json':{'schema':'janus.eye.r4_3.policy_tree.v1','artifact_id':receipt.get('artifact_id'),'status':receipt.get('status'),'root_node_id':receipt.get('root_node_id'),'policy_nodes':receipt.get('policy_nodes',[]),'source_git_commit':receipt.get('source_git_commit')},
      'next_test_ranking.json':{'schema':'janus.eye.r4_3.next_test_ranking.v1','artifact_id':receipt.get('artifact_id'),'status':receipt.get('status'),'root_greedy_next_test_ranking':receipt.get('root_greedy_next_test_ranking',[]),'warning':'Greedy expected-information ranking is diagnostic only; exact stochastic policy controls when available.','source_git_commit':receipt.get('source_git_commit')},
      'stress_test_receipt.json':receipt.get('stress_test',{'schema':'janus.eye.r4_3.stress_test_receipt.v1','status':'NOT_RUN'}),
      'policy_summary.json':{'schema':'janus.eye.r4_3.policy_summary.v1','artifact_id':receipt.get('artifact_id'),'status':receipt.get('status'),'root_next_test':receipt.get('root_next_test'),'confidence_threshold':receipt.get('confidence_threshold'),'expected_cost_to_confident_identification':receipt.get('expected_cost_to_confident_identification'),'worst_case_cost_to_confident_identification':receipt.get('worst_case_cost_to_confident_identification'),'stress_status':receipt.get('stress_test',{}).get('status'),'source_model':str(model_path),'source_git_commit':receipt.get('source_git_commit'),'epistemic_ceiling':receipt.get('authority')}
    }
    for name,p in payloads.items(): (outdir/name).write_text(json.dumps(p,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--output-dir',required=True); a=ap.parse_args(); p=Path(a.input); d=json.loads(p.read_text(encoding='utf-8')); receipt=solve(d,p.stem); write_outputs(p,receipt,Path(a.output_dir)); print(json.dumps({'status':receipt.get('status'),'root_next_test':receipt.get('root_next_test'),'expected_cost':receipt.get('expected_cost_to_confident_identification'),'worst_case_cost':receipt.get('worst_case_cost_to_confident_identification'),'stress_status':receipt.get('stress_test',{}).get('status')},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
