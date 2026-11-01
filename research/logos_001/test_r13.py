"""R1.3 frozen observed data, source verification and adversarial evidence gates."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import r13_data
import r13_discover
import r13_witness

class R13ScientificGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw=r13_data.discovery_input()
        cls.proposal=r13_discover.discover(cls.raw)

    def test_provenance_and_group_disjointness(self):
        for name,(_,n,uni,counts,sha) in r13_data.SPECS.items():
            observed=r13_data.observed(name)
            self.assertEqual(len(observed),n)
            self.assertEqual(len(set(x for x,y in observed)),uni)
            d=r13_data.split(name)
            self.assertEqual(tuple(len(d[k]) for k in ("train","validation","test")),counts)
            ss=[{x for x,y in d[k]} for k in ("train","validation","test")]
            self.assertFalse(ss[0]&ss[1] or ss[0]&ss[2] or ss[1]&ss[2])

    def test_discovery_has_no_test_labels(self):
        self.assertEqual(len(self.raw["cases"]),6)
        for case in self.raw["cases"]:
            self.assertEqual(set(case),{"id","train","validation"})
        self.assertEqual(self.proposal["input_access"],"TRAIN_VALIDATION_ONLY_NO_HOLDOUT")

    def test_scoring_and_heldout_falsifiers(self):
        result=r13_witness.verify(self.proposal)
        self.assertEqual(result["total_real_datasets"],3)
        self.assertEqual(result["negative_controls_rejected"],3)
        self.assertFalse(result["production_model_promotion_allowed"])
        self.assertEqual(result["integrity"],"PASS_SOURCE_AND_PROPOSAL_CHECKS")

    def test_four_integrity_tamper_checks(self):
        checks=r13_witness.tamper_checks(self.proposal)
        self.assertEqual(set(checks),{"digest","model_coefficient","model_injection","negative_promotion"})
        self.assertTrue(all(x=="REJECTED" for x in checks.values()))

    def test_leakage_blocked(self):
        malformed=copy.deepcopy(self.raw)
        malformed["cases"][0]["test"]=[[0,0]]
        with self.assertRaises(ValueError):
            r13_discover.discover(malformed)

    def test_invalid_values_blocked(self):
        bad=copy.deepcopy(self.raw)
        bad["cases"][0]["train"][0][1]=float("nan")
        with self.assertRaises(ValueError):r13_discover.discover(bad)

if __name__=="__main__":unittest.main()
