#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_r5_word_level_role_learning_v0_1 as r5
import janus_linear_a_r7_formula_slot_completion_v0_1 as r70

FROZEN_COMMIT="43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"


def typed_neighbor(item):
    cert="CERTAIN" if item.get("certain") else "NONCERTAIN"
    if item.get("kind")=="W":
        return f"LEX|{cert}"
    if item.get("kind")=="N":
        if cert=="CERTAIN":
            return f"{item['context']}|CERTAIN"
        return "N:*|NONCERTAIN"
    return f"OTHER|{cert}"


def family_observations(docs):
    for d in docs:
        seq=d["sequence"]
        for i in range(1,len(seq)-1):
            left,target,right=seq[i-1],seq[i],seq[i+1]
            if target.get("kind")!="W" or not target.get("certain"):
                continue
            if left.get("certain"):
                yield {
                    "doc":d,"family":"LEFT_EXACT_RIGHT_TYPE",
                    "anchor":left["context"],"opposite_type":typed_neighbor(right),
                    "target":target["word"],"opposite_exact":right["context"]
                }
            if right.get("certain"):
                yield {
                    "doc":d,"family":"LEFT_TYPE_RIGHT_EXACT",
                    "anchor":right["context"],"opposite_type":typed_neighbor(left),
                    "target":target["word"],"opposite_exact":left["context"]
                }


def select_train(train_docs,spec):
    cfg=spec["train_candidate_gate"]
    by_frame=defaultdict(Counter); frame_docs=defaultdict(set)
    family_target_freq=defaultdict(Counter); family_total=Counter()
    for o in family_observations(train_docs):
        frame=(o["family"],o["anchor"],o["opposite_type"])
        by_frame[frame][o["target"]]+=1
        frame_docs[frame].add(o["doc"]["doc"])
        family_target_freq[o["family"]][o["target"]]+=1
        family_total[o["family"]]+=1
    out=[]
    for frame in sorted(by_frame):
        c=by_frame[frame]; n=sum(c.values())
        if n<cfg["minimum_frame_occurrences"] or len(frame_docs[frame])<cfg["minimum_frame_documents"]: continue
        ranked=c.most_common()
        if len(ranked)>1 and ranked[0][1]==ranked[1][1]: continue
        target,k=ranked[0]; rate=k/n
        if k<cfg["minimum_dominant_target_occurrences"] or rate<cfg["minimum_dominant_target_rate"]: continue
        family=frame[0]; p0=family_target_freq[family][target]/family_total[family] if family_total[family] else 0.0
        out.append({
          "family":family,"anchor":frame[1],"opposite_type":frame[2],"target":target,
          "train_frame_occurrences":n,"train_frame_documents":len(frame_docs[frame]),
          "train_dominant_target_occurrences":k,"train_dominant_target_rate":rate,
          "train_family_target_unigram_probability":p0
        })
    return out,{k:int(v) for k,v in family_total.items()}


def score(test_docs,cand):
    n=k=0; docs=set(); hit_docs=set(); regions=set(); alternatives=Counter(); opposite_exact=Counter()
    for o in family_observations(test_docs):
        if o["family"]!=cand["family"] or o["anchor"]!=cand["anchor"] or o["opposite_type"]!=cand["opposite_type"]: continue
        n+=1; docs.add(o["doc"]["doc"]); regions.add(r5.base.region_of(o["doc"]["doc"])); alternatives[o["target"]]+=1; opposite_exact[o["opposite_exact"]]+=1
        if o["target"]==cand["target"]: k+=1; hit_docs.add(o["doc"]["doc"])
    return {"heldout_occurrences":n,"heldout_hits":k,"heldout_documents":sorted(docs),"heldout_hit_documents":sorted(hit_docs),"heldout_regions":sorted(regions),"heldout_alternatives":dict(alternatives),"heldout_opposite_exact":dict(opposite_exact)}


def reveal_context(tok,reveal):
    return tok if tok.startswith("N:") else reveal.get(tok,tok)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--corpus',required=True); ap.add_argument('--spec',required=True); ap.add_argument('--parent-canonical',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    spec=json.load(open(a.spec,encoding='utf-8')); parent=json.load(open(a.parent_canonical,encoding='utf-8'))
    assert spec['source']['frozen_commit']==FROZEN_COMMIT
    assert spec['parent_canonical_target']=='v2.25'
    assert parent['version']=='v2.25' and parent['status']=='CURRENT_CANONICAL_RESEARCH_STATE'
    assert spec['typed_neighbor']['none_or_doubtful_is_never_reinterpreted_as_certain'] is True
    assert spec['cross_fitting']['candidate_selection_train_only'] is True
    assert spec['train_candidate_gate']['manual_candidate_addition_forbidden'] is True
    assert spec['train_candidate_gate']['manual_candidate_removal_forbidden'] is True

    docs,reveal,failures=r5.load_corpus(Path(a.corpus)); by_fold={f:[d for d in docs if d['fold']==f] for f in range(5)}
    hist=defaultdict(lambda:{"selected_folds":[],"train_rows":[],"test_rows":[],"null_probs":[]}); per_fold=[]
    for fold in range(5):
        train=[d for d in docs if d['fold']!=fold]; test=by_fold[fold]; selected,family_total=select_train(train,spec)
        held=0
        for cand in selected:
            key=(cand['family'],cand['anchor'],cand['opposite_type'],cand['target']); s=score(test,cand); held+=s['heldout_occurrences']; h=hist[key]
            h['selected_folds'].append(fold); h['train_rows'].append({'fold':fold,**cand}); h['test_rows'].append({'fold':fold,**s}); h['null_probs'].extend([cand['train_family_target_unigram_probability']]*s['heldout_occurrences'])
        per_fold.append({'fold':fold,'train_documents':len(train),'heldout_documents':len(test),'train_family_observations':family_total,'train_selected_candidates':len(selected),'heldout_occurrences_of_selected_frames':held})

    cfg=spec['heldout_candidate_gate']; family=[]
    for (fam,anchor,otype,target),h in sorted(hist.items()):
        sf=sorted(h['selected_folds'])
        if len(sf)<cfg['minimum_selected_folds']: continue
        n=sum(x['heldout_occurrences'] for x in h['test_rows']); k=sum(x['heldout_hits'] for x in h['test_rows']); docs_all=sorted({d for x in h['test_rows'] for d in x['heldout_documents']}); hit_docs=sorted({d for x in h['test_rows'] for d in x['heldout_hit_documents']}); regs=sorted({r for x in h['test_rows'] for r in x['heldout_regions']}); alts=Counter(); opp=Counter()
        for x in h['test_rows']: alts.update(x['heldout_alternatives']); opp.update(x['heldout_opposite_exact'])
        p=r70.poisson_binomial_upper_tail(h['null_probs'],k) if n else 1.0
        family.append({'family':fam,'anchor_token':anchor,'opposite_type':otype,'target_token':target,'selected_folds':sf,'selected_fold_count':len(sf),'train_rows':h['train_rows'],'heldout_occurrences':n,'heldout_hits':k,'heldout_precision':k/n if n else None,'heldout_document_ids':docs_all,'heldout_hit_document_ids':hit_docs,'heldout_document_count':len(docs_all),'heldout_region_set':regs,'heldout_alternative_counts_opaque':dict(alts),'heldout_opposite_exact_counts_opaque':dict(opp),'p_value':p})
    q=r70.bh_qvalues(family); admitted=[]
    for row,qv in zip(family,q):
        row['BH_q']=qv; pr=row['heldout_precision'] or 0.0
        ok=bool(row['heldout_occurrences']>=cfg['minimum_heldout_occurrences'] and row['heldout_document_count']>=cfg['minimum_heldout_documents'] and pr>=cfg['minimum_heldout_precision'] and qv<=cfg['FDR_q_max'])
        row['ANCHORED_FORMULA_FAMILY_CANDIDATE_ADMITTED']=ok
        if ok: admitted.append(row)

    def reveal_row(row):
        x=dict(row); x['source_anchor_after_scoring']=reveal_context(row['anchor_token'],reveal); x['source_target_after_scoring']=reveal.get(row['target_token'],row['target_token']); x['heldout_alternative_counts_after_scoring']={reveal.get(t,t):n for t,n in row['heldout_alternative_counts_opaque'].items()}; x['heldout_opposite_exact_counts_after_scoring']={reveal_context(t,reveal):n for t,n in row['heldout_opposite_exact_counts_opaque'].items()}; return x
    family=[reveal_row(x) for x in family]; admitted=[x for x in family if x['ANCHORED_FORMULA_FAMILY_CANDIDATE_ADMITTED']]
    family.sort(key=lambda x:(not x['ANCHORED_FORMULA_FAMILY_CANDIDATE_ADMITTED'],x['BH_q'],-(x['heldout_precision'] or 0),-x['heldout_occurrences']))
    admitted.sort(key=lambda x:(x['BH_q'],-(x['heldout_precision'] or 0),-x['heldout_occurrences']))
    status='CROSS_FITTED_ANCHORED_FORMULA_FAMILY_CANDIDATES_ADMITTED' if admitted else 'CROSS_FITTED_ANCHORED_FORMULA_FAMILY_CANDIDATES_NOT_ESTABLISHED'
    result={'artifact_uuid':'JANUS-LINEAR-A-R7-A0-ANCHORED-FORMULA-FAMILY-RESULT-2026-08-15-v0.1','version':'v0.1','node_type':'cross_fitted_anchored_formula_family_result','status':status,'source':{'repository':'Hawkar-usls/lineara.xyz','frozen_commit':FROZEN_COMMIT,'parsed_documents':len(docs),'parse_failures_or_empty':failures},'method':{'folds':5,'families':['LEFT_EXACT_RIGHT_TYPE','LEFT_TYPE_RIGHT_EXACT'],'multiple_testing':'Benjamini-Hochberg','FDR_q_max':cfg['FDR_q_max'],'null':cfg['null']},'per_fold':per_fold,'cross_fitted_candidate_family_size':len(family),'admitted_candidate_count':len(admitted),'admitted_candidates':admitted,'candidate_family_after_scoring':family,'leakage_firewall':{'R7_0_thresholds_relaxed':False,'candidate_selection_used_heldout_documents':False,'source_labels_used_for_selection_or_scoring':False,'none_or_doubtful_reinterpreted_as_certain':False,'translations_used':False,'external_dictionaries_used':False,'Linear_B_supervision_used':False,'Notti_readings_used':False,'manual_candidate_addition_or_removal':False,'R3B_blind_eligibility_affected':False},'epistemic_gate':{'anchored_formula_family_candidates_established':bool(admitted),'probable_function_established':False,'word_meaning_established':False,'grammatical_label_established':False,'translation_established':False,'phonetic_value_established':False,'new_anchor_established':False,'decipherment_established':False,'R3B_external_replication_established':False},'next_gate':'Freeze admitted candidates unchanged for R7-A1 cross-region transfer and R7-A2 adversarial destruction.' if admitted else 'Preserve negative and move to a separately preregistered document-template/position-family hypothesis without altering this gate.','claim_ceiling':spec['claim_ceiling']}
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'status':status,'family':len(family),'admitted':len(admitted)},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
