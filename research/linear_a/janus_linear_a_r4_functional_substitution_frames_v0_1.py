#!/usr/bin/env python3
"""JANUS Linear A R4-2 cross-fitted functional substitution-frame audit.

Consumes only the four CV-replicated opaque-token pairs selected by R4-1.
For each pair, scoring is restricted to held-out folds in which that pair was
selected from the complementary training documents. Numeric tokens may appear
as typed contexts but can never be prediction/meaning targets.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_full_corpus as base
import janus_linear_a_token_typing_policy_v0_6_2 as typing_policy
import janus_linear_a_r4_self_supervised_structural_learning_v0_1 as r4
import janus_linear_a_r4_five_fold_structural_learning_v0_1 as cv

FROZEN_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"


def numeric_context(token: str) -> str | None:
    exact = typing_policy.parse_exact_numeric_literal(token)
    if exact is not None:
        value = float(exact)
        return "N:" + base.bucket(value)
    if typing_policy.is_numeric_like_literal(token):
        return "N:UNCERTAIN"
    return None


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
        nctx = numeric_context(token)
        if nctx is not None:
            rows[int(row_i)].append({
                "kind": "N", "context": nctx, "status": status.lower(),
                "line": int(line_i), "word": int(word_i)
            })
            continue
        oid = r4.opaque_token(token)
        reveal.setdefault(oid, token)
        rows[int(row_i)].append({
            "kind": "T", "context": oid, "token": oid, "status": status.lower(),
            "line": int(line_i), "word": int(word_i)
        })
    packed = []
    for row_i in sorted(rows):
        if rows[row_i]:
            packed.append({"row": row_i, "items": rows[row_i]})
    if not packed:
        return None
    return {"doc": path.stem, "fold": cv.fold_of(path.stem), "rows": packed, "reveal": reveal}


def load_corpus(root: Path):
    docs, reveal = [], {}
    failures = 0
    for p in sorted((root / "items").glob("*.html")):
        try:
            d = parse_document(p)
        except Exception:
            d = None
        if not d:
            failures += 1
            continue
        docs.append(d)
        reveal.update(d["reveal"])
    if len(docs) < 300:
        raise SystemExit("R4_2_FULL_CORPUS_GATE_FAIL")
    return docs, reveal, failures


def typed_context(x: str) -> str:
    if x in {"BOS", "EOS"}:
        return x
    if x.startswith("N:"):
        return x
    return "T"


def position_class(i: int, n: int) -> str:
    if n == 1:
        return "SINGLE"
    if i == 0:
        return "START"
    if i == n - 1:
        return "END"
    return "MIDDLE"


def occurrences_for_pair(docs, token_a: str, token_b: str, fold: int):
    occ = {token_a: [], token_b: []}
    for d in docs:
        if d["fold"] != fold:
            continue
        for row in d["rows"]:
            items = row["items"]
            n = len(items)
            for i, item in enumerate(items):
                if item.get("kind") != "T" or item.get("token") not in occ:
                    continue
                if item.get("status") != "certain":
                    continue
                left = "BOS" if i == 0 else items[i - 1]["context"]
                right = "EOS" if i == n - 1 else items[i + 1]["context"]
                rec = {
                    "doc": d["doc"],
                    "row": row["row"],
                    "left": left,
                    "right": right,
                    "frame": left + "||" + right,
                    "typed_frame": typed_context(left) + "||" + typed_context(right),
                    "position": position_class(i, n),
                    "numeric_profile": (
                        (left if left.startswith("N:") else "NO_LEFT_NUM") + "||" +
                        (right if right.startswith("N:") else "NO_RIGHT_NUM")
                    ),
                }
                occ[item["token"]].append(rec)
    return occ


def jaccard(a, b):
    a, b = set(a), set(b)
    if not a and not b:
        return None
    return len(a & b) / len(a | b) if (a | b) else None


def cross_document_shared_frames(a_rows, b_rows):
    by_a, by_b = defaultdict(set), defaultdict(set)
    for r in a_rows:
        by_a[r["frame"]].add(r["doc"])
    for r in b_rows:
        by_b[r["frame"]].add(r["doc"])
    out = []
    for frame in sorted(set(by_a) & set(by_b)):
        adocs, bdocs = by_a[frame], by_b[frame]
        cross_doc = any(a != b for a in adocs for b in bdocs)
        if cross_doc:
            out.append({
                "frame": frame,
                "token_a_documents": sorted(adocs),
                "token_b_documents": sorted(bdocs),
            })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--parent-r4-1", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec = json.load(open(args.spec, encoding="utf-8"))
    parent = json.load(open(args.parent_r4_1, encoding="utf-8"))
    assert parent["status"] == "CROSS_VALIDATED_INTERNAL_CONTEXT_STRUCTURE_SIGNAL_PRESENT"
    assert parent["cross_fold_structural_analogy"]["CV_replicated_pair_count"] == 4
    assert spec["source"]["frozen_commit"] == FROZEN_COMMIT
    assert spec["candidate_family"]["candidate_count_required"] == 4
    assert spec["cross_fitting"]["target_reading_status"] == "certain_only"
    assert spec["cross_fitting"]["source_status_none_reinterpreted"] is False

    pairs = parent["cross_fold_structural_analogy"]["CV_replicated_pairs"]
    assert len(pairs) == 4
    docs, reveal, failures = load_corpus(Path(args.corpus))

    pair_results = []
    for pair in pairs:
        a, b = pair["token_a"], pair["token_b"]
        selected_folds = list(pair["folds_selected"])
        fold_results = []
        exact_cross_doc_positive_folds = []
        for fold in selected_folds:
            occ = occurrences_for_pair(docs, a, b, fold)
            ar, br = occ[a], occ[b]
            exact_cross = cross_document_shared_frames(ar, br)
            exact_shared = sorted(set(r["frame"] for r in ar) & set(r["frame"] for r in br))
            typed_shared = sorted(set(r["typed_frame"] for r in ar) & set(r["typed_frame"] for r in br))
            if exact_cross:
                exact_cross_doc_positive_folds.append(fold)
            fold_results.append({
                "fold": fold,
                "token_a_occurrences": len(ar),
                "token_b_occurrences": len(br),
                "token_a_documents": len({r['doc'] for r in ar}),
                "token_b_documents": len({r['doc'] for r in br}),
                "exact_shared_frame_count": len(exact_shared),
                "cross_document_exact_shared_frame_count": len(exact_cross),
                "cross_document_exact_shared_frames": exact_cross,
                "typed_shared_frame_count": len(typed_shared),
                "position_class_jaccard": jaccard([r["position"] for r in ar], [r["position"] for r in br]),
                "numeric_adjacency_profile_jaccard": jaccard([r["numeric_profile"] for r in ar], [r["numeric_profile"] for r in br]),
            })

        positive = len(exact_cross_doc_positive_folds) >= 2
        pair_results.append({
            "token_a": a,
            "token_b": b,
            "selected_folds_from_R4_1": selected_folds,
            "folds_with_cross_document_exact_shared_frame": exact_cross_doc_positive_folds,
            "cross_document_exact_shared_frame_positive_fold_count": len(exact_cross_doc_positive_folds),
            "FUNCTIONAL_SUBSTITUTION_GATE_PASS": positive,
            "fold_results": fold_results,
        })

    family_positive_count = sum(r["FUNCTIONAL_SUBSTITUTION_GATE_PASS"] for r in pair_results)
    family_positive = family_positive_count >= 1
    # Labels are revealed only after all fold evidence is fixed.
    for r in pair_results:
        r["source_label_a_after_scoring"] = reveal.get(r["token_a"])
        r["source_label_b_after_scoring"] = reveal.get(r["token_b"])

    status = (
        "CROSS_FITTED_EXACT_FUNCTIONAL_SUBSTITUTION_EVIDENCE_PRESENT"
        if family_positive else
        "CROSS_FITTED_EXACT_FUNCTIONAL_SUBSTITUTION_EVIDENCE_NOT_ESTABLISHED"
    )
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R4-2-CROSS-FITTED-FUNCTIONAL-SUBSTITUTION-FRAME-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "cross_fitted_functional_substitution_result",
        "status": status,
        "source": {
            "repository": "Hawkar-usls/lineara.xyz",
            "frozen_commit": FROZEN_COMMIT,
            "parsed_documents": len(docs),
            "parse_failures_or_empty": failures,
        },
        "candidate_count": len(pair_results),
        "pair_results": pair_results,
        "summary": {
            "pairs_passing_functional_substitution_gate": family_positive_count,
            "family_functional_substitution_evidence_present": family_positive,
            "target_status": "certain_only",
            "source_status_none_reinterpreted": False,
            "source_status_doubtful_reinterpreted": False,
        },
        "leakage_firewall": {
            "candidate_family_changed_after_R4_1": False,
            "source_labels_used_for_scoring": False,
            "translations_used": False,
            "external_dictionaries_used": False,
            "Notti_readings_used": False,
            "R3B_blind_eligibility_affected": False,
        },
        "epistemic_gate": {
            "functional_substitution_evidence_present": family_positive,
            "semantic_equivalence_established": False,
            "grammatical_label_established": False,
            "translation_established": False,
            "phonetic_value_established": False,
            "new_anchor_established": False,
            "decipherment_established": False,
            "R3B_external_replication_established": False,
        },
        "claim_ceiling": spec["claim_ceiling"],
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "parsed_documents": len(docs),
        "candidate_count": len(pair_results),
        "pairs_passing": family_positive_count,
        "pairs": [
            {
                "labels": [r["source_label_a_after_scoring"], r["source_label_b_after_scoring"]],
                "positive_folds": r["folds_with_cross_document_exact_shared_frame"],
                "pass": r["FUNCTIONAL_SUBSTITUTION_GATE_PASS"],
            } for r in pair_results
        ],
        "decipherment_established": False,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
