"""Independent synthetic source-binding tests for AURA/Demiurge Meta Registry forge."""
import importlib.util,json,tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location("coordination",ROOT/"coordination_ingest.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def sample():
    state={"schema_id":"janus.rowan.observer_state.v1","latest_durable_external_run":12345,
           "last_completed_mutants":0,"underlying_state_is_derived_from":"a"*64}
    aura={"schema_id":"janus.aura.rowan_hypothesis_packet.v1",
          "source":{"upstream_run":12345,"completed_mutants":0,
                    "state_sha256":m.sha(state),"upstream_artifact_sha256":"a"*64},
          "hypotheses":[{"id":i,"status":"HYPOTHESIS_ONLY__NOT_MEASURED",
                         "empirical_truth_probability":None} for i in m.AURA_HYPOS]}
    aura["packet_digest_sha256"]=m.sha(aura)
    council={"schema_id":"janus.demiurge.rowan_council_proposal.v1",
             "sources":{"meta_registry":{"canonical_run":12345,"sha256":m.sha(state)},
                        "aura_oracle":{"packet_sha256":m.sha(aura),
                                       "packet_digest":aura["packet_digest_sha256"]}},
             "completed_pilot_cases":0,
             "next_beetle_direction_id":"protein_stability_falsifiers",
             "next_aura_question_id":"RAW_ASSAY_LINEAGE",
             "research_status":"PENDING_PRE_REGISTERED_ROWAN_RESULTS",
             "scientific_authority":"NONE__PROPOSAL_NOT_EXPERIMENT",
             "gates":{k:False for k in
                  ("rowan_credit_spend_new","rowan_job_submission_new",
                   "aura_predictions_empirical_evidence","beetle_candidates_empirical_evidence",
                   "production_model_weight_promotion")}}
    council["content_sha256"]=m.sha(council)
    return state,aura,council

class CoordinationTests(unittest.TestCase):
    def test_valid_three_way_source_binding(self):
        s,a,c=sample()
        r=m.clean(s,a,c)
        self.assertEqual(r["observation"]["completed_mutants"],0)
        self.assertFalse(r["authority"]["new_credit_spend"])
    def test_source_changed_stops_archiving(self):
        s,a,c=sample()
        s["last_completed_mutants"]=1
        with self.assertRaises(m.Hold):m.clean(s,a,c)
    def test_oracle_packet_tamper_rejected(self):
        s,a,c=sample()
        a["hypotheses"][0]["empirical_truth_probability"]=.99
        with self.assertRaises(m.Hold):m.clean(s,a,c)
    def test_council_promotes_billing_rejected(self):
        s,a,c=sample()
        c["gates"]["rowan_credit_spend_new"]=True
        c["content_sha256"]=m.sha({k:v for k,v in c.items() if k!="content_sha256"})
        with self.assertRaises(m.Hold):m.clean(s,a,c)
    def test_demiurge_must_match_aura_digest(self):
        s,a,c=sample()
        c["sources"]["aura_oracle"]["packet_sha256"]="b"*64
        c["content_sha256"]=m.sha({k:v for k,v in c.items() if k!="content_sha256"})
        with self.assertRaises(m.Hold):m.clean(s,a,c)
    def test_append_only_deduped_receipts(self):
        s,a,c=sample()
        with tempfile.TemporaryDirectory() as root:
            base=Path(root)/"data/rowan"
            base.mkdir(parents=True)
            (base/"CANONICAL_STATE.json").write_text(json.dumps(s))
            with patch.object(m,"fetch",side_effect=[a,c]):
                p=m.ingest(root)
            raw=p.read_bytes()
            with patch.object(m,"fetch",side_effect=[a,c]):
                again=m.ingest(root)
            self.assertEqual(again,p)
            self.assertEqual(p.read_bytes(),raw)
            self.assertTrue((base/"coordination/LATEST_COORDINATION_STATE.json").exists())
            self.assertEqual(len(list((base/"coordination/receipts").glob("*.json"))),1)
if __name__=="__main__":unittest.main()
