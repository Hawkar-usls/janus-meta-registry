"""Synthetic provider/local T8A pair receipt validation and sign-sensitive regression."""
import copy,importlib.util,tempfile,unittest
from pathlib import Path
sp=importlib.util.spec_from_file_location("audit",Path(__file__).with_name("rowan_1ey0_T8A_actual_pair_audit.py"))
a=importlib.util.module_from_spec(sp);sp.loader.exec_module(a)
def sources():
 local={
  "technical_status":"PASS_TWO_REAL_LOCAL_BOLTZ2_1EY0_WT_T8A_MSA_RUNS",
  "wt_sequence_sha256":a.WT_SHA,"mutant_T8A_sequence_sha256":a.MUT_SHA,
  "source_prereg":a.FROZEN_REG,
  "wt":{"ptm":.9377234578132629,"mean_plddt":.9478468894958496,"count":136},
  "T8A":{"ptm":.9397260546684265,"mean_plddt":.9504383206367493,"count":136}
 }
 shared={"case_name":a.NAME,"workflow_uuid":a.UUID,"source_mutant_sha256":a.MUT_SHA,
   "wt_sha256":a.WT_SHA,"model":"BOLTZ_2","use_msa_server":True,"num_samples":1,
   "original_zip_PDB_bytes_attested":False,"mutation_level_ddg_claim":False,
   "shadow_model_weights_modified":False,"FireProt_210_inference_authorized":False}
 sub={**shared,"status":"ONE_PREREGISTERED_T8A_PROVIDER_JOB_SUBMITTED","new_jobs":1,
   "credit_source":"ORG_WEEKLY_MIN_30_VERIFIED","max_credits_per_new_job":10}
 out={**shared,"status":"EXISTING_SINGLE_MUTANT_NO_SPEND","new_jobs":0,
   "provider_result_state":"PROVIDER_RESULT_RETURNED","actual_provider_status":"Status.COMPLETED_OK",
   "ptm":.940,"avg_lddt":.949,"credits_charged":4.39}
 return local,sub,out
class PairTests(unittest.TestCase):
 def test_real_value_mock_agrees_on_source_but_disagrees_ptm_sign(self):
  result=a.compare(*sources())
  self.assertTrue(result["cross_provider"]["ptm_mutation_delta_sign_disagrees"])
  self.assertAlmostEqual(result["cross_provider"]["rowan_minus_local_delta_ptm"],-.00500259685516)
  self.assertAlmostEqual(result["rowan"]["actual_credits_charged"],4.39)
  self.assertFalse(result["firewalls"]["FireProt_210_scale_up_authorized"])
 def test_unfinished_provider_is_rejected(self):
  l,s,p=sources();p["provider_result_state"]="PENDING_OR_IN_PROGRESS"
  with self.assertRaisesRegex(a.Hold,"PROVIDER_RESULT_NOT_COMPLETE"):a.compare(l,s,p)
 def test_no_attested_source_approval_if_experimental_claim(self):
  l,s,p=sources();p["mutation_level_ddg_claim"]=True
  with self.assertRaisesRegex(a.Hold,"FALSE_SCIENTIFIC_CLAIM"):a.compare(l,s,p)
 def test_duplicate_new_job_rejected(self):
  l,s,p=sources();p["new_jobs"]=1
  with self.assertRaisesRegex(a.Hold,"DUPLICATE_WORKFLOW"):a.compare(l,s,p)
 def test_nonweekly_unknown_pool_rejected(self):
  l,s,p=sources();s["credit_source"]="NONWEEKLY_MIXED"
  with self.assertRaisesRegex(a.Hold,"INVALID_OR_UNKNOWN_WEEKLY_CREDIT_SOURCE"):a.compare(l,s,p)
 def test_wrong_variant_hash_rejected(self):
  l,s,p=sources();p["source_mutant_sha256"]="0"*64
  with self.assertRaisesRegex(a.Hold,"PROVIDER_MUTANT_SEQUENCE_DRIFT"):a.compare(l,s,p)
 def test_missing_source_prereg_rejected(self):
  l,s,p=sources();l["source_prereg"]="other.json"
  with self.assertRaisesRegex(a.Hold,"LOCAL_SOURCE_PREREG_DRIFT"):a.compare(l,s,p)
 def test_invalid_credit_above_max_rejected(self):
  l,s,p=sources();p["credits_charged"]=12.1
  with self.assertRaisesRegex(a.Hold,"PROVIDER_CREDIT_CAP_EXCEEDED"):a.compare(l,s,p)
 def test_source_local_wt_drift_rejected(self):
  l,s,p=sources();l["wt"]["ptm"]=.5
  with self.assertRaisesRegex(a.Hold,"PRIOR_PUBLISHED_WT_LOCAL_DRIFT"):a.compare(l,s,p)
if __name__=="__main__":unittest.main()
