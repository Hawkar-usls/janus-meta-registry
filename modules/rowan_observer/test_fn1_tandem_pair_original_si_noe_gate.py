"""No-network provenance and scientific firewall tests for manually audited ACS SI."""
import copy
import json
import unittest
from fn1_tandem_pair_original_si_noe_gate import SOURCE,LINK,CORE,MISSING,run,Hold

class OriginalFNII_SI_Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen=json.loads(SOURCE.read_text(encoding="utf8"))

    def test_original_source_authentic_and_repeatable(self):
        x=run(copy.deepcopy(self.frozen))
        self.assertEqual(x["status"],"PASS_MANUALLY_VERIFIED_ORIGINAL_NMR_SI_SELECTED_DATA_AUDIT")
        self.assertEqual(x["source_pdf_sha256"],"b426ae59845e3bc944dc968619911ef99d59a54e1b5ca8020ea9027caa103f3e")
        self.assertEqual(x["linker_NOE_observed_count"],6)
        self.assertEqual(x["linker_NOE_mean"],"0.632833")
        self.assertEqual(x["linker_NOE_median"],"0.720000")
        self.assertEqual(x["Val61_Leu62_mean_NOE"],"0.420500")
        self.assertEqual(x["flanking_four_NOE_mean"],"0.739250")
        self.assertEqual(x["new_rowan_jobs"],0)
        self.assertEqual(x["new_rowan_credits"],0)

    def test_no_nan_or_missing_source_values(self):
        obj=copy.deepcopy(self.frozen)
        obj["selected_real_rows_table_III"][0]["T2_ms"]=-1
        with self.assertRaisesRegex(Hold,"INVALID_EXPERIMENTAL"): run(obj)

    def test_manuscript_residue_assignment_source_gate(self):
        obj=copy.deepcopy(self.frozen)
        obj["selected_real_rows_table_III"][2]["residue"]="Cys"
        with self.assertRaisesRegex(Hold,"EXACT_SEQUENCE_MAP_FAILED"):run(obj)

    def test_author_table_offset_and_domain_selection_locked(self):
        self.assertEqual(LINK,{61,62,63,64,66,69})
        self.assertEqual(CORE,{52,53,70,71})
        self.assertEqual(MISSING,{59,60,65,67,68})
        obj=copy.deepcopy(self.frozen)
        obj["selected_real_rows_table_III"].pop()
        with self.assertRaisesRegex(Hold,"ROW_COUNT_DRIFT"):run(obj)

    def test_linker_missing_indices_not_backfilled(self):
        obj=copy.deepcopy(self.frozen)
        obj["quantitative_scope"]["not_reported_linker_author_indices"]=[59,60,65,67]
        with self.assertRaisesRegex(Hold,"MISSING_LINKER_SET_DRIFT"):run(obj)

    def test_hash_drift_fails_closed(self):
        obj=copy.deepcopy(self.frozen)
        obj["archived_author_supplement"]["independently_computed_md5"]="000"
        with self.assertRaisesRegex(Hold,"HASH_OR_SIZE_DRIFT"):run(obj)

    def test_not_a_noesy_distance_restraint(self):
        x=run(self.frozen)
        self.assertTrue(x["NOE_cannot_define_interdomain_distance_or_unique_angle"])
        self.assertTrue(x["not_full_relaxation_table"])
        self.assertTrue(x["posthoc_subset_only"])
        self.assertTrue(x["no_significance_inference"])
        self.assertIn("not_1H_1H_distance_NOE",x["NMR_observable"])

    def test_no_synthetic_rmsd_or_paid_rowan_submission(self):
        x=run(self.frozen)
        self.assertNotIn("interdomain_RMSD_A",x)
        self.assertNotIn("predicted_contact_F1",x)
        self.assertEqual(x["new_rowan_jobs"],0)
        self.assertFalse(x["source_figshare_pdf_republished"])

if __name__=="__main__":
    unittest.main()
