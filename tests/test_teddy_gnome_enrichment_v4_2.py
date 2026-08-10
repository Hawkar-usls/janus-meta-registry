import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "tools/analyze_teddy_gnome_enrichment_v4_2.py"

spec = importlib.util.spec_from_file_location("analyze_teddy_gnome_enrichment_v4_2", MOD_PATH)
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


def test_exact_cell_stratified_positive_enrichment_matches_hypergeometric_tail():
    rows = [row("SKELETON_MALE", "S1", xyz=(0, 0, 0))]
    for i, pos in enumerate(((1, 0, 0), (2, 0, 0), (3, 0, 0), (4, 0, 0))):
        rows.append(row("TEDDY", f"T{i}", xyz=pos))
    for i in range(20):
        pos = (10, 0, 0) if i == 0 else (1000 + i * 10, 0, 0)
        rows.append(row("OTHER", f"C{i}", xyz=pos))

    result = mod.analyze(rows)
    gate = result["v4_2_hardening"]["cell_stratified_exact_test"]["128"]
    expected = math.comb(5, 4) / math.comb(24, 4)
    assert gate["observed_teddy_near"] == 4
    assert math.isclose(gate["one_sided_p_enrichment"], expected, rel_tol=1e-12)


def test_cell_stratification_rejects_cross_cell_composition_confounding():
    rows = []

    # CELL_A is skeleton-heavy: every candidate MISC position is near a skeleton.
    rows.append(row("SKELETON_MALE", "SA", loc="CELL_A", xyz=(0, 0, 0)))
    for i in range(10):
        rows.append(row("TEDDY", f"TA{i}", loc="CELL_A", xyz=(10 + i, 0, 0)))
    rows.append(row("OTHER", "CA0", loc="CELL_A", xyz=(20, 0, 0)))

    # CELL_B is skeleton-free: no candidate position can be near a skeleton.
    rows.append(row("TEDDY", "TB0", loc="CELL_B", xyz=(0, 0, 0)))
    for i in range(20):
        rows.append(row("OTHER", f"CB{i}", loc="CELL_B", xyz=(100 + i, 0, 0)))

    result = mod.analyze(rows)
    pooled = result["teddy_skeleton_enrichment"]["primary_misc_baseline"]["128"]
    strat = result["v4_2_hardening"]["cell_stratified_exact_test"]["128"]

    assert pooled["risk_ratio_teddy_vs_control"] > 10
    assert math.isclose(strat["one_sided_p_enrichment"], 1.0, rel_tol=1e-12)


def test_geometry_diagnostic_exposes_vertical_floor_like_separation():
    rows = [
        row("TEDDY", "T1", xyz=(0, 0, 0)),
        row("SKELETON_MALE", "S1", xyz=(0, 0, 500)),
        row("OTHER", "C1", xyz=(1000, 0, 0)),
    ]
    result = mod.analyze(rows)
    geo = result["v4_2_hardening"]["geometry_diagnostics"][0]["nearest_skeleton_proxy"]

    assert geo["within_512_3d"] is True
    assert geo["abs_vertical_delta_units"] == 500.0
    assert geo["within_512_3d_and_vertical_band_128"] is False
    assert result["claim_ceiling"]["same_scene_established_by_512_distance"] is False


def test_population_is_static_skeleton_proxy_not_all_human_remains():
    rows = [
        row("TEDDY", "T1", xyz=(0, 0, 0)),
        row("SKELETON_FEMALE", "S1", xyz=(10, 0, 0)),
        row("OTHER", "C1", xyz=(1000, 0, 0)),
    ]
    result = mod.analyze(rows)
    semantics = result["v4_2_hardening"]["population_semantics"]

    assert semantics["target_is_static_skeleton_proxy_not_all_human_remains"] is True
    assert semantics["all_human_remains_claim_allowed"] is False
    assert result["claim_ceiling"]["all_human_remains_measured"] is False
