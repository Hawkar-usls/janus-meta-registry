#!/usr/bin/env python3
"""
Verify an FO3Edit/xEdit TSV export for exact Fallout 3 -> Mothership Zeta
birthday/happy-place asset lineage.

This verifier does NOT parse Bethesda ESM files itself. It consumes the
read-only export produced by tools/fo3edit_zeta_birthday_lineage_export.pas.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

BIRTHDAY_BASES = {
    "00028FF8": "KIDS_PARTY_HAT",
    "0009FAED": "BIRTHDAY_BALLOONS",
    "0009AE97": "BIRTHDAY_BANNER",
    "0009AE98": "BIRTHDAY_CAKE_STATIC",
    "0009FE61": "BIRTHDAY_CAKE_FX",
}
ADULT_PARTY_HAT = "00050E44"

CONTEXT_TERMS = ("dlc05mz1", "abduction", "playerstartmarker", "examination", "holding cells")


def truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


def norm_formid(value: str) -> str:
    value = value.strip().upper().replace("0X", "")
    return value.zfill(8) if value else ""


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    required = {
        "record_file", "record_signature", "record_formid", "base_file",
        "base_formid", "parent_cell_or_world", "initially_disabled",
        "deleted", "full_path", "match_reason",
    }
    missing = required.difference(rows[0].keys() if rows else set())
    if missing:
        raise SystemExit(f"receipt missing required columns: {sorted(missing)}")
    return rows


def verify(rows: list[dict[str, str]]) -> dict:
    zeta_rows = [r for r in rows if r["record_file"].lower() == "zeta.esm"]

    direct = []
    strong = []
    adult_hats = []
    keyword_only = []

    for r in zeta_rows:
        base = norm_formid(r.get("base_formid", ""))
        context = " ".join(
            [
                r.get("record_editorid", ""),
                r.get("base_editorid", ""),
                r.get("base_name", ""),
                r.get("parent_cell_or_world", ""),
                r.get("full_path", ""),
                r.get("match_reason", ""),
            ]
        ).lower()

        if base == ADULT_PARTY_HAT:
            adult_hats.append(r)

        if base in BIRTHDAY_BASES:
            item = dict(r)
            item["birthday_target"] = BIRTHDAY_BASES[base]
            direct.append(item)
            if (
                any(term in context for term in CONTEXT_TERMS)
                or truthy(r.get("initially_disabled", ""))
                or truthy(r.get("deleted", ""))
            ):
                strong.append(item)
        elif "target_base_form:" not in r.get("match_reason", ""):
            keyword_only.append(r)

    four_hat_count = len(adult_hats) == 4

    if strong:
        direct_status = "STRONG_PASS"
    elif direct:
        direct_status = "PASS"
    else:
        direct_status = "NOT_ESTABLISHED"

    return {
        "schema": "janus.zeta_birthday_lineage_receipt.v1",
        "result": "PASS" if direct else "OPEN",
        "claims": {
            "DIRECT_DLC05_REFERENCE_TO_FALLOUT3_BIRTHDAY_BASE": direct_status,
            "EXAMINATION_CONTEXT_BIRTHDAY_REFERENCE": "PASS" if strong else "NOT_ESTABLISHED",
            "ZETA_ADULT_PARTY_HAT_REFERENCE_COUNT": len(adult_hats),
            "FOUR_ZETA_ADULT_PARTY_HATS": "PASS" if four_hat_count else "RECOMPUTED_COUNT_DIFFERS",
            "KIDS_PARTY_HAT_BASE_ON_ZETA": "PASS"
            if any(norm_formid(r.get("base_formid", "")) == "00028FF8" for r in direct)
            else "NOT_ESTABLISHED",
            "LIFELONG_ALIEN_SURVEILLANCE": "NOT_DERIVABLE_FROM_THIS_RECEIPT",
        },
        "direct_edges": direct,
        "strong_context_edges": strong,
        "adult_party_hat_refs": adult_hats,
        "keyword_residue_candidates": keyword_only,
        "invariants": {
            "COUNT_PARALLEL_DOES_NOT_CREATE_REFERENCE_EDGE": True,
            "ADULT_HAT_BASE_DOES_NOT_EQUAL_KID_HAT_BASE": True,
            "MEMORY_OR_BIRTHDAY_ASSET_DOES_NOT_PROVE_SURVEILLANCE": True,
            "REFERENCE_PROVENANCE_MUST_BE_PRESERVED": True,
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", required=True, type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--pretty", action="store_true")
    args = ap.parse_args()

    receipt = verify(load_rows(args.tsv))
    text = json.dumps(receipt, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
