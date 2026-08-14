#!/usr/bin/env python3
"""Validate the FO3 structural save parser against pinned real Fallout 3 saves.

This is a format-execution gate only. The fixtures are public Vortex test saves and
are not part of the user's James/Vault 112 T0/T1/T2/T3 lineage. Successful parsing
therefore validates real-file format execution, not James persistence or memory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List

VORTEX_REPOSITORY = "Nexus-Mods/Vortex"
VORTEX_COMMIT = "87eb92131c2e85dd52d4fdb9a69d41b4eb9148e6"
FIXTURE_BASE_PATH = "extensions/gamebryo-savegame-management/test/saves/fallout3"
FIXTURES = (
    {
        "name": "fallout3_1.fos",
        "size_bytes": 1839887,
        "git_blob_sha1": "9a38323a96e9f59b7430c784304ecf4b65adc968",
    },
    {
        "name": "fallout3_2.fos",
        "size_bytes": 1381193,
        "git_blob_sha1": "f9c11b2da0038d1528120cbd70eeac2322c44066",
    },
    {
        "name": "fallout3_3.fos",
        "size_bytes": 1870207,
        "git_blob_sha1": "16f87bc5f150465c105cc3187cf96f8cf39b0a31",
    },
)


class CorpusError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _load_structural_parser():
    path = Path(__file__).resolve().with_name("fo3_fos_changed_form_header_index_v0_1.py")
    spec = importlib.util.spec_from_file_location("fo3_structural_v01", path)
    if spec is None or spec.loader is None:
        raise CorpusError(f"cannot load structural parser: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def summarize_changed_forms(parsed: dict) -> dict:
    body = parsed["structural_body"]
    changed = body["changed_forms"]
    records = changed["header_index"]
    change_types = Counter(str(rec["change_type"]) for rec in records)
    ref_classes = Counter(rec["save_refid"]["type"] for rec in records)
    unresolved = sum(rec["resolved_formid_hex"] is None for rec in records)
    target_counts = {
        name: len(matches)
        for name, matches in changed["target_matches"].items()
    }
    return {
        "file_location_table": {
            "offset": body["file_location_table"]["offset"],
            "changed_forms_offset": body["file_location_table"]["changed_forms_offset"],
            "global_data_table_2_offset": body["file_location_table"]["global_data_table_2_offset"],
            "refid_array_count_offset": body["file_location_table"]["refid_array_count_offset"],
            "changed_forms_count": body["file_location_table"]["changed_forms_count"],
        },
        "formid_array_count": body["formid_array"]["count"],
        "changed_forms_count_declared": changed["count_declared"],
        "changed_forms_count_indexed": changed["count_indexed"],
        "exact_next_chapter_boundary_match": changed["exact_next_chapter_boundary_match"],
        "unresolved_save_refid_count": unresolved,
        "save_refid_class_histogram": dict(sorted(ref_classes.items())),
        "change_type_histogram": dict(sorted(change_types.items(), key=lambda kv: int(kv[0]))),
        "frozen_target_match_counts": target_counts,
        "frozen_target_match_fingerprints": changed["target_matches"],
        "frozen_target_match_authority": "INCIDENTAL_EXTERNAL_FIXTURE_ONLY_NOT_JAMES_LINEAGE",
    }


def validate_fixture(root: Path, fixture: dict, parser) -> dict:
    path = root / fixture["name"]
    result = {
        "name": fixture["name"],
        "source_path": f"{FIXTURE_BASE_PATH}/{fixture['name']}",
        "expected_size_bytes": fixture["size_bytes"],
        "expected_git_blob_sha1": fixture["git_blob_sha1"],
        "status": "FAIL",
    }
    if not path.is_file():
        result["error"] = "FIXTURE_MISSING"
        return result

    data = path.read_bytes()
    result["observed_size_bytes"] = len(data)
    result["observed_sha256"] = sha256_bytes(data)
    result["observed_git_blob_sha1"] = git_blob_sha1(data)
    result["size_match"] = len(data) == fixture["size_bytes"]
    result["git_blob_sha1_match"] = result["observed_git_blob_sha1"] == fixture["git_blob_sha1"]
    if not result["size_match"] or not result["git_blob_sha1_match"]:
        result["error"] = "PINNED_FIXTURE_IDENTITY_MISMATCH"
        return result

    try:
        parsed = parser.parse_file(path)
    except Exception as exc:
        result["error"] = f"STRUCTURAL_PARSE_FAILED: {exc}"
        return result

    header = parsed["header_and_plugins"]
    summary = summarize_changed_forms(parsed)
    execution_pass = (
        header["magic"] == "FO3SAVEGAME"
        and header["file_version_hex"] == "0x30"
        and summary["changed_forms_count_declared"] == summary["changed_forms_count_indexed"]
        and summary["exact_next_chapter_boundary_match"]
    )
    result.update({
        "header": {
            "magic": header["magic"],
            "file_version_hex": header["file_version_hex"],
            "save_number": header["save_number"],
            "character_level": header["character_level"],
            "location": header["location"],
            "plugin_count": header["plugin_count"],
            "ordered_plugin_manifest_sha256": header["ordered_plugin_manifest_sha256"],
            "body_offset": header["body_offset"],
        },
        "structural_summary": summary,
        "status": "PASS_REAL_FO3_STRUCTURAL_FORMAT_EXECUTION" if execution_pass else "FAIL_STRUCTURAL_INVARIANT",
    })
    return result


def cross_fixture_negative_control(results: List[dict]) -> dict:
    valid = [item for item in results if "structural_summary" in item]
    target_names = sorted({
        target
        for item in valid
        for target in item["structural_summary"]["frozen_target_match_counts"]
    })
    presence = {
        target: [
            item["structural_summary"]["frozen_target_match_counts"].get(target, 0) > 0
            for item in valid
        ]
        for target in target_names
    }
    present_in_all = [target for target, values in presence.items() if values and all(values)]
    locations = [item["header"]["location"] for item in valid]
    return {
        "fixture_header_locations": locations,
        "target_presence_vectors": presence,
        "targets_present_in_all_fixtures": present_in_all,
        "mq04_present_in_all": "MQ04" in present_in_all,
        "mqdadref_present_in_all": "MQDadRef" in present_in_all,
        "presence_only_admission": "REJECTED_AS_VAULT112_OR_JAMES_STATE_DISCRIMINATOR",
        "reason": "A target Changed Form can already be present in unrelated external fixtures whose save header location is Vault 101 Entrance. Future James inference must therefore use controlled differential fingerprints, not record presence alone.",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    parser = _load_structural_parser()
    results: List[dict] = [validate_fixture(args.fixture_dir, fixture, parser) for fixture in FIXTURES]
    all_pass = all(item["status"] == "PASS_REAL_FO3_STRUCTURAL_FORMAT_EXECUTION" for item in results)

    receipt: Dict[str, object] = {
        "schema": "janus.fo3_fos_real_fixture_corpus.v0_1",
        "authority": "REAL_EXTERNAL_FO3_SAVE_FORMAT_EXECUTION_ONLY",
        "corpus": {
            "repository": VORTEX_REPOSITORY,
            "commit": VORTEX_COMMIT,
            "base_path": FIXTURE_BASE_PATH,
            "fixture_count": len(FIXTURES),
            "fixture_identity_rule": "PINNED_COMMIT_PLUS_GIT_BLOB_SHA1_PLUS_SIZE",
        },
        "fixtures": results,
        "cross_fixture_negative_control": cross_fixture_negative_control(results),
        "overall_status": "PASS_ON_ALL_PINNED_REAL_FO3_FIXTURES" if all_pass else "FAIL_ONE_OR_MORE_REAL_FO3_FIXTURES",
        "format_execution_established": all_pass,
        "real_james_t0_t3_lineage_present": False,
        "james_changed_form_binding_established": False,
        "cross_exit_james_engine_persistence_established": False,
        "james_autobiographical_payload_established": False,
        "in_world_braun_serialization_established": False,
        "hard_rules": [
            "REAL_EXTERNAL_FIXTURE_FORMAT_PASS != USER_JAMES_T0_T3_EXECUTION",
            "INCIDENTAL_TARGET_FORMID_MATCH != JAMES_LINEAGE_EVIDENCE",
            "TARGET_RECORD_PRESENCE_ALONE != VAULT112_SESSION_DISCRIMINATOR",
            "CHANGED_FORM_PRESENCE != AUTOBIOGRAPHICAL_MEMORY",
            "ENGINE_SAVE_STATE != IN_WORLD_MEMORY_CARRIER",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
