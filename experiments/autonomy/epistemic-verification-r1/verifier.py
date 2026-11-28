"""Bounded epistemic verifier. Research only; never writes knowledge."""
import json
import re
from pathlib import Path

INTEGER = r"[+-]?[0-9]{1,32}"
ARITH = re.compile(rf"({INTEGER}) *(=|!=) *({INTEGER})", re.ASCII)
SYMBOL = re.compile(r"(P|NP) *(=|!=) *(P|NP)", re.ASCII)
ACTIONS = {"TRUE": "ACCEPT_TRUE", "FALSE": "ACCEPT_FALSE",
           "UNRESOLVED": "HOLD", "INVALID": "REJECT_INPUT"}

def verify(claim, assertion=None, evidence=None):
    result = {"claim": claim, "syntax_valid": False,
              "semantic_status": "OUTSIDE_SUPPORTED_GRAMMAR",
              "proposition": None, "verified_evidence": None,
              "supplied_assertion_is_proof": False,
              "supplied_evidence_status": "NOT_PROVIDED" if evidence is None else "UNVERIFIED_IGNORED",
              "truth_status": "INVALID"}
    if isinstance(claim, str) and 0 < len(claim) <= 128 and claim.isascii():
        text = claim.strip(" ")
        match = ARITH.fullmatch(text)
        if match:
            lhs, op, rhs = match.groups()
            a, b = int(lhs), int(rhs)
            truth = (a == b) if op == "=" else (a != b)
            result.update(syntax_valid=True, semantic_status="PARSED_INTEGER_EQUALITY",
                          proposition={"left": a, "operator": op, "right": b},
                          verified_evidence={"method": "EXACT_INTEGER_COMPARISON",
                                             "left": a, "operator": op, "right": b,
                                             "result": truth},
                          truth_status="TRUE" if truth else "FALSE")
        else:
            match = SYMBOL.fullmatch(text)
            if match and match.group(1) != match.group(3):
                lhs, op, rhs = match.groups()
                result.update(syntax_valid=True, semantic_status="PARSED_SYMBOLIC_QUERY",
                              proposition={"left": lhs, "operator": op, "right": rhs},
                              truth_status="UNRESOLVED")
    result["epistemic_action"] = ACTIONS[result["truth_status"]]
    return result

def main():
    spec = json.loads(Path(__file__).with_name("precommit.json").read_text(encoding="utf-8"))
    rows = []
    for t in spec["tests"]:
        r = verify(t["claim"], t.get("assertion"), t.get("evidence"))
        expected = t["status"]
        checks = {
            "status": r["truth_status"] == expected,
            "action": r["epistemic_action"] == ACTIONS[expected],
            "syntax": r["syntax_valid"] == (expected != "INVALID"),
            "evidence": ((r["verified_evidence"] is not None) == (expected in ("TRUE", "FALSE"))),
            "assertion_not_proof": r["supplied_assertion_is_proof"] is False,
            "external_evidence_not_trusted": r["supplied_evidence_status"] ==
                ("UNVERIFIED_IGNORED" if t.get("evidence") is not None else "NOT_PROVIDED"),
        }
        rows.append({"id": t["id"], "expected": expected, "checks": checks,
                     "pass": all(checks.values()), "observed": r})
    passed = sum(r["pass"] for r in rows)
    report = {"schema":"janus.epistemic_verification.r1.result.v1",
              "status":"ENGINEERING_PASS" if passed == len(rows) == 20 else "ENGINEERING_FAIL",
              "passed":passed, "total":len(rows), "production":False,
              "training":False, "knowledge_write":False, "rows":rows}
    print(json.dumps(report, indent=2, ensure_ascii=True))
    if report["status"] != "ENGINEERING_PASS":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
