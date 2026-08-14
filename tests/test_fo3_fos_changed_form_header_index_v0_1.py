import importlib.util
import struct
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "fo3_fos_changed_form_header_index_v0_1.py"
spec = importlib.util.spec_from_file_location("fo3_body", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def save_refid_bytes(ref_type: int, value: int) -> bytes:
    raw = ((ref_type & 3) << 22) | (value & 0x3FFFFF)
    return raw.to_bytes(3, "big")


def make_record(ref_type, value, flags, change_type, length_code, version, payload):
    out = bytearray(save_refid_bytes(ref_type, value))
    out += struct.pack("<I", flags)
    out.append(((length_code & 3) << 6) | (change_type & 0x3F))
    out.append(version)
    if length_code == 0:
        out.append(len(payload))
    elif length_code == 1:
        out += struct.pack("<H", len(payload))
    elif length_code == 2:
        out += struct.pack("<I", len(payload))
    else:
        out.append(0)
    out += payload
    return bytes(out)


def make_structural_blob():
    data = bytearray(b"\x00" * 0x500)
    flt_offset = 0x20
    gdt1 = 0x100
    changed = 0x120

    formids = [0x00019D09, 0x0006023C]
    record_1 = make_record(0, 1, 0x1234, 1, 0, 7, b"abc")
    record_2 = make_record(0, 2, 0x89ABCDEF, 1, 1, 8, b"doc-state")
    gdt2 = changed + len(record_1) + len(record_2)
    refarr = gdt2 + 0x40
    unknown = refarr + 4 + len(formids) * 4 + 0x20

    fields = [refarr, unknown, gdt1, changed, gdt2, 0, 0, 2, 0]
    data[flt_offset:flt_offset + 36] = struct.pack("<9I", *fields)
    data[flt_offset + 36:flt_offset + mod.FLT_SIZE] = b"\x00" * mod.FLT_RESERVED_SIZE
    data[changed:gdt2] = record_1 + record_2
    data[refarr:refarr + 4] = struct.pack("<I", len(formids))
    data[refarr + 4:refarr + 12] = struct.pack("<2I", *formids)
    return bytes(data), flt_offset, fields


def test_file_location_table_and_chapter_order():
    data, flt_offset, fields = make_structural_blob()
    flt = mod.parse_file_location_table(data, flt_offset)
    assert flt["changed_forms_offset"] == fields[3]
    assert flt["changed_forms_count"] == 2
    assert flt["reserved_all_zero"] is True


def test_save_refid_big_endian_and_formid_array_resolution():
    raw = save_refid_bytes(0, 2)
    ref = mod.read_save_refid(raw)
    assert ref["type"] == "FORMID_ARRAY"
    assert ref["value"] == 2
    assert mod.resolve_save_refid(ref, [0x00019D09, 0x0006023C]) == 0x0006023C


def test_created_refid_resolution():
    ref = mod.read_save_refid(save_refid_bytes(2, 0x123))
    assert ref["type"] == "CREATED"
    assert mod.resolve_save_refid(ref, []) == 0xFF000123


def test_changed_form_index_binds_james_targets_structurally():
    data, flt_offset, _ = make_structural_blob()
    flt = mod.parse_file_location_table(data, flt_offset)
    formids, _ = mod.parse_formid_array(data, flt["refid_array_count_offset"])
    records, end = mod.parse_changed_forms(
        data,
        flt["changed_forms_offset"],
        flt["changed_forms_count"],
        flt["global_data_table_2_offset"],
        formids,
    )
    assert end == flt["global_data_table_2_offset"]
    assert records[0]["resolved_formid_hex"] == "0x00019D09"
    assert records[1]["resolved_formid_hex"] == "0x0006023C"
    matches = mod.target_matches(records)
    assert len(matches["MQDadRef"]) == 1
    assert len(matches["MQ04Doc_REF"]) == 1
    assert matches["MQ04"] == []


def test_length_code_three_fails_closed():
    record = bytearray(save_refid_bytes(0, 1))
    record += struct.pack("<I", 0)
    record.append((3 << 6) | 1)
    record.append(1)
    record.append(0)
    with pytest.raises(mod.ParseError, match="length code 3"):
        mod.parse_changed_forms(bytes(record), 0, 1, len(record), [0x00019D09])


def test_payload_cannot_cross_next_chapter_boundary():
    record = bytearray(save_refid_bytes(0, 1))
    record += struct.pack("<I", 0)
    record.append(1)
    record.append(1)
    record.append(20)
    record += b"short"
    with pytest.raises(mod.ParseError, match="crosses Global Data Table 2 boundary"):
        mod.parse_changed_forms(bytes(record), 0, 1, len(record), [0x00019D09])
