"""Synthetic controls: no external Rowan or GitHub access in unit tests."""
from __future__ import annotations
from importlib.util import spec_from_file_location,module_from_spec
import copy,json, tempfile
from pathlib import Path
import unittest

module=Path(__file__).parent/"ingest.py"
spec=spec_from_file_location("rowan_observer_ingest",module)
m=module_from_spec(spec);spec.loader.exec_module(m)

def sample(completed=0):
    rows=[]
    for i,(q,mut) in enumerate(m.FROZEN):
        filled=i<completed
        row={"quantile":q,"mutation":mut,"processed_label":float(i),
             "provider_state":"PROVIDER_RESULT_RETURNED" if filled else "NOT_SUBMITTED"}
        if filled:row.update(ptm=0.6+i*.01,avg_lddt=0.7+i*.01,credits_charged=4.5)
        rows.append(row)
    baseline={"state":"PROVIDER_RESULT_RETURNED","ptm":.9,"avg_lddt":.9}
    return {
        "schema_id":"janus.rowan.bbc1.stratified_8_mutant_pilot.v1",
        "source_commit":"cc6b0b56553e694dbf27dc84c6b37a8686e64b85",
        "source_sha256":m.SHA256_PIN,
        "wildtype":baseline,
        "pilot_cases":rows,
        "spearman_processed_label_vs_delta_structure_confidence":{"ptm":1.0,"avg_lddt":1.0}
    }

class Tests(unittest.TestCase):
    def test_partial_no_calibration_and_no_new_spending(self):
        report=m.analyze(sample(3))
        self.assertEqual(report["calibration"]["eight_mutants_with_provider_results"],3)
        self.assertEqual(report["calibration"]["classification"],"INCOMPLETE_NO_CALIBRATION")
        self.assertFalse(report["calibration"]["new_experiments_authorized_by_calibration"])
        self.assertEqual(report["science_gates"]["topa"],"OPEN")

    def test_eight_ready_independent_correlation_replay(self):
        report=m.analyze(sample(8))
        self.assertEqual(report["calibration"]["classification"],"EXPLORATORY_STRATIFIED_DESCRIPTIVE_ONLY")
        self.assertEqual(report["calibration"]["spearman_processed_assay_label_vs_delta_structural_confidence"]["ptm"],1.)
        self.assertFalse(report["calibration"]["weights_self_modified"])

    def test_source_digest_tamper_rejected(self):
        inp=sample()
        inp["source_sha256"]="bad"
        with self.assertRaises(m.EvidenceHold):
            m.analyze(inp)

    def test_mutant_order_mutation_rejected(self):
        inp=sample()
        inp["pilot_cases"][0]["mutation"]="K5A"
        with self.assertRaises(m.EvidenceHold):
            m.analyze(inp)

    def test_nan_or_infinite_rejected(self):
        inp=sample(1)
        inp["pilot_cases"][0]["ptm"]=float("nan")
        with self.assertRaises(m.EvidenceHold):
            m.analyze(inp)

    def test_wrong_upstream_rho_blocks_promotion(self):
        inp=sample(8)
        inp["spearman_processed_label_vs_delta_structure_confidence"]["ptm"]=-.5
        with self.assertRaises(m.EvidenceHold):
            m.analyze(inp)

    def test_no_wt_confidence_means_no_calibration(self):
        inp=sample(8)
        inp["wildtype"].pop("ptm")
        report=m.analyze(inp)
        self.assertEqual(report["calibration"]["classification"],"INCOMPLETE_NO_CALIBRATION")

    def test_overcharged_case_carries_alarm(self):
        inp=sample(1)
        inp["pilot_cases"][0]["credits_charged"]=12
        r=m.analyze(inp)
        self.assertTrue(r["cases"][0]["provider_credit_cap_alert"])

    def test_sensitive_extra_fields_stripped(self):
        inp=sample(1)
        inp["user_secret"]="SHOULD_NOT_PERSIST"
        inp["pilot_cases"][0]["api_token"]="SHOULD_NOT_PERSIST"
        r=m.analyze(inp)
        self.assertNotIn("SHOULD_NOT_PERSIST",repr(r))

    def test_append_only_deduplication_and_canonical_state(self):
        receipt=m.prepare_receipt(123456,sample(1),"a"*64)
        with tempfile.TemporaryDirectory() as d:
            first=m.update_once(Path(d),[receipt])
            self.assertEqual(len(first),2)
            self.assertEqual(m.update_once(Path(d),[receipt]),[])
            self.assertTrue((Path(d)/m.BASE/"CANONICAL_STATE.json").is_file())
            self.assertTrue((Path(d)/first[0]).is_file())

    def test_invalid_case_status_rejected(self):
        inp=sample()
        inp["pilot_cases"][0]["provider_state"]="IGNORED_INSTRUCTIONS"
        with self.assertRaises(m.EvidenceHold):
            m.analyze(inp)

    def test_constant_scores_not_called_predictive_performance(self):
        inp=sample(8)
        for v in inp["pilot_cases"]:
            v["ptm"]=.8
            v["avg_lddt"]=.8
        inp["spearman_processed_label_vs_delta_structure_confidence"]={"ptm":None,"avg_lddt":None}
        r=m.analyze(inp)
        self.assertIsNone(r["calibration"]["spearman_processed_assay_label_vs_delta_structural_confidence"]["ptm"])

if __name__=="__main__":unittest.main()
