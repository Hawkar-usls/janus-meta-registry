#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import itertools
import json
import math
import os
import random
import re
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "janus.eye.r4.domain_mechanism_decontamination.v1"

FORBIDDEN_PREFIXES = (
    "EYE/",
    "assets/hrain-full-memory/",
)
FORBIDDEN_EXACT = {
    "assets/hrain-registry-index.json",
}
TEXT_EXTENSIONS = {
    ".json", ".md", ".markdown", ".txt", ".py", ".yml", ".yaml", ".toml", ".ini",
    ".cfg", ".csv", ".tsv", ".html", ".htm", ".js", ".ts", ".tsx", ".jsx", ".css",
    ".scss", ".sh", ".ps1", ".xml", ".jsonl", ".ndjson",
}

TARGET = ("PALOMAR", "MUSIC", "GENESIS")

RECORD_KEY_SEGMENTS = {
    "schema", "schema_version", "artifact_id", "artifact_uuid", "artifact_slug",
    "created_at", "created_at_local", "created_date", "timestamp", "timestamp_utc",
    "parents", "parent", "parent_artifact", "parent_artifacts", "provenance", "lineage",
    "repository", "runtime_repository", "source_repository", "source_repo", "commit",
    "commit_sha", "merge_commit_sha", "head_sha", "pr_tested_head_sha", "run_id", "job_id",
    "workflow", "workflow_run_id", "workflow_conclusion", "receipt", "receipts", "digest",
    "sha", "sha1", "sha256", "hash", "integrity", "canonical", "canonical_sha256",
    "claim_ceiling", "evidence_ceiling", "authority", "epistemic_firewall", "seal",
    "next_gate", "verdict", "registry_class",
}
GOVERNANCE_KEY_SEGMENTS = {
    "gate", "gates", "pass", "fail", "open", "blocked", "validation", "admission",
    "promotion", "authority", "firewall", "workflow", "ci", "test", "tests", "timeout",
    "resource_limit", "claim_boundary", "claim_boundaries",
}
RECORD_LINE_SIGNALS = {
    "artifact_id", "schema", "sha256", "commit", "workflow", "run_id", "job_id",
    "parent", "parents", "provenance", "claim_ceiling", "canonical", "receipt",
}
GOVERNANCE_LINE_SIGNALS = {
    "pass", "fail", "open", "blocked", "gate", "authority", "firewall", "validation",
    "preregister", "workflow", "timeout",
}

SUBJECT_OPERATORS: dict[str, dict[str, Any]] = {
    "PARTIAL_OR_SPARSE_INPUT": {
        "phase": "INPUT",
        "signals": (
            "partial", "sparse", "missing", "fragment", "residual", "incomplete", "masked",
            "pixel", "image", "plate", "frame", "signal", "audio", "track", "sample",
            "observation", "world state", "player state", "input",
        ),
        "invariant": "The mechanism begins from an incomplete, sampled, or directly observed subject state.",
    },
    "REFERENCE_OR_CONTEXT_INPUT": {
        "phase": "INPUT",
        "signals": (
            "reference frame", "reference star", "coordinate", "wcs", "baseline", "median",
            "neighborhood", "context", "pitch field", "harmony", "branch", "local pixel scale",
            "control group", "adjacent", "initial state",
        ),
        "invariant": "The subject is interpreted relative to a domain reference or context.",
    },
    "MULTIVIEW_OR_MULTI_CHANNEL_INPUT": {
        "phase": "INPUT",
        "signals": (
            "view", "perspective", "observer", "mirror", "hemisphere", "channel", "camera",
            "multi-eye", "multiview", "modal", "stereo",
        ),
        "invariant": "Multiple subject views or channels constrain one underlying object/state.",
    },
    "RECONSTRUCT_OR_RESTORE_TRANSFORM": {
        "phase": "TRANSFORM",
        "signals": (
            "reconstruct", "reconstruction", "recover", "recovery", "restore", "restoration",
            "repair", "rebuild", "inverse", "inpaint", "fill", "return path",
        ),
        "invariant": "A transformation attempts to restore or reconstruct subject structure.",
    },
    "MAP_OR_TRANSLATE_TRANSFORM": {
        "phase": "TRANSFORM",
        "signals": (
            "mapping", "map", "translate", "translation", "projection", "project", "transform",
            "convert", "bridge", "resolver", "reproject",
        ),
        "invariant": "A subject relation is carried through an explicit transform or representation bridge.",
    },
    "PERTURB_OR_FILTER_TRANSFORM": {
        "phase": "TRANSFORM",
        "signals": (
            "perturb", "intervention", "ablation", "rotate", "rotation", "shift", "filter",
            "compress", "decode", "resample", "convolve", "threshold", "scrape", "purge",
        ),
        "invariant": "The subject is actively altered or filtered to reveal a response.",
    },
    "STATE_EVOLUTION_TRANSFORM": {
        "phase": "TRANSFORM",
        "signals": (
            "severance", "restoration path", "restart", "return", "role change", "seamless transition",
            "evolve", "evolution", "aging", "growth", "landing", "launch", "flow", "rotation",
            "cooling", "condensation",
        ),
        "invariant": "The subject undergoes an actual state evolution rather than a record-status change.",
    },
    "DETECTION_OR_CLASSIFICATION_OUTPUT": {
        "phase": "OUTPUT",
        "signals": (
            "detect", "detection", "identified", "classification", "cluster", "anomaly", "morphology",
            "shape", "pattern", "object", "source detected", "candidate source",
        ),
        "invariant": "The mechanism yields a subject-level detection, class, or structured object.",
    },
    "RECONSTRUCTED_OR_RESTORED_OUTPUT": {
        "phase": "OUTPUT",
        "signals": (
            "reconstructed", "recovered", "restored", "repaired", "rebuilt", "restoration",
            "reconstruction", "returned", "return into", "same branch",
        ),
        "invariant": "The output is a restored/reconstructed subject state.",
    },
    "CONTINUITY_OR_ROLE_OUTPUT": {
        "phase": "OUTPUT",
        "signals": (
            "continuity", "persistent", "persistence", "same player", "same branch", "identity",
            "role change", "without total reset", "observer voice", "preserved life", "legacy",
        ),
        "invariant": "The output preserves continuity or identity while allowing a role/state change.",
    },
    "DIFFERENCE_OR_RESPONSE_OUTPUT": {
        "phase": "OUTPUT",
        "signals": (
            "difference", "residual", "response", "effect", "world change", "change in", "delta",
            "impact", "landing", "yield", "flux", "mass flow", "temperature drop",
        ),
        "invariant": "The output is a measurable subject response or difference.",
    },
}

PHASES = ("INPUT", "TRANSFORM", "OUTPUT")
SUBJECT_SIGNAL_SET = {s.casefold() for cfg in SUBJECT_OPERATORS.values() for s in cfg["signals"]}

RECORD_CONTROL_STAGES = {
    "PROVENANCE_BINDING": (
        "provenance", "parent", "parents", "source", "repository", "commit", "receipt", "run_id",
        "workflow", "sha256", "digest",
    ),
    "STATE_TRANSITION": (
        "status", "pass", "fail", "open", "blocked", "before", "after", "delta", "transition",
        "freeze", "frozen", "next_gate",
    ),
    "IDENTITY_OR_CLAIM_BINDING": (
        "artifact_id", "identity", "claim", "claim_ceiling", "canonical", "hash", "exact",
        "semantic", "allowed_interpretation",
    ),
}

TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_.:+/-]{2,}", re.UNICODE)
GENERIC_TOKENS = {
    "this", "that", "with", "from", "into", "then", "than", "only", "also", "true", "false",
    "null", "data", "json", "janus", "artifact", "status", "schema", "version", "result",
    "results", "source", "commit", "workflow", "sha256", "claim", "gate", "pass", "fail",
    "open", "blocked", "registry", "file", "path", "main", "used", "using",
    "это", "как", "что", "для", "при", "без", "если", "уже", "после", "перед", "только",
}


def load_r2(root: Path):
    path = root / "EYE/r2/eye_r2_novel_bridge_miner.py"
    spec = importlib.util.spec_from_file_location("eye_r2_novel_bridge_miner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("R2_MODULE_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def key_norm(key: Any) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(key).casefold()).strip("_")


def has_segment(path: tuple[str, ...], segments: set[str]) -> bool:
    return any(key_norm(seg) in segments for seg in path)


def scalar_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def flatten_scalars(obj: Any, prefix: tuple[str, ...] = ()) -> Iterable[tuple[str, str]]:
    if isinstance(obj, dict):
        for key in sorted(obj, key=lambda x: str(x)):
            yield from flatten_scalars(obj[key], prefix + (str(key),))
    elif isinstance(obj, list):
        for i, child in enumerate(obj):
            yield from flatten_scalars(child, prefix + (str(i),))
    elif isinstance(obj, (str, int, float, bool)) or obj is None:
        yield ".".join(prefix), scalar_text(obj)


def flatten_partitioned_json(
    obj: Any,
    path: tuple[str, ...] = (),
    subject: list[str] | None = None,
    record: list[str] | None = None,
    governance: list[str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    if subject is None:
        subject, record, governance = [], [], []
    assert record is not None and governance is not None
    if isinstance(obj, dict):
        for key in sorted(obj, key=lambda x: str(x)):
            child = obj[key]
            p = path + (str(key),)
            kn = key_norm(key)
            top_level_record = kn in {"version", "date"} and len(p) == 1
            contextual_status_record = kn == "status" and (
                len(p) == 1
                or any(key_norm(seg) in {"receipt", "execution_receipt", "workflow", "metadata", "integrity"} for seg in path)
            )
            if has_segment(p, RECORD_KEY_SEGMENTS) or top_level_record:
                record.append(kn)
                record.extend(v for _, v in flatten_scalars(child))
                continue
            if has_segment(p, GOVERNANCE_KEY_SEGMENTS) or contextual_status_record:
                governance.append(kn)
                governance.extend(v for _, v in flatten_scalars(child))
                continue
            subject.append(kn)
            flatten_partitioned_json(child, p, subject, record, governance)
    elif isinstance(obj, list):
        for child in obj:
            flatten_partitioned_json(child, path, subject, record, governance)
    elif isinstance(obj, (str, int, float, bool)) or obj is None:
        subject.append(scalar_text(obj))
    return subject, record, governance


def partition_text(text: str) -> tuple[str, str, str]:
    subject_lines: list[str] = []
    record_lines: list[str] = []
    governance_lines: list[str] = []
    for line in text.splitlines():
        low = line.casefold()
        rec_hits = sum(1 for x in RECORD_LINE_SIGNALS if x in low)
        gov_hits = sum(1 for x in GOVERNANCE_LINE_SIGNALS if x in low)
        if rec_hits >= 2:
            record_lines.append(line)
        elif gov_hits >= 2:
            governance_lines.append(line)
        else:
            subject_lines.append(line)
    return "\n".join(subject_lines), "\n".join(record_lines), "\n".join(governance_lines)


def partition_source(path: Path, max_bytes: int) -> tuple[str, str, str, bool, str | None]:
    data = path.read_bytes()[:max_bytes]
    text = data.decode("utf-8", errors="replace")
    if path.suffix.casefold() == ".json":
        try:
            obj = json.loads(text)
        except Exception as exc:
            return "", text, "", False, f"JSON_PARSE:{type(exc).__name__}:{exc}"
        subject, record, governance = flatten_partitioned_json(obj)
        return "\n".join(subject), "\n".join(record), "\n".join(governance), True, None
    s, r, g = partition_text(text)
    return s, r, g, False, None


def signal_hits(text: str, signals: Iterable[str]) -> list[str]:
    low = text.casefold()
    hits: list[str] = []
    for sig in signals:
        s = str(sig).casefold()
        variants = {s, s.replace("-", "_"), s.replace("_", "-")}
        if any(v in low for v in variants):
            hits.append(str(sig))
    return sorted(set(hits))


def operator_profile(subject_text: str, min_signals: int) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, cfg in SUBJECT_OPERATORS.items():
        hits = signal_hits(subject_text, cfg["signals"])
        if len(hits) < min_signals:
            continue
        out[name] = {
            "phase": cfg["phase"],
            "hits": hits,
            "signal_count": len(hits),
            "invariant": cfg["invariant"],
        }
    return out


def record_control_profile(record_text: str, governance_text: str, full_text: str) -> dict[str, Any]:
    rec_stage_hits = {
        stage: signal_hits(record_text, signals)
        for stage, signals in RECORD_CONTROL_STAGES.items()
    }
    stage_coverage = sum(1 for hits in rec_stage_hits.values() if len(hits) >= 2) / len(RECORD_CONTROL_STAGES)
    record_density = min(1.0, sum(len(hits) for hits in rec_stage_hits.values()) / 15.0)
    governance_hits = signal_hits(
        governance_text,
        GOVERNANCE_LINE_SIGNALS | {"authority", "validation", "admission", "preregister", "claim_ceiling"},
    )
    governance_density = min(1.0, len(governance_hits) / 7.0)
    return {
        "record_stage_hits": rec_stage_hits,
        "record_signal": round(0.65 * stage_coverage + 0.35 * record_density, 6),
        "governance_hits": governance_hits,
        "governance_signal": round(governance_density, 6),
    }


def subject_tokens(text: str, limit: int = 180) -> set[str]:
    counter: collections.Counter[str] = collections.Counter()
    for raw in TOKEN_RE.findall(text):
        t = raw.strip("._:+/-").casefold()
        if len(t) < 4 or t in GENERIC_TOKENS or t in SUBJECT_SIGNAL_SET:
            continue
        if re.fullmatch(r"[0-9a-f]{24,}", t) or t.isdigit():
            continue
        counter[t] += 1
    return {t for t, _ in counter.most_common(limit)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    u = a | b
    return len(a & b) / len(u) if u else 0.0


def shuffle_json(obj: Any, rng: random.Random) -> Any:
    if isinstance(obj, dict):
        items = list(obj.items())
        rng.shuffle(items)
        return {k: shuffle_json(v, rng) for k, v in items}
    if isinstance(obj, list):
        return [shuffle_json(v, rng) for v in obj]
    return obj


def shuffle_control(path: Path, baseline_ops: dict[str, dict[str, Any]], rounds: int = 3) -> dict[str, Any]:
    if path.suffix.casefold() != ".json":
        return {"applicable": False, "passes": True, "rounds": 0}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"applicable": True, "passes": False, "rounds": 0, "reason": "JSON_PARSE_FAILED"}
    expected = {k: tuple(v["hits"]) for k, v in baseline_ops.items()}
    for i in range(rounds):
        shuffled = shuffle_json(obj, random.Random(1138 + i))
        s, _, _ = flatten_partitioned_json(shuffled)
        observed = {k: tuple(v["hits"]) for k, v in operator_profile("\n".join(s), 2).items()}
        if observed != expected:
            return {
                "applicable": True,
                "passes": False,
                "rounds": i + 1,
                "reason": "SUBJECT_OPERATOR_PROFILE_CHANGED_AFTER_FIELD_SHUFFLE",
            }
    return {"applicable": True, "passes": True, "rounds": rounds}


def machine_candidates(ops: dict[str, dict[str, Any]]) -> list[tuple[str, str, str]]:
    by_phase: dict[str, list[str]] = {p: [] for p in PHASES}
    for name, meta in ops.items():
        by_phase[meta["phase"]].append(name)
    if any(not by_phase[p] for p in PHASES):
        return []
    return [tuple(combo) for combo in itertools.product(by_phase["INPUT"], by_phase["TRANSFORM"], by_phase["OUTPUT"])]


def machine_subject_signal(machine: tuple[str, str, str], ops: dict[str, dict[str, Any]]) -> float:
    vals = [min(1.0, ops[name]["signal_count"] / 4.0) for name in machine]
    return round(sum(vals) / len(vals), 6)


def deterministic_holdout(docs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_lineage: dict[str, dict[str, Any]] = {}
    for d in sorted(docs, key=lambda x: (-x["subject_signal"], x["path"])):
        by_lineage.setdefault(d["lineage"], d)
    arr = list(by_lineage.values())
    arr.sort(key=lambda d: stable_hash([d["lineage"], d["sha256"], "R4_HOLDOUT"]))
    if len(arr) < 3:
        return arr, []
    return arr[1:], [arr[0]]


def explicit_relation(a: list[dict[str, Any]], b: list[dict[str, Any]], edge_set: set[tuple[str, str]]) -> bool:
    return any(tuple(sorted((x["path"], y["path"]))) in edge_set for x in a for y in b)


def domain_lexical_distance(domain_docs: dict[str, list[dict[str, Any]]]) -> float:
    domains = sorted(domain_docs)
    token_sets = [set().union(*(d["subject_tokens"] for d in domain_docs[domain][:4])) for domain in domains]
    ds: list[float] = []
    for i, j in itertools.combinations(range(len(domains)), 2):
        ds.append(1.0 - jaccard(token_sets[i], token_sets[j]))
    return sum(ds) / len(ds) if ds else 0.0


def compact_support(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": d["path"],
        "sha256": d["sha256"],
        "artifact_id": d.get("artifact_id"),
        "lineage": d["lineage"],
        "subject_signal": d["subject_signal"],
        "record_signal": d["record_signal"],
        "governance_signal": d["governance_signal"],
        "operator_hits": d["operator_hits"],
        "shuffle_control": d["shuffle_control"],
    }


def confidence(score: float, domain_count: int, lexical_distance: float) -> str:
    if domain_count >= 3 and lexical_distance >= 0.70 and score >= 68:
        return "STRONG_DOMAIN_MACHINE_CANDIDATE__VERIFY_REQUIRED"
    if domain_count >= 2 and lexical_distance >= 0.55 and score >= 55:
        return "MEDIUM_DOMAIN_MACHINE_CANDIDATE__VERIFY_REQUIRED"
    return "WEAK_DOMAIN_MACHINE_CANDIDATE__OPEN"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--index", default="EYE/generated/EYE-REGISTRY-INDEX.json")
    ap.add_argument("--output-dir", default="EYE/r4/generated")
    ap.add_argument("--r3-2-audit", default="EYE/r3_2/EYE-R3.2-PALOMAR-MUSIC-GENESIS-SEMANTIC-MECHANISM-AUDIT-2026-09-01-v1.0.json")
    ap.add_argument("--max-read-bytes", type=int, default=1_000_000)
    ap.add_argument("--min-operator-signals", type=int, default=2)
    ap.add_argument("--top-candidates", type=int, default=80)
    ap.add_argument("--top-contamination", type=int, default=120)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    index_path = root / args.index
    index = json.loads(index_path.read_text(encoding="utf-8"))
    r2 = load_r2(root)
    outdir = root / args.output_dir
    outdir.mkdir(parents=True, exist_ok=True)

    derivative_input = [
        r["path"] for r in index.get("records", [])
        if r["path"] in FORBIDDEN_EXACT or any(r["path"].startswith(p) for p in ("assets/hrain-full-memory/",))
    ]
    if derivative_input:
        raise SystemExit("R4_FORBIDDEN_DERIVATIVE_INPUT:" + ",".join(derivative_input[:10]))

    edge_set = r2.explicit_edges(index)
    docs: list[dict[str, Any]] = []
    parse_errors: list[dict[str, str]] = []
    skipped_meta = 0
    recognized_domains: set[str] = set()

    for record in index.get("records", []):
        rel = record["path"]
        if rel in FORBIDDEN_EXACT or any(rel.startswith(p) for p in FORBIDDEN_PREFIXES):
            skipped_meta += 1
            continue
        if record.get("semantic_kind") not in {"JSON", "TEXT"} or record.get("parse_error"):
            continue
        path = root / rel
        if not path.is_file() or path.suffix.casefold() not in TEXT_EXTENSIONS:
            continue
        domain = r2.domain_for(rel, record.get("artifact_id"), record.get("title"))
        if domain == "OTHER":
            continue
        recognized_domains.add(domain)
        try:
            raw = path.read_bytes()[: args.max_read_bytes]
            full_text = raw.decode("utf-8", errors="replace").casefold()
            subject_text, record_text, governance_text, is_json, partition_error = partition_source(path, args.max_read_bytes)
        except OSError as exc:
            parse_errors.append({"path": rel, "error": f"OSError:{exc}"})
            continue
        if partition_error:
            parse_errors.append({"path": rel, "error": partition_error})
            continue
        ops = operator_profile(subject_text, args.min_operator_signals)
        if not ops:
            continue
        machines = machine_candidates(ops)
        if not machines:
            continue
        controls = record_control_profile(record_text, governance_text, full_text)
        shuffle = shuffle_control(path, ops)
        tokens = subject_tokens(subject_text)
        lineage = r2.lineage_key(record)

        for machine in machines:
            subject_signal = machine_subject_signal(machine, ops)
            docs.append({
                "path": rel,
                "sha256": record.get("sha256"),
                "artifact_id": record.get("artifact_id"),
                "domain": domain,
                "lineage": lineage,
                "machine": machine,
                "subject_signal": subject_signal,
                "record_signal": controls["record_signal"],
                "governance_signal": controls["governance_signal"],
                "record_stage_hits": controls["record_stage_hits"],
                "governance_hits": controls["governance_hits"],
                "subject_tokens": tokens,
                "operator_hits": {name: ops[name]["hits"] for name in machine},
                "shuffle_control": shuffle,
                "is_json": is_json,
            })

    grouped: dict[tuple[str, str, str], dict[str, list[dict[str, Any]]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for d in docs:
        grouped[d["machine"]][d["domain"]].append(d)

    candidates: list[dict[str, Any]] = []
    contamination: list[dict[str, Any]] = []
    target_matches: list[dict[str, Any]] = []

    for machine, per_domain_raw in grouped.items():
        eligible_domains: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for domain, arr in per_domain_raw.items():
            discovery, holdout = deterministic_holdout(arr)
            if len(discovery) < 2 or len(holdout) < 1:
                continue
            eligible_domains[domain] = {"discovery": discovery, "holdout": holdout}
        if len(eligible_domains) < 2:
            continue

        domain_docs = {d: x["discovery"] for d, x in eligible_domains.items()}
        lexical_distance = domain_lexical_distance(domain_docs)
        all_disc = [x for v in domain_docs.values() for x in v]
        all_hold = [x for v in eligible_domains.values() for x in v["holdout"]]
        subject_signal = sum(x["subject_signal"] for x in all_disc) / max(1, len(all_disc))
        record_signal = sum(x["record_signal"] for x in all_disc) / max(1, len(all_disc))
        governance_signal = sum(x["governance_signal"] for x in all_disc) / max(1, len(all_disc))
        holdout_subject = min(x["subject_signal"] for x in all_hold) if all_hold else 0.0
        holdout_record_margin = min(
            x["subject_signal"] - max(x["record_signal"], x["governance_signal"])
            for x in all_hold
        ) if all_hold else -1.0
        shuffle_pass = all(x["shuffle_control"]["passes"] for x in all_disc + all_hold)

        explicit_pairs = 0
        domains = sorted(eligible_domains)
        for da, db in itertools.combinations(domains, 2):
            if explicit_relation(domain_docs[da], domain_docs[db], edge_set):
                explicit_pairs += 1

        subject_margin = subject_signal - max(record_signal, governance_signal)
        heldout_pass = holdout_subject >= 0.50 and holdout_record_margin > 0.0
        low_lexical = lexical_distance >= 0.55
        contamination_reason: list[str] = []
        if subject_margin <= 0:
            contamination_reason.append("RECORD_OR_GOVERNANCE_EXPLAINS_DISCOVERY_SUPPORT")
        if not heldout_pass:
            contamination_reason.append("HELDOUT_MISMATCH")
        if not shuffle_pass:
            contamination_reason.append("FIELD_ORDER_ARTIFACT")
        if not low_lexical:
            contamination_reason.append("LEXICAL_OVERLAP_TOO_HIGH")
        if explicit_pairs > 0:
            contamination_reason.append("EXPLICIT_CROSS_REFERENCE_PRESENT")

        support_strength = min(1.0, min(len(v["discovery"]) for v in eligible_domains.values()) / 4.0)
        domain_bonus = min(1.0, len(domains) / 4.0)
        score = (
            28.0
            + 18.0 * subject_signal
            + 16.0 * max(0.0, subject_margin)
            + 16.0 * lexical_distance
            + 10.0 * support_strength
            + 8.0 * domain_bonus
            + (8.0 if heldout_pass else -12.0)
            + (5.0 if shuffle_pass else -14.0)
            - 8.0 * explicit_pairs
        )

        candidate_id = "EYE-R4-MACHINE-" + stable_hash([machine, domains])[:16]
        base = {
            "candidate_id": candidate_id,
            "machine": list(machine),
            "formula": " -> ".join(machine),
            "domains": domains,
            "domain_count": len(domains),
            "score": round(score, 6),
            "confidence_class": confidence(score, len(domains), lexical_distance),
            "subject_signal": round(subject_signal, 6),
            "record_signal": round(record_signal, 6),
            "governance_signal": round(governance_signal, 6),
            "subject_over_record_margin": round(subject_margin, 6),
            "lexical_distance": round(lexical_distance, 6),
            "explicit_pair_count": explicit_pairs,
            "field_order_shuffle_pass": shuffle_pass,
            "heldout_pass": heldout_pass,
            "heldout_min_subject_signal": round(holdout_subject, 6),
            "heldout_min_subject_over_record_margin": round(holdout_record_margin, 6),
            "named_target_bonus": False,
            "representation_invariants": [SUBJECT_OPERATORS[x]["invariant"] for x in machine],
            "discovery_support": {
                d: [compact_support(x) for x in eligible_domains[d]["discovery"][:6]]
                for d in domains
            },
            "heldout_support": {
                d: [compact_support(x) for x in eligible_domains[d]["holdout"]]
                for d in domains
            },
            "falsifier": "Mask record/governance surfaces, shuffle JSON field order, then test a held-out lineage in every domain. Any loss of subject-level input/transform/output support blocks promotion.",
            "verify_next": "Manually map concrete subject input -> transformation -> output in each held-out lineage and test a domain-specific negative control that can say NO.",
            "authority": "CANDIDATE_ONLY__INDEPENDENT_SEMANTIC_MECHANISM_VERIFY_REQUIRED",
        }

        admitted = subject_margin > 0 and heldout_pass and shuffle_pass and low_lexical and explicit_pairs == 0
        if admitted:
            base["verdict"] = "DOMAIN_MACHINE_CANDIDATE__VERIFY_REQUIRED"
            candidates.append(base)
        else:
            base["verdict"] = (
                "FIELD_ORDER_ARTIFACT" if "FIELD_ORDER_ARTIFACT" in contamination_reason
                else "HELDOUT_MISMATCH" if "HELDOUT_MISMATCH" in contamination_reason
                else "RECORD_PROTOCOL_CONTAMINATION" if "RECORD_OR_GOVERNANCE_EXPLAINS_DISCOVERY_SUPPORT" in contamination_reason
                else "OPEN"
            )
            base["contamination_reasons"] = contamination_reason
            contamination.append(base)

        if set(domains) >= set(TARGET):
            target_matches.append({
                "candidate_id": candidate_id,
                "machine": list(machine),
                "formula": " -> ".join(machine),
                "admitted": admitted,
                "verdict": base["verdict"],
                "score": round(score, 6),
                "subject_over_record_margin": round(subject_margin, 6),
                "lexical_distance": round(lexical_distance, 6),
                "heldout_pass": heldout_pass,
                "field_order_shuffle_pass": shuffle_pass,
                "explicit_pair_count": explicit_pairs,
            })

    candidates.sort(key=lambda x: (-x["score"], x["candidate_id"]))
    contamination.sort(key=lambda x: (-x["score"], x["candidate_id"]))
    target_matches.sort(key=lambda x: (-x["score"], x["candidate_id"]))

    audit_path = root / args.r3_2_audit
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    calibration_rows: list[dict[str, Any]] = []
    for item in audit.get("source_audit", []):
        rel = item["path"]
        p = root / rel
        if not p.is_file():
            calibration_rows.append({"path": rel, "classification": "MISSING_SOURCE"})
            continue
        try:
            raw = p.read_bytes()[: args.max_read_bytes]
            full = raw.decode("utf-8", errors="replace").casefold()
            subject_text, record_text, gov_text, _, err = partition_source(p, args.max_read_bytes)
        except OSError as exc:
            calibration_rows.append({"path": rel, "classification": f"READ_ERROR:{exc}"})
            continue
        if err:
            calibration_rows.append({"path": rel, "classification": err})
            continue
        ops = operator_profile(subject_text, args.min_operator_signals)
        controls = record_control_profile(record_text, gov_text, full)
        subj = max([machine_subject_signal(m, ops) for m in machine_candidates(ops)] or [0.0])
        classification = (
            "RECORD_CONTROL_DOMINATES"
            if controls["record_signal"] >= subj or controls["governance_signal"] >= subj
            else "SUBJECT_SIGNAL_DOMINATES"
        )
        calibration_rows.append({
            "path": rel,
            "subject_signal_max": round(subj, 6),
            "record_signal": controls["record_signal"],
            "governance_signal": controls["governance_signal"],
            "classification": classification,
        })

    calibrated = [x for x in calibration_rows if x.get("classification") == "RECORD_CONTROL_DOMINATES"]
    negative_control_pass = len(calibrated) >= math.ceil(0.625 * max(1, len(calibration_rows)))

    candidates_obj = {
        "schema": SCHEMA,
        "artifact_id": "JANUS-EYE-R4-DOMAIN-MACHINE-CANDIDATES",
        "status": "CANDIDATE_MINING_COMPLETE__VERIFY_REQUIRED" if candidates else "OPEN_NO_ADMITTED_DOMAIN_MACHINE_CANDIDATES",
        "source_git_commit": os.environ.get("GITHUB_SHA", "LOCAL_OR_UNKNOWN"),
        "source_index_corpus_digest_sha256": index.get("corpus_root_digest_sha256"),
        "named_target_bonus": False,
        "method": {
            "record_protocol_masked_or_downweighted": True,
            "governance_protocol_masked_or_downweighted": True,
            "field_order_shuffle_control": True,
            "subject_level_input_transform_output_required": True,
            "minimum_discovery_lineages_per_domain": 2,
            "minimum_heldout_lineages_per_domain": 1,
            "cross_domain_only": True,
            "low_lexical_overlap_required": True,
            "explicit_cross_reference_disallowed_for_admission": True,
        },
        "top_candidates": candidates[: args.top_candidates],
        "authority_firewall": [
            "SAME_WORDS != SAME_MACHINE",
            "SAME_RECORD_PROTOCOL != SAME_DOMAIN_MECHANISM",
            "SUBJECT_LEVEL_MATCH != CAUSAL_PROOF",
            "HELDOUT_MATCH != INDEPENDENT_REPLICATION",
            "R4_CANDIDATE != DISCOVERY",
            "UNKNOWN != NEGATIVE",
            "VERIFY_DECIDES",
        ],
    }

    contamination_obj = {
        "schema": "janus.eye.r4.contamination_ledger.v1",
        "artifact_id": "JANUS-EYE-R4-CONTAMINATION-LEDGER",
        "status": "CONTAMINATION_AND_FAILURES_PRESERVED",
        "negative_control": "JANUS CROSS-DOMAIN RECORD COMMIT MACHINE",
        "negative_control_calibration": {
            "status": "PASS" if negative_control_pass else "FAIL_CLOSED",
            "required_fraction": 0.625,
            "rows": calibration_rows,
            "record_control_dominates_count": len(calibrated),
            "total": len(calibration_rows),
        },
        "top_excluded_candidates": contamination[: args.top_contamination],
        "parse_or_read_errors": parse_errors,
        "law": "DOWNGRADE_IS_PROGRESS; RECORD_PROTOCOL_CONTAMINATION_IS_A_RESULT_NOT_A_MISSING_RESULT.",
    }

    target_obj = {
        "schema": "janus.eye.r4.palomar_music_genesis_diagnostic.v1",
        "artifact_id": "JANUS-EYE-R4-PALOMAR-MUSIC-GENESIS-DIAGNOSTIC",
        "status": "DIAGNOSTIC_ONLY__NO_TARGET_BOOST",
        "domains": list(TARGET),
        "named_target_bonus": False,
        "matching_candidates": target_matches[:50],
        "admitted_count": sum(1 for x in target_matches if x["admitted"]),
        "interpretation_rule": "A target match is interesting only if it independently passes the same R4 decontamination, held-out, lexical-distance, explicit-link and shuffle controls as every other domain combination.",
    }

    for obj, filename in (
        (candidates_obj, "EYE-R4-DOMAIN-MACHINE-CANDIDATES.json"),
        (contamination_obj, "EYE-R4-CONTAMINATION-LEDGER.json"),
        (target_obj, "EYE-R4-PALOMAR-MUSIC-GENESIS-DIAGNOSTIC.json"),
    ):
        (outdir / filename).write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    counts = collections.Counter(x["verdict"] for x in contamination)
    receipt = {
        "schema": "janus.eye.r4.receipt.v1",
        "artifact_id": "JANUS-EYE-R4-RECEIPT",
        "status": (
            "FAIL_CLOSED_NEGATIVE_CONTROL_CALIBRATION" if not negative_control_pass
            else "PASS_WITH_DOMAIN_MACHINE_CANDIDATES__VERIFY_REQUIRED" if candidates
            else "PASS_DECONTAMINATION__OPEN_NO_ADMITTED_DOMAIN_MACHINE_CANDIDATES"
        ),
        "source_git_commit": os.environ.get("GITHUB_SHA", "LOCAL_OR_UNKNOWN"),
        "source_index_corpus_digest_sha256": index.get("corpus_root_digest_sha256"),
        "counts": {
            "input_records": len(index.get("records", [])),
            "meta_or_eye_records_skipped": skipped_meta,
            "recognized_domains": len(recognized_domains),
            "document_machine_supports": len(docs),
            "raw_machine_signatures": len(grouped),
            "admitted_domain_machine_candidates": len(candidates),
            "excluded_candidates": len(contamination),
            "target_diagnostic_matches": len(target_matches),
            "target_diagnostic_admitted": sum(1 for x in target_matches if x["admitted"]),
            "parse_or_read_errors": len(parse_errors),
            "negative_control_calibration_record_dominates": len(calibrated),
            "negative_control_calibration_total": len(calibration_rows),
        },
        "excluded_verdict_counts": dict(sorted(counts.items())),
        "negative_control_calibration": "PASS" if negative_control_pass else "FAIL_CLOSED",
        "named_target_bonus": False,
        "generated_outputs": {
            "candidates": "EYE/r4/generated/EYE-R4-DOMAIN-MACHINE-CANDIDATES.json",
            "contamination_ledger": "EYE/r4/generated/EYE-R4-CONTAMINATION-LEDGER.json",
            "target_diagnostic": "EYE/r4/generated/EYE-R4-PALOMAR-MUSIC-GENESIS-DIAGNOSTIC.json",
        },
        "next_gate": "Manually/semantically verify the highest admitted subject-level machines on held-out source lineages with domain-specific controls. If no candidates were admitted, revise only by preregistering a new subject representation; do not weaken controls post hoc.",
        "authority_firewall": [
            "R4_PASS != DISCOVERY",
            "DOMAIN_MACHINE_CANDIDATE != SHARED_PHYSICAL_LAW",
            "NEGATIVE_CONTROL_PASS != MECHANISM_PROOF",
            "BICAMERAL_AGREEMENT != INDEPENDENT_REPLICATION",
            "CONTROL_MUST_HAVE_POWER_TO_SAY_NO",
            "VERIFY_DECIDES",
        ],
        "seal": "REMOVE THE RECORDING MACHINE FROM THE SKY. THEN ASK WHETHER THE WORLD STILL MOVES THE SAME WAY.",
    }
    (outdir / "EYE-R4-RECEIPT.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": receipt["status"],
        "input_records": receipt["counts"]["input_records"],
        "document_machine_supports": receipt["counts"]["document_machine_supports"],
        "raw_machine_signatures": receipt["counts"]["raw_machine_signatures"],
        "admitted": receipt["counts"]["admitted_domain_machine_candidates"],
        "excluded": receipt["counts"]["excluded_candidates"],
        "target_matches": receipt["counts"]["target_diagnostic_matches"],
        "target_admitted": receipt["counts"]["target_diagnostic_admitted"],
        "negative_control_calibration": receipt["negative_control_calibration"],
    }, sort_keys=True))
    return 0 if negative_control_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
