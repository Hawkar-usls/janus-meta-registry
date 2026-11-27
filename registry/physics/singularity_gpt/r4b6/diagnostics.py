"""Frozen conditioning and floor diagnostics, without modifying classifier."""
import ast,json,sys,hashlib
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
HERE=Path(__file__).resolve().parent
P=json.loads((HERE/"protocol.json").read_text())
OUT=Path("r4b6-output");OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(HERE.parent/"r4b3"))
from generator import cases
def load_functions(path,names,env):
    nodes=[x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),"exec"),env)
    return env
def conditioning():
    rows=[]
    for delta in P["conditioning"]["periods"]:
        q=np.exp(-delta/2);a=1.;b=q;d=a-b
        da=-b*b/d**2;db=2*b/d+b*b/d**2
        J=np.array([-da,da-db,1+db])
        gap=b*b/d
        # Unit peak timestamp errors scaled by the first interval a.
        relative_l1=float(np.sum(abs(J))*a/gap)
        relative_l2=float(np.linalg.norm(J)*a/gap)
        # Idealized last prefix triplet: remaining interval to full end shrinks.
        remaining_cycles=P["conditioning"]["cycles"]*(1-P["conditioning"]["prefix"])
        extrapolation=float(np.exp(remaining_cycles*delta))
        rows.append({"period":delta,"q":float(q),"jacobian":J.tolist(),"common_shift_gain":float(J.sum()),"absolute_l1":float(np.sum(abs(J))),"absolute_l2":float(np.linalg.norm(J)),"local_relative_l1_for_unit_first_interval_error":relative_l1,"local_relative_l2_for_unit_first_interval_error":relative_l2,"ideal_prefix_to_end_gap_amplification":extrapolation,"end_relative_l1_for_unit_first_interval_error":relative_l1*extrapolation})
    return {"rows":rows,"interpretation":"First-order perturbation of three exact peak times; not a waveform noise bound. Prefix-to-end factor assumes 2.7 remaining log cycles."}
def floor():
    env=load_functions(HERE.parent/"r4b5"/"diagnose.py",{"objective"},{"np":np,"least_squares":least_squares})
    objective=env["objective"]
    parent=json.loads((HERE.parent/"r4b4"/"protocol.json").read_text())["generator"]
    cfg={**parent,"new_seed":parent["seed"]};rows=[]
    for c in cases(cfg):
        if c["subtype"]!="positive" or c["level"]!=0 or c["kind"]!="iid":continue
        t=c["t"];y=c["raw"]/c["envelope"];truth=float(np.log((c["star"]-t[-1])/(t[-1]-t[0])))
        r={"i":c["i"],"truth":truth,"true_score":objective(t,y,truth),"grids":[]}
        for lower in (-40,-45,-50):
            grid=np.linspace(lower,-1,29)
            scores=[{"log_gap":float(g),"score":objective(t,y,float(g))} for g in grid]
            valid=[x for x in scores if x["score"] is not None]
            a=min(valid,key=lambda x:x["score"]["legacy"]);b=min(valid,key=lambda x:x["score"]["frequency_refined"])
            vals=[x["score"]["frequency_refined"] for x in valid]
            r["grids"].append({"lower":lower,"legacy_estimate":a["log_gap"],"refined_estimate":b["log_gap"],"legacy_floor":a["log_gap"]==lower,"refined_floor":b["log_gap"]==lower,"legacy_error":a["log_gap"]-truth,"refined_error":b["log_gap"]-truth,"refined_score_range":float(max(vals)-min(vals)),"grid_scores":scores})
        rows.append(r)
        if len(rows)==30:break
    summary=[]
    for lower in (-40,-45,-50):
        x=[g for r in rows for g in r["grids"] if g["lower"]==lower]
        summary.append({"lower":lower,"n":len(x),"legacy_floor":sum(g["legacy_floor"] for g in x),"refined_floor":sum(g["refined_floor"] for g in x),"legacy_median_abs_error":float(np.median([abs(g["legacy_error"]) for g in x])),"refined_median_abs_error":float(np.median([abs(g["refined_error"]) for g in x]))})
    (OUT/"trials.json").write_text(json.dumps(rows,indent=2,allow_nan=False)+"\n")
    return {"summary":summary,"note":"Changing grid lower bound also changes spacing. Local frequency refinement is not global joint optimization. Does not isolate boundary logic alone."}
mode=sys.argv[1];result={"conditioning":conditioning,"floor":floor}[mode]()
result.update({"mode":mode,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"scientific_hold":True})
(OUT/"result.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
print("R4B6_RESULT",json.dumps(result,allow_nan=False),flush=True)
