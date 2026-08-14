#!/usr/bin/env python3
"""Decode the source-bound prefix of MQDadRef's real FO3 ACHR payload.

Authority boundary:
- xEdit/TES5Edit FO3 runtime save definitions provide the ACHR/MobileObject/
  Changed Extra field order and actor Changed-Extra flag mask.
- fallout-xbox-360-utils independently confirms pipe-terminated SaveData fields,
  VSVal encoding, and ExtraDataList framing.
- Extra type 0x0D has matching binary grammar in both sources but different
  human labels (xEdit: Script-style structure; independent decoder: ActivateRef).
  This tool therefore uses the neutral name EXTRA_0D_SCRIPT_ACTIVATE_REF_CLASS.

This is runtime actor-state decoding only. Nothing decoded here is admitted as
James autobiographical memory or Braun memory serialization.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import struct
from pathlib import Path
from typing import Any, Dict, List, Tuple

TARGET_FORMID = 0x00019D09
PIPE = 0x7C
EXPECTED_FLAGS = 0x80000000
EXPECTED_CHANGE_TYPE = 1
EXPECTED_VERSION = 21


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


class Reader:
    def __init__(self, data: bytes, parser: Any, formids: List[int]):
        self.data = data
        self.pos = 0
        self.parser = parser
        self.formids = formids

    def _need(self, n: int, label: str) -> None:
        if self.pos + n > len(self.data):
            raise ProbeError(f"{label}: need {n} bytes at {self.pos}, only {len(self.data)-self.pos} remain")

    def _pipe(self, label: str) -> None:
        self._need(1, f"{label} pipe")
        if self.data[self.pos] != PIPE:
            raise ProbeError(f"{label}: expected pipe 0x7C at {self.pos}, got 0x{self.data[self.pos]:02X}")
        self.pos += 1

    def u8t(self, label: str) -> int:
        self._need(1, label)
        value = self.data[self.pos]
        self.pos += 1
        self._pipe(label)
        return value

    def i8t(self, label: str) -> int:
        value = self.u8t(label)
        return value - 256 if value >= 128 else value

    def u32t(self, label: str) -> int:
        self._need(4, label)
        value = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        self._pipe(label)
        return value

    def f32t(self, label: str) -> float:
        self._need(4, label)
        value = struct.unpack_from("<f", self.data, self.pos)[0]
        self.pos += 4
        self._pipe(label)
        return value

    def f64t(self, label: str) -> float:
        self._need(8, label)
        value = struct.unpack_from("<d", self.data, self.pos)[0]
        self.pos += 8
        self._pipe(label)
        return value

    def bytes_t(self, label: str, n: int) -> str:
        self._need(n, label)
        value = self.data[self.pos:self.pos+n]
        self.pos += n
        self._pipe(label)
        return value.hex()

    def vsvalt(self, label: str) -> Dict[str, Any]:
        self._need(1, label)
        start = self.pos
        first = self.data[self.pos]
        tag = first & 0x03
        width = 1 if tag == 0 else 2 if tag == 1 else 4
        self._need(width, label)
        raw_bytes = self.data[self.pos:self.pos+width]
        raw = int.from_bytes(raw_bytes, "little")
        self.pos += width
        self._pipe(label)
        return {
            "value": raw >> 2,
            "width": width,
            "tag": tag,
            "raw_hex": raw_bytes.hex(),
            "offset": start,
        }

    def refidt(self, label: str) -> Dict[str, Any]:
        self._need(3, label)
        start = self.pos
        raw3 = self.data[self.pos:self.pos+3]
        self.pos += 3
        self._pipe(label)
        save_ref = self.parser.read_save_refid(raw3)
        resolved = self.parser.resolve_save_refid(save_ref, self.formids)
        return {
            "label": label,
            "offset": start,
            "save_refid": save_ref,
            "resolved_formid_hex": None if resolved is None else f"0x{resolved:08X}",
        }


def decode_extra_0d(r: Reader) -> Dict[str, Any]:
    start = r.pos
    linked_ref = r.refidt("EXTRA_0D_PRIMARY_REF")
    var_count = r.vsvalt("EXTRA_0D_SCRIPT_VAR_COUNT")
    variables = []
    for i in range(var_count["value"]):
        flag_and_var_id = r.u32t(f"EXTRA_0D_VAR_{i}_FLAG_AND_VAR_ID")
        if flag_and_var_id & 0x80000000:
            value: Any = r.refidt(f"EXTRA_0D_VAR_{i}_REF")
            value_class = "REFID"
        else:
            value = r.f64t(f"EXTRA_0D_VAR_{i}_DOUBLE")
            value_class = "DOUBLE"
        variables.append({
            "index": i,
            "flag_and_var_id_hex": f"0x{flag_and_var_id:08X}",
            "value_class": value_class,
            "value": value,
        })
    has_event = r.u8t("EXTRA_0D_HAS_EVENT_DATA")
    event_hex = r.bytes_t("EXTRA_0D_EVENT_DATA", 8) if has_event else None
    script_flag = r.u8t("EXTRA_0D_SCRIPT_FLAG")
    return {
        "neutral_name": "EXTRA_0D_SCRIPT_ACTIVATE_REF_CLASS",
        "source_label_disagreement": {
            "xedit": "Script-style Extra structure",
            "independent_decoder": "ActivateRef",
            "policy": "BINARY_GRAMMAR_ADMITTED_HUMAN_LABEL_NOT_CANONICALIZED",
        },
        "primary_ref": linked_ref,
        "script_var_count": var_count,
        "variables": variables,
        "has_event_data": has_event,
        "event_data_hex": event_hex,
        "script_flag": script_flag,
        "decoded_size_bytes": r.pos - start,
    }


def decode_source_bound_prefix(payload: bytes, parser: Any, formids: List[int]) -> Dict[str, Any]:
    r = Reader(payload, parser, formids)
    process_level = r.i8t("PROCESS_LEVEL")
    extra_count = r.vsvalt("ACTOR_EXTRA_COUNT")
    extras = []
    for index in range(extra_count["value"]):
        entry_start = r.pos
        extra_type = r.u8t(f"EXTRA_{index}_TYPE")
        if extra_type != 0x0D:
            raise ProbeError(
                f"source-bound decoder admits only observed Extra Type 0x0D, got 0x{extra_type:02X}"
            )
        decoded = decode_extra_0d(r)
        decoded.update({
            "index": index,
            "extra_type_hex": f"0x{extra_type:02X}",
            "entry_offset": entry_start,
            "entry_size_bytes": r.pos - entry_start,
        })
        extras.append(decoded)

    mobile_specs: Tuple[Tuple[str, str], ...] = (
        ("Byt084", "i8"), ("Byt085", "i8"), ("Byt07C", "i8"), ("Byt07F", "i8"),
        ("Byt080", "i8"), ("Byt07D", "i8"), ("Byt07E", "i8"), ("Byt086", "i8"),
        ("Unk074", "u32"), ("Unk078", "u32"), ("Byt081", "i8"), ("Byt083", "u8"),
    )
    mobile: Dict[str, Any] = {}
    for name, kind in mobile_specs:
        if kind == "i8":
            mobile[name] = r.i8t(f"MOBILE_{name}")
        elif kind == "u8":
            mobile[name] = r.u8t(f"MOBILE_{name}")
        else:
            mobile[name] = r.u32t(f"MOBILE_{name}")
    mobile["Unk06C"] = r.refidt("MOBILE_Unk06C")
    mobile["Unk070"] = r.refidt("MOBILE_Unk070")

    return {
        "decoded_prefix_size_bytes": r.pos,
        "remaining_opaque_bytes": len(payload) - r.pos,
        "process_level": process_level,
        "process_level_class": {
            -1: "NONE", 0: "HIGH", 1: "MIDDLE_HIGH", 2: "MIDDLE_LOW", 3: "LOW", 4: "BASE"
        }.get(process_level, "UNKNOWN"),
        "extra_count": extra_count,
        "extras": extras,
        "mobile_object_post_refr_fields": mobile,
        "next_layer": "PROCESS_STATE_THEN_ACTOR_UNCONDITIONAL_FIELDS",
    }


def probe(path: Path, parser: Any) -> dict:
    data = path.read_bytes()
    parsed = parser.parse_file(path)
    records = parsed["structural_body"]["changed_forms"]["header_index"]
    target = [r for r in records if r["resolved_formid_hex"] == f"0x{TARGET_FORMID:08X}"]
    if len(target) != 1:
        raise ProbeError(f"{path.name}: expected exactly one MQDadRef record, got {len(target)}")
    rec = target[0]
    if int(rec["change_flags_hex"], 16) != EXPECTED_FLAGS:
        raise ProbeError(f"{path.name}: unexpected MQDadRef flags {rec['change_flags_hex']}")
    if rec["change_type"] != EXPECTED_CHANGE_TYPE or rec["version"] != EXPECTED_VERSION:
        raise ProbeError(f"{path.name}: unexpected MQDadRef type/version")

    start = rec["payload_offset"]
    end = start + rec["data_length"]
    payload = data[start:end]
    flt = parsed["structural_body"]["file_location_table"]
    formids, _ = parser.parse_formid_array(data, flt["refid_array_count_offset"])
    decoded = decode_source_bound_prefix(payload, parser, formids)

    return {
        "file_name": path.name,
        "file_sha256": parsed["sha256"],
        "header_location": parsed["header_and_plugins"]["location"],
        "plugin_manifest_sha256": parsed["header_and_plugins"]["ordered_plugin_manifest_sha256"],
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
        "source_bound_prefix": decoded,
        "payload_prefix_96_hex": payload[:96].hex(),
        "claim_ceiling": {
            "vsval_framing_admitted": True,
            "changed_extra_framing_admitted": True,
            "extra_type_sequence_admitted": True,
            "extra_0d_binary_grammar_admitted": True,
            "extra_0d_human_label_canonicalized": False,
            "mobile_object_prefix_fields_admitted": True,
            "full_actor_payload_decoded": False,
            "autobiographical_memory_semantics_admitted": False,
        },
    }


def fingerprint_value(value: Any) -> Any:
    if isinstance(value, dict):
        if "resolved_formid_hex" in value and "save_refid" in value:
            return value["resolved_formid_hex"]
        return {k: fingerprint_value(v) for k, v in value.items() if k not in {"offset", "raw_hex"}}
    if isinstance(value, list):
        return [fingerprint_value(v) for v in value]
    return value


def cross_fixture_baseline(fixtures: List[dict]) -> dict:
    prefixes = [f["source_bound_prefix"] for f in fixtures]
    semantic = [fingerprint_value(p) for p in prefixes]

    mobile_names = list(prefixes[0]["mobile_object_post_refr_fields"].keys())
    stable_mobile: Dict[str, Any] = {}
    variable_mobile: Dict[str, List[Any]] = {}
    for field in mobile_names:
        vals = [fingerprint_value(p["mobile_object_post_refr_fields"][field]) for p in prefixes]
        if vals.count(vals[0]) == len(vals):
            stable_mobile[field] = vals[0]
        else:
            variable_mobile[field] = vals

    extra_refs = [
        p["extras"][0]["primary_ref"]["resolved_formid_hex"]
        if p["extras"] else None
        for p in prefixes
    ]
    return {
        "fixture_count": len(fixtures),
        "all_process_levels": [p["process_level"] for p in prefixes],
        "all_extra_counts": [p["extra_count"]["value"] for p in prefixes],
        "all_extra_type_sequences": [
            [e["extra_type_hex"] for e in p["extras"]] for p in prefixes
        ],
        "extra_0d_resolved_primary_refs": extra_refs,
        "extra_0d_resolved_primary_ref_stable": len(set(extra_refs)) == 1,
        "stable_mobile_fields": stable_mobile,
        "variable_mobile_fields": variable_mobile,
        "decoded_prefix_semantically_identical": semantic.count(semantic[0]) == len(semantic),
        "interpretation": "Decoded runtime fields that vary across Vault 101 external controls are nonspecific baseline variability. Stable fields are baseline structure, not James-memory evidence.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture-dir", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    parser = _load_structural_parser()
    files = [args.fixture_dir / f"fallout3_{i}.fos" for i in (1, 2, 3)]
    fixtures = [probe(path, parser) for path in files]
    result = {
        "schema": "janus.fo3_fos_achr_changed_extra_probe.v0_2",
        "authority": "REAL_EXTERNAL_ACHR_SOURCE_BOUND_PREFIX_DECODER",
        "sources": {
            "xedit": "TES5Edit/TES5Edit@93cc0bc5a1251936c3c7859eee3150eda12a62d7 Core/wbDefinitionsFO3Saves.pas",
            "independent_crosscheck": "slfx77/fallout-xbox-360-utils@f3e3793224e84947d91916c09895c253ab5d874f FormDataReader.cs + ExtraDataDecoder.cs + ExtraDataTypeHandlers.cs + ActorDecoder.cs",
        },
        "fixtures": fixtures,
        "cross_fixture_baseline": cross_fixture_baseline(fixtures),
        "hard_rules": [
            "EXTERNAL_VAULT101_FIXTURE != JAMES_T1_T2_T3_LINEAGE",
            "EXTRA_0D_RUNTIME_STRUCTURE != AUTOBIOGRAPHICAL_MEMORY",
            "SAVE_LOCAL_REFID_INDEX_DIFFERENCE != AUTHORED_FORMID_DIFFERENCE",
            "RUNTIME_FIELD_VARIABILITY != TRANQUILITY_LANE_EVENT",
            "ENGINE_SAVE_STATE != IN_WORLD_MEMORY_CARRIER",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
