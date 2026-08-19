#!/usr/bin/env python3
"""JANUS suspect-blind sequential reverse-pattern audit v1.0.

The executor intentionally separates two phases:

1. Every JSON is parsed and classified from its own source body only. File names,
   titles, narrative prose, prior Connection labels, and other records are not
   available as positive evidence. A deterministic hash-derived queue prevents
   choosing a convenient first target. Each receipt is frozen before the next
   receipt is produced.
2. Only after all receipts exist are structural signatures compared. Repetition
   can promote a *pattern candidate* only under the frozen repeat gate, and a
   mirror/back-forth gate is additionally required for the strongest structural
   status. Semantic identity/causality remains unconfirmed.

This is a structural detector, not a semantic oracle and not external
replication. Negative, not-applicable, and malformed records are retained.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

VERSION = "1.0"
EPHEMERAL_DIRS = {".git", "out", "node_modules", ".venv", "__pycache__"}

IGNORED_KEYS = {
    "artifact_uuid", "artifact_id", "artifact_slug", "schema", "schema_version",
    "version", "title", "display_title", "name", "filename", "path", "url",
    "display_url", "github_url", "source_url", "repository", "commit", "commit_sha",
    "sha", "sha1", "sha256", "sha256_raw", "sha256_canonical_json", "created_at",
    "created_at_utc", "created_at_local", "updated_at", "modified_at", "timestamp",
    "timestamp_utc", "timestamp_local", "description", "summary", "purpose", "note",
    "notes", "reason", "statement", "interpretation", "comment", "comments"
}

WORD_RE = re.compile(r"[A-Za-z0-9]+", re.ASCII)

FAMILY_TERMS = {
    "REVERSE_OR_INVERSE": {
        "reverse", "inverse", "invert", "inverted", "inversion", "backward",
        "backwards", "rewind", "undo"
    },
    "FORWARD_OR_REPLAY": {
        "forward", "replay", "redo"
    },
    "RETURN_ROLLBACK_RECOVERY_REASSEMBLY": {
        "return", "rollback", "recover", "recovery", "restore", "restoration",
        "reassemble", "reassembly", "regenerate", "regeneration", "rejuvenation"
    },
    "MIRROR_OR_SYMMETRY": {
        "mirror", "mirrored", "symmetry", "symmetric", "bidirectional",
        "bidir", "twoway", "two", "ways"
    },
    "REPEAT_OR_AGAIN": {
        "repeat", "repeated", "again", "rerun", "replay"
    },
    "DIRECTIONAL_BACK_FORWARD_LEFT_RIGHT": {
        "back", "backward", "forward", "left", "right", "again"
    },
    "EXACTNESS_OR_WITNESS": {
        "exact", "witness", "verified", "verification", "reproduce", "reproduced",
        "reproduction", "bytewise", "identical", "equality"
    },
    "GATE_OR_ADMISSION_STATE": {
        "gate", "status", "pass", "fail", "failed", "reject", "rejected",
        "blocked", "open", "admission", "admitted", "keep", "stop", "close", "closed"
    },
    "PROVENANCE_IDENTITY_ANCHOR_PARENT": {
        "provenance", "identity", "anchor", "parent", "source", "hash", "commitment"
    },
    "NEGATIVE_RESULT_PRESERVATION": {
        "reject", "rejected", "fail", "failed", "blocked", "negative", "stop",
        "unconfirmed", "unresolved", "open", "not", "established", "preserved"
    },
}

DIRECTION_CANON = {
    "back": "BACK",
    "backward": "BACK",
    "backwards": "BACK",
    "forward": "FORWARD",
    "left": "LEFT",
    "right": "RIGHT",
    "backagain": "BACK_AGAIN",
    "forwardagain": "FORWARD_AGAIN",
}

NEGATIVE_ENUM_TERMS = {
    "REJECT", "REJECTED", "FAIL", "FAILED", "BLOCKED", "NEGATIVE", "STOP",
    "UNCONFIRMED", "UNRESOLVED", "NOT_ESTABLISHED", "OPEN"
}


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git_head(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "NO_GIT_HEAD"


def enumish(value: str) -> bool:
    s = value.strip()
    if not s or len(s) > 180 or "http://" in s.lower() or "https://" in s.lower():
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(c.isupper() for c in letters) / len(letters)
    return upper_ratio >= 0.55 or "_" in s or "->" in s or "→" in s


def words(value: str) -> set[str]:
    # Split camel-ish/underscore/hyphen status strings into normalized ASCII words.
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    s = s.replace("_", " ").replace("-", " ").replace("/", " ").replace("→", " ").replace("->", " ")
    return {w.lower() for w in WORD_RE.findall(s)}


def pointer(parts: list[str]) -> str:
    if not parts:
        return "/"
    return "/" + "/".join(p.replace("~", "~0").replace("/", "~1") for p in parts)


def flatten(obj: Any, parts: list[str] | None = None, depth: int = 0) -> Iterable[tuple[list[str], Any]]:
    parts = [] if parts is None else parts
    yield parts, obj
    if depth > 36:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from flatten(v, parts + [str(k)], depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from flatten(v, parts + [str(i)], depth + 1)


def ignored_path(parts: list[str]) -> bool:
    return any((not p.isdigit()) and p.lower() in IGNORED_KEYS for p in parts[-3:])


def add_evidence(evidence: dict[str, list[dict[str, str]]], family: str, ptr: str, kind: str, token: str) -> None:
    rows = evidence[family]
    key = (ptr, kind, token)
    if len(rows) >= 24:
        return
    if any((r["pointer"], r["kind"], r["token"]) == key for r in rows):
        return
    rows.append({"pointer": ptr, "kind": kind, "token": token})


def family_hits(token_set: set[str]) -> dict[str, set[str]]:
    return {family: token_set & terms for family, terms in FAMILY_TERMS.items() if token_set & terms}


def direction_token(value: str) -> str | None:
    compact = re.sub(r"[^A-Za-z]", "", value).lower()
    if compact in DIRECTION_CANON:
        return DIRECTION_CANON[compact]
    ws = words(value)
    if ws == {"back"}:
        return "BACK"
    if ws == {"forward"}:
        return "FORWARD"
    if ws == {"left"}:
        return "LEFT"
    if ws == {"right"}:
        return "RIGHT"
    if "back" in ws and "again" in ws:
        return "BACK_AGAIN"
    if "forward" in ws and "again" in ws:
        return "FORWARD_AGAIN"
    return None


def explicit_direction_arrays(obj: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for parts, value in flatten(obj):
        if not isinstance(value, list) or not 2 <= len(value) <= 20:
            continue
        if not all(isinstance(x, str) and len(x) <= 80 for x in value):
            continue
        seq = [direction_token(x) for x in value]
        seq = [x for x in seq if x]
        if len(seq) >= 2 and len(seq) >= max(2, len(value) // 2):
            out.append({"pointer": pointer(parts), "sequence": seq})
            if len(out) >= 12:
                break
    return out


def detect_negative_states(obj: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for parts, value in flatten(obj):
        if ignored_path(parts):
            continue
        if not isinstance(value, str) or not enumish(value):
            continue
        upper = value.upper().replace("-", "_").replace(" ", "_")
        if any(term in upper for term in NEGATIVE_ENUM_TERMS):
            out.append({"pointer": pointer(parts), "value": value[:180]})
            if len(out) >= 20:
                break
    return out


def phase1_features(obj: Any) -> dict[str, Any]:
    evidence: dict[str, list[dict[str, str]]] = {k: [] for k in FAMILY_TERMS}

    for parts, value in flatten(obj):
        if not parts or ignored_path(parts):
            continue
        ptr = pointer(parts)
        leaf = parts[-1]
        if not leaf.isdigit() and leaf.lower() not in IGNORED_KEYS:
            hit = family_hits(words(leaf))
            for family, tokens in hit.items():
                for token in sorted(tokens):
                    add_evidence(evidence, family, ptr, "key", token)

        if isinstance(value, str) and enumish(value):
            hit = family_hits(words(value))
            for family, tokens in hit.items():
                for token in sorted(tokens):
                    add_evidence(evidence, family, ptr, "enum_value", token)

    direction_arrays = explicit_direction_arrays(obj)
    for row in direction_arrays:
        for token in row["sequence"]:
            add_evidence(
                evidence,
                "DIRECTIONAL_BACK_FORWARD_LEFT_RIGHT",
                row["pointer"],
                "direction_array",
                token,
            )
            if token.startswith("BACK"):
                add_evidence(evidence, "REVERSE_OR_INVERSE", row["pointer"], "direction_array", token)
            if token.startswith("FORWARD"):
                add_evidence(evidence, "FORWARD_OR_REPLAY", row["pointer"], "direction_array", token)
            if token.endswith("AGAIN"):
                add_evidence(evidence, "REPEAT_OR_AGAIN", row["pointer"], "direction_array", token)

    present = {family: bool(rows) for family, rows in evidence.items()}
    directions = [d for row in direction_arrays for d in row["sequence"]]
    direction_set = set(directions)

    paired_reverse_forward = present["REVERSE_OR_INVERSE"] and present["FORWARD_OR_REPLAY"]
    has_back_and_forward = "BACK" in direction_set and "FORWARD" in direction_set
    has_again = "BACK_AGAIN" in direction_set or "FORWARD_AGAIN" in direction_set
    repeated_base_direction = any(directions.count(x) >= 2 for x in ("BACK", "FORWARD", "LEFT", "RIGHT"))

    mirror_gate = bool(
        present["MIRROR_OR_SYMMETRY"]
        and (paired_reverse_forward or has_back_and_forward)
    )
    backforth_gate = bool(
        (has_back_and_forward and (has_again or repeated_base_direction))
        or (
            paired_reverse_forward
            and present["EXACTNESS_OR_WITNESS"]
            and present["RETURN_ROLLBACK_RECOVERY_REASSEMBLY"]
        )
    )

    reverse_signal = present["REVERSE_OR_INVERSE"] or has_back_and_forward
    strong = bool(
        paired_reverse_forward
        and present["EXACTNESS_OR_WITNESS"]
        and present["GATE_OR_ADMISSION_STATE"]
        and present["PROVENANCE_IDENTITY_ANCHOR_PARENT"]
        and (present["RETURN_ROLLBACK_RECOVERY_REASSEMBLY"] or bool(direction_arrays))
    )

    if not reverse_signal:
        structural_status = "NOT_APPLICABLE_NO_REVERSE_STRUCTURE"
    elif strong and (mirror_gate or backforth_gate):
        structural_status = "STRONG_REVERSE_STRUCTURE"
    elif backforth_gate:
        structural_status = "BACKFORTH_CANDIDATE"
    elif mirror_gate:
        structural_status = "MIRROR_CANDIDATE"
    elif paired_reverse_forward or present["RETURN_ROLLBACK_RECOVERY_REASSEMBLY"] or bool(direction_arrays):
        structural_status = "REVERSE_CANDIDATE"
    else:
        structural_status = "OBSERVATION_REVERSE_SIGNAL_ONLY"

    active_families = sorted(f for f, yes in present.items() if yes)
    direction_profile = sorted(direction_set)
    signature_payload = {
        "families": active_families,
        "direction_profile": direction_profile,
        "structural_status": structural_status,
    }
    signature = hashlib.sha256(
        json.dumps(signature_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]

    return {
        "operator_families_present": active_families,
        "evidence": {k: v for k, v in evidence.items() if v},
        "direction_arrays": direction_arrays,
        "direction_profile": direction_profile,
        "paired_reverse_forward": paired_reverse_forward,
        "mirror_gate": mirror_gate,
        "backforth_gate": backforth_gate,
        "structural_status": structural_status,
        "semantic_status": "UNCONFIRMED",
        "pattern_signature": signature,
        "negative_source_states": detect_negative_states(obj),
    }


def broad_bucket(rel_path: str) -> str:
    parts = Path(rel_path).parts
    if not parts:
        return "root"
    if parts[0] == "registry" and len(parts) > 1:
        return f"registry:{parts[1]}"
    if parts[0] == "security_research" and len(parts) > 1:
        return f"security_research:{parts[1]}"
    return parts[0]


def is_self_referential_control(rel_path: str, obj: Any) -> bool:
    # This uses path/metadata only to REDUCE independence weight; never as positive evidence.
    up = rel_path.upper()
    if "REVERSE-PATTERN-BLIND-SEQUENTIAL" in up:
        return True
    if isinstance(obj, dict):
        au = str(obj.get("artifact_uuid", "")).upper()
        if "REVERSE-PATTERN-BLIND-SEQUENTIAL" in au:
            return True
    return False


def queue_key(snapshot_commit: str, raw_sha: str, rel_path: str) -> tuple[str, str]:
    primary = hashlib.sha256((snapshot_commit + "\0" + raw_sha).encode("ascii", "strict")).hexdigest()
    # Only exact raw duplicates reach the tie breaker. Path hash changes order but cannot create support.
    tie = hashlib.sha256(rel_path.encode("utf-8")).hexdigest()
    return primary, tie


def scan_files(root: Path, snapshot_commit: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for p in root.rglob("*.json"):
        if any(part in EPHEMERAL_DIRS for part in p.parts):
            continue
        rel = p.relative_to(root).as_posix()
        raw = p.read_bytes()
        raw_sha = sha256_bytes(raw)
        q1, q2 = queue_key(snapshot_commit, raw_sha, rel)
        candidates.append({"path": rel, "raw": raw, "sha256_raw": raw_sha, "q1": q1, "q2": q2})
    candidates.sort(key=lambda r: (r["q1"], r["q2"]), reverse=True)
    return candidates


def parse_json(raw: bytes) -> tuple[Any | None, str | None]:
    try:
        return json.loads(raw.decode("utf-8-sig")), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {str(exc)[:240]}"


def phase1_receipts(root: Path, snapshot_commit: str) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for index, row in enumerate(scan_files(root, snapshot_commit), start=1):
        obj, error = parse_json(row["raw"])
        alias = "RPT-" + row["sha256_raw"][:12].upper()
        if error is not None:
            decision = {
                "operator_families_present": [],
                "evidence": {},
                "direction_arrays": [],
                "direction_profile": [],
                "paired_reverse_forward": False,
                "mirror_gate": False,
                "backforth_gate": False,
                "structural_status": "INVALID_JSON",
                "semantic_status": "UNCONFIRMED",
                "pattern_signature": None,
                "negative_source_states": [],
            }
            self_control = False
        else:
            decision = phase1_features(obj)
            self_control = is_self_referential_control(row["path"], obj)

        # The path is attached only after decision computation.
        receipts.append({
            "queue_index": index,
            "blind_alias": alias,
            "queue_key": row["q1"],
            "sha256_raw": row["sha256_raw"],
            "bytes": len(row["raw"]),
            "json_valid": error is None,
            "parse_error": error,
            "independent_check": decision,
            "source_path_revealed_after_decision": row["path"],
            "broad_source_bucket_for_phase2_only": broad_bucket(row["path"]),
            "self_referential_control_zero_weight_in_phase2": self_control,
        })
    return receipts


def phase2_aggregate(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for r in receipts:
        sig = r["independent_check"]["pattern_signature"]
        if sig and r["independent_check"]["structural_status"] != "NOT_APPLICABLE_NO_REVERSE_STRUCTURE":
            groups[sig].append(r)

    gate_by_sig: dict[str, dict[str, Any]] = {}
    for sig, rows in groups.items():
        eligible = [r for r in rows if not r["self_referential_control_zero_weight_in_phase2"]]
        # Exact duplicate raw bytes count once.
        by_raw: dict[str, dict[str, Any]] = {}
        for r in eligible:
            by_raw.setdefault(r["sha256_raw"], r)
        unique_rows = list(by_raw.values())
        buckets = collections.Counter(r["broad_source_bucket_for_phase2_only"] for r in unique_rows)
        n = len(unique_rows)
        max_fraction = (max(buckets.values()) / n) if n and buckets else 1.0
        repeat_gate = bool(n >= 3 and len(buckets) >= 2 and max_fraction <= 0.5)
        gate_by_sig[sig] = {
            "unique_nonself_records": n,
            "broad_source_buckets": dict(sorted(buckets.items())),
            "max_fraction_one_bucket": max_fraction,
            "repeat_gate": repeat_gate,
        }

    pattern_counts: collections.Counter[str] = collections.Counter()
    promotion_candidates: list[dict[str, Any]] = []
    for r in receipts:
        d = r["independent_check"]
        sig = d["pattern_signature"]
        repeat_gate = bool(sig and gate_by_sig.get(sig, {}).get("repeat_gate"))
        mirror_gate = bool(d["mirror_gate"])
        backforth_gate = bool(d["backforth_gate"])
        if repeat_gate and (mirror_gate or backforth_gate):
            status = "PATTERN_PROMOTION_CANDIDATE"
        elif repeat_gate:
            status = "REPEAT_CANDIDATE"
        elif mirror_gate:
            status = "MIRROR_CANDIDATE"
        elif backforth_gate:
            status = "BACKFORTH_CANDIDATE"
        elif d["structural_status"] not in {"INVALID_JSON", "NOT_APPLICABLE_NO_REVERSE_STRUCTURE"}:
            status = "OBSERVATION"
        else:
            status = "NO_PATTERN"
        r["phase2"] = {
            "repeat_gate": repeat_gate,
            "mirror_gate": mirror_gate,
            "backforth_gate": backforth_gate,
            "pattern_status": status,
            "semantic_status": "UNCONFIRMED_UNLESS_SEPARATE_SOURCE_GROUNDED_SEMANTIC_TEST_IS_RUN",
        }
        pattern_counts[status] += 1
        if status == "PATTERN_PROMOTION_CANDIDATE":
            promotion_candidates.append({
                "queue_index": r["queue_index"],
                "blind_alias": r["blind_alias"],
                "source_path": r["source_path_revealed_after_decision"],
                "pattern_signature": sig,
                "structural_status": d["structural_status"],
                "mirror_gate": mirror_gate,
                "backforth_gate": backforth_gate,
            })

    signature_rows = []
    for sig, gate in sorted(gate_by_sig.items(), key=lambda kv: (-kv[1]["unique_nonself_records"], kv[0])):
        signature_rows.append({"pattern_signature": sig, **gate})

    return {
        "signature_groups": signature_rows,
        "repeat_gate_signature_count": sum(1 for x in signature_rows if x["repeat_gate"]),
        "pattern_status_counts": dict(sorted(pattern_counts.items())),
        "promotion_candidates": promotion_candidates,
    }


def self_test() -> None:
    no_signal = phase1_features({"temperature": 3, "mode": "NORMAL"})
    assert no_signal["structural_status"] == "NOT_APPLICABLE_NO_REVERSE_STRUCTURE"

    title_only = phase1_features({"title": "REVERSE_FORWARD_MIRROR_BACK_AGAIN"})
    assert title_only["structural_status"] == "NOT_APPLICABLE_NO_REVERSE_STRUCTURE"

    reverse_only = phase1_features({"operator": "EXACT_REVERSE"})
    assert reverse_only["structural_status"] == "OBSERVATION_REVERSE_SIGNAL_ONLY"

    six = phase1_features({
        "operator": "STRICT_REVERSE_REPLAY",
        "direction_sequence": ["BACK", "FORWARD", "LEFT", "RIGHT", "FORWARD_AGAIN", "BACK_AGAIN"],
        "gates": {"direction_order_exact": True, "rollback_pass": True},
        "identity_anchor": "PARENT_COMMITMENT_VERIFIED",
        "rollback": "EXACT_RETURN",
        "negative_result": "REJECT_PRESERVED",
    })
    assert six["backforth_gate"] is True
    assert six["structural_status"] in {"BACKFORTH_CANDIDATE", "STRONG_REVERSE_STRUCTURE"}
    assert six["semantic_status"] == "UNCONFIRMED"
    assert six["negative_source_states"], "negative states must be retained"

    mirror = phase1_features({
        "operator": "BIDIRECTIONAL_REVERSE_FORWARD_MIRROR",
        "proof": "EXACT_WITNESS_VERIFIED",
        "identity_anchor": "SOURCE_PARENT",
        "gate_status": "PASS",
        "recovery": "RETURN_REPLAY",
    })
    assert mirror["mirror_gate"] is True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--out")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        print(json.dumps({"status": "PASS_SELF_TEST", "version": VERSION}))
        if not args.out:
            return

    if not args.out:
        raise SystemExit("--out is required unless --self-test is used alone")

    root = Path(args.repo_root).resolve()
    snapshot_commit = git_head(root)
    receipts = phase1_receipts(root, snapshot_commit)
    phase2 = phase2_aggregate(receipts)

    structural_counts = collections.Counter(r["independent_check"]["structural_status"] for r in receipts)
    valid_count = sum(1 for r in receipts if r["json_valid"])
    queue_digest = hashlib.sha256(
        "\n".join(r["queue_key"] + ":" + r["sha256_raw"] for r in receipts).encode("ascii")
    ).hexdigest()

    result = {
        "schema": "janus.reverse_pattern.blind_sequential_result.v1.0",
        "artifact_uuid": "JANUS-REVERSE-PATTERN-BLIND-SEQUENTIAL-RESULT",
        "status": "CANONICAL_STRUCTURAL_RUN_COMPLETE",
        "executor_version": VERSION,
        "snapshot_commit": snapshot_commit,
        "protocol": "data/JANUS-REVERSE-PATTERN-BLIND-SEQUENTIAL-PROTOCOL-2026-08-19-v1.0.json",
        "execution_contract": {
            "suspect_list_used": False,
            "filename_or_title_used_as_positive_evidence": False,
            "narrative_prose_used_as_positive_evidence": False,
            "cross_record_information_used_during_phase1": False,
            "receipts_frozen_before_phase2": True,
            "queue_order_digest": queue_digest,
        },
        "summary": {
            "json_seen": len(receipts),
            "json_valid": valid_count,
            "json_invalid": len(receipts) - valid_count,
            "structural_status_counts": dict(sorted(structural_counts.items())),
            "repeat_gate_signature_count": phase2["repeat_gate_signature_count"],
            "pattern_status_counts": phase2["pattern_status_counts"],
            "promotion_candidate_count": len(phase2["promotion_candidates"]),
        },
        "phase2_signature_groups": phase2["signature_groups"],
        "promotion_candidates": phase2["promotion_candidates"],
        "receipts": receipts,
        "claim_ceiling": {
            "structural_internal_pattern_test": True,
            "semantic_match_confirmed": False,
            "identity_confirmed": False,
            "causal_relation_confirmed": False,
            "external_replication": False,
            "scientific_law": False,
        },
        "next_gate": "Review only frozen PATTERN_PROMOTION_CANDIDATE receipts with a separate preregistered source-grounded semantic test. Do not reinterpret observations after seeing later records."
    }

    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = sha256_bytes(out.read_bytes())

    print(json.dumps({
        "status": "PASS_REVERSE_PATTERN_BLIND_SEQUENTIAL",
        "snapshot_commit": snapshot_commit,
        "json_seen": len(receipts),
        "json_valid": valid_count,
        "json_invalid": len(receipts) - valid_count,
        "structural_status_counts": dict(sorted(structural_counts.items())),
        "pattern_status_counts": phase2["pattern_status_counts"],
        "repeat_gate_signature_count": phase2["repeat_gate_signature_count"],
        "promotion_candidate_count": len(phase2["promotion_candidates"]),
        "promotion_candidates": phase2["promotion_candidates"][:20],
        "output_sha256": digest,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
