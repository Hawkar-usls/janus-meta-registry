import importlib.util, json, unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location('r43',HERE/'eye_r4_3_stochastic_witness_planner.py'); r43=importlib.util.module_from_spec(SPEC); assert SPEC and SPEC.loader; SPEC.loader.exec_module(r43)
def load(name): return json.loads((HERE/'benchmarks'/name).read_text(encoding='utf-8'))

class StochasticPlannerTests(unittest.TestCase):
    def test_synthetic_noisy_policy(self):
        r=r43.solve(load('synthetic_noisy_adaptive.json'),'synthetic')
        self.assertEqual(r['status'],'EXACT_STOCHASTIC_POLICY_FOUND')
        self.assertEqual(r['root_next_test'],'t_root')
        self.assertAlmostEqual(r['expected_cost_to_confident_identification'],2.445,places=9)
        self.assertEqual(r['worst_case_cost_to_confident_identification'],8.0)
    def test_posterior_nodes_reach_threshold_only_at_terminal(self):
        r=r43.solve(load('synthetic_noisy_adaptive.json'),'synthetic')
        for n in r['policy_nodes']:
            conf=max(n['posterior_by_target'].values())
            if n['terminal']: self.assertGreaterEqual(conf+1e-12,0.9)
            else: self.assertLess(conf,0.9+1e-12)
    def test_stress_scenario_detects_model_uncertainty(self):
        r=r43.solve(load('synthetic_noisy_adaptive.json'),'synthetic')
        s=r['stress_test']; self.assertEqual(s['status'],'MODEL_UNCERTAIN_UNDER_DECLARED_STRESS_SCENARIOS')
        row=s['scenarios'][0]; self.assertAlmostEqual(row['success_probability'],0.84,places=9); self.assertAlmostEqual(row['unresolved_probability'],0.16,places=9); self.assertEqual(row['wrong_confident_probability'],0.0)
    def test_search_proof_stochastic(self):
        r=r43.solve(load('search_proof_stochastic.json'),'searchproof')
        self.assertEqual(r['status'],'EXACT_STOCHASTIC_POLICY_FOUND'); self.assertEqual(r['root_next_test'],'provenance_hash_audit'); self.assertAlmostEqual(r['expected_cost_to_confident_identification'],2.83,places=9); self.assertEqual(r['worst_case_cost_to_confident_identification'],4.0)
    def test_palomar_remains_non_identifiable(self):
        r=r43.solve(load('palomar_xe325_stochastic.json'),'palomar'); self.assertEqual(r['status'],'NON_IDENTIFIABLE_UNDER_CURRENT_STOCHASTIC_MODEL'); self.assertEqual(r['root_greedy_next_test_ranking'],[])
    def test_uncalibrated_probability_cannot_drive_decision(self):
        d={'cause_classes':['A','B'],'tests':[{'id':'t','decision_usable':True,'calibrated':False,'likelihood_by_cause':{'A':{'x':1},'B':{'y':1}}}]}
        with self.assertRaisesRegex(r43.ModelError,'UNCALIBRATED_DECISION_TEST'): r43.solve(d,'uncalibrated')
    def test_prior_only_confidence_is_blocked_by_default(self):
        d={'cause_classes':[{'id':'A','prior':0.99},{'id':'B','prior':0.01}],'requirements':{'confidence_threshold':0.95},'tests':[]}
        r=r43.solve(d,'priorblocked'); self.assertEqual(r['status'],'NON_IDENTIFIABLE_UNDER_CURRENT_STOCHASTIC_MODEL')
        d['requirements']['allow_prior_only_identification']=True; r2=r43.solve(d,'priorallowed'); self.assertEqual(r2['status'],'BASELINE_ALREADY_CONFIDENT'); self.assertEqual(r2['expected_cost_to_confident_identification'],0.0)
    def test_resource_ceiling_is_unknown_not_negative(self):
        d={'cause_classes':['A','B'],'requirements':{'max_decision_tests':1},'tests':[{'id':'t1','calibrated':True,'likelihood_by_cause':{'A':{'a':1},'B':{'b':1}}},{'id':'t2','calibrated':True,'likelihood_by_cause':{'A':{'a':1},'B':{'b':1}}}]}
        r=r43.solve(d,'resource'); self.assertEqual(r['status'],'UNKNOWN_RESOURCE_LIMIT'); self.assertEqual(r['reason'],'DECISION_TEST_COUNT_EXCEEDS_EXACT_CEILING')

if __name__=='__main__': unittest.main()
