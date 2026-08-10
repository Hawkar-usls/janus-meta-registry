#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

JAMES_PHYSICAL_LABEL = "Vault112PodTermDad"
JAMES_SEED_LABELS = {
    "Vault112PodTermDad", "MQ04StressNoteDad", "MQ04StatusNoteDad", "MQ04Doc",
    "MQ04DocRef", "MQ04DadPodScript", "MQ04PlayerContainerScript", "MQ04Script",
    "BettyScript", "MQ04VersionControlCurrent", "MQ04PlayerPodScript",
}
STORAGE_TERMS = {
    "memory", "mem chip", "memory chip", "memchip", "neural", "engram",
    "persist", "archive", "backup", "snapshot", "storage", "store", "save",
    "restore", "reload", "cache", "buffer", "slot", "sync", "synchron",
    "visiontron", "think machine", "transfer", "serialize", "copy", "write",
}

REQ_SEED = {
    "seed_fixed_formid", "seed_label", "record_file", "record_signature", "record_formid",
    "element_path", "element_name", "element_value", "linked_file", "linked_signature",
    "linked_formid", "linked_editorid", "linked_name",
}
REQ_REV = {
    "seed_fixed_formid", "seed_label", "seed_file", "seed_signature", "referencing_file",
    "referencing_signature", "referencing_formid", "referencing_editorid",
    "referencing_name", "referencing_full_path",
}
REQ_PLACED = {
    "logical_ref_formid", "winning_file", "base_fixed_formid", "base_seed_label",
    "base_editorid", "base_name", "location_key", "cell_editorid", "position_x",
    "position_y", "position_z", "initially_disabled", "enable_parent_raw", "owner_raw",
    "ref_script_raw", "base_script_raw", "full_path",
}
REQ_VAULT = {
    "logical_ref_formid", "winning_file", "base_signature", "base_fixed_formid",
    "base_editorid", "base_name", "position_x", "position_y", "position_z",
    "initially_disabled", "enable_parent_raw", "owner_raw", "ref_script_raw",
    "base_script_raw", "storage_identity_term", "full_path",
}
REQ_CAND = {
    "record_file", "record_signature", "record_formid", "root_fixed_formid",
    "record_editorid", "record_name", "matched_term", "element_path", "element_value",
    "is_seed_record", "seed_label", "record_full_path",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_tsv(path: Path) -> tuple[list[dict[str, str]], set[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = list(reader)
        return rows, set(reader.fieldnames or [])


def norm(s: str) -> str:
    return " ".join(str(s or "").lower().split())


def has_storage(text: str) -> bool:
    t = norm(text)
    return any(x in t for x in STORAGE_TERMS)


def parse_bool(v: str, field: str) -> bool:
    x = norm(v)
    if x == "true":
        return True
    if x == "false":
        return False
    raise ValueError(f"{field} must be true/false, got {v!r}")


def parse_float(v: str, field: str) -> float:
    try:
        x = float(str(v).strip())
    except Exception as exc:
        raise ValueError(f"{field} must be numeric, got {v!r}") from exc
    if not math.isfinite(x):
        raise ValueError(f"{field} must be finite")
    return x


def xyz(row: dict[str, str]) -> tuple[float, float, float]:
    rid = row.get("logical_ref_formid", "?")
    return (
        parse_float(row.get("position_x", ""), f"{rid}.position_x"),
        parse_float(row.get("position_y", ""), f"{rid}.position_y"),
        parse_float(row.get("position_z", ""), f"{rid}.position_z"),
    )


def dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def record_key(file: str, sig: str, formid: str) -> str:
    return "|".join([file.strip(), sig.strip().upper(), formid.strip().upper()])


def audit(seed_rows: list[dict[str, str]], reverse_rows: list[dict[str, str]],
          placed_rows: list[dict[str, str]], vault_rows: list[dict[str, str]],
          candidate_rows: list[dict[str, str]]) -> dict:
    # Validate seed labels and collect direct linked-form candidates.
    direct_linked = []
    seed_link_counts = Counter()
    for row in seed_rows:
        label = row.get("seed_label", "").strip()
        if not label:
            raise ValueError("seed leaf missing seed_label")
        if label not in JAMES_SEED_LABELS:
            raise ValueError(f"unexpected seed label: {label}")
        linked_id = row.get("linked_formid", "").strip().upper()
        if linked_id:
            seed_link_counts[label] += 1
            linked_text = " ".join([row.get("linked_editorid", ""), row.get("linked_name", ""), row.get("element_value", "")])
            if has_storage(linked_text):
                direct_linked.append({
                    "seed_label": label,
                    "linked_formid": linked_id,
                    "linked_signature": row.get("linked_signature", ""),
                    "linked_editorid": row.get("linked_editorid", ""),
                    "linked_name": row.get("linked_name", ""),
                    "element_path": row.get("element_path", ""),
                    "classification": "DIRECT_SEED_LINK_STORAGE_CANDIDATE",
                    "james_session_persistence_proven": False,
                })

    # Reverse graph from exact seeds.
    reverse_keys: dict[str, set[str]] = defaultdict(set)
    reverse_counts = Counter()
    for row in reverse_rows:
        label = row.get("seed_label", "").strip()
        if label not in JAMES_SEED_LABELS:
            raise ValueError(f"unexpected reverse seed label: {label}")
        reverse_counts[label] += 1
        key = record_key(row.get("referencing_file", ""), row.get("referencing_signature", ""), row.get("referencing_formid", ""))
        reverse_keys[key].add(label)

    # Candidate records grouped by exact record key.
    candidate_groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in candidate_rows:
        if not row.get("record_formid", "").strip():
            raise ValueError("candidate row missing record_formid")
        term = norm(row.get("matched_term", ""))
        if not term:
            raise ValueError("candidate row missing matched_term")
        candidate_groups[record_key(row.get("record_file", ""), row.get("record_signature", ""), row.get("record_formid", ""))].append(row)

    graph_candidates = []
    for key, rows in candidate_groups.items():
        exemplar = rows[0]
        terms = sorted({norm(x.get("matched_term", "")) for x in rows})
        linked_seeds = sorted(reverse_keys.get(key, set()))
        is_seed = norm(exemplar.get("is_seed_record", "")) == "true"
        seed_label = exemplar.get("seed_label", "").strip()
        source_bound = bool(linked_seeds) or (is_seed and seed_label in JAMES_SEED_LABELS)
        item = {
            "record_key": key,
            "record_file": exemplar.get("record_file", ""),
            "record_signature": exemplar.get("record_signature", ""),
            "record_formid": exemplar.get("record_formid", ""),
            "record_editorid": exemplar.get("record_editorid", ""),
            "record_name": exemplar.get("record_name", ""),
            "matched_terms": terms,
            "reverse_links_to_seeds": linked_seeds,
            "source_bound_candidate": source_bound,
            "classification": "SOURCE_BOUND_STORAGE_CANDIDATE" if source_bound else "UNBOUND_STORAGE_CANDIDATE",
            "james_session_persistence_proven": False,
        }
        if source_bound:
            graph_candidates.append(item)

    # Exact placed source instances.
    placed_ids = set()
    monitor_rows = []
    for row in placed_rows:
        rid = row.get("logical_ref_formid", "").strip().upper()
        if not rid:
            raise ValueError("placed seed row missing logical_ref_formid")
        if rid in placed_ids:
            raise ValueError(f"duplicate placed logical RefID: {rid}")
        placed_ids.add(rid)
        xyz(row)
        parse_bool(row.get("initially_disabled", ""), f"{rid}.initially_disabled")
        if row.get("base_seed_label", "") == JAMES_PHYSICAL_LABEL:
            monitor_rows.append(row)

    # Vault112a local physical neighborhood around each exact James monitor placement.
    local_candidates = []
    vault_ids = set()
    for row in vault_rows:
        rid = row.get("logical_ref_formid", "").strip().upper()
        if not rid:
            raise ValueError("Vault112a row missing logical_ref_formid")
        if rid in vault_ids:
            raise ValueError(f"duplicate Vault112a logical RefID: {rid}")
        vault_ids.add(rid)
        p = xyz(row)
        disabled = parse_bool(row.get("initially_disabled", ""), f"{rid}.initially_disabled")
        identity_storage = bool(row.get("storage_identity_term", "").strip()) or has_storage(
            " ".join([row.get("base_editorid", ""), row.get("base_name", ""), row.get("ref_script_raw", ""), row.get("base_script_raw", "")])
        )
        dependency = bool(row.get("enable_parent_raw", "").strip() or row.get("ref_script_raw", "").strip() or row.get("base_script_raw", "").strip() or disabled)
        if not monitor_rows:
            continue
        distances = [dist(p, xyz(m)) for m in monitor_rows]
        nearest = min(distances)
        if nearest <= 1024.0 and rid not in {m.get("logical_ref_formid", "").strip().upper() for m in monitor_rows}:
            local_candidates.append({
                "logical_ref_formid": rid,
                "base_signature": row.get("base_signature", ""),
                "base_fixed_formid": row.get("base_fixed_formid", ""),
                "base_editorid": row.get("base_editorid", ""),
                "base_name": row.get("base_name", ""),
                "distance_to_nearest_james_monitor": nearest,
                "within_128": nearest <= 128.0,
                "within_512": nearest <= 512.0,
                "within_1024": True,
                "storage_identity_candidate": identity_storage,
                "direct_dependency_marker": dependency,
                "classification": "POD_LOCAL_STORAGE_OR_DEPENDENCY_CANDIDATE" if (identity_storage or dependency) else "POD_LOCAL_ORDINARY_REFR",
                "james_session_persistence_proven": False,
            })

    interesting_local = [x for x in local_candidates if x["classification"] == "POD_LOCAL_STORAGE_OR_DEPENDENCY_CANDIDATE"]

    # A candidate becomes high-priority if it is directly linked from a James seed,
    # a storage-term record reverse-references a James seed, or a pod-local object
    # within 512 units carries storage identity plus a direct lifecycle dependency.
    local_high = [x for x in interesting_local if x["within_512"] and x["storage_identity_candidate"] and x["direct_dependency_marker"]]
    high_priority_count = len(direct_linked) + len(graph_candidates) + len(local_high)

    return {
        "schema": "janus.fo3.james_session_storage_association_audit.v1_7",
        "seed_leaf_count": len(seed_rows),
        "seed_direct_link_counts": dict(seed_link_counts),
        "seed_reverse_reference_counts": dict(reverse_counts),
        "placed_seed_ref_count": len(placed_rows),
        "james_monitor_placed_ref_count": len(monitor_rows),
        "vault112a_ref_count": len(vault_rows),
        "storage_candidate_hit_count": len(candidate_rows),
        "storage_candidate_record_count": len(candidate_groups),
        "direct_seed_link_storage_candidate_count": len(direct_linked),
        "direct_seed_link_storage_candidates": direct_linked,
        "source_bound_storage_candidate_count": len(graph_candidates),
        "source_bound_storage_candidates": graph_candidates,
        "pod_local_within_1024_count": len(local_candidates),
        "pod_local_interesting_count": len(interesting_local),
        "pod_local_interesting_candidates": interesting_local,
        "pod_local_high_priority_count": len(local_high),
        "pod_local_high_priority_candidates": local_high,
        "combined_high_priority_candidate_count": high_priority_count,
        "admission": {
            "james_physical_monitor_placed_instance_bound": bool(monitor_rows),
            "james_session_to_persistent_storage": "NOT_ESTABLISHED_BY_GRAPH_OR_PROXIMITY_ALONE",
            "james_session_autopersistence": "NOT_ESTABLISHED",
            "james_specific_removable_carrier": "NOT_ESTABLISHED",
            "carrier_rewritable": "NOT_ESTABLISHED",
            "asset_level_executable_save_james": "BLOCKED_PENDING_PRIMARY_STORAGE_OR_PAYLOAD_BINDING",
        },
        "claim_ceiling": {
            "DIRECT_LINK_EQUALS_STORAGE_SEMANTICS": False,
            "REVERSE_REFERENCE_EQUALS_PERSISTENCE_DIRECTION": False,
            "POD_PROXIMITY_EQUALS_SESSION_STORAGE": False,
            "STORAGE_KEYWORD_EQUALS_MEMORY_PAYLOAD": False,
            "SHARED_BACKEND_EQUALS_SHARED_MEMORY_BUFFER": False,
            "AUTOMATIC_PERSISTENCE_PLAUSIBILITY_EQUALS_PER_SESSION_AUTOPERSISTENCE": False,
            "HIGH_PRIORITY_CANDIDATE_EQUALS_PASS": False,
            "manual_primary_record_review_required": True,
        },
    }


def check_columns(actual: set[str], required: set[str], name: str) -> None:
    missing = sorted(required - actual)
    if missing:
        raise SystemExit(f"missing {name} columns: {missing}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed-leaves", required=True, type=Path)
    ap.add_argument("--reverse", required=True, type=Path)
    ap.add_argument("--placed", required=True, type=Path)
    ap.add_argument("--vault112a", required=True, type=Path)
    ap.add_argument("--candidates", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    seed_rows, seed_cols = read_tsv(args.seed_leaves)
    rev_rows, rev_cols = read_tsv(args.reverse)
    placed_rows, placed_cols = read_tsv(args.placed)
    vault_rows, vault_cols = read_tsv(args.vault112a)
    cand_rows, cand_cols = read_tsv(args.candidates)
    check_columns(seed_cols, REQ_SEED, "seed-leaf")
    check_columns(rev_cols, REQ_REV, "reverse")
    check_columns(placed_cols, REQ_PLACED, "placed")
    check_columns(vault_cols, REQ_VAULT, "Vault112a")
    check_columns(cand_cols, REQ_CAND, "candidate")

    result = audit(seed_rows, rev_rows, placed_rows, vault_rows, cand_rows)
    result["source_binding"] = {
        "seed_leaves_sha256": sha256(args.seed_leaves),
        "reverse_refs_sha256": sha256(args.reverse),
        "placed_seed_refs_sha256": sha256(args.placed),
        "vault112a_refr_inventory_sha256": sha256(args.vault112a),
        "storage_candidates_sha256": sha256(args.candidates),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
