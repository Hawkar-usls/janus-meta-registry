#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "registry/myth_busted/JANUS-BEAR-GNOME-SPATIAL-PUBLICATION-RECEIPT-v4.1.json"
TECHNICAL = ROOT / "registry/myth_busted/FALLOUT-3-JANUS-BEAR-SPATIAL-ENRICHMENT-TECHNICAL-v4.0.json"
ANALYZER = ROOT / "tools/analyze_teddy_gnome_enrichment.py"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def git_blob_sha(path: Path) -> str:
    return git("hash-object", str(path.relative_to(ROOT)))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify() -> dict:
    receipt = load_json(RECEIPT)
    technical = load_json(TECHNICAL)

    checks: list[dict] = []

    def check(name: str, condition: bool, observed=None, expected=None):
        checks.append(
            {
                "name": name,
                "pass": bool(condition),
                "observed": observed,
                "expected": expected,
            }
        )

    bindings = receipt["engineering_receipt"]
    for key in (
        "janus_bear",
        "gnome_grammar",
        "spatial_technical",
        "context_ledger_schema",
        "reference_exporter",
        "enrichment_analyzer",
        "tests",
    ):
        node = bindings[key]
        path = ROOT / node["path"]
        check(f"{key}.exists", path.exists(), str(path.relative_to(ROOT)), "exists")
        if path.exists():
            actual_blob = git_blob_sha(path)
            check(
                f"{key}.blob_sha1",
                actual_blob == node["blob_sha1"],
                actual_blob,
                node["blob_sha1"],
            )

    frozen = receipt["frozen_findings"]
    check(
        "old_exact_teddy_literal_stays_unrecovered",
        frozen["OLD_EXACT_TEDDY_LITERAL"] == "NOT_RECOVERED",
        frozen["OLD_EXACT_TEDDY_LITERAL"],
        "NOT_RECOVERED",
    )
    for field in (
        "REAL_TEDDY_WITHIN_128_PERCENT",
        "REAL_TEDDY_WITHIN_512_PERCENT",
        "REAL_TEDDY_VS_MISC_ENRICHMENT",
        "REAL_GNOME_TEDDY_SKELETON_TRIAD_COUNT",
    ):
        check(
            f"{field}.remains_unknown",
            frozen[field] == "UNKNOWN_PENDING_ESM_EXPORT",
            frozen[field],
            "UNKNOWN_PENDING_ESM_EXPORT",
        )

    boundary = receipt["execution_boundary"]
    for field in (
        "official_Fallout3_and_DLC_master_bytes_present_in_current_runtime",
        "FO3Edit_export_executed_on_real_masters",
        "real_reference_population_available",
        "public_full_reference_dump_sufficient_for_exact_replay_found",
        "real_128_512_percentages_computed",
    ):
        check(f"execution_boundary.{field}", boundary[field] is False, boundary[field], False)

    targets = technical["targets"]
    check(
        "damaged_gnome_formid_bound",
        targets.get("GNOME_DAMAGED") == "0005B635",
        targets.get("GNOME_DAMAGED"),
        "0005B635",
    )

    source = ANALYZER.read_text(encoding="utf-8")
    check(
        "analyzer_tracks_damaged_gnome",
        '"GNOME_DAMAGED"' in source,
        '"GNOME_DAMAGED"' in source,
        True,
    )
    check(
        "analyzer_keeps_same_location_pairing",
        'c.get("location_key", "") != loc' in source,
        'c.get("location_key", "") != loc' in source,
        True,
    )
    check(
        "analyzer_contains_fisher_gate",
        "fisher_two_sided" in source,
        "fisher_two_sided" in source,
        True,
    )

    rules = set(receipt["formal_rules"])
    required_rules = {
        "SPATIAL_ENRICHMENT != SINGLE_PLACER",
        "SPATIAL_ENRICHMENT != AUTHORIAL_INTENT_BY_ITSELF",
        "GNOME_POSE != GNOME_SENTIENCE",
        "SYNTHETIC_TEST_PASS != REAL_ESM_RESULT",
        "CHILD_GUARDIAN != CHILD_OWNER",
    }
    check(
        "claim_ceiling_rules_complete",
        required_rules.issubset(rules),
        sorted(required_rules.intersection(rules)),
        sorted(required_rules),
    )

    failed = [c for c in checks if not c["pass"]]
    return {
        "schema": "janus.bear.ci_lineage_verification.v1",
        "status": "PASS" if not failed else "FAIL",
        "git": {
            "head": git("rev-parse", "HEAD"),
            "tree": git("rev-parse", "HEAD^{tree}"),
        },
        "receipt": {
            "path": str(RECEIPT.relative_to(ROOT)),
            "sha256": sha256(RECEIPT),
        },
        "checks_total": len(checks),
        "checks_passed": len(checks) - len(failed),
        "checks_failed": len(failed),
        "checks": checks,
        "claim_ceiling": {
            "synthetic_logic_may_be_verified_by_ci": True,
            "real_esm_spatial_result_established": False,
            "authorial_intent_established_by_statistics": False,
            "single_in_world_placer_established": False,
            "gnome_sentience_established": False,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    result = verify()
    text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
