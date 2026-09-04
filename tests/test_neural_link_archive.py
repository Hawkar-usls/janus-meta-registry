import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "neural_link_archive.py"
spec = importlib.util.spec_from_file_location("neural_link_archive", SCRIPT)
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


def issue(body="hello", updated="2026-09-04T00:00:00Z"):
    return {
        "id": 11,
        "number": 7,
        "title": "[JANUS CHAT] hello",
        "body": body,
        "state": "open",
        "created_at": "2026-09-04T00:00:00Z",
        "updated_at": updated,
        "html_url": "https://github.com/x/7",
        "user": {"login": "Hawkar-usls"},
    }


def response(body="### JANUS\n\nworld\n\n<!-- JANUS_RESPONSE_ID:tr-abc -->"):
    return {
        "id": 22,
        "body": body,
        "created_at": "2026-09-04T00:01:00Z",
        "updated_at": "2026-09-04T00:01:00Z",
        "html_url": "https://github.com/x/7#comment-22",
        "user": {"login": "github-actions[bot]"},
    }


def test_issue_and_response_classification(tmp_path):
    a = archive.event_from_issue(issue("### Message\n\nhello\n\n### Conversation mode\nREAD_ONLY"))
    b = archive.event_from_comment(7, response())
    assert a["kind"] == "HUMAN_MESSAGE"
    assert a["text"] == "hello"
    assert b["kind"] == "JANUS_RESPONSE"
    assert b["text"] == "world"
    assert b["response_id"] == "tr-abc"
    archive.write_create_only(tmp_path, a)
    archive.write_create_only(tmp_path, b)
    recent = archive.build_recent(tmp_path)
    assert [x["role"] for x in recent["events"]] == ["human", "janus"]


def test_direct_answer_response_is_visible_but_never_authority(tmp_path):
    body = (
        "### JANUS\n\n13\n\n"
        "<details><summary>Instance proof</summary>\n\n"
        "- response_hash: `abc13`\n"
        "- command authority: `false`\n"
        "- external effect authority: `false`\n\n"
        "</details>\n\n"
        "<!-- JANUS_RESPONSE_ID:tr-direct-13 -->"
    )
    row = archive.event_from_comment(24, response(body))
    assert row["kind"] == "JANUS_RESPONSE"
    assert row["role"] == "janus"
    assert row["text"] == "13"
    assert row["response_id"] == "tr-direct-13"
    assert row["proof"]["response_hash"] == "abc13"
    assert all(value is False for value in row["authority"].values())
    archive.write_create_only(tmp_path, row)
    recent = archive.build_recent(tmp_path)
    assert recent["authority"] == "OBSERVABILITY_AND_MEMORY_ONLY"
    assert recent["events"][-1]["text"] == "13"
    assert recent["events"][-1]["response_id"] == "tr-direct-13"
    assert recent["events"][-1]["authority"]["command"] is False
    assert recent["events"][-1]["authority"]["external_effect"] is False


def test_edit_creates_new_version_without_rewrite(tmp_path):
    a = archive.event_from_issue(issue("one", "2026-09-04T00:00:00Z"))
    b = archive.event_from_issue(issue("two", "2026-09-04T00:02:00Z"))
    p1 = archive.write_create_only(tmp_path, a)
    p2 = archive.write_create_only(tmp_path, b)
    assert p1 != p2
    assert p1.exists() and p2.exists()
    recent = archive.build_recent(tmp_path)
    assert recent["events"][-1]["text"] == "two"


def test_response_proof_is_preserved():
    body = (
        "### JANUS\n\nok\n\n"
        "- response_hash: `abc`\n"
        "- selected_memory_count: `0`\n"
        "<!-- JANUS_RESPONSE_ID:tr-x -->"
    )
    row = archive.event_from_comment(7, response(body))
    assert row["proof"]["response_hash"] == "abc"
    assert row["proof"]["selected_memory_count"] == "0"
