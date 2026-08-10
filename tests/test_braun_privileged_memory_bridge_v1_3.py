import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "tools/verify_braun_privileged_memory_bridge_v1_3.py"
spec = importlib.util.spec_from_file_location("bridge", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def cand(term, form="00001000", sig="SCPT", path="SCTX - Script Source", editor="TestScript"):
    return {
        "record_file": "Fallout3.esm",
        "record_signature": sig,
        "record_formid": form,
        "root_fixed_formid": form,
        "record_editorid": editor,
        "record_name": "",
        "matched_keyword": term,
        "element_path": path,
        "element_value": term,
        "is_seed_record": "False",
        "seed_label": "",
        "record_full_path": f"Fallout3.esm/{sig}/{editor}",
    }


def rev(seed="Vault112PodTermDad", form="00001000", sig="SCPT"):
    return {
        "seed_fixed_formid": "00031190",
        "seed_label": seed,
        "seed_file": "Fallout3.esm",
        "seed_signature": "TERM",
        "referencing_file": "Fallout3.esm",
        "referencing_signature": sig,
        "referencing_formid": form,
        "referencing_editorid": "TestScript",
        "referencing_name": "",
        "referencing_full_path": "Fallout3.esm/SCPT/TestScript",
    }


class BraunBridgeTests(unittest.TestCase):
    def test_source_carrier_operation_convergence_never_auto_proves_edge(self):
        rows = [cand("mq04doc"), cand("mem chip"), cand("write")]
        r = mod.audit(rows, [])
        self.assertEqual(r["high_priority_bridge_candidate_count"], 1)
        item = r["high_priority_bridge_candidates"][0]
        self.assertIn("SOURCE+CARRIER+OPERATION", item["convergence"])
        self.assertFalse(item["direct_james_to_carrier_write_edge_proven"])
        self.assertFalse(r["claim_ceiling"]["high_priority_candidate_is_pass"])

    def test_script_surface_operation_is_candidate_only(self):
        r = mod.audit([cand("write")], [])
        item = r["records"][0]
        self.assertTrue(item["executable_surface_candidate"])
        self.assertFalse(r["claim_ceiling"]["script_surface_keyword_is_semantic_write_proof"])

    def test_reverse_reference_to_james_seed_creates_source_bound_candidate_not_direction(self):
        r = mod.audit([cand("memory")], [rev()])
        item = r["records"][0]
        self.assertTrue(item["source_bound_candidate"])
        self.assertIn("Vault112PodTermDad", item["seed_reverse_links"])
        self.assertFalse(r["claim_ceiling"]["reverse_reference_is_write_direction"])

    def test_braun_admin_carrier_operation_convergence_still_requires_james_source(self):
        rows = [cand("braun"), cand("mem chip"), cand("transfer")]
        r = mod.audit(rows, [])
        item = r["records"][0]
        self.assertTrue(item["admin_bound_candidate"])
        self.assertTrue(item["carrier_bound_candidate"])
        self.assertTrue(item["operation_bound_candidate"])
        self.assertFalse(item["source_bound_candidate"])
        self.assertEqual(r["high_priority_bridge_candidate_count"], 0)

    def test_unknown_user_never_equals_james(self):
        r = mod.audit([cand("user unknown")], [])
        self.assertFalse(r["claim_ceiling"]["unknown_user_equals_james"])

    def test_inventory_transfer_term_counts_as_operation_candidate(self):
        r = mod.audit([cand("mq04doc"), cand("additem")], [])
        item = r["records"][0]
        self.assertTrue(item["operation_bound_candidate"])
        self.assertIn("SOURCE+OPERATION", item["convergence"])
        self.assertFalse(item["direct_james_to_carrier_write_edge_proven"])

    def test_missing_keyword_fails_closed(self):
        bad = cand("memory")
        bad["matched_keyword"] = ""
        with self.assertRaisesRegex(ValueError, "missing matched_keyword"):
            mod.audit([bad], [])


if __name__ == "__main__":
    unittest.main()
