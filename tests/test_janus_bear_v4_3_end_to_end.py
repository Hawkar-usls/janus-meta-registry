import csv
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


acq = load_module("acq_v43", "tools/verify_janus_bear_v4_3_acquisition.py")
analyzer = load_module("analyzer_v42", "tools/analyze_teddy_gnome_enrichment_v4_2.py")
finalizer = load_module("finalizer_v43", "tools/finalize_janus_bear_v4_3_result.py")

HEADER = [
    "record_file", "record_signature", "record_formid", "record_editorid",
    "target_kind", "base_file", "base_signature", "base_formid",
    "base_editorid", "base_name", "location_key", "initially_disabled",
    "deleted", "persistent", "position_x", "position_y", "position_z",
    "full_path", "logical_ref_formid", "origin_record_file",
    "winning_record_file", "override_count", "location_editorid",
]


def make_row(plugin, logical, kind, x, disabled="false"):
    base_id = {
        "TEDDY": "0001F21F",
        "SKELETON_MALE": "0002EC65",
        "GNOME_DAMAGED": "0005B635",
    }.get(kind, "00000000")
    return {
        "record_file": plugin,
        "record_signature": "REFR",
        "record_formid": logical,
        "record_editorid": "",
        "target_kind": kind,
        "base_file": "Fallout3.esm",
        "base_signature": "MISC",
        "base_formid": base_id,
        "base_editorid": "",
        "base_name": "",
        "location_key": "CELL|Fallout3.esm|00000001",
        "initially_disabled": disabled,
        "deleted": "false",
        "persistent": "false",
        "position_x": str(x),
        "position_y": "0",
        "position_z": "0",
        "full_path": "synthetic",
        "logical_ref_formid": logical,
        "origin_record_file": plugin,
        "winning_record_file": plugin,
        "override_count": "0",
        "location_editorid": "TEST",
    }


def write_tsv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def test_v43_hash_bound_inventory_runs_through_v42_and_finalizer(tmp_path):
    master_dir = tmp_path / "Data"
    master_dir.mkdir()
    for i, name in enumerate(acq.REQUIRED_MASTERS):
        (master_dir / name).write_bytes(f"synthetic-{name}-{i}".encode("ascii"))

    kinds = ["TEDDY", "SKELETON_MALE", "GNOME_DAMAGED", "OTHER", "OTHER", "OTHER"]
    rows = []
    for i, (plugin, kind) in enumerate(zip(acq.REQUIRED_MASTERS, kinds)):
        rows.append(make_row(plugin, f"00{i+1:06X}", kind, x=i * 20, disabled="true" if i == 5 else "false"))

    inv = tmp_path / "inventory.tsv"
    enabled = tmp_path / "enabled.tsv"
    write_tsv(inv, rows)

    acquisition = acq.verify(master_dir, inv, synthetic=True, enabled_only_out=enabled)
    assert acquisition["status"].startswith("PASS_")

    all_analysis = analyzer.analyze(analyzer.base.load(inv))
    enabled_analysis = analyzer.analyze(analyzer.base.load(enabled))
    result = finalizer.build(acquisition, all_analysis, enabled_analysis)

    assert result["status"] == "REAL_ESM_SPATIAL_STATISTICS_COMPUTED_FROM_HASH_BOUND_EFFECTIVE_REFR_EXPORT"
    assert result["source_binding"]["inventory_sha256"] == acquisition["inventory"]["sha256"]
    assert result["all_effective_non_deleted_refr"]["population"]["teddy_count"] == 1
    assert result["all_effective_non_deleted_refr"]["population"]["gnome_count"] == 1
    assert result["claim_ceiling"]["statistical_enrichment_is_authorial_intent"] is False
    assert result["claim_ceiling"]["universal_official_distribution_authenticity_cryptographically_proved"] is False
