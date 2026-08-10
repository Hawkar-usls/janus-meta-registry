#!/usr/bin/env python3
import argparse
import copy
import json
from pathlib import Path

PASS = "PASS"
REJECT = "REJECT"

class VerificationError(Exception):
    pass

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def evidence_index(spec):
    return {item["id"]: item for item in spec["evidence"]}

def claim_index(spec):
    return {item["id"]: item for item in spec["claims"]}

def apply_mutations(selected, mutations):
    selected = copy.deepcopy(selected)
    idx = {e["id"]: e for e in selected}
    for m in mutations or []:
        if m["evidence_id"] not in idx:
            raise VerificationError(f"unknown evidence in mutation: {m['evidence_id']}")
        idx[m["evidence_id"]][m["field"]] = m["value"]
    return selected

def verify_claim(spec, claim_id, evidence_ids, mutations=None):
    evid = evidence_index(spec)
    claims = claim_index(spec)
    if claim_id not in claims:
        raise VerificationError(f"unknown claim: {claim_id}")

    unknown = [eid for eid in evidence_ids if eid not in evid]
    if unknown:
        raise VerificationError(f"unknown evidence ids: {unknown}")

    selected = apply_mutations([evid[eid] for eid in evidence_ids], mutations)

    inadmissible = [
        e["id"] for e in selected
        if not e.get("authentic", False) or not e.get("source_bound", False)
    ]
    admissible = [e for e in selected if e["id"] not in inadmissible]

    established_by = {}
    for e in admissible:
        for atom in e.get("establishes", []):
            established_by.setdefault(atom, []).append(e["id"])

    claim = claims[claim_id]
    established = set(established_by)
    blocking = [a for a in claim.get("blocking_atoms", []) if a in established]

    missing_all = [a for a in claim.get("required_atoms", []) if a not in established]
    required_any = claim.get("required_atoms_any", [])
    missing_any = bool(required_any) and not any(a in established for a in required_any)

    reasons = []
    if inadmissible:
        reasons.append({
            "code": "INADMISSIBLE_EVIDENCE",
            "evidence_ids": inadmissible,
            "detail": "Evidence must be authentic and source-bound before it can establish any proposition."
        })
    if missing_all:
        reasons.append({
            "code": "MISSING_REQUIRED_ATOMS",
            "atoms": missing_all
        })
    if missing_any:
        reasons.append({
            "code": "NO_DIRECT_SUPPORT_FOR_ANY_REQUIRED_ALTERNATIVE",
            "atoms": required_any
        })
    if blocking:
        reasons.append({
            "code": "BLOCKING_COUNTEREVIDENCE",
            "atoms": blocking,
            "established_by": {a: established_by[a] for a in blocking}
        })

    result = PASS if not reasons else REJECT
    return {
        "claim": claim_id,
        "result": result,
        "evidence_ids": evidence_ids,
        "admissible_evidence_ids": [e["id"] for e in admissible],
        "inadmissible_evidence_ids": inadmissible,
        "established_atoms": sorted(established),
        "established_by": established_by,
        "blocking_atoms_present": blocking,
        "reasons": reasons,
        "invariants": {
            "OBJECT_AUTHENTICITY_NEVER_IMPLIES_CLAIM_TRUTH": True,
            "NO_IMPLICIT_ENTAILMENT": bool(spec["model"].get("no_implicit_entailment", False)),
            "SOURCE_BINDING_REQUIRED": True
        }
    }

def run_case(spec, case):
    return verify_claim(
        spec,
        case["claim"],
        case["evidence_ids"],
        case.get("mutations")
    )

def run_self_test(spec):
    rows = []
    ok = True
    for case in spec.get("test_cases", []):
        receipt = run_case(spec, case)
        passed = receipt["result"] == case["expected"]
        rows.append({
            "case": case["id"],
            "expected": case["expected"],
            "actual": receipt["result"],
            "test": PASS if passed else REJECT
        })
        ok = ok and passed
    return {
        "result": PASS if ok else REJECT,
        "tests": rows
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--spec", required=True)
    p.add_argument("--case")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--pretty", action="store_true")
    args = p.parse_args()

    spec = load_json(args.spec)
    if args.self_test:
        out = run_self_test(spec)
    elif args.case:
        matches = [c for c in spec.get("test_cases", []) if c["id"] == args.case]
        if not matches:
            raise SystemExit(f"unknown case: {args.case}")
        out = run_case(spec, matches[0])
    else:
        raise SystemExit("use --self-test or --case CASE_ID")

    print(json.dumps(out, ensure_ascii=False, indent=2 if args.pretty else None))
    raise SystemExit(0 if out["result"] == PASS else 1)

if __name__ == "__main__":
    main()
