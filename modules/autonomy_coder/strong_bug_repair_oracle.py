"""Networkless read-only evaluator for model-authored repair of real UTC age bug.

Run ONLY inside pinned no-network Docker. Verifies source AST, not just tests.
The generated Python is not imported by the trusted host process.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import random

SCHEMA = "janus.self_writer.real_bug_repair_candidates.v1"
RECEIPT_SCHEMA = "janus.self_writer.real_bug_repair_evaluation.v1"
AUTHOR = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
REVISION = "2e1fd397ee46e1388853d2af2c993145b0f1098a"
WEIGHTS = "c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8"
PARENT_BLOB = "7a28b110fef7c7458372ba50c9e5d37224d4c0a0"
ALLOWED = (
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign,
    ast.Name, ast.Load, ast.Store, ast.Constant, ast.BinOp, ast.UnaryOp,
    ast.FloorDiv, ast.Div, ast.Add, ast.Sub, ast.Mult, ast.Mod,
    ast.USub, ast.UAdd, ast.If, ast.Compare, ast.Lt, ast.LtE, ast.Gt,
    ast.GtE, ast.Eq, ast.NotEq, ast.IfExp, ast.BoolOp, ast.And, ast.Or,
    ast.Call
)


def digest(raw: bytes):
    return hashlib.sha256(raw).hexdigest()


def source_check(source: str):
    if not isinstance(source, str) or not 0 < len(source.encode()) < 2048:
        raise ValueError("REAL_REPAIR_SOURCE_SIZE")
    tree = ast.parse(source)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("REAL_REPAIR_SINGLE_FUNCTION")
    f = tree.body[0]
    if (f.name != "floor_age_us" or f.decorator_list or f.returns is not None
            or [arg.arg for arg in f.args.args] != ["delta_us"]
            or f.args.posonlyargs or f.args.kwonlyargs or f.args.vararg
            or f.args.kwarg or f.args.defaults or f.args.kw_defaults):
        raise ValueError("REAL_REPAIR_SIGNATURE")
    all_nodes = list(ast.walk(tree))
    if len(all_nodes) > 100:
        raise ValueError("REAL_REPAIR_AST_TOO_LARGE")
    for node in all_nodes:
        if not isinstance(node, ALLOWED):
            raise ValueError("REAL_REPAIR_UNSAFE_AST_" + type(node).__name__)
        if isinstance(node, ast.Constant) and type(node.value) not in (int, bool):
            raise ValueError("REAL_REPAIR_FORBIDDEN_CONSTANT")
        if isinstance(node, ast.Name) and (node.id.startswith("_")
                  or node.id in ("exec", "eval", "open", "__import__", "globals")):
            raise ValueError("REAL_REPAIR_UNSAFE_SYMBOL")
        if isinstance(node, ast.Call) and (
                not isinstance(node.func, ast.Name)
                or node.func.id not in ("int", "abs")
                or node.keywords or len(node.args) != 1):
            raise ValueError("REAL_REPAIR_UNSAFE_CALL")
        if isinstance(node, ast.Assign) and (
                len(node.targets) != 1
                or not isinstance(node.targets[0], ast.Name)):
            raise ValueError("REAL_REPAIR_UNSAFE_ASSIGN")
    if not any(isinstance(x, ast.Return) for x in all_nodes):
        raise ValueError("REAL_REPAIR_MISSING_RETURN")
    return tree


def validate_bundle(b):
    model = b.get("model") or {}
    prior = b.get("original_source") or {}
    if (b.get("schema") != SCHEMA
            or b.get("task") != "signed_utc_age_floor"
            or prior.get("path") != "modules/autonomy_coder/real_operational_consumer.py"
            or prior.get("git_blob_sha") != PARENT_BLOB
            or prior.get("real_baseline_input_us") != -500000
            or prior.get("real_baseline_age_seconds") != 0
            or prior.get("expected_correct_age_seconds") != -1
            or model.get("id") != AUTHOR or model.get("revision") != REVISION
            or model.get("weights_sha256") != WEIGHTS
            or model.get("authorship") != "EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS"
            or b.get("authority_delta") != 0 or b.get("auto_merge") is not False
            or b.get("publish_to_main") is not False
            or digest(str(b.get("prompt", "")).encode()) != b.get("prompt_sha256")
            or not isinstance(b.get("candidates"), list)
            or len(b["candidates"]) != 2):
        raise ValueError("REAL_REPAIR_BUNDLE_NOT_ADMITTED")
    return b


def evaluate(b):
    validate_bundle(b)
    r = random.Random(20261031)
    samples = [
        -2000000001, -2000000, -1999999, -1500000, -1000001,
        -1000000, -999999, -500000, -1, 0, 1, 500000,
        999999, 1000000, 1000001, 1500000, 999999999
    ]
    samples += [r.randrange(-10**13, 10**13) for _ in range(400)]
    verdicts = []
    for i, row in enumerate(b["candidates"]):
        verdict = {"index": i, "source_sha256": row.get("source_sha256")}
        try:
            src = row.get("source")
            if row.get("index") != i or digest(src.encode()) != row.get("source_sha256"):
                raise ValueError("REAL_REPAIR_CANDIDATE_TAMPERED")
            tree = source_check(src)
            ns = {}
            exec(compile(tree, "<isolated-model-candidate>", "exec"),
                 {"__builtins__": {"int": int, "abs": abs}}, ns)
            fn = ns["floor_age_us"]
            for x in samples:
                actual = fn(x)
                if type(actual) is not int or actual != x // 1_000_000:
                    raise ValueError("REAL_REPAIR_BEHAVIOR_INCORRECT")
            verdict.update(status="PASS_SIGNED_MICROSECOND_FLOOR",
                           tested_cases=len(samples), past_and_future=True)
        except (ValueError, SyntaxError, TypeError, KeyError, AttributeError,
                ArithmeticError, NameError, RuntimeError, RecursionError) as exc:
            verdict.update(status="REJECTED", error=type(exc).__name__)
        verdicts.append(verdict)
    selected = next((v["index"] for v in verdicts
                     if v["status"] == "PASS_SIGNED_MICROSECOND_FLOOR"), None)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": "REVIEWABLE_MODEL_REPAIR" if selected is not None
                  else "HOLD_NO_VALID_MODEL_REPAIR",
        "source_bug": "FUTURE_SUBSECOND_TIMESTAMP_TRUNCATED_TO_ZERO",
        "original_source_blob_sha": PARENT_BLOB,
        "generator_commit": b.get("generator_commit"),
        "run_id": b.get("run_id"),
        "bundle_sha256": digest(json.dumps(b, sort_keys=True, separators=(",", ":")).encode()),
        "model_weights_sha256": WEIGHTS,
        "evaluated_cases_per_variant": len(samples),
        "selected_index": selected,
        "variants": verdicts,
        "sandbox_network_enabled": False,
        "trusted_runtime_execution": False,
        "main_code_mutations": 0,
        "auto_merge": False,
        "authority_delta": 0,
        "installed_into_production": False,
        "full_self_writer_proven": False,
    }
    return receipt


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bundle", required=True, type=Path)
    args = p.parse_args()
    raw = args.bundle.read_bytes()
    if not 0 < len(raw) < 20000:
        raise SystemExit("REAL_REPAIR_INPUT_SIZE_DENIED")
    try:
        result = evaluate(json.loads(raw))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit("REAL_REPAIR_HOLD:" + type(exc).__name__) from exc


if __name__ == "__main__":
    main()
