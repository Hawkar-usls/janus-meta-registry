#!/usr/bin/env python3
"""JANUS Linear A R6-0 cross-fitted numeric-adjacency role discovery."""
from __future__ import annotations
import argparse, hashlib, json, math
from collections import Counter, defaultdict
from pathlib import Path
import janus_linear_a_full_corpus as base
import janus_linear_a_r5_word_level_role_learning_v0_1 as r5

FROZEN_COMMIT="43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
NS="JANUS-LINA-R6-0-CV-v0.1"
SIDES=("RIGHT_NUMERIC","LEFT_NUMERIC")

def fold_of(doc): return int(hashlib.sha256(f"{NS}|{doc}".encode()).hexdigest()[:8],16)%5

def load_corpus(root:Path):
    docs=[]; reveal={}; failures=0
    for p in sorted((root/'items').glob('*.html')):
        try:d=r5.parse_document(p)
        except Exception:d=None
        if not d: failures+=1; continue
        d['r6_fold']=fold_of(d['doc']); docs.append(d); reveal.update(d['reveal'])
    if len(docs)<300: raise SystemExit('R6_FULL_CORPUS_GATE_FAIL')
    return docs,reveal,failures

def side_hit(seq,i,side):
    j=i+1 if side=='RIGHT_NUMERIC' else i-1
    return 0<=j<len(seq) and seq[j]['kind']=='N'

def adjacent_bucket(seq,i,side):
    j=i+1 if side=='RIGHT_NUMERIC' else i-1
    return seq[j]['context'] if 0<=j<len(seq) and seq[j]['kind']=='N' else None

def iter_certain_words(docs):
    for d in docs:
        for i,item in enumerate(d['sequence']):
            if item.get('kind')=='W' and item.get('certain'):
                yield d,d['sequence'],i,item

def train_select(train_docs):
    stats={side:defaultdict(lambda:{'n':0,'hits':0,'docs':set()}) for side in SIDES}
    for d,seq,i,item in iter_certain_words(train_docs):
        w=item['word']
        for side in SIDES:
            s=stats[side][w];s['n']+=1;s['hits']+=int(side_hit(seq,i,side));s['docs'].add(d['doc'])
    selected=[]
    for side in SIDES:
        for w,s in stats[side].items():
            rate=s['hits']/s['n'] if s['n'] else 0
            if s['n']>=8 and len(s['docs'])>=4 and rate>=0.70:
                selected.append((w,side,s['n'],len(s['docs']),rate))
    return selected

def binom_tail(n,k,p):
    if n<=0:return 1.0
    if p<=0:return 0.0 if k>0 else 1.0
    if p>=1:return 1.0
    return min(1.0,sum(math.comb(n,j)*(p**j)*((1-p)**(n-j)) for j in range(k,n+1)))

def bh(rows):
    m=len(rows)
    if not m:return
    order=sorted(range(m),key=lambda i:rows[i]['p_value'])
    prev=1.0
    for rank_rev,idx in enumerate(reversed(order),start=1):
        rank=m-rank_rev+1
        q=min(prev,rows[idx]['p_value']*m/rank); rows[idx]['BH_q']=q; prev=q

def heldout_score(docs, word, side, folds):
    n=hits=bg_n=bg_hits=0; buckets=Counter(); regions=set(); hit_docs=set(); all_docs=set()
    folds=set(folds)
    for d,seq,i,item in iter_certain_words([x for x in docs if x['r6_fold'] in folds]):
        h=side_hit(seq,i,side); bg_n+=1; bg_hits+=int(h)
        if item['word']!=word: continue
        n+=1;hits+=int(h);all_docs.add(d['doc']);regions.add(base.region_of(d['doc']))
        if h:
            hit_docs.add(d['doc']); buckets[adjacent_bucket(seq,i,side)]+=1
    p0=bg_hits/bg_n if bg_n else 0.0; rate=hits/n if n else 0.0
    return {'heldout_occurrences':n,'heldout_numeric_hits':hits,'heldout_adjacency_rate':rate,'background_occurrences':bg_n,'background_numeric_hits':bg_hits,'background_adjacency_rate':p0,'p_value':binom_tail(n,hits,p0),'numeric_bucket_distribution':dict(sorted(buckets.items())),'region_set':sorted(regions),'heldout_document_ids':sorted(all_docs),'heldout_hit_document_ids':sorted(hit_docs)}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--corpus',required=True);ap.add_argument('--spec',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    spec=json.load(open(a.spec,encoding='utf-8'));assert spec['source']['frozen_commit']==FROZEN_COMMIT;assert spec['cross_fitting']['none_reinterpreted_as_certain'] is False
    docs,reveal,failures=load_corpus(Path(a.corpus)); fold_counts={str(k):sum(d['r6_fold']==k for d in docs) for k in range(5)}; history=defaultdict(lambda:{'folds':[],'train_rates':[],'train_ns':[],'train_docs':[]}); per_fold=[]
    for fold in range(5):
        train=[d for d in docs if d['r6_fold']!=fold]; selected=train_select(train)
        per_fold.append({'fold':fold,'train_documents':len(train),'selected_candidate_count':len(selected)})
        for w,side,n,dc,rate in selected:
            h=history[(w,side)];h['folds'].append(fold);h['train_rates'].append(rate);h['train_ns'].append(n);h['train_docs'].append(dc)
    family=[]
    for (w,side),h in history.items():
        if len(h['folds'])<3:continue
        score=heldout_score(docs,w,side,h['folds'])
        family.append({'word_token':w,'role':side,'selected_folds':h['folds'],'selected_fold_count':len(h['folds']),'mean_train_adjacency_rate':sum(h['train_rates'])/len(h['train_rates']),'min_train_occurrences_across_selected_folds':min(h['train_ns']),'min_train_documents_across_selected_folds':min(h['train_docs']),**score})
    bh(family)
    for r in family:
        r['ROLE_CANDIDATE_ADMITTED']=bool(r['heldout_occurrences']>=5 and r['heldout_adjacency_rate']>=0.75 and r['BH_q']<=0.05)
    # Only now reveal source word labels.
    for r in family:r['source_word_after_scoring']=reveal.get(r['word_token'])
    family.sort(key=lambda r:(-int(r['ROLE_CANDIDATE_ADMITTED']),r['BH_q'],-r['heldout_adjacency_rate'],-r['heldout_occurrences'],r['word_token'],r['role']))
    admitted=[r for r in family if r['ROLE_CANDIDATE_ADMITTED']]
    status='CROSS_FITTED_NUMERIC_ADJACENCY_ROLE_CANDIDATES_PRESENT' if admitted else 'CROSS_FITTED_NUMERIC_ADJACENCY_ROLE_CANDIDATES_NOT_ESTABLISHED'
    result={'artifact_uuid':'JANUS-LINEAR-A-R6-0-CROSS-FITTED-NUMERIC-ADJACENCY-ROLE-RESULT-2026-08-14-v0.1','version':'v0.1','node_type':'cross_fitted_numeric_adjacency_role_result','status':status,'source':{'repository':'Hawkar-usls/lineara.xyz','frozen_commit':FROZEN_COMMIT,'parsed_documents':len(docs),'parse_failures_or_empty':failures},'fold_counts':fold_counts,'per_fold_train_selection_summary':per_fold,'cross_fitted_candidate_family_size':len(family),'admitted_role_candidate_count':len(admitted),'admitted_role_candidates':admitted,'all_cross_fitted_candidates_after_scoring':family,'statistical_gate':{'test':'one-sided exact binomial tail','multiple_testing':'Benjamini-Hochberg','FDR_q_max':0.05,'minimum_heldout_occurrences':5,'minimum_heldout_rate':0.75},'leakage_firewall':{'word_labels_used_for_selection_or_scoring':False,'none_reinterpreted_as_certain':False,'doubtful_reinterpreted_as_certain':False,'translations_used':False,'external_dictionaries_used':False,'Notti_readings_used':False,'R3B_blind_eligibility_affected':False},'epistemic_gate':{'quantity_adjacency_roles_detected':bool(admitted),'commodity_meanings_established':False,'person_meanings_established':False,'transaction_meanings_established':False,'grammatical_labels_established':False,'translation_established':False,'phonetic_value_established':False,'new_anchor_established':False,'decipherment_established':False,'R3B_external_replication_established':False},'claim_ceiling':spec['claim_ceiling']}
    Path(a.out).parent.mkdir(parents=True,exist_ok=True);Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps({'status':status,'candidate_family_size':len(family),'admitted_count':len(admitted),'admitted_labels_after_scoring':[(x['source_word_after_scoring'],x['role'],x['heldout_occurrences'],x['heldout_adjacency_rate'],x['BH_q']) for x in admitted],'decipherment_established':False},ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
