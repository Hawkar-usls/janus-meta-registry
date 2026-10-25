"""Pure synthetic position-group drift tests, no external data or networking."""
import unittest,importlib.util,json
from pathlib import Path
spec=importlib.util.spec_from_file_location("proteingym_position_audit",Path(__file__).with_name("proteingym_position_audit.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def fixtures():
    p=[{"mutant":"W38L","mutated_sequence":"SEQ1","DMS_score":"-0.8445540655216376"},
       {"mutant":"K13N","mutated_sequence":"SEQ2","DMS_score":"-0.3899916009181281"}]
    mirror="\n".join(json.dumps({"dataset_id":"proteingym_raw","row":{
        "mut_type":mut,"aa_seq":seq,"ddG_ML_float":score}})
        for mut,seq,score in (("W38L","SEQ1","-1.0025844433957378"),
                              ("K13N","SEQ2","-0.3899916009181281")))
    return p,mirror
class TestPositionAudit(unittest.TestCase):
    def test_one_position_specific_difference(self):
        p,r=fixtures();res=m.compare(p,r)
        self.assertEqual(res["matching"],1)
        self.assertEqual(res["different_numeric"],1)
        self.assertEqual(res["numeric_difference_positions"],{"38":1})
        self.assertEqual(res["W38L"]["mutation"],"W38L")
        self.assertFalse(res["processing_transformation_algorithm_identified"])
    def test_all_match(self):
        p,r=fixtures()
        p[0]["DMS_score"]="-1.0025844433957378"
        res=m.compare(p,r)
        self.assertEqual(res["status"],"MATCHED")
    def test_missing_identity(self):
        p,r=fixtures();p[1]["mutated_sequence"]="DIFFERENT"
        res=m.compare(p,r)
        self.assertEqual(res["missing_exact_sequence"],1)
    def test_nonfinite_fails_closed(self):
        p,r=fixtures();p[1]["DMS_score"]="nan"
        with self.assertRaisesRegex(m.GateHold,"NONFINITE_SCORE"):
            m.compare(p,r)
if __name__=="__main__":unittest.main()
