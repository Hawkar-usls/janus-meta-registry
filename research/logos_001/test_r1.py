"""Self-contained protocol guards; run using Python stdlib unittest."""
import copy
import json
import math
import unittest
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import r1_data
import r1_discover
import r1_witness

class ScientificGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset=r1_data.generate()
        cls.candidates=r1_discover.discover(cls.dataset)

    def test_frozen_case_count_and_training_only(self):
        self.assertEqual(len(self.dataset["cases"]),6)
        self.assertEqual(set(self.dataset),{"experiment","phase","protocol","cases"})
        self.assertEqual(self.candidates["data_access"],"TRAIN_AND_VALIDATION_ONLY__NO_TEST")
        for case in self.dataset["cases"]:
            self.assertEqual(set(case),{"id","train","validation"})

    def test_positive_laws_and_negative_controls(self):
        result=r1_witness.verify(self.candidates)
        self.assertEqual(result["positive_holdout_passes"],4)
        self.assertEqual(result["negative_controls_rejected"],2)
        self.assertEqual(result["cases"][-1]["decision"],"REJECTED_REGIME_SHIFT")

    def test_tampered_claims_are_rejected(self):
        result=r1_witness.tamper_tests(self.candidates)
        self.assertEqual(len(result["tamper_trials"]),4)
        self.assertTrue(all(v=="REJECTED" for v in result["tamper_trials"].values()))

    def test_input_leakage_and_malformed_data_blocked(self):
        x=copy.deepcopy(self.dataset)
        x["cases"][0]["test"]=[[1.0,1.0]]
        with self.assertRaises(ValueError):
            r1_discover.discover(x)
        x=copy.deepcopy(self.dataset)
        x["cases"][0]["train"][0][1]=float("nan")
        with self.assertRaises(ValueError):
            r1_discover.discover(x)

    def test_wrong_case_list_is_rejected(self):
        x=copy.deepcopy(self.candidates)
        x["cases"][2]["id"]="C04"
        with self.assertRaises(ValueError):
            r1_witness.verify(x)

    def test_uncertified_basis_is_rejected(self):
        x=copy.deepcopy(self.candidates)
        x["cases"][0]["model"]["basis"]=["eval"]
        with self.assertRaises(ValueError):
            r1_witness.verify(x)

if __name__=="__main__":
    unittest.main()
