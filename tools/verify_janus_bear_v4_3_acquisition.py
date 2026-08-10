#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

REQUIRED_MASTERS = (
    "Fallout3.esm",
    "Anchorage.esm",
    "ThePitt.esm",
    "BrokenSteel.esm",
    "PointLookout.esm",
    "Zeta.esm",
)

REQUIRED_COLUMNS = (
    "record_file",
    "record_signature",
    "record_formid",
    "target_kind",
    "base_file",
    "base_signature",
    "base_formid",
    "location_key",
    "initially_disabled",
    "deleted",
    "persistent",
    "position_x",
    "position_y",
    "position_z",
    "logical_ref_formid",
    "origin_record_file",
    "winning_record_file",
    "override_count",
)

SKELETON_KINDS = {
    "SKELETON_CLOTHES",
    "SKELETON_RAGS",
    "SKELETON_MALE",
    "SKELETON_FEMALE",
}
GNOME_KINDS = {"GNOME_GENERIC", "GNOME_INTACT", "GNOME_DAMAGED"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def finite_float(value: str) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def load_inventory(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        header = reader.fieldnames or []
        rows = list(reader)
    return header, rows


def write_enabled_only(path: Path, header: list[str], rows: list[dict[str, str]]) -> int:
    enabled = [r for r in rows if r.get("initially_disabled", "").lower() != "true"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(enabled)
    return len(enabled)


def verify(master_dir: Path, inventory: Path, *, synthetic: bool = False, enabled_only_out: Path | None = None) -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, observed=None, expected=None):
        checks.append({"name": name, "pass": bool(ok), "observed": observed, "expected": expected})

    master_entries = []
    for name in REQUIRED_MASTERS:
        path = master_dir / name
        exists = path.is_file()
        check(f"master.{name}.exists", exists, str(path) if exists else None, "regular file")
        if not exists:
            continue
        size = path.stat().st_size
        digest = sha256(path)
        master_entries.append({"name": name, "size_bytes": size, "sha256": digest})
        min_size = 1 if synthetic else 65536
        check(f"master.{name}.size_floor", size >= min_size, size, f">={min_size}")
        check(f"master.{name}.sha256_shape", len(digest) == 64, digest, "64 lowercase hex chars")

    check("master_bundle.complete", len(master_entries) == len(REQUIRED_MASTERS), len(master_entries), len(REQUIRED_MASTERS))

    inventory_exists = inventory.is_file()
    check("inventory.exists", inventory_exists, str(inventory) if inventory_exists else None, "regular file")
    header: list[str] = []
    rows: list[dict[str, str]] = []
    if inventory_exists:
        try:
            header, rows = load_inventory(inventory)
            check("inventory.parse_tsv", True, len(rows), "parseable TSV")
        except Exception as exc:
            check("inventory.parse_tsv", False, type(exc).__name__, "parseable TSV")

    missing_columns = [c for c in REQUIRED_COLUMNS if c not in header]
    check("inventory.required_columns", not missing_columns, missing_columns, [])

    min_rows = 1 if synthetic else 1000
    check("inventory.row_floor", len(rows) >= min_rows, len(rows), f">={min_rows}")

    logical_ids = [r.get("logical_ref_formid", "") for r in rows]
    nonempty_logical = [x for x in logical_ids if x]
    check("inventory.logical_ids_nonempty", len(nonempty_logical) == len(rows), len(nonempty_logical), len(rows))
    check("inventory.logical_ids_unique", len(set(nonempty_logical)) == len(nonempty_logical), len(set(nonempty_logical)), len(nonempty_logical))

    bad_signature = sum(r.get("record_signature") != "REFR" for r in rows)
    check("inventory.only_REFR", bad_signature == 0, bad_signature, 0)

    official = set(REQUIRED_MASTERS)
    bad_winning_file = sum(r.get("winning_record_file") not in official for r in rows)
    bad_record_file = sum(r.get("record_file") not in official for r in rows)
    bad_origin_file = sum(r.get("origin_record_file") not in official for r in rows)
    check("inventory.winning_files_official_set", bad_winning_file == 0, bad_winning_file, 0)
    check("inventory.record_files_official_set", bad_record_file == 0, bad_record_file, 0)
    check("inventory.origin_files_official_set", bad_origin_file == 0, bad_origin_file, 0)

    winning_counts = Counter(r.get("winning_record_file", "") for r in rows)
    missing_winning_plugins = [m for m in REQUIRED_MASTERS if winning_counts[m] == 0]
    check("inventory.every_master_contributes_winning_REFR", not missing_winning_plugins, missing_winning_plugins, [])

    deleted_rows = sum(r.get("deleted", "").lower() == "true" for r in rows)
    check("inventory.no_winning_deleted_rows", deleted_rows == 0, deleted_rows, 0)

    empty_locations = sum(not r.get("location_key", "") for r in rows)
    check("inventory.location_key_complete", empty_locations == 0, empty_locations, 0)

    invalid_positions = sum(
        not all(finite_float(r.get(k, "")) for k in ("position_x", "position_y", "position_z"))
        for r in rows
    )
    check("inventory.positions_finite", invalid_positions == 0, invalid_positions, 0)

    bad_override_count = 0
    for r in rows:
        try:
            if int(r.get("override_count", "")) < 0:
                bad_override_count += 1
        except ValueError:
            bad_override_count += 1
    check("inventory.override_count_valid", bad_override_count == 0, bad_override_count, 0)

    target_counts = Counter(r.get("target_kind", "OTHER") for r in rows)
    check("inventory.teddy_population_nonzero", target_counts["TEDDY"] > 0, target_counts["TEDDY"], ">0")
    skeleton_count = sum(target_counts[k] for k in SKELETON_KINDS)
    gnome_count = sum(target_counts[k] for k in GNOME_KINDS)
    check("inventory.static_skeleton_proxy_population_nonzero", skeleton_count > 0, skeleton_count, ">0")
    check("inventory.gnome_population_nonzero", gnome_count > 0, gnome_count, ">0")

    enabled_rows = sum(r.get("initially_disabled", "").lower() != "true" for r in rows)
    initially_disabled_rows = len(rows) - enabled_rows
    enabled_only_sha = None
    if enabled_only_out is not None and header and rows:
        written = write_enabled_only(enabled_only_out, header, rows)
        enabled_only_sha = sha256(enabled_only_out)
        check("enabled_only.row_count", written == enabled_rows, written, enabled_rows)

    failed = [c for c in checks if not c["pass"]]
    result = {
        "schema": "janus.bear.v4_3.acquisition_verification.v1",
        "status": "PASS_SOURCE_BUNDLE_HASH_BOUND_AND_EFFECTIVE_REFR_INVENTORY_ADMITTED" if not failed else "BLOCKED",
        "synthetic_mode": synthetic,
        "master_bundle": {
            "required_names": list(REQUIRED_MASTERS),
            "entries": master_entries,
            "bundle_identity": "sha256-per-file",
            "source_path_published": False,
        },
        "inventory": {
            "path_basename": inventory.name,
            "sha256": sha256(inventory) if inventory_exists else None,
            "rows": len(rows),
            "winning_rows_by_plugin": dict(sorted(winning_counts.items())),
            "effective_logical_refr_count": len(nonempty_logical),
            "enabled_rows": enabled_rows,
            "initially_disabled_rows": initially_disabled_rows,
            "enabled_only_sha256": enabled_only_sha,
            "target_counts": dict(sorted(target_counts.items())),
            "static_skeleton_proxy_count": skeleton_count,
            "gnome_count": gnome_count,
        },
        "checks_total": len(checks),
        "checks_passed": len(checks) - len(failed),
        "checks_failed": len(failed),
        "checks": checks,
        "claim_ceiling": {
            "master_bytes_hash_bound": not failed and len(master_entries) == 6,
            "official_distribution_authenticity_cryptographically_proved": False,
            "reason_authenticity_ceiling": "File names, sizes, hashes and xEdit-export structure bind the supplied game-install bundle, but no universal Bethesda-signed digest set is asserted across Steam/GOG/localized/revised distributions.",
            "effective_winning_REFR_population_admitted": not failed,
            "real_spatial_result_established": False,
            "authorial_intent_established": False,
        },
    }
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--master-dir", required=True, type=Path)
    ap.add_argument("--inventory", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--enabled-only-out", type=Path)
    ap.add_argument("--synthetic", action="store_true", help="Testing only: lower file-size and inventory row floors.")
    args = ap.parse_args()

    result = verify(
        args.master_dir,
        args.inventory,
        synthetic=args.synthetic,
        enabled_only_out=args.enabled_only_out,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"].startswith("PASS_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
