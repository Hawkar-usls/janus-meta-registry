#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

REQUIRED_INDEX_COLUMNS = {
    "info_logical_formid", "winning_file", "topic_logical_formid", "topic_editorid",
    "topic_name", "speaker_raw", "speaker_formid", "speaker_editorid",
    "previous_topic_raw", "previous_info_raw", "full_path",
}
REQUIRED_LEAF_COLUMNS = {
    "info_logical_formid", "topic_logical_formid", "section", "element_path",
    "element_name", "element_value", "linked_file", "linked_signature",
    "linked_formid", "linked_editorid",
}
SECTIONS = {"RESPONSES", "CONDITIONS", "BEGIN_SCRIPT", "END_SCRIPT"}

DISCLOSURE_TERMS = {"daddoginfo", "dadinfo", "brauninfo"}
RESET_TERMS = {"npcreset", "resetinfo", "resurrect", "reload", "restart"}
JAMES_TERMS = {
    "mq04doc", "vault112podtermdad", "mq04statusnotedad", "mq04stressnotedad",
    "mq04dadpodscript", "dadpod", "doc",
}
MEMORY_TERMS = {"memory", "neural", "engram", "remember", "memories"}
CARRIER_TERMS = {"mem chip", "memory chip", "memchip", "neuralizer", "carrier"}
PERSISTENCE_TERMS = {"persist", "archive", "backup", "snapshot", "storage", "save", "restore", "reload"}
OPERATION_TERMS = {
    "copy", "write", "rewrite", "export", "transfer", "overwrite", "serialize",
    "persist", "archive", "backup", "save", "restore", "reload", "rebind",
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


def contains_any(text: str, terms: set[str]) -> bool:
    t = norm(text)
    return any(term in t for term in terms)


def audit(index_rows: list[dict[str, str]], leaf_rows: list[dict[str, str]]) -> dict:
    if not index_rows:
        raise ValueError("MQ04 INFO index contains no rows")

    info_ids: set[str] = set()
    index_by_id: dict[str, dict[str, str]] = {}
    for row in index_rows:
        iid = row.get("info_logical_formid", "").strip().upper()
        if not iid:
            raise ValueError("index row missing info_logical_formid")
        if iid in info_ids:
            raise ValueError(f"duplicate MQ04 INFO logical FormID: {iid}")
        info_ids.add(iid)
        index_by_id[iid] = row

    leaves_by_info: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in leaf_rows:
        iid = row.get("info_logical_formid", "").strip().upper()
        if not iid:
            raise ValueError("leaf row missing info_logical_formid")
        if iid not in info_ids:
            raise ValueError(f"leaf points to absent INFO: {iid}")
        section = row.get("section", "").strip().upper()
        if section not in SECTIONS:
            raise ValueError(f"unexpected section {section!r} for INFO {iid}")
        leaves_by_info[iid].append(row)

    classifications = Counter()
    high_priority: list[dict] = []
    compiled_only: list[dict] = []
    records: list[dict] = []

    for iid in sorted(info_ids):
        rows = leaves_by_info.get(iid, [])
        by_section: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            by_section[row["section"].upper()].append(row)

        def section_text(section: str) -> str:
            vals = []
            for r in by_section.get(section, []):
                vals.extend([
                    r.get("element_name", ""), r.get("element_value", ""),
                    r.get("linked_editorid", ""), r.get("linked_formid", ""),
                ])
            return "\n".join(vals)

        begin_text = section_text("BEGIN_SCRIPT")
        end_text = section_text("END_SCRIPT")
        script_text = begin_text + "\n" + end_text
        response_text = section_text("RESPONSES")
        condition_text = section_text("CONDITIONS")
        all_text = "\n".join([script_text, response_text, condition_text])

        source_present = False
        compiled_present = False
        linked_forms = []
        for r in rows:
            nm = norm(r.get("element_name", ""))
            val = r.get("element_value", "").strip()
            if r.get("section", "").upper() in {"BEGIN_SCRIPT", "END_SCRIPT"}:
                if "embedded script source" in nm and val:
                    source_present = True
                if "compiled embedded script" in nm and val:
                    compiled_present = True
            if r.get("linked_formid", "").strip():
                linked_forms.append({
                    "formid": r.get("linked_formid", ""),
                    "editorid": r.get("linked_editorid", ""),
                    "signature": r.get("linked_signature", ""),
                    "section": r.get("section", ""),
                })

        disclosure = contains_any(script_text, DISCLOSURE_TERMS)
        reset_trigger = contains_any(script_text, RESET_TERMS)
        james_bound = contains_any(script_text, JAMES_TERMS) or contains_any(
            " ".join(x["editorid"] for x in linked_forms), JAMES_TERMS
        )
        memory_bound = contains_any(script_text, MEMORY_TERMS)
        carrier_bound = contains_any(script_text, CARRIER_TERMS)
        persistence_bound = contains_any(script_text, PERSISTENCE_TERMS)
        operation_bound = contains_any(script_text, OPERATION_TERMS)
        unknown_user_mentioned = "user unknown" in norm(all_text)

        tags = []
        if disclosure:
            tags.append("DISCLOSURE_FLAG_RESULT")
        if reset_trigger:
            tags.append("RESET_OR_RELOAD_RESULT")
        if james_bound:
            tags.append("JAMES_SOURCE_BOUND_CANDIDATE")
        if memory_bound:
            tags.append("MEMORY_TERM_IN_RESULT")
        if carrier_bound:
            tags.append("CARRIER_TERM_IN_RESULT")
        if persistence_bound:
            tags.append("PERSISTENCE_TERM_IN_RESULT")
        if operation_bound:
            tags.append("OPERATION_TERM_IN_RESULT")
        if unknown_user_mentioned:
            tags.append("UNKNOWN_USER_MENTION")
        if compiled_present and not source_present:
            tags.append("COMPILED_ONLY_RESULT_SCRIPT")

        high = james_bound and operation_bound and (memory_bound or carrier_bound or persistence_bound)
        if high:
            tags.append("HIGH_PRIORITY_SELECTOR_PERSISTENCE_CANDIDATE")

        for tag in tags:
            classifications[tag] += 1

        item = {
            "info_logical_formid": iid,
            "topic_logical_formid": index_by_id[iid].get("topic_logical_formid"),
            "topic_editorid": index_by_id[iid].get("topic_editorid"),
            "speaker_editorid": index_by_id[iid].get("speaker_editorid"),
            "tags": tags,
            "begin_script_source_present": source_present,
            "compiled_script_present": compiled_present,
            "linked_forms": linked_forms,
            "james_source_bound_candidate": james_bound,
            "memory_term_in_result": memory_bound,
            "carrier_term_in_result": carrier_bound,
            "persistence_term_in_result": persistence_bound,
            "operation_term_in_result": operation_bound,
            "unknown_user_mentioned": unknown_user_mentioned,
            "direct_james_memory_to_carrier_binding_proven": False,
            "unknown_user_equals_james_proven": False,
        }
        records.append(item)
        if high:
            high_priority.append(item)
        if compiled_present and not source_present:
            compiled_only.append(item)

    return {
        "schema": "janus.fo3.mq04_info_selector_boundary_audit.v1_6",
        "info_count": len(index_rows),
        "leaf_count": len(leaf_rows),
        "classification_counts": dict(classifications),
        "high_priority_selector_persistence_candidate_count": len(high_priority),
        "high_priority_selector_persistence_candidates": high_priority,
        "compiled_only_result_script_count": len(compiled_only),
        "compiled_only_result_scripts": compiled_only,
        "records": records,
        "admission": {
            "mq04_info_population_bound": True,
            "begin_end_embedded_scripts_and_conditions_bound": True,
            "dad_dog_or_braun_disclosure_flag_is_memory_mutation": False,
            "npcreset_or_reload_result_is_memory_export": False,
            "unknown_user_is_james": "NOT_ESTABLISHED",
            "direct_james_selected_state_to_carrier": "NOT_ESTABLISHED_BY_AUTOMATED_CLASSIFICATION",
            "asset_level_executable_save_james": "BLOCKED_PENDING_PRIMARY_RESULT_SCRIPT_SEMANTICS_OR_STORAGE_BINDING",
        },
        "claim_ceiling": {
            "INFO_FLAG_SET_EQUALS_MEMORY_MUTATION": False,
            "DADDOGINFO_EQUALS_CARRIER_BINDING": False,
            "BRAUNINFO_EQUALS_ADMIN_SERIALIZER": False,
            "NPCRESET_EQUALS_MEMORY_EXPORT": False,
            "USER_UNKNOWN_EQUALS_JAMES": False,
            "SAME_INFO_TERM_CONVERGENCE_EQUALS_WRITE_DIRECTION": False,
            "COMPILED_ONLY_SCRIPT_EQUALS_HIDDEN_SERIALIZER": False,
            "HIGH_PRIORITY_CANDIDATE_EQUALS_PASS": False,
            "manual_primary_record_review_required": True,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True, type=Path)
    ap.add_argument("--leaves", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    index_rows, index_cols = read_tsv(args.index)
    leaf_rows, leaf_cols = read_tsv(args.leaves)
    missing_index = sorted(REQUIRED_INDEX_COLUMNS - index_cols)
    missing_leaf = sorted(REQUIRED_LEAF_COLUMNS - leaf_cols)
    if missing_index:
        raise SystemExit(f"missing index columns: {missing_index}")
    if missing_leaf:
        raise SystemExit(f"missing leaf columns: {missing_leaf}")

    result = audit(index_rows, leaf_rows)
    result["source_binding"] = {
        "mq04_info_index_tsv_sha256": sha256(args.index),
        "mq04_info_embedded_control_tsv_sha256": sha256(args.leaves),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
