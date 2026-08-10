import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "tools/verify_zeta_birthday_lineage_receipt.py"

spec = importlib.util.spec_from_file_location("verify_zeta_birthday_lineage_receipt", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def row(base, rec="05000001", loc="DLC05CargoHold", disabled="false", reason=""):
    return {
        "record_file":"Zeta.esm","record_signature":"REFR","record_formid":rec,
        "record_editorid":"","base_file":"Fallout3.esm","base_signature":"ARMO",
        "base_formid":base,"base_editorid":"","base_name":"",
        "parent_cell_or_world":loc,"initially_disabled":disabled,
        "deleted":"false","persistent":"false","position_x":"0","position_y":"0",
        "position_z":"0","full_path":f"Zeta.esm/{loc}","match_reason":reason,
    }


def test_four_adult_hats_do_not_create_direct_cg02_edge():
    rows = [row("00050E44", f"0500000{i}") for i in range(1,5)]
    r = mod.verify(rows)
    assert r["claims"]["FOUR_ZETA_ADULT_PARTY_HATS"] == "PASS"
    assert r["claims"]["DIRECT_DLC05_REFERENCE_TO_FALLOUT3_BIRTHDAY_BASE"] == "NOT_ESTABLISHED"


def test_kid_hat_reference_creates_direct_edge():
    rows = [row("00028FF8", "0500ABCD")]
    r = mod.verify(rows)
    assert r["claims"]["DIRECT_DLC05_REFERENCE_TO_FALLOUT3_BIRTHDAY_BASE"] == "PASS"
    assert r["claims"]["KIDS_PARTY_HAT_BASE_ON_ZETA"] == "PASS"


def test_disabled_exam_reference_is_strong_pass():
    rows = [row("0009AE98", "0500ABCE", "DLC05MZ1 Examination", "true")]
    r = mod.verify(rows)
    assert r["claims"]["DIRECT_DLC05_REFERENCE_TO_FALLOUT3_BIRTHDAY_BASE"] == "STRONG_PASS"
    assert r["claims"]["EXAMINATION_CONTEXT_BIRTHDAY_REFERENCE"] == "PASS"


def test_surveillance_is_never_derived_from_asset_receipt():
    rows = [row("00028FF8", "0500ABCF", "DLC05MZ1 Examination", "true")]
    r = mod.verify(rows)
    assert r["claims"]["LIFELONG_ALIEN_SURVEILLANCE"] == "NOT_DERIVABLE_FROM_THIS_RECEIPT"
