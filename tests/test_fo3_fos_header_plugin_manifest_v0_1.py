import importlib.util
import struct
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "fo3_fos_header_plugin_manifest_v0_1.py"
spec = importlib.util.spec_from_file_location("fo3_header", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def marked_u32(value: int) -> bytes:
    return struct.pack("<I", value) + b"|"


def marked_i32(value: int) -> bytes:
    return struct.pack("<i", value) + b"|"


def marked_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<H", len(raw)) + b"|" + raw + (b"|" if raw else b"")


def make_fo3_save(plugins=None, *, discriminator_size=4, corrupt_location_marker=False):
    plugins = plugins or ["Fallout3.esm", "BrokenSteel.esm"]
    width, height = 2, 1
    out = bytearray(mod.MAGIC)
    out += struct.pack("<I", 123)
    out += struct.pack("<I", 0x30)
    out += b"|"

    if discriminator_size == 4:
        out += marked_u32(width)
    else:
        out += b"X" * discriminator_size + b"|"

    if discriminator_size == 4:
        out += marked_u32(height)
        out += marked_u32(7)
        out += marked_string("Hawkar")
        out += marked_string("karma")
        out += marked_i32(20)
        loc = marked_string("Vault 112")
        if corrupt_location_marker:
            loc = loc[:-1] + b"!"
        out += loc
        out += marked_string("01.02.03")
        out += bytes([1, 2, 3, 4, 5, 6])
        out += b"\x00" + struct.pack("<I", 999)
        out += bytes([len(plugins)]) + b"|"
        for plugin in plugins:
            out += marked_string(plugin)
        out += b"OPAQUE_BODY"
    return bytes(out)


def test_valid_fo3_header_and_plugins():
    result = mod.parse_fo3_header_and_plugins(make_fo3_save())
    assert result["magic"] == "FO3SAVEGAME"
    assert result["file_version_hex"] == "0x30"
    assert result["plugins"] == ["Fallout3.esm", "BrokenSteel.esm"]
    assert result["opaque_body_bytes_remaining"] == len(b"OPAQUE_BODY")
    assert result["body_semantics"] == "OPAQUE_NOT_DECODED_BY_THIS_TOOL"


def test_new_vegas_like_discriminator_rejected():
    with pytest.raises(mod.ParseError, match="expected 4"):
        mod.parse_fo3_header_and_plugins(make_fo3_save(discriminator_size=5))


def test_corrupt_field_marker_rejected():
    with pytest.raises(mod.ParseError, match="field marker"):
        mod.parse_fo3_header_and_plugins(make_fo3_save(corrupt_location_marker=True))


def test_cross_timepoint_plugin_mismatch_fails_strict_admission(tmp_path):
    results = {}
    for tp in mod.TIMEPOINTS:
        plugins = ["Fallout3.esm", "BrokenSteel.esm"]
        if tp == "T3":
            plugins = ["Fallout3.esm"]
        path = tmp_path / f"{tp}.fos"
        path.write_bytes(make_fo3_save(plugins))
        results[tp] = mod.parse_file(path)
    cmp = mod.compare_timepoints(results)
    assert cmp["exact_ordered_plugin_manifest_match"] is False
    assert cmp["strict_runtime_differential_admission"] == "FAIL_PLUGIN_ENVIRONMENT_MISMATCH"
