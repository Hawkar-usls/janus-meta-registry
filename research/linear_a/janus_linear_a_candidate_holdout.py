#!/usr/bin/env python3
"""
JANUS Linear A candidate-specific held-out replication.

Candidate discovery is performed on a deterministic training split only.
Human-readable sign labels are revealed only after the train screen and held-out
test statistics are frozen.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

import janus_linear_a_full_corpus as base

VERSION = "JANUS-LINA-CANDIDATE-HOLDOUT-v0.2"


def split_pairs(pairs):
    train, test = [], []
    for p in pairs:
        (test if base.deterministic_split(p["doc"]) == "test" else train).append(p)
    return train, test


def region_means(rows):
    by = defaultdict(list)
    for p in rows:
        by[p["region"]].append(math.log2(p["value"]))
    return {r: statistics.fmean(vs) for r, vs in by.items()}


def candidate_table(rows, feature, min_n=8, min_regions=2):
    rmean = region_means(rows)
    by = defaultdict(list)
    for p in rows:
        by[p[feature]].append(p)
    out = {}
    for f, rr in by.items():
        regs = sorted({x["region"] for x in rr})
        if len(rr) < min_n or len(regs) < min_regions:
            continue
        residuals = [math.log2(x["value"]) - rmean[x["region"]] for x in rr]
        effect = statistics.fmean(residuals)
        out[f] = {
            "n_train": len(rr),
            "regions_train": regs,
            "train_residual_effect": effect,
            "train_abs_effect": abs(effect),
        }
    return out


def train_max_t(rows, feature, permutations, seed, min_n=8, min_regions=2):
    rng = random.Random(seed)
    candidates = candidate_table(rows, feature, min_n, min_regions)
    if not candidates:
        return {}, []
    feature_idxs = defaultdict(list)
    region_idxs = defaultdict(list)
    logs = [math.log2(p["value"]) for p in rows]
    rmean = region_means(rows)
    for i, p in enumerate(rows):
        region_idxs[p["region"]].append(i)
        if p[feature] in candidates:
            feature_idxs[p[feature]].append(i)
    max_null = []
    for _ in range(permutations):
        perm = list(logs)
        for idxs in region_idxs.values():
            vals = [perm[i] for i in idxs]
            rng.shuffle(vals)
            for i, v in zip(idxs, vals):
                perm[i] = v
        mx = 0.0
        for idxs in feature_idxs.values():
            eff = statistics.fmean(perm[i] - rmean[rows[i]["region"]] for i in idxs)
            mx = max(mx, abs(eff))
        max_null.append(mx)
    ranked = []
    for f, meta in candidates.items():
        obs = meta["train_abs_effect"]
        p = (1 + sum(x >= obs for x in max_null)) / (1 + len(max_null))
        ranked.append({"feature_hash": f, **meta, "train_fwer_p": p})
    ranked.sort(key=lambda x: (x["train_fwer_p"], -x["train_abs_effect"]))
    return candidates, ranked


def heldout_test(test_rows, feature, selected, permutations, seed):
    rng = random.Random(seed)
    rmean = region_means(test_rows)
    by_feature = defaultdict(list)
    region_idxs = defaultdict(list)
    logs = [math.log2(p["value"]) for p in test_rows]
    for i, p in enumerate(test_rows):
        by_feature[p[feature]].append(i)
        region_idxs[p["region"]].append(i)
    evaluable = [x for x in selected if len(by_feature.get(x["feature_hash"], [])) >= 3]
    m = max(1, len(evaluable))
    results = []
    for rank, sel in enumerate(selected, 1):
        f = sel["feature_hash"]
        idxs = by_feature.get(f, [])
        row = {**sel, "train_rank": rank, "n_test": len(idxs)}
        if len(idxs) < 3:
            row.update({
                "heldout_status": "INSUFFICIENT_TEST_OCCURRENCES",
                "heldout_same_direction": None,
                "heldout_p_one_sided": None,
                "heldout_p_bonferroni": None,
                "heldout_survives": False,
            })
            results.append(row)
            continue
        obs = statistics.fmean(logs[i] - rmean[test_rows[i]["region"]] for i in idxs)
        direction = 1 if sel["train_residual_effect"] > 0 else -1
        signed_obs = direction * obs
        null = []
        for _ in range(permutations):
            perm = list(logs)
            for r_idxs in region_idxs.values():
                vals = [perm[i] for i in r_idxs]
                rng.shuffle(vals)
                for i, v in zip(r_idxs, vals):
                    perm[i] = v
            eff = statistics.fmean(perm[i] - rmean[test_rows[i]["region"]] for i in idxs)
            null.append(direction * eff)
        p = (1 + sum(x >= signed_obs for x in null)) / (1 + len(null))
        p_bonf = min(1.0, p * m)
        same = signed_obs > 0
        survives = bool(same and p_bonf <= 0.05)
        row.update({
            "regions_test": sorted({test_rows[i]["region"] for i in idxs}),
            "heldout_residual_effect": obs,
            "heldout_same_direction": same,
            "heldout_p_one_sided": p,
            "heldout_p_bonferroni": p_bonf,
            "heldout_null_operator": "WITHIN_REGION_NUMERIC_REWIRE_DIRECTION_FROZEN_FROM_TRAIN",
            "heldout_survives": survives,
            "heldout_status": "PASS" if survives else "FAIL",
        })
        results.append(row)
    return results


def run_feature(train, test, feature, permutations, seed):
    _, ranked = train_max_t(train, feature, permutations, seed)
    selected = [x for x in ranked if x["train_fwer_p"] <= 0.05]
    tested = heldout_test(test, feature, selected, permutations, seed + 100)
    return {
        "feature": feature,
        "eligible_train_candidates": len(ranked),
        "train_screen_null": "WITHIN_REGION_NUMERIC_REWIRE_MAX_T",
        "train_significant_after_fwer": len(selected),
        "train_selected": selected[:50],
        "heldout_results": tested,
        "survivors": [x for x in tested if x.get("heldout_survives")],
    }


def add_reveal(section, reveal):
    out = json.loads(json.dumps(section))
    for key in ("train_selected", "heldout_results", "survivors"):
        for row in out.get(key, []):
            row["post_score_reveal"] = reveal.get(row["feature_hash"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--permutations", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=260814125)
    args = ap.parse_args()

    paths = sorted((Path(args.corpus) / "items").glob("*.html"))
    docs, failures = [], []
    for p in paths:
        try:
            d = base.parse_inscription(p)
            if d:
                docs.append(d)
            else:
                failures.append(p.stem)
        except Exception:
            failures.append(p.stem)
    pairs = base.extract_pairs(docs)
    if len(docs) < 300 or len(pairs) < 100:
        raise SystemExit("FULL_CORPUS_GATE_FAIL")

    train, test = split_pairs(pairs)
    reveal = base.collect_reveal(docs)
    word_blind = run_feature(train, test, "word", args.permutations, args.seed + 1)
    suffix_blind = run_feature(train, test, "suffix", args.permutations, args.seed + 2)
    survivors = word_blind["survivors"] + suffix_blind["survivors"]

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-CANDIDATE-HOLDOUT-2026-08-14-v0.2",
        "version": VERSION,
        "status": "CANDIDATE_SPECIFIC_HELDOUT_EXECUTION_RECEIPT",
        "source": {
            "repository": "mwenge/lineara.xyz",
            "frozen_commit": base.CORPUS_COMMIT,
            "LinearAInscriptions_js_blob_sha": base.CORPUS_BLOB,
        },
        "split": {
            "operator": "SHA256_DOCUMENT_80_20",
            "train_pairs": len(train),
            "test_pairs": len(test),
            "candidate_selection_reads_test": False,
            "effect_direction_frozen_from_train": True,
        },
        "blindness": {
            "candidate_selection": "OPAQUE_HASHED_TOKEN_IDS",
            "semantic_glosses_used_for_selection": False,
            "post_score_reveal_only": True,
            "caveat": "Algorithmic representation blinding is not independent human replication.",
        },
        "word": add_reveal(word_blind, reveal),
        "suffix": add_reveal(suffix_blind, reveal),
        "epistemic_gate": {
            "heldout_survivor_count": len(survivors),
            "candidate_specific_heldout_gate_pass": len(survivors) > 0,
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NOVELTY_AUDIT_REQUIRED" if survivors else "NO_PROMOTION",
            "required_next_if_survivor": [
                "candidate-specific literature novelty audit",
                "independent parser/corpus implementation",
                "behavioral validation independent of same transcription annotation",
                "alternative segmentation and script-prior ablation",
            ],
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "artifact": str(out),
        "train_pairs": len(train),
        "test_pairs": len(test),
        "word_train_significant": word_blind["train_significant_after_fwer"],
        "suffix_train_significant": suffix_blind["train_significant_after_fwer"],
        "heldout_survivors": len(survivors),
        "new_anchor_established": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
