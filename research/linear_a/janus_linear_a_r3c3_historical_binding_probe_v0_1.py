#!/usr/bin/env python3
"""Static targeted binding probe for historical Linear A software.

Finds assignments/references for a predeclared identifier set through AST only.
No recovered source is imported or executed.
"""
from __future__ import annotations
import argparse, ast, io, json, zipfile
from pathlib import Path
import janus_linear_a_r3c3_historical_method_semantic_extract_v0_1 as v01
import janus_linear_a_r3c3_historical_method_semantic_extract_v0_1_1 as v011

TARGETS={"complied_list","complied_list2","alphabets","special_characters","vowels","df_load","df_load2","LinAcol1","LinAcol2","LinAcol3","LinAcol4","LinAcol5"}
BUNDLE_SHA="a4627d4c2e26668593e8f6f9c8a004ae75bb3f1bbf497a39c0d4a772c9012850"
PY_SHA="bf204b1751f6b961a6f2f04b2576e3770cd29ae81e42c2a23f44d13d8458d76e"
MEMBER="LinearADecipherment/Working_UI_ab_update.py"


def target_names(n: ast.AST) -> set[str]:
    out=set()
    if isinstance(n,ast.Name): out.add(n.id)
    elif isinstance(n,ast.Attribute): out.add(n.attr); p=v01.dotted(n); out.add(p or n.attr)
    elif isinstance(n,(ast.Tuple,ast.List)):
        for e in n.elts: out |= target_names(e)
    elif isinstance(n,ast.Subscript): out |= target_names(n.value)
    return out


def scope_for(node: ast.AST, parents: dict[int,ast.AST]) -> str:
    cur=parents.get(id(node))
    while cur is not None:
        if isinstance(cur,(ast.FunctionDef,ast.AsyncFunctionDef)): return f"function:{cur.name}@{cur.lineno}"
        if isinstance(cur,ast.ClassDef): return f"class:{cur.name}@{cur.lineno}"
        cur=parents.get(id(cur))
    return "module"


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("bundle"); ap.add_argument("--out",required=True); a=ap.parse_args()
    raw=Path(a.bundle).read_bytes(); assert v01.sha(raw)==BUNDLE_SHA
    with zipfile.ZipFile(io.BytesIO(raw)) as z: py=z.read(MEMBER)
    assert v01.sha(py)==PY_SHA
    tree=ast.parse(py.decode('utf-8-sig'),filename=MEMBER)
    parents={}
    for p in ast.walk(tree):
        for c in ast.iter_child_nodes(p): parents[id(c)]=p
    rows=[]
    for node in ast.walk(tree):
        ts=[]
        if isinstance(node,ast.Assign):
            for t in node.targets: ts.extend(target_names(t))
        elif isinstance(node,ast.AnnAssign): ts.extend(target_names(node.target))
        elif isinstance(node,ast.AugAssign): ts.extend(target_names(node.target))
        hit=sorted(x for x in set(ts) if x in TARGETS or x.split('.')[-1] in TARGETS)
        if hit:
            rows.append({"lineno":node.lineno,"end_lineno":getattr(node,'end_lineno',None),"scope":scope_for(node,parents),"targets":hit,"statement":v011.stmt_ir(node,100)})
    refs={t:[] for t in sorted(TARGETS)}
    for node in ast.walk(tree):
        if isinstance(node,ast.Name) and node.id in TARGETS: refs[node.id].append({"lineno":node.lineno,"ctx":type(node.ctx).__name__,"scope":scope_for(node,parents)})
        elif isinstance(node,ast.Attribute) and node.attr in TARGETS: refs[node.attr].append({"lineno":node.lineno,"ctx":type(node.ctx).__name__,"scope":scope_for(node,parents),"path":v01.dotted(node)})
    result={"artifact_uuid":"JANUS-LINEAR-A-R3C-3-HISTORICAL-BINDING-PROBE-RESULT-2026-08-14-v0.1","version":"v0.1","node_type":"static_targeted_binding_probe","status":"TARGET_BINDINGS_LOCALIZED","bundle_sha256":v01.sha(raw),"python_sha256":v01.sha(py),"target_identifiers":sorted(TARGETS),"assignments":sorted(rows,key=lambda r:r['lineno']),"reference_index":refs,"safety":{"source_executed":False,"source_imported":False,"full_source_persisted":False},"claim_ceiling":{"historical_binding_localization_only":True,"language_matching_performed":False,"paper_exact_2024_execution_permitted":False,"R3B_effect":"NONE","new_anchor":False,"decipherment":False}}
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({"assignments":len(rows),"targets_with_assignments":sorted({x for r in rows for x in r['targets']})},sort_keys=True))
if __name__=='__main__': main()
