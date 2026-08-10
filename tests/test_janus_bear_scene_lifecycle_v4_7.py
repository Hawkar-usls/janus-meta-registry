import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "tools/verify_janus_bear_scene_lifecycle_v4_7.py"
spec = importlib.util.spec_from_file_location("life", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def life(ref="00000001", kind="TEDDY", **kw):
    row = {
        "logical_ref_formid": ref,
        "target_kind": kind,
        "origin_record_file": "Fallout3.esm",
        "winning_record_file": "Fallout3.esm",
        "winning_record_formid": ref,
        "base_file": "Fallout3.esm",
        "base_formid": "0001F21F",
        "base_editorid": "TeddyBear01",
        "location_key": "CELL|Fallout3.esm|000000AA",
        "location_editorid": "TestCell",
        "position_x": "1",
        "position_y": "2",
        "position_z": "3",
        "initially_disabled": "false",
        "persistent": "false",
        "override_count": "0",
        "enable_parent_reference_raw": "",
        "enable_parent_flags_raw": "",
        "owner_raw": "",
        "ref_script_raw": "",
        "base_script_raw": "",
        "direct_reverse_reference_count": "0",
        "full_path": "Fallout3.esm/TestCell/REFR",
    }
    row.update(kw)
    return row


def rev(target="00000001", sig="QUST"):
    return {
        "target_logical_ref_formid": target,
        "target_kind": "TEDDY",
        "referencing_file": "Fallout3.esm",
        "referencing_signature": sig,
        "referencing_formid": "000000BB",
        "referencing_editorid": "TestQuest",
        "referencing_name": "",
        "referencing_full_path": "Fallout3.esm/QUST/TestQuest",
    }


class LifecycleTests(unittest.TestCase):
    def test_direct_quiet_never_becomes_static_proof(self):
        r = mod.audit([life()], [])
        self.assertEqual(r["direct_quiet_target_count"], 1)
        self.assertFalse(r["claim_ceiling"]["direct_quiet_means_static_lifecycle_proven"])
        self.assertTrue(r["claim_ceiling"]["temporal_falsification_requires_manual_source_bound_lifecycle_decision"])

    def test_initially_disabled_is_dynamic_marker(self):
        r = mod.audit([life(initially_disabled="true")], [])
        self.assertIn("INITIALLY_DISABLED", r["direct_dependency_marker_targets"][0]["direct_dynamic_or_dependency_markers"])

    def test_enable_parent_is_dynamic_marker(self):
        r = mod.audit([life(enable_parent_reference_raw="PlayerRef [00000014]")], [])
        self.assertIn("ENABLE_PARENT", r["direct_dependency_marker_targets"][0]["direct_dynamic_or_dependency_markers"])

    def test_reverse_reference_is_preserved_as_review_marker(self):
        r = mod.audit([life(direct_reverse_reference_count="1")], [rev()])
        item = r["direct_dependency_marker_targets"][0]
        self.assertIn("OFFICIAL_REVERSE_REFERENCES", item["direct_dynamic_or_dependency_markers"])
        self.assertEqual(item["official_reverse_reference_count"], 1)

    def test_duplicate_logical_ref_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate logical"):
            mod.audit([life(), life()], [])

    def test_reverse_reference_to_missing_target_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "absent lifecycle targets"):
            mod.audit([life()], [rev(target="DEADBEEF")])

    def test_reverse_export_cannot_exceed_xedit_reported_count(self):
        with self.assertRaisesRegex(ValueError, "exceeds xEdit count"):
            mod.audit([life(direct_reverse_reference_count="0")], [rev()])


if __name__ == "__main__":
    unittest.main()
