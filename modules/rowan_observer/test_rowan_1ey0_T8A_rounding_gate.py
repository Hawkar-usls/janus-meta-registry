"""Independent unit checks for honest Rowan pTM precision statements."""
import copy
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).with_name("rowan_1ey0_T8A_rounding_gate.py")
spec = importlib.util.spec_from_file_location("janus_topa_rounding", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def fixture():
    return {
        "status": mod.EXPECTED_STATUS,
        "rowan": {"WT_ptm": .943, "T8A_ptm": .940, "provider_result": "Status.COMPLETED_OK",
                  "extra_jobs_created_on_collection": 0},
        "local": {"WT_ptm": .9377234578132629, "T8A_ptm": .9397260546684265},
        "cross_provider": {"provider_equivalence_proven": False, "protein_fitness_or_DDG_inference": False},
        "firewalls": {f: False for f in ("experimental_DDG_labels_accessed", "genuine_blind_validation",
                    "independent_unpublished_custodian", "FireProt_210_scale_up_authorized",
                    "additional_protein_mutations_authorized", "shadow_weights_retrained",
                    "production_model_promoted")}
    }

class PrecisionGate(unittest.TestCase):
    def test_sign_remains_opposite_under_rounding(self):
        r = mod.audit(fixture())
        self.assertEqual(r["rowan_rounding_only_delta_lower"], "-0.004")
        self.assertEqual(r["rowan_rounding_only_delta_upper"], "-0.002")
        self.assertTrue(r["sign_disagreement_survives_three_decimal_rounding"])
        self.assertFalse(r["stochasticity_quantified"])
        self.assertEqual(r["new_rowan_jobs"], 0)

    def test_no_blind_validation_without_custody(self):
        f = fixture()
        f["firewalls"]["genuine_blind_validation"] = True
        with self.assertRaisesRegex(mod.GateHold, "SCIENTIFIC_FIREWALL"):
            mod.audit(f)

    def test_no_promotion_or_scaleup(self):
        for name in ("FireProt_210_scale_up_authorized", "shadow_weights_retrained", "production_model_promoted"):
            with self.subTest(name=name):
                f = fixture()
                f["firewalls"][name] = True
                with self.assertRaises(mod.GateHold):
                    mod.audit(f)

    def test_no_precision_fabrication(self):
        f = fixture()
        f["rowan"]["T8A_ptm"] = 0.9402
        with self.assertRaisesRegex(mod.GateHold, "ROWAN_PRECISION"):
            mod.audit(f)

    def test_no_sign_difference_means_hold(self):
        f = fixture()
        f["rowan"]["T8A_ptm"] = 0.947
        with self.assertRaisesRegex(mod.GateHold, "SIGN_SEPARATION"):
            mod.audit(f)

    def test_not_completed_provider_rejected(self):
        f = fixture()
        f["rowan"]["provider_result"] = "Status.RUNNING"
        with self.assertRaisesRegex(mod.GateHold, "PROVIDER_NOT_FROZEN_COMPLETE"):
            mod.audit(f)

    def test_reject_claimed_provider_equivalence(self):
        f = fixture()
        f["cross_provider"]["provider_equivalence_proven"] = True
        with self.assertRaisesRegex(mod.GateHold, "FALSE_PROVIDER_EQUIVALENCE"):
            mod.audit(f)

if __name__ == "__main__":
    unittest.main()
