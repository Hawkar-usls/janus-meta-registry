"""Fail-closed offline controls for P0.3 input preflight and privacy scope."""
import copy
import importlib.util
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parents[1]
f = BASE/"modules/autonomy_loop/p03_preflight.py"
spec = importlib.util.spec_from_file_location("p03",f)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def sample():
    rows={}
    for name in m.RECEIVERS:
        rows[name]={"status":"UP_TO_DATE","produced":4,"confirmed":4,"pending":0}
    rows[m.PRIVATE]={"status":"ACK_UNAVAILABLE","produced":1,"confirmed":0,"pending":1}
    health={"schema":"janus.beetle.delivery_health.v1",
            "ack_semantics":"INBOX_DURABLE_ONLY_NOT_RUNTIME_CONSUMPTION",
            "scientific_authority_delta":0,
            "repositories":rows,"total_pending":1}
    gate={"schema":"janus.beetle.producer_routing_gate.v1",
          "ack_semantics":health["ack_semantics"],"scientific_authority_delta":0,
          "rowan_credit_authority_delta":0,
          "new_packet_queue_mutations_performed_by_gate":0,
          "receiver_count":len(m.RECEIVERS),"routing_allowed":True,
          "reason":"ROUTING_ALLOWED","total_pending_before_route":0}
    home={"schema":"JANUS_HABITAT_CLOUD_HOME_STATE_V1",
          "status":"CLOUD_HOME_ACTIVE","durable_identity":"JANUS_HABITAT_RESIDENT_V1",
          "sequence":272,"authority_delta":0,"source_writeback_default":"DENY",
          "destructive_action":"FORBIDDEN","last_receipt_sha256":"a"*64,
          "source_main_sha":"b"*40,
          "pc_required":False,"remote_desktop_required":False,"nas_required":False,
          "lan_required":False,"process_uptime_required":False,
          "beetle_memory":{"status":"HASH_MATCHED_UNVERIFIED_CONTEXT_STAGED",
                           "scientific_authority_delta":0,
                           "command_authority":False,"external_effect_authority":False}}
    d={"beetle_delivery":health,"beetle_gate":gate,"home":home,"genesis_current":{}}
    return {k:{"status":"OBSERVED","data":v, **({"commit_sha":"b"*40} if k=="genesis_current" else {})} for k,v in d.items()}


class PreflightTests(unittest.TestCase):
    def test_realistic_private_ack_hold_without_faking_p03_pass(self):
        r=m.preflight(sample())
        self.assertEqual(r["status"],"P03_PREFLIGHT_BLOCKED")
        self.assertIn("PRIVATE_ACK_AUTH_UNKNOWN",r["blockers"])
        self.assertEqual(r["public_receiver_count"],18)
        self.assertEqual(r["public_receiver_pending"],0)
        self.assertFalse(r["p03_acceptance"])
        self.assertFalse(r["runtime_consumption_attested"])

    def test_pre_route_gate_not_falsely_bound_to_post_route_queue(self):
        x=sample()
        row=x["beetle_delivery"]["data"]["repositories"]["Hawkar-usls/Janus_Genesis"]
        row.update(status="PENDING",produced=5,confirmed=4,pending=1)
        x["beetle_delivery"]["data"]["total_pending"]=2
        report=m.preflight(x)
        self.assertEqual(report["producer_after_route_pending"],2)
        self.assertTrue(report["pre_route_gate_allowed"])
        self.assertIn("PUBLIC_RECEIVER_ACK_PENDING", report["blockers"])

    def test_full_public_and_claimed_private_never_auto_accepts(self):
        x=sample()
        x["beetle_delivery"]["data"]["repositories"][m.PRIVATE].update(
            status="UP_TO_DATE",confirmed=1,pending=0)
        x["beetle_delivery"]["data"]["total_pending"]=0
        r=m.preflight(x)
        self.assertEqual(r["status"],"P03_PREFLIGHT_CANDIDATE_ONLY")
        self.assertFalse(r["p03_acceptance"])
        self.assertEqual(r["private_ack_visibility"],
                         "CLAIMED_IN_PRODUCER_TELEMETRY_NOT_INDEPENDENTLY_REPLAYED")

    def test_forged_totals_authority_or_receiver_identity_fail_closed(self):
        x=sample()
        candidates=[]
        y=copy.deepcopy(x); y["beetle_delivery"]["data"]["total_pending"]=100; candidates.append(y)
        y=copy.deepcopy(x); y["beetle_delivery"]["data"]["repositories"].pop(m.PRIVATE); candidates.append(y)
        y=copy.deepcopy(x); y["beetle_delivery"]["data"]["repositories"][m.PRIVATE]["confirmed"]=2; candidates.append(y)
        y=copy.deepcopy(x); y["beetle_gate"]["data"]["receiver_count"]=18; candidates.append(y)
        y=copy.deepcopy(x); y["home"]["data"]["authority_delta"]=1; candidates.append(y)
        y=copy.deepcopy(x); y["home"]["data"]["pc_required"]=True; candidates.append(y)
        y=copy.deepcopy(x); y["beetle_delivery"]["status"]="UNKNOWN"; candidates.append(y)
        for i,y in enumerate(candidates):
            with self.subTest(case=i):
                self.assertEqual(m.preflight(y)["status"],"HOLD_P03_SOURCE_INTEGRITY")

    def test_older_home_main_commit_is_not_promoted(self):
        x=sample()
        x["genesis_current"]["commit_sha"]="c"*40
        r=m.preflight(x)
        self.assertIn("HOME_SOURCE_HEAD_DRIFT",r["blockers"])
        self.assertFalse(r["p03_acceptance"])


if __name__=="__main__":
    unittest.main()
