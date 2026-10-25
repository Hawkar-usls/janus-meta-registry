"""Synthetic, network-free tests for exact cross-repository pipeline watchdog."""
import importlib.util
import json
import hashlib
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import TestCase, main

spec=importlib.util.spec_from_file_location(
    "pipeline_watchdog", Path(__file__).parent/"pipeline_watchdog.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

NOW=datetime(2026,10,25,12,0,tzinfo=timezone.utc)

def fixtures():
    tmp=tempfile.TemporaryDirectory()
    root=Path(tmp.name)
    base=root/"data"/"rowan"
    (base/"receipts").mkdir(parents=True)
    (base/"learned").mkdir()
    (base/"topa").mkdir()
    (base/"coordination").mkdir()
    state={
        "schema_id":"janus.rowan.observer_state.v1",
        "latest_durable_external_run":12345,
        "last_completed_mutants":1,
        "underlying_state_is_derived_from":"a"*64,
        "autonomous_spend_authority":"ONLY_FROZEN_EIGHT_MUTANT_S2_WITH_EXISTING_WEEKLY_BUDGET",
        "new_unreviewed_studies":"PROPOSAL_ONLY_NOT_AUTO_EXECUTED",
        "budget_guard_alert_mutations":[]
    }
    (base/"CANONICAL_STATE.json").write_text(json.dumps(state))
    receipt={"source":{"run_id":12345,"source_artifact_sha256":"a"*64},
             "calibration":{"eight_mutants_with_provider_results":1}}
    (base/"receipts"/"ROWAN-S2-12345-mock.json").write_text(json.dumps(receipt))
    modelpath=base/"learned"/"SHADOW-BBC1-test.json"
    modelpath.write_text('{"weights":[1]}\n')
    (base/"topa"/"TOPA-SHADOW-test.json").write_text(json.dumps({
        "schema_id":"janus.topa.independent_shadow_replay.v1",
        "audit":"PASS_INDEPENDENT_WITHIN_ASSAY_REPLAY",
        "promotion_gate":"SHADOW_ONLY",
        "fundamental_model_weights_updated":False,
        "model_file_sha256":hashlib.sha256(modelpath.read_bytes()).hexdigest()}))
    (base/"coordination"/"LATEST_COORDINATION_STATE.json").write_text(
        json.dumps({"meta_canonical_run":12345}))
    runs=[{"id":12345,"status":"completed","conclusion":"success",
           "head_branch":"main","event":"workflow_dispatch",
           "created_at":"2026-10-25T11:00:00Z"}]
    return tmp,root,base,state,runs

class PipelineWatchdogTests(TestCase):
    def setup_fixture(self):
        temp,root,base,state,runs=fixtures()
        self.addCleanup(temp.cleanup)
        return root,base,state,runs

    def test_live_one_of_eight_has_healthy_status_and_no_spend(self):
        root,_,_,runs=self.setup_fixture()
        r=m.evaluate(root,runs,now=NOW)
        self.assertEqual(r["archive_status"],"ARCHIVE_CURRENT")
        self.assertEqual(r["pilot_status"],"PILOT_ACTIVE")
        self.assertEqual(r["independent_TOPA_shadow_status"],"PASS_INDEPENDENT_NUMERICAL_REPLAY")
        self.assertEqual(r["coordination_status"],"COUNCIL_CURRENT")
        self.assertEqual(r["severity"],"MONITORING")
        self.assertFalse(r["science_gates"]["new_billing_authorized_by_watchdog"])

    def test_recent_new_success_is_archiving_grace_not_alarm(self):
        root,_,_,runs=self.setup_fixture()
        runs.append({"id":12346,"status":"completed","conclusion":"success",
                     "head_branch":"main","event":"workflow_dispatch",
                     "created_at":"2026-10-25T11:30:00Z"})
        r=m.evaluate(root,runs,now=NOW)
        self.assertEqual(r["archive_status"],"ARCHIVE_PENDING_WITHIN_GRACE")
        self.assertEqual(r["severity"],"MONITORING")

    def test_missing_archive_over_twelve_hours_is_alert(self):
        root,_,_,runs=self.setup_fixture()
        runs.append({"id":12346,"status":"completed","conclusion":"success",
                     "head_branch":"main","event":"schedule",
                     "created_at":"2026-10-24T20:30:00Z"})
        r=m.evaluate(root,runs,now=NOW)
        self.assertEqual(r["archive_status"],"ARCHIVE_LAG_OVER_12H")
        self.assertEqual(r["severity"],"ACTION_REQUIRED")

    def test_pilot_stall_over_thirty_six_hours(self):
        root,_,_,runs=self.setup_fixture()
        now=NOW+timedelta(hours=45)
        r=m.evaluate(root,runs,now=now)
        self.assertEqual(r["pilot_status"],"PILOT_STALLED_OVER_36H")

    def test_newly_updated_archive_with_old_council_grace(self):
        root,base,state,runs=self.setup_fixture()
        state["latest_durable_external_run"]=12346
        (base/"CANONICAL_STATE.json").write_text(json.dumps(state))
        (base/"receipts"/"ROWAN-S2-12346-mock.json").write_text(json.dumps(
            {"source":{"run_id":12346,"source_artifact_sha256":"a"*64},
             "calibration":{"eight_mutants_with_provider_results":1}}))
        runs.append({"id":12346,"status":"completed","conclusion":"success",
                     "head_branch":"main","event":"schedule",
                     "created_at":"2026-10-25T11:40:00Z"})
        r=m.evaluate(root,runs,now=NOW)
        self.assertEqual(r["coordination_status"],"COUNCIL_PENDING_WITHIN_GRACE")
        self.assertEqual(r["severity"],"MONITORING")

    def test_missing_attested_receipt_is_hard_hold(self):
        root,base,state,runs=self.setup_fixture()
        state["underlying_state_is_derived_from"]="b"*64
        (base/"CANONICAL_STATE.json").write_text(json.dumps(state))
        with self.assertRaises(m.WatchdogHold):
            m.evaluate(root,runs,now=NOW)

    def test_budget_alarm_is_action_required(self):
        root,base,state,runs=self.setup_fixture()
        state["budget_guard_alert_mutations"]=["G48D"]
        (base/"CANONICAL_STATE.json").write_text(json.dumps(state))
        r=m.evaluate(root,runs,now=NOW)
        self.assertEqual(r["credit_cap_violations"],["G48D"])
        self.assertEqual(r["severity"],"ACTION_REQUIRED")

    def test_progress_regression_fails_closed(self):
        root,_,_,runs=self.setup_fixture()
        with self.assertRaises(m.WatchdogHold):
            m.evaluate(root,runs,now=NOW,previous={"completed_mutants":2})

    def test_topa_missing_attestation_is_alert(self):
        root,base,_,runs=self.setup_fixture()
        for p in (base/"topa").glob("TOPA-SHADOW-*.json"):
            p.unlink()
        r=m.evaluate(root,runs,now=NOW)
        self.assertEqual(r["independent_TOPA_shadow_status"],"MISSING_SHADOW_AUDIT")
        self.assertEqual(r["severity"],"ACTION_REQUIRED")

    def test_two_new_failures_without_success_is_alert(self):
        root,_,_,runs=self.setup_fixture()
        for n in (12346,12347):
            runs.append({"id":n,"status":"completed","conclusion":"failure",
                         "head_branch":"main","event":"schedule",
                         "created_at":"2026-10-25T11:50:00Z"})
        r=m.evaluate(root,runs,now=NOW)
        self.assertEqual(r["workflow_failure_status"],"REPEATED_POST_SUCCESS_FAILURES")
        self.assertEqual(r["severity"],"ACTION_REQUIRED")

    def test_future_archive_run_vs_github_is_hold(self):
        root,_,_,runs=self.setup_fixture()
        runs[0]["id"]=10000
        with self.assertRaises(m.WatchdogHold):
            m.evaluate(root,runs,now=NOW)

if __name__=="__main__":main()
