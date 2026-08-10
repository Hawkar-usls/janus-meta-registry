import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "tools/analyze_teddy_gnome_enrichment.py"

spec = importlib.util.spec_from_file_location("analyze_teddy_gnome_enrichment", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def row(kind, ref, loc="CELL_A", xyz=(0, 0, 0), base_signature="MISC"):
    return {
        "record_file": "Fallout3.esm",
        "record_signature": "REFR",
        "record_formid": ref,
        "record_editorid": "",
        "target_kind": kind,
        "base_file": "Fallout3.esm",
        "base_signature": base_signature,
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


def test_strong_enrichment_recomputes_twenty_x_and_fisher():
    rows = [row("SKELETON_MALE", "S1", xyz=(0, 0, 0))]
    for i, pos in enumerate(((1, 0, 0), (2, 0, 0), (3, 0, 0), (4, 0, 0))):
        rows.append(row("TEDDY", f"T{i}", xyz=pos))
    for i in range(20):
        pos = (10, 0, 0) if i == 0 else (1000 + i * 10, 0, 0)
        rows.append(row("OTHER", f"C{i}", xyz=pos))

    result = mod.analyze(rows)
    gate = result["teddy_skeleton_enrichment"]["primary_misc_baseline"]["128"]
    assert gate["risk_ratio_teddy_vs_control"] == 20.0
    assert gate["fisher_exact_two_sided_p"] < 0.01


def test_non_misc_broad_reference_does_not_contaminate_primary_misc_baseline():
    rows = [
        row("SKELETON_MALE", "S1", xyz=(0, 0, 0)),
        row("TEDDY", "T1", xyz=(1, 0, 0)),
        row("OTHER", "M1", xyz=(1000, 0, 0), base_signature="MISC"),
        row("OTHER", "D1", xyz=(2, 0, 0), base_signature="DOOR"),
    ]
    result = mod.analyze(rows)
    assert result["population"]["matched_misc_clutter_control_count"] == 1
    assert result["population"]["matched_broad_reference_control_count"] == 2


def test_different_location_keys_never_pair():
    rows = [
        row("SKELETON_MALE", "S1", loc="CELL_B", xyz=(0, 0, 0)),
        row("TEDDY", "T1", loc="CELL_A", xyz=(0, 0, 0)),
        row("OTHER", "M1", loc="CELL_A", xyz=(1, 0, 0)),
    ]
    result = mod.analyze(rows)
    assert result["per_teddy"][0]["nearest_skeleton"] is None


def test_damaged_gnome_and_teddy_skeleton_gnome_triad_are_tracked():
    rows = [
        row("SKELETON_MALE", "S1", xyz=(0, 0, 0)),
        row("TEDDY", "T1", xyz=(10, 0, 0)),
        row("GNOME_DAMAGED", "G1", xyz=(20, 0, 0)),
        row("OTHER", "M1", xyz=(1000, 0, 0)),
    ]
    result = mod.analyze(rows)
    assert result["population"]["gnome_by_kind"]["GNOME_DAMAGED"] == 1
    assert result["teddy_gnome_grammar"]["teddy_with_skeleton_and_gnome_within_512"] == 1


def test_zero_control_hit_baseline_returns_infinite_ratio_without_crash():
    rows = [
        row("SKELETON_MALE", "S1", xyz=(0, 0, 0)),
        row("TEDDY", "T1", xyz=(10, 0, 0)),
        row("OTHER", "M1", xyz=(1000, 0, 0)),
    ]
    result = mod.analyze(rows)
    gate = result["teddy_skeleton_enrichment"]["primary_misc_baseline"]["128"]
    assert gate["risk_ratio_teddy_vs_control"] == "INF"


def test_exact_context_map_separates_tragedy_and_store_without_name_heuristics():
    rows = [
        row("SKELETON_MALE", "S1", loc="A", xyz=(0, 0, 0)),
        row("TEDDY", "T1", loc="A", xyz=(1, 0, 0)),
        row("OTHER", "M1", loc="A", xyz=(20, 0, 0)),
        row("TEDDY", "T2", loc="B", xyz=(0, 0, 0)),
        row("OTHER", "M2", loc="B", xyz=(20, 0, 0)),
    ]
    result = mod.analyze(rows, context_map={"A": "TRAGEDY", "B": "STORE"})
    assert result["context_ledger_summary"]["TRAGEDY"]["teddy_near_skeleton_128_rate"] == 1.0
    assert result["context_ledger_summary"]["STORE"]["teddy_near_skeleton_128_rate"] == 0.0


def test_statistics_never_create_hidden_placer_intent_or_living_gnome_claim():
    rows = [
        row("SKELETON_MALE", "S1", xyz=(0, 0, 0)),
        row("TEDDY", "T1", xyz=(1, 0, 0)),
        row("GNOME_INTACT", "G1", xyz=(2, 0, 0)),
        row("OTHER", "M1", xyz=(1000, 0, 0)),
    ]
    result = mod.analyze(rows)
    assert result["claim_ceiling"]["enrichment_proves_authorial_intent"] is False
    assert result["claim_ceiling"]["enrichment_proves_single_in_world_placer"] is False
    assert result["claim_ceiling"]["gnome_proximity_proves_gnomes_alive"] is False
