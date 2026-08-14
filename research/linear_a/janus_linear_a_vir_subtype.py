#!/usr/bin/env python3
"""
JANUS Linear A A100-102 versus VIR-family quantitative subtype audit v0.4.

Post-reveal exploratory falsification only. This stage asks whether the held-out survivor
U+10647 (LINEAR A SIGN A100-102) has a numeric magnitude profile beyond the already-known
broader VIR/personnel-logogram family. It cannot establish a lexical anchor or decipherment.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_full_corpus as base
import janus_linear_a_survivor_decomposition as dec

VERSION = "JANUS-LINA-VIR-SUBTYPE-v0.4"
A100_102 = "𐙇"
CANONICAL_313 = {"VIR+*313A", "VIR+*313B", "VIR+*313C"}


def norm(s: str | None) -> str:
    return dec.normalize_label(s or "")


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
    return docs, failures, rows


def is_vir(r):
    return norm(r.get("word_label")).startswith("VIR")


def is_a100_102(r):
    return r.get("unicode_word") == A100_102 and norm(r.get("word_label")) == "VIR+?"


def is_other_vir(r):
    return is_vir(r) and not is_a100_102(r)


def is_313(r):
    return norm(r.get("word_label")) in CANONICAL_313


def summarize(rows):
    by = defaultdict(list)
    for r in rows:
        key = (r.get("word_label"), r.get("unicode_word"))
        by[key].append(r)
    out = []
    for (label, uw), rr in by.items():
        vals = [x["value"] for x in rr]
        out.append({
            "label": label,
            "normalized_label": norm(label),
            "unicode_word": uw,
            "codepoints": [f"U+{ord(ch):04X}" for ch in uw] if uw else [],
            "n": len(rr),
            "documents": len({x["doc"] for x in rr}),
            "regions": sorted({x["region"] for x in rr}),
            "mean_value": statistics.fmean(vals),
            "median_value": statistics.median(vals),
            "mean_log2_value": statistics.fmean(x["log2_value"] for x in rr),
            "min_value": min(vals),
            "max_value": max(vals),
        })
    out.sort(key=lambda x: (-x["n"], x["normalized_label"], x["unicode_word"] or ""))
    return out


def subtype_test(rows, candidate_pred, comparator_pred, permutations, seed, label):
    candidate = [r for r in rows if candidate_pred(r)]
    comparator = [r for r in rows if comparator_pred(r)]
    cand_regions = Counter(r["region"] for r in candidate)
    comp_regions = Counter(r["region"] for r in comparator)
    shared = sorted(set(cand_regions) & set(comp_regions))
    use = [r for r in rows if r["region"] in shared and (candidate_pred(r) or comparator_pred(r))]
    if not shared or len(candidate) < 3 or len(comparator) < 3:
        return {
            "label": label,
            "status": "INSUFFICIENT_SHARED_SUPPORT",
            "candidate_n": len(candidate),
            "comparator_n": len(comparator),
            "shared_regions": shared,
        }

    by_region_vals = defaultdict(list)
    for r in use:
        by_region_vals[r["region"]].append(r["log2_value"])
    rmean = {k: statistics.fmean(v) for k, v in by_region_vals.items()}
    residual = [r["log2_value"] - rmean[r["region"]] for r in use]
    labels = [1 if candidate_pred(r) else 0 for r in use]

    def effect(labs):
        a = [v for v, z in zip(residual, labs) if z == 1]
        b = [v for v, z in zip(residual, labs) if z == 0]
        return statistics.fmean(a) - statistics.fmean(b)

    obs = effect(labels)
    region_idxs = defaultdict(list)
    for i, r in enumerate(use):
        region_idxs[r["region"]].append(i)
    rng = random.Random(seed)
    null = []
    for _ in range(permutations):
        labs = list(labels)
        for idxs in region_idxs.values():
            vals = [labs[i] for i in idxs]
            rng.shuffle(vals)
            for i, z in zip(idxs, vals):
                labs[i] = z
        null.append(effect(labs))
    p2 = (1 + sum(abs(x) >= abs(obs) for x in null)) / (1 + len(null))
    p_high = (1 + sum(x >= obs for x in null)) / (1 + len(null))

    region_effects = {}
    for region in shared:
        aa = [r["log2_value"] for r in use if r["region"] == region and candidate_pred(r)]
        bb = [r["log2_value"] for r in use if r["region"] == region and comparator_pred(r)]
        if aa and bb:
            region_effects[region] = {
                "candidate_n": len(aa),
                "comparator_n": len(bb),
                "delta_mean_log2": statistics.fmean(aa) - statistics.fmean(bb),
            }

    loo = []
    for excluded in shared:
        idxs = [i for i, r in enumerate(use) if r["region"] != excluded]
        labs = [labels[i] for i in idxs]
        vals = [residual[i] for i in idxs]
        if not labs or not any(labs) or all(labs):
            eff = None
        else:
            eff = statistics.fmean(v for v, z in zip(vals, labs) if z) - statistics.fmean(v for v, z in zip(vals, labs) if not z)
        loo.append({"excluded_region": excluded, "delta_residual_log2": eff})

    return {
        "label": label,
        "status": "EXECUTED",
        "candidate_n_all_regions": len(candidate),
        "comparator_n_all_regions": len(comparator),
        "candidate_regions": sorted(cand_regions),
        "comparator_regions": sorted(comp_regions),
        "shared_regions": shared,
        "inference_rows_shared_regions": len(use),
        "candidate_n_shared_regions": sum(candidate_pred(r) for r in use),
        "comparator_n_shared_regions": sum(comparator_pred(r) for r in use),
        "observed_delta_residual_log2": obs,
        "approx_quantity_ratio": 2 ** obs,
        "empirical_p_two_sided": p2,
        "empirical_p_direction_high": p_high,
        "permutations": permutations,
        "null_operator": "WITHIN_REGION_VIR_SUBTYPE_LABEL_PERMUTATION_PRESERVING_COUNTS",
        "region_effects": region_effects,
        "leave_one_region_out": loo,
        "claim_ceiling": "POST_REVEAL_EXPLORATORY_QUANTITATIVE_SUBTYPE_TEST",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--permutations", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=260814325)
    args = ap.parse_args()

    docs, failures, rows = load_rows(Path(args.corpus))
    vir = [r for r in rows if is_vir(r)]
    a100 = [r for r in rows if is_a100_102(r)]
    other = [r for r in rows if is_other_vir(r)]
    v313 = [r for r in rows if is_313(r)]

    broad = subtype_test(
        vir, is_a100_102, is_other_vir,
        args.permutations, args.seed + 1,
        "A100_102_VS_ALL_OTHER_VIR_FAMILY",
    )
    canonical = subtype_test(
        vir, is_a100_102, is_313,
        args.permutations, args.seed + 2,
        "A100_102_VS_VIR_313ABC",
    )

    broad_signal = broad.get("status") == "EXECUTED" and broad.get("empirical_p_two_sided", 1) <= 0.05
    canonical_signal = canonical.get("status") == "EXECUTED" and canonical.get("empirical_p_two_sided", 1) <= 0.05
    same_sign_loo = False
    if broad.get("status") == "EXECUTED":
        vals = [x["delta_residual_log2"] for x in broad.get("leave_one_region_out", []) if x["delta_residual_log2"] is not None]
        same_sign_loo = bool(vals and all(v > 0 for v in vals))

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-VIR-SUBTYPE-2026-08-14-v0.4",
        "version": VERSION,
        "status": "POST_REVEAL_QUANTITATIVE_SUBTYPE_AUDIT",
        "source": {
            "repository": "mwenge/lineara.xyz",
            "frozen_commit": base.CORPUS_COMMIT,
            "LinearAInscriptions_js_blob_sha": base.CORPUS_BLOB,
        },
        "identity": {
            "candidate_unicode": A100_102,
            "candidate_codepoint": "U+10647",
            "unicode_name": "LINEAR A SIGN A100-102",
            "orthographic_identity_stable_in_corpus_numeric_occurrences": len(a100) == 20 and all(r.get("unicode_word") == A100_102 for r in a100),
            "semantic_identity_resolved": False,
            "note": "Unicode stabilizes the encoded base sign; it does not by itself resolve the corpus label VIR+[?] or establish a lexical meaning.",
        },
        "counts": {
            "parsed_inscriptions": len(docs),
            "parse_failures": len(failures),
            "all_token_to_number_pairs": len(rows),
            "vir_family_pairs": len(vir),
            "a100_102_pairs": len(a100),
            "other_vir_pairs": len(other),
            "vir_313abc_pairs": len(v313),
        },
        "vir_family_forms": summarize(vir),
        "tests": {
            "broad_vir_family_contrast": broad,
            "canonical_313_variant_contrast": canonical,
        },
        "epistemic_gate": {
            "broad_subtype_signal": broad_signal,
            "canonical_313_contrast_signal": canonical_signal,
            "leave_one_region_out_positive": same_sign_loo,
            "quantitative_subtype_candidate": bool(broad_signal and same_sign_loo),
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "EXPLORATORY_QUANTITATIVE_CONNECTION_ONLY" if broad_signal and same_sign_loo else "NO_PROMOTION",
            "why_not_anchor": [
                "VIR/personnel semantic class is already known in scholarship",
                "subtype test is post-reveal on the same corpus and is not independent replication",
                "numeric association does not identify a lexical reading or grammatical function",
                "A100-102 encodes a person-class sign but does not resolve the corpus VIR+[?] semantic uncertainty",
            ],
            "required_next_if_signal": [
                "freeze A100-102 quantitative hypothesis before a new corpus/parser implementation",
                "replicate on an independently curated transcription source",
                "condition on document type and commodity/personnel-list structure",
                "test whether A100-102 predicts quantity on held-out inscriptions beyond VIR-family membership",
                "audit scholarship specifically for A100-102 versus A313a/b/c quantity distributions",
            ],
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "artifact": str(out),
        "vir_n": len(vir),
        "a100_102_n": len(a100),
        "other_vir_n": len(other),
        "broad_p_two_sided": broad.get("empirical_p_two_sided"),
        "broad_delta_log2": broad.get("observed_delta_residual_log2"),
        "canonical_p_two_sided": canonical.get("empirical_p_two_sided"),
        "quantitative_subtype_candidate": result["epistemic_gate"]["quantitative_subtype_candidate"],
        "new_anchor_established": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
