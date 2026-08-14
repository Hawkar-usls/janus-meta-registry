#!/usr/bin/env python3
"""Static, non-executing inspection of the recovered historical R3C-3 bundle.

The ZIP is never extracted. Python source is parsed with ast.parse only and is
never imported/eval'ed/exec'ed. CSV lexical values are used only to compute
structural counts and cryptographic fingerprints; raw rows are not persisted.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

RUNNER_ID = "JANUS-LINEAR-A-R3C3-HISTORICAL-BUNDLE-STATIC-INSPECTION-v0.1"
SPEC_PATH = "data/JANUS-LINEAR-A-R3C-3-HISTORICAL-BUNDLE-STATIC-METHOD-INSPECTION-SPEC-2026-08-14-v0.1.json"
ACQ_PATH = "data/JANUS-LINEAR-A-R3C-3-HISTORICAL-MAC-BUNDLE-ACQUISITION-RESULT-2026-08-14-v0.1.json"
SELECTED_CALLS = {"read_csv","read_excel","to_csv","to_excel","replace","translate","lower","upper","strip","split","dropna","astype"}
KEYWORDS = ("match", "conson", "vowel", "word", "format", "source", "linear", "cluster")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_bytes(data: bytes, encodings: list[str]) -> tuple[str, str]:
    for enc in encodings:
        try:
            return data.decode(enc), enc
        except UnicodeDecodeError:
            pass
    raise ValueError("NO_DECLARED_DECODING_SUCCEEDED")


def call_name(node: ast.Call) -> str:
    f=node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def bounded_unparse(node: ast.AST, limit: int) -> str | None:
    try:
        s=ast.unparse(node)
    except Exception:
        return None
    s=" ".join(s.split())
    return s if len(s) <= limit else None


def inspect_python(source: str, limit: int) -> dict[str, Any]:
    tree=ast.parse(source, filename="Working_UI_ab_update.py", mode="exec")
    functions=[]
    imports=[]
    calls=[]
    equality=[]
    resource_literals=set()
    column_literals=set()
    vowel_sets=[]
    for node in ast.walk(tree):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            functions.append({"name":node.name,"lineno":node.lineno,"end_lineno":getattr(node,"end_lineno",None)})
        elif isinstance(node,ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node,ast.ImportFrom):
            imports.append((node.module or "") + ":" + ",".join(a.name for a in node.names))
        elif isinstance(node,ast.Call):
            n=call_name(node)
            if n in SELECTED_CALLS:
                expr=bounded_unparse(node,limit)
                calls.append({"call":n,"lineno":getattr(node,"lineno",None),"expression":expr})
        elif isinstance(node,ast.Compare) and any(isinstance(op,ast.Eq) for op in node.ops):
            expr=bounded_unparse(node,limit)
            if expr and any(k in expr.lower() for k in KEYWORDS):
                equality.append({"lineno":getattr(node,"lineno",None),"expression":expr})
        elif isinstance(node,ast.Constant) and isinstance(node.value,str):
            s=node.value
            low=s.lower()
            if low.endswith((".csv",".xlsx",".xls",".otf",".txt")) and len(s)<=160:
                resource_literals.add(s)
            if s in {"Source","source","NEW FORMAT","New Format","new format","Linear A","Linear A word","List","Identical Matches","Original_Word"}:
                column_literals.add(s)
        elif isinstance(node,(ast.Set,ast.List,ast.Tuple)):
            vals=[]
            ok=True
            for e in node.elts:
                if isinstance(e,ast.Constant) and isinstance(e.value,str) and len(e.value)==1:
                    vals.append(e.value)
                else:
                    ok=False; break
            if ok and vals and set(vals).issubset(set("aeiouAEIOU")) and set(v.lower() for v in vals).issubset(set("aeiou")):
                vowel_sets.append({"lineno":getattr(node,"lineno",None),"values":sorted(vals)})
    # Deduplicate compact evidence while preserving line-specific evidence.
    call_seen=set(); call_out=[]
    for r in sorted(calls,key=lambda x:(x["lineno"] or 0,x["call"],x["expression"] or "")):
        key=(r["call"],r["lineno"],r["expression"])
        if key not in call_seen:
            call_seen.add(key); call_out.append(r)
    eq_seen=set(); eq_out=[]
    for r in sorted(equality,key=lambda x:(x["lineno"] or 0,x["expression"])):
        key=(r["lineno"],r["expression"])
        if key not in eq_seen:
            eq_seen.add(key); eq_out.append(r)
    return {
        "ast_parse_success":True,
        "function_count":len(functions),
        "functions":sorted(functions,key=lambda x:(x["lineno"],x["name"])),
        "imports":sorted(set(imports)),
        "selected_method_call_count":len(call_out),
        "selected_method_calls":call_out,
        "selected_equality_expression_count":len(eq_out),
        "selected_equality_expressions":eq_out,
        "vowel_set_literals":vowel_sets,
        "resource_literals":sorted(resource_literals),
        "column_literals":sorted(column_literals),
        "full_source_persisted":False,
        "source_executed":False,
        "source_imported":False,
    }


def value_stream_hash(values: list[str]) -> str:
    h=hashlib.sha256()
    for v in values:
        b=v.encode("utf-8")
        h.update(len(b).to_bytes(8,"big")); h.update(b)
    return h.hexdigest()


def inspect_csv(data: bytes, encodings: list[str]) -> dict[str, Any]:
    text,enc=decode_bytes(data,encodings)
    rows=list(csv.reader(io.StringIO(text,newline="")))
    if not rows:
        return {"encoding":enc,"headers":[],"row_count":0,"columns":[]}
    headers=rows[0]
    body=rows[1:]
    width=max([len(headers)]+[len(r) for r in body])
    padded_headers=headers+[f"__UNNAMED_{i}" for i in range(len(headers),width)]
    cols=[]
    for i,hdr in enumerate(padded_headers):
        vals=[r[i] if i<len(r) else "" for r in body]
        nonempty=[v for v in vals if v!=""]
        hist=Counter(len(v) for v in vals)
        cols.append({
            "column_index":i,
            "header":hdr,
            "nonempty_count":len(nonempty),
            "unique_nonempty_count":len(set(nonempty)),
            "value_length_histogram":{str(k):hist[k] for k in sorted(hist)},
            "value_stream_sha256":value_stream_hash(vals),
        })
    return {
        "encoding":enc,
        "headers":padded_headers,
        "row_count":len(body),
        "max_column_count":width,
        "columns":cols,
        "raw_lexical_values_persisted":False,
    }


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("--out",required=True)
    args=ap.parse_args()
    spec=json.load(open(SPEC_PATH,encoding="utf-8"))
    acq=json.load(open(ACQ_PATH,encoding="utf-8"))
    assert spec["status"]=="FROZEN_BEFORE_EXECUTION"
    assert acq["status"]==spec["parent_acquisition"]["required_status"]
    bundle=Path(args.bundle)
    raw=bundle.read_bytes()
    assert sha256_bytes(raw)==spec["parent_acquisition"]["bundle_sha256"]
    assert len(raw)==1765475
    encodings=spec["csv_structure_analysis"]["decode_candidates"]
    with zipfile.ZipFile(io.BytesIO(raw),"r") as zf:
        names=zf.namelist()
        py_path=spec["target_members"]["python_source"]["path"]
        base_path=spec["target_members"]["base_sheet"]["path"]
        py_bytes=zf.read(py_path)
        base_bytes=zf.read(base_path)
        assert sha256_bytes(py_bytes)==spec["target_members"]["python_source"]["sha256"]
        assert len(py_bytes)==spec["target_members"]["python_source"]["bytes"]
        assert sha256_bytes(base_bytes)==spec["target_members"]["base_sheet"]["sha256"]
        assert len(base_bytes)==spec["target_members"]["base_sheet"]["bytes"]
        py_text,py_encoding=decode_bytes(py_bytes,["utf-8-sig","utf-8","latin-1"])
        py_report=inspect_python(py_text,spec["static_python_analysis"]["max_persisted_expression_characters"])
        py_report.update({"path":py_path,"bytes":len(py_bytes),"sha256":sha256_bytes(py_bytes),"encoding":py_encoding})
        base_report=inspect_csv(base_bytes,encodings)
        base_report.update({"path":base_path,"bytes":len(base_bytes),"sha256":sha256_bytes(base_bytes)})
        dict_names=[]
        for n in names:
            low=n.lower()
            if low.startswith("linearadecipherment/misc/") and low.endswith("numberedwords.csv") and not Path(n).name.startswith("._"):
                dict_names.append(n)
        dict_reports=[]
        for n in sorted(dict_names):
            b=zf.read(n)
            rep=inspect_csv(b,encodings)
            rep.update({"path":n,"bytes":len(b),"sha256":sha256_bytes(b)})
            dict_reports.append(rep)
        all_low="\n".join(names).lower()
        language_presence={
            "Ancient Egyptian": any("ancientegyptian" in n.lower() or "egyptian" in n.lower() for n in names),
            "Luwian": any("luwian" in n.lower() for n in names),
            "Hittite": any("hittite" in n.lower() for n in names),
            "Proto-Celtic": any("proto_celtic" in n.lower() or "proto-celtic" in n.lower() for n in names),
            "Uralic": "ural" in all_low,
        }
    present_count=sum(language_presence.values())
    result={
      "artifact_uuid":"JANUS-LINEAR-A-R3C-3-HISTORICAL-BUNDLE-STATIC-METHOD-INSPECTION-RESULT-2026-08-14-v0.1",
      "version":"v0.1",
      "node_type":"static_nonexecuting_method_and_input_structure_inspection_result",
      "status":"STATIC_METHOD_AND_INPUT_STRUCTURE_RECOVERED_PARTIAL_2024_LANGUAGE_RESOURCE_SET" if present_count<5 else "STATIC_METHOD_AND_INPUT_STRUCTURE_RECOVERED_ALL_5_LANGUAGE_NAMES_PRESENT",
      "runner_id":RUNNER_ID,
      "frozen_spec":SPEC_PATH,
      "bundle":{"sha256":sha256_bytes(raw),"bytes":len(raw),"git_blob_sha1":spec["parent_acquisition"]["bundle_git_blob_sha1"]},
      "python_source":py_report,
      "base_sheet":base_report,
      "dictionary_resource_count":len(dict_reports),
      "dictionary_resources":dict_reports,
      "paper_2024_language_resource_name_presence":language_presence,
      "paper_2024_language_resource_name_presence_count":present_count,
      "safety":{
        "archive_extracted_to_filesystem":False,
        "python_executed":False,
        "python_imported":False,
        "eval_used":False,
        "exec_used":False,
        "raw_dictionary_rows_persisted":False,
        "raw_BaseSheet_rows_persisted":False,
        "scientific_language_match_scoring_performed":False,
        "manual_semantic_filtering_performed":False
      },
      "readiness_effect":{
        "public_plaintext_python_source_recovered":True,
        "historical_BaseSheet_byte_identity_recovered":True,
        "historical_dictionary_byte_identities_recovered":len(dict_reports)>0,
        "historical_normalization_contract_static_evidence_recovered":True,
        "paper_exact_2024_input_identity_admitted":False,
        "upstream_normalization_contract_complete_for_2024":False,
        "scientific_R3C3_execution_permitted":False
      },
      "claim_ceiling":{
        "historical_software_method_structure_reconstructed":True,
        "historical_input_structure_reconstructed":True,
        "paper_exact_2024_inputs_established":False,
        "published_matches_reproduced":False,
        "language_family_relationship_established":False,
        "R3B_effect":"NONE","new_anchor":False,"decipherment":False
      }
    }
    Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"functions":py_report["function_count"],"calls":py_report["selected_method_call_count"],"base_rows":base_report["row_count"],"dicts":len(dict_reports),"language_presence":language_presence},ensure_ascii=False,sort_keys=True))

if __name__=="__main__":
    main()
