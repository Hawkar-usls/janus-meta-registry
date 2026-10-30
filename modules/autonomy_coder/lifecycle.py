"""Verify, publish and consume admitted extensions. Never execute them on the host."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
from policy import (TASKS, IMAGE, canonical, digest, source_digest, validate_source,
                    validate_state, validate_bundle, next_task)

def load(path):
    raw = Path(path).read_bytes()
    if len(raw) > 150000:
        raise ValueError("ARTIFACT_SIZE")
    return json.loads(raw)

def write_new(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("IMMUTABLE_CONFLICT")
    else:
        path.write_bytes(raw)

def safe_path(root, name):
    root = Path(root).resolve()
    path = root / name
    if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in [path, *path.parents] if p != root and p.is_relative_to(root)):
        raise ValueError("STATE_PATH_ESCAPE")
    return path

def isolated_check(source, task, *, call=None, runner=None, seed=None):
    validate_source(source, task)
    runner = runner or subprocess.run
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        folder.chmod(0o755)
        (folder / "source.py").write_text(source)
        (folder / "source.py").chmod(0o644)
        command = ["docker", "run", "--rm", "--network", "none", "--read-only", "--user", "65534:65534",
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "256m",
                   "--cpus", "1", "--pids-limit", "32", "--ulimit", "cpu=4:4",
                   "--mount", "type=bind,src=" + str(folder.resolve()) + ",dst=/input,readonly",
                   "--mount", "type=bind,src=" + str(Path(__file__).parent.resolve()) + ",dst=/suite,readonly",
                   IMAGE, "python", "-I", "-B", "/suite/checker.py", "--task", task,
                   "--source", "/input/source.py", "--seed", seed or secrets.token_hex(16)]
        if call is not None:
            command += ["--call", json.dumps(call)]
        done = runner(command, timeout=15, capture_output=True, text=True)
        if done.returncode or len(done.stdout.encode()) > 8192:
            raise ValueError("ISOLATED_CHECK_FAILED")
        result = json.loads(done.stdout)
        if result.get("status") != "PASS_PURE_FUNCTION_ONLY" or result.get("cases", 0) < 200:
            raise ValueError("INSUFFICIENT_BEHAVIORAL_EVIDENCE")
        return result

def evaluate(bundle, check=isolated_check):
    validate_bundle(bundle)
    rows = []
    for row in bundle["candidates"]:
        try:
            proof = check(row["source"], bundle["task_id"])
            result = {"status": "PASS_PURE_FUNCTION_ONLY", "cases": proof["cases"]}
        except (ValueError, SyntaxError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
            result = {"status": "REJECTED", "error_class": type(exc).__name__}
        rows.append({"index": row["index"], "source_sha256": row["source_sha256"], **result})
    result = {"schema": "janus.autonomous_coder.evaluation.v1", "bundle_sha256": digest(bundle),
              "run_id": bundle["run_id"], "task_id": bundle["task_id"], "image": IMAGE,
              "code_commit": os.environ.get("GITHUB_SHA", "LOCAL"), "variants": rows,
              "authority_delta": 0, "full_issue_162_acceptance": False}
    result["evaluation_sha256"] = digest(result)
    return result

def publish(root, bundle, evaluation):
    root = Path(root)
    validate_bundle(bundle)
    state = validate_state(load(safe_path(root, "STATE.json")))
    unsigned = {k: v for k, v in evaluation.items() if k != "evaluation_sha256"}
    if (evaluation.get("schema") != "janus.autonomous_coder.evaluation.v1" or
        evaluation.get("bundle_sha256") != digest(bundle) or evaluation.get("run_id") != bundle["run_id"] or
        evaluation.get("task_id") != bundle["task_id"] or evaluation.get("image") != IMAGE or
        evaluation.get("authority_delta") != 0 or evaluation.get("full_issue_162_acceptance") is not False or
        evaluation.get("evaluation_sha256") != digest(unsigned) or
        evaluation.get("code_commit") != bundle.get("code_commit") or
        len(evaluation.get("variants", [])) != len(bundle["candidates"])):
        raise ValueError("EVALUATION_REBINDING")
    selected = None
    for candidate, verdict in zip(bundle["candidates"], evaluation["variants"]):
        if (candidate["index"], candidate["source_sha256"]) != (verdict.get("index"), verdict.get("source_sha256")):
            raise ValueError("VERDICT_REBINDING")
        if verdict.get("status") == "PASS_PURE_FUNCTION_ONLY":
            validate_source(candidate["source"], bundle["task_id"])
            if type(verdict.get("cases")) is not int or verdict["cases"] < 200:
                raise ValueError("WEAK_VERDICT")
            if selected is None:
                selected = candidate
        elif verdict.get("status") != "REJECTED":
            raise ValueError("UNKNOWN_VERDICT")
    retained_path = safe_path(root, "receipts/" + bundle["run_id"] + ".json")
    if retained_path.exists():
        retained = load(retained_path)
        if retained.get("bundle_sha256") != digest(bundle) or retained.get("evaluation") != evaluation:
            raise ValueError("REPLAY_CONFLICT")
        entry = state["accepted"].get(bundle["task_id"])
        if selected and (not entry or entry.get("source_sha256") != selected["source_sha256"] or
                         source_digest(safe_path(root, entry["path"]).read_text()) != selected["source_sha256"]):
            raise ValueError("REPLAY_STATE_MISMATCH")
        return {"status": "ALREADY_PUBLISHED", "changed": False}
    if digest(state) != bundle["base_state_sha256"] or next_task(state) != bundle["task_id"]:
        raise ValueError("STALE_AUTHOR_STATE")
    if bundle["task_id"] is None:
        return {"status": "IDLE_ALL_ADMITTED_TASKS_DONE", "changed": False}
    run = bundle["run_id"]
    receipt = {"schema": "janus.autonomous_coder.receipt.v1", "run_id": run, "task_id": bundle["task_id"],
               "prior_state_sha256": digest(state), "bundle_sha256": digest(bundle),
               "evaluation": evaluation, "model": bundle["model"],
               "selected_source_sha256": selected["source_sha256"] if selected else None,
               "status": "PROMOTED_PURE_EXTENSION_ONLY" if selected else "REJECTED_NO_PROMOTION",
               "authority_delta": 0, "main_code_mutations": 0, "full_issue_162_acceptance": False}
    raw = canonical(receipt) + b"\n"
    write_new(safe_path(root, "attempts/" + run + "/CANDIDATES.json"), canonical(bundle) + b"\n")
    write_new(retained_path, raw)
    if selected:
        task, sha = bundle["task_id"], selected["source_sha256"]
        path = f"generated/{task}/{sha}.py"
        write_new(safe_path(root, path), selected["source"].encode())
        state["accepted"][task] = {"source_sha256": sha, "path": path, "run_id": run,
            "receipt_sha256": hashlib.sha256(raw).hexdigest(), "author_model": bundle["model"]["id"]}
    state.update(sequence=state["sequence"] + 1, last_receipt="receipts/" + run + ".json")
    safe_path(root, "STATE.json").write_bytes(canonical(state) + b"\n")
    safe_path(root, "ROADMAP.md").write_text("# JANUS autonomous code queue\n\n" + "\n".join(
        f"- [{'x' if task in state['accepted'] else ' '}] {task}" for task in TASKS) +
        "\n\nScope: pure extensions only. External model attribution retained. Full #162 acceptance remains false.\n")
    return {"status": receipt["status"], "changed": True, "task_id": bundle["task_id"],
            "accepted_count": len(state["accepted"]), "next_task": next_task(state)}

def consume(root, task="retry_delay", call=None, check=isolated_check):
    root = Path(root)
    state = validate_state(load(safe_path(root, "STATE.json")))
    if task not in state["accepted"]:
        return {"status": "WAIT_NO_ACCEPTED_EXTENSION", "task_id": task}
    entry = state["accepted"][task]
    source = safe_path(root, entry["path"]).read_text()
    receipt_raw = safe_path(root, "receipts/" + entry["run_id"] + ".json").read_bytes()
    receipt = json.loads(receipt_raw)
    if (source_digest(source) != entry["source_sha256"] or
        hashlib.sha256(receipt_raw).hexdigest() != entry["receipt_sha256"] or
        receipt.get("selected_source_sha256") != entry["source_sha256"] or receipt.get("task_id") != task or
        receipt.get("status") != "PROMOTED_PURE_EXTENSION_ONLY"):
        raise ValueError("CONSUMER_SOURCE_REBINDING")
    result = check(source, task, call=call)
    return {"status": "CONSUMED_VERIFIED_PURE_EXTENSION", "task_id": task,
            "source_sha256": entry["source_sha256"], "value": result.get("value"), "cases": result["cases"],
            "full_issue_162_acceptance": False, "authority_delta": 0}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("evaluate", "publish", "consume"))
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--evaluation", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "evaluate":
        result = evaluate(load(args.bundle))
    elif args.mode == "publish":
        result = publish(args.root, load(args.bundle), load(args.evaluation))
    else:
        result = consume(args.root, call=[3, 30])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(canonical(result) + b"\n")
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    main()
