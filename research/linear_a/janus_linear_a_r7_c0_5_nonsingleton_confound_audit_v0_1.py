#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, json, math
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_r7_arithmetic_summary_role_v0_1 as b0

FROZEN_COMMIT='43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a'
BOUNDARY_ROLES={'DOCUMENT_HEADER','DOCUMENT_CLOSER','ROW_HEADER','ROW_CLOSER'}


def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def binom_upper(n,k,p):
    if n==0: return 1.0
    if p<=0: return 0.0 if k>0 else 1.0
    if p>=1: return 1.0
    s=0.0
    for i in range(k,n+1):
        s += math.comb(n,i)*(p**i)*((1-p)**(n-i))
    return min(1.0,max(0.0,s))

def bh(rows):
    m=len(rows)
    order=sorted(range(m), key=lambda i: rows[i]['p_value'])
    q=[1.0]*m; prev=1.0
    for rank0 in range(m-1,-1,-1):
        i=order[rank0]; rank=rank0+1
        val=min(prev, rows[i]['p_value']*m/rank)
        q[i]=min(1.0,val); prev=q[i]
    return q

def lexical_indices(seq): return [i for i,x in enumerate(seq) if x.get('kind')=='W']

def corrected_occurrences(docs, role):
    for d in docs:
        seq=d['sequence']; lex=lexical_indices(seq)
        if role in {'DOCUMENT_HEADER','DOCUMENT_CLOSER'}:
            if len(lex)<2: continue
            boundary=lex[0] if role=='DOCUMENT_HEADER' else lex[-1]
            for i in lex:
                x=seq[i]
                yield {'doc':d['doc'],'region':d['region'],'word':x['word'],'hit':i==boundary,'statuses':x.get('statuses',[]),'domain':'DOCUMENT'}
        elif role in {'ROW_HEADER','ROW_CLOSER'}:
            by_row=defaultdict(list)
            for i in lex:
                x=seq[i]
                if len(x.get('rows',[]))==1: by_row[x['rows'][0]].append(i)
            for row,idxs in by_row.items():
                if len(idxs)<2: continue
                boundary=idxs[0] if role=='ROW_HEADER' else idxs[-1]
                for i in idxs:
                    x=seq[i]
                    yield {'doc':d['doc'],'region':d['region'],'word':x['word'],'hit':i==boundary,'statuses':x.get('statuses',[]),'domain':f'ROW:{row}'}
        elif role=='NUMERIC_BLOCK_INTRODUCER':
            for i in lex:
                n=0; j=i+1
                while j<len(seq) and seq[j].get('kind')=='N': n+=1; j+=1
                x=seq[i]
                yield {'doc':d['doc'],'region':d['region'],'word':x['word'],'hit':n>=2,'statuses':x.get('statuses',[]),'domain':'DOCUMENT'}
        elif role=='NUMERIC_BLOCK_CLOSER':
            for i in lex:
                n=0; j=i-1
                while j>=0 and seq[j].get('kind')=='N': n+=1; j-=1
                x=seq[i]
                yield {'doc':d['doc'],'region':d['region'],'word':x['word'],'hit':n>=2,'statuses':x.get('statuses',[]),'domain':'DOCUMENT'}
        else: raise ValueError(role)

def confound_inventory(docs):
    docs_with_lex=0; singleton_docs=0; rows_total=0; singleton_rows=0
    for d in docs:
        lex=lexical_indices(d['sequence'])
        if lex:
            docs_with_lex+=1
            if len(lex)==1: singleton_docs+=1
        by_row=defaultdict(int)
        for i in lex:
            x=d['sequence'][i]
            if len(x.get('rows',[]))==1: by_row[x['rows'][0]]+=1
        for n in by_row.values():
            rows_total+=1
            if n==1: singleton_rows+=1
    return {
      'documents_with_lexical_occurrence':docs_with_lex,
      'singleton_lexical_documents':singleton_docs,
      'singleton_document_fraction': singleton_docs/docs_with_lex if docs_with_lex else None,
      'unambiguous_rows_with_lexical_occurrence':rows_total,
      'singleton_lexical_rows':singleton_rows,
      'singleton_row_fraction': singleton_rows/rows_total if rows_total else None,
    }

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--corpus',required=True); ap.add_argument('--spec',required=True); ap.add_argument('--freeze',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    spec=json.loads(Path(a.spec).read_text(encoding='utf-8')); fr=json.loads(Path(a.freeze).read_text(encoding='utf-8'))
    assert fr['status']=='R7_C0_ADMITTED_FAMILY_FROZEN_43_OF_65' and len(fr['candidate_family'])==43
    assert spec['candidate_policy']['candidate_family_is_exactly_all_43_frozen_rows'] is True
    docs,reveal,failures=b0.load_corpus(Path(a.corpus))
    inv=confound_inventory(docs)
    role_cache={}; backgrounds={}; domain_counts={}
    for role in sorted({r['role'] for r in fr['candidate_family']}):
        obs=list(corrected_occurrences(docs,role)); role_cache[role]=obs
        domain_counts[role]=len(obs); backgrounds[role]=sum(x['hit'] for x in obs)/len(obs) if obs else 0.0
    rows=[]
    for frozen in fr['candidate_family']:
        role=frozen['role']; token=frozen['word_token']; obs=[x for x in role_cache[role] if x['word']==token]
        hits=[x for x in obs if x['hit']]
        n=len(obs); k=len(hits); hit_docs=sorted({x['doc'] for x in hits}); docs_seen=sorted({x['doc'] for x in obs})
        precision=k/n if n else None; bg=backgrounds[role]; lift=(precision-bg) if precision is not None else None
        p=binom_upper(n,k,bg) if n else 1.0
        rows.append({
          'candidate_id':frozen['candidate_id'],'role':role,'word_token':token,'source_word_after_scoring':frozen['source_word_after_scoring'],
          'original_C0_heldout_eligible_occurrences':frozen['heldout_eligible_occurrences'],'original_C0_heldout_role_precision':frozen['heldout_role_precision'],
          'corrected_eligible_occurrences':n,'corrected_role_hits':k,'corrected_role_precision':precision,'corrected_role_background_probability':bg,
          'corrected_absolute_precision_lift':lift,'corrected_document_count':len(docs_seen),'corrected_role_hit_document_count':len(hit_docs),
          'corrected_region_set':sorted({x['region'] for x in obs}),'p_value':p
        })
    q=bh(rows); cfg=spec['survival_gate']
    for r,qv in zip(rows,q):
        r['BH_q']=qv
        r['SURVIVES_NONSINGLETON_AUDIT']=bool(
          r['corrected_eligible_occurrences']>=cfg['minimum_eligible_occurrences_after_correction'] and
          r['corrected_role_hits']>=cfg['minimum_role_hits_after_correction'] and
          r['corrected_role_hit_document_count']>=cfg['minimum_role_hit_documents_after_correction'] and
          (r['corrected_role_precision'] or 0)>=cfg['minimum_role_precision_after_correction'] and
          (r['corrected_absolute_precision_lift'] if r['corrected_absolute_precision_lift'] is not None else -1)>=cfg['minimum_absolute_precision_lift_over_corrected_role_background'] and
          qv<=cfg['FDR_q_max'])
    survivors=[r for r in rows if r['SURVIVES_NONSINGLETON_AUDIT']]
    role_survivors=dict(Counter(r['role'] for r in survivors))
    result={
      'artifact_uuid':'JANUS-LINEAR-A-R7-C0-5-NONSINGLETON-BOUNDARY-CONFOUND-AUDIT-RESULT-2026-08-16-v0.1',
      'version':'v0.1','node_type':'posthoc_corrective_boundary_confound_audit_result',
      'status':'R7_C0_5_NONSINGLETON_CONFOUND_AUDIT_COMPLETE',
      'source':{'repository':'Hawkar-usls/lineara.xyz','frozen_commit':FROZEN_COMMIT,'parsed_documents':len(docs),'parse_failures_or_empty':failures},
      'candidate_freeze':a.freeze,'candidate_freeze_sha256':sha256(a.freeze),'candidate_count':43,
      'confound_inventory':inv,'corrected_role_domain_occurrence_counts':domain_counts,'corrected_role_background_probabilities':backgrounds,
      'survivor_count':len(survivors),'survivor_count_by_role':role_survivors,
      'candidate_results':rows,
      'survivors':survivors,
      'credit':{'blind_confirmation_credit':False,'independent_confirmation_credit':False,'posthoc_corrective_only':True},
      'epistemic_gate':{'nonsingleton_robust_positional_candidates_exist':bool(survivors),'probable_function_established':False,'exact_word_meaning_established':False,'translation_established':False,'decipherment_established':False,'R3B_external_replication_established':False},
      'next_gate':'Keep all 43 frozen for provenance; only candidates with SURVIVES_NONSINGLETON_AUDIT=true are eligible for eventual R7-C3 promotion, while R7-C1/C2 must still report every frozen candidate.',
      'claim_ceiling':spec['claim_ceiling']
    }
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'survivors':len(survivors),'roles':role_survivors,'singleton_document_fraction':inv['singleton_document_fraction'],'singleton_row_fraction':inv['singleton_row_fraction']},sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
