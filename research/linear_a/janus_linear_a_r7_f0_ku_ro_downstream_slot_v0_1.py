#!/usr/bin/env python3
"""R7-F0 object-blocked KU-RO downstream slot organization.

This is an internal cross-fitted structural test on a previously accessed development
corpus. It does not create a new cold holdout. The already-admitted opaque KU-RO anchor
is fixed before scoring. Three downstream signature channels are preregistered. For
each target-bearing physical object, every event from that object is excluded from
training. An object-preserving tail permutation destroys anchor->downstream order while
preserving the multiset of downstream tails inside each physical object.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import janus_linear_a_r7_arithmetic_summary_role_v0_1 as b0
import janus_linear_a_r7_positional_template_roles_v0_1 as c0
import janus_linear_a_r7_region_scoped_object_status_v0_1 as d0

SPEC_ID = "JANUS-LINEAR-A-R7-F0-KU-RO-DOWNSTREAM-SLOT-2026-08-15-v0.1"
PARENT_MERGE = "c2f57985891ac0628fa0da0849df0d24aeddebcd"
CANONICAL_VERSION = "v2.30"
CORPUS_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
TARGET = "KU-RO"
TARGET_TOKEN = "6a2ea59b95fe1b610d20"
REGION = "HT"
CHANNELS = ("NEXT_KIND", "NEXT_LEX_OR_KIND", "TWO_KIND")
ALPHA = 0.5
NULL_N = 5000
NULL_SEED = 71301
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


class F0Error(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise F0Error(message)


def load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: top level must be object")
    return value


def validate_spec(spec: Mapping[str, Any]) -> Dict[str, Any]:
    require(spec.get("spec_id") == SPEC_ID, "spec id mismatch")
    require(spec.get("stage") == "R7-F0", "stage mismatch")
    require(spec.get("status") == "PREREGISTERED_BEFORE_F0_SCORING", "spec status mismatch")
    parent = spec.get("parent", {})
    require(parent.get("e2_merge_commit_sha") == PARENT_MERGE, "parent merge mismatch")
    require(parent.get("canonical_version") == CANONICAL_VERSION, "canonical version mismatch")
    require(parent.get("target") == TARGET and parent.get("opaque_target_token") == TARGET_TOKEN, "target binding mismatch")
    require(parent.get("region") == REGION and parent.get("retained_parent_role") == "ROW-OPENING-LIKE", "parent role mismatch")
    require(parent.get("e2_status") == "E2_CANDIDATE_PROFILE_NOT_REPLICATED_RETAIN_ROW-OPENING-LIKE", "E2 status mismatch")
    source = spec.get("source", {})
    require(source.get("frozen_commit") == CORPUS_COMMIT, "corpus commit mismatch")
    require(source.get("internal_corpus_status") == "DEVELOPMENT_CORPUS_PREVIOUSLY_ACCESSED", "development-corpus label required")
    require(source.get("external_or_cold_replication_claim_allowed") is False, "cold replication claim forbidden")
    require(tuple(spec.get("channels", {}).keys()) == CHANNELS, "channel family drift")
    cross = spec.get("cross_fitting", {})
    require(cross.get("scheme") == "leave-one-physical-object-out over target-bearing physical objects", "LOPO scheme drift")
    require(cross.get("smoothing") == "symmetric Dirichlet alpha=0.5 on the frozen channel support", "smoothing drift")
    null = spec.get("structure_destroying_null", {})
    require(null.get("permutations") == NULL_N and null.get("seed") == NULL_SEED, "null settings drift")
    require(null.get("recompute_full_LOPO_pipeline_each_permutation") is True, "full null recomputation required")
    family = spec.get("familywise_decision", {})
    require(family.get("channels_tested") == 3 and family.get("multiple_testing") == "Holm", "family definition drift")
    require(family.get("familywise_alpha") == 0.01, "family alpha drift")
    expected = {
        "minimum_target_events": 25,
        "minimum_target_physical_objects": 20,
        "minimum_background_events": 300,
        "minimum_exchangeable_target_event_fraction": 0.70,
        "maximum_single_target_object_event_fraction": 0.15,
        "minimum_observed_information_gain_bits": 0.15,
        "minimum_observed_minus_null_mean_bits": 0.15,
        "minimum_positive_target_object_fraction": 0.65,
        "Holm_adjusted_p_max": 0.01,
    }
    gates = family.get("channel_gates", {})
    for key, value in expected.items():
        require(gates.get(key) == value, f"channel gate drift: {key}")
    anti = spec.get("anti_flexibility", {})
    require(anti and all(v is True for v in anti.values()), "anti-flexibility must be all true")
    ceiling = spec.get("claim_ceiling", {})
    require(ceiling.get("parent_probable_region_scoped_structural_function_retained") is True, "parent retention missing")
    require(ceiling.get("internal_cross_fitted_downstream_slot_organization_may_be_established") is True, "F0 structural claim permission missing")
    for key in FALSE_CLAIMS:
        require(ceiling.get(key) is False, f"claim ceiling violation: {key}")
    return {"stage": "R7-F0", "status": "R7_F0_PREREGISTRATION_VALIDATED", "spec_id": SPEC_ID}


def fixed_support(channel: str) -> Tuple[str, ...] | None:
    if channel == "NEXT_KIND":
        return ("W", "N", "X", "END")
    if channel == "TWO_KIND":
        kinds = ("W", "N", "X", "END")
        return tuple(f"{a}|{b}" for a in kinds for b in kinds)
    if channel == "NEXT_LEX_OR_KIND":
        return None
    raise AssertionError(channel)


def tail_bundle(seq: Sequence[Mapping[str, Any]], row_indices: Sequence[int], anchor_index: int) -> Tuple[str, str, str]:
    suffix = [seq[i] for i in row_indices if i > anchor_index]
    kinds = [x.get("kind") for x in suffix]
    require(all(k in {"W", "N", "X"} for k in kinds), "unexpected downstream item kind")
    first_kind = kinds[0] if kinds else "END"
    if not suffix:
        lex_or_kind = "END"
    elif first_kind == "W":
        token = suffix[0].get("word")
        require(isinstance(token, str) and token, "downstream lexical token missing")
        lex_or_kind = f"W:{token}"
    else:
        lex_or_kind = first_kind
    first = kinds[0] if len(kinds) >= 1 else "END"
    second = kinds[1] if len(kinds) >= 2 else "END"
    return first_kind, lex_or_kind, f"{first}|{second}"


def build_events(docs: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    docmap = {d["doc"]: d for d in docs}
    events: List[Dict[str, Any]] = []
    for obs in c0.role_observations(docs):
        if obs.get("role") != "ROW_FIRST_LEXICAL" or not obs.get("match") or obs.get("region") != REGION:
            continue
        doc = docmap[obs["doc"]]
        seq = doc["sequence"]
        row = obs["meta"]["row"]
        rows = c0.row_index_sequences(seq)
        require(row in rows, "row-first source row missing")
        anchor_index = None
        for i in rows[row]:
            item = seq[i]
            if item.get("kind") == "W" and item.get("word_index") == obs["word_index"] and item.get("word") == obs["word"]:
                anchor_index = i
                break
        require(anchor_index is not None, "row-first anchor binding failed")
        bundle = tail_bundle(seq, rows[row], anchor_index)
        events.append({
            "doc": doc["doc"],
            "object_id": d0.object_id(doc["doc"]),
            "is_target": obs["word"] == TARGET_TOKEN,
            "word": obs["word"],
            "row": row,
            "bundle": bundle,
        })
    return events


def channel_index(channel: str) -> int:
    return CHANNELS.index(channel)


def lexical_support_for_holdout(events: Sequence[Mapping[str, Any]], bundles: Sequence[Tuple[str, str, str]], holdout_object: str) -> Tuple[str, ...]:
    idx = channel_index("NEXT_LEX_OR_KIND")
    support = {"N", "X", "END", "W:<UNK>"}
    for event, bundle in zip(events, bundles):
        if event["object_id"] == holdout_object:
            continue
        support.add(bundle[idx])
    return tuple(sorted(support))


def normalize_signature(channel: str, raw: str, support: Sequence[str]) -> str:
    if channel == "NEXT_LEX_OR_KIND" and raw.startswith("W:") and raw not in support:
        return "W:<UNK>"
    return raw


def score_assignment(events: Sequence[Mapping[str, Any]], bundles: Sequence[Tuple[str, str, str]], channel: str) -> Dict[str, Any]:
    require(len(events) == len(bundles), "event/bundle length mismatch")
    cidx = channel_index(channel)
    target_indices = [i for i, e in enumerate(events) if e["is_target"]]
    target_objects = sorted({events[i]["object_id"] for i in target_indices})
    require(target_objects, "no target objects")

    global_target = Counter()
    global_background = Counter()
    object_target: Dict[str, Counter] = defaultdict(Counter)
    object_background: Dict[str, Counter] = defaultdict(Counter)
    object_target_indices: Dict[str, List[int]] = defaultdict(list)

    for i, (event, bundle) in enumerate(zip(events, bundles)):
        raw = bundle[cidx]
        oid = event["object_id"]
        if event["is_target"]:
            global_target[raw] += 1
            object_target[oid][raw] += 1
            object_target_indices[oid].append(i)
        else:
            global_background[raw] += 1
            object_background[oid][raw] += 1

    total_target = sum(global_target.values())
    total_background = sum(global_background.values())
    object_scores = []
    event_scores = []
    for oid in target_objects:
        support = fixed_support(channel)
        if support is None:
            support = lexical_support_for_holdout(events, bundles, oid)
        support_set = set(support)
        k_support = len(support)
        train_target_n = total_target - sum(object_target[oid].values())
        train_background_n = total_background - sum(object_background[oid].values())
        require(train_target_n > 0 and train_background_n > 0, "empty LOPO training distribution")
        scores = []
        for i in object_target_indices[oid]:
            raw = bundles[i][cidx]
            sig = normalize_signature(channel, raw, support)
            require(sig in support_set, "signature outside frozen support")
            ct = global_target[raw] - object_target[oid][raw] if sig == raw else 0
            cb = global_background[raw] - object_background[oid][raw] if sig == raw else 0
            pt = (ct + ALPHA) / (train_target_n + ALPHA * k_support)
            pb = (cb + ALPHA) / (train_background_n + ALPHA * k_support)
            gain = math.log2(pt / pb)
            scores.append(gain)
            event_scores.append({"doc": events[i]["doc"], "object_id": oid, "raw_signature": raw, "model_signature": sig, "information_gain_bits": gain})
        object_scores.append({"object_id": oid, "target_events": len(scores), "information_gain_bits": sum(scores) / len(scores)})

    mean_gain = sum(x["information_gain_bits"] for x in object_scores) / len(object_scores)
    positive_fraction = sum(x["information_gain_bits"] > 0 for x in object_scores) / len(object_scores)
    return {
        "mean_information_gain_bits": mean_gain,
        "positive_target_object_fraction": positive_fraction,
        "target_object_scores": object_scores,
        "target_event_scores": event_scores,
    }


def object_index_map(events: Sequence[Mapping[str, Any]]) -> Dict[str, List[int]]:
    out: Dict[str, List[int]] = defaultdict(list)
    for i, event in enumerate(events):
        out[event["object_id"]].append(i)
    return dict(out)


def permuted_bundles(original: Sequence[Tuple[str, str, str]], by_object: Mapping[str, Sequence[int]], rng: random.Random) -> List[Tuple[str, str, str]]:
    out = list(original)
    for indices in by_object.values():
        if len(indices) <= 1:
            continue
        values = [original[i] for i in indices]
        rng.shuffle(values)
        for i, value in zip(indices, values):
            out[i] = value
    return out


def holm_adjusted(pvalues: Mapping[str, float]) -> Dict[str, float]:
    ordered = sorted(pvalues, key=lambda c: (pvalues[c], c))
    m = len(ordered)
    adjusted: Dict[str, float] = {}
    running = 0.0
    for rank, channel in enumerate(ordered, start=1):
        value = min(1.0, (m - rank + 1) * pvalues[channel])
        running = max(running, value)
        adjusted[channel] = running
    return adjusted


def evaluate(spec: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    targets = [e for e in events if e["is_target"]]
    background = [e for e in events if not e["is_target"]]
    target_objects = Counter(e["object_id"] for e in targets)
    by_object = object_index_map(events)
    exchangeable_target_events = sum(target_objects[oid] for oid in target_objects if len(by_object[oid]) > target_objects[oid])
    exchangeable_fraction = exchangeable_target_events / len(targets) if targets else 0.0
    max_object_fraction = max(target_objects.values()) / len(targets) if targets else 1.0
    gates = spec["familywise_decision"]["channel_gates"]
    support_pass = bool(
        len(targets) >= gates["minimum_target_events"]
        and len(target_objects) >= gates["minimum_target_physical_objects"]
        and len(background) >= gates["minimum_background_events"]
        and exchangeable_fraction >= gates["minimum_exchangeable_target_event_fraction"]
        and max_object_fraction <= gates["maximum_single_target_object_event_fraction"]
    )

    original = [tuple(e["bundle"]) for e in events]
    observed = {channel: score_assignment(events, original, channel) for channel in CHANNELS}
    ge = Counter()
    null_sum = Counter()
    rng = random.Random(NULL_SEED)
    for _ in range(NULL_N):
        shuffled = permuted_bundles(original, by_object, rng)
        for channel in CHANNELS:
            score = score_assignment(events, shuffled, channel)["mean_information_gain_bits"]
            null_sum[channel] += score
            ge[channel] += int(score >= observed[channel]["mean_information_gain_bits"] - 1e-15)

    raw_p = {channel: (1 + ge[channel]) / (1 + NULL_N) for channel in CHANNELS}
    holm = holm_adjusted(raw_p)
    rows = []
    admitted = []
    for channel in CHANNELS:
        obs = observed[channel]
        null_mean = null_sum[channel] / NULL_N
        excess = obs["mean_information_gain_bits"] - null_mean
        row = {
            "channel": channel,
            "observed_information_gain_bits": obs["mean_information_gain_bits"],
            "null_mean_information_gain_bits": null_mean,
            "observed_minus_null_mean_bits": excess,
            "positive_target_object_fraction": obs["positive_target_object_fraction"],
            "permutations": NULL_N,
            "ge_observed": ge[channel],
            "empirical_p": raw_p[channel],
            "Holm_adjusted_p": holm[channel],
            "support_pass": support_pass,
            "observed_gain_pass": obs["mean_information_gain_bits"] >= gates["minimum_observed_information_gain_bits"],
            "null_excess_pass": excess >= gates["minimum_observed_minus_null_mean_bits"],
            "positive_object_fraction_pass": obs["positive_target_object_fraction"] >= gates["minimum_positive_target_object_fraction"],
            "Holm_pass": holm[channel] <= gates["Holm_adjusted_p_max"],
            "target_object_scores": obs["target_object_scores"],
            "target_event_scores": obs["target_event_scores"],
        }
        row["channel_admitted"] = bool(
            row["support_pass"] and row["observed_gain_pass"] and row["null_excess_pass"]
            and row["positive_object_fraction_pass"] and row["Holm_pass"]
        )
        row["admitted_constraint_label"] = spec["channels"][channel]["claim_if_admitted"] if row["channel_admitted"] else None
        rows.append(row)
        if row["channel_admitted"]:
            admitted.append(row["admitted_constraint_label"])

    if not support_pass:
        status = spec["decision"]["underpowered_status"]
    elif admitted:
        status = spec["decision"]["pass_status"]
    else:
        status = spec["decision"]["fail_status"]
    result = {
        "schema_version": "1.0",
        "artifact_uuid": "JANUS-LINEAR-A-R7-F0-KU-RO-DOWNSTREAM-SLOT-RESULT-2026-08-15-v0.1",
        "stage": "R7-F0",
        "status": status,
        "spec_id": SPEC_ID,
        "target": TARGET,
        "target_opaque_token": TARGET_TOKEN,
        "region": REGION,
        "inherited_parent_role": "ROW-OPENING-LIKE",
        "inherited_parent_role_retained": True,
        "internal_cross_fitted_development_corpus_test": True,
        "cold_or_external_replication": False,
        "target_events": len(targets),
        "target_physical_objects": len(target_objects),
        "background_events": len(background),
        "exchangeable_target_events": exchangeable_target_events,
        "exchangeable_target_event_fraction": exchangeable_fraction,
        "maximum_single_target_object_event_fraction": max_object_fraction,
        "support_pass": support_pass,
        "channel_results": rows,
        "admitted_channel_count": len(admitted),
        "admitted_constraint_labels": admitted,
        "internal_cross_fitted_downstream_slot_organization_established": bool(admitted),
        "canonical_auto_promotion_performed": False,
    }
    result.update({key: False for key in FALSE_CLAIMS})
    return result


def run(spec: Mapping[str, Any], corpus: Path) -> Dict[str, Any]:
    docs, reveal, failures = b0.load_corpus(corpus)
    require(reveal.get(TARGET_TOKEN) == TARGET, "frozen target source binding mismatch")
    events = build_events(docs)
    result = evaluate(spec, events)
    result["source"] = {
        "repository": "Hawkar-usls/lineara.xyz",
        "frozen_commit": CORPUS_COMMIT,
        "parsed_documents": len(docs),
        "parse_failures_or_empty": failures,
    }
    return result


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
        require(args.corpus is not None and args.out is not None, "scoring requires corpus and out")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        spec = load_json(args.spec)
        validation = validate_spec(spec)
        if args.validate_spec:
            emit(validation, args.out)
            return 0
        result = run(spec, args.corpus)
        emit(result, args.out)
        print(json.dumps({
            "status": result["status"],
            "target_events": result["target_events"],
            "target_physical_objects": result["target_physical_objects"],
            "background_events": result["background_events"],
            "admitted_channel_count": result["admitted_channel_count"],
        }, sort_keys=True))
        return 0
    except (F0Error, OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"R7-F0 ERROR: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
