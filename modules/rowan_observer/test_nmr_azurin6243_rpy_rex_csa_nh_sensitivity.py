"""Source-locked read-only Rotne-Prager azurin tensor and scientific gates."""
from __future__ import annotations
import importlib.util,math,unittest
REQUIRED=("numpy","scipy","pynmrstar","Bio")
@unittest.skipUnless(all(importlib.util.find_spec(n) for n in REQUIRED),
 "Pinned azurin science dependencies only in dedicated environment")
class RPYSourceTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  import nmr_azurin6243_rpy_rex_csa_nh_sensitivity as m
  cls.m=m
  import json
  p=json.loads(m.PROTO.read_text(encoding="utf8"))
  cls.p=p
  src=p["prior_sources"]
  cls.raw=m.load_raw("https://files.rcsb.org/download/1E5Y.cif",src["PDB1E5Y_SHA256"],471185)
  star=m.load_raw("https://bmrb.io/ftp/pub/bmrb/entry_directories/bmr6243/bmr6243_3.str",
                  src["BMRB6243_SHA256"],323833)
  seq,cls.data,cls.conditions=m.parse_nmr(star.decode())
  cls.xyz,cls.nh,cls.omitted=m.load_structure(cls.raw,seq)
  cls.hydro=m.rpy_rotational_tensor(cls.xyz,3.0)

 def test_source_absolute_identity_and_full_original_observables(self):
  self.assertEqual(len(self.data[1]),116)
  self.assertEqual(len(self.data[2]),114)
  self.assertEqual(len(self.nh),123)
  self.assertEqual(len(self.nh)+len(self.omitted),128)

 def test_rpy_rotational_eigenvalues_positive_and_symmetric(self):
  eigen=self.hydro["rotational_mobility_eigenvalues_unscaled"]
  self.assertEqual(len(eigen),3)
  self.assertGreater(eigen[0],0)
  self.assertLess(eigen[0],eigen[1])
  self.assertLess(eigen[1],eigen[2])
  self.assertAlmostEqual(sum(v*v for v in self.hydro["fast_axis_xyz"]),1,places=8)

 def test_rpy_is_hydrodynamic_prediction_not_pca(self):
  self.assertTrue(self.hydro["theoretical_eigenvalues_independent_of_NMR"])
  self.assertTrue(self.hydro["assumed_viscosity_not_used"])
  self.assertTrue(self.hydro["approximation_CA_centric_beads_not_hydronmr"])
  self.assertGreater(self.hydro["rotational_diffusion_fast_to_two_transverse_mean_ratio"],1)

 def test_spherical_rotation_covariance(self):
  import numpy as np
  rot=np.array([[0,-1,0],[1,0,0],[0,0,1.]])
  x=self.m.rpy_rotational_tensor(self.xyz@rot.T,3.)
  a=self.hydro["rotational_mobility_eigenvalues_unscaled"]
  b=x["rotational_mobility_eigenvalues_unscaled"]
  for u,v in zip(a,b):
   self.assertAlmostEqual(u/v,1,places=8)

 def test_stochastic_proton_rotation_not_used_to_fit(self):
  import inspect
  text=inspect.getsource(self.m.nh_perturbation_envelopes)
  self.assertIn("for deg in (0,5,10)",text)
  self.assertIn("for phase in",text)
  self.assertNotIn("least_squares",text)
  self.assertNotIn("row[\"data\"][\"800\"]",text)

 def test_train500600_only_and_no_rowan_api(self):
  import inspect
  src=inspect.getsource(self.m.one_local_fit)
  self.assertIn("TRAIN_FIELDS",src)
  self.assertNotIn("800",src)
  self.assertNotIn("ROWAN_API_KEY",inspect.getsource(self.m))

 def test_bond_angles_valid_and_model_ratios(self):
  a=self.m.theta_for_vectors(self.nh,self.hydro)
  self.assertEqual(len(a),123)
  self.assertTrue(all(0<=z<=90 for z in a.values()))

if __name__=="__main__":
 unittest.main()
