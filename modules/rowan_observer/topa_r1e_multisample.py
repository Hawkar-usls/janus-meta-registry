"""TOPA exact-decimal replay; independent of Rowan SDK, no provider credentials."""
from decimal import Decimal as D, localcontext
import argparse, copy, json, re
from pathlib import Path
SOURCE="data/rowan/provenance/ROWAN-R1E-REAL-FIVE-SAMPLE-WT-COST-2026-11-19-v1.json"
def req(b,msg):
    if not b:raise ValueError(msg)
def number(x):
    req(isinstance(x,(int,float,D)) and not isinstance(x,bool),"not numeric")
    v=D(str(x));req(v.is_finite(),"nonfinite");return v
def near(x,y):
    req(abs(number(x)-number(y))<=D("0.000000000001"),"reported value mismatch")
def audit(src):
    req(src["receipt_sha256"]=="04d5c83a8164940e5c3b873ea66d153defd95ff8b0cb3486f8041f03aff02ed7","source hash")
    req(src["single_receipt_sha256"]=="4beda3b328823ae69e61a4b87ce3d7102493eedee8a88826839f0eef542501ba","control hash")
    r,c=src["receipt"],src["single_control"]
    req(src["submit_run_id"]=="44527758520" and r["github_run_id"]=="44531233894" and c["github_run_id"]=="44517772207","run IDs")
    req(r["sequence_sha256"]==c["sequence_sha256"]=="94a6f4324114f9e643076e2bfcb727145d400345f4c5feff0607e5c1fb787be1","WT identity")
    req(r["case"]=="JANUS-ROWAN-1EY0-R1E-WT-5S-20261119-R0" and r["model"]=="BOLTZ_2","case")
    req(r["status"]=="RESULT_COLLECTED_ALL_FIVE" and r["provider_state"]=="Status.COMPLETED_OK" and r["new_jobs"]==0 and c["new_jobs"]==0,"collect boundary")
    req(all(r[k] is False for k in ("provider_equivalence","wetlab_validation","label_access","weights_changed","independent_seeds_verified")),"scope")
    xs=r["samples"];req(len(xs)==r["requested_samples"]==r["returned_sample_count"]==5,"count")
    req(sorted(x["index"] for x in xs)==list(range(5)),"index")
    ids=[x["structure_uuid_sha256"] for x in xs]
    req(len(set(ids))==5 and all(re.fullmatch("[0-9a-f]{64}",x) for x in ids),"structure identity")
    summary={}
    with localcontext() as ctx:
        ctx.prec=40
        for k in ("ptm","avg_lddt"):
            v=[number(x[k]) for x in xs];req(all(0<=x<=1 for x in v),"score bounds")
            mu=sum(v)/5;sd=(sum((x-mu)**2 for x in v)/4).sqrt()
            result={"mean":mu,"sd":sd,"min":min(v),"max":max(v)}
            for field,t in result.items():near(t,r["summary"][k][field])
            req(number(r["primary_scores"][k])==v[0],"primary score")
            summary[k]={key:str(val) for key,val in result.items()}
        cost=number(r["credits_charged"]);single=number(c["credits_charged"])
        req(cost==D("5.69") and 0<cost<=number(r["max_credits"])==10 and single==D("5.05"),"cost")
        near(cost/5,r["credits_per_returned_sample"]);near(cost/(5*single),r["cost_ratio_vs_five_repeated_single_WT_reference"])
        near(single,r["single_WT_comparator_credits"])
        return {"status":"PASS_INTERNAL_TOPA_EXACT_DECIMAL_REPLAY","samples":5,"summary":summary,"credits":str(cost),"per_sample":str(cost/5),"five_single_reference":str(5*single),"relative_saving_percent":str((1-cost/(5*single))*100),"cost_ratio":str(cost/(5*single)),"new_provider_calls":0,"new_credits":0,"scope":"One WT cost control only; no independent seed or coordinate equivalence; no prediction accuracy claim."}
def main():
    p=argparse.ArgumentParser();p.add_argument("--out",required=True);a=p.parse_args()
    src=json.loads(Path(SOURCE).read_text(encoding="utf8"));res=audit(src)
    for mode in ("duplicate","metric","cost"):
        t=copy.deepcopy(src)
        if mode=="duplicate":t["receipt"]["samples"][1]["structure_uuid_sha256"]=t["receipt"]["samples"][0]["structure_uuid_sha256"]
        elif mode=="metric":t["receipt"]["samples"][2]["ptm"]+=0.01
        else:t["receipt"]["credits_per_returned_sample"]=0.01
        try:audit(t)
        except ValueError:pass
        else:raise ValueError("negative control failed: "+mode)
    res["negative_controls_rejected"]=3
    with Path(a.out).open("x",encoding="utf8") as f:json.dump(res,f,indent=2,allow_nan=False)
    print("TOPA_R1E=PASS_INTERNAL_TOPA_EXACT_DECIMAL_REPLAY");print("TOPA_R1E_SAMPLES=5");print("TOPA_R1E_NEGATIVE_CONTROLS=3");print("TOPA_R1E_COST="+res["credits"])
if __name__=="__main__":main()
