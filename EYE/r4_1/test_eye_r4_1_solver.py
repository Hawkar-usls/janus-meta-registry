#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "eye_r4_1_minimum_witness_set_solver",
    HERE / "eye_r4_1_minimum_witness_set_solver.py",
)
assert SPEC and SPEC.loader
solver = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = solver
SPEC.loader.exec_module(solver)


class EyeR41SolverTests(unittest.TestCase):
    def parse(self, model):
        return solver.parse(model)

    def run_search(self, model):
        causes, witnesses, requirements, acquired = self.parse(model)
        return causes, witnesses, requirements, acquired, solver.search(causes, witnesses, requirements, acquired)

    def test_known_minimum(self):
        model = json.loads((HERE / "benchmarks/synthetic_known_minimum.json").read_text())
        causes, witnesses, req, acquired, search = self.run_search(model)
        self.assertEqual(search["status"], "EXACT_MINIMUM_FOUND")
        best = search["solutions"][0]
        self.assertEqual(best - acquired, frozenset({"t_temporal", "t_geometry"}))
        self.assertEqual(solver.cost(best, witnesses, acquired), 3.0)

    def test_dependency_cost_is_not_hidden(self):
        model = {
            "cause_classes": ["A", "B"],
            "tests": [
                {
                    "id": "cheap_probe",
                    "cost": 1,
                    "depends_on": ["expensive_calibration"],
                    "failure_domains": ["probe"],
                    "distinguishes": [["A", "B"]],
                },
                {
                    "id": "expensive_calibration",
                    "cost": 9,
                    "failure_domains": ["cal"],
                    "distinguishes": [],
                },
                {
                    "id": "direct_test",
                    "cost": 5,
                    "failure_domains": ["direct"],
                    "distinguishes": [["A", "B"]],
                },
            ],
        }
        causes, witnesses, req, acquired, search = self.run_search(model)
        best = search["solutions"][0]
        self.assertEqual(best - acquired, frozenset({"direct_test"}))
        self.assertEqual(solver.cost(best, witnesses, acquired), 5.0)

    def test_shared_failure_domain_does_not_fake_two_independent_witnesses(self):
        model = {
            "cause_classes": ["A", "B"],
            "requirements": {"required_independent_separators_per_pair": 2},
            "tests": [
                {
                    "id": "cam1",
                    "cost": 1,
                    "failure_domains": ["shared_pipeline"],
                    "distinguishes": [["A", "B"]],
                },
                {
                    "id": "cam2",
                    "cost": 1,
                    "failure_domains": ["shared_pipeline"],
                    "distinguishes": [["A", "B"]],
                },
                {
                    "id": "orthogonal",
                    "cost": 2,
                    "failure_domains": ["independent_physics"],
                    "distinguishes": [["A", "B"]],
                },
            ],
        }
        causes, witnesses, req, acquired, search = self.run_search(model)
        best = search["solutions"][0]
        self.assertEqual(solver.cost(best, witnesses, acquired), 3.0)
        self.assertIn("orthogonal", best)
        self.assertEqual(len(best), 2)

    def test_unavailable_required_separator_yields_non_identifiable(self):
        model = {
            "cause_classes": ["A", "B"],
            "tests": [
                {
                    "id": "only_separator",
                    "cost": 1,
                    "available": False,
                    "failure_domains": ["x"],
                    "distinguishes": [["A", "B"]],
                }
            ],
        }
        *_, search = self.run_search(model)
        self.assertEqual(
            search["status"],
            "NON_IDENTIFIABLE_UNDER_CURRENT_MEASUREMENT_MODEL",
        )

    def test_resource_ceiling_is_unknown_not_negative(self):
        model = {
            "cause_classes": ["A", "B"],
            "requirements": {"max_exact_tests": 1},
            "tests": [
                {"id": "t1", "cost": 1, "failure_domains": ["x"], "distinguishes": [["A", "B"]]},
                {"id": "t2", "cost": 1, "failure_domains": ["y"], "distinguishes": [["A", "B"]]},
            ],
        }
        *_, search = self.run_search(model)
        self.assertEqual(search["status"], "UNKNOWN_RESOURCE_LIMIT")
        self.assertFalse(search["exact"])


if __name__ == "__main__":
    unittest.main()
