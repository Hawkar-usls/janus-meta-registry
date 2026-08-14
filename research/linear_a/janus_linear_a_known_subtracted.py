#!/usr/bin/env python3
"""
JANUS Linear A known-family-subtracted cross-region numeric search v0.5.

Discovery is performed on HT only after a frozen semantic exclusion mask removes families
already explained by prior runs. Candidate scoring uses anonymous hashes only. Replication
is evaluated on non-HT regions. Because earlier JANUS runs have touched the full corpus,
this is explicitly CROSS_REGION_REPLICATION, not a pristine unseen holdout.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

import janus_linear_a_full_corpus as base
import janus_linear_a_survivor_decomposition as dec

VERSION = "JANUS-LINA-KNOWN-SUBTRACTED-v0.5"
KNOWN_ACCOUNTING_WORDS = {"KURO", "KIRO", "POTOKURO"}


def norm(s):
    return dec.normalize_label(s or "")


def excluded_word_label(label):
    x = norm(label)
    return x.startswith("VIR") or x in KNOWN_ACCOUNTING_WORDS


def excluded_candidate_label(label):
    x = norm(label)
    return x == "RO" or x.startswith("VIR")


def load_rows(corpus: Path):
    docs, failures = [], []
    for p in sorted((corpus / "items").glob("*.html")):
        try:
            d = base.parse_inscription(p)
            if d:
                docs.append(d)
            else:
                failures.append({"doc": p.stem, "reason": "NO_PARSEABLE_READING_SPEC"})
        except Exception as exc:
            failures.append({"doc": p.stem, "reason": f"PARSE_EXCEPTION:{type(exc).__name__}"})
    if len(docs) < 300:
        raise SystemExit("FULL_CORPUS_GATE_FAIL")
    reveal = base.collect_reveal(docs)
    rows = dec.detailed_pairs(docs, corpus / "items", reveal)
    if len(rows) < 100:
        raise SystemExit("PAIR_GATE_FAIL")
    return docs, failures, rows, reveal


def eligible_rows(rows):
    return [r for r in rows if not excluded_word_label(r.get("word_label"))]


def candidate_map(rows, key, label_key, min_n):
    by = defaultdict(list)
    for i, r in enumerate(rows):
        if excluded_candidate_label(r.get(label_key)):
            continue
        by[r[key]].append(i)
    return {k: idxs for k, idxs in by.items() if len(idxs) >= min_n}


def train_discovery(rows, key, label_key, min_n, permutations, seed, fwer_threshold):
    cands = candidate_map(rows, key, label_key, min_n)
    logs = [r["log2_value"] for r in rows]
    if not logs:
        return [], []
    overall = statistics.fmean(logs)
    obs = {}
    for cid, idxs in cands.items():
        eff = statistics.fmean(logs[i] for i in idxs) - overall
        obs[cid] = {"n": len(idxs), "effect": eff}
    rng = random.Random(seed)
    max_null = []
    for _ in range(permutations):
        vals = list(logs)
        rng.shuffle(vals)
        mean = statistics.fmean(vals)
        mx = 0.0
        for idxs in cands.values():
            eff = statistics.fmean(vals[i] for i in idxs) - mean
            mx = max(mx, abs(eff))
        max_null.append(mx)
    ranked = []
    for cid, o in obs.items():
        p = (1 + sum(x >= abs(o["effect"]) for x in max_null)) / (1 + len(max_null))
        ranked.append({
            "candidate_id": cid,
            "train_n": o["n"],
            "train_effect_log2": o["effect"],
            "train_direction": "HIGH" if o["effect"] > 0 else "LOW",
            "train_fwer_p": p,
            "selected": p <= fwer_threshold,
        })
    ranked.sort(key=lambda x: (x["train_fwer_p"], -abs(x["train_effect_log2"]), x["candidate_id"]))
    return ranked, [x for x in ranked if x["selected"]]


def cross_region_test(rows, selected, key, label_key, permutations, seed, min_test_n, min_test_regions):
    if not selected or not rows:
        return []
    logs = [r["log2_value"] for r in rows]
    by_region = defaultdict(list)
    for i, r in enumerate(rows):
        by_region[r["region"]].append(i)
    region_mean = {reg: statistics.fmean(logs[i] for i in idxs) for reg, idxs in by_region.items()}
    residual = [logs[i] - region_mean[rows[i]["region"]] for i in range(len(rows))]

    evaluable = []
    for s in selected:
        idxs = [i for i, r in enumerate(rows) if r[key] == s["candidate_id"] and not excluded_candidate_label(r.get(label_key))]
        regs = sorted({rows[i]["region"] for i in idxs})
        if len(idxs) >= min_test_n and len(regs) >= min_test_regions:
            evaluable.append((s, idxs, regs))
    m = max(1, len(evaluable))
    rng = random.Random(seed)
    out = []
    for pos, (s, idxs, regs) in enumerate(evaluable):
        obs = statistics.fmean(residual[i] for i in idxs)
        sign = 1 if s["train_effect_log2"] > 0 else -1
        signed_obs = sign * obs
        null = []
        local_rng = random.Random(rng.randrange(2**63) + pos)
        for _ in range(permutations):
            perm_logs = list(logs)
            for ridxs in by_region.values():
                vals = [perm_logs[i] for i in ridxs]
                local_rng.shuffle(vals)
                for i, v in zip(ridxs, vals):
                    perm_logs[i] = v
            eff = statistics.fmean(perm_logs[i] - region_mean[rows[i]["region"]] for i in idxs)
            null.append(sign * eff)
        p = (1 + sum(x >= signed_obs for x in null)) / (1 + len(null))
        p_bonf = min(1.0, p * m)
        same = (obs > 0) == (s["train_effect_log2"] > 0)
        region_effects = {}
        for reg in regs:
            rr = [residual[i] for i in idxs if rows[i]["region"] == reg]
            region_effects[reg] = {"n": len(rr), "mean_residual_log2": statistics.fmean(rr)}
        out.append({
            **s,
            "test_n": len(idxs),
            "test_regions": regs,
            "test_effect_log2": obs,
            "same_direction": same,
            "test_one_sided_p": p,
            "test_bonferroni_p": p_bonf,
            "replication_pass": bool(same and p_bonf <= 0.05),
            "region_effects": region_effects,
            "revealed_label": rows[idxs[0]].get(label_key),
        })
    out.sort(key=lambda x: (x["test_bonferroni_p"], x["train_fwer_p"]))
    return out


def family_run(all_rows, family, key, label_key, args):
    ht = eligible_rows([r for r in all_rows if r["region"] == "HT"])
    nonht = eligible_rows([r for r in all_rows if r["region"] != "HT"])
    ranked, selected = train_discovery(
        ht, key, label_key, args.min_train_n, args.train_permutations,
        args.seed + (11 if family == "word" else 21), args.train_fwer_threshold,
    )
    rep = cross_region_test(
        nonht, selected, key, label_key, args.test_permutations,
        args.seed + (12 if family == "word" else 22),
        args.min_test_n, args.min_test_regions,
    )
    survivors = [x for x in rep if x["replication_pass"]]
    return {
        "family": family,
        "train_partition": "HT",
        "replication_partition": "NON_HT",
        "train_rows_after_known_family_subtraction": len(ht),
        "test_rows_after_known_family_subtraction": len(nonht),
        "candidate_count_train": len(ranked),
        "selected_train_count": len(selected),
        "evaluable_cross_region_count": len(rep),
        "replication_survivor_count": len(survivors),
        "top_train_candidates": ranked[:20],
        "cross_region_results": rep,
        "survivors": survivors,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=260814425)
    ap.add_argument("--train-permutations", type=int, default=5000)
    ap.add_argument("--test-permutations", type=int, default=10000)
    ap.add_argument("--min-train-n", type=int, default=8)
    ap.add_argument("--min-test-n", type=int, default=4)
    ap.add_argument("--min-test-regions", type=int, default=2)
    ap.add_argument("--train-fwer-threshold", type=float, default=0.10)
    args = ap.parse_args()

    docs, failures, rows, reveal = load_rows(Path(args.corpus))
    word = family_run(rows, "word", "word_hash", "word_label", args)
    suffix = family_run(rows, "suffix", "suffix_hash", "suffix_label", args)
    survivors = [{"family": "word", **x} for x in word["survivors"]] + [{"family": "suffix", **x} for x in suffix["survivors"]]

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-KNOWN-SUBTRACTED-CROSS-REGION-2026-08-14-v0.5",
        "version": VERSION,
        "status": "KNOWN_FAMILY_SUBTRACTED_CROSS_REGION_EXECUTION",
        "source": {
            "repository": "mwenge/lineara.xyz",
            "frozen_commit": base.CORPUS_COMMIT,
            "LinearAInscriptions_js_blob_sha": base.CORPUS_BLOB,
        },
        "corpus_counts": {
            "parsed_inscriptions": len(docs),
            "parse_failures": len(failures),
            "token_to_number_pairs": len(rows),
        },
        "frozen_exclusion_mask": {
            "word_families_removed_before_scoring": ["VIR*", "KU-RO", "KI-RO", "PO-TO-KU-RO"],
            "candidate_suffixes_removed_before_scoring": ["VIR*", "RO"],
            "reason": "These families explained prior held-out survivors and are already known in scholarship.",
            "scoring_after_mask_uses_semantic_labels": False,
        },
        "methodology": {
            "discovery_partition": "HT_ONLY",
            "replication_partition": "ALL_NON_HT",
            "replication_is_pristine_unseen_holdout": False,
            "why_not_pristine": "Earlier JANUS stages touched the full corpus; this stage is a cross-region replication stress test, not a new unseen holdout.",
            "train_candidate_selection": "anonymous word/suffix hashes, max-T FWER under numeric permutation",
            "train_fwer_threshold": args.train_fwer_threshold,
            "test": "within-region numeric rewiring; direction frozen from HT; Bonferroni across evaluable selected candidates",
            "min_train_n": args.min_train_n,
            "min_test_n": args.min_test_n,
            "min_test_regions": args.min_test_regions,
        },
        "word_family": word,
        "suffix_family": suffix,
        "cross_region_survivors": survivors,
        "epistemic_gate": {
            "cross_region_survivor_count": len(survivors),
            "cross_region_candidate_exists": bool(survivors),
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NOVELTY_AND_BEHAVIORAL_AUDIT_REQUIRED" if survivors else "NO_PROMOTION",
            "required_next_if_survivor": [
                "post-score literature novelty audit of revealed candidate label",
                "independent corpus/parser implementation",
                "document-role conditioning and alternative-predecessor controls",
                "fresh external data or independently curated transcription for true held-out replication",
            ],
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "artifact": str(out),
        "word_selected": word["selected_train_count"],
        "word_survivors": word["replication_survivor_count"],
        "suffix_selected": suffix["selected_train_count"],
        "suffix_survivors": suffix["replication_survivor_count"],
        "total_survivors": len(survivors),
        "new_anchor_established": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
