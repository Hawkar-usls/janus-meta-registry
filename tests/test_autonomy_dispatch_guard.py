"""No-network adversarial controls for the JANUS bounded wake guardian."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "bounded_wake", ROOT / "modules/autonomy_loop/dispatch_guard.py")
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)


def record(minutes, *, rid=42, status="completed", conclusion="success",
           event="schedule", age_updated=None):
    start = NOW - timedelta(minutes=minutes)
    updated = NOW - timedelta(
        minutes=minutes if age_updated is None else age_updated)
    return {
        "id": rid, "created": start, "updated": updated,
        "event": event, "status": status, "conclusion": conclusion,
        "url": f"https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/{rid}",
    }


def fixture_policy():
    return json.loads((ROOT / "data/autonomy_loop/BOUNDED_WAKE_POLICY.json")
                      .read_text(encoding="utf-8"))


def fixture_checkpoint():
    snap = "a" * 64
    latest = {
        "schema": "janus.autonomy.latest.v1",
        "current_phase": "P0.2", "state_sha256": snap,
        "full_issue_162_acceptance": False,
        "ecosystem_status": "AUTONOMY_PARTIAL",
    }
    checkpoint = {
        "schema": "janus.autonomy.checkpoint.v1",
        "authority_delta": 0,
        "current_phase": "P0.2", "last_verified_snapshot": snap,
        "unimplemented_handlers_do_not_count_as_done": True,
        "accepted_phases": {
            "P0.2": {"full_issue_162_acceptance": False, "status": "PASS_SOURCE_COHORT_ONLY"}
        },
    }
    return latest, checkpoint


class FakeAPI:
    def __init__(self, histories, race=None):
        self.histories = histories
        self.race = race
        self.calls = {}
        self.dispatches = []

    def history(self, workflow):
        self.calls[workflow] = self.calls.get(workflow, 0) + 1
        if self.race is not None and self.calls[workflow] > 1:
            return self.race
        if workflow not in self.histories:
            raise guard.Hold("MISSING_HISTORY")
        return self.histories[workflow]

    def dispatch(self, workflow):
        self.dispatches.append(workflow)


class BoundedWakeTests(unittest.TestCase):
    def setUp(self):
        self.policy = fixture_policy()
        self.latest, self.checkpoint = fixture_checkpoint()
        self.lanes = guard.validate_policy(
            self.policy, self.latest, self.checkpoint)

    def test_exact_reviewed_workflow_names_and_dispatch_contract(self):
        guard.validate_workflow_sources(ROOT)
        self.assertEqual(
            {x["workflow"] for x in self.lanes}, set(guard.LANES))
        self.assertEqual(self.policy["max_dispatches_per_tick"], 1)
        self.assertFalse(self.policy["paid_model_calls"])
        self.assertFalse(self.policy["auto_merge"])

    def test_no_workflow_whitelist_extension_or_shorter_cooldown(self):
        changed = fixture_policy()
        changed["lanes"][0]["workflow"] = "janus-demiurge-full-launcher.yml"
        with self.assertRaises(guard.Hold):
            guard.validate_policy(changed, self.latest, self.checkpoint)
        changed = fixture_policy()
        changed["lanes"][2]["min_gap_minutes"] = 5
        with self.assertRaises(guard.Hold):
            guard.validate_policy(changed, self.latest, self.checkpoint)
        changed = fixture_policy()
        changed["max_dispatches_per_tick"] = 3
        with self.assertRaises(guard.Hold):
            guard.validate_policy(changed, self.latest, self.checkpoint)
        changed = fixture_policy()
        changed["paid_model_calls"] = True
        with self.assertRaises(guard.Hold):
            guard.validate_policy(changed, self.latest, self.checkpoint)

    def test_phase_and_snapshot_mismatch_holds_before_network(self):
        l, c = fixture_checkpoint()
        c["last_verified_snapshot"] = "b" * 64
        with self.assertRaises(guard.Hold):
            guard.validate_policy(self.policy, l, c)
        l, c = fixture_checkpoint()
        l["current_phase"] = "P0.3"
        with self.assertRaises(guard.Hold):
            guard.validate_policy(self.policy, l, c)
        l, c = fixture_checkpoint()
        c["current_phase"] = "P0.4"
        with self.assertRaises(guard.Hold):
            guard.validate_policy(self.policy, l, c)
        l, c = fixture_checkpoint()
        l["full_issue_162_acceptance"] = True
        with self.assertRaises(guard.Hold):
            guard.validate_policy(self.policy, l, c)

    def test_recent_success_or_failure_prevents_duplicate_wake(self):
        lane = self.lanes[0]
        for result in ("success", "failure"):
            state = guard.evaluate(
                [record(60, conclusion=result)], lane, NOW)
            self.assertEqual(state["status"], "HOLD_RECENT_RUN")
            self.assertFalse(state["dispatch"])

    def test_in_progress_blocks_even_when_very_stale(self):
        lane = self.lanes[0]
        for age, expected in [
            (45, "HOLD_ACTIVE_RUN"), (180, "HOLD_POSSIBLY_STUCK_ACTIVE_RUN")
        ]:
            state = guard.evaluate(
                [record(900, rid=1),
                 record(age, rid=2, status="in_progress", conclusion=None)],
                lane, NOW)
            self.assertEqual(state["status"], expected)
            self.assertFalse(state["dispatch"])

    def test_one_priority_target_only_then_future_cycles(self):
        histories = {x["workflow"]: [record(1400, rid=i + 10)]
                     for i, x in enumerate(self.lanes)}
        api = FakeAPI(histories)
        result = guard.tick(api, self.lanes, NOW, dry_run=False)
        self.assertEqual(result["status"], "DISPATCH_ACCEPTED_NOT_EXECUTION_PROVEN")
        self.assertEqual(api.dispatches, [self.lanes[0]["workflow"]])
        self.assertFalse(result["dispatch_is_success"])
        self.assertFalse(result["grants_code_admission"])
        self.assertEqual(result["authority_delta"], 0)

    def test_dry_run_never_triggers_dispatch(self):
        histories = {x["workflow"]: [record(1400)] for x in self.lanes}
        api = FakeAPI(histories)
        result = guard.tick(api, self.lanes, NOW, dry_run=True)
        self.assertEqual(result["status"], "DRY_RUN_WOULD_DISPATCH")
        self.assertEqual(api.dispatches, [])

    def test_incomplete_one_lane_prevents_all_dispatch(self):
        histories = {self.lanes[0]["workflow"]: [record(1400)]}
        api = FakeAPI(histories)
        with self.assertRaises(guard.Hold):
            guard.tick(api, self.lanes, NOW, dry_run=False)
        self.assertEqual(api.dispatches, [])

    def test_race_before_dispatch_holds(self):
        histories = {x["workflow"]: [record(1400)] for x in self.lanes}
        api = FakeAPI(histories, race=[record(1, rid=99)])
        result = guard.tick(api, self.lanes, NOW, dry_run=False)
        self.assertEqual(result["status"], "HOLD_RACE_NEW_RUN")
        self.assertEqual(api.dispatches, [])

    def test_not_due_means_no_dispatch(self):
        histories = {x["workflow"]: [record(3)] for x in self.lanes}
        api = FakeAPI(histories)
        result = guard.tick(api, self.lanes, NOW, dry_run=False)
        self.assertEqual(result["status"], "IDLE_ALL_LANES_GATED_OR_FRESH")
        self.assertFalse(api.dispatches)

    def test_validation_of_utc_and_refuses_unknowns(self):
        for value in ("2026-11-07", "2026-11-07T11:00:00+03:00",
                      "yesterday", "2026-11-07T99:00:00Z"):
            with self.assertRaises(guard.Hold):
                guard.iso_utc(value)
        with self.assertRaises(guard.Hold):
            guard.evaluate([], self.lanes[0], NOW)

    def test_github_api_only_allowlisted_main_workflow_and_ten_per_page(self):
        name = self.lanes[0]["workflow"]
        expected = guard.LANES[name][0]
        class Stub(guard.GitHub):
            def __init__(self):
                super().__init__("fake-test-token", guard.REPOSITORY)
                self.requests = []
                self.dispatches = []
            def request(self, path, *, method="GET", payload=None):
                self.requests.append((path, method, payload))
                if method == "POST":
                    self.dispatches.append(path)
                    return None
                timestamp = "2026-11-07T03:00:00Z"
                return {"total_count": 1, "workflow_runs": [
                    {"id": 123, "name": expected, "head_branch": "main",
                     "event": "schedule", "status": "completed",
                     "conclusion": "success", "created_at": timestamp,
                     "updated_at": timestamp, "html_url": "https://example.invalid/123"}
                ]}
        api = Stub()
        history = api.history(name)
        self.assertEqual(len(history), 1)
        self.assertIn("per_page=10&page=1", api.requests[0][0])
        self.assertEqual(api.requests[0][1], "GET")
        api.dispatch(name)
        self.assertEqual(api.requests[-1][1], "POST")
        self.assertEqual(api.requests[-1][2], {"ref": "main"})
        self.assertEqual(len(api.dispatches), 1)
        with self.assertRaises(guard.Hold):
            api.dispatch("any-other-workflow.yml")

    def test_github_api_unknown_page_never_becomes_no_schedule(self):
        name = self.lanes[0]["workflow"]
        class Broken(guard.GitHub):
            def __init__(self):
                super().__init__("fake", guard.REPOSITORY)
            def request(self, path, *, method="GET", payload=None):
                return {"total_count": 1000, "workflow_runs": []}
        with self.assertRaises(guard.Hold):
            Broken().history(name)


if __name__ == "__main__":
    unittest.main()
