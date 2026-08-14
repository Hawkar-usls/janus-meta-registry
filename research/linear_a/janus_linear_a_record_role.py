#!/usr/bin/env python3
"""
JANUS Linear A record-boundary / formula-slot cross-region search v0.6.

Known families that explained prior survivors are removed before scoring. Candidate identity
is opaque during scoring. Discovery uses HT only; non-HT is a cross-region replication,
not a pristine unseen holdout because earlier JANUS stages touched the full corpus.

The null preserves document membership, candidate frequency per document, numeric slots,
row geometry, and all role slots. It destroys only token-identity <-> structural-role coupling
by shuffling anonymous token identities among eligible token positions within each document.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import janus_linear_a_full_corpus as base
import janus_linear_a_survivor_decomposition as dec

VERSION = "JANUS-LINA-RECORD-ROLE-v0.6"
ROLES = (
    "ROW_INITIAL",
    "ROW_FINAL",
    "PRE_NUMERIC",
    "POST_NUMERIC",
    "DOC_INITIAL",
    "DOC_FINAL",
    "NONNUMERIC_ONLY_ROW",
    "SOLE_TOKEN_ROW",
)

READING_SPEC_RE = base.READING_SPEC_RE
TAG_RE = base.TAG_RE
ROW_RE = base.ROW_RE

KNOWN_ACCOUNTING_WORDS = {"KURO", "KIRO", "POTOKURO"}


def norm(s):
    return dec.normalize_label(s or "")


def excluded_word_label(label):
    x = norm(label)
    return x.startswith("VIR") or x in KNOWN_ACCOUNTING_WORDS or x == "GRA"


def excluded_suffix_label(label):
    x = norm(label)
    return x.startswith("VIR") or x in {"RO", "GRA"}


def parse_layout(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    m = READING_SPEC_RE.search(text)
    if not m:
        return None
    body = TAG_RE.sub("", m.group(1))
    by_word = defaultdict(list)
    statuses = defaultdict(list)
    rows = defaultdict(list)
    lines = defaultdict(list)
    for raw in body.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        rm = ROW_RE.match(raw)
        if not rm:
            continue
        row_i, line_i, word_i, token, status = rm.groups()
        wi = int(word_i)
        by_word[wi].append(token.strip())
        statuses[wi].append(status.lower())
        rows[wi].append(int(row_i))
        lines[wi].append(int(line_i))

    words = []
    reveal = {}
    for wi in sorted(by_word):
        pieces = by_word[wi]
        numeric_parts = [base.parse_numeric_piece(x) for x in pieces]
        unique_rows = sorted(set(rows[wi]))
        unique_lines = sorted(set(lines[wi]))
        row = unique_rows[0] if len(unique_rows) == 1 else None
        line = unique_lines[0] if len(unique_lines) == 1 else None
        if all(v is not None for v in numeric_parts):
            value = sum(float(v) for v in numeric_parts)
            if value > 0:
                words.append({"kind": "N", "value": value, "word_index": wi, "row": row, "line": line})
            continue
        raw_word = "·".join(pieces)
        raw_suffix = pieces[-1]
        wh = base.stable_id(raw_word, "WORD")
        sh = base.stable_id(raw_suffix, "SUFFIX")
        words.append({
            "kind": "T", "word": wh, "suffix": sh, "word_index": wi,
            "row": row, "line": line, "reading_status": sorted(set(statuses[wi])),
        })
        reveal.setdefault(wh, raw_word)
        reveal.setdefault(sh, raw_suffix)
    if not words:
        return None

    row_groups = defaultdict(list)
    for i, w in enumerate(words):
        if w.get("row") is not None:
            row_groups[w["row"]].append(i)
    first_t = next((i for i, w in enumerate(words) if w["kind"] == "T"), None)
    last_t = next((i for i in range(len(words)-1, -1, -1) if words[i]["kind"] == "T"), None)

    positions = []
    for i, w in enumerate(words):
        if w["kind"] != "T":
            continue
        role = {r: False for r in ROLES}
        role["DOC_INITIAL"] = i == first_t
        role["DOC_FINAL"] = i == last_t
        if w.get("row") is not None:
            idxs = sorted(row_groups[w["row"]], key=lambda j: words[j]["word_index"])
            if i in idxs:
                j = idxs.index(i)
                role["ROW_INITIAL"] = j == 0
                role["ROW_FINAL"] = j == len(idxs) - 1
                role["PRE_NUMERIC"] = j + 1 < len(idxs) and words[idxs[j+1]]["kind"] == "N"
                role["POST_NUMERIC"] = j > 0 and words[idxs[j-1]]["kind"] == "N"
                role["NONNUMERIC_ONLY_ROW"] = not any(words[k]["kind"] == "N" for k in idxs)
                role["SOLE_TOKEN_ROW"] = len(idxs) == 1
        positions.append({
            "doc": path.stem, "region": base.region_of(path.stem),
            "word": w["word"], "suffix": w["suffix"], "word_index": w["word_index"],
            "roles": role,
        })
    return {"doc": path.stem, "region": base.region_of(path.stem), "positions": positions, "reveal": reveal}


def load_corpus(corpus: Path):
    docs, failures = [], []
    reveal = {}
    for p in sorted((corpus / "items").glob("*.html")):
        try:
            d = parse_layout(p)
            if d:
                docs.append(d)
                reveal.update(d["reveal"])
            else:
                failures.append({"doc": p.stem, "reason": "NO_PARSEABLE_LAYOUT"})
        except Exception as exc:
            failures.append({"doc": p.stem, "reason": f"PARSE_EXCEPTION:{type(exc).__name__}"})
    if len(docs) < 300:
        raise SystemExit("FULL_CORPUS_GATE_FAIL")
    return docs, failures, reveal


def eligible_positions(docs, family, reveal):
    out = []
    for d in docs:
        for p in d["positions"]:
            label = reveal.get(p[family])
            if family == "word" and excluded_word_label(label):
                continue
            if family == "suffix" and excluded_suffix_label(label):
                continue
            out.append({**p, "identity": p[family]})
    return out


def candidate_metadata(pos, min_n, min_docs):
    by = defaultdict(list)
    for i, p in enumerate(pos):
        by[p["identity"]].append(i)
    keep = {}
    for cid, idxs in by.items():
        docs = {pos[i]["doc"] for i in idxs}
        if len(idxs) >= min_n and len(docs) >= min_docs:
            keep[cid] = idxs
    return keep


def expected_rate(pos, idxs, role):
    by_doc_all = defaultdict(list)
    for i, p in enumerate(pos):
        by_doc_all[p["doc"]].append(i)
    cand_counts = Counter(pos[i]["doc"] for i in idxs)
    num = 0.0
    den = len(idxs)
    for doc, n_c in cand_counts.items():
        all_idxs = by_doc_all[doc]
        rate = sum(bool(pos[i]["roles"][role]) for i in all_idxs) / len(all_idxs)
        num += n_c * rate
    return num / den if den else 0.0


def z_score(obs_rate, exp_rate, n):
    var = max(exp_rate * (1.0 - exp_rate) / max(n, 1), 1e-6)
    return (obs_rate - exp_rate) / math.sqrt(var)


def train_discovery(pos, args, seed):
    cands = candidate_metadata(pos, args.min_train_n, args.min_train_docs)
    if not cands:
        return [], []
    expected = {}
    observed = {}
    for cid, idxs in cands.items():
        for role in ROLES:
            exp = expected_rate(pos, idxs, role)
            obs = sum(bool(pos[i]["roles"][role]) for i in idxs) / len(idxs)
            expected[(cid, role)] = exp
            observed[(cid, role)] = {
                "n": len(idxs), "docs": len({pos[i]["doc"] for i in idxs}),
                "obs_rate": obs, "expected_rate": exp, "z": z_score(obs, exp, len(idxs)),
            }

    by_doc = defaultdict(list)
    for i, p in enumerate(pos):
        by_doc[p["doc"]].append(i)
    identities = [p["identity"] for p in pos]
    rng = random.Random(seed)
    max_null = []
    for _ in range(args.train_permutations):
        perm = list(identities)
        for idxs in by_doc.values():
            vals = [perm[i] for i in idxs]
            rng.shuffle(vals)
            for i, v in zip(idxs, vals):
                perm[i] = v
        perm_by = defaultdict(list)
        for i, cid in enumerate(perm):
            if cid in cands:
                perm_by[cid].append(i)
        mx = 0.0
        for cid, orig_idxs in cands.items():
            idxs = perm_by.get(cid, [])
            if len(idxs) != len(orig_idxs):
                continue
            for role in ROLES:
                obs = sum(bool(pos[i]["roles"][role]) for i in idxs) / len(idxs)
                z = z_score(obs, expected[(cid, role)], len(idxs))
                mx = max(mx, abs(z))
        max_null.append(mx)

    ranked = []
    for (cid, role), o in observed.items():
        p_fwer = (1 + sum(x >= abs(o["z"]) for x in max_null)) / (1 + len(max_null))
        ranked.append({
            "candidate_id": cid, "role": role,
            "train_n": o["n"], "train_docs": o["docs"],
            "train_observed_rate": o["obs_rate"], "train_expected_rate": o["expected_rate"],
            "train_delta_rate": o["obs_rate"] - o["expected_rate"], "train_z": o["z"],
            "train_direction": "ENRICHED" if o["z"] > 0 else "DEPLETED",
            "train_fwer_p": p_fwer,
            "selected": p_fwer <= args.train_fwer_threshold and abs(o["obs_rate"] - o["expected_rate"]) >= args.min_train_delta,
        })
    ranked.sort(key=lambda x: (x["train_fwer_p"], -abs(x["train_z"]), x["candidate_id"], x["role"]))
    return ranked, [x for x in ranked if x["selected"]]


def test_selected(pos, selected, args, seed):
    if not selected:
        return []
    cands = defaultdict(list)
    for i, p in enumerate(pos):
        cands[p["identity"]].append(i)
    evaluable = []
    for s in selected:
        idxs = cands.get(s["candidate_id"], [])
        regs = sorted({pos[i]["region"] for i in idxs})
        docs = {pos[i]["doc"] for i in idxs}
        if len(idxs) >= args.min_test_n and len(regs) >= args.min_test_regions and len(docs) >= args.min_test_docs:
            evaluable.append((s, idxs, regs, docs))
    m = max(1, len(evaluable))

    by_doc = defaultdict(list)
    for i, p in enumerate(pos):
        by_doc[p["doc"]].append(i)
    identities = [p["identity"] for p in pos]
    rng = random.Random(seed)
    out = []
    for k, (s, idxs, regs, docs) in enumerate(evaluable):
        role = s["role"]
        exp = expected_rate(pos, idxs, role)
        obs = sum(bool(pos[i]["roles"][role]) for i in idxs) / len(idxs)
        z = z_score(obs, exp, len(idxs))
        sign = 1 if s["train_z"] > 0 else -1
        signed_obs = sign * z
        local = random.Random(rng.randrange(2**63) + k)
        null = []
        for _ in range(args.test_permutations):
            perm = list(identities)
            for didxs in by_doc.values():
                vals = [perm[i] for i in didxs]
                local.shuffle(vals)
                for i, v in zip(didxs, vals):
                    perm[i] = v
            pidxs = [i for i, cid in enumerate(perm) if cid == s["candidate_id"]]
            if len(pidxs) != len(idxs):
                continue
            prate = sum(bool(pos[i]["roles"][role]) for i in pidxs) / len(pidxs)
            null.append(sign * z_score(prate, exp, len(pidxs)))
        p_one = (1 + sum(x >= signed_obs for x in null)) / (1 + len(null))
        p_bonf = min(1.0, p_one * m)
        same = (z > 0) == (s["train_z"] > 0)
        region_rates = {}
        for reg in regs:
            ridxs = [i for i in idxs if pos[i]["region"] == reg]
            region_rates[reg] = {
                "n": len(ridxs),
                "observed_rate": sum(bool(pos[i]["roles"][role]) for i in ridxs) / len(ridxs),
            }
        out.append({
            **s,
            "test_n": len(idxs), "test_docs": len(docs), "test_regions": regs,
            "test_observed_rate": obs, "test_expected_rate": exp,
            "test_delta_rate": obs - exp, "test_z": z,
            "same_direction": same, "test_one_sided_p": p_one,
            "test_bonferroni_p": p_bonf,
            "replication_pass": bool(same and p_bonf <= 0.05 and abs(obs-exp) >= args.min_test_delta),
            "region_rates": region_rates,
        })
    out.sort(key=lambda x: (x["test_bonferroni_p"], x["train_fwer_p"]))
    return out


def family_run(all_docs, reveal, family, args, seed):
    ht_docs = [d for d in all_docs if d["region"] == "HT"]
    nonht_docs = [d for d in all_docs if d["region"] != "HT"]
    ht = eligible_positions(ht_docs, family, reveal)
    nonht = eligible_positions(nonht_docs, family, reveal)
    ranked, selected = train_discovery(ht, args, seed + 1)
    rep = test_selected(nonht, selected, args, seed + 2)
    for x in rep:
        x["revealed_label"] = reveal.get(x["candidate_id"])
    survivors = [x for x in rep if x["replication_pass"]]
    return {
        "family": family,
        "train_partition": "HT",
        "replication_partition": "NON_HT",
        "train_positions": len(ht), "test_positions": len(nonht),
        "train_candidate_role_tests": len(ranked),
        "selected_train_count": len(selected),
        "evaluable_cross_region_count": len(rep),
        "replication_survivor_count": len(survivors),
        "top_train_candidate_roles": ranked[:30],
        "cross_region_results": rep,
        "survivors": survivors,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=260814525)
    ap.add_argument("--train-permutations", type=int, default=5000)
    ap.add_argument("--test-permutations", type=int, default=10000)
    ap.add_argument("--min-train-n", type=int, default=8)
    ap.add_argument("--min-train-docs", type=int, default=4)
    ap.add_argument("--min-test-n", type=int, default=4)
    ap.add_argument("--min-test-docs", type=int, default=3)
    ap.add_argument("--min-test-regions", type=int, default=2)
    ap.add_argument("--train-fwer-threshold", type=float, default=0.10)
    ap.add_argument("--min-train-delta", type=float, default=0.15)
    ap.add_argument("--min-test-delta", type=float, default=0.10)
    args = ap.parse_args()

    docs, failures, reveal = load_corpus(Path(args.corpus))
    word = family_run(docs, reveal, "word", args, args.seed + 100)
    suffix = family_run(docs, reveal, "suffix", args, args.seed + 200)
    survivors = [{"family": "word", **x} for x in word["survivors"]] + [{"family": "suffix", **x} for x in suffix["survivors"]]

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-RECORD-ROLE-CROSS-REGION-2026-08-14-v0.6",
        "version": VERSION,
        "status": "RECORD_ROLE_CROSS_REGION_EXECUTION",
        "source": {
            "repository": "mwenge/lineara.xyz",
            "frozen_commit": base.CORPUS_COMMIT,
            "LinearAInscriptions_js_blob_sha": base.CORPUS_BLOB,
        },
        "corpus_counts": {"parsed_inscriptions": len(docs), "parse_failures": len(failures)},
        "frozen_exclusion_mask": {
            "words_removed_before_scoring": ["VIR*", "KU-RO", "KI-RO", "PO-TO-KU-RO", "GRA"],
            "suffixes_removed_before_scoring": ["VIR*", "RO", "GRA"],
            "selection_after_mask_uses_semantic_labels": False,
        },
        "roles": list(ROLES),
        "methodology": {
            "discovery_partition": "HT_ONLY",
            "replication_partition": "ALL_NON_HT",
            "replication_is_pristine_unseen_holdout": False,
            "why_not_pristine": "Earlier JANUS stages touched the full corpus; this is a cross-region replication stress test.",
            "null": "WITHIN_DOCUMENT_ANONYMOUS_IDENTITY_SHUFFLE_PRESERVING_CANDIDATE_COUNTS_NUMERIC_SLOTS_AND_ROW_GEOMETRY",
            "train_familywise_control": "max-T across candidate x role tests",
            "test_familywise_control": "Bonferroni across evaluable train-selected candidate-role pairs",
            "direction_frozen_from_train": True,
        },
        "word_family": word,
        "suffix_family": suffix,
        "cross_region_survivors": survivors,
        "epistemic_gate": {
            "cross_region_survivor_count": len(survivors),
            "record_role_candidate_exists": bool(survivors),
            "new_anchor_established": False,
            "decipherment_established": False,
            "promotion": "NOVELTY_AND_BEHAVIORAL_AUDIT_REQUIRED" if survivors else "NO_PROMOTION",
            "required_next_if_survivor": [
                "post-score literature novelty audit",
                "alternative row/line segmentation replay",
                "independent corpus/parser implementation",
                "fresh transcription source for true held-out replication",
                "test whether role predicts a document-level behavioral outcome beyond position alone",
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
