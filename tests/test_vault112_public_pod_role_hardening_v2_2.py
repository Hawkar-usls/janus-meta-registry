from __future__ import annotations

import unittest

from tools.verify_vault112_public_pod_role_hardening_v2_2 import audit


def row(refid: str, base: str, x: float, y: float = 0.0, z: float = 0.0, *, edid: str = "") -> dict[str, str]:
    return {
        "logical_ref_formid": refid,
        "winning_file": "Fallout3.esm",
        "base_signature": "ACTI" if base != "00031190" else "TERM",
        "base_fixed_formid": base,
        "base_editorid": edid,
        "base_name": "Tranquility Lounger" if base != "00031190" else "",
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
        "base_model_raw": "",
        "full_path": "GRUP/CELL/REFR",
    }


class PublicPodRoleHardeningTests(unittest.TestCase):
    def test_player_pod_closer_than_dad_is_not_james_candidate(self):
        data = [
            row("00000001", "00031190", 0),
            row("00000002", "0002A45B", 10, edid="MQ04PlayerPodActivator"),
            row("00000003", "000B364C", 100, edid="TLpod01"),
        ]
        out = audit(data)
        b = out["monitor_role_bound_bindings"][0]
        self.assertTrue(b["nearest_any_would_conflict_with_role_if_used_as_james"])
        self.assertEqual(b["dad_role_candidate_count"], 1)
        self.assertEqual(b["dad_role_candidates"][0]["base_formid"], "000B364C")
        self.assertIsNone(b["exact_james_pod_refid"])

    def test_broken_pod_closer_is_excluded(self):
        data = [
            row("00000001", "00031190", 0),
            row("00000002", "000B06D4", 5, edid="TLpodBroken"),
            row("00000003", "000572D6", 50, edid="MQ04PodDad"),
        ]
        out = audit(data)
        b = out["monitor_role_bound_bindings"][0]
        self.assertTrue(b["nearest_any_would_conflict_with_role_if_used_as_james"])
        self.assertEqual(b["dad_role_candidates"][0]["base_formid"], "000572D6")

    def test_only_player_pod_fails_closed(self):
        data = [row("00000001", "00031190", 0), row("00000002", "0002A45B", 8)]
        b = audit(data)["monitor_role_bound_bindings"][0]
        self.assertEqual(b["classification"], "NO_ROLE_BOUND_DAD_POD_PLACEMENT_IN_INPUT")
        self.assertEqual(b["dad_role_candidate_count"], 0)
        self.assertFalse(b["unique_role_bound_candidate"])

    def test_both_dad_role_bases_preserve_ambiguity(self):
        data = [
            row("00000001", "00031190", 0),
            row("00000002", "000B364C", 20),
            row("00000003", "000572D6", 30),
        ]
        b = audit(data)["monitor_role_bound_bindings"][0]
        self.assertEqual(b["dad_role_candidate_count"], 2)
        self.assertFalse(b["unique_role_bound_candidate"])
        self.assertEqual(b["classification"], "MULTIPLE_DAD_ROLE_PLACEMENTS_REQUIRE_PRIMARY_INSTANCE_BINDING")
        self.assertIsNone(b["exact_james_pod_refid"])

    def test_exact_dad_distance_tie_is_preserved(self):
        data = [
            row("00000001", "00031190", 0),
            row("00000002", "000B364C", 20),
            row("00000003", "000572D6", -20),
        ]
        b = audit(data)["monitor_role_bound_bindings"][0]
        self.assertTrue(b["nearest_dad_distance_tie"])
        self.assertEqual(b["classification"], "MULTIPLE_DAD_ROLE_PLACEMENTS_DISTANCE_TIE_PRESERVED")

    def test_mq04poddad_is_recognized_as_dad_named_candidate(self):
        data = [row("00000001", "00031190", 0), row("00000002", "000572D6", 12)]
        b = audit(data)["monitor_role_bound_bindings"][0]
        self.assertEqual(b["dad_role_candidates"][0]["base_role"], "DAD_NAMED_BASE_CANDIDATE")
        self.assertFalse(b["role_evidence_proves_exact_placement"])

    def test_tlpod01_is_recognized_as_dad_script_candidate(self):
        data = [row("00000001", "00031190", 0), row("00000002", "000B364C", 12)]
        b = audit(data)["monitor_role_bound_bindings"][0]
        self.assertEqual(b["dad_role_candidates"][0]["base_role"], "DAD_SCRIPT_BOUND_BASE_CANDIDATE")
        self.assertFalse(b["dad_role_candidates"][0]["james_pod_instance_proven"])

    def test_duplicate_refid_fails_closed(self):
        data = [row("00000001", "00031190", 0), row("00000001", "000B364C", 10)]
        with self.assertRaisesRegex(ValueError, "duplicate logical RefID"):
            audit(data)

    def test_nonnumeric_coordinate_fails_closed(self):
        bad = row("00000001", "00031190", 0)
        bad["position_x"] = "not-a-number"
        with self.assertRaisesRegex(ValueError, "must be numeric"):
            audit([bad, row("00000002", "000B364C", 10)])

    def test_public_role_evidence_never_promotes_persisted_state(self):
        data = [row("00000001", "00031190", 0), row("00000002", "000B364C", 10)]
        out = audit(data)
        self.assertFalse(out["admission"]["public_derived_role_evidence_can_prove_exact_james_placed_ref"])
        self.assertEqual(out["admission"]["james_specific_persisted_memory_state"], "NOT_ESTABLISHED")
        self.assertFalse(out["claim_ceiling"]["TTW_DERIVED_XML_EQUALS_VANILLA_ALL_REFR_DUMP"])


if __name__ == "__main__":
    unittest.main()
