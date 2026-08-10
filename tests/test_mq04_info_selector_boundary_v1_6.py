import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "tools/verify_mq04_info_selector_boundary_v1_6.py"
spec = importlib.util.spec_from_file_location("mq04info", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def idx(info="00001000", topic="00002000"):
    return {
        "info_logical_formid": info,
        "winning_file": "Fallout3.esm",
        "topic_logical_formid": topic,
        "topic_editorid": "MQ04TestTopic",
        "topic_name": "Test Topic",
        "speaker_raw": "",
        "speaker_formid": "",
        "speaker_editorid": "Betty",
        "previous_topic_raw": "",
        "previous_info_raw": "",
        "full_path": f"Fallout3.esm/DIAL/{topic}/INFO/{info}",
    }


def leaf(value, info="00001000", topic="00002000", section="BEGIN_SCRIPT",
         name="Embedded Script Source", linked_editorid="", linked_formid="",
         linked_signature=""):
    return {
        "info_logical_formid": info,
        "topic_logical_formid": topic,
        "section": section,
        "element_path": f"Script/{name}",
        "element_name": name,
        "element_value": value,
        "linked_file": "Fallout3.esm" if linked_formid else "",
        "linked_signature": linked_signature,
        "linked_formid": linked_formid,
        "linked_editorid": linked_editorid,
    }


class MQ04InfoSelectorBoundaryTests(unittest.TestCase):
    def test_daddoginfo_result_is_disclosure_not_memory_mutation(self):
        r = mod.audit([idx()], [leaf("set MQ04.DadDogInfo to 1")])
        item = r["records"][0]
        self.assertIn("DISCLOSURE_FLAG_RESULT", item["tags"])
        self.assertEqual(r["high_priority_selector_persistence_candidate_count"], 0)
        self.assertFalse(r["claim_ceiling"]["DADDOGINFO_EQUALS_CARRIER_BINDING"])

    def test_brauninfo_result_is_not_admin_serializer(self):
        r = mod.audit([idx()], [leaf("set MQ04.BraunInfo to 1")])
        self.assertIn("DISCLOSURE_FLAG_RESULT", r["records"][0]["tags"])
        self.assertFalse(r["claim_ceiling"]["BRAUNINFO_EQUALS_ADMIN_SERIALIZER"])

    def test_npcreset_result_is_state_trigger_not_memory_export(self):
        r = mod.audit([idx()], [leaf("set MQ04.NPCReset to 1")])
        self.assertIn("RESET_OR_RELOAD_RESULT", r["records"][0]["tags"])
        self.assertFalse(r["claim_ceiling"]["NPCRESET_EQUALS_MEMORY_EXPORT"])

    def test_same_info_james_persistence_convergence_is_candidate_only(self):
        rows = [
            leaf("MQ04Doc persist memory to storage"),
        ]
        r = mod.audit([idx()], rows)
        self.assertEqual(r["high_priority_selector_persistence_candidate_count"], 1)
        item = r["high_priority_selector_persistence_candidates"][0]
        self.assertTrue(item["james_source_bound_candidate"])
        self.assertTrue(item["operation_term_in_result"])
        self.assertFalse(item["direct_james_memory_to_carrier_binding_proven"])
        self.assertFalse(r["claim_ceiling"]["HIGH_PRIORITY_CANDIDATE_EQUALS_PASS"])

    def test_terms_in_different_infos_do_not_converge(self):
        indexes = [idx("00001000", "00002000"), idx("00001001", "00002001")]
        leaves = [
            leaf("MQ04Doc", info="00001000", topic="00002000"),
            leaf("write memory chip", info="00001001", topic="00002001"),
        ]
        r = mod.audit(indexes, leaves)
        self.assertEqual(r["high_priority_selector_persistence_candidate_count"], 0)

    def test_unknown_user_never_promotes_to_james(self):
        r = mod.audit([idx()], [leaf("User UNKNOWN Altered by S. Braun", section="RESPONSES", name="Response Text")])
        item = r["records"][0]
        self.assertTrue(item["unknown_user_mentioned"])
        self.assertFalse(item["unknown_user_equals_james_proven"])
        self.assertFalse(r["claim_ceiling"]["USER_UNKNOWN_EQUALS_JAMES"])

    def test_compiled_without_source_requires_manual_decompile(self):
        rows = [leaf("01 02 03 04", name="Compiled Embedded Script")]
        r = mod.audit([idx()], rows)
        self.assertEqual(r["compiled_only_result_script_count"], 1)
        self.assertIn("COMPILED_ONLY_RESULT_SCRIPT", r["records"][0]["tags"])
        self.assertFalse(r["claim_ceiling"]["COMPILED_ONLY_SCRIPT_EQUALS_HIDDEN_SERIALIZER"])

    def test_leaf_for_absent_info_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "absent INFO"):
            mod.audit([idx()], [leaf("x", info="DEADBEEF")])

    def test_duplicate_info_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate MQ04 INFO"):
            mod.audit([idx(), idx()], [])

    def test_linked_james_form_can_bind_source_candidate_but_not_direction(self):
        rows = [
            leaf("persist memory", linked_editorid="Vault112PodTermDad",
                 linked_formid="00031190", linked_signature="TERM"),
        ]
        r = mod.audit([idx()], rows)
        item = r["records"][0]
        self.assertTrue(item["james_source_bound_candidate"])
        self.assertEqual(r["high_priority_selector_persistence_candidate_count"], 1)
        self.assertFalse(item["direct_james_memory_to_carrier_binding_proven"])
        self.assertFalse(r["claim_ceiling"]["SAME_INFO_TERM_CONVERGENCE_EQUALS_WRITE_DIRECTION"])


if __name__ == "__main__":
    unittest.main()
