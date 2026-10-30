"""Review-bound self-module catalog built from exact model, evaluator and Git receipts.

This emits pure extension modules to the *isolated state branch only*. It never
imports generated code into the publisher, changes main, installs packages,
alters permissions, or treats source text as an instruction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from lifecycle import load, safe_path, write_new
from policy import (IMAGE, MODEL_ID, MODEL_REVISION, WEIGHTS_SHA256, TASKS,
                    canonical, digest, source_digest, validate_bundle,
                    validate_source, validate_state)

SCHEMA = "janus.autonomous_coder.module_index.v1"
MODULE_SCHEMA = "janus.autonomous_coder.pure_module.v1"
RECEIPT_SCHEMA = "janus.autonomous_coder.receipt.v1"
EVALUATION_SCHEMA = "janus.autonomous_coder.evaluation.v1"


def exact(root, name, limit=150000):
    path = safe_path(root, name)
    raw = path.read_bytes()
    if not raw or len(raw) > limit:
        raise ValueError("MODULE_INPUT_SIZE")
    return raw


def proven(root, task, entry):
    """Independent exact-source replay of all links; no model-output execution."""
    source_bytes = exact(root, entry["path"], 4096)
    source = source_bytes.decode("utf-8")
    if (source_digest(source) != entry["source_sha256"] or
            validate_source(source, task) != source):
        raise ValueError("MODULE_SOURCE_MISMATCH")
    receipt_bytes = exact(root, "receipts/" + entry["run_id"] + ".json")
    if hashlib.sha256(receipt_bytes).hexdigest() != entry["receipt_sha256"]:
        raise ValueError("MODULE_RECEIPT_BYTES_CHANGED")
    receipt = json.loads(receipt_bytes)
    if (receipt.get("schema") != RECEIPT_SCHEMA or
            receipt.get("run_id") != entry["run_id"] or
            receipt.get("task_id") != task or
            receipt.get("selected_source_sha256") != entry["source_sha256"] or
            receipt.get("status") != "PROMOTED_PURE_EXTENSION_ONLY" or
            receipt.get("authority_delta") != 0 or
            receipt.get("main_code_mutations") != 0 or
            receipt.get("full_issue_162_acceptance") is not False):
        raise ValueError("MODULE_RECEIPT_AUTHORITY_OR_SOURCE")
    bundle = json.loads(exact(root, "attempts/" + entry["run_id"] + "/CANDIDATES.json"))
    validate_bundle(bundle)
    if (bundle["run_id"] != entry["run_id"] or
            bundle["task_id"] != task or
            receipt.get("bundle_sha256") != digest(bundle) or
            receipt.get("model") != bundle["model"] or
            entry.get("author_model") != MODEL_ID):
        raise ValueError("MODULE_AUTHOR_BINDING")
    evaluation = receipt.get("evaluation")
    if not isinstance(evaluation, dict):
        raise ValueError("MODULE_EVALUATION_MISSING")
    unsigned = {key: val for key, val in evaluation.items() if key != "evaluation_sha256"}
    if (evaluation.get("schema") != EVALUATION_SCHEMA or
            evaluation.get("evaluation_sha256") != digest(unsigned) or
            evaluation.get("bundle_sha256") != digest(bundle) or
            evaluation.get("task_id") != task or
            evaluation.get("run_id") != entry["run_id"] or
            evaluation.get("image") != IMAGE or
            evaluation.get("code_commit") != bundle.get("code_commit") or
            evaluation.get("authority_delta") != 0 or
            evaluation.get("full_issue_162_acceptance") is not False):
        raise ValueError("MODULE_EVALUATOR_BINDING")
    results = evaluation.get("variants")
    candidates = bundle.get("candidates")
    if not isinstance(results, list) or len(results) != len(candidates):
        raise ValueError("MODULE_EVALUATION_SET")
    first_pass = None
    for index, (candidate, verdict) in enumerate(zip(candidates, results)):
        if (candidate["index"] != index or
                verdict.get("index") != index or
                candidate["source_sha256"] != verdict.get("source_sha256")):
            raise ValueError("MODULE_VERDICT_REBINDING")
        if verdict.get("status") == "PASS_PURE_FUNCTION_ONLY":
            if type(verdict.get("cases")) is not int or verdict["cases"] < 200:
                raise ValueError("MODULE_WEAK_BEHAVIOR_PROOF")
            if first_pass is None:
                first_pass = candidate
        elif verdict.get("status") != "REJECTED":
            raise ValueError("MODULE_UNKNOWN_VERDICT")
    if (first_pass is None or first_pass["source"] != source or
            first_pass["source_sha256"] != entry["source_sha256"]):
        raise ValueError("MODULE_MODEL_BYTES_NOT_SELECTED")
    return source_bytes, {
        "schema": MODULE_SCHEMA,
        "module_id": "janus.pure." + task + ".v1",
        "task_id": task,
        "public_signature": "def " + task + "(" + ", ".join(TASKS[task][0]) + ")",
        "source_sha256": entry["source_sha256"],
        "source_path": entry["path"],
        "receipt_sha256": entry["receipt_sha256"],
        "receipt_path": "receipts/" + entry["run_id"] + ".json",
        "author_model": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "model_weights_sha256": WEIGHTS_SHA256,
        "isolated_evaluation_image": IMAGE,
        "evaluated_cases": results[first_pass["index"]]["cases"],
        "run_id": entry["run_id"],
        "dependencies": [],
        "permissions": [],
        "import_into_trusted_main": False,
        "main_code_mutations": 0,
        "authority_delta": 0,
        "review_required_for_integration": True,
        "not_native_janus_model": True,
    }


def plan(root):
    root = Path(root)
    state = validate_state(load(safe_path(root, "STATE.json")))
    modules, artifacts = {}, {}
    for task in TASKS:
        if task not in state["accepted"]:
            continue
        content, manifest = proven(root, task, state["accepted"][task])
        name = "self_modules/" + task
        module_path = name + "/module.py"
        manifest_path = name + "/MODULE.json"
        artifacts[module_path] = content
        artifacts[manifest_path] = canonical(manifest) + b"\n"
        modules[task] = {
            "module_id": manifest["module_id"],
            "path": module_path,
            "manifest_path": manifest_path,
            "source_sha256": manifest["source_sha256"],
            "receipt_sha256": manifest["receipt_sha256"],
            "run_id": manifest["run_id"],
            "module_manifest_sha256": hashlib.sha256(artifacts[manifest_path]).hexdigest(),
        }
    index = {
        "schema": SCHEMA, "state_sequence": state["sequence"],
        "accepted_count": len(modules), "modules": modules,
        "installation_scope": "ISOLATED_STATE_BRANCH_ONLY",
        "model_authorship": "EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS",
        "runtime_auto_import": False,
        "new_permissions": 0, "authority_delta": 0,
        "full_issue_162_acceptance": False,
    }
    index["index_sha256"] = digest(index)
    return index, artifacts


def verify(root, expected_run_id=None):
    index, artifacts = plan(root)
    for name, data in artifacts.items():
        if exact(root, name, 150000) != data:
            raise ValueError("MODULE_PACKAGE_REBINDING")
    stored = json.loads(exact(root, "MODULE_INDEX.json"))
    if stored != index:
        raise ValueError("MODULE_INDEX_REBINDING")
    if expected_run_id is not None:
        state = load(safe_path(root, "STATE.json"))
        if state.get("last_receipt") != "receipts/" + expected_run_id + ".json":
            raise ValueError("MODULE_LATEST_RUN_MISMATCH")
        receipt = json.loads(exact(root, state["last_receipt"]))
        if receipt.get("run_id") != expected_run_id:
            raise ValueError("MODULE_RUN_RECEIPT_MISMATCH")
        if receipt.get("status") == "PROMOTED_PURE_EXTENSION_ONLY":
            task = receipt.get("task_id")
            if task not in index["modules"] or index["modules"][task]["run_id"] != expected_run_id:
                raise ValueError("MODULE_LATEST_NOT_PACKAGED")
        elif receipt.get("status") != "REJECTED_NO_PROMOTION":
            raise ValueError("MODULE_LATEST_STATUS_INVALID")
    return {"status": "VERIFIED_ISOLATED_MODULE_CATALOG",
            "modules": len(index["modules"]), "state_sequence": index["state_sequence"],
            "authority_delta": 0, "main_code_mutations": 0}


def build(root):
    root = Path(root)
    index, artifacts = plan(root)
    # Existing immutable module packages must never change in place, even if
    # a model later proposes another result for the same task.
    for name, data in artifacts.items():
        path = safe_path(root, name)
        if path.exists() and path.read_bytes() != data:
            raise ValueError("IMMUTABLE_MODULE_CONFLICT")
    prior = safe_path(root, "MODULE_INDEX.json")
    if prior.exists():
        earlier = json.loads(exact(root, "MODULE_INDEX.json"))
        if (earlier.get("schema") != SCHEMA or
                type(earlier.get("state_sequence")) is not int or
                earlier["state_sequence"] > index["state_sequence"] or
                not isinstance(earlier.get("modules"), dict)):
            raise ValueError("MODULE_CATALOG_ROLLBACK")
        for task, item in earlier["modules"].items():
            if task not in index["modules"] or item != index["modules"][task]:
                raise ValueError("MODULE_CATALOG_HISTORY_REWRITE")
    for name, data in artifacts.items():
        write_new(safe_path(root, name), data)
    prior.write_bytes(canonical(index) + b"\n")
    return verify(root)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("build", "verify"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--expected-run-id")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = build(args.root) if args.mode == "build" else verify(args.root, args.expected_run_id)
    data = canonical(result) + b"\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(data)
    print(data.decode().strip())


if __name__ == "__main__":
    main()
