#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,random,statistics
from collections import Counter,defaultdict
from pathlib import Path
import janus_linear_a_r7_arithmetic_summary_role_v0_1 as b0
import janus_linear_a_r7_positional_template_roles_v0_1 as c0
import janus_linear_a_r7_formula_slot_completion_v0_1 as stats
FROZEN_COMMIT='43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--corpus',required=True);ap.add_argument('--spec',required=True);ap.add_argument('--parent-canonical',required=True);ap.add_argument('--c0-result',required=True);ap.add_argument('--out',required=True);a=ap.parse_args();spec=json.load(open(a.spec,encoding='utf-8'));parent=json.load(open(a.parent_canonical,encoding='utf-8'));p0=json.load(open(a.c0_result,encoding='utf-8'))
 assert parent['version']=='v2.28' and parent['status']=='CURRENT_CANONICAL_RESEARCH_STATE';assert spec['source'] if 'source' in spec else True
 assert p0['admitted_candidate_count']==8 and spec['frozen_candidate_count']==8;adm=p0['admitted_candidates'];frozen={(x['role'],x['word_token']) for x in adm};assert len(frozen)==8
 docs,reveal,failures=b0.load_corpus(Path(a.corpus));perm_n=spec['null_operator']['permutations'];base_seed=spec['null_operator']['seed'];cfg=spec['candidate_gate'];labels={(x['role'],x['word_token']):x['source_word_after_scoring'] for x in adm};results=[]
 roles=sorted({r for r,_ in frozen})
 for role in roles:
  candidates=sorted(w for r,w in frozen if r==role);cset=set(candidates);obs=[x for x in c0.role_observations(docs) if x['role']==role];by_region=defaultdict(list)
  for x in obs:by_region[x['region']].append((x['word'],bool(x['match'])))
  observed={w:{'n':sum(x['word']==w for x in obs),'k':sum(x['word']==w and x['match'] for x in obs)} for w in candidates}
  ge=Counter();sumrate=Counter();sumsq=Counter();seed=base_seed+int(hashlib.sha256(role.encode()).hexdigest()[:8],16);rng=random.Random(seed)
  region_data={r:( [w for w,_ in rows], [m for _,m in rows]) for r,rows in by_region.items()}
  for _ in range(perm_n):
   hits=Counter()
   for r,(words0,matches) in region_data.items():
    words=list(words0);rng.shuffle(words)
    for w,m in zip(words,matches):
     if m and w in cset:hits[w]+=1
   for w in candidates:
    n=observed[w]['n'];rate=(hits[w]/n) if n else 0.0;sumrate[w]+=rate;sumsq[w]+=rate*rate
    if hits[w]>=observed[w]['k']:ge[w]+=1
  for w in candidates:
   n=observed[w]['n'];k=observed[w]['k'];rate=k/n if n else 0.0;mean=sumrate[w]/perm_n if perm_n else None;var=(sumsq[w]/perm_n-mean*mean) if perm_n else None;p=(1+ge[w])/(1+perm_n);results.append({'role':role,'word_token':w,'observed_occurrences':n,'observed_matches':k,'observed_match_rate':rate,'null_mean_match_rate':mean,'null_sd_match_rate':(var**0.5 if var is not None and var>0 else 0.0),'observed_minus_null_mean_rate':rate-mean,'permutations':perm_n,'empirical_p':p,'source_word_after_scoring':labels[(role,w)]})
 q=stats.bh_qvalues([{'p_value':x['empirical_p']} for x in results])
 for x,qv in zip(results,q):
  x['BH_q']=qv;x['C2_STRUCTURE_DEPENDENCE_PASS']=bool(x['observed_occurrences']>=cfg['minimum_observed_occurrences'] and x['observed_match_rate']>=cfg['minimum_observed_match_rate'] and x['observed_minus_null_mean_rate']>=cfg['minimum_observed_minus_null_mean_rate'] and qv<=cfg['FDR_q_max'])
 survivors=[x for x in results if x['C2_STRUCTURE_DEPENDENCE_PASS']];status='STRUCTURE_DESTROYING_NULL_SURVIVORS_PRESENT' if survivors else 'STRUCTURE_DESTROYING_NULL_SURVIVORS_NOT_ESTABLISHED';out={'artifact_uuid':'JANUS-LINEAR-A-R7-C2-STRUCTURE-DESTROYING-NULL-RESULT-2026-08-15-v0.1','version':'v0.1','status':status,'source':{'frozen_commit':FROZEN_COMMIT,'parsed_documents':len(docs),'parse_failures_or_empty':failures},'frozen_candidate_count':8,'candidate_family_changed':False,'null_operator':spec['null_operator'],'candidate_results':results,'survivor_count':len(survivors),'survivors':survivors,'leakage_firewall':{'new_candidates_added':False,'candidates_removed':False,'roles_changed':False,'thresholds_changed':False,'source_labels_used_inside_permutation':False,'translations_used':False,'external_dictionaries_used':False,'Linear_B_supervision_used':False,'Notti_readings_used':False},'epistemic_gate':{'structure_dependent_candidates_established':bool(survivors),'probable_function_established':False,'exact_word_meaning_established':False,'translation_established':False,'phonetic_value_established':False,'new_anchor_established':False,'decipherment_established':False,'R3B_external_replication_established':False},'claim_ceiling':spec['claim_ceiling']};Path(a.out).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':status,'survivors':len(survivors)},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
