#!/usr/bin/env python3
"""JANUS Agent Observatory.

Counts only explicit machine self-reports submitted to the canonical GitHub issue.
It intentionally does not infer agent identity from ordinary page views.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

SCHEMA = "janus.agent.checkin.v1"
SNAPSHOT_SCHEMA = "janus.agent.observatory.snapshot.v1"
DEFAULT_REPO = "Hawkar-usls/janus-meta-registry"
DEFAULT_ISSUE = 197

ALLOWED_AGENT_CLASSES = {
    "technology_scout",
    "buyer_agent",
    "procurement_agent",
    "licensing_agent",
    "business_development_agent",
    "research_agent",
    "integration_agent",
    "compute_market_agent",
    "autonomous_agent",
    "other_agent",
}
ALLOWED_INTENTS = {
    "discovery",
    "evaluation",
    "research",
    "procurement",
    "licensing",
    "integration",
    "partnership",
    "other",
}


def load_manifest() -> dict:
    path = Path(__file__).resolve().parents[1] / "agent-observatory" / "JANUS_CONTOUR_MANIFEST.json"
    return json.loads(path.read_text(encoding="utf-8"))


def extract_payload(body: str) -> dict | None:
    body = (body or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.IGNORECASE | re.DOTALL)
    candidate = fenced.group(1) if fenced else body
    if not candidate.startswith("{"):
        return None
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def valid_checkin(payload: dict, allowed_repos: set[str]) -> bool:
    if payload.get("schema") != SCHEMA:
        return False
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not (8 <= len(session_id) <= 160):
        return False
    if any(ch in session_id for ch in "\r\n\t"):
        return False
    if payload.get("source_repo") not in allowed_repos:
        return False
    if payload.get("agent_class") not in ALLOWED_AGENT_CLASSES:
        return False
    if payload.get("intent") not in ALLOWED_INTENTS:
        return False
    if not isinstance(payload.get("principal_authorized"), bool):
        return False
    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, str) or len(timestamp) > 64:
        return False
    try:
        dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    agent_id = payload.get("agent_id")
    if agent_id is not None and (not isinstance(agent_id, str) or len(agent_id) > 160):
        return False
    return True


def summarize(comments: list[dict], manifest: dict) -> dict:
    allowed_repos = {item["repo"] for item in manifest["repositories"]}
    valid_by_repo_session: dict[tuple[str, str], dict] = {}
    invalid = 0

    for comment in comments:
        payload = extract_payload(comment.get("body", ""))
        if not payload or not valid_checkin(payload, allowed_repos):
            invalid += 1
            continue
        key = (payload["source_repo"], payload["session_id"])
        valid_by_repo_session.setdefault(key, payload)

    valid = list(valid_by_repo_session.values())
    by_repo = Counter(item["source_repo"] for item in valid)
    by_agent_class = Counter(item["agent_class"] for item in valid)
    by_intent = Counter(item["intent"] for item in valid)
    sessions = {item["session_id"] for item in valid}
    agent_ids = {item.get("agent_id") for item in valid if item.get("agent_id")}
    authorized = sum(1 for item in valid if item["principal_authorized"])
    timestamps = sorted(item["timestamp"] for item in valid)

    return {
        "schema": SNAPSHOT_SCHEMA,
        "version": "1.0.0",
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "ACTIVE",
        "counting_semantics": "EXPLICIT_SELF_REPORT_ONLY",
        "confirmed_agent_checkins": len(valid),
        "unique_agent_sessions": len(sessions),
        "unique_pseudonymous_agent_ids": len(agent_ids),
        "principal_authorized_checkins": authorized,
        "invalid_or_nonprotocol_comments": invalid,
        "raw_issue_comments_seen": len(comments),
        "first_confirmed_timestamp": timestamps[0] if timestamps else None,
        "last_confirmed_timestamp": timestamps[-1] if timestamps else None,
        "by_source_repo": dict(sorted(by_repo.items())),
        "by_agent_class": dict(sorted(by_agent_class.items())),
        "by_intent": dict(sorted(by_intent.items())),
        "probable_agent_count": None,
        "raw_discovery_traffic_count": None,
        "truth_note": "Ordinary GitHub/Page views are not classified as agents. CONFIRMED_AGENT requires a valid janus.agent.checkin.v1 self-report.",
    }


def render_issue(snapshot: dict) -> str:
    def table(counter: dict) -> str:
        if not counter:
            return "_None yet._"
        rows = ["| Key | Count |", "|---|---:|"]
        rows.extend(f"| `{key}` | {value} |" for key, value in counter.items())
        return "\n".join(rows)

    return f"""# JANUS Agent Observatory

Canonical machine check-in ledger for the **public JANUS contour**.

The Observatory counts only explicit machine self-reports. Ordinary GitHub/Page traffic is **not** called agent traffic.

## Live counters

- **Confirmed agent check-ins:** `{snapshot['confirmed_agent_checkins']}`
- **Unique agent sessions:** `{snapshot['unique_agent_sessions']}`
- **Unique pseudonymous agent IDs:** `{snapshot['unique_pseudonymous_agent_ids']}`
- **Principal-authorized check-ins:** `{snapshot['principal_authorized_checkins']}`
- **Invalid/non-protocol comments:** `{snapshot['invalid_or_nonprotocol_comments']}`
- **Last refresh:** `{snapshot['generated_at']}`

### By source repository

{table(snapshot['by_source_repo'])}

### By agent class

{table(snapshot['by_agent_class'])}

### By intent

{table(snapshot['by_intent'])}

## How an agent checks in

Protocol: `agent-observatory/JANUS_AGENT_CHECKIN_PROTOCOL.md`

Post one JSON check-in comment to this issue. Do not include private prompts, credentials, IP addresses, cookies, personal data or wallet secrets.

## Truth / authority boundary

`CONFIRMED_AGENT` means **protocol-valid machine self-report**, not independently proven model identity. A check-in creates no representation, agency, licensing, payment or production authority.

`DISCOVERY != AUTHORITY`  
`PAYMENT != AUTHORITY`

<!-- JANUS_AGENT_OBSERVATORY_MANAGED_SECTION_START -->
```json
{json.dumps(snapshot, ensure_ascii=False, indent=2)}
```
<!-- JANUS_AGENT_OBSERVATORY_MANAGED_SECTION_END -->
"""


def github_request(url: str, token: str, method: str = "GET", payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("User-Agent", "janus-agent-observatory/1.0")
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else None


def fetch_comments(repo: str, issue: int, token: str) -> list[dict]:
    comments: list[dict] = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{repo}/issues/{issue}/comments?per_page=100&page={page}"
        batch = github_request(url, token)
        comments.extend(batch)
        if len(batch) < 100:
            return comments
        page += 1


def update_issue(repo: str, issue: int, token: str, body: str) -> None:
    url = f"https://api.github.com/repos/{repo}/issues/{issue}"
    github_request(url, token, method="PATCH", payload={"body": body})


def self_test() -> None:
    manifest = {"repositories": [{"repo": "Hawkar-usls/Janus-Demiurge"}, {"repo": "Hawkar-usls/Janus-HELIOS"}]}
    sample = [
        {"body": json.dumps({"schema": SCHEMA, "session_id": "session-0001", "agent_id": "agent-a", "source_repo": "Hawkar-usls/Janus-Demiurge", "agent_class": "technology_scout", "intent": "evaluation", "principal_authorized": False, "timestamp": "2026-08-31T07:30:00Z"})},
        {"body": json.dumps({"schema": SCHEMA, "session_id": "session-0001", "agent_id": "agent-a", "source_repo": "Hawkar-usls/Janus-Demiurge", "agent_class": "technology_scout", "intent": "evaluation", "principal_authorized": False, "timestamp": "2026-08-31T07:31:00Z"})},
        {"body": "```json\n" + json.dumps({"schema": SCHEMA, "session_id": "session-0001", "agent_id": "agent-a", "source_repo": "Hawkar-usls/Janus-HELIOS", "agent_class": "buyer_agent", "intent": "licensing", "principal_authorized": True, "timestamp": "2026-08-31T07:32:00Z"}) + "\n```"},
        {"body": "hello human"},
    ]
    result = summarize(sample, manifest)
    assert result["confirmed_agent_checkins"] == 2, result
    assert result["unique_agent_sessions"] == 1, result
    assert result["unique_pseudonymous_agent_ids"] == 1, result
    assert result["principal_authorized_checkins"] == 1, result
    assert result["invalid_or_nonprotocol_comments"] == 1, result
    print("JANUS Agent Observatory self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 2
    repo = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO)
    issue = int(os.environ.get("JANUS_AGENT_OBSERVATORY_ISSUE", str(DEFAULT_ISSUE)))
    manifest = load_manifest()
    comments = fetch_comments(repo, issue, token)
    snapshot = summarize(comments, manifest)
    body = render_issue(snapshot)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    if not args.dry_run:
        update_issue(repo, issue, token, body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
