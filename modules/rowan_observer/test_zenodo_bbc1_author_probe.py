"""Offline synthetic tests for direct-author ΔΔG lineage and hard-stop behavior."""
import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("zenodo_bbc1_author_probe",Path(__file__).with_name("zenodo_bbc1_author_probe.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
SCORES=(-2.9513259829873366,-2.3129026098944245,-1.4905599208892324,
        -1.0025844433957378,-0.3899916009181281,.0025466003782845803,
        .44037905833600277,1.3228887174599038)
def fixture():
    rows=[{"WT_name":"1TG0.pdb","mut_type":mu,"aa_seq":m.mutation_sequence(mu),
           "ddG_ML":str(score),"dG_ML":"0.123"} for mu,score in zip(m.MUTATIONS,SCORES)]
    p={mu:score for mu,score in zip(m.MUTATIONS,SCORES)}
    return rows,p
class TestAuthorAudit(unittest.TestCase):
    def test_all_eight_exact_match(self):
        raw,processed=fixture()
        a=m.compare_rows(raw,processed)
        self.assertEqual(a["n_mismatches"],0)
        self.assertEqual(a["n_matching"],8)
        self.assertFalse(a["member_crc32_fully_verified"])
    def test_single_w38l_version_discrepancy_is_hold(self):
        raw,processed=fixture()
        processed["W38L"]=-.8445540655216376
        a=m.compare_rows(raw,processed)
        self.assertEqual(a["status"],"HOLD_AUTHOR_PROCESSED_LABEL_DISCREPANCY")
        self.assertEqual(a["n_matching"],7)
        self.assertEqual(a["mismatch_mutations"],["W38L"])
        w=next(x for x in a["comparisons"] if x["mutation"]=="W38L")
        self.assertAlmostEqual(w["processed_minus_author"],.15803037787410024)
    def test_wrong_sequence_blocks(self):
        raw,processed=fixture()
        raw[3]["aa_seq"]="X"*64
        with self.assertRaisesRegex(m.Hold,"AUTHOR_SEQUENCE_DRIFT_W38L"):
            m.compare_rows(raw,processed)
    def test_missing_mutation_blocks(self):
        raw,processed=fixture()
        with self.assertRaisesRegex(m.Hold,"AUTHOR_MISSING_ROWS"):
            m.compare_rows(raw[:-1],processed)
    def test_duplicate_blocks(self):
        raw,processed=fixture()
        with self.assertRaisesRegex(m.Hold,"AUTHOR_DUPLICATE_MUTATION_G53A"):
            m.compare_rows(raw+[raw[0]],processed)
if __name__=="__main__":unittest.main()
