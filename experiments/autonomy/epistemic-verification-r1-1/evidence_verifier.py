"""Evidence immunity: strict typed binding and independent integer recheck."""
import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
R1 = runpy.run_path(str(HERE.parent / "epistemic-verification-r1" / "verifier.py"))
verify = R1["verify"]

def canonical(result):
    prop = result["proposition"]
    if prop is None:
        return None
    return (result["semantic_status"], prop["operator"],
            *sorted((prop["left"], prop["right"])))

def assess(claim, certificates, reports):
    if type(certificates) is not list or type(reports) is not list or len(certificates) > 32 or len(reports) > 32:
        raise ValueError("EVIDENCE_ENVELOPE")
    base = verify(claim)
    target = canonical(base)
    checked = []
    for item in certificates:
        reason = "MALFORMED"
        if type(item) is dict and set(item) == {"method", "claim", "result"} and type(item["result"]) is bool:
            candidate = verify(item["claim"])
            if item["method"] != "EXACT_INTEGER_COMPARISON":
                reason = "METHOD_UNSUPPORTED"
            elif target is None or canonical(candidate) != target:
                reason = "PROPOSITION_MISMATCH"
            elif candidate["semantic_status"] != "PARSED_INTEGER_EQUALITY":
                reason = "NO_SUPPORTED_PROOF_METHOD"
            elif candidate["verified_evidence"]["result"] is not item["result"]:
                reason = "RESULT_MISMATCH"
            else:
                reason = "RECOMPUTED_CONTENT_VALID"
        checked.append(reason)
    bound = []
    rejected = 0
    for item in reports:
        if (type(item) is dict and set(item) == {"claim", "asserted_truth", "source"}
                and type(item["asserted_truth"]) is bool and type(item["source"]) is str
                and 0 < len(item["source"].strip()) <= 256 and len(item["source"]) <= 256
                and target is not None and canonical(verify(item["claim"])) == target):
            bound.append(item["asserted_truth"])
        else:
            rejected += 1
    valid = checked.count("RECOMPUTED_CONTENT_VALID")
    return {"truth_status": base["truth_status"], "epistemic_action": base["epistemic_action"],
            "verified_certificate_count": valid, "rejected_certificate_count": len(checked)-valid,
            "certificate_reasons": checked, "report_conflict": len(set(bound)) > 1,
            "bound_report_count": len(bound), "rejected_report_count": rejected,
            "source_authentication": "NOT_IMPLEMENTED", "verified_conflict": False,
            "truth_origin": "INTERNAL_R1_RECHECK" if base["verified_evidence"] else "NO_PROOF"}

def main():
    spec = json.loads((HERE / "precommit.json").read_text(encoding="utf-8"))
    rows = []
    for t in spec["tests"]:
        result = assess(t["claim"], t["certificates"], t["reports"])
        ok = all(result[k] == v for k,v in t["expected"].items())
        baseline = verify(t["claim"])
        ok = ok and result["truth_status"] == baseline["truth_status"]
        ok = ok and result["epistemic_action"] == baseline["epistemic_action"]
        ok = ok and result["source_authentication"] == "NOT_IMPLEMENTED" and result["verified_conflict"] is False
        rows.append({"id":t["id"],"expected":t["expected"],"observed":result,"pass":ok})
    passed = sum(r["pass"] for r in rows)
    envelope_checks = []
    for certs, reports in [(None, []), ([], {}), ([None]*33, []), ([], [None]*33)]:
        try:
            assess("2 = 2", certs, reports)
            envelope_checks.append(False)
        except ValueError as e:
            envelope_checks.append(str(e) == "EVIDENCE_ENVELOPE")
    status = "ENGINEERING_PASS" if passed == len(rows) == 30 and all(envelope_checks) else "ENGINEERING_FAIL"
    print(json.dumps({"schema":"janus.epistemic_verification.r1_1.result.v1","status":status,
                      "passed":passed,"total":len(rows),"envelope_checks":envelope_checks,
                      "production":False,"training":False,"knowledge_write":False,"rows":rows},indent=2))
    if status != "ENGINEERING_PASS":
        raise SystemExit(1)

if __name__ == "__main__":
    main()
