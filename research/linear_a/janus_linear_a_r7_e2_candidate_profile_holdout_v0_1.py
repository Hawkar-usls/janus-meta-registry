#!/usr/bin/env python3
"""R7-E2 held-out confirmation of the two training-derived anonymous KU-RO atoms.

No feature discovery occurs here. The candidate atoms were generated on the R7-E1
training partition and are frozen in the E2 preregistration before any E1 holdout
content is opened. The primary unit is the physical object.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import janus_linear_a_r7_e1_anonymous_local_role_graph_v0_1 as e1

SPEC_ID = "JANUS-LINEAR-A-R7-E2-CANDIDATE-PROFILE-HOLDOUT-2026-08-15-v0.1"
PARENT_MERGE = "96dfca6972df19cc619a9bc9919ebdc5dabded46"
CANONICAL_VERSION = "v2.30"
CORPUS_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
TARGET = "KU-RO"
TARGET_TOKEN = "6a2ea59b95fe1b610d20"
REGION = "HT"
CANDIDATE_ATOMS = (
    "PREV_ROW_NUMERIC_COUNT=2PLUS",
    "PREV_ROW_LEXICAL_COUNT=2PLUS",
)
RANDOM_SIGNFLIP_N = 100000
RANDOM_SIGNFLIP_SEED = 71201
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


class E2Error(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise E2Error(message)


def load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: top level must be object")
    return value


def canonical_sha(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def validate_spec(spec: Mapping[str, Any]) -> Dict[str, Any]:
    require(spec.get("spec_id") == SPEC_ID, "spec id mismatch")
    require(spec.get("stage") == "R7-E2", "stage mismatch")
    require(spec.get("status") == "PREREGISTERED_BEFORE_E2_HOLDOUT_ACCESS", "spec status mismatch")
    p = spec.get("parent", {})
    require(p.get("e1_merge_commit_sha") == PARENT_MERGE, "parent merge mismatch")
    require(p.get("canonical_version") == CANONICAL_VERSION, "canonical version mismatch")
    require(p.get("target") == TARGET and p.get("opaque_target_token") == TARGET_TOKEN, "target binding mismatch")
    require(p.get("region") == REGION and p.get("retained_parent_role") == "ROW-OPENING-LIKE", "parent role mismatch")
    require(p.get("e1_status") == "E1_DISCOVERY_PROFILE_NOT_FROZEN_RETAIN_ROW-OPENING-LIKE", "E1 status mismatch")
    require(spec.get("source", {}).get("frozen_commit") == CORPUS_COMMIT, "corpus mismatch")
    reserved = spec.get("reserved_test_partition", {})
    require(reserved.get("holdout_buckets") == [3, 4], "holdout buckets drift")
    require(reserved.get("content_was_not_parsed_by_e1_discovery") is True, "holdout purity assertion missing")
    require(reserved.get("e1_holdout_execution_was_not_performed") is True, "E1 holdout purity assertion missing")
    require(reserved.get("e2_is_the_first_authorized_inferential_access_to_this_partition") is True, "first-access assertion missing")
    profile = spec.get("training_derived_candidate_profile", {})
    require(tuple(profile.get("atoms", [])) == CANDIDATE_ATOMS, "candidate atoms drift")
    require(profile.get("manual_post_e1_atom_addition") is False and profile.get("manual_post_e1_atom_removal") is False, "manual atom edit forbidden")
    matching = spec.get("matching", {})
    require(matching.get("stratum") == ["relative_row_position_third", "document_row_count_bin"], "matching stratum drift")
    require(matching.get("minimum_control_events_per_target") == 20, "control event floor drift")
    require(matching.get("minimum_control_physical_objects_per_target") == 10, "control object floor drift")
    require(matching.get("adaptive_stratum_relaxation_forbidden") is True, "adaptive relaxation forbidden")
    require(matching.get("nearest_neighbor_fallback_forbidden") is True, "nearest-neighbor fallback forbidden")
    primary = spec.get("primary_statistic", {})
    require(primary.get("random_seed_if_needed") == RANDOM_SIGNFLIP_SEED, "sign-flip seed drift")
    require(primary.get("alpha") == 0.01, "alpha drift")
    gates = spec.get("support_and_robustness_gates", {})
    expected = {
        "minimum_total_holdout_target_events": 8,
        "minimum_eligible_target_events": 8,
        "minimum_eligible_target_fraction": 0.70,
        "minimum_target_documents": 7,
        "minimum_target_physical_objects": 7,
        "minimum_primary_effect": 0.15,
        "minimum_leave_one_target_object_out_positive_fraction": 0.85,
        "maximum_single_target_object_event_fraction": 0.25,
        "each_frozen_atom_must_have_positive_object_weighted_effect": True,
    }
    for key, value in expected.items():
        require(gates.get(key) == value, f"gate drift: {key}")
    anti = spec.get("anti_flexibility", {})
    require(anti and all(v is True for v in anti.values()), "anti-flexibility must be all true")
    firewall = spec.get("feature_firewall", {})
    require(firewall and all(v is False for v in firewall.values()), "forbidden feature flags must remain false")
    ceiling = spec.get("claim_ceiling", {})
    require(ceiling.get("parent_probable_region_scoped_structural_function_retained") is True, "parent retention missing")
    require(ceiling.get("heldout_structural_context_refinement_may_be_established") is True, "context-refinement permission missing")
    for key in FALSE_CLAIMS:
        require(ceiling.get(key) is False, f"claim ceiling violation: {key}")
    return {"stage": "R7-E2", "status": "R7_E2_PREREGISTRATION_VALIDATED", "spec_id": SPEC_ID, "spec_sha256": canonical_sha(spec)}


def document_row_count_bin(n: int) -> str:
    require(n >= 1, "document must contain at least one row")
    if n <= 4:
        return "1-4"
    if n <= 9:
        return "5-9"
    return "10PLUS"


def profile_score(event: Mapping[str, Any]) -> float:
    atoms = set(event["atoms"])
    return sum(atom in atoms for atom in CANDIDATE_ATOMS) / len(CANDIDATE_ATOMS)


def atom_score(event: Mapping[str, Any], atom: str) -> float:
    return 1.0 if atom in set(event["atoms"]) else 0.0


def event_stratum(event: Mapping[str, Any]) -> Tuple[str, str]:
    return event["position_bin"], document_row_count_bin(int(event["row_count"]))


def object_weighted_control_mean(events: Sequence[Mapping[str, Any]], scorer) -> Tuple[float, int, int]:
    by_object: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        by_object[event["object_id"]].append(event)
    object_means = [sum(scorer(e) for e in rows) / len(rows) for rows in by_object.values()]
    require(object_means, "empty control pool")
    return sum(object_means) / len(object_means), len(events), len(by_object)


def signflip_p(object_effects: Sequence[float]) -> Dict[str, Any]:
    n = len(object_effects)
    require(n > 0, "no object effects")
    observed = sum(object_effects) / n
    if n <= 20:
        ge = 0
        total = 1 << n
        for signs in itertools.product((-1.0, 1.0), repeat=n):
            score = sum(s * x for s, x in zip(signs, object_effects)) / n
            ge += int(score >= observed - 1e-15)
        return {"mode": "exact", "assignments": total, "ge_observed": ge, "p": ge / total}
    rng = random.Random(RANDOM_SIGNFLIP_SEED)
    ge = 0
    for _ in range(RANDOM_SIGNFLIP_N):
        score = sum((1.0 if rng.getrandbits(1) else -1.0) * x for x in object_effects) / n
        ge += int(score >= observed - 1e-15)
    return {"mode": "seeded_random", "assignments": RANDOM_SIGNFLIP_N, "ge_observed": ge, "p": (1 + ge) / (1 + RANDOM_SIGNFLIP_N), "seed": RANDOM_SIGNFLIP_SEED}


def evaluate_events(spec: Mapping[str, Any], events: Sequence[Mapping[str, Any]], load_audit: Mapping[str, Any]) -> Dict[str, Any]:
    require(all(e.get("partition") == "holdout" for e in events), "non-holdout event entered E2")
    targets = [e for e in events if e["is_target"]]
    target_objects = {e["object_id"] for e in targets}
    pure_controls = [e for e in events if not e["is_target"] and e["object_id"] not in target_objects]
    require(not any(e["object_id"] in target_objects for e in pure_controls), "target object leaked into control pool")

    controls_by_stratum: Dict[Tuple[str, str], List[Mapping[str, Any]]] = defaultdict(list)
    for control in pure_controls:
        controls_by_stratum[event_stratum(control)].append(control)

    match_cfg = spec["matching"]
    matched_rows: List[Dict[str, Any]] = []
    ineligible_rows: List[Dict[str, Any]] = []
    for target in targets:
        stratum = event_stratum(target)
        controls = controls_by_stratum.get(stratum, [])
        control_objects = {c["object_id"] for c in controls}
        if len(controls) < match_cfg["minimum_control_events_per_target"] or len(control_objects) < match_cfg["minimum_control_physical_objects_per_target"]:
            ineligible_rows.append({
                "doc": target["doc"],
                "object_id": target["object_id"],
                "stratum": list(stratum),
                "control_events": len(controls),
                "control_physical_objects": len(control_objects),
            })
            continue
        control_profile_mean, n_control_events, n_control_objects = object_weighted_control_mean(controls, profile_score)
        atom_control_means = {}
        for atom in CANDIDATE_ATOMS:
            atom_control_means[atom] = object_weighted_control_mean(controls, lambda e, a=atom: atom_score(e, a))[0]
        target_profile = profile_score(target)
        matched_rows.append({
            "doc": target["doc"],
            "object_id": target["object_id"],
            "stratum": list(stratum),
            "target_profile_score": target_profile,
            "matched_control_profile_mean": control_profile_mean,
            "profile_difference": target_profile - control_profile_mean,
            "control_events": n_control_events,
            "control_physical_objects": n_control_objects,
            "target_atom_scores": {atom: atom_score(target, atom) for atom in CANDIDATE_ATOMS},
            "matched_control_atom_means": atom_control_means,
        })

    by_target_object: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in matched_rows:
        by_target_object[row["object_id"]].append(row)
    object_rows = []
    for object_id, rows in sorted(by_target_object.items()):
        effect = sum(r["profile_difference"] for r in rows) / len(rows)
        atom_effects = {
            atom: sum(r["target_atom_scores"][atom] - r["matched_control_atom_means"][atom] for r in rows) / len(rows)
            for atom in CANDIDATE_ATOMS
        }
        object_rows.append({
            "object_id": object_id,
            "target_events": len(rows),
            "documents": sorted({r["doc"] for r in rows}),
            "profile_difference": effect,
            "atom_differences": atom_effects,
        })

    object_effects = [r["profile_difference"] for r in object_rows]
    observed_effect = sum(object_effects) / len(object_effects) if object_effects else 0.0
    signflip = signflip_p(object_effects) if object_effects else {"mode": "not_run_no_eligible_objects", "assignments": 0, "ge_observed": 0, "p": 1.0}
    loo_effects = []
    if len(object_effects) >= 2:
        for i in range(len(object_effects)):
            kept = object_effects[:i] + object_effects[i + 1:]
            loo_effects.append(sum(kept) / len(kept))
    loo_positive_fraction = sum(x > 0 for x in loo_effects) / len(loo_effects) if loo_effects else 0.0

    eligible_events = len(matched_rows)
    eligible_fraction = eligible_events / len(targets) if targets else 0.0
    object_counts = Counter(r["object_id"] for r in matched_rows)
    max_object_fraction = max(object_counts.values()) / eligible_events if eligible_events and object_counts else 1.0
    eligible_docs = {r["doc"] for r in matched_rows}
    eligible_objects = set(object_counts)
    atom_effects = {
        atom: (sum(r["atom_differences"][atom] for r in object_rows) / len(object_rows) if object_rows else 0.0)
        for atom in CANDIDATE_ATOMS
    }

    gates = spec["support_and_robustness_gates"]
    support_pass = (
        len(targets) >= gates["minimum_total_holdout_target_events"]
        and eligible_events >= gates["minimum_eligible_target_events"]
        and eligible_fraction >= gates["minimum_eligible_target_fraction"]
        and len(eligible_docs) >= gates["minimum_target_documents"]
        and len(eligible_objects) >= gates["minimum_target_physical_objects"]
    )
    effect_pass = observed_effect >= gates["minimum_primary_effect"]
    p_pass = signflip["p"] <= spec["primary_statistic"]["alpha"]
    loo_pass = loo_positive_fraction >= gates["minimum_leave_one_target_object_out_positive_fraction"]
    concentration_pass = max_object_fraction <= gates["maximum_single_target_object_event_fraction"]
    atom_direction_pass = all(v > 0 for v in atom_effects.values())
    passed = all((support_pass, effect_pass, p_pass, loo_pass, concentration_pass, atom_direction_pass))
    if not support_pass:
        status = spec["decision"]["underpowered_status"]
    elif passed:
        status = spec["decision"]["pass_status"]
    else:
        status = spec["decision"]["fail_status"]

    result = {
        "schema_version": "1.0",
        "artifact_uuid": "JANUS-LINEAR-A-R7-E2-CANDIDATE-PROFILE-HOLDOUT-RESULT-2026-08-15-v0.1",
        "stage": "R7-E2",
        "status": status,
        "spec_id": SPEC_ID,
        "spec_sha256": canonical_sha(spec),
        "target": TARGET,
        "target_opaque_token": TARGET_TOKEN,
        "region": REGION,
        "inherited_parent_role": "ROW-OPENING-LIKE",
        "candidate_atoms": list(CANDIDATE_ATOMS),
        "holdout_partition_opened_for_first_inferential_test": True,
        "load_audit": dict(load_audit),
        "total_holdout_target_events": len(targets),
        "eligible_target_events": eligible_events,
        "ineligible_target_events": len(ineligible_rows),
        "eligible_target_fraction": eligible_fraction,
        "eligible_target_documents": len(eligible_docs),
        "eligible_target_physical_objects": len(eligible_objects),
        "pure_control_events": len(pure_controls),
        "pure_control_physical_objects": len({e["object_id"] for e in pure_controls}),
        "observed_object_weighted_profile_effect": observed_effect,
        "signflip": signflip,
        "leave_one_target_object_out_effects": loo_effects,
        "leave_one_target_object_out_positive_fraction": loo_positive_fraction,
        "maximum_single_target_object_event_fraction": max_object_fraction,
        "frozen_atom_object_weighted_effects": atom_effects,
        "support_pass": support_pass,
        "effect_pass": effect_pass,
        "p_pass": p_pass,
        "leave_one_object_out_pass": loo_pass,
        "object_concentration_pass": concentration_pass,
        "frozen_atom_direction_pass": atom_direction_pass,
        "heldout_structural_context_refinement_established": passed,
        "admitted_context_refinement_label": spec["decision"]["pass_context_refinement_label"] if passed else None,
        "matched_target_event_audit": matched_rows,
        "ineligible_target_event_audit": ineligible_rows,
        "target_object_audit": object_rows,
        "canonical_auto_promotion_performed": False,
    }
    result.update({key: False for key in FALSE_CLAIMS})
    return result


def run_holdout(spec: Mapping[str, Any], corpus: Path) -> Dict[str, Any]:
    docs, reveal, audit = e1.load_partition(corpus, "holdout")
    require(reveal.get(TARGET_TOKEN) == TARGET, "frozen target binding absent in reserved holdout partition")
    events = e1.build_events(docs)
    require(events, "no holdout row-first events")
    return evaluate_events(spec, events, audit)


def emit(value: Mapping[str, Any], path: Path | None) -> None:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, type=Path)
    ap.add_argument("--validate-spec", action="store_true")
    ap.add_argument("--corpus", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if not args.validate_spec:
        require(args.corpus is not None and args.out is not None, "holdout execution requires corpus and out")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        spec = load_json(args.spec)
        validation = validate_spec(spec)
        if args.validate_spec:
            emit(validation, args.out)
            return 0
        result = run_holdout(spec, args.corpus)
        emit(result, args.out)
        print(json.dumps({
            "status": result["status"],
            "total_holdout_target_events": result["total_holdout_target_events"],
            "eligible_target_events": result["eligible_target_events"],
            "eligible_target_physical_objects": result["eligible_target_physical_objects"],
            "effect": result["observed_object_weighted_profile_effect"],
            "p": result["signflip"]["p"],
        }, sort_keys=True))
        return 0
    except (E2Error, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"R7-E2 ERROR: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
