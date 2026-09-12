#!/usr/bin/env python3
"""Compatibility entry point for JANUS Fresco Forge.

Diffusers 0.40 removed some convenience methods from StableDiffusionPipeline.
This shim restores the historical calls expected by forge.py by delegating to
component-level APIs when needed, then executes the normal Forge main().
"""

from __future__ import annotations

from diffusers import StableDiffusionPipeline


def _install_compat_shims() -> None:
    if not hasattr(StableDiffusionPipeline, "enable_vae_slicing"):
        def enable_vae_slicing(self: StableDiffusionPipeline) -> None:
            vae = getattr(self, "vae", None)
            if vae is not None and hasattr(vae, "enable_slicing"):
                vae.enable_slicing()
        StableDiffusionPipeline.enable_vae_slicing = enable_vae_slicing  # type: ignore[attr-defined]

    if not hasattr(StableDiffusionPipeline, "enable_attention_slicing"):
        def enable_attention_slicing(self: StableDiffusionPipeline) -> None:
            unet = getattr(self, "unet", None)
            if unet is not None and hasattr(unet, "set_attention_slice"):
                unet.set_attention_slice("auto")
        StableDiffusionPipeline.enable_attention_slicing = enable_attention_slicing  # type: ignore[attr-defined]


_install_compat_shims()

from forge import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
