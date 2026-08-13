#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, random, re
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "artifacts" / "full_data_relation_gate_2026_08_13"
SEED = 20260813
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{4,}")
META_KEYS = {
    "title", "name", "description", "display_title", "display_name",
    "repository", "url", "html_url", "download_url", "git_url", "path",
    "created_date_utc", "modified_date", "created_at", "updated_at",
    "provenance", "source", "sources", "source_objects", "scan_scope",
}

def sha(x: str) -> str:
    return hashlib.sha256(x.encode("utf-8")).hexdigest()

def walk_strings(x, out):
    if isinstance(x, dict):
        for k, v in x.items():
            if k not in META_KEYS:
                walk_strings(v, out)
    elif isinstance(x, list):
        for v in x: walk_strings(v, out)
    elif isinstance(x, str):
        out.append(x)

def canonical_payload(obj):
    if isinstance(obj, dict):
        return {k: canonical_payload(v) for k,v in sorted(obj.items()) if k not in META_KEYS}
    if isinstance(obj, list): return [canonical_payload(v) for v in obj]
    return obj

def refs_for(doc, known):
    text = json.dumps(doc, ensure_ascii=False, sort_keys=True)
    hits = []
    for p in known:
        base = Path(p).name
        if base in text:
            hits.append(p)
    # Stable high-information identifiers.
    strings = []
    walk_strings(doc, strings)
    for s in strings:
        for m in TOKEN_RE.findall(s):
            if len(m) >= 10 and ("-" in m or "_" in m) and m in known_ids:
                hits.append(known_ids[m])
    return sorted(set(hits))

files = sorted(str(p.relative_to(DATA)) for p in DATA.rglob("*.json"))
records, errors = {}, []
for rel in files:
    p = DATA / rel
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        records[rel] = obj
    except Exception as e:
        errors.append({"file": rel, "error": repr(e)})

known_ids = {}
for rel, obj in records.items():
    if isinstance(obj, dict):
        for k in ("artifact_uuid", "artifact_slug", "connection_id", "id", "uuid"):
            v = obj.get(k)
            if isinstance(v, str): known_ids[v] = rel

real_edges = {}
blind_edges = {}
for rel, obj in records.items():
    real_edges[rel] = refs_for(obj, records.keys())
    blind = canonical_payload(obj)
    blind_edges[rel] = refs_for(blind, records.keys())

# Matched rewiring: preserve each source's number of outgoing reference slots,
# but randomly reassign targets to other files, using a fixed seed.
rng = random.Random(SEED)
all_targets = list(records.keys())
rewired_edges = {}
null_edges = {}
for rel in records:
    n = len(real_edges[rel])
    if n:
        pool = [x for x in all_targets if x != rel]
        rewired_edges[rel] = sorted(set(rng.sample(pool, min(n, len(pool)))))
        null_edges[rel] = sorted(set(rng.sample(pool, min(n, len(pool)))))
    else:
        rewired_edges[rel] = []
        null_edges[rel] = []

def edge_count(d): return sum(len(v) for v in d.values())

def overlap(a,b):
    return sum(len(set(a[k]) & set(b[k])) for k in a)

real_n = edge_count(real_edges)
blind_n = edge_count(blind_edges)
rewire_overlap = overlap(real_edges, rewired_edges)
null_overlap = overlap(real_edges, null_edges)

# Per-file 1/1/0/0 gate: at least one real relation, at least one survives
# metadata blinding, and no relation survives either matched rewiring or null.
per_file = []
for rel in records:
    r = set(real_edges[rel]); b = set(blind_edges[rel])
    rw = set(rewired_edges[rel]); nu = set(null_edges[rel])
    per_file.append({
        "file": rel,
        "real": bool(r),
        "blind": bool(r & b),
        "rewired": bool(r & rw),
        "null": bool(r & nu),
        "real_targets": sorted(r),
        "blind_survivors": sorted(r & b),
        "rewired_survivors": sorted(r & rw),
        "null_survivors": sorted(r & nu),
    })

gated = [x for x in per_file if x["real"]]
passed = [x for x in gated if x["blind"] and not x["rewired"] and not x["null"]]

schema_counts = Counter()
for obj in records.values():
    if isinstance(obj, dict): schema_counts[tuple(sorted(obj.keys()))] += 1
    else: schema_counts[(type(obj).__name__,)] += 1

summary = {
    "test": "JANUS_FULL_DATA_RELATION_GATE",
    "version": "v1.0",
    "seed": SEED,
    "scope": "data/**/*.json",
    "n_files": len(files),
    "n_parseable": len(records),
    "n_parse_errors": len(errors),
    "real_edge_count": real_n,
    "blind_edge_count": blind_n,
    "rewire_survivor_count": rewire_overlap,
    "null_survivor_count": null_overlap,
    "n_files_with_real_edges": len(gated),
    "n_files_passing_1_1_0_0": len(passed),
    "pass_rate_among_edge_files": (len(passed)/len(gated) if gated else None),
    "rule": "REAL=1, BLIND=1, REWIRED=0, NULL=0",
    "errors": errors,
    "schema_families": len(schema_counts),
}

OUT.mkdir(parents=True, exist_ok=True)
(OUT/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT/"per_file.json").write_text(json.dumps(per_file, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT/"manifest.json").write_text(json.dumps({"files": files, "scope_sha256": sha("\n".join(files)), "seed": SEED}, ensure_ascii=False, indent=2), encoding="utf-8")

print(json.dumps(summary, ensure_ascii=False, indent=2))
