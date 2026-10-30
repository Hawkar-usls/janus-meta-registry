"""Reviewed admission policy for small pure self-maintenance extensions."""
from __future__ import annotations
import ast
import hashlib
import json
import re

MODEL_ID = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
MODEL_REVISION = "ea3f2471cf1b1f0db85067f1ef93848e38e88c25"
WEIGHTS_SHA256 = "f9523886352217ded3aeeef552b381af79d568c6d49a4b9e423288cea56b0a44"
IMAGE = "python@sha256:1148dbb014615300fa7e713b2f94f550c0d1c69780c0805f84f093ceee34dd0b"
BRANCH = "janus/autonomous-code-state"
HEX = re.compile(r"^[0-9a-f]{64}$")
RUN = re.compile(r"^[0-9]{5,}-[1-9][0-9]?$" )
TASKS = {
    "retry_delay": (["attempt", "cap"], "Return min(cap, 2 raised to attempt). Integers: 0 <= attempt <= 12, 1 <= cap <= 900. Return an integer. Used for bounded transport retry timing."),
    "clamp": (["value", "low", "high"], "Clamp integer value to the inclusive integer interval [low, high]. low <= high. Values are between -10000 and 10000."),
    "stable_unique": (["values"], "Return a new list containing the first occurrence of each string in values, preserving original order. Input has at most 64 strings. Do not mutate input."),
    "pending_count": (["produced", "confirmed"], "Return max(0, produced - confirmed) as integer. Both inputs are integers between 0 and 100000."),
    "is_fresh": (["age", "max_age"], "Return bool: True exactly when 0 <= age <= max_age. Inputs are integers between -10000 and 10000; max_age is nonnegative."),
    "chunk_count": (["total", "chunk_size"], "Return the integer number of chunks needed for total items, rounding up. total is integer 0..100000; chunk_size is integer 1..1000."),
    "bounded_batch": (["remaining", "limit"], "Return max(0, min(remaining, limit)). Inputs are integers; remaining is -100..10000 and limit is 0..1000."),
    "all_equal": (["values"], "Return bool: True when all integers in values are equal. Empty and one-element lists return True. At most 64 integers."),
    "safe_ratio": (["numerator", "denominator"], "Return numerator / denominator, or 0.0 when denominator is zero. Inputs are integers between -1000 and 1000."),
    "common_prefix": (["left", "right"], "Return the longest common prefix of two ASCII strings, each at most 64 characters. Return a string."),
}

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def source_digest(source):
    return hashlib.sha256(source.encode()).hexdigest()

def empty_state():
    return {"schema": "janus.autonomous_coder.state.v1", "sequence": 0, "accepted": {},
            "last_receipt": None, "authority_delta": 0, "universal_code_writer_proven": False}

def validate_state(state):
    if (state.get("schema") != "janus.autonomous_coder.state.v1" or state.get("authority_delta") != 0 or
        state.get("universal_code_writer_proven") is not False or type(state.get("sequence")) is not int or
        state["sequence"] < 0 or not isinstance(state.get("accepted"), dict) or set(state["accepted"]) - set(TASKS)):
        raise ValueError("INVALID_CODER_STATE")
    for task, entry in state["accepted"].items():
        if (not isinstance(entry, dict) or not HEX.fullmatch(entry.get("source_sha256", "")) or
            entry.get("path") != f'generated/{task}/{entry["source_sha256"]}.py' or
            not RUN.fullmatch(entry.get("run_id", "")) or not HEX.fullmatch(entry.get("receipt_sha256", ""))):
            raise ValueError("INVALID_ACCEPTED_EXTENSION")
    return state

def next_task(state):
    validate_state(state)
    return next((task for task in TASKS if task not in state["accepted"]), None)

def extract_source(raw):
    if not isinstance(raw, str) or not 0 < len(raw.encode()) <= 12000:
        raise ValueError("MODEL_OUTPUT_SIZE")
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", raw, re.S)
    return (blocks[0] if len(blocks) == 1 else raw).strip() + "\n"

def validate_source(source, task):
    if task not in TASKS or not isinstance(source, str) or not 0 < len(source.encode()) <= 4096:
        raise ValueError("SOURCE_SIZE_OR_TASK")
    tree = ast.parse(source)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("ONE_FUNCTION_REQUIRED")
    fn = tree.body[0]
    if (fn.name != task or [a.arg for a in fn.args.args] != TASKS[task][0] or
        fn.args.posonlyargs or fn.args.vararg or fn.args.kwarg or fn.args.kwonlyargs or
        fn.args.defaults or fn.args.kw_defaults or fn.decorator_list):
        raise ValueError("FUNCTION_SIGNATURE")
    forbidden = (ast.Import, ast.ImportFrom, ast.With, ast.AsyncWith, ast.AsyncFunctionDef,
                 ast.ClassDef, ast.Global, ast.Nonlocal, ast.Lambda, ast.Try, ast.Raise,
                 ast.Delete, ast.Yield, ast.YieldFrom, ast.Await, ast.NamedExpr)
    calls = {"min", "max", "abs", "len", "sum", "all", "any", "range", "enumerate", "zip",
             "sorted", "reversed", "list", "dict", "set", "tuple", "int", "float", "str", "bool", "round"}
    methods = {"append", "get", "items", "values", "keys", "fromkeys", "startswith"}
    nodes = list(ast.walk(tree))
    if len(nodes) > 512:
        raise ValueError("AST_TOO_LARGE")
    for node in nodes:
        if isinstance(node, forbidden):
            raise ValueError("FORBIDDEN_SYNTAX")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ValueError("PRIVATE_NAME")
        if isinstance(node, ast.Attribute) and node.attr not in methods:
            raise ValueError("FORBIDDEN_ATTRIBUTE")
        if isinstance(node, ast.Constant) and (isinstance(node.value, (str, bytes)) and len(node.value) > 128):
            raise ValueError("CONSTANT_TOO_LARGE")
        if isinstance(node, ast.Call):
            if not ((isinstance(node.func, ast.Name) and node.func.id in calls) or
                    (isinstance(node.func, ast.Attribute) and node.func.attr in methods)):
                raise ValueError("FORBIDDEN_CALL")
    return source

def validate_bundle(bundle):
    if (bundle.get("schema") != "janus.autonomous_coder.candidates.v1" or
        bundle.get("model") != {"id": MODEL_ID, "revision": MODEL_REVISION, "weights_sha256": WEIGHTS_SHA256,
                                "attribution": "EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS"} or
        not RUN.fullmatch(bundle.get("run_id", "")) or not HEX.fullmatch(bundle.get("base_state_sha256", ""))):
        raise ValueError("BUNDLE_IDENTITY")
    task = bundle.get("task_id")
    if task is None:
        if bundle.get("candidates") != []:
            raise ValueError("IDLE_WITH_CANDIDATES")
        return bundle
    if task not in TASKS or not isinstance(bundle.get("candidates"), list) or len(bundle["candidates"]) != 2:
        raise ValueError("BUNDLE_TASK_OR_VARIANTS")
    for index, row in enumerate(bundle["candidates"]):
        if (row.get("index") != index or extract_source(row.get("raw_response")) != row.get("source") or
            source_digest(row["source"]) != row.get("source_sha256")):
            raise ValueError("CANDIDATE_REBINDING")
    return bundle
