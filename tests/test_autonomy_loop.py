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
    data("self_writer_state").update(
        schema="janus.autonomous_coder.state.v1", sequence=1,
        authority_delta=0, universal_code_writer_proven=False,
        accepted={"retry_delay": {"source_sha256": "d"*64, "receipt_sha256": "e"*64, "run_id": "123456-1"}})
    module = {"module_id": "janus.pure.retry_delay.v1",
              "path": "self_modules/retry_delay/module.py",
              "manifest_path": "self_modules/retry_delay/MODULE.json",
              "source_sha256": "d"*64, "receipt_sha256": "e"*64,
              "run_id": "123456-1", "module_manifest_sha256": "f"*64}
    index = data("self_module_index")
    index.update(schema="janus.autonomous_coder.module_index.v1",
                 state_sequence=1, accepted_count=1, modules={"retry_delay": module},
                 installation_scope="ISOLATED_STATE_BRANCH_ONLY",
                 model_authorship="EXTERNAL_OPEN_WEIGHTS_NOT_NATIVE_JANUS",
                 runtime_auto_import=False, new_permissions=0, authority_delta=0,
                 full_issue_162_acceptance=False)
    index["index_sha256"] = m.digest(index)
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
    def test_self_module_registry_is_visible_but_not_p2_completion(self):
        r = snapshot()
        self.assertEqual(r["metrics"]["self_writer"]["accepted_pure_modules"], 1)
        self.assertEqual(r["metrics"]["self_writer"]["attempt_sequence"], 1)
        self.assertTrue(r["metrics"]["self_writer"]["not_native_janus_model"])
        self.assertFalse(r["metrics"]["self_writer"]["full_p2_acceptance"])
        self.assertFalse(r["metrics"]["self_writer"]["trusted_main_auto_update"])
        self.assertIn("SELF_WRITER_REVIEWED_TASKS_REMAINING",
                      {f["reason"] for f in r["findings"]})

    def test_self_writer_rejects_source_rebinding_even_with_rehashed_index(self):
        s, w = fixture()
        index = s["self_module_index"]["data"]
        index["modules"]["retry_delay"]["source_sha256"] = "a"*64
        index["index_sha256"] = m.digest({k: v for k, v in index.items()
                                            if k != "index_sha256"})
        result = m.summarize(s, w, "now", "d"*40)
        self.assertEqual(result["metrics"]["self_writer"]["status"], "UNVERIFIED")
        self.assertIsNone(result["metrics"]["self_writer"]["accepted_pure_modules"])
        self.assertIn("SELF_MODULE_CATALOG_UNVERIFIED",
                      {f["reason"] for f in result["findings"]})

    def test_model_does_not_self_grant_main_admission_via_catalog_metadata(self):
        s, w = fixture()
        index = s["self_module_index"]["data"]
        index["runtime_auto_import"] = True
        index["index_sha256"] = m.digest({k: v for k, v in index.items()
                                            if k != "index_sha256"})
        result = m.summarize(s, w, "now", "d"*40)
        self.assertEqual(result["metrics"]["self_writer"]["status"], "UNVERIFIED")
        self.assertEqual(result["ecosystem_status"], "AUTONOMY_PARTIAL")
        self.assertFalse(result["full_issue_162_acceptance"])

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

    def test_matching_new_sources_still_recheck_old_checkpoint_proof(self):
        s, w = fixture()
        new_run = 124
        s["canonical"]["data"]["latest_durable_external_run"] = new_run
        s["aura"]["data"]["source"]["upstream_run"] = new_run
        s["aura"]["data"]["source"]["state_sha256"] = m.digest(s["canonical"]["data"])
        s["council"]["data"]["sources"]["meta_registry"]["canonical_run"] = new_run
        s["council"]["data"]["sources"]["meta_registry"]["sha256"] = m.digest(s["canonical"]["data"])
        s["council"]["data"]["sources"]["aura_oracle"]["packet_sha256"] = m.digest(s["aura"]["data"])
        s["coordination"]["data"]["meta_canonical_run"] = new_run
        s["cosmos"]["data"]["canonical_rowan_run"] = new_run
        previous = {"accepted_phases": {
            "P0.1": {"status": "PASS_STATUS_CAPTURE_ONLY"},
            "P0.2": {"status": "PASS_SOURCE_COHORT_ONLY", "canonical_run": 123}}}
        out = m.summarize(s, w, "now", "d"*40, previous)
        self.assertFalse(any("GENERATION_DRIFT" in item["reason"] or
                             "DIGEST_DRIFT" in item["reason"] for item in out["findings"]))
        self.assertEqual(out["current_phase"], "P0.2")
        self.assertEqual(out["roadmap"][1]["state"], "ACTIVE_RECHECK")

    def test_exact_new_independent_cohort_replaces_old_generation(self):
        phases = {"P0.1": {"status": "PASS_STATUS_CAPTURE_ONLY"},
                  "P0.2": {"status": "PASS_SOURCE_COHORT_ONLY",
                           "canonical_run": 123, "proof_sha256": "a"*64}}
        refreshed = {"status": "PASS_SOURCE_COHORT_ONLY", "canonical_run": 124,
                     "proof_sha256": "b"*64, "authority_delta": 0,
                     "full_issue_162_acceptance": False}
        result = m.admit_verified_p02(phases, refreshed, 124)
        self.assertEqual(result["P0.2"]["canonical_run"], 124)
        self.assertEqual(result["P0.2"]["proof_sha256"], "b"*64)
        s, w = fixture()
        s["canonical"]["data"]["latest_durable_external_run"] = 124
        s["aura"]["data"]["source"].update(
            upstream_run=124, state_sha256=m.digest(s["canonical"]["data"]))
        s["council"]["data"]["sources"]["meta_registry"].update(
            canonical_run=124, sha256=m.digest(s["canonical"]["data"]))
        s["council"]["data"]["sources"]["aura_oracle"]["packet_sha256"] = m.digest(s["aura"]["data"])
        s["coordination"]["data"]["meta_canonical_run"] = 124
        s["cosmos"]["data"]["canonical_rowan_run"] = 124
        self.assertEqual(m.summarize(s, w, "now", "d"*40,
                                     {"accepted_phases": phases})["current_phase"], "P0.3")

    def test_p02_replacement_refuses_rollback_or_unverified_authority(self):
        phases = {"P0.2": {"status": "PASS_SOURCE_COHORT_ONLY", "canonical_run": 124}}
        good = {"status": "PASS_SOURCE_COHORT_ONLY", "canonical_run": 123,
                "authority_delta": 0, "full_issue_162_acceptance": False}
        with self.assertRaisesRegex(m.Hold, "P02_GENERATION_ROLLBACK_DENIED"):
            m.admit_verified_p02(phases, good, 123)
        self.assertEqual(phases["P0.2"]["canonical_run"], 124)
        good["canonical_run"] = 125
        good["full_issue_162_acceptance"] = True
        with self.assertRaisesRegex(m.Hold, "P02_INVALID_CURRENT_GENERATION_PROOF"):
            m.admit_verified_p02(phases, good, 125)
        with self.assertRaisesRegex(m.Hold, "P02_INVALID_CURRENT_GENERATION_PROOF"):
            m.admit_verified_p02(phases, {**good, "full_issue_162_acceptance": False}, 126)
        self.assertEqual(phases["P0.2"]["canonical_run"], 124)

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
    def test_workflow_attempt_pin_survives_later_rerun_of_same_id(self):
        # The unqualified GitHub run endpoint changes after a rerun; the
        # specific completed attempt is the only reproducible observation.
        class AttemptPinnedClient(ReplayClient):
            def __init__(self):
                self.paths = []
            def get(self, repo, path):
                self.paths.append(path)
                if "/attempts/1" not in path:
                    raise AssertionError("MUTABLE_WORKFLOW_RUN_ENDPOINT_DISALLOWED")
                return {"id": 101, "run_attempt": 1, "status": "completed",
                        "event": "schedule", "conclusion": "success",
                        "head_sha": "a"*40,
                        "created_at": "2026-10-30T10:00:00Z",
                        "html_url": "https://github.com/example/run"}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, workflows = fixture()
            for item in workflows.values():
                item["run_attempt"] = 1
            receipt = m.summarize(sources, workflows, "2026-10-30T15:00:00Z", "d"*40)
            m.persist(root, receipt)
            client = AttemptPinnedClient()
            result = m.verify_persisted(root, client, True)
            self.assertEqual(result["status"], "PASS_STATUS_CAPTURE_ONLY")
            self.assertEqual(len(client.paths), len(m.WORKFLOWS))
            self.assertTrue(all(p.endswith("/attempts/1") for p in client.paths))

    def test_replay_rejects_attempt_rebinding_even_if_status_success(self):
        class WrongAttempt(ReplayClient):
            def get(self, repo, path):
                return {"id": 101, "run_attempt": 2, "status": "completed",
                        "event": "schedule", "conclusion": "success",
                        "head_sha": "a"*40,
                        "created_at": "2026-10-30T10:00:00Z",
                        "html_url": "https://github.com/example/run"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources, workflows = fixture()
            for item in workflows.values():
                item["run_attempt"] = 1
            m.persist(root, m.summarize(sources, workflows, "2026-10-30T15:00:00Z", "d"*40))
            with self.assertRaisesRegex(m.Hold, "INDEPENDENT_WORKFLOW_REPLAY_MISMATCH"):
                m.verify_persisted(root, WrongAttempt(), True)

    def test_collector_rejects_inflight_or_drifted_attempt(self):
        class AttemptClient:
            def pin(self, *args):
                raise m.Hold("not required for workflow contract")
            def get(self, repo, path):
                if "/actions/workflows/" in path:
                    return {"workflow_runs": [{"id": 101, "run_attempt": 1,
                             "event": "schedule", "conclusion": "success",
                             "head_sha": "a"*40,
                             "created_at": "2026-10-30T10:00:00Z",
                             "html_url": "https://github.com/example/run"}]}
                if path.endswith("/attempts/1"):
                    return {"id": 101, "run_attempt": 1,
                            "status": "in_progress", "event": "schedule",
                            "conclusion": None, "head_sha": "a"*40,
                            "created_at": "2026-10-30T10:00:00Z",
                            "html_url": "https://github.com/example/run"}
                raise AssertionError("unexpected path " + path)
        _, workflows = m.collect(AttemptClient())
        self.assertTrue(all(v["status"] == "UNKNOWN" for v in workflows.values()))
        self.assertTrue(all(v["error_class"] == "Hold" for v in workflows.values()))

    def test_rerun_original_creation_time_does_not_fake_attempt_drift(self):
        # Real GitHub list /runs reports original run.created_at, while
        # /runs/{id}/attempts/2 reports the later retry's created_at.
        class RerunClient:
            def pin(self, *args):
                raise m.Hold("not needed")
            def get(self, repo, path):
                if "/actions/workflows/" in path:
                    return {"workflow_runs": [{
                        "id": 41252334708, "run_attempt": 2,
                        "status": "completed", "event": "workflow_run",
                        "conclusion": "success", "head_sha": "a"*40,
                        "created_at": "2026-10-31T23:23:29Z",
                        "html_url": "https://github.com/example/run"}]}
                if path.endswith("/runs/41252334708/attempts/2"):
                    return {"id": 41252334708, "run_attempt": 2,
                            "status": "completed", "event": "workflow_run",
                            "conclusion": "success", "head_sha": "a"*40,
                            "created_at": "2026-11-01T00:12:35Z",
                            "html_url": "https://github.com/example/run"}
                raise AssertionError("unexpected GitHub access " + path)
        sources, workflows = m.collect(RerunClient())
        self.assertTrue(all(value["status"] == "OBSERVED"
                            for value in workflows.values()))
        self.assertTrue(all(value["run_attempt"] == 2
                            for value in workflows.values()))
        self.assertTrue(all(value["created_at"] == "2026-11-01T00:12:35Z"
                            for value in workflows.values()))
        self.assertTrue(all(value["status"] == "UNKNOWN"
                            for value in sources.values()))

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

