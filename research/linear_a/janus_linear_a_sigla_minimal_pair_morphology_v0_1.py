#!/usr/bin/env python3
"""JANUS Linear A — SigLA-native one-sign minimal-pair morphology v0.1.

Tests whether a single boundary sign repeatedly forms PREFIX or SUFFIX one-sign
extension pairs over multiple distinct base forms, using only SigLA sign IDs
until SCREEN/CONFIRM/TEST states are frozen.

This is not a translation engine. A survivor is at most a cross-digitization
morphological-operator candidate pending novelty, segmentation, and independent
implementation audits.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import janus_linear_a_sigla_inventory_audit as inv
import janus_linear_a_sigla_document_bridge_v0_1 as bridge
import janus_linear_a_sigla_native_blind_role_v0_1 as role

SPEC_PATH = "data/JANUS-LINEAR-A-SIGLA-MINIMAL-PAIR-MORPHOLOGY-SPEC-2026-08-14-v0.1.json"
SPEC_COMMIT = "3f1fb8ad2e2a1bd0f9378ddb9ba6c0b5bf70ebdd"
MWENGE_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
PARTITION_NAMESPACE = "SIGLA-MORPH-PARTITION-v0.1"
SEED_NAMESPACE = "JANUS-SIGLA-MORPH-v0.1"
SIDES = ("PREFIX", "SUFFIX")
SIGN_RE = re.compile(r"^(?:AB|A)[0-9]+[A-Za-z]?$")


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def partition_bucket(bridge_key: str) -> int:
    return int(sha256_hex(f"{PARTITION_NAMESPACE}|{bridge_key}"), 16) % 10


def partition_name(bucket: int) -> str:
    if bucket <= 5:
        return "SCREEN"
    if bucket <= 7:
        return "CONFIRM"
    return "TEST"


def tokenize_resolved(pattern: str):
    if not pattern or any(x in pattern for x in ("?", "[", "]", "(", ")", " ")):
        return None
    parts = pattern.split("-")
    if not parts or any(not SIGN_RE.fullmatch(x) for x in parts):
        return None
    return tuple(parts)


def rebuild_pairs(sigla_ids: Iterable[str], mwenge_ids: Iterable[str]) -> List[dict]:
    smap = bridge.map_by_key(sigla_ids, bridge.sigla_bridge_key)
    mmap = bridge.map_by_key(mwenge_ids, bridge.mwenge_bridge_key)
    scoll = {k for k, v in smap.items() if len(set(v)) > 1}
    mcoll = {k for k, v in mmap.items() if len(set(v)) > 1}
    keys = sorted(k for k in set(smap) & set(mmap) if k not in scoll and k not in mcoll)
    out = []
    for k in keys:
        b = partition_bucket(k)
        sid = smap[k][0]
        out.append({
            "bridge_key": k,
            "sigla_id": sid,
            "mwenge_id": mmap[k][0],
            "location": role.location_from_sigla_id(sid),
            "partition_bucket": b,
            "partition": partition_name(b),
        })
    return out


def fetch_doc(item: dict, retries: int) -> dict:
    return role.fetch_document(item, retries)


def build_type_inventory(docs: List[dict]) -> dict:
    info = {}
    rejected_occurrences = 0
    accepted_occurrences = 0
    for d in docs:
        if not d.get("ok"):
            continue
        for pat, tr in zip(d["patterns"], d["transliterations"]):
            toks = tokenize_resolved(pat)
            if toks is None:
                rejected_occurrences += 1
                continue
            accepted_occurrences += 1
            key = toks
            row = info.setdefault(key, {
                "tokens": key,
                "occurrences": 0,
                "documents": set(),
                "locations": set(),
                "transliterations": Counter(),
                "examples": [],
            })
            row["occurrences"] += 1
            row["documents"].add(d["bridge_key"])
            row["locations"].add(d["location"])
            if tr:
                row["transliterations"][tr] += 1
            if len(row["examples"]) < 8:
                row["examples"].append({
                    "bridge_key": d["bridge_key"],
                    "sigla_id": d["sigla_id"],
                    "location": d["location"],
                })
    return {
        "types": info,
        "accepted_occurrences": accepted_occurrences,
        "rejected_occurrences": rejected_occurrences,
    }


def observed_edges(type_info: dict, side: str) -> Dict[str, dict]:
    types = type_info
    by_sign = {}
    for ext_tokens, ext in types.items():
        if len(ext_tokens) < 2:
            continue
        if side == "PREFIX":
            sign = ext_tokens[0]
            stem = ext_tokens[1:]
        else:
            sign = ext_tokens[-1]
            stem = ext_tokens[:-1]
        if stem not in types:
            continue
        row = by_sign.setdefault(sign, {
            "sign": sign,
            "side": side,
            "stems": set(),
            "extended_documents": set(),
            "locations": set(),
            "edges": [],
        })
        if stem in row["stems"]:
            continue
        row["stems"].add(stem)
        row["extended_documents"].update(ext["documents"])
        row["locations"].update(ext["locations"])
        row["edges"].append({
            "stem": stem,
            "extended": ext_tokens,
            "extended_documents": sorted(ext["documents"]),
        })

    out = {}
    for sign, row in by_sign.items():
        out[sign] = {
            **row,
            "distinct_stems": len(row["stems"]),
            "extended_variant_documents": len(row["extended_documents"]),
            "distinct_locations": len(row["locations"]),
        }
    return out


def null_edge_counts(type_info: dict, side: str, candidate_signs: List[str], permutations: int, seed_text: str) -> Dict[str, List[int]]:
    rng = random.Random(int(sha256_hex(seed_text), 16))
    types = set(type_info)
    groups = defaultdict(list)
    for toks in types:
        if len(toks) < 2:
            continue
        if side == "PREFIX":
            boundary, stem = toks[0], toks[1:]
        else:
            boundary, stem = toks[-1], toks[:-1]
        groups[len(toks)].append((boundary, stem))

    wanted = set(candidate_signs)
    out = {s: [] for s in candidate_signs}
    for _ in range(permutations):
        stems_by_sign = defaultdict(set)
        for _, rows in groups.items():
            labels = [x[0] for x in rows]
            rng.shuffle(labels)
            for new_sign, (_, stem) in zip(labels, rows):
                if new_sign in wanted and stem in types:
                    stems_by_sign[new_sign].add(stem)
        for sign in candidate_signs:
            out[sign].append(len(stems_by_sign.get(sign, ())))
    return out


def serialize_edge_row(row: dict, type_info: dict, reveal: bool = False) -> dict:
    base = {
        "sign_id": row["sign"],
        "side": row["side"],
        "distinct_stems": row["distinct_stems"],
        "extended_variant_documents": row["extended_variant_documents"],
        "distinct_locations": row["distinct_locations"],
        "locations": sorted(row["locations"]),
    }
    if reveal:
        edges = []
        for e in row["edges"][:20]:
            stem_info = type_info[e["stem"]]
            ext_info = type_info[e["extended"]]
            edges.append({
                "stem_sign_sequence": "-".join(e["stem"]),
                "extended_sign_sequence": "-".join(e["extended"]),
                "stem_transliterations": [{"value": k, "count": v} for k, v in stem_info["transliterations"].most_common(3)],
                "extended_transliterations": [{"value": k, "count": v} for k, v in ext_info["transliterations"].most_common(3)],
                "extended_documents": e["extended_documents"][:10],
            })
        base["edge_reveal"] = edges
    return base


def sign_hash(sign: str) -> str:
    return sha256_hex(f"SIGLA-SIGN-v0.1|{sign}")


def screen_stage(type_info: dict, permutations: int, alpha: float) -> dict:
    obs = {side: observed_edges(type_info, side) for side in SIDES}
    hyps = []
    for side in SIDES:
        for sign, row in obs[side].items():
            if row["distinct_stems"] >= 3 and row["extended_variant_documents"] >= 4:
                hyps.append((sign, side))
    if not hyps:
        return {
            "eligible_hypothesis_count": 0,
            "tested": [],
            "selected": [],
            "selected_count": 0,
            "observed_edge_sign_count": {s: len(obs[s]) for s in SIDES},
        }

    nulls = {}
    for side in SIDES:
        signs = sorted({sign for sign, s in hyps if s == side})
        if signs:
            nulls[side] = null_edge_counts(type_info, side, signs, permutations, f"{SEED_NAMESPACE}|SCREEN|{side}|{permutations}")
    m = len(hyps)
    tested = []
    for sign, side in hyps:
        row = obs[side][sign]
        vals = nulls[side][sign]
        observed = row["distinct_stems"]
        p = (1 + sum(1 for x in vals if x >= observed)) / (len(vals) + 1)
        null_mean = sum(vals) / len(vals)
        item = {
            "sign_id_hash": sign_hash(sign),
            "side": side,
            "distinct_stems": observed,
            "extended_variant_documents": row["extended_variant_documents"],
            "distinct_locations": row["distinct_locations"],
            "null_mean_distinct_stems": null_mean,
            "effect": observed - null_mean,
            "p_empirical_one_sided": p,
            "p_bonferroni": min(1.0, p * m),
        }
        item["selected"] = item["effect"] > 0 and item["p_bonferroni"] <= alpha
        tested.append(item)
    tested.sort(key=lambda x: (x["p_bonferroni"], -x["effect"], x["sign_id_hash"], x["side"]))
    selected = [x for x in tested if x["selected"]]
    return {
        "eligible_hypothesis_count": m,
        "tested": tested,
        "selected": selected,
        "selected_count": len(selected),
        "observed_edge_sign_count": {s: len(obs[s]) for s in SIDES},
    }


def locked_stage(type_info: dict, locked_rows: List[dict], permutations: int, alpha: float, min_stems: int, min_docs: int, min_locations: int, stage_name: str) -> dict:
    if not locked_rows:
        return {
            "locked_count": 0,
            "evaluable_count": 0,
            "survivor_count": 0,
            "tested": [],
            "survivors": [],
            "state": "NOT_ENTERED_NO_LOCKED_HYPOTHESES",
        }

    obs = {side: observed_edges(type_info, side) for side in SIDES}
    not_eval = []
    evaluable = []
    for source_row in locked_rows:
        sign = None
        for s in obs[source_row["side"]]:
            if sign_hash(s) == source_row["sign_id_hash"]:
                sign = s
                break
        if sign is None:
            not_eval.append({
                "sign_id_hash": source_row["sign_id_hash"],
                "side": source_row["side"],
                "state": "NOT_EVALUABLE",
                "reason": "NO_EXTENSION_EDGE_IN_PARTITION",
                "distinct_stems": 0,
                "extended_variant_documents": 0,
                "distinct_locations": 0,
            })
            continue
        r = obs[source_row["side"]][sign]
        reason = None
        if r["distinct_stems"] < min_stems:
            reason = f"DISTINCT_STEMS_BELOW_MIN:{r['distinct_stems']}<{min_stems}"
        elif r["extended_variant_documents"] < min_docs:
            reason = f"DOCUMENTS_BELOW_MIN:{r['extended_variant_documents']}<{min_docs}"
        elif min_locations and r["distinct_locations"] < min_locations:
            reason = f"LOCATIONS_BELOW_MIN:{r['distinct_locations']}<{min_locations}"
        if reason:
            not_eval.append({
                "sign_id_hash": source_row["sign_id_hash"],
                "side": source_row["side"],
                "state": "NOT_EVALUABLE",
                "reason": reason,
                "distinct_stems": r["distinct_stems"],
                "extended_variant_documents": r["extended_variant_documents"],
                "distinct_locations": r["distinct_locations"],
            })
        else:
            evaluable.append((sign, source_row["side"]))

    if not evaluable:
        return {
            "locked_count": len(locked_rows),
            "evaluable_count": 0,
            "survivor_count": 0,
            "tested": not_eval,
            "survivors": [],
            "state": "NO_EVALUABLE_LOCKED_HYPOTHESES",
        }

    nulls = {}
    for side in SIDES:
        signs = sorted({s for s, sd in evaluable if sd == side})
        if signs:
            nulls[side] = null_edge_counts(type_info, side, signs, permutations, f"{SEED_NAMESPACE}|{stage_name}|{side}|{permutations}")

    m = len(locked_rows)
    tested = list(not_eval)
    survivors = []
    for sign, side in evaluable:
        r = obs[side][sign]
        vals = nulls[side][sign]
        observed = r["distinct_stems"]
        p = (1 + sum(1 for x in vals if x >= observed)) / (len(vals) + 1)
        null_mean = sum(vals) / len(vals)
        item = {
            "sign_id_hash": sign_hash(sign),
            "side": side,
            "distinct_stems": observed,
            "extended_variant_documents": r["extended_variant_documents"],
            "distinct_locations": r["distinct_locations"],
            "null_mean_distinct_stems": null_mean,
            "effect": observed - null_mean,
            "p_empirical_one_sided": p,
            "p_bonferroni": min(1.0, p * m),
            "state": "EVALUATED",
        }
        item["survived"] = item["effect"] > 0 and item["p_bonferroni"] <= alpha
        tested.append(item)
        if item["survived"]:
            survivors.append(item)

    return {
        "locked_count": len(locked_rows),
        "evaluable_count": len(evaluable),
        "survivor_count": len(survivors),
        "tested": tested,
        "survivors": survivors,
        "state": "EVALUATED",
    }


def reveal_hypotheses(type_info: dict, rows: List[dict]) -> List[dict]:
    obs = {side: observed_edges(type_info, side) for side in SIDES}
    revealed = []
    for r in rows:
        side = r["side"]
        sign = None
        for s in obs[side]:
            if sign_hash(s) == r["sign_id_hash"]:
                sign = s
                break
        item = dict(r)
        if sign is None:
            item["sign_id"] = None
            item["edge_reveal"] = []
        else:
            item.update(serialize_edge_row(obs[side][sign], type_info, reveal=True))
        revealed.append(item)
    return revealed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mwenge-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--screen-permutations", type=int, default=3000)
    ap.add_argument("--confirm-permutations", type=int, default=5000)
    ap.add_argument("--test-permutations", type=int, default=5000)
    ap.add_argument("--alpha", type=float, default=0.05)
    args = ap.parse_args()

    _, _, _, db_body = role.fetch_with_retries("https://sigla.phis.me/database.js", retries=args.retries)
    db_sha = hashlib.sha256(db_body).hexdigest()
    if db_sha != role.FROZEN_SIGLA_DATABASE_SHA256:
        raise SystemExit(f"SIGLA_DATABASE_SHA_MISMATCH:{db_sha}")

    _, _, _, browse_body = role.fetch_with_retries(inv.DEFAULT_SIGLA_URL, retries=args.retries)
    browse_sha = hashlib.sha256(browse_body).hexdigest()
    if browse_sha != role.FROZEN_SIGLA_BROWSE_SHA256:
        raise SystemExit(f"SIGLA_BROWSE_SHA_MISMATCH:{browse_sha}")
    bp = inv.SigLABrowseParser()
    bp.feed(browse_body.decode("utf-8", errors="replace"))
    sigla_ids = sorted({x for h in bp.document_hrefs if (x := inv.extract_sigla_id_from_href(h))})
    mwenge_ids = inv.inventory_mwenge(Path(args.mwenge_root))
    pairs = rebuild_pairs(sigla_ids, mwenge_ids)
    if len(pairs) != 686:
        raise SystemExit(f"BRIDGE_COUNT_MISMATCH:{len(pairs)}")

    docs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(fetch_doc, p, args.retries) for p in pairs]
        for fut in concurrent.futures.as_completed(futs):
            docs.append(fut.result())
    docs.sort(key=lambda x: x["bridge_key"])

    parse_ok = [d for d in docs if d.get("ok")]
    if len(parse_ok) < 400 or len(parse_ok) / 686.0 < 0.80:
        raise SystemExit(f"PARSER_COVERAGE_GATE_FAIL:{len(parse_ok)}/686")

    by_partition_docs = {p: [d for d in parse_ok if d["partition"] == p] for p in ("SCREEN", "CONFIRM", "TEST")}
    invs = {p: build_type_inventory(ds) for p, ds in by_partition_docs.items()}

    screen = screen_stage(invs["SCREEN"]["types"], args.screen_permutations, args.alpha)
    confirm = locked_stage(invs["CONFIRM"]["types"], screen["selected"], args.confirm_permutations, args.alpha, min_stems=2, min_docs=3, min_locations=0, stage_name="CONFIRM")
    test = locked_stage(invs["TEST"]["types"], confirm["survivors"], args.test_permutations, args.alpha, min_stems=2, min_docs=3, min_locations=2, stage_name="TEST")

    screen_top = screen["tested"][:10]
    screen_selected = screen["selected"]
    confirm_survivors = confirm["survivors"]
    test_survivors = test["survivors"]

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-SIGLA-MINIMAL-PAIR-MORPHOLOGY-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "status": "EXECUTED_SURVIVOR_REQUIRES_NOVELTY_AND_SEGMENTATION_AUDIT" if test_survivors else "EXECUTED_VALID_NEGATIVE_NO_FULL_SURVIVOR",
        "frozen_spec": {"path": SPEC_PATH, "commit": SPEC_COMMIT},
        "source": {
            "sigla_database_sha256": db_sha,
            "sigla_browse_sha256": browse_sha,
            "bridge_pair_count": len(pairs),
            "source_independence_class": "L1_INDEPENDENT_DIGITIZATION_SHARED_TRANSCRIPTION",
            "mwenge_frozen_commit_for_identity_bridge_only": MWENGE_COMMIT,
        },
        "parser_audit": {
            "documents_total": len(docs),
            "parse_ok": len(parse_ok),
            "parse_fail": len(docs) - len(parse_ok),
            "parse_success_fraction": len(parse_ok) / 686.0,
        },
        "morphology_inventory": {
            p: {
                "documents": len(by_partition_docs[p]),
                "eligible_word_occurrences": invs[p]["accepted_occurrences"],
                "excluded_ambiguous_or_nonstandard_occurrences": invs[p]["rejected_occurrences"],
                "unique_eligible_word_types": len(invs[p]["types"]),
                "locations": sorted({d["location"] for d in by_partition_docs[p]}),
            }
            for p in ("SCREEN", "CONFIRM", "TEST")
        },
        "blind_representation": {
            "scoring_used_visible_transliteration": False,
            "scoring_used_known_gloss": False,
            "scoring_used_linear_b_values": False,
            "ambiguous_sign_sequences_excluded": True,
            "candidate": "sign hash + PREFIX/SUFFIX side",
        },
        "SCREEN": screen,
        "CONFIRM": confirm,
        "TEST": test,
        "full_survivor_count": len(test_survivors),
        "post_score_reveal": {
            "screen_top": reveal_hypotheses(invs["SCREEN"]["types"], screen_top),
            "screen_selected": reveal_hypotheses(invs["SCREEN"]["types"], screen_selected),
            "confirm_survivors": reveal_hypotheses(invs["CONFIRM"]["types"], confirm_survivors),
            "test_survivors": reveal_hypotheses(invs["TEST"]["types"], test_survivors),
        },
        "classification": "NOVELTY_AND_ALTERNATIVE_SEGMENTATION_AUDIT_REQUIRED" if test_survivors else "VALID_NEGATIVE_FOR_PREDECLARED_ONE_SIGN_EXTENSION_ONTOLOGY",
        "epistemic_gate": {
            "cross_digitization_morphological_operator_candidate_exists": bool(test_survivors),
            "new_lexical_anchor_established": False,
            "external_transcription_replication_established": False,
            "decipherment_established": False,
            "promotion": "MORPHOLOGICAL_OPERATOR_CANDIDATE_ONLY" if test_survivors else "NO_PROMOTION",
        },
        "required_next": [
            "Post-score scholarly novelty audit for each full survivor.",
            "Alternative segmentation and sign-tokenization replay.",
            "Independent implementation replay.",
            "No grammatical meaning assignment from topology alone.",
        ] if test_survivors else [
            "Preserve valid negative and do not lower thresholds.",
            "Move to SigLA-native formula-neighborhood/co-occurrence graph channel.",
        ],
        "claim_ceiling": {
            "maximum": "NOVEL_CROSS_DIGITIZATION_MORPHOLOGICAL_OPERATOR_CANDIDATE" if test_survivors else "VALID_NEGATIVE_NO_FULL_SURVIVOR",
            "new_lexical_anchor_established": False,
            "external_transcription_replication_established": False,
            "decipherment_established": False,
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "parse_ok": len(parse_ok),
        "screen_types": len(invs["SCREEN"]["types"]),
        "screen_eligible_hypotheses": screen["eligible_hypothesis_count"],
        "screen_selected": screen["selected_count"],
        "confirm_evaluable": confirm["evaluable_count"],
        "confirm_survivors": confirm["survivor_count"],
        "test_evaluable": test["evaluable_count"],
        "test_survivors": test["survivor_count"],
        "new_lexical_anchor_established": False,
        "decipherment_established": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
