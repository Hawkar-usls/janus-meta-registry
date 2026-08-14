#!/usr/bin/env python3
"""Static current-vs-historical method differential for R3C-3.

Reads exact members from the current public ZIP in memory. Python is parsed with
ast.parse only and never imported/executed. BaseSheet.xlsx is treated as an
Office ZIP; only workbook/sheet names, declared dimensions, and first-row text
are retained. No scientific data rows are persisted.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SPEC='data/JANUS-LINEAR-A-R3C-3-CURRENT-SOURCE-METHOD-DIFFERENTIAL-SPEC-2026-08-14-v0.1.json'
HIST='data/JANUS-LINEAR-A-R3C-3-HISTORICAL-METHOD-SEMANTIC-EXTRACTION-RESULT-2026-08-14-v0.1.1.json'
CURRENT_PY='LinearADecipherment/LinearADecipherment.py'
CURRENT_XLSX='LinearADecipherment/BaseSheet.xlsx'
RUNNER='JANUS-LINEAR-A-R3C3-CURRENT-SOURCE-METHOD-DIFFERENTIAL-v0.1'
SELECTED_CALLS={'read_csv','read_excel','replace','lower','sort_values','drop_duplicates','to_csv','to_excel'}
NS_MAIN='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
NS_REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS_PKG_REL='http://schemas.openxmlformats.org/package/2006/relationships'


def sha256(data: bytes)->str:
    return hashlib.sha256(data).hexdigest()


def normalized_ast_hash(node: ast.AST)->str:
    return sha256(ast.dump(node,annotate_fields=True,include_attributes=False).encode('utf-8'))


def call_leaf(node: ast.Call)->str:
    f=node.func
    if isinstance(f,ast.Name): return f.id
    if isinstance(f,ast.Attribute): return f.attr
    return type(f).__name__


def function_record(fn: ast.FunctionDef|ast.AsyncFunctionDef)->dict[str,Any]:
    calls=Counter()
    for n in ast.walk(fn):
        if isinstance(n,ast.Call):
            leaf=call_leaf(n)
            if leaf in SELECTED_CALLS: calls[leaf]+=1
    return {
        'name':fn.name,
        'lineno':fn.lineno,
        'end_lineno':getattr(fn,'end_lineno',None),
        'normalized_ast_sha256':normalized_ast_hash(fn),
        'selected_call_counts':dict(sorted(calls.items())),
    }


def shared_strings(zf:zipfile.ZipFile)->list[str]:
    path='xl/sharedStrings.xml'
    if path not in zf.namelist(): return []
    root=ET.fromstring(zf.read(path))
    out=[]
    for si in root.findall(f'{{{NS_MAIN}}}si'):
        parts=[]
        for t in si.iter(f'{{{NS_MAIN}}}t'):
            parts.append(t.text or '')
        out.append(''.join(parts))
    return out


def col_index(ref:str)->int:
    m=re.match(r'([A-Z]+)',ref.upper())
    if not m: return 10**9
    n=0
    for ch in m.group(1): n=n*26+(ord(ch)-64)
    return n


def xlsx_schema(data:bytes)->dict[str,Any]:
    with zipfile.ZipFile(io.BytesIO(data),'r') as zf:
        names=set(zf.namelist())
        wb=ET.fromstring(zf.read('xl/workbook.xml'))
        rels=ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
        relmap={r.attrib['Id']:r.attrib['Target'] for r in rels.findall(f'{{{NS_PKG_REL}}}Relationship')}
        ss=shared_strings(zf)
        sheets=[]
        for sh in wb.find(f'{{{NS_MAIN}}}sheets') or []:
            sname=sh.attrib.get('name','')
            rid=sh.attrib.get(f'{{{NS_REL}}}id')
            target=relmap.get(rid or '')
            if not target:
                sheets.append({'name':sname,'target_missing':True}); continue
            target=target.lstrip('/')
            if not target.startswith('xl/'): target='xl/'+target
            target=str(Path(target))
            root=ET.fromstring(zf.read(target))
            dim=root.find(f'{{{NS_MAIN}}}dimension')
            dimref=dim.attrib.get('ref') if dim is not None else None
            first=[]
            sd=root.find(f'{{{NS_MAIN}}}sheetData')
            row1=None
            if sd is not None:
                for row in sd.findall(f'{{{NS_MAIN}}}row'):
                    if row.attrib.get('r')=='1': row1=row; break
            if row1 is not None:
                cells=[]
                for c in row1.findall(f'{{{NS_MAIN}}}c'):
                    cref=c.attrib.get('r','')
                    formula=c.find(f'{{{NS_MAIN}}}f')
                    typ=c.attrib.get('t')
                    text=''
                    if formula is not None:
                        text='__FORMULA_REDACTED__'
                    elif typ=='s':
                        v=c.find(f'{{{NS_MAIN}}}v')
                        if v is not None and v.text is not None:
                            idx=int(v.text); text=ss[idx] if 0<=idx<len(ss) else '__BAD_SHARED_STRING_INDEX__'
                    elif typ=='inlineStr':
                        isel=c.find(f'{{{NS_MAIN}}}is')
                        if isel is not None: text=''.join((t.text or '') for t in isel.iter(f'{{{NS_MAIN}}}t'))
                    else:
                        v=c.find(f'{{{NS_MAIN}}}v')
                        text='' if v is None or v.text is None else v.text
                    cells.append((col_index(cref),cref,text))
                first=[{'cell':ref,'text':text} for _,ref,text in sorted(cells)]
            sheets.append({'name':sname,'worksheet_target':target,'declared_dimension':dimref,'first_row':first,'non_header_rows_persisted':False})
        return {
            'sheet_count':len(sheets),
            'sheets':sheets,
            'shared_string_count':len(ss),
            'macro_member_present':any(n.lower().endswith('vbaproject.bin') for n in names),
            'formulas_executed':False,
            'non_header_cell_values_persisted':False,
        }


def main()->None:
    ap=argparse.ArgumentParser(); ap.add_argument('bundle'); ap.add_argument('--out',required=True); a=ap.parse_args()
    spec=json.load(open(SPEC,encoding='utf-8')); hist=json.load(open(HIST,encoding='utf-8'))
    assert spec['status']=='FROZEN_BEFORE_EXECUTION'
    raw=Path(a.bundle).read_bytes()
    assert len(raw)==spec['current_bundle']['bytes'] and sha256(raw)==spec['current_bundle']['sha256']
    with zipfile.ZipFile(io.BytesIO(raw),'r') as zf:
        py=zf.read(CURRENT_PY); xlsx=zf.read(CURRENT_XLSX)
    assert len(py)==spec['current_bundle']['source_member']['bytes'] and sha256(py)==spec['current_bundle']['source_member']['sha256']
    assert len(xlsx)==spec['current_bundle']['base_sheet_member']['bytes'] and sha256(xlsx)==spec['current_bundle']['base_sheet_member']['sha256']
    text=py.decode('utf-8-sig'); tree=ast.parse(text,filename=CURRENT_PY,mode='exec')
    allf=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
    byname=defaultdict(list)
    for f in allf: byname[f.name].append(f)
    for rows in byname.values(): rows.sort(key=lambda f:f.lineno)
    hist_byname=defaultdict(list)
    for r in hist['functions']: hist_byname[r['name']].append(r)
    for rows in hist_byname.values(): rows.sort(key=lambda r:r['lineno'])
    targets=[]
    for name in spec['target_function_names']:
        current=[function_record(f) for f in byname.get(name,[])]
        historical=hist_byname.get(name,[])
        comparisons=[]
        for i in range(max(len(current),len(historical))):
            c=current[i] if i<len(current) else None; h=historical[i] if i<len(historical) else None
            comparisons.append({'occurrence_index':i,'current_present':c is not None,'historical_present':h is not None,'current_ast_sha256':c['normalized_ast_sha256'] if c else None,'historical_ast_sha256':h['normalized_ast_sha256'] if h else None,'ast_structurally_identical':bool(c and h and c['normalized_ast_sha256']==h['normalized_ast_sha256']),'current_line_span':[c['lineno'],c['end_lineno']] if c else None,'historical_line_span':[h['lineno'],h['end_lineno']] if h else None,'current_selected_call_counts':c['selected_call_counts'] if c else None})
        targets.append({'name':name,'current_occurrence_count':len(current),'historical_occurrence_count':len(historical),'comparisons':comparisons})
    schema=xlsx_schema(xlsx)
    first_headers=[]
    if schema['sheets']:
        first_headers=[x['text'] for x in schema['sheets'][0].get('first_row',[])]
    historical_headers=spec['historical_baseline']['historical_base_sheet_csv']['headers']
    total_comp=sum(len(t['comparisons']) for t in targets)
    identical=sum(c['ast_structurally_identical'] for t in targets for c in t['comparisons'])
    current_present=sum(c['current_present'] for t in targets for c in t['comparisons'])
    historical_present=sum(c['historical_present'] for t in targets for c in t['comparisons'])
    result={'artifact_uuid':'JANUS-LINEAR-A-R3C-3-CURRENT-SOURCE-METHOD-DIFFERENTIAL-RESULT-2026-08-14-v0.1','version':'v0.1','node_type':'static_current_vs_historical_method_differential_result','status':'CURRENT_METHOD_DIFFERENTIAL_COMPLETE','frozen_spec':SPEC,'bundle':{'sha256':sha256(raw),'bytes':len(raw)},'current_source':{'path':CURRENT_PY,'sha256':sha256(py),'bytes':len(py),'ast_parse_success':True,'total_function_count':len(allf),'module_executed':False,'module_imported':False},'target_functions':targets,'target_summary':{'target_names':len(spec['target_function_names']),'comparison_slots':total_comp,'current_occurrences_present':current_present,'historical_occurrences_present':historical_present,'ast_structurally_identical_occurrences':identical,'ast_changed_or_missing_occurrences':total_comp-identical},'current_BaseSheet':{'path':CURRENT_XLSX,'sha256':sha256(xlsx),'bytes':len(xlsx),**schema,'first_sheet_first_row_text':first_headers,'historical_csv_headers':historical_headers,'first_sheet_headers_equal_historical_csv_headers':first_headers==historical_headers},'safety':{'current_source_executed':False,'current_source_imported':False,'xlsx_formulas_executed':False,'source_bodies_persisted':False,'BaseSheet_data_rows_persisted':False,'language_matching_performed':False},'readiness_effect':{'current_plaintext_method_static_diff_available':True,'current_BaseSheet_schema_available':True,'paper_exact_2024_method_identity_admitted':False,'paper_exact_2024_input_receipt_admitted':False,'scientific_five_language_execution_permitted':False},'claim_ceiling':{'current_vs_historical_static_method_change_established':True,'current_BaseSheet_schema_established':True,'paper_exact_2024_method_identity_established':False,'paper_exact_2024_inputs_established':False,'published_2024_matches_reproduced':False,'language_family_relationship_established':False,'R3B_effect':'NONE','new_anchor':False,'decipherment':False}}
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'total_functions':len(allf),'target_summary':result['target_summary'],'BaseSheet_headers':first_headers,'BaseSheet_headers_equal_historical':first_headers==historical_headers},ensure_ascii=False,sort_keys=True))
if __name__=='__main__': main()
