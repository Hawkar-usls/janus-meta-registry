import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD_PATH = ROOT / "tools/verify_vault112_per_lounger_backend_shard_v2_0.py"
spec = importlib.util.spec_from_file_location("shard", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def hardware(ref, kind, base, x, y=0, z=0, sig="ACTI", edid="", name=""):
    return {
        "logical_ref_formid": ref,
        "winning_file": "Fallout3.esm",
        "hardware_kind": kind,
        "base_signature": sig,
        "base_fixed_formid": base,
        "base_editorid": edid,
        "base_name": name,
        "position_x": str(x),
        "position_y": str(y),
        "position_z": str(z),
        "initially_disabled": "false",
        "enable_parent_raw": "",
        "owner_raw": "",
        "ref_script_raw": "",
        "base_script_raw": "",
        "full_path": f"Fallout3.esm/Vault112a/REFR/{ref}",
    }


def monitor(ref="00070001", x=0):
    return hardware(ref, "JAMES_MONITOR", "00031190", x, sig="TERM", edid="Vault112PodTermDad")


def vision(ref="00070010", x=10, base="0002A45B"):
    return hardware(ref, "VISIONTRON", base, x, sig="FURN", edid="Visiontron")


def computer(ref="00070020", x=20, base="00060000", edid="Vault112LoungerComputer"):
    return hardware(ref, "COMPUTER_IDENTITY", base, x, sig="ACTI", edid=edid)


def terminal(ref="00070030", x=20, base="00060010", edid="Vault112Terminal"):
    return hardware(ref, "TERMINAL", base, x, sig="TERM", edid=edid)


def link(owner_formid="00070020", owner_sig="REFR", owner_kind="COMPUTER_IDENTITY", linked="00090000", value="memory storage"):
    return {
        "owner_scope": "PLACED_REF",
        "owner_kind": owner_kind,
        "owner_file": "Fallout3.esm",
        "owner_signature": owner_sig,
        "owner_formid": owner_formid,
        "owner_editorid": "",
        "owner_name": "",
        "element_path": "Test\\Linked",
        "element_name": "Reference",
        "element_value": value,
        "linked_file": "Fallout3.esm",
        "linked_signature": "SCPT",
        "linked_formid": linked,
        "linked_editorid": "ResidentMemoryStorage",
        "linked_name": "",
    }


def reverse(anchor_formid="00070020", anchor_sig="REFR", anchor_kind="COMPUTER_IDENTITY", referencing="00090000"):
    return {
        "anchor_scope": "PLACED_REF",
        "anchor_kind": anchor_kind,
        "anchor_file": "Fallout3.esm",
        "anchor_signature": anchor_sig,
        "anchor_formid": anchor_formid,
        "anchor_editorid": "",
        "anchor_name": "",
        "referencing_file": "Fallout3.esm",
        "referencing_signature": "SCPT",
        "referencing_formid": referencing,
        "referencing_editorid": "ResidentStateScript",
        "referencing_name": "",
        "referencing_full_path": f"Fallout3.esm/SCPT/{referencing}",
    }


def semantic(form="00090000", term="memory", value="resident memory storage"):
    return {
        "record_file": "Fallout3.esm",
        "record_signature": "SCPT",
        "record_formid": form,
        "record_editorid": "ResidentStateScript",
        "record_name": "",
        "matched_term": term,
        "element_path": "SCTX - Script Source",
        "element_name": "Script Source",
        "element_value": value,
        "linked_file": "",
        "linked_signature": "",
        "linked_formid": "",
        "linked_editorid": "",
        "record_full_path": f"Fallout3.esm/SCPT/{form}",
    }


class Vault112ShardTests(unittest.TestCase):
    def test_monitor_nearest_visiontron_is_geometric_only(self):
        r = mod.audit([monitor(), vision()], [], [], [])
        self.assertEqual(len(r["monitor_to_visiontron_candidates"]), 1)
        c = r["monitor_to_visiontron_candidates"][0]
        self.assertEqual(c["visiontron_refid"], "00070010")
        self.assertFalse(c["functional_binding_proven"])
        self.assertFalse(r["claim_ceiling"]["NEAREST_MONITOR_TO_VISIONTRON_EQUALS_FUNCTIONAL_BINDING"])

    def test_exact_distance_tie_is_preserved(self):
        rows = [monitor(x=0), vision("00070010", x=10), vision("00070011", x=-10, base="000B364C")]
        r = mod.audit(rows, [], [], [])
        self.assertTrue(r["monitor_to_visiontron_candidates"][0]["exact_distance_tie"])

    def test_invalid_visiontron_base_fails_closed(self):
        bad = vision(base="DEADBEEF")
        with self.assertRaisesRegex(ValueError, "unexpected base"):
            mod.audit([monitor(), bad], [], [], [])

    def test_nearest_computer_is_candidate_only(self):
        rows = [monitor(), vision(), computer(x=25)]
        r = mod.audit(rows, [], [], [])
        s = r["james_per_lounger_shard_candidates"][0]
        self.assertEqual(s["candidate_refid"], "00070020")
        self.assertFalse(s["james_specific_backend_handle_proven"])
        self.assertFalse(r["claim_ceiling"]["NEAREST_COMPUTER_TO_VISIONTRON_EQUALS_PER_LOUNGER_SHARD"])

    def test_repeated_layout_same_base_across_two_loungers_is_detected_not_proven(self):
        rows = [
            monitor(),
            vision("00070010", x=10),
            vision("00070011", x=1010, base="000B364C"),
            computer("00070020", x=20, base="00060000"),
            computer("00070021", x=1020, base="00060000"),
        ]
        r = mod.audit(rows, [], [], [])
        self.assertEqual(r["james_repeated_layout_shard_candidate_count"], 1)
        self.assertFalse(r["claim_ceiling"]["REPEATED_LAYOUT_EQUALS_FUNCTIONAL_WIRING"])

    def test_different_nearest_bases_do_not_form_repeated_pattern(self):
        rows = [
            monitor(), vision("00070010", x=10), vision("00070011", x=1010, base="000B364C"),
            computer("00070020", x=20, base="00060000"), computer("00070021", x=1020, base="00060001"),
        ]
        r = mod.audit(rows, [], [], [])
        self.assertEqual(r["james_repeated_layout_shard_candidate_count"], 0)

    def test_direct_link_from_james_shard_is_candidate_not_direction(self):
        rows = [monitor(), vision(), computer()]
        r = mod.audit(rows, [link()], [], [])
        self.assertEqual(r["direct_james_backend_link_candidate_count"], 1)
        self.assertFalse(r["direct_james_backend_link_candidates"][0]["persistence_direction_proven"])
        self.assertFalse(r["claim_ceiling"]["DIRECT_LINK_EQUALS_PERSISTENCE_DIRECTION"])

    def test_reverse_reference_intersect_memory_semantics_is_high_priority(self):
        rows = [monitor(), vision(), computer()]
        r = mod.audit(rows, [], [reverse()], [semantic(term="memory")])
        self.assertEqual(r["source_bound_backend_state_candidate_count"], 1)
        self.assertEqual(r["high_priority_memory_persistence_candidate_count"], 1)
        self.assertFalse(r["source_bound_backend_state_candidates"][0]["james_specific_persisted_state_proven"])
        self.assertFalse(r["claim_ceiling"]["HIGH_PRIORITY_CANDIDATE_EQUALS_PASS"])

    def test_reverse_reference_with_backend_only_term_not_high_priority_memory(self):
        rows = [monitor(), vision(), computer()]
        r = mod.audit(rows, [], [reverse()], [semantic(term="resident", value="resident table")])
        self.assertEqual(r["source_bound_backend_state_candidate_count"], 1)
        self.assertEqual(r["high_priority_memory_persistence_candidate_count"], 0)

    def test_semantic_memory_record_without_reverse_edge_stays_unbound(self):
        rows = [monitor(), vision(), computer()]
        r = mod.audit(rows, [], [], [semantic(term="memory")])
        self.assertEqual(r["source_bound_backend_state_candidate_count"], 0)

    def test_duplicate_hardware_ref_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate hardware"):
            mod.audit([monitor(), monitor()], [], [], [])

    def test_static_monitor_is_explicitly_not_dynamic_memory_store(self):
        r = mod.audit([monitor(), vision()], [], [], [])
        self.assertFalse(r["admission"]["lounger23_monitor_is_dynamic_memory_store"])
        self.assertEqual(r["admission"]["james_specific_persisted_memory_state"], "NOT_ESTABLISHED")

    def test_shared_backend_never_auto_promotes_shared_memory_buffer(self):
        r = mod.audit([monitor(), vision()], [], [], [])
        self.assertFalse(r["claim_ceiling"]["THINK_MACHINE_SHARED_BACKEND_EQUALS_SHARED_MEMORY_BUFFER"])


if __name__ == "__main__":
    unittest.main()
