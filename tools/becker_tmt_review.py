#!/usr/bin/env python3
"""Validate the ontology and route an optional structured proposal locally."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.becker_tmt_policy import ACTIONS, BASES, LEVELS, VERIFICATION_STATES, review_proposal

ROOT = Path(__file__).resolve().parents[1]
POINTER = ROOT / "registry/psychology/BECKER_TMT_CURRENT.json"
SCHEMA = ROOT / "schemas/becker-tmt-ontology.schema.json"


def unique(rows, label):
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"DUPLICATE_{label}_ID")
    return set(ids)


def validate_ontology(value):
    # Schema validation is mandatory; a missing dependency must never look green.
    from jsonschema import Draft202012Validator
    schema = json.loads(SCHEMA.read_bytes())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(value)
    concepts = unique(value["concept_catalog"], "CONCEPT")
    sources = unique(value["source_catalog"], "SOURCE")
    unique(value["relations"], "RELATION")
    unique(value["evidence_catalog"], "EVIDENCE")
    unique(value["engineering_rules"], "RULE")
    unique(value["synthetic_experiment_protocols"], "PROTOCOL")
    for concept in value["concept_catalog"]:
        if not set(concept["source_refs"]) <= sources:
            raise ValueError("DANGLING_CONCEPT_SOURCE")
    for row in value["evidence_catalog"]:
        if not set(row["source_refs"]) <= sources:
            raise ValueError("DANGLING_EVIDENCE_SOURCE")
    for edge in value["relations"]:
        if edge["subject"] not in concepts or edge["object"] not in concepts:
            raise ValueError("DANGLING_RELATION")
    for rule in value["engineering_rules"]:
        if not set(rule["concept_refs"]) <= concepts:
            raise ValueError("DANGLING_RULE_CONCEPT")
    for row in value["worked_examples"]:
        if not set(row["concept_refs"]) <= concepts:
            raise ValueError("DANGLING_WORKED_EXAMPLE")
    for card in value.get("video_context", {}).get("claim_cards", []):
        if card["concept_ref"] not in concepts or not set(card["verification_source_refs"]) <= sources:
            raise ValueError("DANGLING_VIDEO_REFERENCE")
        if not 0 <= card["start_seconds"] < card["end_seconds"] <= value["video_context"]["original_duration_seconds"]:
            raise ValueError("VIDEO_TIME_RANGE_INVALID")
    if value["checkpoint"]["p_vs_np"] != "OPEN":
        raise ValueError("PROOF_STATUS_INFLATION")
    for field, choices in (("actions", ACTIONS), ("bases", BASES), ("claim_levels", LEVELS),
                           ("verification_states", VERIFICATION_STATES)):
        if set(value["structured_review_contract"][field]) != choices:
            raise ValueError("REVIEW_CONTRACT_DRIFT")


def validate_bundle(root=ROOT):
    pointer = json.loads((root / "registry/psychology/BECKER_TMT_CURRENT.json").read_bytes())
    raw = (root / pointer["path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != pointer["sha256"]:
        raise ValueError("ONTOLOGY_HASH_MISMATCH")
    value = json.loads(raw)
    validate_ontology(value)
    raw_projection = (root / pointer["engineering_projection"]).read_bytes()
    if hashlib.sha256(raw_projection).hexdigest() != pointer["projection_sha256"]:
        raise ValueError("PROJECTION_HASH_MISMATCH")
    projection = json.loads(raw_projection)
    if projection["canonical_source"]["sha256"] != pointer["sha256"]:
        raise ValueError("PROJECTION_SOURCE_MISMATCH")
    expected_rules = [{k: r[k] for k in ("id", "concept_refs", "statement_en")}
                      for r in value["engineering_rules"]]
    if (projection["boundaries"] != value["boundaries"] or projection["rules"] != expected_rules or
        projection["review_contract"] != value["structured_review_contract"]):
        raise ValueError("PROJECTION_SEMANTIC_DRIFT")
    return {"schema": "janus.psychology.becker_tmt.validation_receipt.v1", "status": "PASS",
            "ontology_sha256": pointer["sha256"], "projection_sha256": pointer["projection_sha256"],
            "concept_count": len(value["concept_catalog"]), "source_count": len(value["source_catalog"]),
            "authority_delta": 0, "psychological_theory_verified": False, "p_vs_np": "OPEN"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, help="Strict typed JSON proposal; never source-text instructions.")
    args = parser.parse_args()
    result = {"validation": validate_bundle()}
    if args.proposal:
        if args.proposal.stat().st_size > 64000:
            raise ValueError("PROPOSAL_TOO_LARGE")
        result["review"] = review_proposal(json.loads(args.proposal.read_bytes()))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
