#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

REQUIRED_STATUS='CROSS_FITTED_POSITIONAL_FUNCTIONAL_ROLE_CANDIDATES_ADMITTED'

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--result',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    x=json.loads(Path(a.result).read_text(encoding='utf-8'))
    assert x['status']==REQUIRED_STATUS
    assert x['cross_fitted_candidate_family_size']==65
    assert x['admitted_candidate_count']==43
    assert len(x['admitted_candidates'])==43
    assert x['leakage_firewall']['manual_candidate_addition_or_removal'] is False
    assert x['epistemic_gate']['probable_function_established'] is False
    rows=[]
    seen=set()
    for r in x['admitted_candidates']:
        assert r['POSITIONAL_ROLE_CANDIDATE_ADMITTED'] is True
        key=(r['role'],r['word_token'])
        assert key not in seen; seen.add(key)
        rows.append({
          'candidate_id': hashlib.sha256((r['role']+'|'+r['word_token']).encode()).hexdigest()[:20],
          'role': r['role'],
          'word_token': r['word_token'],
          'source_word_after_scoring': r['source_word_after_scoring'],
          'selected_folds': r['selected_folds'],
          'selected_fold_count': r['selected_fold_count'],
          'heldout_eligible_occurrences': r['heldout_eligible_occurrences'],
          'heldout_role_hits': r['heldout_role_hits'],
          'heldout_role_precision': r['heldout_role_precision'],
          'heldout_document_count': r['heldout_document_count'],
          'heldout_role_hit_document_count': r['heldout_role_hit_document_count'],
          'heldout_region_set': r['heldout_region_set'],
          'p_value': r['p_value'],
          'BH_q': r['BH_q'],
        })
    rows.sort(key=lambda r:(r['role'],r['source_word_after_scoring'],r['word_token']))
    out={
      'artifact_uuid':'JANUS-LINEAR-A-R7-C0-ADMITTED-CANDIDATE-FAMILY-FREEZE-2026-08-16-v0.1',
      'version':'v0.1',
      'node_type':'immutable_admitted_candidate_family_freeze',
      'status':'R7_C0_ADMITTED_FAMILY_FROZEN_43_OF_65',
      'source_result':a.result,
      'source_result_sha256':sha256(a.result),
      'source_result_status':x['status'],
      'source_candidate_family_size':65,
      'frozen_candidate_count':43,
      'selection_rule':'exactly every R7-C0 row with POSITIONAL_ROLE_CANDIDATE_ADMITTED=true; no additions, removals, ranking filter, or semantic selection',
      'candidate_family':rows,
      'downstream_constraints':{
        'R7_C1_candidate_addition_forbidden':True,
        'R7_C1_candidate_removal_forbidden':True,
        'R7_C2_candidate_addition_forbidden':True,
        'R7_C2_candidate_removal_forbidden':True,
        'human_readable_label_may_not_control_downstream_selection':True,
        'probable_function_claim_before_C1_C2_forbidden':True
      },
      'epistemic_gate':{
        'cross_fitted_positional_candidates_established':True,
        'probable_function_established':False,
        'exact_word_meaning_established':False,
        'translation_established':False,
        'decipherment_established':False,
        'R3B_external_replication_established':False
      }
    }
    Path(a.out).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':out['status'],'count':43,'source_sha256':out['source_result_sha256'],'roles':dict(__import__('collections').Counter(r['role'] for r in rows))},ensure_ascii=False,sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
