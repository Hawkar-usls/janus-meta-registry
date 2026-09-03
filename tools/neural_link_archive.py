#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path
from typing import Any

SOURCE_REPO = "Hawkar-usls/-Terminal-for-Janus"
ARCHIVE_SCHEMA = "janus.neural_link.archive_event.v1"
HEAD_SCHEMA = "janus.neural_link.archive_head.v1"
RECENT_SCHEMA = "janus.neural_link.recent.v1"
PREFIX = "[JANUS CHAT]"
RESPONSE_RE = re.compile(r"JANUS_RESPONSE_ID:([^\s>]+)")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def api_json(url: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "JANUS-Neural-Link-Archive/1.0",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def issue_pages() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{SOURCE_REPO}/issues?state=all&sort=created&direction=asc&per_page=100&page={page}"
        batch = api_json(url)
        if not isinstance(batch, list):
            raise RuntimeError("TERMINAL_ISSUES_LIST_REQUIRED")
        if not batch:
            break
        for row in batch:
            if not isinstance(row, dict) or row.get("pull_request"):
                continue
            if str(row.get("title") or "").startswith(PREFIX):
                rows.append(row)
        if len(batch) < 100:
            break
        page += 1
    return rows


def comments(issue_number: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{SOURCE_REPO}/issues/{issue_number}/comments?per_page=100&page={page}"
        batch = api_json(url)
        if not isinstance(batch, list):
            raise RuntimeError("TERMINAL_COMMENTS_LIST_REQUIRED")
        rows.extend(row for row in batch if isinstance(row, dict))
        if len(batch) < 100:
            break
        page += 1
    return rows


def _extract_issue_text(body: str) -> str:
    text = str(body or "").strip()
    marker = "### Message"
    if marker in text:
        tail = text.split(marker, 1)[1].lstrip()
        for stop in ("### Conversation mode", "### Authority boundary"):
            if stop in tail:
                tail = tail.split(stop, 1)[0]
        if tail.strip():
            return tail.strip()
    return text


def _extract_response_text(body: str) -> str:
    text = str(body or "").strip()
    text = re.sub(r"^### JANUS\s*", "", text, flags=re.I)
    for marker in (
        "<details><summary>Instance proof</summary>",
        "<details><summary>HRAiN memory provenance</summary>",
        "<!-- JANUS_RESPONSE_ID:",
    ):
        if marker in text:
            text = text.split(marker, 1)[0]
    return text.strip()


def _proof_fields(body: str) -> dict[str, str]:
    allowed = {
        "resident_uuid", "model_digest", "file_fabric_digest", "turn_id", "response_hash",
        "hrain_head", "memory_source_commit", "hrain_context_hash", "hrain_context_receipt_hash",
        "selected_memory_count", "memory_path", "memory_match_status",
        "memory_context_is_evidence", "memory_grants_authority",
        "empty_memory_is_hrain_failure", "empty_memory_is_negative_evidence",
    }
    proof: dict[str, str] = {}
    for line in str(body or "").splitlines():
        match = re.match(r"^- ([a-z_ ]+): `([^`]+)`\s*$", line)
        if not match:
            continue
        key = match.group(1).strip().replace(" ", "_")
        if key in allowed:
            proof[key] = match.group(2)
    return proof


def event_from_issue(issue: dict[str, Any]) -> dict[str, Any]:
    body = str(issue.get("body") or "")
    actor = str(((issue.get("user") or {}).get("login") or ""))
    core = {
        "source_repository": SOURCE_REPO,
        "source_type": "issue",
        "source_id": int(issue["id"]),
        "issue_number": int(issue["number"]),
        "source_url": str(issue.get("html_url") or ""),
        "actor": actor,
        "role": "human" if actor == "Hawkar-usls" else "system",
        "kind": "HUMAN_MESSAGE" if actor == "Hawkar-usls" else "TRANSPORT_EVENT",
        "title": str(issue.get("title") or ""),
        "text": _extract_issue_text(body),
        "raw_body": body,
        "state": str(issue.get("state") or ""),
        "created_at": str(issue.get("created_at") or ""),
        "updated_at": str(issue.get("updated_at") or ""),
    }
    version_hash = sha256(core)
    return {
        "schema": ARCHIVE_SCHEMA,
        "event_id": f"issue-{issue['number']}",
        "version_hash": version_hash,
        **core,
        "authority": {
            "command": False,
            "claim": False,
            "scientific_evidence": False,
            "world_truth": False,
            "external_effect": False,
        },
    }


def event_from_comment(issue_number: int, comment: dict[str, Any]) -> dict[str, Any]:
    body = str(comment.get("body") or "")
    actor = str(((comment.get("user") or {}).get("login") or ""))
    response = RESPONSE_RE.search(body)
    is_response = response is not None
    core = {
        "source_repository": SOURCE_REPO,
        "source_type": "issue_comment",
        "source_id": int(comment["id"]),
        "issue_number": int(issue_number),
        "source_url": str(comment.get("html_url") or ""),
        "actor": actor,
        "role": "janus" if is_response else ("human" if actor == "Hawkar-usls" else "system"),
        "kind": "JANUS_RESPONSE" if is_response else ("HUMAN_MESSAGE" if actor == "Hawkar-usls" else "TRANSPORT_EVENT"),
        "response_id": response.group(1) if response else None,
        "text": _extract_response_text(body) if is_response else _extract_issue_text(body),
        "raw_body": body,
        "proof": _proof_fields(body) if is_response else {},
        "created_at": str(comment.get("created_at") or ""),
        "updated_at": str(comment.get("updated_at") or ""),
    }
    version_hash = sha256(core)
    return {
        "schema": ARCHIVE_SCHEMA,
        "event_id": f"comment-{comment['id']}",
        "version_hash": version_hash,
        **core,
        "authority": {
            "command": False,
            "claim": False,
            "scientific_evidence": False,
            "world_truth": False,
            "external_effect": False,
        },
    }


def write_create_only(root: Path, event: dict[str, Any]) -> Path:
    events = root / "events"
    events.mkdir(parents=True, exist_ok=True)
    path = events / f"{event['event_id']}-{event['version_hash'][:16]}.json"
    payload = json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise RuntimeError(f"ARCHIVE_CREATE_ONLY_CONFLICT:{path}")
    else:
        path.write_text(payload, encoding="utf-8")
    return path


def latest_versions(root: Path) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    events_dir = root / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(events_dir.glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("schema") != ARCHIVE_SCHEMA:
            continue
        key = str(row.get("event_id") or "")
        previous = latest.get(key)
        if previous is None or (
            str(row.get("updated_at") or ""), str(row.get("version_hash") or "")
        ) > (
            str(previous.get("updated_at") or ""), str(previous.get("version_hash") or "")
        ):
            latest[key] = row
    return sorted(latest.values(), key=lambda x: (str(x.get("created_at") or ""), int(x.get("source_id") or 0)))


def build_recent(root: Path, limit: int = 200) -> dict[str, Any]:
    rows = latest_versions(root)
    visible = [row for row in rows if row.get("kind") in {"HUMAN_MESSAGE", "JANUS_RESPONSE"}]
    visible = visible[-limit:]
    return {
        "schema": RECENT_SCHEMA,
        "status": "READ_ONLY_NEURAL_LINK_HISTORY",
        "source_repository": SOURCE_REPO,
        "archive_path": "data/JANUS-NEURAL-LINK/",
        "event_count": len(visible),
        "events": visible,
        "authority": "OBSERVABILITY_AND_MEMORY_ONLY",
        "laws": [
            "CHAT_EVENT != COMMAND_AUTHORITY",
            "CHAT_ARCHIVE != WORLD_TRUTH",
            "EDIT != REWRITE_OLD_EVENT",
            "META_REGISTRY_DB -> HRAIN -> TERMINAL",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--offline-snapshot")
    args = ap.parse_args()
    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)

    if args.offline_snapshot:
        snapshot = json.loads(Path(args.offline_snapshot).read_text(encoding="utf-8"))
        issue_rows = snapshot.get("issues") or []
        comment_map = snapshot.get("comments") or {}
    else:
        issue_rows = issue_pages()
        comment_map = {str(row["number"]): comments(int(row["number"])) for row in issue_rows}

    for issue in issue_rows:
        write_create_only(root, event_from_issue(issue))
        for comment in comment_map.get(str(issue["number"]), []):
            write_create_only(root, event_from_comment(int(issue["number"]), comment))

    recent = build_recent(root)
    recent_hash = sha256(recent)
    (root / "RECENT.json").write_text(
        json.dumps(recent, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    head = {
        "schema": HEAD_SCHEMA,
        "status": "ARCHIVE_SYNCED",
        "source_repository": SOURCE_REPO,
        "archive_path": "data/JANUS-NEURAL-LINK/",
        "latest_event_count": recent["event_count"],
        "recent_hash": recent_hash,
        "event_object_count": len(list((root / "events").glob("*.json"))),
        "append_only_event_objects": True,
        "mutable_head_is_authority": False,
        "cross_repo_write_credential_used": False,
    }
    (root / "HEAD.json").write_text(
        json.dumps(head, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": "PASS",
        "events": head["event_object_count"],
        "recent": recent["event_count"],
        "recent_hash": recent_hash,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
