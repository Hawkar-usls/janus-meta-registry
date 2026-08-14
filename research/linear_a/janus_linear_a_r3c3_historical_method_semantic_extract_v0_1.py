#!/usr/bin/env python3
"""Extract a bounded semantic IR from selected functions in a historical bundle.

This module never imports or executes the recovered third-party source. It reads
one ZIP member in memory, parses it with ast.parse, and emits a normalized,
bounded control/data-flow description suitable for a later clean-room replay.
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

SPEC = "data/JANUS-LINEAR-A-R3C-3-HISTORICAL-METHOD-SEMANTIC-EXTRACTION-SPEC-2026-08-14-v0.1.json"
STATIC = "data/JANUS-LINEAR-A-R3C-3-HISTORICAL-BUNDLE-STATIC-METHOD-INSPECTION-RESULT-2026-08-14-v0.1.json"
PY_MEMBER = "LinearADecipherment/Working_UI_ab_update.py"
RUNNER = "JANUS-LINEAR-A-R3C3-HISTORICAL-METHOD-SEMANTIC-EXTRACT-v0.1"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left=dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return None


def const_ir(v: Any, limit: int) -> dict[str, Any]:
    if isinstance(v, str):
        b=v.encode("utf-8")
        if len(v) <= limit:
            return {"type":"CONSTANT","value_type":"str","value":v}
        return {"type":"CONSTANT","value_type":"str","value_redacted":True,"characters":len(v),"sha256":sha(b)}
    if v is None or isinstance(v,(bool,int,float)):
        return {"type":"CONSTANT","value_type":type(v).__name__,"value":v}
    return {"type":"CONSTANT","value_type":type(v).__name__}


def expr_ir(node: ast.AST | None, limit: int, depth: int=0) -> dict[str, Any] | None:
    if node is None:
        return None
    if depth > 10:
        return {"type":"DEPTH_LIMIT","ast_type":type(node).__name__}
    d=depth+1
    if isinstance(node, ast.Constant): return const_ir(node.value,limit)
    if isinstance(node, ast.Name): return {"type":"NAME","id":node.id}
    if isinstance(node, ast.Attribute): return {"type":"ATTRIBUTE","path":dotted(node),"value":expr_ir(node.value,limit,d)}
    if isinstance(node, ast.Call):
        return {"type":"CALL","function":dotted(node.func) or type(node.func).__name__,"args":[expr_ir(x,limit,d) for x in node.args],"keywords":[{"arg":k.arg,"value":expr_ir(k.value,limit,d)} for k in node.keywords]}
    if isinstance(node, ast.Subscript): return {"type":"SUBSCRIPT","value":expr_ir(node.value,limit,d),"slice":expr_ir(node.slice,limit,d)}
    if isinstance(node, ast.Slice): return {"type":"SLICE","lower":expr_ir(node.lower,limit,d),"upper":expr_ir(node.upper,limit,d),"step":expr_ir(node.step,limit,d)}
    if isinstance(node, ast.Compare): return {"type":"COMPARE","left":expr_ir(node.left,limit,d),"ops":[type(o).__name__ for o in node.ops],"comparators":[expr_ir(x,limit,d) for x in node.comparators]}
    if isinstance(node, ast.BinOp): return {"type":"BINOP","op":type(node.op).__name__,"left":expr_ir(node.left,limit,d),"right":expr_ir(node.right,limit,d)}
    if isinstance(node, ast.UnaryOp): return {"type":"UNARYOP","op":type(node.op).__name__,"operand":expr_ir(node.operand,limit,d)}
    if isinstance(node, ast.BoolOp): return {"type":"BOOLOP","op":type(node.op).__name__,"values":[expr_ir(x,limit,d) for x in node.values]}
    if isinstance(node, ast.IfExp): return {"type":"IFEXP","test":expr_ir(node.test,limit,d),"body":expr_ir(node.body,limit,d),"orelse":expr_ir(node.orelse,limit,d)}
    if isinstance(node, ast.List): return {"type":"LIST","elts":[expr_ir(x,limit,d) for x in node.elts]}
    if isinstance(node, ast.Tuple): return {"type":"TUPLE","elts":[expr_ir(x,limit,d) for x in node.elts]}
    if isinstance(node, ast.Set): return {"type":"SET","elts":[expr_ir(x,limit,d) for x in node.elts]}
    if isinstance(node, ast.Dict): return {"type":"DICT","items":[{"key":expr_ir(k,limit,d),"value":expr_ir(v,limit,d)} for k,v in zip(node.keys,node.values)]}
    if isinstance(node, ast.ListComp):
        return {"type":"LISTCOMP","elt":expr_ir(node.elt,limit,d),"generators":[{"target":expr_ir(g.target,limit,d),"iter":expr_ir(g.iter,limit,d),"ifs":[expr_ir(x,limit,d) for x in g.ifs]} for g in node.generators]}
    if isinstance(node, ast.JoinedStr): return {"type":"JOINEDSTR","parts":[expr_ir(x,limit,d) for x in node.values]}
    if isinstance(node, ast.FormattedValue): return {"type":"FORMATTED_VALUE","value":expr_ir(node.value,limit,d)}
    return {"type":"OTHER_EXPR","ast_type":type(node).__name__}


def target_ir(node: ast.AST, limit: int) -> Any:
    return expr_ir(node,limit)


def stmt_ir(node: ast.stmt, limit: int, depth: int=0) -> dict[str, Any]:
    if depth > 12:
        return {"type":"DEPTH_LIMIT_STMT","ast_type":type(node).__name__}
    base={"lineno":getattr(node,"lineno",None),"end_lineno":getattr(node,"end_lineno",None)}
    d=depth+1
    if isinstance(node, ast.Assign): return {**base,"type":"ASSIGN","targets":[target_ir(t,limit) for t in node.targets],"value":expr_ir(node.value,limit)}
    if isinstance(node, ast.AnnAssign): return {**base,"type":"ASSIGN","targets":[target_ir(node.target,limit)],"value":expr_ir(node.value,limit),"annotation":expr_ir(node.annotation,limit)}
    if isinstance(node, ast.AugAssign): return {**base,"type":"AUG_ASSIGN","target":target_ir(node.target,limit),"op":type(node.op).__name__,"value":expr_ir(node.value,limit)}
    if isinstance(node, ast.For): return {**base,"type":"FOR","target":target_ir(node.target,limit),"iter":expr_ir(node.iter,limit),"body":[stmt_ir(x,limit,d) for x in node.body],"orelse":[stmt_ir(x,limit,d) for x in node.orelse]}
    if isinstance(node, ast.While): return {**base,"type":"WHILE","test":expr_ir(node.test,limit),"body":[stmt_ir(x,limit,d) for x in node.body],"orelse":[stmt_ir(x,limit,d) for x in node.orelse]}
    if isinstance(node, ast.If): return {**base,"type":"IF","test":expr_ir(node.test,limit),"body":[stmt_ir(x,limit,d) for x in node.body],"orelse":[stmt_ir(x,limit,d) for x in node.orelse]}
    if isinstance(node, ast.Return): return {**base,"type":"RETURN","value":expr_ir(node.value,limit)}
    if isinstance(node, ast.Expr): return {**base,"type":"EXPR","value":expr_ir(node.value,limit)}
    if isinstance(node, ast.With): return {**base,"type":"WITH","items":[{"context":expr_ir(i.context_expr,limit),"as":target_ir(i.optional_vars,limit) if i.optional_vars else None} for i in node.items],"body":[stmt_ir(x,limit,d) for x in node.body]}
    if isinstance(node, ast.Try): return {**base,"type":"TRY","body":[stmt_ir(x,limit,d) for x in node.body],"handlers":[{"exception":expr_ir(h.type,limit),"name":h.name,"body":[stmt_ir(x,limit,d) for x in h.body]} for h in node.handlers],"orelse":[stmt_ir(x,limit,d) for x in node.orelse],"finalbody":[stmt_ir(x,limit,d) for x in node.finalbody]}
    if isinstance(node, ast.Break): return {**base,"type":"BREAK"}
    if isinstance(node, ast.Continue): return {**base,"type":"CONTINUE"}
    if isinstance(node, ast.Pass): return {**base,"type":"PASS"}
    return {**base,"type":"OTHER_STMT","ast_type":type(node).__name__}


def find_function(tree: ast.Module, name: str, lineno: int) -> ast.FunctionDef | ast.AsyncFunctionDef:
    rows=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name==name and n.lineno==lineno]
    if len(rows)!=1:
        raise ValueError(f"FUNCTION_IDENTITY_MISMATCH:{name}:{lineno}:matches={len(rows)}")
    return rows[0]


def normalized_ast_hash(fn: ast.AST) -> str:
    text=ast.dump(fn, annotate_fields=True, include_attributes=False, indent=None)
    return sha(text.encode("utf-8"))


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("bundle"); ap.add_argument("--out",required=True); args=ap.parse_args()
    spec=json.load(open(SPEC,encoding="utf-8")); parent=json.load(open(STATIC,encoding="utf-8"))
    assert spec["status"]=="FROZEN_BEFORE_EXECUTION"
    assert parent["status"]==spec["parents"]["required_status"]
    raw=Path(args.bundle).read_bytes(); assert sha(raw)==spec["parents"]["bundle_sha256"]
    with zipfile.ZipFile(io.BytesIO(raw),"r") as zf: py=zf.read(PY_MEMBER)
    assert sha(py)==spec["parents"]["python_member_sha256"]
    source=py.decode("utf-8-sig"); tree=ast.parse(source,filename=PY_MEMBER,mode="exec")
    limit=spec["semantic_ir"]["persist_small_constants_max_chars"]
    functions=[]; unsupported=[]
    for t in spec["target_functions"]:
        fn=find_function(tree,t["name"],t["lineno"])
        ops=[stmt_ir(s,limit) for s in fn.body if not (isinstance(s,ast.Expr) and isinstance(s.value,ast.Constant) and isinstance(s.value.value,str))]
        unsupported_types=sorted({x["ast_type"] for x in walk_stmt_ir(ops) if x.get("type") in {"OTHER_STMT","OTHER_EXPR"} and "ast_type" in x})
        if unsupported_types: unsupported.append({"name":fn.name,"lineno":fn.lineno,"types":unsupported_types})
        functions.append({
            "function_id":f"{fn.name}@{fn.lineno}","name":fn.name,"lineno":fn.lineno,"end_lineno":getattr(fn,"end_lineno",None),
            "args":[a.arg for a in fn.args.args],"normalized_ast_sha256":normalized_ast_hash(fn),"operations":ops,"unsupported_ast_types":unsupported_types
        })
    status="SEMANTIC_IR_EXTRACTED_COMPLETE_FOR_TARGETS" if not unsupported else "SEMANTIC_IR_EXTRACTED_WITH_UNSUPPORTED_AST_TYPES"
    result={
      "artifact_uuid":"JANUS-LINEAR-A-R3C-3-HISTORICAL-METHOD-SEMANTIC-EXTRACTION-RESULT-2026-08-14-v0.1",
      "version":"v0.1","node_type":"cleanroom_semantic_ir_result","status":status,"runner_id":RUNNER,"frozen_spec":SPEC,
      "bundle_sha256":sha(raw),"python_member":{"path":PY_MEMBER,"sha256":sha(py),"bytes":len(py)},
      "functions":functions,"unsupported_summary":unsupported,
      "safety":{"third_party_source_executed":False,"third_party_source_imported":False,"eval_used":False,"exec_used":False,"full_source_persisted":False,"ast_parse_only":True},
      "readiness_effect":{"historical_function_semantics_machine_represented":not unsupported,"cleanroom_reimplementation_may_be_frozen_after_review":not unsupported,"historical_output_replay_performed":False,"paper_exact_2024_execution_permitted":False},
      "claim_ceiling":{"historical_control_flow_reconstructed":True,"historical_outputs_reproduced":False,"paper_exact_2024_outputs_reproduced":False,"R3B_effect":"NONE","new_anchor":False,"decipherment":False}
    }
    Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":status,"functions":len(functions),"unsupported":unsupported},ensure_ascii=False,sort_keys=True))


def walk_stmt_ir(x: Any):
    if isinstance(x,dict):
        yield x
        for v in x.values(): yield from walk_stmt_ir(v)
    elif isinstance(x,list):
        for v in x: yield from walk_stmt_ir(v)


if __name__=="__main__": main()
