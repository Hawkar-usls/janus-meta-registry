#!/usr/bin/env python3
"""Discovery-only Fallout 3 .fos differential scanner for the SAVE JAMES line.

This is intentionally NOT a Fallout 3 savegame parser. It searches raw immutable
save bytes for exact known FormID byte patterns and produces candidates for a
later format-aware structured decoder. A hit must never be promoted to a
structured reference, ChangeForm, memory payload, or carrier binding by itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Dict, List

ANCHORS: Dict[str, int] = {
    "MQ04": 0x00014E8A,
    "MQ04Script": 0x000254C9,
    "MQDadRef": 0x00019D09,
    "MQDad": 0x00019CEF,
    "MQ04Doc": 0x0004E79C,
    "MQ04DocRef": 0x0006023C,
    "Vault112PodTermDad_BASE": 0x00031190,
    "Vault112PodTermDad_REF": 0x000B3645,
    "MQ04DadPod": 0x000B3644,
    "MQ04DadPodShellRef": 0x000B3654,
    "MQ04DadExitTLMarker": 0x0002A45A,
    "MQ04PlayerContainerRef_NEGATIVE_CONTROL": 0x0004C253,
    "MQ04PlayerContainer_NEGATIVE_CONTROL": 0x0004C254,
    "MQ04VersionControlCurrent": 0x000C339E,
    "BettyScript": 0x0007DC71,
}

TIMEPOINTS = ("T0", "T1", "T2", "T3")
WINDOW = 32
MAX_OFFSETS_PER_PATTERN = 256


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def find_all(data: bytes, needle: bytes, limit: int = MAX_OFFSETS_PER_PATTERN) -> List[int]:
    out: List[int] = []
    start = 0
    while len(out) < limit:
        idx = data.find(needle, start)
        if idx < 0:
            break
        out.append(idx)
        start = idx + 1
    return out


def context_digest(data: bytes, offset: int, needle_len: int) -> str:
    a = max(0, offset - WINDOW)
    b = min(len(data), offset + needle_len + WINDOW)
    return sha256_bytes(data[a:b])


def scan_one(path: Path) -> dict:
    data = path.read_bytes()
    patterns = {}
    for label, formid in ANCHORS.items():
        encodings = {
            "u32_little_endian": formid.to_bytes(4, "little"),
            "u32_big_endian": formid.to_bytes(4, "big"),
        }
        enc_results = {}
        for enc_name, needle in encodings.items():
            offsets = find_all(data, needle)
            enc_results[enc_name] = {
                "count": len(offsets),
                "offsets": offsets,
                "context_sha256": [context_digest(data, x, len(needle)) for x in offsets],
                "truncated": len(offsets) >= MAX_OFFSETS_PER_PATTERN,
            }
        patterns[label] = {
            "form_id": f"{formid:08X}",
            "encodings": enc_results,
            "classification": "RAW_BYTE_CANDIDATE_ONLY",
        }
    return {
        "path_name": path.name,
        "size_bytes": len(data),
        "sha256": sha256_bytes(data),
        "patterns": patterns,
    }


def summarize_timeline(scans: Dict[str, dict]) -> dict:
    out = {}
    for label in ANCHORS:
        counts = {}
        for tp in TIMEPOINTS:
            p = scans[tp]["patterns"][label]["encodings"]
            counts[tp] = p["u32_little_endian"]["count"] + p["u32_big_endian"]["count"]
        out[label] = {
            "raw_hit_counts": counts,
            "appears_after_T0": counts["T0"] == 0 and any(counts[x] > 0 for x in ("T1", "T2", "T3")),
            "present_T1_and_T2": counts["T1"] > 0 and counts["T2"] > 0,
            "raw_presence_survives_T3": counts["T3"] > 0,
            "classification": "HEURISTIC_TIMELINE_ONLY_NOT_STRUCTURED_PERSISTENCE",
        }
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    for tp in TIMEPOINTS:
        p.add_argument(f"--{tp.lower()}", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    paths = {tp: getattr(args, tp.lower()) for tp in TIMEPOINTS}
    for tp, path in paths.items():
        if not path.is_file():
            raise SystemExit(f"{tp} missing: {path}")
    scans = {tp: scan_one(path) for tp, path in paths.items()}
    result = {
        "schema": "janus.fo3_fos_james_state_diff.discovery.v0_1",
        "authority": "DISCOVERY_ONLY",
        "warning": "RAW BYTE HITS ARE NOT STRUCTURED SAVE REFERENCES, CHANGEFORMS, MEMORY PAYLOADS, OR CARRIER BINDINGS.",
        "timepoints": scans,
        "timeline": summarize_timeline(scans),
        "next_required_stage": "FORMAT_AWARE_FALLOUT3_FOS_STRUCTURED_DECODER",
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
