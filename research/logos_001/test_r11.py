"""NIST R1.1 source integrity, forbidden information and independent controls."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import r11_data
import r11_discover
import r11_witness

class NistR11Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=r11_data.discovery()
        cls.output=r11_discover.run(cls.data)

    def test_real_nist_counts_and_group_holdout(self):
        self.assertEqual(len(r11_data.PONTIUS),40)
        self.assertEqual(len(r11_data.NORRIS),36)
        self.assertEqual((len(r11_data.split("PONTIUS")["train"]),
                          len(r11_data.split("PONTIUS")["validation"]),
                          len(r11_data.split("PONTIUS")["test"])),(24,8,8))
        self.assertEqual((len(r11_data.split("NORRIS")["train"]),
                          len(r11_data.split("NORRIS")["validation"]),
                          len(r11_data.split("NORRIS")["test"])),(21,7,8))
        p=r11_data.split("PONTIUS")
        self.assertFalse({x for x,y in p["train"]} & {x for x,y in p["test"]})

    def test_no_test_values_in_discovery_input(self):
        for d in self.data["datasets"]:
            self.assertEqual(set(d),{"id","train","validation"})
        self.assertEqual(set(self.output),{"experiment","phase","generator","source_sha256","cases","provenance","scientific_limit"})

    def test_independent_verification_and_negative_controls(self):
        result=r11_witness.check(self.output)
        self.assertEqual(result["corrupted_pairing_controls_rejected"],2)
        self.assertEqual(result["verdict"],"PASS_SCIENTIFIC_EVALUATION_INTEGRITY")

    def test_tampered_evidence_rejected(self):
        t=r11_witness.tamper_checks(self.output)
        self.assertEqual(len(t),4)
        self.assertTrue(all(value=="REJECTED" for value in t.values()))

    def test_untrusted_holdout_field_rejected(self):
        x=copy.deepcopy(self.data)
        x["datasets"][0]["test"]=[[0.,0.]]
        with self.assertRaises(ValueError):r11_discover.run(x)

    def test_nonfinite_training_value_rejected(self):
        x=copy.deepcopy(self.data)
        x["datasets"][0]["train"][0][1]=float("nan")
        with self.assertRaises(ValueError):r11_discover.run(x)

if __name__=="__main__":unittest.main()
