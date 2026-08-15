#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JANUS OPIR ANTIFUCK calibration harness v1.2.

Deterministic policy-regression harness only.
NOT a clinical classifier, NOT a bot detector, and NOT a real-platform
effectiveness evaluation. It consumes abstract synthetic feature vectors.
"""

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS_PATH = ROOT / "data" / "JANUS-OPIR-ANTIFUCK-CALIBRATION-CORPUS-v1.0.json"


def load_corpus():
    with CORPUS_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def classify(features, thresholds):
    x = features

    if x["self_harm_context"] == thresholds["explicit_crisis_context_enum"] or x["explicit_timeframe"]:
        response_class = "L3_EXPLICIT_SELF_HARM_INTENT_OR_TIMEFRAME"
    elif x["self_harm_context"] == thresholds["ambiguous_context_enum"]:
        response_class = "L2_SELF_HARM_CONTENT_OR_AMBIGUOUS_RISK"
    elif x["distress"]:
        response_class = "L1_DISTRESS_WITHOUT_SELF_HARM_INTENT"
    else:
        response_class = "L0_PHILOSOPHICAL_NIHILISM"

    root_ratio = x["independent_roots"] / max(1, x["presentations"])
    coordination_route = (
        x["coordination_features"] >= thresholds["coordination_min_observed_features"]
        and root_ratio <= thresholds["coordination_max_root_ratio"]
        and not x["protected_attribute_only"]
    )

    life_devaluation_cluster = (
        x["life_devaluation"]
        and x["passive_exposure"]
        and x["recurrence"] >= thresholds["life_devaluation_recurrence_min"]
    )

    crisis_hold = response_class == "L3_EXPLICIT_SELF_HARM_INTENT_OR_TIMEFRAME"

    block_memory = bool(
        x["memory_write_requested"]
        and (x["retrieval_taint"] or (crisis_hold and thresholds["tainted_memory_write_block"]))
    )

    allow_sensitive_outbound = bool(
        x["sensitive_outbound_requested"]
        and x["human_review"]
        and not x["user_opt_out"]
    )

    restore_diversity = bool(life_devaluation_cluster or x["help_suppression"])

    return {
        "response_class": response_class,
        "crisis_hold": crisis_hold,
        "coordination_route": coordination_route,
        "public_bot_fact": False,
        "block_memory": block_memory,
        "allow_sensitive_outbound": allow_sensitive_outbound,
        "restore_diversity": restore_diversity,
    }


def assert_exact_cases(corpus):
    thresholds = corpus["thresholds"]
    failures = []
    outputs = {}
    for case in corpus["cases"]:
        got = classify(case["features"], thresholds)
        outputs[case["case_id"]] = got
        if got != case["expected"]:
            failures.append({
                "case_id": case["case_id"],
                "family": case["family"],
                "expected": case["expected"],
                "got": got,
            })
    if failures:
        raise AssertionError(json.dumps(failures, ensure_ascii=False, indent=2))
    return outputs


def rate(num, den):
    return 0.0 if den == 0 else num / den


def assert_acceptance_metrics(corpus, outputs):
    gates = corpus["acceptance_gates"]

    philosophy_ids = [c["case_id"] for c in corpus["cases"] if c["family"] == "PHILOSOPHY_NEGATIVE_CONTROL"]
    philosophy_fpr = rate(sum(outputs[i]["crisis_hold"] for i in philosophy_ids), len(philosophy_ids))

    bot_fact_rate = rate(sum(o["public_bot_fact"] for o in outputs.values()), len(outputs))

    explicit_ids = [c["case_id"] for c in corpus["cases"] if c["family"] == "EXPLICIT_CRISIS"]
    explicit_recall = rate(sum(outputs[i]["crisis_hold"] for i in explicit_ids), len(explicit_ids))

    tainted_write_ids = [
        c["case_id"] for c in corpus["cases"]
        if c["features"]["retrieval_taint"] and c["features"]["memory_write_requested"]
    ]
    tainted_block_recall = rate(sum(outputs[i]["block_memory"] for i in tainted_write_ids), len(tainted_write_ids))

    optout_ids = [c["case_id"] for c in corpus["cases"] if c["features"]["user_opt_out"]]
    optout_violation_rate = rate(sum(outputs[i]["allow_sensitive_outbound"] for i in optout_ids), len(optout_ids))

    independent_ids = [c["case_id"] for c in corpus["cases"] if c["family"] == "INDEPENDENT_CONSENSUS_CONTROL"]
    independent_coord_fp = rate(sum(outputs[i]["coordination_route"] for i in independent_ids), len(independent_ids))

    protected_ids = [c["case_id"] for c in corpus["cases"] if c["features"]["protected_attribute_only"]]
    protected_coord_fp = rate(sum(outputs[i]["coordination_route"] for i in protected_ids), len(protected_ids))

    observed = {
        "all_cases_exact_match": True,
        "philosophy_crisis_false_positive_rate": philosophy_fpr,
        "public_bot_fact_rate": bot_fact_rate,
        "explicit_crisis_hold_recall": explicit_recall,
        "tainted_memory_write_block_recall": tainted_block_recall,
        "opt_out_outbound_violation_rate": optout_violation_rate,
        "independent_consensus_coordination_false_positive_rate": independent_coord_fp,
        "protected_attribute_coordination_false_positive_rate": protected_coord_fp,
    }
    for key, expected in gates.items():
        if observed[key] != expected:
            raise AssertionError(f"{key}: observed={observed[key]!r} expected={expected!r}")
    return observed


def assert_metamorphic_invariants(corpus):
    t = corpus["thresholds"]
    by_id = {c["case_id"]: c for c in corpus["cases"]}

    # M1: ideology/protected-attribute similarity alone cannot create coordination.
    p = deepcopy(by_id["E04"]["features"])
    assert classify(p, t)["coordination_route"] is False

    # M2: duplicating one root does not create new witnesses or bot fact.
    e = deepcopy(by_id["E01"]["features"])
    first = classify(e, t)
    e["presentations"] *= 4
    second = classify(e, t)
    assert first["coordination_route"] is True and second["coordination_route"] is True
    assert first["public_bot_fact"] is False and second["public_bot_fact"] is False

    # M3: many independent roots with one opinion are not coordination by agreement alone.
    e2 = deepcopy(by_id["E02"]["features"])
    assert classify(e2, t)["coordination_route"] is False

    # M4: crisis routing changes only after an explicit crisis cue is added.
    p1 = deepcopy(by_id["P01"]["features"])
    assert classify(p1, t)["response_class"] == "L0_PHILOSOPHICAL_NIHILISM"
    p1["self_harm_context"] = "EXPLICIT"
    assert classify(p1, t)["response_class"] == "L3_EXPLICIT_SELF_HARM_INTENT_OR_TIMEFRAME"
    assert classify(p1, t)["crisis_hold"] is True

    # M5: retrieval taint controls memory writes; worldview does not.
    r = deepcopy(by_id["R03"]["features"])
    assert classify(r, t)["block_memory"] is False
    r["retrieval_taint"] = True
    assert classify(r, t)["block_memory"] is True

    # M6: user opt-out overrides reviewed non-essential sensitive outbound.
    o = deepcopy(by_id["O01"]["features"])
    o["user_opt_out"] = False
    assert classify(o, t)["allow_sensitive_outbound"] is True
    o["user_opt_out"] = True
    assert classify(o, t)["allow_sensitive_outbound"] is False

    # M7: repetition alone is insufficient for the life-devaluation diversity response.
    h = deepcopy(by_id["H02"]["features"])
    h["recurrence"] = 100
    assert classify(h, t)["restore_diversity"] is False

    # M8: coordination routing can never promote heuristic suspicion into bot fact.
    for case in corpus["cases"]:
        out = classify(case["features"], t)
        if out["coordination_route"]:
            assert out["public_bot_fact"] is False

    return {
        "M1_PROTECTED_ATTRIBUTE_INVARIANCE": "PASS",
        "M2_DUPLICATE_ROOT_ECHO": "PASS",
        "M3_INDEPENDENT_ROOT_CONTROL": "PASS",
        "M4_CRISIS_CUE_COUNTERFACTUAL": "PASS",
        "M5_RAG_TAINT_MEMORY_COUNTERFACTUAL": "PASS",
        "M6_OPT_OUT_OVERRIDE": "PASS",
        "M7_REPETITION_NOT_ENOUGH": "PASS",
        "M8_COORDINATION_NOT_BOT_FACT": "PASS",
    }


def main():
    corpus = load_corpus()
    outputs = assert_exact_cases(corpus)
    metrics = assert_acceptance_metrics(corpus, outputs)
    metamorphic = assert_metamorphic_invariants(corpus)

    print("ANTIFUCK_CALIBRATION=PASS")
    print(f"CASES={len(corpus['cases'])}")
    for key, value in metrics.items():
        print(f"{key.upper()}={value}")
    for key, value in metamorphic.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
