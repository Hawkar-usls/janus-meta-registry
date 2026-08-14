#!/usr/bin/env python3
"""Fallout 3 .fos File Location Table / Changed Form header indexer.

Authority boundary:
- FO3 File Location Table and Changed Form header grammar follow the
  xEdit/TES5Edit Fallout 3 runtime save definition.
- Save RefID encoding/resolution is cross-checked against an independent
  Fallout 3/New Vegas save parser implementation.
- Changed Form payload bytes remain opaque. This tool does not infer
  autobiographical memory, Braun memory serialization, or carrier semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TIMEPOINTS = ("T0", "T1", "T2", "T3")
FLT_SIZE = 0x6E
FLT_RESERVED_SIZE = FLT_SIZE - 9 * 4
MAX_CHANGED_FORMS = 1_000_000
MAX_FORMID_ARRAY = 1_000_000

TARGETS = {
    "MQ04": 0x00014E8A,
    "MQDadRef": 0x00019D09,
    "MQ04Doc_BASE": 0x0004E79C,
    "MQ04Doc_REF": 0x0006023C,
    "MQ04PlayerContainerRef_CONTROL": 0x0004C253,
    "MQ04DadPod": 0x000B3644,
    "Vault112PodTermDad_REF": 0x000B3645,
    "MQ04DadPodShellRef": 0x000B3654,
}


class ParseError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_header_module():
    path = Path(__file__).resolve().with_name("fo3_fos_header_plugin_manifest_v0_1.py")
    spec = importlib.util.spec_from_file_location("fo3_header_v01", path)
    if spec is None or spec.loader is None:
        raise ParseError(f"cannot load header authenticator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_file_location_table(data: bytes, offset: int) -> dict:
    if offset < 0 or offset + FLT_SIZE > len(data):
        raise ParseError(f"File Location Table at {offset} exceeds file size {len(data)}")
    values = struct.unpack_from("<9I", data, offset)
    names = (
        "refid_array_count_offset",
        "unknown_table_offset",
        "global_data_table_1_offset",
        "changed_forms_offset",
        "global_data_table_2_offset",
        "global_data_table_1_count",
        "global_data_table_2_count",
        "changed_forms_count",
        "unknown_count",
    )
    table = dict(zip(names, values))
    reserved = data[offset + 36: offset + FLT_SIZE]
    table.update({
        "offset": offset,
        "size_bytes": FLT_SIZE,
        "reserved_sha256": sha256_bytes(reserved),
        "reserved_all_zero": all(b == 0 for b in reserved),
    })

    for key in (
        "refid_array_count_offset",
        "unknown_table_offset",
        "global_data_table_1_offset",
        "changed_forms_offset",
        "global_data_table_2_offset",
    ):
        value = table[key]
        if value >= len(data):
            raise ParseError(f"{key}=0x{value:X} outside file size 0x{len(data):X}")

    g1 = table["global_data_table_1_offset"]
    cf = table["changed_forms_offset"]
    g2 = table["global_data_table_2_offset"]
    refs = table["refid_array_count_offset"]
    if not (offset + FLT_SIZE <= g1 < cf < g2 < refs):
        raise ParseError(
            "unsupported/invalid FO3 chapter ordering: expected "
            "FLT_END <= GDT1 < CHANGED_FORMS < GDT2 < REFID_ARRAY"
        )
    if table["changed_forms_count"] > MAX_CHANGED_FORMS:
        raise ParseError("changed_forms_count exceeds safety cap")
    return table


def parse_formid_array(data: bytes, offset: int) -> Tuple[List[int], int]:
    if offset < 0 or offset + 4 > len(data):
        raise ParseError("FormID array count offset outside file")
    count = struct.unpack_from("<I", data, offset)[0]
    if count > MAX_FORMID_ARRAY:
        raise ParseError("FormID array count exceeds safety cap")
    end = offset + 4 + count * 4
    if end > len(data):
        raise ParseError("FormID array extends beyond file")
    values = list(struct.unpack_from(f"<{count}I", data, offset + 4)) if count else []
    return values, end


def read_save_refid(raw3: bytes) -> dict:
    if len(raw3) != 3:
        raise ParseError("save RefID must be exactly 3 bytes")
    raw = (raw3[0] << 16) | (raw3[1] << 8) | raw3[2]
    ref_type = raw >> 22
    value = raw & 0x3FFFFF
    labels = {0: "FORMID_ARRAY", 1: "DEFAULT", 2: "CREATED", 3: "UNKNOWN"}
    return {
        "raw_hex": raw3.hex(),
        "raw_u24_hex": f"0x{raw:06X}",
        "type_code": ref_type,
        "type": labels[ref_type],
        "value": value,
    }


def resolve_save_refid(ref: dict, formids: List[int]) -> Optional[int]:
    ref_type = ref["type_code"]
    value = ref["value"]
    if ref_type == 0:
        if value == 0 or value > len(formids):
            return None
        return formids[value - 1]
    if ref_type == 1:
        return value
    if ref_type == 2:
        return 0xFF000000 | value
    return None


def _read_length(data: bytes, pos: int, length_code: int, limit: int) -> Tuple[int, int]:
    widths = {0: 1, 1: 2, 2: 4}
    if length_code not in widths:
        raise ParseError("Changed Form length code 3 is not admitted")
    width = widths[length_code]
    if pos + width > limit:
        raise ParseError("Changed Form length field crosses chapter boundary")
    if width == 1:
        return data[pos], pos + 1
    if width == 2:
        return struct.unpack_from("<H", data, pos)[0], pos + 2
    return struct.unpack_from("<I", data, pos)[0], pos + 4


def parse_changed_forms(
    data: bytes,
    offset: int,
    count: int,
    end_offset: int,
    formids: List[int],
) -> Tuple[List[dict], int]:
    if not (0 <= offset <= end_offset <= len(data)):
        raise ParseError("invalid Changed Forms chapter bounds")
    pos = offset
    records: List[dict] = []
    for index in range(count):
        start = pos
        if pos + 10 > end_offset:
            raise ParseError(f"Changed Form {index} header crosses chapter boundary")
        ref = read_save_refid(data[pos:pos + 3])
        pos += 3
        change_flags = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        raw_type = data[pos]
        pos += 1
        change_type = raw_type & 0x3F
        length_code = raw_type >> 6
        version = data[pos]
        pos += 1
        data_length, pos = _read_length(data, pos, length_code, end_offset)
        payload_start = pos
        payload_end = payload_start + data_length
        if payload_end > end_offset:
            raise ParseError(
                f"Changed Form {index} payload crosses Global Data Table 2 boundary"
            )
        payload = data[payload_start:payload_end]
        pos = payload_end
        resolved = resolve_save_refid(ref, formids)
        records.append({
            "index": index,
            "record_offset": start,
            "record_size_bytes": pos - start,
            "save_refid": ref,
            "resolved_formid_hex": None if resolved is None else f"0x{resolved:08X}",
            "change_flags_hex": f"0x{change_flags:08X}",
            "raw_type_hex": f"0x{raw_type:02X}",
            "change_type": change_type,
            "length_code": length_code,
            "version": version,
            "data_length": data_length,
            "payload_offset": payload_start,
            "payload_sha256": sha256_bytes(payload),
            "payload_semantics": "OPAQUE_NOT_DECODED_BY_THIS_TOOL",
        })
    return records, pos


def target_matches(records: List[dict]) -> Dict[str, list]:
    by_formid: Dict[int, List[dict]] = {}
    for rec in records:
        text = rec["resolved_formid_hex"]
        if text is not None:
            by_formid.setdefault(int(text, 16), []).append(rec)
    out: Dict[str, list] = {}
    for name, formid in TARGETS.items():
        matches = by_formid.get(formid, [])
        out[name] = [{
            "changed_form_index": rec["index"],
            "record_offset": rec["record_offset"],
            "change_flags_hex": rec["change_flags_hex"],
            "change_type": rec["change_type"],
            "version": rec["version"],
            "data_length": rec["data_length"],
            "payload_sha256": rec["payload_sha256"],
        } for rec in matches]
    return out


def parse_structural_body(data: bytes, header: dict) -> dict:
    flt = parse_file_location_table(data, header["body_offset"])
    formids, formids_end = parse_formid_array(data, flt["refid_array_count_offset"])
    records, changed_end = parse_changed_forms(
        data,
        flt["changed_forms_offset"],
        flt["changed_forms_count"],
        flt["global_data_table_2_offset"],
        formids,
    )
    return {
        "file_location_table": flt,
        "formid_array": {
            "count": len(formids),
            "offset": flt["refid_array_count_offset"],
            "end_offset": formids_end,
            "sha256": sha256_bytes(b"".join(struct.pack("<I", value) for value in formids)),
        },
        "changed_forms": {
            "count_declared": flt["changed_forms_count"],
            "count_indexed": len(records),
            "offset": flt["changed_forms_offset"],
            "parsed_end_offset": changed_end,
            "next_chapter_offset": flt["global_data_table_2_offset"],
            "exact_next_chapter_boundary_match": changed_end == flt["global_data_table_2_offset"],
            "header_index": records,
            "target_matches": target_matches(records),
        },
        "structured_change_region_established": True,
        "changed_form_payload_semantics_established": False,
        "james_autobiographical_payload_established": False,
    }


def parse_file(path: Path) -> dict:
    header_mod = _load_header_module()
    data = path.read_bytes()
    header = header_mod.parse_fo3_header_and_plugins(data)
    body = parse_structural_body(data, header)
    return {
        "file_name": path.name,
        "size_bytes": len(data),
        "sha256": sha256_bytes(data),
        "header_and_plugins": header,
        "structural_body": body,
    }


def compare_timepoints(results: Dict[str, dict]) -> dict:
    manifests = {
        tp: results[tp]["header_and_plugins"]["ordered_plugin_manifest_sha256"]
        for tp in TIMEPOINTS
    }
    plugin_match = len(set(manifests.values())) == 1
    lifecycle = {}
    for target in TARGETS:
        lifecycle[target] = {}
        for tp in TIMEPOINTS:
            matches = results[tp]["structural_body"]["changed_forms"]["target_matches"][target]
            lifecycle[target][tp] = {
                "present": bool(matches),
                "count": len(matches),
                "matches": matches,
            }
    return {
        "plugin_environment_exact_match": plugin_match,
        "targets": lifecycle,
        "runtime_state_claim_authority": (
            "STRUCTURED_CHANGED_FORM_PRESENCE_AND_HEADER_DIFFERENTIAL_ONLY"
            if plugin_match
            else "BLOCKED_PLUGIN_ENVIRONMENT_MISMATCH"
        ),
        "non_implications": [
            "CHANGED_FORM_PRESENCE_DOES_NOT_EQUAL_AUTOBIOGRAPHICAL_MEMORY",
            "PERSISTENCE_ACROSS_T2_T3_DOES_NOT_EQUAL_BRAUN_MEMORY_SERIALIZATION",
            "ENGINE_SAVE_STATE_DOES_NOT_EQUAL_IN_WORLD_MEMORY_CARRIER",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    for tp in TIMEPOINTS:
        parser.add_argument(f"--{tp.lower()}", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = {}
    for tp in TIMEPOINTS:
        path = getattr(args, tp.lower())
        if not path.is_file():
            raise SystemExit(f"{tp} missing: {path}")
        try:
            results[tp] = parse_file(path)
        except Exception as exc:
            raise SystemExit(f"{tp} structural parse failed: {exc}") from exc

    output = {
        "schema": "janus.fo3_fos_changed_form_header_index.v0_1",
        "authority": "FO3_STRUCTURAL_RUNTIME_STATE_INDEX_ONLY",
        "sources": {
            "primary_layout": "TES5Edit/TES5Edit Core/wbDefinitionsFO3Saves.pas",
            "refid_crosscheck": "slfx77/fallout-xbox-360-utils SaveRefId.cs",
        },
        "timepoints": results,
        "cross_timepoint": compare_timepoints(results),
        "changed_form_payload_decoder_established": False,
        "persisted_james_autobiographical_memory_established": False,
        "in_world_james_serialization_established": False,
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
