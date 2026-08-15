#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,math
from collections import Counter
from pathlib import Path
import janus_linear_a_r7_arithmetic_summary_role_v0_1 as b0
import janus_linear_a_r7_positional_template_roles_v0_1 as c0
import janus_linear_a_r7_formula_slot_completion_v0_1 as stats
FROZEN_COMMIT='43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a'
def binom_upper(n,k,p):
    if k<=0:return 1.0
    if p<=0:return 0.0 if k>0 else 1.0
    if p>=1:return 1.0
    return min(1.0,sum(math.comb(n,j)*(p**j)*((1-p)**(n-j)) for j in range(k,n+1)))
def rows_for(docs,role,word=None):
    return [x for x in c0.role_observations(docs) if x['role']==role and (word is None or x['word']==word)]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--corpus',required=True);ap.add_argument('--spec',required=True);ap.add_argument('--parent-canonical',required=True);ap.add_argument('--c0-result',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    spec=json.load(open(a.spec,encoding='utf-8'));parent=json.load(open(a.parent_canonical,encoding='utf-8'));p0=json.load(open(a.c0_result,encoding='utf-8'))
    assert spec['source']['frozen_commit']==FROZEN_COMMIT and parent['version']=='v2.28' and parent['status']=='CURRENT_CANONICAL_RESEARCH_STATE'
    assert p0['status']=='CROSS_FITTED_POSITIONAL_TEMPLATE_ROLE_CANDIDATES_ADMITTED' and p0['admitted_candidate_count']==8
    frozen={(x['role'],x['word_token']) for x in p0['admitted_candidates']};assert len(frozen)==8 and spec['frozen_candidate_count']==8
    docs,reveal,failures=b0.load_corpus(Path(a.corpus));regions=sorted({d['region'] for d in docs});rg=spec['nonregion_replay_gate'];sg=spec['heldout_region_support_gate'];cg=spec['heldout_region_confirmation_gate']
    tests=[];candidate_rows=[]
    label={(x['role'],x['word_token']):x['source_word_after_scoring'] for x in p0['admitted_candidates']}
    for role,word in sorted(frozen):
        entries=[]
        for region in regions:
            testdocs=[d for d in docs if d['region']==region];td=rows_for(testdocs,role,word);n=len(td);nd=len({x['doc'] for x in td})
            support=n>=sg['minimum_candidate_occurrences'] and nd>=sg['minimum_candidate_documents']
            if not support:continue
            traindocs=[d for d in docs if d['region']!=region];tr=rows_for(traindocs,role,word);alltr=rows_for(traindocs,role);tn=len(tr);tnd=len({x['doc'] for x in tr});tk=sum(x['match'] for x in tr);trate=tk/tn if tn else 0.0;bg=sum(x['match'] for x in alltr)/len(alltr) if alltr else 0.0;lift=trate-bg
            replay=tn>=rg['minimum_eligible_occurrences'] and tnd>=rg['minimum_documents'] and trate>=rg['minimum_role_match_rate'] and lift>=rg['minimum_absolute_rate_lift_over_role_background']
            other=[x for x in rows_for(testdocs,role) if x['word']!=word];pbg=sum(x['match'] for x in other)/len(other) if other else 0.0;k=sum(x['match'] for x in td);rate=k/n if n else 0.0;p=binom_upper(n,k,pbg) if replay else 1.0
            row={'role':role,'word_token':word,'region':region,'nonregion_replay_pass':replay,'nonregion_occurrences':tn,'nonregion_documents':tnd,'nonregion_match_rate':trate,'nonregion_background_rate':bg,'nonregion_rate_lift':lift,'heldout_occurrences':n,'heldout_documents':nd,'heldout_matches':k,'heldout_match_rate':rate,'heldout_role_background_rate_other_words':pbg,'p_value':p,'heldout_document_ids':sorted({x['doc'] for x in td})};tests.append(row);entries.append(row)
        candidate_rows.append({'role':role,'word_token':word,'source_word_after_scoring':label[(role,word)],'eligible_region_count':len(entries)})
    q=stats.bh_qvalues(tests)
    for x,qv in zip(tests,q):
        x['BH_q']=qv;x['REGION_CONFIRMED']=bool(x['nonregion_replay_pass'] and x['heldout_match_rate']>=cg['minimum_match_rate'] and qv<=cg['FDR_q_max'])
    outc=[]
    for c in candidate_rows:
        ts=[x for x in tests if x['role']==c['role'] and x['word_token']==c['word_token']];conf=[x for x in ts if x['REGION_CONFIRMED']];c.update({'tested_regions':sorted(x['region'] for x in ts),'confirmed_regions':sorted(x['region'] for x in conf),'confirmed_region_count':len(conf),'C1_NESTED_REGION_SURVIVAL':len(conf)>=spec['candidate_survival_gate']['minimum_confirmed_regions'],'region_tests':ts});outc.append(c)
    survivors=[x for x in outc if x['C1_NESTED_REGION_SURVIVAL']];status='NESTED_REGION_TRANSFER_SURVIVORS_PRESENT' if survivors else 'NESTED_REGION_TRANSFER_SURVIVORS_NOT_ESTABLISHED'
    result={'artifact_uuid':'JANUS-LINEAR-A-R7-C1-NESTED-REGION-TRANSFER-RESULT-2026-08-15-v0.1','version':'v0.1','status':status,'source':{'frozen_commit':FROZEN_COMMIT,'parsed_documents':len(docs),'parse_failures_or_empty':failures},'frozen_candidate_count':8,'candidate_family_changed':False,'region_test_count':len(tests),'survivor_count':len(survivors),'survivors':survivors,'candidate_results':outc,'leakage_firewall':{'new_candidates_added':False,'candidates_removed':False,'roles_changed':False,'thresholds_changed':False,'translations_used':False,'external_dictionaries_used':False,'Linear_B_supervision_used':False,'Notti_readings_used':False},'epistemic_gate':{'nested_cross_region_candidates_established':bool(survivors),'probable_function_established':False,'exact_word_meaning_established':False,'translation_established':False,'phonetic_value_established':False,'new_anchor_established':False,'decipherment_established':False,'R3B_external_replication_established':False},'claim_ceiling':spec['claim_ceiling']}
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':status,'tests':len(tests),'survivors':len(survivors)},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
