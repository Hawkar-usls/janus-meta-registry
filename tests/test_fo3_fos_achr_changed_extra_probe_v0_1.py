import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROBE_PATH = ROOT / "tools" / "fo3_fos_achr_changed_extra_probe_v0_1.py"
STRUCT_PATH = ROOT / "tools" / "fo3_fos_changed_form_header_index_v0_1.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


probe = load(PROBE_PATH, "fo3_probe_test")
structural = load(STRUCT_PATH, "fo3_structural_test_for_probe")


def t(raw: bytes) -> bytes:
    return raw + b"\x7c"


def u8(v):
    return t(bytes([v & 0xFF]))


def i8(v):
    return u8(v & 0xFF)


def u32(v):
    return t(int(v).to_bytes(4, "little"))


def vsval_1byte(v):
    assert 0 <= v < 64
    return t(bytes([(v << 2) & 0xFC]))


def ref_array(index):
    assert 0 <= index < (1 << 22)
    return t(index.to_bytes(3, "big"))


def valid_prefix_payload():
    out = bytearray()
    out += i8(3)                 # LowProcess
    out += vsval_1byte(1)        # one ExtraData entry
    out += u8(0x0D)
    out += ref_array(1)           # resolves through formid array
    out += vsval_1byte(0)        # script/local vars
    out += u8(0)                 # no event data
    out += u8(0)                 # script flag

    # MobileObject post-REFR fields
    for value in (-1, 0, 1, 1, 1, 0, 0, 1):
        out += i8(value)
    out += u32(0x3FB70D2C)        # deliberately variable baseline field
    out += u32(0)
    out += i8(0)
    out += u8(0)
    out += ref_array(0)
    out += ref_array(0)
    return bytes(out)


def test_vsval_04_decodes_to_one():
    r = probe.Reader(b"\x04\x7c", structural, [])
    decoded = r.vsvalt("count")
    assert decoded["value"] == 1
    assert decoded["width"] == 1
    assert r.pos == 2


def test_source_bound_prefix_resolves_save_local_refid():
    payload = valid_prefix_payload()
    decoded = probe.decode_source_bound_prefix(payload, structural, [0x0001F40A])
    assert decoded["process_level"] == 3
    assert decoded["process_level_class"] == "LOW"
    assert decoded["extra_count"]["value"] == 1
    assert decoded["extras"][0]["extra_type_hex"] == "0x0D"
    assert decoded["extras"][0]["primary_ref"]["resolved_formid_hex"] == "0x0001F40A"
    assert decoded["extras"][0]["script_var_count"]["value"] == 0
    assert decoded["extras"][0]["has_event_data"] == 0
    assert decoded["remaining_opaque_bytes"] == 0


def test_missing_pipe_fails_closed():
    payload = bytearray(valid_prefix_payload())
    payload[1] = 0x00
    with pytest.raises(probe.ProbeError, match="expected pipe"):
        probe.decode_source_bound_prefix(bytes(payload), structural, [0x0001F40A])


def test_unadmitted_extra_type_fails_closed():
    payload = bytearray(valid_prefix_payload())
    payload[4] = 0x18
    with pytest.raises(probe.ProbeError, match="admits only observed Extra Type 0x0D"):
        probe.decode_source_bound_prefix(bytes(payload), structural, [0x0001F40A])


def test_truncated_extra_ref_fails_closed():
    payload = valid_prefix_payload()[:7]
    with pytest.raises(probe.ProbeError):
        probe.decode_source_bound_prefix(payload, structural, [0x0001F40A])


def test_save_local_refid_index_changes_but_authored_formid_can_stay_same():
    # The resolver's semantics, not raw three-byte equality, define authored identity.
    r1 = probe.Reader(ref_array(1), structural, [0x0001F40A, 0x12345678])
    r2 = probe.Reader(ref_array(2), structural, [0x12345678, 0x0001F40A])
    a = r1.refidt("a")
    b = r2.refidt("b")
    assert a["save_refid"]["raw_hex"] != b["save_refid"]["raw_hex"]
    assert a["resolved_formid_hex"] == b["resolved_formid_hex"] == "0x0001F40A"
