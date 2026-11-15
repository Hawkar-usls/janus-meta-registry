"""JANUS v5.0 independent Meta EYE source admission (no network)."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from tools import janus_v50_verified_json_intake as m


def fixture():
    obj={
        "schema":"janus.essence.continual_prospective_first_trial_evidence/4.9",
        "status":"HOLD_REPLAY_DID_NOT_CLEAR_PREDECLARED_GATES",
        "deployment":{"production_admission":False},
        "interpretation":{"external_custodian":False},
        "results":{
            "fresh_unseen_legacy_oracle":{"replay_exact":16,"naive_exact":8},
            "lapis_paraphrased_source":{"replay_exact":0,"n":6}
        }
    }
    raw=m.canonical(obj)
    rawsha=hashlib.sha256(raw).hexdigest()
    sem=hashlib.sha256(m.canonical(obj)+b"\n").hexdigest()
    commit="a"*40
    tasksha="b"*64
    fact={
        "schema":m.LEARNING_SCHEMA,
        "status":"TOPA_STRUCTURAL_SOURCE_VERIFIED_NOT_SCIENTIFIC_TRUTH",
        "source_repository":"Hawkar-usls/Janus-Demiurge",
        "source_path":m.SOURCE,"source_commit":commit,
        "source_raw_sha256":rawsha,
        "topa_code_commit":m.TOPA_SHA,
        "topa_semantic_stream_sha256":sem,
        "research_experiment_run_id":43755360999,
        "research_verdict":obj["status"],
        "proof_authority":"SOURCE_INTEGRITY_ONLY",
        "confirmed_counts":{
            "replay_fresh_old":16,"naive_fresh_old":8,
            "replay_new_lapis_exact":0,"new_lapis_count":6},
        "epistemic_boundary":{
            "topa_bytes_are_world_truth":False,
            "model_output_is_independent_validation":False,
            "used_as_direct_neural_supervision":False,
            "automatic_model_promotion":False,
            "verified_negative_results_preserved":True
        }
    }
    packet={
        "schema":m.PACKET_SCHEMA,
        "status":"SOURCE_INTEGRITY_VERIFIED_DISPATCH_REQUEST_ONLY",
        "source_path":m.SOURCE,"source_commit":commit,
        "source_raw_sha256":rawsha,"topa_code_commit":m.TOPA_SHA,
        "beetle_task_id":"janus_json_registry_provenance_audit",
        "beetle_intent_sha256":tasksha,
        "source_beetle_intent":"EXPLICIT_USER_DISCOVERY_STEERING",
        "native_model":{"native_proposed_this_user_task":False},
        "external_scientific_validation":False,"production_write_authority":False,
        "sentinel_dispatch":False,"source_fact_json":fact
    }
    packet["receipt_sha256"]=m.sha(packet)
    index={
        "schema":m.LATEST_SCHEMA,"packet_id":packet["receipt_sha256"],
        "source_sha256":rawsha,"source_commit":commit,
        "beetle_intent_sha256":tasksha,
        "science_truth_authority":False,"topa_structural_only":True,
    }
    return raw,index,packet


class MetaV50Tests(unittest.TestCase):
    def test_independent_source_packet_and_negative_fact(self):
        raw,index,packet=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"source.json"
            path.write_bytes(raw)
            actual=m.verify(index,packet,path)
            self.assertEqual(actual["status"],"SOURCE_AND_TOPA_JSON_HASH_RECHECK_PASS")
            self.assertEqual(actual["factual_experiment_status"],
                             "HOLD_REPLAY_DID_NOT_CLEAR_PREDECLARED_GATES")
            self.assertEqual(actual["replay_vs_naive_old_route"],{"replay":16,"naive":8})
            self.assertFalse(actual["scientific_truth_admission"])
            self.assertFalse(actual["model_weight_change"])
            self.assertEqual(actual["record_sha256"],m.sha({
                k:v for k,v in actual.items() if k!="record_sha256"}))

    def test_forged_topa_science_promotion_refused(self):
        raw,index,packet=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"source.json"
            file.write_bytes(raw)
            tampered=copy.deepcopy(packet)
            tampered["sentinel_dispatch"]=True
            tampered["receipt_sha256"]=m.sha({
                k:v for k,v in tampered.items() if k!="receipt_sha256"})
            with self.assertRaisesRegex(ValueError,"ESCALATION"):
                m.verify(index,tampered,file)
            tampered=copy.deepcopy(packet)
            tampered["source_fact_json"]["epistemic_boundary"]["topa_bytes_are_world_truth"]=True
            tampered["receipt_sha256"]=m.sha({
                k:v for k,v in tampered.items() if k!="receipt_sha256"})
            index["packet_id"]=tampered["receipt_sha256"]
            with self.assertRaisesRegex(ValueError,"AUTHORITY"):
                m.verify(index,tampered,file)

    def test_source_changed_and_unverified_metrics_refused(self):
        raw,index,packet=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"source.json"
            p.write_bytes(raw+b" ")
            with self.assertRaisesRegex(ValueError,"SOURCE_BYTES"):
                m.verify(index,packet,p)
            p.write_bytes(raw)
            wrong=copy.deepcopy(packet)
            wrong["source_fact_json"]["confirmed_counts"]["replay_fresh_old"]=14
            wrong["receipt_sha256"]=m.sha({k:v for k,v in wrong.items()
                                            if k!="receipt_sha256"})
            index["packet_id"]=wrong["receipt_sha256"]
            with self.assertRaisesRegex(ValueError,"METRIC_MISMATCH"):
                m.verify(index,wrong,p)

    def test_duplicate_index_not_interpreted_as_two_trials(self):
        raw,index,packet=fixture()
        self.assertEqual(index["source_sha256"],packet["source_raw_sha256"])
        wrong=copy.deepcopy(index)
        wrong["source_commit"]="0"*40
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"original.json"
            path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError,"SOURCE_INDEX"):
                m.verify(wrong,packet,path)


if __name__=="__main__":
    unittest.main()
