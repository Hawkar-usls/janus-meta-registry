"""Synthetic fail-closed checks for source-authenticated Rowan SCOBY+FN1 pilots."""
import unittest
from pathlib import Path
from importlib.util import spec_from_file_location,module_from_spec
sp=spec_from_file_location("pilot",Path(__file__).with_name("scoby_placenta_two_real_rowan_pilots_audit.py"))
m=module_from_spec(sp);sp.loader.exec_module(m)
def make(case):
 data=m.CASES[case]
 common={"case":case,"case_name":data["name"],"provider_uuid":data["uuid"],
    "source_uniprot":data["uniprot"],"sequence_sha256":data["source_sha"],
    "sequence_length":data["length"],"model":"BOLTZ_2","use_msa_server":True,
    "num_samples":1,"source_registry_protocol":m.PREREG,
    "max_credits_per_new_job":10,"SCOBY_microbiome_predicted":False,
    "placental_tissue_or_BC_composite_predicted":False,
    "experimental_material_performance_proven":False}
 submit={**common,"status":"ONE_PREREGISTERED_SCOBY_RELATED_PROTEIN_SUBMITTED",
         "new_jobs":1,"weekly_authorization":"ORG_WEEKLY_AVAILABLE_GE_30_AT_SUBMIT"}
 collect={**common,"status":"CASE_ALREADY_EXISTS_NO_NEW_SUBMISSION",
    "new_jobs":0,"additional_jobs":0,"result_state":"PROVIDER_SCORES_RETURNED",
    "provider_status":"Status.COMPLETED_OK","ptm":.85,"avg_lddt":.93,"charged_credits":3.7}
 return submit,collect
class RealProviderPilotReceiptTests(unittest.TestCase):
 def test_synthetic_pass_for_both_but_no_biological_claim(self):
  for case in m.CASES:
   z=m.validate_one(case,*make(case))
   self.assertEqual(z["new_jobs_on_collection"],0)
   self.assertEqual(z["credits_charged"],3.7)
   self.assertTrue(z["scientific_interpretation_limit"])
 def test_no_completed_result_holds(self):
  s,c=make("scoby_acsD");c["result_state"]="PENDING_OR_IN_PROGRESS"
  with self.assertRaisesRegex(m.Hold,"NOT_YET_REAL_RESULT"):
   m.validate_one("scoby_acsD",s,c)
 def test_wrong_source_mutation_not_claimable(self):
  s,c=make("placenta_fn1");s["sequence_sha256"]="0"*64
  with self.assertRaisesRegex(m.Hold,"SOURCE_SEQUENCE_IDENTITY_DRIFT"):
   m.validate_one("placenta_fn1",s,c)
 def test_wrong_provider_uuid_blocks(self):
  s,c=make("scoby_acsD");c["provider_uuid"]="BAD-UUID"
  with self.assertRaisesRegex(m.Hold,"SOURCE_CASE_NAME_UUID_DRIFT"):
   m.validate_one("scoby_acsD",s,c)
 def test_wrong_msa_or_model_blocks(self):
  s,c=make("scoby_acsD");c["use_msa_server"]=False
  with self.assertRaisesRegex(m.Hold,"MODEL_OR_MSA_CONFIG_DRIFT"):
   m.validate_one("scoby_acsD",s,c)
 def test_weekly_budget_gate_mandatory(self):
  s,c=make("scoby_acsD");s["weekly_authorization"]="OTHER_CREDITS"
  with self.assertRaisesRegex(m.Hold,"NO_VERIFIED_WEEKLY_ONLY"):
   m.validate_one("scoby_acsD",s,c)
 def test_duplicate_collector_spend_blocks(self):
  s,c=make("placenta_fn1");c["new_jobs"]=1
  with self.assertRaisesRegex(m.Hold,"DUPLICATE_OR_NOT_READONLY"):
   m.validate_one("placenta_fn1",s,c)
 def test_false_materials_claim_blocks(self):
  s,c=make("placenta_fn1");c["placental_tissue_or_BC_composite_predicted"]=True
  with self.assertRaisesRegex(m.Hold,"FALSE_MATERIALS_CLAIM"):
   m.validate_one("placenta_fn1",s,c)
 def test_invalid_ptm_blocks(self):
  s,c=make("placenta_fn1");c["ptm"]=1.2
  with self.assertRaisesRegex(m.Hold,"SCORES_OUT_OF_RANGE"):
   m.validate_one("placenta_fn1",s,c)
 def test_cost_above_10_blocks(self):
  s,c=make("scoby_acsD");c["charged_credits"]=12
  with self.assertRaisesRegex(m.Hold,"CREDIT_SPEND_CAP_EXCEEDED"):
   m.validate_one("scoby_acsD",s,c)
 def test_wrong_case_not_allowed(self):
  with self.assertRaisesRegex(m.Hold,"UNKNOWN_OR_UNFROZEN_CASE"):
   m.validate_one("dangerous_or_unsupported",{}, {})
if __name__=="__main__":unittest.main()
