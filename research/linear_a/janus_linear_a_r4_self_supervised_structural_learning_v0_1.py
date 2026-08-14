#!/usr/bin/env python3
"""JANUS Linear A R4-0 self-supervised structural learner v0.1.

Learns only from opaque source-token identities and directional context.
No translations, language dictionaries, Linear B supervision, or Notti readings are used.
The test partition is document-held-out and never used for model selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import janus_linear_a_full_corpus as base
import janus_linear_a_token_typing_policy_v0_6_2 as typing_policy

VERSION = "JANUS-LINEAR-A-R4-0-SELF-SUPERVISED-v0.1"
FROZEN_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
SPLIT_NAMESPACE = "JANUS-LINA-R4-0-v0.1"
DIRECTIONS = ((-2, "L2"), (-1, "L1"), (1, "R1"), (2, "R2"))


def opaque_token(raw: str) -> str:
    return hashlib.sha256(("R4SIGN|" + raw).encode("utf-8")).hexdigest()[:16]


def split_for_doc(doc_id: str) -> str:
    b = int(hashlib.sha256(f"{SPLIT_NAMESPACE}|{doc_id}".encode("utf-8")).hexdigest()[:8], 16) % 10
    if b <= 7:
        return "TRAIN"
    if b == 8:
        return "DEV"
    return "TEST"


def parse_document(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    m = base.READING_SPEC_RE.search(text)
    if not m:
        return None
    body = base.TAG_RE.sub("", m.group(1))
    rows = defaultdict(list)
    reveal = {}
    for raw_line in body.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        rm = base.ROW_RE.match(raw_line)
        if not rm:
            continue
        row_i, line_i, word_i, raw_token, status = rm.groups()
        token = raw_token.strip()
        if typing_policy.p61.is_nonlexical_piece(token):
            continue
        if typing_policy.is_numeric_like_literal(token):
            continue
        oid = opaque_token(token)
        prior = reveal.get(oid)
        if prior is not None and prior != token:
            raise RuntimeError("OPAQUE_HASH_COLLISION")
        reveal[oid] = token
        rows[int(row_i)].append({
            "token": oid,
            "status": status.lower(),
            "line": int(line_i),
            "word": int(word_i),
        })
    seqs = []
    for row_i in sorted(rows):
        seq = rows[row_i]
        if seq:
            seqs.append({"row": row_i, "tokens": seq})
    if not seqs:
        return None
    return {"doc": path.stem, "split": split_for_doc(path.stem), "rows": seqs, "reveal": reveal}


def load_corpus(root: Path):
    docs = []
    reveal = {}
    failures = 0
    for p in sorted((root / "items").glob("*.html")):
        try:
            d = parse_document(p)
        except Exception:
            d = None
        if d is None:
            failures += 1
            continue
        docs.append(d)
        for k, v in d["reveal"].items():
            if k in reveal and reveal[k] != v:
                raise RuntimeError("GLOBAL_OPAQUE_HASH_COLLISION")
            reveal[k] = v
    if len(docs) < 300:
        raise SystemExit("R4_FULL_CORPUS_GATE_FAIL")
    return docs, reveal, failures


def iter_positions(docs):
    for d in docs:
        for row in d["rows"]:
            toks = row["tokens"]
            for i, item in enumerate(toks):
                yield d, row, toks, i, item


def directional_context(toks, i):
    out = []
    for delta, label in DIRECTIONS:
        j = i + delta
        if 0 <= j < len(toks):
            out.append(f"{label}|{toks[j]['token']}")
    return out


def build_train_model(train_docs, min_freq=5, rank=32):
    freq = Counter(item["token"] for _, _, _, _, item in iter_positions(train_docs))
    docsets = defaultdict(set)
    for d, _, _, _, item in iter_positions(train_docs):
        docsets[item["token"]].add(d["doc"])
    vocab = sorted(t for t, n in freq.items() if n >= min_freq)
    vidx = {t: i for i, t in enumerate(vocab)}

    feature_counts = Counter()
    pair_counts = Counter()
    row_context_totals = Counter()
    for _, _, toks, i, item in iter_positions(train_docs):
        t = item["token"]
        if t not in vidx:
            continue
        for c in directional_context(toks, i):
            pair_counts[(t, c)] += 1
            feature_counts[c] += 1
            row_context_totals[t] += 1

    features = sorted(feature_counts)
    cidx = {c: i for i, c in enumerate(features)}
    counts = np.zeros((len(vocab), len(features)), dtype=np.float64)
    for (t, c), n in pair_counts.items():
        if t in vidx and c in cidx:
            counts[vidx[t], cidx[c]] = float(n)

    total = float(counts.sum())
    row_sum = counts.sum(axis=1)
    col_sum = counts.sum(axis=0)
    ppmi = np.zeros_like(counts)
    nz_i, nz_j = np.nonzero(counts)
    if total > 0:
        vals = np.log((counts[nz_i, nz_j] * total) / (row_sum[nz_i] * col_sum[nz_j]))
        ppmi[nz_i, nz_j] = np.maximum(vals, 0.0)

    if min(ppmi.shape, default=0) >= 2 and np.any(ppmi):
        u, s, vt = np.linalg.svd(ppmi, full_matrices=False)
        k = max(1, min(rank, len(s)))
        latent = u[:, :k] * s[:k]
        reconstructed = latent @ vt[:k, :]
    else:
        k = 0
        latent = np.zeros((len(vocab), 1), dtype=np.float64)
        reconstructed = np.zeros_like(ppmi)

    train_target_total = sum(freq[t] for t in vocab)
    return {
        "freq": freq,
        "docsets": docsets,
        "vocab": vocab,
        "vidx": vidx,
        "features": features,
        "cidx": cidx,
        "counts": counts,
        "feature_counts": feature_counts,
        "row_context_totals": row_context_totals,
        "latent": latent,
        "reconstructed": reconstructed,
        "rank_used": k,
        "train_target_total": train_target_total,
    }


def sorted_rank_indices(scores, vocab):
    return sorted(range(len(vocab)), key=lambda i: (-float(scores[i]), vocab[i]))


def evaluate(test_docs, model):
    vocab = model["vocab"]
    vidx = model["vidx"]
    cidx = model["cidx"]
    V = len(vocab)
    unigram_order = sorted(range(V), key=lambda i: (-model["freq"][vocab[i]], vocab[i]))
    unigram_rank = {i: r + 1 for r, i in enumerate(unigram_order)}
    N = max(1, model["train_target_total"])
    C = max(1, len(model["features"]))
    alpha = 1.0
    prior = np.array([
        math.log((model["freq"][t] + alpha) / (N + alpha * V)) for t in vocab
    ], dtype=np.float64)
    target_context_den = np.array([
        model["row_context_totals"].get(t, 0) + alpha * C for t in vocab
    ], dtype=np.float64)

    stats = {
        name: {"n": 0, "top1": 0, "top5": 0, "rr_sum": 0.0}
        for name in ("B0_UNIGRAM", "B1_DIRECTIONAL_CONTEXT_COUNT", "M1_DIRECTIONAL_PPMI_SVD")
    }
    total_certain = 0
    oov = 0
    no_context = 0

    for _, _, toks, i, item in iter_positions(test_docs):
        if item["status"] != "certain":
            continue
        total_certain += 1
        target = item["token"]
        if target not in vidx:
            oov += 1
            continue
        feat_idx = [cidx[c] for c in directional_context(toks, i) if c in cidx]
        if not feat_idx:
            no_context += 1
            continue
        true_i = vidx[target]

        ranks = {}
        ranks["B0_UNIGRAM"] = unigram_rank[true_i]

        count_scores = prior.copy()
        for cj in feat_idx:
            col = model["counts"][:, cj]
            count_scores += np.log((col + alpha) / target_context_den)
        order = sorted_rank_indices(count_scores, vocab)
        ranks["B1_DIRECTIONAL_CONTEXT_COUNT"] = order.index(true_i) + 1

        svd_scores = model["reconstructed"][:, feat_idx].mean(axis=1)
        order = sorted_rank_indices(svd_scores, vocab)
        ranks["M1_DIRECTIONAL_PPMI_SVD"] = order.index(true_i) + 1

        for name, rank_value in ranks.items():
            s = stats[name]
            s["n"] += 1
            s["top1"] += int(rank_value == 1)
            s["top5"] += int(rank_value <= 5)
            s["rr_sum"] += 1.0 / rank_value

    metrics = {}
    for name, s in stats.items():
        n = s["n"]
        metrics[name] = {
            "evaluable_masks": n,
            "top1_accuracy": s["top1"] / n if n else None,
            "top5_accuracy": s["top5"] / n if n else None,
            "mean_reciprocal_rank": s["rr_sum"] / n if n else None,
        }
    return {
        "total_certain_test_targets": total_certain,
        "oov_test_targets": oov,
        "no_known_context_test_targets": no_context,
        "evaluable_test_masks": stats["M1_DIRECTIONAL_PPMI_SVD"]["n"],
        "coverage": stats["M1_DIRECTIONAL_PPMI_SVD"]["n"] / total_certain if total_certain else 0.0,
        "metrics": metrics,
    }


def sparse_cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def analogy_probe(train_docs, test_docs, model, reveal, topn=30):
    latent = model["latent"]
    vocab = model["vocab"]
    norms = np.linalg.norm(latent, axis=1)
    eligible = [
        i for i, t in enumerate(vocab)
        if model["freq"][t] >= 8 and len(model["docsets"][t]) >= 3 and norms[i] > 0
    ]
    pairs = []
    for ai in range(len(eligible)):
        i = eligible[ai]
        for bj in range(ai + 1, len(eligible)):
            j = eligible[bj]
            sim = float(np.dot(latent[i], latent[j]) / (norms[i] * norms[j]))
            pairs.append((sim, vocab[i], vocab[j]))
    pairs.sort(key=lambda x: (-x[0], x[1], x[2]))
    selected = pairs[:topn]

    test_contexts = defaultdict(Counter)
    test_occ = Counter()
    for _, _, toks, i, item in iter_positions(test_docs):
        t = item["token"]
        test_occ[t] += 1
        for c in directional_context(toks, i):
            test_contexts[t][c] += 1

    scored = []
    for train_cos, a, b in selected:
        eligible_test = test_occ[a] >= 2 and test_occ[b] >= 2
        test_cos = sparse_cosine(test_contexts[a], test_contexts[b]) if eligible_test else None
        replicated = bool(eligible_test and test_cos is not None and test_cos >= 0.20)
        scored.append({
            "token_a": a,
            "token_b": b,
            "train_latent_cosine": train_cos,
            "token_a_test_occurrences": test_occ[a],
            "token_b_test_occurrences": test_occ[b],
            "test_context_cosine": test_cos,
            "test_eligible": eligible_test,
            "replicated_context_similarity": replicated,
        })

    # Reveal occurs only after train selection and test scoring are complete.
    revealed = [
        {
            **row,
            "source_label_a": reveal.get(row["token_a"]),
            "source_label_b": reveal.get(row["token_b"]),
        }
        for row in scored
    ]
    return {
        "selected_train_pairs": len(scored),
        "test_eligible_pairs": sum(r["test_eligible"] for r in scored),
        "test_replicated_pairs": sum(r["replicated_context_similarity"] for r in scored),
        "pairs_after_postscore_source_label_reveal": revealed,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = json.load(open(args.spec, encoding="utf-8"))
    assert spec["source"]["frozen_commit"] == FROZEN_COMMIT
    assert spec["partition"]["selection_from_test_forbidden"] is True
    assert spec["leakage_firewall"]["Notti_2021_2025_PH13_content_used"] is False

    docs, reveal, failures = load_corpus(Path(args.corpus))
    by_split = {s: [d for d in docs if d["split"] == s] for s in ("TRAIN", "DEV", "TEST")}
    model = build_train_model(by_split["TRAIN"], min_freq=5, rank=32)
    evaluation = evaluate(by_split["TEST"], model)
    analogies = analogy_probe(by_split["TRAIN"], by_split["TEST"], model, reveal, topn=30)

    m0 = evaluation["metrics"]["B0_UNIGRAM"]
    m1 = evaluation["metrics"]["M1_DIRECTIONAL_PPMI_SVD"]
    enough = evaluation["evaluable_test_masks"] >= 50
    structure_signal = bool(
        enough and m1["mean_reciprocal_rank"] is not None and m0["mean_reciprocal_rank"] is not None
        and m1["mean_reciprocal_rank"] > m0["mean_reciprocal_rank"]
        and m1["top5_accuracy"] > m0["top5_accuracy"]
    )
    if not enough:
        status = "BLOCKED_INSUFFICIENT_EVALUABLE_TEST_MASKS"
    elif structure_signal:
        status = "SELF_SUPERVISED_INTERNAL_STRUCTURE_SIGNAL_PRESENT"
    else:
        status = "SELF_SUPERVISED_INTERNAL_STRUCTURE_SIGNAL_NOT_ESTABLISHED"

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R4-0-SELF-SUPERVISED-STRUCTURAL-LEARNING-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "self_supervised_structural_learning_result",
        "status": status,
        "source": {
            "repository": "Hawkar-usls/lineara.xyz",
            "upstream_lineage": "mwenge/lineara.xyz",
            "frozen_commit": FROZEN_COMMIT,
            "parsed_documents": len(docs),
            "parse_failures_or_empty": failures,
        },
        "split_counts": {k: len(v) for k, v in by_split.items()},
        "training": {
            "raw_labels_available_to_training": false if False else False,
            "candidate_vocabulary_size": len(model["vocab"]),
            "directional_context_feature_count": len(model["features"]),
            "svd_rank_requested": 32,
            "svd_rank_used": model["rank_used"],
            "minimum_train_frequency": 5,
            "translations_used": False,
            "language_dictionaries_used": False,
            "external_semantic_supervision_used": False,
        },
        "heldout_masked_prediction": evaluation,
        "primary_structure_signal": structure_signal,
        "structural_analogy_probe": analogies,
        "leakage_firewall": {
            "test_used_for_model_selection": False,
            "Notti_2021_2025_PH13_content_used": False,
            "Notti_2018_readings_used": False,
            "R3C_language_dictionary_inputs_used": False,
            "R3B_blind_eligibility_affected": False,
        },
        "epistemic_gate": {
            "internal_distributional_structure_learned": structure_signal,
            "structural_analogy_candidates_are_semantic_equivalences": False,
            "translation_established": False,
            "phonetic_value_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "R3B_external_replication_established": False,
        },
        "claim_ceiling": {
            "allowed": "Held-out predictive structure and train-selected/test-scored structural analogy candidates only.",
            "forbidden": [
                "No translation claim.",
                "No semantic-equivalence claim.",
                "No phonetic assignment.",
                "No language-family assignment.",
                "No new anchor.",
                "No Linear A decipherment.",
                "No R3B external replication."
            ]
        }
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "documents": result["source"]["parsed_documents"],
        "split_counts": result["split_counts"],
        "vocab": result["training"]["candidate_vocabulary_size"],
        "evaluable_test_masks": evaluation["evaluable_test_masks"],
        "metrics": evaluation["metrics"],
        "test_replicated_analogy_pairs": analogies["test_replicated_pairs"],
        "decipherment_established": False,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
