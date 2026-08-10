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
    for mutation in mutations or []:
        eid = mutation["evidence_id"]
        if eid not in idx:
            raise VerificationError(f"unknown evidence in mutation: {eid}")
        idx[eid][mutation["field"]] = mutation["value"]
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
    for evidence in admissible:
        for atom in evidence.get("establishes", []):
            established_by.setdefault(atom, []).append(evidence["id"])
    established = set(established_by)

    claim = claims[claim_id]
    missing_all = [a for a in claim.get("required_atoms", []) if a not in established]
    alternatives = claim.get("required_atoms_any", [])
    missing_any = bool(alternatives) and not any(a in established for a in alternatives)
    blocking = [a for a in claim.get("blocking_atoms", []) if a in established]

    reasons = []
    if inadmissible:
        reasons.append({"code": "INADMISSIBLE_EVIDENCE", "evidence_ids": inadmissible})
    if missing_all:
        reasons.append({"code": "MISSING_REQUIRED_ATOMS", "atoms": missing_all})
    if missing_any:
        reasons.append({"code": "NO_DIRECT_SUPPORT_FOR_ANY_REQUIRED_ALTERNATIVE", "atoms": alternatives})
    if blocking:
        reasons.append({
            "code": "BLOCKING_COUNTEREVIDENCE",
            "atoms": blocking,
            "established_by": {a: established_by[a] for a in blocking},
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
            "SOURCE_BINDING_REQUIRED": True,
            "NO_IMPLICIT_ENTAILMENT": bool(spec.get("model", {}).get("no_implicit_entailment", True)),
        },
    }

def run_case(spec, case):
    return verify_claim(spec, case["claim"], case["evidence_ids"], case.get("mutations"))

def run_self_test(spec):
    rows = []
    all_ok = True
    for case in spec.get("test_cases", []):
        receipt = run_case(spec, case)
        ok = receipt["result"] == case["expected"]
        rows.append({"case": case["id"], "expected": case["expected"], "actual": receipt["result"], "test": PASS if ok else REJECT})
        all_ok = all_ok and ok
    return {"result": PASS if all_ok else REJECT, "tests": rows}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--case")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    spec = load_json(args.spec)
    if args.self_test:
        out = run_self_test(spec)
    elif args.case:
        cases = [c for c in spec.get("test_cases", []) if c["id"] == args.case]
        if not cases:
            raise SystemExit(f"unknown case: {args.case}")
        out = run_case(spec, cases[0])
    else:
        raise SystemExit("use --self-test or --case CASE_ID")
    print(json.dumps(out, ensure_ascii=False, indent=2 if args.pretty else None))
    raise SystemExit(0 if out["result"] == PASS else 1)

if __name__ == "__main__":
    main()
