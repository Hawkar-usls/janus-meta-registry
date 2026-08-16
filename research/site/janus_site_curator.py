#!/usr/bin/env python3
"""Build the deterministic JANUS activity/spotlight feed.

The curator ranks repository activity and explicit actionability metadata. It does
not rank scientific truth, positive outcome valence, ideology, or agreement with
JANUS. Surface membership is identity-first: a document mentioning another
research family does not become a member of that family.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "data/JANUS-SITE-CURATOR-POLICY-v1.1.json"
DEFAULT_OUTPUT = ROOT / "assets/site-feed.json"
REPOSITORY = "Hawkar-usls/janus-meta-registry"
GITHUB_BLOB = f"https://github.com/{REPOSITORY}/blob/main/"
SITE_BASE = "https://hawkar-usls.github.io/janus-meta-registry/"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def first_scalar(obj: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(obj, dict):
        lowered = {str(k).lower(): v for k, v in obj.items()}
        for key in keys:
            value = lowered.get(key.lower())
            if isinstance(value, (str, int, float, bool)):
                text = str(value).strip()
                if text:
                    return text
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, (str, int, float, bool)) and str(item).strip():
                        return str(item).strip()
        for value in obj.values():
            found = first_scalar(value, keys)
            if found:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = first_scalar(value, keys)
            if found:
                return found
    return None


def clean(text: str | None, limit: int) -> str | None:
    if not text:
        return None
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def markdown_metadata(text: str, fallback: str) -> tuple[str, str | None, str | None, str | None]:
    title = fallback
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    paragraphs = [
        p.strip()
        for p in re.split(r"\n\s*\n", text)
        if p.strip() and not p.lstrip().startswith("#") and not p.lstrip().startswith("<div")
    ]
    summary = paragraphs[0] if paragraphs else None
    return title, None, None, summary


def object_metadata(path: Path, text: str) -> tuple[str, str | None, str | None, str | None]:
    fallback = path.stem.replace("_", " ").replace("-", " ")
    if path.suffix.lower() == ".json":
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            return clean(fallback, 120) or fallback, "INVALID_JSON", None, "JSON parse failed; object retained as activity only."
        title = first_scalar(obj, ("title", "name", "artifact_id", "artifact", "id", "schema")) or fallback
        status = first_scalar(obj, ("status", "current_status", "state", "current_state", "conclusion", "result"))
        gate = first_scalar(obj, ("next_required_gate", "next_gate", "current_gate", "open_gate", "terminal_state"))
        summary = first_scalar(obj, ("summary", "purpose", "description", "claim_ceiling", "finding", "established"))
        return clean(title, 120) or fallback, clean(status, 80), clean(gate, 100), clean(summary, 220)
    if path.suffix.lower() == ".md":
        title, status, gate, summary = markdown_metadata(text, fallback)
        return clean(title, 120) or fallback, status, gate, clean(summary, 220)
    return clean(fallback, 120) or fallback, None, None, None


def classify_surface(path: str, title: str, policy: dict[str, Any]) -> tuple[str, str | None]:
    """Classify from object identity only; referenced topics inside content cannot route it."""
    identity = f"{path}\n{title}".upper()
    for rule in policy["surface_rules"]:
        if any(token.upper() in identity for token in rule["match_any"]):
            return rule["surface"], rule.get("site_path")
    return policy.get("routing", {}).get("unmatched_surface", "other"), None


def recency_points(age_days: float, policy: dict[str, Any]) -> int:
    for bucket in policy["ranking"]["recency_points"]:
        if age_days <= float(bucket["max_age_days"]):
            return int(bucket["points"])
    return 0


def rank_signals(
    path: str,
    title: str,
    status: str | None,
    gate: str | None,
    age_days: float,
    policy: dict[str, Any],
) -> tuple[int, list[str]]:
    """Score explicit identity/status/gate metadata, never broad body mentions."""
    metadata = "\n".join([path, title, status or "", gate or ""]).upper()
    score = recency_points(age_days, policy)
    reasons = ["recent-activity"]
    status_upper = (status or "").strip().upper()

    for signal_name, spec in policy["ranking"]["signals"].items():
        matched = any(token.upper() in metadata for token in spec.get("tokens", []))
        if spec.get("gate_present") and gate:
            matched = True
        if status_upper and status_upper in {str(x).upper() for x in spec.get("status_exact", [])}:
            matched = True
        if matched:
            score += int(spec["points"])
            reasons.append(signal_name.replace("_", "-"))
    return score, reasons


def spotlight_eligible(item: dict[str, Any], policy: dict[str, Any]) -> bool:
    rules = policy.get("spotlight", {})
    path = item["path"]
    prefixes = tuple(rules.get("eligible_path_prefixes", []))
    if prefixes and not path.startswith(prefixes):
        return False
    if path in set(rules.get("exclude_exact_paths", [])):
        return False
    if any(token in path for token in rules.get("exclude_path_contains", [])):
        return False
    return True


def latest_paths(policy: dict[str, Any]) -> list[tuple[str, str, str]]:
    lookback = int(policy["inputs"]["lookback_commits"])
    roots = policy["inputs"]["public_paths"]
    output = git(
        "log", "-n", str(lookback), "--date=iso-strict", "--format=@@%H%x09%cI", "--name-only", "--", *roots
    )
    seen: set[str] = set()
    result: list[tuple[str, str, str]] = []
    commit_sha = ""
    commit_time = ""
    allowed = {ext.lower() for ext in policy["inputs"]["extensions"]}
    excludes = tuple(policy["exclusions"]["path_contains"])
    maximum = int(policy["inputs"]["maximum_candidate_files"])

    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("@@"):
            commit_sha, commit_time = line[2:].split("\t", 1)
            continue
        if line in seen or any(token in line for token in excludes):
            continue
        path = ROOT / line
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        seen.add(line)
        result.append((line, commit_sha, commit_time))
        if len(result) >= maximum:
            break
    return result


def build_feed(policy: dict[str, Any]) -> dict[str, Any]:
    head_sha = git("rev-parse", "HEAD")
    head_time = git("show", "-s", "--format=%cI", "HEAD")
    now = parse_dt(head_time)
    max_bytes = int(policy["inputs"]["maximum_file_bytes_for_metadata"])
    entries: list[dict[str, Any]] = []

    for rel, commit_sha, modified_at in latest_paths(policy):
        path = ROOT / rel
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        text = raw[:max_bytes].decode("utf-8", errors="replace")
        title, status, gate, summary = object_metadata(path, text)
        modified = parse_dt(modified_at)
        age_days = max(0.0, (now - modified).total_seconds() / 86400.0)
        surface, site_path = classify_surface(rel, title, policy)
        score, reasons = rank_signals(rel, title, status, gate, age_days, policy)
        item: dict[str, Any] = {
            "path": rel,
            "title": title,
            "surface": surface,
            "modified_at": modified_at,
            "commit_sha": commit_sha,
            "sha256": digest,
            "github_url": GITHUB_BLOB + quote(rel, safe="/"),
            "score": score,
            "score_reasons": reasons,
        }
        if site_path:
            item["surface_url"] = SITE_BASE + site_path
        if status:
            item["status"] = status
        if gate:
            item["gate"] = gate
        if summary:
            item["summary"] = summary
        entries.append(item)

    # Latest is chronology, independent of curation score.
    entries = sorted(entries, key=lambda x: x["path"])
    entries = sorted(entries, key=lambda x: parse_dt(x["modified_at"]), reverse=True)
    latest = entries[: int(policy["outputs"]["latest_updates_count"])]

    # Stable deterministic ordering: score desc, modified desc, path asc.
    scored = sorted(entries, key=lambda x: x["path"])
    scored = sorted(scored, key=lambda x: parse_dt(x["modified_at"]), reverse=True)
    scored = sorted(scored, key=lambda x: x["score"], reverse=True)

    spotlight: list[dict[str, Any]] = []
    family_counts: defaultdict[str, int] = defaultdict(int)
    family_cap = int(policy["outputs"]["spotlight_family_cap"])
    for item in scored:
        if not spotlight_eligible(item, policy):
            continue
        if family_counts[item["surface"]] >= family_cap:
            continue
        spotlight.append(item)
        family_counts[item["surface"]] += 1
        if len(spotlight) >= int(policy["outputs"]["spotlight_count"]):
            break

    per_surface: dict[str, list[dict[str, Any]]] = {}
    per_count = int(policy["outputs"]["per_surface_count"])
    surfaces = [rule["surface"] for rule in policy["surface_rules"]] + ["other"]
    for surface in surfaces:
        per_surface[surface] = [item for item in entries if item["surface"] == surface][:per_count]

    return {
        "schema": "janus.site.activity_feed.v1_1",
        "status": "AUTO_GENERATED_PRESENTATION_INDEX",
        "generated_at": head_time,
        "source_commit": head_sha,
        "policy": "data/JANUS-SITE-CURATOR-POLICY-v1.1.json",
        "repository": REPOSITORY,
        "candidate_count": len(entries),
        "latest_updates": latest,
        "spotlight": spotlight,
        "surfaces": per_surface,
        "claim_ceiling": policy["claim_ceiling"],
        "ranking_note": "Scores represent recent activity and explicit identity/status/gate actionability only; body cross-references do not route or score an object.",
    }


def validate(feed: dict[str, Any], policy: dict[str, Any]) -> None:
    assert feed["schema"] == "janus.site.activity_feed.v1_1"
    assert feed["status"] == "AUTO_GENERATED_PRESENTATION_INDEX"
    assert len(feed["latest_updates"]) <= int(policy["outputs"]["latest_updates_count"])
    assert len(feed["spotlight"]) <= int(policy["outputs"]["spotlight_count"])
    assert "FEATURED != SCIENTIFICALLY_TRUE" in feed["claim_ceiling"]
    assert "CURATION_SCORE != EVIDENCE_STRENGTH" in feed["claim_ceiling"]
    assert "MENTION != SURFACE_MEMBERSHIP" in feed["claim_ceiling"]
    assert policy["ranking"]["status_valence_used"] is False
    assert policy["ranking"]["positive_result_bonus"] == 0
    assert policy["ranking"]["negative_result_penalty"] == 0
    assert policy["ranking"]["null_result_penalty"] == 0
    assert policy["routing"]["full_content_mentions_may_route"] is False
    assert policy["ranking"]["full_content_mentions_may_score"] is False
    assert policy["autonomy_boundary"]["may_rewrite_scientific_source_objects"] is False
    assert policy["autonomy_boundary"]["may_raise_claim_ceiling"] is False

    for canary in policy.get("routing_canaries", []):
        observed, _ = classify_surface(canary["path"], canary["title"], policy)
        assert observed == canary["expected_surface"], (
            f"routing canary failed: {canary['path']} expected {canary['expected_surface']} got {observed}"
        )

    for item in feed["latest_updates"] + feed["spotlight"]:
        assert item["github_url"].startswith("https://github.com/Hawkar-usls/janus-meta-registry/blob/main/")
        assert len(item["sha256"]) == 64
        assert isinstance(item["score"], int)

    assert all(item["path"] != "data/INDEX.md" for item in feed["spotlight"])
    assert all(item["path"] not in {"README.md", "PROJECT_STATUS.json"} for item in feed["spotlight"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    policy_path = args.policy if args.policy.is_absolute() else ROOT / args.policy
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    feed = build_feed(policy)
    validate(feed, policy)

    if not args.validate_only:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(feed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"JANUS_SITE_CURATOR_SOURCE_COMMIT={feed['source_commit']}")
    print(f"JANUS_SITE_CURATOR_CANDIDATES={feed['candidate_count']}")
    print(f"JANUS_SITE_CURATOR_LATEST={len(feed['latest_updates'])}")
    print(f"JANUS_SITE_CURATOR_SPOTLIGHT={len(feed['spotlight'])}")
    print("JANUS_SITE_CURATOR_ROUTING_SCOPE=IDENTITY_ONLY")
    print("JANUS_SITE_CURATOR_POLICY_BOUNDARY=PASS")
    print("JANUS_SITE_CURATOR=PASS")


if __name__ == "__main__":
    main()
