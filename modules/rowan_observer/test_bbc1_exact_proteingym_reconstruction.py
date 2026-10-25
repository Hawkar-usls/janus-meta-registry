"""BBC1-specific regression and adversarial gates; no external dependencies."""
from __future__ import annotations
import importlib.util,unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location("bbc1_exact_proteingym_reconstruction",
    Path(__file__).with_name("bbc1_exact_proteingym_reconstruction.py"))
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

def synthetic():
    w=r.WT
    q=r.mutation_sequence("W38L")
    g=r.mutation_sequence("G53A")
    raw=[
        {"aa_seq":w,"name":"1TG0_WT","mut_type":"wt","ddG_ML_float":"0"},
        {"aa_seq":q,"name":"1TG0_W38L","mut_type":"W38L",
         "ddG_ML_float":"-1.0025844433957378"},
        {"aa_seq":q,"name":"1TG0_F10F:W38L","mut_type":"F10F:W38L",
         "ddG_ML_float":"-0.6865236876475374"},
        {"aa_seq":g,"name":"1TG0_G53A","mut_type":"G53A",
         "ddG_ML_float":"-2.9513259829873366"}
    ]
    processed=[
        {"mutated_sequence":q,"mutant":"W38L",
         "DMS_score":"-0.8445540655216376","DMS_score_bin":"1"},
        {"mutated_sequence":g,"mutant":"G53A",
         "DMS_score":"-2.9513259829873366","DMS_score_bin":"0"}]
    return raw,processed

class ReconstructionTest(unittest.TestCase):
    def test_exact_w38l_pseudomutation_mean(self):
        raw,p=synthetic()
        with unittest.mock.patch.object(r,"EIGHT_MUTATIONS",("W38L","G53A")):
            report=r.reconstruct(raw,p,-1.271998543)
        self.assertEqual(report["final_mutant_rows"],2)
        self.assertEqual(report["all_binary_scores_reproduced"],2)
        self.assertEqual(report["multiplicity_distribution"],{"1":1,"2":1})
        self.assertEqual(report["earlier_exact_mut_type_comparison_numeric_differences"],1)
        self.assertAlmostEqual(report["frozen_eight_summary"][0]["reconstructed_label"],
                               -0.8445540655216376)
    def test_earlier_single_row_is_not_full_mean(self):
        raw,p=synthetic();p[0]["DMS_score"]=raw[1]["ddG_ML_float"]
        with unittest.mock.patch.object(r,"EIGHT_MUTATIONS",("W38L","G53A")):
            with self.assertRaisesRegex(r.ReconciliationHold,"MEAN_SCORE_RECONSTRUCTION_FAILED"):
                r.reconstruct(raw,p,-1.271998543)
    def test_wrong_binary_label_is_blocked(self):
        raw,p=synthetic();p[0]["DMS_score_bin"]="0"
        with unittest.mock.patch.object(r,"EIGHT_MUTATIONS",("W38L","G53A")):
            with self.assertRaisesRegex(r.ReconciliationHold,"BINARY_SCORE_RECONSTRUCTION_FAILED"):
                r.reconstruct(raw,p,-1.271998543)
    def test_raw_nonfinite_blocks(self):
        raw,p=synthetic();raw[0]["ddG_ML_float"]="nan"
        with self.assertRaisesRegex(r.ReconciliationHold,"NON_FINITE_SCORE"):
            r.reconstruct(raw,p,-1.271998543)
    def test_duplicate_processed_sequence_blocks(self):
        raw,p=synthetic()
        with self.assertRaisesRegex(r.ReconciliationHold,"DUPLICATED_PROCESSED_SEQUENCE"):
            r.reconstruct(raw,p+[dict(p[0])],-1.271998543)
    def test_unrepresented_mutation_blocks(self):
        raw,p=synthetic();p[1]["mutated_sequence"]=r.mutation_sequence("E42H")
        with self.assertRaisesRegex(r.ReconciliationHold,"PROCESSED_WITHOUT_RAW"):
            r.reconstruct(raw,p,-1.271998543)
    def test_wildtype_required(self):
        raw,p=synthetic()
        with self.assertRaisesRegex(r.ReconciliationHold,"WILDTYPE_MISSING"):
            r.reconstruct(raw[1:],p,-1.271998543)
    def test_pinned_raw_sha_enforced(self):
        with self.assertRaisesRegex(r.ReconciliationHold,"RAW_SHA256_DRIFT"):
            r.verify_files(b"fake_raw_bytes",b"fake_processed_bytes",b"fake_meta")
    def test_reference_git_blob_pin_enforced(self):
        with self.assertRaisesRegex(r.ReconciliationHold,"METADATA_BLOB_DRIFT"):
            r.source_cutoff(b"fake reference")
    def test_wrong_mutation_identity_blocks(self):
        with self.assertRaisesRegex(r.ReconciliationHold,"BAD_MUTATION"):
            r.mutation_sequence("A38L")

if __name__=="__main__":
    unittest.main()
