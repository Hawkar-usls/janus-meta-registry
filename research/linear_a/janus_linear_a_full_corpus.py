#!/usr/bin/env python3
"""
JANUS Linear A full-corpus blind structural runner.

The scoring stage treats non-numeric sign strings as opaque identifiers. Human-readable
transliterations are revealed only after all statistics and candidate promotion decisions
have been frozen in memory.

No decipherment claim is produced by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Sequence

CORPUS_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
CORPUS_BLOB = "ef41c58802a3135f295072ba60fc0df39450a10c"
ANALYZER_VERSION = "JANUS-LINA-FULL-CORPUS-v0.1"
DEFAULT_SEED = 260814025
BUCKETS = ("FRAC", "ONE", "2_4", "5_9", "10PLUS")

FRACTION_MAP = {
    "¹⁄₂": 1 / 2, "1/2": 1 / 2, "½": 1 / 2,
    "¹⁄₄": 1 / 4, "1/4": 1 / 4, "¼": 1 / 4,
    "³⁄₄": 3 / 4, "3/4": 3 / 4, "¾": 3 / 4,
    "¹⁄₈": 1 / 8, "1/8": 1 / 8, "⅛": 1 / 8,
    "³⁄₈": 3 / 8, "3/8": 3 / 8, "⅜": 3 / 8,
    "⁵⁄₈": 5 / 8, "5/8": 5 / 8, "⅝": 5 / 8,
    "⁷⁄₈": 7 / 8, "7/8": 7 / 8, "⅞": 7 / 8,
    "¹⁄₁₆": 1 / 16, "1/16": 1 / 16,
    "³⁄₁₆": 3 / 16, "3/16": 3 / 16,
    "⁵⁄₁₆": 5 / 16, "5/16": 5 / 16,
    "⁷⁄₁₆": 7 / 16, "7/16": 7 / 16,
}

READING_SPEC_RE = re.compile(r"<reading-spec\b[^>]*>(.*?)</reading-spec>", flags=re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
ROW_RE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(.+?)\s+(certain|doubtful|none)\s*$", re.I)


def stable_id(text: str, namespace: str) -> str:
    return hashlib.sha256(f"{namespace}|{text}".encode("utf-8")).hexdigest()[:16]


def parse_numeric_piece(token: str):
    t = token.strip().replace(",", "")
    if t in FRACTION_MAP:
        return FRACTION_MAP[t]
    if re.fullmatch(r"\d+(?:\.\d+)?", t):
        return float(t)
    return None


def region_of(doc_id: str) -> str:
    m = re.match(r"^([A-Z]{2})", doc_id)
    if m:
        return m.group(1)
    m = re.match(r"^([A-Z]+)", doc_id)
    return m.group(1) if m else "UNK"


def bucket(value: float) -> str:
    if value < 1:
        return "FRAC"
    if value == 1:
        return "ONE"
    if value < 5:
        return "2_4"
    if value < 10:
        return "5_9"
    return "10PLUS"


def parse_inscription(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    m = READING_SPEC_RE.search(text)
    if not m:
        return None
    body = TAG_RE.sub("", m.group(1))
    by_word = defaultdict(list)
    statuses = defaultdict(list)
    for raw in body.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        rm = ROW_RE.match(raw)
        if not rm:
            continue
        _, _, word_i, token, status = rm.groups()
        by_word[int(word_i)].append(token.strip())
        statuses[int(word_i)].append(status.lower())

    words = []
    reveal = {}
    for word_i in sorted(by_word):
        pieces = by_word[word_i]
        numeric_parts = [parse_numeric_piece(x) for x in pieces]
        if all(v is not None for v in numeric_parts):
            value = sum(float(v) for v in numeric_parts)
            if value > 0:
                words.append({"kind": "N", "value": value, "word_index": word_i})
            continue

        raw_word = "·".join(pieces)
        raw_suffix = pieces[-1]
        word_hash = stable_id(raw_word, "WORD")
        suffix_hash = stable_id(raw_suffix, "SUFFIX")
        words.append({
            "kind": "T", "word": word_hash, "suffix": suffix_hash,
            "word_index": word_i, "reading_status": sorted(set(statuses[word_i])),
        })
        reveal.setdefault(word_hash, raw_word)
        reveal.setdefault(suffix_hash, raw_suffix)

    if not words:
        return None
    return {"doc": path.stem, "region": region_of(path.stem), "words": words, "reveal": reveal}


def extract_pairs(docs):
    pairs = []
    for d in docs:
        seq = d["words"]
        for a, b in zip(seq, seq[1:]):
            if a["kind"] == "T" and b["kind"] == "N":
                pairs.append({
                    "doc": d["doc"], "region": d["region"], "word": a["word"],
                    "suffix": a["suffix"], "value": b["value"], "bucket": bucket(b["value"]),
                })
    return pairs


def transition_counts(docs):
    c = Counter()
    for d in docs:
        kinds = [w["kind"] for w in d["words"]]
        for a, b in zip(kinds, kinds[1:]):
            c[a + "->" + b] += 1
    return dict(c)


def adjacency_null(docs, permutations: int, seed: int):
    rng = random.Random(seed)
    observed = transition_counts(docs).get("T->N", 0)
    null = []
    kind_lists = [[w["kind"] for w in d["words"]] for d in docs]
    for _ in range(permutations):
        score = 0
        for kinds0 in kind_lists:
            kinds = list(kinds0)
            rng.shuffle(kinds)
            score += sum(a == "T" and b == "N" for a, b in zip(kinds, kinds[1:]))
        null.append(score)
    p = (1 + sum(x >= observed for x in null)) / (1 + len(null))
    return {
        "observed_T_to_N": observed,
        "null_mean": statistics.fmean(null) if null else None,
        "null_sd": statistics.pstdev(null) if len(null) > 1 else None,
        "empirical_p": p, "permutations": permutations,
        "null_operator": "WITHIN_DOCUMENT_WORD_TYPE_SHUFFLE",
    }


def mutual_information(feature_values: Sequence[str], target_values: Sequence[str]) -> float:
    n = len(feature_values)
    if not n:
        return 0.0
    cx, cy = Counter(feature_values), Counter(target_values)
    cxy = Counter(zip(feature_values, target_values))
    mi = 0.0
    for (x, y), nxy in cxy.items():
        pxy, px, py = nxy / n, cx[x] / n, cy[y] / n
        mi += pxy * math.log2(pxy / (px * py))
    return mi


def within_doc_numeric_shuffle(pairs, permutations: int, seed: int, feature: str):
    rng = random.Random(seed)
    observed = mutual_information([p[feature] for p in pairs], [p["bucket"] for p in pairs])
    by_doc = defaultdict(list)
    for idx, p in enumerate(pairs):
        by_doc[p["doc"]].append(idx)
    null = []
    base_buckets = [p["bucket"] for p in pairs]
    features = [p[feature] for p in pairs]
    for _ in range(permutations):
        shuffled = list(base_buckets)
        for idxs in by_doc.values():
            vals = [shuffled[i] for i in idxs]
            rng.shuffle(vals)
            for i, v in zip(idxs, vals):
                shuffled[i] = v
        null.append(mutual_information(features, shuffled))
    pval = (1 + sum(x >= observed for x in null)) / (1 + len(null))
    return {
        "feature": feature, "observed_mi_bits": observed,
        "null_mean": statistics.fmean(null) if null else None,
        "null_sd": statistics.pstdev(null) if len(null) > 1 else None,
        "empirical_p": pval, "permutations": permutations,
        "null_operator": "WITHIN_DOCUMENT_NUMERIC_BUCKET_SHUFFLE",
    }


def candidate_effects(pairs, feature: str, min_n: int = 8, min_regions: int = 2):
    by_feature = defaultdict(list)
    for p in pairs:
        by_feature[p[feature]].append(p)
    global_mean = statistics.fmean(math.log2(p["value"]) for p in pairs)
    out = {}
    for f, rows in by_feature.items():
        regions = {r["region"] for r in rows}
        if len(rows) < min_n or len(regions) < min_regions:
            continue
        vals = [math.log2(r["value"]) for r in rows]
        mean = statistics.fmean(vals)
        out[f] = {
            "n": len(rows), "regions": sorted(regions), "mean_log2_value": mean,
            "effect_abs_from_global": abs(mean - global_mean),
        }
    return out


def max_t_candidate_null(pairs, feature: str, permutations: int, seed: int, min_n: int = 8, min_regions: int = 2):
    rng = random.Random(seed)
    candidates = candidate_effects(pairs, feature, min_n=min_n, min_regions=min_regions)
    if not candidates:
        return {"feature": feature, "eligible_candidates": 0, "candidates": []}
    global_mean = statistics.fmean(math.log2(p["value"]) for p in pairs)
    feature_indices, region_indices = defaultdict(list), defaultdict(list)
    for i, p in enumerate(pairs):
        if p[feature] in candidates:
            feature_indices[p[feature]].append(i)
        region_indices[p["region"]].append(i)
    logs = [math.log2(p["value"]) for p in pairs]
    max_null = []
    for _ in range(permutations):
        perm = list(logs)
        for idxs in region_indices.values():
            vals = [perm[i] for i in idxs]
            rng.shuffle(vals)
            for i, v in zip(idxs, vals):
                perm[i] = v
        mx = 0.0
        for idxs in feature_indices.values():
            eff = abs(statistics.fmean(perm[i] for i in idxs) - global_mean)
            mx = max(mx, eff)
        max_null.append(mx)
    ranked = []
    for f, meta in candidates.items():
        obs = meta["effect_abs_from_global"]
        fwer_p = (1 + sum(x >= obs for x in max_null)) / (1 + len(max_null))
        ranked.append({"feature_hash": f, **meta, "fwer_p": fwer_p})
    ranked.sort(key=lambda x: (x["fwer_p"], -x["effect_abs_from_global"]))
    return {
        "feature": feature, "eligible_candidates": len(candidates), "permutations": permutations,
        "null_operator": "REGION_PRESERVING_NUMERIC_VALUE_REWIRE_MAX_T", "candidates": ranked[:50],
    }


def region_interaction_candidates(pairs, feature: str, min_per_region: int = 3):
    by_feature_region = defaultdict(lambda: defaultdict(list))
    region_means = defaultdict(list)
    for p in pairs:
        v = math.log2(p["value"])
        by_feature_region[p[feature]][p["region"]].append(v)
        region_means[p["region"]].append(v)
    rmean = {r: statistics.fmean(vs) for r, vs in region_means.items()}
    eligible = {}
    for f, rg0 in by_feature_region.items():
        rg = {r: vs for r, vs in rg0.items() if len(vs) >= min_per_region}
        if len(rg) < 2:
            continue
        residual_means = {r: statistics.fmean(vs) - rmean[r] for r, vs in rg.items()}
        vals = list(residual_means.values())
        eligible[f] = {
            "regions": sorted(rg), "n_by_region": {r: len(rg[r]) for r in sorted(rg)},
            "region_residual_means": residual_means, "max_residual_gap": max(vals) - min(vals),
        }
    return eligible


def region_interaction_null(pairs, feature: str, permutations: int, seed: int, min_per_region: int = 3):
    rng = random.Random(seed)
    eligible = region_interaction_candidates(pairs, feature, min_per_region)
    if not eligible:
        return {"feature": feature, "eligible_candidates": 0, "candidates": []}
    feature_region_indices = defaultdict(lambda: defaultdict(list))
    region_indices = defaultdict(list)
    for i, p in enumerate(pairs):
        region_indices[p["region"]].append(i)
        if p[feature] in eligible:
            feature_region_indices[p[feature]][p["region"]].append(i)
    logs = [math.log2(p["value"]) for p in pairs]
    region_mean = {r: statistics.fmean(logs[i] for i in idxs) for r, idxs in region_indices.items()}
    max_null = []
    for _ in range(permutations):
        perm = list(logs)
        for idxs in region_indices.values():
            vals = [perm[i] for i in idxs]
            rng.shuffle(vals)
            for i, v in zip(idxs, vals):
                perm[i] = v
        mx = 0.0
        for rg in feature_region_indices.values():
            residuals = []
            for r, idxs in rg.items():
                if len(idxs) >= min_per_region:
                    residuals.append(statistics.fmean(perm[i] for i in idxs) - region_mean[r])
            if len(residuals) >= 2:
                mx = max(mx, max(residuals) - min(residuals))
        max_null.append(mx)
    ranked = []
    for f, meta in eligible.items():
        obs = meta["max_residual_gap"]
        p = (1 + sum(x >= obs for x in max_null)) / (1 + len(max_null))
        ranked.append({"feature_hash": f, **meta, "fwer_p": p})
    ranked.sort(key=lambda x: (x["fwer_p"], -x["max_residual_gap"]))
    return {
        "feature": feature, "eligible_candidates": len(eligible), "permutations": permutations,
        "null_operator": "WITHIN_REGION_NUMERIC_REWIRE_MAX_T_ON_REGION_RESIDUAL_GAP",
        "candidates": ranked[:50],
    }


def deterministic_split(doc_id: str) -> str:
    h = int(hashlib.sha256(f"HOLDOUT|{doc_id}".encode()).hexdigest()[:8], 16)
    return "test" if h % 5 == 0 else "train"


def heldout_predictor(pairs, feature: str, min_train: int = 3):
    train = [p for p in pairs if deterministic_split(p["doc"]) == "train"]
    test = [p for p in pairs if deterministic_split(p["doc"]) == "test"]
    if not train or not test:
        return {"feature": feature, "status": "INSUFFICIENT_SPLIT"}
    global_counts = Counter(p["bucket"] for p in train)
    global_pred = global_counts.most_common(1)[0][0]
    feature_counts = defaultdict(Counter)
    for p in train:
        feature_counts[p[feature]][p["bucket"]] += 1
    def pred(row):
        c = feature_counts.get(row[feature])
        if c and sum(c.values()) >= min_train:
            return c.most_common(1)[0][0]
        return global_pred
    acc = sum(pred(p) == p["bucket"] for p in test) / len(test)
    base = sum(global_pred == p["bucket"] for p in test) / len(test)
    covered = sum(sum(feature_counts.get(p[feature], {}).values()) >= min_train for p in test)
    return {
        "feature": feature, "split_operator": "SHA256_DOCUMENT_80_20",
        "train_pairs": len(train), "test_pairs": len(test), "test_accuracy": acc,
        "global_frequency_baseline_accuracy": base, "delta_accuracy": acc - base,
        "covered_test_pairs": covered, "covered_fraction": covered / len(test),
        "promotion_condition": "delta_accuracy > 0 AND candidate survives destructive nulls",
    }


def collect_reveal(docs):
    reveal = {}
    for d in docs:
        reveal.update(d["reveal"])
    return reveal


def reveal_ranked(result, reveal, max_items=20):
    out = []
    for row in result.get("candidates", [])[:max_items]:
        h = row["feature_hash"]
        out.append({"feature_hash": h, "post_score_reveal": reveal.get(h), **{k: v for k, v in row.items() if k != "feature_hash"}})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True, help="Path to frozen lineara.xyz checkout")
    ap.add_argument("--out", required=True)
    ap.add_argument("--permutations", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args()

    corpus = Path(args.corpus)
    paths = sorted((corpus / "items").glob("*.html"))
    if len(paths) < 300:
        raise SystemExit(f"FULL_CORPUS_GATE_FAIL: only {len(paths)} item HTML files found")

    docs, failures = [], []
    for p in paths:
        try:
            d = parse_inscription(p)
            if d:
                docs.append(d)
            else:
                failures.append({"doc": p.stem, "reason": "NO_PARSEABLE_READING_SPEC"})
        except Exception as exc:
            failures.append({"doc": p.stem, "reason": f"PARSE_EXCEPTION:{type(exc).__name__}"})
    if len(docs) < 300:
        raise SystemExit(f"FULL_CORPUS_GATE_FAIL: only {len(docs)} inscriptions parsed")

    pairs = extract_pairs(docs)
    if len(pairs) < 100:
        raise SystemExit(f"FULL_CORPUS_GATE_FAIL: only {len(pairs)} TOKEN->NUMBER pairs")

    reveal = collect_reveal(docs)
    adjacency = adjacency_null(docs, args.permutations, args.seed + 1)
    mi_word = within_doc_numeric_shuffle(pairs, args.permutations, args.seed + 2, "word")
    mi_suffix = within_doc_numeric_shuffle(pairs, args.permutations, args.seed + 3, "suffix")
    cand_word = max_t_candidate_null(pairs, "word", args.permutations, args.seed + 4)
    cand_suffix = max_t_candidate_null(pairs, "suffix", args.permutations, args.seed + 5)
    reg_word = region_interaction_null(pairs, "word", args.permutations, args.seed + 6)
    reg_suffix = region_interaction_null(pairs, "suffix", args.permutations, args.seed + 7)
    hold_word = heldout_predictor(pairs, "word")
    hold_suffix = heldout_predictor(pairs, "suffix")

    strongest_p = min(
        [x.get("fwer_p", 1.0) for x in cand_word.get("candidates", [])]
        + [x.get("fwer_p", 1.0) for x in cand_suffix.get("candidates", [])]
        + [x.get("fwer_p", 1.0) for x in reg_word.get("candidates", [])]
        + [x.get("fwer_p", 1.0) for x in reg_suffix.get("candidates", [])]
        + [1.0]
    )
    candidate_gate = strongest_p <= 0.05 and max(hold_word.get("delta_accuracy", 0), hold_suffix.get("delta_accuracy", 0)) > 0

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-FULL-CORPUS-RUN-2026-08-14",
        "analyzer_version": ANALYZER_VERSION,
        "status": "FULL_CORPUS_EXECUTION_RECEIPT",
        "source": {
            "repository": "mwenge/lineara.xyz", "frozen_commit": CORPUS_COMMIT,
            "LinearAInscriptions_js_blob_sha": CORPUS_BLOB, "input_mode": "items/*.html reading-spec",
        },
        "blindness": {
            "scoring_layer": "OPAQUE_HASHED_TOKEN_IDS", "semantic_glosses_used": False,
            "language_family_labels_used": False, "linear_b_readings_used_as_semantics": False,
            "numeric_values_visible_as_behavioral_anchor": True,
            "important_caveat": "Sign labels are used only for equality/grouping then hashed; this is algorithmic representation blinding, not an independently staffed human-blind replication.",
            "reveal_policy": "Human-readable token strings attached only after all scores and p-values are frozen in memory.",
        },
        "corpus_counts": {
            "item_html_files": len(paths), "parsed_inscriptions": len(docs), "parse_failures": len(failures),
            "token_to_number_pairs": len(pairs), "regions": dict(Counter(d["region"] for d in docs)),
        },
        "pre_registered_buckets": list(BUCKETS),
        "tests": {
            "T_TO_N_ADJACENCY_BASELINE": adjacency,
            "WORD_TO_MAGNITUDE_MI": mi_word, "SUFFIX_TO_MAGNITUDE_MI": mi_suffix,
            "WORD_MAGNITUDE_CANDIDATES_MAX_T": cand_word,
            "SUFFIX_MAGNITUDE_CANDIDATES_MAX_T": cand_suffix,
            "WORD_REGION_INTERACTION_MAX_T": reg_word,
            "SUFFIX_REGION_INTERACTION_MAX_T": reg_suffix,
            "WORD_HELDOUT": hold_word, "SUFFIX_HELDOUT": hold_suffix,
        },
        "post_score_reveal": {
            "word_magnitude_top": reveal_ranked(cand_word, reveal),
            "suffix_magnitude_top": reveal_ranked(cand_suffix, reveal),
            "word_region_interaction_top": reveal_ranked(reg_word, reveal),
            "suffix_region_interaction_top": reveal_ranked(reg_suffix, reveal),
        },
        "failures_sample": failures[:100],
        "epistemic_gate": {
            "strongest_familywise_corrected_p": strongest_p,
            "blind_numeric_candidate_gate_pass": candidate_gate,
            "new_anchor_established": False, "decipherment_established": False,
            "promotion": "FORBIDDEN_UNTIL_LITERATURE_NOVELTY_CHECK_AND_INDEPENDENT_REPLICATION",
            "required_next_if_gate_passes": [
                "verify candidate is not already reported in Linear A scholarship",
                "repeat with independent corpus/parser implementation",
                "cross-region/document holdout replication",
                "behavioral validation that does not derive from the same transcription annotation",
                "alternative segmentation and Linear-B-prior ablation",
            ],
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "artifact": str(out), "parsed_inscriptions": len(docs), "pairs": len(pairs),
        "strongest_fwer_p": strongest_p, "candidate_gate_pass": candidate_gate,
        "new_anchor_established": False, "decipherment_established": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
