#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
import janus_linear_a_r6_numeric_adjacency_roles_v0_1 as r6
import janus_linear_a_full_corpus as base


def bh(rows):
    m=len(rows)
    order=sorted(range(m),key=lambda i:rows[i]['region_conditioned_p'])
    prev=1.0
    for rev,idx in enumerate(reversed(order),start=1):
        rank=m-rev+1
        q=min(prev,rows[idx]['region_conditioned_p']*m/rank)
        rows[idx]['region_conditioned_BH_q']=q;prev=q

def region_background(docs, side, folds, regions):
    folds=set(folds);regions=set(regions);n=hits=0
    for d,seq,i,item in r6.iter_certain_words([x for x in docs if x['r6_fold'] in folds and base.region_of(x['doc']) in regions]):
        n+=1;hits+=int(r6.side_hit(seq,i,side))
    return n,hits,(hits/n if n else 0.0)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--corpus',required=True);ap.add_argument('--spec',required=True);ap.add_argument('--parent',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    spec=json.load(open(a.spec,encoding='utf-8'));parent=json.load(open(a.parent,encoding='utf-8'))
    assert parent['cross_fitted_candidate_family_size']==2
    assert len(parent['all_cross_fitted_candidates_after_scoring'])==2
    docs,reveal,failures=r6.load_corpus(Path(a.corpus))
    rows=[]
    for p in parent['all_cross_fitted_candidates_after_scoring']:
        bg_n,bg_hits,bg_rate=region_background(docs,p['role'],p['selected_folds'],p['region_set'])
        assert p['source_word_after_scoring']==reveal.get(p['word_token'])
        row={
          'word_token':p['word_token'],'role':p['role'],'selected_folds':p['selected_folds'],'region_set':p['region_set'],
          'heldout_occurrences':p['heldout_occurrences'],'heldout_numeric_hits':p['heldout_numeric_hits'],'heldout_adjacency_rate':p['heldout_adjacency_rate'],
          'region_background_occurrences':bg_n,'region_background_numeric_hits':bg_hits,'region_background_adjacency_rate':bg_rate,
          'region_conditioned_p':r6.binom_tail(p['heldout_occurrences'],p['heldout_numeric_hits'],bg_rate),
          'parent_global_p':p['p_value'],'parent_global_BH_q':p['BH_q']
        }
        rows.append(row)
    bh(rows)
    for row in rows:
        row['REGION_CONDITIONED_SURVIVAL']=bool(row['heldout_occurrences']>=5 and row['heldout_adjacency_rate']>=0.75 and row['region_conditioned_BH_q']<=0.05)
    # Reveal only after region-conditioned statistical scoring.
    for row in rows: row['source_word_after_scoring']=reveal.get(row['word_token'])
    rows.sort(key=lambda x:(-int(x['REGION_CONDITIONED_SURVIVAL']),x['region_conditioned_BH_q'],x['word_token'],x['role']))
    survivors=[x for x in rows if x['REGION_CONDITIONED_SURVIVAL']]
    status='POSTHOC_REGION_CONDITIONED_PATTERN_SURVIVES' if survivors else 'POSTHOC_REGION_CONDITIONED_PATTERN_NOT_ROBUST'
    out={'artifact_uuid':'JANUS-LINEAR-A-R6-1-REGION-CONDITIONED-NULL-AUDIT-RESULT-2026-08-14-v0.1','version':'v0.1','node_type':'posthoc_corrective_region_conditioned_null_result','status':status,'posthoc_status':spec['posthoc_status'],'candidate_family_size':len(rows),'survivor_count':len(survivors),'candidate_results':rows,'leakage_and_credit':{'candidate_family_changed':False,'parent_heldout_n_or_hits_changed':False,'word_labels_used_for_statistical_scoring':False,'blind_confirmation_credit':False,'independent_confirmation_claimed':False},'epistemic_gate':{'region_conditioned_robust_pattern_present':bool(survivors),'meaning_established':False,'translation_established':False,'phonetic_value_established':False,'new_anchor_established':False,'decipherment_established':False,'R3B_external_replication_established':False},'claim_ceiling':spec['claim_ceiling']}
    Path(a.out).write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps({'status':status,'survivor_count':len(survivors),'rows':[(x['source_word_after_scoring'],x['role'],x['region_background_adjacency_rate'],x['region_conditioned_p'],x['region_conditioned_BH_q'],x['REGION_CONDITIONED_SURVIVAL']) for x in rows],'decipherment_established':False},ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
