#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,random,re
from collections import Counter,defaultdict
from pathlib import Path
import janus_linear_a_r7_arithmetic_summary_role_v0_1 as b0
import janus_linear_a_r7_positional_template_roles_v0_1 as c0
import janus_linear_a_r7_formula_slot_completion_v0_1 as stats
FROZEN_COMMIT='43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a'
def object_id(doc):return re.sub(r'(?<=[0-9>])[ab]$','',doc)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--corpus',required=True);ap.add_argument('--spec',required=True);ap.add_argument('--parent-canonical',required=True);ap.add_argument('--c0-result',required=True);ap.add_argument('--c2-result',required=True);ap.add_argument('--out',required=True);a=ap.parse_args();spec=json.load(open(a.spec,encoding='utf-8'));parent=json.load(open(a.parent_canonical,encoding='utf-8'));p0=json.load(open(a.c0_result,encoding='utf-8'));p2=json.load(open(a.c2_result,encoding='utf-8'))
 assert parent['version']=='v2.29' and parent['status']=='CURRENT_CANONICAL_RESEARCH_STATE';assert p0['admitted_candidate_count']==8 and p2['survivor_count']==8 and spec['frozen_candidate_count']==8
 frozen=[(x['role'],x['word_token'],x['source_word_after_scoring']) for x in p0['admitted_candidates']];assert len(set((r,w) for r,w,_ in frozen))==8
 docs,reveal,failures=b0.load_corpus(Path(a.corpus));cfg=spec['D0_candidate_gate'];scfg=spec['status_robustness_gate'];perm_n=spec['object_block_null']['permutations'];seed0=spec['object_block_null']['seed'];rows=[]
 for role,word,label in sorted(frozen):
  allrole=[x for x in c0.role_observations(docs) if x['role']==role];counts=Counter(x['region'] for x in allrole if x['word']==word);dominant=sorted(counts,key=lambda r:(-counts[r],r))[0] if counts else None;regionrows=[x for x in allrole if x['region']==dominant];cand=[x for x in regionrows if x['word']==word];n=len(cand);k=sum(x['match'] for x in cand);rate=k/n if n else 0.0;objects=sorted({object_id(x['doc']) for x in cand});groups=defaultdict(list)
  for x in regionrows:groups[object_id(x['doc'])].append((x['word'],bool(x['match'])))
  rng=random.Random(seed0+int(hashlib.sha256(f'{role}|{word}'.encode()).hexdigest()[:8],16));ge=0;sumrate=0.0;sumsq=0.0
  for _ in range(perm_n):
   hits=0
   for oid,g in groups.items():
    words=[w for w,_ in g];matches=[m for _,m in g];rng.shuffle(words);hits+=sum(1 for w,m in zip(words,matches) if w==word and m)
   pr=hits/n if n else 0.0;sumrate+=pr;sumsq+=pr*pr;ge+=int(hits>=k)
  mean=sumrate/perm_n if perm_n else 0.0;var=max(0.0,sumsq/perm_n-mean*mean);p=(1+ge)/(1+perm_n)
  strata=defaultdict(lambda:{'n':0,'k':0})
  for x in cand:
   key='+'.join(x.get('statuses',[])) or 'EMPTY';strata[key]['n']+=1;strata[key]['k']+=int(x['match'])
  srows=[]
  for key,v in sorted(strata.items()):srows.append({'status_stratum':key,'occurrences':v['n'],'matches':v['k'],'match_rate':v['k']/v['n'] if v['n'] else None,'supported':v['n']>=scfg['supported_stratum_minimum_occurrences']})
  supported=[x for x in srows if x['supported']];status_ok=len(supported)>=scfg['minimum_supported_strata'] and all(x['match_rate']>=scfg['minimum_match_rate_in_each_supported_stratum'] for x in supported)
  rows.append({'role':role,'word_token':word,'source_word_after_scoring':label,'dominant_region':dominant,'dominant_region_occurrences':n,'dominant_region_matches':k,'dominant_region_match_rate':rate,'dominant_region_document_count':len({x['doc'] for x in cand}),'dominant_region_physical_object_count':len(objects),'physical_object_ids':objects,'null_mean_match_rate':mean,'null_sd_match_rate':var**0.5,'observed_minus_null_mean_rate':rate-mean,'empirical_p':p,'status_strata':srows,'supported_status_strata_count':len(supported),'STATUS_ROBUSTNESS_PASS':status_ok})
 q=stats.bh_qvalues([{'p_value':x['empirical_p']} for x in rows])
 for x,qv in zip(rows,q):
  x['BH_q']=qv;x['D0_OBJECT_BLOCK_PASS']=bool(x['dominant_region_occurrences']>=cfg['minimum_occurrences'] and x['dominant_region_physical_object_count']>=cfg['minimum_physical_objects'] and x['dominant_region_match_rate']>=cfg['minimum_match_rate'] and x['observed_minus_null_mean_rate']>=cfg['minimum_observed_minus_null_mean_rate'] and qv<=cfg['FDR_q_max']);x['D0_REGION_SCOPED_VALIDATION_PASS']=bool(x['D0_OBJECT_BLOCK_PASS'] and x['STATUS_ROBUSTNESS_PASS'])
 valid=[x for x in rows if x['D0_REGION_SCOPED_VALIDATION_PASS']];floor=spec['C3_probable_region_scoped_support_floor']
 for x in rows:x['C3_SUPPORT_FLOOR_PASS']=bool(x['dominant_region_occurrences']>=floor['minimum_occurrences'] and x['dominant_region_physical_object_count']>=floor['minimum_physical_objects'] and x['D0_REGION_SCOPED_VALIDATION_PASS'])
 eligible=[x for x in rows if x['C3_SUPPORT_FLOOR_PASS']];out={'artifact_uuid':'JANUS-LINEAR-A-R7-D0-REGION-SCOPED-OBJECT-STATUS-VALIDATION-RESULT-2026-08-15-v0.1','version':'v0.1','status':'REGION_SCOPED_OBJECT_STATUS_SURVIVORS_PRESENT' if valid else 'REGION_SCOPED_OBJECT_STATUS_SURVIVORS_NOT_ESTABLISHED','source':{'frozen_commit':FROZEN_COMMIT,'parsed_documents':len(docs),'parse_failures_or_empty':failures},'frozen_candidate_count':8,'candidate_family_changed':False,'object_normalization':spec['physical_object_normalization'],'null_operator':spec['object_block_null'],'candidate_results':rows,'D0_survivor_count':len(valid),'D0_survivors':valid,'C3_support_floor_eligible_count':len(eligible),'C3_support_floor_eligible':eligible,'leakage_firewall':{'new_candidates_added':False,'candidates_removed':False,'roles_changed':False,'thresholds_changed':False,'dominant_region_selection_used_match_outcomes':False,'translations_used':False,'external_dictionaries_used':False,'Linear_B_supervision_used':False,'Notti_readings_used':False},'epistemic_gate':{'region_scoped_object_status_candidates_established':bool(valid),'probable_region_scoped_function_established':False,'universal_probable_function_established':False,'exact_word_meaning_established':False,'translation_established':False,'phonetic_value_established':False,'new_anchor_established':False,'decipherment_established':False,'R3B_external_replication_established':False},'claim_ceiling':spec['claim_ceiling']};Path(a.out).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':out['status'],'D0_survivors':len(valid),'C3_floor':len(eligible)},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
