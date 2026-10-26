"""Fail-closed controls for original frozen 8-mutant structural transfer report."""
import importlib.util,unittest,tempfile
from pathlib import Path
from unittest import mock
spec=importlib.util.spec_from_file_location("bbc1_public_msa_eight_mutant_validation",Path(__file__).with_name("bbc1_public_msa_eight_mutant_validation.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def three():
    return {"state":"PASS_LOCAL_BBC1_THREE_MSA_SOURCE_VERIFIED_METRIC_PROVIDER_EQUIVALENCE_HOLD",
      "cases":{
       "BBC1_WT_MSA":{"ptm":.9316620826721191,"complex_plddt":.9701703786849976,
                      "rowan_ptm":.927,"rowan_avg_lddt":.963},
       "BBC1_G53A_MSA":{"ptm":.9208811521530151,"complex_plddt":.9676069617271423,
                        "rowan_ptm":.918,"rowan_avg_lddt":.968},
       "BBC1_G48D_MSA":{"ptm":.9302268028259277,"complex_plddt":.9701615571975708,
                        "rowan_ptm":.926,"rowan_avg_lddt":.971}}}
def six():
    return {"partial_completed_count":6,"paid_rowan_jobs":0,"FireProt_210_jobs":0,
            "records":[{"mutation":x[0],"rowan":{"ptm":x[1],"avg_lddt":x[2]}}
                       for x in m.PREDECLARED]}
def verified_dummy():
    return [{"mutation":x[0],"rowan_ptm":x[1],"rowan_avg_lddt":x[2],
             "ptm":x[1]+.002,"complex_plddt":x[2]-.002}
            for x in m.PREDECLARED]

class EightMutantAuditTests(unittest.TestCase):
    def test_all_nine_structural_sources_do_not_authorize_fireprot(self):
        with mock.patch.object(m,"verify_six",return_value=verified_dummy()):
            r=m.summary(three(),six(),Path("."),Path("."))
        self.assertEqual(r["sample_size"],8)
        self.assertEqual(len(r["source_bound_frozen_mutant_rows"]),8)
        self.assertFalse(r["fireprot_210_authorized"])
        self.assertFalse(r["scientific_fitness_or_stability_claim"])
        self.assertIn("OPEN",r["provider_alignment_equivalence"])
    def test_missing_three_case_source_blocks(self):
        bad=three();bad["state"]="PASS_CONFIDENCE_WITHOUT_EVIDENCE"
        with self.assertRaisesRegex(m.AuditHold,"PINNED_THREE_CASE_BRIDGE_NOT_VERIFIED"):
            m.summary(bad,six(),Path("."),Path("."))
    def test_prior_provider_score_drift_blocks(self):
        bad=three();bad["cases"]["BBC1_WT_MSA"]["rowan_ptm"]=.500
        with self.assertRaisesRegex(m.AuditHold,"INITIAL_THREE_ROWAN_DRIFT"):
            m.summary(bad,six(),Path("."),Path("."))
    def test_six_missing_or_misordered_blocks(self):
        bad=six();bad["records"][0],bad["records"][1]=bad["records"][1],bad["records"][0]
        with self.assertRaisesRegex(m.AuditHold,"EXACT_SIX_FROZEN_ORDER"):
            m.verify_six(bad,Path("."),Path("."))
    def test_partial_or_paid_run_blocks(self):
        bad=six();bad["partial_completed_count"]=5
        with self.assertRaisesRegex(m.AuditHold,"INCOMPLETE_OR_CREDITS_DRIFT"):
            m.verify_six(bad,Path("."),Path("."))
        bad=six();bad["paid_rowan_jobs"]=1
        with self.assertRaisesRegex(m.AuditHold,"INCOMPLETE_OR_CREDITS_DRIFT"):
            m.verify_six(bad,Path("."),Path("."))
    def test_original_source_rowan_ref_drift_blocks(self):
        bad=six();bad["records"][0]["rowan"]["ptm"]=.010
        with self.assertRaisesRegex(m.AuditHold,"ORIGINAL_ROWAN_REFERENCE_CHANGED"):
            m.verify_six(bad,Path("."),Path("."))
if __name__=="__main__":unittest.main()
