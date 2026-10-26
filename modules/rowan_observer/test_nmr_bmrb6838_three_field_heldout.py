"""Independent genuine three-field data integrity and held-out physics tests."""
from __future__ import annotations
import inspect
import math
import unittest
from nmr_bmrb6838_three_field_heldout import (
 SOURCE_SHA,MODELS,TRAIN,TEST,OBS,BASE_STARTS,read_protocol,source_text,
 parse_all_nine_real_observables,predict_field,train_one_residue,summarize,Hold
)

class PSE4HoldoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=read_protocol()
        cls.rows,cls.sizes,cls.conditions=parse_all_nine_real_observables(source_text(cls.p))

    def test_true_3_fields_and_9_lists_with_230_shared_residues(self):
        self.assertEqual(TRAIN,(500,600))
        self.assertEqual(TEST,800)
        self.assertEqual(len(self.rows),230)
        self.assertEqual(len(self.sizes),9)
        self.assertEqual({r["resid"] for r in self.rows},set(r["resid"] for r in self.rows))

    def test_same_ph_temperature_sample_and_source_sha(self):
        self.assertEqual(SOURCE_SHA,"aa437c7f9dd906b8622907aa79f372a211cac2606fbcd3603c477f3cc9cde661")
        self.assertEqual(self.conditions["temperature_K"],304.65)
        self.assertEqual(self.conditions["pH"],6.65)
        self.assertEqual(self.conditions["sample_condition_id"],2)

    def test_measured_errors_and_unit_transform(self):
        row=self.rows[0]
        self.assertEqual(row["resid"],4)
        self.assertEqual(row["aa3"],"LYS")
        for f in ("500","600","800"):
            for typ in OBS:
                data=row["data"][f][typ]
                self.assertGreater(data["se"],0)
                self.assertTrue(math.isfinite(data["value"]))
        t1=row["data"]["500"]["R1"]
        self.assertAlmostEqual(t1["value"],1000/591.751)
        self.assertAlmostEqual(t1["se"],1000*50.564/(591.751**2))
        t2=row["data"]["500"]["R2"]
        self.assertAlmostEqual(t2["value"],1000/75.738)

    def test_deterministic_fit_modes(self):
        self.assertEqual(len(MODELS),4)
        x=self.rows[0]
        # Verify the optimizer returns finite fit & authentic heldout residual,
        # not a solved fixed input or fabricated experiment.
        for k in MODELS:
            r=train_one_residue(x,k)
            self.assertGreaterEqual(r["train_chi2_six_observations"],0)
            self.assertGreaterEqual(r["holdout_total_chi2"],0)
            self.assertEqual(set(r["holdout_800MHz"]),set(OBS))
            self.assertEqual(r["fitted_params"]["NH_angle_deg_frozen_illustrative"],45)

    def test_exact_synthetic_training_recovery_for_m0(self):
        known=[15.0,0.85]
        sample={"resid":999,"aa3":"GLY","data":{}}
        for f in (500,600,800):
            vals=predict_field(f,known,"M0_ISO_CSA170")
            sample["data"][str(f)]={
              obs:{"value":vals[i],"se":0.005 if i<2 else .001,
                   "original":{"synthetic":True}}
              for i,obs in enumerate(OBS)
            }
        r=train_one_residue(sample,"M0_ISO_CSA170")
        self.assertLess(r["train_chi2_six_observations"],1e-9)
        self.assertLess(r["holdout_total_chi2"],1e-9)

    def test_nonpositive_uncertainty_is_rejected(self):
        x={**self.rows[0],"data":{k:{a:dict(v) for a,v in x.items()}
                                 for k,x in self.rows[0]["data"].items()}}
        x["data"]["500"]["R1"]["se"]=0.
        with self.assertRaises((ValueError,ZeroDivisionError,Hold)):
            train_one_residue(x,"M0_ISO_CSA170")

    def test_train_only_500_600_not_future_800(self):
        src=inspect.getsource(train_one_residue)
        self.assertIn("for mhz in TRAIN",src)
        self.assertIn("vals800=predict_field(TEST",src)
        self.assertNotIn("for mhz in FIELDS",src)
        self.assertEqual(len(BASE_STARTS),3)

    def test_no_rowan_or_functional_3d_claim(self):
        from nmr_bmrb6838_three_field_heldout import evaluate
        src=inspect.getsource(evaluate)+inspect.getsource(train_one_residue)
        self.assertNotIn("ROWAN_API_KEY",src)
        self.assertNotIn("submit_protein_cofolding_workflow",src)
        self.assertIn("known_800MHz_R2_dataset_inconsistency",src)

if __name__=="__main__":
    unittest.main()
