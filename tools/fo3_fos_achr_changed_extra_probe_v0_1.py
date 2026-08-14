#!/usr/bin/env python3
"""Probe real FO3 ACHR Changed Form payloads without assigning memory semantics.

The immediate target is MQDadRef (00019D09) in the pinned external Vortex saves.
This probe preserves selected payload bytes so the xEdit Changed Extra grammar can
be tested against real records. It is a discovery tool, not an autobiographical
memory decoder.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import struct
from pathlib import Path

TARGET_FORMID = 0x00019D09


class ProbeError(ValueError):
    pass


def _load_structural_parser():
    path = Path(__file__).resolve().with_name("fo3_fos_changed_form_header_index_v0_1.py")
    spec = importlib.util.spec_from_file_location("fo3_structural_v01", path)
    if spec is None or spec.loader is None:
        raise ProbeError(f"cannot load parser: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def vsval_low2_candidate(data: bytes, pos: int) -> dict:
    """Expose, but do not yet admit, the common low-2-bit variable-size candidate."""
    if pos >= len(data):
        return {"status": "OUT_OF_RANGE"}
    first = data[pos]
    code = first & 0x03
    width = (1, 2, 4, 4)[code]
    if pos + width > len(data):
        return {"status": "TRUNCATED", "code": code, "width": width}
    raw = int.from_bytes(data[pos:pos + width], "little")
    return {
        "status": "CANDIDATE_ONLY_NOT_ADMITTED",
        "code": code,
        "width": width,
        "raw_hex": data[pos:pos + width].hex(),
        "value_shift2": raw >> 2,
    }


def probe(path: Path, parser) -> dict:
    data = path.read_bytes()
    parsed = parser.parse_file(path)
    records = parsed["structural_body"]["changed_forms"]["header_index"]
    target = [r for r in records if r["resolved_formid_hex"] == f"0x{TARGET_FORMID:08X}"]
    if len(target) != 1:
        raise ProbeError(f"{path.name}: expected exactly one MQDadRef record, got {len(target)}")
    rec = target[0]
    start = rec["payload_offset"]
    end = start + rec["data_length"]
    payload = data[start:end]
    if len(payload) != rec["data_length"]:
        raise ProbeError("payload extraction length mismatch")
    if not payload:
        raise ProbeError("empty ACHR payload")

    process_level_signed = struct.unpack("b", payload[:1])[0]
    changed_extra_candidate_offset = 1
    candidate = payload[changed_extra_candidate_offset:]

    return {
        "file_name": path.name,
        "file_sha256": parsed["sha256"],
        "header_location": parsed["header_and_plugins"]["location"],
        "target": "MQDadRef",
        "formid_hex": f"0x{TARGET_FORMID:08X}",
        "record": {
            "change_flags_hex": rec["change_flags_hex"],
            "change_type": rec["change_type"],
            "version": rec["version"],
            "data_length": rec["data_length"],
            "payload_offset": start,
            "payload_sha256": rec["payload_sha256"],
        },
        "xedit_bound_prefix_interpretation": {
            "initial_data_expected": "NONE_FOR_NONCREATED_ACHR_WITH_ONLY_FLAG31",
            "change_type_1": "ACHR",
            "process_level_offset": 0,
            "process_level_signed": process_level_signed,
            "changed_extra_candidate_offset": changed_extra_candidate_offset,
            "basis": "wbChangedACHR -> wbChangedCharacter -> wbChangedActor -> wbChangedMobileObject(Process Level, wbChangedREFR); wbChangedREFR selects Changed Extra under actor mask when flag31 is set",
            "authority": "SOURCE_BOUND_LAYOUT_PREFIX_ONLY",
        },
        "candidate_bytes": {
            "payload_hex": payload.hex(),
            "payload_prefix_64_hex": payload[:64].hex(),
            "payload_suffix_64_hex": payload[-64:].hex(),
            "from_changed_extra_candidate_prefix_64_hex": candidate[:64].hex(),
            "u8_at_candidate": candidate[0] if candidate else None,
            "u16le_at_candidate": int.from_bytes(candidate[:2], "little") if len(candidate) >= 2 else None,
            "u32le_at_candidate": int.from_bytes(candidate[:4], "little") if len(candidate) >= 4 else None,
            "low2_variable_size_candidate": vsval_low2_candidate(payload, changed_extra_candidate_offset),
        },
        "claim_ceiling": {
            "changed_extra_framing_admitted": False,
            "extra_type_sequence_admitted": False,
            "actor_runtime_field_semantics_admitted": False,
            "autobiographical_memory_semantics_admitted": False,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture-dir", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    parser = _load_structural_parser()
    files = [args.fixture_dir / f"fallout3_{i}.fos" for i in (1, 2, 3)]
    result = {
        "schema": "janus.fo3_fos_achr_changed_extra_probe.v0_1",
        "authority": "REAL_EXTERNAL_ACHR_PAYLOAD_DISCOVERY_ONLY",
        "fixtures": [probe(path, parser) for path in files],
        "hard_rules": [
            "EXTRACTED_BYTES != DECODED_FIELDS",
            "CHANGED_EXTRA != AUTOBIOGRAPHICAL_MEMORY",
            "EXTERNAL_VAULT101_FIXTURE != JAMES_T1_T2_T3_LINEAGE",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
