#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JGPT_CODEX.py
MIT License

A GitHub-ready, single-file JANUS trainer/exporter/runtime registry module.

What this file does:
- trains a compact byte-level autoregressive transformer on real text/code corpora
- tracks training quality with EMA and a lightweight tachyon-style predictor
- protects against gradient spikes and non-finite gradients
- exports canonical JANUS import payloads for HTTP or SMB handoff
- emits clean "quantum JSON" runtime registries with strict observed/inferred/planned separation
- keeps the exported metadata compatible with HRAIN / Titan / NAS style workflows

Important note:
"quantum JSON" here is a registry naming convention for multi-state knowledge packing.
It does not claim any quantum-physics mechanism.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import random
import socket
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

try:
    import psutil
except Exception:  # pragma: no cover
    psutil = None

try:
    import requests
except Exception:  # pragma: no cover
    requests = None

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    import torch.nn.functional as F
except Exception as exc:  # pragma: no cover
    raise RuntimeError("PyTorch is required for JGPT_CODEX.py") from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utc_now_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_text_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_json_write(path: Path, payload: Dict[str, Any]) -> None:
    atomic_text_write(path, json.dumps(payload, ensure_ascii=False, indent=2))


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def clip_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def sha1_json(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def read_textish_file(path: Path, max_bytes: int) -> str:
    try:
        data = path.read_bytes()[:max_bytes]
    except Exception:
        return ""
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def iter_live_files(root: Path, extensions: Sequence[str], recursive: bool = True) -> Iterable[Path]:
    if recursive:
        for current_root, _, files in os.walk(root):
            for name in files:
                path = Path(current_root) / name
                if path.suffix.lower() in extensions:
                    yield path
    else:
        for path in root.iterdir():
            if path.is_file() and path.suffix.lower() in extensions:
                yield path


def load_code_corpus(
    roots: Sequence[Path],
    extensions: Sequence[str],
    max_files: int,
    max_file_bytes: int,
) -> Tuple[bytes, Dict[str, Any]]:
    chunks: List[bytes] = []
    used_files = 0
    used_bytes = 0
    meta_files: List[str] = []

    for root in roots:
        if not root.exists():
            continue
        for path in iter_live_files(root, extensions, recursive=True):
            if used_files >= max_files:
                break
            text = read_textish_file(path, max_file_bytes)
            if not text.strip():
                continue
            block = f"\n\n# FILE: {path.as_posix()}\n{text}\n".encode("utf-8", errors="ignore")
            chunks.append(block)
            used_files += 1
            used_bytes += len(block)
            meta_files.append(path.as_posix())
        if used_files >= max_files:
            break

    return b"".join(chunks), {
        "files": used_files,
        "bytes": used_bytes,
        "roots": [p.as_posix() for p in roots],
        "sample_files": meta_files[:24],
    }


def default_registry_template() -> Dict[str, Any]:
    return {
        "$schema": "https://janus.local/schemas/quantum-registry/v1.json",
        "registry_kind": "janus_quantum_json",
        "title": "JANUS Runtime Registry",
        "license": "MIT",
        "epistemic_contract": {
            "observed": "Directly grounded in code, logs, metrics, or file metadata.",
            "inferred": "Derived interpretation based on observed signals.",
            "planned": "Intended work not yet verified."
        },
    }


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG: Dict[str, Any] = {
    "save_dir": "./jgpt_codex_runtime",
    "logs_dir": "./jgpt_codex_runtime/logs",
    "exports_dir": "./jgpt_codex_runtime/exports",
    "registry_dir": "./jgpt_codex_runtime/registry",
    "device": "cuda" if torch.cuda.is_available() else "cpu",
    "seed": 42,
    # corpus
    "code_roots": ["."],
    "file_extensions": [".py", ".txt", ".md", ".json", ".yaml", ".yml", ".ini", ".cfg", ".toml", ".log", ".csv"],
    "max_files": 4000,
    "max_file_bytes": 1_500_000,
    "min_corpus_bytes": 4096,
    "val_ratio": 0.10,
    # model
    "vocab_size": 256,
    "block_size": 256,
    "n_layer": 4,
    "n_embd": 256,
    "n_head": 8,
    "dropout": 0.10,
    # train
    "batch_size": 16,
    "lr": 3e-4,
    "weight_decay": 0.01,
    "grad_clip": 1.0,
    "train_steps_per_cycle": 100,
    "eval_batches": 16,
    "cycles": 10,
    "ema_alpha": 0.10,
    # protection
    "gradient_blackhole_threshold": 8.0,
    "gradient_blackhole_decay": 0.35,
    "gradient_starvation_floor": 1e-7,
    "gradient_blackhole_spike_ratio": 2.6,
    # runtime
    "tachyon_lead_factor": 1.8,
    "checkpoint_every": 1,
    "history_jsonl": "history.jsonl",
    "event_jsonl": "events.jsonl",
    # export
    "nas_http_enabled": False,
    "nas_http_import_url": "http://127.0.0.1:5000/api/quant/import",
    "nas_http_timeout": 10.0,
    "nas_http_device_id": "jgpt_codex_runtime",
    "nas_source_name": "jgpt_codex_runtime",
    "quantize_mode": "int8",
    "write_registry_every_cycle": True,
}


def build_config_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    cfg = dict(CONFIG)
    cfg["save_dir"] = args.save_dir or cfg["save_dir"]
    cfg["logs_dir"] = str(Path(cfg["save_dir"]) / "logs")
    cfg["exports_dir"] = str(Path(cfg["save_dir"]) / "exports")
    cfg["registry_dir"] = str(Path(cfg["save_dir"]) / "registry")
    cfg["code_roots"] = args.code_roots or cfg["code_roots"]
    cfg["cycles"] = int(args.cycles or cfg["cycles"])
    cfg["batch_size"] = int(args.batch_size or cfg["batch_size"])
    cfg["train_steps_per_cycle"] = int(args.train_steps_per_cycle or cfg["train_steps_per_cycle"])
    if args.device:
        cfg["device"] = args.device
    return cfg


# ---------------------------------------------------------------------------
# Logging and monitoring
# ---------------------------------------------------------------------------

def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("JGPT_CODEX")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    return logger


class SystemMonitor:
    def snapshot(self) -> Dict[str, float]:
        cpu = 0.0
        ram = 0.0
        if psutil is not None:
            try:
                cpu = float(psutil.cpu_percent(interval=None))
                ram = float(psutil.virtual_memory().percent)
            except Exception:
                pass
        gpu = 0.0
        vram = 0.0
        if torch.cuda.is_available():
            try:
                vram = float(torch.cuda.memory_allocated() / max(1, torch.cuda.get_device_properties(0).total_memory))
            except Exception:
                pass
        return {
            "cpu_percent": cpu,
            "ram_percent": ram,
            "gpu_percent": gpu,
            "vram_ratio": vram,
        }


class RollingEMA:
    def __init__(self, alpha: float):
        self.alpha = float(alpha)
        self.value: Optional[float] = None

    def update(self, x: float) -> float:
        x = float(x)
        self.value = x if self.value is None else (1.0 - self.alpha) * self.value + self.alpha * x
        return float(self.value)


class TachyonField:
    def __init__(self, lead: float):
        self.lead = float(lead)
        self.history: Deque[float] = deque(maxlen=3)

    def update(self, score: float) -> Dict[str, float]:
        self.history.append(float(score))
        if len(self.history) == 1:
            return {"velocity": 0.0, "acceleration": 0.0, "predicted_score": float(score)}
        if len(self.history) == 2:
            v = self.history[-1] - self.history[-2]
            return {"velocity": v, "acceleration": 0.0, "predicted_score": self.history[-1] + v * self.lead}
        prev_prev, prev, cur = self.history[-3], self.history[-2], self.history[-1]
        velocity = cur - prev
        acceleration = cur - 2.0 * prev + prev_prev
        predicted = cur + velocity * self.lead + 0.5 * acceleration
        return {
            "velocity": float(velocity),
            "acceleration": float(acceleration),
            "predicted_score": float(predicted),
        }


class GradientBlackholeGuard:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.grad_norm_ema: Optional[float] = None

    def inspect(self, model: nn.Module) -> Dict[str, float]:
        total_sq = 0.0
        max_abs = 0.0
        mean_abs_total = 0.0
        count = 0
        nonfinite = False
        small = 0
        for p in model.parameters():
            if p.grad is None:
                continue
            g = p.grad.detach()
            if not torch.isfinite(g).all():
                nonfinite = True
            total_sq += float(torch.norm(g).item()) ** 2
            max_abs = max(max_abs, float(g.abs().max().item()))
            mean_abs_total += float(g.abs().mean().item()) * float(g.numel())
            small += int((g.abs() < self.cfg["gradient_starvation_floor"]).sum().item())
            count += int(g.numel())
        grad_norm = math.sqrt(max(total_sq, 0.0))
        mean_abs_grad = float(mean_abs_total / max(1, count))
        starvation_ratio = float(small / max(1, count))
        return {
            "grad_norm": grad_norm,
            "max_abs_grad": max_abs,
            "nonfinite": 1.0 if nonfinite else 0.0,
            "mean_abs_grad": mean_abs_grad,
            "starvation_ratio": starvation_ratio,
        }

    def apply(self, model: nn.Module, diag: Dict[str, float], optimizer: optim.Optimizer) -> Dict[str, Any]:
        grad_norm = float(diag["grad_norm"])
        self.grad_norm_ema = grad_norm if self.grad_norm_ema is None else 0.92 * self.grad_norm_ema + 0.08 * grad_norm
        grad_spike_ratio = grad_norm / max(self.grad_norm_ema, 1e-8)
        event = "stable"

        if bool(diag["nonfinite"]):
            event = "nonfinite"
            for p in model.parameters():
                if p.grad is not None:
                    p.grad = torch.nan_to_num(p.grad, nan=0.0, posinf=0.0, neginf=0.0)
                    p.grad.zero_()
        elif (
            grad_norm > self.cfg["gradient_blackhole_threshold"]
            and grad_spike_ratio > self.cfg["gradient_blackhole_spike_ratio"]
        ):
            event = "blackhole_spike"
            decay = float(self.cfg["gradient_blackhole_decay"])
            for p in model.parameters():
                if p.grad is not None:
                    p.grad.mul_(1.0 - decay)

        try:
            torch.nn.utils.clip_grad_norm_(model.parameters(), self.cfg["grad_clip"])
        except Exception:
            pass

        return {
            "event": event,
            "grad_norm_ema": float(self.grad_norm_ema or grad_norm),
            "grad_spike_ratio": float(grad_spike_ratio),
        }


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class ByteTransformer(nn.Module):
    def __init__(self, cfg: Dict[str, Any]):
        super().__init__()
        self.vocab_size = int(cfg["vocab_size"])
        self.block_size = int(cfg["block_size"])
        self.n_embd = int(cfg["n_embd"])
        self.n_head = int(cfg["n_head"])
        self.n_layer = int(cfg["n_layer"])
        self.dropout = float(cfg["dropout"])

        self.wte = nn.Embedding(self.vocab_size, self.n_embd)
        self.wpe = nn.Embedding(self.block_size, self.n_embd)

        enc = nn.TransformerEncoderLayer(
            d_model=self.n_embd,
            nhead=self.n_head,
            dim_feedforward=4 * self.n_embd,
            dropout=self.dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.transformer = nn.TransformerEncoder(enc, num_layers=self.n_layer, enable_nested_tensor=False)
        self.ln_f = nn.LayerNorm(self.n_embd)
        self.lm_head = nn.Linear(self.n_embd, self.vocab_size, bias=False)
        self.apply(self._init_weights)

    def _init_weights(self, module: nn.Module) -> None:
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if isinstance(module, nn.Linear) and module.bias is not None:
                nn.init.zeros_(module.bias)

    def forward(self, idx: torch.Tensor) -> torch.Tensor:
        seq_len = min(idx.size(1), self.block_size)
        idx = idx[:, :seq_len]
        pos = torch.arange(0, seq_len, device=idx.device)
        x = self.wte(idx) + self.wpe(pos)[None, :, :]
        mask = torch.triu(torch.ones(seq_len, seq_len, device=idx.device) * float("-inf"), diagonal=1)
        x = self.transformer(x, mask=mask)
        return self.lm_head(self.ln_f(x))


# ---------------------------------------------------------------------------
# Exporter and registry
# ---------------------------------------------------------------------------

class NASShadowExporter:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

    def model_config(self) -> Dict[str, Any]:
        return {
            "arch": "ByteTransformer",
            "export_runtime": "pc_jgpt",
            "lightweight_runtime_target": "janus_nas_microgpt",
            "vocab_size": int(self.cfg["vocab_size"]),
            "block_size": int(self.cfg["block_size"]),
            "n_layer": int(self.cfg["n_layer"]),
            "n_embd": int(self.cfg["n_embd"]),
            "n_head": int(self.cfg["n_head"]),
            "dropout": float(self.cfg["dropout"]),
        }

    def export_weight_summary(self, state_dict: Dict[str, torch.Tensor]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for name, tensor in state_dict.items():
            arr = tensor.detach().float().cpu()
            out[name] = {
                "shape": list(arr.shape),
                "mean": float(arr.mean().item()),
                "std": float(arr.std().item()),
                "absmax": float(arr.abs().max().item()),
            }
        return out

    def _quantize_scalar(self, value: float, bits: int) -> int:
        levels = (2 ** (max(2, int(bits)) - 1)) - 1
        clipped = max(-1.0, min(1.0, float(value)))
        return int(round(clipped * levels))

    def _quantize_array(self, arr: np.ndarray, mode: str) -> Any:
        mode = str(mode).strip().lower()
        if mode == "int8":
            return np.clip(np.round(arr * 127.0), -127, 127).astype(int).tolist()
        if mode == "int4":
            return np.clip(np.round(arr * 7.0), -7, 7).astype(int).tolist()

        # mixed mode
        def quantize_value(v: float) -> Any:
            av = abs(float(v))
            if av < 0.12:
                return {"q": self._quantize_scalar(v, 4), "bits": 4}
            if av < 0.55:
                return {"q": self._quantize_scalar(v, 8), "bits": 8}
            return round(float(v), 4)

        return np.vectorize(quantize_value, otypes=[object])(arr).tolist()

    def export_quantized_weights(self, state_dict: Dict[str, torch.Tensor]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for name, tensor in state_dict.items():
            arr = tensor.detach().float().cpu().numpy()
            out[name] = self._quantize_array(arr, self.cfg["quantize_mode"])
        return out

    def build_meta(self, cycle: int, best_val: float, diagnostics: Dict[str, Any], transport: str, payload_branch: str) -> Dict[str, Any]:
        diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
        return {
            "source": self.cfg["nas_source_name"],
            "device_id": self.cfg["nas_http_device_id"],
            "cycle": int(cycle),
            "best_val": float(best_val),
            "timestamp": utc_now_z(),
            "transport": str(transport),
            "payload_branch": str(payload_branch),
            "search_mode": diagnostics.get("search_mode"),
            "mode_label": diagnostics.get("mode_label"),
            "model_signature": diagnostics.get("model_config") or self.model_config(),
            "swarm_success_rate": diagnostics.get("swarm_success_rate"),
            "handoff_role": "pc_to_nas_quantized_export",
            "event_id": diagnostics.get("event_id"),
            "dedupe_key": diagnostics.get("dedupe_key"),
            "lineage": diagnostics.get("lineage"),
            "graph_hint": diagnostics.get("graph_hint"),
            "thought_hint": diagnostics.get("thought_hint"),
            "experience_hints": diagnostics.get("experience_hints"),
            "titan_hints": diagnostics.get("titan_hints"),
            "memory_contract": diagnostics.get("memory_contract"),
            "import_contract": diagnostics.get("import_contract"),
            "transfer_manifest": diagnostics.get("transfer_manifest"),
            "janus_context": diagnostics.get("janus_context"),
            "diagnostics": diagnostics,
            "provenance": {
                "trainer": "JGPT_CODEX.py",
                "ecosystem": ["HRAIN", "Titan", "janus_nas", "pc_to_nas_quant_handoff"],
                "windows_safe": True,
            },
        }

    def build_http_payload(self, state_dict: Dict[str, torch.Tensor], cycle: int, best_val: float, diagnostics: Dict[str, Any]) -> Dict[str, Any]:
        payload_branch = "canonical_weights"
        return {
            "format": "janus_import_canonical_v1",
            "event_id": diagnostics.get("event_id"),
            "dedupe_key": diagnostics.get("dedupe_key"),
            "payload_branch": payload_branch,
            "transport": "http",
            "quant_mode": self.cfg["quantize_mode"],
            "weights": self.export_quantized_weights(state_dict),
            "model_config": self.model_config(),
            "weight_summary": self.export_weight_summary(state_dict),
            "meta": self.build_meta(cycle, best_val, diagnostics, transport="http", payload_branch=payload_branch),
        }

    def build_smb_payload(self, state_dict: Dict[str, torch.Tensor], cycle: int, best_val: float, diagnostics: Dict[str, Any]) -> Dict[str, Any]:
        payload_branch = "smb_quantized_model"
        return {
            "format": "janus_import_smb_quant_v1",
            "event_id": diagnostics.get("event_id"),
            "dedupe_key": diagnostics.get("dedupe_key"),
            "payload_branch": payload_branch,
            "transport": "smb_inbox",
            "quant_mode": self.cfg["quantize_mode"],
            "quantized_model": {
                "state": self.export_quantized_weights(state_dict),
                "mode": self.cfg["quantize_mode"],
            },
            "model_config": self.model_config(),
            "weight_summary": self.export_weight_summary(state_dict),
            "meta": self.build_meta(cycle, best_val, diagnostics, transport="smb_inbox", payload_branch=payload_branch),
        }


class QuantumRegistryBuilder:
    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg

    def build(self, trainer: "EvolutionTrainer", diag: Dict[str, Any]) -> Dict[str, Any]:
        payload = default_registry_template()
        payload.update({
            "registry_id": f"jgp_codex_registry_cycle_{trainer.current_cycle}",
            "version": "1.0.0",
            "created_utc": utc_now_z(),
            "runtime": {
                "device": self.cfg["device"],
                "host": socket.gethostname(),
                "cycle": int(trainer.current_cycle),
                "best_val": float(trainer.best_val),
                "ema_val": float(trainer.ema.value if trainer.ema.value is not None else trainer.best_val),
            },
            "components": {
                "trainer": {
                    "name": "JGPT CODEX",
                    "state": "observed",
                    "model_signature": trainer.exporter.model_config(),
                },
                "tachyon": {
                    "state": "observed",
                    "lead_factor": float(self.cfg["tachyon_lead_factor"]),
                    "latest": diag.get("tachyon"),
                },
                "gradient_guard": {
                    "state": "observed",
                    "latest": diag.get("grad"),
                },
            },
            "observed_metrics": {
                "loss_train": diag.get("train_loss"),
                "loss_val": diag.get("val_loss"),
                "monitor": diag.get("monitor"),
            },
            "inferred_state": {
                "training_health": {
                    "state": "inferred",
                    "label": "recovering" if diag.get("guard_event") != "stable" else "stable",
                }
            },
            "planned": [
                "optional NAS HTTP export",
                "shared schema validation",
                "structured lineage bundles",
            ],
        })
        return payload


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

class EvolutionTrainer:
    def __init__(self, cfg: Dict[str, Any], logger: logging.Logger):
        self.cfg = cfg
        self.logger = logger
        self.device = torch.device(cfg["device"])
        self.monitor = SystemMonitor()
        self.guard = GradientBlackholeGuard(cfg)
        self.tachyon = TachyonField(cfg["tachyon_lead_factor"])
        self.ema = RollingEMA(cfg["ema_alpha"])
        self.exporter = NASShadowExporter(cfg)
        self.registry_builder = QuantumRegistryBuilder(cfg)

        self.model = ByteTransformer(cfg).to(self.device)
        self.optimizer = optim.AdamW(
            self.model.parameters(),
            lr=cfg["lr"],
            weight_decay=cfg["weight_decay"],
        )

        self.train_data: Optional[torch.Tensor] = None
        self.val_data: Optional[torch.Tensor] = None
        self.corpus_meta: Dict[str, Any] = {}
        self.current_cycle = 0
        self.best_val = float("inf")

        self.save_dir = Path(cfg["save_dir"])
        self.logs_dir = Path(cfg["logs_dir"])
        self.exports_dir = Path(cfg["exports_dir"])
        self.registry_dir = Path(cfg["registry_dir"])
        self.history_path = self.logs_dir / cfg["history_jsonl"]
        self.event_path = self.logs_dir / cfg["event_jsonl"]

    def checkpoint_path(self) -> Path:
        return self.save_dir / "checkpoint_latest.pt"

    def load_real_corpus(self) -> None:
        roots = [Path(x) for x in self.cfg["code_roots"]]
        corpus, meta = load_code_corpus(
            roots=roots,
            extensions=self.cfg["file_extensions"],
            max_files=self.cfg["max_files"],
            max_file_bytes=self.cfg["max_file_bytes"],
        )
        if len(corpus) < self.cfg["min_corpus_bytes"]:
            raise RuntimeError(f"Corpus too small: {len(corpus)} bytes from {meta}")
        split = int(len(corpus) * (1.0 - self.cfg["val_ratio"]))
        split = max(self.cfg["block_size"] + 2, split)
        train_bytes = corpus[:split]
        val_bytes = corpus[split:]
        if len(val_bytes) < self.cfg["block_size"] + 2:
            val_bytes = corpus[max(0, len(corpus) - max(self.cfg["block_size"] * 8, 4096)):]
        self.train_data = torch.tensor(list(train_bytes), dtype=torch.long)
        self.val_data = torch.tensor(list(val_bytes), dtype=torch.long)
        self.corpus_meta = {
            **meta,
            "train_bytes": int(len(train_bytes)),
            "val_bytes": int(len(val_bytes)),
        }
        self.logger.info(
            "Corpus loaded: files=%s | bytes=%s | train=%s | val=%s",
            meta["files"], meta["bytes"], len(train_bytes), len(val_bytes)
        )

    def save_checkpoint(self) -> None:
        self.save_dir.mkdir(parents=True, exist_ok=True)
        torch.save({
            "cycle": self.current_cycle,
            "best_val": self.best_val,
            "model_state": self.model.state_dict(),
            "optimizer_state": self.optimizer.state_dict(),
            "corpus_meta": self.corpus_meta,
        }, self.checkpoint_path())

    def try_resume(self) -> None:
        path = self.checkpoint_path()
        if not path.exists():
            return
        try:
            cp = torch.load(path, map_location="cpu")
            self.model.load_state_dict(cp["model_state"], strict=True)
            self.optimizer.load_state_dict(cp["optimizer_state"])
            self.current_cycle = int(cp.get("cycle", 0))
            self.best_val = float(cp.get("best_val", self.best_val))
            self.corpus_meta = dict(cp.get("corpus_meta", {}))
            self.logger.info("Auto-resumed from %s", path)
        except Exception as exc:
            self.logger.warning("Resume skipped: %s", exc)

    def get_batch(self, split: str) -> Tuple[torch.Tensor, torch.Tensor]:
        data = self.train_data if split == "train" else self.val_data
        if data is None:
            raise RuntimeError("Corpus not loaded")
        ix = torch.randint(len(data) - self.cfg["block_size"] - 1, (self.cfg["batch_size"],))
        x = torch.stack([data[i:i + self.cfg["block_size"]] for i in ix]).to(self.device)
        y = torch.stack([data[i + 1:i + 1 + self.cfg["block_size"]] for i in ix]).to(self.device)
        return x, y

    @torch.no_grad()
    def estimate_loss(self) -> Dict[str, float]:
        self.model.eval()
        out: Dict[str, float] = {}
        for split in ("train", "val"):
            losses = []
            for _ in range(int(self.cfg["eval_batches"])):
                xb, yb = self.get_batch(split)
                logits = self.model(xb)
                loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), yb.reshape(-1))
                losses.append(float(loss.item()))
            out[split] = float(sum(losses) / max(1, len(losses)))
        self.model.train()
        return out

    def build_diagnostics(self, losses: Dict[str, float], monitor: Dict[str, float], grad_diag: Dict[str, Any], tachyon_diag: Dict[str, Any]) -> Dict[str, Any]:
        event_seed = {
            "cycle": self.current_cycle,
            "train": losses["train"],
            "val": losses["val"],
            "best": self.best_val,
        }
        event_id = sha1_json(event_seed)
        dedupe_key = hashlib.sha1(f"{event_id}:{self.current_cycle}".encode("utf-8")).hexdigest()
        return {
            "event_id": event_id,
            "dedupe_key": dedupe_key,
            "search_mode": "TRAIN",
            "mode_label": "stable" if grad_diag["event"] == "stable" else "protected",
            "model_config": self.exporter.model_config(),
            "swarm_success_rate": None,
            "lineage": {
                "cycle": self.current_cycle,
                "checkpoint": self.checkpoint_path().as_posix(),
            },
            "graph_hint": {
                "kind": "training_cycle",
                "cycle": self.current_cycle,
                "best_val": self.best_val,
                "event": grad_diag["event"],
            },
            "thought_hint": {
                "summary": "Cycle completed",
                "train_loss": losses["train"],
                "val_loss": losses["val"],
            },
            "experience_hints": {
                "monitor": monitor,
                "grad": grad_diag,
                "tachyon": tachyon_diag,
            },
            "titan_hints": {
                "monitor": monitor,
                "device": self.cfg["device"],
            },
            "memory_contract": {
                "registry_kind": "janus_quantum_json",
                "state_labels": ["observed", "inferred", "planned"],
            },
            "import_contract": {
                "http_format": "janus_import_canonical_v1",
                "smb_format": "janus_import_smb_quant_v1",
            },
            "transfer_manifest": {
                "export_modes": ["http", "smb_inbox"],
                "quant_mode": self.cfg["quantize_mode"],
            },
            "janus_context": {
                "runtime": "JGPT_CODEX.py",
                "device_id": self.cfg["nas_http_device_id"],
                "cycle": self.current_cycle,
            },
        }

    def maybe_export(self, diagnostics: Dict[str, Any]) -> None:
        state_dict = self.model.state_dict()
        http_payload = self.exporter.build_http_payload(state_dict, self.current_cycle, self.best_val, diagnostics)
        smb_payload = self.exporter.build_smb_payload(state_dict, self.current_cycle, self.best_val, diagnostics)
        atomic_json_write(self.exports_dir / f"http_export_cycle_{self.current_cycle}.json", http_payload)
        atomic_json_write(self.exports_dir / f"smb_export_cycle_{self.current_cycle}.json", smb_payload)

        if self.cfg["nas_http_enabled"] and requests is not None:
            try:
                response = requests.post(
                    self.cfg["nas_http_import_url"],
                    json=http_payload,
                    timeout=float(self.cfg["nas_http_timeout"]),
                )
                append_jsonl(self.event_path, {
                    "ts": utc_now_z(),
                    "event": "http_export",
                    "cycle": self.current_cycle,
                    "status_code": getattr(response, "status_code", None),
                })
            except Exception as exc:
                append_jsonl(self.event_path, {
                    "ts": utc_now_z(),
                    "event": "http_export_error",
                    "cycle": self.current_cycle,
                    "error": str(exc),
                })

    def maybe_write_registry(self, diag: Dict[str, Any]) -> None:
        if not self.cfg["write_registry_every_cycle"]:
            return
        registry = self.registry_builder.build(self, diag)
        atomic_json_write(self.registry_dir / f"registry_cycle_{self.current_cycle}.json", registry)

    def train_cycle(self) -> Dict[str, Any]:
        self.model.train()
        last_loss = None

        for _ in range(int(self.cfg["train_steps_per_cycle"])):
            xb, yb = self.get_batch("train")
            logits = self.model(xb)
            loss = F.cross_entropy(logits.reshape(-1, logits.size(-1)), yb.reshape(-1))
            self.optimizer.zero_grad(set_to_none=True)
            loss.backward()

            raw_grad_diag = self.guard.inspect(self.model)
            guard_diag = self.guard.apply(self.model, raw_grad_diag, self.optimizer)
            self.optimizer.step()

            last_loss = float(loss.item())

        losses = self.estimate_loss()
        losses["train_step_last"] = float(last_loss if last_loss is not None else losses["train"])
        monitor = self.monitor.snapshot()

        score = -losses["val"]
        tachyon_diag = self.tachyon.update(score)
        ema_val = self.ema.update(losses["val"])

        if losses["val"] < self.best_val:
            self.best_val = float(losses["val"])

        diag = {
            "train_loss": losses["train"],
            "val_loss": losses["val"],
            "ema_val": ema_val,
            "monitor": monitor,
            "grad": {**raw_grad_diag, **guard_diag},
            "tachyon": tachyon_diag,
            "guard_event": guard_diag["event"],
        }

        diagnostics = self.build_diagnostics(losses, monitor, {**raw_grad_diag, **guard_diag}, tachyon_diag)
        self.maybe_export(diagnostics)
        self.maybe_write_registry(diag)

        append_jsonl(self.history_path, {
            "ts": utc_now_z(),
            "cycle": self.current_cycle,
            "train_loss": losses["train"],
            "val_loss": losses["val"],
            "ema_val": ema_val,
            "best_val": self.best_val,
            "monitor": monitor,
            "grad": {**raw_grad_diag, **guard_diag},
            "tachyon": tachyon_diag,
        })
        return diag

    def fit(self, cycles: int) -> None:
        self.load_real_corpus()
        self.try_resume()
        target_last = self.current_cycle + int(cycles)

        for cycle in range(self.current_cycle + 1, target_last + 1):
            self.current_cycle = cycle
            diag = self.train_cycle()
            self.logger.info(
                "Cycle %4d | train=%.4f | val=%.4f | ema=%.4f | best=%.4f | grad=%s | CPU=%.0f%% RAM=%.0f%%",
                cycle,
                diag["train_loss"],
                diag["val_loss"],
                diag["ema_val"],
                self.best_val,
                diag["guard_event"],
                diag["monitor"]["cpu_percent"],
                diag["monitor"]["ram_percent"],
            )
            if cycle % int(self.cfg["checkpoint_every"]) == 0:
                self.save_checkpoint()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="JGPT CODEX - GitHub-ready JANUS trainer/exporter")
    parser.add_argument("--save-dir", type=str, default="./jgpt_codex_runtime")
    parser.add_argument("--code-roots", type=str, nargs="*", default=["."])
    parser.add_argument("--cycles", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--train-steps-per-cycle", type=int, default=None)
    parser.add_argument("--device", type=str, default=None)
    args = parser.parse_args()

    cfg = build_config_from_args(args)
    save_dir = Path(cfg["save_dir"])
    logs_dir = Path(cfg["logs_dir"])
    exports_dir = Path(cfg["exports_dir"])
    registry_dir = Path(cfg["registry_dir"])

    save_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    exports_dir.mkdir(parents=True, exist_ok=True)
    registry_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(logs_dir / "trainer.log")
    set_seed(int(cfg["seed"]))
    trainer = EvolutionTrainer(cfg, logger)
    trainer.fit(int(cfg["cycles"]))


if __name__ == "__main__":
    main()
