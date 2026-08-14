#!/usr/bin/env python3
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T1 = ROOT / "data/JANUS-SING-WHEN-YOURE-WINNING-SPORTS-MVP-PREVALENCE-TRANCHE-01-v1.0.json"
T2 = ROOT / "data/JANUS-SING-WHEN-YOURE-WINNING-SPORTS-MVP-PREVALENCE-TRANCHE-02-v1.0.json"


def load(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def expected_first_break(r):
    s = r.get("source_physical_subject")
    w = r.get("one_world")
    o = r.get("receipt_outcome_bearing")
    if s is None:
        return "UNDETERMINED"
    if s is False:
        return "SOURCE"
    if w is None:
        return "UNDETERMINED"
    if w is False:
        return "WORLD"
    if o is None:
        return "UNDETERMINED"
    if o is False:
        return "RECEIPT"
    return "NONE"


def chain_value(r):
    vals = [r.get("source_physical_subject"), r.get("one_world"), r.get("receipt_outcome_bearing")]
    if any(v is None for v in vals):
        return None
    return all(vals)


def summarize(records):
    resolved = [r for r in records if chain_value(r) is not None]
    breaks = Counter(expected_first_break(r) for r in resolved)
    return {
        "records": len(records),
        "resolved_records": len(resolved),
        "pending_source_count": sum(r.get("source_physical_subject") is None for r in records),
        "full_chain_resolved": sum(chain_value(r) is True for r in resolved),
        "world_break_resolved": breaks["WORLD"],
        "source_break_resolved": breaks["SOURCE"],
        "receipt_break_resolved": breaks["RECEIPT"],
        "exactly_five_visible_resolved": sum(r.get("visible_same_subject_instances") == 5 for r in resolved),
        "exactly_five_full_chain_resolved": sum(
            r.get("visible_same_subject_instances") == 5 and chain_value(r) is True for r in resolved
        ),
    }


def main():
    t1 = load(T1)
    t2 = load(T2)
    errors = []

    ids1 = {r["id"] for r in t1["controls"]}
    ids2 = {r["id"] for r in t2["controls"]}
    if ids1 & ids2:
        errors.append(f"duplicate IDs across tranches: {sorted(ids1 & ids2)}")

    for r in t2["controls"]:
        derived_break = expected_first_break(r)
        recorded_break = r.get("first_break_physical_outcome")
        if recorded_break != derived_break:
            errors.append(f"{r['id']}: first_break recorded={recorded_break} derived={derived_break}")
        derived_chain = chain_value(r)
        if r.get("chain_outcome_receipt") is not derived_chain:
            errors.append(f"{r['id']}: chain recorded={r.get('chain_outcome_receipt')} derived={derived_chain}")
        if r.get("visible_same_subject_instances") == 5 and r.get("source_physical_subject") is not True:
            errors.append(f"{r['id']}: exact-five visible count without SOURCE_PHYSICAL_SUBJECT=true")

    s2 = summarize(t2["controls"])
    if s2 != t2["derived_counts"]:
        errors.append(f"tranche2 counts mismatch: derived={s2} recorded={t2['derived_counts']}")

    combined = t1["controls"] + t2["controls"]
    cumulative = summarize(combined)
    if cumulative != t2["cumulative_after_tranche_02"]:
        errors.append(
            f"cumulative counts mismatch: derived={cumulative} recorded={t2['cumulative_after_tranche_02']}"
        )

    # Anti-rescue / falsification-preservation checks.
    if cumulative["full_chain_resolved"] < 10:
        errors.append("full-chain counterexamples were lost; expected at least 10 cumulative hits")
    if cumulative["exactly_five_full_chain_resolved"] < 1:
        errors.append("near-isomorphic exactly-five full-chain counterexample was lost")
    if s2["exactly_five_visible_resolved"] < 10:
        errors.append("second tranche no longer contains the intended exact-five stress layer")
    sportsnet = next((r for r in t2["controls"] if r["id"] == "MP-029"), None)
    if not sportsnet or sportsnet.get("chain_outcome_receipt") is not True:
        errors.append("MP-029 non-memorabilia full-chain counterexample must be preserved")
    if t2["epistemic_ceiling"].get("population_prevalence_claim") is not False:
        errors.append("population prevalence claim ceiling must remain false")

    out = {
        "artifact_id": t2["artifact_id"],
        "tranche_02": s2,
        "cumulative": cumulative,
        "errors": errors,
        "ok": not errors,
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
