#!/usr/bin/env python3
"""Convert one JANUS Guestbook issue event into cache or quarantine JSON.

The workflow is automatic and deterministic:
- GitHub login is the displayed nickname;
- maximum three processed guestbook submissions per login;
- messages are at most 100 characters;
- explicit public-display consent from the Issue Form is required;
- JANUS mention + profanity/direct insult is quarantined;
- quarantined raw text is not copied into the website JSON;
- accepted entries are appended to guestbook/messages.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from janus_guestbook_filter import evaluate_message


HEADING_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
MAX_MESSAGES_PER_LOGIN = 3
MAX_MESSAGE_CHARACTERS = 100


def parse_issue_form(body: str) -> dict[str, str]:
    matches = list(HEADING_RE.finditer(body or ""))
    fields: dict[str, str] = {}
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        fields[match.group(1).strip().lower()] = body[start:end].strip()
    return fields


def plain_one_line(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text or "", flags=re.S)
    text = text.replace("\x00", "")
    return re.sub(r"\s+", " ", text).strip()


def load_json(path: Path, fallback: dict) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return fallback


def save_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")
    else:
        print(f"{name}={value}")


def append_quarantine(
    quarantine: dict,
    *,
    issue_number: int,
    issue_url: str,
    author_login: str,
    created_at: str,
    reason: str,
    message: str,
) -> bool:
    entries = quarantine.setdefault("entries", [])
    if any(int(entry.get("issue_number", -1)) == issue_number for entry in entries):
        return False
    entries.append(
        {
            "issue_number": issue_number,
            "issue_url": issue_url,
            "author_login": author_login,
            "created_at": created_at,
            "reason": reason,
            "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
            "raw_message_stored": False,
            "render_in_ticker": False,
        }
    )
    quarantine["entry_count"] = len(entries)
    quarantine["last_issue_number"] = issue_number
    return True


def processed_count(author_login: str, guestbook: dict, quarantine: dict) -> int:
    login = author_login.casefold()
    accepted = sum(
        1 for entry in guestbook.get("entries", [])
        if str(entry.get("author_login", "")).casefold() == login
    )
    rejected = sum(
        1 for entry in quarantine.get("entries", [])
        if str(entry.get("author_login", "")).casefold() == login
    )
    return accepted + rejected


def quarantine_and_exit(
    quarantine_path: Path,
    quarantine: dict,
    *,
    issue_number: int,
    issue_url: str,
    author_login: str,
    created_at: str,
    reason: str,
    message: str,
) -> int:
    append_quarantine(
        quarantine,
        issue_number=issue_number,
        issue_url=issue_url,
        author_login=author_login,
        created_at=created_at,
        reason=reason,
        message=message,
    )
    save_json(quarantine_path, quarantine)
    write_output("status", "quarantined")
    write_output("reason", reason)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--guestbook", required=True)
    parser.add_argument("--quarantine", required=True)
    args = parser.parse_args()

    event = json.loads(Path(args.event).read_text(encoding="utf-8"))
    issue = event.get("issue") or {}
    issue_number = int(issue.get("number", 0))
    title = str(issue.get("title") or "")
    body = str(issue.get("body") or "")
    author_login = str((issue.get("user") or {}).get("login") or "unknown")
    issue_url = str(issue.get("html_url") or "")
    created_at = str(issue.get("created_at") or "")

    if not title.startswith("[GUESTBOOK]"):
        write_output("status", "ignored")
        write_output("reason", "NOT_GUESTBOOK_ISSUE")
        return 0

    fields = parse_issue_form(body)
    message = plain_one_line(fields.get("message", ""))
    public_display = fields.get("public display", "")
    consent = re.search(r"\[[xX]\]", public_display) is not None

    guestbook_path = Path(args.guestbook)
    quarantine_path = Path(args.quarantine)
    guestbook = load_json(
        guestbook_path,
        {
            "schema": "janus.guestbook.public_messages.v1",
            "status": "PUBLIC_AUTOMATIC_GUESTBOOK_CACHE",
            "entries": [],
        },
    )
    quarantine = load_json(
        quarantine_path,
        {
            "schema": "janus.guestbook.quarantine.v1",
            "status": "PUBLIC_AUDIT_LEDGER_NOT_RENDERED_IN_TICKER",
            "entries": [],
        },
    )

    known_issue_numbers = {
        int(entry.get("issue_number", -1))
        for collection in (guestbook.get("entries", []), quarantine.get("entries", []))
        for entry in collection
    }
    if issue_number in known_issue_numbers:
        write_output("status", "duplicate")
        write_output("reason", "ISSUE_ALREADY_PROCESSED")
        return 0

    if not consent:
        return quarantine_and_exit(
            quarantine_path,
            quarantine,
            issue_number=issue_number,
            issue_url=issue_url,
            author_login=author_login,
            created_at=created_at,
            reason="PUBLIC_DISPLAY_CONSENT_MISSING",
            message=message,
        )

    if not message:
        return quarantine_and_exit(
            quarantine_path,
            quarantine,
            issue_number=issue_number,
            issue_url=issue_url,
            author_login=author_login,
            created_at=created_at,
            reason="EMPTY_MESSAGE",
            message=message,
        )

    if len(message) > MAX_MESSAGE_CHARACTERS:
        return quarantine_and_exit(
            quarantine_path,
            quarantine,
            issue_number=issue_number,
            issue_url=issue_url,
            author_login=author_login,
            created_at=created_at,
            reason="MESSAGE_TOO_LONG_MAX_100",
            message=message,
        )

    if processed_count(author_login, guestbook, quarantine) >= MAX_MESSAGES_PER_LOGIN:
        return quarantine_and_exit(
            quarantine_path,
            quarantine,
            issue_number=issue_number,
            issue_url=issue_url,
            author_login=author_login,
            created_at=created_at,
            reason="AUTHOR_MESSAGE_LIMIT_3",
            message=message,
        )

    result = evaluate_message(message)
    if not result.accepted:
        return quarantine_and_exit(
            quarantine_path,
            quarantine,
            issue_number=issue_number,
            issue_url=issue_url,
            author_login=author_login,
            created_at=created_at,
            reason=result.reason,
            message=message,
        )

    entries = guestbook.setdefault("entries", [])
    entries.append(
        {
            "issue_number": issue_number,
            "issue_url": issue_url,
            "author_login": author_login,
            "display_name": f"@{author_login}",
            "message": message,
            "created_at": created_at,
            "publication_mode": "AUTOMATIC_AFTER_DETERMINISTIC_FILTER",
            "render_in_ticker": True,
        }
    )
    guestbook["entry_count"] = len(entries)
    guestbook["last_issue_number"] = issue_number
    save_json(guestbook_path, guestbook)

    write_output("status", "accepted")
    write_output("reason", result.reason)
    write_output("issue_number", str(issue_number))
    return 0


if __name__ == "__main__":
    sys.exit(main())
