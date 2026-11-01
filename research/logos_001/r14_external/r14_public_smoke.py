"""PUBLIC synthetic protocol smoke only. NEVER an independent scientific result."""
import argparse
import json
import math
from pathlib import Path
from r14_submission import produce_predictions

def fixture():
    names=("fixture_wave","fixture_linear","fixture_quadratic")
    results=[]
    for index,name in enumerate(names):
        rows=[]
        for i in range(50):
            x=i/49
            y=(1+0.7*x if index==0 else
               -0.1+1.2*x-0.3*x*x if index==1 else
               0.5+math.sin(math.pi*x))
            rows.append([x,y])
        out={"train":[],"validation":[],"test":[]}
        for i,row in enumerate(rows):
            slot=i%5
            out["test" if slot==0 else "validation" if slot==1 else "train"].append(row)
        results.append({
          "domain_id":name,"physical_domain":"SYNTHETIC_FIXTURE_"+str(index),
          "provider_reference":"PUBLIC_SYNTHETIC_TEST_NOT_INDEPENDENT",
          **out})
    return {"benchmark":"JANUS-LOGOS-001-R1.4","domains":results}

def participant_outputs():
    output=[]
    for d in fixture()["domains"]:
        request={"domain_id":d["domain_id"],"train":d["train"],"validation":d["validation"],
                 "test_x":[x for x,y in d["test"]]}
        output.append(produce_predictions(request))
    return {"protocol":"PUBLIC_FIXTURE_PROTOCOL_SMOKE_ONLY","outputs":output}

def custodian_smoke(proposals):
    from r14_custodian_reference import evaluate_custodian_private
    if proposals.get("protocol")!="PUBLIC_FIXTURE_PROTOCOL_SMOKE_ONLY" or len(proposals.get("outputs",[]))!=3:
        raise ValueError("Not a public fixture submission")
    by_id={r["domain_id"]:r for r in proposals["outputs"]}
    if len(by_id)!=3:raise ValueError("Duplicated fixture")
    def participant_replay(request):
        r=by_id[request["domain_id"]]
        regenerated=produce_predictions(request)
        if r!=regenerated:raise ValueError("Candidate artifact is tampered or not reproducible")
        return r
    result=evaluate_custodian_private(fixture(),runner=participant_replay)
    if result["status"]!="UNSIGNED_DRAFT_NOT_EXTERNAL_PROOF" or result["independent_external_evaluation_verified"]:
        raise AssertionError("PUBLIC FIXTURE WAS INCORRECTLY TREATED AS EXTERNAL")
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=("participant","custodian"),required=True)
    p.add_argument("--input")
    p.add_argument("--out",required=True)
    a=p.parse_args()
    if a.mode=="participant":doc=participant_outputs()
    else:
        if not a.input:raise ValueError("Missing participant artifact")
        doc=custodian_smoke(json.loads(Path(a.input).read_text()))
    Path(a.out).write_text(json.dumps(doc,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"mode":a.mode,"status":doc.get("status","UNSCORED_PROPOSAL"),
                      "external_blind_evidence":"NONE_PUBLIC_FIXTURE"}))

if __name__=="__main__":main()
