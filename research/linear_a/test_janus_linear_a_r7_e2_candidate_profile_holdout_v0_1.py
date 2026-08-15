#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

import janus_linear_a_r7_e2_candidate_profile_holdout_v0_1 as e2

SPEC_PATH = Path("data/JANUS-LINEAR-A-R7-E2-CANDIDATE-PROFILE-HOLDOUT-SPEC-2026-08-15-v0.1.json")


def spec():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def event(doc, oid, is_target, atoms, row_count=6, position="middle"):
    return {
        "doc": doc,
        "object_id": oid,
        "partition": "holdout",
        "word": e2.TARGET_TOKEN if is_target else "opaque-control",
        "is_target": is_target,
        "row": 3,
        "row_rank": 2,
        "row_count": row_count,
        "position_bin": position,
        "atoms": sorted(atoms),
    }


def control_events(profile_positive: bool):
    atoms = set(e2.CANDIDATE_ATOMS) if profile_positive else set()
    rows = []
    for i in range(10):
        for j in range(2):
            rows.append(event(f"HTC{i}_{j}", f"HTC{i}", False, atoms))
    return rows


class R7E2Tests(unittest.TestCase):
    def test_spec_validates(self):
        out = e2.validate_spec(spec())
        self.assertEqual(out["status"], "R7_E2_PREREGISTRATION_VALIDATED")

    def test_document_row_count_bins_are_frozen(self):
        self.assertEqual(e2.document_row_count_bin(1), "1-4")
        self.assertEqual(e2.document_row_count_bin(4), "1-4")
        self.assertEqual(e2.document_row_count_bin(5), "5-9")
        self.assertEqual(e2.document_row_count_bin(9), "5-9")
        self.assertEqual(e2.document_row_count_bin(10), "10PLUS")

    def test_profile_uses_exactly_two_frozen_atoms(self):
        self.assertEqual(e2.profile_score(event("D", "O", True, set())), 0.0)
        self.assertEqual(e2.profile_score(event("D", "O", True, {e2.CANDIDATE_ATOMS[0]})), 0.5)
        self.assertEqual(e2.profile_score(event("D", "O", True, set(e2.CANDIDATE_ATOMS))), 1.0)

    def test_strong_heldout_replication_passes(self):
        events = control_events(False)
        for i in range(8):
            events.append(event(f"HTT{i}", f"HTT{i}", True, set(e2.CANDIDATE_ATOMS)))
        result = e2.evaluate_events(spec(), events, {"partition": "holdout"})
        self.assertEqual(result["status"], "HELDOUT_DENSE_PREDECESSOR_PROFILE_REPLICATED")
        self.assertTrue(result["heldout_structural_context_refinement_established"])
        self.assertEqual(result["eligible_target_events"], 8)
        self.assertEqual(result["eligible_target_physical_objects"], 8)
        self.assertEqual(result["observed_object_weighted_profile_effect"], 1.0)
        self.assertLessEqual(result["signflip"]["p"], 0.01)
        self.assertTrue(all(v > 0 for v in result["frozen_atom_object_weighted_effects"].values()))
        for key in e2.FALSE_CLAIMS:
            self.assertFalse(result[key])

    def test_reversed_profile_fails_without_revoking_parent(self):
        events = control_events(True)
        for i in range(8):
            events.append(event(f"HTT{i}", f"HTT{i}", True, set()))
        result = e2.evaluate_events(spec(), events, {"partition": "holdout"})
        self.assertEqual(result["status"], "E2_CANDIDATE_PROFILE_NOT_REPLICATED_RETAIN_ROW-OPENING-LIKE")
        self.assertFalse(result["heldout_structural_context_refinement_established"])
        self.assertLess(result["observed_object_weighted_profile_effect"], 0)
        self.assertFalse(result["frozen_atom_direction_pass"])

    def test_underpowered_support_cannot_pass_even_with_perfect_effect(self):
        events = control_events(False)
        for i in range(6):
            events.append(event(f"HTT{i}", f"HTT{i}", True, set(e2.CANDIDATE_ATOMS)))
        result = e2.evaluate_events(spec(), events, {"partition": "holdout"})
        self.assertEqual(result["status"], "E2_HOLDOUT_UNDERPOWERED_RETAIN_ROW-OPENING-LIKE")
        self.assertFalse(result["support_pass"])
        self.assertFalse(result["heldout_structural_context_refinement_established"])

    def test_target_bearing_objects_are_never_controls(self):
        events = control_events(False)
        # Add a non-target event on every target-bearing object; it must not inflate control count.
        for i in range(8):
            oid = f"HTT{i}"
            events.append(event(f"HTT{i}", oid, True, set(e2.CANDIDATE_ATOMS)))
            events.append(event(f"HTT{i}_control", oid, False, set()))
        result = e2.evaluate_events(spec(), events, {"partition": "holdout"})
        self.assertEqual(result["pure_control_physical_objects"], 10)
        self.assertEqual(result["pure_control_events"], 20)

    def test_control_object_weighting_prevents_long_object_domination(self):
        controls = []
        # Nine objects score 0; one long object scores 1 many times. Object weighting => 0.1, not event weighting.
        for i in range(9):
            controls.extend([event(f"C{i}_{j}", f"C{i}", False, set()) for j in range(2)])
        controls.extend([event(f"LONG_{j}", "LONG", False, set(e2.CANDIDATE_ATOMS)) for j in range(50)])
        mean, n_events, n_objects = e2.object_weighted_control_mean(controls, e2.profile_score)
        self.assertEqual(n_objects, 10)
        self.assertEqual(n_events, 68)
        self.assertAlmostEqual(mean, 0.1)


if __name__ == "__main__":
    unittest.main()
