"""No-network tests for the NMR physical forward equations and epistemic gates."""
import inspect
import json
import math
import unittest

import fn1_nmr_twoscale_forward_gate as m

class Physical15NForwardTests(unittest.TestCase):
    def test_spectral_density_even_positive_and_nonzero(self):
        for x in (0,m.OMEGA_N,m.OMEGA_H,m.OMEGA_H+m.OMEGA_N):
            j=m.spectral_density(x,0.1,6.0,0.25)
            self.assertGreaterEqual(j,0)
            self.assertAlmostEqual(j,m.spectral_density(-x,0.1,6,0.25),places=17)

    def test_spectral_density_endpoint_degeneracy(self):
        # At w=1 the slow timescale drops out exactly; at w=0 fast drops out.
        self.assertEqual(m.spectral_density(m.OMEGA_N,0.1,3.0,1),
                         m.spectral_density(m.OMEGA_N,0.1,15,1))
        self.assertEqual(m.spectral_density(m.OMEGA_N,0.05,8,0),
                         m.spectral_density(m.OMEGA_N,1,8,0))

    def test_15N_gyromagnetic_sign_and_millisecond_units(self):
        self.assertLess(m.GAMMA_15N,0)
        t1,t2,noe=m.predict(0.1,7,0.1,0)
        self.assertGreater(t1,100)
        self.assertLess(t1,3000)
        self.assertGreater(t2,30)
        self.assertLess(t2,2000)
        self.assertLess(noe,1.0)

    def test_rex_only_increases_R2(self):
        a=m.predict(0.2,6,0.4,0)
        b=m.predict(0.2,6,0.4,4)
        self.assertEqual(a[0],b[0])
        self.assertEqual(a[2],b[2])
        self.assertLess(b[1],a[1])
        with self.assertRaisesRegex(m.Hold,"REX"):m.predict(0.2,6,0.4,-1)

    def test_synthetic_true_point_is_accepted(self):
        T1,T2,noe=m.predict(0.1,6.0,0.25,2)
        row={
          "si_residue":61,"residue":"Val","category":"OBSERVED_INTERDOMAIN_LINKER",
          "T1_ms":T1,"T2_ms":T2,"het_NOE":noe,
          "T1_uncertainty_ms":.1,"T2_uncertainty_ms":.1,"NOE_uncertainty":.001
        }
        r=m.score_single(row,m.REX_SENSITIVITY)
        self.assertGreater(r["T1_T2_accept_count"],0)
        self.assertGreater(r["NOE_independent_2sigma_check_count"],0)

    def test_zero_rex_is_subset_of_extended_rex_models(self):
        r=m.read_real_subset()[0]
        a=m.score_single(r,m.REX_NONE)
        b=m.score_single(r,m.REX_SENSITIVITY)
        self.assertGreaterEqual(b["T1_T2_accept_count"],a["T1_T2_accept_count"])
        self.assertGreaterEqual(b["NOE_independent_2sigma_check_count"],a["NOE_independent_2sigma_check_count"])

    def test_strict_original_si_frozen_data_and_uncertainty(self):
        rows=m.read_real_subset()
        self.assertEqual(len(rows),10)
        self.assertEqual({r["si_residue"] for r in rows},{52,53,61,62,63,64,66,69,70,71})
        x=next(r for r in rows if r["si_residue"]==61)
        self.assertEqual(x["T1_uncertainty_ms"],10.12)
        self.assertEqual(x["T2_uncertainty_ms"],2.85)
        self.assertEqual(x["NOE_uncertainty"],.023)

    def test_full_report_fails_closed_on_angle_inference(self):
        obj=m.evaluate()
        self.assertEqual(obj["status"],"EXPLORATORY_FIXED_PHYSICAL_FORWARD_MODEL_ADEQUACY_TEST_COMPLETED")
        for variant in obj["models"].values():
            self.assertEqual(len(variant["individual_residues"]),10)
            self.assertEqual(variant["rows_total"],10)
            for row in variant["individual_residues"]:
                self.assertNotIn("interdomain_angle",row)
                self.assertNotIn("binding_affinity",row)
        self.assertTrue(obj["comparative_scope"]["domain_rotation_angles_not_identifiable"])
        self.assertTrue(obj["comparative_scope"]["no_prospective_blind"])
        self.assertEqual(obj["comparative_scope"]["new_rowan_jobs"],0)

    def test_cannot_submit_or_generate_structure(self):
        src=inspect.getsource(m.evaluate)+inspect.getsource(m.predict)+inspect.getsource(m.main)
        self.assertNotIn("submit_protein_cofolding_workflow",src)
        self.assertNotIn("read_pdb",src)
        self.assertNotIn("model.predict",src)

if __name__=="__main__":
    unittest.main()
