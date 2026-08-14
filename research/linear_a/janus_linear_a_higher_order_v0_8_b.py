#!/usr/bin/env python3
"""JANUS Linear A v0.8 Implementation B.

Higher-order WORD_ONLY row-aware relation discovery with three complementary destructive
nulls and studentized max-T family-wise control. The implementation is deliberately
architecturally distinct from v0.8-A while consuming the same v0.6.2 typed-token baseline.

Frozen execution spec:
  data/JANUS-LINEAR-A-V0.8-IMPLEMENTATION-B-EXECUTION-SPEC-2026-08-14-v1.0.json

No new-anchor, lexical, decipherment, or external-replication claim can be emitted here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_formula_transition as b7

VERSION = "JANUS-LINA-HIGHER-ORDER-v0.8-B"
SPEC = "data/JANUS-LINEAR-A-V0.8-IMPLEMENTATION-B-EXECUTION-SPEC-2026-08-14-v1.0.json"
SPEC_COMMIT = "2f45e76977ec209a8bc1f3697db4991fc3317017"
NUMERIC_KINDS = {"N", "N_UNCERTAIN"}


def deterministic_partition(doc_id: str) -> str:
    h = int(hashlib.sha256(f"JANUS-LINA-v0.8B|{doc_id}".encode()).hexdigest()[:8], 16)
    return "HT_SCREEN" if h % 5 in {0, 1, 2} else "HT_CONFIRM"


def numeric_bucket(slot: dict) -> str:
    if slot["kind"] == "N_UNCERTAIN":
        return "UNCERTAIN"
    v = float(slot["value"])
    if v < 1:
        return "FRAC"
    if v == 1:
        return "ONE"
    if v < 5:
        return "2_4"
    if v < 10:
        return "5_9"
    return "10PLUS"


def pair_events_for_row(slots):
    n = len(slots)
    if n >= 2 and slots[0]["kind"] == "T" and slots[1]["kind"] == "T":
        yield ("ROW_PREFIX_TT", "NONE", slots[0]["id"], slots[1]["id"])
    if n >= 2 and slots[-2]["kind"] == "T" and slots[-1]["kind"] == "T":
        yield ("ROW_SUFFIX_TT", "NONE", slots[-2]["id"], slots[-1]["id"])
    for i in range(n - 2):
        a, m, c = slots[i], slots[i + 1], slots[i + 2]
        if a["kind"] == "T" and m["kind"] == "T" and c["kind"] == "T":
            yield ("TTT_CONTEXT_EDGE", m["id"], a["id"], c["id"])
        if a["kind"] == "T" and m["kind"] in NUMERIC_KINDS and c["kind"] == "T":
            yield ("TBT_NUMERIC_BUCKET_EDGE", numeric_bucket(m), a["id"], c["id"])


def adjacency_events_for_row(slots):
    for a, b in zip(slots, slots[1:]):
        if a["kind"] == "T" and b["kind"] == "T":
            yield a["id"], b["id"]


def endpoint_eligibility(docs, min_occurrences, min_docs):
    counts = Counter()
    docs_by = defaultdict(set)
    for doc in docs:
        for row in doc["rows"]:
            for s in row["slots"]:
                if s["kind"] == "T":
                    counts[s["id"]] += 1
                    docs_by[s["id"]].add(doc["doc"])
    eligible = {cid for cid, n in counts.items() if n >= min_occurrences and len(docs_by[cid]) >= min_docs}
    return eligible, counts, {k: len(v) for k, v in docs_by.items()}


def build_stats(docs, eligible, with_context=False):
    pair_counts = Counter()
    pair_left = Counter()
    pair_right = Counter()
    pair_totals = Counter()
    pair_docs = defaultdict(set)
    pair_regions = defaultdict(set)
    incoming = defaultdict(Counter)
    outgoing = defaultdict(Counter)
    spec_docs = defaultdict(set)
    spec_regions = defaultdict(set)

    for doc in docs:
        for row in doc["rows"]:
            slots = row["slots"]
            for family, context, a, b in pair_events_for_row(slots):
                if a not in eligible or b not in eligible or a == b:
                    continue
                if family == "TTT_CONTEXT_EDGE" and context not in eligible:
                    continue
                rel = (family, context)
                key = ("PAIR", family, context, a, b)
                pair_counts[key] += 1
                pair_left[(rel, a)] += 1
                pair_right[(rel, b)] += 1
                pair_totals[rel] += 1
                if with_context:
                    pair_docs[key].add(doc["doc"])
                    pair_regions[key].add(doc["region"])

            for pred, succ in adjacency_events_for_row(slots):
                if pred not in eligible or succ not in eligible:
                    continue
                outgoing[pred][succ] += 1
                incoming[succ][pred] += 1
                if with_context:
                    spec_docs[("SPEC", "OUT", pred)].add(doc["doc"])
                    spec_regions[("SPEC", "OUT", pred)].add(doc["region"])
                    spec_docs[("SPEC", "IN", succ)].add(doc["doc"])
                    spec_regions[("SPEC", "IN", succ)].add(doc["region"])

    return {
        "pair_counts": pair_counts,
        "pair_left": pair_left,
        "pair_right": pair_right,
        "pair_totals": pair_totals,
        "pair_docs": pair_docs,
        "pair_regions": pair_regions,
        "incoming": incoming,
        "outgoing": outgoing,
        "spec_docs": spec_docs,
        "spec_regions": spec_regions,
    }


def raw_score(stats, key):
    if key[0] == "PAIR":
        _, family, context, a, b = key
        rel = (family, context)
        total = stats["pair_totals"].get(rel, 0)
        if total <= 0:
            return 0.0
        count = stats["pair_counts"].get(key, 0)
        expected = stats["pair_left"].get((rel, a), 0) * stats["pair_right"].get((rel, b), 0) / total
        return math.log2((count + 0.5) / (expected + 0.5))
    _, direction, cid = key
    neigh = stats["incoming"].get(cid, Counter()) if direction == "IN" else stats["outgoing"].get(cid, Counter())
    total = sum(neigh.values())
    if total <= 0:
        return 0.0
    return sum((n / total) ** 2 for n in neigh.values())


def support_meta(stats, key):
    if key[0] == "PAIR":
        return {
            "events": stats["pair_counts"].get(key, 0),
            "documents": len(stats["pair_docs"].get(key, set())),
            "regions": sorted(stats["pair_regions"].get(key, set())),
        }
    _, direction, cid = key
    neigh = stats["incoming"].get(cid, Counter()) if direction == "IN" else stats["outgoing"].get(cid, Counter())
    return {
        "events": sum(neigh.values()),
        "documents": len(stats["spec_docs"].get(key, set())),
        "regions": sorted(stats["spec_regions"].get(key, set())),
    }


def dominant_neighbor(stats, key):
    if key[0] != "SPEC":
        return None
    _, direction, cid = key
    neigh = stats["incoming"].get(cid, Counter()) if direction == "IN" else stats["outgoing"].get(cid, Counter())
    if not neigh:
        return None
    return sorted(neigh.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def hypothesis_universe(stats):
    keys = set(stats["pair_counts"])
    keys.update(("SPEC", "IN", cid) for cid, c in stats["incoming"].items() if sum(c.values()) > 0)
    keys.update(("SPEC", "OUT", cid) for cid, c in stats["outgoing"].items() if sum(c.values()) > 0)
    return sorted(keys)


def pair_edge_lists(docs, eligible):
    edges = defaultdict(list)
    adjacency = []
    for doc in docs:
        for row in doc["rows"]:
            slots = row["slots"]
            for family, context, a, b in pair_events_for_row(slots):
                if a not in eligible or b not in eligible or a == b:
                    continue
                if family == "TTT_CONTEXT_EDGE" and context not in eligible:
                    continue
                edges[(family, context)].append((a, b))
            for a, b in adjacency_events_for_row(slots):
                if a in eligible and b in eligible:
                    adjacency.append((a, b))
    return edges, adjacency


def stats_from_rewire(docs, eligible, rng):
    edge_lists, adjacency = pair_edge_lists(docs, eligible)
    pair_counts = Counter()
    pair_left = Counter()
    pair_right = Counter()
    pair_totals = Counter()
    for rel, eds in edge_lists.items():
        lefts = [a for a, _ in eds]
        rights = [b for _, b in eds]
        rng.shuffle(rights)
        family, context = rel
        for a, b in zip(lefts, rights):
            key = ("PAIR", family, context, a, b)
            pair_counts[key] += 1
            pair_left[(rel, a)] += 1
            pair_right[(rel, b)] += 1
            pair_totals[rel] += 1

    incoming = defaultdict(Counter)
    outgoing = defaultdict(Counter)
    if adjacency:
        lefts = [a for a, _ in adjacency]
        rights = [b for _, b in adjacency]
        rng.shuffle(rights)
        for a, b in zip(lefts, rights):
            outgoing[a][b] += 1
            incoming[b][a] += 1

    return {
        "pair_counts": pair_counts,
        "pair_left": pair_left,
        "pair_right": pair_right,
        "pair_totals": pair_totals,
        "pair_docs": defaultdict(set),
        "pair_regions": defaultdict(set),
        "incoming": incoming,
        "outgoing": outgoing,
        "spec_docs": defaultdict(set),
        "spec_regions": defaultdict(set),
    }


def permuted_docs(docs, rng, mode):
    if mode == "ROW":
        return b7.copy_docs_with_row_shuffle(docs, rng)
    if mode == "DOCUMENT":
        return b7.copy_docs_with_document_shuffle(docs, rng)
    raise ValueError(mode)


def null_matrix(docs, eligible, universe, permutations, seed, mode):
    rng = random.Random(seed)
    matrix = []
    for _ in range(permutations):
        if mode in {"ROW", "DOCUMENT"}:
            st = build_stats(permuted_docs(docs, rng, mode), eligible)
        elif mode == "REWIRE":
            st = stats_from_rewire(docs, eligible, rng)
        else:
            raise ValueError(mode)
        matrix.append([raw_score(st, key) for key in universe])
    return matrix


def studentized_max_t(observed_scores, matrix):
    if not observed_scores:
        return [], {"means": [], "sds": [], "max_t": []}
    cols = list(zip(*matrix)) if matrix else [[] for _ in observed_scores]
    means = [statistics.fmean(c) if c else 0.0 for c in cols]
    sds = [statistics.pstdev(c) if len(c) > 1 else 0.0 for c in cols]

    def tval(x, mean, sd):
        if sd > 1e-12:
            return (x - mean) / sd
        if x > mean + 1e-12:
            return 1e9
        if x < mean - 1e-12:
            return -1e9
        return 0.0

    observed_t = [tval(x, m, s) for x, m, s in zip(observed_scores, means, sds)]
    max_t = []
    for row in matrix:
        vals = [tval(x, m, s) for x, m, s in zip(row, means, sds)]
        max_t.append(max(vals) if vals else 0.0)
    pvals = [(1 + sum(mx >= t for mx in max_t)) / (1 + len(max_t)) for t in observed_t]
    return pvals, {"means": means, "sds": sds, "max_t": max_t, "observed_t": observed_t}


def screen_discovery(docs, args):
    eligible, endpoint_counts, endpoint_docs = endpoint_eligibility(docs, args.min_endpoint_occurrences, args.min_endpoint_docs)
    observed = build_stats(docs, eligible, with_context=True)
    universe = hypothesis_universe(observed)
    obs_scores = [raw_score(observed, k) for k in universe]
    matrices = {
        "ROW": null_matrix(docs, eligible, universe, args.screen_permutations, args.seed + 11, "ROW"),
        "DOCUMENT": null_matrix(docs, eligible, universe, args.screen_permutations, args.seed + 23, "DOCUMENT"),
        "REWIRE": null_matrix(docs, eligible, universe, args.screen_permutations, args.seed + 37, "REWIRE"),
    }
    p = {}
    diag = {}
    for mode, mat in matrices.items():
        p[mode], diag[mode] = studentized_max_t(obs_scores, mat)

    rows = []
    for i, key in enumerate(universe):
        support = support_meta(observed, key)
        dominant = dominant_neighbor(observed, key)
        row = {
            "key": list(key),
            "raw_score": obs_scores[i],
            **support,
            "p_fwer_row": p["ROW"][i],
            "p_fwer_document": p["DOCUMENT"][i],
            "p_fwer_rewire": p["REWIRE"][i],
            "max_fwer_p": max(p["ROW"][i], p["DOCUMENT"][i], p["REWIRE"][i]),
        }
        if dominant:
            row["dominant_neighbor_id"] = dominant[0]
            row["dominant_neighbor_events"] = dominant[1]
        rows.append(row)

    rows.sort(key=lambda x: (x["max_fwer_p"], -x["raw_score"], -x["events"], x["key"]))
    selected = [
        r for r in rows
        if r["events"] >= args.min_pair_occurrences
        and r["documents"] >= args.min_pair_docs
        and r["raw_score"] > 0
        and r["p_fwer_row"] <= args.alpha
        and r["p_fwer_document"] <= args.alpha
        and r["p_fwer_rewire"] <= args.alpha
    ]
    return {
        "eligible_ids": eligible,
        "endpoint_counts": endpoint_counts,
        "endpoint_docs": endpoint_docs,
        "hypotheses": rows,
        "selected": selected,
        "null_diagnostics": {
            mode: {
                "permutations": args.screen_permutations,
                "max_t_mean": statistics.fmean(d["max_t"]) if d["max_t"] else None,
                "max_t_sd": statistics.pstdev(d["max_t"]) if len(d["max_t"]) > 1 else None,
            }
            for mode, d in diag.items()
        },
    }


def key_tuple(row):
    return tuple(row["key"])


def evaluate_locked_max_t(docs, eligible, locked, permutations, seed, min_events, min_docs, alpha):
    if not locked:
        return {"tested": [], "survivors": [], "evaluable_count": 0, "survivor_count": 0}
    universe = [key_tuple(r) for r in locked]
    observed = build_stats(docs, eligible, with_context=True)
    obs_scores = [raw_score(observed, k) for k in universe]
    matrices = {
        "ROW": null_matrix(docs, eligible, universe, permutations, seed + 11, "ROW"),
        "DOCUMENT": null_matrix(docs, eligible, universe, permutations, seed + 23, "DOCUMENT"),
        "REWIRE": null_matrix(docs, eligible, universe, permutations, seed + 37, "REWIRE"),
    }
    p = {mode: studentized_max_t(obs_scores, mat)[0] for mode, mat in matrices.items()}
    tested = []
    for i, (key, screen_row) in enumerate(zip(universe, locked)):
        sup = support_meta(observed, key)
        evaluable = sup["events"] >= min_events and sup["documents"] >= min_docs
        dominant = dominant_neighbor(observed, key)
        row = {
            "key": list(key),
            "screen_max_fwer_p": screen_row["max_fwer_p"],
            "raw_score": obs_scores[i],
            **sup,
            "evaluable": evaluable,
            "p_fwer_row": p["ROW"][i],
            "p_fwer_document": p["DOCUMENT"][i],
            "p_fwer_rewire": p["REWIRE"][i],
        }
        row["pass"] = bool(evaluable and obs_scores[i] > 0 and all(row[x] <= alpha for x in ("p_fwer_row", "p_fwer_document", "p_fwer_rewire")))
        if dominant:
            row["dominant_neighbor_id"] = dominant[0]
            row["dominant_neighbor_events"] = dominant[1]
        tested.append(row)
    return {
        "tested": tested,
        "survivors": [r for r in tested if r["pass"]],
        "evaluable_count": sum(r["evaluable"] for r in tested),
        "survivor_count": sum(r["pass"] for r in tested),
    }


def replicate_locked(docs, eligible, confirmed, permutations, seed, min_events, min_docs, min_regions, alpha):
    if not confirmed:
        return {"tested": [], "survivors": [], "evaluable_count": 0, "survivor_count": 0, "bonferroni_family_size": 0}
    universe = [key_tuple(r) for r in confirmed]
    observed = build_stats(docs, eligible, with_context=True)
    obs_scores = [raw_score(observed, k) for k in universe]
    mats = {
        "ROW": null_matrix(docs, eligible, universe, permutations, seed + 11, "ROW"),
        "DOCUMENT": null_matrix(docs, eligible, universe, permutations, seed + 23, "DOCUMENT"),
        "REWIRE": null_matrix(docs, eligible, universe, permutations, seed + 37, "REWIRE"),
    }
    family_size = len(universe) * 3
    tested = []
    for i, key in enumerate(universe):
        sup = support_meta(observed, key)
        evaluable = sup["events"] >= min_events and sup["documents"] >= min_docs and len(sup["regions"]) >= min_regions
        corrected = {}
        raw_p = {}
        for mode, mat in mats.items():
            vals = [row[i] for row in mat]
            pv = (1 + sum(v >= obs_scores[i] for v in vals)) / (1 + len(vals))
            raw_p[mode] = pv
            corrected[mode] = min(1.0, pv * family_size)
        dominant = dominant_neighbor(observed, key)
        row = {
            "key": list(key),
            "raw_score": obs_scores[i],
            **sup,
            "evaluable": evaluable,
            "p_raw_row": raw_p["ROW"],
            "p_raw_document": raw_p["DOCUMENT"],
            "p_raw_rewire": raw_p["REWIRE"],
            "p_bonf_row": corrected["ROW"],
            "p_bonf_document": corrected["DOCUMENT"],
            "p_bonf_rewire": corrected["REWIRE"],
        }
        row["pass"] = bool(evaluable and obs_scores[i] > 0 and all(row[x] <= alpha for x in ("p_bonf_row", "p_bonf_document", "p_bonf_rewire")))
        if dominant:
            row["dominant_neighbor_id"] = dominant[0]
            row["dominant_neighbor_events"] = dominant[1]
        tested.append(row)
    return {
        "tested": tested,
        "survivors": [r for r in tested if r["pass"]],
        "evaluable_count": sum(r["evaluable"] for r in tested),
        "survivor_count": sum(r["pass"] for r in tested),
        "bonferroni_family_size": family_size,
    }


def reveal_key(row, reveal):
    out = dict(row)
    key = tuple(row["key"])
    if key[0] == "PAIR":
        _, family, context, left, right = key
        r = {
            "hypothesis_kind": "PAIR",
            "family": family,
            "left_label": reveal.get(left),
            "right_label": reveal.get(right),
        }
        if family == "TTT_CONTEXT_EDGE":
            r["middle_context_label"] = reveal.get(context)
        elif family == "TBT_NUMERIC_BUCKET_EDGE":
            r["numeric_bucket"] = context
        out["post_score_reveal"] = r
    else:
        _, direction, cid = key
        r = {
            "hypothesis_kind": "NEIGHBOR_SPECIALIZATION",
            "direction": direction,
            "candidate_label": reveal.get(cid),
        }
        if row.get("dominant_neighbor_id"):
            r["dominant_neighbor_label"] = reveal.get(row["dominant_neighbor_id"])
        out["post_score_reveal"] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=260814850)
    ap.add_argument("--screen-permutations", type=int, default=3000)
    ap.add_argument("--confirm-permutations", type=int, default=5000)
    ap.add_argument("--test-permutations", type=int, default=5000)
    ap.add_argument("--min-endpoint-occurrences", type=int, default=8)
    ap.add_argument("--min-endpoint-docs", type=int, default=5)
    ap.add_argument("--min-pair-occurrences", type=int, default=4)
    ap.add_argument("--min-pair-docs", type=int, default=3)
    ap.add_argument("--confirm-min-events", type=int, default=2)
    ap.add_argument("--confirm-min-docs", type=int, default=2)
    ap.add_argument("--test-min-events", type=int, default=3)
    ap.add_argument("--test-min-docs", type=int, default=2)
    ap.add_argument("--test-min-regions", type=int, default=2)
    ap.add_argument("--alpha", type=float, default=0.05)
    args = ap.parse_args()

    corpus = Path(args.corpus)
    docs, reveal, known, failures, multirow = b7.load_corpus(corpus)
    ht_screen = [d for d in docs if d["region"] == "HT" and deterministic_partition(d["doc"]) == "HT_SCREEN"]
    ht_confirm = [d for d in docs if d["region"] == "HT" and deterministic_partition(d["doc"]) == "HT_CONFIRM"]
    non_ht = [d for d in docs if d["region"] != "HT"]

    screen = screen_discovery(ht_screen, args)
    confirm = evaluate_locked_max_t(
        ht_confirm, screen["eligible_ids"], screen["selected"], args.confirm_permutations,
        args.seed + 1000, args.confirm_min_events, args.confirm_min_docs, args.alpha,
    )
    replication = replicate_locked(
        non_ht, screen["eligible_ids"], confirm["survivors"], args.test_permutations,
        args.seed + 2000, args.test_min_events, args.test_min_docs, args.test_min_regions, args.alpha,
    )

    screen_selected_revealed = [reveal_key(r, reveal) for r in screen["selected"]]
    confirm_tested_revealed = [reveal_key(r, reveal) for r in confirm["tested"]]
    replication_tested_revealed = [reveal_key(r, reveal) for r in replication["tested"]]

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-V0.8-IMPLEMENTATION-B-RESULT-2026-08-14-v1.0",
        "version": VERSION,
        "status": "EXECUTED_HIGHER_ORDER_TRIPLE_NULL_MAXT",
        "frozen_execution_spec": {"path": SPEC, "commit": SPEC_COMMIT},
        "source": {
            "repository": "mwenge/lineara.xyz",
            "frozen_commit": b7.base.CORPUS_COMMIT,
            "typed_token_policy": b7.typing_policy.POLICY_ID,
            "representation": "WORD_ONLY_ROW_AWARE",
        },
        "corpus_counts": {
            "parsed_documents": len(docs),
            "parse_failures": failures,
            "multirow_words_dropped": multirow,
            "HT_SCREEN": len(ht_screen),
            "HT_CONFIRM": len(ht_confirm),
            "NON_HT": len(non_ht),
            "known_mask_counts": dict(known),
        },
        "hypothesis_families": [
            "TTT_CONTEXT_EDGE", "TBT_NUMERIC_BUCKET_EDGE", "ROW_PREFIX_TT", "ROW_SUFFIX_TT",
            "IN_NEIGHBOR_SPECIALIZATION", "OUT_NEIGHBOR_SPECIALIZATION",
        ],
        "nulls": [
            "WITHIN_ROW_SEMANTIC_IDENTITY_SHUFFLE_PRESERVING_TYPED_SLOTS_MASKS_AND_ROW_TOKEN_MULTISET",
            "WITHIN_DOCUMENT_SEMANTIC_IDENTITY_SHUFFLE_PRESERVING_TYPED_SLOTS_MASKS_AND_DOCUMENT_TOKEN_MULTISET",
            "GRAPH_ENDPOINT_REWIRE_PRESERVING_RELATION_CONTEXT_AND_ENDPOINT_MARGINALS",
        ],
        "screen": {
            "eligible_endpoint_count": len(screen["eligible_ids"]),
            "hypothesis_count": len(screen["hypotheses"]),
            "selected_count": len(screen["selected"]),
            "selected": screen_selected_revealed,
            "top_hypotheses_post_score_reveal": [reveal_key(r, reveal) for r in screen["hypotheses"][:50]],
            "null_diagnostics": screen["null_diagnostics"],
        },
        "HT_CONFIRM": {
            "locked_count": len(screen["selected"]),
            "evaluable_count": confirm["evaluable_count"],
            "survivor_count": confirm["survivor_count"],
            "tested": confirm_tested_revealed,
        },
        "NON_HT_REPLICATION": {
            "locked_count": len(confirm["survivors"]),
            "evaluable_count": replication["evaluable_count"],
            "survivor_count": replication["survivor_count"],
            "bonferroni_family_size": replication["bonferroni_family_size"],
            "tested": replication_tested_revealed,
            "classification": "CROSS_REGION_REPLICATION_AFTER_PRIOR_FULL_CORPUS_EXPOSURE_NOT_PRISTINE_EXTERNAL_HOLDOUT",
        },
        "epistemic_gate": {
            "new_anchor_established": False,
            "decipherment_established": False,
            "external_replication_established": False,
            "maximum_if_survivor": "INTERNALLY_REPLICATED_STRUCTURAL_RELATION_CANDIDATE",
            "promotion": "A_B_RECONCILIATION_REQUIRED" if replication["survivor_count"] else "NO_PROMOTION",
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "artifact": str(out),
        "eligible_endpoints": len(screen["eligible_ids"]),
        "screen_hypotheses": len(screen["hypotheses"]),
        "screen_selected": len(screen["selected"]),
        "confirm_evaluable": confirm["evaluable_count"],
        "confirm_survivors": confirm["survivor_count"],
        "non_ht_evaluable": replication["evaluable_count"],
        "non_ht_survivors": replication["survivor_count"],
        "new_anchor_established": False,
        "decipherment_established": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
