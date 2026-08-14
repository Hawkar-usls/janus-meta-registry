#!/usr/bin/env python3
"""
JANUS Linear A v0.8 higher-order typed neighborhood / specialization analysis.

Consumes canonical v2.2 and the v0.6.2 typed-token ontology.
Two channels:
  CONTROL_INCLUDED: known controls remain semantic identities; infrastructure-only.
  NOVELTY_MASKED: known control positions become fixed MASK slots; claim-bearing.

Partitions:
  HT_SCREEN -> HT_CONFIRM -> NON_HT

Hypothesis families:
  H1 TTT_DIRECTED_TRIGRAM
  H2 T_NBUCKET_T
  H3 ROW_PREFIX_TTT
  H4 ROW_SUFFIX_TTT
  H5 NEIGHBOR_SPECIALIZATION_OUT
  H6 NEIGHBOR_SPECIALIZATION_IN

No semantic reveal occurs until screen/confirm/replication states are frozen.
No new-anchor or decipherment claim can be emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_full_corpus as base

if not hasattr(base, "_JANUS_V061_ORIGINAL_PARSE_NUMERIC_PIECE"):
    base._JANUS_V061_ORIGINAL_PARSE_NUMERIC_PIECE = base.parse_numeric_piece

import janus_linear_a_token_typing_policy_v0_6_2 as typing_policy

VERSION = "JANUS-LINA-HIGHER-ORDER-NEIGHBORHOOD-v0.8"
ARTIFACT_UUID = "JANUS-LINEAR-A-HIGHER-ORDER-NEIGHBORHOOD-2026-08-14-v0.8"
CANONICAL_PARENT = "data/JANUS-LINEAR-A-RESEARCH-STATE-2026-08-14-v2.2.json"
CANONICAL_PARENT_COMMIT = "c45adaa5732600a27cea3f72d366efa36e8d68c3"
SPEC_PATH = "data/JANUS-LINEAR-A-HIGHER-ORDER-NEIGHBORHOOD-EXECUTION-SPEC-2026-08-14-v0.8.json"
SPEC_COMMIT = "402c1f2750dfe8e56fd432bcc3ff88d06d0285ab"

CHANNELS = ("CONTROL_INCLUDED", "NOVELTY_MASKED")
MOTIF_FAMILIES = (
    "TTT_DIRECTED_TRIGRAM",
    "T_NBUCKET_T",
    "ROW_PREFIX_TTT",
    "ROW_SUFFIX_TTT",
)
SPECIALIZATION_FAMILIES = (
    "NEIGHBOR_SPECIALIZATION_OUT",
    "NEIGHBOR_SPECIALIZATION_IN",
)
FAMILIES = MOTIF_FAMILIES + SPECIALIZATION_FAMILIES
NUMERIC_BUCKETS = ("FRAC", "ONE", "2_4", "5_9", "10PLUS", "UNCERTAIN")
KNOWN_ACCOUNTING_WORDS = {"KURO", "KIRO", "POTOKURO"}
KNOWN_CONTROL_WORDS = KNOWN_ACCOUNTING_WORDS | {"GRA"}
NUMERIC_KINDS = {"N", "N_UNCERTAIN"}


def norm(label: str) -> str:
    return re.sub(r"[^A-Z0-9*]+", "", (label or "").upper())


def is_known_control_label(label: str) -> bool:
    x = norm(label)
    return x.startswith("VIR") or x.startswith("GRA") or x in KNOWN_CONTROL_WORDS


def deterministic_ht_partition(doc_id: str) -> str:
    h = int(hashlib.sha256(f"JANUS-LINA-v0.8|{doc_id}".encode("utf-8")).hexdigest()[:8], 16)
    return "HT_SCREEN" if h % 5 in {0, 1, 2} else "HT_CONFIRM"


def numeric_bucket(kind: str, value=None) -> str:
    if kind == "N_UNCERTAIN":
        return "UNCERTAIN"
    if value is None:
        return "UNCERTAIN"
    return base.bucket(float(value))


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
    multirow_words = 0
    for wi in sorted(by_word):
        entries = [e for e in by_word[wi] if not typing_policy.p61.is_nonlexical_piece(e["token"])]
        if not entries:
            continue
        row_values = sorted({e["row"] for e in entries})
        if len(row_values) != 1:
            multirow_words += 1
            continue
        row = row_values[0]
        pieces = [e["token"] for e in entries]
        exact = [typing_policy.parse_exact_numeric_literal(t) for t in pieces]
        if exact and all(v is not None for v in exact):
            value = sum(float(v) for v in exact)
            if value > 0:
                rows[row].append(
                    {
                        "kind": "N",
                        "bucket": numeric_bucket("N", value),
                        "value": value,
                        "word_index": wi,
                    }
                )
            continue
        if pieces and all(typing_policy.is_numeric_like_literal(t) for t in pieces):
            rows[row].append(
                {
                    "kind": "N_UNCERTAIN",
                    "bucket": "UNCERTAIN",
                    "word_index": wi,
                }
            )
            continue

        semantic = [t for t in pieces if not typing_policy.is_numeric_like_literal(t)]
        if not semantic:
            continue
        raw_word = "·".join(semantic)
        word_id = base.stable_id(raw_word, "WORD")
        rows[row].append(
            {
                "kind": "T",
                "id": word_id,
                "word_index": wi,
                "known_control": is_known_control_label(raw_word),
            }
        )
        reveal.setdefault(word_id, raw_word)

    packed = []
    for row_i in sorted(rows):
        slots = sorted(rows[row_i], key=lambda x: x["word_index"])
        if slots:
            packed.append({"row": row_i, "slots": slots})
    if not packed:
        return None
    return {
        "doc": path.stem,
        "region": base.region_of(path.stem),
        "rows": packed,
        "reveal": reveal,
        "multirow_words_dropped": multirow_words,
    }


def load_corpus(corpus: Path):
    docs, reveal = [], {}
    failures = 0
    multirow = 0
    for path in sorted((corpus / "items").glob("*.html")):
        try:
            d = parse_document(path)
        except Exception:
            d = None
        if not d:
            failures += 1
            continue
        docs.append(d)
        reveal.update(d["reveal"])
        multirow += d["multirow_words_dropped"]
    if len(docs) < 300:
        raise SystemExit("FULL_CORPUS_GATE_FAIL")
    return docs, reveal, failures, multirow


def channelize_doc(doc: dict, channel: str):
    rows = []
    for row in doc["rows"]:
        slots = []
        for s in row["slots"]:
            if s["kind"] == "T" and channel == "NOVELTY_MASKED" and s.get("known_control"):
                slots.append({"kind": "MASK", "word_index": s["word_index"]})
            else:
                slots.append(dict(s))
        rows.append({"row": row["row"], "slots": slots})
    return {"doc": doc["doc"], "region": doc["region"], "rows": rows}


def endpoint_eligibility(docs, min_occurrences=8, min_docs=5):
    counts = Counter()
    docsets = defaultdict(set)
    for d in docs:
        for row in d["rows"]:
            for s in row["slots"]:
                if s["kind"] == "T":
                    counts[s["id"]] += 1
                    docsets[s["id"]].add(d["doc"])
    eligible = {
        cid for cid, n in counts.items()
        if n >= min_occurrences and len(docsets[cid]) >= min_docs
    }
    return eligible, counts, {cid: len(v) for cid, v in docsets.items()}


def motif_events(docs, family: str, eligible_ids):
    events = []
    for d in docs:
        for row in d["rows"]:
            slots = row["slots"]
            if family == "TTT_DIRECTED_TRIGRAM":
                for i in range(len(slots) - 2):
                    a, b, c = slots[i:i+3]
                    if (
                        a["kind"] == b["kind"] == c["kind"] == "T"
                        and a["id"] in eligible_ids
                        and b["id"] in eligible_ids
                        and c["id"] in eligible_ids
                    ):
                        events.append(((a["id"], b["id"], c["id"]), d["doc"], d["region"]))
            elif family == "T_NBUCKET_T":
                for i in range(len(slots) - 2):
                    a, b, c = slots[i:i+3]
                    if (
                        a["kind"] == "T"
                        and b["kind"] in NUMERIC_KINDS
                        and c["kind"] == "T"
                        and a["id"] in eligible_ids
                        and c["id"] in eligible_ids
                    ):
                        bucket = b.get("bucket") or numeric_bucket(b["kind"], b.get("value"))
                        events.append(((a["id"], bucket, c["id"]), d["doc"], d["region"]))
            elif family == "ROW_PREFIX_TTT":
                if len(slots) >= 3:
                    a, b, c = slots[0:3]
                    if (
                        a["kind"] == b["kind"] == c["kind"] == "T"
                        and a["id"] in eligible_ids
                        and b["id"] in eligible_ids
                        and c["id"] in eligible_ids
                    ):
                        events.append(((a["id"], b["id"], c["id"]), d["doc"], d["region"]))
            elif family == "ROW_SUFFIX_TTT":
                if len(slots) >= 3:
                    a, b, c = slots[-3:]
                    if (
                        a["kind"] == b["kind"] == c["kind"] == "T"
                        and a["id"] in eligible_ids
                        and b["id"] in eligible_ids
                        and c["id"] in eligible_ids
                    ):
                        events.append(((a["id"], b["id"], c["id"]), d["doc"], d["region"]))
            else:
                raise ValueError(family)
    return events


def motif_stats_from_events(family: str, events):
    counts = Counter(key for key, _doc, _region in events)
    docs_by = defaultdict(set)
    regions_by = defaultdict(set)
    for key, doc, region in events:
        docs_by[key].add(doc)
        regions_by[key].add(region)

    if family == "T_NBUCKET_T":
        left = Counter()
        right = Counter()
        totals = Counter()
        for (a, bucket, b), n in counts.items():
            left[(bucket, a)] += n
            right[(bucket, b)] += n
            totals[bucket] += n
        return {
            "counts": counts,
            "docs_by": docs_by,
            "regions_by": regions_by,
            "left": left,
            "right": right,
            "totals": totals,
        }

    ab = Counter()
    c = Counter()
    total = sum(counts.values())
    for (a, b, c_id), n in counts.items():
        ab[(a, b)] += n
        c[c_id] += n
    return {
        "counts": counts,
        "docs_by": docs_by,
        "regions_by": regions_by,
        "ab": ab,
        "c": c,
        "total": total,
    }


def motif_stats(docs, family: str, eligible_ids):
    return motif_stats_from_events(family, motif_events(docs, family, eligible_ids))


def motif_score(family: str, stats, key):
    obs = stats["counts"].get(key, 0)
    if family == "T_NBUCKET_T":
        a, bucket, b = key
        total = stats["totals"].get(bucket, 0)
        if total <= 0:
            return 0.0
        expected = stats["left"].get((bucket, a), 0) * stats["right"].get((bucket, b), 0) / total
    else:
        a, b, c_id = key
        total = stats["total"]
        if total <= 0:
            return 0.0
        expected = stats["ab"].get((a, b), 0) * stats["c"].get(c_id, 0) / total
    return math.log2((obs + 0.5) / (expected + 0.5))


def neighbor_category(slot, eligible_ids):
    if slot["kind"] == "MASK":
        return "MASK"
    if slot["kind"] in NUMERIC_KINDS:
        return "N:" + (slot.get("bucket") or numeric_bucket(slot["kind"], slot.get("value")))
    if slot["kind"] == "T":
        return "T:" + slot["id"] if slot["id"] in eligible_ids else "T_OTHER"
    return None


def specialization_stats(docs, direction: str, eligible_ids):
    cand_cat = Counter()
    cand_totals = Counter()
    category_totals = Counter()
    docs_by = defaultdict(set)
    regions_by = defaultdict(set)

    for d in docs:
        for row in d["rows"]:
            slots = row["slots"]
            for i, center in enumerate(slots):
                if center["kind"] != "T" or center["id"] not in eligible_ids:
                    continue
                j = i + 1 if direction == "OUT" else i - 1
                if j < 0 or j >= len(slots):
                    continue
                cat = neighbor_category(slots[j], eligible_ids)
                if cat is None:
                    continue
                cid = center["id"]
                cand_cat[(cid, cat)] += 1
                cand_totals[cid] += 1
                category_totals[cat] += 1
                docs_by[cid].add(d["doc"])
                regions_by[cid].add(d["region"])

    return {
        "cand_cat": cand_cat,
        "cand_totals": cand_totals,
        "category_totals": category_totals,
        "total": sum(category_totals.values()),
        "docs_by": docs_by,
        "regions_by": regions_by,
    }


def g_deviance(stats, cid):
    n = stats["cand_totals"].get(cid, 0)
    total = stats["total"]
    if n <= 0 or total <= 0:
        return 0.0
    score = 0.0
    for cat, global_n in stats["category_totals"].items():
        obs = stats["cand_cat"].get((cid, cat), 0)
        if obs <= 0:
            continue
        expected = n * global_n / total
        if expected > 0:
            score += 2.0 * obs * math.log(obs / expected)
    return score


def hypothesis_family_record(family, key=None, cid=None):
    if family in MOTIF_FAMILIES:
        return {"family": family, "kind": "MOTIF", "key": tuple(key)}
    direction = "OUT" if family.endswith("_OUT") else "IN"
    return {"family": family, "kind": "SPECIALIZATION", "candidate_id": cid, "direction": direction}


def observed_hypotheses(docs, eligible_ids, args):
    hyps = []
    for family in MOTIF_FAMILIES:
        stats = motif_stats(docs, family, eligible_ids)
        for key, n in stats["counts"].items():
            nd = len(stats["docs_by"].get(key, set()))
            if n < args.min_screen_n or nd < args.min_screen_docs:
                continue
            h = hypothesis_family_record(family, key=key)
            h.update({
                "screen_count": n,
                "screen_docs": nd,
                "screen_regions": sorted(stats["regions_by"].get(key, set())),
                "screen_score": motif_score(family, stats, key),
            })
            hyps.append(h)

    for family, direction in (
        ("NEIGHBOR_SPECIALIZATION_OUT", "OUT"),
        ("NEIGHBOR_SPECIALIZATION_IN", "IN"),
    ):
        stats = specialization_stats(docs, direction, eligible_ids)
        for cid, n in stats["cand_totals"].items():
            nd = len(stats["docs_by"].get(cid, set()))
            if n < args.min_specialization_n or nd < args.min_specialization_docs:
                continue
            h = hypothesis_family_record(family, cid=cid)
            h.update({
                "screen_count": n,
                "screen_docs": nd,
                "screen_regions": sorted(stats["regions_by"].get(cid, set())),
                "screen_score": g_deviance(stats, cid),
            })
            hyps.append(h)
    return hyps


def score_hypotheses(docs, eligible_ids, hyps):
    by_family = defaultdict(list)
    for i, h in enumerate(hyps):
        by_family[h["family"]].append((i, h))
    scores = [0.0] * len(hyps)

    for family, items in by_family.items():
        if family in MOTIF_FAMILIES:
            stats = motif_stats(docs, family, eligible_ids)
            for i, h in items:
                scores[i] = motif_score(family, stats, h["key"])
        else:
            direction = "OUT" if family.endswith("_OUT") else "IN"
            stats = specialization_stats(docs, direction, eligible_ids)
            for i, h in items:
                scores[i] = g_deviance(stats, h["candidate_id"])
    return scores


def copy_docs_with_shuffle(docs, rng, mode):
    out = []
    for d in docs:
        new_rows = [{"row": r["row"], "slots": [dict(s) for s in r["slots"]]} for r in d["rows"]]
        if mode == "ROW":
            for row in new_rows:
                idxs = [i for i, s in enumerate(row["slots"]) if s["kind"] == "T"]
                ids = [row["slots"][i]["id"] for i in idxs]
                rng.shuffle(ids)
                for i, cid in zip(idxs, ids):
                    row["slots"][i]["id"] = cid
        elif mode == "DOCUMENT":
            locs = []
            ids = []
            for ri, row in enumerate(new_rows):
                for si, s in enumerate(row["slots"]):
                    if s["kind"] == "T":
                        locs.append((ri, si))
                        ids.append(s["id"])
            rng.shuffle(ids)
            for (ri, si), cid in zip(locs, ids):
                new_rows[ri]["slots"][si]["id"] = cid
        else:
            raise ValueError(mode)
        out.append({"doc": d["doc"], "region": d["region"], "rows": new_rows})
    return out


def motif_rewired_stats(docs, family, eligible_ids, rng):
    events = motif_events(docs, family, eligible_ids)
    if family == "T_NBUCKET_T":
        groups = defaultdict(list)
        for (a, bucket, b), doc, region in events:
            groups[bucket].append([a, b, doc, region])
        rewired = []
        for bucket, rows in groups.items():
            rights = [r[1] for r in rows]
            rng.shuffle(rights)
            for r, b2 in zip(rows, rights):
                rewired.append(((r[0], bucket, b2), r[2], r[3]))
        return motif_stats_from_events(family, rewired)

    left_pairs = [(k[0], k[1]) for k, _d, _r in events]
    thirds = [k[2] for k, _d, _r in events]
    rng.shuffle(thirds)
    rewired = []
    for ((a, b), c_id), (_key, doc, region) in zip(zip(left_pairs, thirds), events):
        rewired.append(((a, b, c_id), doc, region))
    return motif_stats_from_events(family, rewired)


def specialization_rewired_stats(docs, direction, eligible_ids, rng):
    base_stats = specialization_stats(docs, direction, eligible_ids)
    edges = []
    for (cid, cat), n in base_stats["cand_cat"].items():
        edges.extend([(cid, cat)] * n)
    cats = [cat for _cid, cat in edges]
    rng.shuffle(cats)
    cand_cat = Counter()
    cand_totals = Counter()
    cat_totals = Counter()
    for (cid, _old), cat in zip(edges, cats):
        cand_cat[(cid, cat)] += 1
        cand_totals[cid] += 1
        cat_totals[cat] += 1
    return {
        "cand_cat": cand_cat,
        "cand_totals": cand_totals,
        "category_totals": cat_totals,
        "total": sum(cat_totals.values()),
        "docs_by": base_stats["docs_by"],
        "regions_by": base_stats["regions_by"],
    }


def score_hypotheses_rewire(docs, eligible_ids, hyps, rng):
    by_family = defaultdict(list)
    for i, h in enumerate(hyps):
        by_family[h["family"]].append((i, h))
    scores = [0.0] * len(hyps)
    for family, items in by_family.items():
        if family in MOTIF_FAMILIES:
            stats = motif_rewired_stats(docs, family, eligible_ids, rng)
            for i, h in items:
                scores[i] = motif_score(family, stats, h["key"])
        else:
            direction = "OUT" if family.endswith("_OUT") else "IN"
            stats = specialization_rewired_stats(docs, direction, eligible_ids, rng)
            for i, h in items:
                scores[i] = g_deviance(stats, h["candidate_id"])
    return scores


def null_family_maxima(docs, eligible_ids, hyps, permutations, seed, mode):
    rng = random.Random(seed)
    family_indexes = defaultdict(list)
    for i, h in enumerate(hyps):
        family_indexes[h["family"]].append(i)
    maxima = {family: [] for family in family_indexes}

    for _ in range(permutations):
        if mode in {"ROW", "DOCUMENT"}:
            perm_docs = copy_docs_with_shuffle(docs, rng, mode)
            scores = score_hypotheses(perm_docs, eligible_ids, hyps)
        elif mode == "REWIRE":
            scores = score_hypotheses_rewire(docs, eligible_ids, hyps, rng)
        else:
            raise ValueError(mode)
        for family, idxs in family_indexes.items():
            maxima[family].append(max(scores[i] for i in idxs) if idxs else 0.0)
    return maxima


def empirical_p_ge(observed, values):
    return (1 + sum(v >= observed for v in values)) / (1 + len(values))


def screen_discovery(docs, args, seed):
    eligible_ids, endpoint_counts, endpoint_docs = endpoint_eligibility(
        docs, args.min_endpoint_n, args.min_endpoint_docs
    )
    hyps = observed_hypotheses(docs, eligible_ids, args)
    if not hyps:
        return {
            "eligible_ids": eligible_ids,
            "endpoint_counts": endpoint_counts,
            "endpoint_docs": endpoint_docs,
            "hypotheses": [],
            "selected": [],
            "null_summary": {},
        }

    row_max = null_family_maxima(docs, eligible_ids, hyps, args.screen_permutations, seed + 11, "ROW")
    doc_max = null_family_maxima(docs, eligible_ids, hyps, args.screen_permutations, seed + 23, "DOCUMENT")
    rw_max = null_family_maxima(docs, eligible_ids, hyps, args.screen_permutations, seed + 37, "REWIRE")

    family_multiplier = len(FAMILIES)
    for h in hyps:
        family = h["family"]
        score = h["screen_score"]
        h["p_maxT_row_within_family"] = empirical_p_ge(score, row_max[family])
        h["p_maxT_document_within_family"] = empirical_p_ge(score, doc_max[family])
        h["p_maxT_rewire_within_family"] = empirical_p_ge(score, rw_max[family])
        h["p_screen_row_family_bonferroni"] = min(1.0, h["p_maxT_row_within_family"] * family_multiplier)
        h["p_screen_document_family_bonferroni"] = min(1.0, h["p_maxT_document_within_family"] * family_multiplier)
        h["p_screen_rewire_family_bonferroni"] = min(1.0, h["p_maxT_rewire_within_family"] * family_multiplier)
        h["screen_max_corrected_p"] = max(
            h["p_screen_row_family_bonferroni"],
            h["p_screen_document_family_bonferroni"],
            h["p_screen_rewire_family_bonferroni"],
        )
        h["screen_pass"] = bool(h["screen_score"] > 0 and h["screen_max_corrected_p"] <= args.alpha)

    hyps.sort(key=lambda h: (h["screen_max_corrected_p"], -h["screen_score"], h["family"], str(h.get("key") or h.get("candidate_id"))))
    selected = [h for h in hyps if h["screen_pass"]]
    return {
        "eligible_ids": eligible_ids,
        "endpoint_counts": endpoint_counts,
        "endpoint_docs": endpoint_docs,
        "hypotheses": hyps,
        "selected": selected,
        "null_summary": {
            "screen_permutations_per_null": args.screen_permutations,
            "family_count_for_bonferroni": family_multiplier,
            "operators": [
                "WITHIN_ROW_SEMANTIC_IDENTITY_SHUFFLE_PRESERVING_TYPED_SLOTS_MASKS_AND_ROW_TOKEN_MULTISET",
                "WITHIN_DOCUMENT_SEMANTIC_IDENTITY_SHUFFLE_PRESERVING_TYPED_SLOTS_MASKS_AND_DOCUMENT_TOKEN_MULTISET",
                "TEMPLATE_ENDPOINT_REWIRE_PRESERVING_FAMILY_CONDITION_AND_ENDPOINT_MARGINALS",
            ],
        },
    }


def support_for_hypothesis(docs, eligible_ids, h):
    if h["kind"] == "MOTIF":
        stats = motif_stats(docs, h["family"], eligible_ids)
        key = h["key"]
        return {
            "count": stats["counts"].get(key, 0),
            "docs": len(stats["docs_by"].get(key, set())),
            "regions": sorted(stats["regions_by"].get(key, set())),
            "score": motif_score(h["family"], stats, key),
        }
    direction = h["direction"]
    stats = specialization_stats(docs, direction, eligible_ids)
    cid = h["candidate_id"]
    return {
        "count": stats["cand_totals"].get(cid, 0),
        "docs": len(stats["docs_by"].get(cid, set())),
        "regions": sorted(stats["regions_by"].get(cid, set())),
        "score": g_deviance(stats, cid),
    }


def evaluable_support(support, h, stage, args):
    if h["kind"] == "MOTIF":
        if stage == "HT_CONFIRM":
            return support["count"] >= args.min_confirm_n and support["docs"] >= args.min_confirm_docs
        return (
            support["count"] >= args.min_test_n
            and support["docs"] >= args.min_test_docs
            and len(support["regions"]) >= args.min_test_regions
        )
    base_ok = support["count"] >= args.min_specialization_n and support["docs"] >= args.min_specialization_docs
    if stage == "NON_HT":
        base_ok = base_ok and len(support["regions"]) >= args.min_test_regions
    return base_ok


def null_fixed_scores(docs, eligible_ids, hyps, permutations, seed, mode):
    rng = random.Random(seed)
    samples = [[] for _ in hyps]
    for _ in range(permutations):
        if mode in {"ROW", "DOCUMENT"}:
            perm_docs = copy_docs_with_shuffle(docs, rng, mode)
            scores = score_hypotheses(perm_docs, eligible_ids, hyps)
        else:
            scores = score_hypotheses_rewire(docs, eligible_ids, hyps, rng)
        for i, score in enumerate(scores):
            samples[i].append(score)
    return samples


def confirm_or_replicate(docs, eligible_ids, locked, args, seed, stage):
    rows = []
    evaluable = []
    for h in locked:
        support = support_for_hypothesis(docs, eligible_ids, h)
        row = {
            "hypothesis": h,
            "support": support,
            "state": "EVALUABLE" if evaluable_support(support, h, stage, args) else "NOT_EVALUABLE",
        }
        rows.append(row)
        if row["state"] == "EVALUABLE":
            evaluable.append(h)

    if not evaluable:
        return {"rows": rows, "evaluable_count": 0, "survivors": [], "survivor_count": 0}

    permutations = args.confirm_permutations if stage == "HT_CONFIRM" else args.test_permutations
    row_samples = null_fixed_scores(docs, eligible_ids, evaluable, permutations, seed + 101, "ROW")
    doc_samples = null_fixed_scores(docs, eligible_ids, evaluable, permutations, seed + 211, "DOCUMENT")
    rw_samples = null_fixed_scores(docs, eligible_ids, evaluable, permutations, seed + 307, "REWIRE")
    multiplier = len(evaluable) * 3

    eval_lookup = {}
    for i, h in enumerate(evaluable):
        support = support_for_hypothesis(docs, eligible_ids, h)
        p_row = empirical_p_ge(support["score"], row_samples[i])
        p_doc = empirical_p_ge(support["score"], doc_samples[i])
        p_rw = empirical_p_ge(support["score"], rw_samples[i])
        b_row = min(1.0, p_row * multiplier)
        b_doc = min(1.0, p_doc * multiplier)
        b_rw = min(1.0, p_rw * multiplier)
        passed = bool(
            support["score"] > 0
            and b_row <= args.alpha
            and b_doc <= args.alpha
            and b_rw <= args.alpha
        )
        eval_lookup[hypothesis_id(h)] = {
            "p_row": p_row,
            "p_document": p_doc,
            "p_rewire": p_rw,
            "p_bonferroni_row": b_row,
            "p_bonferroni_document": b_doc,
            "p_bonferroni_rewire": b_rw,
            "bonferroni_multiplier": multiplier,
            "pass": passed,
        }

    survivors = []
    for row in rows:
        hid = hypothesis_id(row["hypothesis"])
        if row["state"] == "EVALUABLE":
            row.update(eval_lookup[hid])
            row["state"] = "PASS" if row["pass"] else "FAILED_REPLICATION_OR_CONFIRMATION"
            if row["pass"]:
                survivors.append(row["hypothesis"])
    return {
        "rows": rows,
        "evaluable_count": len(evaluable),
        "survivors": survivors,
        "survivor_count": len(survivors),
    }


def hypothesis_id(h):
    if h["kind"] == "MOTIF":
        return h["family"] + "|" + "|".join(map(str, h["key"]))
    return h["family"] + "|" + h["candidate_id"]


def public_hypothesis(h, reveal=None):
    out = {
        "hypothesis_id": hypothesis_id(h),
        "family": h["family"],
        "kind": h["kind"],
        "screen_count": h.get("screen_count"),
        "screen_docs": h.get("screen_docs"),
        "screen_regions": h.get("screen_regions"),
        "screen_score": h.get("screen_score"),
        "p_screen_row_family_bonferroni": h.get("p_screen_row_family_bonferroni"),
        "p_screen_document_family_bonferroni": h.get("p_screen_document_family_bonferroni"),
        "p_screen_rewire_family_bonferroni": h.get("p_screen_rewire_family_bonferroni"),
        "screen_max_corrected_p": h.get("screen_max_corrected_p"),
        "screen_pass": h.get("screen_pass"),
    }
    if h["kind"] == "MOTIF":
        out["key_ids"] = list(h["key"])
        if reveal is not None:
            labels = []
            for part in h["key"]:
                if part in NUMERIC_BUCKETS:
                    labels.append(part)
                else:
                    labels.append(reveal.get(part, "<UNRESOLVED>"))
            out["post_score_labels"] = labels
    else:
        out["candidate_id"] = h["candidate_id"]
        out["direction"] = h["direction"]
        if reveal is not None:
            out["post_score_label"] = reveal.get(h["candidate_id"], "<UNRESOLVED>")
    return out


def public_stage_rows(stage_rows, reveal=None):
    out = []
    for row in stage_rows:
        item = {
            "hypothesis": public_hypothesis(row["hypothesis"], reveal=reveal),
            "support": row["support"],
            "state": row["state"],
        }
        for k in (
            "p_row", "p_document", "p_rewire",
            "p_bonferroni_row", "p_bonferroni_document", "p_bonferroni_rewire",
            "bonferroni_multiplier", "pass",
        ):
            if k in row:
                item[k] = row[k]
        out.append(item)
    return out


def run_channel(channel, docs, reveal, args, seed):
    ch_docs = [channelize_doc(d, channel) for d in docs]
    screen_docs = [d for d in ch_docs if d["region"] == "HT" and deterministic_ht_partition(d["doc"]) == "HT_SCREEN"]
    confirm_docs = [d for d in ch_docs if d["region"] == "HT" and deterministic_ht_partition(d["doc"]) == "HT_CONFIRM"]
    test_docs = [d for d in ch_docs if d["region"] != "HT"]

    discovery = screen_discovery(screen_docs, args, seed)
    locked = [dict(h) for h in discovery["selected"]]

    confirmation = confirm_or_replicate(
        confirm_docs,
        discovery["eligible_ids"],
        locked,
        args,
        seed + 1000,
        "HT_CONFIRM",
    )
    confirmed = [dict(h) for h in confirmation["survivors"]]

    replication = confirm_or_replicate(
        test_docs,
        discovery["eligible_ids"],
        confirmed,
        args,
        seed + 2000,
        "NON_HT",
    )
    replicated = [dict(h) for h in replication["survivors"]]

    frozen_counts = {
        "screen_selected": len(locked),
        "HT_confirmed": len(confirmed),
        "NON_HT_replicated": len(replicated),
    }

    return {
        "channel": channel,
        "claim_bearing": channel == "NOVELTY_MASKED",
        "partition_counts": {
            "HT_SCREEN_documents": len(screen_docs),
            "HT_CONFIRM_documents": len(confirm_docs),
            "NON_HT_documents": len(test_docs),
            "NON_HT_regions": sorted({d["region"] for d in test_docs}),
        },
        "screen": {
            "eligible_semantic_ids": len(discovery["eligible_ids"]),
            "tested_hypotheses": len(discovery["hypotheses"]),
            "selected_count": len(locked),
            "null_summary": discovery["null_summary"],
            "selected_pre_reveal": [public_hypothesis(h) for h in locked],
            "top_25_post_score": [public_hypothesis(h, reveal=reveal) for h in discovery["hypotheses"][:25]],
        },
        "HT_CONFIRM": {
            "evaluable_count": confirmation["evaluable_count"],
            "survivor_count": confirmation["survivor_count"],
            "rows_pre_reveal": public_stage_rows(confirmation["rows"]),
            "rows_post_score_reveal": public_stage_rows(confirmation["rows"], reveal=reveal),
        },
        "NON_HT": {
            "evaluable_count": replication["evaluable_count"],
            "survivor_count": replication["survivor_count"],
            "rows_pre_reveal": public_stage_rows(replication["rows"]),
            "rows_post_score_reveal": public_stage_rows(replication["rows"], reveal=reveal),
        },
        "frozen_counts_before_reveal": frozen_counts,
        "replicated_post_score_reveal": [public_hypothesis(h, reveal=reveal) for h in replicated],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=260814725)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--screen-permutations", type=int, default=1500)
    ap.add_argument("--confirm-permutations", type=int, default=3000)
    ap.add_argument("--test-permutations", type=int, default=3000)
    ap.add_argument("--min-endpoint-n", type=int, default=8)
    ap.add_argument("--min-endpoint-docs", type=int, default=5)
    ap.add_argument("--min-screen-n", type=int, default=4)
    ap.add_argument("--min-screen-docs", type=int, default=3)
    ap.add_argument("--min-confirm-n", type=int, default=3)
    ap.add_argument("--min-confirm-docs", type=int, default=2)
    ap.add_argument("--min-test-n", type=int, default=3)
    ap.add_argument("--min-test-docs", type=int, default=2)
    ap.add_argument("--min-test-regions", type=int, default=2)
    ap.add_argument("--min-specialization-n", type=int, default=8)
    ap.add_argument("--min-specialization-docs", type=int, default=5)
    args = ap.parse_args()

    corpus = Path(args.corpus)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    docs, reveal, failures, multirow = load_corpus(corpus)

    control = run_channel("CONTROL_INCLUDED", docs, reveal, args, args.seed + 10)
    novelty = run_channel("NOVELTY_MASKED", docs, reveal, args, args.seed + 10000)

    novelty_replicated = novelty["frozen_counts_before_reveal"]["NON_HT_replicated"]
    result = {
        "artifact_uuid": ARTIFACT_UUID,
        "version": "v0.8",
        "status": "EXECUTED",
        "title": "JANUS Linear A higher-order typed neighborhood / specialization analysis",
        "source": {
            "repository": "mwenge/lineara.xyz",
            "frozen_commit": base.CORPUS_COMMIT,
            "token_typing_policy_id": typing_policy.POLICY_ID,
            "canonical_parent": CANONICAL_PARENT,
            "canonical_parent_commit": CANONICAL_PARENT_COMMIT,
            "execution_spec": SPEC_PATH,
            "execution_spec_commit": SPEC_COMMIT,
        },
        "methodology": {
            "channels": list(CHANNELS),
            "hypothesis_families": list(FAMILIES),
            "numeric_buckets": list(NUMERIC_BUCKETS),
            "partition_chain": ["HT_SCREEN", "HT_CONFIRM", "NON_HT"],
            "representation": "WORD_ONLY",
            "claim_bearing_channel": "NOVELTY_MASKED",
            "known_control_geometry": "FIXED_MASK_IN_NOVELTY_CHANNEL",
            "screen_error_control": "MAX_T_WITHIN_FAMILY_X_BONFERRONI_ACROSS_SIX_FAMILIES_UNDER_ALL_THREE_NULLS",
            "confirmation_replication_error_control": "LOCKED_ONE_SIDED_SCORE_X_BONFERRONI_OVER_EVALUABLE_HYPOTHESES_X_THREE_NULLS",
            "null_operators": [
                "WITHIN_ROW_SEMANTIC_IDENTITY_SHUFFLE_PRESERVING_TYPED_SLOTS_MASKS_AND_ROW_TOKEN_MULTISET",
                "WITHIN_DOCUMENT_SEMANTIC_IDENTITY_SHUFFLE_PRESERVING_TYPED_SLOTS_MASKS_AND_DOCUMENT_TOKEN_MULTISET",
                "TEMPLATE_ENDPOINT_REWIRE_PRESERVING_FAMILY_CONDITION_AND_ENDPOINT_MARGINALS",
            ],
            "semantic_reveal": "AFTER_SCREEN_CONFIRM_AND_NON_HT_STATES_FROZEN",
            "not_evaluable_is_distinct_from_failed_replication": True,
        },
        "corpus_counts": {
            "item_html_files": len(list((corpus / "items").glob("*.html"))),
            "parsed_documents": len(docs),
            "parse_failures": failures,
            "multirow_words_dropped": multirow,
        },
        "control_channel": control,
        "novelty_channel": novelty,
        "epistemic_gate": {
            "typed_candidate_universe_frozen": True,
            "novel_higher_order_cross_region_survivor_count": novelty_replicated,
            "higher_order_structural_candidate_exists": novelty_replicated > 0,
            "new_anchor_established": False,
            "decipherment_established": False,
            "external_replication_established": False,
            "promotion": (
                "BLOCKED_PENDING_v0.8.1_ALTERNATIVE_SEGMENTATION_NOVELTY_AND_INDEPENDENT_REPLAY"
                if novelty_replicated > 0
                else "NO_PROMOTION"
            ),
        },
        "claim_ceiling": (
            "HIGHER_ORDER_STRUCTURAL_RELATION_CANDIDATE_ONLY"
            if novelty_replicated > 0
            else "REPRESENTATION_CLEAN_NEGATIVE_RESULT_FOR_PREDECLARED_HIGHER_ORDER_TYPED_NEIGHBORHOODS"
        ),
        "next_gate": (
            "v0.8.1_ALTERNATIVE_SEGMENTATION_AND_INDEPENDENT_IMPLEMENTATION_REPLAY"
            if novelty_replicated > 0
            else "FRESH_INDEPENDENT_TRANSCRIPTION_OR_SEPARATELY_FROZEN_NONLOCAL_DOCUMENT_MODEL_WITHOUT_THRESHOLD_RELAXATION"
        ),
    }
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "parsed_documents": len(docs),
        "control_screen_selected": control["frozen_counts_before_reveal"]["screen_selected"],
        "control_HT_confirmed": control["frozen_counts_before_reveal"]["HT_confirmed"],
        "control_NON_HT_replicated": control["frozen_counts_before_reveal"]["NON_HT_replicated"],
        "novelty_screen_selected": novelty["frozen_counts_before_reveal"]["screen_selected"],
        "novelty_HT_confirmed": novelty["frozen_counts_before_reveal"]["HT_confirmed"],
        "novelty_NON_HT_replicated": novelty_replicated,
        "new_anchor_established": False,
        "decipherment_established": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
