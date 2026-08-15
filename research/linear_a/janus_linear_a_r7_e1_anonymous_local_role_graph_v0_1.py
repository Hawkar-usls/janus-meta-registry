#!/usr/bin/env python3
"""R7-E1 anonymous local-role graph discovery and held-out replication for KU-RO.

The target is already frozen by R7-C3/E0.  This lane does not discover vocabulary and
never uses lexical semantics, numeric magnitude, arithmetic equality, or phonetics as
features.  Physical objects are partitioned before document content is parsed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import janus_linear_a_r7_arithmetic_summary_role_v0_1 as b0
import janus_linear_a_r7_positional_template_roles_v0_1 as c0
import janus_linear_a_r7_region_scoped_object_status_v0_1 as d0

SPEC_ID = "JANUS-LINEAR-A-R7-E1-ANONYMOUS-LOCAL-ROLE-GRAPH-2026-08-15-v0.1"
PARENT_MERGE = "053ced377db1d2d50594f265da3309888ce35193"
CANONICAL_VERSION = "v2.30"
CORPUS_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
TARGET = "KU-RO"
TARGET_TOKEN = "6a2ea59b95fe1b610d20"
REGION = "HT"
SPLIT_SALT = "JANUS-R7-E1-v0.1|"
DISCOVERY_BUCKETS = {0, 1, 2}
HOLDOUT_BUCKETS = {3, 4}
PERMUTATIONS = 10000
HOLDOUT_SEED = 71101

FALSE_CLAIMS = (
    "specific_semantic_function_established",
    "exact_word_meaning_established",
    "translation_established",
    "phonetic_value_established",
    "language_family_established",
    "new_anchor_established",
    "universal_cross_region_function_established",
    "external_replication_established",
    "decipherment_established",
)


class E1Error(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise E1Error(message)


def load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: top level must be object")
    return value


def canonical_sha(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_spec(spec: Mapping[str, Any]) -> Dict[str, Any]:
    require(spec.get("spec_id") == SPEC_ID, "spec id mismatch")
    require(spec.get("stage") == "R7-E1", "stage mismatch")
    require(spec.get("status") == "PREREGISTERED_BEFORE_E1_DISCOVERY_SCORING", "spec status mismatch")
    parent = spec.get("parent", {})
    require(parent.get("merge_commit_sha") == PARENT_MERGE, "parent merge mismatch")
    require(parent.get("canonical_version") == CANONICAL_VERSION, "canonical mismatch")
    require(parent.get("target") == TARGET and parent.get("opaque_target_token") == TARGET_TOKEN, "target binding mismatch")
    require(parent.get("region") == REGION and parent.get("admitted_parent_role") == "ROW-OPENING-LIKE", "parent role mismatch")
    require(parent.get("e0_status") == "MECHANISM_UNRESOLVED_RETAIN_ROW-OPENING-LIKE", "E0 lineage mismatch")
    source = spec.get("source", {})
    require(source.get("frozen_commit") == CORPUS_COMMIT, "corpus commit mismatch")
    split = spec.get("physical_object_split", {})
    require(split.get("discovery_buckets") == [0, 1, 2] and split.get("holdout_buckets") == [3, 4], "split buckets drift")
    require(split.get("split_is_computed_from_filename_object_identity_before_document_content_is_parsed") is True, "pre-parse split required")
    require(split.get("discovery_must_not_parse_holdout_document_content") is True, "discovery firewall missing")
    firewall = spec.get("feature_firewall", {})
    require(firewall and all(v is True for v in firewall.values()), "feature firewall must be all true")
    ds = spec.get("discovery_selection", {})
    expected_discovery = {
        "minimum_exchangeable_target_events": 10,
        "minimum_target_atom_support": 5,
        "minimum_target_atom_prevalence": 0.40,
        "minimum_matched_effect": 0.15,
        "maximum_selected_atoms": 4,
        "maximum_atoms_per_family": 1,
        "minimum_selected_atoms_to_open_holdout": 2,
    }
    for k, v in expected_discovery.items(): require(ds.get(k) == v, f"discovery threshold drift: {k}")
    require(ds.get("manual_atom_addition_forbidden") is True and ds.get("manual_atom_removal_forbidden") is True, "manual selection forbidden")
    h = spec.get("holdout_primary_test", {})
    expected_holdout = {
        "permutations": PERMUTATIONS,
        "seed": HOLDOUT_SEED,
        "alpha": 0.01,
        "minimum_exchangeable_target_events": 8,
        "minimum_documents": 7,
        "minimum_physical_objects": 7,
        "minimum_exchangeable_fraction_of_holdout_target_events": 0.70,
        "minimum_effect_over_matched_null": 0.15,
        "minimum_leave_one_object_out_positive_fraction": 0.85,
        "maximum_single_object_target_support_fraction": 0.25,
        "selected_atom_directional_replication_required_when_holdout_target_support_at_least": 3,
        "selected_atom_minimum_directional_effect": 0.0,
    }
    for k, v in expected_holdout.items(): require(h.get(k) == v, f"holdout threshold drift: {k}")
    ceiling = spec.get("claim_ceiling", {})
    require(ceiling.get("probable_region_scoped_structural_function_parent_retained") is True, "parent retention required")
    require(ceiling.get("anonymous_local_role_profile_may_be_established") is True, "E1 profile claim permission required")
    for key in FALSE_CLAIMS: require(ceiling.get(key) is False, f"claim ceiling violation: {key}")
    return {"stage": "R7-E1", "status": "R7_E1_PREREGISTRATION_VALIDATED", "spec_id": SPEC_ID, "spec_sha256": canonical_sha(spec)}


def object_bucket(object_id: str) -> int:
    digest = hashlib.sha256((SPLIT_SALT + object_id).encode()).hexdigest()
    return int(digest[:8], 16) % 5


def partition_of_object(object_id: str) -> str:
    bucket = object_bucket(object_id)
    if bucket in DISCOVERY_BUCKETS: return "discovery"
    if bucket in HOLDOUT_BUCKETS: return "holdout"
    raise AssertionError(bucket)


def count_bin(n: int) -> str:
    if n <= 0: return "0"
    if n == 1: return "1"
    return "2PLUS"


def position_bin(rank: int, total: int) -> str:
    require(total > 0 and 0 <= rank < total, "invalid row rank")
    bucket = min(2, (3 * rank) // total)
    return ("early", "middle", "late")[bucket]


def load_partition(root: Path, partition: str) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[str, Any]]:
    require(partition in {"discovery", "holdout"}, "invalid partition")
    docs: List[Dict[str, Any]] = []
    reveal: Dict[str, str] = {}
    skipped_other_partition = 0
    opened_files = 0
    failures = 0
    opened_objects = set()
    for path in sorted((root / "items").glob("*.html")):
        stem = path.stem
        if b0.r5.base.region_of(stem) != REGION:
            continue
        oid = d0.object_id(stem)
        if partition_of_object(oid) != partition:
            skipped_other_partition += 1
            continue
        # Content is opened only after filename-derived object partition is accepted.
        opened_files += 1
        opened_objects.add(oid)
        try:
            doc = b0.parse_document(path)
        except Exception:
            doc = None
        if doc is None:
            failures += 1
            continue
        docs.append(doc)
        for token, label in doc["reveal"].items():
            require(token not in reveal or reveal[token] == label, "opaque hash collision")
            reveal[token] = label
    return docs, reveal, {
        "partition": partition,
        "opened_HT_files": opened_files,
        "opened_HT_physical_objects": len(opened_objects),
        "parsed_HT_documents": len(docs),
        "parse_failures_or_empty": failures,
        "HT_files_skipped_before_parse_due_to_other_partition": skipped_other_partition,
    }


def row_layout(doc: Mapping[str, Any]) -> Tuple[Dict[int, List[int]], List[int], Dict[int, int]]:
    rows = c0.row_index_sequences(doc["sequence"])
    order = sorted(rows, key=lambda r: min(rows[r]))
    return rows, order, {row: i for i, row in enumerate(order)}


def row_summary(seq: Sequence[Mapping[str, Any]], indices: Sequence[int], prefix: str) -> set[str]:
    kinds = [seq[i].get("kind") for i in indices]
    nums = sum(k in {"N", "X"} for k in kinds)
    lex = sum(k == "W" for k in kinds)
    has_x = any(k == "X" for k in kinds)
    return {
        f"{prefix}_NUMERIC_COUNT={count_bin(nums)}",
        f"{prefix}_LEXICAL_COUNT={count_bin(lex)}",
        f"{prefix}_HAS_UNCERTAIN_NUMERIC={'YES' if has_x else 'NO'}",
    }


def absent_row_atoms(prefix: str) -> set[str]:
    return {
        f"{prefix}_NUMERIC_COUNT=ABSENT",
        f"{prefix}_LEXICAL_COUNT=ABSENT",
        f"{prefix}_HAS_UNCERTAIN_NUMERIC=ABSENT",
    }


def build_events(docs: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    docmap = {d["doc"]: d for d in docs}
    out: List[Dict[str, Any]] = []
    for obs in c0.role_observations(docs):
        if obs.get("role") != "ROW_FIRST_LEXICAL" or not obs.get("match") or obs.get("region") != REGION:
            continue
        doc = docmap[obs["doc"]]
        seq = doc["sequence"]
        row = obs["meta"]["row"]
        seq_index = None
        for i, item in enumerate(seq):
            if item.get("kind") == "W" and item.get("word_index") == obs["word_index"] and item.get("word") == obs["word"]:
                seq_index = i
                break
        require(seq_index is not None, "row-first event binding failed")
        rows, order, ranks = row_layout(doc)
        rank = ranks[row]
        row_indices = rows[row]
        suffix = [i for i in row_indices if i > seq_index]
        suffix_kinds = [seq[i].get("kind") for i in suffix]
        require(all(k in {"W", "N", "X"} for k in suffix_kinds), "unexpected item kind")
        atoms = {
            f"SELF_NEXT_KIND={suffix_kinds[0] if suffix_kinds else 'END'}",
            f"SELF_SUFFIX_NUMERIC_COUNT={count_bin(sum(k in {'N','X'} for k in suffix_kinds))}",
            f"SELF_SUFFIX_LEXICAL_COUNT={count_bin(sum(k == 'W' for k in suffix_kinds))}",
            f"SELF_END_KIND={suffix_kinds[-1] if suffix_kinds else 'EMPTY'}",
        }
        if rank > 0:
            atoms |= row_summary(seq, rows[order[rank - 1]], "PREV_ROW")
        else:
            atoms |= absent_row_atoms("PREV_ROW")
        if rank + 1 < len(order):
            atoms |= row_summary(seq, rows[order[rank + 1]], "NEXT_ROW")
        else:
            atoms |= absent_row_atoms("NEXT_ROW")
        oid = d0.object_id(doc["doc"])
        out.append({
            "doc": doc["doc"],
            "object_id": oid,
            "partition": partition_of_object(oid),
            "word": obs["word"],
            "is_target": obs["word"] == TARGET_TOKEN,
            "row": row,
            "row_rank": rank,
            "row_count": len(order),
            "position_bin": position_bin(rank, len(order)),
            "atoms": sorted(atoms),
        })
    return out


def atom_family(atom: str) -> str:
    require("=" in atom, "invalid atom")
    return atom.split("=", 1)[0]


def exchangeable(events: Sequence[Mapping[str, Any]]) -> Tuple[List[Mapping[str, Any]], Dict[Tuple[str, str], List[Mapping[str, Any]]]]:
    strata: Dict[Tuple[str, str], List[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        strata[(event["doc"], event["position_bin"])].append(event)
    eligible_strata = {
        key: rows for key, rows in strata.items()
        if any(r["is_target"] for r in rows) and any(not r["is_target"] for r in rows)
    }
    targets = [r for rows in eligible_strata.values() for r in rows if r["is_target"]]
    return targets, eligible_strata


def discovery(spec: Mapping[str, Any], docs: Sequence[Mapping[str, Any]], load_audit: Mapping[str, Any]) -> Dict[str, Any]:
    events = build_events(docs)
    require(all(e["partition"] == "discovery" for e in events), "holdout event entered discovery feature extractor")
    total_targets = [e for e in events if e["is_target"]]
    targets, strata = exchangeable(events)
    all_atoms = sorted({atom for e in events for atom in e["atoms"]})
    metrics = []
    for atom in all_atoms:
        support = sum(atom in t["atoms"] for t in targets)
        prevalence = support / len(targets) if targets else 0.0
        control_expectations = []
        for t in targets:
            controls = [r for r in strata[(t["doc"], t["position_bin"])] if not r["is_target"]]
            require(controls, "exchangeability invariant failed")
            control_expectations.append(sum(atom in c["atoms"] for c in controls) / len(controls))
        matched_control = sum(control_expectations) / len(control_expectations) if control_expectations else 0.0
        effect = prevalence - matched_control
        metrics.append({
            "atom_id": atom,
            "family": atom_family(atom),
            "target_support": support,
            "target_prevalence": prevalence,
            "matched_control_prevalence": matched_control,
            "matched_effect": effect,
        })
    cfg = spec["discovery_selection"]
    candidates = [m for m in metrics if m["target_support"] >= cfg["minimum_target_atom_support"] and m["target_prevalence"] >= cfg["minimum_target_atom_prevalence"] and m["matched_effect"] >= cfg["minimum_matched_effect"]]
    candidates.sort(key=lambda m: (-m["matched_effect"], -m["target_prevalence"], -m["target_support"], m["atom_id"]))
    selected = []
    used_families = Counter()
    for row in candidates:
        if used_families[row["family"]] >= cfg["maximum_atoms_per_family"]:
            continue
        selected.append(row)
        used_families[row["family"]] += 1
        if len(selected) >= cfg["maximum_selected_atoms"]:
            break
    enough_targets = len(targets) >= cfg["minimum_exchangeable_target_events"]
    enough_atoms = len(selected) >= cfg["minimum_selected_atoms_to_open_holdout"]
    status = "E1_DISCOVERY_PROFILE_FROZEN_HOLDOUT_MAY_OPEN" if enough_targets and enough_atoms else "E1_DISCOVERY_PROFILE_NOT_FROZEN_RETAIN_ROW-OPENING-LIKE"
    return {
        "schema_version": "1.0",
        "artifact_uuid": "JANUS-LINEAR-A-R7-E1-ANONYMOUS-ROLE-DISCOVERY-2026-08-15-v0.1",
        "stage": "R7-E1-DISCOVERY",
        "status": status,
        "spec_id": SPEC_ID,
        "spec_sha256": canonical_sha(spec),
        "parent_canonical_version": CANONICAL_VERSION,
        "target_opaque_token": TARGET_TOKEN,
        "region": REGION,
        "partition": "discovery",
        "load_audit": dict(load_audit),
        "total_target_events_in_opened_partition": len(total_targets),
        "exchangeable_target_events": len(targets),
        "exchangeable_documents": len({t["doc"] for t in targets}),
        "exchangeable_physical_objects": len({t["object_id"] for t in targets}),
        "candidate_atom_count_before_family_cap": len(candidates),
        "selected_atoms": selected,
        "selected_atom_ids": [r["atom_id"] for r in selected],
        "all_atom_metrics_for_discovery_audit": metrics,
        "holdout_content_parsed": False,
        "inference_claim_established": False,
        **{key: False for key in FALSE_CLAIMS},
    }


def holdout(spec: Mapping[str, Any], discovery_freeze: Mapping[str, Any], docs: Sequence[Mapping[str, Any]], load_audit: Mapping[str, Any]) -> Dict[str, Any]:
    require(discovery_freeze.get("status") == "E1_DISCOVERY_PROFILE_FROZEN_HOLDOUT_MAY_OPEN", "discovery did not authorize holdout")
    require(discovery_freeze.get("spec_id") == SPEC_ID and discovery_freeze.get("spec_sha256") == canonical_sha(spec), "discovery/spec binding mismatch")
    selected_atoms = discovery_freeze.get("selected_atom_ids")
    require(isinstance(selected_atoms, list) and 2 <= len(selected_atoms) <= 4 and len(set(selected_atoms)) == len(selected_atoms), "invalid frozen atom set")
    selected_metrics = discovery_freeze.get("selected_atoms")
    require([r.get("atom_id") for r in selected_metrics] == selected_atoms, "frozen atom ordering mismatch")

    events = build_events(docs)
    require(all(e["partition"] == "holdout" for e in events), "discovery event entered holdout extractor")
    total_targets = [e for e in events if e["is_target"]]
    targets, strata = exchangeable(events)
    for e in events:
        e["profile_score"] = sum(atom in e["atoms"] for atom in selected_atoms) / len(selected_atoms)
    n_target = len(targets)
    observed = sum(e["profile_score"] for e in targets) / n_target if n_target else 0.0

    # Frozen matched-label permutation within document + row-position strata.
    rng = random.Random(HOLDOUT_SEED)
    target_count_by_stratum = {key: sum(r["is_target"] for r in rows) for key, rows in strata.items()}
    null_total = 0.0
    ge = 0
    for _ in range(PERMUTATIONS):
        chosen = []
        for key, rows in strata.items():
            k = target_count_by_stratum[key]
            require(0 < k < len(rows), "holdout stratum must be exchangeable")
            chosen.extend(rng.sample(rows, k))
        require(len(chosen) == n_target, "target-count drift in holdout permutation")
        score = sum(r["profile_score"] for r in chosen) / n_target if n_target else 0.0
        null_total += score
        ge += int(score >= observed - 1e-15)
    null_mean = null_total / PERMUTATIONS if n_target else 0.0
    effect = observed - null_mean
    raw_p = (1 + ge) / (1 + PERMUTATIONS)

    # Exact permutation expectation per stratum for atom-level directional replication.
    atom_rows = []
    for atom in selected_atoms:
        target_support = sum(atom in t["atoms"] for t in targets)
        target_prev = target_support / n_target if n_target else 0.0
        expected_sum = 0.0
        for key, rows in strata.items():
            k = target_count_by_stratum[key]
            expected_sum += k * (sum(atom in r["atoms"] for r in rows) / len(rows))
        null_prev = expected_sum / n_target if n_target else 0.0
        atom_rows.append({
            "atom_id": atom,
            "holdout_target_support": target_support,
            "holdout_target_prevalence": target_prev,
            "matched_null_prevalence": null_prev,
            "directional_effect": target_prev - null_prev,
        })

    object_counts = Counter(t["object_id"] for t in targets)
    loo_effects = []
    for oid in sorted(object_counts):
        kept_strata = {key: rows for key, rows in strata.items() if all(r["object_id"] != oid for r in rows)}
        kept_targets = [r for rows in kept_strata.values() for r in rows if r["is_target"]]
        if not kept_targets:
            continue
        obs = sum(r["profile_score"] for r in kept_targets) / len(kept_targets)
        expected_sum = 0.0
        for key, rows in kept_strata.items():
            k = sum(r["is_target"] for r in rows)
            expected_sum += k * (sum(r["profile_score"] for r in rows) / len(rows))
        nul = expected_sum / len(kept_targets)
        loo_effects.append(obs - nul)
    positive_fraction = sum(x > 0 for x in loo_effects) / len(loo_effects) if loo_effects else 0.0
    max_object_fraction = max(object_counts.values()) / n_target if n_target and object_counts else 1.0
    exchangeable_fraction = n_target / len(total_targets) if total_targets else 0.0

    cfg = spec["holdout_primary_test"]
    support_pass = n_target >= cfg["minimum_exchangeable_target_events"] and len({t["doc"] for t in targets}) >= cfg["minimum_documents"] and len(object_counts) >= cfg["minimum_physical_objects"] and exchangeable_fraction >= cfg["minimum_exchangeable_fraction_of_holdout_target_events"]
    effect_pass = effect >= cfg["minimum_effect_over_matched_null"]
    p_pass = raw_p <= cfg["alpha"]
    loo_pass = positive_fraction >= cfg["minimum_leave_one_object_out_positive_fraction"]
    concentration_pass = max_object_fraction <= cfg["maximum_single_object_target_support_fraction"]
    directional_failures = [r["atom_id"] for r in atom_rows if r["holdout_target_support"] >= cfg["selected_atom_directional_replication_required_when_holdout_target_support_at_least"] and r["directional_effect"] < cfg["selected_atom_minimum_directional_effect"]]
    directional_pass = not directional_failures
    passed = all((support_pass, effect_pass, p_pass, loo_pass, concentration_pass, directional_pass))
    status = "HELDOUT_ANONYMOUS_LOCAL_ROLE_PROFILE_REPLICATED" if passed else "ANONYMOUS_LOCAL_ROLE_PROFILE_NOT_ESTABLISHED_RETAIN_ROW-OPENING-LIKE"
    return {
        "schema_version": "1.0",
        "artifact_uuid": "JANUS-LINEAR-A-R7-E1-ANONYMOUS-ROLE-HOLDOUT-RESULT-2026-08-15-v0.1",
        "stage": "R7-E1-HOLDOUT",
        "status": status,
        "spec_id": SPEC_ID,
        "spec_sha256": canonical_sha(spec),
        "discovery_freeze_canonical_sha256": canonical_sha(discovery_freeze),
        "target": TARGET,
        "target_opaque_token": TARGET_TOKEN,
        "region": REGION,
        "inherited_role": "ROW-OPENING-LIKE",
        "inherited_role_retained": True,
        "selected_anonymous_atoms": selected_atoms,
        "load_audit": dict(load_audit),
        "total_target_events_in_opened_holdout_partition": len(total_targets),
        "exchangeable_target_events": n_target,
        "exchangeable_fraction": exchangeable_fraction,
        "documents": len({t["doc"] for t in targets}),
        "physical_objects": len(object_counts),
        "observed_profile_score": observed,
        "matched_null_mean": null_mean,
        "effect_over_matched_null": effect,
        "permutation_n": PERMUTATIONS,
        "permutation_ge_observed": ge,
        "raw_empirical_p": raw_p,
        "leave_one_object_out_effects": loo_effects,
        "leave_one_object_out_positive_fraction": positive_fraction,
        "maximum_single_object_target_support_fraction": max_object_fraction,
        "object_target_event_counts": dict(sorted(object_counts.items())),
        "selected_atom_holdout_metrics": atom_rows,
        "selected_atom_directional_failures": directional_failures,
        "support_pass": support_pass,
        "effect_pass": effect_pass,
        "p_pass": p_pass,
        "loo_pass": loo_pass,
        "object_concentration_pass": concentration_pass,
        "selected_atom_directional_replication_pass": directional_pass,
        "anonymous_local_role_profile_established": passed,
        "canonical_auto_promotion_performed": False,
        **{key: False for key in FALSE_CLAIMS},
    }


def emit(value: Mapping[str, Any], path: Path | None) -> None:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path: path.write_text(rendered, encoding="utf-8")
    else: sys.stdout.write(rendered)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, type=Path)
    ap.add_argument("--validate-spec", action="store_true")
    ap.add_argument("--mode", choices=("discovery", "holdout"))
    ap.add_argument("--corpus", type=Path)
    ap.add_argument("--discovery-freeze", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    require(args.validate_spec ^ bool(args.mode), "choose validate-spec xor mode")
    if args.mode:
        require(args.corpus is not None and args.out is not None, "mode requires corpus and out")
    if args.mode == "holdout": require(args.discovery_freeze is not None, "holdout requires discovery freeze")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        spec = load_json(args.spec)
        validation = validate_spec(spec)
        if args.validate_spec:
            emit(validation, args.out)
            return 0
        docs, reveal, audit = load_partition(args.corpus, args.mode)
        require(reveal.get(TARGET_TOKEN) == TARGET, "frozen target source binding missing from opened partition")
        if args.mode == "discovery":
            result = discovery(spec, docs, audit)
        else:
            result = holdout(spec, load_json(args.discovery_freeze), docs, audit)
        emit(result, args.out)
        print(json.dumps({"status": result["status"], "stage": result["stage"]}, sort_keys=True))
        return 0
    except (E1Error, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"R7-E1 ERROR: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
