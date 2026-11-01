"""Offline adversarial regression for GitHub Actions attempt-bound roadmap receipts.

A run-level conclusion is mutable following a GitHub retry. An attempt is
immutable evidence. No test calls GitHub, accesses secrets, or runs compute.
"""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("janus_attempt_pinning",
    ROOT/"modules/autonomy_loop/runtime.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

BASE={
    "id":41250472038, "event":"schedule", "conclusion":"failure",
    "head_sha":"2f27efbc31f7b5ecd7a03c15c5d8bec856d47312",
    "created_at":"2026-10-31T22:57:53Z",
    "html_url":"https://github.com/Hawkar-usls/janus-meta-registry/actions/runs/41250472038",
    "status":"completed", "run_attempt":1,
}
RERUN={**BASE, "conclusion":"success", "created_at":"2026-11-01T00:18:09Z",
       "run_attempt":2}
def observation(run, attempt=True):
    result={key:run[key] for key in ("event","conclusion","head_sha","created_at")}
    result["run_id"]=run["id"]
    result["url"]=run["html_url"]
    if attempt:
        result["run_attempt"]=run["run_attempt"]
    return result

class Fake:
    def __init__(self, latest=None, first=None, second=None):
        self.latest=latest or RERUN
        self.first=first or BASE
        self.second=second or RERUN
        self.reads=[]
    def get(self, repo, path):
        self.reads.append(path)
        if path.endswith("/attempts/1"):
            return self.first
        if path.endswith("/attempts/2"):
            return self.second
        if path.endswith("/actions/runs/"+str(BASE["id"])):
            return self.latest
        raise AssertionError("UNEXPECTED_ENDPOINT_"+path)

class AttemptReplayTests(unittest.TestCase):
    def test_original_failure_survives_new_success_as_immutable_attempt(self):
        f=Fake()
        m.verify_workflow_observation(f,"janus-meta-registry",observation(BASE))
        self.assertEqual(len(f.reads),1)
        self.assertTrue(f.reads[0].endswith("/attempts/1"))

    def test_new_success_pins_second_attempt(self):
        f=Fake()
        m.verify_workflow_observation(f,"janus-meta-registry",observation(RERUN))
        self.assertEqual(len(f.reads),1)
        self.assertTrue(f.reads[0].endswith("/attempts/2"))

    def test_legacy_failure_stays_replayable_after_rerun(self):
        f=Fake()
        m.verify_workflow_observation(f,"janus-meta-registry",observation(BASE,False))
        self.assertEqual(len(f.reads),3)
        self.assertIn("/attempts/1",f.reads[1])
        self.assertIn("/attempts/2",f.reads[2])

    def test_replay_does_not_rewrite_legacy_failure_into_success(self):
        f=Fake()
        prior=observation(BASE,False)
        m.verify_workflow_observation(f,"janus-meta-registry",prior)
        self.assertEqual(prior["conclusion"],"failure")
        self.assertNotIn("run_attempt",prior)

    def test_legacy_same_run_fast_path(self):
        f=Fake(latest=BASE)
        m.verify_workflow_observation(f,"janus-meta-registry",observation(BASE,False))
        self.assertEqual(len(f.reads),1)

    def test_tampered_sha_rejected(self):
        f=Fake()
        tampered=observation(BASE)
        tampered["head_sha"]="f"*40
        with self.assertRaisesRegex(m.Hold,"INDEPENDENT_WORKFLOW_ATTEMPT_REPLAY_MISMATCH"):
            m.verify_workflow_observation(f,"janus-meta-registry",tampered)

    def test_changed_conclusion_or_created_at_rejected(self):
        for field,value in [("conclusion","success"),("created_at","2030-01-01T00:00:00Z")]:
            with self.subTest(field=field):
                tampered=observation(BASE)
                tampered[field]=value
                with self.assertRaises(m.Hold):
                    m.verify_workflow_observation(Fake(),"janus-meta-registry",tampered)

    def test_ambiguous_legacy_attempts_rejected(self):
        f=Fake(first=BASE,second={**BASE,"run_attempt":2})
        with self.assertRaisesRegex(m.Hold,"INDEPENDENT_WORKFLOW_REPLAY_MISMATCH"):
            m.verify_workflow_observation(f,"janus-meta-registry",observation(BASE,False))

    def test_bounded_attempts_and_mismatched_id_rejected(self):
        for value in (-1,0,17,True,"1"):
            with self.subTest(value=value):
                bad=observation(BASE)
                bad["run_attempt"]=value
                with self.assertRaises(m.Hold):
                    m.verify_workflow_observation(Fake(),"janus-meta-registry",bad)
        with self.assertRaisesRegex(m.Hold,"INDEPENDENT_WORKFLOW_ATTEMPT_REPLAY_MISMATCH"):
            m.verify_workflow_observation(Fake(first={**BASE,"id":999}),
                                         "janus-meta-registry",observation(BASE))

    def test_legacy_outside_bounded_history_fails_closed(self):
        f=Fake(latest={**RERUN,"run_attempt":17})
        with self.assertRaisesRegex(m.Hold,"LEGACY_WORKFLOW_ATTEMPT_COUNT_UNVERIFIABLE"):
            m.verify_workflow_observation(f,"janus-meta-registry",observation(BASE,False))

    def test_new_collector_seals_attempt_specific_creation_time(self):
        class CaptureClient:
            def pin(self,repo,ref):return "a"*40
            def file(self,repo,commit,path):return {}, "b"*64,"c"*40
            def get(self,repo,path):
                if "/attempts/" in path:return RERUN
                if "/runs?" in path:return {"workflow_runs":[RERUN]}
                raise AssertionError(path)
        _,workflows=m.collect(CaptureClient())
        self.assertEqual(set(workflows),set(m.WORKFLOWS))
        for row in workflows.values():
            self.assertEqual(row["status"],"OBSERVED")
            self.assertEqual(row["run_attempt"],2)
            self.assertEqual(row["conclusion"],"success")
            self.assertEqual(row["created_at"],RERUN["created_at"])

    def test_collector_rejects_race_between_list_and_attempt(self):
        class RaceClient:
            def pin(self,repo,ref):return "a"*40
            def file(self,repo,commit,path):return {}, "b"*64,"c"*40
            def get(self,repo,path):
                if "/attempts/" in path:return {**RERUN,"conclusion":"failure"}
                if "/runs?" in path:return {"workflow_runs":[RERUN]}
                raise AssertionError(path)
        _,workflows=m.collect(RaceClient())
        self.assertTrue(all(r["status"]=="UNKNOWN" for r in workflows.values()))
        self.assertTrue(all(r.get("error_class")=="Hold" for r in workflows.values()))


if __name__=="__main__":
    unittest.main()
