#!/usr/bin/env python3
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
from typing import Any

SCHEMA = "janus.eye.r2.novel_bridge_miner.v1"
TEXT_EXTENSIONS = {
    ".json", ".md", ".markdown", ".txt", ".py", ".yml", ".yaml", ".toml",
    ".ini", ".cfg", ".csv", ".tsv", ".html", ".htm", ".js", ".ts", ".tsx",
    ".jsx", ".css", ".scss", ".sh", ".ps1", ".xml", ".jsonl", ".ndjson"
}
FORBIDDEN_PREFIXES = ("EYE/generated/", "EYE/r2/generated/", "assets/hrain-full-memory/")
FORBIDDEN_EXACT = {"assets/hrain-registry-index.json"}
TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9_.:+/-]{2,}", re.UNICODE)
DATE_VERSION_RE = re.compile(r"(?:^|[-_.])(?:20\d{2}(?:[-_.]\d{2}){0,2}|v?\d+(?:[._-]\d+){0,3})(?:$|[-_.])", re.I)

BOILERPLATE = {
    "the", "and", "for", "with", "from", "into", "this", "that", "these", "those", "then", "than",
    "only", "also", "are", "was", "were", "been", "being", "does", "did", "but", "can", "could", "would",
    "should", "may", "might", "must", "will", "shall", "one", "two", "three", "all", "any", "none", "each",
    "when", "while", "where", "which", "what", "who", "why", "how", "not", "without", "within", "before",
    "after", "through", "under", "over", "between", "same", "more", "less", "other", "another", "rather",
    "true", "false", "null", "name", "title", "date", "status", "schema", "version", "artifact", "artifact_id",
    "artifact_uuid", "created_at", "created_at_local", "path", "file", "files", "json", "yaml", "yml", "python",
    "main", "run", "runs", "github", "workflow", "workflows", "repository", "registry", "data", "janus",
    "string", "return", "result", "results", "value", "values", "object", "objects", "id", "commit", "sha",
    "sha256", "source", "sources", "current", "new", "old", "first", "later", "future", "used", "using",
    "или", "для", "это", "как", "что", "при", "без", "его", "она", "они", "есть", "так", "из", "до",
    "после", "перед", "только", "если", "уже", "ещё", "еще", "этот", "эта", "эти", "тот", "там", "тут"
}

DOMAIN_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("PALOMAR", ("palomar", "jpfm", "xe325")),
    ("MUSIC", ("alan-parsons", "alan_parsons", "robert-miles", "robert_miles", "music", "sirius", "eye-in-the-sky", "eye_in_the_sky", "9live-calltv", "enigma")),
    ("GENESIS", ("genesis",)),
    ("HRAIN_INAIHR", ("hrain", "inaihr", "demi_head", "demi-head")),
    ("EYE", ("eye/", "janus-eye-", "eye_")),
    ("TRUMP_SLIME", ("trump", "slime", "keymaster", "roosters", "finish-him", "finish_him")),
    ("AURA_ORACLE", ("aura", "oracle", "set-sun-moon", "set_sun_moon", "kem-")),
    ("LINEAR_A", ("linear-a", "linear_a", "sigla", "notti")),
    ("CONNECTION", ("connection", "hidden-pattern", "hidden_pattern")),
    ("FALLOUT", ("fallout", "f3dad", "fos-")),
    ("BEAR", ("janus-bear", "bear-spatial", "bear_scene")),
    ("COSMOS", ("janus-cosmos", "cosmos")),
    ("P_N_JUNCTION", ("p-n-junction", "p_n_junction", "p-vs-np", "p_vs_np")),
    ("SC0BY", ("scoby",)),
    ("OSIRIS_MYTH", ("osiris", "horus", "anubis", "sobek", "wedjat")),
    ("LOVE_EDEM", ("edem", "love-sky", "love_sky")),
    ("ENGINE_CALCIFER", ("calcifer", "rotating-gill", "rotating_gill", "janus-engine", "janus_engine")),
    ("LONGEVITY", ("longevity", "pv11", "odontoforge")),
    ("BLUEBOOK", ("bluebook",)),
]

OPERATORS: dict[str, dict[str, Any]] = {
    "REPRESENTATION_BRIDGE": {
        "signals": ("representation", "invariant", "bridge", "mapping", "translate", "translation", "resolver", "contextual", "semantic"),
        "description": "Preserve a bridge invariant in one representation so a target can be resolved in another representation.",
        "invariant": "relation-preserving transform across representations",
        "counterexample": "Two artifacts share bridge vocabulary but the mapped quantities are unrelated or the transform destroys the claimed invariant.",
        "falsifier": "Show that the proposed cross-domain mapping does not preserve the named invariant on held-out examples.",
        "verify_next": "Freeze the invariant, map positive/negative controls across both domains, and require MATCH/MISMATCH/OPEN from an independent verifier."
    },
    "FREEZE_COMPARE": {
        "signals": ("freeze", "frozen", "preregister", "preregistration", "holdout", "heldout", "baseline", "compare", "comparison", "difference", "delta"),
        "description": "Freeze a reference frame before observing a difference, then interpret the change against that frozen frame.",
        "invariant": "precommitted reference frame before comparison",
        "counterexample": "The threshold, metric, or comparator was changed after seeing the result.",
        "falsifier": "Replay from the frozen pre-result artifact and show the claimed comparison cannot be reproduced without post-hoc edits.",
        "verify_next": "Locate immutable pre-result state, rerun against held-out data, and preserve every null/failure."
    },
    "EXTERNAL_WITNESS": {
        "signals": ("external", "independent", "witness", "verify", "verifier", "control", "panel", "third-party", "outside"),
        "description": "A local candidate is not promoted until a separate witness can contradict it.",
        "invariant": "independent falsifiability of a local claim",
        "counterexample": "The supposed verifier is derived from the same evidence or cannot return a negative verdict.",
        "falsifier": "Demonstrate shared provenance or a verifier that cannot say NO.",
        "verify_next": "Construct an explicitly independent negative control and verify provenance separation."
    },
    "PRESERVE_FAILURE": {
        "signals": ("failure", "failed", "unknown", "open", "blocked", "mismatch", "null", "resource_limit", "timeout", "preserve", "retained"),
        "description": "Treat failure, OPEN, UNKNOWN, and resource limits as first-class states instead of rewriting them into success or negative evidence.",
        "invariant": "epistemic state identity under unsuccessful execution",
        "counterexample": "A timeout or missing observation is silently converted into target-negative evidence or dropped from history.",
        "falsifier": "Find a transition where the original unsuccessful state is not recoverable from provenance.",
        "verify_next": "Trace failure receipts end-to-end and confirm replay preserves the same state class."
    },
    "PROVENANCE_CHAIN": {
        "signals": ("provenance", "lineage", "parent", "receipt", "source", "commit", "digest", "hash", "sha256", "canonical"),
        "description": "Bind conclusions to a reconstructible chain of source identity, transformation, and receipt lineage.",
        "invariant": "source-to-result identity chain",
        "counterexample": "A result can no longer be tied to the exact source snapshot or transformation that produced it.",
        "falsifier": "Break one required source/parent/hash link and show the result still claims authority.",
        "verify_next": "Rebuild from the cited source snapshot and compare all required digests."
    },
    "PARTIAL_RECONSTRUCTION": {
        "signals": ("reconstruct", "reconstruction", "recover", "recovery", "missing", "partial", "sparse", "residual", "inverse", "fragment", "gap"),
        "description": "Infer a bounded missing structure from surviving partial evidence without claiming exact recovery unless independently verified.",
        "invariant": "constraints surviving loss or sparsity",
        "counterexample": "The reconstruction is driven primarily by priors or decorative completion rather than surviving constraints.",
        "falsifier": "Use a matched control with the same sparsity and show equally strong reconstructions arise without the target structure.",
        "verify_next": "Run injection-recovery or masked holdout tests with preregistered success criteria."
    },
    "MULTI_VIEW_MEDIATION": {
        "signals": ("mirror", "perspective", "multi-eye", "multieye", "view", "hemisphere", "bicameral", "mediate", "mediation", "observer"),
        "description": "Use multiple non-authoritative views to propose context while keeping a separate mediation and verification boundary.",
        "invariant": "shared object identity across differing views",
        "counterexample": "Multiple views are copies of the same upstream representation and are counted as independent evidence.",
        "falsifier": "Trace both views to one source or show view agreement persists on shuffled controls.",
        "verify_next": "Freeze view provenance, test disagreement cases, and keep bicameral agreement below proof authority."
    },
    "BOUNDED_CANDIDATE_SEARCH": {
        "signals": ("candidate", "rank", "ranking", "route", "routing", "selector", "gate", "shortlist", "keymaster", "admission", "fallback"),
        "description": "Generate and rank bounded candidates, route them through gates, and retain fallback/OPEN rather than forcing a choice.",
        "invariant": "candidate set plus admission constraints",
        "counterexample": "Ranking score is treated as truth or the fallback path is removed.",
        "falsifier": "Produce a high-ranked false candidate that bypasses independent verification.",
        "verify_next": "Adversarially inject attractive wrong candidates and require the authority gate to reject them."
    },
    "STATE_TRANSITION": {
        "signals": ("state", "transition", "before", "after", "change", "delta", "terminal", "open", "pass", "blocked", "match", "mismatch", "verdict"),
        "description": "Model knowledge as explicit transitions among states rather than as one final label.",
        "invariant": "typed transition semantics between epistemic states",
        "counterexample": "Different causes such as OPEN, BLOCKED, and NEGATIVE collapse into one terminal label.",
        "falsifier": "Find two semantically distinct transitions that the mechanism maps to the same state without provenance.",
        "verify_next": "Build a transition matrix and test reversible provenance for each edge."
    },
    "HIDDEN_STRUCTURE_DETECTION": {
        "signals": ("hidden", "latent", "pattern", "cluster", "anomaly", "signal", "dark", "structure", "morphology", "shape"),
        "description": "Detect latent structure by aggregating weak local clues while separating discovery from confirmation.",
        "invariant": "repeatable structure above matched-background expectation",
        "counterexample": "The same pattern rate appears in shuffled, null, or matched-control data.",
        "falsifier": "Run blind controls and show candidate structure is not enriched over null.",
        "verify_next": "Preregister a held-out detector and compare candidate prevalence to matched controls."
    },
    "CAUSAL_CONTROL": {
        "signals": ("causal", "control", "counterfactual", "intervention", "matched", "falsifier", "negative-control", "positive-control", "ablation"),
        "description": "Distinguish correlation from mechanism by requiring controls that can remove or invert the effect.",
        "invariant": "effect dependence on a manipulable or discriminating cause",
        "counterexample": "The effect survives removal of the purported causal component.",
        "falsifier": "Ablate the proposed cause or use matched controls and observe unchanged effect size.",
        "verify_next": "Run preregistered ablation/intervention with independent scoring."
    },
    "EXACT_VS_SEMANTIC_IDENTITY": {
        "signals": ("exact", "identity", "semantic", "byte", "bytes", "plaintext", "continuity", "hash", "sha256", "fingerprint"),
        "description": "Separate exact byte/object identity from semantic or continuity identity and use the correct verifier for each.",
        "invariant": "identity type is explicit and not silently upgraded",
        "counterexample": "Semantic similarity is reported as exact recovery, or exact digest match is treated as proof of semantic truth.",
        "falsifier": "Construct same-semantics/different-bytes and same-bytes/false-content controls.",
        "verify_next": "Run both exact-identity and semantic-equivalence controls under separate metrics."
    },
    "REPLAY_REPLICATION": {
        "signals": ("replay", "replicate", "replication", "reproducible", "reproduce", "rerun", "roundtrip", "fresh-checkout", "fresh_checkout"),
        "description": "Require a mechanism to survive a fresh replay rather than only the state in which it was created.",
        "invariant": "result stability under independent rerun from frozen inputs",
        "counterexample": "The result depends on hidden mutable state, cached data, or same-run leakage.",
        "falsifier": "Fresh checkout or clean-room replay fails while original run passes.",
        "verify_next": "Execute clean replay with hashes, environment receipt, and no same-holdout learning."
    },
    "COST_REGRET_ROUTING": {
        "signals": ("cost", "regret", "resource", "work", "saved", "budget", "timeout", "fallback", "route", "shadow"),
        "description": "Use measured cost/regret to route exploration while preserving an exact authority lane and fallback.",
        "invariant": "resource-aware routing without authority escalation",
        "counterexample": "A cheaper heuristic path becomes terminal authority merely because it saves work.",
        "falsifier": "Find a low-cost wrong route that changes the asserted verdict without exact verification.",
        "verify_next": "Measure counterfactual cost and error under shadow execution before promotion."
    },
    "SEALED_CONTEXT_RECOVERY": {
        "signals": ("sealed", "commitment", "destroyed", "plaintext", "oracle", "hash", "sha256", "context", "recover", "recovery"),
        "description": "Recover a bounded semantic region around an irreversible commitment using surviving external context, without pretending to invert the commitment.",
        "invariant": "surviving contextual constraints around an irreversible identity token",
        "counterexample": "A plausible reconstruction is called the original plaintext without an exact hash match.",
        "falsifier": "Generate multiple equally plausible candidates satisfying all context constraints but with different semantics.",
        "verify_next": "Freeze candidate generation, test exact candidates against the digest, otherwise retain SEMANTIC_REGION_SUPPORTED or OPEN."
    },
    "SPATIAL_REFERENCE_FRAME": {
        "signals": ("coordinate", "coordinates", "geometry", "spatial", "wcs", "reference-frame", "reference_frame", "locator", "position", "alignment"),
        "description": "Interpret observations only after anchoring them to an explicit spatial/reference coordinate system.",
        "invariant": "object relation under a declared reference frame",
        "counterexample": "Apparent alignment disappears when coordinate conventions or transformations are corrected.",
        "falsifier": "Reproject into an independent frame and show the claimed relation is not invariant.",
        "verify_next": "Freeze coordinate transforms and test matched off-target controls."
    },
    "CONTINUITY_CONTRAST": {
        "signals": ("continuity", "contrast", "reference", "difference", "change", "transition", "adjacent", "sequence", "context"),
        "description": "Make change interpretable by preserving continuity and a reference frame while measuring contrast.",
        "invariant": "continuity plus controlled difference across a sequence",
        "counterexample": "The two compared states lack a shared reference or continuity relation.",
        "falsifier": "Break the continuity/control link and show the same interpretation still appears.",
        "verify_next": "Test adjacent and non-adjacent controls under a frozen representation contract."
    },
}

OPERATOR_SIGNAL_SET = {s for cfg in OPERATORS.values() for s in cfg["signals"]}


def norm(s: str) -> str:
    return s.casefold().replace("\\", "/")


def domain_for(path: str, artifact_id: str | None, title: str | None) -> str:
    hay = norm(" ".join(x for x in (path, artifact_id or "", title or "") if x))
    for name, keys in DOMAIN_RULES:
        if any(k in hay for k in keys):
            return name
    return "OTHER"


def lineage_key(record: dict[str, Any]) -> str:
    raw = str(record.get("artifact_id") or Path(record["path"]).stem)
    x = raw.casefold()
    x = re.sub(r"20\d{2}[-_.]\d{2}[-_.]\d{2}", "", x)
    x = re.sub(r"(?:[-_.])v?\d+(?:[._-]\d+){0,3}$", "", x)
    x = re.sub(r"[-_.]+", "-", x).strip("-")
    return x or record["path"].casefold()


def safe_text(root: Path, rel: str, max_bytes: int) -> str:
    if rel in FORBIDDEN_EXACT or any(rel.startswith(p) for p in FORBIDDEN_PREFIXES):
        return ""
    p = root / rel
    if not p.is_file() or p.suffix.casefold() not in TEXT_EXTENSIONS:
        return ""
    try:
        return p.read_bytes()[:max_bytes].decode("utf-8", errors="replace").casefold()
    except OSError:
        return ""


def subject_tokens(text: str, rel: str, limit: int = 200) -> set[str]:
    counter: collections.Counter[str] = collections.Counter()
    src = f"{rel.replace('/', ' ')}\n{text}"
    for raw in TOKEN_RE.findall(src):
        t = raw.strip("._:+/-").casefold()
        if len(t) < 4 or t in BOILERPLATE or t in OPERATOR_SIGNAL_SET:
            continue
        if re.fullmatch(r"[0-9a-f]{32,}", t):
            continue
        if t.isdigit():
            continue
        counter[t] += 1
    return {t for t, _ in counter.most_common(limit)}


def operator_score(text: str, rel: str, cfg: dict[str, Any]) -> tuple[int, list[str]]:
    hay = f" {rel.casefold()} {text} "
    hits: list[str] = []
    for signal in cfg["signals"]:
        s = signal.casefold()
        variants = {s, s.replace("-", "_"), s.replace("_", "-")}
        if any(v in hay for v in variants):
            hits.append(signal)
    return len(set(hits)), sorted(set(hits))


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def stable_hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def explicit_edges(index: dict[str, Any]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for e in index.get("relations", []):
        a = e.get("source")
        b = e.get("target_resolved_path")
        if a and b:
            out.add(tuple(sorted((a, b))))
    return out


def select_independent_support(docs: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d in sorted(docs, key=lambda x: (-x["operator_score"], x["path"])):
        if d["lineage"] in seen:
            continue
        seen.add(d["lineage"])
        chosen.append(d)
        if len(chosen) >= limit:
            break
    return chosen


def confidence(score: float, explicit: bool, min_lineages: int, lexical_distance: float) -> str:
    if explicit:
        return "KNOWN_OR_EXPLICIT_LINK__NOT_NOVEL"
    if min_lineages >= 3 and lexical_distance >= 0.75 and score >= 70:
        return "STRONG_CANDIDATE__VERIFY_REQUIRED"
    if min_lineages >= 2 and lexical_distance >= 0.55 and score >= 50:
        return "MEDIUM_CANDIDATE__VERIFY_REQUIRED"
    return "WEAK_CANDIDATE__OPEN"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--index", default="EYE/generated/EYE-REGISTRY-INDEX.json")
    ap.add_argument("--output-dir", default="EYE/r2/generated")
    ap.add_argument("--max-read-bytes", type=int, default=800000)
    ap.add_argument("--min-operator-signals", type=int, default=2)
    ap.add_argument("--min-lineages-per-domain", type=int, default=2)
    ap.add_argument("--top-pairs", type=int, default=100)
    ap.add_argument("--top-triples", type=int, default=40)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    index_path = root / args.index
    outdir = root / args.output_dir
    index = json.loads(index_path.read_text(encoding="utf-8"))
    forbidden_seen = [r["path"] for r in index.get("records", []) if r["path"] in FORBIDDEN_EXACT or any(r["path"].startswith(p) for p in FORBIDDEN_PREFIXES)]
    if forbidden_seen:
        raise SystemExit("FORBIDDEN_DERIVATIVE_MEMORY_PRESENT_IN_INPUT_INDEX:" + ",".join(forbidden_seen[:10]))

    edge_set = explicit_edges(index)
    docs: list[dict[str, Any]] = []
    parse_skips = 0
    for r in index.get("records", []):
        rel = r["path"]
        if r.get("semantic_kind") not in {"JSON", "TEXT"} or r.get("parse_error"):
            parse_skips += 1
            continue
        text = safe_text(root, rel, args.max_read_bytes)
        if not text:
            continue
        domain = domain_for(rel, r.get("artifact_id"), r.get("title"))
        if domain == "OTHER":
            continue
        base = {
            "path": rel,
            "sha256": r.get("sha256"),
            "artifact_id": r.get("artifact_id"),
            "title": r.get("title"),
            "status": r.get("status"),
            "domain": domain,
            "lineage": lineage_key(r),
            "subject_tokens": subject_tokens(text, rel),
        }
        for op_name, cfg in OPERATORS.items():
            sc, hits = operator_score(text, rel, cfg)
            if sc >= args.min_operator_signals:
                d = dict(base)
                d["operator"] = op_name
                d["operator_score"] = sc
                d["operator_hits"] = hits
                docs.append(d)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for d in docs:
        grouped[(d["operator"], d["domain"])].append(d)

    eligible: dict[tuple[str, str], list[dict[str, Any]]] = {}
    operator_domains: dict[str, list[str]] = collections.defaultdict(list)
    for key, arr in grouped.items():
        support = select_independent_support(arr)
        if len(support) >= args.min_lineages_per_domain:
            eligible[key] = support
            operator_domains[key[0]].append(key[1])

    pairs: list[dict[str, Any]] = []
    for op_name, domains in sorted(operator_domains.items()):
        unique_domains = sorted(set(domains))
        domain_rarity_bonus = max(0.0, 18.0 - 1.4 * len(unique_domains))
        cfg = OPERATORS[op_name]
        for da, db in itertools.combinations(unique_domains, 2):
            a = eligible[(op_name, da)]
            b = eligible[(op_name, db)]
            ta = set().union(*(d["subject_tokens"] for d in a[:4]))
            tb = set().union(*(d["subject_tokens"] for d in b[:4]))
            overlap = jaccard(ta, tb)
            lexical_distance = 1.0 - overlap
            explicit = any(tuple(sorted((x["path"], y["path"]))) in edge_set for x in a for y in b)
            strength = sum(d["operator_score"] for d in a[:3] + b[:3]) / max(1, len(a[:3] + b[:3]))
            min_lineages = min(len(a), len(b))
            support_bonus = min(24.0, 4.0 * (len(a) + len(b)))
            score = 20.0 + support_bonus + 24.0 * lexical_distance + 2.2 * strength + domain_rarity_bonus
            if explicit:
                score -= 28.0
            candidate = {
                "candidate_id": "EYE-R2-PAIR-" + stable_hash([op_name, da, db])[:16],
                "candidate_type": "CROSS_DOMAIN_OPERATOR_BRIDGE",
                "operator": op_name,
                "formula": f"{da} --[{op_name}]--> {db}",
                "domains": [da, db],
                "why": cfg["description"],
                "representation_invariant": cfg["invariant"],
                "score": round(score, 6),
                "confidence_class": confidence(score, explicit, min_lineages, lexical_distance),
                "lexical_overlap": round(overlap, 6),
                "lexical_distance": round(lexical_distance, 6),
                "already_explicit_relation_detected": explicit,
                "independent_lineage_support": {da: len(a), db: len(b)},
                "provenance": {
                    da: [{k: d[k] for k in ("path", "sha256", "artifact_id", "lineage", "operator_score", "operator_hits")} for d in a],
                    db: [{k: d[k] for k in ("path", "sha256", "artifact_id", "lineage", "operator_score", "operator_hits")} for d in b],
                },
                "counterexample": cfg["counterexample"],
                "falsifier": cfg["falsifier"],
                "verify_next": cfg["verify_next"],
                "authority": "CANDIDATE_ONLY__INDEPENDENT_VERIFY_REQUIRED"
            }
            pairs.append(candidate)

    pairs.sort(key=lambda c: (-c["score"], c["candidate_id"]))
    novel_pairs = [p for p in pairs if not p["already_explicit_relation_detected"]][:args.top_pairs]

    triples: list[dict[str, Any]] = []
    for op_name, domains in sorted(operator_domains.items()):
        cfg = OPERATORS[op_name]
        unique_domains = sorted(set(domains))
        if len(unique_domains) < 3:
            continue
        for tri in itertools.combinations(unique_domains, 3):
            supports = [eligible[(op_name, d)] for d in tri]
            token_sets = [set().union(*(x["subject_tokens"] for x in arr[:4])) for arr in supports]
            pair_distances = [1.0 - jaccard(token_sets[i], token_sets[j]) for i, j in ((0,1),(0,2),(1,2))]
            lexical_distance = sum(pair_distances) / 3.0
            explicit_pairs = 0
            for i, j in ((0,1),(0,2),(1,2)):
                if any(tuple(sorted((x["path"], y["path"]))) in edge_set for x in supports[i] for y in supports[j]):
                    explicit_pairs += 1
            min_lineages = min(len(x) for x in supports)
            strength_vals = [d["operator_score"] for arr in supports for d in arr[:2]]
            strength = sum(strength_vals) / max(1, len(strength_vals))
            score = 28.0 + 5.0 * sum(min(3, len(x)) for x in supports) + 28.0 * lexical_distance + 2.0 * strength - 15.0 * explicit_pairs
            triples.append({
                "candidate_id": "EYE-R2-TRIPLE-" + stable_hash([op_name, *tri])[:16],
                "candidate_type": "THREE_DOMAIN_OPERATOR_BRIDGE",
                "operator": op_name,
                "formula": f"{tri[0]} <--> {tri[1]} <--> {tri[2]} via {op_name}",
                "domains": list(tri),
                "why": cfg["description"],
                "representation_invariant": cfg["invariant"],
                "score": round(score, 6),
                "confidence_class": confidence(score, explicit_pairs > 0, min_lineages, lexical_distance),
                "lexical_distance": round(lexical_distance, 6),
                "explicit_pair_count": explicit_pairs,
                "independent_lineage_support": {d: len(eligible[(op_name, d)]) for d in tri},
                "provenance": {d: [{k: x[k] for k in ("path", "sha256", "artifact_id", "lineage", "operator_score", "operator_hits")} for x in eligible[(op_name, d)]] for d in tri},
                "counterexample": cfg["counterexample"],
                "falsifier": cfg["falsifier"],
                "verify_next": cfg["verify_next"],
                "authority": "CANDIDATE_ONLY__INDEPENDENT_VERIFY_REQUIRED"
            })
    triples.sort(key=lambda c: (-c["score"], c["candidate_id"]))
    novel_triples = [t for t in triples if t["explicit_pair_count"] == 0][:args.top_triples]

    target = ["PALOMAR", "MUSIC", "GENESIS"]
    target_diag: dict[str, Any] = {"domains": target, "status": "NOT_FOUND_UNDER_FROZEN_R2_RULES", "matching_operators": []}
    for t in triples:
        if set(t["domains"]) == set(target):
            target_diag["matching_operators"].append({
                "operator": t["operator"],
                "score": t["score"],
                "confidence_class": t["confidence_class"],
                "explicit_pair_count": t["explicit_pair_count"],
                "candidate_id": t["candidate_id"]
            })
    if target_diag["matching_operators"]:
        target_diag["status"] = "CANDIDATE_FOUND__VERIFY_REQUIRED"
        target_diag["matching_operators"].sort(key=lambda x: (-x["score"], x["operator"]))

    backbone = []
    for op_name, domains in sorted(operator_domains.items(), key=lambda kv: (-len(set(kv[1])), kv[0])):
        per_domain = {d: len(eligible[(op_name, d)]) for d in sorted(set(domains))}
        backbone.append({
            "operator": op_name,
            "domain_count": len(per_domain),
            "domains": per_domain,
            "interpretation": OPERATORS[op_name]["description"],
            "representation_invariant": OPERATORS[op_name]["invariant"],
            "status": "REPEATED_OPERATOR_PATTERN__NOT_DISCOVERY"
        })

    candidates_obj = {
        "schema": SCHEMA,
        "artifact_id": "JANUS-EYE-R2-NOVEL-BRIDGE-CANDIDATES",
        "status": "CANDIDATE_MINING_COMPLETE__VERIFY_REQUIRED",
        "source_git_commit": os.environ.get("GITHUB_SHA", "LOCAL_OR_UNKNOWN"),
        "source_index": args.index,
        "source_index_corpus_digest_sha256": index.get("corpus_root_digest_sha256"),
        "method": {
            "raw_word_frequency_used_as_terminal_signal": False,
            "boilerplate_removed": True,
            "minimum_operator_signals_per_document": args.min_operator_signals,
            "minimum_unique_lineages_per_domain": args.min_lineages_per_domain,
            "cross_domain_only": True,
            "same_lineage_repetition_counts_as_independent": False,
            "explicit_relation_penalty": True,
            "low_subject_vocabulary_overlap_rewarded": True,
            "named_target_bonus": False
        },
        "target_hunt": target_diag,
        "top_pair_candidates": novel_pairs,
        "top_triple_candidates": novel_triples,
        "authority_firewall": [
            "ASSOCIATION != EVIDENCE",
            "BRIDGE != PROOF",
            "R2_SCORE != TRUTH",
            "BICAMERAL_AGREEMENT != INDEPENDENT_REPLICATION",
            "UNKNOWN != NEGATIVE",
            "VERIFY_DECIDES"
        ]
    }
    backbone_obj = {
        "schema": "janus.eye.r2.operator_backbone.v1",
        "artifact_id": "JANUS-EYE-R2-OPERATOR-BACKBONE",
        "status": "DESCRIPTIVE_OPERATOR_MAP__NOT_DISCOVERY",
        "source_index_corpus_digest_sha256": index.get("corpus_root_digest_sha256"),
        "operators": backbone,
        "hypothesis_status": "CANDIDATE",
        "hypothesis": "The registry contains recurring epistemic transition operators spanning otherwise distant project domains.",
        "falsifier": "After controlling for boilerplate, shared templates, and lineage duplication, cross-domain operator enrichment disappears on held-out/manual verification."
    }

    outdir.mkdir(parents=True, exist_ok=True)
    cand_path = outdir / "EYE-R2-NOVEL-BRIDGE-CANDIDATES.json"
    back_path = outdir / "EYE-R2-OPERATOR-BACKBONE.json"
    cand_path.write_text(json.dumps(candidates_obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    back_path.write_text(json.dumps(backbone_obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    receipt = {
        "schema": "janus.eye.r2.receipt.v1",
        "artifact_id": "JANUS-EYE-R2-RECEIPT",
        "status": "PASS" if novel_pairs else "OPEN_NO_NOVEL_PAIR_CANDIDATES",
        "source_git_commit": os.environ.get("GITHUB_SHA", "LOCAL_OR_UNKNOWN"),
        "source_index_corpus_digest_sha256": index.get("corpus_root_digest_sha256"),
        "counts": {
            "input_records": len(index.get("records", [])),
            "semantic_records_skipped_due_to_kind_or_parse": parse_skips,
            "operator_document_supports": len(docs),
            "eligible_operator_domain_cells": len(eligible),
            "all_pair_candidates_before_explicit_filter": len(pairs),
            "novel_pair_candidates_emitted": len(novel_pairs),
            "all_triple_candidates_before_explicit_filter": len(triples),
            "novel_triple_candidates_emitted": len(novel_triples)
        },
        "top_pair_ids": [x["candidate_id"] for x in novel_pairs[:10]],
        "top_triple_ids": [x["candidate_id"] for x in novel_triples[:10]],
        "target_hunt": target_diag,
        "outputs": {
            "EYE-R2-NOVEL-BRIDGE-CANDIDATES.json": hashlib.sha256(cand_path.read_bytes()).hexdigest(),
            "EYE-R2-OPERATOR-BACKBONE.json": hashlib.sha256(back_path.read_bytes()).hexdigest()
        },
        "gates": {
            "derivative_memory_input_absent": True,
            "minimum_two_unique_lineages_per_domain": True,
            "named_target_not_boosted": True,
            "authority_remains_candidate_only": True,
            "independent_verify_required": True
        },
        "seal": "THE MINER MAY POINT AT A STAR. IT MAY NOT DECLARE THE CONSTELLATION REAL."
    }
    receipt_path = outdir / "EYE-R2-RECEIPT.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": receipt["status"],
        "novel_pairs": len(novel_pairs),
        "novel_triples": len(novel_triples),
        "target_hunt": target_diag["status"],
        "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
