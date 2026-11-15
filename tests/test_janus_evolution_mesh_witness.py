import unittest
from tools import janus_evolution_mesh_witness as w

def ck(value,parent=None):
    x={"schema":"janus.sentinel.transformer_checkpoint/1.0",
       "production_authority":False,"dispatch_authority":False,
       "external_independent_validation":False,
       "model_type":"CAUSAL_ATTENTION_SHARED_A_B",
       "weights":{"tiny.weight":[value]}}
    if parent is not None:
        x.update(parent_checkpoint_sha256=parent,prospective_after_parent=True,
                 replaces_previous=False)
    x["checkpoint_sha256"]=w.digest(x)
    return x

def mf(repo):
    return {"schema":"janus.essence.microkernel/0.1","repository":repo,
            "enabled":False,"activation":"EXPLICIT_READONLY_TEST_ONLY",
            "birth_policy":"PROPOSAL_ONLY",
            "capabilities":{"network":False,"repo_write":False},
            "microkernels":[{"id":"test-core","generation":0,"gene_sources":["JGPT1"]}]}

def fixture():
    a=ck(1);b=ck(2,a["checkpoint_sha256"])
    p={"schema":"janus.sentinel.precommitted_weight_challenge/1.0",
       "candidate_file":"sentinel/model/candidates/123.json",
       "source_run_id":"123",
       "candidate_checkpoint_sha256":b["checkpoint_sha256"],
       "parent_checkpoint_sha256":a["checkpoint_sha256"],
       "production_authority":False,"research_only":True}
    p["receipt_sha256"]=w.digest(p)
    return a,p,b,{r:mf(r) for r in (w.DEMI,w.GEN,w.META)}

class EvolutionContract(unittest.TestCase):
    def test_chain_does_not_prove_improvement(self):
        q=w.validate(*fixture())
        self.assertTrue(q["parent_snapshot_available_for_rollback"])
        self.assertFalse(q["prospective_neural_gain_verified"])
        self.assertFalse(q["service_update_authorized"])
        self.assertFalse(q["rollback_actually_executed"])
    def test_reject_mutated_neural_chain(self):
        a,p,b,ms=fixture();b["weights"]["tiny.weight"][0]=3
        with self.assertRaises(ValueError):w.validate(a,p,b,ms)
        a,p,b,ms=fixture();p["parent_checkpoint_sha256"]="0"*64
        with self.assertRaises(ValueError):w.validate(a,p,b,ms)
    def test_reject_privileged_or_invalid_microcores(self):
        a,p,b,ms=fixture();ms[w.GEN]["enabled"]=True
        with self.assertRaises(ValueError):w.validate(a,p,b,ms)
        a,p,b,ms=fixture();ms[w.META]["microkernels"][0]["generation"]=-1
        with self.assertRaises(ValueError):w.validate(a,p,b,ms)
    def test_reject_unknown_source(self):
        with self.assertRaises(ValueError):
            w.fetch_json("attacker/repo",w.MANIFEST,"main","x"*40)
        with self.assertRaises(ValueError):
            w.fetch_json(w.GEN,"arbitrary.py","main","x"*40)
    def test_hold_without_fake_pass(self):
        x=w.run("x"*30,fetch=lambda *args:
                (_ for _ in ()).throw(ValueError("missing")))
        self.assertEqual(x["status"],"HOLD_SOURCE_UNAVAILABLE_OR_LINEAGE_INVALID")
        self.assertFalse(x["verdict"]["verified_gain"])
