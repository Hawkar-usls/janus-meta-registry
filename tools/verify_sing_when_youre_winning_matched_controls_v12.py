#!/usr/bin/env python3
import json
import sys
from collections import Counter
from pathlib import Path

PANEL = Path("data/JANUS-SING-WHEN-YOURE-WINNING-PROVENANCE-MATCHED-24-CONTROL-STRESS-PANEL-v1.0.json")
SOURCE = Path("data/JANUS-SING-WHEN-YOURE-WINNING-SOURCE-ONTOLOGY-PROTOCOL-AMENDMENT-v1.2.json")
RECEIPT = Path("data/JANUS-SING-WHEN-YOURE-WINNING-RECEIPT-ONTOLOGY-PROTOCOL-AMENDMENT-v1.1.json")


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def first_break(source, world, receipt):
    if source is None:
        return "UNDETERMINED"
    if source is False:
        return "SOURCE"
    if world is None:
        return "UNDETERMINED"
    if world is False:
        return "WORLD"
    if receipt is None:
        return "UNDETERMINED"
    if receipt is False:
        return "RECEIPT"
    return "NONE"


def main():
    p = load(PANEL)
    s = load(SOURCE)
    r = load(RECEIPT)
    errors = []

    if not s.get("no_silent_rewrite"):
        errors.append("source ontology must preserve no_silent_rewrite")
    if s["primary_visual_source_endpoint"]["name"] != "SOURCE_PHYSICAL_SUBJECT":
        errors.append("unexpected primary visual source endpoint")
    if not r.get("preserves_original_endpoint") or not r.get("no_silent_rewrite"):
        errors.append("receipt amendment must preserve the legacy endpoint explicitly")
    if r["chain_endpoints"]["CHAIN_LEGACY_BROAD"]["status"] != "PRIMARY_FALSIFICATION_ENDPOINT_FOR_THE_ORIGINAL_BROAD_HYPOTHESIS":
        errors.append("legacy broad chain lost its falsification status")
    if r["chain_endpoints"]["CHAIN_OUTCOME_RECEIPT"]["status"] != "NEW_SECONDARY_HYPOTHESIS_TO_BE_TESTED_SEPARATELY":
        errors.append("outcome chain must remain secondary/new")

    controls = p["controls"]
    ids = [x["id"] for x in controls]
    if len(ids) != len(set(ids)):
        errors.append("duplicate control IDs")
    if len(controls) < 20:
        errors.append("matched-control minimum not reached")

    broad_breaks = Counter()
    outcome_breaks = Counter()
    cluster_counts = Counter()
    physical_pass = 0
    world_pass = 0
    world_fail = 0
    broad_true = broad_false = broad_null = 0
    outcome_true = outcome_false = outcome_null = 0
    broad_chain_true = broad_chain_world_fail = broad_chain_null = 0
    outcome_chain_true = outcome_chain_false = 0

    for x in controls:
        cluster_counts[x["cluster"]] += 1
        src = x.get("source_physical_subject")
        world = x.get("one_world")
        broad = x.get("receipt_broad_anchor_legacy")
        outcome = x.get("receipt_outcome_bearing")
        bb = first_break(src, world, broad)
        ob = first_break(src, world, outcome)
        broad_breaks[bb] += 1
        outcome_breaks[ob] += 1
        if x.get("first_break_physical_legacy_broad") != bb:
            errors.append(f"{x['id']}: stored legacy break != derived {bb}")
        if x.get("first_break_physical_outcome") != ob:
            errors.append(f"{x['id']}: stored outcome break != derived {ob}")
        physical_pass += int(src is True)
        world_pass += int(world is True)
        world_fail += int(world is False)
        broad_true += int(broad is True)
        broad_false += int(broad is False)
        broad_null += int(broad is None)
        outcome_true += int(outcome is True)
        outcome_false += int(outcome is False)
        outcome_null += int(outcome is None)
        if src is True and world is True and broad is True:
            broad_chain_true += 1
        elif src is True and world is False:
            broad_chain_world_fail += 1
        elif src is True and world is True and broad is None:
            broad_chain_null += 1
        if src is True and world is True and outcome is True:
            outcome_chain_true += 1
        else:
            outcome_chain_false += 1

    d = p["derived_counts"]
    expected = {
        "controls_n": len(controls),
        "creator_or_series_clusters_n": len(cluster_counts),
        "source_physical_subject_pass": physical_pass,
        "one_world_pass": world_pass,
        "one_world_fail": world_fail,
        "legacy_broad_receipt_true": broad_true,
        "legacy_broad_receipt_false": broad_false,
        "legacy_broad_receipt_undetermined": broad_null,
        "outcome_bearing_receipt_true": outcome_true,
        "outcome_bearing_receipt_false": outcome_false,
        "chain_legacy_broad_true": broad_chain_true,
        "chain_legacy_broad_false_by_world": broad_chain_world_fail,
        "chain_legacy_broad_undetermined": broad_chain_null,
        "chain_outcome_receipt_true": outcome_chain_true,
        "chain_outcome_receipt_false": outcome_chain_false,
    }
    for k, v in expected.items():
        if d.get(k) != v:
            errors.append(f"derived_counts.{k}: stored={d.get(k)!r}, derived={v!r}")

    for label in ["NONE", "SOURCE", "WORLD", "RECEIPT", "UNDETERMINED"]:
        if d["first_break_physical_legacy_broad"].get(label, 0) != broad_breaks.get(label, 0):
            errors.append(f"legacy break count mismatch for {label}")
        if d["first_break_physical_outcome"].get(label, 0) != outcome_breaks.get(label, 0):
            errors.append(f"outcome break count mismatch for {label}")

    target = p["target_reference"]
    if not (target["chain_legacy_broad"] and target["chain_outcome_receipt"]):
        errors.append("target reference must preserve both frozen chain classifications")
    if broad_chain_true == 0:
        errors.append("stress panel failed to contain a direct legacy broad-chain counterexample")
    if outcome_chain_true != 0:
        errors.append("panel summary assumes no matched outcome-chain control; revise artifact if one is added")

    report = {
        "artifact_id": p["artifact_id"],
        "controls": len(controls),
        "clusters": len(cluster_counts),
        "legacy_broad_full_chain_controls": broad_chain_true,
        "outcome_full_chain_controls": outcome_chain_true,
        "first_break_legacy": {k: broad_breaks.get(k, 0) for k in ["NONE", "SOURCE", "WORLD", "RECEIPT", "UNDETERMINED"]},
        "first_break_outcome": {k: outcome_breaks.get(k, 0) for k in ["NONE", "SOURCE", "WORLD", "RECEIPT", "UNDETERMINED"]},
        "errors": errors,
        "ok": not errors,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
