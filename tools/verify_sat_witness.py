#!/usr/bin/env python3
"""Offline SAT-witness verifier. Does NOT solve SAT or verify UNSAT.

Treat input CNFs and candidate assignments as untrusted data. Never imports,
executes or unpickles any historical solver artifact. Bounded to 8 MiB.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

MAX_BYTES = 8_000_000
MAX_VARIABLES = 10_000
MAX_CLAUSES = 100_000
SCHEMA = "janus.sat_reproducibility.sat_witness.v1"


class InvalidWitness(ValueError):
    pass


def parse_3cnf(data: bytes) -> tuple[int, list[tuple[int, int, int]]]:
    if not data or len(data) > MAX_BYTES:
        raise InvalidWitness("empty or oversized DIMACS file")
    try:
        source = data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise InvalidWitness("DIMACS must be ASCII") from exc
    header = None
    clauses = []
    pending = []
    for lineno, raw in enumerate(source.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("c"):
            continue
        if line.startswith("p"):
            if header is not None or pending or clauses:
                raise InvalidWitness("multiple or misplaced header")
            parts = line.split()
            if len(parts) != 4 or parts[:2] != ["p", "cnf"]:
                raise InvalidWitness("header must be: p cnf N M")
            if not all(re.fullmatch(r"[0-9]+", x) for x in parts[2:]):
                raise InvalidWitness("invalid DIMACS header numbers")
            n, m = map(int, parts[2:])
            if not (1 <= n <= MAX_VARIABLES and 1 <= m <= MAX_CLAUSES):
                raise InvalidWitness("DIMACS resource bound")
            header = n, m
            continue
        if header is None:
            raise InvalidWitness(f"clause before header, line {lineno}")
        if len(clauses) >= header[1] and line:
            raise InvalidWitness("excess tokens after declared clauses")
        for token in line.split():
            if not re.fullmatch(r"-?[0-9]+", token):
                raise InvalidWitness(f"invalid literal at line {lineno}")
            literal = int(token)
            if literal == 0:
                if len(pending) != 3:
                    raise InvalidWitness("expected exactly three literals per clause")
                if len({abs(x) for x in pending}) != 3:
                    raise InvalidWitness("repeated or complementary variables in clause")
                clauses.append(tuple(pending))
                pending = []
                if len(clauses) > header[1]:
                    raise InvalidWitness("excess clauses")
            else:
                if abs(literal) > header[0]:
                    raise InvalidWitness("out-of-bounds variable")
                pending.append(literal)
                if len(pending) > 3:
                    raise InvalidWitness("clause longer than 3 literals")
    if header is None:
        raise InvalidWitness("missing DIMACS header")
    if pending:
        raise InvalidWitness("unterminated final clause")
    if len(clauses) != header[1]:
        raise InvalidWitness("declared clause count mismatch")
    return header[0], clauses


def verify_sat(cnf_bytes: bytes, witness: dict) -> dict:
    n, clauses = parse_3cnf(cnf_bytes)
    if not isinstance(witness, dict) or witness.get("schema") != SCHEMA:
        raise InvalidWitness("wrong witness schema")
    if witness.get("verdict") != "SAT":
        raise InvalidWitness("UNSAT and UNKNOWN are not SAT certificates")
    source_hash = hashlib.sha256(cnf_bytes).hexdigest()
    if witness.get("instance_sha256") != source_hash:
        raise InvalidWitness("source CNF SHA-256 mismatch")
    literals = witness.get("literals")
    if not isinstance(literals, list) or len(literals) != n:
        raise InvalidWitness("assignment must provide one literal per variable")
    assignment = {}
    for lit in literals:
        if type(lit) is not int or not (1 <= abs(lit) <= n):
            raise InvalidWitness("nonintegral or out-of-range witness literal")
        v = abs(lit)
        if v in assignment:
            raise InvalidWitness("duplicate variable assignment")
        assignment[v] = lit > 0
    if len(assignment) != n:
        raise InvalidWitness("incomplete assignment")
    for index, clause in enumerate(clauses):
        if not any(assignment[abs(lit)] == (lit > 0) for lit in clause):
            raise InvalidWitness(f"unsatisfied clause index={index}")
    return {
        "schema": "janus.sat_reproducibility.witness_verification.v1",
        "status": "VERIFIED_SAT_ASSIGNMENT_ONLY",
        "instance_sha256": source_hash,
        "n_variables": n,
        "n_clauses": len(clauses),
        "solver_provenance_attested": False,
        "scientific_authority_delta": 0,
        "proof_of_unsatisfiability": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cnf", type=Path, required=True)
    parser.add_argument("--witness", type=Path, required=True)
    args = parser.parse_args()
    try:
        cnf = args.cnf.read_bytes()
        if len(cnf) > MAX_BYTES:
            raise InvalidWitness("oversized input")
        raw = args.witness.read_bytes()
        if len(raw) > MAX_BYTES:
            raise InvalidWitness("oversized witness")
        witness = json.loads(raw)
        report = verify_sat(cnf, witness)
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        print(json.dumps({"status": "INVALID_SAT_ASSIGNMENT",
                          "error": str(exc), "scientific_authority_delta": 0}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
