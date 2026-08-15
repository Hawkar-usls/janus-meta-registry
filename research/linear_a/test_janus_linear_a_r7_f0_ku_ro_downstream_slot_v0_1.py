#!/usr/bin/env python3
from __future__ import annotations

import json
import random
import unittest
from collections import Counter
from pathlib import Path

import janus_linear_a_r7_f0_ku_ro_downstream_slot_v0_1 as f0

SPEC_PATH = Path("data/JANUS-LINEAR-A-R7-F0-KU-RO-DOWNSTREAM-SLOT-SPEC-2026-08-15-v0.1.json")


def spec():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def event(doc, oid, target, bundle):
    return {
        "doc": doc,
        "object_id": oid,
        "is_target": target,
        "word": f0.TARGET_TOKEN if target else "opaque-control",
        "row": 1,
        "bundle": tuple(bundle),
    }


class R7F0Tests(unittest.TestCase):
    def test_spec_validates_and_channel_family_is_exact(self):
        out = f0.validate_spec(spec())
        self.assertEqual(out["status"], "R7_F0_PREREGISTRATION_VALIDATED")
        self.assertEqual(tuple(spec()["channels"].keys()), f0.CHANNELS)

    def test_tail_bundle_uses_only_downstream_same_row_structure(self):
        seq = [
            {"kind": "N"},
            {"kind": "W", "word": f0.TARGET_TOKEN},
            {"kind": "W", "word": "opaque-next"},
            {"kind": "N"},
        ]
        got = f0.tail_bundle(seq, [0, 1, 2, 3], 1)
        self.assertEqual(got, ("W", "W:opaque-next", "W|N"))
        self.assertEqual(f0.tail_bundle(seq, [0, 1], 1), ("END", "END", "END|END"))

    def test_lopo_information_gain_rewards_target_specific_downstream_kind(self):
        events = []
        for i in range(4):
            oid = f"O{i}"
            events.append(event(f"T{i}", oid, True, ("N", "N", "N|END")))
            events.append(event(f"C{i}", oid, False, ("W", f"W:c{i}", "W|END")))
        bundles = [e["bundle"] for e in events]
        result = f0.score_assignment(events, bundles, "NEXT_KIND")
        self.assertGreater(result["mean_information_gain_bits"], 0.0)
        self.assertEqual(result["positive_target_object_fraction"], 1.0)

    def test_heldout_object_background_is_excluded_from_its_own_model(self):
        events = []
        for i in range(3):
            oid = f"O{i}"
            events.append(event(f"T{i}", oid, True, ("N", "N", "N|END")))
            events.append(event(f"C{i}", oid, False, ("W", f"W:c{i}", "W|END")))
        original = [e["bundle"] for e in events]
        a = f0.score_assignment(events, original, "NEXT_KIND")
        changed = list(original)
        # Change only O0's non-target downstream signature. O0's own heldout model must not use it.
        changed[1] = ("N", "N", "N|END")
        b = f0.score_assignment(events, changed, "NEXT_KIND")
        a0 = next(x for x in a["target_object_scores"] if x["object_id"] == "O0")
        b0 = next(x for x in b["target_object_scores"] if x["object_id"] == "O0")
        self.assertAlmostEqual(a0["information_gain_bits"], b0["information_gain_bits"], places=14)

    def test_lexicalized_channel_maps_unseen_heldout_lexeme_to_UNK(self):
        events = [
            event("T0", "O0", True, ("W", "W:heldout-only", "W|END")),
            event("C0", "O0", False, ("N", "N", "N|END")),
            event("T1", "O1", True, ("W", "W:train-a", "W|END")),
            event("C1", "O1", False, ("W", "W:train-b", "W|END")),
            event("T2", "O2", True, ("W", "W:train-a", "W|END")),
            event("C2", "O2", False, ("W", "W:train-b", "W|END")),
        ]
        result = f0.score_assignment(events, [e["bundle"] for e in events], "NEXT_LEX_OR_KIND")
        row = next(x for x in result["target_event_scores"] if x["object_id"] == "O0")
        self.assertEqual(row["model_signature"], "W:<UNK>")

    def test_structure_destroying_null_preserves_each_object_tail_multiset(self):
        events = [
            event("A", "O0", True, ("N", "N", "N|END")),
            event("B", "O0", False, ("W", "W:b", "W|END")),
            event("C", "O0", False, ("X", "X", "X|END")),
            event("D", "O1", True, ("END", "END", "END|END")),
            event("E", "O1", False, ("N", "N", "N|N")),
        ]
        original = [e["bundle"] for e in events]
        by_object = f0.object_index_map(events)
        shuffled = f0.permuted_bundles(original, by_object, random.Random(123))
        for oid, indices in by_object.items():
            self.assertEqual(Counter(original[i] for i in indices), Counter(shuffled[i] for i in indices))

    def test_holm_adjustment_is_monotone_and_familywise(self):
        out = f0.holm_adjusted({"A": 0.001, "B": 0.006, "C": 0.03})
        self.assertAlmostEqual(out["A"], 0.003)
        self.assertAlmostEqual(out["B"], 0.012)
        self.assertAlmostEqual(out["C"], 0.03)


if __name__ == "__main__":
    unittest.main()
