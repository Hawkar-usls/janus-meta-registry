"""Keymaster Meta Registry mirror: replay, tamper and idempotency tests."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))

import keymaster_db_sync as sync
from keymaster_db_verify import digest, verify_queue

SRC = hashlib.sha256(b"synthetic-source").hexdigest()
HEAD = "a"*40
AFTER = "b"*40
ZERO = "0"*64


def sign(schema, parts):
    obj={"schema":schema,**parts}
    return {**obj,"receipt_sha256":digest(obj)}


def enqueue():
    detail={"kind":"contract_test","source_sha256":SRC,
            "priority":1,"cpu":1,"max_seconds":120}
    body={"seq":1,"kind":"ENQUEUE","task_id":"ci-contract-lab",
          "detail":detail,"previous_sha256":ZERO}
    event={**body,"event_sha256":digest(body)}
    return {"schema":"janus.daddy_keymaster.git_cas_queue.v1",
            "epoch":1,"tip_sha256":event["event_sha256"],
            "events":[event],
            "tasks":{"ci-contract-lab":{**detail,"state":"QUEUED",
                      "generation":0,"holder":None,"lease_until":None,
                      "checkpoint_sha256":None,"result_sha256":None}}}


def terminal_queue():
    s=enqueue()
    # Event chain in the exact production format.
    for kind,detail in [
        ("CLAIM",{"holder":"worker-synthetic","generation":1,
                  "lease_until":"2026-10-31T14:00:00Z"}),
        ("CHECKPOINT",{"holder":"worker-synthetic","generation":1,
                       "content_sha256":SRC}),
        ("COMPLETE",{"holder":"worker-synthetic","generation":1,
                     "checkpoint_sha256":SRC,"result_sha256":SRC}),
    ]:
        body={"seq":len(s["events"])+1,"kind":kind,
              "task_id":"ci-contract-lab","detail":detail,
              "previous_sha256":s["tip_sha256"]}
        item={**body,"event_sha256":digest(body)}
        s["events"].append(item)
        s["tip_sha256"]=item["event_sha256"]
        s["epoch"]+=1
    s["tasks"]["ci-contract-lab"].update({
        "state":"COMPLETE","generation":1,"holder":"worker-synthetic",
        "lease_until":"2026-10-31T14:00:00Z",
        "checkpoint_sha256":SRC,"result_sha256":SRC
    })
    verify_queue(s)
    return s


def valid_files():
    archived=terminal_queue()
    segment=sign("janus.daddy_keymaster.archive_segment.v1",{
        "serial":1,"source_ref":HEAD,
        "previous_segment_digest_sha256":ZERO,
        "queue":archived,"queue_tip_sha256":archived["tip_sha256"]
    })
    index=sign("janus.daddy_keymaster.archive_head.v1",{
        "serial":1,"segment_path":"state/archive_segments/00000001.json",
        "segment_digest_sha256":segment["receipt_sha256"],
        "previous_head_digest_sha256":ZERO
    })
    marker=sign("janus.daddy_keymaster.retired_source.v1",{
        "source_sha256":SRC,"segment":1,
        "segment_digest_sha256":segment["receipt_sha256"],
        "task_ids":["ci-contract-lab"],"terminal_states":["COMPLETE"]
    })
    return {"state/relay_queue.json":{
                "schema":"janus.daddy_keymaster.git_cas_queue.v1",
                "epoch":0,"tip_sha256":ZERO,"tasks":{},"events":[]},
            "state/relay_archive_head.json":index,
            "state/archive_segments/00000001.json":segment,
            f"state/processed_sources/{SRC}.json":marker}


class SyncTests(unittest.TestCase):
    def test_full_verified_archive(self):
        proof=sync.validate_documents(HEAD,valid_files())
        self.assertEqual(proof["archive_segments"],1)
        self.assertEqual(proof["queue_epoch"],0)
        doc=sync.make_snapshot(HEAD,valid_files())
        self.assertEqual(doc["snapshot_sha256"],sync.h({
            k:v for k,v in doc.items() if k!="snapshot_sha256"
        }))
        self.assertEqual(len(doc["documents"]),4)

    def test_untrusted_queued_task_mutation_rejected(self):
        d=valid_files()
        d["state/archive_segments/00000001.json"]["queue"]["tasks"]["ci-contract-lab"]["kind"]="run_shell"
        with self.assertRaises(ValueError):
            sync.make_snapshot(HEAD,d)

    def test_corrupt_archive_receipt_refused(self):
        d=valid_files()
        d["state/archive_segments/00000001.json"]["receipt_sha256"]="f"*64
        with self.assertRaises(ValueError):
            sync.make_snapshot(HEAD,d)

    def test_missing_source_marker_refused(self):
        d=valid_files()
        del d[f"state/processed_sources/{SRC}.json"]
        with self.assertRaisesRegex(ValueError,"SOURCE_MARKER_COVERAGE"):
            sync.make_snapshot(HEAD,d)

    def test_append_only_dedup_latest(self):
        doc=sync.make_snapshot(HEAD,valid_files())
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sync.write_copy(doc,tmp),"UPDATED")
            self.assertEqual(sync.write_copy(doc,tmp),"UNCHANGED")
            p=Path(tmp)/"LATEST.json"
            latest=json.loads(p.read_text())
            self.assertEqual(latest["source_commit_sha"],HEAD)
            self.assertEqual(latest["archive_count"],1)
            mirror=(Path(tmp)/"MIRROR.json").read_bytes()
            checksum=(Path(tmp)/"MIRROR.sha256").read_text().split()[0]
            self.assertEqual(hashlib.sha256(mirror).hexdigest(),checksum)
            self.assertEqual(json.loads(mirror)["snapshot_sha256"],doc["snapshot_sha256"])
            self.assertTrue((Path(tmp)/"snapshots"/(HEAD+".json")).exists())
            corrupt=copy.deepcopy(doc)
            corrupt["archive_count"]=77
            with self.assertRaisesRegex(ValueError,"SNAPSHOT_DIGEST_MISMATCH"):
                sync.write_copy(corrupt,tmp)

    def test_head_rewind_rejected(self):
        doc=sync.make_snapshot(HEAD,valid_files())
        with tempfile.TemporaryDirectory() as tmp:
            sync.write_copy(doc,tmp)
            next_doc=sync.make_snapshot(AFTER,valid_files())
            with self.assertRaisesRegex(ValueError,"SOURCE_REF_REWOUND"):
                sync.write_copy(next_doc,tmp,compare=lambda a,b: (_ for _ in ()).throw(
                    ValueError("KEYMASTER_SOURCE_REF_REWOUND_OR_DIVERGED")))
            self.assertEqual(json.loads((Path(tmp)/"LATEST.json").read_text())["source_commit_sha"],HEAD)

    def test_missing_previous_snapshot_refuses_head_advance(self):
        doc=sync.make_snapshot(HEAD,valid_files())
        with tempfile.TemporaryDirectory() as tmp:
            sync.write_copy(doc,tmp)
            (Path(tmp)/"snapshots"/(HEAD+".json")).unlink()
            newer=sync.make_snapshot(AFTER,valid_files())
            with self.assertRaisesRegex(ValueError,"MISSING_PRIOR_PINNED_SNAPSHOT"):
                sync.write_copy(newer,tmp,compare=lambda x,y: True)

    def test_same_head_collision_rejected(self):
        doc=sync.make_snapshot(HEAD,valid_files())
        with tempfile.TemporaryDirectory() as tmp:
            sync.write_copy(doc,tmp)
            path=Path(tmp)/"snapshots"/(HEAD+".json")
            path.write_text("{}")
            with self.assertRaisesRegex(ValueError,"IMMUTABLE_SNAPSHOT_COLLISION"):
                sync.write_copy(doc,tmp)

    def test_bounded_archives_and_allowlist(self):
        head=valid_files()["state/relay_archive_head.json"]
        with self.assertRaisesRegex(ValueError,"ARCHIVE_COUNT_BOUND"):
            sync.fetch_documents(HEAD,fetch=lambda h,p: {
                "state/relay_queue.json":valid_files()["state/relay_queue.json"],
                "state/relay_archive_head.json":{**head,"serial":1000}
            }[p])
        with self.assertRaisesRegex(ValueError,"UNAPPROVED_SOURCE_PATH"):
            sync.exact_raw(HEAD,"../../secret.json")


if __name__ == "__main__":
    unittest.main()
