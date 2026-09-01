#!/usr/bin/env python3
from __future__ import annotations
import argparse, functools, itertools, json, math, os
from pathlib import Path

INF=float('inf')
class ModelError(ValueError): pass

def parse(d):
    causes={}; total=0.0
    for x in d.get('cause_classes',[]):
        x={'id':x} if isinstance(x,str) else dict(x); cid=str(x.get('id','')).strip()
        if not cid or cid in causes: raise ModelError(f'BAD_CAUSE:{cid}')
        prior=float(x.get('prior',1.0)); target=str(x.get('target_class',cid)).strip()
        if prior<=0 or not math.isfinite(prior): raise ModelError(f'BAD_PRIOR:{cid}')
        causes[cid]={'target_class':target,'prior':prior}; total+=prior
    if len(causes)<2: raise ModelError('NEED_2_CAUSES')
    for c in causes.values(): c['prior']/=total
    tests={}
    for x in d.get('tests',[]):
        x=dict(x); tid=str(x.get('id','')).strip(); cost=float(x.get('cost',1.0))
        if not tid or tid in tests: raise ModelError(f'BAD_TEST:{tid}')
        if cost<0 or not math.isfinite(cost): raise ModelError(f'BAD_COST:{tid}')
        available=bool(x.get('available',True)); usable=bool(x.get('decision_usable',True)); outcomes={str(k):str(v) for k,v in dict(x.get('outcome_by_cause',{})).items()}
        if available and usable and set(outcomes)!=set(causes): raise ModelError(f'OUTCOME_MAP_MISMATCH:{tid}')
        tests[tid]={'cost':cost,'available':available,'usable':usable,'depends_on':tuple(map(str,x.get('depends_on',[]))),'failure_domains':frozenset(map(str,x.get('failure_domains',[]))),'outcomes':outcomes}
    for tid,t in tests.items():
        if any(dep not in tests for dep in t['depends_on']): raise ModelError(f'UNKNOWN_DEP:{tid}')
    acquired=frozenset(map(str,d.get('already_acquired',[])))
    if acquired-set(tests): raise ModelError('UNKNOWN_ACQUIRED')
    r=dict(d.get('requirements',{})); r.setdefault('max_decision_tests',18); r.setdefault('max_states',200000); r.setdefault('max_nonadaptive_tests',18); r.setdefault('require_failure_domain_disjoint_path',False); r.setdefault('objective','expected_cost_then_worst_case_then_test_id')
    for k in ('max_decision_tests','max_states','max_nonadaptive_tests'): r[k]=int(r[k])
    return causes,tests,acquired,r

def targets(rem,causes): return frozenset(causes[c]['target_class'] for c in rem)
def identified(rem,causes): return len(targets(rem,causes))<=1

def weights(rem,causes):
    z=sum(causes[c]['prior'] for c in rem); return {c:causes[c]['prior']/z for c in rem}

def partition(rem,tid,tests):
    out={}
    for c in rem: out.setdefault(tests[tid]['outcomes'][c],set()).add(c)
    return {k:frozenset(v) for k,v in sorted(out.items())}

def available(tid,acq,used_fd,tests,r):
    t=tests[tid]
    if tid in acq or not t['available'] or not t['usable'] or any(dep not in acq for dep in t['depends_on']): return False
    if r['require_failure_domain_disjoint_path'] and (not t['failure_domains'] or not used_fd.isdisjoint(t['failure_domains'])): return False
    return True

def next_fd(used,tid,tests,r): return frozenset(set(used)|set(tests[tid]['failure_domains'])) if r['require_failure_domain_disjoint_path'] else frozenset()

def entropy(rem,causes): return -sum(p*math.log2(p) for p in weights(rem,causes).values())

def rank(rem,acq,used,causes,tests,r):
    base=entropy(rem,causes); w=weights(rem,causes); rows=[]
    for tid in sorted(tests):
        if not available(tid,acq,used,tests,r): continue
        post=0.0; probs={}
        for o,s in partition(rem,tid,tests).items():
            p=sum(w[c] for c in s); probs[o]=p; post+=p*entropy(s,causes)
        gain=base-post; cost=tests[tid]['cost']; gpc='INF' if cost==0 and gain>0 else (gain/cost if cost else 0.0)
        rows.append({'test_id':tid,'cost':cost,'expected_information_gain_bits':round(gain,12),'gain_per_cost':gpc,'outcome_probabilities':{k:round(v,12) for k,v in probs.items()},'unlocks':sorted(x for x,t in tests.items() if tid in t['depends_on'])})
    def key(x): return (-(1e100 if x['gain_per_cost']=='INF' else x['gain_per_cost']),-x['expected_information_gain_bits'],x['cost'],x['test_id'])
    return sorted(rows,key=key)

def closure(selected,tests,acquired):
    out=set(acquired); stack=list(selected)
    while stack:
        tid=stack.pop()
        if tid in out: continue
        t=tests[tid]
        if not t['available'] or not t['usable']: return None
        out.add(tid); stack.extend(dep for dep in t['depends_on'] if dep not in out)
    return frozenset(out)

def fixed_identifies(evidence,causes,tests):
    order=sorted(evidence)
    for a,b in itertools.combinations(sorted(causes),2):
        if causes[a]['target_class']==causes[b]['target_class']: continue
        if tuple(tests[t]['outcomes'][a] for t in order if tests[t]['usable'])==tuple(tests[t]['outcomes'][b] for t in order if tests[t]['usable']): return False
    return True

def nonadaptive(causes,tests,acquired,r):
    decisions=sorted(t for t,x in tests.items() if x['available'] and x['usable'] and t not in acquired)
    if len(decisions)>r['max_nonadaptive_tests']: return {'status':'UNKNOWN_RESOURCE_LIMIT','exact':False}
    best=None; bestset=None; seen=set()
    for mask in range(1<<len(decisions)):
        s=frozenset(decisions[i] for i in range(len(decisions)) if mask>>i&1); c=closure(s,tests,acquired)
        if c is None or c in seen: continue
        seen.add(c)
        if not fixed_identifies(c,causes,tests): continue
        inc=c-acquired; obj=(round(sum(tests[t]['cost'] for t in inc),12),len(inc),tuple(sorted(inc)))
        if best is None or obj<best: best,bestset=obj,c
    if bestset is None: return {'status':'NON_IDENTIFIABLE_UNDER_CURRENT_MEASUREMENT_MODEL','exact':True}
    return {'status':'EXACT_NONADAPTIVE_MINIMUM_FOUND','exact':True,'additional_tests':sorted(bestset-acquired),'cost':best[0]}

def solve(d,source='MODEL'):
    causes,tests,acq0,r=parse(d); allc=frozenset(causes); baseline=nonadaptive(causes,tests,acq0,r); decisions=sum(1 for t,x in tests.items() if x['available'] and x['usable'] and t not in acq0)
    if decisions>r['max_decision_tests']: return {'schema':'janus.eye.r4_2.adaptive_policy_receipt.v1','artifact_id':d.get('id',source),'status':'UNKNOWN_RESOURCE_LIMIT','reason':'DECISION_TEST_COUNT_EXCEEDS_EXACT_CEILING','decision_test_count':decisions,'max_decision_tests':r['max_decision_tests'],'nonadaptive_baseline':baseline,'source_git_commit':os.getenv('GITHUB_SHA','LOCAL_OR_UNKNOWN'),'authority':'NO_POLICY_OPTIMALITY_CLAIM'}
    counter={'n':0,'limit':False}; policy={}
    @functools.lru_cache(None)
    def dp(rem_t,acq_t,fd_t):
        counter['n']+=1
        if counter['n']>r['max_states']: counter['limit']=True; return INF,INF,None
        rem=frozenset(rem_t); acq=frozenset(acq_t); used=frozenset(fd_t)
        if identified(rem,causes): return 0.0,0.0,{'terminal':True}
        w=weights(rem,causes); best=(INF,INF,None); record=None
        for tid in sorted(tests):
            if not available(tid,acq,used,tests,r): continue
            parts=partition(rem,tid,tests)
            if len(parts)==1 and not any(tid in x['depends_on'] and j not in acq and x['available'] and x['usable'] for j,x in tests.items()): continue
            nacq=frozenset(set(acq)|{tid}); nfd=next_fd(used,tid,tests,r); ef=0.0; wf=0.0; ok=True
            for _,s in parts.items():
                p=sum(w[c] for c in s); ce,cw,_=dp(tuple(sorted(s)),tuple(sorted(nacq)),tuple(sorted(nfd)))
                if not math.isfinite(ce): ok=False; break
                ef+=p*ce; wf=max(wf,cw)
            if not ok: continue
            et=tests[tid]['cost']+ef; wt=tests[tid]['cost']+wf; cand=(round(et,12),round(wt,12),tid)
            if cand<best: best=cand; record={'test_id':tid,'expected':et,'worst':wt}
        key=(rem_t,acq_t,fd_t)
        if record is not None: policy[key]=record; return best[0],best[1],record
        return INF,INF,None
    expected,worst,root=dp(tuple(sorted(allc)),tuple(sorted(acq0)),tuple())
    common={'schema':'janus.eye.r4_2.adaptive_policy_receipt.v1','artifact_id':d.get('id',source),'nonadaptive_baseline':baseline,'source_git_commit':os.getenv('GITHUB_SHA','LOCAL_OR_UNKNOWN')}
    if counter['limit']: return {**common,'status':'UNKNOWN_RESOURCE_LIMIT','reason':'STATE_COUNT_EXCEEDS_EXACT_CEILING','states_visited':counter['n'],'max_states':r['max_states'],'authority':'NO_POLICY_OPTIMALITY_CLAIM'}
    if root is None or not math.isfinite(expected): return {**common,'status':'NON_IDENTIFIABLE_UNDER_CURRENT_MEASUREMENT_MODEL','exact_policy_search_completed':True,'states_visited':counter['n'],'remaining_causes':sorted(allc),'remaining_target_classes':sorted(targets(allc,causes)),'root_greedy_next_test_ranking':rank(allc,acq0,frozenset(),causes,tests,r),'authority':'ADAPTIVE_NON_IDENTIFIABILITY_UNDER_DECLARED_DETERMINISTIC_OUTCOME_MODEL_ONLY','firewalls':['NON_IDENTIFIABLE != FALSE','DETERMINISTIC_OUTCOME_MODEL != TRUE_WORLD','SOFT_UNCALIBRATED_TEST != BINARY_DISCRIMINATOR','GREEDY_RANKING != POLICY_PROOF']}
    node_ids={}; nodes=[]
    def walk(rem,acq,used):
        key=(tuple(sorted(rem)),tuple(sorted(acq)),tuple(sorted(used)))
        if key in node_ids: return node_ids[key]
        nid=f'N{len(node_ids):04d}'; node_ids[key]=nid
        if identified(rem,causes): nodes.append({'node_id':nid,'terminal':True,'remaining_causes':sorted(rem),'identified_target_class':next(iter(targets(rem,causes))),'acquired_tests':sorted(acq)}); return nid
        rec=policy[key]; tid=rec['test_id']; nacq=frozenset(set(acq)|{tid}); nfd=next_fd(used,tid,tests,r); w=weights(rem,causes); branches=[]
        for o,s in partition(rem,tid,tests).items(): branches.append({'outcome':o,'probability':round(sum(w[c] for c in s),12),'child_node_id':walk(s,nacq,nfd),'remaining_causes':sorted(s),'remaining_target_classes':sorted(targets(s,causes))})
        nodes.append({'node_id':nid,'terminal':False,'remaining_causes':sorted(rem),'remaining_target_classes':sorted(targets(rem,causes)),'acquired_tests':sorted(acq),'next_test':tid,'immediate_cost':tests[tid]['cost'],'expected_total_cost_from_state':round(rec['expected'],12),'worst_case_total_cost_from_state':round(rec['worst'],12),'branches':branches}); return nid
    root_id=walk(allc,acq0,frozenset()); basecost=baseline.get('cost') if baseline.get('status')=='EXACT_NONADAPTIVE_MINIMUM_FOUND' else None
    return {**common,'status':'EXACT_ADAPTIVE_POLICY_FOUND','exact_policy_search_completed':True,'objective':r['objective'],'root_node_id':root_id,'root_next_test':root['test_id'],'expected_cost_to_identification':round(expected,12),'worst_case_cost_to_identification':round(worst,12),'expected_cost_savings_vs_nonadaptive':None if basecost is None else round(basecost-expected,12),'states_visited':counter['n'],'policy_node_count':len(nodes),'policy_nodes':sorted(nodes,key=lambda x:x['node_id']),'root_greedy_next_test_ranking':rank(allc,acq0,frozenset(),causes,tests,r),'authority':'EXACT_OPTIMAL_POLICY_UNDER_DECLARED_DETERMINISTIC_OUTCOME_AND_PRIOR_MODEL__NOT_TRUE_CAUSE_PROOF','firewalls':['ADAPTIVE_POLICY != CAUSAL_TRUTH','PRIOR != EVIDENCE','EXPECTED_COST_OPTIMUM != WORST_CASE_OPTIMUM','DETERMINISTIC_OUTCOME_MODEL != TRUE_WORLD','SOFT_UNCALIBRATED_TEST != BINARY_DISCRIMINATOR','GREEDY_NEXT_TEST != OPTIMAL_POLICY','NON_IDENTIFIABLE != FALSE']}

def write_outputs(model_path,receipt,outdir):
    outdir.mkdir(parents=True,exist_ok=True)
    payloads={
      'adaptive_policy_receipt.json':receipt,
      'policy_tree.json':{'schema':'janus.eye.r4_2.policy_tree.v1','artifact_id':receipt.get('artifact_id'),'status':receipt.get('status'),'root_node_id':receipt.get('root_node_id'),'policy_nodes':receipt.get('policy_nodes',[]),'source_git_commit':receipt.get('source_git_commit')},
      'next_test_ranking.json':{'schema':'janus.eye.r4_2.next_test_ranking.v1','artifact_id':receipt.get('artifact_id'),'status':receipt.get('status'),'root_greedy_next_test_ranking':receipt.get('root_greedy_next_test_ranking',[]),'warning':'Greedy ranking is diagnostic only; exact adaptive policy controls when available.','source_git_commit':receipt.get('source_git_commit')},
      'policy_summary.json':{'schema':'janus.eye.r4_2.policy_summary.v1','artifact_id':receipt.get('artifact_id'),'status':receipt.get('status'),'root_next_test':receipt.get('root_next_test'),'expected_cost_to_identification':receipt.get('expected_cost_to_identification'),'worst_case_cost_to_identification':receipt.get('worst_case_cost_to_identification'),'nonadaptive_baseline':receipt.get('nonadaptive_baseline'),'expected_cost_savings_vs_nonadaptive':receipt.get('expected_cost_savings_vs_nonadaptive'),'source_model':str(model_path),'source_git_commit':receipt.get('source_git_commit'),'epistemic_ceiling':receipt.get('authority')}
    }
    for name,p in payloads.items(): (outdir/name).write_text(json.dumps(p,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--output-dir',required=True); a=ap.parse_args(); p=Path(a.input); d=json.loads(p.read_text(encoding='utf-8')); receipt=solve(d,p.stem); write_outputs(p,receipt,Path(a.output_dir)); print(json.dumps({'status':receipt.get('status'),'root_next_test':receipt.get('root_next_test'),'expected_cost_to_identification':receipt.get('expected_cost_to_identification'),'worst_case_cost_to_identification':receipt.get('worst_case_cost_to_identification'),'nonadaptive_baseline':receipt.get('nonadaptive_baseline')},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
