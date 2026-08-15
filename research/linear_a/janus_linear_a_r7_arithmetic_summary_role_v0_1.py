#!/usr/bin/env python3
"""JANUS Linear A R7-B0 blind arithmetic-summary functional-structure discovery."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import janus_linear_a_r5_word_level_role_learning_v0_1 as r5
import janus_linear_a_r7_formula_slot_completion_v0_1 as stats

FROZEN_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"

FRACTIONS = {
    "¹⁄₂": Fraction(1,2), "1/2": Fraction(1,2), "½": Fraction(1,2),
    "¹⁄₄": Fraction(1,4), "1/4": Fraction(1,4), "¼": Fraction(1,4),
    "³⁄₄": Fraction(3,4), "3/4": Fraction(3,4), "¾": Fraction(3,4),
    "¹⁄₈": Fraction(1,8), "1/8": Fraction(1,8), "⅛": Fraction(1,8),
    "³⁄₈": Fraction(3,8), "3/8": Fraction(3,8), "⅜": Fraction(3,8),
    "⁵⁄₈": Fraction(5,8), "5/8": Fraction(5,8), "⅝": Fraction(5,8),
    "⁷⁄₈": Fraction(7,8), "7/8": Fraction(7,8), "⅞": Fraction(7,8),
    "¹⁄₁₆": Fraction(1,16), "1/16": Fraction(1,16),
    "³⁄₁₆": Fraction(3,16), "3/16": Fraction(3,16),
    "⁵⁄₁₆": Fraction(5,16), "5/16": Fraction(5,16),
    "⁷⁄₁₆": Fraction(7,16), "7/16": Fraction(7,16),
}


def exact_piece(token: str):
    t = token.strip().replace(",", "")
    if t in FRACTIONS:
        return FRACTIONS[t]
    if re.fullmatch(r"\d+(?:\.\d+)?", t):
        return Fraction(t)
    return None


def qstr(x: Fraction) -> str:
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def parse_document(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    m = r5.base.READING_SPEC_RE.search(text)
    if not m:
        return None
    body = r5.base.TAG_RE.sub("", m.group(1))
    words = {}
    order = []
    for serial, raw in enumerate(body.splitlines()):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        rm = r5.base.ROW_RE.match(raw)
        if not rm:
            continue
        row_i, line_i, word_i, raw_piece, status = rm.groups()
        wi = int(word_i)
        if wi not in words:
            words[wi] = {"pieces": [], "statuses": [], "rows": set(), "lines": set(), "first_serial": serial}
            order.append(wi)
        w = words[wi]
        w["pieces"].append(raw_piece.strip())
        w["statuses"].append(status.lower())
        w["rows"].add(int(row_i)); w["lines"].add(int(line_i))

    seq = []
    reveal = {}
    for wi in sorted(order, key=lambda k: words[k]["first_serial"]):
        w = words[wi]; pieces = w["pieces"]
        vals = [exact_piece(p) for p in pieces]
        status_set = sorted(set(w["statuses"]))
        meta = {"word_index": wi, "rows": sorted(w["rows"]), "lines": sorted(w["lines"]), "statuses": status_set, "all_certain": bool(status_set) and status_set == ["certain"]}
        if pieces and all(v is not None for v in vals):
            value = sum(vals, Fraction(0,1))
            if value > 0:
                seq.append({"kind": "N", "value": value, **meta})
            continue
        if pieces and all(r5.typing_policy.is_numeric_like_literal(p) for p in pieces):
            seq.append({"kind": "X", "reason": "NUMERIC_LIKE_NOT_EXACTLY_PARSEABLE", **meta})
            continue
        oid = r5.opaque_word(pieces)
        label = "-".join(pieces)
        if oid in reveal and reveal[oid] != label:
            raise RuntimeError("R7_B0_OPAQUE_HASH_COLLISION")
        reveal[oid] = label
        seq.append({"kind": "W", "word": oid, **meta})
    if not seq:
        return None
    return {"doc": path.stem, "fold": r5.fold_of(path.stem), "region": r5.base.region_of(path.stem), "sequence": seq, "reveal": reveal}


def load_corpus(root: Path):
    docs=[]; reveal={}; failures=0
    for p in sorted((root/"items").glob("*.html")):
        try: d=parse_document(p)
        except Exception: d=None
        if d is None:
            failures += 1; continue
        docs.append(d)
        for k,v in d["reveal"].items():
            if k in reveal and reveal[k] != v: raise RuntimeError("R7_B0_GLOBAL_HASH_COLLISION")
            reveal[k]=v
    if len(docs) < 300: raise SystemExit("R7_B0_FULL_CORPUS_GATE_FAIL")
    return docs,reveal,failures


def arithmetic_observations(docs, spec):
    min_doc = spec["operators"]["DOC_PREFIX_SUM"]["minimum_prior_numeric_terms"]
    min_row = spec["operators"]["ROW_PREFIX_SUM"]["minimum_prior_numeric_terms"]
    for d in docs:
        seq=d["sequence"]
        for i in range(len(seq)-1):
            cand,following=seq[i],seq[i+1]
            if cand.get("kind")!="W" or following.get("kind")!="N": continue
            prior_doc=[x for x in seq[:i] if x.get("kind")=="N"]
            if len(prior_doc) >= min_doc:
                total=sum((x["value"] for x in prior_doc),Fraction(0,1))
                yield {"operator":"DOC_PREFIX_SUM","doc":d["doc"],"fold":d["fold"],"region":d["region"],"word":cand["word"],"word_statuses":cand["statuses"],"following_statuses":following["statuses"],"prior_numeric_statuses":[x["statuses"] for x in prior_doc],"prior_terms":len(prior_doc),"prefix_sum":total,"following_value":following["value"],"match":total==following["value"]}
            if len(cand["rows"])==1 and len(following["rows"])==1 and cand["rows"][0]==following["rows"][0]:
                row=cand["rows"][0]
                prior_row=[x for x in seq[:i] if x.get("kind")=="N" and len(x["rows"])==1 and x["rows"][0]==row]
                if len(prior_row) >= min_row:
                    total=sum((x["value"] for x in prior_row),Fraction(0,1))
                    yield {"operator":"ROW_PREFIX_SUM","doc":d["doc"],"fold":d["fold"],"region":d["region"],"word":cand["word"],"word_statuses":cand["statuses"],"following_statuses":following["statuses"],"prior_numeric_statuses":[x["statuses"] for x in prior_row],"prior_terms":len(prior_row),"prefix_sum":total,"following_value":following["value"],"match":total==following["value"]}


def select_train(train_docs,spec):
    cfg=spec["train_candidate_gate"]
    obs=list(arithmetic_observations(train_docs,spec)); bg={}
    for op in ("DOC_PREFIX_SUM","ROW_PREFIX_SUM"):
        rows=[x for x in obs if x["operator"]==op]; bg[op]=sum(x["match"] for x in rows)/len(rows) if rows else 0.0
    by=defaultdict(list)
    for x in obs: by[(x["operator"],x["word"])].append(x)
    out=[]
    for (op,w),rows in sorted(by.items()):
        n=len(rows); docs={x["doc"] for x in rows}; k=sum(x["match"] for x in rows); rate=k/n if n else 0.0; lift=rate-bg[op]
        if n<cfg["minimum_eligible_occurrences"] or len(docs)<cfg["minimum_documents"]: continue
        if rate<cfg["minimum_arithmetic_match_rate"] or lift<cfg["minimum_absolute_rate_lift_over_operator_background"]: continue
        out.append({"operator":op,"word":w,"train_occurrences":n,"train_documents":len(docs),"train_matches":k,"train_match_rate":rate,"train_operator_background_rate":bg[op],"train_rate_lift":lift})
    return out,bg,{op:sum(1 for x in obs if x['operator']==op) for op in ("DOC_PREFIX_SUM","ROW_PREFIX_SUM")}


def score_test(test_docs,cand,spec):
    rows=[x for x in arithmetic_observations(test_docs,spec) if x["operator"]==cand["operator"] and x["word"]==cand["word"]]
    examples=[]; status=Counter()
    for x in rows:
        status["word:"+"+".join(x["word_statuses"])]+=1
        status["following:"+"+".join(x["following_statuses"])]+=1
        examples.append({"doc":x["doc"],"region":x["region"],"prior_terms":x["prior_terms"],"prefix_sum":qstr(x["prefix_sum"]),"following_value":qstr(x["following_value"]),"match":x["match"],"word_statuses":x["word_statuses"],"following_statuses":x["following_statuses"]})
    return {"heldout_occurrences":len(rows),"heldout_matches":sum(x["match"] for x in rows),"heldout_documents":sorted({x["doc"] for x in rows}),"heldout_regions":sorted({x["region"] for x in rows}),"status_distribution":dict(status),"examples":examples}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--corpus',required=True);ap.add_argument('--spec',required=True);ap.add_argument('--parent-canonical',required=True);ap.add_argument('--out',required=True);a=ap.parse_args()
    spec=json.load(open(a.spec,encoding='utf-8')); parent=json.load(open(a.parent_canonical,encoding='utf-8'))
    assert spec['source']['frozen_commit']==FROZEN_COMMIT
    assert spec['parent_canonical_target']=='v2.26'
    assert parent['version']=='v2.26' and parent['status']=='CURRENT_CANONICAL_RESEARCH_STATE'
    assert spec['status_policy']['none_or_doubtful_is_never_reinterpreted_as_certain'] is True
    assert spec['cross_fitting']['candidate_selection_train_only'] is True
    assert spec['train_candidate_gate']['manual_candidate_addition_forbidden'] is True
    assert spec['train_candidate_gate']['manual_candidate_removal_forbidden'] is True

    docs,reveal,failures=load_corpus(Path(a.corpus)); byfold={f:[d for d in docs if d['fold']==f] for f in range(5)}
    hist=defaultdict(lambda:{"selected_folds":[],"train_rows":[],"test_rows":[],"null_probs":[]}); perfold=[]
    for fold in range(5):
        train=[d for d in docs if d['fold']!=fold]; test=byfold[fold]; selected,bg,obs_counts=select_train(train,spec)
        held=0
        for cand in selected:
            sc=score_test(test,cand,spec); held+=sc['heldout_occurrences']; key=(cand['operator'],cand['word']); h=hist[key]
            h['selected_folds'].append(fold); h['train_rows'].append({'fold':fold,**cand}); h['test_rows'].append({'fold':fold,**sc}); h['null_probs'].extend([cand['train_operator_background_rate']]*sc['heldout_occurrences'])
        perfold.append({'fold':fold,'train_documents':len(train),'heldout_documents':len(test),'train_operator_observation_counts':obs_counts,'train_operator_background_match_rates':bg,'train_selected_candidates':len(selected),'heldout_occurrences_of_selected_candidates':held})

    cfg=spec['heldout_candidate_gate']; family=[]
    for (op,w),h in sorted(hist.items()):
        sf=sorted(h['selected_folds'])
        if len(sf)<cfg['minimum_selected_folds']: continue
        n=sum(x['heldout_occurrences'] for x in h['test_rows']); k=sum(x['heldout_matches'] for x in h['test_rows']); docs_all=sorted({d for x in h['test_rows'] for d in x['heldout_documents']}); regs=sorted({r for x in h['test_rows'] for r in x['heldout_regions']}); examples=[e for x in h['test_rows'] for e in x['examples']]; stat=Counter()
        for x in h['test_rows']: stat.update(x['status_distribution'])
        p=stats.poisson_binomial_upper_tail(h['null_probs'],k) if n else 1.0
        family.append({'operator':op,'word_token':w,'selected_folds':sf,'selected_fold_count':len(sf),'train_rows':h['train_rows'],'heldout_occurrences':n,'heldout_matches':k,'heldout_match_rate':k/n if n else None,'heldout_document_ids':docs_all,'heldout_document_count':len(docs_all),'heldout_region_set':regs,'heldout_status_distribution':dict(stat),'heldout_examples':examples,'p_value':p})
    q=stats.bh_qvalues(family); admitted=[]
    for row,qv in zip(family,q):
        row['BH_q']=qv; rate=row['heldout_match_rate'] or 0.0
        ok=bool(row['heldout_occurrences']>=cfg['minimum_heldout_occurrences'] and row['heldout_document_count']>=cfg['minimum_heldout_documents'] and rate>=cfg['minimum_heldout_match_rate'] and qv<=cfg['FDR_q_max'])
        row['ARITHMETIC_SUMMARY_BEHAVIOR_CANDIDATE_ADMITTED']=ok
        if ok: admitted.append(row)

    # Reveal source labels only after all candidate statistics and admissions exist.
    for row in family: row['source_word_after_scoring']=reveal.get(row['word_token'],row['word_token'])
    admitted=[x for x in family if x['ARITHMETIC_SUMMARY_BEHAVIOR_CANDIDATE_ADMITTED']]
    family.sort(key=lambda x:(not x['ARITHMETIC_SUMMARY_BEHAVIOR_CANDIDATE_ADMITTED'],x['BH_q'],-(x['heldout_match_rate'] or 0),-x['heldout_occurrences']))
    admitted.sort(key=lambda x:(x['BH_q'],-(x['heldout_match_rate'] or 0),-x['heldout_occurrences']))
    status='CROSS_FITTED_ARITHMETIC_SUMMARY_BEHAVIOR_CANDIDATES_ADMITTED' if admitted else 'CROSS_FITTED_ARITHMETIC_SUMMARY_BEHAVIOR_CANDIDATES_NOT_ESTABLISHED'
    result={'artifact_uuid':'JANUS-LINEAR-A-R7-B0-ARITHMETIC-SUMMARY-ROLE-RESULT-2026-08-15-v0.1','version':'v0.1','node_type':'cross_fitted_arithmetic_summary_behavior_result','status':status,'source':{'repository':'Hawkar-usls/lineara.xyz','frozen_commit':FROZEN_COMMIT,'parsed_documents':len(docs),'parse_failures_or_empty':failures},'method':{'folds':5,'operators':spec['operators'],'exact_rational_arithmetic':True,'multiple_testing':'Benjamini-Hochberg','FDR_q_max':cfg['FDR_q_max'],'null':cfg['null']},'per_fold':perfold,'cross_fitted_candidate_family_size':len(family),'admitted_candidate_count':len(admitted),'admitted_candidates':admitted,'candidate_family_after_scoring':family,'leakage_firewall':{'candidate_selection_used_heldout_documents':False,'source_word_labels_used_for_selection_or_scoring':False,'none_or_doubtful_reinterpreted_as_certain':False,'translations_used':False,'external_dictionaries_used':False,'Linear_B_supervision_used':False,'Notti_readings_used':False,'manual_candidate_addition_or_removal':False,'R3B_blind_eligibility_affected':False},'epistemic_gate':{'arithmetic_summary_behavior_candidates_established':bool(admitted),'probable_total_or_summary_function_established':False,'exact_word_meaning_established':False,'translation_established':False,'phonetic_value_established':False,'new_anchor_established':False,'decipherment_established':False,'R3B_external_replication_established':False},'next_gate':'Freeze admitted arithmetic candidate family unchanged for full cross-region transfer and structure-destroying arithmetic nulls.' if admitted else 'Preserve negative and continue to separately preregistered positional/document-template functional hypotheses.','claim_ceiling':spec['claim_ceiling']}
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps({'status':status,'family':len(family),'admitted':len(admitted)},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
