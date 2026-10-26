"""Independent arithmetic/provenance tests, never simulate a provider run."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location("bbc1_local_boltz2_bridge",Path(__file__).with_name("bbc1_local_boltz2_bridge.py"))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class BridgeTests(unittest.TestCase):
    def test_frozen_sequences_and_wt_identity(self):
        cases=m.cases()
        self.assertEqual(len(cases["BBC1_WT"]),64)
        self.assertEqual(cases["BBC1_WT"][52],"G")
        self.assertEqual(cases["BBC1_G53A"][52],"A")
        self.assertEqual([i for i,(a,b) in enumerate(zip(*cases.values())) if a!=b],[52])
    def test_yaml_is_single_sequence(self):
        x=m.yaml_payload(m.BBC1_WT).decode()
        self.assertIn("msa: empty",x)
        self.assertIn("id: A",x)
        self.assertNotIn("msa_server",x)
    def test_confidence_fields_from_original_boltz2_output_required(self):
        with self.assertRaisesRegex(m.Hold,"FIELDS_MISSING"):
            m.confidence_score(b'{"ptm":0.9,"avg_lddt":0.9}')
        with self.assertRaisesRegex(m.Hold,"RANGE_BAD"):
            m.confidence_score(b'{"ptm":1.1,"complex_plddt":0.9}')
    def test_no_fabricated_metrics_with_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            x=m.audit(d,{})
            self.assertEqual(x["status"],"HOLD_NO_LOCAL_BOLTZ2_PREDICTIONS")
            self.assertEqual(x["local_confidence_files"],{})
            self.assertFalse(x["production_promotion"])
            self.assertFalse(x["FireProt_outcome_labels_accessed"])
    def test_partial_output_does_not_unlock_bridge(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"wt.json"
            p.write_text('{"ptm":0.93,"complex_plddt":0.96}')
            x=m.audit(d,{"BBC1_WT":p})
            self.assertEqual(x["status"],"PARTIAL_ONE_LOCAL_BOLTZ2_RESULT_NOT_COMPARABLE")
            self.assertEqual(len(x["comparison"]),1)
    def test_two_fixture_results_still_not_equivalent_to_rowan(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/"wt.json",Path(d)/"mutant.json"
            a.write_text('{"ptm":0.927,"complex_plddt":0.963}')
            b.write_text('{"ptm":0.918,"complex_plddt":0.968}')
            x=m.audit(d,{"BBC1_WT":a,"BBC1_G53A":b})
            self.assertEqual(x["status"],"PASS_TWO_LOCAL_BOLTZ2_RESULTS_METRIC_EQUIVALENCE_NOT_ESTABLISHED")
            self.assertEqual(x["scientific_status"],"COMPATIBILITY_UNPROVEN")
            self.assertEqual(x["comparison"]["pair_deltas"]["rowan_delta_ptm"],-.009000000000000008)
    def test_windows_crlf_inputs_keep_exact_observed_hash(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d,"BBC1_WT.yaml")
            original=m.yaml_payload(m.BBC1_WT).replace(b"\n",b"\r\n")
            p.write_bytes(original)
            report=m.generate_inputs(d)
            self.assertEqual(p.read_bytes(),original)
            self.assertEqual(report["BBC1_WT"]["yaml_sha256"],m.sha(original))
            self.assertEqual(report["BBC1_WT"]["original_input_line_endings"],"CRLF")
    def test_immutable_yaml_input_prevents_reuse_under_changed_sequence(self):
        with tempfile.TemporaryDirectory() as d:
            m.generate_inputs(d)
            Path(d,"BBC1_WT.yaml").write_text("mutated")
            with self.assertRaisesRegex(m.Hold,"FROZEN_YAML_INPUT_WOULD_CHANGE"):
                m.generate_inputs(d)
if __name__=="__main__":unittest.main()
