"""JANUS real-bug repair author. Only pinned external Qwen weights author bytes.

A real failing regression exists in real_operational_consumer.py: int(-0.5) == 0,
so a future-dated source is falsely reported fresh. Model's only task is a
narrow pure signed-microsecond age helper. This author NEVER runs model output.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from strong_code_model import load_model
from strong_code_model import MODEL_ID, MODEL_REVISION, WEIGHTS_SHA256
from policy import extract_source, source_digest

TARGET = "modules/autonomy_coder/real_operational_consumer.py"
PARENT_BLOB_SHA = "7a28b110fef7c7458372ba50c9e5d37224d4c0a0"
ORIGINAL = 'age = int((clock - _timestamp(latest.get("last_observed_at_utc"))).total_seconds())'
FUNCTION = "floor_age_us"
PROMPT = (
    "Write a pure Python function with the EXACT signature "
    "def floor_age_us(delta_us):\n"
    "The input is a signed integer number of microseconds elapsed between "
    "now and an observed UTC timestamp. Return the mathematically floored "
    "whole number of seconds, as an integer; negative fractions MUST round "
    "toward negative infinity. For example a future timestamp by 500000 "
    "microseconds must produce -1, not 0; an elapsed interval of 1500000 "
    "microseconds must produce 1. Do not write tests, imports, print, "
    "decorators, explanations, or Markdown. Return only one function."
)


def source_preflight(root: Path):
    path = root / TARGET
    raw = path.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if blob != PARENT_BLOB_SHA or raw.decode("utf-8").count(ORIGINAL) != 1:
        raise ValueError("REAL_REPAIR_PARENT_SOURCE_MOVED")
    if int(-0.5) != 0:
        raise ValueError("REAL_REPAIR_BASELINE_BUG_NOT_REPRODUCIBLE")
    return {"path": TARGET, "git_blob_sha": blob,
            "real_baseline_input_us": -500000,
            "real_baseline_age_seconds": 0,
            "expected_correct_age_seconds": -1}


def generate(root: Path, cache):
    evidence = source_preflight(root)
    torch, tokenizer, model, versions = load_model(cache)
    run_id = os.getenv("GITHUB_RUN_ID", "LOCAL") + "-" + os.getenv("GITHUB_RUN_ATTEMPT", "1")
    result = {
        "schema": "janus.self_writer.real_bug_repair_candidates.v1",
        "task": "signed_utc_age_floor",
        "original_source": evidence,
        "source_sha256": hashlib.sha256((root / TARGET).read_bytes()).hexdigest(),
        "prompt": PROMPT,
        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION,
                  "weights_sha256": WEIGHTS_SHA256,
                  "authorship": "EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS"},
        "generator_commit": os.environ.get("GITHUB_SHA", "LOCAL"),
        "run_id": run_id, "runtime_versions": versions, "candidates": [],
        "authority_delta": 0, "auto_merge": False, "publish_to_main": False
    }
    for index in range(2):
        messages = [
            {"role": "system", "content": "You write short Python functions. Return code only."},
            {"role": "user", "content": PROMPT +
                (" Write a different valid implementation." if index else "")}
        ]
        inputs = tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=True, return_tensors="pt")
        torch.manual_seed(int(hashlib.sha256((run_id + ":" + str(index)).encode()).hexdigest()[:8], 16))
        start = time.monotonic()
        with torch.inference_mode():
            output = model.generate(
                inputs, attention_mask=torch.ones_like(inputs), max_new_tokens=132,
                do_sample=bool(index), temperature=0.6 if index else None,
                pad_token_id=tokenizer.eos_token_id)
        raw = tokenizer.decode(output[0, inputs.shape[-1]:], skip_special_tokens=True)
        source = extract_source(raw)
        result["candidates"].append({
            "index": index, "raw_response": raw, "source": source,
            "source_sha256": source_digest(source),
            "tokens_generated": int(output.shape[-1] - inputs.shape[-1]),
            "duration_seconds": round(time.monotonic() - start, 3)
        })
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--cache", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    b = generate(args.root, args.cache)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(b, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "REAL_MODEL_AUTHORED_CANDIDATES_UNVERIFIED",
                      "variants": len(b["candidates"]),
                      "source_blob_sha": b["original_source"]["git_blob_sha"],
                      "prompt_sha256": b["prompt_sha256"],
                      "model_revision": b["model"]["revision"],
                      "authority_delta": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
