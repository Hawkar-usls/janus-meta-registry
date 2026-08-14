#!/usr/bin/env python3
"""Static dataflow reconstruction for the recovered historical Linear A software.

No recovered code is imported or executed. Selected top-level statements and
four file-loading functions are represented with the previously admitted
semantic IR machinery.
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
import janus_linear_a_r3c3_historical_method_semantic_extract_v0_1_1 as v011

SPEC="data/JANUS-LINEAR-A-R3C-3-HISTORICAL-DATAFLOW-RECONSTRUCTION-SPEC-2026-08-14-v0.1.json"
PARENT="data/JANUS-LINEAR-A-R3C-3-HISTORICAL-METHOD-SEMANTIC-EXTRACTION-RESULT-2026-08-14-v0.1.1.json"
RUNNER="JANUS-LINEAR-A-R3C3-HISTORICAL-DATAFLOW-RECONSTRUCT-v0.1"


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("bundle"); ap.add_argument("--out",required=True); args=ap.parse_args()
    spec=json.load(open(SPEC,encoding="utf-8")); parent=json.load(open(PARENT,encoding="utf-8"))
    assert spec["status"]=="FROZEN_BEFORE_EXECUTION"
    assert parent["status"]==spec["parents"]["required_status"]
    raw=Path(args.bundle).read_bytes(); assert v01.sha(raw)==spec["parents"]["bundle_sha256"]
    with zipfile.ZipFile(io.BytesIO(raw),"r") as zf: py=zf.read(v01.PY_MEMBER)
    assert v01.sha(py)==spec["parents"]["python_member_sha256"]
    tree=ast.parse(py.decode("utf-8-sig"),filename=v01.PY_MEMBER,mode="exec")
    limit=spec["representation"]["small_constant_limit"]
    lo=spec["module_scope"]["top_level_start_line"]; hi=spec["module_scope"]["top_level_end_line"]
    top=[]
    for s in tree.body:
        ln=getattr(s,"lineno",0)
        if lo <= ln <= hi and not isinstance(s,(ast.Import,ast.ImportFrom,ast.ClassDef,ast.FunctionDef,ast.AsyncFunctionDef)):
            top.append(v011.stmt_ir(s,limit))
    funcs=[]; unsupported=[]
    for t in spec["target_functions"]:
        fn=v01.find_function(tree,t["name"],t["lineno"])
        ops=[v011.stmt_ir(s,limit) for s in fn.body if not (isinstance(s,ast.Expr) and isinstance(s.value,ast.Constant) and isinstance(s.value.value,str))]
        bad=sorted({x["ast_type"] for x in v01.walk_stmt_ir(ops) if x.get("type") in {"OTHER_STMT","OTHER_EXPR"} and "ast_type" in x})
        if bad: unsupported.append({"name":fn.name,"lineno":fn.lineno,"types":bad})
        funcs.append({"function_id":f"{fn.name}@{fn.lineno}","name":fn.name,"lineno":fn.lineno,"end_lineno":getattr(fn,"end_lineno",None),"args":[a.arg for a in fn.args.args],"normalized_ast_sha256":v01.normalized_ast_hash(fn),"operations":ops,"unsupported_ast_types":bad})
    top_bad=sorted({x["ast_type"] for x in v01.walk_stmt_ir(top) if x.get("type") in {"OTHER_STMT","OTHER_EXPR"} and "ast_type" in x})
    if top_bad: unsupported.append({"name":"<module:1-110>","lineno":1,"types":top_bad})
    status="HISTORICAL_DATAFLOW_MACHINE_RECONSTRUCTED" if not unsupported else "HISTORICAL_DATAFLOW_PARTIAL_UNSUPPORTED_AST"
    result={
      "artifact_uuid":"JANUS-LINEAR-A-R3C-3-HISTORICAL-DATAFLOW-RECONSTRUCTION-RESULT-2026-08-14-v0.1",
      "version":"v0.1","node_type":"historical_software_static_dataflow_result","status":status,"runner_id":RUNNER,"frozen_spec":SPEC,
      "bundle_sha256":v01.sha(raw),"python_member_sha256":v01.sha(py),"module_top_level_semantic_ir":top,"functions":funcs,"unsupported_summary":unsupported,
      "safety":{"third_party_source_executed":False,"third_party_source_imported":False,"full_source_persisted":False,"language_matching_performed":False},
      "readiness_effect":{"historical_dataflow_machine_reconstructed":not unsupported,"historical_conformance_replay_may_be_frozen":not unsupported,"paper_exact_2024_execution_permitted":False},
      "claim_ceiling":{"historical_dataflow_reconstructed":True,"historical_outputs_reproduced":False,"paper_exact_2024_outputs_reproduced":False,"R3B_effect":"NONE","new_anchor":False,"decipherment":False}
    }
    Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":status,"top_level_statements":len(top),"functions":len(funcs),"unsupported":unsupported},ensure_ascii=False,sort_keys=True))

if __name__=="__main__": main()
