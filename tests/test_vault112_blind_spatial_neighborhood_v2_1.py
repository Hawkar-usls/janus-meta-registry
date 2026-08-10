import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "tools/verify_vault112_blind_spatial_neighborhood_v2_1.py"
spec = importlib.util.spec_from_file_location("blind", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def ref(rid, base, x, y=0, z=0, sig="ACTI", edid="", name="", model=""):
    return {
        "logical_ref_formid": rid,
        "winning_file": "Fallout3.esm",
        "base_signature": sig,
        "base_fixed_formid": base,
        "base_editorid": edid,
        "base_name": name,
        "ref_editorid": "",
        "ref_name": "",
        "position_x": str(x),
        "position_y": str(y),
        "position_z": str(z),
        "initially_disabled": "false",
        "enable_parent_raw": "",
        "owner_raw": "",
        "ref_script_raw": "",
        "base_script_raw": "",
        "base_model_raw": model,
        "full_path": f"Fallout3.esm/Vault112a/REFR/{rid}",
    }


def monitor(rid="00070001", x=0):
    return ref(rid, "00031190", x, sig="TERM", edid="Vault112PodTermDad")


def vision(rid="00070010", x=10, base="0002A45B"):
    return ref(rid, base, x, sig="FURN", edid="Visiontron")


class BlindSpatialTests(unittest.TestCase):
    def test_monitor_nearest_visiontron_is_geometric_only(self):
        r = mod.audit([monitor(), vision()])
        self.assertEqual(r["monitor_to_visiontron_candidates"][0]["visiontron_refid"], "00070010")
        self.assertFalse(r["monitor_to_visiontron_candidates"][0]["functional_binding_proven"])

    def test_exact_distance_tie_is_preserved(self):
        rows = [monitor(), vision("00070010", 10), vision("00070011", -10, base="000B364C")]
        r = mod.audit(rows)
        self.assertTrue(r["monitor_to_visiontron_candidates"][0]["exact_distance_tie"])

    def test_unnamed_generic_acti_repeated_near_loungers_is_detected(self):
        rows = [
            monitor(),
            vision("00070010", 10),
            vision("00070011", 1010, base="000B364C"),
            ref("00071000", "0006AA00", 20, sig="ACTI"),
            ref("00071001", "0006AA00", 1020, sig="ACTI"),
        ]
        r = mod.audit(rows)
        c = [x for x in r["repeated_blind_neighbor_base_candidates"] if x["base_formid"] == "0006AA00"]
        self.assertEqual(len(c), 1)
        self.assertTrue(c[0]["unnamed_base"])
        self.assertFalse(c[0]["functional_shard_binding_proven"])

    def test_generic_stat_is_not_filtered_out(self):
        rows = [monitor(), vision(), ref("00071000", "0006AA01", 12, sig="STAT")]
        r = mod.audit(rows)
        got = [x for x in r["james_blind_neighbor_candidates"] if x["refid"] == "00071000"]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["base_signature"], "STAT")

    def test_generic_mstt_is_not_filtered_out(self):
        rows = [monitor(), vision(), ref("00071000", "0006AA02", 12, sig="MSTT")]
        r = mod.audit(rows)
        self.assertTrue(any(x["refid"] == "00071000" for x in r["james_blind_neighbor_candidates"]))

    def test_different_bases_do_not_form_repeated_candidate(self):
        rows = [
            monitor(), vision("00070010", 10), vision("00070011", 1010, base="000B364C"),
            ref("00071000", "0006AA00", 20), ref("00071001", "0006AA01", 1020),
        ]
        r = mod.audit(rows)
        bases = {x["base_formid"] for x in r["repeated_blind_neighbor_base_candidates"]}
        self.assertNotIn("0006AA00", bases)
        self.assertNotIn("0006AA01", bases)

    def test_outside_radius_is_not_considered(self):
        rows = [
            monitor(),
            vision("00070010", 10),
            vision("00070011", 1010, base="000B364C"),
            ref("00071000", "0006AA00", 20),
            ref("00071001", "0006AA00", 3000),
        ]
        r = mod.audit(rows, radius=128)
        self.assertEqual(r["james_repeated_blind_candidate_count"], 0)

    def test_self_visiontron_is_never_its_own_neighbor(self):
        rows = [monitor(), vision()]
        r = mod.audit(rows)
        self.assertFalse(any(x["refid"] == "00070010" for x in r["james_blind_neighbor_candidates"]))

    def test_duplicate_ref_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate logical RefID"):
            mod.audit([monitor(), monitor()])

    def test_non_numeric_position_fails_closed(self):
        bad = monitor()
        bad["position_x"] = "nope"
        with self.assertRaisesRegex(ValueError, "must be numeric"):
            mod.audit([bad, vision()])

    def test_repeated_james_neighbor_is_candidate_not_backend_proof(self):
        rows = [
            monitor(),
            vision("00070010", 10),
            vision("00070011", 1010, base="000B364C"),
            ref("00071000", "0006AA00", 20),
            ref("00071001", "0006AA00", 1020),
        ]
        r = mod.audit(rows)
        j = [x for x in r["james_repeated_blind_candidates"] if x["base_formid"] == "0006AA00"]
        self.assertEqual(len(j), 1)
        self.assertFalse(j[0]["james_specific_backend_handle_proven"])
        self.assertFalse(r["claim_ceiling"]["REPEATED_BASE_EQUALS_FUNCTIONAL_WIRING"])

    def test_no_memory_persistence_auto_promotion(self):
        rows = [monitor(), vision(), ref("00071000", "0006AA00", 12)]
        r = mod.audit(rows)
        self.assertEqual(r["admission"]["james_specific_persisted_memory_state"], "NOT_ESTABLISHED")
        self.assertFalse(r["claim_ceiling"]["SPATIAL_PATTERN_EQUALS_MEMORY_PERSISTENCE"])


if __name__ == "__main__":
    unittest.main()
