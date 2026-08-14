#!/usr/bin/env python3
"""Frozen held-out selector for Connection HIDDEN-001/002/003.

Selection is intentionally structural. It does not read narrative prose, titles,
Connection labels, or the curated pattern names when ranking candidates.
Known formulation sources and the entire Connection family are excluded before
ranking. The goal is to freeze a new source-family panel *before* source-level
interpretation of those selected records.

The selector is not itself validation. It creates the held-out panel on which
transport can subsequently succeed or fail.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORMULATION_SOURCES = {
    "data/JANUS-SING-WHEN-YOURE-WINNING-SOURCE-ONTOLOGY-PROTOCOL-AMENDMENT-v1.2.json",
    "data/JANUS-SING-WHEN-YOURE-WINNING-BOUNDARY-LOCALIZED-SCORING-SPEC-v1.0.json",
    "data/JANUS-SING-WHEN-YOURE-WINNING-VISUAL-CONTROL-PILOT-44-v0.1.json",
    "registry/myth_busted/FALLOUT-3-VAULT112A-PUBLIC-DERIVED-POD-ROLE-ANCHOR-HARDENING-v2.4.json",
    "data/JANUS-LINEAR-A-SIGLA-DOCUMENT-IDENTITY-BRIDGE-RESULT-2026-08-14-v0.1.json",
    "data/SCOBY-D1-CHITIN-BIOCOMPOSITE-v1.0.json",
}

DERIVATIVE_NAME_TOKENS = (
    "RECEIPT", "LEDGER", "AUDIT", "STRENGTHENING", "SHA256", "SIDECAR",
    "SEMANTIC", "COMPANION", "CURRENT", "INDEX", "MANIFEST"
)

GATE_KEY = re.compile(r"(?:gate|stage|phase|level|state|status|admission|verdict|decision|require|condition|matrix|sequence|step|transition|eligib|claim_ceiling|evidence)", re.I)
ORDER_KEY = re.compile(r"(?:sequence|stages|phases|steps|levels|gates|ceremony|pipeline|workflow|ladder|chain)", re.I)
AMBIG_STATUS = {"OPEN", "UNKNOWN", "UNRESOLVED", "UNDETERMINED", "NOT_ESTABLISHED", "PENDING", "AMBIGUOUS", "CANDIDATE"}
PASS_STATUS = {"PASS", "COMPLETE", "ESTABLISHED", "ADMITTED", "TRUE", "VALID"}
BLOCK_STATUS = {"FAIL", "BLOCKED", "REJECTED", "FALSE", "NOT_ESTABLISHED", "OPEN"}


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def flatten(obj, parts=None, depth=0):
    parts = [] if parts is None else parts
    yield parts, obj
    if depth > 25:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from flatten(v, parts + [str(k)], depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from flatten(v, parts + [str(i)], depth + 1)


def family_stem(path: str) -> str:
    s = Path(path).stem.upper()
    s = re.sub(r"20\d\d[-_]\d\d[-_]\d\d", "DATE", s)
    s = re.sub(r"[-_]V?\d+(?:[._-]\d+)*.*$", "", s)
    s = re.sub(r"\d+", "#", s)
    return s


def excluded(rel: str) -> tuple[bool, str | None]:
    up = Path(rel).name.upper()
    if rel in FORMULATION_SOURCES:
        return True, "FORMULATION_SOURCE"
    if rel.startswith("registry/connections/") or up.startswith("JANUS-CONNECTION-"):
        return True, "CONNECTION_FAMILY"
    if any(tok in up for tok in DERIVATIVE_NAME_TOKENS):
        return True, "OBVIOUS_DERIVATIVE_OR_SEMANTIC_COMPANION"
    return False, None


def status_token(v):
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if not isinstance(v, str):
        return None
    s = v.strip().upper().replace(" ", "_")
    for t in AMBIG_STATUS | PASS_STATUS | BLOCK_STATUS:
        if s == t or s.startswith(t + "_") or ("_" + t + "_") in ("_" + s + "_"):
            return t
    return None


def features(obj):
    gate_keys = 0
    order_arrays = 0
    ordered_dict_arrays = 0
    status_scalars = 0
    ambiguous_status = 0
    pass_status = 0
    blocked_status = 0
    null_scalars = 0
    boolean_scalars = 0
    scalar_arrays = 0
    dict_arrays = 0
    depth_max = 0
    top_keys = sorted(obj.keys()) if isinstance(obj, dict) else []

    for parts, v in flatten(obj):
        depth_max = max(depth_max, len(parts))
        key = parts[-1] if parts and not parts[-1].isdigit() else ""
        if key and GATE_KEY.search(key):
            gate_keys += 1
        if v is None:
            null_scalars += 1
        elif isinstance(v, bool):
            boolean_scalars += 1
        elif isinstance(v, (str, int, float)):
            st = status_token(v)
            if st:
                status_scalars += 1
                if st in AMBIG_STATUS: ambiguous_status += 1
                if st in PASS_STATUS: pass_status += 1
                if st in BLOCK_STATUS: blocked_status += 1
        elif isinstance(v, list) and 3 <= len(v) <= 12:
            if key and ORDER_KEY.search(key):
                order_arrays += 1
            if all(isinstance(x, (str, int, float, bool, type(None))) for x in v):
                scalar_arrays += 1
            if all(isinstance(x, dict) for x in v):
                dict_arrays += 1
                keysets = [tuple(sorted(x.keys())) for x in v]
                if len(set(keysets)) <= max(2, len(v)//3):
                    ordered_dict_arrays += 1

    # Three separate structural targets, no narrative content.
    ladder_score = (
        min(gate_keys, 16) * 1.0
        + min(order_arrays, 4) * 4.0
        + min(ordered_dict_arrays, 3) * 5.0
        + min(pass_status, 6) * 0.8
        + min(blocked_status, 6) * 1.1
    )
    ambiguity_score = (
        min(ambiguous_status, 8) * 3.0
        + min(null_scalars, 8) * 1.3
        + (2.0 if pass_status and ambiguous_status else 0.0)
    )
    first_break_applicability_score = (
        min(order_arrays, 4) * 5.0
        + min(ordered_dict_arrays, 3) * 4.0
        + (3.0 if pass_status and blocked_status else 0.0)
        + min(status_scalars, 10) * 0.5
    )
    combined = 0.46*ladder_score + 0.26*ambiguity_score + 0.28*first_break_applicability_score
    return {
        "gate_key_count": gate_keys,
        "order_array_count": order_arrays,
        "ordered_dict_array_count": ordered_dict_arrays,
        "status_scalar_count": status_scalars,
        "ambiguous_status_count": ambiguous_status,
        "pass_status_count": pass_status,
        "blocked_status_count": blocked_status,
        "null_scalar_count": null_scalars,
        "boolean_scalar_count": boolean_scalars,
        "scalar_array_count": scalar_arrays,
        "dict_array_count": dict_arrays,
        "max_depth": depth_max,
        "top_level_key_count": len(top_keys),
        "ladder_score": ladder_score,
        "ambiguity_score": ambiguity_score,
        "first_break_applicability_score": first_break_applicability_score,
        "combined_score": combined,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--panel-size", type=int, default=16)
    args = ap.parse_args()

    candidates = []
    excluded_counts = Counter()
    all_json = sorted(p for p in ROOT.rglob("*.json") if ".git" not in p.parts and "out" not in p.parts)
    for p in all_json:
        rel = p.relative_to(ROOT).as_posix()
        ex, reason = excluded(rel)
        if ex:
            excluded_counts[reason] += 1
            continue
        obj = load(p)
        if obj is None:
            excluded_counts["UNPARSEABLE"] += 1
            continue
        f = features(obj)
        if f["combined_score"] <= 0:
            continue
        candidates.append({
            "path": rel,
            "family_stem": family_stem(rel),
            "blob_sha1": subprocess.check_output(["git", "hash-object", rel], cwd=ROOT, text=True).strip(),
            "features": f,
        })

    candidates.sort(key=lambda x: (
        x["features"]["combined_score"],
        x["features"]["ladder_score"],
        x["features"]["ambiguity_score"],
        x["features"]["first_break_applicability_score"],
        x["path"],
    ), reverse=True)

    # One record per normalized family stem; limit dominance of any top directory.
    selected = []
    seen_family = set()
    dir_counts = Counter()
    for c in candidates:
        fam = c["family_stem"]
        topdir = c["path"].split("/")[0]
        if fam in seen_family:
            continue
        if dir_counts[topdir] >= max(4, args.panel_size//2):
            continue
        selected.append(c)
        seen_family.add(fam)
        dir_counts[topdir] += 1
        if len(selected) >= args.panel_size:
            break

    require_n = min(args.panel_size, 8)
    if len(selected) < require_n:
        raise SystemExit(f"INSUFFICIENT_HELDOUT_PANEL {len(selected)} < {require_n}")

    snap = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    out = {
        "schema": "janus.connection.hidden_pattern_heldout_selector.v0.1",
        "artifact_uuid": "JANUS-CONNECTION-HIDDEN-PATTERN-HELDOUT-SELECTION-2026-08-14-V0.1",
        "snapshot_commit": snap,
        "selection_frozen_before_source_interpretation": True,
        "selection_channels": "JSON_STRUCTURE_AND_GENERIC_STATUS_VOCABULARY_ONLY",
        "narrative_prose_used_for_ranking": False,
        "titles_used_for_ranking": False,
        "connection_labels_used_for_ranking": False,
        "known_formulation_sources_excluded": sorted(FORMULATION_SOURCES),
        "excluded_counts": dict(excluded_counts),
        "json_seen": len(all_json),
        "eligible_structural_candidates": len(candidates),
        "panel_size": len(selected),
        "selected": selected,
        "claim_ceiling": "HELDOUT_PANEL_SELECTION_ONLY; no selected record has yet been interpreted as support or contradiction for HIDDEN-001/002/003.",
        "next_gate": "Inspect selected source bodies only after this selection receipt is frozen; classify support, contradiction, or not-applicable using a separately frozen domain-neutral rubric."
    }
    path = Path(args.out); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    raw=path.read_bytes()
    print(json.dumps({
        "status":"PASS_HELDOUT_PANEL_FROZEN",
        "snapshot":snap,
        "json_seen":len(all_json),
        "eligible":len(candidates),
        "panel_size":len(selected),
        "selected_paths":[x["path"] for x in selected],
        "sha256":hashlib.sha256(raw).hexdigest(),
    },ensure_ascii=False))

if __name__ == "__main__":
    main()
