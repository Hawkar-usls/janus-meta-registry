import unittest
from datetime import datetime,timezone,timedelta
from tools import janus_sentinel_mesh_24h_audit as m
REPO="Hawkar-usls/Janus-Demiurge"
NOW=datetime(2026,11,17,15,21,tzinfo=timezone.utc)
def r(k,t,*,event="schedule",conclusion="success"):
    return {"id":k,"created_at":t.isoformat(),"head_branch":"main",
            "event":event,"status":"completed","conclusion":conclusion}
class Audit(unittest.TestCase):
    def test_before_24h_never_passes(self):
        early=datetime(2026,11,15,16,tzinfo=timezone.utc)
        self.assertEqual(m.judge(REPO,[r(1,early)],early)["status"],
                         "HOLD_24H_NOT_ELAPSED_SINCE_DEPLOY")
    def test_push_and_manual_do_not_count(self):
        events=[r(i+1,NOW-timedelta(minutes=15*i),event="push")
                for i in range(96)]
        q=m.judge(REPO,events,NOW)
        self.assertEqual(q["observed_success"],0)
        self.assertEqual(q["status"],"HOLD_24H_DELIVERY_OR_RELIABILITY")
    def test_full_24h_real_delivery(self):
        runs=[r(i+1,NOW-timedelta(minutes=15*i+5))
              for i in range(96)]
        q=m.judge(REPO,runs,NOW)
        self.assertEqual(q["observed_success"],96)
        self.assertEqual(q["status"],"PASS_OBSERVED_24H_SCHEDULE_DELIVERY")
    def test_missing_gap_or_failed_schedule_holds(self):
        runs=[r(i+1,NOW-timedelta(minutes=15*i+5))
              for i in range(96) if i not in range(20,26)]
        self.assertEqual(m.judge(REPO,runs,NOW)["status"],
                         "HOLD_24H_DELIVERY_OR_RELIABILITY")
        runs=[r(i+1,NOW-timedelta(minutes=15*i+5),
                conclusion=("failure" if i==30 else "success")) for i in range(96)]
        self.assertEqual(m.judge(REPO,runs,NOW)["status"],
                         "HOLD_24H_DELIVERY_OR_RELIABILITY")
    def test_missing_pages_no_fake_pass(self):
        runs=[r(i+1,NOW-timedelta(minutes=15*i+5)) for i in range(96)]
        self.assertEqual(m.judge(REPO,runs,NOW,page_complete=False)["status"],
                         "HOLD_INCOMPLETE_GITHUB_HISTORY")
    def test_api_failure_hold(self):
        obj=m.evaluate("x"*30,now=NOW,
                       fetch=lambda *args: (_ for _ in ()).throw(ValueError("no API")))
        self.assertEqual(obj["status"],"HOLD_NOT_ALL_THREE_VERIFIED")
        self.assertTrue(all(x["no_uptime_proof"] for x in obj["repos"].values()))
