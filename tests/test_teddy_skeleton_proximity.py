import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "tools/analyze_teddy_skeleton_proximity.py"

spec = importlib.util.spec_from_file_location("analyze_teddy_skeleton_proximity", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def row(kind, ref, loc="CELL_A", xyz=(0, 0, 0)):
    return {
        "record_file": "Fallout3.esm",
        "record_signature": "REFR",
        "record_formid": ref,
        "record_editorid": "",
        "target_kind": kind,
        "base_file": "Fallout3.esm",
        "base_signature": "MISC",
        "base_formid": "00000000",
        "base_editorid": "",
        "base_name": "",
        "location_key": loc,
        "initially_disabled": "false",
        "deleted": "false",
        "persistent": "false",
        "position_x": str(xyz[0]),
        "position_y": str(xyz[1]),
        "position_z": str(xyz[2]),
        "full_path": f"Fallout3.esm/{loc}/{ref}",
    }


def test_tight_teddy_skeleton_pair_recomputes_distance():
    rows = [
        row("TEDDY", "00000001", xyz=(0, 0, 0)),
        row("SKELETON_MALE", "00000002", xyz=(3, 4, 0)),
    ]
    r = mod.analyze(rows)
    nearest = r["teddy_receipts"][0]["nearest_skeleton"]
    assert nearest["distance_units"] == 5.0
    assert nearest["bucket"] == "TIGHT"


def test_same_cell_far_pair_is_not_near():
    rows = [
        row("TEDDY", "00000001", xyz=(0, 0, 0)),
        row("SKELETON_RAGS", "00000002", xyz=(1000, 0, 0)),
    ]
    r = mod.analyze(rows)
    nearest = r["teddy_receipts"][0]["nearest_skeleton"]
    assert nearest["bucket"] == "SAME_CELL"
    assert r["teddies_with_skeleton_within_512"] == 0


def test_different_location_keys_never_pair_even_with_same_xyz():
    rows = [
        row("TEDDY", "00000001", loc="CELL_A", xyz=(0, 0, 0)),
        row("SKELETON_FEMALE", "00000002", loc="CELL_B", xyz=(0, 0, 0)),
    ]
    r = mod.analyze(rows)
    assert r["teddy_receipts"][0]["nearest_skeleton"] is None
    assert r["teddy_skeleton_bucket_counts"]["NO_SKELETON_IN_LOCATION"] == 1


def test_gnome_is_tracked_separately_and_never_counts_as_skeleton():
    rows = [
        row("TEDDY", "00000001", xyz=(0, 0, 0)),
        row("GNOME_INTACT", "00000002", xyz=(1, 0, 0)),
    ]
    r = mod.analyze(rows)
    assert r["reference_counts"]["tracked_gnome"] == 1
    assert r["teddy_receipts"][0]["nearest_gnome"]["distance_units"] == 1.0
    assert r["teddy_receipts"][0]["nearest_skeleton"] is None


def test_proximity_never_claims_single_in_world_placer():
    rows = [
        row("TEDDY", "00000001", xyz=(0, 0, 0)),
        row("SKELETON_MALE", "00000002", xyz=(1, 0, 0)),
        row("TEDDY", "00000003", xyz=(10, 0, 0)),
        row("SKELETON_FEMALE", "00000004", xyz=(11, 0, 0)),
    ]
    r = mod.analyze(rows)
    assert r["teddies_with_skeleton_within_512"] == 2
    assert r["claim_ceiling"]["single_in_world_placer_proven"] is False
