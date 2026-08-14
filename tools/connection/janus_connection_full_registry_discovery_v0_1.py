#!/usr/bin/env python3
"""JANUS Connection full-registry hidden-pattern discovery engine v0.1.

Scans every parseable *.json in the checkout. Connection-family artifacts are
included in corpus accounting and dependency memory, but are not eligible to
self-confirm new Connection evidence. Integrity sidecars likewise carry zero
independent-evidence weight.

The engine is intentionally deterministic and stdlib-only. It separates
CONTENT similarity (what a record is about) from OPERATOR/STRUCTURE similarity
(how evidence, gates, transitions, controls and schemas are organized). High
operator similarity with low content similarity is ranked as a candidate human
blind-spot bridge, subject to lineage/dependency penalties.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import math
import os
import re
from pathlib import Path

VERSION = "0.1"
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+", re.UNICODE)
VERSION_RE = re.compile(r"(?:^|[-_])v?\d+(?:[._-]\d+)*(?:$|[-_])", re.I)
DATE_RE = re.compile(r"20\d\d[-_]\d\d[-_]\d\d")
HASH_RE = re.compile(r"^[0-9a-f]{32,128}$", re.I)
URL_RE = re.compile(r"^(?:https?://|git@)", re.I)

STOP = {
    # project/common schema noise
    "janus","json","artifact","uuid","version","schema","data","registry","research",
    "path","file","files","name","title","status","type","value","values","note","notes",
    "result","results","source","sources","object","objects","record","records","field","fields",
    "true","false","null","none","yes","no","en","ru","utc","local","timestamp","date",
    "current","new","old","v1","v2","v3","v0","meta","canonical","purpose","summary",
    "the","a","an","and","or","of","to","in","for","on","with","by","from","as","is",
    "are","be","this","that","it","its","not","only","may","can","must","should","will",
    "и","в","на","с","по","для","что","это","как","не","или","к","из","от","до","при",
    "его","ее","их","быть","может","только","так","также","у","о","об","под","над",
}

GENERIC_FILE_TOKENS = {
    "janus","connection","scan","data","batch","proof","hardening","ledger","registry","meta",
    "v","json","current","audit","strengthening","report","raw","seed","manifest"
}

ROLE_WEIGHTS = {
    "PRIMARY_OR_DOMAIN_RECORD": 1.0,
    "DERIVED_META_OR_LEDGER": 0.72,
    "CONNECTION_HYPOTHESIS_MEMORY": 0.0,
    "INTEGRITY_DERIVATIVE": 0.0,
}


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def canonical_sha(obj) -> str:
    b = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(b)


def split_identifier(s: str) -> list[str]:
    s = re.sub(r"([a-zа-яё])([A-ZА-ЯЁ])", r"\1 \2", s)
    s = s.replace("_", " ").replace("-", " ").replace("/", " ").replace(".", " ")
    out = []
    for tok in TOKEN_RE.findall(s.lower()):
        if len(tok) < 2 or tok in STOP or tok.isdigit() or HASH_RE.match(tok):
            continue
        out.append(tok)
    return out


def enumish(s: str) -> bool:
    if len(s) > 120 or URL_RE.match(s.strip()) or HASH_RE.match(s.strip()):
        return False
    letters = [c for c in s if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(c.isupper() for c in letters) / len(letters)
    return upper_ratio >= 0.55 or "_" in s or "->" in s or "→" in s


def normalize_pointer(parts: list[str]) -> str:
    return "/" + "/".join("[]" if p.isdigit() else p.lower() for p in parts)


def flatten(obj, parts=None, depth=0):
    if parts is None:
        parts = []
    yield parts, obj
    if depth > 30:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from flatten(v, parts + [str(k)], depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from flatten(v, parts + [str(i)], depth + 1)


def classify_role(path: str, obj) -> str:
    base = Path(path).name.upper()
    p = path.lower()
    au = ""
    if isinstance(obj, dict):
        au = str(obj.get("artifact_uuid", "")).upper()
    if base.endswith(".SHA256.JSON") or "SHA256-SIDECAR" in au or "INTEGRITY-SIDECAR" in au:
        return "INTEGRITY_DERIVATIVE"
    if p.startswith("registry/connections/") or base.startswith("JANUS-CONNECTION-") or "CONNECTION-SCAN" in au:
        return "CONNECTION_HYPOTHESIS_MEMORY"
    if any(x in base for x in ("LEDGER", "AUDIT", "STRENGTHENING", "INDEX", "DOSSIER", "CURRENT")):
        return "DERIVED_META_OR_LEDGER"
    return "PRIMARY_OR_DOMAIN_RECORD"


def lineage_stem(path: str, obj) -> str:
    if isinstance(obj, dict) and obj.get("artifact_uuid"):
        s = str(obj["artifact_uuid"])
    else:
        s = Path(path).stem
    s = DATE_RE.sub("DATE", s)
    s = re.sub(r"(?:[-_])v?\d+(?:[._-]\d+)*$", "", s, flags=re.I)
    s = re.sub(r"(?:[-_])(scan|batch)[-_]?\d+.*$", "", s, flags=re.I)
    s = re.sub(r"\d+", "#", s)
    return s.upper()


def domain_bucket(path: str) -> str:
    pp = Path(path).parts
    if not pp:
        return "root"
    if pp[0] == "registry" and len(pp) >= 2:
        return "registry:" + pp[1]
    if pp[0] == "security_research" and len(pp) >= 2:
        return "security:" + pp[1]
    if pp[0] == "data":
        if len(pp) >= 3:
            return "data:" + pp[1]
        toks = [t for t in split_identifier(Path(path).stem) if t not in GENERIC_FILE_TOKENS]
        return "data:" + (toks[0] if toks else "root")
    return pp[0]


def extract_doc(path: str, obj, raw: bytes):
    op = collections.Counter()
    content = collections.Counter()
    pointers = set()
    refs = set()
    scalar_enum = set()
    keyset = set()
    top_keys = []
    if isinstance(obj, dict):
        top_keys = sorted(map(str, obj.keys()))

    for parts, val in flatten(obj):
        if parts:
            ptr = normalize_pointer(parts)
            pointers.add(ptr)
            key = parts[-1]
            if not key.isdigit():
                keyset.add(key.lower())
                for t in split_identifier(key):
                    op["K:" + t] += 2
                if len(parts) >= 2 and not parts[-2].isdigit():
                    p = parts[-2].lower()
                    c = key.lower()
                    op["PC:" + p + ">" + c] += 1
        if isinstance(val, bool):
            if parts and not parts[-1].isdigit():
                op["BV:" + parts[-1].lower() + "=" + str(val).lower()] += 2
        elif isinstance(val, (int, float)) and not isinstance(val, bool):
            if parts and abs(float(val)) <= 1000000:
                op["NT:" + parts[-1].lower()] += 1
        elif isinstance(val, str):
            st = val.strip()
            if st.endswith(".json") and len(st) < 400:
                refs.add(st.lstrip("./"))
            if enumish(st):
                scalar_enum.add(st[:120])
                k = parts[-1].lower() if parts and not parts[-1].isdigit() else "value"
                for t in split_identifier(st):
                    op["E:" + k + ":" + t] += 1
            # narrative/content channel: prose + titles + labels, but cap per scalar
            if len(st) >= 12 and not URL_RE.match(st) and not HASH_RE.match(st):
                toks = split_identifier(st[:1200])
                for t in toks[:160]:
                    content["T:" + t] += 1

    # filename tokens are content, not operator features
    for t in split_identifier(Path(path).stem):
        if t not in GENERIC_FILE_TOKENS:
            content["F:" + t] += 2

    meta = {}
    if isinstance(obj, dict):
        for k in ("artifact_uuid","artifact_slug","registry_class","schema","schema_version","status","version"):
            if k in obj and isinstance(obj[k], (str,int,float,bool)):
                meta[k] = obj[k]
        title = obj.get("title")
        if isinstance(title, str):
            meta["title"] = title[:300]
        elif isinstance(title, dict):
            meta["title"] = {str(k): str(v)[:240] for k,v in list(title.items())[:4]}

    return {
        "path": path,
        "bytes": len(raw),
        "sha256_raw": sha256_bytes(raw),
        "sha256_canonical_json": canonical_sha(obj),
        "role": classify_role(path, obj),
        "role_weight": ROLE_WEIGHTS[classify_role(path, obj)],
        "lineage_stem": lineage_stem(path, obj),
        "domain_bucket": domain_bucket(path),
        "meta": meta,
        "top_level_keys": top_keys,
        "op": op,
        "content": content,
        "pointers": pointers,
        "refs": refs,
        "keyset": keyset,
        "scalar_enum": scalar_enum,
    }


def tfidf_vectors(docs, field: str):
    n = len(docs)
    df = collections.Counter()
    for d in docs:
        for f in d[field]:
            df[f] += 1
    idf = {f: math.log((1+n)/(1+c)) + 1.0 for f,c in df.items()}
    vecs, norms = [], []
    for d in docs:
        v = {}
        for f,c in d[field].items():
            # logarithmic term frequency
            v[f] = (1.0 + math.log(c)) * idf[f]
        norm = math.sqrt(sum(x*x for x in v.values())) or 1.0
        vecs.append(v); norms.append(norm)
    return df, idf, vecs, norms


def cosine(v1, n1, v2, n2):
    if len(v1) > len(v2):
        v1, v2 = v2, v1
    dot = sum(w * v2.get(f, 0.0) for f,w in v1.items())
    return dot / (n1*n2) if dot else 0.0


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dependency_penalty(a, b, explicit_ref):
    reasons = []
    factor = 1.0
    if a["sha256_canonical_json"] == b["sha256_canonical_json"]:
        return 0.0, ["EXACT_CANONICAL_DUPLICATE"]
    if a["lineage_stem"] == b["lineage_stem"]:
        factor *= 0.18; reasons.append("SAME_LINEAGE_STEM")
    if explicit_ref:
        factor *= 0.48; reasons.append("EXPLICIT_CROSS_REFERENCE")
    if a["domain_bucket"] == b["domain_bucket"]:
        factor *= 0.78; reasons.append("SAME_DOMAIN_BUCKET")
    if a["role_weight"] < 1.0 or b["role_weight"] < 1.0:
        factor *= min(1.0, max(a["role_weight"],0.25) * max(b["role_weight"],0.25) * 1.35)
        reasons.append("DERIVED_OR_META_ROLE")
    return factor, reasons


def compact_feature(f: str) -> str:
    return f.replace("PC:", "parent_child:").replace("K:", "key:").replace("E:", "enum:").replace("BV:", "bool:").replace("NT:", "numeric_field:")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--out", required=True)
    ap.add_argument("--top-pairs", type=int, default=180)
    ap.add_argument("--top-motifs", type=int, default=140)
    args = ap.parse_args()

    root = Path(args.repo_root).resolve()
    files = sorted(p for p in root.rglob("*.json") if ".git" not in p.parts)
    docs = []
    parse_failures = []
    for p in files:
        rel = p.relative_to(root).as_posix()
        raw = p.read_bytes()
        try:
            obj = json.loads(raw.decode("utf-8"))
            docs.append(extract_doc(rel, obj, raw))
        except Exception as e:
            parse_failures.append({"path": rel, "error": type(e).__name__ + ": " + str(e)[:300], "sha256_raw": sha256_bytes(raw), "bytes": len(raw)})

    n = len(docs)
    path_to_idx = {d["path"]: i for i,d in enumerate(docs)}
    # resolve explicit JSON references against corpus paths
    explicit_edges = set()
    for i,d in enumerate(docs):
        for r in d["refs"]:
            if r in path_to_idx:
                j = path_to_idx[r]
                explicit_edges.add(tuple(sorted((i,j))))

    op_df, op_idf, op_vec, op_norm = tfidf_vectors(docs, "op")
    co_df, co_idf, co_vec, co_norm = tfidf_vectors(docs, "content")

    # Inverted index of informative operator features. Common boilerplate and singletons do not seed pair candidates.
    max_df = max(3, min(80, int(max(4, n * 0.18))))
    inv = collections.defaultdict(list)
    for i,d in enumerate(docs):
        if d["role_weight"] <= 0:
            continue
        for f in d["op"]:
            c = op_df[f]
            if 2 <= c <= max_df:
                inv[f].append(i)

    pair_shared = collections.defaultdict(float)
    pair_feats = collections.defaultdict(list)
    for f, ids in inv.items():
        w = op_idf[f]
        for i,j in itertools.combinations(ids,2):
            if docs[i]["role_weight"] <= 0 or docs[j]["role_weight"] <= 0:
                continue
            key = (i,j) if i<j else (j,i)
            pair_shared[key] += w
            if len(pair_feats[key]) < 16:
                pair_feats[key].append((w,f))

    pair_rows = []
    for (i,j), shared_weight in pair_shared.items():
        a,b = docs[i],docs[j]
        op_sim = cosine(op_vec[i], op_norm[i], op_vec[j], op_norm[j])
        if op_sim < 0.035:
            continue
        content_sim = cosine(co_vec[i], co_norm[i], co_vec[j], co_norm[j])
        # structural pointers are exact normalized paths; low weight because common templates can dominate.
        struct_sim = jaccard(a["pointers"], b["pointers"])
        explicit = (i,j) in explicit_edges
        dep, reasons = dependency_penalty(a,b,explicit)
        if dep <= 0:
            continue
        # reward topology/operator similarity when narrative/content similarity is lower.
        hiddenness = max(0.0, 1.0 - min(1.0, content_sim / 0.72))
        rarity = min(1.0, shared_weight / 22.0)
        base = 0.56*op_sim + 0.20*struct_sim + 0.14*rarity + 0.10*hiddenness
        cross_domain = 1.10 if a["domain_bucket"] != b["domain_bucket"] else 0.88
        score = base * dep * cross_domain
        if score < 0.045:
            continue
        feats = [compact_feature(f) for _,f in sorted(pair_feats[(i,j)], reverse=True)[:10]]
        pair_rows.append({
            "score": round(score, 8),
            "operator_similarity": round(op_sim, 8),
            "content_similarity": round(content_sim, 8),
            "structural_pointer_jaccard": round(struct_sim, 8),
            "hiddenness_component": round(hiddenness, 8),
            "dependency_factor": round(dep, 8),
            "dependency_flags": reasons,
            "cross_domain": a["domain_bucket"] != b["domain_bucket"],
            "a": {"path":a["path"],"domain":a["domain_bucket"],"role":a["role"],"artifact_uuid":a["meta"].get("artifact_uuid")},
            "b": {"path":b["path"],"domain":b["domain_bucket"],"role":b["role"],"artifact_uuid":b["meta"].get("artifact_uuid")},
            "shared_operator_features": feats,
            "interpretation_status": "MACHINE_CANDIDATE_NOT_VALIDATED"
        })
    pair_rows.sort(key=lambda x:(x["score"],x["operator_similarity"],-x["content_similarity"]), reverse=True)

    # Higher-order feature motifs: individual operator features spread across >=3 domain buckets.
    motifs = []
    for f, ids in inv.items():
        elig = [i for i in ids if docs[i]["role_weight"] > 0]
        domains = sorted({docs[i]["domain_bucket"] for i in elig})
        lineages = {docs[i]["lineage_stem"] for i in elig}
        if len(elig) < 3 or len(domains) < 3 or len(lineages) < 3:
            continue
        score = op_idf[f] * math.log1p(len(domains)) * math.log1p(len(lineages))
        motifs.append({
            "feature": compact_feature(f),
            "score": round(score,8),
            "document_count": len(elig),
            "domain_count": len(domains),
            "lineage_count": len(lineages),
            "domains": domains[:20],
            "example_paths": [docs[i]["path"] for i in elig[:14]],
            "status": "CROSS_DOMAIN_OPERATOR_RECURRENCE_CANDIDATE"
        })
    motifs.sort(key=lambda x:(x["score"],x["domain_count"],-x["document_count"]), reverse=True)

    # Co-occurring operator motif pairs across independently named/domain-spread records.
    motif_pair_docs = collections.defaultdict(set)
    for i,d in enumerate(docs):
        if d["role_weight"] <= 0:
            continue
        informative = []
        for f in d["op"]:
            c = op_df[f]
            if 2 <= c <= max_df:
                informative.append((op_idf[f],f))
        topf = [f for _,f in sorted(informative,reverse=True)[:24]]
        for f1,f2 in itertools.combinations(sorted(topf),2):
            motif_pair_docs[(f1,f2)].add(i)
    motif_pairs=[]
    for (f1,f2),idsset in motif_pair_docs.items():
        ids=sorted(idsset)
        if len(ids)<3:
            continue
        domains={docs[i]["domain_bucket"] for i in ids}
        lineages={docs[i]["lineage_stem"] for i in ids}
        if len(domains)<3 or len(lineages)<3:
            continue
        p12=len(ids)/max(n,1); p1=op_df[f1]/max(n,1); p2=op_df[f2]/max(n,1)
        pmi=math.log((p12+1e-12)/(p1*p2+1e-12),2)
        if pmi<=0:
            continue
        score=pmi*math.log1p(len(ids))*math.log1p(len(domains))
        motif_pairs.append({
            "features":[compact_feature(f1),compact_feature(f2)],
            "score":round(score,8),"pmi_bits":round(pmi,8),"document_count":len(ids),
            "domain_count":len(domains),"lineage_count":len(lineages),
            "example_paths":[docs[i]["path"] for i in ids[:14]],
            "status":"HIGHER_ORDER_CROSS_DOMAIN_MOTIF_CANDIDATE"
        })
    motif_pairs.sort(key=lambda x:(x["score"],x["domain_count"]),reverse=True)

    # Bridge nodes from top candidate graph: high cross-domain weighted degree.
    bridge_acc=collections.defaultdict(lambda:{"degree":0,"score_sum":0.0,"domains":set(),"neighbors":[]})
    for row in pair_rows[:max(300,args.top_pairs*3)]:
        if not row["cross_domain"]:
            continue
        for side,other in ((row["a"],row["b"]),(row["b"],row["a"])):
            x=bridge_acc[side["path"]]
            x["degree"]+=1; x["score_sum"]+=row["score"]; x["domains"].add(other["domain"])
            if len(x["neighbors"])<10:
                x["neighbors"].append({"path":other["path"],"domain":other["domain"],"edge_score":row["score"]})
    bridges=[]
    for path,x in bridge_acc.items():
        if len(x["domains"])<2:
            continue
        bridges.append({"path":path,"cross_domain_degree":x["degree"],"distinct_neighbor_domains":len(x["domains"]),
                        "score_sum":round(x["score_sum"],8),"neighbor_domains":sorted(x["domains"]),"sample_neighbors":x["neighbors"]})
    bridges.sort(key=lambda x:(x["distinct_neighbor_domains"],x["score_sum"],x["cross_domain_degree"]),reverse=True)

    role_counts=collections.Counter(d["role"] for d in docs)
    domain_counts=collections.Counter(d["domain_bucket"] for d in docs)
    lineage_counts=collections.Counter(d["lineage_stem"] for d in docs)
    canonical_counts=collections.Counter(d["sha256_canonical_json"] for d in docs)
    duplicates=[{"sha256_canonical_json":h,"count":c,"paths":[d["path"] for d in docs if d["sha256_canonical_json"]==h]}
                for h,c in canonical_counts.items() if c>1]

    snapshot_sha=os.environ.get("GITHUB_SHA") or os.popen("git rev-parse HEAD 2>/dev/null").read().strip() or None
    manifest=[{"path":d["path"],"sha256_raw":d["sha256_raw"],"sha256_canonical_json":d["sha256_canonical_json"],
               "bytes":d["bytes"],"role":d["role"],"lineage_stem":d["lineage_stem"],"domain_bucket":d["domain_bucket"],"meta":d["meta"]}
              for d in docs]

    out={
        "schema":"janus.connection.full_registry_discovery.v0_1",
        "artifact_uuid":"JANUS-CONNECTION-FULL-REGISTRY-DISCOVERY-2026-08-14-V0.1",
        "engine_version":VERSION,
        "snapshot_commit":snapshot_sha,
        "objective":"Search every JSON in the repository for non-obvious cross-object relations, especially high operator/structural similarity across low-content-similarity domains, while collapsing direct lineage and preventing Connection-family self-confirmation.",
        "epistemic_boundary":{
            "all_json_accounted_in_corpus_manifest":True,
            "connection_family_included_as_hypothesis_memory_but_not_independent_support":True,
            "integrity_sidecars_included_but_zero_independent_support":True,
            "machine_candidates_are_not_causal_proof":True,
            "machine_candidates_are_not_novelty_proof":True,
            "pair_scores_are_not_probabilities":True,
            "motif_pmi_is_descriptive_not_population_significance":True,
            "human_non_obviousness_not_yet_blind_human_measured":True
        },
        "corpus":{
            "json_files_seen":len(files),"json_parse_success":n,"json_parse_failures":len(parse_failures),
            "total_json_bytes":sum(d["bytes"] for d in docs)+sum(x["bytes"] for x in parse_failures),
            "role_counts":dict(role_counts),"domain_bucket_count":len(domain_counts),"lineage_stem_count":len(lineage_counts),
            "exact_canonical_duplicate_groups":len(duplicates),"explicit_json_reference_edges":len(explicit_edges)
        },
        "ranking_model":{
            "channels":["CONTENT","OPERATOR_STRUCTURE"],
            "blind_spot_target":"high operator/structure similarity + relatively low narrative/content similarity + cross-domain + dependency-collapsed",
            "dependency_penalties":["exact duplicate -> zero","same lineage stem -> strong penalty","explicit cross-reference -> penalty","same domain -> penalty","derived/meta role -> penalty"],
            "discovery_evidence_exclusions":["Connection-family hypothesis memory","integrity derivative sidecars"],
            "no_llm_or_embedding_used":True,
            "deterministic_stdlib_only":True
        },
        "top_hidden_bridge_pairs":pair_rows[:args.top_pairs],
        "top_cross_domain_operator_motifs":motifs[:args.top_motifs],
        "top_higher_order_motif_pairs":motif_pairs[:args.top_motifs],
        "top_bridge_documents":bridges[:80],
        "exact_duplicate_groups":duplicates,
        "parse_failures":parse_failures,
        "corpus_manifest":manifest,
        "claim_ceiling":"FULL_CORPUS_MACHINE_DISCOVERY_PASS_ONLY; candidates require source-level reinspection, independence review, destructive controls and where applicable held-out/external transport before promotion.",
        "next_gate":"Human/assistant source-level interpretation of top cross-domain candidates, followed by frozen relation-specific tests on the strongest non-lineage motifs."
    }
    out_path=Path(args.out)
    out_path.parent.mkdir(parents=True,exist_ok=True)
    out_path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS_FULL_CORPUS_DISCOVERY_EXECUTED","snapshot":snapshot_sha,"json_seen":len(files),"parsed":n,
                      "parse_failures":len(parse_failures),"pair_candidates":len(pair_rows),"motifs":len(motifs),
                      "motif_pairs":len(motif_pairs),"bridges":len(bridges),"output":str(out_path)},ensure_ascii=False))

if __name__ == "__main__":
    main()
