#!/usr/bin/env python3
"""JANUS Linear A — SigLA-native directed formula-neighborhood v0.1.

Claim-bearing R3A-6 experiment. Discovery uses only hashed exact SigLA sign-ID
word sequences, document membership, original word slots, and deterministic
partitions. Unresolved/nonstandard words remain fixed MASK slots so removing
them cannot fabricate adjacency. Human transliterations are revealed only
after SCREEN/CONFIRM/TEST states are frozen.
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

SPEC_PATH = "data/JANUS-LINEAR-A-SIGLA-FORMULA-NEIGHBORHOOD-SPEC-2026-08-14-v0.1.json"
SPEC_COMMIT = "9ac0ac5a6ca471f037f0d13aa874276c71699098"
MWENGE_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
PARTITION_NAMESPACE = "SIGLA-FORMULA-PARTITION-v0.1"
WORD_NAMESPACE = "SIGLA-FORMULA-WORD-v0.1"
SEED_NAMESPACE = "JANUS-SIGLA-FORMULA-v0.1"
SIGN_RE = re.compile(r"^(?:AB|A)[0-9]+[A-Za-z]?$")
MASK = "__MASK__"


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def word_id(pattern: str) -> str:
    return sha256_hex(f"{WORD_NAMESPACE}|{pattern}")


def resolved_pattern(pattern: str) -> bool:
    if not pattern or any(x in pattern for x in ("?", "[", "]", "(", ")", " ")):
        return False
    parts = pattern.split("-")
    return bool(parts) and all(SIGN_RE.fullmatch(x) for x in parts)


def partition_bucket(key: str) -> int:
    return int(sha256_hex(f"{PARTITION_NAMESPACE}|{key}"), 16) % 10


def partition_name(bucket: int) -> str:
    if bucket <= 5:
        return "SCREEN"
    if bucket <= 7:
        return "CONFIRM"
    return "TEST"


def rebuild_pairs(sigla_ids: Iterable[str], mwenge_ids: Iterable[str]) -> List[dict]:
    smap = bridge.map_by_key(sigla_ids, bridge.sigla_bridge_key)
    mmap = bridge.map_by_key(mwenge_ids, bridge.mwenge_bridge_key)
    scoll = {k for k, v in smap.items() if len(set(v)) > 1}
    mcoll = {k for k, v in mmap.items() if len(set(v)) > 1}
    keys = sorted(k for k in set(smap) & set(mmap) if k not in scoll and k not in mcoll)
    out = []
    for k in keys:
        sid = smap[k][0]
        b = partition_bucket(k)
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
    d = role.fetch_document(item, retries)
    if not d.get("ok"):
        d["formula_slots"] = []
        return d
    slots = []
    for pat in d["patterns"]:
        slots.append(word_id(pat) if resolved_pattern(pat) else MASK)
    d["formula_slots"] = slots
    return d


def candidate_support(docs: List[dict]) -> Dict[str, dict]:
    counts = Counter()
    docsets = defaultdict(set)
    for d in docs:
        seen = set()
        for cid in d["formula_slots"]:
            if cid == MASK:
                continue
            counts[cid] += 1
            seen.add(cid)
        for cid in seen:
            docsets[cid].add(d["bridge_key"])
    return {cid: {"occurrences": counts[cid], "documents": len(docsets[cid])} for cid in counts}


def edge_instances(docs: List[dict]) -> List[Tuple[str, str, str, str]]:
    """Return (left,right,document,location) for immediately adjacent eligible slots."""
    out = []
    for d in docs:
        s = d["formula_slots"]
        for a, b in zip(s, s[1:]):
            if a == MASK or b == MASK or a == b:
                continue
            out.append((a, b, d["bridge_key"], d["location"]))
    return out


def observed_edges(docs: List[dict]) -> Dict[Tuple[str, str], dict]:
    rows = {}
    for a, b, doc, loc in edge_instances(docs):
        key = (a, b)
        r = rows.setdefault(key, {"count": 0, "documents": set(), "locations": set()})
        r["count"] += 1
        r["documents"].add(doc)
        r["locations"].add(loc)
    return rows


def n1_within_doc_counts(docs: List[dict], hypotheses: List[Tuple[str, str]], permutations: int, seed_text: str):
    rng = random.Random(int(sha256_hex(seed_text), 16))
    wanted = set(hypotheses)
    result = {h: [] for h in hypotheses}
    templates = [list(d["formula_slots"]) for d in docs]
    for _ in range(permutations):
        counts = Counter()
        for slots in templates:
            ids = [x for x in slots if x != MASK]
            rng.shuffle(ids)
            it = iter(ids)
            shuffled = [next(it) if x != MASK else MASK for x in slots]
            for a, b in zip(shuffled, shuffled[1:]):
                if a == MASK or b == MASK or a == b:
                    continue
                if (a, b) in wanted:
                    counts[(a, b)] += 1
        for h in hypotheses:
            result[h].append(counts.get(h, 0))
    return result


def n2_endpoint_rewire_counts(docs: List[dict], hypotheses: List[Tuple[str, str]], permutations: int, seed_text: str):
    rng = random.Random(int(sha256_hex(seed_text), 16))
    wanted = set(hypotheses)
    inst = edge_instances(docs)
    lefts = [x[0] for x in inst]
    rights0 = [x[1] for x in inst]
    result = {h: [] for h in hypotheses}
    for _ in range(permutations):
        rights = list(rights0)
        rng.shuffle(rights)
        counts = Counter()
        for a, b in zip(lefts, rights):
            if a == b:
                continue
            if (a, b) in wanted:
                counts[(a, b)] += 1
        for h in hypotheses:
            result[h].append(counts.get(h, 0))
    return result


def empirical_row(obs: int, null_values: List[int]) -> dict:
    mean = sum(null_values) / len(null_values) if null_values else 0.0
    p = (1 + sum(1 for x in null_values if x >= obs)) / (len(null_values) + 1)
    return {"null_mean": mean, "effect": obs - mean, "p_empirical_one_sided": p}


def screen_stage(docs: List[dict], permutations: int, alpha: float) -> dict:
    support = candidate_support(docs)
    endpoints = {cid for cid, s in support.items() if s["occurrences"] >= 8 and s["documents"] >= 5}
    obs = observed_edges(docs)
    hypotheses = sorted(
        k for k, r in obs.items()
        if k[0] in endpoints and k[1] in endpoints and r["count"] >= 4 and len(r["documents"]) >= 3
    )
    if not hypotheses:
        return {
            "eligible_endpoint_count": len(endpoints),
            "eligible_hypothesis_count": 0,
            "tested": [], "selected": [], "selected_count": 0,
        }
    n1 = n1_within_doc_counts(docs, hypotheses, permutations, f"{SEED_NAMESPACE}|SCREEN|N1|{permutations}")
    n2 = n2_endpoint_rewire_counts(docs, hypotheses, permutations, f"{SEED_NAMESPACE}|SCREEN|N2|{permutations}")
    m = len(hypotheses)
    tested = []
    for h in hypotheses:
        r = obs[h]
        a = empirical_row(r["count"], n1[h])
        b = empirical_row(r["count"], n2[h])
        row = {
            "left_id": h[0], "right_id": h[1],
            "edge_occurrences": r["count"],
            "edge_documents": len(r["documents"]),
            "edge_locations": len(r["locations"]),
            "locations": sorted(r["locations"]),
            "N1": {**a, "p_bonferroni": min(1.0, a["p_empirical_one_sided"] * m)},
            "N2": {**b, "p_bonferroni": min(1.0, b["p_empirical_one_sided"] * m)},
        }
        row["selected"] = (
            row["N1"]["effect"] > 0 and row["N2"]["effect"] > 0 and
            row["N1"]["p_bonferroni"] <= alpha and row["N2"]["p_bonferroni"] <= alpha
        )
        tested.append(row)
    tested.sort(key=lambda x: (max(x["N1"]["p_bonferroni"], x["N2"]["p_bonferroni"]), -min(x["N1"]["effect"], x["N2"]["effect"]), x["left_id"], x["right_id"]))
    selected = [x for x in tested if x["selected"]]
    return {
        "eligible_endpoint_count": len(endpoints),
        "eligible_hypothesis_count": m,
        "tested": tested,
        "selected": selected,
        "selected_count": len(selected),
    }


def locked_stage(docs: List[dict], locked: List[dict], permutations: int, alpha: float, min_occ: int, min_docs: int, min_locations: int, stage: str) -> dict:
    if not locked:
        return {"locked_count": 0, "evaluable_count": 0, "survivor_count": 0, "tested": [], "survivors": [], "state": "NOT_ENTERED_NO_LOCKED_HYPOTHESES"}
    obs = observed_edges(docs)
    evaluable = []
    not_eval = []
    for x in locked:
        h = (x["left_id"], x["right_id"])
        r = obs.get(h)
        if not r:
            not_eval.append({"left_id": h[0], "right_id": h[1], "state": "NOT_EVALUABLE", "reason": "EDGE_ABSENT", "edge_occurrences": 0, "edge_documents": 0, "edge_locations": 0})
            continue
        reason = None
        if r["count"] < min_occ:
            reason = f"EDGE_OCCURRENCES_BELOW_MIN:{r['count']}<{min_occ}"
        elif len(r["documents"]) < min_docs:
            reason = f"EDGE_DOCUMENTS_BELOW_MIN:{len(r['documents'])}<{min_docs}"
        elif min_locations and len(r["locations"]) < min_locations:
            reason = f"EDGE_LOCATIONS_BELOW_MIN:{len(r['locations'])}<{min_locations}"
        if reason:
            not_eval.append({"left_id": h[0], "right_id": h[1], "state": "NOT_EVALUABLE", "reason": reason, "edge_occurrences": r["count"], "edge_documents": len(r["documents"]), "edge_locations": len(r["locations"]), "locations": sorted(r["locations"])})
        else:
            evaluable.append(h)
    if not evaluable:
        return {"locked_count": len(locked), "evaluable_count": 0, "survivor_count": 0, "tested": not_eval, "survivors": [], "state": "NO_EVALUABLE_LOCKED_HYPOTHESES"}
    n1 = n1_within_doc_counts(docs, evaluable, permutations, f"{SEED_NAMESPACE}|{stage}|N1|{permutations}")
    n2 = n2_endpoint_rewire_counts(docs, evaluable, permutations, f"{SEED_NAMESPACE}|{stage}|N2|{permutations}")
    m = len(locked)
    tested = list(not_eval)
    survivors = []
    for h in evaluable:
        r = obs[h]
        a = empirical_row(r["count"], n1[h]); b = empirical_row(r["count"], n2[h])
        row = {
            "left_id": h[0], "right_id": h[1], "state": "EVALUATED",
            "edge_occurrences": r["count"], "edge_documents": len(r["documents"]), "edge_locations": len(r["locations"]), "locations": sorted(r["locations"]),
            "N1": {**a, "p_bonferroni": min(1.0, a["p_empirical_one_sided"] * m)},
            "N2": {**b, "p_bonferroni": min(1.0, b["p_empirical_one_sided"] * m)},
        }
        row["survived"] = row["N1"]["effect"] > 0 and row["N2"]["effect"] > 0 and row["N1"]["p_bonferroni"] <= alpha and row["N2"]["p_bonferroni"] <= alpha
        tested.append(row)
        if row["survived"]:
            survivors.append(row)
    return {"locked_count": len(locked), "evaluable_count": len(evaluable), "survivor_count": len(survivors), "tested": tested, "survivors": survivors, "state": "EVALUATED"}


def reveal_index(docs: List[dict]) -> Dict[str, dict]:
    by = defaultdict(lambda: {"patterns": Counter(), "transliterations": Counter(), "examples": []})
    for d in docs:
        if not d.get("ok"):
            continue
        for pat, tr, cid in zip(d["patterns"], d["transliterations"], d["formula_slots"]):
            if cid == MASK:
                continue
            by[cid]["patterns"][pat] += 1
            if tr:
                by[cid]["transliterations"][tr] += 1
            if len(by[cid]["examples"]) < 5:
                by[cid]["examples"].append({"bridge_key": d["bridge_key"], "sigla_id": d["sigla_id"], "location": d["location"]})
    return {
        cid: {
            "sign_id_sequences": [{"value": k, "count": v} for k, v in x["patterns"].most_common()],
            "visible_transliterations": [{"value": k, "count": v} for k, v in x["transliterations"].most_common()],
            "examples": x["examples"],
        } for cid, x in by.items()
    }


def reveal_rows(rows: List[dict], idx: Dict[str, dict]) -> List[dict]:
    out = []
    for r in rows:
        x = dict(r)
        x["left_reveal"] = idx.get(r["left_id"], {})
        x["right_reveal"] = idx.get(r["right_id"], {})
        out.append(x)
    return out


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

    _, _, _, db = role.fetch_with_retries("https://sigla.phis.me/database.js", retries=args.retries)
    db_sha = hashlib.sha256(db).hexdigest()
    if db_sha != role.FROZEN_SIGLA_DATABASE_SHA256:
        raise SystemExit(f"SIGLA_DATABASE_SHA_MISMATCH:{db_sha}")
    _, _, _, browse = role.fetch_with_retries(inv.DEFAULT_SIGLA_URL, retries=args.retries)
    browse_sha = hashlib.sha256(browse).hexdigest()
    if browse_sha != role.FROZEN_SIGLA_BROWSE_SHA256:
        raise SystemExit(f"SIGLA_BROWSE_SHA_MISMATCH:{browse_sha}")
    bp = inv.SigLABrowseParser(); bp.feed(browse.decode("utf-8", errors="replace"))
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

    byp = {p: [d for d in parse_ok if d["partition"] == p] for p in ("SCREEN", "CONFIRM", "TEST")}
    screen = screen_stage(byp["SCREEN"], args.screen_permutations, args.alpha)
    confirm = locked_stage(byp["CONFIRM"], screen["selected"], args.confirm_permutations, args.alpha, 2, 2, 0, "CONFIRM")
    test = locked_stage(byp["TEST"], confirm["survivors"], args.test_permutations, args.alpha, 2, 2, 2, "TEST")
    reveal = reveal_index(parse_ok)
    result = {
        "artifact_uuid": "JANUS-LINEAR-A-SIGLA-FORMULA-NEIGHBORHOOD-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "status": "EXECUTED_SURVIVOR_REQUIRES_NOVELTY_AUDIT" if test["survivor_count"] else "EXECUTED_VALID_NEGATIVE_NO_FULL_SURVIVOR",
        "frozen_spec": {"path": SPEC_PATH, "commit": SPEC_COMMIT},
        "source": {"source_independence_class": "L1_INDEPENDENT_DIGITIZATION_SHARED_TRANSCRIPTION", "sigla_database_sha256": db_sha, "sigla_browse_sha256": browse_sha, "bridge_pair_count": 686, "mwenge_frozen_commit_for_identity_bridge_only": MWENGE_COMMIT},
        "parser_audit": {"documents_total": 686, "parse_ok": len(parse_ok), "parse_fail": 686-len(parse_ok), "parse_success_fraction": len(parse_ok)/686.0, "masked_word_occurrences": sum(1 for d in parse_ok for x in d["formula_slots"] if x == MASK), "eligible_word_occurrences": sum(1 for d in parse_ok for x in d["formula_slots"] if x != MASK)},
        "partitions": {p: {"documents": len(byp[p]), "eligible_adjacency_edges": len(edge_instances(byp[p])), "locations": sorted({d["location"] for d in byp[p]})} for p in ("SCREEN","CONFIRM","TEST")},
        "blind_representation": {"scoring_used_visible_transliteration": False, "scoring_used_known_gloss": False, "scoring_used_linear_b_values": False, "ambiguous_word_slots_preserved_as_MASK": True},
        "SCREEN": screen,
        "CONFIRM": confirm,
        "TEST": test,
        "full_survivor_count": test["survivor_count"],
        "post_score_reveal": {"screen_top": reveal_rows(screen["tested"][:10], reveal), "screen_selected": reveal_rows(screen["selected"], reveal), "confirm_survivors": reveal_rows(confirm["survivors"], reveal), "test_survivors": reveal_rows(test["survivors"], reveal)},
        "classification": "NOVELTY_AUDIT_REQUIRED_FOR_FULL_SURVIVOR" if test["survivor_count"] else "VALID_NEGATIVE_FOR_PREDECLARED_DIRECTED_ADJACENCY_ONTOLOGY",
        "epistemic_gate": {"cross_digitization_formula_relation_candidate_exists": bool(test["survivor_count"]), "new_lexical_anchor_established": False, "external_transcription_replication_established": False, "decipherment_established": False, "promotion": "FORMULA_RELATION_CANDIDATE_ONLY" if test["survivor_count"] else "NO_PROMOTION"},
        "claim_ceiling": {"maximum": "NOVEL_CROSS_DIGITIZATION_FORMULA_RELATION_CANDIDATE" if test["survivor_count"] else "VALID_NEGATIVE_NO_FULL_SURVIVOR", "new_lexical_anchor_established": False, "external_transcription_replication_established": False, "decipherment_established": False},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps({"parse_ok": len(parse_ok), "screen_endpoints": screen["eligible_endpoint_count"], "screen_hypotheses": screen["eligible_hypothesis_count"], "screen_selected": screen["selected_count"], "confirm_evaluable": confirm["evaluable_count"], "confirm_survivors": confirm["survivor_count"], "test_evaluable": test["evaluable_count"], "test_survivors": test["survivor_count"], "new_lexical_anchor_established": False, "decipherment_established": False}, sort_keys=True))


if __name__ == "__main__":
    main()
