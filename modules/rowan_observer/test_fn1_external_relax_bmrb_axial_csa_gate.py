"""Independent published nmr-relax fixture and source authenticity scientific firewalls."""
import inspect
import json
import math
import unittest
import fn1_external_relax_bmrb_axial_csa_gate as m

class ExternalBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol=json.loads(m.PROTOCOL.read_text(encoding="utf8"))

    def test_external_independent_r1_r2_noe_at_three_fields(self):
        x=m.independent_relax_comparison(self.protocol)
        self.assertEqual(len(x),3)
        self.assertEqual({p["proton_MHz"] for p in x},{400,600,800})
        self.assertTrue(all(row["max_absolute_relax_R1_R2_NOE_error"]<1e-10 for row in x))

    def test_external_ref_sha_commit_frozen(self):
        s=self.protocol["independent_software"]
        self.assertEqual(s["source_file_sha256"],"b149bfb6f3f328020ae71268bcc12b05d90188d160b20c7b42866b60fd83ebd7")
        self.assertEqual(s["commit"],"c48b81e4042f12df1610c8fd32a79448ff857783")
        self.assertEqual(len(s["fixtures"]),3)

    def test_spherical_limit_invariant_to_angle(self):
        x=[m.rates(600,axial_ratio=1,angle_deg=angle)[0] for angle in (0,45,90,180)]
        for row in x[1:]:
            for u,v in zip(row,x[0]):
                self.assertAlmostEqual(u,v,places=11)

    def test_anisotropic_and_axial_angle_variation(self):
        a=m.rates(600,axial_ratio=2,angle_deg=0)[0]
        b=m.rates(600,axial_ratio=2,angle_deg=90)[0]
        self.assertGreater(abs(a[1]-b[1]),1e-5)

    def test_variation_csa_matters(self):
        a=m.rates(600,csa_ppm=-155)[0]
        b=m.rates(600,csa_ppm=-185)[0]
        self.assertGreater(abs(a[0]-b[0]),1e-3)
        self.assertGreater(abs(a[1]-b[1]),1e-3)

    def test_sensitivity_fixed_81_cases_each_field(self):
        x=m.sensitivity()
        self.assertEqual(x["cases_count"],81)
        self.assertEqual({y["proton_MHz"] for y in x["cases"]},{400,600,800})
        self.assertEqual(sum(y["proton_MHz"]==600 for y in x["cases"]),27)

    def test_BMRB_metadata_never_multifield(self):
        x=self.protocol["published_data"]
        self.assertEqual(x["source_sha256"],"12286a75fe8d1d6a2d7f0b078a4e5981f633c8670285e40dfd2c13da34ec2b7d")
        self.assertEqual(x["all_six_proton_spectrometer_frequency_MHz"],600)
        self.assertEqual(len(x["dataset_type"]),6)

    def test_BMRB_live_published_all_six_source(self):
        source=m.get_bmrb(self.protocol)
        maps=m.parse_bmrb_frames(source)
        self.assertEqual(len(maps),6)
        self.assertTrue(all(len(val)==68 for val in maps.values()))
        summary=m.summarize_bmrb(maps)
        self.assertTrue(all(x["n_common_residues"]==68 for x in summary.values()))

    def test_no_provider_call_or_3D_conformer_inference(self):
        source=inspect.getsource(m)
        self.assertNotIn("submit_protein_cofolding_workflow",source)
        self.assertNotIn("ROWAN_API_KEY",source)
        self.assertNotIn("rowan.get_workflow",source)

    def test_input_diffusion_guard(self):
        with self.assertRaises(m.Hold): m.density(0,6,.8,.1,0.,45)
        with self.assertRaises(m.Hold): m.rates(600,csa_ppm=600)

if __name__=="__main__":
    unittest.main()
