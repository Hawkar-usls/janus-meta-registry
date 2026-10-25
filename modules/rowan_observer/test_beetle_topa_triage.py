"""Independent synthetic triage tests: ACK does not establish scientific validation."""
import importlib.util,sys
from pathlib import Path
import unittest
p=Path(__file__).resolve().parent/"beetle_topa_triage.py"
spec=importlib.util.spec_from_file_location("beetle_topa_triage",p)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
def fixture():
    ack={"schema":"janus.beetle.inbox_ack.v1",
         "target_repository":m.TARGET,"status":"INBOX_DURABLE_UNVERIFIED__NOT_RUNTIME_CONSUMPTION",
         "scientific_authority_delta":0,"last_sequence":59,"batch_id":"a"*20,"sha256":"b"*64}
    x={"schema":"janus.beetle.repo_memory_item.v2","target_repository":m.TARGET,
       "base_direction_id":"protein_stability_falsifiers","candidate_id":"c"*24,
       "source_context_sha256":"d"*64,"mirror_lens":"COUNTEREVIDENCE",
       "epistemic_status":"DISCOVERY_INBOX__UNVERIFIED__NO_PROOF_AUTHORITY",
       "title":"Protein mutation stability experimental benchmark",
       "summary":"Experimental protein stability of mutation variants","source":"arxiv",
       "url":"https://arxiv.org/abs/2601.12345","score":3.5}
    batch={"schema":"janus.beetle.repo_memory_batch.v1","batch_id":ack["batch_id"],
           "target_repository":m.TARGET,
           "claim_ceiling":"DISCOVERY_MEMORY_ONLY__TARGET_REPO_MUST_VERIFY_INDEPENDENTLY",
           "fragment_count":1,"fragment_index":1,"items":[x]}
    return ack,batch,"e"*64
class Tests(unittest.TestCase):
    def test_good_candidate_remains_unverified(self):
        a,b,c=fixture();r=m.triage(a,b,c)
        self.assertEqual(r["counts"]["domain_relevant_unique"],1)
        self.assertEqual(r["candidate_previews"][0]["topa_primary_data_audit"],"NOT_PERFORMED")
        self.assertEqual(r["authority"]["new_credit_spend"],0)
    def test_unrelated_article_rejected_by_topa_independently(self):
        a,b,c=fixture();b["items"][0]["title"]="Cloud incident forecast";b["items"][0]["summary"]="Independent replication and benchmark"
        self.assertEqual(m.triage(a,b,c)["counts"]["domain_relevant_unique"],0)
    def test_ack_batch_mismatch_rejected(self):
        a,b,c=fixture();b["batch_id"]="0"*20
        with self.assertRaises(m.Hold):m.triage(a,b,c)
    def test_inbox_not_verified_claim_ceiling(self):
        a,b,c=fixture();a["status"]="SCIENTIFICALLY_VERIFIED"
        with self.assertRaises(m.Hold):m.triage(a,b,c)
    def test_disallowed_domain_rejected(self):
        a,b,c=fixture();b["items"][0]["url"]="https://danger.example/path"
        with self.assertRaises(m.Hold):m.triage(a,b,c)
    def test_cross_target_block(self):
        a,b,c=fixture();b["items"][0]["target_repository"]="Hawkar-usls/SkinGPT"
        with self.assertRaises(m.Hold):m.triage(a,b,c)
    def test_duplicate_item_only_once(self):
        a,b,c=fixture();b["items"].append(dict(b["items"][0]))
        self.assertEqual(m.triage(a,b,c)["counts"]["domain_relevant_unique"],1)
    def test_missing_receiver_commit_rejected(self):
        a,b,c=fixture()
        with self.assertRaises(m.Hold):m.triage(a,b,"not-a-commit")
    def test_four_lenses_preserved_no_proof(self):
        a,b,c=fixture()
        for lens in ("FORWARD","REVERSE","COUNTEREVIDENCE","CONTROL"):
            b["items"][0]["mirror_lens"]=lens
            self.assertFalse(m.triage(a,b,c)["authority"]["discovery_candidate_is_evidence"])
if __name__=="__main__":unittest.main()
