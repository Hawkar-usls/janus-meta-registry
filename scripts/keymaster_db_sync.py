"""JANUS DADDY_KEYMASTER: bounded, read-only Git-CAS DB -> Meta Registry JSON.

Source: public own project *pinned commit* on dedicated state branch.
Destination: immutable full JSON snapshots + idempotent LATEST pointer.
Never polls NAS, executes queued tasks, reads secrets, or changes worker rights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

from keymaster_db_verify import validate, verify_queue

SOURCE_REPO = "Hawkar-usls/Janus-Demiurge"
SOURCE_REF = "janus/daddy-keymaster-ci-queue-state"
SCHEMA = "janus.meta_registry.keymaster_db_snapshot.v1"
POINTER_SCHEMA = "janus.meta_registry.keymaster_db_latest.v1"
BASE = "https://raw.githubusercontent.com/" + SOURCE_REPO + "/"
API = "https://api.github.com/repos/" + SOURCE_REPO + "/"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MARKER = re.compile(r"^state/processed_sources/[0-9a-f]{64}\.json$")
ARCHIVE = re.compile(r"^state/archive_segments/[0-9]{8}\.json$")
MAX_ARCHIVES = 64
MAX_DOC_BYTES = 200_000
MAX_TOTAL_BYTES = 8_000_000


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def h(x):
    return hashlib.sha256(canonical(x)).hexdigest()


def get_json_url(url):
    request = Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "janus-meta-registry-keymaster-readonly-sync",
    })
    with urlopen(request, timeout=15) as response:
        body = response.read(MAX_DOC_BYTES + 1)
    if len(body) > MAX_DOC_BYTES:
        raise ValueError("KEYMASTER_SOURCE_TOO_LARGE")
    return json.loads(body)


def source_head():
    data = get_json_url(API + "git/ref/heads/" + SOURCE_REF)
    head = data.get("object", {}).get("sha")
    if not isinstance(head, str) or not HEX40.fullmatch(head):
        raise ValueError("KEYMASTER_UNPINNED_REF")
    return head


def exact_raw(head, path):
    if not HEX40.fullmatch(head):
        raise ValueError("KEYMASTER_INVALID_PIN")
    if not (path in ("state/relay_queue.json", "state/relay_archive_head.json")
            or ARCHIVE.fullmatch(path) or MARKER.fullmatch(path)):
        raise ValueError("KEYMASTER_UNAPPROVED_SOURCE_PATH")
    return get_json_url(BASE + head + "/" + quote(path, safe="/"))


def fetch_documents(head, fetch=exact_raw):
    """Only an exact Git commit is ever used to read the full set."""
    files = {"state/relay_queue.json": fetch(head, "state/relay_queue.json")}
    archive_head = fetch(head, "state/relay_archive_head.json")
    serial = archive_head.get("serial")
    if type(serial) is not int or not 1 <= serial <= MAX_ARCHIVES:
        raise ValueError("KEYMASTER_ARCHIVE_COUNT_BOUND")
    files["state/relay_archive_head.json"] = archive_head
    sources = set()
    for i in range(1, serial + 1):
        path = "state/archive_segments/%08d.json" % i
        segment = fetch(head, path)
        files[path] = segment
        for row in segment.get("queue", {}).get("tasks", {}).values():
            src = row.get("source_sha256")
            if not isinstance(src, str) or not HEX64.fullmatch(src):
                raise ValueError("KEYMASTER_INVALID_ARCHIVED_SOURCE")
            sources.add(src)
    if len(sources) > 2 * MAX_ARCHIVES:
        raise ValueError("KEYMASTER_MARKER_BOUND")
    for src in sorted(sources):
        files["state/processed_sources/" + src + ".json"] = fetch(
            head, "state/processed_sources/" + src + ".json"
        )
    if sum(len(canonical(x)) for x in files.values()) > MAX_TOTAL_BYTES:
        raise ValueError("KEYMASTER_TOTAL_SNAPSHOT_TOO_LARGE")
    return files


def validate_documents(head, files):
    """Invoke the independent R4 full replay on exact JSON source documents."""
    if not isinstance(head, str) or not HEX40.fullmatch(head):
        raise ValueError("KEYMASTER_INVALID_HEAD")
    if "state/relay_queue.json" not in files:
        raise ValueError("KEYMASTER_QUEUE_MISSING")
    if len(files) > 2 + MAX_ARCHIVES * 3:
        raise ValueError("KEYMASTER_FILE_COUNT_BOUND")
    if any(not (name in ("state/relay_queue.json", "state/relay_archive_head.json")
                or ARCHIVE.fullmatch(name) or MARKER.fullmatch(name)) for name in files):
        raise ValueError("KEYMASTER_UNAPPROVED_DOCUMENT")
    active = verify_queue(files["state/relay_queue.json"])
    with tempfile.TemporaryDirectory(prefix="janus-keymaster-verify-") as tmp:
        zpath = Path(tmp) / "snapshot.zip"
        rp = Path(tmp) / "proof.json"
        with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for path, document in sorted(files.items()):
                payload = canonical(document)
                if len(payload) > MAX_DOC_BYTES:
                    raise ValueError("KEYMASTER_OVERSIZED_DOCUMENT")
                z.writestr(path, payload)
        receipt = {
            "schema": "janus.daddy_keymaster.physical_backup_receipt.v1",
            "head_sha": head,
            "zip_sha256": hashlib.sha256(zpath.read_bytes()).hexdigest(),
            "queue_epoch": active["epoch"],
            "queue_tip_sha256": active["tip"],
        }
        rp.write_bytes(canonical(receipt))
        proof = validate(zpath, rp)
    if proof["status"] != "JANUS_INDEPENDENT_LOCAL_REPLAY_PASS":
        raise ValueError("KEYMASTER_INDEPENDENT_REPLAY_FAILED")
    return proof


def make_snapshot(head, files):
    proof = validate_documents(head, files)
    document = {
        "schema": SCHEMA,
        "status": "VERIFIED_READONLY_COPY_NOT_EXECUTION_AUTHORITY",
        "source_repo": SOURCE_REPO,
        "source_ref": SOURCE_REF,
        "source_commit_sha": head,
        "provenance": "EXACT_COMMIT_PUBLIC_GIT_CAS_STATE",
        "active_epoch": proof["queue_epoch"],
        "active_tip_sha256": files["state/relay_queue.json"]["tip_sha256"],
        "archive_count": proof["archive_segments"],
        "terminal_count_active": proof["completed"],
        "safety": {
            "no_private_nas_data": True,
            "remote_dispatch": False,
            "source_state_mutated": False,
            "champion_promoted": False,
            "paid_resources_used": False,
        },
        "documents": {name: files[name] for name in sorted(files)},
    }
    return {**document, "snapshot_sha256": h(document)}


def check_nonrewound(old_head, new_head, query=get_json_url):
    if old_head == new_head:
        return True
    if not HEX40.fullmatch(old_head) or not HEX40.fullmatch(new_head):
        raise ValueError("KEYMASTER_COMPARE_BAD_HEAD")
    result = query(API + "compare/" + old_head + "..." + new_head)
    if result.get("status") != "ahead" or result.get("behind_by") != 0:
        raise ValueError("KEYMASTER_SOURCE_REF_REWOUND_OR_DIVERGED")
    return True


def write_copy(snapshot, output_dir, compare=check_nonrewound):
    out = Path(output_dir)
    if snapshot.get("schema") != SCHEMA:
        raise ValueError("KEYMASTER_BAD_SNAPSHOT_SCHEMA")
    digest = snapshot.get("snapshot_sha256")
    body = {k:v for k,v in snapshot.items() if k != "snapshot_sha256"}
    if digest != h(body):
        raise ValueError("KEYMASTER_SNAPSHOT_DIGEST_MISMATCH")
    head = snapshot["source_commit_sha"]
    if not HEX40.fullmatch(head):
        raise ValueError("KEYMASTER_BAD_COMMIT")
    ptr = out / "LATEST.json"
    live = out / "MIRROR.json"
    live_hash = out / "MIRROR.sha256"
    rel = "snapshots/" + head + ".json"
    dest = out / rel
    if ptr.exists():
        old = json.loads(ptr.read_text(encoding="utf-8"))
        if old.get("schema") != POINTER_SCHEMA:
            raise ValueError("KEYMASTER_POINTER_SCHEMA_MISMATCH")
        prior_path = out / "snapshots" / (old["source_commit_sha"] + ".json")
        if (not HEX40.fullmatch(old["source_commit_sha"]) or
            old.get("snapshot_path") != "data/daddy_keymaster_db/snapshots/" + old["source_commit_sha"] + ".json" or
            not prior_path.exists()):
            raise ValueError("KEYMASTER_MISSING_PRIOR_PINNED_SNAPSHOT")
        prior = json.loads(prior_path.read_text(encoding="utf-8"))
        if (prior.get("snapshot_sha256") != old.get("snapshot_sha256") or
            h({k:v for k,v in prior.items() if k != "snapshot_sha256"}) != prior["snapshot_sha256"]):
            raise ValueError("KEYMASTER_PREVIOUS_SNAPSHOT_INVALID")
        if old["source_commit_sha"] != head:
            compare(old["source_commit_sha"], head)
        if old["source_commit_sha"] == head and old.get("snapshot_sha256") != digest:
            raise ValueError("KEYMASTER_SAME_HEAD_CHANGED_SNAPSHOT")
    encoded = canonical(snapshot) + b"\n"
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():
        if dest.read_bytes() != encoded:
            raise ValueError("KEYMASTER_IMMUTABLE_SNAPSHOT_COLLISION")
    else:
        # Exclusive creation: never replace a historical snapshot.
        with dest.open("xb") as f:
            f.write(encoded)
    pointer = {
        "schema": POINTER_SCHEMA,
        "status": "SOURCE_VERIFIED",
        "source_repo": SOURCE_REPO,
        "source_ref": SOURCE_REF,
        "source_commit_sha": head,
        "snapshot_sha256": digest,
        "snapshot_path": "data/daddy_keymaster_db/" + rel,
        "archive_count": snapshot["archive_count"],
        "active_epoch": snapshot["active_epoch"],
    }
    pbytes = canonical(pointer) + b"\n"
    # A stable small-endpoint full JSON DB is provided for an optional NAS
    # read-only cold mirror. The NAS never has to parse the pointer, run
    # Python, keep SSH keys or monitor a repository clone.
    expected_hash = hashlib.sha256(encoded).hexdigest() + "  MIRROR.json\n"
    stable_correct = (
        live.exists() and live.read_bytes() == encoded and
        live_hash.exists() and live_hash.read_text(encoding="utf-8") == expected_hash
    )
    pointer_correct = ptr.exists() and ptr.read_bytes() == pbytes
    if not stable_correct or not pointer_correct:
        live.write_bytes(encoded)
        live_hash.write_text(expected_hash, encoding="utf-8")
        ptr.write_bytes(pbytes)
        return "UPDATED"
    return "UNCHANGED"


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output-dir",default="data/daddy_keymaster_db")
    p.add_argument("--check-only",action="store_true")
    args=p.parse_args()
    commit=source_head()
    files=fetch_documents(commit)
    snapshot=make_snapshot(commit, files)
    if args.check_only:
        status="VERIFIED_ONLY"
    else:
        status=write_copy(snapshot, args.output_dir)
    print(json.dumps({"status":status, "source_head":commit,
                      "snapshot_sha256":snapshot["snapshot_sha256"],
                      "archive_count":snapshot["archive_count"],
                      "active_epoch":snapshot["active_epoch"],
                      "no_remote_dispatch":True},sort_keys=True))


if __name__=="__main__":
    main()
