#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

SPEC='data/JANUS-LINEAR-A-R3C-3-CURRENT-SOURCE-METHOD-DIFFERENTIAL-CORRECTIVE-SPEC-2026-08-14-v0.1.1.json'
CUR='data/JANUS-LINEAR-A-R3C-3-CURRENT-SOURCE-METHOD-DIFFERENTIAL-RESULT-2026-08-14-v0.1.json'
FLOW='data/JANUS-LINEAR-A-R3C-3-HISTORICAL-DATAFLOW-RECONSTRUCTION-RESULT-2026-08-14-v0.1.json'
LOADERS=['openFileDialog','openFileDialog_new_update','openFileDialog1','openFileDialog2']

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); a=ap.parse_args()
    s=json.load(open(SPEC,encoding='utf-8')); cur=json.load(open(CUR,encoding='utf-8')); flow=json.load(open(FLOW,encoding='utf-8'))
    assert s['status']=='FROZEN_AFTER_V0_1_BASELINE_GAP_BEFORE_RECONCILIATION'
    assert cur['status']=='CURRENT_METHOD_DIFFERENTIAL_COMPLETE'
    assert flow['status']=='HISTORICAL_DATAFLOW_MACHINE_RECONSTRUCTED'
    assert cur['bundle']['sha256']==s['admission']['required_current_bundle_sha256']
    assert cur['current_BaseSheet']['first_sheet_headers_equal_historical_csv_headers'] is True
    by=defaultdict(list)
    for r in flow['functions']:
        if r['name'] in LOADERS: by[r['name']].append(r)
    for rows in by.values(): rows.sort(key=lambda r:r['lineno'])
    assert all(len(by[n])>=1 for n in LOADERS), {n:len(by[n]) for n in LOADERS}
    out=deepcopy(cur)
    for t in out['target_functions']:
        if t['name'] not in LOADERS: continue
        hist=by[t['name']]
        current_comp=t['comparisons']
        assert len(current_comp)==len(hist), (t['name'],len(current_comp),len(hist))
        t['historical_occurrence_count']=len(hist)
        for i,(c,h) in enumerate(zip(current_comp,hist)):
            assert c['occurrence_index']==i and c['current_present'] is True
            c['historical_present']=True
            c['historical_ast_sha256']=h['normalized_ast_sha256']
            c['historical_line_span']=[h['lineno'],h['end_lineno']]
            c['ast_structurally_identical']=c['current_ast_sha256']==h['normalized_ast_sha256']
            c['historical_baseline_source']='HISTORICAL_DATAFLOW_RECONSTRUCTION_v0.1'
    slots=[c for t in out['target_functions'] for c in t['comparisons']]
    out['artifact_uuid']='JANUS-LINEAR-A-R3C-3-CURRENT-SOURCE-METHOD-DIFFERENTIAL-RESULT-2026-08-14-v0.1.1'
    out['version']='v0.1.1'
    out['node_type']='static_current_vs_historical_method_differential_corrected_baseline_result'
    out['status']='CURRENT_METHOD_DIFFERENTIAL_CORRECTED_BASELINE_COMPLETE'
    out['corrective_spec']=SPEC
    out['parent_v0_1']=CUR
    out['correction']={'affected_loader_names':LOADERS,'current_AST_hashes_recomputed':False,'historical_source_reparsed':False,'current_source_reparsed':False,'BaseSheet_observation_changed':False,'target_function_set_changed':False,'scientific_content_reinterpreted':False}
    out['target_summary']={
      'target_names':len(out['target_functions']),
      'comparison_slots':len(slots),
      'current_occurrences_present':sum(c['current_present'] for c in slots),
      'historical_occurrences_present':sum(c['historical_present'] for c in slots),
      'ast_structurally_identical_occurrences':sum(c['ast_structurally_identical'] for c in slots),
      'ast_changed_or_missing_occurrences':sum(not c['ast_structurally_identical'] for c in slots)
    }
    out['loader_reconciliation']={n:{'current_occurrences':next(t for t in out['target_functions'] if t['name']==n)['current_occurrence_count'],'historical_occurrences':len(by[n]),'all_occurrences_ast_identical':all(c['ast_structurally_identical'] for c in next(t for t in out['target_functions'] if t['name']==n)['comparisons'])} for n in LOADERS}
    out['readiness_effect']['current_vs_historical_loader_baseline_reconciled']=True
    out['claim_ceiling']['paper_exact_2024_method_identity_established']=False
    Path(a.out).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':out['status'],'summary':out['target_summary'],'loaders':out['loader_reconciliation'],'BaseSheet_headers_equal_historical':out['current_BaseSheet']['first_sheet_headers_equal_historical_csv_headers']},ensure_ascii=False,sort_keys=True))
if __name__=='__main__': main()
