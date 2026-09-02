#!/usr/bin/env python3
import importlib.util, pathlib, unittest

P = pathlib.Path(__file__).with_name("eye_r4_6_continuous_uncertainty_adversary.py")
spec = importlib.util.spec_from_file_location("r46", P); r46 = importlib.util.module_from_spec(spec); spec.loader.exec_module(r46)

def base(calibrated=True):
    return {
        "cause_classes":[{"id":"A","target_class":"A","prior":0.5},{"id":"B","target_class":"B","prior":0.5}],
        "requirements":{"confidence_threshold":0.9,"robust_objective":"minimax_expected_cost"},
        "tests":[{"id":"t","cost":2,"calibrated":calibrated,"likelihood_by_cause":{"A":{"AS":0.9,"BS":0.1},"B":{"AS":0.1,"BS":0.9}}}],
        "model_set":[{"id":"m1","provenance":"x"},{"id":"m2","provenance":"y"}]
    }

def receipt():
    return {"status":"EXACT_ROBUST_POLICY_FOUND","root_node_id":"N0","confidence_threshold":0.9,"policy_nodes":[
        {"node_id":"N0","terminal":False,"next_test":"t","branches":[{"outcome":"AS","child_node_id":"NA"},{"outcome":"BS","child_node_id":"NB"}]},
        {"node_id":"NA","terminal":True,"identified_target_class":"A"},
        {"node_id":"NB","terminal":True,"identified_target_class":"B"}
    ]}

def env():
    return {"uncertainty_envelope":{"type":"INDEPENDENT_BINARY_LIKELIHOOD_BOX","likelihood_intervals":[
        {"test_id":"t","cause_id":"A","outcome":"AS","lower":0.6,"upper":0.9},
        {"test_id":"t","cause_id":"B","outcome":"BS","lower":0.6,"upper":0.9}
    ]}}

class R46Tests(unittest.TestCase):
    def parsed(self, d=None):
        d = d or base(); return r46.parse_base(d)

    def test_exact_box_corner_maximum(self):
        d=base(); causes,tests=self.parsed(d); _,vars=r46.parse_continuous_envelope(env(),causes,tests)
        out=r46.exact_box_attack(receipt(),d,vars,causes,tests)
        self.assertEqual(out["status"],"EXACT_CONTINUOUS_BOX_ATTACK_COMPLETED"); self.assertEqual(out["corner_count"],4)
        self.assertAlmostEqual(out["worst_risk"]["evaluation"]["policy_risk"],0.4)
        self.assertEqual(out["extremum_certificate"],"MULTI_AFFINE_BOX_EXTREMA_AT_VERTICES")

    def test_binary_prior_adds_dimension(self):
        d=base(); causes,tests=self.parsed(d); e=env(); e["uncertainty_envelope"]["binary_prior_interval"]={"cause_id":"A","lower":0.3,"upper":0.7}
        _,vars=r46.parse_continuous_envelope(e,causes,tests); out=r46.exact_box_attack(receipt(),d,vars,causes,tests)
        self.assertEqual(out["corner_count"],8)

    def test_bad_class_rejected(self):
        causes,tests=self.parsed()
        with self.assertRaisesRegex(r46.ModelError,"UNSUPPORTED_CONTINUOUS_CLASS"):
            r46.parse_continuous_envelope({"uncertainty_envelope":{"type":"MAGIC"}},causes,tests)

    def test_nonbinary_row_rejected(self):
        d=base(); d["tests"][0]["likelihood_by_cause"]={"A":{"X":.4,"Y":.3,"Z":.3},"B":{"X":.3,"Y":.3,"Z":.4}}
        causes,tests=self.parsed(d); e={"uncertainty_envelope":{"type":"INDEPENDENT_BINARY_LIKELIHOOD_BOX","likelihood_intervals":[{"test_id":"t","cause_id":"A","outcome":"X","lower":.2,"upper":.5}]}}
        with self.assertRaisesRegex(r46.ModelError,"BINARY_ROW_REQUIRED"): r46.parse_continuous_envelope(e,causes,tests)

    def test_duplicate_row_rejected(self):
        d=base(); causes,tests=self.parsed(d); e=env(); e["uncertainty_envelope"]["likelihood_intervals"].append({"test_id":"t","cause_id":"A","outcome":"AS","lower":.5,"upper":.8})
        with self.assertRaisesRegex(r46.ModelError,"DUPLICATE_UNCERTAIN_ROW"): r46.parse_continuous_envelope(e,causes,tests)

    def test_uncalibrated_row_rejected(self):
        d=base(False); causes,tests=self.parsed(d)
        with self.assertRaisesRegex(r46.ModelError,"INTERVAL_TEST_NOT_DECISION_USABLE_CALIBRATED"): r46.parse_continuous_envelope(env(),causes,tests)

    def test_repeated_test_policy_rejected(self):
        x=receipt(); x["policy_nodes"]=[{"node_id":"N0","terminal":False,"next_test":"t","branches":[{"outcome":"AS","child_node_id":"N1"}]},{"node_id":"N1","terminal":False,"next_test":"t","branches":[{"outcome":"AS","child_node_id":"NA"}]},{"node_id":"NA","terminal":True,"identified_target_class":"A"}]
        with self.assertRaisesRegex(r46.ModelError,"REPEATED_TEST_ON_POLICY_PATH_UNSUPPORTED"): r46.validate_policy_tree(x)

    def test_out_of_policy_support_counts_as_risk(self):
        d=base(); causes,tests=self.parsed(d); cand=r46.candidate_from_model(d,{"id":"c","provenance":"x","likelihood_overrides":{"t":{"A":{"AS":.8,"NEW":.2},"B":{"AS":.1,"NEW":.9}}}},causes,tests)
        ev=r46.evaluate_fixed_policy_exact(receipt(),cand,causes,tests)
        self.assertGreater(ev["out_of_policy_support_probability"],0); self.assertAlmostEqual(ev["success_probability"]+ev["policy_risk"],1.0)

    def test_corner_ceiling_fail_closed(self):
        d=base(); causes,tests=self.parsed(d); _,vars=r46.parse_continuous_envelope(env(),causes,tests); out=r46.exact_box_attack(receipt(),d,vars,causes,tests,max_corners=2)
        self.assertEqual(out["status"],"UNKNOWN_RESOURCE_LIMIT")

    def test_exact_cost_for_one_test(self):
        d=base(); causes,tests=self.parsed(d); raw,cand=r46.corner_model(d,[],(),causes,tests); ev=r46.evaluate_fixed_policy_exact(receipt(),cand,causes,tests)
        self.assertAlmostEqual(ev["expected_cost"],2.0); self.assertAlmostEqual(ev["policy_risk"],0.1)

if __name__ == "__main__": unittest.main(verbosity=2)
