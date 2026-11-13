"""One bounded CPU-only feedback iteration after a REAL independent rejected model patch.

Previous exact artifacts are pinned by byte SHA256 and run id. Model is asked
to correct *its own* rejected code; no assistant-authored candidate is supplied.
This does not authorize merging, production writes or arbitrary model code.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import time

from author import load_model
from policy import MODEL_ID, MODEL_REVISION, WEIGHTS_SHA256, extract_source, source_digest
from real_bug_repair_author import source_preflight, PROMPT, PARENT_BLOB_SHA

PRIOR_RUN = "41146877435-1"
PRIOR_BUNDLE_BYTES_SHA256 = "ad86af023af4f1282d7aa3be92340e8afc6f81f6eedc6139227dcd6d1c0e76f1"
PRIOR_EVALUATION_BYTES_SHA256 = "67b838ff5b1dae3899b57b625739395f0f0e9d23d62c86b474febfbe46112ab3"
PRIOR_VERDICT = "HOLD_NO_VALID_MODEL_REPAIR"


def load_prior(bundle_path, evaluation_path):
    rb = Path(bundle_path).read_bytes()
    re = Path(evaluation_path).read_bytes()
    if (hashlib.sha256(rb).hexdigest() != PRIOR_BUNDLE_BYTES_SHA256
            or hashlib.sha256(re).hexdigest() != PRIOR_EVALUATION_BYTES_SHA256):
        raise ValueError("REPAIR_FEEDBACK_PRIOR_BYTES_MISMATCH")
    old = json.loads(rb)
    verdict = json.loads(re)
    model = old.get("model", {})
    if (old.get("schema") != "janus.self_writer.real_bug_repair_candidates.v1"
            or old.get("run_id") != PRIOR_RUN
            or old.get("original_source", {}).get("git_blob_sha") != PARENT_BLOB_SHA
            or model.get("id") != MODEL_ID
            or model.get("revision") != MODEL_REVISION
            or model.get("weights_sha256") != WEIGHTS_SHA256
            or old.get("authority_delta") != 0 or old.get("auto_merge") is not False
            or old.get("publish_to_main") is not False
            or len(old.get("candidates", [])) != 2
            or verdict.get("schema") != "janus.self_writer.real_bug_repair_evaluation.v1"
            or verdict.get("run_id") != PRIOR_RUN
            or verdict.get("status") != PRIOR_VERDICT
            or verdict.get("selected_index") is not None
            or any(x.get("status") != "REJECTED"
                   for x in verdict.get("variants", []))
            or verdict.get("authority_delta") != 0
            or verdict.get("auto_merge") is not False):
        raise ValueError("REPAIR_FEEDBACK_PRIOR_PROVENANCE_REJECTED")
    return old, verdict


def feedback_prompt(prior):
    # Derive error types from actual raw candidate AST; never execute them.
    reasons = []
    for row in prior["candidates"]:
        try:
            tree = ast.parse(row["source"])
            errors = []
            if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
                errors.append("extra top-level constructs (imports or calls)")
            if any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree)):
                errors.append("imports prohibited")
            if any(isinstance(n, ast.Constant) and
                   type(n.value) is int and n.value == 1000
                   for n in ast.walk(tree)):
                errors.append("mixed up thousand with a MILLION")
            if any(isinstance(n, ast.Constant) and isinstance(n.value, str)
                   for n in ast.walk(tree)):
                errors.append("docstrings or explanatory strings prohibited")
            if any(isinstance(n, ast.Call) for n in ast.walk(tree)):
                errors.append("function calls prohibited; use pure arithmetic")
            reasons.append("; ".join(errors) if errors else "failed independent constraints")
        except SyntaxError:
            reasons.append("syntax not valid Python")
    return (
        "Previous responses from THIS SAME MODEL failed independent review:\n"
        + "\n".join("Attempt " + str(i) + " was rejected: " + x
                    for i, x in enumerate(reasons))
        + "\nOriginal bounded task: " + PROMPT
        + "\nProvide a genuinely corrected version, not explanations. "
        "Return exactly ONE function with signature def floor_age_us(delta_us): "
        "and a single return statement containing only integer arithmetic. "
        "Avoid imports, docstrings, printed tests, float division and extra code. "
        "The input is signed MICROSECONDS, not milliseconds. "
        "The operation must floor negative nonmultiples toward minus infinity."
    )


def generate(root, old, verdict, cache):
    evidence = source_preflight(root)
    torch, tokenizer, model, versions = load_model(cache)
    run_id = os.getenv("GITHUB_RUN_ID", "LOCAL") + "-" + os.getenv("GITHUB_RUN_ATTEMPT", "1")
    prompt = feedback_prompt(old)
    result = {
        "schema": "janus.self_writer.real_bug_repair_candidates.v1",
        "task": "signed_utc_age_floor",
        "original_source": evidence,
        "source_sha256": hashlib.sha256((root / evidence["path"]).read_bytes()).hexdigest(),
        "prompt": prompt, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION,
                  "weights_sha256": WEIGHTS_SHA256,
                  "authorship": "EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS"},
        "feedback_provenance": {
            "prior_run_id": PRIOR_RUN,
            "prior_bundle_file_sha256": PRIOR_BUNDLE_BYTES_SHA256,
            "prior_evaluation_file_sha256": PRIOR_EVALUATION_BYTES_SHA256,
            "prior_status": PRIOR_VERDICT,
            "attempt_limit": 1,
        },
        "generator_commit": os.environ.get("GITHUB_SHA", "LOCAL"),
        "run_id": run_id, "runtime_versions": versions,
        "candidates": [],
        "authority_delta": 0, "auto_merge": False, "publish_to_main": False,
    }
    for index in range(2):
        messages = [
            {"role": "system", "content": "You correct faulty small Python functions. Produce a single code-only function."},
            {"role": "user", "content": prompt + (
                " Use a different correct integer-only expression." if index else "")},
        ]
        inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True,
                                               tokenize=True, return_tensors="pt")
        torch.manual_seed(int(hashlib.sha256((run_id + ":" + str(index)).encode()).hexdigest()[:8], 16))
        start = time.monotonic()
        with torch.inference_mode():
            output = model.generate(
                inputs, attention_mask=torch.ones_like(inputs), max_new_tokens=130,
                do_sample=bool(index), temperature=0.6 if index else None,
                pad_token_id=tokenizer.eos_token_id)
        raw = tokenizer.decode(output[0, inputs.shape[-1]:], skip_special_tokens=True)
        source = extract_source(raw)
        result["candidates"].append({
            "index": index, "raw_response": raw, "source": source,
            "source_sha256": source_digest(source),
            "tokens_generated": int(output.shape[-1] - inputs.shape[-1]),
            "duration_seconds": round(time.monotonic() - start, 3),
        })
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path("."))
    p.add_argument("--cache", required=True)
    p.add_argument("--prior-bundle", type=Path, required=True)
    p.add_argument("--prior-evaluation", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    old, verdict = load_prior(args.prior_bundle, args.prior_evaluation)
    result = generate(args.root, old, verdict, args.cache)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "FEEDBACK_MODEL_CANDIDATES_UNVERIFIED",
                      "variants": len(result["candidates"]),
                      "prior_run": PRIOR_RUN,
                      "prompt_sha256": result["prompt_sha256"],
                      "authority_delta": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
