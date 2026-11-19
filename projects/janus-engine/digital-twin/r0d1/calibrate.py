"""Fit only an explicitly normalized, provenance-reviewed run-level table.
No synthetic results are admitted as measurements. No row-level random split."""
import argparse, csv, json, math
from pathlib import Path

QREF=.663
A=3.0
def fit(train, exponent):
    xs=[A*r["delta_p_pa"]*(r["flow_l_s"]/QREF)**exponent for r in train]
    ys=[r["flux_mol_s"] for r in train]
    k=sum(x*y for x,y in zip(xs,ys))/sum(x*x for x in xs)
    return k
def predict(row,k,alpha):
    return k*A*row["delta_p_pa"]*(row["flow_l_s"]/QREF)**alpha
def validate(rows):
    if len({r["run_id"] for r in rows}) != len(rows):
        raise ValueError("duplicate run identifiers")
    if len({r["flow_l_s"] for r in rows})<3:
        raise ValueError("at least three distinct flow settings required")
    for r in rows:
        if not r["run_id"] or not all(math.isfinite(r[k]) and r[k]>0 for k in ("flow_l_s","delta_p_pa","flux_mol_s")):
            raise ValueError("invalid or nonpositive run values")
def metrics(predictions):
    n=len(predictions)
    return {"n":n,"mae_umol_s":1e6*sum(abs(p["predicted"]-p["measured"]) for p in predictions)/n,
            "rmse_umol_s":1e6*math.sqrt(sum((p["predicted"]-p["measured"])**2 for p in predictions)/n),
            "mean_absolute_relative_error":sum(abs(p["predicted"]-p["measured"])/p["measured"] for p in predictions)/n}
def evaluate(rows):
    validate(rows)
    results={}
    for name,alpha in (("constant_conductance",0.0),("laminar_scaling",1/3)):
        preds=[]; folds=[]
        for flow in sorted({r["flow_l_s"] for r in rows}):
            train=[r for r in rows if r["flow_l_s"]!=flow]
            test=[r for r in rows if r["flow_l_s"]==flow]
            k=fit(train,alpha)
            fold=[{"run_id":r["run_id"],"flow_l_s":flow,"predicted":predict(r,k,alpha),"measured":r["flux_mol_s"]} for r in test]
            preds.extend(fold)
            folds.append({"held_out_flow_l_s":flow,"train_ids":[r["run_id"] for r in train],"test_ids":[r["run_id"] for r in test],"k":k,"metrics":metrics(fold)})
        results[name]={"alpha":alpha,"folds":folds,"metrics":metrics(preds),"predictions":preds,
                       "all_data_fit_k_descriptive_only":fit(rows,alpha)}
    return results
def self_test():
    rows=[{"run_id":f"{q}-{p}","flow_l_s":q,"delta_p_pa":p,"flux_mol_s":1e-10*A*p*(q/QREF)**(1/3)} for q in (.478,.663,.847) for p in (1000,2000,3000)]
    result=evaluate(rows)
    assert result["laminar_scaling"]["metrics"]["rmse_umol_s"]<1e-12
    assert result["constant_conductance"]["metrics"]["rmse_umol_s"]>1e-3
    for f in result["laminar_scaling"]["folds"]:
        assert not set(f["train_ids"]) & set(f["test_ids"])
    return {"status":"PASS","evidence":"SYNTHETIC_SOFTWARE_TEST_ONLY","checks":3}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--csv",type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    out={"stage":"R0D1B","self_test":self_test(),"physical_janus_runs":0,"run008_modified":False}
    if a.csv:
        with a.csv.open(newline="",encoding="utf-8") as f:
            rows=[{"run_id":r["run_id"],**{k:float(r[k]) for k in ("flow_l_s","delta_p_pa","flux_mol_s")}} for r in csv.DictReader(f)]
        out.update({"status":"GROUPED_CROSS_VALIDATION_DESCRIPTIVE","results":evaluate(rows),"source_class":"INPUT_TABLE_REQUIRES_SEPARATE_PROVENANCE_REVIEW"})
    else:
        out["status"]="PASS_SOFTWARE_TEST_ONLY"
    a.output.write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    print(out["status"],out["self_test"])
if __name__=="__main__":
    main()
