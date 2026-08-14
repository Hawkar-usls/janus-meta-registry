#!/usr/bin/env python3
"""Fail-closed source validator for curated Connection hidden-pattern candidates v1.0.

This validator does NOT decide whether a hidden pattern is true in general.
It verifies the narrower claim that the pinned source JSON bodies still contain
exactly the source-level distinctions used to formulate HIDDEN-001/002/003.

It also enforces anti-circularity: prior Connection artifacts may be cited as
hypothesis/novelty memory but carry zero independent support.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CURATED = ROOT / "data/JANUS-CONNECTION-FULL-CORPUS-HIDDEN-PATTERNS-2026-08-14-v1.0.json"

PINNED = {
    "ROBBIE_SOURCE_ONTOLOGY": (
        "data/JANUS-SING-WHEN-YOURE-WINNING-SOURCE-ONTOLOGY-PROTOCOL-AMENDMENT-v1.2.json",
        "829291235111350e6b69b4adc753e3e8a31de00e",
    ),
    "ROBBIE_FIRST_BREAK": (
        "data/JANUS-SING-WHEN-YOURE-WINNING-BOUNDARY-LOCALIZED-SCORING-SPEC-v1.0.json",
        "3fc2ea1e0d035ad5e273d55de3852a91b2aea7da",
    ),
    "FALLOUT_POD_ROLE": (
        "registry/myth_busted/FALLOUT-3-VAULT112A-PUBLIC-DERIVED-POD-ROLE-ANCHOR-HARDENING-v2.4.json",
        "dee5e8e52cb8eef52b9287e225dabb0f4df85864",
    ),
    "LINEAR_A_DOCUMENT_BRIDGE": (
        "data/JANUS-LINEAR-A-SIGLA-DOCUMENT-IDENTITY-BRIDGE-RESULT-2026-08-14-v0.1.json",
        "0efd42a6c7c2842d13aef5de121d2423e084bff2",
    ),
    "SCOBY_CHITIN": (
        "data/SCOBY-D1-CHITIN-BIOCOMPOSITE-v1.0.json",
        "a63c47d25afdd61463004b7604db3321080ae1b5",
    ),
    "CONNECTION_SCAN_015": (
        "data/JANUS-CONNECTION-SCAN-2026-08-13-015-DATA-BATCH-001.json",
        "cb8882c76e9bf043d6f7a4ec6cf57b409371781a",
    ),
}


def load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8-sig"))


def blob_sha(rel: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", rel], cwd=ROOT, text=True
    ).strip()


def require(cond: bool, msg: str):
    if not cond:
        raise AssertionError(msg)


def contains_text(values, needle: str) -> bool:
    return any(needle in str(v) for v in values)


def main():
    # Exact source identity first: if a source changes, review/re-pin explicitly.
    for label, (rel, expected) in PINNED.items():
        actual = blob_sha(rel)
        require(actual == expected, f"BLOB_MISMATCH {label} {actual} != {expected}")

    robbie = load(PINNED["ROBBIE_SOURCE_ONTOLOGY"][0])
    firstbreak = load(PINNED["ROBBIE_FIRST_BREAK"][0])
    fallout = load(PINNED["FALLOUT_POD_ROLE"][0])
    linear = load(PINNED["LINEAR_A_DOCUMENT_BRIDGE"][0])
    scoby = load(PINNED["SCOBY_CHITIN"][0])
    scan015 = load(PINNED["CONNECTION_SCAN_015"][0])
    curated = json.loads(CURATED.read_text(encoding="utf-8"))

    # HIDDEN-001 source facts: evidence type N is not evidence type N+1.
    require(
        robbie["primary_visual_source_endpoint"]["name"] == "SOURCE_PHYSICAL_SUBJECT",
        "ROBBIE physical-subject endpoint changed",
    )
    require(
        "SOURCE_REPRESENTED_IDENTITY" in robbie["secondary_source_endpoints"],
        "ROBBIE represented-identity split missing",
    )
    require(
        robbie["source_relation_ontology"]["SAME_PERFORMER_MULTIPLE_STAGED_ROLES"]["represented_identity"] is None,
        "ROBBIE staged-role ambiguity no longer null",
    )

    hard_rules = fallout["hard_rules"]
    require("DAD_ROLE_BASE != EXACT_JAMES_PLACED_REF" in hard_rules, "Fallout base->instance boundary missing")
    require("ROLE_BOUND_CANDIDATE != PERSISTED_MEMORY_STATE" in hard_rules, "Fallout role->outcome boundary missing")
    design = fallout["successor_tooling"]["design"]
    require(
        contains_text(design, "preserve ambiguity") and contains_text(design, "require primary placed-instance semantics"),
        "Fallout ambiguity-preservation rule missing",
    )

    br = linear["bridge_result"]
    eg = linear["epistemic_gate"]
    require(br["collision_free_one_to_one_matches"] == 686, "Linear A bridge count changed")
    require(eg["document_identity_bridge_established_for_686_collision_free_matches"] is True, "Linear A identity bridge not admitted")
    require(eg["cross_digitization_content_replication_established"] is False, "Linear A identity unexpectedly promoted to content replication")
    require(eg["external_transcription_replication_established"] is False, "Linear A identity unexpectedly promoted to transcription replication")
    require(eg["decipherment_established"] is False, "Linear A identity unexpectedly promoted to decipherment")
    method = {x["name"]: x for x in linear["methodological_connections"]}
    require(
        "UNRESOLVED_IDENTITY_RESIDUES_SHOULD_BE_EXCLUDED_NOT_GUESSED" in method,
        "Linear A unresolved-residue anti-guess rule missing",
    )

    require(
        scoby["central_invariant"] == "APPLICATION_CLASSIFICATION_MUST_NOT_PRECEDE_MATERIAL_IDENTITY",
        "SCOBY identity-before-application invariant changed",
    )
    seq = scoby["gating_sequence"]
    require(seq[0].startswith("G0_IDENTITY"), "SCOBY first gate is no longer identity")
    require(seq[1].startswith("G2_STRUCTURE"), "SCOBY second gate is no longer structure")
    require(seq[2].startswith("G3_MECHANICAL_FUNCTION"), "SCOBY third gate is no longer mechanical function")
    require(
        "Do not attribute improvement to chitin" in scoby["decision_logic"]["if_mechanics_improve_but_chitin_signal_is_absent"],
        "SCOBY attribution firewall changed",
    )

    # HIDDEN-003: explicit first-break source plus three implicit gate ladders.
    require(firstbreak["core_model"]["ordered_chain"] == ["SOURCE", "WORLD", "RECEIPT"], "Robbie ordered first-break chain changed")
    require(firstbreak["first_break_rule"]["ordered_evaluation"] == ["SOURCE", "WORLD", "RECEIPT"], "Robbie first-break evaluation changed")
    require(
        "more diagnostically informative than a single aggregate semantic score" in firstbreak["first_break_rule"]["reason"],
        "Robbie aggregate-vs-boundary rationale changed",
    )

    # Anti-circularity / novelty boundary.
    old = {x["name"]: x for x in scan015["cross_batch_findings"]}
    require("CLAIM_REQUIRES_IDENTITY_BEFORE_INTERPRETATION" in old, "Prior comparator absent")
    hidden1 = next(x for x in curated["discoveries"] if x["id"] == "HIDDEN-001")
    require(hidden1["relation_to_prior_connection"]["independent_support_from_prior_connection"] == 0, "Prior Connection scan given self-support")
    require(curated["claim_ceiling"]["relation_specific_destructive_validation_of_new_candidates"] is False, "Curated record overclaims destructive validation")
    require(curated["claim_ceiling"]["external_replication"] is False, "Curated record overclaims external replication")
    require(curated["claim_ceiling"]["scientific_novelty_established"] is False, "Curated record overclaims novelty")
    require(curated["claim_ceiling"]["family_wide_connection_promotion"] is False, "Curated record overclaims family-wide promotion")

    print("PASS_HIDDEN_PATTERN_SOURCE_VALIDATION")
    print("PINNED_SOURCES", len(PINNED))
    print("VALIDATED_CANDIDATES", "HIDDEN-001,HIDDEN-002,HIDDEN-003")


if __name__ == "__main__":
    main()
