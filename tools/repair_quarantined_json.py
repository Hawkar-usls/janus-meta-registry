#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

TARGETS = [
    "data/JANUS-ARCHITECTURAL-INFLUENCE-REGISTRY-V18.json",
    "data/JANUS-ARCHITECTURE-V26.4.json",
    "data/JANUS-CINEMA-SOUL-SIGNAL-REGISTRY-v24.1.json",
    "data/JANUS-DOGMA-DIVINE-KEVIN-SMITH-CROSS-REFERENCES-v1.2.json",
    "data/JANUS-FERMI-META-IRONY-PROTOCOL-v1.0.json",
    "data/JANUS-LINEAR-A-R7-B0-ARITHMETIC-SUMMARY-ROLE-SPEC-2026-08-15-v0.1.json",
    "data/JANUS-MULTIVERSE-ROSEWINE-SPIDER-DEADGIRL-v1.0.json",
    "data/JANUS_META_REGISTRY_v21.4_FINAL.json",
    "data/janus-ai-integration-v5.9.json",
    "data/janus-meta-registry-v9.5-academic.json",
    "data/janus-registry-v5.2.json",
    "data/janus_pathfinder_registry.json",
    "data/proofs/stochastic_light_interface_model.json",
    "data/semantic_field_registry_v12.json",
]

LOOSE_FILES = {
    "data/JANUS-CINEMA-SOUL-SIGNAL-REGISTRY-v24.1.json",
    "data/JANUS-MULTIVERSE-ROSEWINE-SPIDER-DEADGIRL-v1.0.json",
}

FENCED_FILES = {
    "data/JANUS_META_REGISTRY_v21.4_FINAL.json",
    "data/janus-meta-registry-v9.5-academic.json",
    "data/proofs/stochastic_light_interface_model.json",
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def strip_markdown_fence(text: str) -> tuple[str, bool]:
    stripped = text.strip()
    if stripped.startswith("```json") and stripped.endswith("```"):
        body = stripped[len("```json"):]
        body = body[:-3]
        return body.strip() + "\n", True
    return text, False


def strip_json_line_comments(text: str) -> tuple[str, int]:
    out: list[str] = []
    in_string = False
    escaped = False
    removed = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            removed += 1
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out), removed


def decode_legacy_unicode_tokens(value: str) -> str:
    value = re.sub(
        r"uU([0-9A-Fa-f]{8})",
        lambda m: chr(int(m.group(1), 16)),
        value,
    )
    value = re.sub(
        r"u([0-9A-Fa-f]{4})",
        lambda m: chr(int(m.group(1), 16)),
        value,
    )
    return value


def repair_invalid_json_unicode_escapes(text: str) -> tuple[str, int]:
    count = 0

    def repl_uU(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return chr(int(match.group(1), 16))

    def repl_U(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return chr(int(match.group(1), 16))

    text = re.sub(r"\\uU([0-9A-Fa-f]{8})", repl_uU, text)
    text = re.sub(r"\\U([0-9A-Fa-f]{8})", repl_U, text)
    if "\\uD83E\\uC82" in text:
        text = text.replace("\\uD83E\\uC82", "🧂")
        count += 1
    return text, count


def parse_scalar(raw: str) -> Any:
    s = raw.strip()
    if s.endswith(","):
        s = s[:-1].rstrip()
    s = decode_legacy_unicode_tokens(s)
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low == "null":
        return None
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?(?:\d+\.\d*|\d*\.\d+)", s):
        return float(s)
    return s


def parse_loose_registry(text: str) -> Any:
    root: Any = None
    stack: list[Any] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "{":
            if root is None:
                root = {}
                stack.append(root)
            elif isinstance(stack[-1], list):
                obj: dict[str, Any] = {}
                stack[-1].append(obj)
                stack.append(obj)
            else:
                raise ValueError(f"unexpected bare object opener: {raw_line!r}")
            continue
        if line in {"}", "},", "]", "],"}:
            if not stack:
                raise ValueError(f"unexpected closer: {raw_line!r}")
            stack.pop()
            continue
        if not stack:
            raise ValueError(f"content outside root: {raw_line!r}")

        current = stack[-1]
        if isinstance(current, dict):
            m = re.fullmatch(r"([A-Za-z0-9_\-]+)\s+([\{\[]),?", line)
            if m:
                key, opener = m.groups()
                child: Any = {} if opener == "{" else []
                current[key] = child
                stack.append(child)
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                raise ValueError(f"cannot parse mapping line: {raw_line!r}")
            key, value = parts
            current[key] = parse_scalar(value)
            continue

        if isinstance(current, list):
            current.append(parse_scalar(line))
            continue

        raise TypeError(type(current).__name__)

    if root is None:
        raise ValueError("empty loose registry")
    if stack:
        raise ValueError(f"unclosed containers: {len(stack)}")
    return root


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


def normalize_ellipsis_json(text: str) -> tuple[str, int]:
    text = re.sub(r"\{\s*\.\.\.\s*\}", '{"_omitted_in_source": true}', text)
    text = re.sub(r"\[\s*\.\.\.\s*\]", '[{"_omitted_in_source": true}]', text)

    stack: list[str] = []
    out: list[str] = []
    replaced = 0
    object_placeholder_counter = 0

    for raw_line in text.splitlines():
        line = raw_line
        if re.fullmatch(r"\s*\.\.\.\s*,?\s*", line):
            replaced += 1
            indent = line[: len(line) - len(line.lstrip())]
            if stack and stack[-1] == "[":
                line = indent + '{"_omitted_in_source": true},'
            elif stack and stack[-1] == "{":
                object_placeholder_counter += 1
                line = indent + json.dumps(f"_omitted_in_source_{object_placeholder_counter}") + ": true,"
            else:
                raise ValueError("ellipsis encountered outside a JSON container")
        out.append(line)
        for event in container_events(line):
            if event in "{[":
                stack.append(event)
            elif event == "}":
                if stack and stack[-1] == "{":
                    stack.pop()
            elif event == "]":
                if stack and stack[-1] == "[":
                    stack.pop()

    return "\n".join(out) + "\n", replaced


def recover_pathfinder(text: str) -> dict[str, Any]:
    marker = "```json"
    if marker not in text:
        raise ValueError("embedded JSON marker not found")
    prefix, embedded = text.split(marker, 1)
    embedded = embedded.strip()
    if embedded.endswith("```"):
        embedded = embedded[:-3].rstrip()
    embedded, _ = strip_json_line_comments(embedded)
    embedded, _ = normalize_ellipsis_json(embedded)
    embedded_value = json.loads(embedded)
    return {
        "artifact_uuid": "JANUS-PATHFINDER-REGISTRY-FORENSIC-RECOVERY-2026-08-25",
        "recovery_status": "PARTIAL_SOURCE_FRAGMENT_PRESERVED_PLUS_EMBEDDED_DOCUMENT_RECOVERED",
        "source_path": "data/janus_pathfinder_registry.json",
        "source_fragment_complete": False,
        "corrupted_prefix_raw": prefix,
        "embedded_document": embedded_value,
        "recovery_notes": [
            "The original file is truncated mid-string before an embedded fenced JSON document.",
            "No missing text was invented or inferred.",
            "The damaged prefix is preserved byte-for-text as a JSON string; the embedded complete document is parsed structurally.",
        ],
    }


def repair_one(rel: str, text: str) -> tuple[str, list[str]]:
    actions: list[str] = []

    if rel in LOOSE_FILES:
        value = parse_loose_registry(text)
        actions.append("parsed legacy loose key/value registry without inventing fields")
        return dump_json(value), actions

    if rel == "data/janus_pathfinder_registry.json":
        value = recover_pathfinder(text)
        actions.append("forensic wrapper: preserved truncated prefix and recovered embedded complete JSON")
        return dump_json(value), actions

    if rel in FENCED_FILES:
        text, changed = strip_markdown_fence(text)
        if changed:
            actions.append("removed Markdown ```json fence from .json payload")

    if rel == "data/janus-ai-integration-v5.9.json":
        first = text.find("{")
        if first > 0 and text[:first].strip():
            text = text[first:]
            actions.append("removed non-JSON leading glyph prefix before root object")

    if rel in {
        "data/JANUS-ARCHITECTURE-V26.4.json",
        "data/JANUS-ARCHITECTURAL-INFLUENCE-REGISTRY-V18.json",
    }:
        text, n = strip_json_line_comments(text)
        if n:
            actions.append(f"removed {n} JavaScript-style line comment(s) outside strings")

    if rel == "data/JANUS-ARCHITECTURAL-INFLUENCE-REGISTRY-V18.json":
        text, n = normalize_ellipsis_json(text)
        if n or "_omitted_in_source" in text:
            actions.append("converted source ellipsis placeholders to explicit non-invented omission markers")

    if rel == "data/JANUS-DOGMA-DIVINE-KEVIN-SMITH-CROSS-REFERENCES-v1.2.json":
        old = '"year": 1998-1999 publication window'
        new = '"year": "1998-1999 publication window"'
        if old in text:
            text = text.replace(old, new, 1)
            actions.append("quoted publication-window value that had been parsed as arithmetic")

    if rel == "data/JANUS-LINEAR-A-R7-B0-ARITHMETIC-SUMMARY-ROLE-SPEC-2026-08-15-v0.1.json":
        old = '"admission_claim_is_about_source-transcription arithmetic structure, not editorial certainty"'
        new = old + ': true'
        if old in text and new not in text:
            text = text.replace(old, new, 1)
            actions.append("restored missing boolean value on admission-claim policy key")

    text, n = repair_invalid_json_unicode_escapes(text)
    if n:
        actions.append(f"repaired {n} invalid Unicode escape sequence(s) without changing codepoint intent")

    value = json.loads(text)
    if rel == "data/JANUS-ARCHITECTURAL-INFLUENCE-REGISTRY-V18.json" and isinstance(value, dict):
        value["_repair_notice"] = {
            "status": "VALID_JSON_WITH_EXPLICIT_SOURCE_OMISSIONS",
            "missing_fields_reconstructed": False,
            "note": "Original artifact used literal ellipsis placeholders such as '...'; these are preserved as explicit omission markers rather than guessed content.",
        }
        actions.append("added transparent repair notice for intentionally omitted source sections")
    return dump_json(value), actions


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--report", default="data/JANUS-QUARANTINE-REPAIR-2026-08-25.json")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    report: dict[str, Any] = {
        "artifact_uuid": "JANUS-QUARANTINE-REPAIR-2026-08-25",
        "schema": "janus.registry.quarantine_repair_receipt.v1",
        "policy": {
            "invent_missing_data": False,
            "preserve_semantic_content": True,
            "validate_with_python_json_parser": True,
            "forensic_wrap_irrecoverably_truncated_source": True,
        },
        "targets_expected": len(TARGETS),
        "results": [],
    }

    failures = 0
    for rel in TARGETS:
        path = root / rel
        row: dict[str, Any] = {"path": rel}
        if not path.exists():
            row.update({"status": "MISSING", "error": "file not found"})
            failures += 1
            report["results"].append(row)
            continue
        original = path.read_text(encoding="utf-8-sig")
        row["before_sha256"] = sha256_text(original)
        try:
            repaired, actions = repair_one(rel, original)
            json.loads(repaired)
            path.write_text(repaired, encoding="utf-8")
            row.update({
                "status": "REPAIRED_VALID_JSON",
                "after_sha256": sha256_text(repaired),
                "actions": actions,
                "changed": repaired != original,
            })
        except Exception as exc:
            failures += 1
            row.update({
                "status": "UNRESOLVED_LEFT_UNCHANGED",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "changed": False,
            })
        report["results"].append(row)

    valid_after = 0
    for rel in TARGETS:
        path = root / rel
        if not path.exists():
            continue
        try:
            json.loads(path.read_text(encoding="utf-8-sig"))
            valid_after += 1
        except Exception:
            pass

    report["targets_valid_after"] = valid_after
    report["targets_unresolved_after"] = len(TARGETS) - valid_after
    report["repair_run_status"] = "PASS_ALL_TARGETS_VALID_JSON" if valid_after == len(TARGETS) else "PARTIAL_REPAIR_UNRESOLVED_TARGETS"

    report_path = root / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(dump_json(report), encoding="utf-8")
    print(dump_json(report), end="")
    return 0 if valid_after == len(TARGETS) else 2


if __name__ == "__main__":
    raise SystemExit(main())
