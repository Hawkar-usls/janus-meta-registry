"""Authenticated independent azurin BMRB6243/1E5Y three-field regression tests."""
import importlib.util,inspect,unittest

REQUIRES=("numpy","scipy","pynmrstar","Bio")
@unittest.skipUnless(all(importlib.util.find_spec(x) for x in REQUIRES),
 "Pinned NMR science dependencies are only installed in dedicated test job")
class RealAzurinTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  import nmr_azurin6243_1e5y_structural_holdout as m
  cls.m=m
  import json
  cls.p=json.loads(m.PROTO.read_text(encoding="utf8"))
  raw=m.load_raw(cls.p["source"]["nmr_url"],cls.p["source"]["nmr_sha256"],323833)
  pdb=m.load_raw(cls.p["source"]["pdb_url"],cls.p["source"]["pdb_sha256"],471185)
  cls.sequence,cls.data,cls.conditions=m.parse_nmr(raw.decode("utf-8"))
  cls.polar,cls.omitted,cls.geometry=m.structural_theta(pdb,cls.sequence)

 def test_source_9rows_both_temperatures(self):
  self.assertEqual({k:len(v) for k,v in self.data.items()},{1:116,2:114})
  self.assertEqual(self.conditions[1]["temperature"],289)
  self.assertEqual(self.conditions[2]["temperature"],317)
  self.assertEqual(self.conditions[1]["pH"],5.5)

 def test_native_128aa_PDB_residue_alignment(self):
  self.assertEqual(len(self.sequence),128)
  self.assertEqual(self.geometry["experimental_PDB"],"1E5Y")
  self.assertGreater(len(self.polar),100)
  self.assertEqual(len(set(self.polar)|set(self.omitted)),128)
  self.assertTrue(all(0<=theta<=90 for theta in self.polar.values()))

 def test_planned_global_axis_is_PCA_not_measured_tensor(self):
  self.assertFalse(self.geometry["diffusion_axis_independently_measured"])
  self.assertFalse(self.geometry["hydrogen_positions_directly_observed"])
  self.assertEqual(len(self.geometry["axis_xyz"]),3)

 def test_measured_relaxation_is_seconds_and_inverse_converted(self):
  row=next(r for r in self.data[1] if r["pos"]==2)
  t=row["data"]["500"]["R1"]
  self.assertAlmostEqual(t["value"],1/0.8126)
  self.assertAlmostEqual(t["SE"],0.0025/(0.8126**2))
  self.assertEqual(row["aa3"],"GLU")

 def test_exact_synthetic_forward_s2_recovery(self):
  m=self.m
  rate=m.rates(500,tm_ns=10,s2=0.75,csa_ppm=-170,axial_ratio=1)[0]
  row={"data":{}}
  for mhz in (500,600,800):
   p=m.rates(mhz,tm_ns=10,s2=0.75,csa_ppm=-170,axial_ratio=1)[0]
   row["data"][str(mhz)]={ob:{"value":p[i],"SE":0.01}
                           for i,ob in enumerate(("R1","R2","NOE"))}
  fit=m.fit_local(row,10,1,35,False)
  self.assertLess(fit[0],1e-8)
  self.assertAlmostEqual(fit[1][0],0.75,places=5)

 def test_frozen_fields_no_800_in_fit(self):
  src=inspect.getsource(self.m.fit_local)
  self.assertIn("(500,600)",src)
  self.assertNotIn("800",src)
  self.assertEqual(self.p["measurements"]["test_field_MHz"],800)

 def test_no_rowan_provider_or_FNII_ensemble(self):
  code=inspect.getsource(self.m)
  self.assertNotIn("ROWAN_API_KEY",code)
  self.assertNotIn("submit_protein_cofolding_workflow",code)

if __name__=="__main__":unittest.main()
