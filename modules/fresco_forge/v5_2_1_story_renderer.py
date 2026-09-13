#!/usr/bin/env python3
"""JANUS Fresco Forge v5.2.1 scheduler compatibility hotfix.

DreamShaper 8 ships a scheduler configuration whose algorithm is incompatible with
v3's unconditional DPMSolverMultistepScheduler conversion under current diffusers.
Keep the model-native scheduler instead; all v5.2 story, anti-collapse, retry,
quarantine and receipt logic remains unchanged.
"""
from __future__ import annotations

import torch
from diffusers import StableDiffusionPipeline

import forge as base
import v5_2_story_renderer as v52

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v5.2.1-reference-style-native-scheduler"


def create_pipeline(model: str) -> StableDiffusionPipeline:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    print(f"FRESCO_FORGE_DEVICE={device}")
    print(f"FRESCO_FORGE_MODEL={model}")
    print("FRESCO_FORGE_SCHEDULER=MODEL_NATIVE")
    try:
        pipe = StableDiffusionPipeline.from_pretrained(model, dtype=dtype)
    except TypeError:
        pipe = StableDiffusionPipeline.from_pretrained(model, torch_dtype=dtype)
    pipe = pipe.to(device)
    if device == "cpu":
        if hasattr(pipe, "enable_attention_slicing"):
            pipe.enable_attention_slicing()
        elif hasattr(pipe.unet, "set_attention_slice"):
            pipe.unet.set_attention_slice("auto")
        if hasattr(pipe, "enable_vae_slicing"):
            pipe.enable_vae_slicing()
        elif hasattr(pipe.vae, "enable_slicing"):
            pipe.vae.enable_slicing()
    return pipe


# Importing v5.2 installs all story/prompt/gate monkeypatches.  Override only the
# pipeline constructor that failed with DreamShaper 8.
base.GENERATOR_VERSION = GENERATOR_VERSION
base.create_pipeline = create_pipeline
base.generate_one = v52.generate_one

if __name__ == "__main__":
    raise SystemExit(base.main())
