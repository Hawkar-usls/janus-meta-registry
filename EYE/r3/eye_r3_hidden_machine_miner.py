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
from pathlib import Path
from typing import Any

SCHEMA = "janus.eye.r3.hidden_machine_miner.v1"
FORBIDDEN_PREFIXES = (
    "EYE/generated/",
    "EYE/r2/generated/",
    "EYE/r3/generated/",
    "assets/hrain-full-memory/",
)
FORBIDDEN_EXACT = {"assets/hrain-registry-index.json"}
TARGET = ("PALOMAR", "MUSIC", "GENESIS")


def load_r2_module(root: Path):
    path = root / "EYE/r2/eye_r2_novel_bridge_miner.py"
    spec = importlib.util.spec_from_file_location("eye_r2_novel_bridge_miner", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("R2_MODULE_LOAD_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def operator_event(text: str, cfg: dict[str, Any], minimum_signals: int) -> dict[str, Any] | None:
    low = text.casefold()
    hits: list[tuple[int, str]] = []
    for signal in cfg.get("signals", ()):
        s = str(signal).casefold()
        pos = low.find(s)
        if pos >= 0:
            hits.append((pos, str(signal)))
    unique_signals = sorted({sig for _, sig in hits})
    if len(unique_signals) < minimum_signals:
        return None
    earliest = min(pos for pos, _ in hits)
    return {
        "position": earliest,
        "normalized_position": round(earliest / max(1, len(low)), 8),
        "hits": unique_signals,
        "signal_count": len(unique_signals),
    }


def machine_windows(events: list[dict[str, Any]], min_len: int, max_len: int) -> list[tuple[tuple[str, ...], int, int]]:
    out: list[tuple[tuple[str, ...], int, int]] = []
    names = [e["operator"] for e in events]
    n = len(names)
    for length in range(min_len, min(max_len, n) + 1):
        for start in range(0, n - length + 1):
            signature = tuple(names[start : start + length])
            out.append((signature, start, start + length))
    return out


def select_independent(docs: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d in sorted(docs, key=lambda x: (-x["machine_signal_strength"], x["path"])):
        lineage = d["lineage"]
        if lineage in seen:
            continue
        seen.add(lineage)
        chosen.append(d)
        if len(chosen) >= limit:
            break
    return chosen


def token_union(docs: list[dict[str, Any]], limit: int = 4) -> set[str]:
    out: set[str] = set()
    for d in docs[:limit]:
        out.update(d.get("subject_tokens", set()))
    return out


def lineage_set(docs: list[dict[str, Any]]) -> set[str]:
    return {d["lineage"] for d in docs}


def explicit_between(a: list[dict[str, Any]], b: list[dict[str, Any]], edge_set: set[tuple[str, str]]) -> bool:
    return any(tuple(sorted((x["path"], y["path"]))) in edge_set for x in a for y in b)


def confidence(score: float, lexical_distance: float, min_lineages: int, explicit_count: int) -> str:
    if explicit_count == 0 and min_lineages >= 3 and lexical_distance >= 0.72 and score >= 76:
        return "STRONG_HIDDEN_MACHINE_CANDIDATE__VERIFY_REQUIRED"
    if explicit_count == 0 and min_lineages >= 2 and lexical_distance >= 0.58 and score >= 60:
        return "MEDIUM_HIDDEN_MACHINE_CANDIDATE__VERIFY_REQUIRED"
    return "WEAK_HIDDEN_MACHINE_CANDIDATE__OPEN"


def compact_doc(d: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": d["path"],
        "sha256": d["sha256"],
        "artifact_id": d.get("artifact_id"),
        "lineage": d["lineage"],
        "machine_signal_strength": d["machine_signal_strength"],
        "machine_normalized_positions": d["machine_normalized_positions"],
        "operator_hits": d["operator_hits"],
    }


def pair_metrics(
    signature: tuple[str, ...],
    supports: dict[str, list[dict[str, Any]]],
    da: str,
    db: str,
    edge_set: set[tuple[str, str]],
    machine_domain_count: int,
    total_domains: int,
    operator_domain_counts: dict[str, int],
) -> dict[str, Any]:
    a = supports[da]
    b = supports[db]
    ta, tb = token_union(a), token_union(b)
    lexical_overlap = jaccard(ta, tb)
    lexical_distance = 1.0 - lexical_overlap
    lineage_overlap = jaccard(lineage_set(a), lineage_set(b))
    explicit = explicit_between(a, b, edge_set)
    min_lineages = min(len(a), len(b))
    machine_rarity = 1.0 - (machine_domain_count / max(1, total_domains))
    avg_ubiquity = sum(operator_domain_counts.get(op, total_domains) / max(1, total_domains) for op in signature) / len(signature)
    operator_specificity = 1.0 - avg_ubiquity
    support_strength = min(1.0, min_lineages / 4.0)
    score = (
        20.0
        + 20.0 * lexical_distance
        + 15.0 * operator_specificity
        + 15.0 * machine_rarity
        + 12.0 * support_strength
        + 4.0 * len(signature)
        - 18.0 * lineage_overlap
        - (22.0 if explicit else 0.0)
    )
    return {
        "score": round(score, 6),
        "lexical_overlap": round(lexical_overlap, 6),
        "lexical_distance": round(lexical_distance, 6),
        "lineage_overlap": round(lineage_overlap, 6),
        "already_explicit_relation_detected": explicit,
        "explicit_count": 1 if explicit else 0,
        "machine_domain_rarity": round(machine_rarity, 6),
        "operator_specificity": round(operator_specificity, 6),
        "minimum_independent_lineages": min_lineages,
    }


def triple_metrics(
    signature: tuple[str, ...],
    supports: dict[str, list[dict[str, Any]]],
    tri: tuple[str, str, str],
    edge_set: set[tuple[str, str]],
    machine_domain_count: int,
    total_domains: int,
    operator_domain_counts: dict[str, int],
) -> dict[str, Any]:
    token_sets = [token_union(supports[d]) for d in tri]
    lineage_sets = [lineage_set(supports[d]) for d in tri]
    lexical_distances: list[float] = []
    lineage_overlaps: list[float] = []
    explicit_pairs = 0
    for i, j in ((0, 1), (0, 2), (1, 2)):
        lexical_distances.append(1.0 - jaccard(token_sets[i], token_sets[j]))
        lineage_overlaps.append(jaccard(lineage_sets[i], lineage_sets[j]))
        if explicit_between(supports[tri[i]], supports[tri[j]], edge_set):
            explicit_pairs += 1
    lexical_distance = sum(lexical_distances) / 3.0
    lineage_overlap = sum(lineage_overlaps) / 3.0
    min_lineages = min(len(supports[d]) for d in tri)
    machine_rarity = 1.0 - (machine_domain_count / max(1, total_domains))
    avg_ubiquity = sum(operator_domain_counts.get(op, total_domains) / max(1, total_domains) for op in signature) / len(signature)
    operator_specificity = 1.0 - avg_ubiquity
    support_strength = min(1.0, min_lineages / 4.0)
    score = (
        24.0
        + 22.0 * lexical_distance
        + 15.0 * operator_specificity
        + 15.0 * machine_rarity
        + 12.0 * support_strength
        + 4.0 * len(signature)
        - 15.0 * lineage_overlap
        - 10.0 * explicit_pairs
    )
    return {
        "score": round(score, 6),
        "lexical_distance": round(lexical_distance, 6),
        "average_lineage_overlap": round(lineage_overlap, 6),
        "explicit_pair_count": explicit_pairs,
        "explicit_count": explicit_pairs,
        "machine_domain_rarity": round(machine_rarity, 6),
        "operator_specificity": round(operator_specificity, 6),
        "minimum_independent_lineages": min_lineages,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--index", default="EYE/generated/EYE-REGISTRY-INDEX.json")
    ap.add_argument("--output-dir", default="EYE/r3/generated")
    ap.add_argument("--max-read-bytes", type=int, default=800000)
    ap.add_argument("--min-operator-signals", type=int, default=2)
    ap.add_argument("--min-machine-length", type=int, default=3)
    ap.add_argument("--max-machine-length", type=int, default=5)
    ap.add_argument("--min-lineages-per-domain", type=int, default=2)
    ap.add_argument("--top-pairs", type=int, default=100)
    ap.add_argument("--top-triples", type=int, default=50)
    ap.add_argument("--catalog-limit", type=int, default=1000)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    outdir = root / args.output_dir
    index = json.loads((root / args.index).read_text(encoding="utf-8"))
    r2 = load_r2_module(root)

    forbidden_seen = [
        r["path"]
        for r in index.get("records", [])
        if r["path"] in FORBIDDEN_EXACT or any(r["path"].startswith(p) for p in FORBIDDEN_PREFIXES)
    ]
    if forbidden_seen:
        raise SystemExit("R3_FORBIDDEN_DERIVATIVE_MEMORY_PRESENT:" + ",".join(forbidden_seen[:10]))

    edge_set = r2.explicit_edges(index)
    doc_profiles: list[dict[str, Any]] = []
    semantic_skips = 0
    recognized_domains: set[str] = set()
    operator_domains_raw: dict[str, set[str]] = collections.defaultdict(set)

    for record in index.get("records", []):
        if record.get("semantic_kind") not in {"JSON", "TEXT"} or record.get("parse_error"):
            semantic_skips += 1
            continue
        rel = record["path"]
        text = r2.safe_text(root, rel, args.max_read_bytes)
        if not text:
            continue
        domain = r2.domain_for(rel, record.get("artifact_id"), record.get("title"))
        if domain == "OTHER":
            continue
        recognized_domains.add(domain)
        events: list[dict[str, Any]] = []
        for op_name, cfg in r2.OPERATORS.items():
            ev = operator_event(text, cfg, args.min_operator_signals)
            if ev is None:
                continue
            events.append({"operator": op_name, **ev})
            operator_domains_raw[op_name].add(domain)
        events.sort(key=lambda e: (e["position"], e["operator"]))
        if len(events) < args.min_machine_length:
            continue
        doc_profiles.append({
            "path": rel,
            "sha256": record.get("sha256"),
            "artifact_id": record.get("artifact_id"),
            "title": record.get("title"),
            "domain": domain,
            "lineage": r2.lineage_key(record),
            "subject_tokens": r2.subject_tokens(text, rel),
            "events": events,
        })

    machine_support_raw: dict[tuple[str, ...], dict[str, list[dict[str, Any]]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    machine_window_supports = 0
    for doc in doc_profiles:
        seen_in_doc: set[tuple[str, ...]] = set()
        for signature, start, end in machine_windows(doc["events"], args.min_machine_length, args.max_machine_length):
            if signature in seen_in_doc:
                continue
            seen_in_doc.add(signature)
            segment = doc["events"][start:end]
            machine_signal_strength = sum(e["signal_count"] for e in segment)
            machine_support_raw[signature][doc["domain"]].append({
                "path": doc["path"],
                "sha256": doc["sha256"],
                "artifact_id": doc.get("artifact_id"),
                "lineage": doc["lineage"],
                "subject_tokens": doc["subject_tokens"],
                "machine_signal_strength": machine_signal_strength,
                "machine_normalized_positions": [e["normalized_position"] for e in segment],
                "operator_hits": {e["operator"]: e["hits"] for e in segment},
            })
            machine_window_supports += 1

    eligible: dict[tuple[str, ...], dict[str, list[dict[str, Any]]]] = {}
    for signature, per_domain in machine_support_raw.items():
        kept: dict[str, list[dict[str, Any]]] = {}
        for domain, docs in per_domain.items():
            support = select_independent(docs)
            if len(support) >= args.min_lineages_per_domain:
                kept[domain] = support
        if len(kept) >= 2:
            eligible[signature] = kept

    total_domains = max(1, len(recognized_domains))
    operator_domain_counts = {op: len(domains) for op, domains in operator_domains_raw.items()}

    pairs: list[dict[str, Any]] = []
    triples: list[dict[str, Any]] = []
    catalog: list[dict[str, Any]] = []
    target_matches: list[dict[str, Any]] = []

    for signature, supports in eligible.items():
        domains = sorted(supports)
        invariants = [r2.OPERATORS[op]["invariant"] for op in signature]
        formula_machine = " -> ".join(signature)
        machine_id = "EYE-R3-MACHINE-" + stable_hash(signature)[:16]
        avg_ubiquity = sum(operator_domain_counts.get(op, total_domains) / total_domains for op in signature) / len(signature)
        catalog.append({
            "machine_id": machine_id,
            "machine": list(signature),
            "formula": formula_machine,
            "machine_length": len(signature),
            "eligible_domain_count": len(domains),
            "domains": domains,
            "operator_specificity": round(1.0 - avg_ubiquity, 6),
            "representation_invariants": invariants,
            "status": "REPEATED_ORDERED_MACHINE__NOT_DISCOVERY",
        })

        for da, db in itertools.combinations(domains, 2):
            metrics = pair_metrics(signature, supports, da, db, edge_set, len(domains), total_domains, operator_domain_counts)
            candidate = {
                "candidate_id": "EYE-R3-PAIR-" + stable_hash([signature, da, db])[:16],
                "candidate_type": "CROSS_DOMAIN_HIDDEN_MACHINE",
                "machine_id": machine_id,
                "machine": list(signature),
                "formula": f"{da} --[{formula_machine}]--> {db}",
                "domains": [da, db],
                "score": metrics["score"],
                "confidence_class": confidence(metrics["score"], metrics["lexical_distance"], metrics["minimum_independent_lineages"], metrics["explicit_count"]),
                "lexical_overlap": metrics["lexical_overlap"],
                "lexical_distance": metrics["lexical_distance"],
                "lineage_overlap": metrics["lineage_overlap"],
                "machine_domain_rarity": metrics["machine_domain_rarity"],
                "operator_specificity": metrics["operator_specificity"],
                "already_explicit_relation_detected": metrics["already_explicit_relation_detected"],
                "independent_lineage_support": {da: len(supports[da]), db: len(supports[db])},
                "provenance": {da: [compact_doc(d) for d in supports[da]], db: [compact_doc(d) for d in supports[db]]},
                "representation_invariants": invariants,
                "why": "The same ordered operator machine appears in both domains despite penalized surface vocabulary overlap and lineage reuse.",
                "counterexample": "The sequence is caused by shared JSON/workflow template order or generic JANUS governance boilerplate rather than the same operational mechanism.",
                "falsifier": "On held-out/manual verification, the claimed operator order or input-state-output semantics fail to align in either domain, or matched controls recover the same score without the mechanism.",
                "verify_next": "Freeze the candidate; manually map input, state transition, output and verifier for each supporting lineage; then compare against lexically similar reordered negative controls.",
                "authority": "CANDIDATE_ONLY__INDEPENDENT_VERIFY_REQUIRED",
            }
            pairs.append(candidate)

        if len(domains) >= 3:
            for tri in itertools.combinations(domains, 3):
                metrics = triple_metrics(signature, supports, tri, edge_set, len(domains), total_domains, operator_domain_counts)
                candidate = {
                    "candidate_id": "EYE-R3-TRIPLE-" + stable_hash([signature, *tri])[:16],
                    "candidate_type": "THREE_DOMAIN_HIDDEN_MACHINE_CONSTELLATION",
                    "machine_id": machine_id,
                    "machine": list(signature),
                    "formula": f"{tri[0]} <--> {tri[1]} <--> {tri[2]} via {formula_machine}",
                    "domains": list(tri),
                    "score": metrics["score"],
                    "confidence_class": confidence(metrics["score"], metrics["lexical_distance"], metrics["minimum_independent_lineages"], metrics["explicit_count"]),
                    "lexical_distance": metrics["lexical_distance"],
                    "average_lineage_overlap": metrics["average_lineage_overlap"],
                    "explicit_pair_count": metrics["explicit_pair_count"],
                    "machine_domain_rarity": metrics["machine_domain_rarity"],
                    "operator_specificity": metrics["operator_specificity"],
                    "independent_lineage_support": {d: len(supports[d]) for d in tri},
                    "provenance": {d: [compact_doc(x) for x in supports[d]] for d in tri},
                    "representation_invariants": invariants,
                    "why": "Three distant domains independently instantiate the same ordered operator machine while lexical and lineage overlap are penalized.",
                    "counterexample": "A shared authoring template, generic governance skeleton, or ubiquitous operator ordering explains the apparent constellation.",
                    "falsifier": "Held-out/manual sequence verification fails in one domain, or shuffled/reordered controls score equivalently.",
                    "verify_next": "Freeze the three-domain candidate and run explicit sequence-order controls plus manual input/state/output mapping in at least two independent lineages per domain.",
                    "authority": "CANDIDATE_ONLY__INDEPENDENT_VERIFY_REQUIRED",
                }
                triples.append(candidate)
                if set(tri) == set(TARGET):
                    target_matches.append(candidate)

    pairs.sort(key=lambda c: (-c["score"], c["candidate_id"]))
    triples.sort(key=lambda c: (-c["score"], c["candidate_id"]))
    target_matches.sort(key=lambda c: (-c["score"], c["candidate_id"]))
    catalog.sort(key=lambda c: (c["eligible_domain_count"], -c["machine_length"], -c["operator_specificity"], c["machine_id"]))

    novel_pairs = [c for c in pairs if not c["already_explicit_relation_detected"]][: args.top_pairs]
    novel_triples = [c for c in triples if c["explicit_pair_count"] == 0][: args.top_triples]
    target_status = "CANDIDATE_FOUND__VERIFY_REQUIRED" if target_matches else "NOT_FOUND_UNDER_FROZEN_R3_RULES"

    candidate_obj = {
        "schema": SCHEMA,
        "artifact_id": "JANUS-EYE-R3-HIDDEN-MACHINE-CANDIDATES",
        "status": "CANDIDATE_MINING_COMPLETE__VERIFY_REQUIRED" if novel_pairs else "OPEN_NO_HIDDEN_MACHINE_CANDIDATES",
        "source_git_commit": os.environ.get("GITHUB_SHA", "LOCAL_OR_UNKNOWN"),
        "source_index_corpus_digest_sha256": index.get("corpus_root_digest_sha256"),
        "method": {
            "raw_word_frequency_used_as_terminal_signal": False,
            "operator_order_required": True,
            "minimum_machine_length": args.min_machine_length,
            "maximum_machine_length": args.max_machine_length,
            "minimum_unique_lineages_per_domain": args.min_lineages_per_domain,
            "lexical_overlap_penalized": True,
            "lineage_overlap_penalized": True,
            "ubiquitous_operator_usage_penalized": True,
            "explicit_relation_penalized": True,
            "named_target_bonus": False,
            "same_lineage_repetition_counts_as_independent": False,
        },
        "top_pair_candidates": novel_pairs,
        "top_triple_candidates": novel_triples,
        "target_hunt": {
            "domains": list(TARGET),
            "status": target_status,
            "named_target_bonus": False,
            "matching_machine_count": len(target_matches),
            "top_matching_machines": target_matches[:20],
        },
        "authority_firewall": [
            "MACHINE_MATCH != DISCOVERY",
            "ASSOCIATION != EVIDENCE",
            "BRIDGE != PROOF",
            "R3_SCORE != TRUTH",
            "BICAMERAL_AGREEMENT != INDEPENDENT_REPLICATION",
            "COMMON_OPERATOR != NOVEL_MACHINE",
            "UNKNOWN != NEGATIVE",
            "VERIFY_DECIDES",
        ],
    }

    catalog_obj = {
        "schema": "janus.eye.r3.machine_catalog.v1",
        "artifact_id": "JANUS-EYE-R3-MACHINE-CATALOG",
        "status": "DESCRIPTIVE_ORDERED_MACHINE_MAP__NOT_DISCOVERY",
        "source_git_commit": os.environ.get("GITHUB_SHA", "LOCAL_OR_UNKNOWN"),
        "source_index_corpus_digest_sha256": index.get("corpus_root_digest_sha256"),
        "recognized_domains": sorted(recognized_domains),
        "operator_domain_counts": dict(sorted(operator_domain_counts.items())),
        "eligible_machine_count": len(eligible),
        "machines": catalog[: args.catalog_limit],
    }

    target_obj = {
        "schema": "janus.eye.r3.target_constellation.v1",
        "artifact_id": "JANUS-EYE-R3-PALOMAR-MUSIC-GENESIS-CONSTELLATION",
        "status": target_status,
        "domains": list(TARGET),
        "named_target_bonus": False,
        "candidate_count": len(target_matches),
        "candidates": target_matches[:50],
        "claim_ceiling": "CANDIDATE_ONLY__INDEPENDENT_VERIFY_REQUIRED",
        "falsifier": "The ordered machine does not survive manual/held-out sequence verification or matched reordered controls.",
    }

    outdir.mkdir(parents=True, exist_ok=True)
    cand_path = outdir / "EYE-R3-HIDDEN-MACHINE-CANDIDATES.json"
    catalog_path = outdir / "EYE-R3-MACHINE-CATALOG.json"
    target_path = outdir / "EYE-R3-PALOMAR-MUSIC-GENESIS-CONSTELLATION.json"
    cand_path.write_text(json.dumps(candidate_obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    catalog_path.write_text(json.dumps(catalog_obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    target_path.write_text(json.dumps(target_obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    receipt = {
        "schema": "janus.eye.r3.receipt.v1",
        "artifact_id": "JANUS-EYE-R3-RECEIPT",
        "status": "PASS" if novel_pairs else "OPEN_NO_HIDDEN_MACHINE_CANDIDATES",
        "source_git_commit": os.environ.get("GITHUB_SHA", "LOCAL_OR_UNKNOWN"),
        "source_index_corpus_digest_sha256": index.get("corpus_root_digest_sha256"),
        "counts": {
            "input_records": len(index.get("records", [])),
            "semantic_records_skipped_due_to_kind_or_parse": semantic_skips,
            "recognized_domain_count": len(recognized_domains),
            "document_operator_profiles": len(doc_profiles),
            "machine_window_supports": machine_window_supports,
            "eligible_ordered_machines": len(eligible),
            "all_pair_candidates": len(pairs),
            "all_triple_candidates": len(triples),
            "novel_pairs_emitted": len(novel_pairs),
            "novel_triples_emitted": len(novel_triples),
            "palomar_music_genesis_matching_machines": len(target_matches),
        },
        "gates": {
            "operator_order_required": True,
            "minimum_two_unique_lineages_per_domain": True,
            "derivative_memory_input_absent": True,
            "named_target_not_boosted": True,
            "authority_remains_candidate_only": True,
            "independent_verify_required": True,
        },
        "target_hunt": {
            "domains": list(TARGET),
            "status": target_status,
            "top_candidate_ids": [c["candidate_id"] for c in target_matches[:10]],
        },
        "outputs": {
            cand_path.name: sha256_bytes(cand_path.read_bytes()),
            catalog_path.name: sha256_bytes(catalog_path.read_bytes()),
            target_path.name: sha256_bytes(target_path.read_bytes()),
        },
        "seal": "THE MINER MAY FIND THE SAME MACHINE UNDER DIFFERENT WORDS. ONLY VERIFICATION MAY CALL IT REAL.",
    }
    receipt_path = outdir / "EYE-R3-RECEIPT.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": receipt["status"],
        "eligible_ordered_machines": len(eligible),
        "novel_pairs": len(novel_pairs),
        "novel_triples": len(novel_triples),
        "target_status": target_status,
        "target_matching_machines": len(target_matches),
        "receipt_sha256": sha256_bytes(receipt_path.read_bytes()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
