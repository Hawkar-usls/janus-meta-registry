#!/usr/bin/env python3
"""R3C-1B: reconstruct Briakos' published analysis scope without 419-target search.

The candidate scope is frozen from Briakos' own explicit support semantics:
source support exactly 'Tablet' or 'Stone vessel', with distributional metrics
computed on records that carry retained THESIS_LITERAL_ALPHA_v0.1 content.

The published 419 total-record claim is tested separately.  A mismatch there
must not trigger subset search in this runner.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from janus_linear_a_r3c_common_v0_1 import (
    corpus_metrics,
    document_signs,
    word_items,
)
from janus_linear_a_r3c_source_loader_v0_4 import LOADER_ID, load_lineara_map_v0_4

PROFILE = "THESIS_LITERAL_ALPHA_v0.1"
EXPECTED_BYTES = 1609122
EXPECTED_SHA = "b7b383b93db55b504eb00c552a8b18c19a588e83bba7ff0ab93ca32277d8bfe2"
EXPLICIT_SUPPORTS = ("Tablet", "Stone vessel")
MDP_LEDGER_SUPPORTS = ("Tablet", "Lames (short thin tablet)", "3-sided bar", "4-sided bar")

TARGETS = {
    "total_tablets_claim": 419,
    "content_documents": 336,
    "administrative_documents": 299,
    "ceremonial_documents": 37,
    "administrative_sign_tokens": 2139,
    "ceremonial_sign_tokens": 342,
    "sign_tokens": 2481,
    "sign_types": 65,
    "word_tokens": 1244,
    "word_types": 573,
    "entropy_bits": 5.5826,
    "hapax_word_types": 434,
    "hapax_rate": 0.757,
    "mean_word_length_signs": 1.99,
}


def content(doc: dict[str, Any]) -> bool:
    return bool(word_items(doc, PROFILE))


def compare(name: str, observed: Any, target: Any) -> dict[str, Any]:
    row = {"metric": name, "observed": observed, "published_target": target}
    if isinstance(target, int) and isinstance(observed, int):
        row["match"] = observed == target
        row["delta"] = observed - target
        return row
    if isinstance(observed, (int, float)) and isinstance(target, (int, float)):
        precision = {"entropy_bits": 4, "hapax_rate": 3, "mean_word_length_signs": 2}.get(name)
        row["match"] = round(float(observed), precision) == round(float(target), precision) if precision is not None else observed == target
        row["delta"] = float(observed) - float(target)
        return row
    row["match"] = observed == target
    return row


def support_snapshot(docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total = Counter(str(v.get("support", "")) for v in docs.values())
    positive = Counter(str(v.get("support", "")) for v in docs.values() if content(v))
    sign_tokens = Counter()
    word_tokens = Counter()
    for v in docs.values():
        s = str(v.get("support", ""))
        sign_tokens[s] += len(document_signs(v, PROFILE))
        word_tokens[s] += len(word_items(v, PROFILE))
    keys = sorted(set(total) | set(positive) | set(sign_tokens) | set(word_tokens))
    return {
        "rows": [
            {
                "support": k,
                "effective_documents": total[k],
                "content_documents": positive[k],
                "retained_word_tokens": word_tokens[k],
                "retained_sign_tokens": sign_tokens[k],
            }
            for k in keys
        ]
    }


def ids_for_supports(docs: dict[str, dict[str, Any]], supports: tuple[str, ...], *, require_content: bool) -> list[str]:
    return [
        k for k, v in docs.items()
        if str(v.get("support", "")) in supports and (content(v) if require_content else True)
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    docs, meta = load_lineara_map_v0_4(args.source)
    source_ok = meta["bytes"] == EXPECTED_BYTES and meta["sha256"] == EXPECTED_SHA and meta["loader_id"] == LOADER_ID

    explicit_all_ids = ids_for_supports(docs, EXPLICIT_SUPPORTS, require_content=False)
    explicit_content_ids = ids_for_supports(docs, EXPLICIT_SUPPORTS, require_content=True)
    explicit_content_docs = {k: docs[k] for k in explicit_content_ids}

    admin_ids = ids_for_supports(docs, ("Tablet",), require_content=True)
    ceremonial_ids = ids_for_supports(docs, ("Stone vessel",), require_content=True)
    admin_signs = sum(len(document_signs(docs[k], PROFILE)) for k in admin_ids)
    ceremonial_signs = sum(len(document_signs(docs[k], PROFILE)) for k in ceremonial_ids)

    basic = corpus_metrics(explicit_content_docs, PROFILE)
    observed = {
        "total_tablets_claim": len(explicit_all_ids),
        "content_documents": len(explicit_content_ids),
        "administrative_documents": len(admin_ids),
        "ceremonial_documents": len(ceremonial_ids),
        "administrative_sign_tokens": admin_signs,
        "ceremonial_sign_tokens": ceremonial_signs,
        "sign_tokens": basic["sign_tokens"],
        "sign_types": basic["sign_types"],
        "word_tokens": basic["word_tokens"],
        "word_types": basic["word_types"],
        "entropy_bits": basic["entropy_bits"],
        "hapax_word_types": basic["hapax_word_types"],
        "hapax_rate": basic["hapax_rate"],
        "mean_word_length_signs": basic["mean_word_length_signs"],
    }
    comparisons = [compare(k, observed[k], TARGETS[k]) for k in TARGETS]

    scientific_names = [k for k in TARGETS if k != "total_tablets_claim"]
    scientific_match = all(next(r for r in comparisons if r["metric"] == k)["match"] for k in scientific_names)
    total_match = next(r for r in comparisons if r["metric"] == "total_tablets_claim")["match"]

    mdp_all = ids_for_supports(docs, MDP_LEDGER_SUPPORTS, require_content=False)
    mdp_content = ids_for_supports(docs, MDP_LEDGER_SUPPORTS, require_content=True)

    if not source_ok:
        status = "BLOCKED_SOURCE_IDENTITY_MISMATCH"
    elif scientific_match and total_match:
        status = "BRIAKOS_SCOPE_AND_TOTAL_COUNT_RECONSTRUCTED"
    elif scientific_match and not total_match:
        status = "BRIAKOS_SCIENTIFIC_SCOPE_RECONSTRUCTED_TOTAL_419_UNRESOLVED"
    else:
        status = "BRIAKOS_SCOPE_HYPOTHESIS_NOT_REPRODUCED"

    result = {
        "artifact_uuid": "JANUS-LINEAR-A-R3C-1B-BRIAKOS-SCOPE-RECONSTRUCTION-RESULT-2026-08-14-v0.1",
        "version": "v0.1",
        "node_type": "same_lineage_method_scope_reconstruction_result",
        "status": status,
        "frozen_spec": "data/JANUS-LINEAR-A-R3C-1B-BRIAKOS-SCOPE-RECONSTRUCTION-SPEC-2026-08-14-v0.1.json",
        "source": meta,
        "source_identity_admitted": source_ok,
        "predeclared_scope": {
            "supports_exact": list(EXPLICIT_SUPPORTS),
            "content_profile": PROFILE,
            "target_guided_subset_search": False,
        },
        "support_inventory": support_snapshot(docs),
        "explicit_support_scope": {
            "all_effective_documents": len(explicit_all_ids),
            "content_documents": len(explicit_content_ids),
            "noncontent_documents": len(explicit_all_ids) - len(explicit_content_ids),
            "administrative_content_documents": len(admin_ids),
            "ceremonial_content_documents": len(ceremonial_ids),
            "administrative_sign_tokens": admin_signs,
            "ceremonial_sign_tokens": ceremonial_signs,
            "basic_metrics": basic,
            "comparisons": comparisons,
            "scientific_target_vector_match": scientific_match,
            "published_total_419_match": total_match,
        },
        "external_MDP_clue_transport_only": {
            "supports_exact": list(MDP_LEDGER_SUPPORTS),
            "all_effective_documents_under_admitted_loader": len(mdp_all),
            "content_documents_under_admitted_loader": len(mdp_content),
            "used_for_Briakos_scope_selection": False,
            "blind_discovery_credit": False,
        },
        "interpretation_rule": {
            "if_scientific_match_total_mismatch": "Treat Briakos' analyzable scientific scope as reconstructed from explicit support semantics, but keep the reported 419 total as methodologically unresolved. Do not search for a 419 subset in this execution lineage.",
            "if_scientific_mismatch": "Preserve all divergences; no filter mutation in this run."
        },
        "execution_firewall": {
            "javascript_executed": False,
            "eval_used": False,
            "source_mutated": False,
            "R3B_effect": "NONE",
            "decipherment": False,
        },
        "claim_ceiling": {
            "same_lineage_method_reconstruction_only": True,
            "independent_transcription_replication": False,
            "new_anchor": False,
            "decipherment": False,
        },
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": status,
        "source_ok": source_ok,
        "explicit_all": len(explicit_all_ids),
        "explicit_content": len(explicit_content_ids),
        "admin_docs": len(admin_ids),
        "ceremonial_docs": len(ceremonial_ids),
        "sign_tokens": basic["sign_tokens"],
        "scientific_match": scientific_match,
        "total_419_match": total_match,
        "mdp_ledger_effective_count": len(mdp_all),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
