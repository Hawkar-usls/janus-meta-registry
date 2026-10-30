"""Pure offline adversarial tests for independent REAL44 GitHub public witness."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("real44_witness", ROOT/"tools/janus_real44_public_verdict_witness.py")
assert spec and spec.loader
w=importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
RUN=41049447362
SHA="e4baea1840173648150d10161096134e43b81926"


def fixture(*, success=True, omit=None, bad_artifact=None, event="push"):
    run={"id":RUN, "name":w.WORKFLOW, "status":"completed",
         "conclusion":"success" if success else "failure",
         "head_sha":SHA, "head_branch":"main", "event":event}
    jobs=[{"id":120000000000+i, "name":name, "status":"completed", "conclusion":"success"}
          for i,name in enumerate(w.REQUIRED_JOBS)]
    if omit:
        jobs=[j for j in jobs if j["name"]!=omit]
    artifacts=[{
       "id":12970000000+i, "name":name, "expired":False,
       "digest":"sha256:"+str(i+1)*64
    } for i,name in enumerate((
      f"janus-real44-cloud-worker-a-public-{RUN}",
      f"janus-real44-cloud-worker-b-public-{RUN}",
      f"janus-real44-cloud-public-verdict-{RUN}"
    ))]
    if bad_artifact=="expired": artifacts[-1]["expired"]=True
    if bad_artifact=="digest": artifacts[0]["digest"]="invalid"
    return {
      "/actions/workflows/janus-real44-cloud-materialization-v2.yml/runs?per_page=20":{"workflow_runs":[run]},
      f"/actions/runs/{RUN}/jobs?per_page=100":{"jobs":jobs},
      f"/actions/runs/{RUN}/artifacts?per_page=100":{"artifacts":artifacts}
    }


class TestReal44Witness(unittest.TestCase):
    def test_success_is_explicitly_limited_to_source_github_evidence(self):
        source=fixture()
        report=w.inspect(lambda path:deepcopy(source[path]))
        self.assertEqual(report["status"],"PASS_REAL44_GITHUB_PUBLIC_JOB_AND_ARCHIVE_EVIDENCE")
        self.assertEqual(report["source_run_id"],RUN)
        self.assertEqual(report["source_commit"],SHA)
        self.assertEqual(len(report["job_ids"]),4)
        self.assertEqual(len(report["public_artifact_proofs"]),3)
        self.assertFalse(report["claim_ceiling"]["actual_cross_organ_runtime_execution_attested"])
        self.assertFalse(report["claim_ceiling"]["full_issue_162_acceptance"])
        self.assertFalse(report["claim_ceiling"]["private_source_metadata_collected"])
        self.assertNotIn("github_pat_",json.dumps(report))
        self.assertEqual(report["source_scope"]["historical_top_level_git_trees"],44)

    def test_failed_latest_run_cannot_reuse_last_success_as_live(self):
        report=w.inspect(lambda path:fixture(success=False)[path])
        self.assertEqual(report["status"],"HOLD_LATEST_RUN_NOT_SUCCESS")
        self.assertEqual(report["public_artifact_proofs"],{})
        self.assertFalse(report["claim_ceiling"]["public_github_job_and_artifact_metadata_verified"])

    def test_skipped_or_failed_job_never_passes(self):
        with self.assertRaises(w.WitnessHold):
            w.inspect(lambda path:fixture(omit="worker-b")[path])
        rows=fixture()
        rows[f"/actions/runs/{RUN}/jobs?per_page=100"]["jobs"][2]["conclusion"]="skipped"
        with self.assertRaises(w.WitnessHold):
            w.inspect(lambda path:rows[path])

    def test_missing_expired_or_corrupted_artifact_never_passes(self):
        for bad in ("expired", "digest"):
            with self.assertRaises(w.WitnessHold):
                w.inspect(lambda path:fixture(bad_artifact=bad)[path])

    def test_pr_run_cannot_be_accepted_as_trusted_live_run(self):
        rows=fixture(event="pull_request")
        with self.assertRaises(w.WitnessHold):
            w.inspect(lambda path:rows[path])

    def test_immutable_receipts_dedupe_and_reject_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            report=w.inspect(lambda path:fixture()[path])
            receipt,changed=w.persist(report,root)
            self.assertTrue(changed)
            self.assertTrue(receipt.exists())
            same,changed=w.persist(report,root)
            self.assertEqual(same,receipt)
            self.assertFalse(changed)
            self.assertEqual(list(receipt.parent.glob("*.json")),[receipt])
            marker=root/"data/integrations/nexus_real44/LATEST.json"
            obj=json.loads(marker.read_text())
            self.assertFalse(obj["actual_cross_organ_runtime_execution_attested"])
            obj["source_run_id"]=RUN+50
            marker.write_text(json.dumps(obj))
            with self.assertRaises(w.WitnessHold):
                w.persist(report,root)
            self.assertEqual(list(receipt.parent.glob("*.json")),[receipt])


if __name__=="__main__":
    unittest.main()
