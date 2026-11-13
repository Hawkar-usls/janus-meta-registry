"""Adversarial offline replay of R1.4 actual is_fresh consumer profiling."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"modules/autonomy_loop/verify_r14_real_consumer.py"
spec=importlib.util.spec_from_file_location("janus_r14_replay",P)
verify=importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)
FOLDER=ROOT/"experiments/closed_loop_is_fresh_r14"


def records():
    proto=json.loads((FOLDER/"PROTOCOL.json").read_text())
    raw=json.loads((FOLDER/"receipts/github-run-42503712794.json").read_text())
    return raw,proto


def resign(raw):
    report=raw["report"]
    report["report_sha256"]=verify.digest({k:v for k,v in report.items() if k!="report_sha256"})


class R14OperationalProfileTests(unittest.TestCase):
    def test_exact_archived_profile_replays_without_docker(self):
        output=verify.verify()
        self.assertEqual(output["status"],"PASS_RECORDED_ARITHMETIC_AND_SOURCE_BINDINGS_ONLY")
        self.assertEqual(output["replayed_probes"],3)
        self.assertGreater(output["oracle_share_pct"],90)
        self.assertFalse(output["independently_remeasured_cpu_time"])
        self.assertFalse(output["candidate_improvement_proven"])
        self.assertFalse(output["production_promotion"])
        self.assertEqual(output["authority_delta"],0)

    def test_fake_stage_speedup_is_rejected_despite_recomputed_self_hash(self):
        r,p=records()
        r["report"]["profiles"][0]["total_ms"]=1
        resign(r)
        with self.assertRaisesRegex(verify.Hold,"PROFILE_STAGE_SUM_INVALID"):
            verify.validate(r,p)

    def test_median_tamper_rejected_even_with_recomputed_hash(self):
        r,p=records()
        r["report"]["medians"]["networkless_docker_oracle_ms"]=1
        resign(r)
        with self.assertRaisesRegex(verify.Hold,"MEDIAN_ARITHMETIC_TAMPERED"):
            verify.validate(r,p)

    def test_false_speedup_or_authority_claim_is_rejected(self):
        for field in ("candidate_improvement_proven","system_runtime_speedup",
                      "independent_external_replay","auto_merge","runtime_source_mutation"):
            r,p=records()
            r["report"][field]=True
            resign(r)
            with self.subTest(field=field),self.assertRaisesRegex(verify.Hold,"PROFILE_IDENTITY_OR_DIGEST"):
                verify.validate(r,p)
        r,p=records()
        r["scope"]["main_modified"]=True
        with self.assertRaisesRegex(verify.Hold,"UNSAFE_SCOPE_ESCALATION"):
            verify.validate(r,p)

    def test_tampered_model_or_pr_head_is_rejected(self):
        r,p=records()
        r["source_run"]["source_checkout_sha"]="0"*40
        with self.assertRaisesRegex(verify.Hold,"RUN_SOURCE_BINDING"):
            verify.validate(r,p)
        r,p=records()
        r["report"]["source_module_sha256"]="0"*64
        resign(r)
        with self.assertRaisesRegex(verify.Hold,"PROFILE_IDENTITY_OR_DIGEST"):
            verify.validate(r,p)

    def test_changed_preregistration_or_snapshot_is_rejected(self):
        r,p=records()
        changed=copy.deepcopy(p)
        changed["baseline_commit"]="0"*40
        with self.assertRaisesRegex(verify.Hold,"PREREGISTERED_PROTOCOL_REBOUND"):
            verify.validate(r,changed)
        r,p=records()
        r["report"]["snapshot_sha256"]="0"*64
        resign(r)
        with self.assertRaisesRegex(verify.Hold,"PROFILE_IDENTITY_OR_DIGEST"):
            verify.validate(r,p)

    def test_frozen_same_clock_receipt_and_model_checks(self):
        r,p=records()
        self.assertEqual(len({x["receipt_sha256"] for x in r["report"]["profiles"]}),1)
        self.assertEqual({x["behavioral_cases"] for x in r["report"]["profiles"]},{270})
        self.assertEqual({x["status"] for x in r["report"]["profiles"]},{"FRESH_SOURCE_DIAGNOSTIC_ONLY"})
        self.assertEqual(r["report"]["baseline_main_sha"],p["baseline_commit"])


if __name__=="__main__":
    unittest.main()
