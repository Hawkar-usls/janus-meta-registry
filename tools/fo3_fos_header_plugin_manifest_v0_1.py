#!/usr/bin/env python3
"""Fallout 3 .fos header/plugin manifest authenticator.

Scope is deliberately limited to the structure parsed by the Nexus-Mods/Vortex
Fallout 3 save metadata implementation. This tool does NOT decode the save body,
ChangeForms, quest state, actor state, memory payloads, or carrier bindings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Dict, List

MAGIC = b"FO3SAVEGAME"
FIELD_MARKER = 0x7C
EXPECTED_FILE_VERSION = 0x30
MAX_SCREENSHOT_DIM = 2000
MAX_PLUGIN_NAME = 256
TIMEPOINTS = ("T0", "T1", "T2", "T3")


class ParseError(ValueError):
    pass


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0
        self.field_markers = False

    def read(self, n: int) -> bytes:
        if n < 0 or self.offset + n > len(self.data):
            raise ParseError(f"unexpected EOF at {self.offset}, need {n} bytes")
        out = self.data[self.offset:self.offset + n]
        self.offset += n
        return out

    def skip(self, n: int) -> None:
        self.read(n)

    def seek(self, pos: int) -> None:
        if pos < 0 or pos > len(self.data):
            raise ParseError(f"invalid seek {pos}")
        self.offset = pos

    def marker(self) -> None:
        got = self.read(1)[0]
        if got != FIELD_MARKER:
            raise ParseError(
                f"expected field marker 0x7c at {self.offset - 1}, got 0x{got:02x}"
            )

    def u8(self) -> int:
        value = self.read(1)[0]
        if self.field_markers:
            self.marker()
        return value

    def u16(self) -> int:
        value = struct.unpack("<H", self.read(2))[0]
        if self.field_markers:
            self.marker()
        return value

    def u32(self) -> int:
        value = struct.unpack("<I", self.read(4))[0]
        if self.field_markers:
            self.marker()
        return value

    def i32(self) -> int:
        value = struct.unpack("<i", self.read(4))[0]
        if self.field_markers:
            self.marker()
        return value

    def string_bytes(self) -> bytes:
        length = self.u16()
        if length > 65535:
            raise ParseError("invalid string length")
        raw = self.read(length)
        if self.field_markers and length > 0:
            self.marker()
        return raw


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_text(raw: bytes) -> str:
    for encoding in ("utf-8", "cp1251", "latin1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin1", errors="replace")


def plugin_manifest_sha256(plugins: List[str]) -> str:
    canonical = "\n".join(plugins).encode("utf-8")
    return sha256_bytes(canonical)


def parse_fo3_header_and_plugins(data: bytes) -> dict:
    r = Reader(data)
    if r.read(len(MAGIC)) != MAGIC:
        raise ParseError("invalid magic: expected FO3SAVEGAME")

    save_header_size = struct.unpack("<I", r.read(4))[0]
    file_version = struct.unpack("<I", r.read(4))[0]
    if file_version != EXPECTED_FILE_VERSION:
        raise ParseError(
            f"unexpected Fallout 3 file version 0x{file_version:x}; expected 0x30"
        )

    delimiter = r.read(1)[0]

    # Mirror the Vortex FO3-vs-NV discriminator, but fail closed for anything
    # other than the four-byte FO3 field before the next '|'.
    discriminator_start = r.offset
    field_size = 0
    while True:
        if r.offset >= len(data):
            raise ParseError("EOF while finding FO3/NV discriminator marker")
        value = r.read(1)[0]
        if value == FIELD_MARKER:
            break
        field_size += 1
        if field_size > 16:
            raise ParseError("implausible FO3/NV discriminator field")
    if field_size != 4:
        raise ParseError(
            f"not strict Fallout 3 header: pre-marker field size is {field_size}, expected 4"
        )
    r.seek(discriminator_start)
    r.field_markers = True

    width = r.u32()
    height = r.u32()
    if width >= MAX_SCREENSHOT_DIM or height >= MAX_SCREENSHOT_DIM:
        raise ParseError(f"invalid screenshot dimensions {width}x{height}")

    save_number = r.u32()
    character_name_raw = r.string_bytes()
    unknown_string_raw = r.string_bytes()
    character_level = r.i32()
    location_raw = r.string_bytes()
    play_time_raw = r.string_bytes()

    screenshot_bytes = width * height * 3
    screenshot = r.read(screenshot_bytes)
    screenshot_sha256 = sha256_bytes(screenshot)

    plugin_preamble = r.read(5)
    plugin_count = r.u8()
    plugins: List[str] = []
    plugin_raw_sha256: List[str] = []
    for _ in range(plugin_count):
        raw = r.string_bytes()
        name = decode_text(raw)
        if len(name) > MAX_PLUGIN_NAME:
            raise ParseError(f"plugin name too long at offset {r.offset}")
        plugins.append(name)
        plugin_raw_sha256.append(sha256_bytes(raw))

    body_offset = r.offset
    return {
        "format": "FALLOUT_3_FOS_HEADER_PLUGIN_SCOPE",
        "magic": MAGIC.decode("ascii"),
        "save_header_size": save_header_size,
        "file_version_hex": f"0x{file_version:02X}",
        "initial_delimiter_hex": f"0x{delimiter:02X}",
        "fo3_nv_discriminator_field_size": field_size,
        "screenshot": {
            "width": width,
            "height": height,
            "rgb_byte_count": screenshot_bytes,
            "sha256": screenshot_sha256,
        },
        "save_number": save_number,
        "character_name": decode_text(character_name_raw),
        "character_name_raw_sha256": sha256_bytes(character_name_raw),
        "unknown_string_raw_sha256": sha256_bytes(unknown_string_raw),
        "character_level": character_level,
        "location": decode_text(location_raw),
        "location_raw_sha256": sha256_bytes(location_raw),
        "play_time": decode_text(play_time_raw),
        "plugin_preamble_hex": plugin_preamble.hex(),
        "plugin_count": plugin_count,
        "plugins": plugins,
        "plugin_raw_sha256": plugin_raw_sha256,
        "ordered_plugin_manifest_sha256": plugin_manifest_sha256(plugins),
        "body_offset": body_offset,
        "opaque_body_bytes_remaining": len(data) - body_offset,
        "body_semantics": "OPAQUE_NOT_DECODED_BY_THIS_TOOL",
    }


def parse_file(path: Path) -> dict:
    data = path.read_bytes()
    parsed = parse_fo3_header_and_plugins(data)
    return {
        "file_name": path.name,
        "size_bytes": len(data),
        "sha256": sha256_bytes(data),
        "header_and_plugins": parsed,
    }


def compare_timepoints(results: Dict[str, dict]) -> dict:
    manifests = {
        tp: results[tp]["header_and_plugins"]["ordered_plugin_manifest_sha256"]
        for tp in TIMEPOINTS
    }
    lists = {
        tp: results[tp]["header_and_plugins"]["plugins"]
        for tp in TIMEPOINTS
    }
    baseline = manifests["T0"]
    exact_manifest_match = all(manifests[tp] == baseline for tp in TIMEPOINTS)
    exact_list_match = all(lists[tp] == lists["T0"] for tp in TIMEPOINTS)
    return {
        "ordered_plugin_manifest_sha256": manifests,
        "exact_ordered_plugin_manifest_match": exact_manifest_match,
        "exact_ordered_plugin_list_match": exact_list_match,
        "strict_runtime_differential_admission": (
            "PASS_HEADER_AND_PLUGIN_ENVIRONMENT_ONLY"
            if exact_manifest_match and exact_list_match
            else "FAIL_PLUGIN_ENVIRONMENT_MISMATCH"
        ),
        "non_implication": "MATCHING_PLUGIN_ENVIRONMENT_DOES_NOT_PROVE_SAME_GAMEPLAY_LINEAGE_OR_RUNTIME_STATE",
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    for tp in TIMEPOINTS:
        p.add_argument(f"--{tp.lower()}", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    paths = {tp: getattr(args, tp.lower()) for tp in TIMEPOINTS}
    results: Dict[str, dict] = {}
    for tp, path in paths.items():
        if not path.is_file():
            raise SystemExit(f"{tp} missing: {path}")
        try:
            results[tp] = parse_file(path)
        except ParseError as exc:
            raise SystemExit(f"{tp} parse failed: {exc}") from exc

    output = {
        "schema": "janus.fo3_fos_header_plugin_manifest.v0_1",
        "authority": "HEADER_AND_PLUGIN_MANIFEST_AUTHENTICATION_ONLY",
        "source_model": "Nexus-Mods/Vortex FO3 save metadata parser semantics",
        "timepoints": results,
        "cross_timepoint": compare_timepoints(results),
        "body_change_state_decoder_established": False,
        "structured_james_runtime_state_established": False,
        "persisted_james_memory_established": False,
    }
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
