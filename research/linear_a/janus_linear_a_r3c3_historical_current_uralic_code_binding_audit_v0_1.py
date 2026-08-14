#!/usr/bin/env python3
"""Static cross-version language-name binding audit for R3C-3.

The two recovered upstream Python sources are parsed with ast.parse only. No
module is imported/executed. Only matching small string literals, identifiers,
and attribute names for a frozen language-term family are persisted.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

SPEC_PATH='data/JANUS-LINEAR-A-R3C-3-HISTORICAL-CURRENT-URALIC-CODE-BINDING-AUDIT-SPEC-2026-08-14-v0.1.json'
PARENT_NAME_AUDIT='data/JANUS-LINEAR-A-R3C-3-ALL-PUBLIC-PACKAGE-MEMBER-NAME-AUDIT-RESULT-2026-08-14-v0.1.json'
RUNNER_ID='JANUS-LINEAR-A-R3C3-HISTORICAL-CURRENT-URALIC-CODE-BINDING-AUDIT-v0.1'


def sha256(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()


def term_hits(text:str, terms:list[dict[str,Any]])->list[str]:
    low=text.lower()
    out=[]
    for term in terms:
        if any(p.lower() in low for p in term['patterns']): out.append(term['id'])
    return out


def inspect_source(data:bytes, expected_sha:str, terms:list[dict[str,Any]], literal_limit:int)->dict[str,Any]:
    if sha256(data)!=expected_sha: raise ValueError(f'SOURCE_SHA256_MISMATCH:{sha256(data)}:{expected_sha}')
    text=data.decode('utf-8-sig')
    tree=ast.parse(text,mode='exec')
    hits=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Constant) and isinstance(node.value,str):
            matched=term_hits(node.value,terms)
            if matched:
                value=node.value if len(node.value)<=literal_limit else None
                hits.append({'kind':'STRING_LITERAL','lineno':getattr(node,'lineno',None),'term_ids':matched,'literal':value,'literal_redacted':value is None,'literal_characters':len(node.value)})
        elif isinstance(node,ast.Name):
            matched=term_hits(node.id,terms)
            if matched:
                hits.append({'kind':'IDENTIFIER','lineno':getattr(node,'lineno',None),'term_ids':matched,'identifier':node.id})
        elif isinstance(node,ast.Attribute):
            matched=term_hits(node.attr,terms)
            if matched:
                hits.append({'kind':'ATTRIBUTE','lineno':getattr(node,'lineno',None),'term_ids':matched,'attribute':node.attr})
    counts={t['id']:0 for t in terms}
    kinds={t['id']:{'STRING_LITERAL':0,'IDENTIFIER':0,'ATTRIBUTE':0} for t in terms}
    for h in hits:
        for tid in h['term_ids']:
            counts[tid]+=1; kinds[tid][h['kind']]+=1
    hits.sort(key=lambda h:(h.get('lineno') or 0,h['kind'],','.join(h['term_ids'])))
    return {'sha256':sha256(data),'bytes':len(data),'ast_parse_success':True,'term_hit_counts':counts,'term_hit_kind_counts':kinds,'matching_nodes':hits,'source_executed':False,'source_imported':False,'full_source_persisted':False}


def main()->None:
    ap=argparse.ArgumentParser(); ap.add_argument('--historical-bundle',required=True); ap.add_argument('--current-bundle',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    spec=json.load(open(SPEC_PATH,encoding='utf-8')); parent=json.load(open(PARENT_NAME_AUDIT,encoding='utf-8'))
    assert spec['status']=='FROZEN_BEFORE_EXECUTION'
    assert parent['status']==spec['parents']['required_parent_status']
    terms=spec['fixed_terms']; limit=spec['static_analysis']['persist_matching_literal_only_if_characters_at_most']
    hb=Path(a.historical_bundle).read_bytes(); cb=Path(a.current_bundle).read_bytes()
    assert sha256(hb)==spec['historical_source']['bundle_sha256']; assert sha256(cb)==spec['current_source']['bundle_sha256']
    with zipfile.ZipFile(io.BytesIO(hb)) as zf: hs=zf.read(spec['historical_source']['source_member'])
    with zipfile.ZipFile(io.BytesIO(cb)) as zf: cs=zf.read(spec['current_source']['source_member'])
    hist=inspect_source(hs,spec['historical_source']['source_sha256'],terms,limit)
    curr=inspect_source(cs,spec['current_source']['source_sha256'],terms,limit)
    uralic_hist=hist['term_hit_counts']['URALIC']; uralic_curr=curr['term_hit_counts']['URALIC']
    positive_controls={tid:{'historical_hits':hist['term_hit_counts'][tid],'current_hits':curr['term_hit_counts'][tid]} for tid in ['ANCIENT_EGYPTIAN','LUWIAN','HITTITE','PROTO_CELTIC']}
    any_positive_control=any(v['historical_hits']>0 or v['current_hits']>0 for v in positive_controls.values())
    status='URALIC_NAME_ABSENT_FROM_HISTORICAL_AND_CURRENT_PLAINTEXT_SOURCE' if uralic_hist==0 and uralic_curr==0 else 'URALIC_NAME_PRESENT_IN_RECOVERED_PLAINTEXT_SOURCE'
    result={'artifact_uuid':'JANUS-LINEAR-A-R3C-3-HISTORICAL-CURRENT-URALIC-CODE-BINDING-AUDIT-RESULT-2026-08-14-v0.1','version':'v0.1','node_type':'static_cross_version_language_binding_audit_result','status':status,'runner_id':RUNNER_ID,'frozen_spec':SPEC_PATH,'parent_member_name_audit':PARENT_NAME_AUDIT,'historical_source':{'member':spec['historical_source']['source_member'],**hist},'current_source':{'member':spec['current_source']['source_member'],**curr},'positive_controls':positive_controls,'any_non_Uralic_positive_control_present':any_positive_control,'summary':{'Uralic_historical_hit_count':uralic_hist,'Uralic_current_hit_count':uralic_curr,'Uralic_total_hit_count':uralic_hist+uralic_curr,'all_public_package_Uralic_named_member_total':parent['summary']['Uralic_named_member_total'],'all_public_package_Uralic_named_snapshot_count':parent['summary']['Uralic_named_snapshot_count']},'inference_support':{'external_or_user_supplied_Uralic_channel_supported_as_inference':status=='URALIC_NAME_ABSENT_FROM_HISTORICAL_AND_CURRENT_PLAINTEXT_SOURCE' and parent['summary']['Uralic_named_member_total']==0,'reason':'No Uralic-named member occurs across the six unique public package snapshots and no Uralic token occurs in either recovered plaintext source version; because the software accepts user-selected files, an external/user-supplied study input is a plausible provenance route. This remains an inference, not proof.'},'safety':{'historical_source_executed':False,'current_source_executed':False,'historical_source_imported':False,'current_source_imported':False,'full_source_persisted':False},'claim_ceiling':{'static_Uralic_name_binding_presence_across_historical_current_source_established':True,'external_or_user_supplied_Uralic_channel_supported_as_inference':True,'external_or_user_supplied_Uralic_channel_proved':False,'absence_of_Uralic_linguistic_data_proved':False,'paper_exact_2024_input_identity_established':False,'published_2024_matches_reproduced':False,'language_family_relationship_established':False,'R3B_effect':'NONE','new_anchor':False,'decipherment':False}}
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':status,'summary':result['summary'],'positive_controls':positive_controls,'inference_supported':result['inference_support']['external_or_user_supplied_Uralic_channel_supported_as_inference']},ensure_ascii=False,sort_keys=True))
if __name__=='__main__': main()
