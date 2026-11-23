"""JANUS Meta Registry R2: source-bound public pillars evidence, no autonomy inflation."""
import json
import re
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/"data/autonomy_map/JANUS_OPEN_PILLARS_R2_2026-11-24.json"


class PillarEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.j=json.loads(DOC.read_text())

    def test_expected_schema_and_current_scientific_hold(self):
        j=self.j
        self.assertEqual(j["schema"],"janus.meta_registry.pillars_r2_evidence/1.0")
        self.assertEqual(j["source"]["repository"],"Hawkar-usls/Janus")
        self.assertTrue(j["status"].endswith("JANUS_AUTONOMY_PARTIAL_P03"))
        self.assertFalse(j["gates"]["full_autonomy_proven"])
        self.assertFalse(j["gates"]["neural_functional_gain_proven"])

    def test_original_actions_are_bound_to_exact_commit(self):
        j=self.j
        self.assertEqual(j["original_ci"]["run"],"https://github.com/Hawkar-usls/Janus/actions/runs/45290176238")
        self.assertEqual(j["original_ci"]["jobs_passed"],4)
        self.assertEqual(j["original_ci"]["jobs_total"],4)
        self.assertEqual(j["source"]["head_sha"],"c7593137f0831d44476b125198c5c36f9cfa9388")
        for key in ("plan_artifact_sha256","plan_receipt_sha256","watch_artifact_sha256",
                    "watch_receipt_sha256","plan_gene_event_head"):
            self.assertRegex(j["original_ci"][key],r"^[0-9a-f]{64}$")

    def test_drift_is_not_automatically_updated(self):
        v=self.j["external_source_check"]
        self.assertEqual(v["sources_total"],13)
        self.assertEqual((v["pinned_metadata_matched"],v["held_due_to_drift"]),(12,1))
        self.assertEqual(v["drift_repository"],"paperclipai/paperclip")
        self.assertNotEqual(v["old_frozen_commit_sha"],v["observed_commit_sha"])
        self.assertEqual(v["status"],"HOLD_METADATA_DRIFT_OR_UNVERIFIED")
        self.assertEqual(v["HTTP_GET_requests"],26)
        self.assertFalse(v["auto_code_import"] if "auto_code_import" in v else self.j["gates"]["auto_code_import"])

    def test_historical_map_stays_observation_hold(self):
        v=self.j["health_triage"]
        self.assertEqual(v["health_gate"],"HOLD")
        self.assertEqual(v["public_repositories_in_historical_map"],49)
        self.assertEqual(v["observed_reasons"],41)
        self.assertEqual(v["member_link_unverified"]+
                         v["checks_stale"]+v["checks_not_all_success"]+
                         v["unclassified"],41)
        self.assertEqual(v["repaired_by_this_stage"],0)
        self.assertFalse(v["fresh_operational_probe_of_all_repos"])

    def test_all_selected_organs_are_inert(self):
        v=self.j["candidate_organs"]
        self.assertEqual(v["source_gaps_identified"],16)
        self.assertEqual(len(v["ranked_first_four"]),4)
        self.assertEqual(v["selected_state"],"CATALOGUED_NOT_BORN")
        self.assertEqual(v["actual_new_modules_activated"],0)
        self.assertEqual(v["actual_new_repositories_created"],0)
        self.assertFalse(v["separate_codepath_is_outside_independent_custodian"])

    def test_no_out_of_scope_evolution_or_secret_writes(self):
        gates=self.j["gates"]
        for key in ("new_daily_schedule_active_on_default_branch","auto_fork",
                    "auto_code_import","auto_merge","source_writeback",
                    "model_weights_changed","exam_data_used_for_learning",
                    "neural_functional_gain_proven","external_admission_authenticated",
                    "P03_checkpoint_updated","full_autonomy_proven"):
            self.assertFalse(gates[key],key)


if __name__=="__main__":
    unittest.main()
