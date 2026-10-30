"""CPU author: pinned open weights, no API key, no execution of model output."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from policy import (MODEL_ID, MODEL_REVISION, WEIGHTS_SHA256, TASKS, digest, empty_state,
                    next_task, extract_source, source_digest, validate_bundle)

FILES = {"config.json": "e2aa18293b0dd66539341467fa454878a5adb2be",
         "generation_config.json": "c28f9c697cbc09f047434efec57556505af31111",
         "merges.txt": "20024bfe7c83998e9aeaf98a0cd6a2ce6306c2f0",
         "tokenizer.json": "443909a61d429dff23010e5bddd28ff530edda00",
         "tokenizer_config.json": "acee076f49bf3c0298e15de0909d1da7b392f0c3",
         "vocab.json": "4783fe10ac3adce15ac8f358ef5462739852c569"}

def load_model(cache):
    import torch
    import transformers
    from huggingface_hub import snapshot_download
    folder = Path(snapshot_download(MODEL_ID, revision=MODEL_REVISION, cache_dir=cache,
                                   allow_patterns=list(FILES) + ["model.safetensors"]))
    for name, expected in FILES.items():
        raw = (folder / name).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if actual != expected:
            raise ValueError("MODEL_CONFIG_DIGEST")
    h = hashlib.sha256()
    with (folder / "model.safetensors").open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    if h.hexdigest() != WEIGHTS_SHA256:
        raise ValueError("MODEL_WEIGHTS_DIGEST")
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    tokenizer = transformers.AutoTokenizer.from_pretrained(folder, local_files_only=True, trust_remote_code=False)
    model = transformers.AutoModelForCausalLM.from_pretrained(folder, local_files_only=True,
        trust_remote_code=False, use_safetensors=True, torch_dtype=torch.float32).eval()
    return torch, tokenizer, model, {"torch": torch.__version__, "transformers": transformers.__version__}

def generate(state, run_id, cache):
    task = next_task(state)
    result = {"schema": "janus.autonomous_coder.candidates.v1", "run_id": run_id,
              "base_state_sha256": digest(state), "task_id": task,
              "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "weights_sha256": WEIGHTS_SHA256,
                        "attribution": "EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS"},
              "code_commit": os.environ.get("GITHUB_SHA", "LOCAL"), "candidates": []}
    if task is None:
        return validate_bundle(result)
    torch, tokenizer, model, versions = load_model(cache)
    result["runtime_versions"] = versions
    args, description = TASKS[task]
    prompt = (f"Write one Python function: def {task}({', '.join(args)}):\n{description}\n"
              "Return only Python code. No imports, no I/O, no external functions, no decorators. "
              "Use only Python builtins and local variables. Do not include tests or a main program.")
    for index in range(2):
        messages = [{"role": "system", "content": "You write short, correct, pure Python functions."},
                    {"role": "user", "content": prompt + (" Prefer a different implementation." if index else "")}]
        inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True,
                                              tokenize=True, return_tensors="pt")
        torch.manual_seed(int(hashlib.sha256((run_id + str(index)).encode()).hexdigest()[:8], 16))
        start = time.monotonic()
        with torch.inference_mode():
            output = model.generate(inputs, attention_mask=torch.ones_like(inputs), max_new_tokens=384,
                do_sample=bool(index), temperature=0.6 if index else None,
                pad_token_id=tokenizer.eos_token_id)
        raw = tokenizer.decode(output[0, inputs.shape[-1]:], skip_special_tokens=True)
        source = extract_source(raw)
        result["candidates"].append({"index": index, "raw_response": raw, "source": source,
            "source_sha256": source_digest(source), "generated_tokens": output.shape[-1] - inputs.shape[-1],
            "duration_seconds": round(time.monotonic() - start, 3)})
    return validate_bundle(result)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", required=True)
    args = parser.parse_args()
    state = json.loads(args.state.read_bytes()) if args.state.exists() else empty_state()
    bundle = generate(state, os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"], args.cache)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(bundle, sort_keys=True, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"task_id": bundle["task_id"], "variants": len(bundle["candidates"]),
                      "model_revision": MODEL_REVISION, "status": "GENERATED_UNVERIFIED" if bundle["task_id"] else "IDLE_ALL_ADMITTED_TASKS_DONE"}))

if __name__ == "__main__":
    main()
