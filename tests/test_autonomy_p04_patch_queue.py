"""Regression suite for P0.4 proposal-only, lossless queue audit."""
import copy
import json
import unittest

from modules.autonomy_loop.p04_patch_queue_dedup import AuditHold, audit_index

SHA = "a" * 40


def encoded(rows, *, verified=None, blocked=0):
    if verified is None:
        verified = sum(x["status"] == "VERIFY_PASS" for x in rows)
    return json.dumps({
        "schema": "janus.patch_queue.index.v1",
        "status": "AUDIT_INPUT_ONLY",
        "proposal_count": len(rows),
        "verified_count": verified,
        "blocked_count": blocked,
        "proposals": rows,
    }, sort_keys=True).encode("utf-8")


def row(pid, status="VERIFY_PASS", *, sha=SHA):
    return {
        "proposal_id": pid,
        "status": status,
        "main_mutated": False,
        "native_model_selected": False,
        "target_repository": "Hawkar-usls/Hrain",
        "target_module_id": "LEFT_HRAIN",
        "target_branch": "janus-self/one",
        "patch_commit": sha,
    }


class NonLossyAuditTests(unittest.TestCase):
    def test_equal_artifact_identity_is_review_only_and_keeps_both(self):
        result = audit_index(encoded([row("jpatch-a"), row("jpatch-b")]))
        self.assertEqual(result["status"], "NONLOSSY_AUDIT_ONLY_NOT_PHASE_ACCEPTANCE")
        self.assertEqual(len(result["duplicate_groups"]), 1)
        self.assertEqual(result["duplicate_groups"][0]["proposal_ids"], ["jpatch-a", "jpatch-b"])
        self.assertEqual(result["preserved_proposal_ids"], ["jpatch-a", "jpatch-b"])
        self.assertFalse(result["p04_acceptance"])
        self.assertFalse(result["full_issue_162_acceptance"])
        self.assertFalse(result["source_files_modified"])
        self.assertEqual(result["authority_delta"], 0)

    def test_missing_identity_never_coalesces_historical_waiting_rows(self):
        waiting = [{"proposal_id": "jpatch-wait-1", "status": "WAITING_FOR_TARGET_BRANCH",
                    "repository": "Hawkar-usls/Hrain"},
                   {"proposal_id": "jpatch-wait-2", "status": "WAITING_FOR_TARGET_BRANCH",
                    "repository": "Hawkar-usls/Hrain"}]
        result = audit_index(encoded([row("jpatch-done"), *waiting]))
        self.assertEqual(result["unbound_count"], 2)
        self.assertEqual(result["unbound_proposal_ids"], ["jpatch-wait-1", "jpatch-wait-2"])
        self.assertEqual(result["duplicate_groups"], [])
        self.assertEqual(len(result["preserved_proposal_ids"]), 3)

    def test_distinct_patch_commit_is_not_duplicate(self):
        result = audit_index(encoded([row("jpatch-a"), row("jpatch-b", sha="b" * 40)]))
        self.assertEqual(result["duplicate_groups"], [])

    def test_reordered_rows_keep_same_group_and_lineage(self):
        items = [row("jpatch-z"), row("jpatch-a"), row("jpatch-new", sha="b" * 40)]
        first = audit_index(encoded(items))
        second = audit_index(encoded(list(reversed(items))))
        self.assertEqual(first["duplicate_groups"], second["duplicate_groups"])
        self.assertEqual(first["preserved_proposal_ids"], second["preserved_proposal_ids"])
        self.assertNotEqual(first["index_bytes_sha256"], second["index_bytes_sha256"])

    def test_reused_proposal_id_is_fail_closed_even_if_payload_same(self):
        with self.assertRaisesRegex(AuditHold, "DUPLICATE_PROPOSAL_ID"):
            audit_index(encoded([row("jpatch-repeat"), row("jpatch-repeat")]))

    def test_main_or_model_mutation_is_never_admitted(self):
        for key in ("main_mutated", "native_model_selected"):
            with self.subTest(key=key):
                altered = row("jpatch-unsafe")
                altered[key] = True
                with self.assertRaisesRegex(AuditHold, "UNADMITTED_MAIN_OR_MODEL_MUTATION"):
                    audit_index(encoded([altered]))

    def test_forged_verified_counter_or_incomplete_pass_is_hold(self):
        with self.assertRaisesRegex(AuditHold, "VERIFIED_ACCOUNTING"):
            audit_index(encoded([row("jpatch-a")], verified=0))
        partial = row("jpatch-partial")
        del partial["target_repository"]
        with self.assertRaisesRegex(AuditHold, "UNBOUND_VERIFIED_PATCH"):
            audit_index(encoded([partial]))

    def test_invalid_input_and_boolean_counters_are_hold(self):
        with self.assertRaisesRegex(AuditHold, "INDEX_JSON"):
            audit_index(b"{")
        wrong = json.loads(encoded([row("jpatch-a")]))
        wrong["proposal_count"] = True
        with self.assertRaisesRegex(AuditHold, "INDEX_COUNT"):
            audit_index(json.dumps(wrong).encode("utf-8"))
        with self.assertRaisesRegex(AuditHold, "INDEX_SIZE"):
            audit_index(b"")


if __name__ == "__main__":
    unittest.main()
