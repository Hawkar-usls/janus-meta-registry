"""Frozen R1.2 scientific contract tests. All results remain reportable."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import r12_data
import r12_discover
import r12_witness

class LogosR12(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset=r12_data.discovery()
        cls.result=r12_discover.run(cls.dataset)

    def test_original_source_blob_and_split_counts(self):
        r12_witness.verify_source_git_blobs()
        for name,(_,_,counts) in r12_data.EXPECTED.items():
            x=r12_data.split(name)
            self.assertEqual(tuple(len(x[key]) for key in ("train","validation","test")),counts)
            self.assertFalse({z for z,y in x["train"]}&{z for z,y in x["test"]})
            self.assertFalse({z for z,y in x["validation"]}&{z for z,y in x["test"]})

    def test_no_test_labels_enter_discoverer(self):
        self.assertEqual(set(self.dataset),{"experiment","phase","source","cases"})
        for c in self.dataset["cases"]:
            self.assertEqual(set(c),{"id","train","validation"})

    def test_separate_witness_scientific_result(self):
        witness=r12_witness.verify(self.result)
        self.assertEqual(witness["integrity_verdict"],"PASS_CODE_AND_SOURCE_INTEGRITY")
        self.assertFalse(witness["production_model_promotion_allowed"])
        self.assertEqual(witness["negative_controls_rejected"],2)
        self.assertIn(witness["scientific_performance"],(
            "BOTH_DATASETS_BEAT_BASELINE_GE_5PCT",
            "NOT_COMPETITIVE_IN_ALL_PREDECLARED_DATASETS"))

    def test_four_rejected_falsifiers(self):
        self.assertEqual(len(r12_witness.tamper_tests(self.result)),4)

    def test_test_set_in_input_is_rejected(self):
        d=copy.deepcopy(self.dataset)
        d["cases"][0]["test"]=[[0.,0.]]
        with self.assertRaises(ValueError):r12_discover.run(d)

    def test_nan_and_malicious_family_rejected(self):
        d=copy.deepcopy(self.dataset)
        d["cases"][0]["train"][0][1]=float("nan")
        with self.assertRaises(ValueError):r12_discover.run(d)
        e=copy.deepcopy(self.result)
        e["cases"][0]["decision"]="PROPOSE"
        e["cases"][0]["model"]={"template":{"family":"exec"},"coefficients":[0.,0.]}
        with self.assertRaises((ValueError,KeyError)):r12_witness.verify(e)

if __name__=="__main__":
    unittest.main()
