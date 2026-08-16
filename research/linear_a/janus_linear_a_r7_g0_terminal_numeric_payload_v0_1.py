#!/usr/bin/env python3
"""R7-G0 blocked numeric-payload profile test for KU-RO N|END events.

The event family, log2 transform, energy-distance statistic, blocked permutation null,
and all thresholds are frozen before numeric payload values are inspected. A positive
result is structural/quantitative only and cannot establish TOTAL/SUMMARY semantics.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import janus_linear_a_r7_arithmetic_summary_role_v0_1 as b0
import janus_linear_a_r7_f0_ku_ro_downstream_slot_v0_1 as f0
import janus_linear_a_r7_positional_template_roles_v0_1 as c0

SPEC_ID="JANUS-LINEAR-A-R7-G0-TERMINAL-NUMERIC-PAYLOAD-PROFILE-2026-08-16-v0.1"
CORPUS_COMMIT="43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
TARGET="KU-RO"; TARGET_TOKEN="6a2ea59b95fe1b610d20"; REGION="HT"; SIGNATURE="N|END"
NULL_N=10000; NULL_SEED=71701

class G0Error(ValueError): pass
def require(ok: bool,msg: str)->None:
    if not ok: raise G0Error(msg)
def load_json(path: Path)->Dict[str,Any]:
    x=json.loads(path.read_text(encoding='utf-8')); require(isinstance(x,dict),f'{path}: object required'); return x

def validate(spec:Mapping[str,Any],parent:Mapping[str,Any],f1:Mapping[str,Any])->None:
    require(spec.get('spec_id')==SPEC_ID,'spec id mismatch'); require(spec.get('stage')=='R7-G0','stage mismatch'); require(spec.get('status')=='PREREGISTERED_BEFORE_NUMERIC_PAYLOAD_INSPECTION','spec status mismatch')
    require(parent.get('version')=='v2.31' and parent.get('status')=='CURRENT_CANONICAL_RESEARCH_STATE','canonical mismatch'); require(parent.get('canonicality',{}).get('canonicality_audit_status')=='CANONICALITY_AUDIT_PASS','canonical audit mismatch')
    p=spec.get('parent',{}); require(p.get('canonical_version')=='v2.31','parent version drift'); require(p.get('target')==TARGET and p.get('opaque_target_token')==TARGET_TOKEN,'target drift'); require(p.get('region')==REGION,'region drift'); require(p.get('internal_F1_refinement')=='ROW-OPENING-WITH-TERMINAL-NUMERIC-SLOT-LIKE','F1 refinement drift')
    require(f1.get('status')=='INTERNAL_POST_F0_TERMINAL_NUMERIC_SLOT_REFINEMENT_ADMITTED','F1 status mismatch'); require(f1.get('candidate',{}).get('signature')==SIGNATURE,'F1 signature mismatch'); require(f1.get('admission',{}).get('internal_post_F0_terminal_numeric_slot_refinement_established') is True,'F1 admission missing')
    source=spec.get('source',{}); require(source.get('frozen_commit')==CORPUS_COMMIT,'corpus drift'); require(source.get('numeric_payload_values_inspected_before_freeze') is False,'pre-freeze payload inspection forbidden')
    require(spec.get('event_family',{}).get('required_TWO_KIND_signature')==SIGNATURE,'event family drift'); require(spec.get('primary_statistic',{}).get('transform')=='log2(exact_positive_numeric_value)','transform drift')
    null=spec.get('object_blocked_null',{}); require(null.get('permutations')==NULL_N and null.get('seed')==NULL_SEED,'null drift'); require(null.get('empirical_p_max')==0.01,'p threshold drift')
    anti=spec.get('anti_flexibility',{}); require(anti and all(v is True for v in anti.values()),'anti-flexibility must be true')
    ceiling=spec.get('claim_ceiling',{}); require(ceiling.get('TOTAL_or_SUMMARY_semantic_function_established') is False,'semantic ceiling violation'); require(ceiling.get('exact_word_meaning_established') is False and ceiling.get('translation_established') is False and ceiling.get('decipherment_established') is False,'claim ceiling violation')

def qstr(x:Fraction)->str: return b0.qstr(x)
def median_fraction(vals:Sequence[Fraction])->Fraction:
    s=sorted(vals); n=len(s); require(n>0,'empty median'); return s[n//2] if n%2 else (s[n//2-1]+s[n//2])/2

def bucket(v:Fraction)->str:
    if v<1: return 'FRAC'
    if v==1: return 'ONE'
    if v<5: return '2_4'
    if v<10: return '5_9'
    return '10PLUS'

def energy_distance(a:Sequence[float],b:Sequence[float])->float:
    require(a and b,'energy groups empty')
    cross=sum(abs(x-y) for x in a for y in b)/(len(a)*len(b))
    aa=sum(abs(x-y) for x in a for y in a)/(len(a)*len(a))
    bb=sum(abs(x-y) for x in b for y in b)/(len(b)*len(b))
    return max(0.0,2*cross-aa-bb)

def build_numeric_events(docs:Sequence[Mapping[str,Any]])->List[Dict[str,Any]]:
    docmap={d['doc']:d for d in docs}; out=[]
    for event in f0.build_events(docs):
        if event.get('bundle',[None,None,None])[2] != SIGNATURE: continue
        doc=docmap[event['doc']]; seq=doc['sequence']; row=event['row']; rows=c0.row_index_sequences(seq); require(row in rows,'row missing')
        idxs=rows[row]; lexical=[i for i in idxs if seq[i].get('kind')=='W']; require(lexical,'no lexical anchor'); anchor=lexical[0]
        require(seq[anchor].get('word')==event.get('word'),'row-first anchor mismatch')
        suffix=[i for i in idxs if i>anchor]
        require(len(suffix)==1 and seq[suffix[0]].get('kind')=='N','N|END binding mismatch')
        value=seq[suffix[0]].get('value'); require(isinstance(value,Fraction) and value>0,'exact positive Fraction required')
        out.append({'doc':event['doc'],'object_id':event['object_id'],'row':row,'is_target':bool(event['is_target']),'anchor_word':event['word'],'value':value,'log2_value':math.log2(float(value))})
    return out

def groups_by_object(events:Sequence[Mapping[str,Any]])->Dict[str,List[int]]:
    out=defaultdict(list)
    for i,e in enumerate(events): out[e['object_id']].append(i)
    return dict(out)

def exchangeable(events:Sequence[Mapping[str,Any]])->tuple[List[Dict[str,Any]],List[str]]:
    by=groups_by_object(events); objects=[]
    for oid,idxs in by.items():
        t=sum(events[i]['is_target'] for i in idxs); c=len(idxs)-t
        if t>0 and c>0: objects.append(oid)
    keep=set(objects); return [dict(e) for e in events if e['object_id'] in keep],sorted(objects)

def statistic(events:Sequence[Mapping[str,Any]],labels:Sequence[bool]|None=None)->float:
    if labels is None: labels=[bool(e['is_target']) for e in events]
    ta=[float(e['log2_value']) for e,l in zip(events,labels) if l]; co=[float(e['log2_value']) for e,l in zip(events,labels) if not l]
    return energy_distance(ta,co)

def permuted_labels(events:Sequence[Mapping[str,Any]],by:Mapping[str,Sequence[int]],rng:random.Random)->List[bool]:
    labels=[bool(e['is_target']) for e in events]
    out=list(labels)
    for idxs in by.values():
        vals=[labels[i] for i in idxs]; rng.shuffle(vals)
        for i,v in zip(idxs,vals): out[i]=v
    return out

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--corpus',required=True); ap.add_argument('--spec',required=True); ap.add_argument('--canonical',required=True); ap.add_argument('--f1-result',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    spec=load_json(Path(a.spec)); parent=load_json(Path(a.canonical)); f1=load_json(Path(a.f1_result)); validate(spec,parent,f1)
    docs,reveal,failures=b0.load_corpus(Path(a.corpus)); all_events=build_numeric_events(docs)
    targets=[e for e in all_events if e['is_target']]; target_objects=Counter(e['object_id'] for e in targets)
    ex_events,ex_objects=exchangeable(all_events); ex_targets=[e for e in ex_events if e['is_target']]; ex_controls=[e for e in ex_events if not e['is_target']]
    max_obj=max(target_objects.values())/len(targets) if targets else 1.0
    scfg=spec['support_gates']; support_checks={
      'minimum_all_target_N_END_events':len(targets)>=scfg['minimum_all_target_N_END_events'],
      'minimum_exchangeable_target_events':len(ex_targets)>=scfg['minimum_exchangeable_target_events'],
      'minimum_exchangeable_target_physical_objects':len(ex_objects)>=scfg['minimum_exchangeable_target_physical_objects'],
      'minimum_exchangeable_control_events':len(ex_controls)>=scfg['minimum_exchangeable_control_events'],
      'maximum_single_target_object_event_fraction':max_obj<=scfg['maximum_single_target_object_event_fraction']}
    support_pass=all(support_checks.values())
    obs=statistic(ex_events) if ex_targets and ex_controls else 0.0
    by=groups_by_object(ex_events); rng=random.Random(NULL_SEED); ge=0; null_sum=0.0
    for _ in range(NULL_N):
        lab=permuted_labels(ex_events,by,rng); st=statistic(ex_events,lab); null_sum+=st
        if st>=obs-1e-15: ge+=1
    null_mean=null_sum/NULL_N; p=(1+ge)/(1+NULL_N); effect=obs-null_mean
    loo=[]
    for drop in ex_objects:
        subset=[e for e in ex_events if e['object_id']!=drop]
        val=statistic(subset) if any(e['is_target'] for e in subset) and any(not e['is_target'] for e in subset) else 0.0
        retained=val>=0.5*obs if obs>0 else False; loo.append({'dropped_object':drop,'energy_distance':val,'retains_at_least_half_full_effect':retained})
    loo_fraction=sum(x['retains_at_least_half_full_effect'] for x in loo)/len(loo) if loo else 0.0
    ecfg=spec['effect_and_robustness_gates']; effect_checks={'minimum_observed_minus_null_mean_energy':effect>=ecfg['minimum_observed_minus_null_mean_energy'],'minimum_LOO_retention_fraction':loo_fraction>=ecfg['minimum_LOO_retention_fraction']}
    null_pass=p<=spec['object_blocked_null']['empirical_p_max']; admitted=bool(support_pass and null_pass and all(effect_checks.values()))
    status='INTERNAL_TERMINAL_NUMERIC_PAYLOAD_DISTRIBUTION_DIFFERENCE_ESTABLISHED' if admitted else 'TERMINAL_NUMERIC_PAYLOAD_DISTRIBUTION_DIFFERENCE_NOT_ESTABLISHED'
    tvals=[e['value'] for e in ex_targets]; cvals=[e['value'] for e in ex_controls]; tlogs=[e['log2_value'] for e in ex_targets]; clogs=[e['log2_value'] for e in ex_controls]
    result={
      'artifact_uuid':'JANUS-LINEAR-A-R7-G0-TERMINAL-NUMERIC-PAYLOAD-PROFILE-RESULT-2026-08-16-v0.1','stage':'R7-G0','status':status,
      'parent':{'canonical_version':'v2.31','target':TARGET,'region':REGION,'probable_parent_role':'ROW-OPENING-LIKE','internal_F1_refinement':'ROW-OPENING-WITH-TERMINAL-NUMERIC-SLOT-LIKE'},
      'source':{'repository':'Hawkar-usls/lineara.xyz','frozen_commit':CORPUS_COMMIT,'parsed_documents':len(docs),'parse_failures_or_empty':failures,'numeric_payload_values_inspected_before_freeze':False},
      'support':{'all_N_END_events':len(all_events),'all_target_N_END_events':len(targets),'all_target_physical_objects':len(target_objects),'exchangeable_target_events':len(ex_targets),'exchangeable_control_events':len(ex_controls),'exchangeable_target_physical_objects':len(ex_objects),'maximum_single_target_object_event_fraction':max_obj,'checks':support_checks,'support_pass':support_pass},
      'primary_test':{'transform':'log2(exact_positive_numeric_value)','statistic':'one-dimensional energy distance','observed_energy_distance':obs,'null_mean_energy_distance':null_mean,'observed_minus_null_mean_energy':effect,'permutations':NULL_N,'seed':NULL_SEED,'ge_observed':ge,'empirical_p':p,'p_threshold':spec['object_blocked_null']['empirical_p_max'],'permutation_p_pass':null_pass,'effect_checks':effect_checks,'effect_and_robustness_pass':all(effect_checks.values()),'leave_one_target_object_out_retention_fraction':loo_fraction,'leave_one_target_object_out':loo},
      'postscore_descriptive_profile':{
        'target_exchangeable_event_count':len(tvals),'control_exchangeable_event_count':len(cvals),
        'target_exact_median':qstr(median_fraction(tvals)) if tvals else None,'control_exact_median':qstr(median_fraction(cvals)) if cvals else None,
        'target_log2_median':sorted(tlogs)[len(tlogs)//2] if tlogs else None,'control_log2_median':sorted(clogs)[len(clogs)//2] if clogs else None,
        'target_magnitude_bucket_counts':dict(Counter(bucket(v) for v in tvals)),'control_magnitude_bucket_counts':dict(Counter(bucket(v) for v in cvals)),
        'per_object_counts':[{'object_id':oid,'target_events':sum(e['is_target'] for e in ex_events if e['object_id']==oid),'control_events':sum(not e['is_target'] for e in ex_events if e['object_id']==oid)} for oid in ex_objects],
        'descriptors_are_not_separate_inference':True},
      'admission':{'numeric_payload_distribution_difference_established':admitted,'allowed_claim':spec['admission']['allowed_claim_if_pass'] if admitted else None,'semantic_function_established':False},
      'epistemic_gate':{'parent_probable_region_scoped_ROW_OPENING_LIKE_retained':True,'F1_internal_terminal_numeric_slot_refinement_retained':True,'numeric_payload_distribution_difference_established':admitted,'TOTAL_or_SUMMARY_semantic_function_established':False,'exact_word_meaning_established':False,'translation_established':False,'phonetic_value_established':False,'language_family_established':False,'new_anchor_established':False,'universal_cross_region_function_established':False,'external_replication_established':False,'decipherment_established':False},
      'next_gate':'If positive, freeze the quantitative profile only as an internal structural property; any semantic interpretation or confirmatory mechanism requires untouched/external evidence. If negative, retain F1 structural refinement without a distinct numeric-value profile.',
      'claim_ceiling':spec['claim_ceiling']}
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':status,'target_all':len(targets),'target_exchangeable':len(ex_targets),'control_exchangeable':len(ex_controls),'objects':len(ex_objects),'energy':obs,'null_mean':null_mean,'effect':effect,'p':p,'LOO_retention':loo_fraction,'admitted':admitted},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
