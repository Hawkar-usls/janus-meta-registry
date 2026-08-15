#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile

from janus_guestbook_filter import _selftest as filter_selftest


HERE = Path(__file__).resolve().parent
PUBLISHER = HERE / "janus_guestbook_publish.py"


def body(message: str, consent: bool = True) -> str:
    mark = "x" if consent else " "
    return (
        f"### Message\n\n{message}\n\n"
        "### Public display\n\n"
        f"- [{mark}] I understand that my GitHub login and accepted message may be displayed publicly.\n"
    )


def event(number: int, login: str, message: str, consent: bool = True) -> dict:
    return {
        "issue": {
            "number": number,
            "title": "[GUESTBOOK] test",
            "body": body(message, consent),
            "html_url": f"https://github.com/Hawkar-usls/janus-meta-registry/issues/{number}",
            "created_at": f"2026-08-15T17:{number:02d}:00Z",
            "user": {"login": login},
        }
    }


def run_case(root: Path, payload: dict) -> dict[str, str]:
    event_path = root / f"event-{payload['issue']['number']}.json"
    event_path.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(PUBLISHER),
            "--event",
            str(event_path),
            "--guestbook",
            str(root / "messages.json"),
            "--quarantine",
            str(root / "quarantine.json"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    outputs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            outputs[key] = value
    return outputs


def main() -> None:
    filter_selftest()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        cases = [
            (event(1, "alice", "I disagree with JANUS."), "accepted", "PASS_NARROW_RESPECT_FILTER"),
            (event(2, "alice", "JANUS failed this test; preserve the negative result."), "accepted", "PASS_NARROW_RESPECT_FILTER"),
            (event(3, "alice", "JANUS is an idiot"), "quarantined", "JANUS_MENTION_WITH_PROFANITY_OR_DIRECT_INSULT"),
            (event(4, "alice", "A fourth safe note should not publish."), "quarantined", "AUTHOR_MESSAGE_LIMIT_3"),
            (event(5, "bob", "Found the registry through Linear A. Keep the evidence open."), "accepted", "PASS_NARROW_RESPECT_FILTER"),
            (event(6, "charlie", "This bypasses the Issue Form consent.", consent=False), "quarantined", "PUBLIC_DISPLAY_CONSENT_MISSING"),
        ]

        for payload, expected_status, expected_reason in cases:
            output = run_case(root, payload)
            assert output.get("status") == expected_status, (payload, output)
            assert output.get("reason") == expected_reason, (payload, output)

        messages = json.loads((root / "messages.json").read_text(encoding="utf-8"))
        quarantine = json.loads((root / "quarantine.json").read_text(encoding="utf-8"))

        assert len(messages["entries"]) == 3
        assert [x["author_login"] for x in messages["entries"]] == ["alice", "alice", "bob"]
        assert all(x["render_in_ticker"] is True for x in messages["entries"])
        assert messages["entries"][0]["message"] == "I disagree with JANUS."

        assert len(quarantine["entries"]) == 3
        reasons = {x["reason"] for x in quarantine["entries"]}
        assert reasons == {
            "JANUS_MENTION_WITH_PROFANITY_OR_DIRECT_INSULT",
            "AUTHOR_MESSAGE_LIMIT_3",
            "PUBLIC_DISPLAY_CONSENT_MISSING",
        }
        assert all("message" not in x for x in quarantine["entries"])
        assert all(len(x["message_sha256"]) == 64 for x in quarantine["entries"])
        assert all(x["render_in_ticker"] is False for x in quarantine["entries"])

        print("JANUS_GUESTBOOK_E2E_SELFTEST=PASS")
        print("ACCEPTED_MESSAGES=3")
        print("QUARANTINED_MESSAGES=3")
        print("MAX_MESSAGES_PER_LOGIN=3")
        print("CRITICISM_ALLOWED=TRUE")
        print("RAW_QUARANTINED_TEXT_STORED=FALSE")
        print("PUBLIC_SHAMING_TICKER=FALSE")


if __name__ == "__main__":
    main()
