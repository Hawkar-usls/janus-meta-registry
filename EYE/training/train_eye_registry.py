#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "janus.eye.meta_registry_training.v1"
TEXT_EXTENSIONS = {
    ".json", ".md", ".markdown", ".txt", ".py", ".yml", ".yaml", ".toml",
    ".ini", ".cfg", ".csv", ".tsv", ".html", ".htm", ".js", ".ts", ".tsx",
    ".jsx", ".css", ".scss", ".sh", ".ps1", ".xml", ".jsonl", ".ndjson"
}
EXCLUDED_DIR_NAMES = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"}
EXCLUDED_PREFIXES = ("EYE/generated/", "assets/hrain-full-memory/")
EXCLUDED_EXACT_PATHS = {"assets/hrain-registry-index.json"}
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_.:/+-]{2,}", re.UNICODE)
HEX64_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
RELATION_KEYS = {
    "parent", "parents", "parent_artifact", "parent_artifacts", "extends", "sources",
    "source_artifact", "source_artifacts", "canonical_path", "canonical_paths",
    "lineage", "depends_on", "dependencies", "supersedes", "superseded_by",
    "related_artifacts", "evidence", "provenance_sources"
}
ARTIFACT_ID_KEYS = ("artifact_id", "artifact_uuid", "receipt_id", "component_id", "benchmark_id", "id", "schema")
TITLE_KEYS = ("title", "title_ru", "title_en", "canonical_title", "name")
STATUS_KEYS = ("status", "verdict", "result", "state")
CLAIM_KEYS = ("claim_ceiling", "evidence_ceiling", "scientific_boundary")
STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "this", "that", "true", "false", "null",
    "data", "json", "janus", "version", "status", "schema", "artifact", "file", "path",
    "или", "для", "это", "как", "что", "при", "без", "его", "она", "они", "есть", "так", "из"
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def norm_token(token: str) -> str:
    return token.strip("._:/+-").casefold()


def tokenize(text: str, max_tokens: int = 120000) -> collections.Counter[str]:
    counter: collections.Counter[str] = collections.Counter()
    for i, raw in enumerate(TOKEN_RE.findall(text)):
        if i >= max_tokens:
            break
        tok = norm_token(raw)
        if len(tok) < 3 or tok in STOPWORDS or HEX64_RE.fullmatch(tok):
            continue
        counter[tok] += 1
    return counter


def iter_files(root: Path) -> Iterable[Path]:
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED_DIR_NAMES)
        base_path = Path(base)
        for name in sorted(files):
            p = base_path / name
            rel = p.relative_to(root).as_posix()
            if rel in EXCLUDED_EXACT_PATHS:
                continue
            if any(rel == pref.rstrip("/") or rel.startswith(pref) for pref in EXCLUDED_PREFIXES):
                continue
            yield p


def flatten_strings(obj: Any, prefix: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(obj, dict):
        for key in sorted(obj, key=lambda x: str(x)):
            kp = f"{prefix}.{key}" if prefix else str(key)
            yield from flatten_strings(obj[key], kp)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from flatten_strings(value, f"{prefix}[{i}]")
    elif isinstance(obj, (str, int, float, bool)):
        yield prefix, str(obj)


def first_value(obj: Any, keys: tuple[str, ...]) -> Any:
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if key not in obj:
            continue
        value = obj[key]
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            for lang in ("ru", "en"):
                if isinstance(value.get(lang), str):
                    return value[lang]
    return None


def collect_hashes(obj: Any) -> list[dict[str, str]]:
    if obj is None:
        return []
    found: dict[tuple[str, str], dict[str, str]] = {}
    for kp, value in flatten_strings(obj):
        for m in HEX64_RE.finditer(value):
            item = {"field": kp, "sha256_like": m.group(0).lower()}
            found[(item["field"], item["sha256_like"])] = item
    return [found[k] for k in sorted(found)]


def collect_relation_targets(obj: Any) -> list[dict[str, str]]:
    out: dict[tuple[str, str], dict[str, str]] = {}

    def visit(value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            for key in sorted(value, key=lambda x: str(x)):
                child = value[key]
                kp = f"{prefix}.{key}" if prefix else str(key)
                if str(key).casefold() in RELATION_KEYS:
                    vals: list[str] = []
                    if isinstance(child, str):
                        vals = [child]
                    elif isinstance(child, list):
                        vals = [str(x) for x in child if isinstance(x, (str, int, float))]
                    elif isinstance(child, dict):
                        vals = [str(x) for x in child.values() if isinstance(x, (str, int, float))]
                    for target in vals:
                        target = target.strip()
                        if target:
                            item = {"field": kp, "target": target}
                            out[(kp, target)] = item
                visit(child, kp)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                visit(child, f"{prefix}[{i}]")

    visit(obj)
    return [out[k] for k in sorted(out)]


def read_semantic_text(path: Path, data: bytes, limit: int) -> tuple[str | None, str | None]:
    if path.suffix.casefold() not in TEXT_EXTENSIONS:
        return None, None
    sample = data[:limit]
    try:
        return sample.decode("utf-8"), None
    except UnicodeDecodeError as exc:
        return sample.decode("utf-8", errors="replace"), f"UTF8_REPLACEMENT:{exc.start}"


def classify_lane(record: dict[str, Any]) -> str:
    if record["semantic_kind"] in {"BINARY_OR_UNSUPPORTED", "JSON_OVERSIZE_HASH_ONLY"}:
        return "RAW_INDEX_ONLY"
    if record["parse_error"]:
        return "OPEN_PARSE_ERROR"
    direct = bool(record["sha256_fields"]) and (
        record["artifact_id"] is not None
        or record["status"] is not None
        or any("provenance" in r["field"].casefold() for r in record["relations"])
    )
    if direct:
        return "EXACT_OR_PROVENANCE_CANDIDATE"
    if record["relations"] or len(record["bridge_tokens"]) >= 3:
        return "M2R_CONTEXT_CANDIDATE"
    return "OPEN_CONTEXT"


def receipt_eligibility(record: dict[str, Any]) -> dict[str, Any]:
    if record["semantic_kind"] != "JSON" or record["parse_error"]:
        return {"eligible_candidate": False, "reason": "NOT_PARSED_JSON"}
    text_keys = set(record.get("_top_level_keys", []))
    required = {
        "receipt_class", "finalized", "route_match", "route_terminal", "source_digest",
        "verifier_digest", "resource_cost", "gross_saved_work", "learning_cost_work", "receipt_hash"
    }
    missing = sorted(required - text_keys)
    if missing:
        return {"eligible_candidate": False, "reason": "MISSING_REQUIRED_FIELDS", "missing": missing}
    return {
        "eligible_candidate": True,
        "reason": "FIELD_SHAPE_PRESENT__FULL_SCHEMA_SEMANTIC_AND_HASH_VERIFICATION_STILL_REQUIRED"
    }


def build_record(root: Path, path: Path, semantic_limit: int) -> tuple[dict[str, Any], collections.Counter[str]]:
    rel = path.relative_to(root).as_posix()
    data = path.read_bytes()
    digest = sha256_bytes(data)
    semantic_text: str | None = None
    decode_note: str | None = None
    parsed: Any = None
    parse_error: str | None = None
    semantic_kind = "BINARY_OR_UNSUPPORTED"
    top_level_keys: list[str] = []

    if path.suffix.casefold() == ".json":
        if len(data) <= 10_000_000:
            semantic_kind = "JSON"
            try:
                semantic_text = data.decode("utf-8")
                parsed = json.loads(semantic_text)
                if isinstance(parsed, dict):
                    top_level_keys = sorted(str(k) for k in parsed)
            except Exception as exc:
                parse_error = f"{type(exc).__name__}:{exc}"
        else:
            semantic_kind = "JSON_OVERSIZE_HASH_ONLY"
    else:
        semantic_text, decode_note = read_semantic_text(path, data, semantic_limit)
        if semantic_text is not None:
            semantic_kind = "TEXT"
            parse_error = decode_note

    token_source = rel.replace("/", " ") + "\n"
    if parsed is not None:
        token_source += "\n".join(f"{kp} {value}" for kp, value in flatten_strings(parsed))
    elif semantic_text is not None:
        token_source += semantic_text
    tokens = tokenize(token_source)
    bridge_tokens = [t for t, _ in sorted(tokens.items(), key=lambda kv: (-kv[1], kv[0]))[:32]]

    relations = collect_relation_targets(parsed)
    hashes = collect_hashes(parsed)
    artifact_id = first_value(parsed, ARTIFACT_ID_KEYS)
    title = first_value(parsed, TITLE_KEYS)
    status = first_value(parsed, STATUS_KEYS)
    claim = first_value(parsed, CLAIM_KEYS)

    record: dict[str, Any] = {
        "path": rel,
        "sha256": digest,
        "bytes": len(data),
        "extension": path.suffix.casefold(),
        "semantic_kind": semantic_kind,
        "parse_error": parse_error,
        "artifact_id": str(artifact_id) if artifact_id is not None else None,
        "title": str(title) if title is not None else None,
        "status": str(status) if status is not None else None,
        "claim_ceiling_or_boundary": str(claim) if claim is not None else None,
        "sha256_fields": hashes[:64],
        "relations": relations[:128],
        "bridge_tokens": bridge_tokens,
        "_top_level_keys": top_level_keys,
    }
    record["trump_lane"] = classify_lane(record)
    record["slime_promotable_receipt_discovery"] = receipt_eligibility(record)
    return record, tokens


def resolve_edges(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    aliases: dict[str, str] = {}
    for r in records:
        aliases[r["path"]] = r["path"]
        aliases[Path(r["path"]).name] = r["path"]
        if r.get("artifact_id"):
            aliases[str(r["artifact_id"])] = r["path"]
    edges: list[dict[str, Any]] = []
    resolved_count = 0
    for r in records:
        for relation in r["relations"]:
            target = relation["target"]
            resolved = aliases.get(target)
            if resolved is not None:
                resolved_count += 1
            edges.append({
                "source": r["path"],
                "field": relation["field"],
                "target_raw": target,
                "target_resolved_path": resolved
            })
    edges.sort(key=lambda x: (x["source"], x["field"], x["target_raw"]))
    return edges, resolved_count


def build_associative_memory(records: list[dict[str, Any]], token_counters: dict[str, collections.Counter[str]], max_clusters: int) -> dict[str, Any]:
    doc_freq: collections.Counter[str] = collections.Counter()
    total_freq: collections.Counter[str] = collections.Counter()
    token_docs: dict[str, list[str]] = collections.defaultdict(list)
    for path in sorted(token_counters):
        counter = token_counters[path]
        for tok in counter:
            doc_freq[tok] += 1
            total_freq[tok] += counter[tok]
            if len(token_docs[tok]) < 12:
                token_docs[tok].append(path)
    n = max(1, len(records))
    scored = []
    for tok, df in doc_freq.items():
        if df < 2:
            continue
        rarity = max(0.0, 1.0 - (df / n))
        score = df * (0.35 + rarity)
        scored.append((score, tok, df, total_freq[tok]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    clusters = []
    for score, tok, df, tf in scored[:max_clusters]:
        clusters.append({
            "bridge_token": tok,
            "document_support": df,
            "total_occurrences": tf,
            "association_score": round(score, 6),
            "support_class": "STRONG" if df >= 3 else "MEDIUM",
            "example_paths": sorted(token_docs[tok])[:6]
        })
    eligible = [r["path"] for r in records if r["slime_promotable_receipt_discovery"].get("eligible_candidate")]
    return {
        "schema": "janus.eye.slime_associative_memory.v1",
        "status": "DERIVATIVE_NON_AUTHORITATIVE_ASSOCIATIVE_MEMORY",
        "binding": "EYE/bindings/EYE-SLIME-BINDING-v1.0.json",
        "corpus_documents": len(records),
        "cluster_count": len(clusters),
        "clusters": clusters,
        "promotable_receipt_candidates_by_field_shape": eligible,
        "promotable_route_confidence_updated": False,
        "law": "SLIME_ASSOCIATION != EVIDENCE; ordinary corpus ingestion never upgrades promotable route confidence."
    }


def build_routing_index(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = collections.Counter(r["trump_lane"] for r in records)
    examples: dict[str, list[str]] = collections.defaultdict(list)
    for r in records:
        if len(examples[r["trump_lane"]]) < 12:
            examples[r["trump_lane"]].append(r["path"])
    return {
        "schema": "janus.eye.trump_routing_index.v1",
        "status": "DERIVATIVE_ADVISORY_ROUTING_INDEX",
        "binding": "EYE/bindings/EYE-TRUMP-BINDING-v1.0.json",
        "lane_counts": dict(sorted(counts.items())),
        "lane_examples": {k: sorted(v) for k, v in sorted(examples.items())},
        "terminal_authority": "INDEPENDENT_VERIFIER_ONLY",
        "same_holdout_learning": False,
        "law": "TRUMP_ADMISSION != TRUTH"
    }


def corpus_digest(records: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    for r in records:
        h.update(r["path"].encode("utf-8"))
        h.update(b"\0")
        h.update(r["sha256"].encode("ascii"))
        h.update(b"\0")
        h.update(str(r["bytes"]).encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def write_json(path: Path, obj: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(data)
    return sha256_bytes(data)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--output-dir", default="EYE/generated")
    ap.add_argument("--semantic-byte-limit", type=int, default=2_000_000)
    ap.add_argument("--max-clusters", type=int, default=1000)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    outdir = (root / args.output_dir).resolve()
    records: list[dict[str, Any]] = []
    token_counters: dict[str, collections.Counter[str]] = {}
    hard_errors: list[dict[str, str]] = []

    for path in iter_files(root):
        try:
            record, counter = build_record(root, path, args.semantic_byte_limit)
            token_counters[record["path"]] = counter
            records.append(record)
        except Exception as exc:
            rel = path.relative_to(root).as_posix()
            hard_errors.append({"path": rel, "error": f"{type(exc).__name__}:{exc}"})

    records.sort(key=lambda r: r["path"])
    edges, resolved_edge_count = resolve_edges(records)
    root_digest = corpus_digest(records)
    by_kind = collections.Counter(r["semantic_kind"] for r in records)
    parse_errors = [r["path"] for r in records if r["parse_error"]]

    public_records = []
    for r in records:
        rr = dict(r)
        rr.pop("_top_level_keys", None)
        public_records.append(rr)

    index = {
        "schema": "janus.eye.registry_index.v1",
        "status": "DERIVATIVE_REBUILDABLE_INDEX",
        "source_git_commit": os.environ.get("GITHUB_SHA", "LOCAL_OR_UNKNOWN"),
        "corpus_root_digest_sha256": root_digest,
        "record_count": len(records),
        "relation_edge_count": len(edges),
        "resolved_relation_edge_count": resolved_edge_count,
        "records": public_records,
        "relations": edges
    }
    slime = build_associative_memory(records, token_counters, args.max_clusters)
    slime["corpus_root_digest_sha256"] = root_digest
    trump = build_routing_index(records)
    trump["corpus_root_digest_sha256"] = root_digest

    index_hash = write_json(outdir / "EYE-REGISTRY-INDEX.json", index)
    slime_hash = write_json(outdir / "EYE-SLIME-ASSOCIATIVE-MEMORY.json", slime)
    trump_hash = write_json(outdir / "EYE-TRUMP-ROUTING-INDEX.json", trump)

    receipt = {
        "schema": SCHEMA,
        "artifact_id": "JANUS-EYE-META-REGISTRY-TRAINING-RECEIPT",
        "status": "PASS" if not hard_errors else "PASS_WITH_INDEXING_ERRORS_PRESERVED",
        "definition_of_training": "deterministic whole-repository ingest/index/graph/association derivation; no foundation-model weight update",
        "source_git_commit": os.environ.get("GITHUB_SHA", "LOCAL_OR_UNKNOWN"),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "corpus_root_digest_sha256": root_digest,
        "source_exclusion_policy": {
            "excluded_prefixes": list(EXCLUDED_PREFIXES),
            "excluded_exact_paths": sorted(EXCLUDED_EXACT_PATHS),
            "law": "DERIVATIVE_MEMORY_EXPORT != FRESH_SOURCE_EVIDENCE"
        },
        "counts": {
            "files_indexed": len(records),
            "semantic_kind": dict(sorted(by_kind.items())),
            "parse_error_records": len(parse_errors),
            "hard_indexing_errors": len(hard_errors),
            "relation_edges": len(edges),
            "resolved_relation_edges": resolved_edge_count,
            "slime_association_clusters": slime["cluster_count"],
            "slime_promotable_receipt_candidates_by_field_shape": len(slime["promotable_receipt_candidates_by_field_shape"])
        },
        "parse_error_paths": parse_errors,
        "hard_errors": hard_errors,
        "outputs": {
            "EYE-REGISTRY-INDEX.json": index_hash,
            "EYE-SLIME-ASSOCIATIVE-MEMORY.json": slime_hash,
            "EYE-TRUMP-ROUTING-INDEX.json": trump_hash
        },
        "bindings": {
            "eye": "data/JANUS-EYE-CONTEXTUAL-SEMANTIC-RECOVERY-METHOD-2026-09-01-v1.0.json",
            "representation_contract": "data/JANUS-REPRESENTATION-CONTRACT-v1.0.json",
            "slime": "EYE/bindings/EYE-SLIME-BINDING-v1.0.json",
            "trump": "EYE/bindings/EYE-TRUMP-BINDING-v1.0.json"
        },
        "firewall": [
            "EYE != SHA256_REVERSAL",
            "SLIME_ASSOCIATION != EVIDENCE",
            "TRUMP_ADMISSION != TRUTH",
            "SEMANTIC_REGION != EXACT_PLAINTEXT",
            "UNKNOWN != NEGATIVE",
            "CONTROL_MUST_HAVE_POWER_TO_SAY_NO",
            "GENERATED_INDEX != SOURCE_AUTHORITY",
            "DERIVATIVE_MEMORY_EXPORT != FRESH_SOURCE_EVIDENCE"
        ]
    }
    receipt_hash = write_json(outdir / "EYE-TRAINING-RECEIPT.json", receipt)
    print(stable_dump({
        "status": receipt["status"],
        "corpus_root_digest_sha256": root_digest,
        "files_indexed": len(records),
        "relation_edges": len(edges),
        "resolved_relation_edges": resolved_edge_count,
        "slime_clusters": slime["cluster_count"],
        "receipt_sha256": receipt_hash
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())