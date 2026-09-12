#!/usr/bin/env python3
"""JANUS Fresco Forge v4.1.1 hotfix.

Distinguishes logical/workflow gates from physical architectural gates.
A field named `gate` remains a system/control concept unless descriptive
narrative explicitly establishes physical architecture such as an airlock,
hatch, chamber, threshold, door, decompression, or vacuum.
"""
from __future__ import annotations

from collections import Counter

import forge as base
import v4_1_runner as prev

GENERATOR_VERSION = "JANUS-FRESCO-FORGE-v4.1.1-physical-gate-firewall"

PHYSICAL_ARCH_WORDS = {
    "airlock", "hatch", "chamber", "corridor", "threshold", "door", "vault",
    "decompression", "vacuum", "bulkhead", "passage", "vestibule",
}


def infer_scene_archetype(audit: list[dict]) -> tuple[str, dict]:
    scores = Counter()
    corpus = " ".join(str(x.get("value", "")) for x in audit)

    for fact in audit:
        role = fact["field_role"]
        value = str(fact.get("value", ""))

        if role == "PERSON_OR_MYTHIC_ENTITY":
            scores["HUMAN_NARRATIVE"] += 5
        if role == "DESCRIPTIVE_NARRATIVE" and prev.has_any(value, prev.MYTHIC_WORDS):
            scores["MYTHIC_NARRATIVE"] += 6

        if role == "SYSTEM_COMPONENT":
            scores["SYSTEM_ALLEGORY"] += 3
        if prev.has_any(value, prev.SYSTEM_WORDS):
            scores["SYSTEM_ALLEGORY"] += 2

        # Critical firewall: a JSON key/value named `gate` is not physical architecture.
        # Architectural evidence must come from an environment field or descriptive prose
        # that explicitly contains physical-architecture vocabulary.
        if role == "ENVIRONMENT_OR_ARCHITECTURE":
            scores["ARCHITECTURAL_EVENT"] += 4
        elif role == "DESCRIPTIVE_NARRATIVE" and prev.has_any(value, PHYSICAL_ARCH_WORDS):
            scores["ARCHITECTURAL_EVENT"] += 5

        if role == "OBJECT_OR_ARTIFACT":
            scores["OBJECT_RITUAL"] += 3
        if prev.has_any(value, prev.RITUAL_WORDS):
            scores["OBJECT_RITUAL"] += 2

    people = prev.explicit_person_evidence(audit)
    if not people:
        scores["HUMAN_NARRATIVE"] = 0
        scores["MYTHIC_NARRATIVE"] = 0

    order = ["MYTHIC_NARRATIVE", "HUMAN_NARRATIVE", "ARCHITECTURAL_EVENT", "SYSTEM_ALLEGORY", "OBJECT_RITUAL"]
    archetype = max(order, key=lambda x: (scores[x], -order.index(x)))
    if scores[archetype] == 0:
        archetype = "SYSTEM_ALLEGORY" if prev.has_any(corpus, prev.SYSTEM_WORDS) else "OBJECT_RITUAL"
    return archetype, dict(scores)


# Monkeypatch the v4.1 scene builder at runtime. build_scene_plan() resolves this
# module-global function dynamically, so prev.generate_one receives the corrected
# archetype without duplicating the full renderer/receipt implementation.
prev.infer_scene_archetype = infer_scene_archetype
prev.GENERATOR_VERSION = GENERATOR_VERSION
base.GENERATOR_VERSION = GENERATOR_VERSION
base.create_pipeline = prev.v3.create_pipeline
base.generate_one = prev.generate_one

if __name__ == "__main__":
    raise SystemExit(base.main())
