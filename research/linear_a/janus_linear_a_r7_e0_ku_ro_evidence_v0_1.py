#!/usr/bin/env python3
"""Produce R7-E0 frozen-target KU-RO mechanism evidence from the frozen corpus.

This producer does not discover words, rank vocabulary, or use lexical semantics.
The already-admitted KU-RO opaque token is bound before scoring.  It evaluates only
execution operators frozen in the R7-E0 execution spec and emits evidence for the
separate janus_linear_a_r7_ku_ro_mechanism_v0_1 admission gate.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

import janus_linear_a_r7_arithmetic_summary_role_v0_1 as b0
import janus_linear_a_r7_positional_template_roles_v0_1 as c0
import janus_linear_a_r7_region_scoped_object_status_v0_1 as d0
import janus_linear_a_r7_ku_ro_mechanism_v0_1 as gate

FROZEN_CORPUS_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
TARGET_TOKEN = "6a2ea59b95fe1b610d20"
TARGET_LABEL = "KU-RO"
REGION = "HT"
N_PERM = 10000
SEEDS = {"ARITHMETIC_SUMMARY": 71001, "SECTION_BOUNDARY": 71002}


def load_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top level must be object")
    return value


def validate_execution_spec(ex: Mapping[str, Any], c3: Mapping[str, Any]) -> None:
    assert ex["status"] == "EXECUTION_OPERATORS_FROZEN_BEFORE_E0_CORPUS_SCORING"
    assert ex["source"]["frozen_commit"] == FROZEN_CORPUS_COMMIT
    binding = ex["frozen_target_binding"]
    assert binding["source_word"] == TARGET_LABEL
    assert binding["opaque_word_token"] == TARGET_TOKEN
    assert binding["region"] == REGION
    assert binding["required_parent_role"] == "ROW_FIRST_LEXICAL"
    assert binding["probable_parent_function"] == "ROW-OPENING-LIKE"
    admitted = c3["admitted_candidates"]
    assert c3["status"] == "REGION_SCOPED_PROBABLE_STRUCTURAL_FUNCTION_ADMITTED"
    assert len(admitted) == 1
    assert admitted[0]["word_token"] == TARGET_TOKEN
    assert admitted[0]["source_word"] == TARGET_LABEL
    assert admitted[0]["source_role"] == "ROW_FIRST_LEXICAL"
    assert admitted[0]["scope_region"] == REGION
    assert admitted[0]["probable_structural_function_label"] == "ROW-OPENING-LIKE"
    assert ex["mechanisms"]["ARITHMETIC_SUMMARY"]["seed"] == SEEDS["ARITHMETIC_SUMMARY"]
    assert ex["mechanisms"]["SECTION_BOUNDARY"]["seed"] == SEEDS["SECTION_BOUNDARY"]
    assert ex["mechanisms"]["ARITHMETIC_SUMMARY"]["permutations"] == N_PERM
    assert ex["mechanisms"]["SECTION_BOUNDARY"]["permutations"] == N_PERM


def status_name(statuses: Sequence[str]) -> str:
    return "+".join(statuses) if statuses else "EMPTY"


def term_bin(n: int) -> str:
    if n <= 3:
        return "2-3"
    if n <= 7:
        return "4-7"
    return "8+"


def exposure_bin(n: int) -> str:
    if n <= 0:
        return "0"
    if n == 1:
        return "1"
    return "2+"


def position_bin(rank: int, total: int) -> str:
    assert 0 <= rank < total
    bucket = min(2, (3 * rank) // max(total, 1))
    return ("early", "middle", "late")[bucket]


def levenshtein(a: Sequence[str], b: Sequence[str]) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, av in enumerate(a, start=1):
        current = [i]
        for j, bv in enumerate(b, start=1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (av != bv)))
        previous = current
    return previous[-1]


def normalized_kind_distance(a: Sequence[str], b: Sequence[str]) -> float:
    denom = max(len(a), len(b))
    return 0.0 if denom == 0 else levenshtein(a, b) / denom


def row_layout(doc: Mapping[str, Any]) -> Tuple[Dict[int, List[int]], List[int], Dict[int, int]]:
    rows = c0.row_index_sequences(doc["sequence"])
    order = sorted(rows, key=lambda r: min(rows[r]))
    return rows, order, {r: i for i, r in enumerate(order)}


def shared_row_first_events(docs: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    docmap = {d["doc"]: d for d in docs}
    out: List[Dict[str, Any]] = []
    for obs in c0.role_observations(docs):
        if obs["role"] != "ROW_FIRST_LEXICAL" or not obs["match"] or obs["region"] != REGION:
            continue
        doc = docmap[obs["doc"]]
        row = obs["meta"]["row"]
        seq_index = None
        for i, item in enumerate(doc["sequence"]):
            if item.get("kind") == "W" and item.get("word_index") == obs["word_index"] and item.get("word") == obs["word"]:
                seq_index = i
                break
        if seq_index is None:
            raise RuntimeError("R7_E0_ROW_FIRST_EVENT_BINDING_FAIL")
        rows, order, ranks = row_layout(doc)
        if row not in ranks:
            raise RuntimeError("R7_E0_ROW_LAYOUT_BINDING_FAIL")
        out.append({
            "doc": doc["doc"],
            "object_id": d0.object_id(doc["doc"]),
            "word": obs["word"],
            "is_target": obs["word"] == TARGET_TOKEN,
            "statuses": list(obs.get("statuses", [])),
            "status": status_name(obs.get("statuses", [])),
            "row": row,
            "row_rank": ranks[row],
            "row_count": len(order),
            "seq_index": seq_index,
            "doc_record": doc,
            "rows": rows,
            "row_order": order,
        })
    return out


def arithmetic_record(event: Mapping[str, Any]) -> Dict[str, Any] | None:
    doc = event["doc_record"]
    seq = doc["sequence"]
    i = event["seq_index"]
    row = event["row"]
    if i + 1 >= len(seq):
        return None
    following = seq[i + 1]
    if following.get("kind") != "N" or len(following.get("rows", [])) != 1 or following["rows"][0] != row:
        return None

    rows: Mapping[int, List[int]] = event["rows"]
    order: Sequence[int] = event["row_order"]
    rank = event["row_rank"]
    block_indices: List[int] = []

    # Numeric material on the same row before the frozen row-first lexical event.
    for j in rows[row]:
        if j >= i:
            break
        if seq[j].get("kind") in {"N", "X"}:
            block_indices.append(j)

    # Then walk backward through the maximal contiguous run of numeric-bearing rows.
    r = rank - 1
    while r >= 0:
        prow = order[r]
        p_numeric = [j for j in rows[prow] if seq[j].get("kind") in {"N", "X"}]
        if not p_numeric:
            break
        block_indices.extend(p_numeric)
        r -= 1

    block_indices = sorted(set(block_indices))
    if len(block_indices) < 2:
        return None
    if any(seq[j].get("kind") == "X" for j in block_indices):
        return None
    values = [seq[j]["value"] for j in block_indices]
    if not all(isinstance(v, Fraction) for v in values):
        raise RuntimeError("R7_E0_EXACT_ARITHMETIC_TYPE_FAIL")
    total = sum(values, Fraction(0, 1))
    target_value = following["value"]
    score = 1.0 if total == target_value else 0.0
    return {
        "mechanism_id": "ARITHMETIC_SUMMARY",
        "doc": event["doc"],
        "object_id": event["object_id"],
        "status": event["status"],
        "is_target": event["is_target"],
        "score": score,
        "stratum": (event["doc"], event["status"], term_bin(len(values))),
        "audit": {
            "row": row,
            "prior_exact_numeric_terms": len(values),
            "prior_exact_sum": b0.qstr(total),
            "following_exact_value": b0.qstr(target_value),
            "exact_match": bool(score),
        },
    }


def boundary_record(event: Mapping[str, Any]) -> Dict[str, Any] | None:
    rank = event["row_rank"]
    order: Sequence[int] = event["row_order"]
    if rank <= 0 or rank + 1 >= len(order):
        return None
    rows: Mapping[int, List[int]] = event["rows"]
    seq = event["doc_record"]["sequence"]
    prev_row, target_row, next_row = order[rank - 1], order[rank], order[rank + 1]
    prev_sig = [seq[j].get("kind") for j in rows[prev_row]]
    next_sig = [seq[j].get("kind") for j in rows[next_row]]
    if any(k not in {"W", "N", "X"} for k in prev_sig + next_sig):
        raise RuntimeError("R7_E0_KIND_SIGNATURE_FAIL")
    target_numeric_exposure = sum(seq[j].get("kind") in {"N", "X"} for j in rows[target_row])
    score = normalized_kind_distance(prev_sig, next_sig)
    return {
        "mechanism_id": "SECTION_BOUNDARY",
        "doc": event["doc"],
        "object_id": event["object_id"],
        "status": event["status"],
        "is_target": event["is_target"],
        "score": score,
        "stratum": (
            event["doc"],
            event["status"],
            exposure_bin(target_numeric_exposure),
            position_bin(rank, len(order)),
        ),
        "audit": {
            "row": target_row,
            "previous_row": prev_row,
            "next_row": next_row,
            "previous_signature": "".join(prev_sig),
            "next_signature": "".join(next_sig),
            "normalized_edit_distance": score,
            "target_row_numeric_exposure_bin": exposure_bin(target_numeric_exposure),
            "relative_row_position_bin": position_bin(rank, len(order)),
        },
    }


def permute_mechanism(records: Sequence[Mapping[str, Any]], mechanism_id: str) -> Dict[str, Any]:
    targets = [r for r in records if r["is_target"]]
    if not targets:
        raise RuntimeError(f"R7_E0_{mechanism_id}_NO_ELIGIBLE_TARGET_EVENTS")
    n_target = len(targets)
    obs_sum = sum(float(r["score"]) for r in targets)
    observed = obs_sum / n_target

    by_stratum: Dict[Tuple[Any, ...], List[Mapping[str, Any]]] = defaultdict(list)
    for r in records:
        by_stratum[tuple(r["stratum"])].append(r)

    target_count_by_stratum = {s: sum(bool(r["is_target"]) for r in rs) for s, rs in by_stratum.items()}
    exchangeable_target_events = sum(
        k for s, k in target_count_by_stratum.items() if k and len(by_stratum[s]) > k
    )

    object_counts = Counter(r["object_id"] for r in targets)
    object_obs_sum = Counter()
    status_counts = Counter(r["status"] for r in targets)
    status_obs_sum = Counter()
    for r in targets:
        object_obs_sum[r["object_id"]] += float(r["score"])
        status_obs_sum[r["status"]] += float(r["score"])

    rng = random.Random(SEEDS[mechanism_id])
    ge = 0
    null_score_total = 0.0
    null_object_score_total = Counter()
    null_status_score_total = Counter()

    for _ in range(N_PERM):
        selected: List[Mapping[str, Any]] = []
        for s, rs in by_stratum.items():
            k = target_count_by_stratum[s]
            if k <= 0:
                continue
            if k >= len(rs):
                chosen = rs
            else:
                chosen = rng.sample(rs, k)
            selected.extend(chosen)
        if len(selected) != n_target:
            raise RuntimeError("R7_E0_PERMUTATION_TARGET_COUNT_DRIFT")
        pscore_sum = sum(float(r["score"]) for r in selected)
        pscore = pscore_sum / n_target
        null_score_total += pscore_sum
        ge += int(pscore >= observed - 1e-15)
        for r in selected:
            null_object_score_total[r["object_id"]] += float(r["score"])
            null_status_score_total[r["status"]] += float(r["score"])

    null_mean = null_score_total / (N_PERM * n_target)
    loo_effects: List[float] = []
    for oid in sorted(object_counts):
        remain = n_target - object_counts[oid]
        if remain <= 0:
            continue
        obs_excl = (obs_sum - object_obs_sum[oid]) / remain
        mean_total_perm_sum = null_score_total / N_PERM
        mean_oid_perm_sum = null_object_score_total[oid] / N_PERM
        null_excl = (mean_total_perm_sum - mean_oid_perm_sum) / remain
        loo_effects.append(obs_excl - null_excl)
    if not loo_effects:
        loo_effects = [0.0]

    editorial = []
    for status in sorted(status_counts):
        n = status_counts[status]
        obs = status_obs_sum[status] / n
        nul = null_status_score_total[status] / (N_PERM * n)
        editorial.append({"name": status, "n": n, "observed": obs, "matched_null_mean": nul, "effect": obs - nul})

    return {
        "mechanism_id": mechanism_id,
        "permutation_seed": SEEDS[mechanism_id],
        "eligible_target_events": n_target,
        "documents": len({r["doc"] for r in targets}),
        "physical_objects": len(object_counts),
        "observed_score": observed,
        "matched_null_mean": null_mean,
        "permutation": {"n": N_PERM, "ge_observed": ge},
        "leave_one_object_out_effects": loo_effects,
        "object_event_counts": dict(sorted(object_counts.items())),
        "editorial_strata": editorial,
        "audit": {
            "eligible_control_plus_target_events": len(records),
            "target_events_in_exchangeable_strata": exchangeable_target_events,
            "target_events_in_fixed_strata": n_target - exchangeable_target_events,
            "target_documents": sorted({r["doc"] for r in targets}),
            "target_event_details": [
                {"doc": r["doc"], "object_id": r["object_id"], "status": r["status"], "score": r["score"], **r["audit"]}
                for r in targets
            ],
        },
    }


def produce(corpus: Path, spec: Mapping[str, Any], execution: Mapping[str, Any], c3: Mapping[str, Any]) -> Dict[str, Any]:
    gate_validation = gate.validate_spec(spec)
    validate_execution_spec(execution, c3)
    docs, reveal, failures = b0.load_corpus(corpus)
    if reveal.get(TARGET_TOKEN) != TARGET_LABEL:
        raise RuntimeError("R7_E0_FROZEN_TARGET_SOURCE_BINDING_FAIL")
    shared = shared_row_first_events(docs)
    shared_targets = [e for e in shared if e["is_target"]]
    if not shared_targets:
        raise RuntimeError("R7_E0_NO_FROZEN_TARGET_IN_SHARED_POPULATION")

    arithmetic_records = [r for e in shared if (r := arithmetic_record(e)) is not None]
    boundary_records = [r for e in shared if (r := boundary_record(e)) is not None]
    mechanisms = [
        permute_mechanism(arithmetic_records, "ARITHMETIC_SUMMARY"),
        permute_mechanism(boundary_records, "SECTION_BOUNDARY"),
    ]

    return {
        "schema_version": "1.0",
        "artifact_uuid": "JANUS-LINEAR-A-R7-E0-KU-RO-MECHANISM-EVIDENCE-2026-08-15-v0.1",
        "stage": "R7-E0",
        "spec_id": gate.SPEC_ID,
        "spec_sha256": gate_validation["spec_sha256"],
        "execution_spec_sha256": gate.canonical_json_sha256(execution),
        "canonical_version": gate.CANONICAL_VERSION,
        "target": gate.TARGET,
        "target_opaque_token": TARGET_TOKEN,
        "region": gate.REGION,
        "inherited_role": gate.PARENT_ROLE,
        "row_first_conditioned": True,
        "vocabulary_ranking_performed": False,
        "row_first_enrichment_used_as_test_statistic": False,
        "semantic_inputs_used": False,
        "phonetic_inputs_used": False,
        "external_meaning_inputs_used": False,
        "post_reveal_retuning": False,
        "source": {
            "repository": "Hawkar-usls/lineara.xyz",
            "frozen_commit": FROZEN_CORPUS_COMMIT,
            "parsed_documents": len(docs),
            "parse_failures_or_empty": failures,
            "shared_HT_row_first_events": len(shared),
            "shared_frozen_target_events": len(shared_targets),
        },
        "mechanisms": mechanisms,
        "leakage_firewall": {
            "target_selected_after_E0_scores": False,
            "control_word_identity_used_as_feature": False,
            "translation_used": False,
            "lexical_semantics_used": False,
            "phonetics_used": False,
            "language_family_used": False,
            "external_proposed_meaning_used": False,
            "thresholds_retuned_after_evidence": False,
            "operator_changed_after_evidence": False,
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--spec", required=True, type=Path)
    ap.add_argument("--execution-spec", required=True, type=Path)
    ap.add_argument("--c3-result", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    return ap.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    a = parse_args(argv)
    evidence = produce(a.corpus, load_json(a.spec), load_json(a.execution_spec), load_json(a.c3_result))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "R7_E0_EVIDENCE_PRODUCED_NOT_YET_ADMITTED",
        "mechanisms": {
            x["mechanism_id"]: {
                "eligible_target_events": x["eligible_target_events"],
                "observed_score": x["observed_score"],
                "matched_null_mean": x["matched_null_mean"],
                "empirical_p": (1 + x["permutation"]["ge_observed"]) / (1 + x["permutation"]["n"]),
            }
            for x in evidence["mechanisms"]
        },
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
