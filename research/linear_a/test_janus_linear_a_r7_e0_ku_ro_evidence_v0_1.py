#!/usr/bin/env python3
from __future__ import annotations

import unittest
from fractions import Fraction

import janus_linear_a_r7_e0_ku_ro_evidence_v0_1 as e0


def item(kind, row, value=None, word=None, word_index=None):
    out = {"kind": kind, "rows": [row]}
    if value is not None:
        out["value"] = value
    if word is not None:
        out["word"] = word
    if word_index is not None:
        out["word_index"] = word_index
    return out


class R7E0ExecutionOperatorTests(unittest.TestCase):
    def test_kind_distance_is_identity_blind_and_normalized(self):
        self.assertEqual(e0.normalized_kind_distance(list("WN"), list("WN")), 0.0)
        self.assertAlmostEqual(e0.normalized_kind_distance(list("WN"), list("WNN")), 1 / 3)
        self.assertEqual(e0.normalized_kind_distance(list("WW"), list("NN")), 1.0)

    def test_exact_arithmetic_local_contiguous_prefix_match(self):
        seq = [
            item("W", 1, word="control", word_index=0),
            item("N", 1, Fraction(2, 1)),
            item("N", 1, Fraction(3, 1)),
            item("N", 2, Fraction(5, 1)),
            item("W", 2, word=e0.TARGET_TOKEN, word_index=4),
            item("N", 2, Fraction(10, 1)),
        ]
        event = {
            "doc": "HTTEST",
            "object_id": "HTTEST",
            "status": "certain",
            "is_target": True,
            "row": 2,
            "row_rank": 1,
            "row_count": 2,
            "seq_index": 4,
            "doc_record": {"doc": "HTTEST", "sequence": seq},
            "rows": {1: [0, 1, 2], 2: [3, 4, 5]},
            "row_order": [1, 2],
        }
        rec = e0.arithmetic_record(event)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["score"], 1.0)
        self.assertEqual(rec["audit"]["prior_exact_sum"], "10")
        self.assertEqual(rec["audit"]["following_exact_value"], "10")

    def test_arithmetic_unknown_numeric_makes_event_ineligible(self):
        seq = [
            item("X", 1),
            item("N", 1, Fraction(3, 1)),
            item("N", 2, Fraction(5, 1)),
            item("W", 2, word=e0.TARGET_TOKEN, word_index=3),
            item("N", 2, Fraction(8, 1)),
        ]
        event = {
            "doc": "HTTEST",
            "object_id": "HTTEST",
            "status": "none",
            "is_target": True,
            "row": 2,
            "row_rank": 1,
            "row_count": 2,
            "seq_index": 3,
            "doc_record": {"doc": "HTTEST", "sequence": seq},
            "rows": {1: [0, 1], 2: [2, 3, 4]},
            "row_order": [1, 2],
        }
        self.assertIsNone(e0.arithmetic_record(event))

    def test_accounting_block_stops_at_non_numeric_row(self):
        seq = [
            item("N", 1, Fraction(100, 1)),
            item("W", 2, word="separator", word_index=1),
            item("N", 3, Fraction(2, 1)),
            item("N", 3, Fraction(3, 1)),
            item("W", 4, word=e0.TARGET_TOKEN, word_index=4),
            item("N", 4, Fraction(5, 1)),
        ]
        event = {
            "doc": "HTTEST",
            "object_id": "HTTEST",
            "status": "none",
            "is_target": True,
            "row": 4,
            "row_rank": 3,
            "row_count": 4,
            "seq_index": 4,
            "doc_record": {"doc": "HTTEST", "sequence": seq},
            "rows": {1: [0], 2: [1], 3: [2, 3], 4: [4, 5]},
            "row_order": [1, 2, 3, 4],
        }
        rec = e0.arithmetic_record(event)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["score"], 1.0)
        self.assertEqual(rec["audit"]["prior_exact_sum"], "5")

    def test_boundary_score_excludes_target_row_shape_and_identity(self):
        seq = [
            item("W", 1, word="a", word_index=0), item("N", 1, Fraction(1)),
            item("W", 2, word=e0.TARGET_TOKEN, word_index=2), item("N", 2, Fraction(2)),
            item("W", 3, word="b", word_index=4), item("N", 3, Fraction(3)), item("N", 3, Fraction(4)),
        ]
        event = {
            "doc": "HTTEST", "object_id": "HTTEST", "status": "certain", "is_target": True,
            "row": 2, "row_rank": 1, "row_count": 3, "seq_index": 2,
            "doc_record": {"doc": "HTTEST", "sequence": seq},
            "rows": {1: [0, 1], 2: [2, 3], 3: [4, 5, 6]}, "row_order": [1, 2, 3],
        }
        rec1 = e0.boundary_record(event)
        self.assertAlmostEqual(rec1["score"], 1 / 3)
        seq[2]["word"] = "COMPLETELY_DIFFERENT_OPAQUE_ID"
        seq.insert(3, item("W", 2, word="extra", word_index=99))
        event["rows"] = {1: [0, 1], 2: [2, 3, 4], 3: [5, 6, 7]}
        event["doc_record"]["sequence"] = seq
        rec2 = e0.boundary_record(event)
        self.assertAlmostEqual(rec2["score"], rec1["score"])

    def test_position_bins_are_predeclared_thirds(self):
        self.assertEqual(e0.position_bin(0, 9), "early")
        self.assertEqual(e0.position_bin(3, 9), "middle")
        self.assertEqual(e0.position_bin(8, 9), "late")


if __name__ == "__main__":
    unittest.main()
