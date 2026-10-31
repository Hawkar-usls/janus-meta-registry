"""Adversarial contract tests for the continuing JANUS installed-patch watchdog.

All source data is read as bytes. No test executes model-authored source or
touches production Git. Tests do NOT self-authorize merge or source write.
"""
from pathlib import Path
import copy
import hashlib
import sys
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "modules/autonomy_coder"))
import repair_integrity_watch as watch

SOURCE = (BASE / watch.CODE).read_bytes()
FUNCTION = ("def floor_age_us(delta_us):\n"
            "    return delta_us // 1000000\n")


def fixture():
    return {
        "schema": "janus.self_writer.real_operational_repair.v1",
        "record_id": "JANUS_SELF_WRITER_REAL_REPAIR_001",
        "repository": watch.REPO,
        "defect": {"original_git_blob_sha": watch.OLD_BLOB},
        "model_proposal": {
            "model": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
            "raw_source_admitted": False,
            "raw_variants": [
                {"source": "import math\ndef floor_age_us(delta_us):\n    return math.floor(delta_us / 1000000)\n",
                 "original_verdict": "REJECTED_BY_NO_IMPORT_AST"},
                {"source": "import math\ndef floor_age_us(delta_us):\n    return math.floor(delta_us / 1e6)\n",
                 "original_verdict": "REJECTED_BY_NO_IMPORT_AST"},
            ],
        },
        "typed_compilation": {
            "source": FUNCTION,
            "source_sha256": watch.MODEL_FUNCTION_SHA,
            "independent_variants_passed": 2,
            "independent_cases_each": 417,
            "raw_code_becomes_trusted_directly": False,
        },
        "installation": {
            "merge_commit_sha": watch.INSTALL_COMMIT,
            "postmerge_target_git_blob_sha": watch.LIVE_BLOB,
            "model_can_modify_main_directly": False,
            "authority_delta": 0,
        },
        "rollback": {
            "isolated_rehearsal": "PASS_IN_READONLY_INDEPENDENT_GIT_WORKER",
            "rehearsal_run_id": 41182302141,
            "production_rollback_executed": False,
            "automatic_main_revert_enabled": False,
        },
        "limits": {
            "full_autonomy_status": "PARTIAL",
            "native_demiurge_authorship_proven": False,
            "p2_ten_independent_tasks_accepted": False,
        },
    }


class IndependentContinuousIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.evidence = fixture()
        for row in self.evidence["model_proposal"]["raw_variants"]:
            row["source_sha256"] = watch.sha256(row["source"].encode())

    def test_exact_real_production_source_and_trusted_compiler_bytes(self):
        self.assertEqual(watch.git_blob(SOURCE), watch.LIVE_BLOB)
        self.assertEqual(watch.sha256(FUNCTION.encode()), watch.MODEL_FUNCTION_SHA)
        result = watch.verify_contents(SOURCE, self.evidence, watch.ARCHIVE_COMMIT)
        self.assertEqual(result["live_source_blob"], watch.LIVE_BLOB)
        self.assertFalse(result["raw_model_source_admitted"])
        self.assertEqual(result["authority_delta"], 0)

    def test_single_byte_mutation_cannot_remain_accepted(self):
        with self.assertRaisesRegex(ValueError, "ACTIVE_SOURCE_CHANGED"):
            watch.verify_contents(SOURCE + b" ", self.evidence, watch.ARCHIVE_COMMIT)
        with self.assertRaisesRegex(ValueError, "ARCHIVE_COMMIT_MOVED"):
            watch.verify_contents(SOURCE, self.evidence, "0"*40)

    def test_forged_full_autonomy_or_authority_fails_closed(self):
        for path, key, newvalue in [
            ("limits", "full_autonomy_status", "FULL"),
            ("limits", "p2_ten_independent_tasks_accepted", True),
            ("limits", "native_demiurge_authorship_proven", True),
            ("installation", "authority_delta", 1),
            ("installation", "model_can_modify_main_directly", True),
            ("model_proposal", "raw_source_admitted", True),
            ("rollback", "automatic_main_revert_enabled", True),
            ("rollback", "production_rollback_executed", True),
            ("rollback", "isolated_rehearsal", "PENDING"),
        ]:
            with self.subTest(path=path,key=key):
                forged = copy.deepcopy(self.evidence)
                forged[path][key] = newvalue
                with self.assertRaisesRegex(ValueError, "UNTRUSTED_ARCHIVED_CLAIMS"):
                    watch.verify_contents(SOURCE, forged, watch.ARCHIVE_COMMIT)

    def test_forged_model_source_and_laundered_rejection_denied(self):
        forged = copy.deepcopy(self.evidence)
        forged["model_proposal"]["raw_variants"][0]["source"] += "# changed\n"
        with self.assertRaisesRegex(ValueError, "RAW_MODEL_OR_REJECTION_CHANGED"):
            watch.verify_contents(SOURCE, forged, watch.ARCHIVE_COMMIT)
        forged = copy.deepcopy(self.evidence)
        forged["model_proposal"]["raw_variants"][0]["original_verdict"] = "PASS"
        with self.assertRaisesRegex(ValueError, "RAW_MODEL_OR_REJECTION_CHANGED"):
            watch.verify_contents(SOURCE, forged, watch.ARCHIVE_COMMIT)

    def test_cloud_witness_rejects_forged_run_or_wrong_head(self):
        records = {rid: {"id": rid, "name": name, "status": "completed",
                         "conclusion": "success", "head_sha": sha,
                         "head_repository": {"full_name": watch.REPO}}
                   for rid, (sha, name) in watch.PASS_RUNS.items()}
        self.assertEqual(watch.verify_runs(records), sorted(watch.PASS_RUNS))
        modified = copy.deepcopy(records)
        modified[41181981029]["head_sha"] = "0"*40
        with self.assertRaisesRegex(ValueError, "INVALID_RUN_41181981029"):
            watch.verify_runs(modified)
        modified = copy.deepcopy(records)
        modified[41182302141]["conclusion"] = "failure"
        with self.assertRaisesRegex(ValueError, "INVALID_RUN_41182302141"):
            watch.verify_runs(modified)
        modified = copy.deepcopy(records)
        modified[41181981061]["head_repository"]["full_name"] = "not/the-repo"
        with self.assertRaisesRegex(ValueError, "INVALID_RUN_41181981061"):
            watch.verify_runs(modified)
        del records[41181745142]
        with self.assertRaisesRegex(ValueError, "MISSING_VERIFIED_RUN"):
            watch.verify_runs(records)

    def test_main_archive_must_exist_and_match_pinned_historical_bytes(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            journal = Path(directory) / "JANUS_SELF_WRITER_REAL_REPAIR_001.json"
            sealed = b'{"immutable":true}\n'
            with self.assertRaisesRegex(ValueError, "MAIN_JOURNAL_MISSING"):
                watch.verify_main_archive(journal, sealed)
            journal.write_bytes(sealed + b" ")
            with self.assertRaisesRegex(ValueError, "MAIN_JOURNAL_NOT_SAME_AS_PINNED_EVIDENCE"):
                watch.verify_main_archive(journal, sealed)
            journal.write_bytes(sealed)
            self.assertIs(watch.verify_main_archive(journal, sealed), True)

    def test_actual_main_archive_present_and_locked_to_trusted_model_intent(self):
        path = BASE / watch.JOURNAL
        self.assertTrue(path.is_file(), "Merged archive must exist in main")
        import json
        data = json.loads(path.read_bytes())
        self.assertEqual(data["record_id"], "JANUS_SELF_WRITER_REAL_REPAIR_001")
        self.assertEqual(data["typed_compilation"]["source_sha256"], watch.MODEL_FUNCTION_SHA)
        self.assertFalse(data["installation"]["model_can_modify_main_directly"])
        self.assertTrue(watch.verify_main_archive(path, path.read_bytes()))

    def test_no_production_mutation_controls(self):
        file = (BASE / "modules/autonomy_coder/repair_integrity_watch.py").read_text()
        self.assertNotIn("update_ref(", file)
        self.assertNotIn("git push", file)
        self.assertNotIn("merge_pull_request", file)
        self.assertIn('"remote_write": False', file)
        self.assertIn('"full_autonomy": False', file)
        self.assertIn("HOLD_FAIL_CLOSED", file)

if __name__ == "__main__":
    unittest.main()
