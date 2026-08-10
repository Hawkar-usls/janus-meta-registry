import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "tools/analyze_zeta_crystal_colocation.py"

spec = importlib.util.spec_from_file_location("analyze_zeta_crystal_colocation", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def row(form, ref, loc="Robot Assembly", edid="", name="", xyz=(0, 0, 0)):
    return {
        "record_file": "Zeta.esm",
        "record_signature": "REFR",
        "record_formid": ref,
        "record_editorid": "",
        "base_file": "Zeta.esm",
        "base_signature": "MISC",
        "base_formid": form,
        "base_editorid": edid,
        "base_name": name,
        "parent_cell_or_world": loc,
        "initially_disabled": "false",
        "deleted": "false",
        "persistent": "false",
        "position_x": str(xyz[0]),
        "position_y": str(xyz[1]),
        "position_z": str(xyz[2]),
        "full_path": f"Zeta.esm/{loc}",
    }


def test_cell_name_does_not_classify_all_contents_as_technology():
    rows = [
        row("0000A9E9", "05000001"),
        row("00001234", "05000002", name="Coffee cup", xyz=(1, 0, 0)),
    ]
    result = mod.analyze(rows)
    assert result["tech_candidate_reference_count"] == 0
    assert result["nearest_tech_by_crystal"][0]["nearest_tech"] == []


def test_crystals_do_not_count_as_technology_candidates_for_each_other():
    rows = [
        row("0000A9E9", "05000001"),
        row("0000A9E6", "05000002", xyz=(1, 0, 0)),
    ]
    result = mod.analyze(rows)
    assert result["crystal_reference_count"] == 2
    assert result["tech_candidate_reference_count"] == 0


def test_explicit_console_is_classified_and_distance_is_recomputed():
    rows = [
        row("0000A9E9", "05000001"),
        row(
            "00001234",
            "05000002",
            edid="DLC05RobotAssemblyConsole",
            name="Control console",
            xyz=(3, 4, 0),
        ),
    ]
    result = mod.analyze(rows)
    assert result["tech_candidate_reference_count"] == 1
    nearest = result["nearest_tech_by_crystal"][0]["nearest_tech"][0]
    assert nearest["record_formid"] == "05000002"
    assert nearest["distance_units"] == 5.0
