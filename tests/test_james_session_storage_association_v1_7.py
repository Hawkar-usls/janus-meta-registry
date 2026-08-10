import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "tools/verify_james_session_storage_association_v1_7.py"
spec = importlib.util.spec_from_file_location("storage", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def seed(label="Vault112PodTermDad", linked_formid="", linked_editorid="", linked_name="", value="x"):
    return {
        "seed_fixed_formid": "00031190",
        "seed_label": label,
        "record_file": "Fallout3.esm",
        "record_signature": "TERM",
        "record_formid": "00031190",
        "element_path": "Test\\Leaf",
        "element_name": "Test",
        "element_value": value,
        "linked_file": "Fallout3.esm" if linked_formid else "",
        "linked_signature": "REFR" if linked_formid else "",
        "linked_formid": linked_formid,
        "linked_editorid": linked_editorid,
        "linked_name": linked_name,
    }


def rev(seed_label="Vault112PodTermDad", form="00090000", sig="SCPT", editor="StorageScript"):
    return {
        "seed_fixed_formid": "00031190",
        "seed_label": seed_label,
        "seed_file": "Fallout3.esm",
        "seed_signature": "TERM",
        "referencing_file": "Fallout3.esm",
        "referencing_signature": sig,
        "referencing_formid": form,
        "referencing_editorid": editor,
        "referencing_name": "",
        "referencing_full_path": f"Fallout3.esm/{sig}/{editor}",
    }


def placed(ref="00080000", label="Vault112PodTermDad", x="0", y="0", z="0"):
    return {
        "logical_ref_formid": ref,
        "winning_file": "Fallout3.esm",
        "base_fixed_formid": "00031190",
        "base_seed_label": label,
        "base_editorid": "Vault112PodTermDad",
        "base_name": "Lounger Monitor -- Subject: Unknown",
        "location_key": "CELL|Fallout3.esm|0001852C",
        "cell_editorid": "Vault112a",
        "position_x": x,
        "position_y": y,
        "position_z": z,
        "initially_disabled": "false",
        "enable_parent_raw": "",
        "owner_raw": "",
        "ref_script_raw": "",
        "base_script_raw": "",
        "full_path": "Fallout3.esm/Vault112a/REFR",
    }


def vault(ref="00081000", editor="OrdinaryObject", name="", x="10", y="0", z="0", term="", **kw):
    row = {
        "logical_ref_formid": ref,
        "winning_file": "Fallout3.esm",
        "base_signature": "MISC",
        "base_fixed_formid": "00070000",
        "base_editorid": editor,
        "base_name": name,
        "position_x": x,
        "position_y": y,
        "position_z": z,
        "initially_disabled": "false",
        "enable_parent_raw": "",
        "owner_raw": "",
        "ref_script_raw": "",
        "base_script_raw": "",
        "storage_identity_term": term,
        "full_path": "Fallout3.esm/Vault112a/REFR",
    }
    row.update(kw)
    return row


def cand(term="storage", form="00090000", sig="SCPT", editor="StorageScript", seed_label="", is_seed="false"):
    return {
        "record_file": "Fallout3.esm",
        "record_signature": sig,
        "record_formid": form,
        "root_fixed_formid": form,
        "record_editorid": editor,
        "record_name": "",
        "matched_term": term,
        "element_path": "SCTX - Script Source",
        "element_value": term,
        "is_seed_record": is_seed,
        "seed_label": seed_label,
        "record_full_path": f"Fallout3.esm/{sig}/{editor}",
    }


class JamesSessionStorageTests(unittest.TestCase):
    def test_monitor_placement_is_source_binding_not_storage_proof(self):
        r = mod.audit([], [], [placed()], [], [])
        self.assertEqual(r["james_monitor_placed_ref_count"], 1)
        self.assertTrue(r["admission"]["james_physical_monitor_placed_instance_bound"])
        self.assertEqual(r["admission"]["james_session_to_persistent_storage"], "NOT_ESTABLISHED_BY_GRAPH_OR_PROXIMITY_ALONE")

    def test_direct_storage_named_link_from_seed_is_candidate_only(self):
        rows = [seed(linked_formid="00077777", linked_editorid="ResidentMemoryStorage", linked_name="Storage")]
        r = mod.audit(rows, [], [], [], [])
        self.assertEqual(r["direct_seed_link_storage_candidate_count"], 1)
        self.assertFalse(r["direct_seed_link_storage_candidates"][0]["james_session_persistence_proven"])
        self.assertFalse(r["claim_ceiling"]["DIRECT_LINK_EQUALS_STORAGE_SEMANTICS"])

    def test_reverse_link_plus_storage_candidate_is_source_bound_not_direction(self):
        r = mod.audit([], [rev()], [], [], [cand()])
        self.assertEqual(r["source_bound_storage_candidate_count"], 1)
        self.assertTrue(r["source_bound_storage_candidates"][0]["source_bound_candidate"])
        self.assertFalse(r["claim_ceiling"]["REVERSE_REFERENCE_EQUALS_PERSISTENCE_DIRECTION"])

    def test_storage_candidate_without_seed_edge_stays_unbound(self):
        r = mod.audit([], [], [], [], [cand(form="00090001")])
        self.assertEqual(r["source_bound_storage_candidate_count"], 0)

    def test_pod_local_storage_object_with_dependency_is_high_priority_only(self):
        rows = [vault(editor="ResidentMemoryStorage", term="storage", enable_parent_raw="SomeParent [00001234]")]
        r = mod.audit([], [], [placed()], rows, [])
        self.assertEqual(r["pod_local_high_priority_count"], 1)
        item = r["pod_local_high_priority_candidates"][0]
        self.assertTrue(item["within_128"])
        self.assertFalse(item["james_session_persistence_proven"])
        self.assertFalse(r["claim_ceiling"]["POD_PROXIMITY_EQUALS_SESSION_STORAGE"])

    def test_far_storage_object_is_not_local_candidate(self):
        rows = [vault(editor="ResidentMemoryStorage", term="storage", x="1500")]
        r = mod.audit([], [], [placed()], rows, [])
        self.assertEqual(r["pod_local_within_1024_count"], 0)

    def test_near_ordinary_clutter_is_not_high_priority(self):
        r = mod.audit([], [], [placed()], [vault()], [])
        self.assertEqual(r["pod_local_within_1024_count"], 1)
        self.assertEqual(r["pod_local_high_priority_count"], 0)

    def test_duplicate_placed_ref_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate placed"):
            mod.audit([], [], [placed(), placed()], [], [])

    def test_duplicate_vault_ref_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate Vault112a"):
            mod.audit([], [], [placed()], [vault(), vault()], [])

    def test_invalid_boolean_fails_closed(self):
        bad = vault(initially_disabled="maybe")
        with self.assertRaisesRegex(ValueError, "true/false"):
            mod.audit([], [], [placed()], [bad], [])

    def test_shared_backend_never_auto_promotes_memory_buffer(self):
        r = mod.audit([], [], [placed()], [], [])
        self.assertFalse(r["claim_ceiling"]["SHARED_BACKEND_EQUALS_SHARED_MEMORY_BUFFER"])
        self.assertFalse(r["claim_ceiling"]["AUTOMATIC_PERSISTENCE_PLAUSIBILITY_EQUALS_PER_SESSION_AUTOPERSISTENCE"])

    def test_seed_storage_keyword_itself_is_still_candidate_only(self):
        r = mod.audit([], [], [], [], [cand(term="memory", form="00031190", sig="TERM", editor="Vault112PodTermDad", seed_label="Vault112PodTermDad", is_seed="true")])
        self.assertEqual(r["source_bound_storage_candidate_count"], 1)
        self.assertFalse(r["source_bound_storage_candidates"][0]["james_session_persistence_proven"])
        self.assertFalse(r["claim_ceiling"]["STORAGE_KEYWORD_EQUALS_MEMORY_PAYLOAD"])


if __name__ == "__main__":
    unittest.main()
