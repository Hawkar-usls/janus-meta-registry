#!/usr/bin/env python3
"""JANUS Linear A — SigLA-native blind document-boundary role discovery v0.1.

Claim-bearing R3A-4 experiment.

The scientific candidate identity is derived only from SigLA's standard sign-ID
sequence embedded in `!seq-pattern:...//` word-search anchors. Visible
transliteration text is retained only for post-score reveal after SCREEN,
CONFIRM, and TEST states have been frozen.

This is a cross-digitization/parser robustness experiment on an L1 source
(independent digitization, shared transcription tradition). It cannot establish
external transcription replication, a lexical anchor, or decipherment.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import random
import re
import time
import urllib.parse
from collections import Counter, defaultdict
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import janus_linear_a_sigla_inventory_audit as inv
import janus_linear_a_sigla_document_bridge_v0_1 as bridge

SPEC_PATH = "data/JANUS-LINEAR-A-SIGLA-NATIVE-BLIND-ROLE-DISCOVERY-SPEC-2026-08-14-v0.1.json"
SPEC_COMMIT = "502095da1d9e715b4d20b697b3fa85e91f132a04"
MWENGE_COMMIT = "43fe7cf1abc8e6bb1ea3228c3a1bd5938709620a"
FROZEN_SIGLA_BROWSE_SHA256 = "c1d25f91dccf334c3cf24b52c1e4a279970cebd3f5c6f377569de076360170cd"
FROZEN_SIGLA_DATABASE_SHA256 = "cc624f148fd84c94fd2910b0adf92ecace25f52f9175664122bdf8384a8f1b9d"
PARTITION_NAMESPACE = "SIGLA-ROLE-PARTITION-v0.1"
CANDIDATE_NAMESPACE = "SIGLA-WORD-v0.1"
SEED_NAMESPACE = "JANUS-SIGLA-BLIND-ROLE-v0.1"
ROLES = ("INITIAL", "FINAL")
SEQ_RE = re.compile(r"word-match\s+@\s+!seq-pattern:([^/]+)//", re.I)
WORD_COUNT_RE = re.compile(r"\b(\d+)\s+words?\b", re.I)


class WordAnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: List[dict] = []
        self.text_parts: List[str] = []
        self._anchor = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            amap = dict(attrs)
            self._anchor = {
                "href": amap.get("href"),
                "title": amap.get("title"),
                "class": amap.get("class"),
                "text_parts": [],
            }

    def handle_data(self, data):
        if not data:
            return
        self.text_parts.append(data)
        if self._anchor is not None:
            self._anchor["text_parts"].append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._anchor is not None:
            row = dict(self._anchor)
            row["text"] = re.sub(r"\s+", " ", " ".join(row.pop("text_parts"))).strip()
            self.anchors.append(row)
            self._anchor = None


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def candidate_id(pattern: str) -> str:
    return sha256_hex(f"{CANDIDATE_NAMESPACE}|{pattern}")


def partition_bucket(bridge_key: str) -> int:
    return int(sha256_hex(f"{PARTITION_NAMESPACE}|{bridge_key}"), 16) % 10


def partition_name(bucket: int) -> str:
    if bucket <= 5:
        return "SCREEN"
    if bucket <= 7:
        return "CONFIRM"
    return "TEST"


def location_from_sigla_id(sigla_id: str) -> str:
    m = re.match(r"^\s*([A-Z]+)", sigla_id or "")
    return m.group(1) if m else "UNKNOWN"


def fetch_with_retries(url: str, retries: int = 3, base_sleep: float = 0.35):
    last = None
    for attempt in range(retries):
        try:
            status, final_url, content_type, body = inv.fetch_bytes(url)
            if status == 200 and body:
                return status, final_url, content_type, body
            last = RuntimeError(f"HTTP_OR_EMPTY:{status}:{len(body or b'')}")
        except Exception as exc:
            last = exc
        if attempt + 1 < retries:
            time.sleep(base_sleep * (attempt + 1))
    raise RuntimeError(f"FETCH_FAIL:{url}:{last}")


def reconstruct_bridge(sigla_ids: Iterable[str], mwenge_ids: Iterable[str]) -> List[dict]:
    smap = bridge.map_by_key(sigla_ids, bridge.sigla_bridge_key)
    mmap = bridge.map_by_key(mwenge_ids, bridge.mwenge_bridge_key)
    scoll = {k for k, v in smap.items() if len(set(v)) > 1}
    mcoll = {k for k, v in mmap.items() if len(set(v)) > 1}
    keys = sorted(k for k in set(smap) & set(mmap) if k not in scoll and k not in mcoll)
    return [
        {
            "bridge_key": k,
            "sigla_id": smap[k][0],
            "mwenge_id": mmap[k][0],
            "location": location_from_sigla_id(smap[k][0]),
            "partition_bucket": partition_bucket(k),
            "partition": partition_name(partition_bucket(k)),
        }
        for k in keys
    ]


def parse_word_view(body: bytes) -> dict:
    text = body.decode("utf-8", errors="replace")
    parser = WordAnchorParser()
    parser.feed(text)
    visible = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()
    wc = WORD_COUNT_RE.search(visible)
    if not wc:
        return {
            "ok": False,
            "reason": "REPORTED_WORD_COUNT_NOT_FOUND",
            "reported_word_count": None,
            "patterns": [],
            "transliterations": [],
        }

    patterns: List[str] = []
    translits: List[str] = []
    source_anchors: List[dict] = []
    for a in parser.anchors:
        href = a.get("href") or ""
        m = SEQ_RE.search(href)
        if not m:
            continue
        pat = m.group(1).strip()
        if not pat:
            continue
        patterns.append(pat)
        translits.append((a.get("text") or "").strip())
        source_anchors.append({"href": href, "text": (a.get("text") or "").strip()})

    reported = int(wc.group(1))
    if reported != len(patterns):
        return {
            "ok": False,
            "reason": "REPORTED_WORD_COUNT_SEQUENCE_COUNT_MISMATCH",
            "reported_word_count": reported,
            "extracted_sequence_count": len(patterns),
            "patterns": patterns,
            "transliterations": translits,
            "source_anchors": source_anchors[:20],
        }

    return {
        "ok": True,
        "reason": None,
        "reported_word_count": reported,
        "patterns": patterns,
        "transliterations": translits,
    }


def fetch_document(item: dict, retries: int) -> dict:
    encoded = urllib.parse.quote(item["sigla_id"], safe="")
    url = f"https://sigla.phis.me/document/{encoded}/index-word.html"
    try:
        status, final_url, content_type, body = fetch_with_retries(url, retries=retries)
        parsed = parse_word_view(body)
        result = {
            **item,
            "requested_url": url,
            "final_url": final_url,
            "http_status": status,
            "content_type": content_type,
            "bytes": len(body),
            "page_sha256": hashlib.sha256(body).hexdigest(),
            **parsed,
        }
        if parsed["ok"]:
            result["word_ids"] = [candidate_id(x) for x in parsed["patterns"]]
        else:
            result["word_ids"] = []
        return result
    except Exception as exc:
        return {
            **item,
            "requested_url": url,
            "ok": False,
            "reason": f"FETCH_EXCEPTION:{type(exc).__name__}:{exc}",
            "reported_word_count": None,
            "patterns": [],
            "transliterations": [],
            "word_ids": [],
        }


def eligible_role_docs(docs: Iterable[dict]) -> List[dict]:
    return [d for d in docs if d.get("ok") and len(d.get("word_ids", [])) >= 2]


def support_for_candidate(docs: Iterable[dict], cid: str) -> Tuple[int, int, set]:
    occurrences = 0
    documents = 0
    locations = set()
    for d in docs:
        n = d["word_ids"].count(cid)
        if n:
            occurrences += n
            documents += 1
            locations.add(d.get("location", "UNKNOWN"))
    return occurrences, documents, locations


def role_count(docs: Iterable[dict], cid: str, role: str) -> int:
    idx = 0 if role == "INITIAL" else -1
    return sum(1 for d in docs if d["word_ids"][idx] == cid)


def all_candidate_support(docs: Iterable[dict]) -> Dict[str, dict]:
    counts = Counter()
    docsets = defaultdict(set)
    for d in docs:
        for cid in d["word_ids"]:
            counts[cid] += 1
            docsets[cid].add(d["bridge_key"])
    return {cid: {"occurrences": counts[cid], "documents": len(docsets[cid])} for cid in counts}


def permutation_role_counts(
    docs: List[dict],
    candidate_roles: List[Tuple[str, str]],
    permutations: int,
    seed_text: str,
) -> Dict[Tuple[str, str], List[int]]:
    """Within-document identity shuffle, preserving document word multiset and slots."""
    rng = random.Random(int(sha256_hex(seed_text), 16))
    targets = set(candidate_roles)
    out = {cr: [] for cr in candidate_roles}
    original = [list(d["word_ids"]) for d in docs]
    for _ in range(permutations):
        counts = Counter()
        for words in original:
            if len(words) < 2:
                continue
            shuffled = list(words)
            rng.shuffle(shuffled)
            left = shuffled[0]
            right = shuffled[-1]
            if (left, "INITIAL") in targets:
                counts[(left, "INITIAL")] += 1
            if (right, "FINAL") in targets:
                counts[(right, "FINAL")] += 1
        for cr in candidate_roles:
            out[cr].append(counts.get(cr, 0))
    return out


def summarize_hypothesis(
    docs: List[dict],
    cid: str,
    role: str,
    null_counts: List[int],
) -> dict:
    occurrences, documents, locations = support_for_candidate(docs, cid)
    obs = role_count(docs, cid, role)
    obs_fraction = obs / occurrences if occurrences else 0.0
    null_fractions = [(x / occurrences if occurrences else 0.0) for x in null_counts]
    null_mean = sum(null_fractions) / len(null_fractions) if null_fractions else 0.0
    p = (1 + sum(1 for x in null_counts if x >= obs)) / (len(null_counts) + 1)
    return {
        "candidate_id": cid,
        "role": role,
        "occurrences": occurrences,
        "documents": documents,
        "locations": sorted(locations),
        "role_count": obs,
        "observed_role_fraction": obs_fraction,
        "null_mean_role_fraction": null_mean,
        "effect": obs_fraction - null_mean,
        "p_empirical_one_sided": p,
    }


def screen_stage(docs: List[dict], permutations: int, alpha: float) -> dict:
    support = all_candidate_support(docs)
    eligible_ids = sorted(
        cid for cid, s in support.items()
        if s["occurrences"] >= 8 and s["documents"] >= 5
    )
    hypotheses = [(cid, role) for cid in eligible_ids for role in ROLES]
    if not hypotheses:
        return {
            "eligible_candidate_count": 0,
            "tested_hypothesis_count": 0,
            "tested": [],
            "selected": [],
            "selected_count": 0,
        }

    null = permutation_role_counts(
        docs, hypotheses, permutations,
        f"{SEED_NAMESPACE}|SCREEN|{permutations}",
    )
    tested = []
    m = len(hypotheses)
    for cid, role in hypotheses:
        row = summarize_hypothesis(docs, cid, role, null[(cid, role)])
        row["p_bonferroni"] = min(1.0, row["p_empirical_one_sided"] * m)
        row["selected"] = row["effect"] > 0 and row["p_bonferroni"] <= alpha
        tested.append(row)

    tested.sort(key=lambda x: (x["p_bonferroni"], -x["effect"], x["candidate_id"], x["role"]))
    selected = [x for x in tested if x["selected"]]
    return {
        "eligible_candidate_count": len(eligible_ids),
        "tested_hypothesis_count": m,
        "tested": tested,
        "selected": selected,
        "selected_count": len(selected),
    }


def locked_stage(
    docs: List[dict],
    locked: List[dict],
    permutations: int,
    alpha: float,
    min_occurrences: int,
    min_documents: int,
    min_locations: int = 0,
    stage_name: str = "CONFIRM",
) -> dict:
    if not locked:
        return {
            "locked_count": 0,
            "evaluable_count": 0,
            "survivor_count": 0,
            "tested": [],
            "survivors": [],
            "state": "NOT_ENTERED_NO_LOCKED_HYPOTHESES",
        }

    evaluable = []
    not_evaluable = []
    for h in locked:
        cid, role = h["candidate_id"], h["role"]
        occ, ndoc, locs = support_for_candidate(docs, cid)
        reason = None
        if occ < min_occurrences:
            reason = f"OCCURRENCES_BELOW_MIN:{occ}<{min_occurrences}"
        elif ndoc < min_documents:
            reason = f"DOCUMENTS_BELOW_MIN:{ndoc}<{min_documents}"
        elif min_locations and len(locs) < min_locations:
            reason = f"LOCATIONS_BELOW_MIN:{len(locs)}<{min_locations}"
        if reason:
            not_evaluable.append({
                "candidate_id": cid,
                "role": role,
                "occurrences": occ,
                "documents": ndoc,
                "locations": sorted(locs),
                "state": "NOT_EVALUABLE",
                "reason": reason,
            })
        else:
            evaluable.append((cid, role))

    if not evaluable:
        return {
            "locked_count": len(locked),
            "evaluable_count": 0,
            "survivor_count": 0,
            "tested": not_evaluable,
            "survivors": [],
            "state": "NO_EVALUABLE_LOCKED_HYPOTHESES",
        }

    null = permutation_role_counts(
        docs, evaluable, permutations,
        f"{SEED_NAMESPACE}|{stage_name}|{permutations}",
    )
    m = len(locked)
    tested = list(not_evaluable)
    survivors = []
    for cid, role in evaluable:
        row = summarize_hypothesis(docs, cid, role, null[(cid, role)])
        row["p_bonferroni"] = min(1.0, row["p_empirical_one_sided"] * m)
        row["state"] = "EVALUATED"
        row["survived"] = row["effect"] > 0 and row["p_bonferroni"] <= alpha
        tested.append(row)
        if row["survived"]:
            survivors.append(row)

    tested.sort(key=lambda x: (
        0 if x.get("state") == "EVALUATED" else 1,
        x.get("p_bonferroni", 1.0),
        x["candidate_id"], x["role"],
    ))
    return {
        "locked_count": len(locked),
        "evaluable_count": len(evaluable),
        "survivor_count": len(survivors),
        "tested": tested,
        "survivors": survivors,
        "state": "EVALUATED",
    }


def reveal_map(all_docs: List[dict]) -> Dict[str, dict]:
    patterns = defaultdict(Counter)
    translits = defaultdict(Counter)
    examples = defaultdict(list)
    for d in all_docs:
        if not d.get("ok"):
            continue
        for idx, (pat, tr, cid) in enumerate(zip(d["patterns"], d["transliterations"], d["word_ids"])):
            patterns[cid][pat] += 1
            if tr:
                translits[cid][tr] += 1
            if len(examples[cid]) < 8:
                examples[cid].append({
                    "bridge_key": d["bridge_key"],
                    "sigla_id": d["sigla_id"],
                    "location": d["location"],
                    "ordinal": idx,
                    "document_word_count": len(d["word_ids"]),
                })
    out = {}
    for cid in patterns:
        out[cid] = {
            "sign_id_sequences": [{"value": k, "count": v} for k, v in patterns[cid].most_common()],
            "visible_transliterations": [{"value": k, "count": v} for k, v in translits[cid].most_common()],
            "representative_occurrences": examples[cid],
        }
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

    _, _, _, db_body = fetch_with_retries("https://sigla.phis.me/database.js", retries=args.retries)
    db_sha = hashlib.sha256(db_body).hexdigest()
    if db_sha != FROZEN_SIGLA_DATABASE_SHA256:
        raise SystemExit(f"SIGLA_DATABASE_SHA_MISMATCH:{db_sha}")

    _, _, _, browse_body = fetch_with_retries(inv.DEFAULT_SIGLA_URL, retries=args.retries)
    browse_sha = hashlib.sha256(browse_body).hexdigest()
    if browse_sha != FROZEN_SIGLA_BROWSE_SHA256:
        raise SystemExit(f"SIGLA_BROWSE_SHA_MISMATCH:{browse_sha}")
    bp = inv.SigLABrowseParser()
    bp.feed(browse_body.decode("utf-8", errors="replace"))
    sigla_ids = sorted({x for h in bp.document_hrefs if (x := inv.extract_sigla_id_from_href(h))})
    mwenge_ids = inv.inventory_mwenge(Path(args.mwenge_root))
    pairs = reconstruct_bridge(sigla_ids, mwenge_ids)
    if len(pairs) != 686:
        raise SystemExit(f"BRIDGE_COUNT_MISMATCH:{len(pairs)}")

    docs: List[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(fetch_document, p, args.retries): p["bridge_key"] for p in pairs}
        for fut in concurrent.futures.as_completed(futures):
            docs.append(fut.result())
    docs.sort(key=lambda d: d["bridge_key"])

    parse_ok = [d for d in docs if d.get("ok")]
    parse_fail = [d for d in docs if not d.get("ok")]
    parse_fraction = len(parse_ok) / 686.0
    if len(parse_ok) < 400 or parse_fraction < 0.80:
        raise SystemExit(f"PARSER_COVERAGE_GATE_FAIL:{len(parse_ok)}/686:{parse_fraction:.6f}")

    role_docs = eligible_role_docs(parse_ok)
    by_partition = {
        p: [d for d in role_docs if d["partition"] == p]
        for p in ("SCREEN", "CONFIRM", "TEST")
    }

    screen = screen_stage(by_partition["SCREEN"], args.screen_permutations, args.alpha)
    confirm = locked_stage(
        by_partition["CONFIRM"], screen["selected"], args.confirm_permutations,
        args.alpha, min_occurrences=4, min_documents=3, stage_name="CONFIRM"
    )
    test = locked_stage(
        by_partition["TEST"], confirm["survivors"], args.test_permutations,
        args.alpha, min_occurrences=4, min_documents=3, min_locations=2, stage_name="TEST"
    )

    full_survivors = test["survivors"]

    reveal = reveal_map(parse_ok)
    reveal_ids = set()
    for row in screen["tested"][:10]:
        reveal_ids.add(row["candidate_id"])
    for stage_rows in (screen["selected"], confirm["survivors"], full_survivors):
        for row in stage_rows:
            reveal_ids.add(row["candidate_id"])
    post_score = {
        cid: reveal.get(cid, {"sign_id_sequences": [], "visible_transliterations": [], "representative_occurrences": []})
        for cid in sorted(reveal_ids)
    }

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-SIGLA-NATIVE-BLIND-ROLE-DISCOVERY-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "status": (
            "EXECUTED_SURVIVOR_REQUIRES_POST_SCORE_NOVELTY_AUDIT"
            if full_survivors else "EXECUTED_VALID_NEGATIVE_NO_FULL_SURVIVOR"
        ),
        "frozen_spec": {"path": SPEC_PATH, "commit": SPEC_COMMIT},
        "source": {
            "sigla_database_sha256": db_sha,
            "sigla_database_bytes": len(db_body),
            "sigla_browse_sha256": browse_sha,
            "bridge_pair_count": len(pairs),
            "mwenge_frozen_commit_for_identity_bridge_only": MWENGE_COMMIT,
            "source_independence_class": "L1_INDEPENDENT_DIGITIZATION_SHARED_TRANSCRIPTION"
        },
        "parser_audit": {
            "documents_total": len(docs),
            "parse_ok": len(parse_ok),
            "parse_fail": len(parse_fail),
            "parse_success_fraction": parse_fraction,
            "role_eligible_documents_ge_2_words": len(role_docs),
            "zero_word_documents": sum(1 for d in parse_ok if len(d["word_ids"]) == 0),
            "one_word_documents": sum(1 for d in parse_ok if len(d["word_ids"]) == 1),
            "failures_by_reason": dict(Counter(d.get("reason") or "UNKNOWN" for d in parse_fail)),
            "sample_failures": [
                {
                    "bridge_key": d["bridge_key"], "sigla_id": d["sigla_id"],
                    "reason": d.get("reason"), "reported_word_count": d.get("reported_word_count"),
                    "extracted_sequence_count": d.get("extracted_sequence_count")
                }
                for d in parse_fail[:25]
            ]
        },
        "partitions": {
            p: {
                "role_eligible_documents": len(by_partition[p]),
                "locations": sorted({d["location"] for d in by_partition[p]}),
                "total_word_occurrences": sum(len(d["word_ids"]) for d in by_partition[p])
            }
            for p in ("SCREEN", "CONFIRM", "TEST")
        },
        "blind_representation": {
            "candidate_namespace": CANDIDATE_NAMESPACE,
            "partition_namespace": PARTITION_NAMESPACE,
            "discovery_used_visible_transliteration": False,
            "discovery_used_known_gloss": False,
            "discovery_used_linear_b_reading": False
        },
        "SCREEN": screen,
        "CONFIRM": confirm,
        "TEST": test,
        "full_survivor_count": len(full_survivors),
        "post_score_reveal": post_score,
        "post_score_reveal_scope": "top 10 SCREEN hypotheses by corrected p plus every selected/confirmed/test survivor",
        "epistemic_gate": {
            "sigla_native_claim_bearing_execution_completed": True,
            "cross_digitization_structural_role_candidate_exists": bool(full_survivors),
            "external_transcription_replication_established": False,
            "new_lexical_anchor_established": False,
            "decipherment_established": False,
            "promotion": "STRUCTURAL_ROLE_CANDIDATE_ONLY" if full_survivors else "NO_PROMOTION"
        },
        "classification": (
            "NOVELTY_AUDIT_REQUIRED_FOR_FULL_SURVIVOR" if full_survivors
            else "VALID_NEGATIVE_FOR_PREDECLARED_DOCUMENT_BOUNDARY_ROLE_ONTOLOGY"
        ),
        "required_next": (
            [
                "Run post-score scholarly novelty audit for each TEST survivor.",
                "Compare the survivor's SigLA sign-ID identity against known accounting/personnel/formula structures.",
                "Replay with an independently implemented SigLA parser/statistical runner.",
                "Do not infer lexical meaning from boundary-role specialization alone."
            ] if full_survivors else [
                "Preserve this valid negative without lowering thresholds.",
                "Freeze a new SigLA-native sign-within-word morphology or formula-neighborhood experiment.",
                "Keep external transcription replication false until an L3 independent transcription source exists."
            ]
        ),
        "claim_ceiling": {
            "maximum": "NOVEL_CROSS_DIGITIZATION_STRUCTURAL_ROLE_CANDIDATE" if full_survivors else "VALID_NEGATIVE_NO_FULL_SURVIVOR",
            "external_transcription_replication_established": False,
            "new_lexical_anchor_established": False,
            "decipherment_established": False
        }
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "parse_ok": len(parse_ok), "parse_fail": len(parse_fail), "role_docs": len(role_docs),
        "screen_eligible_candidates": screen["eligible_candidate_count"],
        "screen_tested": screen["tested_hypothesis_count"], "screen_selected": screen["selected_count"],
        "confirm_evaluable": confirm["evaluable_count"], "confirm_survivors": confirm["survivor_count"],
        "test_evaluable": test["evaluable_count"], "test_survivors": test["survivor_count"],
        "new_lexical_anchor_established": False, "decipherment_established": False
    }, sort_keys=True))


if __name__ == "__main__":
    main()
