#!/usr/bin/env python3
"""R3C-1D: replay a frozen external MDP parser family on Briakos historical bytes.

No candidate tuning is performed.  The external parser semantics are copied from
souldriver007/mdp-ancient-scripts lineara_mdp_v2.py at its frozen commit, then
compared against Briakos' independently published corpus/site fingerprint.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

EXPECTED_BYTES = 1609122
EXPECTED_SHA = "b7b383b93db55b504eb00c552a8b18c19a588e83bba7ff0ab93ca32277d8bfe2"

REGISTER_MAP = {
    "Tablet": "LEDGER", "Lames (short thin tablet)": "LEDGER",
    "3-sided bar": "LEDGER", "4-sided bar": "LEDGER",
    "Nodule": "NODULE", "Sealing": "NODULE",
    "Roundel": "ROUNDEL",
    "Stone vessel": "RITUAL", "Metal object": "RITUAL",
    "Stone object": "RITUAL", "Clay vessel": "RITUAL",
    "Inked inscription": "OTHER", "Architecture": "OTHER",
    "Graffito": "OTHER", "Label": "OTHER",
}

BRIAKOS_SITE = {
    "Haghia Triada": 185,
    "Khania": 103,
    "Zakros": 44,
    "Phaistos": 41,
    "Knossos": 11,
}
BRIAKOS_OTHER_TEN = 35


def mdp_parse_exact(raw: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    entry_pattern = re.compile(r'\["([^"]+)"\s*,\s*\{', re.DOTALL)
    positions_list = [(m.start(), m.group(1)) for m in entry_pattern.finditer(raw)]
    inscriptions: dict[str, dict[str, Any]] = {}
    first_success_index: dict[str, int] = {}
    failures: list[dict[str, Any]] = []
    replacements: list[dict[str, Any]] = []
    successes = 0
    fallback_successes = 0

    for i, (pos, name) in enumerate(positions_list):
        brace_start = raw.index('{', pos)
        depth = 0
        j = brace_start
        while j < len(raw):
            if raw[j] == '{':
                depth += 1
            elif raw[j] == '}':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        fragment = raw[brace_start:j + 1]
        parsed = None
        mode = None
        try:
            parsed = json.loads(fragment)
            mode = "STRICT_JSON"
        except Exception as e1:
            try:
                parsed = json.loads(fragment.replace("'", '"'))
                mode = "SINGLE_QUOTE_GLOBAL_REPLACEMENT_FALLBACK"
                fallback_successes += 1
            except Exception as e2:
                failures.append({
                    "candidate_index": i,
                    "name": name,
                    "source_position": pos,
                    "fragment_bytes_utf8": len(fragment.encode('utf-8')),
                    "strict_exception": type(e1).__name__,
                    "fallback_exception": type(e2).__name__,
                })
                continue
        if not isinstance(parsed, dict):
            failures.append({
                "candidate_index": i,
                "name": name,
                "source_position": pos,
                "reason": "PARSED_VALUE_NOT_OBJECT",
            })
            continue
        successes += 1
        if name in inscriptions:
            replacements.append({
                "name": name,
                "first_success_index": first_success_index[name],
                "replacement_candidate_index": i,
            })
        else:
            first_success_index[name] = i
        inscriptions[name] = parsed

    return inscriptions, {
        "regex_candidate_count": len(positions_list),
        "successful_candidate_occurrences": successes,
        "effective_unique_record_count": len(inscriptions),
        "fallback_success_count": fallback_successes,
        "failed_candidate_count": len(failures),
        "failures": failures,
        "duplicate_replacement_count": len(replacements),
        "duplicate_replacements": replacements,
        "javascript_executed": False,
        "eval_used": False,
    }


def id_sha(ids: list[str]) -> str:
    return hashlib.sha256(("\n".join(ids) + "\n").encode("utf-8")).hexdigest()


def population_fingerprint(docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sites = Counter(str(v.get("site", "")) for v in docs.values())
    supports = Counter(str(v.get("support", "")) for v in docs.values())
    named_sum = sum(sites.get(k, 0) for k in BRIAKOS_SITE)
    other_sites = {k: n for k, n in sites.items() if k not in BRIAKOS_SITE}
    ids = list(docs)
    named_matches = {k: sites.get(k, 0) == target for k, target in BRIAKOS_SITE.items()}
    residual = len(docs) - named_sum
    site_fingerprint_match = (
        len(docs) == 419
        and all(named_matches.values())
        and len([k for k, n in sites.items() if n > 0]) == 15
        and residual == BRIAKOS_OTHER_TEN
    )
    return {
        "document_count": len(docs),
        "id_set_sha256_sorted": id_sha(sorted(ids)),
        "id_order_sha256": id_sha(ids),
        "site_count": sum(1 for n in sites.values() if n > 0),
        "site_histogram": sites.most_common(),
        "support_histogram": supports.most_common(),
        "Briakos_named_site_matches": named_matches,
        "Briakos_named_site_sum": named_sum,
        "other_site_document_count": residual,
        "other_sites": sorted(other_sites.items()),
        "Briakos_site_fingerprint_match": site_fingerprint_match,
        "source_support_Stone_vessel_count": supports.get("Stone vessel", 0),
        "can_contain_published_37_stone_vessels": supports.get("Stone vessel", 0) >= 37,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    p = Path(args.source)
    rawb = p.read_bytes()
    raw = rawb.decode("utf-8")
    source_ok = len(rawb) == EXPECTED_BYTES and hashlib.sha256(rawb).hexdigest() == EXPECTED_SHA
    parsed, parse_receipt = mdp_parse_exact(raw)

    registers: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for name, data in parsed.items():
        register = REGISTER_MAP.get(str(data.get("support", "unknown")), "OTHER")
        registers[register][name] = data

    populations = {
        "ALL_SUCCESSFUL_EFFECTIVE": parsed,
        "LEDGER": registers.get("LEDGER", {}),
        "RITUAL": registers.get("RITUAL", {}),
        "LEDGER_PLUS_RITUAL": {**registers.get("LEDGER", {}), **registers.get("RITUAL", {})},
    }
    fps = {name: population_fingerprint(docs) for name, docs in populations.items()}

    candidates_419 = [name for name, fp in fps.items() if fp["document_count"] == 419]
    strong = [name for name, fp in fps.items() if fp["Briakos_site_fingerprint_match"] and fp["can_contain_published_37_stone_vessels"]]
    count_only = [name for name in candidates_419 if name not in strong]
    if not source_ok:
        status = "BLOCKED_SOURCE_IDENTITY_MISMATCH"
    elif strong:
        status = "STRONG_CORPUS_IDENTITY_CANDIDATE"
    elif count_only:
        status = "COUNT_ONLY_COLLISION"
    else:
        status = "NO_MATCH"

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1D-EXTERNAL-PARSER-FAMILY-FINGERPRINT-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "same_lineage_external_parser_family_fingerprint_result",
        "status": status,
        "frozen_spec": "data/JANUS-LINEAR-A-R3C-1D-EXTERNAL-PARSER-FAMILY-FINGERPRINT-SPEC-2026-08-14-v0.1.json",
        "source": {
            "bytes": len(rawb),
            "sha256": hashlib.sha256(rawb).hexdigest(),
            "identity_admitted": source_ok,
        },
        "external_parser": {
            "repository": "souldriver007/mdp-ancient-scripts",
            "commit": "154f572fc8ef29e3d49859b5089d90d92c8d3044",
            "path": "lineara_mdp_v2.py",
            "git_blob_sha": "fdce5be99661c31879d31690954f83d605834e3f",
            "receipt": parse_receipt,
        },
        "register_counts": {k: len(v) for k, v in sorted(registers.items())},
        "population_fingerprints": fps,
        "grading": {
            "populations_equal_419": candidates_419,
            "strong_candidates": strong,
            "count_only_collisions": count_only,
            "Briakos_code_identity_claimed": False,
        },
        "contamination": {
            "MDP_LEDGER_419_known_before_execution": True,
            "count_blind_credit": False,
            "site_fingerprint_result_previously_unknown": True,
            "candidate_parameters_changed_after_execution": False,
        },
        "claim_ceiling": {
            "same_lineage_parser_family_comparison_only": True,
            "Briakos_parser_reconstructed": False,
            "R3B_effect": "NONE",
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "source_ok": source_ok,
        "effective": parse_receipt["effective_unique_record_count"],
        "failures": parse_receipt["failed_candidate_count"],
        "register_counts": result["register_counts"],
        "candidates_419": candidates_419,
        "strong": strong,
        "ledger_sites": fps["LEDGER"]["site_histogram"],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
