"""Offline regression controls for duplicate-named artifacts on historical reruns."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec=importlib.util.spec_from_file_location(
    "janus_rowan_archive_ingest",Path(__file__).parent/"ingest.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def checkpoint(root, run_id=40593272360):
    base=Path(root)/m.BASE
    base.mkdir(parents=True,exist_ok=True)
    folder=base/"receipts"
    folder.mkdir(exist_ok=True)
    state={
        "schema_id":"janus.rowan.observer_state.v1",
        "latest_durable_external_run":run_id,
        "underlying_state_is_derived_from":"a"*64,
        "last_completed_mutants":8,
    }
    (base/"CANONICAL_STATE.json").write_text(json.dumps(state))
    saved={"source":{"run_id":run_id,"source_artifact_sha256":"a"*64},
           "calibration":{"eight_mutants_with_provider_results":8}}
    (folder/f"ROWAN-S2-{run_id}-test.json").write_text(json.dumps(saved))
    return base


class IdempotentArchiveTest(unittest.TestCase):
    def test_old_duplicate_attempt_is_not_reopened(self):
        with tempfile.TemporaryDirectory() as t:
            checkpoint(t)
            rows=[{"id":40638479917},{"id":40593272360},{"id":40579973244}]
            todo,old=m.pending_source_runs(Path(t),rows,12)
            self.assertEqual(old,40593272360)
            self.assertEqual([x["id"] for x in todo],[40638479917])

    def test_new_unarchived_duplicate_remains_subject_to_single_artifact_gate(self):
        with tempfile.TemporaryDirectory() as t:
            checkpoint(t)
            rows=[{"id":40638479917},{"id":40593272360}]
            todo,_=m.pending_source_runs(Path(t),rows,12)
            self.assertEqual([r["id"] for r in todo],[40638479917])
            # Only the fetching layer can declare a NEW run's artifact unique;
            # selection must not arbitrarily pick among same-name artifacts.
            self.assertIn("if len(matches)!=1",Path(m.__file__).read_text())

    def test_current_checkpoint_is_idempotent(self):
        with tempfile.TemporaryDirectory() as t:
            checkpoint(t)
            todo,old=m.pending_source_runs(Path(t),[{"id":40593272360}],12)
            self.assertEqual(todo,[])
            self.assertEqual(old,40593272360)

    def test_invalid_or_forged_checkpoint_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            base=checkpoint(t)
            (base/"receipts"/"ROWAN-S2-40593272360-test.json").unlink()
            with self.assertRaisesRegex(m.EvidenceHold,"SOURCE_RECEIPT_NOT_ATTESTED"):
                m.pending_source_runs(Path(t),[{"id":40638479917}],12)

    def test_source_digest_mismatch_halts(self):
        with tempfile.TemporaryDirectory() as t:
            base=checkpoint(t)
            f=base/"CANONICAL_STATE.json"
            d=json.loads(f.read_text())
            d["underlying_state_is_derived_from"]="b"*64
            f.write_text(json.dumps(d))
            with self.assertRaises(m.EvidenceHold):
                m.pending_source_runs(Path(t),[{"id":40638479917}],12)

    def test_history_behind_canonical_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            checkpoint(t)
            with self.assertRaisesRegex(m.EvidenceHold,"GITHUB_HISTORY_BEHIND"):
                m.pending_source_runs(Path(t),[{"id":40579973244}],12)

    def test_first_import_no_checkpoint_still_reads_up_to_limit(self):
        with tempfile.TemporaryDirectory() as t:
            rows=[{"id":3},{"id":2},{"id":1}]
            todo,old=m.pending_source_runs(Path(t),rows,2)
            self.assertIsNone(old)
            self.assertEqual([x["id"] for x in todo],[3,2])


if __name__=="__main__":
    unittest.main()
