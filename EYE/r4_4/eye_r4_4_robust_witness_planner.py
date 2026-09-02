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
        tests[tid]={'cost':cost,'available':available,'usable':usable,'calibrated':calibrated,'depends_on':tuple(map(str,x.get('depends_on',[]))),'failure_domains':frozenset(map(str,x.get('failure_domains',[]))),'likelihoods':likes,'outcomes':tuple(outcomes)}
    for tid,t in tests.items():
        if any(dep not in tests for dep in t['depends_on']): raise ModelError(f'UNKNOWN_DEP:{tid}')
    acquired=frozenset(map(str,d.get('already_acquired',[])))
    if acquired-set(tests): raise ModelError(f'UNKNOWN_ACQUIRED:{sorted(acquired-set(tests))}')
    raw_models=list(d.get('model_set',[]))
    if not raw_models: raise ModelError('NEED_DECLARED_MODEL_SET')
    models={}; weight_total=0.0
    for m in raw_models:
        m=dict(m); mid=str(m.get('id','')).strip()
        if not mid or mid in models: raise ModelError(f'BAD_MODEL:{mid}')
        provenance=str(m.get('provenance','')).strip()
        if not provenance: raise ModelError(f'MISSING_MODEL_PROVENANCE:{mid}')
        weight=float(m.get('weight',1.0))
        if weight<=0 or not math.isfinite(weight): raise ModelError(f'BAD_MODEL_WEIGHT:{mid}')
        priors={c:causes[c]['prior'] for c in causes}
        if 'prior_by_cause' in m:
            priors=norm_dist(m['prior_by_cause'],f'{mid}:priors')
            if set(priors)!=set(causes): raise ModelError(f'MODEL_PRIOR_MISMATCH:{mid}')
        likes={tid:{c:dict(t['likelihoods'].get(c,{})) for c in causes} for tid,t in tests.items()}
        for tid,rows in dict(m.get('likelihood_overrides',{})).items():
            if tid not in tests: raise ModelError(f'MODEL_UNKNOWN_TEST:{mid}:{tid}')
            if set(rows)!=set(causes): raise ModelError(f'MODEL_LIKELIHOOD_CAUSE_MISMATCH:{mid}:{tid}')
            tmp={c:norm_dist(rows[c],f'{mid}:{tid}:{c}') for c in causes}; outs=sorted(set().union(*(set(v) for v in tmp.values())))
            for c in causes: likes[tid][c]={o:tmp[c].get(o,0.0) for o in outs}
        models[mid]={'weight':weight,'provenance':provenance,'priors':priors,'likelihoods':likes}; weight_total+=weight
    for m in models.values(): m['weight']/=weight_total
    r=dict(d.get('requirements',{}))
    defaults={'confidence_threshold':0.95,'max_decision_tests':12,'max_states':200000,'require_failure_domain_disjoint_path':False,'allow_prior_only_identification':False,'belief_round_digits':10,'min_outcome_probability':0.0,'robust_objective':'minimax_expected_cost','cvar_alpha':0.8,'require_common_outcome_support':True}
    for k,v in defaults.items(): r.setdefault(k,v)
    for k in ('max_decision_tests','max_states','belief_round_digits'): r[k]=int(r[k])
    for k in ('confidence_threshold','min_outcome_probability','cvar_alpha'): r[k]=float(r[k])
    if not (0.5<r['confidence_threshold']<=1): raise ModelError('BAD_CONFIDENCE_THRESHOLD')
    if not (0<=r['min_outcome_probability']<1): raise ModelError('BAD_MIN_OUTCOME_PROB')
    if r['robust_objective'] not in ('minimax_expected_cost','cvar_model_expected_cost'): raise ModelError('BAD_ROBUST_OBJECTIVE')
    if not (0<r['cvar_alpha']<=1): raise ModelError('BAD_CVAR_ALPHA')
    return causes,tests,models,acquired,r

def canon_belief(b,causes,digits):
    vals=[max(0.0,float(b.get(c,0.0))) for c in sorted(causes)]; s=sum(vals)
    if s<=0: raise ModelError('ZERO_POSTERIOR_MASS')
    vals=[round(v/s,digits) for v in vals]; s=sum(vals)
    return tuple(round(v/s,digits) for v in vals)

def belief_dict(bt,causes): return {c:bt[i] for i,c in enumerate(sorted(causes))}
def target_posterior(bt,causes):
    out={}
    for c,p in belief_dict(bt,causes).items(): out[causes[c]['target_class']]=out.get(causes[c]['target_class'],0.0)+p
    return dict(sorted(out.items()))
def evidence_count(acq,tests): return sum(1 for tid in acq if tests[tid]['available'] and tests[tid]['usable'] and tests[tid]['calibrated'])

def robust_terminal(joint_bt,model_ids,causes,r,evidence_n):
    rows={}; winners=[]; prior_block=(evidence_n<=0 and not r['allow_prior_only_identification'])
    for i,mid in enumerate(model_ids):
        tp=target_posterior(joint_bt[i],causes); target,conf=max(tp.items(),key=lambda kv:(kv[1],kv[0])); rows[mid]={'target':target,'confidence':conf,'risk':1.0-conf,'posterior_by_target':tp}; winners.append((target,conf))
    same=len({t for t,_ in winners})==1; min_conf=min(c for _,c in winners); ok=same and min_conf+1e-12>=r['confidence_threshold'] and not prior_block
    return {'terminal':ok,'identified_target_class':winners[0][0] if ok else None,'minimum_model_confidence':min_conf,'maximum_model_risk':max(1.0-c for _,c in winners),'models':rows,'prior_only_blocked':prior_block}

def available(tid,acq,used_fd,tests,r):
    t=tests[tid]
    if tid in acq or not t['available'] or not t['usable'] or not t['calibrated'] or any(dep not in acq for dep in t['depends_on']): return False
    if r['require_failure_domain_disjoint_path'] and (not t['failure_domains'] or not used_fd.isdisjoint(t['failure_domains'])): return False
    return True

def next_fd(used,tid,tests,r): return frozenset(set(used)|set(tests[tid]['failure_domains'])) if r['require_failure_domain_disjoint_path'] else frozenset()

def model_predictive(bt,tid,mid,causes,models):
    b=belief_dict(bt,causes); likes=models[mid]['likelihoods'][tid]; outcomes=sorted(set().union(*(set(likes[c]) for c in causes)))
    return {o:sum(b[c]*likes[c].get(o,0.0) for c in causes) for o in outcomes}

def model_posterior(bt,tid,outcome,mid,causes,models,r):
    b=belief_dict(bt,causes); likes=models[mid]['likelihoods'][tid]; vals={c:b[c]*likes[c].get(outcome,0.0) for c in causes}; z=sum(vals.values())
    if z<=0: return None
    return canon_belief({c:v/z for c,v in vals.items()},causes,r['belief_round_digits'])

def cvar_upper(values_weights,alpha):
    pairs=sorted(((float(v),float(w)) for v,w in values_weights),reverse=True)
    if alpha>=1.0: return max(v for v,_ in pairs)
    tail=max(1e-15,1.0-alpha); need=tail; acc=0.0
    for v,w in pairs:
        take=min(w,need); acc+=take*v; need-=take
        if need<=1e-15: break
    if need>1e-12: acc+=need*pairs[-1][0]
    return acc/tail

def scalar_objective(cost_vec,models,r):
    if r['robust_objective']=='minimax_expected_cost': return max(cost_vec.values())
    return cvar_upper([(cost_vec[m],models[m]['weight']) for m in cost_vec],r['cvar_alpha'])

def joint_rank(joint_bt,model_ids,acq,used,causes,tests,models,r):
    rows=[]
    for tid in sorted(tests):
        if not available(tid,acq,used,tests,r): continue
        risks=[]; gains=[]; support_ok=True
        for i,mid in enumerate(model_ids):
            pred=model_predictive(joint_bt[i],tid,mid,causes,models); outcomes=[o for o,p in pred.items() if p>r['min_outcome_probability']]
            if not outcomes: support_ok=False; break
            before=max(target_posterior(joint_bt[i],causes).values()); expected_max=0.0
            for o,p in pred.items():
                if p<=r['min_outcome_probability']: continue
                nb=model_posterior(joint_bt[i],tid,o,mid,causes,models,r)
                if nb is None: continue
                expected_max+=p*max(target_posterior(nb,causes).values())
            risks.append(1.0-expected_max); gains.append(expected_max-before)
        if support_ok: rows.append({'test_id':tid,'cost':tests[tid]['cost'],'worst_expected_posterior_risk':round(max(risks),12),'minimum_expected_confidence_gain':round(min(gains),12),'failure_domains':sorted(tests[tid]['failure_domains'])})
    return sorted(rows,key=lambda x:(x['worst_expected_posterior_risk'],x['cost'],-x['minimum_expected_confidence_gain'],x['test_id']))

def single_model_feasible(mid,causes,tests,models,acq0,r):
    prior=canon_belief(models[mid]['priors'],causes,r['belief_round_digits'])
    @functools.lru_cache(None)
    def rec(bt,acq_t,fd_t):
        acq=frozenset(acq_t); used=frozenset(fd_t); tp=target_posterior(bt,causes); conf=max(tp.values())
        if conf+1e-12>=r['confidence_threshold'] and (evidence_count(acq,tests)>0 or r['allow_prior_only_identification']): return True
        for tid in sorted(tests):
            if not available(tid,acq,used,tests,r): continue
            pred=model_predictive(bt,tid,mid,causes,models); nacq=frozenset(set(acq)|{tid}); nfd=next_fd(used,tid,tests,r); ok=True; anyb=False
            for o,p in pred.items():
                if p<=r['min_outcome_probability']: continue
                nb=model_posterior(bt,tid,o,mid,causes,models,r)
                if nb is None: continue
                anyb=True
                if not rec(nb,tuple(sorted(nacq)),tuple(sorted(nfd))): ok=False; break
            if anyb and ok: return True
        return False
    return rec(prior,tuple(sorted(acq0)),tuple())

def solve(d,source='MODEL'):
    causes,tests,models,acq0,r=parse(d); model_ids=tuple(sorted(models)); prior_joint=tuple(canon_belief(models[m]['priors'],causes,r['belief_round_digits']) for m in model_ids)
    decisions=sum(1 for t,x in tests.items() if x['available'] and x['usable'] and x['calibrated'] and t not in acq0)
    common={'schema':'janus.eye.r4_4.robust_policy_receipt.v1','artifact_id':d.get('id',source),'source_git_commit':os.getenv('GITHUB_SHA','LOCAL_OR_UNKNOWN'),'confidence_threshold':r['confidence_threshold'],'robust_objective':r['robust_objective'],'model_ids':list(model_ids),'model_provenance':{m:models[m]['provenance'] for m in model_ids}}
    if len(models)<2: return {**common,'status':'DEGENERATE_MODEL_SET','authority':'NO_ROBUSTNESS_CLAIM_WITH_SINGLE_MODEL'}
    if decisions>r['max_decision_tests']: return {**common,'status':'UNKNOWN_RESOURCE_LIMIT','reason':'DECISION_TEST_COUNT_EXCEEDS_EXACT_CEILING','decision_test_count':decisions,'max_decision_tests':r['max_decision_tests'],'authority':'NO_POLICY_OPTIMALITY_CLAIM'}
    counter={'n':0,'limit':False}; policy={}
    @functools.lru_cache(None)
    def dp(joint_bt,acq_t,fd_t):
        counter['n']+=1
        if counter['n']>r['max_states']: counter['limit']=True; return None,None,None
        acq=frozenset(acq_t); used=frozenset(fd_t); term=robust_terminal(joint_bt,model_ids,causes,r,evidence_count(acq,tests))
        if term['terminal']: return {m:0.0 for m in model_ids},0.0,{'terminal':True}
        best_key=None; best_vec=None; best_rec=None
        for tid in sorted(tests):
            if not available(tid,acq,used,tests,r): continue
            preds={m:model_predictive(joint_bt[i],tid,m,causes,models) for i,m in enumerate(model_ids)}; outcomes=sorted(set().union(*(set(p) for p in preds.values())))
            if r['require_common_outcome_support']:
                bad=False
                for o in outcomes:
                    vals=[preds[m].get(o,0.0) for m in model_ids]
                    if max(vals)>r['min_outcome_probability'] and min(vals)<=r['min_outcome_probability']: bad=True; break
                if bad: continue
            branches=[]; child_by_out={}; ok=True; nacq=frozenset(set(acq)|{tid}); nfd=next_fd(used,tid,tests,r)
            for o in outcomes:
                if max(preds[m].get(o,0.0) for m in model_ids)<=r['min_outcome_probability']: continue
                child=[]
                for i,m in enumerate(model_ids):
                    nb=model_posterior(joint_bt[i],tid,o,m,causes,models,r)
                    if nb is None: ok=False; break
                    child.append(nb)
                if not ok: break
                child=tuple(child); cvec,_,_=dp(child,tuple(sorted(nacq)),tuple(sorted(nfd)))
                if cvec is None: ok=False; break
                child_by_out[o]=(child,cvec); branches.append((o,child))
            if not ok or not branches: continue
            vec={}
            for m in model_ids:
                exp=tests[tid]['cost']
                for o,_child in branches:
                    p=preds[m].get(o,0.0)
                    if p>r['min_outcome_probability']: exp+=p*child_by_out[o][1][m]
                vec[m]=exp
            scalar=scalar_objective(vec,models,r); child_max=max((max(cv.values()) for _,cv in child_by_out.values()),default=0.0); path_worst=tests[tid]['cost']+child_max; key=(round(scalar,12),round(max(vec.values()),12),round(path_worst,12),tid)
            if best_key is None or key<best_key:
                best_key=key; best_vec=vec; best_rec={'test_id':tid,'cost_vector':vec,'robust_scalar':scalar,'path_worst':path_worst,'branches':branches,'preds':preds}
        key=(joint_bt,tuple(sorted(acq)),tuple(sorted(used)))
        if best_rec is not None: policy[key]=best_rec; return best_vec,best_rec['robust_scalar'],best_rec
        return None,None,None
    vec,scalar,root=dp(prior_joint,tuple(sorted(acq0)),tuple())
    if counter['limit']: return {**common,'status':'UNKNOWN_RESOURCE_LIMIT','reason':'STATE_COUNT_EXCEEDS_EXACT_CEILING','states_visited':counter['n'],'max_states':r['max_states'],'authority':'NO_POLICY_OPTIMALITY_CLAIM'}
    root_term=robust_terminal(prior_joint,model_ids,causes,r,evidence_count(acq0,tests))
    if root_term['terminal']: return {**common,'status':'BASELINE_ALREADY_ROBUST_CONFIDENT','exact_policy_search_completed':True,'root_next_test':None,'robust_cost':0.0,'model_expected_costs':{m:0.0 for m in model_ids},'authority':'ROBUST_CONFIDENCE_THRESHOLD_MET_BY_DECLARED_BASELINE_MODEL_SET','root_model_states':root_term['models']}
    if root is None or vec is None:
        per={m:single_model_feasible(m,causes,tests,models,acq0,r) for m in model_ids}; status='MODEL_SET_TOO_WIDE_FOR_COMMON_ROBUST_IDENTIFICATION' if all(per.values()) else 'ROBUST_NON_IDENTIFIABLE_UNDER_DECLARED_MODEL_SET'
        return {**common,'status':status,'exact_policy_search_completed':True,'states_visited':counter['n'],'individual_model_feasibility':per,'root_model_states':root_term['models'],'root_robust_next_test_ranking':joint_rank(prior_joint,model_ids,acq0,frozenset(),causes,tests,models,r),'authority':'ROBUST_NON_IDENTIFIABILITY_ONLY_UNDER_DECLARED_FINITE_MODEL_SET_AND_TEST_SPACE','firewalls':['ROBUST_NON_IDENTIFIABLE != FALSE','MODEL_SET_TOO_WIDE != TRUE_WORLD_AMBIGUITY','MODEL_SET != TRUE_WORLD','PRIOR_SET != EVIDENCE','UNCALIBRATED_TEST != ROBUST_WITNESS']}
    node_ids={}; nodes=[]
    def walk(joint_bt,acq,used):
        key=(joint_bt,tuple(sorted(acq)),tuple(sorted(used)))
        if key in node_ids: return node_ids[key]
        nid=f'N{len(node_ids):04d}'; node_ids[key]=nid; term=robust_terminal(joint_bt,model_ids,causes,r,evidence_count(acq,tests))
        model_states={m:{'posterior_by_cause':{k:round(v,12) for k,v in belief_dict(joint_bt[i],causes).items()},'posterior_by_target':{k:round(v,12) for k,v in term['models'][m]['posterior_by_target'].items()},'best_target':term['models'][m]['target'],'confidence':round(term['models'][m]['confidence'],12),'risk':round(term['models'][m]['risk'],12)} for i,m in enumerate(model_ids)}
        if term['terminal']:
            nodes.append({'node_id':nid,'terminal':True,'acquired_tests':sorted(acq),'identified_target_class':term['identified_target_class'],'minimum_model_confidence':round(term['minimum_model_confidence'],12),'maximum_model_risk':round(term['maximum_model_risk'],12),'model_states':model_states}); return nid
        rec=policy[key]; tid=rec['test_id']; nacq=frozenset(set(acq)|{tid}); nfd=next_fd(used,tid,tests,r); branches=[]
        for o,child in rec['branches']: branches.append({'outcome':o,'child_node_id':walk(child,nacq,nfd),'probability_by_model':{m:round(rec['preds'][m].get(o,0.0),12) for m in model_ids}})
        nodes.append({'node_id':nid,'terminal':False,'acquired_tests':sorted(acq),'next_test':tid,'immediate_cost':tests[tid]['cost'],'robust_objective_value_from_state':round(rec['robust_scalar'],12),'model_expected_costs_from_state':{m:round(v,12) for m,v in rec['cost_vector'].items()},'model_states':model_states,'branches':branches}); return nid
    root_id=walk(prior_joint,acq0,frozenset())
    return {**common,'status':'EXACT_ROBUST_POLICY_FOUND','exact_policy_search_completed':True,'root_node_id':root_id,'root_next_test':root['test_id'],'robust_cost':round(scalar,12),'model_expected_costs':{m:round(v,12) for m,v in vec.items()},'worst_model_expected_cost':round(max(vec.values()),12),'states_visited':counter['n'],'policy_node_count':len(nodes),'policy_nodes':sorted(nodes,key=lambda x:x['node_id']),'root_robust_next_test_ranking':joint_rank(prior_joint,model_ids,acq0,frozenset(),causes,tests,models,r),'authority':'EXACT_OPTIMAL_ROBUST_POLICY_UNDER_DECLARED_FINITE_MODEL_SET_OBJECTIVE_AND_TEST_SPACE__NOT_CAUSAL_TRUTH','firewalls':['ROBUST_POLICY != CAUSAL_TRUTH','MODEL_SET != TRUE_WORLD','MODEL_PROVENANCE != MODEL_VALIDITY','MINIMAX_OPTIMAL != CALIBRATED','CVAR_OPTIMAL != CALIBRATED','ROBUST_STOP != FREQUENTIST_GUARANTEE','PRIOR_SET != EVIDENCE','ROBUST_NON_IDENTIFIABLE != FALSE']}

def write_outputs(model_path,receipt,outdir):
    outdir.mkdir(parents=True,exist_ok=True)
    payloads={
      'robust_policy_receipt.json':receipt,
      'policy_tree.json':{'schema':'janus.eye.r4_4.policy_tree.v1','artifact_id':receipt.get('artifact_id'),'status':receipt.get('status'),'root_node_id':receipt.get('root_node_id'),'policy_nodes':receipt.get('policy_nodes',[]),'source_git_commit':receipt.get('source_git_commit')},
      'model_set_receipt.json':{'schema':'janus.eye.r4_4.model_set_receipt.v1','artifact_id':receipt.get('artifact_id'),'model_ids':receipt.get('model_ids',[]),'model_provenance':receipt.get('model_provenance',{}),'robust_objective':receipt.get('robust_objective'),'status':receipt.get('status'),'warning':'Finite declared model set is an uncertainty contract, not proof that the true world is inside the set.','source_git_commit':receipt.get('source_git_commit')},
      'next_test_ranking.json':{'schema':'janus.eye.r4_4.next_test_ranking.v1','artifact_id':receipt.get('artifact_id'),'status':receipt.get('status'),'root_robust_next_test_ranking':receipt.get('root_robust_next_test_ranking',[]),'warning':'Ranking is diagnostic only; exact robust policy controls when available.','source_git_commit':receipt.get('source_git_commit')},
      'policy_summary.json':{'schema':'janus.eye.r4_4.policy_summary.v1','artifact_id':receipt.get('artifact_id'),'status':receipt.get('status'),'root_next_test':receipt.get('root_next_test'),'robust_cost':receipt.get('robust_cost'),'worst_model_expected_cost':receipt.get('worst_model_expected_cost'),'model_expected_costs':receipt.get('model_expected_costs'),'source_model':str(model_path),'source_git_commit':receipt.get('source_git_commit'),'epistemic_ceiling':receipt.get('authority')}
    }
    for name,p in payloads.items(): (outdir/name).write_text(json.dumps(p,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--output-dir',required=True); a=ap.parse_args(); p=Path(a.input); d=json.loads(p.read_text(encoding='utf-8')); receipt=solve(d,p.stem); write_outputs(p,receipt,Path(a.output_dir)); print(json.dumps({'status':receipt.get('status'),'root_next_test':receipt.get('root_next_test'),'robust_cost':receipt.get('robust_cost'),'worst_model_expected_cost':receipt.get('worst_model_expected_cost')},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
