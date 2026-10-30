"""Offline controls for source pins, status honesty, recovery and immutable receipts."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
SPEC = importlib.util.spec_from_file_location("autonomy", Path(__file__).parents[1] / "modules/autonomy_loop/runtime.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
def fixture():
    sources = {}
    for key, (repo, ref, path) in m.SPECS.items():
        sources[key] = {"status": "OBSERVED", "repository": m.OWNER + "/" + repo,
                        "ref": ref, "path": path, "commit_sha": "a"*40,
                        "content_sha256": "b"*64, "blob_sha": "c"*40, "data": {}}
    data = lambda key: sources[key]["data"]
    data("canonical").update(latest_durable_external_run=123, last_completed_mutants=8)
    data("aura").update(source={"upstream_run": 123, "state_sha256": m.digest(data("canonical"))})
    data("council").update(sources={"meta_registry": {"canonical_run": 123, "sha256": m.digest(data("canonical"))},
                                  "aura_oracle": {"packet_sha256": m.digest(data("aura"))}})
    data("coordination").update(meta_canonical_run=123)
    data("cosmos").update(canonical_rowan_run=123)
    data("home").update(source_main_sha="a"*40, sequence=214)
    data("beetle_delivery").update(schema="janus.beetle.delivery_health.v1", status="PASS",
        ack_semantics="INBOX_DURABLE_ONLY_NOT_RUNTIME_CONSUMPTION", total_pending=0,
        repositories={"opaque_receiver": {"status": "UP_TO_DATE", "pending": 0}})
    data("beetle_gate").update(schema="janus.beetle.producer_routing_gate.v1", routing_allowed=True,
        reason="ROUTING_ALLOWED", ack_semantics="INBOX_DURABLE_ONLY_NOT_RUNTIME_CONSUMPTION")
    data("scouts").update(agents_expected=17, agents_snapshot_observed=17, agents_model_synthesis_ok=17)
    data("native_model").update(attempt_count=3, promotion_count=1, rejection_count=2, history=[])
    data("native_decision").update(status="NO_ACTION")
    data("forge").update(status="IDLE_NO_CANDIDATE")
    data("patch_queue").update(proposal_count=0, verified_count=0, proposals=[])
    workflows = {key: {"status": "OBSERVED", "conclusion": "success", "run_id": 101,
                       "event": "schedule", "head_sha": "a"*40,
                       "created_at": "2026-10-30T10:00:00Z", "url": "https://github.com/example/run"}
                 for key in m.WORKFLOWS}
    return sources, workflows
def snapshot(previous=None):
    s, w = fixture()
    return m.summarize(s, w, "2026-10-30T15:00:00Z", "d"*40, previous)
class LoopTests(unittest.TestCase):
    def test_successful_workflow_does_not_hide_delivery_backlog(self):
        s, w = fixture()
        s["beetle_delivery"]["data"].update(status="WARN", total_pending=14,
            repositories={"public_receiver": {"status": "PENDING", "pending": 13},
                          "opaque_private_receiver": {"status": "ACK_UNAVAILABLE", "pending": 1}})
        s["beetle_gate"]["data"].update(routing_allowed=False, reason="HOLD_DELIVERY_BACKPRESSURE")
        r = m.summarize(s, w, "now", "d"*40)
        self.assertTrue(all(obs["conclusion"] == "success" for obs in r["workflows"].values()))
        self.assertEqual(r["metrics"]["beetle_delivery"]["total_pending"], 14)
        self.assertEqual(r["metrics"]["beetle_delivery"]["receiver_states"]["ACK_UNAVAILABLE"], 1)
        self.assertFalse(r["metrics"]["beetle_delivery"]["runtime_consumption_attested"])
        self.assertIn("BEETLE_ROUTING_HELD", {f["reason"] for f in r["findings"]})
        self.assertNotIn("opaque_private_receiver", m.encode(r).decode())

    def test_malformed_delivery_totals_do_not_report_clear(self):
        s, w = fixture()
        s["beetle_delivery"]["data"]["total_pending"] = 1
        r = m.summarize(s, w, "now", "d"*40)
        self.assertEqual(r["metrics"]["beetle_delivery"]["status"], "UNVERIFIED")
        self.assertIsNone(r["metrics"]["beetle_delivery"]["total_pending"])
        self.assertIn("BEETLE_DELIVERY_HEALTH_UNVERIFIED", {f["reason"] for f in r["findings"]})

    def test_clear_inbox_still_is_not_runtime_execution(self):
        r = snapshot()
        self.assertEqual(r["metrics"]["beetle_delivery"]["total_pending"], 0)
        self.assertFalse(r["metrics"]["beetle_delivery"]["runtime_consumption_attested"])
        self.assertFalse(r["full_issue_162_acceptance"])

    def test_green_components_never_inherit_full_acceptance(self):
        r = snapshot()
        self.assertEqual(r["ecosystem_status"], "AUTONOMY_PARTIAL")
        self.assertIs(r["full_issue_162_acceptance"], False)
        self.assertEqual(r["current_phase"], "P0.1")

    def test_second_cloud_wake_retains_exact_origin_and_no_pr_writer(self):
        workflow = (Path(__file__).parents[1] /
                    ".github/workflows/janus-autonomy-roadmap-loop.yml").read_text()
        self.assertIn("JANUS Beetle Memory Receiver", workflow)
        self.assertIn("JANUS Rowan Durable Observer", workflow)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", workflow)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", workflow)
        self.assertIn("github.event.workflow_run.head_repository.full_name == github.repository", workflow)
        self.assertIn("github.event_name != 'pull_request'", workflow)
        self.assertIn("cron: '19 * * * *'", workflow)
    def test_unknown_source_remains_visible(self):
        s, w = fixture()
        s["aura"]["status"] = "UNKNOWN"
        r = m.summarize(s, w, "now", "d"*40)
        self.assertTrue(any(f["reason"] == "SOURCE_UNKNOWN_AURA" for f in r["findings"]))
        self.assertNotEqual(r["ecosystem_status"], "PASS")
    def test_same_run_with_changed_digest_holds(self):
        s, w = fixture()
        s["aura"]["data"]["source"]["state_sha256"] = "f"*64
        r = m.summarize(s, w, "now", "d"*40)
        self.assertTrue(any(f["reason"] == "AURA_CANONICAL_DIGEST_DRIFT" for f in r["findings"]))
    def test_council_generation_lag_is_preserved(self):
        s, w = fixture()
        s["council"]["data"]["sources"]["meta_registry"]["canonical_run"] = 122
        r = m.summarize(s, w, "now", "d"*40)
        self.assertTrue(any(f["reason"] == "ROWAN_GENERATION_DRIFT_COUNCIL" for f in r["findings"]))
    def test_model_degradation_separate_from_snapshots(self):
        s, w = fixture()
        s["scouts"]["data"]["agents_model_synthesis_ok"] = 0
        r = m.summarize(s, w, "now", "d"*40)
        found = next(f for f in r["findings"] if f["reason"] == "SCOUT_MODEL_SYNTHESIS_DEGRADED")
        self.assertEqual(found["evidence"], {"snapshots": 17, "synthesis": 0, "expected": 17})
    def test_idle_does_not_become_code_work(self):
        r = snapshot()
        self.assertEqual(r["metrics"]["native_decision"], "NO_ACTION")
        self.assertEqual(r["execution"]["runtime_code_changes_this_cycle"], 0)
    def test_only_verified_checkpoint_advances_order(self):
        r = snapshot({"accepted_phases": {"P0.1": {"status": "PASS_STATUS_CAPTURE_ONLY"}}})
        self.assertEqual(r["current_phase"], "P0.2")
        self.assertEqual(r["roadmap"][2]["state"], "WAITING_FOR_PREVIOUS")
    def test_unknown_phase_cannot_enter_checkpoint(self):
        with self.assertRaisesRegex(m.Hold, "UNKNOWN_ACCEPTANCE_PHASE"):
            snapshot({"accepted_phases": {"DELETE_HISTORY": True}})
    def test_persist_is_idempotent_and_history_remains(self):
        with tempfile.TemporaryDirectory() as root:
            r = snapshot()
            p1 = m.persist(Path(root), r)
            later = copy.deepcopy(r)
            later["observed_at_utc"] = "2026-10-30T16:00:00Z"
            p2 = m.persist(Path(root), later)
            self.assertEqual(p1["receipt_path"], p2["receipt_path"])
            self.assertEqual(p1["receipt_sha256"], p2["receipt_sha256"])
            self.assertEqual(len(list((Path(root)/m.OUTPUT/"receipts").glob("*.json"))), 1)
    def test_receipt_path_rebinding_fails(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            p = m.persist(root, snapshot())
            p["receipt_path"] = "../secrets.json"
            (root/m.OUTPUT/"LATEST.json").write_bytes(m.encode(p))
            with self.assertRaisesRegex(m.Hold, "UNTRUSTED_RECEIPT_PATH"):
                m.load_record(root)
    def test_full_promotion_or_hash_tamper_rejected(self):
        r = snapshot()
        r["full_issue_162_acceptance"] = True
        with self.assertRaisesRegex(m.Hold, "UNPROVEN_AUTONOMY_PROMOTION"):
            m.validate(r)
        r = snapshot()
        r["metrics"]["home"]["sequence"] = 999
        with self.assertRaisesRegex(m.Hold, "SNAPSHOT_DIGEST"):
            m.validate(r)
    def test_independent_source_replay_checks_bytes(self):
        class BadClient:
            def file(self, *args):
                return {}, "f"*64, "c"*40
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            m.persist(root, snapshot())
            with self.assertRaisesRegex(m.Hold, "INDEPENDENT_SOURCE_REPLAY_MISMATCH"):
                m.verify_persisted(root, BadClient(), True)
            self.assertFalse((root/m.OUTPUT/"CHECKPOINT.json").exists())
 
class ReplayClient:
    def file(self, repo, commit, path):
        s, _ = fixture()
        key = next(k for k, spec in m.SPECS.items() if spec[0] == repo and spec[2] == path)
        return s[key]["data"], "b"*64, "c"*40
    def get(self, repo, path):
        return {"id": 101, "event": "schedule", "conclusion": "success",
                "head_sha": "a"*40, "created_at": "2026-10-30T10:00:00Z",
                "html_url": "https://github.com/example/run"}

class ContinuationTests(unittest.TestCase):
    def test_new_generation_reopens_maintenance_without_erasing_proof(self):
        s, w = fixture()
        s["canonical"]["data"]["latest_durable_external_run"] = 124
        prior = {"accepted_phases": {"P0.1": {"status": "PASS_STATUS_CAPTURE_ONLY"},
                                      "P0.2": {"status": "PASS_SOURCE_COHORT_ONLY"}}}
        r = m.summarize(s, w, "now", "d"*40, prior)
        self.assertEqual(r["current_phase"], "P0.2")
        self.assertEqual(r["roadmap"][1]["state"], "ACTIVE_RECHECK")
        self.assertIn("P0.2", r["accepted_phases"])

    def test_serialized_workflow_key_order_does_not_change_observation(self):
        s, w = fixture()
        for row in w.values():
            row["conclusion"] = "failure"
        a = m.summarize(s, w, "now", "d"*40)
        b = m.summarize(s, dict(reversed(list(w.items()))), "now", "d"*40)
        self.assertEqual(a["state_sha256"], b["state_sha256"])
    def test_independent_replay_advances_and_next_worker_resumes(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            m.persist(root, snapshot())
            result = m.verify_persisted(root, ReplayClient(), True)
            self.assertEqual(result["status"], "PASS_STATUS_CAPTURE_ONLY")
            pointer, record = m.load_record(root)
            self.assertEqual(pointer["current_phase"], "P0.2")
            self.assertEqual(record["roadmap"][0]["state"], "DONE")
            self.assertEqual(record["roadmap"][1]["state"], "ACTIVE")
            self.assertEqual(record["roadmap"][2]["state"], "WAITING_FOR_PREVIOUS")
    def test_rehashed_false_metric_is_caught_by_independent_derivation(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            r = snapshot()
            r["metrics"]["patch_queue"]["waiting"] = 999
            identity = {k:v for k,v in r.items() if k not in ("observed_at_utc", "state_sha256", "observation_id")}
            r["state_sha256"] = m.digest(identity)
            r["observation_id"] = r["state_sha256"][:24]
            m.persist(root, r)
            with self.assertRaisesRegex(m.Hold, "DERIVED_STATUS_REPLAY_MISMATCH"):
                m.verify_persisted(root, ReplayClient(), True)
    def test_later_phase_without_handler_is_not_accepted(self):
        with self.assertRaisesRegex(m.Hold, "UNIMPLEMENTED_PHASE_ACCEPTANCE"):
            snapshot({"accepted_phases": {"P0.3": {"status": "PASS"}}})
    def test_file_pin_cache_survives_remote_head_moving(self):
        client = m.PublicGitHub()
        calls = []
        def changing_get(repo, path):
            calls.append(path)
            return {"object": {"sha": ("a" if len(calls) == 1 else "b") * 40}}
        client.get = changing_get
        self.assertEqual(client.pin("Janus-Demiurge", "main"), "a"*40)
        self.assertEqual(client.pin("Janus-Demiurge", "main"), "a"*40)
        self.assertEqual(len(calls), 1)
    def test_source_exception_text_never_enters_public_snapshot(self):
        class Unavailable:
            def pin(self, *args):
                raise ValueError("credential=DO_NOT_PUBLISH")
            def get(self, *args):
                raise ValueError("credential=DO_NOT_PUBLISH")
        sources, workflows = m.collect(Unavailable())
        r = m.summarize(sources, workflows, "now", "d"*40)
        self.assertNotIn("DO_NOT_PUBLISH", m.encode(r).decode())
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            m.persist(root, r)
            with self.assertRaisesRegex(m.Hold, "CORE_OBSERVATION_UNAVAILABLE"):
                m.verify_persisted(root, Unavailable(), True)

if __name__ == "__main__":
    unittest.main()

