#!/usr/bin/env python3
"""JANUS Linear A longer-formula / numeric-bucket neighborhood discovery v0.8.

v0.8 extends the v0.7 relation ontology without relaxing any v0.7 error-control or support
thresholds. It consumes the same v0.6.2 typed-token universe and the same deterministic
HT_SCREEN -> HT_CONFIRM -> NON_HT_REPLICATION partition discipline.

Predeclared motif families:
  TTT  : three consecutive semantic candidates (directed trigram)
  TBT  : semantic candidate -> numeric-like slot -> semantic candidate, where exact numeric
         slots are frozen into FRAC / ONE / 2_4 / 5_9 / 10PLUS buckets and uncertain numeric
         slots remain UNCERTAIN.

Known control families are retained as fixed MASK geometry in the novelty channel. The null is
identical in principle to v0.7: shuffle only anonymous semantic identities within each document,
thereby destroying identity<->longer-neighborhood coupling while preserving document membership,
token-type geometry, numeric buckets, MASK positions, and document-local semantic marginals.

No new-anchor or decipherment claim can be produced by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import janus_linear_a_formula_transition_v0_7 as v7

VERSION = "JANUS-LINA-LONG-FORMULA-v0.8"
ARTIFACT_UUID = "JANUS-LINEAR-A-LONG-FORMULA-NEIGHBORHOOD-2026-08-14-v0.8"


def exact_bucket(value: float) -> str:
    if value < 1:
        return "FRAC"
    if value == 1:
        return "ONE"
    if value < 5:
        return "2_4"
    if value < 10:
        return "5_9"
    return "10PLUS"


def motif_events_v08(doc: dict):
    seq = doc["words"]
    out = []
    for i in range(len(seq) - 2):
        a, b, c = seq[i], seq[i + 1], seq[i + 2]
        if a.get("kind") == "T" and b.get("kind") == "T" and c.get("kind") == "T":
            key = ("TTT", a["word"], b["word"], c["word"], "NONE")
            out.append((key, doc["doc"], doc["region"]))
        if a.get("kind") == "T" and c.get("kind") == "T":
            if b.get("kind") == "N":
                key = ("TBT", a["word"], c["word"], exact_bucket(float(b["value"])), "EXACT")
                out.append((key, doc["doc"], doc["region"]))
            elif b.get("kind") == "N_UNCERTAIN":
                key = ("TBT", a["word"], c["word"], "UNCERTAIN", "UNCERTAIN")
                out.append((key, doc["doc"], doc["region"]))
    return out


def reveal_row_v08(row: dict, reveal: dict) -> dict:
    out = dict(row)
    key = row.get("motif_key") or []
    if not key:
        return out
    if key[0] == "TTT" and len(key) == 5:
        _, a, b, c, _ = key
        out["post_score_reveal"] = {
            "motif_type": "TTT",
            "left_label": reveal.get(a),
            "middle_label": reveal.get(b),
            "right_label": reveal.get(c),
            "numeric_bucket": None,
        }
    elif key[0] == "TBT" and len(key) == 5:
        _, a, c, bucket, slot_class = key
        out["post_score_reveal"] = {
            "motif_type": "TBT",
            "left_label": reveal.get(a),
            "right_label": reveal.get(c),
            "numeric_bucket": bucket,
            "numeric_slot_class": slot_class,
        }
    return out


def evidence_object(row: dict, channel: str) -> dict:
    key = row.get("motif_key", [])
    stable = hashlib.sha256((channel + "|" + "|".join(map(str, key))).encode()).hexdigest()[:16]
    return {
        "evidence_object_id": f"LINA-V08-{stable}",
        "channel": channel,
        "motif_key": key,
        "post_score_reveal": row.get("post_score_reveal"),
        "replication_bonferroni_p": row.get("bonferroni_p"),
        "replication_observed_count": row.get("observed_count"),
        "replication_enrichment_ratio": row.get("enrichment_ratio"),
        "status": "REPLICATED_LONGER_STRUCTURAL_MOTIF_REQUIRES_NOVELTY_AND_BEHAVIORAL_AUDIT",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=260814800)
    # Frozen to the v0.7 values. Do not relax because v0.7 was negative.
    ap.add_argument("--screen-permutations", type=int, default=2000)
    ap.add_argument("--confirm-permutations", type=int, default=5000)
    ap.add_argument("--test-permutations", type=int, default=10000)
    ap.add_argument("--min-screen-n", type=int, default=4)
    ap.add_argument("--min-screen-docs", type=int, default=2)
    ap.add_argument("--screen-p-threshold", type=float, default=0.05)
    ap.add_argument("--max-screen-candidates", type=int, default=40)
    ap.add_argument("--min-confirm-n", type=int, default=2)
    ap.add_argument("--min-confirm-docs", type=int, default=2)
    ap.add_argument("--confirm-alpha", type=float, default=0.05)
    ap.add_argument("--min-test-n", type=int, default=2)
    ap.add_argument("--min-test-docs", type=int, default=2)
    ap.add_argument("--min-test-regions", type=int, default=2)
    ap.add_argument("--test-alpha", type=float, default=0.05)
    args = ap.parse_args()

    # Reuse the v0.7 screening/confirmation/replication machinery with a new frozen ontology.
    v7.motif_events = motif_events_v08
    v7.reveal_row = reveal_row_v08

    corpus = Path(args.corpus)
    docs, failures, reveal = v7.load_docs(corpus)
    control = v7.run_channel("CONTROL_INCLUDED", docs, reveal, args, args.seed + 100)
    novelty = v7.run_channel("NOVELTY_MASKED", docs, reveal, args, args.seed + 200)

    control_survivors = control["replication"]["survivors"]
    novelty_survivors = novelty["replication"]["survivors"]
    evidence = [evidence_object(x, "NOVELTY_MASKED") for x in novelty_survivors]

    result = {
        "artifact_uuid": ARTIFACT_UUID,
        "version": VERSION,
        "status": "LONGER_FORMULA_NEIGHBORHOOD_EXECUTION",
        "inherits_method_from": "JANUS-LINA-FORMULA-TRANSITION-v0.7",
        "source": {
            "repository": "mwenge/lineara.xyz",
            "frozen_commit": v7.base.CORPUS_COMMIT,
            "LinearAInscriptions_js_blob_sha": v7.base.CORPUS_BLOB,
            "typed_token_policy": v7.typing_policy.POLICY_ID,
        },
        "corpus_counts": {
            "parsed_inscriptions": len(docs),
            "parse_failures": len(failures),
            "HT_total": sum(d["region"] == "HT" for d in docs),
            "NON_HT_total": sum(d["region"] != "HT" for d in docs),
        },
        "frozen_candidate_ontology": {
            "candidate_type": "SEMANTIC_CANDIDATE_T_ONLY",
            "motif_families": {
                "TTT": "three consecutive directed semantic candidates",
                "TBT": "semantic candidate -> frozen numeric bucket -> semantic candidate",
            },
            "exact_numeric_buckets": ["FRAC", "ONE", "2_4", "5_9", "10PLUS"],
            "uncertain_numeric_bucket": "UNCERTAIN",
            "known_control_mask_for_novelty_channel": ["VIR*", "KU-RO", "KI-RO", "PO-TO-KU-RO", "GRA"],
            "mask_geometry_rule": "Known controls become fixed MASK positions and are never deleted.",
        },
        "threshold_freeze": {
            "source_stage": "v0.7",
            "lowered_after_negative_result": False,
            "screen_permutations": args.screen_permutations,
            "confirm_permutations": args.confirm_permutations,
            "test_permutations": args.test_permutations,
            "min_screen_n": args.min_screen_n,
            "min_screen_docs": args.min_screen_docs,
            "screen_p_threshold": args.screen_p_threshold,
            "max_screen_candidates": args.max_screen_candidates,
            "min_confirm_n": args.min_confirm_n,
            "min_confirm_docs": args.min_confirm_docs,
            "confirm_alpha_bonferroni": args.confirm_alpha,
            "min_test_n": args.min_test_n,
            "min_test_docs": args.min_test_docs,
            "min_test_regions": args.min_test_regions,
            "test_alpha_bonferroni": args.test_alpha,
        },
        "partitioning": {
            "HT_SCREEN": "same deterministic 3/5 hash partition used by v0.7",
            "HT_CONFIRM": "same deterministic 2/5 hash partition used by v0.7",
            "NON_HT": "all non-HT documents",
            "replication_is_pristine_unseen_holdout": False,
        },
        "null_model": {
            "operator": "WITHIN_DOCUMENT_SEMANTIC_IDENTITY_SHUFFLE",
            "preserves": [
                "document membership",
                "token-type geometry",
                "numeric bucket geometry",
                "uncertain numeric slots",
                "known-family MASK positions",
                "semantic identity multiset per document",
            ],
            "destroys": "semantic identity <-> longer formula neighborhood coupling",
        },
        "channels": {
            "CONTROL_INCLUDED": control,
            "NOVELTY_MASKED": novelty,
        },
        "replicated_novel_structural_evidence_objects": evidence,
        "epistemic_gate": {
            "control_replication_survivor_count": len(control_survivors),
            "novelty_masked_replication_survivor_count": len(novelty_survivors),
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NOVELTY_AND_BEHAVIORAL_AUDIT_REQUIRED" if novelty_survivors else "NO_PROMOTION",
        },
        "required_next": (
            [
                "Deduplicate equivalent longer motifs before counting evidence.",
                "Run post-score literature novelty audit without altering frozen statistics.",
                "Run alternative segmentation and document-role conditioning.",
                "Repeat using an independent transcription/parser and independent implementation before promotion.",
            ] if novelty_survivors else [
                "Retain v0.8 as a valid negative result for the frozen TTT/TBT ontology.",
                "Do not lower statistical or support thresholds in response to the negative result.",
                "Next expansion, if pursued, must be predeclared and structurally distinct (for example row-boundary-conditioned role vectors), not a threshold search.",
                "Prioritize an independent transcription/parser source before further semantic promotion attempts.",
            ]
        ),
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "artifact": str(out),
        "control_screen_selected": control["screen"]["selected_candidate_count"],
        "control_confirm_survivors": control["confirm"]["survivor_count"],
        "control_replication_survivors": len(control_survivors),
        "novelty_screen_selected": novelty["screen"]["selected_candidate_count"],
        "novelty_confirm_survivors": novelty["confirm"]["survivor_count"],
        "novelty_replication_survivors": len(novelty_survivors),
        "new_anchor_established": False,
        "decipherment_established": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
