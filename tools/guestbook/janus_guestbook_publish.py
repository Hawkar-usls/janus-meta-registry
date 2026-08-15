#!/usr/bin/env python3
"""Convert one JANUS Guestbook issue event into a safe JSON entry.

This script never executes visitor text. It parses fixed Issue Form headings,
collapses visitor text to plain one-line strings, applies the JANUS respect
filter, and appends only accepted entries to the guestbook JSON.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

from janus_guestbook_filter import evaluate_message


HEADING_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)


def parse_issue_form(body: str) -> dict[str, str]:
    matches = list(HEADING_RE.finditer(body or ""))
    fields: dict[str, str] = {}
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        value = body[start:end].strip()
        fields[match.group(1).strip().lower()] = value
    return fields


def plain_one_line(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text or "", flags=re.S)
    text = text.replace("\x00", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def write_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")
    else:
        print(f"{name}={value}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--guestbook", required=True)
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
    display_name = plain_one_line(fields.get("display name", ""))
    message = plain_one_line(fields.get("message", ""))

    if not display_name:
        display_name = author_login

    if len(display_name) > 30:
        write_output("status", "rejected")
        write_output("reason", "DISPLAY_NAME_TOO_LONG")
        return 0

    if not message:
        write_output("status", "rejected")
        write_output("reason", "EMPTY_MESSAGE")
        return 0

    if len(message) > 100:
        write_output("status", "rejected")
        write_output("reason", "MESSAGE_TOO_LONG_MAX_100")
        return 0

    result = evaluate_message(message)
    if not result.accepted:
        write_output("status", "rejected")
        write_output("reason", result.reason)
        return 0

    guestbook_path = Path(args.guestbook)
    if guestbook_path.exists():
        guestbook = json.loads(guestbook_path.read_text(encoding="utf-8"))
    else:
        guestbook = {
            "schema": "janus.guestbook.public_messages.v1",
            "status": "PUBLIC_AUTOMATIC_GUESTBOOK",
            "entries": [],
        }

    entries = guestbook.setdefault("entries", [])
    if any(int(entry.get("issue_number", -1)) == issue_number for entry in entries):
        write_output("status", "duplicate")
        write_output("reason", "ISSUE_ALREADY_PUBLISHED")
        return 0

    entries.append(
        {
            "issue_number": issue_number,
            "issue_url": issue_url,
            "author_login": author_login,
            "display_name": display_name,
            "message": message,
            "created_at": created_at,
            "publication_mode": "AUTOMATIC_AFTER_DETERMINISTIC_FILTER",
        }
    )

    guestbook["entry_count"] = len(entries)
    guestbook["last_issue_number"] = issue_number
    guestbook_path.write_text(
        json.dumps(guestbook, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    write_output("status", "accepted")
    write_output("reason", result.reason)
    write_output("issue_number", str(issue_number))
    return 0


if __name__ == "__main__":
    sys.exit(main())
