#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from repair_quarantined_json import TARGETS, strip_json_line_comments

SECOND_PASS = [
    "data/JANUS-ARCHITECTURAL-INFLUENCE-REGISTRY-V18.json",
    "data/JANUS-DOGMA-DIVINE-KEVIN-SMITH-CROSS-REFERENCES-v1.2.json",
    "data/janus-ai-integration-v5.9.json",
    "data/janus-registry-v5.2.json",
]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def container_events(line: str) -> list[str]:
    events: list[str] = []
    in_string = False
    escaped = False
    for ch in line:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[}]":
            events.append(ch)
    return events


def normalize_v18_ellipsis(text: str) -> tuple[str, dict[str, int]]:
    text, comments_removed = strip_json_line_comments(text)
    inline_object = len(re.findall(r"\{\s*\.\.\.\s*\}", text))
    inline_array = len(re.findall(r"\[\s*\.\.\.\s*\]", text))
    text = re.sub(
        r"\{\s*\.\.\.\s*\}",
        '{"_omitted_in_original_source": true}',
        text,
    )
    text = re.sub(
        r"\[\s*\.\.\.\s*\]",
        '[{"_omitted_in_original_source": true}]',
        text,
    )

    lines = text.splitlines()
    stack: list[str] = []
    out: list[str] = []
    standalone = 0
    object_counter = 0

    def next_nonblank(index: int) -> str:
        for nxt in lines[index + 1:]:
            if nxt.strip():
                return nxt.strip()
        return ""

    for idx, raw_line in enumerate(lines):
        line = raw_line
        if re.fullmatch(r"\s*\.\.\.\s*,?\s*", line):
            standalone += 1
            indent = line[: len(line) - len(line.lstrip())]
            nxt = next_nonblank(idx)
            if not stack:
                raise ValueError("ellipsis outside JSON container")
            top = stack[-1]
            if top == "{":
                object_counter += 1
                needs_comma = not nxt.startswith("}")
                line = (
                    indent
                    + json.dumps(f"_omitted_in_original_source_{object_counter}")
                    + ": true"
                    + ("," if needs_comma else "")
                )
            elif top == "[":
                needs_comma = not nxt.startswith("]")
                line = (
                    indent
                    + '{"_omitted_in_original_source": true}'
                    + ("," if needs_comma else "")
                )
            else:
                raise ValueError(f"unknown container {top!r}")

        out.append(line)
        for event in container_events(line):
            if event in "{[":
                stack.append(event)
            elif event == "}" and stack and stack[-1] == "{":
                stack.pop()
            elif event == "]" and stack and stack[-1] == "[":
                stack.pop()

    return "\n".join(out) + "\n", {
        "comments_removed": comments_removed,
        "inline_object_ellipsis": inline_object,
        "inline_array_ellipsis": inline_array,
        "standalone_ellipsis": standalone,
    }


def extract_root_object(text: str) -> tuple[str, str, str]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("root JSON object boundaries not found")
    prefix = text[:start]
    suffix = text[end + 1:]
    body = text[start:end + 1]
    return body + "\n", prefix, suffix


def repair_v18(text: str) -> tuple[str, list[str]]:
    repaired, stats = normalize_v18_ellipsis(text)
    value = json.loads(repaired)
    if not isinstance(value, dict):
        raise TypeError("V18 root is not an object")
    value["_repair_notice"] = {
        "status": "VALID_JSON_WITH_EXPLICIT_SOURCE_OMISSIONS",
        "missing_content_invented": False,
        "original_literal_ellipsis_preserved_as_markers": True,
        "repair_stats": stats,
    }
    return dump_json(value), [
        "removed comments outside strings",
        "converted literal ellipsis placeholders into explicit omission markers",
        "did not reconstruct omitted v15/v17 fields",
    ]


def repair_dogma(text: str) -> tuple[str, list[str]]:
    actions: list[str] = []
    patterns = [
        (r'("year"\s*:\s*)(\d{4}-\d{4}\s+publication window)(\s*,)', "publication-window year"),
        (r'("year"\s*:\s*)(\d{4}-\d{4})(\s*,)', "year range"),
    ]
    for pattern, label in patterns:
        text, count = re.subn(pattern, r'\1"\2"\3', text)
        if count:
            actions.append(f"quoted {count} unquoted {label} value(s)")
    value = json.loads(text)
    return dump_json(value), actions


def repair_ai_integration(text: str) -> tuple[str, list[str]]:
    body, prefix, suffix = extract_root_object(text)
    value = json.loads(body)
    return dump_json(value), [
        f"removed non-JSON framing glyphs around root object (prefix_chars={len(prefix)}, suffix_chars={len(suffix)})"
    ]


def repair_registry_v52(text: str) -> tuple[str, list[str]]:
    body, prefix, suffix = extract_root_object(text)
    actions = [
        f"removed non-JSON trailing/leading annotation outside root object (prefix_chars={len(prefix)}, suffix_chars={len(suffix)})"
    ]
    if "\\uD83E\\uC82" in body:
        body = body.replace("\\uD83E\\uC82", "🧂")
        actions.append("repaired truncated salt emoji surrogate escape to U+1F9C2")
    value = json.loads(body)
    return dump_json(value), actions


def repair_one(rel: str, text: str) -> tuple[str, list[str], str]:
    try:
        json.loads(text)
        return text, [], "ALREADY_VALID_JSON"
    except Exception:
        pass

    if rel == SECOND_PASS[0]:
        repaired, actions = repair_v18(text)
    elif rel == SECOND_PASS[1]:
        repaired, actions = repair_dogma(text)
    elif rel == SECOND_PASS[2]:
        repaired, actions = repair_ai_integration(text)
    elif rel == SECOND_PASS[3]:
        repaired, actions = repair_registry_v52(text)
    else:
        raise ValueError(rel)

    json.loads(repaired)
    return repaired, actions, "REPAIRED_VALID_JSON"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--report", default="data/JANUS-QUARANTINE-REPAIR-2026-08-25-v2.json")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    report: dict[str, Any] = {
        "artifact_uuid": "JANUS-QUARANTINE-REPAIR-2026-08-25-v2",
        "schema": "janus.registry.quarantine_repair_receipt.v2",
        "policy": {
            "invent_missing_data": False,
            "preserve_source_meaning": True,
            "explicit_omission_markers_for_literal_ellipsis": True,
            "strip_only_non_json_framing_outside_root": True,
        },
        "second_pass_targets": SECOND_PASS,
        "results": [],
    }

    for rel in SECOND_PASS:
        p = root / rel
        original = p.read_text(encoding="utf-8-sig")
        row: dict[str, Any] = {
            "path": rel,
            "before_sha256": sha256_text(original),
        }
        try:
            repaired, actions, status = repair_one(rel, original)
            p.write_text(repaired, encoding="utf-8")
            row.update({
                "status": status,
                "after_sha256": sha256_text(repaired),
                "changed": repaired != original,
                "actions": actions,
            })
        except Exception as exc:
            row.update({
                "status": "UNRESOLVED_LEFT_UNCHANGED",
                "changed": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
        report["results"].append(row)

    invalid: list[dict[str, str]] = []
    for rel in TARGETS:
        p = root / rel
        try:
            json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            invalid.append({"path": rel, "error": str(exc)})

    report["all_14_validation"] = {
        "targets": len(TARGETS),
        "valid": len(TARGETS) - len(invalid),
        "invalid": invalid,
    }
    report["repair_run_status"] = "PASS_ALL_14_VALID_JSON" if not invalid else "FAIL_REMAINING_INVALID_JSON"

    report_path = root / args.report
    report_path.write_text(dump_json(report), encoding="utf-8")
    print(dump_json(report), end="")
    return 0 if not invalid else 2


if __name__ == "__main__":
    raise SystemExit(main())
