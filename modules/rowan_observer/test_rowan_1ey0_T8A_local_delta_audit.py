"""Fail-closed mock local artifact tests, no GPU jobs and no assay data."""
import importlib.util,json,hashlib,tempfile,unittest
from pathlib import Path
from unittest import mock
import numpy as np
f=Path(__file__).with_name("rowan_1ey0_T8A_local_delta_audit.py")
sp=importlib.util.spec_from_file_location("rowan_1ey0_T8A_local_delta_audit",f)
m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
def fixture(base):
 base=Path(base)
 inputs=base/"inputs";outputs=base/"outputs";inputs.mkdir()
 variant=m.sequence_check()
 (inputs/"1EY0_RCSB_136AA_T8A.yaml").write_bytes(
  f"sequences:\n  - protein:\n      id: A\n      sequence: {variant}\n".encode())
 confsha={};npzsha={};msha={}
 for name in ("1EY0_RCSB_136AA_WT","1EY0_RCSB_136AA_T8A"):
  root=outputs/("boltz_results_"+name)
  pred=root/"predictions"/name
  pred.mkdir(parents=True)
  c=pred/("confidence_"+name+"_model_0.json")
  c.write_text(json.dumps({"ptm":.92,"complex_plddt":.94}),encoding="utf-8")
  n=pred/("plddt_"+name+"_model_0.npz")
  np.savez(n,plddt=np.ones(136)*.94)
  msa=root/"msa";msa.mkdir()
  msha[name]={}
  for basename in ("uniref.a3m","bfd.mgnify30.metaeuk30.smag30.a3m"):
   q=msa/basename;q.write_text(">query\nAAA\n")
   msha[name][basename]=m.sha(q.read_bytes())
  confsha[name]=m.sha(c.read_bytes())
  npzsha[name]=m.sha(n.read_bytes())
 return inputs,outputs,confsha,npzsha,msha
def patched(confsha,npzsha,msha,inputs):
 return [
  mock.patch.object(m,"INPUT_YAML_SHA",m.sha((inputs/"1EY0_RCSB_136AA_T8A.yaml").read_bytes())),
  mock.patch.object(m,"WT_CONF_SHA",confsha["1EY0_RCSB_136AA_WT"]),
  mock.patch.object(m,"MUT_CONF_SHA",confsha["1EY0_RCSB_136AA_T8A"]),
  mock.patch.object(m,"WT_NPZ_SHA",npzsha["1EY0_RCSB_136AA_WT"]),
  mock.patch.object(m,"MUT_NPZ_SHA",npzsha["1EY0_RCSB_136AA_T8A"]),
  mock.patch.object(m,"MSA_SHA",msha)
 ]
class T8ALocalAuditTests(unittest.TestCase):
 def test_exact_frozen_mutation_sha(self):
  s=m.sequence_check()
  self.assertEqual(s[7],"A");self.assertEqual(len(s),136)
  self.assertEqual(m.sha(s.encode()),m.T8A_SHA)
 def test_synthetic_pair_proves_only_structure_confidence(self):
  with tempfile.TemporaryDirectory() as d:
   inputs,outputs,cs,ps,ms=fixture(d)
   with ExitStacked(patched(cs,ps,ms,inputs)):
    z=m.audit(inputs,outputs)
   self.assertEqual(z["technical_status"],"PASS_TWO_REAL_LOCAL_BOLTZ2_1EY0_WT_T8A_MSA_RUNS")
   self.assertAlmostEqual(z["mutant_minus_wt"]["delta_ptm"],0)
   self.assertFalse(z["scientific_gates"]["true_blind"])
   self.assertTrue(z["scientific_gates"]["FireProt_210_mutants_not_authorized"])
 def test_wrong_mutant_yaml_holds(self):
  with tempfile.TemporaryDirectory() as d:
   inp,out,cs,ps,ms=fixture(d)
   p=inp/"1EY0_RCSB_136AA_T8A.yaml";p.write_bytes(p.read_bytes()+b"msa: empty\n")
   with ExitStacked(patched(cs,ps,ms,inp)):
    with self.assertRaisesRegex(m.Hold,"YAML_NOT_EXACT_136AA_MUTANT"):
     m.audit(inp,out)
 def test_missing_msa_holds(self):
  with tempfile.TemporaryDirectory() as d:
   inp,out,cs,ps,ms=fixture(d)
   next(out.rglob("uniref.a3m")).unlink()
   with ExitStacked(patched(cs,ps,ms,inp)):
    with self.assertRaisesRegex(m.Hold,"MSA_NOT_UNIQUE"):m.audit(inp,out)
 def test_wrong_residue_count_holds(self):
  with tempfile.TemporaryDirectory() as d:
   inp,out,cs,ps,ms=fixture(d)
   p=next(out.rglob("plddt_1EY0_RCSB_136AA_T8A_model_0.npz"))
   np.savez(p,plddt=np.ones(135)*.94)
   ps["1EY0_RCSB_136AA_T8A"]=m.sha(p.read_bytes())
   with ExitStacked(patched(cs,ps,ms,inp)):
    with self.assertRaisesRegex(m.Hold,"PLDDT_NPZ_SCHEMA_DRIFT"):m.audit(inp,out)
 def test_tampered_score_file_holds(self):
  with tempfile.TemporaryDirectory() as d:
   inp,out,cs,ps,ms=fixture(d)
   p=next(out.rglob("confidence_1EY0_RCSB_136AA_T8A_model_0.json"))
   p.write_text('{"ptm":.0}',encoding="utf8")
   with ExitStacked(patched(cs,ps,ms,inp)):
    with self.assertRaisesRegex(m.Hold,"CONFIDENCE_1EY0_RCSB_136AA_T8A_MISSING_OR_SHA_DRIFT"):m.audit(inp,out)
class ExitStacked:
 def __init__(self,patches):self.patches=patches
 def __enter__(self):
  for p in self.patches:p.__enter__()
 def __exit__(self,*args):
  for p in self.patches[::-1]:p.__exit__(*args)
if __name__=="__main__":unittest.main()
