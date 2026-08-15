#!/usr/bin/env python3
"""JANUS Linear A R7-C0 cross-fitted positional/document-template role discovery."""
from __future__ import annotations

import argparse, json
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_r7_arithmetic_summary_role_v0_1 as b0
import janus_linear_a_r7_formula_slot_completion_v0_1 as stats

FROZEN_COMMIT="43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
ROLES=(
  "DOCUMENT_FIRST_LEXICAL","DOCUMENT_LAST_LEXICAL",
  "ROW_FIRST_LEXICAL","ROW_LAST_LEXICAL",
  "BEFORE_NUMERIC_BLOCK_GE2","AFTER_NUMERIC_BLOCK_GE2","BETWEEN_NUMERIC_NEIGHBORS"
)


def is_numlike(item): return item.get('kind') in {'N','X'}


def row_index_sequences(seq):
    rows=defaultdict(list)
    for i,x in enumerate(seq):
        if len(x.get('rows',[]))==1:
            rows[x['rows'][0]].append(i)
    return rows


def role_observations(docs):
    for d in docs:
        seq=d['sequence']; lexical=[i for i,x in enumerate(seq) if x.get('kind')=='W']; rows=row_index_sequences(seq)
        firstlex=lexical[0] if len(lexical)>=2 else None; lastlex=lexical[-1] if len(lexical)>=2 else None
        row_meta={}
        for r,idxs in rows.items():
            lex=[i for i in idxs if seq[i].get('kind')=='W']
            if len(idxs)>=2 and lex: row_meta[r]={'idxs':idxs,'lex_first':lex[0],'lex_last':lex[-1]}
        for i,x in enumerate(seq):
            if x.get('kind')!='W': continue
            base={'doc':d['doc'],'fold':d['fold'],'region':d['region'],'word':x['word'],'statuses':x.get('statuses',[]),'word_index':x.get('word_index'),'rows':x.get('rows',[])}
            if firstlex is not None:
                yield {**base,'role':'DOCUMENT_FIRST_LEXICAL','match':i==firstlex,'meta':{'global_index':i,'lexical_count':len(lexical)}}
                yield {**base,'role':'DOCUMENT_LAST_LEXICAL','match':i==lastlex,'meta':{'global_index':i,'lexical_count':len(lexical)}}
            if len(x.get('rows',[]))!=1: continue
            r=x['rows'][0]
            if r in row_meta:
                rm=row_meta[r]
                yield {**base,'role':'ROW_FIRST_LEXICAL','match':i==rm['lex_first'],'meta':{'row':r,'row_item_count':len(rm['idxs'])}}
                yield {**base,'role':'ROW_LAST_LEXICAL','match':i==rm['lex_last'],'meta':{'row':r,'row_item_count':len(rm['idxs'])}}
                idxs=rm['idxs']; pos=idxs.index(i)
                after=idxs[pos+1:]; before=idxs[:pos]
                run_after=0
                for j in after:
                    if is_numlike(seq[j]): run_after+=1
                    else: break
                run_before=0
                for j in reversed(before):
                    if is_numlike(seq[j]): run_before+=1
                    else: break
                yield {**base,'role':'BEFORE_NUMERIC_BLOCK_GE2','match':run_after>=2,'meta':{'row':r,'numeric_run_after':run_after,'numeric_run_before':run_before}}
                yield {**base,'role':'AFTER_NUMERIC_BLOCK_GE2','match':run_before>=2,'meta':{'row':r,'numeric_run_after':run_after,'numeric_run_before':run_before}}
                immediate_prev=is_numlike(seq[idxs[pos-1]]) if pos>0 else False
                immediate_next=is_numlike(seq[idxs[pos+1]]) if pos+1<len(idxs) else False
                yield {**base,'role':'BETWEEN_NUMERIC_NEIGHBORS','match':immediate_prev and immediate_next,'meta':{'row':r,'immediate_prev_numeric':immediate_prev,'immediate_next_numeric':immediate_next}}


def select_train(train_docs,spec):
    cfg=spec['train_candidate_gate']; obs=list(role_observations(train_docs)); bg={}
    for role in ROLES:
        rows=[x for x in obs if x['role']==role]; bg[role]=sum(x['match'] for x in rows)/len(rows) if rows else 0.0
    by=defaultdict(list)
    for x in obs: by[(x['role'],x['word'])].append(x)
    selected=[]
    for (role,w),rows in sorted(by.items()):
        n=len(rows); docs={x['doc'] for x in rows}; k=sum(x['match'] for x in rows); rate=k/n if n else 0.0; lift=rate-bg[role]
        if n<cfg['minimum_eligible_occurrences'] or len(docs)<cfg['minimum_documents']: continue
        if rate<cfg['minimum_role_match_rate'] or lift<cfg['minimum_absolute_rate_lift_over_role_background']: continue
        selected.append({'role':role,'word':w,'train_occurrences':n,'train_documents':len(docs),'train_matches':k,'train_match_rate':rate,'train_role_background_rate':bg[role],'train_rate_lift':lift})
    return selected,bg,{r:sum(1 for x in obs if x['role']==r) for r in ROLES}


def score_test(test_docs,cand):
    rows=[x for x in role_observations(test_docs) if x['role']==cand['role'] and x['word']==cand['word']]
    return {'heldout_occurrences':len(rows),'heldout_matches':sum(x['match'] for x in rows),'heldout_documents':sorted({x['doc'] for x in rows}),'heldout_regions':sorted({x['region'] for x in rows}),'status_distribution':dict(Counter('+'.join(x['statuses']) for x in rows)),'examples':[{'doc':x['doc'],'region':x['region'],'match':x['match'],'word_index':x['word_index'],'rows':x['rows'],'meta':x['meta'],'statuses':x['statuses']} for x in rows]}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--corpus',required=True);ap.add_argument('--spec',required=True);ap.add_argument('--parent-canonical',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    spec=json.load(open(a.spec,encoding='utf-8')); parent=json.load(open(a.parent_canonical,encoding='utf-8'))
    assert spec['source']['frozen_commit']==FROZEN_COMMIT
    assert spec['parent_canonical_target']=='v2.27'
    assert parent['version']=='v2.27' and parent['status']=='CURRENT_CANONICAL_RESEARCH_STATE'
    assert spec['status_policy']['none_or_doubtful_is_never_reinterpreted_as_certain'] is True
    assert spec['cross_fitting']['candidate_selection_train_only'] is True
    assert spec['train_candidate_gate']['manual_candidate_addition_forbidden'] is True
    assert spec['train_candidate_gate']['manual_candidate_removal_forbidden'] is True
    docs,reveal,failures=b0.load_corpus(Path(a.corpus)); byfold={f:[d for d in docs if d['fold']==f] for f in range(5)}
    hist=defaultdict(lambda:{'selected_folds':[],'train_rows':[],'test_rows':[],'null_probs':[]}); perfold=[]
    for fold in range(5):
        train=[d for d in docs if d['fold']!=fold];test=byfold[fold];selected,bg,counts=select_train(train,spec);held=0
        for cand in selected:
            sc=score_test(test,cand);held+=sc['heldout_occurrences'];key=(cand['role'],cand['word']);h=hist[key];h['selected_folds'].append(fold);h['train_rows'].append({'fold':fold,**cand});h['test_rows'].append({'fold':fold,**sc});h['null_probs'].extend([cand['train_role_background_rate']]*sc['heldout_occurrences'])
        perfold.append({'fold':fold,'train_documents':len(train),'heldout_documents':len(test),'train_role_observation_counts':counts,'train_role_background_rates':bg,'train_selected_candidates':len(selected),'heldout_occurrences_of_selected_candidates':held})
    cfg=spec['heldout_candidate_gate'];family=[]
    for (role,w),h in sorted(hist.items()):
        sf=sorted(h['selected_folds'])
        if len(sf)<cfg['minimum_selected_folds']: continue
        n=sum(x['heldout_occurrences'] for x in h['test_rows']);k=sum(x['heldout_matches'] for x in h['test_rows']);docs_all=sorted({d for x in h['test_rows'] for d in x['heldout_documents']});regs=sorted({r for x in h['test_rows'] for r in x['heldout_regions']});examples=[e for x in h['test_rows'] for e in x['examples']];stat=Counter()
        for x in h['test_rows']:stat.update(x['status_distribution'])
        p=stats.poisson_binomial_upper_tail(h['null_probs'],k) if n else 1.0
        family.append({'role':role,'word_token':w,'selected_folds':sf,'selected_fold_count':len(sf),'train_rows':h['train_rows'],'heldout_occurrences':n,'heldout_matches':k,'heldout_match_rate':k/n if n else None,'heldout_document_ids':docs_all,'heldout_document_count':len(docs_all),'heldout_region_set':regs,'heldout_status_distribution':dict(stat),'heldout_examples':examples,'p_value':p})
    qvals=stats.bh_qvalues(family);admitted=[]
    for row,q in zip(family,qvals):
        row['BH_q']=q;rate=row['heldout_match_rate'] or 0.0;ok=bool(row['heldout_occurrences']>=cfg['minimum_heldout_occurrences'] and row['heldout_document_count']>=cfg['minimum_heldout_documents'] and rate>=cfg['minimum_heldout_match_rate'] and q<=cfg['FDR_q_max']);row['POSITIONAL_TEMPLATE_CANDIDATE_ADMITTED']=ok
        if ok:admitted.append(row)
    for row in family:row['source_word_after_scoring']=reveal.get(row['word_token'],row['word_token'])
    admitted=[x for x in family if x['POSITIONAL_TEMPLATE_CANDIDATE_ADMITTED']];family.sort(key=lambda x:(not x['POSITIONAL_TEMPLATE_CANDIDATE_ADMITTED'],x['BH_q'],-(x['heldout_match_rate'] or 0),-x['heldout_occurrences']));admitted.sort(key=lambda x:(x['BH_q'],-(x['heldout_match_rate'] or 0),-x['heldout_occurrences']))
    status='CROSS_FITTED_POSITIONAL_TEMPLATE_ROLE_CANDIDATES_ADMITTED' if admitted else 'CROSS_FITTED_POSITIONAL_TEMPLATE_ROLE_CANDIDATES_NOT_ESTABLISHED'
    result={'artifact_uuid':'JANUS-LINEAR-A-R7-C0-POSITIONAL-TEMPLATE-ROLE-RESULT-2026-08-15-v0.1','version':'v0.1','node_type':'cross_fitted_positional_template_role_result','status':status,'source':{'repository':'Hawkar-usls/lineara.xyz','frozen_commit':FROZEN_COMMIT,'parsed_documents':len(docs),'parse_failures_or_empty':failures},'method':{'folds':5,'roles':list(ROLES),'multiple_testing':'Benjamini-Hochberg','FDR_q_max':cfg['FDR_q_max'],'null':cfg['null']},'per_fold':perfold,'cross_fitted_candidate_family_size':len(family),'admitted_candidate_count':len(admitted),'admitted_candidates':admitted,'candidate_family_after_scoring':family,'leakage_firewall':{'candidate_selection_used_heldout_documents':False,'source_word_labels_used_for_selection_or_scoring':False,'certainty_status_used_for_candidate_selection':False,'none_or_doubtful_reinterpreted_as_certain':False,'translations_used':False,'external_dictionaries_used':False,'Linear_B_supervision_used':False,'Notti_readings_used':False,'manual_candidate_addition_or_removal':False,'R3B_blind_eligibility_affected':False},'epistemic_gate':{'positional_template_candidates_established':bool(admitted),'probable_function_established':False,'exact_word_meaning_established':False,'translation_established':False,'phonetic_value_established':False,'new_anchor_established':False,'decipherment_established':False,'R3B_external_replication_established':False},'next_gate':'Freeze admitted candidate family unchanged for R7-C1 complete-region holdout and R7-C2 structure-destroying permutations.' if admitted else 'Preserve negative and move to a separately preregistered co-occurrence/record-template role hypothesis without relaxing R7-C0.','claim_ceiling':spec['claim_ceiling']}
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':status,'family':len(family),'admitted':len(admitted)},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
