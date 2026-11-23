"""P0.3 protected review is a fail-closed independent program, not admission."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

from modules.autonomy_loop import p03_recovery_matrix as recovery
from modules.autonomy_loop import p03_protected_review as review

ROOT=Path(__file__).resolve().parents[1]


def evidence():
    raw=(ROOT/review.EVIDENCE).read_bytes()
    return json.loads(raw),hashlib.sha256(raw).hexdigest()


class ProtectedReviewTests(unittest.TestCase):
    def setUp(self):
        self.latest,self.checkpoint,_,_=recovery.read_evidence(ROOT)
        self.manifest,self.sha=evidence()

    def test_actual_crossorgan_status_must_remain_hold(self):
        report=review.assess(self.manifest,self.latest,self.checkpoint,self.sha)
        self.assertEqual(report["status"],"HOLD_P03_NO_INDEPENDENT_CONSUMPTION_AND_PHASE_ADMISSION")
        self.assertEqual(report["actual_software_items_processed"],24)
        self.assertFalse(report["genesis_model_call_attested"])
        self.assertTrue(report["experimental_cpu_model_generate_observed"])
        self.assertTrue(report["two_clean_github_model_runs_same_receipt"])
        self.assertFalse(report["cross_platform_recovery_proven"])
        self.assertFalse(report["experimental_model_truth_or_quality_proven"])
        self.assertEqual(report["gates"]["genesis_neural_model_consumption"],
                         "EXPERIMENTAL_LOCAL_CPU_GENERATE_VERIFIED__PRODUCTION_HOLD")
        self.assertEqual(report["gates"]["active_cloud_home_model_integration"],
                         "HOLD_NOT_IMPLEMENTED_OR_VERIFIED")
        self.assertEqual(report["gates"]["four_lens_fitness"],"HOLD_1_OF_4_LENSES_PRESENT")
        for k in ("can_update_checkpoint","can_wake_janus","may_fork_or_spawn_organ",
                  "can_promote_model","p03_accepted","independent_external_acceptance_performed"):
            self.assertFalse(report[k],k)

    def test_self_claims_cannot_be_external_authentication(self):
        for section,key in (
            ("private_receiver_ack","third_party_custodian_verified"),
            ("private_receiver_ack","sender_active_worker_has_credential_proven"),
            ("genesis_context_consumer","model_call_attested"),
            ("genesis_context_consumer","p03_admission"),
            ("protected_review","outside_custodian_signed_p03_acceptance"),
            ("protected_review","owner_human_approval_recorded"),
            ("protected_review","accepted_phase_p03"),
            ("protected_review","authorized_checkpoint_updated"),
            ("failure_recovery","live_cloud_clean_handoff_attested_in_this_lane"),
            ("boundaries","terminal_fork_workflow_reenabled"),
            ("boundaries","autonomous_dispatch_performed"),
        ):
            bad=copy.deepcopy(self.manifest)
            bad[section][key]=True
            with self.subTest(section=section,key=key),self.assertRaises(review.AdmissionHold):
                review.assess(bad,self.latest,self.checkpoint,self.sha)

    def test_experimental_model_proof_cannot_be_rebound_or_promoted(self):
        cases=[
           ("receipt_sha256","a"*64),
           ("second_artifact_zip_sha256","f"*64),
           ("two_clean_github_workflow_runs_match_entire_receipt",False),
           ("source_commit","b"*40),
           ("input_tokens",0),
           ("production_cloud_home_model_integrated",True),
           ("model_result_authoritative",True),
           ("phase_p03_accepted",True),
           ("external_independent_validation",True),
        ]
        for key,value in cases:
            with self.subTest(key=key):
                forged=copy.deepcopy(self.manifest)
                forged["genesis_experimental_model_consumer"][key]=value
                with self.assertRaisesRegex(review.AdmissionHold,"EXPERIMENTAL_MODEL"):
                    review.assess(forged,self.latest,self.checkpoint,self.sha)

    def test_forged_zero_backlog_with_wrong_count_fails(self):
        a=copy.deepcopy(self.manifest)
        a["private_receiver_ack"]["confirmed"]=3
        with self.assertRaisesRegex(review.AdmissionHold,"PRIVATE_RECEIVER"):
            review.assess(a,self.latest,self.checkpoint,self.sha)

    def test_forged_source_commit_fails(self):
        a=copy.deepcopy(self.manifest)
        a["genesis_context_consumer"]["source_commit"]="a"*40
        with self.assertRaisesRegex(review.AdmissionHold,"GENESIS_CONSUMER"):
            review.assess(a,self.latest,self.checkpoint,self.sha)

    def test_fake_neural_training_or_fork_denied(self):
        for section,key,value in (
            ("genesis_context_consumer","model_call_attested",True),
            ("boundaries","new_repositories_created",1),
            ("boundaries","production_weights_updated",True)):
            a=copy.deepcopy(self.manifest)
            a[section][key]=value
            with self.assertRaises(review.AdmissionHold):
                review.assess(a,self.latest,self.checkpoint,self.sha)

    def test_matching_local_checkpoint_does_not_mean_independent_acceptance(self):
        checkpoint=copy.deepcopy(self.checkpoint)
        checkpoint["last_verified_snapshot"]=self.latest["state_sha256"]
        result=review.assess(self.manifest,self.latest,checkpoint,self.sha)
        self.assertEqual(result["gates"]["checkpoint_anchor"],"MATCH_ONLY_NOT_ACCEPTANCE")
        self.assertFalse(result["p03_accepted"])

    def test_changed_phase_and_invalid_manifest_fail_closed(self):
        fake=copy.deepcopy(self.latest);fake["current_phase"]="P0.4"
        with self.assertRaisesRegex(review.AdmissionHold,"PHASE"):
            review.assess(self.manifest,fake,self.checkpoint,self.sha)
        fake=copy.deepcopy(self.manifest);fake["schema"]="evil"
        with self.assertRaisesRegex(review.AdmissionHold,"UNVERIFIED"):
            review.assess(fake,self.latest,self.checkpoint,self.sha)

    def test_evidence_digest_and_output_stability(self):
        a=review.assess(self.manifest,self.latest,self.checkpoint,self.sha)
        b=review.assess(self.manifest,self.latest,self.checkpoint,self.sha)
        self.assertEqual(a,b)
        self.assertEqual(a["evidence_manifest_sha256"],self.sha)
        with self.assertRaisesRegex(review.AdmissionHold,"DIGEST"):
            review.assess(self.manifest,self.latest,self.checkpoint,"unknown")

    def test_checkpoint_files_not_modified(self):
        paths=(ROOT/recovery.POINTER,ROOT/recovery.CHECKPOINT)
        before=[hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
        review.assess(self.manifest,self.latest,self.checkpoint,self.sha)
        self.assertEqual(before,[hashlib.sha256(path.read_bytes()).hexdigest() for path in paths])


if __name__=="__main__":
    unittest.main()
