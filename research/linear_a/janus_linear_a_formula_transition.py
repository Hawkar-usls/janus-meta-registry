#!/usr/bin/env python3
"""JANUS Linear A v0.7 directed formula-transition / semantic-neighborhood search.

This stage uses the v0.6.2 typed-token ontology as a mandatory precondition. Only full-word
SEMANTIC_CANDIDATE identities are tested. Punctuation, exact/approximate numeric literals,
and frozen known-control families are not eligible relation endpoints.

Discovery is HT-only. Candidate identity pairs, relation type, enrichment direction, and
replication tests are frozen before non-HT evaluation and before semantic reveal.

A v0.7 survivor is at most a structural relation candidate. It is not a lexical anchor and
cannot establish decipherment.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_full_corpus as base
import janus_linear_a_token_typing_policy_v0_6_2 as typing_policy

VERSION = "JANUS-LINA-FORMULA-TRANSITION-v0.7"
DEFAULT_SEED = 260814625
CANONICAL_PARENT = "data/JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.0.json"
CANONICAL_PARENT_COMMIT = "fac7c305e7210c574439a62179e78cb26f13e743"

RELATIONS = (
    "ADJACENT_TT",
    "NUMERIC_BRIDGE_TNT",
    "PRE_NUMERIC_BIGRAM_TTN",
    "POST_NUMERIC_BIGRAM_NTT",
    "ROW_PREFIX_TT",
    "ROW_SUFFIX_TT",
)

KNOWN_EXACT = {"KURO", "KIRO", "POTOKURO"}
NUMERIC_KINDS = {"N", "N_UNCERTAIN"}


def normalize_label(text: str) -> str:
    return re.sub(r"[^A-Z0-9*?+]", "", (text or "").upper())


def frozen_known_exclusion(raw_word: str) -> bool:
    """Removal-only mask frozen from earlier stages; never used to select new candidates."""
    n = normalize_label(raw_word)
    if n in KNOWN_EXACT:
        return True
    if n.startswith("VIR"):
        return True
    if n.startswith("GRA"):
        return True
    return False


def parse_document(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    m = base.READING_SPEC_RE.search(text)
    if not m:
        return None

    body = base.TAG_RE.sub("", m.group(1))
    by_word = defaultdict(list)
    for raw in body.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        rm = base.ROW_RE.match(raw)
        if not rm:
            continue
        row_i, line_i, word_i, token, status = rm.groups()
        by_word[int(word_i)].append(
            {
                "row": int(row_i),
                "line": int(line_i),
                "token": token.strip(),
                "status": status.lower(),
            }
        )

    rows = defaultdict(list)
    reveal = {}
    known_excluded = Counter()
    multirow_words = 0

    for word_i in sorted(by_word):
        entries = [e for e in by_word[word_i] if not typing_policy.p61.is_nonlexical_piece(e["token"])]
        if not entries:
            continue

        row_values = sorted({e["row"] for e in entries})
        if len(row_values) != 1:
            multirow_words += 1
            continue
        row = row_values[0]
        line_values = sorted({e["line"] for e in entries})
        line = line_values[0] if len(line_values) == 1 else None

        pieces = [e["token"] for e in entries]
        exact_values = [typing_policy.parse_exact_numeric_literal(tok) for tok in pieces]

        if exact_values and all(v is not None for v in exact_values):
            value = sum(float(v) for v in exact_values)
            rows[row].append(
                {"kind": "N", "word_index": word_i, "line": line, "value": value}
            )
            continue

        if pieces and all(typing_policy.is_numeric_like_literal(tok) for tok in pieces):
            rows[row].append(
                {"kind": "N_UNCERTAIN", "word_index": word_i, "line": line}
            )
            continue

        semantic_pieces = [tok for tok in pieces if not typing_policy.is_numeric_like_literal(tok)]
        if not semantic_pieces:
            continue

        raw_word = "·".join(semantic_pieces)
        if frozen_known_exclusion(raw_word):
            known_excluded[normalize_label(raw_word)] += 1
            rows[row].append(
                {"kind": "K", "word_index": word_i, "line": line}
            )
            continue

        word_id = base.stable_id(raw_word, "WORD")
        rows[row].append(
            {"kind": "T", "id": word_id, "word_index": word_i, "line": line}
        )
        reveal.setdefault(word_id, raw_word)

    packed_rows = []
    for row_i in sorted(rows):
        slots = sorted(rows[row_i], key=lambda x: x["word_index"])
        if slots:
            packed_rows.append({"row": row_i, "slots": slots})

    if not packed_rows:
        return None

    return {
        "doc": path.stem,
        "region": base.region_of(path.stem),
        "rows": packed_rows,
        "reveal": reveal,
        "known_excluded": dict(known_excluded),
        "multirow_words_dropped": multirow_words,
    }


def load_corpus(corpus: Path):
    docs = []
    reveal = {}
    known = Counter()
    multirow = 0
    failures = 0
    for path in sorted((corpus / "items").glob("*.html")):
        doc = parse_document(path)
        if doc is None:
            failures += 1
            continue
        docs.append(doc)
        reveal.update(doc["reveal"])
        known.update(doc["known_excluded"])
        multirow += doc["multirow_words_dropped"]
    return docs, reveal, known, failures, multirow


def endpoint_eligibility(docs, min_occurrences: int, min_docs: int):
    counts = Counter()
    doc_sets = defaultdict(set)
    for doc in docs:
        for row in doc["rows"]:
            for slot in row["slots"]:
                if slot["kind"] == "T":
                    counts[slot["id"]] += 1
                    doc_sets[slot["id"]].add(doc["doc"])
    eligible = {
        tok
        for tok, n in counts.items()
        if n >= min_occurrences and len(doc_sets[tok]) >= min_docs
    }
    return eligible, counts, {k: len(v) for k, v in doc_sets.items()}


def relation_occurrences_for_row(slots):
    """Yield (relation, left_id, right_id) for predeclared typed-slot templates."""
    n = len(slots)
    if n >= 2 and slots[0]["kind"] == "T" and slots[1]["kind"] == "T":
        yield "ROW_PREFIX_TT", slots[0]["id"], slots[1]["id"]
    if n >= 2 and slots[-2]["kind"] == "T" and slots[-1]["kind"] == "T":
        yield "ROW_SUFFIX_TT", slots[-2]["id"], slots[-1]["id"]

    for i in range(n - 1):
        a, b = slots[i], slots[i + 1]
        if a["kind"] == "T" and b["kind"] == "T":
            yield "ADJACENT_TT", a["id"], b["id"]

    for i in range(n - 2):
        a, b, c = slots[i], slots[i + 1], slots[i + 2]
        if a["kind"] == "T" and b["kind"] in NUMERIC_KINDS and c["kind"] == "T":
            yield "NUMERIC_BRIDGE_TNT", a["id"], c["id"]
        if a["kind"] == "T" and b["kind"] == "T" and c["kind"] in NUMERIC_KINDS:
            yield "PRE_NUMERIC_BIGRAM_TTN", a["id"], b["id"]
        if a["kind"] in NUMERIC_KINDS and b["kind"] == "T" and c["kind"] == "T":
            yield "POST_NUMERIC_BIGRAM_NTT", b["id"], c["id"]


def relation_stats(docs, eligible, with_context=False):
    counts = {r: Counter() for r in RELATIONS}
    left = {r: Counter() for r in RELATIONS}
    right = {r: Counter() for r in RELATIONS}
    totals = Counter()
    doc_sets = defaultdict(set)
    region_sets = defaultdict(set)

    for doc in docs:
        for row in doc["rows"]:
            for relation, a, b in relation_occurrences_for_row(row["slots"]):
                if a not in eligible or b not in eligible:
                    continue
                counts[relation][(a, b)] += 1
                left[relation][a] += 1
                right[relation][b] += 1
                totals[relation] += 1
                if with_context and a != b:
                    key = (relation, a, b)
                    doc_sets[key].add(doc["doc"])
                    region_sets[key].add(doc["region"])

    return {
        "counts": counts,
        "left": left,
        "right": right,
        "totals": totals,
        "doc_sets": doc_sets,
        "region_sets": region_sets,
    }


def association_score(stats, key):
    relation, a, b = key
    total = stats["totals"][relation]
    if total <= 0:
        return 0.0
    count = stats["counts"][relation].get((a, b), 0)
    expected = (
        stats["left"][relation].get(a, 0)
        * stats["right"][relation].get(b, 0)
        / total
    )
    return math.log2((count + 0.5) / (expected + 0.5))


def max_association_score(stats):
    best = 0.0
    for relation in RELATIONS:
        for (a, b), count in stats["counts"][relation].items():
            if a == b or count <= 0:
                continue
            s = association_score(stats, (relation, a, b))
            if s > best:
                best = s
    return best


def copy_docs_with_row_shuffle(docs, rng):
    out = []
    for doc in docs:
        new_rows = []
        for row in doc["rows"]:
            ids = [s["id"] for s in row["slots"] if s["kind"] == "T"]
            rng.shuffle(ids)
            it = iter(ids)
            slots = []
            for s in row["slots"]:
                if s["kind"] == "T":
                    slots.append({**s, "id": next(it)})
                else:
                    slots.append(dict(s))
            new_rows.append({"row": row["row"], "slots": slots})
        out.append({"doc": doc["doc"], "region": doc["region"], "rows": new_rows})
    return out


def copy_docs_with_document_shuffle(docs, rng):
    out = []
    for doc in docs:
        ids = [
            s["id"]
            for row in doc["rows"]
            for s in row["slots"]
            if s["kind"] == "T"
        ]
        rng.shuffle(ids)
        it = iter(ids)
        new_rows = []
        for row in doc["rows"]:
            slots = []
            for s in row["slots"]:
                if s["kind"] == "T":
                    slots.append({**s, "id": next(it)})
                else:
                    slots.append(dict(s))
            new_rows.append({"row": row["row"], "slots": slots})
        out.append({"doc": doc["doc"], "region": doc["region"], "rows": new_rows})
    return out


def max_null_shuffle(docs, eligible, permutations, seed, mode):
    rng = random.Random(seed)
    out = []
    for _ in range(permutations):
        if mode == "ROW":
            permuted = copy_docs_with_row_shuffle(docs, rng)
        elif mode == "DOCUMENT":
            permuted = copy_docs_with_document_shuffle(docs, rng)
        else:
            raise ValueError(mode)
        out.append(max_association_score(relation_stats(permuted, eligible)))
    return out


def eligible_edges_by_relation(docs, eligible):
    edges = {r: [] for r in RELATIONS}
    for doc in docs:
        for row in doc["rows"]:
            for relation, a, b in relation_occurrences_for_row(row["slots"]):
                if a in eligible and b in eligible:
                    edges[relation].append((a, b))
    return edges


def stats_from_rewired_edges(edge_lists, rng):
    counts = {r: Counter() for r in RELATIONS}
    left = {r: Counter() for r in RELATIONS}
    right = {r: Counter() for r in RELATIONS}
    totals = Counter()
    for relation in RELATIONS:
        edges = edge_lists[relation]
        if not edges:
            continue
        lefts = [a for a, _ in edges]
        rights = [b for _, b in edges]
        rng.shuffle(rights)
        for a, b in zip(lefts, rights):
            counts[relation][(a, b)] += 1
            left[relation][a] += 1
            right[relation][b] += 1
            totals[relation] += 1
    return {
        "counts": counts,
        "left": left,
        "right": right,
        "totals": totals,
        "doc_sets": defaultdict(set),
        "region_sets": defaultdict(set),
    }


def max_null_rewire(docs, eligible, permutations, seed):
    rng = random.Random(seed)
    edges = eligible_edges_by_relation(docs, eligible)
    return [
        max_association_score(stats_from_rewired_edges(edges, rng))
        for _ in range(permutations)
    ]


def empirical_max_p(score, max_null):
    return (1 + sum(x >= score for x in max_null)) / (1 + len(max_null))


def train_discovery(
    train_docs,
    min_endpoint_occurrences,
    min_endpoint_docs,
    min_pair_occurrences,
    min_pair_docs,
    permutations,
    seed,
    alpha,
):
    eligible, endpoint_counts, endpoint_docs = endpoint_eligibility(
        train_docs, min_endpoint_occurrences, min_endpoint_docs
    )
    observed = relation_stats(train_docs, eligible, with_context=True)

    row_null = max_null_shuffle(
        train_docs, eligible, permutations, seed + 11, "ROW"
    )
    doc_null = max_null_shuffle(
        train_docs, eligible, permutations, seed + 23, "DOCUMENT"
    )
    rewire_null = max_null_rewire(
        train_docs, eligible, permutations, seed + 37
    )

    hypotheses = []
    for relation in RELATIONS:
        for (a, b), count in observed["counts"][relation].items():
            if a == b:
                continue
            key = (relation, a, b)
            score = association_score(observed, key)
            docs_n = len(observed["doc_sets"][key])
            p_row = empirical_max_p(score, row_null)
            p_doc = empirical_max_p(score, doc_null)
            p_rewire = empirical_max_p(score, rewire_null)
            hypotheses.append(
                {
                    "relation": relation,
                    "left_id": a,
                    "right_id": b,
                    "count": count,
                    "docs": docs_n,
                    "score_log2_enrichment": score,
                    "p_fwer_row_shuffle": p_row,
                    "p_fwer_document_shuffle": p_doc,
                    "p_fwer_endpoint_rewire": p_rewire,
                    "max_fwer_p": max(p_row, p_doc, p_rewire),
                }
            )

    hypotheses.sort(
        key=lambda x: (
            x["max_fwer_p"],
            -x["score_log2_enrichment"],
            -x["count"],
            x["relation"],
            x["left_id"],
            x["right_id"],
        )
    )
    selected = [
        h
        for h in hypotheses
        if h["count"] >= min_pair_occurrences
        and h["docs"] >= min_pair_docs
        and h["score_log2_enrichment"] > 0
        and h["p_fwer_row_shuffle"] <= alpha
        and h["p_fwer_document_shuffle"] <= alpha
        and h["p_fwer_endpoint_rewire"] <= alpha
    ]

    return {
        "eligible_ids": eligible,
        "endpoint_counts": endpoint_counts,
        "endpoint_docs": endpoint_docs,
        "observed": observed,
        "hypotheses": hypotheses,
        "selected": selected,
        "null_summary": {
            "permutations_each": permutations,
            "row_shuffle_max_mean": sum(row_null) / len(row_null) if row_null else None,
            "document_shuffle_max_mean": sum(doc_null) / len(doc_null) if doc_null else None,
            "endpoint_rewire_max_mean": sum(rewire_null) / len(rewire_null) if rewire_null else None,
            "operators": [
                "WITHIN_ROW_IDENTITY_SHUFFLE_PRESERVING_TYPED_SLOTS_AND_ROW_TOKEN_MULTISET",
                "WITHIN_DOCUMENT_IDENTITY_SHUFFLE_PRESERVING_TYPED_SLOTS_AND_DOCUMENT_TOKEN_MULTISET",
                "PREDECESSOR_SUCCESSOR_REWIRE_PRESERVING_RELATION_ENDPOINT_MARGINALS",
            ],
        },
    }


def selected_key(h):
    return (h["relation"], h["left_id"], h["right_id"])


def null_scores_for_selected_shuffle(docs, eligible, selected, permutations, seed, mode):
    rng = random.Random(seed)
    keys = [selected_key(h) for h in selected]
    exceed_samples = {k: [] for k in keys}
    for _ in range(permutations):
        if mode == "ROW":
            permuted = copy_docs_with_row_shuffle(docs, rng)
        else:
            permuted = copy_docs_with_document_shuffle(docs, rng)
        stats = relation_stats(permuted, eligible)
        for key in keys:
            exceed_samples[key].append(association_score(stats, key))
    return exceed_samples


def null_scores_for_selected_rewire(docs, eligible, selected, permutations, seed):
    rng = random.Random(seed)
    keys = [selected_key(h) for h in selected]
    edges = eligible_edges_by_relation(docs, eligible)
    samples = {k: [] for k in keys}
    for _ in range(permutations):
        stats = stats_from_rewired_edges(edges, rng)
        for key in keys:
            samples[key].append(association_score(stats, key))
    return samples


def empirical_one_sided_p(observed, values):
    return (1 + sum(x >= observed for x in values)) / (1 + len(values))


def replicate(
    test_docs,
    eligible,
    selected,
    permutations,
    seed,
    alpha,
    min_pair_occurrences,
    min_pair_docs,
    min_regions,
):
    if not selected:
        return []

    observed = relation_stats(test_docs, eligible, with_context=True)
    row_samples = null_scores_for_selected_shuffle(
        test_docs, eligible, selected, permutations, seed + 101, "ROW"
    )
    doc_samples = null_scores_for_selected_shuffle(
        test_docs, eligible, selected, permutations, seed + 211, "DOCUMENT"
    )
    rewire_samples = null_scores_for_selected_rewire(
        test_docs, eligible, selected, permutations, seed + 307
    )

    multiplier = max(1, len(selected) * 3)
    results = []
    for h in selected:
        key = selected_key(h)
        relation, a, b = key
        score = association_score(observed, key)
        count = observed["counts"][relation].get((a, b), 0)
        docs_n = len(observed["doc_sets"][key])
        regions = sorted(observed["region_sets"][key])

        p_row = empirical_one_sided_p(score, row_samples[key])
        p_doc = empirical_one_sided_p(score, doc_samples[key])
        p_rewire = empirical_one_sided_p(score, rewire_samples[key])

        b_row = min(1.0, p_row * multiplier)
        b_doc = min(1.0, p_doc * multiplier)
        b_rewire = min(1.0, p_rewire * multiplier)

        passed = (
            score > 0
            and count >= min_pair_occurrences
            and docs_n >= min_pair_docs
            and len(regions) >= min_regions
            and b_row <= alpha
            and b_doc <= alpha
            and b_rewire <= alpha
        )
        results.append(
            {
                "relation": relation,
                "left_id": a,
                "right_id": b,
                "locked_direction": "ENRICHED",
                "test_count": count,
                "test_docs": docs_n,
                "test_regions": regions,
                "test_score_log2_enrichment": score,
                "p_one_sided_row_shuffle": p_row,
                "p_one_sided_document_shuffle": p_doc,
                "p_one_sided_endpoint_rewire": p_rewire,
                "bonferroni_multiplier_selected_x_nulls": multiplier,
                "p_bonferroni_row_shuffle": b_row,
                "p_bonferroni_document_shuffle": b_doc,
                "p_bonferroni_endpoint_rewire": b_rewire,
                "replication_pass": passed,
            }
        )
    return results


def reveal_hypothesis(h, reveal):
    return {
        **h,
        "left_label": reveal.get(h["left_id"], "<UNRESOLVED>"),
        "right_label": reveal.get(h["right_id"], "<UNRESOLVED>"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--train-permutations", type=int, default=3000)
    ap.add_argument("--test-permutations", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--min-endpoint-occurrences", type=int, default=8)
    ap.add_argument("--min-endpoint-docs", type=int, default=5)
    ap.add_argument("--min-train-pair-occurrences", type=int, default=4)
    ap.add_argument("--min-train-pair-docs", type=int, default=3)
    ap.add_argument("--min-test-pair-occurrences", type=int, default=3)
    ap.add_argument("--min-test-pair-docs", type=int, default=2)
    ap.add_argument("--min-test-regions", type=int, default=2)
    args = ap.parse_args()

    corpus = Path(args.corpus)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    docs, reveal, known_excluded, failures, multirow = load_corpus(corpus)
    train_docs = [d for d in docs if d["region"] == "HT"]
    test_docs = [d for d in docs if d["region"] != "HT"]

    discovery = train_discovery(
        train_docs=train_docs,
        min_endpoint_occurrences=args.min_endpoint_occurrences,
        min_endpoint_docs=args.min_endpoint_docs,
        min_pair_occurrences=args.min_train_pair_occurrences,
        min_pair_docs=args.min_train_pair_docs,
        permutations=args.train_permutations,
        seed=args.seed,
        alpha=args.alpha,
    )

    # Candidate identities/relation/direction are frozen here, before replication and reveal.
    locked_selected = [dict(h) for h in discovery["selected"]]
    replication = replicate(
        test_docs=test_docs,
        eligible=discovery["eligible_ids"],
        selected=locked_selected,
        permutations=args.test_permutations,
        seed=args.seed,
        alpha=args.alpha,
        min_pair_occurrences=args.min_test_pair_occurrences,
        min_pair_docs=args.min_test_pair_docs,
        min_regions=args.min_test_regions,
    )

    rep_by_key = {selected_key(r): r for r in replication}
    survivors_pre_reveal = [
        h
        for h in locked_selected
        if rep_by_key.get(selected_key(h), {}).get("replication_pass") is True
    ]

    # Semantic reveal occurs only after discovery + replication outcomes are frozen.
    selected_post_reveal = []
    for h in locked_selected:
        key = selected_key(h)
        row = {
            "discovery": reveal_hypothesis(h, reveal),
            "replication": reveal_hypothesis(rep_by_key[key], reveal)
            if key in rep_by_key
            else None,
        }
        selected_post_reveal.append(row)

    top_train_post_reveal = [
        reveal_hypothesis(h, reveal) for h in discovery["hypotheses"][:20]
    ]
    survivor_post_reveal = [
        reveal_hypothesis(h, reveal) for h in survivors_pre_reveal
    ]

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-FORMULA-TRANSITION-CROSS-REGION-2026-08-14-v0.7",
        "version": "v0.7",
        "status": "EXECUTED" if docs else "NO_CORPUS",
        "title": "JANUS Linear A directed formula-transition / semantic-neighborhood cross-region search",
        "source": {
            "repository": "mwenge/lineara.xyz",
            "frozen_commit": base.CORPUS_COMMIT,
            "token_typing_policy_id": typing_policy.POLICY_ID,
            "canonical_parent_state": CANONICAL_PARENT,
            "canonical_parent_commit": CANONICAL_PARENT_COMMIT,
        },
        "methodology": {
            "representation": "WORD_ONLY",
            "candidate_type": "SEMANTIC_CANDIDATE_ONLY",
            "frozen_known_exclusion_mask": {
                "exact": sorted(KNOWN_EXACT),
                "prefixes": ["VIR", "GRA"],
                "purpose": "Removal only; known controls cannot become new v0.7 candidates.",
            },
            "relations": list(RELATIONS),
            "discovery_partition": "HT",
            "replication_partition": "NON_HT",
            "replication_is_pristine_unseen_holdout": False,
            "replication_classification": "CROSS_REGION_REPLICATION_AFTER_PRIOR_FULL_CORPUS_EXPOSURE",
            "endpoint_eligibility": {
                "min_occurrences_HT": args.min_endpoint_occurrences,
                "min_documents_HT": args.min_endpoint_docs,
            },
            "train_promotion_minimums": {
                "pair_occurrences": args.min_train_pair_occurrences,
                "pair_documents": args.min_train_pair_docs,
            },
            "test_promotion_minimums": {
                "pair_occurrences": args.min_test_pair_occurrences,
                "pair_documents": args.min_test_pair_docs,
                "distinct_non_HT_regions": args.min_test_regions,
            },
            "discovery_error_control": "MAX_T_FWER_REQUIRED_UNDER_ALL_THREE_DESTRUCTIVE_NULLS",
            "replication_error_control": "ONE_SIDED_LOCKED_DIRECTION_PLUS_BONFERRONI_OVER_SELECTED_RELATIONS_X_THREE_NULLS",
            "null_operators": discovery["null_summary"]["operators"],
            "semantic_reveal_policy": "AFTER_DISCOVERY_AND_REPLICATION_ARE_FROZEN",
            "self_transitions": "EXCLUDED_FROM_HYPOTHESIS_FAMILY",
        },
        "corpus_counts": {
            "item_html_files": len(list((corpus / "items").glob("*.html"))),
            "parsed_documents": len(docs),
            "parse_failures": failures,
            "multirow_words_dropped_from_relation_geometry": multirow,
            "HT_documents": len(train_docs),
            "non_HT_documents": len(test_docs),
            "non_HT_regions": sorted({d["region"] for d in test_docs}),
            "known_excluded_occurrences": dict(sorted(known_excluded.items())),
            "eligible_semantic_endpoint_ids_HT": len(discovery["eligible_ids"]),
        },
        "blind_discovery_receipt": {
            "train_permutations_per_null": args.train_permutations,
            "null_summary": discovery["null_summary"],
            "tested_nonzero_hypotheses": len(discovery["hypotheses"]),
            "selected_count": len(locked_selected),
            "selected_pre_reveal": [
                {
                    k: h[k]
                    for k in (
                        "relation",
                        "left_id",
                        "right_id",
                        "count",
                        "docs",
                        "score_log2_enrichment",
                        "p_fwer_row_shuffle",
                        "p_fwer_document_shuffle",
                        "p_fwer_endpoint_rewire",
                        "max_fwer_p",
                    )
                }
                for h in locked_selected
            ],
        },
        "cross_region_replication_receipt": {
            "test_permutations_per_null": args.test_permutations,
            "locked_selected_count": len(locked_selected),
            "results_pre_reveal": replication,
            "cross_region_survivor_count": len(survivors_pre_reveal),
        },
        "post_score_reveal": {
            "selected": selected_post_reveal,
            "survivors": survivor_post_reveal,
            "top_20_train_hypotheses": top_train_post_reveal,
        },
        "epistemic_gate": {
            "typed_candidate_universe_frozen": True,
            "formula_transition_candidate_exists": len(survivors_pre_reveal) > 0,
            "cross_region_survivor_count": len(survivors_pre_reveal),
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": (
                "BLOCKED_PENDING_ALTERNATIVE_SEGMENTATION_NOVELTY_AND_EXTERNAL_REPLICATION"
                if survivors_pre_reveal
                else "NO_PROMOTION"
            ),
        },
        "claim_ceiling": (
            "STRUCTURAL_RELATION_CANDIDATE_ONLY"
            if survivors_pre_reveal
            else "REPRESENTATION_CLEAN_NEGATIVE_RESULT_FOR_DIRECTED_FORMULA_TRANSITION_CHANNEL"
        ),
        "next_gate": (
            "V0_7_SURVIVOR_ALTERNATIVE_SEGMENTATION_AND_IDENTITY_NOVELTY_AUDIT"
            if survivors_pre_reveal
            else "ADVANCE_TO_HIGHER_ORDER_FORMULA_GRAPH_OR_FRESH_SOURCE_WITHOUT_RELAXING_THRESHOLDS"
        ),
    }

    out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "parsed_documents": len(docs),
                "eligible_HT_endpoints": len(discovery["eligible_ids"]),
                "train_selected": len(locked_selected),
                "cross_region_survivors": len(survivors_pre_reveal),
                "new_anchor_established": False,
                "decipherment_established": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
