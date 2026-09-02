import copy, importlib.util, json, unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location('r44',HERE/'eye_r4_4_robust_witness_planner.py'); r44=importlib.util.module_from_spec(SPEC); assert SPEC and SPEC.loader; SPEC.loader.exec_module(r44)
def load(name): return json.loads((HERE/'benchmarks'/name).read_text(encoding='utf-8'))

class RobustPlannerTests(unittest.TestCase):
    def test_synthetic_robust_advantage(self):
        r=r44.solve(load('synthetic_robust_advantage.json'),'synthetic')
        self.assertEqual(r['status'],'EXACT_ROBUST_POLICY_FOUND'); self.assertEqual(r['root_next_test'],'t_robust'); self.assertEqual(r['robust_cost'],2.0); self.assertEqual(r['worst_model_expected_cost'],2.0)
    def test_search_proof_changes_root_under_robustness(self):
        r=r44.solve(load('search_proof_robust.json'),'searchproof')
        self.assertEqual(r['status'],'EXACT_ROBUST_POLICY_FOUND'); self.assertEqual(r['root_next_test'],'independent_verifier'); self.assertAlmostEqual(r['robust_cost'],4.024,places=9)
    def test_palomar_remains_robust_non_identifiable(self):
        r=r44.solve(load('palomar_xe325_robust.json'),'palomar')
        self.assertEqual(r['status'],'ROBUST_NON_IDENTIFIABLE_UNDER_DECLARED_MODEL_SET'); self.assertTrue(r['exact_policy_search_completed']); self.assertEqual(r['root_robust_next_test_ranking'],[])
    def test_model_set_too_wide_is_distinct(self):
        d={'cause_classes':[{'id':'A','prior':.5},{'id':'B','prior':.5}],'requirements':{'confidence_threshold':.9,'allow_prior_only_identification':True},'tests':[],'model_set':[{'id':'mA','provenance':'synthetic A prior','prior_by_cause':{'A':.95,'B':.05}},{'id':'mB','provenance':'synthetic B prior','prior_by_cause':{'A':.05,'B':.95}}]}
        r=r44.solve(d,'wide'); self.assertEqual(r['status'],'MODEL_SET_TOO_WIDE_FOR_COMMON_ROBUST_IDENTIFICATION'); self.assertTrue(all(r['individual_model_feasibility'].values()))
    def test_uncalibrated_decision_test_rejected(self):
        d={'cause_classes':[{'id':'A'},{'id':'B'}],'tests':[{'id':'t','decision_usable':True,'calibrated':False,'likelihood_by_cause':{'A':{'x':1},'B':{'x':1}}}],'model_set':[{'id':'m1','provenance':'p1'},{'id':'m2','provenance':'p2'}]}
        with self.assertRaisesRegex(r44.ModelError,'UNCALIBRATED_DECISION_TEST'): r44.solve(d)
    def test_missing_model_provenance_rejected(self):
        d={'cause_classes':[{'id':'A'},{'id':'B'}],'tests':[],'model_set':[{'id':'m1'},{'id':'m2','provenance':'p'}]}
        with self.assertRaisesRegex(r44.ModelError,'MISSING_MODEL_PROVENANCE'): r44.solve(d)
    def test_resource_ceiling_is_unknown(self):
        d={'cause_classes':[{'id':'A'},{'id':'B'}],'requirements':{'max_decision_tests':1},'tests':[{'id':'t1','calibrated':True,'likelihood_by_cause':{'A':{'x':.9,'y':.1},'B':{'x':.1,'y':.9}}},{'id':'t2','calibrated':True,'likelihood_by_cause':{'A':{'x':.9,'y':.1},'B':{'x':.1,'y':.9}}}],'model_set':[{'id':'m1','provenance':'p1'},{'id':'m2','provenance':'p2'}]}
        r=r44.solve(d); self.assertEqual(r['status'],'UNKNOWN_RESOURCE_LIMIT'); self.assertEqual(r['reason'],'DECISION_TEST_COUNT_EXCEEDS_EXACT_CEILING')
    def test_cvar_upper_tail(self):
        self.assertAlmostEqual(r44.cvar_upper([(1,.8),(10,.2)],.8),10.0); self.assertAlmostEqual(r44.cvar_upper([(1,.8),(10,.2)],.5),4.6)
    def test_common_support_firewall_blocks_zero_support_model(self):
        d={'cause_classes':[{'id':'A'},{'id':'B'}],'requirements':{'confidence_threshold':.9,'require_common_outcome_support':True},'tests':[{'id':'t','calibrated':True,'likelihood_by_cause':{'A':{'x':.9,'y':.1},'B':{'x':.1,'y':.9}}}],'model_set':[{'id':'m1','provenance':'p1'},{'id':'m2','provenance':'p2','likelihood_overrides':{'t':{'A':{'x':1.0,'y':0.0},'B':{'x':.2,'y':.8}}}}]}
        r=r44.solve(d); self.assertEqual(r['status'],'ROBUST_NON_IDENTIFIABLE_UNDER_DECLARED_MODEL_SET')
    def test_failure_domain_gate_changes_cost(self):
        d={'cause_classes':[{'id':'A','prior':1/3},{'id':'B','prior':1/3},{'id':'C','prior':1/3}],'requirements':{'confidence_threshold':.9,'require_common_outcome_support':True,'require_failure_domain_disjoint_path':False},'tests':[{'id':'root','cost':1,'calibrated':True,'failure_domains':['shared'],'likelihood_by_cause':{'A':{'A':.99,'BC':.01},'B':{'A':.01,'BC':.99},'C':{'A':.01,'BC':.99}}},{'id':'leaf','cost':1,'calibrated':True,'failure_domains':['shared'],'likelihood_by_cause':{'A':{'B':.5,'C':.5},'B':{'B':.99,'C':.01},'C':{'B':.01,'C':.99}}},{'id':'universal','cost':4,'calibrated':True,'failure_domains':['independent'],'likelihood_by_cause':{'A':{'A':.98,'B':.01,'C':.01},'B':{'A':.01,'B':.98,'C':.01},'C':{'A':.01,'B':.01,'C':.98}}}],'model_set':[{'id':'m1','provenance':'p1'},{'id':'m2','provenance':'p2'}]}
        ung=r44.solve(copy.deepcopy(d),'ungated'); d['requirements']['require_failure_domain_disjoint_path']=True; gat=r44.solve(d,'gated'); self.assertEqual(ung['status'],'EXACT_ROBUST_POLICY_FOUND'); self.assertEqual(gat['status'],'EXACT_ROBUST_POLICY_FOUND'); self.assertGreater(gat['robust_cost'],ung['robust_cost'])

if __name__=='__main__': unittest.main()
