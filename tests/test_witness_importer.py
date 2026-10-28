import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from modules.witness_importer.bridge import (
    classify_ack, classify_highwater, classify_workflow, get_runs,
    persist, validate_queue_ack, HOME_REPO, LAPIS_REPO, PRIVATE_REPO,
)

NOW = dt.datetime(2026, 10, 28, 10, 0, 0, tzinfo=dt.timezone.utc)
H = "1" * 64
A = "2" * 64
COMMIT = "a" * 40


def queue():
    return {"schema": "janus.beetle.delivery_queue.v1", "target_repository": PRIVATE_REPO,
            "next_sequence": 2, "entries": [{"sequence": 1, "batch_id": "batch-one", "sha256": H,
                                              "created_at": "2026-10-28T00:00:00Z"}]}


def ack():
    return {"schema": "janus.beetle.inbox_ack.v1", "target_repository": PRIVATE_REPO,
            "last_sequence": 1, "batch_id": "batch-one", "sha256": H,
            "status": "INBOX_DURABLE_UNVERIFIED__NOT_RUNTIME_CONSUMPTION",
            "scientific_authority_delta": 0}


def run(event="schedule", complete="2026-10-28T09:00:00Z", status="completed", conclusion="success"):
    return {"name": "JANUS Universal Beetle hourly", "head_branch": "main", "event": event,
            "status": status, "conclusion": conclusion, "created_at": "2026-10-28T08:59:00Z",
            "id": 123, "html_url": "https://github.com/run/123", "updated_at": complete}


class TestAck(unittest.TestCase):
    def test_match_and_nonauthority(self):
        self.assertEqual(validate_queue_ack(queue(), ack())["status"], "VERIFIED_DURABLE_INBOX_ACK")
        self.assertEqual(validate_queue_ack(queue(), ack())["pending"], 0)

    def test_hash_mismatch_is_not_missing_data(self):
        a = ack(); a["sha256"] = A
        with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
            validate_queue_ack(queue(), a)

    def test_sequence_and_target(self):
        q = queue(); q["entries"][0]["sequence"] = 3
        with self.assertRaises(ValueError):
            validate_queue_ack(q, ack())
        q = queue(); q["target_repository"] = "other/repo"
        with self.assertRaises(ValueError):
            validate_queue_ack(q, ack())

    def test_delayed_ack_not_delivery_failure(self):
        q = queue(); q["entries"].append({"sequence": 2, "batch_id": "next", "sha256": A,
                                          "created_at": "2026-10-28T01:00:00Z"}); q["next_sequence"] = 3
        result = classify_ack(q, ack(), NOW)
        self.assertEqual(result["status"], "ACK_DELAY_OVER_360_MIN")
        self.assertEqual(result["pending"], 1)

    def test_short_race(self):
        q = queue(); q["entries"].append({"sequence": 2, "batch_id": "next", "sha256": A,
                                          "created_at": "2026-10-28T09:58:00Z"}); q["next_sequence"] = 3
        self.assertEqual(classify_ack(q, ack(), NOW)["status"], "ACK_PENDING")


class TestSchedule(unittest.TestCase):
    def test_qualify_schedule_not_push(self):
        observed = classify_workflow([run(event="push")], LAPIS_REPO, "JANUS Universal Beetle hourly", NOW)
        self.assertEqual(observed["status"], "UNKNOWN")

    def test_success(self):
        observed = classify_workflow([run()], LAPIS_REPO, "JANUS Universal Beetle hourly", NOW,
                                     lambda _: [{"completed_at": "2026-10-28T09:00:00Z"}])
        self.assertEqual(observed["status"], "SCHEDULE_OK")
        self.assertEqual(observed["last_schedule_run"]["completed_at"], "2026-10-28T09:00:00Z")

    def test_silence_requires_completed_at(self):
        self.assertEqual(classify_workflow([run()], LAPIS_REPO,
                         "JANUS Universal Beetle hourly", NOW)["status"], "UNKNOWN")
        observed = classify_workflow([run()], LAPIS_REPO, "JANUS Universal Beetle hourly", NOW,
                                     lambda _: [{"completed_at": "2026-10-28T03:59:00Z"}])
        self.assertEqual(observed["status"], "SCHEDULE_SILENCE")

    def test_long_running_separate_from_silence(self):
        active = run(status="in_progress", conclusion=None)
        active["created_at"] = "2026-10-28T02:00:00Z"
        result = classify_workflow([run(), active], LAPIS_REPO, "JANUS Universal Beetle hourly", NOW,
                                   lambda _: [{"completed_at": "2026-10-28T02:00:00Z"}])
        self.assertEqual(result["status"], "SCHEDULE_LONG_RUNNING")

    def test_active_supersedes_silence(self):
        active = run(status="in_progress", conclusion=None)
        result = classify_workflow([run(), active], LAPIS_REPO, "JANUS Universal Beetle hourly", NOW,
                                   lambda _: [{"completed_at": "2026-10-28T02:00:00Z"}])
        self.assertEqual(result["status"], "SCHEDULE_ACTIVE")


class TestHighwater(unittest.TestCase):
    def issue(self, seq=196, sha=H, commit=COMMIT):
        return "<!-- janus.genesis.home.highwater.v1 -->\n```json\n" + json.dumps({
            "schema": "janus.genesis.home.highwater.v1", "source_repository": HOME_REPO,
            "sequence": seq, "receipt_sha256": sha, "home_commit_sha": commit}) + "\n```"

    def state(self, seq=196, sha=H):
        return {"schema": "JANUS_HABITAT_CLOUD_HOME_STATE_V1", "sequence": seq,
                "last_receipt_sha256": sha}

    def test_match(self):
        x = classify_highwater(self.issue(), self.state(), COMMIT, "2026-10-28T09:00:00Z", NOW)
        self.assertEqual(x["status"], "ANCHOR_MATCH")

    def test_lag_and_grace(self):
        self.assertEqual(classify_highwater(self.issue(195), self.state(), COMMIT,
                         "2026-10-28T08:59:00Z", NOW)["status"], "HIGHWATER_ANCHOR_LAG")
        self.assertEqual(classify_highwater(self.issue(195), self.state(), COMMIT,
                         "2026-10-28T09:59:00Z", NOW)["status"], "ANCHOR_PENDING_WITHIN_GRACE")

    def test_rollback_only_valid_data(self):
        self.assertEqual(classify_highwater(self.issue(197), self.state(), COMMIT,
                         "2026-10-28T09:00:00Z", NOW)["status"], "POSSIBLE_GENESIS_ROLLBACK")
        with self.assertRaises(ValueError):
            classify_highwater(self.issue(), {"schema": "oops"}, COMMIT, "2026-10-28T09:00:00Z", NOW)

    def test_equal_seq_wrong_sha_unknown(self):
        self.assertEqual(classify_highwater(self.issue(196, A), self.state(), COMMIT,
                         "2026-10-28T09:00:00Z", NOW)["status"], "HIGHWATER_UNKNOWN")


class TestPersistence(unittest.TestCase):
    def test_first_alert_repeat_dedup_recovery_and_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            observed = {"genesis_highwater": {"status": "HIGHWATER_ANCHOR_LAG", "home_sequence": 196,
                                               "anchor_sequence": 195}}
            x = persist(root, observed, NOW, "11", "1", COMMIT)
            self.assertEqual(x["transitions"], 1)
            with self.assertRaisesRegex(ValueError, "IMMUTABLE_RECEIPT_COLLISION"):
                persist(root, observed, NOW + dt.timedelta(seconds=1), "11", "1", COMMIT)
            observed["genesis_highwater"]["home_sequence"] = 197
            x = persist(root, observed, NOW + dt.timedelta(minutes=1), "12", "1", COMMIT)
            self.assertEqual(x["transitions"], 0)
            persist(root, {"genesis_highwater": {"status": "HIGHWATER_UNKNOWN"}},
                    NOW + dt.timedelta(minutes=2), "13", "1", COMMIT)
            latest = json.loads((root / "data/witness_importer/LATEST.json").read_text())
            self.assertEqual(latest["line_states"]["genesis_highwater"]["status"], "HIGHWATER_ANCHOR_LAG")
            self.assertEqual(latest["line_states"]["genesis_highwater"]["max_home_sequence"], 197)
            result = persist(root, {"genesis_highwater": {"status": "ANCHOR_MATCH", "home_sequence": 197,
                                                          "anchor_sequence": 197}},
                             NOW + dt.timedelta(minutes=3), "14", "1", COMMIT)
            self.assertEqual(result["transitions"], 1)
            # Repeated MATCH cannot produce another recovery alert.
            result = persist(root, {"genesis_highwater": {"status": "ANCHOR_MATCH", "home_sequence": 197,
                                                          "anchor_sequence": 197}},
                             NOW + dt.timedelta(minutes=4), "15", "1", COMMIT)
            self.assertEqual(result["transitions"], 0)


if __name__ == "__main__":
    unittest.main()