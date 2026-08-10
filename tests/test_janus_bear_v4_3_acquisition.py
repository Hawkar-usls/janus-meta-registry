import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "tools/verify_janus_bear_v4_3_acquisition.py"
spec = importlib.util.spec_from_file_location("verify_janus_bear_v4_3_acquisition", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

HEADER = [
    "record_file", "record_signature", "record_formid", "record_editorid",
    "target_kind", "base_file", "base_signature", "base_formid",
    "base_editorid", "base_name", "location_key", "initially_disabled",
    "deleted", "persistent", "position_x", "position_y", "position_z",
    "full_path", "logical_ref_formid", "origin_record_file",
    "winning_record_file", "override_count", "location_editorid",
]


def make_masters(tmp_path: Path):
    d = tmp_path / "Data"
    d.mkdir()
    for i, name in enumerate(mod.REQUIRED_MASTERS):
        (d / name).write_bytes((name + f"-synthetic-{i}").encode("ascii"))
    return d


def row(plugin, logical, kind="OTHER", disabled="false", deleted="false"):
    base_formid = "00000000"
    if kind == "TEDDY":
        base_formid = "0001F21F"
    elif kind == "SKELETON_MALE":
        base_formid = "0002EC65"
    elif kind == "GNOME_DAMAGED":
        base_formid = "0005B635"
    return {
        "record_file": plugin,
        "record_signature": "REFR",
        "record_formid": logical,
        "record_editorid": "",
        "target_kind": kind,
        "base_file": "Fallout3.esm",
        "base_signature": "MISC",
        "base_formid": base_formid,
        "base_editorid": "",
        "base_name": "",
        "location_key": "CELL|Fallout3.esm|00000001",
        "initially_disabled": disabled,
        "deleted": deleted,
        "persistent": "false",
        "position_x": "1.0",
        "position_y": "2.0",
        "position_z": "3.0",
        "full_path": "synthetic",
        "logical_ref_formid": logical,
        "origin_record_file": plugin,
        "winning_record_file": plugin,
        "override_count": "0",
        "location_editorid": "TEST",
    }


def write_inventory(path: Path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def good_rows():
    rows = []
    for i, plugin in enumerate(mod.REQUIRED_MASTERS):
        kind = "OTHER"
        if i == 0:
            kind = "TEDDY"
        elif i == 1:
            kind = "SKELETON_MALE"
        elif i == 2:
            kind = "GNOME_DAMAGED"
        rows.append(row(plugin, f"00{i+1:06X}", kind=kind, disabled="true" if i == 5 else "false"))
    return rows


def test_complete_hash_bound_bundle_and_effective_inventory_pass(tmp_path):
    masters = make_masters(tmp_path)
    inv = tmp_path / "inventory.tsv"
    enabled = tmp_path / "enabled.tsv"
    write_inventory(inv, good_rows())

    result = mod.verify(masters, inv, synthetic=True, enabled_only_out=enabled)

    assert result["status"].startswith("PASS_")
    assert result["checks_failed"] == 0
    assert len(result["master_bundle"]["entries"]) == 6
    assert result["inventory"]["effective_logical_refr_count"] == 6
    assert result["inventory"]["initially_disabled_rows"] == 1
    assert result["inventory"]["enabled_rows"] == 5
    assert enabled.is_file()
    assert result["claim_ceiling"]["official_distribution_authenticity_cryptographically_proved"] is False
    assert result["claim_ceiling"]["real_spatial_result_established"] is False


def test_missing_dlc_fails_closed(tmp_path):
    masters = make_masters(tmp_path)
    (masters / "Zeta.esm").unlink()
    inv = tmp_path / "inventory.tsv"
    write_inventory(inv, good_rows())

    result = mod.verify(masters, inv, synthetic=True)

    assert result["status"] == "BLOCKED"
    assert any(c["name"] == "master.Zeta.esm.exists" and not c["pass"] for c in result["checks"])


def test_duplicate_logical_reference_fails_closed(tmp_path):
    masters = make_masters(tmp_path)
    rows = good_rows()
    rows.append(dict(rows[0]))
    inv = tmp_path / "inventory.tsv"
    write_inventory(inv, rows)

    result = mod.verify(masters, inv, synthetic=True)

    assert result["status"] == "BLOCKED"
    assert any(c["name"] == "inventory.logical_ids_unique" and not c["pass"] for c in result["checks"])


def test_winning_deleted_row_fails_closed(tmp_path):
    masters = make_masters(tmp_path)
    rows = good_rows()
    rows[0]["deleted"] = "true"
    inv = tmp_path / "inventory.tsv"
    write_inventory(inv, rows)

    result = mod.verify(masters, inv, synthetic=True)

    assert result["status"] == "BLOCKED"
    assert any(c["name"] == "inventory.no_winning_deleted_rows" and not c["pass"] for c in result["checks"])


def test_nonofficial_winning_plugin_fails_closed(tmp_path):
    masters = make_masters(tmp_path)
    rows = good_rows()
    rows[0]["record_file"] = "SomeMod.esp"
    rows[0]["winning_record_file"] = "SomeMod.esp"
    inv = tmp_path / "inventory.tsv"
    write_inventory(inv, rows)

    result = mod.verify(masters, inv, synthetic=True)

    assert result["status"] == "BLOCKED"
    assert any(c["name"] == "inventory.winning_files_official_set" and not c["pass"] for c in result["checks"])
