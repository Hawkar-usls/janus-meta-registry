"""Only synthetic fixtures. Tests never access Rowan, GitHub or real logs."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

MODULE=Path(__file__).with_name('ecosystem_sync_witness.py')
spec=importlib.util.spec_from_file_location('rowan_ecosystem_sync',MODULE)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def mock_inputs():
    run=40520611650; art='3'*64
    meta={"schema_id":"janus.rowan.observer_state.v1","latest_durable_external_run":run,"last_completed_mutants":8,"underlying_state_is_derived_from":art}
    pipeline={"latest_archived_source_run":run,"latest_completed_source_run":run,"completed_mutants":8,"archive_status":"ARCHIVE_CURRENT","credit_cap_violations":[],"science_gates":{"new_billing_authorized_by_watchdog":False,"model_production_promotion":False,"wetlab_independent_validation":"OPEN"}}
    aura={"schema_id":"janus.aura.rowan_hypothesis_packet.v1","source":{"upstream_run":run,"completed_mutants":8,"state_sha256":m.sha_obj(meta)},"hypotheses":[{"status":"HYPOTHESIS_ONLY__NOT_MEASURED","empirical_truth_probability":None} for _ in range(4)],"bounded_authority":{"may_submit_rowan_jobs":False,"may_modify_rowan_credit_budget":False}}
    aura["packet_digest_sha256"]=m.sha_obj(aura)
    council={"sources":{"meta_registry":{"canonical_run":run,"sha256":m.sha_obj(meta)},"aura_oracle":{"packet_sha256":m.sha_obj(aura),"packet_digest":aura["packet_digest_sha256"]}},"scientific_authority":"NONE__PROPOSAL_NOT_EXPERIMENT","gates":{"rowan_credit_spend_new":False,"production_model_weight_promotion":False}}
    council["content_sha256"]=m.sha_obj(council)
    receipt={"sources":{"meta_canonical_run":run,"meta_canonical_sha256":m.sha_obj(meta),"aura_packet_sha256":m.sha_obj(aura),"demiurge_council_sha256":m.sha_obj(council)},"observation":{"completed_mutants":8},"authority":{"new_credit_spend":False,"new_rowan_jobs":False,"hypotheses_are_empirical_proof":False}}
    receipt["source_binding_sha256"]=m.sha_obj(receipt)
    pointer={"meta_canonical_run":run,"source_binding_sha256":receipt["source_binding_sha256"],"receipt_path":"data/rowan/coordination/receipts/ROWAN-COUNCIL-40520611650-"+receipt["source_binding_sha256"][:16]+".json"}
    shadow={"schema_id":"janus.rowan.bbc1.sequence_shadow_ridge.v1","authority":{"deployment":"SHADOW_ONLY"}}
    shadow_raw=json.dumps(shadow).encode()
    topa={"schema_id":"janus.topa.independent_shadow_replay.v1","audit":"PASS_INDEPENDENT_WITHIN_ASSAY_REPLAY","promotion_gate":"SHADOW_ONLY","model_file_sha256":hashlib.sha256(shadow_raw).hexdigest()}
    marker="ROWAN_CROSS_ORGAN_SOURCE_MISMATCH_HOLD; credentials: 'omit'; method: 'GET'; SYNCED_SOURCE_POINTERS_READ_ONLY"
    genesis={"schema":"janus.genesis.rowan_evidence_source_link.v1","authority":{"rowanJobs":False,"changeWorld":False}}
    topa_repo={"schema":"janus.topa.rowan_independent_replay_source_link.v1","authority":{"credits":False}}
    data={"canonical":meta,"pipeline":pipeline,"aura":aura,"council":council,"receipt":receipt,"pointer":pointer,
          "shadow":shadow,"topa":topa,"beetle":{"directions":[{"id":"protein_stability_falsifiers","enabled":True,"mirror_lenses":["FORWARD","REVERSE","COUNTEREVIDENCE","CONTROL"]}]},
          "hrain":marker,"inaihr":marker,"genesis":genesis,"topa_repo":topa_repo,"tranception":{"schema_id":"janus.tranception.rowan.discovery_manifest.v1"}}
    return data,{"shadow":shadow_raw}

class TestSyncWitness(unittest.TestCase):
    def test_bounded_source_authority_passes(self):
        d,raw=mock_inputs();r=m.verify(d,raw)
        self.assertEqual(r["status"],"PASS_PUBLIC_SOURCE_BINDINGS_NOT_SCIENCE_VALIDATION")
        self.assertEqual(r["completedMutants"],8)
        self.assertEqual(r["creditsSpentByWitness"],0)
        self.assertEqual(r["independentWetlab"],"OPEN")
    def test_stale_meta_coordination_fails(self):
        d,raw=mock_inputs();d["pointer"]["meta_canonical_run"]=40452476743
        with self.assertRaisesRegex(m.Hold,"COORDINATION_POINTER_STALE"):
            m.verify(d,raw)
    def test_tampered_aura_hypothesis_fails(self):
        d,raw=mock_inputs();d["aura"]["hypotheses"][0]["empirical_truth_probability"]=0.8
        with self.assertRaisesRegex(m.Hold,"AURA_HYPOTHESIS_INTEGRITY_HOLD"):
            m.verify(d,raw)
    def test_new_billing_authority_fails(self):
        d,raw=mock_inputs();d["pipeline"]["science_gates"]["new_billing_authorized_by_watchdog"]=True
        with self.assertRaisesRegex(m.Hold,"ROWAN_BUDGET_AUTHORITY_HOLD"):
            m.verify(d,raw)
    def test_shadow_model_mismatch_fails(self):
        d,raw=mock_inputs();raw["shadow"]=b'{"not":"same"}'
        with self.assertRaisesRegex(m.Hold,"TOPA_NUMERICAL_REPLAY_HOLD"):
            m.verify(d,raw)
    def test_legacy_consumer_without_readonly_flag_fails(self):
        d,raw=mock_inputs();d["inaihr"]="unverified alternative"
        with self.assertRaisesRegex(m.Hold,"MINDMAP_READONLY_LINK_MISSING"):
            m.verify(d,raw)
    def test_genesis_authority_escalation_fails(self):
        d,raw=mock_inputs();d["genesis"]["authority"]["rowanJobs"]=True
        with self.assertRaisesRegex(m.Hold,"GENESIS_SOURCE_AUTHORITY_HOLD"):
            m.verify(d,raw)
    def test_unapproved_uri_rejected_without_network(self):
        with self.assertRaisesRegex(m.Hold,"SOURCE_URL_NOT_ALLOWLISTED"):
            m.fetch("Hawkar-usls/janus-meta-registry/main/../../private")
if __name__=="__main__":unittest.main()
