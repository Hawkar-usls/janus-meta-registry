#!/usr/bin/env python3
"""R7-F1 post-F0 terminal numeric slot refinement for KU-RO.

N|END is explicitly a post-F0 training-derived candidate, not a fresh confirmatory
hypothesis. The test controls this selection by evaluating N|END against a max-stat
object-preserving null over the complete frozen 16-signature TWO_KIND family.
No lexical meaning or TOTAL/SUMMARY semantics can be established here.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import janus_linear_a_r7_arithmetic_summary_role_v0_1 as b0
import janus_linear_a_r7_f0_ku_ro_downstream_slot_v0_1 as f0

SPEC_ID = "JANUS-LINEAR-A-R7-F1-TERMINAL-NUMERIC-SLOT-2026-08-16-v0.1"
CORPUS_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
TARGET = "KU-RO"
TARGET_TOKEN = "6a2ea59b95fe1b610d20"
REGION = "HT"
CANDIDATE = "N|END"
NULL_N = 10000
NULL_SEED = 71601


class F1Error(ValueError):
    pass


def require(ok: bool, msg: str) -> None:
    if not ok:
        raise F1Error(msg)


def load_json(path: Path) -> Dict[str, Any]:
    x = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(x, dict), f"{path}: top level must be object")
    return x


def validate(spec: Mapping[str, Any], cert: Mapping[str, Any], canonical: Mapping[str, Any]) -> None:
    require(spec.get("spec_id") == SPEC_ID, "spec id mismatch")
    require(spec.get("stage") == "R7-F1", "stage mismatch")
    require(spec.get("status") == "PREREGISTERED_BEFORE_F1_SCORING", "spec not frozen")
    require(canonical.get("version") == "v2.30" and canonical.get("status") == "CURRENT_CANONICAL_RESEARCH_STATE", "canonical mismatch")
    require(canonical.get("canonicality", {}).get("canonicality_audit_status") == "CANONICALITY_AUDIT_PASS", "canonical audit not pass")
    parent = spec.get("parent", {})
    require(parent.get("canonical_version") == "v2.30", "parent canonical drift")
    require(parent.get("target") == TARGET and parent.get("opaque_target_token") == TARGET_TOKEN, "target drift")
    require(parent.get("region") == REGION and parent.get("retained_parent_role") == "ROW-OPENING-LIKE", "role/region drift")
    require(parent.get("F0_status") == "CROSS_FITTED_KU_RO_DOWNSTREAM_SLOT_ORGANIZATION_ESTABLISHED", "parent F0 status drift")
    require(parent.get("F0_admitted_family") == "TWO-SLOT-DOWNSTREAM-TEMPLATE-CONSTRAINT", "F0 family drift")
    require(cert.get("status") == parent.get("F0_status"), "F0 certificate status mismatch")
    require(cert.get("parent", {}).get("target") == TARGET and cert.get("parent", {}).get("opaque_target_token") == TARGET_TOKEN, "F0 certificate target mismatch")
    require(cert.get("admission", {}).get("admitted_constraint_labels") == [parent.get("F0_admitted_family")], "F0 certificate family mismatch")
    source = spec.get("source", {})
    require(source.get("frozen_commit") == CORPUS_COMMIT, "corpus commit drift")
    require(source.get("internal_corpus_status") == "DEVELOPMENT_CORPUS_PREVIOUSLY_ACCESSED", "development corpus label required")
    cand = spec.get("post_F0_candidate", {})
    require(cand.get("signature") == CANDIDATE, "candidate drift")
    require(cand.get("confirmatory_independence_on_same_corpus") is False, "same-corpus independence forbidden")
    null = spec.get("structure_destroying_null", {})
    require(null.get("permutations") == NULL_N and null.get("seed") == NULL_SEED, "null settings drift")
    require(null.get("familywise_statistic") == "maximum object-weighted positive signature effect over all 16 TWO_KIND signatures per permutation", "max-stat family drift")
    require(spec.get("effect_gates", {}).get("N_END_must_be_largest_observed_positive_signature_effect") is True, "candidate dominance gate missing")
    anti = spec.get("anti_flexibility", {})
    require(anti and all(v is True for v in anti.values()), "anti-flexibility must be all true")
    ceiling = spec.get("claim_ceiling", {})
    require(ceiling.get("TOTAL_or_SUMMARY_semantic_function_established") is False, "semantic ceiling violation")
    for key in ("exact_word_meaning_established", "translation_established", "phonetic_value_established", "language_family_established", "new_anchor_established", "universal_cross_region_function_established", "external_replication_established", "decipherment_established"):
        require(ceiling.get(key) is False, f"claim ceiling violation: {key}")


def object_groups(events: Sequence[Mapping[str, Any]]) -> Dict[str, List[int]]:
    out: Dict[str, List[int]] = defaultdict(list)
    for i, e in enumerate(events):
        out[e["object_id"]].append(i)
    return dict(out)


def two_kind(bundle: Sequence[str]) -> str:
    return str(bundle[2])


def exchangeable_objects(events: Sequence[Mapping[str, Any]]) -> List[str]:
    by = object_groups(events)
    out = []
    for oid, idxs in by.items():
        t = sum(bool(events[i]["is_target"]) for i in idxs)
        b = len(idxs) - t
        if t > 0 and b > 0:
            out.append(oid)
    return sorted(out)


def signature_effects(events: Sequence[Mapping[str, Any]], bundles: Sequence[Tuple[str, str, str]], objects: Sequence[str], signatures: Sequence[str]) -> Dict[str, Any]:
    by = object_groups(events)
    sig_effects: Dict[str, List[float]] = {s: [] for s in signatures}
    object_detail = []
    for oid in objects:
        idxs = by[oid]
        ti = [i for i in idxs if events[i]["is_target"]]
        bi = [i for i in idxs if not events[i]["is_target"]]
        require(ti and bi, "nonexchangeable object entered effect calculation")
        row = {"object_id": oid, "target_events": len(ti), "background_events": len(bi), "signature_effects": {}}
        for s in signatures:
            tp = sum(two_kind(bundles[i]) == s for i in ti) / len(ti)
            bp = sum(two_kind(bundles[i]) == s for i in bi) / len(bi)
            d = tp - bp
            sig_effects[s].append(d)
            row["signature_effects"][s] = {"target_prevalence": tp, "background_prevalence": bp, "effect": d}
        object_detail.append(row)
    agg = {}
    for s in signatures:
        vals = sig_effects[s]
        agg[s] = {
            "object_weighted_effect": sum(vals) / len(vals),
            "positive_object_fraction": sum(v > 0 for v in vals) / len(vals),
            "exchangeable_objects": len(vals),
        }
    return {"aggregate": agg, "object_detail": object_detail}


def permuted_bundles(original: Sequence[Tuple[str, str, str]], by_object: Mapping[str, Sequence[int]], rng: random.Random) -> List[Tuple[str, str, str]]:
    out = list(original)
    for idxs in by_object.values():
        if len(idxs) <= 1:
            continue
        vals = [original[i] for i in idxs]
        rng.shuffle(vals)
        for i, v in zip(idxs, vals):
            out[i] = v
    return out


def loo_positive_fraction(events: Sequence[Mapping[str, Any]], bundles: Sequence[Tuple[str, str, str]], objects: Sequence[str], signatures: Sequence[str], signature: str) -> Tuple[float, List[Dict[str, Any]]]:
    rows = []
    for drop in objects:
        keep = [o for o in objects if o != drop]
        effect = signature_effects(events, bundles, keep, signatures)["aggregate"][signature]["object_weighted_effect"]
        rows.append({"dropped_object": drop, "object_weighted_effect": effect, "positive": effect > 0})
    frac = sum(x["positive"] for x in rows) / len(rows) if rows else 0.0
    return frac, rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--f0-certificate", required=True)
    ap.add_argument("--canonical", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    spec = load_json(Path(a.spec)); cert = load_json(Path(a.f0_certificate)); canonical = load_json(Path(a.canonical))
    validate(spec, cert, canonical)
    docs, reveal, failures = b0.load_corpus(Path(a.corpus))
    events = f0.build_events(docs)
    targets = [e for e in events if e["is_target"]]
    target_objects = Counter(e["object_id"] for e in targets)
    by_object = object_groups(events)
    exch_objects = exchangeable_objects(events)
    exch_set = set(exch_objects)
    exchangeable_target_events = sum(1 for e in targets if e["object_id"] in exch_set)
    exch_fraction = exchangeable_target_events / len(targets) if targets else 0.0
    max_object_fraction = max(target_objects.values()) / len(targets) if targets else 1.0

    support_cfg = spec["support_gates"]
    support_checks = {
        "minimum_target_events": len(targets) >= support_cfg["minimum_target_events"],
        "minimum_target_physical_objects": len(target_objects) >= support_cfg["minimum_target_physical_objects"],
        "minimum_exchangeable_target_event_fraction": exch_fraction >= support_cfg["minimum_exchangeable_target_event_fraction"],
        "maximum_single_target_object_event_fraction": max_object_fraction <= support_cfg["maximum_single_target_object_event_fraction"],
        "minimum_exchangeable_target_objects": len(exch_objects) >= support_cfg["minimum_exchangeable_target_objects"],
    }
    support_pass = all(support_checks.values())

    signatures = list(f0.fixed_support("TWO_KIND") or ())
    require(len(signatures) == 16 and CANDIDATE in signatures, "frozen TWO_KIND support mismatch")
    original = [tuple(e["bundle"]) for e in events]
    observed = signature_effects(events, original, exch_objects, signatures)
    agg = observed["aggregate"]
    nend = agg[CANDIDATE]
    target_nend_prevalence = sum(two_kind(e["bundle"]) == CANDIDATE for e in targets) / len(targets) if targets else 0.0
    other_max = max(v["object_weighted_effect"] for s, v in agg.items() if s != CANDIDATE)
    largest_observed = nend["object_weighted_effect"] >= other_max
    loo_fraction, loo_rows = loo_positive_fraction(events, original, exch_objects, signatures, CANDIDATE)

    effect_cfg = spec["effect_gates"]
    effect_checks = {
        "minimum_target_N_END_prevalence": target_nend_prevalence >= effect_cfg["minimum_target_N_END_prevalence"],
        "minimum_object_weighted_effect": nend["object_weighted_effect"] >= effect_cfg["minimum_object_weighted_effect"],
        "minimum_positive_object_fraction": nend["positive_object_fraction"] >= effect_cfg["minimum_positive_object_fraction"],
        "minimum_leave_one_object_out_positive_fraction": loo_fraction >= effect_cfg["minimum_leave_one_object_out_positive_fraction"],
        "N_END_is_largest_observed_positive_signature_effect": largest_observed,
    }
    effect_pass = all(effect_checks.values())

    rng = random.Random(NULL_SEED)
    ge = 0
    max_sum = 0.0
    candidate_ge = 0
    candidate_sum = 0.0
    obs_stat = nend["object_weighted_effect"]
    for _ in range(NULL_N):
        shuffled = permuted_bundles(original, by_object, rng)
        pa = signature_effects(events, shuffled, exch_objects, signatures)["aggregate"]
        max_stat = max(0.0, max(v["object_weighted_effect"] for v in pa.values()))
        cand_stat = pa[CANDIDATE]["object_weighted_effect"]
        max_sum += max_stat; candidate_sum += cand_stat
        if max_stat >= obs_stat - 1e-15:
            ge += 1
        if cand_stat >= obs_stat - 1e-15:
            candidate_ge += 1
    fwer_p = (1 + ge) / (1 + NULL_N)
    raw_candidate_p = (1 + candidate_ge) / (1 + NULL_N)
    null_pass = fwer_p <= spec["structure_destroying_null"]["empirical_FWER_p_max"]

    admitted = bool(support_pass and effect_pass and null_pass)
    status = "INTERNAL_POST_F0_TERMINAL_NUMERIC_SLOT_REFINEMENT_ADMITTED" if admitted else "TERMINAL_NUMERIC_SLOT_REFINEMENT_NOT_ESTABLISHED_RETAIN_ROW_OPENING_LIKE"
    signature_ranking = sorted(
        ({"signature": s, **agg[s]} for s in signatures),
        key=lambda x: (-x["object_weighted_effect"], x["signature"]),
    )
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R7-F1-TERMINAL-NUMERIC-SLOT-RESULT-2026-08-16-v0.1",
        "stage": "R7-F1",
        "status": status,
        "parent": {"canonical_version": "v2.30", "target": TARGET, "region": REGION, "retained_parent_role": "ROW-OPENING-LIKE", "F0_status": cert["status"]},
        "source": {"repository": "Hawkar-usls/lineara.xyz", "frozen_commit": CORPUS_COMMIT, "parsed_documents": len(docs), "parse_failures_or_empty": failures, "internal_corpus_status": "DEVELOPMENT_CORPUS_PREVIOUSLY_ACCESSED"},
        "support": {
            "target_events": len(targets), "target_physical_objects": len(target_objects), "exchangeable_target_events": exchangeable_target_events,
            "exchangeable_target_event_fraction": exch_fraction, "exchangeable_target_objects": len(exch_objects),
            "maximum_single_target_object_event_fraction": max_object_fraction, "checks": support_checks, "support_pass": support_pass,
        },
        "candidate": {
            "signature": CANDIDATE, "post_F0_training_derived": True, "same_corpus_independent_confirmation": False,
            "target_prevalence_all_target_events": target_nend_prevalence,
            "object_weighted_effect": nend["object_weighted_effect"], "positive_object_fraction": nend["positive_object_fraction"],
            "leave_one_object_out_positive_fraction": loo_fraction, "leave_one_object_out": loo_rows,
            "largest_observed_positive_signature_effect": largest_observed, "effect_checks": effect_checks, "effect_pass": effect_pass,
        },
        "all_TWO_KIND_signature_effects": signature_ranking,
        "structure_destroying_null": {
            "operator": spec["structure_destroying_null"]["operator"], "permutations": NULL_N, "seed": NULL_SEED,
            "observed_N_END_object_weighted_effect": obs_stat, "candidate_only_null_mean": candidate_sum / NULL_N,
            "candidate_only_raw_empirical_p": raw_candidate_p, "max_stat_null_mean": max_sum / NULL_N,
            "max_stat_ge_observed": ge, "familywise_empirical_p": fwer_p, "familywise_p_threshold": spec["structure_destroying_null"]["empirical_FWER_p_max"],
            "familywise_null_pass": null_pass,
        },
        "admission": {
            "internal_post_F0_terminal_numeric_slot_refinement_established": admitted,
            "admitted_refinement_label": "ROW-OPENING-WITH-TERMINAL-NUMERIC-SLOT-LIKE" if admitted else None,
            "claim": (
                "Within the previously accessed frozen HT development corpus, KU-RO row-opening events are internally supported as enriched for a one-numeric-item-then-row-end downstream pattern under an all-signature max-stat object-preserving null. This is a post-F0 structural refinement, not independent replication or lexical semantics."
                if admitted else
                "R7-F1 does not establish the post-F0 terminal numeric slot refinement; retain canonical KU-RO ROW-OPENING-LIKE only."
            ),
        },
        "epistemic_gate": {
            "parent_probable_region_scoped_ROW_OPENING_LIKE_retained": True,
            "internal_post_F0_terminal_numeric_slot_refinement_established": admitted,
            "independent_replication_established": False,
            "TOTAL_or_SUMMARY_semantic_function_established": False,
            "exact_word_meaning_established": False,
            "translation_established": False,
            "phonetic_value_established": False,
            "language_family_established": False,
            "new_anchor_established": False,
            "universal_cross_region_function_established": False,
            "external_replication_established": False,
            "decipherment_established": False,
        },
        "next_gate": (
            "If admitted, freeze the structural refinement but require a new untouched/external corpus for confirmatory mechanistic promotion; internal work may only characterize numeric-value distributions without assigning TOTAL/SUMMARY semantics."
            if admitted else
            "Preserve negative and retain ROW-OPENING-LIKE without terminal-numeric refinement."
        ),
        "claim_ceiling": spec["claim_ceiling"],
    }
    Path(a.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status, "target_events": len(targets), "target_objects": len(target_objects), "exchangeable_objects": len(exch_objects),
        "N_END_prevalence": target_nend_prevalence, "N_END_effect": nend["object_weighted_effect"], "positive_object_fraction": nend["positive_object_fraction"],
        "LOO_positive_fraction": loo_fraction, "familywise_p": fwer_p, "admitted": admitted,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
