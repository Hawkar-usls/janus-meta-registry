#!/usr/bin/env python3
"""JANUS Linear A formula-transition / neighborhood-role discovery v0.7.

This stage runs only on the authoritative typed-token representation established by v0.6.2.
It asks whether anonymous semantic-token identities participate in reproducible local formula
motifs beyond what is expected from their document-local marginal frequencies.

Two blind motif families are tested:
  TT   : semantic token -> semantic token adjacency
  TNT  : semantic token -> numeric-like slot -> semantic token
         (exact and uncertain numeric slots remain distinct)

Selection is deliberately separated into three partitions:
  HT_SCREEN  -> exploratory candidate generation only
  HT_CONFIRM -> independent within-HT confirmation with Bonferroni correction
  NON_HT     -> cross-region replication with direction locked to enrichment

Two channels are run:
  CONTROL_INCLUDED : known accounting/personnel families remain available as positive controls
  NOVELTY_MASKED   : a frozen pre-score mask blocks already explained dominant families while
                     preserving their positions as MASK tokens so adjacency is never fabricated.

The null shuffles only anonymous semantic identities among eligible T positions within each
document. Document membership, token-type geometry, numeric slots, known-family MASK positions,
and per-document semantic-token counts are preserved. The relation identity<->neighborhood is
destroyed.

No new-anchor or decipherment claim can be emitted by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_full_corpus as base

# Preserve the historical parser handle before installing the authoritative typed parser.
if not hasattr(base, "_JANUS_V061_ORIGINAL_PARSE_NUMERIC_PIECE"):
    base._JANUS_V061_ORIGINAL_PARSE_NUMERIC_PIECE = base.parse_numeric_piece

import janus_linear_a_token_typing_policy_v0_6_2 as typing_policy

base.parse_inscription = typing_policy.corrected_parse_inscription

VERSION = "JANUS-LINA-FORMULA-TRANSITION-v0.7"
ARTIFACT_UUID = "JANUS-LINEAR-A-FORMULA-TRANSITION-NEIGHBORHOOD-2026-08-14-v0.7"
NUMERIC_KINDS = {"N", "N_UNCERTAIN"}
KNOWN_ACCOUNTING_WORDS = {"KURO", "KIRO", "POTOKURO"}
KNOWN_CONTROL_WORDS = KNOWN_ACCOUNTING_WORDS | {"GRA"}
CHANNELS = ("CONTROL_INCLUDED", "NOVELTY_MASKED")


def norm(label: str) -> str:
    return re.sub(r"[^A-Z0-9*]+", "", (label or "").upper())


def is_known_control_label(label: str) -> bool:
    x = norm(label)
    return x.startswith("VIR") or x in KNOWN_CONTROL_WORDS


def deterministic_ht_partition(doc_id: str) -> str:
    h = int(hashlib.sha256(f"JANUS-LINA-v0.7|{doc_id}".encode("utf-8")).hexdigest()[:8], 16)
    return "HT_SCREEN" if h % 5 in {0, 1, 2} else "HT_CONFIRM"


def load_docs(corpus: Path):
    docs, failures, reveal = [], [], {}
    for path in sorted((corpus / "items").glob("*.html")):
        try:
            d = base.parse_inscription(path)
            if not d:
                failures.append({"doc": path.stem, "reason": "NO_PARSEABLE_TYPED_SEQUENCE"})
                continue
            docs.append(d)
            reveal.update(d.get("reveal", {}))
        except Exception as exc:
            failures.append({"doc": path.stem, "reason": f"PARSE_EXCEPTION:{type(exc).__name__}"})
    if len(docs) < 300:
        raise SystemExit("FULL_CORPUS_GATE_FAIL")
    return docs, failures, reveal


def channelize_doc(doc: dict, reveal: dict, channel: str) -> dict:
    words = []
    for w in doc["words"]:
        if w["kind"] != "T":
            words.append(dict(w))
            continue
        if channel == "NOVELTY_MASKED" and is_known_control_label(reveal.get(w["word"], "")):
            words.append({"kind": "MASK", "word_index": w.get("word_index")})
        else:
            words.append(dict(w))
    return {"doc": doc["doc"], "region": doc["region"], "words": words}


def motif_events(doc: dict):
    seq = doc["words"]
    out = []
    for i in range(len(seq) - 1):
        a, b = seq[i], seq[i + 1]
        if a.get("kind") == "T" and b.get("kind") == "T":
            key = ("TT", a["word"], b["word"], "NONE")
            out.append((key, doc["doc"], doc["region"]))
    for i in range(len(seq) - 2):
        a, b, c = seq[i], seq[i + 1], seq[i + 2]
        if a.get("kind") == "T" and b.get("kind") in NUMERIC_KINDS and c.get("kind") == "T":
            slot = "EXACT" if b.get("kind") == "N" else "UNCERTAIN"
            key = ("TNT", a["word"], c["word"], slot)
            out.append((key, doc["doc"], doc["region"]))
    return out


def event_summary(docs):
    counts = Counter()
    docs_by = defaultdict(set)
    regions_by = defaultdict(set)
    for d in docs:
        for key, doc_id, region in motif_events(d):
            counts[key] += 1
            docs_by[key].add(doc_id)
            regions_by[key].add(region)
    return counts, docs_by, regions_by


def shuffled_docs(docs, rng: random.Random):
    out = []
    for d in docs:
        seq = [dict(w) for w in d["words"]]
        idxs = [i for i, w in enumerate(seq) if w.get("kind") == "T"]
        ids = [seq[i]["word"] for i in idxs]
        rng.shuffle(ids)
        for i, cid in zip(idxs, ids):
            seq[i]["word"] = cid
        out.append({"doc": d["doc"], "region": d["region"], "words": seq})
    return out


def permutation_test(docs, candidate_keys, permutations, seed):
    observed, docs_by, regions_by = event_summary(docs)
    keys = list(candidate_keys)
    exceed = Counter()
    null_sum = Counter()
    rng = random.Random(seed)
    for _ in range(permutations):
        null_counts, _null_docs, _null_regions = event_summary(shuffled_docs(docs, rng))
        for key in keys:
            n = null_counts.get(key, 0)
            null_sum[key] += n
            if n >= observed.get(key, 0):
                exceed[key] += 1
    out = []
    for key in keys:
        obs = observed.get(key, 0)
        mean = null_sum[key] / permutations if permutations else 0.0
        p = (1 + exceed[key]) / (1 + permutations)
        out.append({
            "motif_key": list(key),
            "observed_count": obs,
            "documents": len(docs_by.get(key, set())),
            "regions": sorted(regions_by.get(key, set())),
            "null_mean_count": mean,
            "enrichment_count": obs - mean,
            "enrichment_ratio": (obs + 1.0) / (mean + 1.0),
            "empirical_one_sided_p": p,
        })
    out.sort(key=lambda x: (x["empirical_one_sided_p"], -x["enrichment_count"], x["motif_key"]))
    return out


def screen_candidates(docs, args, seed):
    counts, docs_by, _regions_by = event_summary(docs)
    eligible = [
        key for key, n in counts.items()
        if n >= args.min_screen_n and len(docs_by[key]) >= args.min_screen_docs
    ]
    tested = permutation_test(docs, eligible, args.screen_permutations, seed)
    selected = [x for x in tested if x["empirical_one_sided_p"] <= args.screen_p_threshold and x["enrichment_count"] > 0]
    selected = selected[: args.max_screen_candidates]
    return {
        "eligible_candidate_count": len(eligible),
        "tested_candidate_count": len(tested),
        "selected_candidate_count": len(selected),
        "selection_is_claim_bearing": False,
        "screen_p_threshold": args.screen_p_threshold,
        "top_tested": tested[:50],
        "selected": selected,
    }


def confirm_or_replicate(docs, selected, permutations, seed, min_n, min_docs, min_regions, alpha, stage_name):
    counts, docs_by, regions_by = event_summary(docs)
    key_lookup = {tuple(x["motif_key"]): x for x in selected}
    evaluable = []
    for key, source in key_lookup.items():
        n = counts.get(key, 0)
        nd = len(docs_by.get(key, set()))
        nr = len(regions_by.get(key, set()))
        if n < min_n or nd < min_docs or nr < min_regions:
            continue
        evaluable.append(key)
    tested = permutation_test(docs, evaluable, permutations, seed)
    m = max(1, len(tested))
    out = []
    for row in tested:
        key = tuple(row["motif_key"])
        source = key_lookup[key]
        bonf = min(1.0, row["empirical_one_sided_p"] * m)
        out.append({
            **row,
            "source_screen_p": source["empirical_one_sided_p"],
            "bonferroni_family_size": m,
            "bonferroni_p": bonf,
            "pass": bool(row["enrichment_count"] > 0 and bonf <= alpha),
            "stage": stage_name,
        })
    out.sort(key=lambda x: (x["bonferroni_p"], -x["enrichment_count"], x["motif_key"]))
    return {
        "evaluable_count": len(evaluable),
        "tested": out,
        "survivors": [x for x in out if x["pass"]],
        "survivor_count": sum(bool(x["pass"]) for x in out),
        "alpha": alpha,
        "correction": "BONFERRONI_ACROSS_ALL_EVALUABLE_LOCKED_MOTIFS_IN_CHANNEL",
    }


def reveal_row(row: dict, reveal: dict) -> dict:
    key = row.get("motif_key") or []
    if len(key) != 4:
        return dict(row)
    motif_type, left, right, slot = key
    out = dict(row)
    out["post_score_reveal"] = {
        "motif_type": motif_type,
        "left_label": reveal.get(left),
        "right_label": reveal.get(right),
        "numeric_slot_class": slot,
    }
    return out


def run_channel(name, docs, reveal, args, seed_base):
    ch_docs = [channelize_doc(d, reveal, name) for d in docs]
    screen_docs = [d for d in ch_docs if d["region"] == "HT" and deterministic_ht_partition(d["doc"]) == "HT_SCREEN"]
    confirm_docs = [d for d in ch_docs if d["region"] == "HT" and deterministic_ht_partition(d["doc"]) == "HT_CONFIRM"]
    test_docs = [d for d in ch_docs if d["region"] != "HT"]

    screen = screen_candidates(screen_docs, args, seed_base + 1)
    confirm = confirm_or_replicate(
        confirm_docs, screen["selected"], args.confirm_permutations, seed_base + 2,
        args.min_confirm_n, args.min_confirm_docs, 1, args.confirm_alpha, "HT_CONFIRM",
    )
    replication = confirm_or_replicate(
        test_docs, confirm["survivors"], args.test_permutations, seed_base + 3,
        args.min_test_n, args.min_test_docs, args.min_test_regions, args.test_alpha, "NON_HT_REPLICATION",
    )

    # Semantic identity is revealed only after all scoring gates for this channel are complete.
    screen_revealed = [reveal_row(x, reveal) for x in screen["selected"]]
    confirm_revealed = [reveal_row(x, reveal) for x in confirm["tested"]]
    replication_revealed = [reveal_row(x, reveal) for x in replication["tested"]]

    if name == "NOVELTY_MASKED":
        for row in replication_revealed:
            if not row.get("pass"):
                continue
            rr = row["post_score_reveal"]
            if is_known_control_label(rr.get("left_label")) or is_known_control_label(rr.get("right_label")):
                raise SystemExit("NOVELTY_MASK_LEAK")

    return {
        "channel": name,
        "document_counts": {
            "HT_SCREEN": len(screen_docs),
            "HT_CONFIRM": len(confirm_docs),
            "NON_HT": len(test_docs),
        },
        "screen": {**screen, "selected": screen_revealed},
        "confirm": {**confirm, "tested": confirm_revealed, "survivors": [x for x in confirm_revealed if x["pass"]]},
        "replication": {**replication, "tested": replication_revealed, "survivors": [x for x in replication_revealed if x["pass"]]},
    }


def evidence_object(row: dict, channel: str) -> dict:
    rr = row.get("post_score_reveal", {})
    key = row.get("motif_key", [])
    stable = hashlib.sha256((channel + "|" + "|".join(map(str, key))).encode()).hexdigest()[:16]
    return {
        "evidence_object_id": f"LINA-V07-{stable}",
        "channel": channel,
        "motif_key": key,
        "revealed_motif": rr,
        "replication_bonferroni_p": row.get("bonferroni_p"),
        "replication_observed_count": row.get("observed_count"),
        "replication_enrichment_ratio": row.get("enrichment_ratio"),
        "status": "REPLICATED_STRUCTURAL_MOTIF_REQUIRES_NOVELTY_AND_BEHAVIORAL_AUDIT",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=260814700)
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

    corpus = Path(args.corpus)
    docs, failures, reveal = load_docs(corpus)
    control = run_channel("CONTROL_INCLUDED", docs, reveal, args, args.seed + 100)
    novelty = run_channel("NOVELTY_MASKED", docs, reveal, args, args.seed + 200)

    control_survivors = control["replication"]["survivors"]
    novelty_survivors = novelty["replication"]["survivors"]
    evidence = [evidence_object(x, "NOVELTY_MASKED") for x in novelty_survivors]

    result = {
        "artifact_uuid": ARTIFACT_UUID,
        "version": VERSION,
        "status": "FORMULA_TRANSITION_NEIGHBORHOOD_EXECUTION",
        "source": {
            "repository": "mwenge/lineara.xyz",
            "frozen_commit": base.CORPUS_COMMIT,
            "LinearAInscriptions_js_blob_sha": base.CORPUS_BLOB,
            "typed_token_policy": typing_policy.POLICY_ID,
        },
        "corpus_counts": {
            "parsed_inscriptions": len(docs),
            "parse_failures": len(failures),
            "HT_total": sum(d["region"] == "HT" for d in docs),
            "NON_HT_total": sum(d["region"] != "HT" for d in docs),
        },
        "frozen_candidate_ontology": {
            "candidate_type": "SEMANTIC_CANDIDATE_T_ONLY",
            "numeric_types": sorted(NUMERIC_KINDS),
            "motif_families": {
                "TT": "directed semantic-token adjacency",
                "TNT": "semantic token -> numeric-like slot -> semantic token",
            },
            "known_control_mask_for_novelty_channel": ["VIR*", "KU-RO", "KI-RO", "PO-TO-KU-RO", "GRA"],
            "mask_geometry_rule": "Known controls become fixed MASK positions and are not deleted, preventing synthetic adjacency.",
        },
        "partitioning": {
            "HT_SCREEN": "deterministic 3/5 hash partition of HT documents; candidate generation only",
            "HT_CONFIRM": "deterministic 2/5 hash partition of HT documents; independent confirmation",
            "NON_HT": "all non-HT documents; cross-region replication",
            "replication_is_pristine_unseen_holdout": False,
            "why_not_pristine": "Earlier JANUS stages touched the full corpus; NON_HT remains a cross-region replication stress test rather than fresh unseen data.",
        },
        "null_model": {
            "operator": "WITHIN_DOCUMENT_SEMANTIC_IDENTITY_SHUFFLE",
            "preserves": [
                "document membership",
                "token-type geometry",
                "numeric and uncertain-numeric slots",
                "known-family MASK positions",
                "semantic-token count per document",
                "semantic identity multiset per document",
            ],
            "destroys": "semantic identity <-> local neighborhood/formula coupling",
        },
        "thresholds": {
            "screen_permutations": args.screen_permutations,
            "confirm_permutations": args.confirm_permutations,
            "test_permutations": args.test_permutations,
            "screen_p_threshold": args.screen_p_threshold,
            "confirm_alpha_bonferroni": args.confirm_alpha,
            "test_alpha_bonferroni": args.test_alpha,
            "min_test_regions": args.min_test_regions,
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
                "Deduplicate semantically identical survivors into one evidence object before counting support.",
                "Run post-score literature novelty audit without changing the frozen statistical outcome.",
                "Condition surviving motif on document role and alternative-neighbor controls.",
                "Repeat with an independent transcription/parser implementation.",
                "Obtain fresh or independently curated external data before any lexical promotion.",
            ] if novelty_survivors else [
                "Retain v0.7 as a valid negative result for the tested local motif ontology.",
                "Advance to v0.8 with predeclared longer formula neighborhoods or numeric-bucket-conditioned motifs without lowering error-control thresholds.",
                "Add an independent transcription/parser source before calling any later structural survivor externally replicated.",
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
