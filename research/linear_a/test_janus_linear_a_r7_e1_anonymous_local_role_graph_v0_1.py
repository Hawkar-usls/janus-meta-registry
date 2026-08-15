#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import janus_linear_a_r7_e1_anonymous_local_role_graph_v0_1 as e1

SPEC_PATH = Path("data/JANUS-LINEAR-A-R7-E1-ANONYMOUS-LOCAL-ROLE-GRAPH-SPEC-2026-08-15-v0.1.json")


def spec():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def event(doc, oid, is_target, atoms, partition="holdout", pos="middle"):
    return {
        "doc": doc,
        "object_id": oid,
        "partition": partition,
        "word": e1.TARGET_TOKEN if is_target else "opaque-control",
        "is_target": is_target,
        "row": 2,
        "row_rank": 1,
        "row_count": 3,
        "position_bin": pos,
        "atoms": sorted(atoms),
    }


class R7E1Tests(unittest.TestCase):
    def test_spec_validates(self):
        out = e1.validate_spec(spec())
        self.assertEqual(out["status"], "R7_E1_PREREGISTRATION_VALIDATED")

    def test_object_split_is_deterministic_and_disjoint(self):
        ids = [f"HT{i}" for i in range(1, 500)]
        d = {x for x in ids if e1.partition_of_object(x) == "discovery"}
        h = {x for x in ids if e1.partition_of_object(x) == "holdout"}
        self.assertFalse(d & h)
        self.assertEqual(d | h, set(ids))
        self.assertTrue(d and h)
        for x in ids[:20]:
            self.assertEqual(e1.partition_of_object(x), e1.partition_of_object(x))

    def test_numeric_bins_ignore_magnitude(self):
        self.assertEqual(e1.count_bin(2), e1.count_bin(2000))
        self.assertEqual(e1.count_bin(0), "0")
        self.assertEqual(e1.count_bin(1), "1")
        self.assertEqual(e1.count_bin(2), "2PLUS")

    def test_discovery_selects_train_only_anonymous_profile_with_family_cap(self):
        events = []
        for i in range(10):
            doc = f"HTD{i}"
            oid = f"HTD{i}"
            target_atoms = {
                "SELF_NEXT_KIND=N",
                "SELF_SUFFIX_NUMERIC_COUNT=1",
                "SELF_END_KIND=N",
                "NEXT_ROW_NUMERIC_COUNT=1",
            }
            control_atoms = {
                "SELF_NEXT_KIND=W",
                "SELF_SUFFIX_NUMERIC_COUNT=0",
                "SELF_END_KIND=W",
                "NEXT_ROW_NUMERIC_COUNT=0",
            }
            events.append(event(doc, oid, True, target_atoms, partition="discovery"))
            events.append(event(doc, oid, False, control_atoms, partition="discovery"))
        with patch.object(e1, "build_events", return_value=events):
            result = e1.discovery(spec(), [], {"partition": "discovery"})
        self.assertEqual(result["status"], "E1_DISCOVERY_PROFILE_FROZEN_HOLDOUT_MAY_OPEN")
        self.assertGreaterEqual(len(result["selected_atom_ids"]), 2)
        families = [e1.atom_family(x) for x in result["selected_atom_ids"]]
        self.assertEqual(len(families), len(set(families)))
        self.assertFalse(result["holdout_content_parsed"])
        self.assertFalse(result["inference_claim_established"])

    def test_holdout_canary_passes_only_from_frozen_anonymous_atoms(self):
        s = spec()
        selected = ["SELF_NEXT_KIND=N", "NEXT_ROW_NUMERIC_COUNT=1"]
        freeze = {
            "status": "E1_DISCOVERY_PROFILE_FROZEN_HOLDOUT_MAY_OPEN",
            "spec_id": e1.SPEC_ID,
            "spec_sha256": e1.canonical_sha(s),
            "selected_atom_ids": selected,
            "selected_atoms": [{"atom_id": x} for x in selected],
        }
        events = []
        for i in range(8):
            doc = f"HTH{i}"
            oid = f"HTH{i}"
            events.append(event(doc, oid, True, set(selected)))
            events.append(event(doc, oid, False, {"SELF_NEXT_KIND=W", "NEXT_ROW_NUMERIC_COUNT=0"}))
        with patch.object(e1, "build_events", return_value=events):
            result = e1.holdout(s, freeze, [], {"partition": "holdout"})
        self.assertEqual(result["status"], "HELDOUT_ANONYMOUS_LOCAL_ROLE_PROFILE_REPLICATED")
        self.assertTrue(result["anonymous_local_role_profile_established"])
        self.assertGreaterEqual(result["effect_over_matched_null"], 0.15)
        self.assertLessEqual(result["raw_empirical_p"], 0.01)
        for key in e1.FALSE_CLAIMS:
            self.assertFalse(result[key])

    def test_holdout_canary_rejects_reversed_profile(self):
        s = spec()
        selected = ["SELF_NEXT_KIND=N", "NEXT_ROW_NUMERIC_COUNT=1"]
        freeze = {
            "status": "E1_DISCOVERY_PROFILE_FROZEN_HOLDOUT_MAY_OPEN",
            "spec_id": e1.SPEC_ID,
            "spec_sha256": e1.canonical_sha(s),
            "selected_atom_ids": selected,
            "selected_atoms": [{"atom_id": x} for x in selected],
        }
        events = []
        for i in range(8):
            doc = f"HTN{i}"
            oid = f"HTN{i}"
            events.append(event(doc, oid, True, {"SELF_NEXT_KIND=W", "NEXT_ROW_NUMERIC_COUNT=0"}))
            events.append(event(doc, oid, False, set(selected)))
        with patch.object(e1, "build_events", return_value=events):
            result = e1.holdout(s, freeze, [], {"partition": "holdout"})
        self.assertEqual(result["status"], "ANONYMOUS_LOCAL_ROLE_PROFILE_NOT_ESTABLISHED_RETAIN_ROW-OPENING-LIKE")
        self.assertFalse(result["anonymous_local_role_profile_established"])


if __name__ == "__main__":
    unittest.main()
