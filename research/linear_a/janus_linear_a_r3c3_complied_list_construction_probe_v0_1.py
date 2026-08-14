#!/usr/bin/env python3
from __future__ import annotations
import argparse, ast, io, json, zipfile
from pathlib import Path
import janus_linear_a_r3c3_historical_method_semantic_extract_v0_1 as v01
import janus_linear_a_r3c3_historical_method_semantic_extract_v0_1_1 as v011
SPEC='data/JANUS-LINEAR-A-R3C-3-COMPLIED-LIST-CONSTRUCTION-PROBE-SPEC-2026-08-14-v0.1.json'
PARENT='data/JANUS-LINEAR-A-R3C-3-HISTORICAL-BINDING-PROBE-RESULT-2026-08-14-v0.1.json'
BUNDLE_SHA='a4627d4c2e26668593e8f6f9c8a004ae75bb3f1bbf497a39c0d4a772c9012850'
PY_SHA='bf204b1751f6b961a6f2f04b2576e3770cd29ae81e42c2a23f44d13d8458d76e'
MEMBER='LinearADecipherment/Working_UI_ab_update.py'

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('bundle'); ap.add_argument('--out',required=True); a=ap.parse_args()
    s=json.load(open(SPEC,encoding='utf-8')); p=json.load(open(PARENT,encoding='utf-8'))
    assert s['status']=='FROZEN_BEFORE_EXECUTION'; assert p['status']==s['required_parent_status']
    raw=Path(a.bundle).read_bytes(); assert v01.sha(raw)==BUNDLE_SHA
    with zipfile.ZipFile(io.BytesIO(raw)) as z: py=z.read(MEMBER)
    assert v01.sha(py)==PY_SHA
    tree=ast.parse(py.decode('utf-8-sig'),filename=MEMBER); lo,hi=s['module_line_range']
    ops=[]
    for stmt in tree.body:
        ln=getattr(stmt,'lineno',0)
        if lo <= ln <= hi and not isinstance(stmt,(ast.Import,ast.ImportFrom,ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
            ops.append(v011.stmt_ir(stmt,100))
    bad=sorted({x['ast_type'] for x in v01.walk_stmt_ir(ops) if x.get('type') in {'OTHER_STMT','OTHER_EXPR'} and 'ast_type' in x})
    result={'artifact_uuid':'JANUS-LINEAR-A-R3C-3-COMPLIED-LIST-CONSTRUCTION-PROBE-RESULT-2026-08-14-v0.1','version':'v0.1','node_type':'module_slice_semantic_probe_result','status':'COMPLIED_LIST_CONSTRUCTION_SLICE_MACHINE_REPRESENTED' if not bad else 'COMPLIED_LIST_CONSTRUCTION_SLICE_PARTIAL','frozen_spec':SPEC,'module_line_range':[lo,hi],'operations':ops,'unsupported_ast_types':bad,'safety':{'source_executed':False,'source_imported':False,'language_matching_performed':False},'claim_ceiling':{'construction_path_only':True,'historical_replay_not_yet_run':True,'paper_exact_2024_execution_permitted':False,'R3B_effect':'NONE','new_anchor':False,'decipherment':False}}
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'operations':len(ops),'unsupported':bad},sort_keys=True))
if __name__=='__main__': main()
