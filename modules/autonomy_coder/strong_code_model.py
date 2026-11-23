"""Verified CPU-only larger open-weights author, no privileged actions."""
from pathlib import Path
import hashlib
import os

MODEL_ID = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
MODEL_REVISION = "2e1fd397ee46e1388853d2af2c993145b0f1098a"
WEIGHTS_SHA256 = "c1b9b30e907950516ba3c646bdf570d8084c25a6410a0cdca80cf04b11bc13a8"

def load_model(cache):
    import torch
    import transformers
    from huggingface_hub import snapshot_download
    folder = Path(snapshot_download(
        MODEL_ID, revision=MODEL_REVISION, cache_dir=cache,
        allow_patterns=("*.json", "*.txt", "model.safetensors"),
    ))
    weights = folder / "model.safetensors"
    digest = hashlib.sha256()
    with weights.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != WEIGHTS_SHA256:
        raise ValueError("PINNED_STRONG_CODER_WEIGHTS_MISMATCH")
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        folder, local_files_only=True, trust_remote_code=False)
    model = transformers.AutoModelForCausalLM.from_pretrained(
        folder, local_files_only=True, trust_remote_code=False,
        use_safetensors=True, torch_dtype=torch.float32).eval()
    return torch, tokenizer, model, {
        "torch": torch.__version__, "transformers": transformers.__version__,
    }
