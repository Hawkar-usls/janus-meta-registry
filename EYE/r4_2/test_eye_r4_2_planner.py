import importlib.util, json, unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location('r42',HERE/'eye_r4_2_adaptive_witness_planner.py'); r42=importlib.util.module_from_spec(SPEC); assert SPEC and SPEC.loader; SPEC.loader.exec_module(r42)
def load(name): return json.loads((HERE/'benchmarks'/name).read_text(encoding='utf-8'))

class AdaptivePlannerTests(unittest.TestCase):
    def test_synthetic_adaptive_advantage(self):
        r=r42.solve(load('synthetic_adaptive_advantage.json'),'synthetic'); self.assertEqual(r['status'],'EXACT_ADAPTIVE_POLICY_FOUND'); self.assertEqual(r['root_next_test'],'t_root'); self.assertEqual(r['expected_cost_to_identification'],4.0); self.assertEqual(r['worst_case_cost_to_identification'],5.0); self.assertEqual(r['nonadaptive_baseline']['cost'],5.0); self.assertEqual(r['expected_cost_savings_vs_nonadaptive'],1.0)
    def test_search_proof_adaptive_advantage(self):
        r=r42.solve(load('search_proof_adaptive.json'),'searchproof'); self.assertEqual(r['status'],'EXACT_ADAPTIVE_POLICY_FOUND'); self.assertEqual(r['root_next_test'],'provenance_hash_audit'); self.assertAlmostEqual(r['expected_cost_to_identification'],2.8,places=9); self.assertEqual(r['worst_case_cost_to_identification'],4.0); self.assertEqual(r['nonadaptive_baseline']['cost'],4.0); self.assertAlmostEqual(r['expected_cost_savings_vs_nonadaptive'],1.2,places=9)
    def test_palomar_remains_non_identifiable(self):
        r=r42.solve(load('palomar_xe325_adaptive.json'),'palomar'); self.assertEqual(r['status'],'NON_IDENTIFIABLE_UNDER_CURRENT_MEASUREMENT_MODEL'); self.assertTrue(r['exact_policy_search_completed']); self.assertEqual(r['root_greedy_next_test_ranking'],[])
    def test_noninformative_prerequisite_can_unlock_optimal_test(self):
        d={'cause_classes':[{'id':'A'},{'id':'B'}],'tests':[{'id':'prep','cost':1,'outcome_by_cause':{'A':'READY','B':'READY'}},{'id':'deep','cost':1,'depends_on':['prep'],'outcome_by_cause':{'A':'A','B':'B'}},{'id':'universal','cost':3,'outcome_by_cause':{'A':'A','B':'B'}}]}; r=r42.solve(d,'dependency'); self.assertEqual(r['root_next_test'],'prep'); self.assertEqual(r['expected_cost_to_identification'],2.0); self.assertEqual(r['nonadaptive_baseline']['cost'],2.0)
    def test_resource_ceiling_is_unknown_not_negative(self):
        d={'cause_classes':[{'id':'A'},{'id':'B'}],'requirements':{'max_decision_tests':1},'tests':[{'id':'t1','outcome_by_cause':{'A':'A','B':'B'}},{'id':'t2','outcome_by_cause':{'A':'A','B':'B'}}]}; r=r42.solve(d,'resource'); self.assertEqual(r['status'],'UNKNOWN_RESOURCE_LIMIT'); self.assertEqual(r['reason'],'DECISION_TEST_COUNT_EXCEEDS_EXACT_CEILING')
    def test_failure_domain_disjoint_path_gate_changes_policy(self):
        d={'cause_classes':[{'id':'A'},{'id':'B'},{'id':'C'}],'requirements':{'require_failure_domain_disjoint_path':True},'tests':[{'id':'root_shared','cost':1,'failure_domains':['shared'],'outcome_by_cause':{'A':'A','B':'BC','C':'BC'}},{'id':'leaf_shared','cost':1,'failure_domains':['shared'],'outcome_by_cause':{'A':'B','B':'B','C':'C'}},{'id':'universal_independent','cost':4,'failure_domains':['independent'],'outcome_by_cause':{'A':'A','B':'B','C':'C'}}]}; gated=r42.solve(d,'gated'); self.assertAlmostEqual(gated['expected_cost_to_identification'],11/3,places=9); d['requirements']['require_failure_domain_disjoint_path']=False; ungated=r42.solve(d,'ungated'); self.assertAlmostEqual(ungated['expected_cost_to_identification'],5/3,places=9); self.assertGreater(gated['expected_cost_to_identification'],ungated['expected_cost_to_identification'])

if __name__=='__main__': unittest.main()
