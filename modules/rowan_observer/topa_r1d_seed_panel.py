"""TOPA independent numerical replay of a fixed two-protein diagnostic panel.
No provider communication, secret, experimental label access or model updates.
Source artifacts checked on Yaksa; CI independently recomputes exported metrics.
"""
import argparse, hashlib, json, math, statistics, copy
from pathlib import Path
from decimal import Decimal as D

SOURCE="data/rowan/provenance/ROWAN-R1D-LOCAL-CLOUD-SEED-PANEL-2026-11-19-v1.json"
MODEL="data/rowan/feedback/FEEDBACK-RUN40236409772-38e04b8f73a81a21.json"
HIST="data/rowan/provenance/ROWAN-1EY0-T8A-REAL-ROWAN-VS-LOCAL-MUTATION-DELTA-2026-10-26-v1.json"
EXPECTED_MODEL_SHA="52e0d6e75d603f0596ac7938715e45fccaf38835fac0ed110176128e33d86cf3"

def require(condition, why):
    if not condition: raise ValueError(why)
def near(a,b):
    return math.isclose(a,b,rel_tol=0,abs_tol=2e-12)
def stat(v):
    m=math.fsum(v)/len(v)
    return {"n":len(v),"mean":m,"sd":math.sqrt(math.fsum((x-m)**2 for x in v)/(len(v)-1)),"min":min(v),"max":max(v),"median":statistics.median(v)}
def check_stat(actual,reported):
    require(all(near(v,reported[k]) for k,v in actual.items()),"summary mismatch")
def audit(src, fit, hist):
    require(src["status"]=="PASS_LOCAL_SOURCE_REPLAY" and src["checked_raw_outputs"]==96 and src["checked_pairs"]==48,"source status")
    require(src["scope"].startswith("internal source replay"),"scope guard")
    require(src["checkpoint_sha256"]=="090e82ac8c92f5e943fa1b39e7410a44027bea7243c0bbb3caa67a77fc1428e1","checkpoint")
    require(src["rowan_new_jobs"]==0 and src["credits_used"]==0,"no spending")
    seeds=range(20261122,20261142)
    fixed={(p,"fixed",s,r) for p in ("1EY0","BBC1") for s in seeds for r in ("WT","MUT")}
    sub={(p,"subsample",s,r) for p in ("1EY0","BBC1") for s in (20261122,20261127,20261132,20261137) for r in ("WT","MUT")}
    index={}
    for row in src["raw_rows"]:
        key=tuple(row[k] for k in ("protein","arm","seed","role"))
        require(key not in index,"duplicate")
        require(row["processed_msa_equal"] is True,"MSA drift")
        require(all(isinstance(row[k],str) and len(row[k])==64 and all(c in "0123456789abcdef" for c in row[k]) for k in ("confidence_sha256","hparams_sha256")),"hash format")
        require(all(math.isfinite(row[k]) and 0<=row[k]<=1 for k in ("ptm","complex_plddt")),"metric range")
        index[key]=row
    require(set(index)==fixed|sub,"coverage drift")
    require(len(index)==96,"count")
    f=fit["fit"]; pairs={}
    def score(dp,dl):
        return float(D(str(f["intercept"]))+D(str(f["scale"]))*(D(str(f["weights"][0]))*D(str(dp))+D(str(f["weights"][1]))*D(str(dl))))
    for p,a,s,r in sorted(index):
        if r!="WT": continue
        w,m=index[p,a,s,"WT"],index[p,a,s,"MUT"]
        dp=m["ptm"]-w["ptm"];dl=m["complex_plddt"]-w["complex_plddt"]
        pairs[p,a,s]={"delta_ptm":dp,"delta_plddt":dl,"score":score(dp,dl)}
    verify={}
    for p in ("1EY0","BBC1"):
        v={}; g=src["summary"][p]
        for metric in ("delta_ptm","delta_plddt","score"):
            x=[pairs[p,"fixed",s][metric] for s in seeds]
            y=[pairs[p,"subsample",s][metric] for s in (20261122,20261127,20261132,20261137)]
            diffs=[pairs[p,"subsample",s][metric]-pairs[p,"fixed",s][metric] for s in (20261122,20261127,20261132,20261137)]
            check_stat(stat(x),g["fixed"][metric]);check_stat(stat(y),g["subsample"][metric]);check_stat(stat(diffs),g["matched_subsample_minus_fixed"][metric])
            for k in (1,5,10,20):
                blocks=[math.fsum(x[i:i+k])/k for i in range(0,20,k)]
                q=g["averaging"][metric][str(k)]
                require(near(q["estimated_se_iid"],stat(x)["sd"]/math.sqrt(k)),"SE mismatch")
                require(near(q["empirical_random_subset_sd"],stat(x)["sd"]*math.sqrt((1-k/20)/k)),"finite subset mismatch")
                require(len(blocks)==len(q["nonoverlap_block_means"]) and all(near(a,b) for a,b in zip(blocks,q["nonoverlap_block_means"])),"block mismatch")
            v[metric]={"fixed":stat(x),"subsample":stat(y),"paired_arm_difference":stat(diffs),"se5":stat(x)["sd"]/math.sqrt(5),"se10":stat(x)["sd"]/math.sqrt(10),"se20":stat(x)["sd"]/math.sqrt(20)}
        require(sum(pairs[p,"fixed",s]["delta_ptm"]<0 for s in seeds)==g["fixed"]["ptm_negative"],"sign count")
        verify[p]=v
    c=src["cloud"];require([x["role"] for x in c]==["WT","T8A"],"cloud identities")
    require([x["github_run_id"] for x in c]==["44517772207","44518458966"],"cloud run identity")
    require([x["receipt_sha256"] for x in c]==["4beda3b328823ae69e61a4b87ce3d7102493eedee8a88826839f0eef542501ba","6274a49a40826d69f87346c802c90033bfbe66b3b7968f54a08521efb705ec61"],"cloud receipts")
    require(all(0<=x["credits_charged"]<=10 for x in c),"cloud credit bound")
    now={k: str(D(str(c[1][k]))-D(str(c[0][k]))) for k in ("ptm","avg_lddt")}
    old=hist["rowan"]
    old_delta=str(D(str(old["T8A_ptm"]))-D(str(old["WT_ptm"])))
    return {"status":"PASS_INTERNAL_INDEPENDENT_NUMERIC_REPLAY", "raw_count":len(index),"pair_count":len(pairs),"statistics":verify,"new_cloud_delta":now,"old_cloud_delta_ptm":old_delta,"cloud_repeat_credits":sum(x["credits_charged"] for x in c),"new_jobs":0,"new_credits":0,"provider_equivalence":"HOLD","external_validation":"OPEN","aggregation_recommendation":"5 fixed independent seeds candidate for engineering pilot; 10 when prospectively required by precision; 20 reference panel; no evidence of optimum or predictive gain; cloud support and price unverified"}

def main():
    a=argparse.ArgumentParser();a.add_argument("--out",required=True);args=a.parse_args()
    b=Path(MODEL).read_bytes();require(hashlib.sha256(b).hexdigest()==EXPECTED_MODEL_SHA,"frozen model changed")
    src=json.loads(Path(SOURCE).read_text(encoding="utf8"));fit=json.loads(b);hist=json.loads(Path(HIST).read_text(encoding="utf8"))
    report=audit(src,fit,hist)
    # Negative controls must independently detect duplicated case and tampered pTM.
    for kind in ("duplicate","metric"):
        tamper=copy.deepcopy(src)
        if kind=="duplicate":tamper["raw_rows"].append(tamper["raw_rows"][0])
        else:tamper["raw_rows"][0]["ptm"]+=0.01
        try:audit(tamper,fit,hist)
        except ValueError:pass
        else:raise ValueError("negative control escaped: "+kind)
    report["negative_controls_rejected"]=2
    with Path(args.out).open("x",encoding="utf8") as f:json.dump(report,f,indent=2,allow_nan=False)
    print("TOPA_R1D=PASS_INTERNAL_INDEPENDENT_NUMERIC_REPLAY")
    print("TOPA_R1D_COUNTS=96/48/2")
if __name__=="__main__": main()
