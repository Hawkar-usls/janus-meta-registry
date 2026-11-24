"""Meta R3: validate exact pinned JSON route pointers and no autonomy claims."""
import json
from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/"data/autonomy_map/JANUS_R3_TYPED_BOOTSTRAP_ROUTES_2026-11-24.json"
MAIN=ROOT/"pinned-meta-main"
MAP=ROOT/"pinned-meta-map"


class TypedRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=json.loads(DOC.read_text(encoding="utf-8"))

    def test_explicit_index_does_not_claim_all_organs_indexed(self):
        x=self.m["canonical_main_index"]
        self.assertEqual(self.m["schema"],"janus.meta_registry.r3_json_bootstrap_route_catalog.v1")
        self.assertEqual(x["explicitly_indexed_project_ids"],["COSMOS_SETI","TRUMP"])
        self.assertFalse(x["all_janus_repos_indexed"])
        self.assertFalse(x["not_evidence_of_live_project_current_state"] is False)

    def test_current_and_project_map_are_separate_source_layers(self):
        i=self.m["canonical_main_index"]
        a=self.m["autonomy_overlay"]
        self.assertNotEqual(i["source_commit_sha"],a["source_commit_sha"])
        self.assertEqual(a["observed_public_repos"],49)
        self.assertEqual(a["controller_count"],8)
        self.assertEqual(a["layers_count"],9)
        self.assertEqual(a["next_review_gates_count"],7)
        self.assertEqual(a["old_health_reasons"],41)
        self.assertTrue(a["not_live_service_state"])
        self.assertEqual(a["expected_current_phase"],"P0.3")
        for key in ("git_blob_sha1","state_git_blob_sha1","contract_git_blob_sha1","health_git_blob_sha1"):
            if key in i or key in a:
                self.assertRegex(i.get(key,a.get(key)),r"^[0-9a-f]{40}$")

    def test_original_verified_repair_is_not_live_general_self_healing(self):
        r=self.m["janus_r3_implementation"]
        self.assertEqual(r["research_pr"],"https://github.com/Hawkar-usls/Janus/pull/73")
        self.assertEqual(r["first_green_ci"],"https://github.com/Hawkar-usls/Janus/actions/runs/45296618656")
        self.assertEqual((r["old_correct"],r["new_correct"],r["old_solved_lost"]),(15,24,0))
        self.assertEqual(r["internal_exam_cases"],24)
        self.assertEqual(r["previously_unclassified_reasons_fixed_in_triage"],5)
        self.assertEqual(r["production_service_incidents_repaired"],0)
        self.assertFalse(r["actual_neural_model_gain"])
        self.assertFalse(r["external_blind_exam"])
        self.assertFalse(r["self_merge_enabled"])

    def test_no_foreign_code_license_or_user_authority_claims(self):
        self.assertEqual(len(self.m["source_pattern_references"]),4)
        for x in self.m["source_pattern_references"]:
            self.assertRegex(x["commit"],r"^[0-9a-f]{40}$")
        self.assertEqual(set(self.m["rights"].values()),{False})
        gate=self.m["operational_gates"]
        self.assertTrue(all(x is False or (k=="new_repositories_created" and x==0)
                            for k,x in gate.items()))
        self.assertEqual(len(self.m["how_to_boot"]),7)

    def test_actual_main_context_and_r1_bytes_are_exactly_bound(self):
        from hashlib import sha1
        def git_blob(raw):
            return sha1(("blob %d\0"%len(raw)).encode()+raw).hexdigest()
        i=self.m["canonical_main_index"]
        a=self.m["autonomy_overlay"]
        self.assertEqual(git_blob((MAIN/i["path"]).read_bytes()),i["git_blob_sha1"])
        for key,hash_key in (
          ("state_path","state_git_blob_sha1"),
          ("contract_path","contract_git_blob_sha1"),
          ("health_path","health_git_blob_sha1")):
            self.assertEqual(git_blob((MAP/a[key]).read_bytes()),a[hash_key])
        main_index=json.loads((MAIN/i["path"]).read_text())
        self.assertEqual(main_index["schema"],i["schema"])
        self.assertEqual([p["id"] for p in main_index["projects"]],
                         i["explicitly_indexed_project_ids"])
        state=json.loads((MAP/a["state_path"]).read_text())
        self.assertEqual(state["observation"]["observation_gate"],"HOLD")
        self.assertEqual(state["boundaries"]["action_authority"],False)

    def test_schema_explorer_real_ci_preserves_partial_coverage(self):
        x=self.m["registry_schema_explorer"]
        self.assertEqual(x["total_public_data_json_paths"],4615)
        self.assertEqual(x["bounded_json_objects_parsed"],3922)
        self.assertEqual(x["schema_families_detected"],1080)
        self.assertEqual(x["files_unparsed_or_skipped"],693)
        self.assertEqual(x["ci_run_url"],
                         "https://github.com/Hawkar-usls/Janus/actions/runs/45297638911")
        self.assertEqual(x["ci_conclusion"],"success")
        self.assertRegex(x["inner_receipt_sha256"],r"^[0-9a-f]{64}$")
        for name in ("all_documents_authoritative","active_state_verified_for_each_json",
                     "source_code_executed","auto_admitted_modules",
                     "latest_main_auto_refresh_enabled"):
            self.assertFalse(x[name],name)

    def test_actual_main_head_drift_keeps_boot_hold(self):
        x=self.m["live_meta_freshness"]
        self.assertEqual(x["live_ci_conclusion"],"success")
        self.assertEqual(x["status"],"HOLD_MAIN_OR_BOOT_INDEX_DRIFT__REVALIDATION_REQUIRED")
        self.assertNotEqual(x["expected_main_commit"],x["observed_main_commit"])
        self.assertEqual(x["expected_boot_index_blob_sha1"],x["observed_boot_index_blob_sha1"])
        self.assertEqual(x["same_chat_manual_compare_readonly"]["changed_paths_count"],15)
        self.assertEqual(x["same_chat_manual_compare_readonly"]["changed_data_json_paths_count"],0)
        self.assertEqual(x["same_chat_manual_compare_readonly"]["changed_eye_generated_json_paths_count"],12)
        self.assertTrue(x["same_chat_manual_compare_readonly"]["compare_tool_evidence_is_not_part_of_automated_freshness_artifact"])
        self.assertFalse(x["schedule_active_on_default_branch"])
        self.assertFalse(x["auto_reindex_new_commit"])
        self.assertFalse(x["protected_release_admitted"])

    def test_meta_catalog_cannot_be_sole_phase_authority(self):
        self.assertIn("DRAFT",self.m["status"])
        self.assertIn("HOLD",self.m["status"])
        self.assertFalse(self.m["operational_gates"]["protected_external_reviewer_approved"])
        self.assertFalse(self.m["operational_gates"]["p03_phase_accepted"])
        self.assertFalse(self.m["operational_gates"]["meta_registry_patched_in_main"])


if __name__=="__main__":
    unittest.main()
