#!/usr/bin/env python3
"""Corrective semantic extractor v0.1.1.

Adds only two AST statement forms proven missing by v0.1: Delete and nested
FunctionDef. Third-party code is parsed only; it is never imported or executed.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import janus_linear_a_r3c3_historical_method_semantic_extract_v0_1 as v01

CORR_SPEC = "data/JANUS-LINEAR-A-R3C-3-HISTORICAL-METHOD-SEMANTIC-EXTRACTION-CORRECTIVE-SPEC-2026-08-14-v0.1.1.json"
PARENT = "data/JANUS-LINEAR-A-R3C-3-HISTORICAL-METHOD-SEMANTIC-EXTRACTION-RESULT-2026-08-14-v0.1.json"
RUNNER = "JANUS-LINEAR-A-R3C3-HISTORICAL-METHOD-SEMANTIC-EXTRACT-v0.1.1"


def stmt_ir(node: ast.stmt, limit: int, depth: int=0) -> dict[str, Any]:
    if depth > 12:
        return {"type":"DEPTH_LIMIT_STMT","ast_type":type(node).__name__}
    base={"lineno":getattr(node,"lineno",None),"end_lineno":getattr(node,"end_lineno",None)}
    d=depth+1
    if isinstance(node, ast.Delete):
        return {**base,"type":"DELETE","targets":[v01.target_ir(t,limit) for t in node.targets]}
    if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
        body=[stmt_ir(s,limit,d) for s in node.body if not (isinstance(s,ast.Expr) and isinstance(s.value,ast.Constant) and isinstance(s.value.value,str))]
        return {**base,"type":"NESTED_FUNCTION","name":node.name,"args":[a.arg for a in node.args.args],"normalized_ast_sha256":v01.normalized_ast_hash(node),"body":body}
    if isinstance(node, ast.Assign): return {**base,"type":"ASSIGN","targets":[v01.target_ir(t,limit) for t in node.targets],"value":v01.expr_ir(node.value,limit)}
    if isinstance(node, ast.AnnAssign): return {**base,"type":"ASSIGN","targets":[v01.target_ir(node.target,limit)],"value":v01.expr_ir(node.value,limit),"annotation":v01.expr_ir(node.annotation,limit)}
    if isinstance(node, ast.AugAssign): return {**base,"type":"AUG_ASSIGN","target":v01.target_ir(node.target,limit),"op":type(node.op).__name__,"value":v01.expr_ir(node.value,limit)}
    if isinstance(node, ast.For): return {**base,"type":"FOR","target":v01.target_ir(node.target,limit),"iter":v01.expr_ir(node.iter,limit),"body":[stmt_ir(x,limit,d) for x in node.body],"orelse":[stmt_ir(x,limit,d) for x in node.orelse]}
    if isinstance(node, ast.While): return {**base,"type":"WHILE","test":v01.expr_ir(node.test,limit),"body":[stmt_ir(x,limit,d) for x in node.body],"orelse":[stmt_ir(x,limit,d) for x in node.orelse]}
    if isinstance(node, ast.If): return {**base,"type":"IF","test":v01.expr_ir(node.test,limit),"body":[stmt_ir(x,limit,d) for x in node.body],"orelse":[stmt_ir(x,limit,d) for x in node.orelse]}
    if isinstance(node, ast.Return): return {**base,"type":"RETURN","value":v01.expr_ir(node.value,limit)}
    if isinstance(node, ast.Expr): return {**base,"type":"EXPR","value":v01.expr_ir(node.value,limit)}
    if isinstance(node, ast.With): return {**base,"type":"WITH","items":[{"context":v01.expr_ir(i.context_expr,limit),"as":v01.target_ir(i.optional_vars,limit) if i.optional_vars else None} for i in node.items],"body":[stmt_ir(x,limit,d) for x in node.body]}
    if isinstance(node, ast.Try): return {**base,"type":"TRY","body":[stmt_ir(x,limit,d) for x in node.body],"handlers":[{"exception":v01.expr_ir(h.type,limit),"name":h.name,"body":[stmt_ir(x,limit,d) for x in h.body]} for h in node.handlers],"orelse":[stmt_ir(x,limit,d) for x in node.orelse],"finalbody":[stmt_ir(x,limit,d) for x in node.finalbody]}
    if isinstance(node, ast.Break): return {**base,"type":"BREAK"}
    if isinstance(node, ast.Continue): return {**base,"type":"CONTINUE"}
    if isinstance(node, ast.Pass): return {**base,"type":"PASS"}
    return {**base,"type":"OTHER_STMT","ast_type":type(node).__name__}


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("bundle"); ap.add_argument("--out",required=True); args=ap.parse_args()
    corr=json.load(open(CORR_SPEC,encoding="utf-8")); parent=json.load(open(PARENT,encoding="utf-8")); base_spec=json.load(open(v01.SPEC,encoding="utf-8"))
    assert corr["status"]=="FROZEN_AFTER_V0_1_PARTIAL_BEFORE_CORRECTIVE_EXECUTION"
    assert parent["status"]==corr["parent"]["required_status"]
    assert parent["unsupported_summary"]==corr["parent"]["exact_unsupported_summary"]
    raw=Path(args.bundle).read_bytes(); assert v01.sha(raw)==base_spec["parents"]["bundle_sha256"]
    with zipfile.ZipFile(io.BytesIO(raw),"r") as zf: py=zf.read(v01.PY_MEMBER)
    assert v01.sha(py)==base_spec["parents"]["python_member_sha256"]
    tree=ast.parse(py.decode("utf-8-sig"),filename=v01.PY_MEMBER,mode="exec")
    limit=base_spec["semantic_ir"]["persist_small_constants_max_chars"]
    functions=[]; unsupported=[]
    for t in base_spec["target_functions"]:
        fn=v01.find_function(tree,t["name"],t["lineno"])
        ops=[stmt_ir(s,limit) for s in fn.body if not (isinstance(s,ast.Expr) and isinstance(s.value,ast.Constant) and isinstance(s.value.value,str))]
        bad=sorted({x["ast_type"] for x in v01.walk_stmt_ir(ops) if x.get("type") in {"OTHER_STMT","OTHER_EXPR"} and "ast_type" in x})
        if bad: unsupported.append({"name":fn.name,"lineno":fn.lineno,"types":bad})
        functions.append({"function_id":f"{fn.name}@{fn.lineno}","name":fn.name,"lineno":fn.lineno,"end_lineno":getattr(fn,"end_lineno",None),"args":[a.arg for a in fn.args.args],"normalized_ast_sha256":v01.normalized_ast_hash(fn),"operations":ops,"unsupported_ast_types":bad})
    status="SEMANTIC_IR_EXTRACTED_COMPLETE_FOR_TARGETS" if not unsupported else "SEMANTIC_IR_EXTRACTED_WITH_UNSUPPORTED_AST_TYPES"
    result={
      "artifact_uuid":"JANUS-LINEAR-A-R3C-3-HISTORICAL-METHOD-SEMANTIC-EXTRACTION-RESULT-2026-08-14-v0.1.1",
      "version":"v0.1.1","node_type":"cleanroom_semantic_ir_corrective_result","status":status,"runner_id":RUNNER,
      "base_spec":v01.SPEC,"corrective_spec":CORR_SPEC,"parent_partial_result":PARENT,"bundle_sha256":v01.sha(raw),
      "python_member":{"path":v01.PY_MEMBER,"sha256":v01.sha(py),"bytes":len(py)},"functions":functions,"unsupported_summary":unsupported,
      "correction":{"only_added_ast_statement_types":["Delete","FunctionDef_as_NESTED_FUNCTION"],"target_functions_changed":False,"expression_ir_changed":False,"method_semantics_changed":False,"pass_inherited_from_v0_1":False},
      "safety":{"third_party_source_executed":False,"third_party_source_imported":False,"eval_used":False,"exec_used":False,"full_source_persisted":False,"ast_parse_only":True},
      "readiness_effect":{"historical_function_semantics_machine_represented":not unsupported,"cleanroom_reimplementation_may_be_frozen_after_review":not unsupported,"historical_output_replay_performed":False,"paper_exact_2024_execution_permitted":False},
      "claim_ceiling":{"historical_control_flow_reconstructed":True,"historical_outputs_reproduced":False,"paper_exact_2024_outputs_reproduced":False,"R3B_effect":"NONE","new_anchor":False,"decipherment":False}
    }
    Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":status,"unsupported":unsupported},ensure_ascii=False,sort_keys=True))

if __name__=="__main__": main()
