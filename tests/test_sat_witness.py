"""Bounded, offline, adversarial tests for independent positive SAT witnesses."""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from verify_sat_witness import InvalidWitness, parse_3cnf, verify_sat, SCHEMA  # noqa: E402


CNF = b"c synthetic test only\np cnf 3 2\n1 -2 3 0\n-1 2 3 0\n"


def witness(literals=(1, 2, 3)):
    return {"schema": SCHEMA, "verdict": "SAT",
            "instance_sha256": hashlib.sha256(CNF).hexdigest(),
            "literals": list(literals)}


class SATWitnessValidation(unittest.TestCase):
    def test_synthetic_valid_sat_assignment(self):
        r = verify_sat(CNF, witness())
        self.assertEqual(r["status"], "VERIFIED_SAT_ASSIGNMENT_ONLY")
        self.assertEqual(r["n_variables"], 3)
        self.assertEqual(r["n_clauses"], 2)
        self.assertFalse(r["solver_provenance_attested"])
        self.assertFalse(r["proof_of_unsatisfiability"])
        self.assertEqual(r["scientific_authority_delta"], 0)

    def test_unverified_unsat_not_converted_to_proof(self):
        w = witness()
        w["verdict"] = "UNSAT"
        with self.assertRaises(InvalidWitness):
            verify_sat(CNF, w)

    def test_wrong_assignment_rejected(self):
        with self.assertRaisesRegex(InvalidWitness, "unsatisfied clause"):
            verify_sat(CNF, witness((-1, 2, -3)))

    def test_missing_or_duplicate_assignment_rejected(self):
        for lits in ((1, 2), (1, 1, 3), (1, 2, 4), (1, True, 3)):
            with self.subTest(lits=lits), self.assertRaises(InvalidWitness):
                verify_sat(CNF, witness(lits))

    def test_instance_hash_mismatch_rejected(self):
        w = witness()
        w["instance_sha256"] = "0"*64
        with self.assertRaisesRegex(InvalidWitness, "SHA-256 mismatch"):
            verify_sat(CNF, w)

    def test_extra_invalid_clause_rejected(self):
        for cnf in (b"p cnf 3 1\n1 2 3 0\n1 -2 3 0\n",
                    b"p cnf 3 1\n1 2 3\n",
                    b"p cnf 3 1\n1 1 2 0\n",
                    b"p cnf 3 1\n1 -1 2 0\n",
                    b"p cnf 3 1\n1 2 4 0\n",
                    b"p cnf 3 1\n1 2 3 4 0\n"):
            with self.subTest(cnf=cnf), self.assertRaises(InvalidWitness):
                parse_3cnf(cnf)

    def test_absent_header_and_non_ascii_rejected(self):
        with self.assertRaises(InvalidWitness):
            parse_3cnf(b"1 2 3 0\n")
        with self.assertRaises(InvalidWitness):
            parse_3cnf(b"p cnf 3 1\n1 2 \xff 0\n")

    def test_clause_across_lines_is_valid_DIMACS(self):
        n, clauses = parse_3cnf(b"p cnf 3 1\n1 -2\n3 0\n")
        self.assertEqual(n, 3)
        self.assertEqual(clauses, [(1, -2, 3)])

    def test_untrusted_model_code_never_loaded(self):
        source = (ROOT / "tools/verify_sat_witness.py").read_text()
        for forbidden in ("pickle.load", "torch.load", "exec(", "eval(",
                          "subprocess", "importlib", "urllib.request"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
