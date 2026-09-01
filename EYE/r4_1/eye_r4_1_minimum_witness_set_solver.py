#!/usr/bin/env python3
from __future__ import annotations
import argparse, itertools, json, os
from pathlib import Path

class ModelError(ValueError): pass

def pair(a,b):
    if a==b: raise ModelError(f'SELF_PAIR:{a}')
    return tuple(sorted((str(a),str(b))))

def parse(d):
    causes={}
    for x in d.get('cause_classes',[]):
        x={'id':x} if isinstance(x,str) else x
        cid=str(x.get('id','')).strip(); target=str(x.get('target_class',cid)).strip()
        if not cid or cid in causes: raise ModelError(f'BAD_CAUSE:{cid}')
        causes[cid]=target
    if len(causes)<2: raise ModelError('NEED_2_CAUSES')
    tests={}
    for x in d.get('tests',[]):
        wid=str(x.get('id','')).strip()
        if not wid or wid in tests: raise ModelError(f'BAD_TEST:{wid}')
        cost=float(x.get('cost',1));
        if cost<0: raise ModelError(f'NEGATIVE_COST:{wid}')
        distinguishes=set()
        for p in x.get('distinguishes',[]):
            if len(p)!=2 or str(p[0]) not in causes or str(p[1]) not in causes: raise ModelError(f'BAD_PAIR:{wid}:{p}')
            distinguishes.add(pair(*p))
        tests[wid]={
            'id':wid,'cost':cost,'distinguishes':distinguishes,
            'depends_on':tuple(map(str,x.get('depends_on',[]))),
            'failure_domains':frozenset(map(str,x.get('failure_domains',[]))),
            'available':bool(x.get('available',True)),
            'meta':{k:v for k,v in x.items() if k not in {'id','cost','distinguishes','depends_on','failure_domains','available'}}}
    for wid,t in tests.items():
        for dep in t['depends_on']:
            if dep not in tests: raise ModelError(f'UNKNOWN_DEP:{wid}:{dep}')
    acquired=frozenset(map(str,d.get('already_acquired',[])))
    if acquired-set(tests): raise ModelError(f'UNKNOWN_ACQUIRED:{sorted(acquired-set(tests))}')
    r=dict(d.get('requirements',{})); r.setdefault('required_independent_separators_per_pair',1); r.setdefault('unknown_independence_conflicts',True); r.setdefault('max_exact_tests',20); r.setdefault('max_tied_solutions',20)
    r['required_independent_separators_per_pair']=int(r['required_independent_separators_per_pair']); r['max_exact_tests']=int(r['max_exact_tests']); r['max_tied_solutions']=int(r['max_tied_solutions'])
    if r['required_independent_separators_per_pair']<1: raise ModelError('BAD_K')
    return causes,tests,r,acquired

def rivals(causes):
    return frozenset((a,b) for a,b in itertools.combinations(sorted(causes),2) if causes[a]!=causes[b])

def closure(selected,tests,base):
    out=set(base); stack=list(selected)
    while stack:
        wid=stack.pop()
        if wid in out: continue
        t=tests[wid]
        if not t['available'] and wid not in base: return None
        out.add(wid)
        for dep in t['depends_on']:
            if dep not in out:
                if not tests[dep]['available'] and dep not in base: return None
                stack.append(dep)
    return frozenset(out)

def independent(a,b,tests,unknown_conflicts):
    A=tests[a]['failure_domains']; B=tests[b]['failure_domains']
    if not A or not B: return not unknown_conflicts
    return A.isdisjoint(B)

def max_independent(ids,tests,unknown_conflicts):
    ids=sorted(ids)
    for n in range(len(ids),0,-1):
        for c in itertools.combinations(ids,n):
            if all(independent(a,b,tests,unknown_conflicts) for a,b in itertools.combinations(c,2)): return n,list(c)
    return 0,[]

def evaluate(evidence,pairs,tests,r):
    k=r['required_independent_separators_per_pair']; details={}; unresolved=[]
    for p in sorted(pairs):
        seps=[wid for wid in evidence if p in tests[wid]['distinguishes']]
        n,example=max_independent(seps,tests,bool(r['unknown_independence_conflicts']))
        details[p]={'separators_present':sorted(seps),'max_failure_mode_independent_separators':n,'independent_separator_example':example,'required':k,'resolved':n>=k}
        if n<k: unresolved.append(p)
    return {'identifiable':not unresolved,'unresolved':frozenset(unresolved),'details':details}

def cost(evidence,tests,acquired): return sum(tests[x]['cost'] for x in evidence if x not in acquired)

def search(causes,tests,r,acquired):
    ps=rivals(causes); base=evaluate(acquired,ps,tests,r); decisions=sorted(x for x,t in tests.items() if t['available'] and x not in acquired)
    if base['identifiable']: return {'status':'EXACT_BASELINE_ALREADY_IDENTIFIABLE','exact':True,'pairs':ps,'solutions':[acquired],'best_partial':acquired,'examined':1,'evaluated':1,'decisions':len(decisions)}
    if len(decisions)>r['max_exact_tests']: return {'status':'UNKNOWN_RESOURCE_LIMIT','exact':False,'pairs':ps,'solutions':[],'best_partial':acquired,'examined':0,'evaluated':0,'decisions':len(decisions)}
    seen=set(); best=None; sols=[]; best_partial=acquired; bestp=(len(base['unresolved']),0.0,0,()) ; examined=evaluated=0
    for mask in range(1<<len(decisions)):
        examined+=1; chosen=[decisions[i] for i in range(len(decisions)) if mask>>i&1]; c=closure(chosen,tests,acquired)
        if c is None or c in seen: continue
        seen.add(c); obj=(round(cost(c,tests,acquired),12),len(c-acquired))
        if best is not None and obj>best: continue
        ev=evaluate(c,ps,tests,r); evaluated+=1; pk=(len(ev['unresolved']),obj[0],obj[1],tuple(sorted(c-acquired)))
        if pk<bestp: bestp=pk; best_partial=c
        if not ev['identifiable']: continue
        if best is None or obj<best: best=obj; sols=[c]
        elif obj==best and len(sols)<r['max_tied_solutions']: sols.append(c)
    return {'status':'EXACT_MINIMUM_FOUND' if sols else 'NON_IDENTIFIABLE_UNDER_CURRENT_MEASUREMENT_MODEL','exact':True,'pairs':ps,'solutions':sorted(set(sols),key=lambda s:(cost(s,tests,acquired),len(s-acquired),tuple(sorted(s)))),'best_partial':best_partial,'examined':examined,'evaluated':evaluated,'decisions':len(decisions)}

def forced_remove(evidence,removed,tests,acquired):
    keep=set(evidence); keep.discard(removed); changed=True
    while changed:
        changed=False
        for wid in list(keep):
            if wid in acquired and wid!=removed: continue
            if any(dep not in keep for dep in tests[wid]['depends_on']): keep.remove(wid); changed=True
    return frozenset(keep)

def rank_single(base,tests,r,pairs,unavailable=False):
    b=evaluate(base,pairs,tests,r); out=[]
    for wid,t in sorted(tests.items()):
        if wid in base or ((not t['available'])!=unavailable): continue
        c=frozenset(set(base)|{wid}) if unavailable else closure([wid],tests,base)
        if c is None: continue
        e=evaluate(c,pairs,tests,r); gain=len(b['unresolved'])-len(e['unresolved']); inc=sum(tests[x]['cost'] for x in c-base)
        out.append({'test_id':wid,'available':t['available'],'newly_resolved_pair_count':gain,'remaining_unresolved_pair_count':len(e['unresolved']),'incremental_bundle':sorted(c-base),'incremental_cost':inc,'gain_per_cost':'INF' if inc==0 and gain else (gain/inc if inc else 0)})
    return sorted(out,key=lambda x:(-x['newly_resolved_pair_count'],-(10**9 if x['gain_per_cost']=='INF' else x['gain_per_cost']),x['incremental_cost'],x['test_id']))

def outputs(model_path,d,causes,tests,r,acquired,s):
    ps=s['pairs']; sols=s['solutions']; chosen=sols[0] if sols else s['best_partial']; ev=evaluate(chosen,ps,tests,r)
    verdict='IDENTIFIABILITY_CANDIDATE' if s['status'].startswith('EXACT_') else s['status']
    cause={'schema':'janus.eye.r4_1.cause_class_catalog.v1','source_model':str(model_path),'cause_classes':[{'id':x,'target_class':causes[x]} for x in sorted(causes)],'rival_pairs':[list(p) for p in sorted(ps)]}
    witness={'schema':'janus.eye.r4_1.witness_catalog.v1','already_acquired':sorted(acquired),'tests':[{'id':x,'cost':tests[x]['cost'],'available':tests[x]['available'],'depends_on':list(tests[x]['depends_on']),'failure_domains':sorted(tests[x]['failure_domains']),'distinguishes':[list(p) for p in sorted(tests[x]['distinguishes'])],'metadata':tests[x]['meta']} for x in sorted(tests)]}
    ind={'schema':'janus.eye.r4_1.independence_matrix.v1','unknown_independence_conflicts':bool(r['unknown_independence_conflicts']),'pairs':[{'a':a,'b':b,'independent_under_model':independent(a,b,tests,bool(r['unknown_independence_conflicts'])),'shared_failure_domains':sorted(tests[a]['failure_domains']&tests[b]['failure_domains'])} for a,b in itertools.combinations(sorted(tests),2)]}
    matrix={'schema':'janus.eye.r4_1.pairwise_discrimination_matrix.v1','required_independent_separators_per_pair':r['required_independent_separators_per_pair'],'pairs':[{'cause_pair':list(p),'candidate_separators':sorted(x for x in tests if p in tests[x]['distinguishes']),'selected_pair_evaluation':ev['details'][p]} for p in sorted(ps)]}
    mins={'schema':'janus.eye.r4_1.minimum_witness_sets.v1','search_status':s['status'],'exact':s['exact'],'solutions':[{'additional_tests':sorted(x-acquired),'full_evidence_set':sorted(x),'incremental_cost':cost(x,tests,acquired),'unresolved_pairs':[list(p) for p in sorted(evaluate(x,ps,tests,r)['unresolved'])]} for x in sols],'best_partial':{'additional_tests':sorted(chosen-acquired),'incremental_cost':cost(chosen,tests,acquired),'unresolved_pairs':[list(p) for p in sorted(ev['unresolved'])]},'search_accounting':{'decision_test_count':s['decisions'],'subsets_examined':s['examined'],'unique_dependency_closed_sets_evaluated':s['evaluated'],'max_exact_tests':r['max_exact_tests']}}
    loo=[]
    if sols:
        for wid in sorted(chosen-acquired):
            rem=forced_remove(chosen,wid,tests,acquired); e=evaluate(rem,ps,tests,r); loo.append({'removed_test':wid,'remaining_evidence_after_dependency_prune':sorted(rem),'still_identifiable':e['identifiable'],'new_unresolved_pairs':[list(p) for p in sorted(e['unresolved'])],'required_for_this_solution':not e['identifiable']})
    leave={'schema':'janus.eye.r4_1.leave_one_out_receipt.v1','status':'SUBSET_MINIMAL' if loo and all(x['required_for_this_solution'] for x in loo) else ('NOT_APPLICABLE_NO_FULL_SOLUTION' if not sols else 'REDUNDANCY_PRESENT'),'rows':loo}
    unresolved={'schema':'janus.eye.r4_1.unresolved_equivalence_classes.v1','semantics':'Unresolved pair graph; not a claim of transitive mathematical equivalence.','unresolved_pairs':[list(p) for p in sorted(ev['unresolved'])]}
    nextbest={'schema':'janus.eye.r4_1.next_best_tests.v1','base_evidence':sorted(acquired),'available_ranked':rank_single(acquired,tests,r,ps,False),'unavailable_counterfactual_value_ranked':rank_single(acquired,tests,r,ps,True),'warning':'Unavailable test value is counterfactual planning information only.'}
    receipt={'schema':'janus.eye.r4_1.solver_receipt.v1','artifact_id':d.get('id',model_path.stem),'status':verdict,'search_status':s['status'],'source_git_commit':os.getenv('GITHUB_SHA','LOCAL_OR_UNKNOWN'),'exact_minimum_proved_under_declared_measurement_model':bool(s['exact'] and s['status'].startswith('EXACT_')),'chosen_additional_tests':sorted(chosen-acquired) if sols else [],'chosen_incremental_cost':cost(chosen,tests,acquired) if sols else None,'remaining_unresolved_pairs':[list(p) for p in sorted(ev['unresolved'])],'requirements':r,'authority':'PLANNING_MODEL_ONLY__DISCRIMINATION_AND_INDEPENDENCE_EDGES_REQUIRE_DOMAIN_JUSTIFICATION','firewalls':['OUTPUT_SYMBOL != CAUSE','MORE_EVIDENCE != MORE_INDEPENDENT_EVIDENCE','DEPENDENCY_CLOSURE_COUNTS_TOWARD_COST','UNKNOWN_INDEPENDENCE != INDEPENDENCE','HEURISTIC_RANKING != MINIMUM_PROOF','NON_IDENTIFIABLE != FALSE','CAUSE_CLASS_RECOVERY != EXACT_MECHANISM_RECOVERY']}
    return {'cause_class_catalog.json':cause,'witness_catalog.json':witness,'independence_matrix.json':ind,'pairwise_discrimination_matrix.json':matrix,'minimum_witness_sets.json':mins,'leave_one_out_receipt.json':leave,'unresolved_equivalence_classes.json':unresolved,'next_best_tests.json':nextbest,'solver_receipt.json':receipt}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--output-dir',required=True); a=ap.parse_args(); p=Path(a.input); d=json.loads(p.read_text()); causes,tests,r,acquired=parse(d); s=search(causes,tests,r,acquired); out=outputs(p,d,causes,tests,r,acquired,s); od=Path(a.output_dir); od.mkdir(parents=True,exist_ok=True)
    for name,payload in out.items(): (od/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:out['solver_receipt.json'][k] for k in ['status','search_status','chosen_additional_tests','chosen_incremental_cost']},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
