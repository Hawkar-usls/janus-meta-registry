"""ESSENCE v1.6.5 conservative model admission guard against forged promotion."""
import copy
import unittest
from tools import essence_v165_conservative_admission as gate

class ConservativeINT8Admission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=gate.strict_load(gate.EVIDENCE)
    def test_exact_prospective_provenance(self):
        self.assertEqual(gate.git_blob(gate.EVIDENCE.read_bytes()),gate.EVIDENCE_BLOB)
        self.assertEqual(self.source["source"]["prospective_summary_receipt_sha256"],
                         gate.EXPECTED_V164_RECEIPT)
    def test_empirical_pass_but_conservative_hold(self):
        q=gate.evaluate(self.source)
        self.assertTrue(q["both_prespecified_empirical_thresholds_pass"])
        self.assertFalse(q["both_optimistic_conservative_bounds_pass"])
        self.assertFalse(q["automatic_model_change_authority"])
        self.assertEqual(q["production_gate"],"HOLD_EXTERNAL_BLIND_ROLLBACK_AND_CONSERVATIVE_RELIABILITY")
        a,b=q["cohorts"]
        self.assertTrue(.955<a["wilson_95_lower_independent_token_assumption"]<.956)
        self.assertTrue(.957<b["wilson_95_lower_independent_token_assumption"]<.958)
    def test_token_count_tamper_denied(self):
        x=copy.deepcopy(self.source)
        x["prospective"]["source_cohorts"][0]["top1_total"]=999999
        with self.assertRaisesRegex(ValueError,"FABRICATED_OR_UNBOUNDED_TOP1"):
            gate.evaluate(x)
    def test_fake_external_lab_denied(self):
        x=copy.deepcopy(self.source)
        x["prospective"]["independent_external_custodian"]=True
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_AUTHORITY_OR_SOURCE_CLAIM"):
            gate.evaluate(x)
    def test_fake_autopromote_denied(self):
        x=copy.deepcopy(self.source)
        x["authority"]["automatic_model_swap_allowed"]=True
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_AUTHORITY_OR_SOURCE_CLAIM"):
            gate.evaluate(x)
    def test_fake_conservative_pass_denied(self):
        x=copy.deepcopy(self.source)
        x["risk"]["statistical_lower_bound_gate"]="PASS"
        with self.assertRaisesRegex(ValueError,"EXPECTED_CONSERVATIVE_GATE_CONTRADICTION"):
            gate.evaluate(x)
    def test_wilson_no_invalid_counts(self):
        for matched,total in ((2,1),(-1,3),(1,0),(1,True)):
            with self.subTest(n=(matched,total)),self.assertRaises(ValueError):
                gate.wilson_lower(matched,total)
    def test_forged_original_checkpoint_denied(self):
        x=copy.deepcopy(self.source)
        x["source"]["checkpoint_sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"UNTRUSTED_AUTHORITY_OR_SOURCE_CLAIM"):
            gate.evaluate(x)

if __name__=="__main__":unittest.main()
