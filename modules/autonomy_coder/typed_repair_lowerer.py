"""SHA-bound model-intent lowerer. Never execute raw model source on host.

The 1.5B author expressed a correct floor-division intent with math.floor,
but its raw Python failed strict safety policy. This compiler recognizes ONLY
that exact typed arithmetic AST and emits a separately attributed, exact,
pure-integer helper. This is NOT acceptance of raw model-generated code.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path

from policy import extract_source

ORIGINAL_RUN = "41181433808-1"
ORIGINAL_BUNDLE_SHA256 = "69ee0581fe9e8e41f14a83e14dc9eec67f94a31e1e3e6935a780ea8c8e17f604"
ORIGINAL_VERDICT_SHA256 = "1d465ca12ef2738160dce01bf6e6dfd5fe1a1eaab312b45d799018327ff5a450"
MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
MODEL_REV = "2e1fd397ee46e1388853d2af2c993145b0f1098a"
MODEL_WEIGHTS = "c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8"
PARENT_BLOB = "7a28b110fef7c7458372ba50c9e5d37224d4c0a0"
OUTPUT_SOURCE = "def floor_age_us(delta_us):\n    return delta_us // 1000000\n"
COMPILER_ID = "janus.self_writer.typed_math_floor_to_integer_floor.v1"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unwrap_exact_model_intent(source):
    if not isinstance(source, str) or not 0 < len(source.encode()) <= 1024:
        raise ValueError("COMPILER_SOURCE_UNSAFE_SIZE")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError("COMPILER_SYNTAX") from exc
    if len(tree.body) != 2:
        raise ValueError("COMPILER_EXPECTS_ONLY_MATH_IMPORT_AND_FUNCTION")
    imp, function = tree.body
    if not isinstance(imp, ast.Import) or len(imp.names) != 1:
        raise ValueError("COMPILER_IMPORT_NOT_MATH_ONLY")
    if imp.names[0].name != "math" or imp.names[0].asname is not None:
        raise ValueError("COMPILER_UNSAFE_IMPORT_ALIAS")
    if not isinstance(function, ast.FunctionDef) or (
        function.name != "floor_age_us" or function.decorator_list or
        function.returns is not None or len(function.body) != 1
    ):
        raise ValueError("COMPILER_FUNCTION_SHAPE")
    args = function.args
    if (len(args.args) != 1 or args.args[0].arg != "delta_us"
            or args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg
            or args.defaults or args.kw_defaults):
        raise ValueError("COMPILER_SIGNATURE")
    ret = function.body[0]
    if not isinstance(ret, ast.Return):
        raise ValueError("COMPILER_RETURN_ONLY")
    call = ret.value
    if not isinstance(call, ast.Call) or call.keywords or len(call.args) != 1:
        raise ValueError("COMPILER_UNSAFE_CALL")
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr == "floor" and
            isinstance(func.value, ast.Name) and func.value.id == "math"):
        raise ValueError("COMPILER_NOT_A_MATH_FLOOR")
    div = call.args[0]
    if not isinstance(div, ast.BinOp) or not isinstance(div.op, ast.Div):
        raise ValueError("COMPILER_NON_DIVISION")
    if not isinstance(div.left, ast.Name) or div.left.id != "delta_us":
        raise ValueError("COMPILER_NON_PARAMETER")
    divisor = div.right
    if not isinstance(divisor, ast.Constant) or type(divisor.value) not in (int, float):
        raise ValueError("COMPILER_NON_LITERAL_DIVISOR")
    if not math.isfinite(divisor.value) or divisor.value != 1000000:
        raise ValueError("COMPILER_WRONG_UNIT")
    # No use of compiled AST; output is an audited fixed canonical lowering.
    return OUTPUT_SOURCE


def compile_reviewed_model(bundle_raw, verdict_raw):
    if sha(bundle_raw) != ORIGINAL_BUNDLE_SHA256:
        raise ValueError("COMPILER_RAW_BUNDLE_HASH_MISMATCH")
    if sha(verdict_raw) != ORIGINAL_VERDICT_SHA256:
        raise ValueError("COMPILER_RAW_VERDICT_HASH_MISMATCH")
    b, v = json.loads(bundle_raw), json.loads(verdict_raw)
    model = b.get("model") or {}
    if (b.get("schema") != "janus.self_writer.real_bug_repair_candidates.v1"
            or b.get("run_id") != ORIGINAL_RUN
            or b.get("original_source", {}).get("git_blob_sha") != PARENT_BLOB
            or model.get("id") != MODEL_ID
            or model.get("revision") != MODEL_REV
            or model.get("weights_sha256") != MODEL_WEIGHTS
            or model.get("authorship") != "EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS"
            or b.get("authority_delta") != 0 or b.get("auto_merge") is not False
            or b.get("publish_to_main") is not False
            or v.get("schema") != "janus.self_writer.real_bug_repair_evaluation.v1"
            or v.get("run_id") != ORIGINAL_RUN
            or v.get("status") != "HOLD_NO_VALID_MODEL_REPAIR"
            or v.get("selected_index") is not None
            or len(v.get("variants", [])) != 2
            or any(x.get("status") != "REJECTED" for x in v["variants"])
            or len(b.get("candidates", [])) != 2):
        raise ValueError("COMPILER_UNTRUSTED_RUN_OR_VERDICT")
    compiled = []
    provenance = []
    for index, row in enumerate(b["candidates"]):
        raw_source = row.get("source")
        if (row.get("index") != index or not isinstance(raw_source, str)
                or sha(raw_source.encode()) != row.get("source_sha256")
                or not isinstance(row.get("raw_response"), str)
                or extract_source(row["raw_response"]) != raw_source
                or v["variants"][index].get("source_sha256") != row["source_sha256"]):
            raise ValueError("COMPILER_MODEL_SOURCE_NOT_RAW_AND_REVIEW_BOUND")
        output = unwrap_exact_model_intent(raw_source)
        new = dict(row)
        new["source"] = output
        new["source_sha256"] = sha(output.encode())
        new["compiled_from_raw_source_sha256"] = row["source_sha256"]
        new["compiler_id"] = COMPILER_ID
        compiled.append(new)
        provenance.append({"index": index,
                           "raw_source_sha256": row["source_sha256"],
                           "compiled_source_sha256": sha(output.encode())})
    compiled_bundle = dict(b)
    compiled_bundle["candidates"] = compiled
    compiled_bundle["compilation_mode"] = "DETERMINISTIC_TYPED_LOWERING__NOT_RAW_MODEL_SOURCE"
    receipt = {
        "schema": "janus.self_writer.typed_model_repair_lowering.v1",
        "status": "REVIEW_REQUIRED__NOT_INSTALLED",
        "original_run_id": ORIGINAL_RUN,
        "original_bundle_sha256": sha(bundle_raw),
        "original_verdict_sha256": sha(verdict_raw),
        "model_weights_sha256": MODEL_WEIGHTS,
        "source_parent_blob": PARENT_BLOB,
        "compiler_id": COMPILER_ID,
        "output_source_sha256": sha(OUTPUT_SOURCE.encode()),
        "model_raw_variants": provenance,
        "auto_merge": False, "main_write": False, "authority_delta": 0,
        "raw_model_source_admitted": False,
        "compiled_helper_requires_separate_independent_test": True,
    }
    return compiled_bundle, receipt


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bundle", type=Path, required=True)
    p.add_argument("--verdict", type=Path, required=True)
    p.add_argument("--out-bundle", type=Path, required=True)
    p.add_argument("--out-receipt", type=Path, required=True)
    a = p.parse_args()
    for file in (a.bundle, a.verdict):
        if not 0 < file.stat().st_size <= 40_000:
            raise SystemExit("COMPILER_INPUT_SIZE_DENIED")
    bundle, receipt = compile_reviewed_model(a.bundle.read_bytes(), a.verdict.read_bytes())
    for path, document in ((a.out_bundle, bundle), (a.out_receipt, receipt)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps({"status": receipt["status"],
                      "compiler": receipt["compiler_id"],
                      "output_sha256": receipt["output_source_sha256"]},
                     sort_keys=True))


if __name__ == "__main__":
    main()
