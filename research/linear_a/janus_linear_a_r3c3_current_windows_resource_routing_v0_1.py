#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path,PurePosixPath
from typing import Any
SPEC='data/JANUS-LINEAR-A-R3C-3-CURRENT-WINDOWS-STATIC-RESOURCE-ROUTING-SPEC-2026-08-14-v0.1.json'
QUAR='data/JANUS-LINEAR-A-R3C-3-CURRENT-WINDOWS-BUNDLE-QUARANTINE-RESULT-2026-08-14-v0.1.json'
COMP='data/JANUS-LINEAR-A-R3C-3-CURRENT-WINDOWS-BUNDLE-RESOURCE-COMPARISON-RESULT-2026-08-14-v0.1.json'

def matches(name:str,cat:dict[str,Any])->bool:
    low=name.lower(); ext=PurePosixPath(low).suffix
    exts={x.lower() for x in cat.get('extensions',[])}
    frags=[x.lower() for x in cat.get('name_fragments',[])]
    mode=cat['match_mode']
    if mode=='EXTENSION': return ext in exts
    if mode=='EXTENSION_AND_ANY_FRAGMENT': return ext in exts and any(f in low for f in frags)
    raise ValueError(f'UNKNOWN_MATCH_MODE:{mode}')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); a=ap.parse_args()
    s=json.load(open(SPEC,encoding='utf-8')); q=json.load(open(QUAR,encoding='utf-8')); c=json.load(open(COMP,encoding='utf-8'))
    assert s['status']=='FROZEN_BEFORE_EXECUTION'
    assert c['status']==s['parent']['required_comparison_status']
    assert q['sha256']==s['parent']['bundle_sha256']
    entries=(q.get('inventory') or {}).get('entries') or []
    routed=[]; counts={cat['id']:0 for cat in s['routing_categories']}
    for e in entries:
        if e.get('directory'): continue
        name=str(e.get('name',''))
        cats=[cat['id'] for cat in s['routing_categories'] if matches(name,cat)]
        if not cats: continue
        for cid in cats: counts[cid]+=1
        routed.append({'entry_index':e.get('entry_index'),'name':name,'declared_uncompressed_bytes':e.get('declared_uncompressed_bytes'),'sha256':e.get('sha256'),'code_or_executable_like':e.get('code_or_executable_like'),'categories':cats})
    routed.sort(key=lambda x:(x['entry_index'] if x['entry_index'] is not None else 10**9,x['name']))
    base=[r for r in routed if 'BASE_INPUT' in r['categories']]
    pys=[r for r in routed if 'PYTHON_SOURCE' in r['categories']]
    pyc=[r for r in routed if 'PYTHON_BYTECODE' in r['categories']]
    result={'artifact_uuid':'JANUS-LINEAR-A-R3C-3-CURRENT-WINDOWS-STATIC-RESOURCE-ROUTING-RESULT-2026-08-14-v0.1','version':'v0.1','node_type':'name_only_static_resource_routing_result','status':'CURRENT_WINDOWS_STATIC_RESOURCE_ROUTING_COMPLETE','frozen_spec':SPEC,'bundle':{'sha256':q['sha256'],'bytes':q['bytes'],'entry_count':q['inventory']['entry_count']},'category_counts':counts,'routed_resource_count':len(routed),'routed_resources':routed,'answers':{'plaintext_python_source_member_count':len(pys),'python_bytecode_member_count':len(pyc),'BaseSheet_candidates':[r for r in base if 'basesheet' in r['name'].lower() or 'base_sheet' in r['name'].lower()],'general_decipherment_candidate_count':counts['GENERAL_DECIPHERMENT'],'UI_or_working_source_candidate_count':counts['UI_OR_WORKING_SOURCE'],'packaged_library_candidate_count':counts['PACKAGED_LIBRARY']},'safety':{'member_payload_content_read':False,'members_extracted':False,'members_executed':False,'nested_archives_inspected':False,'lexical_content_inspected':False},'readiness_effect':{'name_only_routing_complete':True,'plaintext_python_source_candidate_available':len(pys)>0,'python_bytecode_candidate_available':len(pyc)>0,'BaseSheet_candidate_available':bool([r for r in base if 'basesheet' in r['name'].lower() or 'base_sheet' in r['name'].lower()]),'paper_exact_2024_input_receipt_admitted':False,'scientific_five_language_execution_permitted':False},'claim_ceiling':{'name_only_resource_routing_established':True,'paper_exact_2024_input_identity_established':False,'published_2024_matches_reproduced':False,'language_family_relationship_established':False,'R3B_effect':'NONE','new_anchor':False,'decipherment':False}}
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'routed':len(routed),'counts':counts,'plaintext_py':len(pys),'pyc':len(pyc),'base_candidates':[x['name'] for x in result['answers']['BaseSheet_candidates']]},ensure_ascii=False,sort_keys=True))
if __name__=='__main__': main()
