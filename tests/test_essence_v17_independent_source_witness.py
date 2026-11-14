"""ESSENCE v1.7 Meta Registry independent public-source witness safeguards."""
import unittest
from tools import essence_v17_independent_source_witness as w

class SourceWitness(unittest.TestCase):
    def test_real_github_record_locked_to_checkpoint_and_no_authority(self):
        record=w.status_record()
        self.assertFalse(record["admission"]["production_model_swap_allowed"])
        self.assertFalse(record["admission"]["automatic_model_swap_allowed"])
        self.assertEqual(record["reviewer"]["github_actions_status"],"SUCCESS")

    def test_wrong_remote_repo_denied_before_network(self):
        with self.assertRaisesRegex(ValueError,"UNPINNED_REMOTE_SOURCE"):
            w.get_raw("untrusted/repo",w.CHECKER_COMMIT,
                      "tools/essence_v17_three_gate_review.py",1000)

    def test_unknown_commit_denied_before_network(self):
        with self.assertRaisesRegex(ValueError,"UNPINNED_REMOTE_SOURCE"):
            w.get_raw("Hawkar-usls/Janus-Demiurge","f"*40,
                      "janus_model/checkpoints/promoted.pt",1000)

    def test_forged_remote_checker_rejected(self):
        def spoof(repo,commit,path,max_bytes):return b"def promote(): return True"
        with self.assertRaisesRegex(ValueError,"EXTERNAL_VERIFIER_CODE_CHANGED"):
            w.witness(fetch=spoof)

    def test_model_not_deserialized_by_witness(self):
        src=w.status_record()
        self.assertEqual(src["reviewer"]["reviewer_git_blob_sha1"],w.CHECKER_BLOB)
        self.assertEqual(src["candidate"]["source_model_checkpoint_git_blob_sha1"],
                         w.CHECKPOINT_BLOB)
        self.assertEqual(src["admission"]["genuine_external_evidence"],"HOLD")
        self.assertEqual(src["admission"]["actual_service_canary_and_rollback"],"HOLD")

if __name__=="__main__":unittest.main()
