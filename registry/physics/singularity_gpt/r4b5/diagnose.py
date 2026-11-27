"""Reproduce signed errors and inspect objective at true nuisance values."""
import ast,json,hashlib,sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/"r4b3")]
from generator import cases
P=json.loads((HERE/"protocol.json").read_text())
parent=json.loads((HERE.parent/"r4b4"/"protocol.json").read_text())["generator"]
cfg={**parent,"new_seed":parent["seed"]}
OUT=Path("r4b5-output");OUT.mkdir(exist_ok=True)
def frozen(path,name,env):
    node=next(x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),"exec"),env)
    return env[name]
time_only=frozen(HERE.parent/"r4b4"/"ablate.py","time_only",{"np":np})
blind=frozen(HERE.parent/"r4b3"/"phase.py","normalize_blind",{"np":np})
grid=np.linspace(-45,-1,29)
def objective(t,y,lg):
    m=int(.55*len(t));d=(t[-1]-t)/(t[-1]-t[0]);gap=np.exp(lg)
    s=-np.log((d+gap)/(1+gap));u=s/s[-1];coord=u[:m]
    z=np.interp(np.linspace(coord[0],coord[-1],512),coord,y[:m])
    freq=np.fft.rfftfreq(2048,d=(coord[-1]-coord[0])/511)
    amp=abs(np.fft.rfft((z-z.mean())*np.hanning(len(z)),n=2048))
    good=(freq>.3)&(freq<45)
    if not good.any():return None
    f=float(freq[np.flatnonzero(good)[np.argmax(amp[good])]])
    b=np.column_stack((np.ones(m),np.sin(2*np.pi*f*coord),np.cos(2*np.pi*f*coord)))
    r=y[:m]-b@np.linalg.lstsq(b,y[:m],rcond=None)[0]
    raw=float(np.mean(r*r)/max(np.mean(y[:m]**2),1e-20))
    # Diagnostic only: refine frequency locally at the same fixed temporal gap.
    def loss(ff):
        a=2*np.pi*float(ff[0])*coord
        B=np.column_stack((np.ones(m),np.sin(a),np.cos(a)))
        return (y[:m]-B@np.linalg.lstsq(B,y[:m],rcond=None)[0])/max(np.sqrt(np.mean(y[:m]**2)),1e-20)
    sol=least_squares(loss,[f],bounds=([.2],[45]),max_nfev=45)
    return {"legacy":raw,"frequency_refined":float(np.mean(sol.fun**2)),"frequency_seed":f}
rows=[]
for c in cases(cfg):
    if c["subtype"]!="positive" or c["level"]!=0 or c["kind"]!="iid":continue
    t=c["t"];v=c["raw"];y=v/c["envelope"]
    true=float(np.log((c["star"]-t[-1])/(t[-1]-t[0])))
    b=time_only(t,y);d=blind(t,v)
    estB=b[2]["log_gap_estimate"] if b else None;estD=d[2]["log_gap_estimate"] if d else None
    nearest=float(grid[np.argmin(abs(grid-true))]);r={"i":c["i"],"true_log_gap":true,"B":estB,"D":estD,"error_B":estB-true if estB is not None else None,"error_D":estD-true if estD is not None else None,"nearest_grid":nearest}
    if len(rows)<30:
        r["objective_true"]=objective(t,y,true);r["objective_nearest"]=objective(t,y,nearest);r["objective_selected"]=objective(t,y,estB) if estB is not None else None
        r["grid_objective"]=[{"log_gap":float(g),"scores":objective(t,y,float(g))} for g in grid]
    rows.append(r)
    if len(rows)==100:break
def summarize(mode):
    e=np.array([r["error_"+mode] for r in rows if r["error_"+mode] is not None]);v=np.array([r[mode] for r in rows if r[mode] is not None])
    counts,edges=np.histogram(e,bins=np.arange(-46,48,2))
    return {"n":len(e),"median_signed":float(np.median(e)),"mean_signed":float(np.mean(e)),"median_absolute":float(np.median(abs(e))),"quantiles_05_25_50_75_95":np.quantile(e,[.05,.25,.5,.75,.95]).tolist(),"positive":int(sum(e>0)),"negative":int(sum(e<0)),"at_lower_grid":int(sum(v==grid[0])),"at_upper_grid":int(sum(v==grid[-1])),"histogram":{"edges":edges.tolist(),"counts":counts.tolist(),"underflow":int(sum(e<edges[0])),"overflow":int(sum(e>edges[-1]))}}
detail=[r for r in rows if "objective_true" in r and r["objective_true"] and r["objective_selected"]]
result={"B":summarize("B"),"D":summarize("D"),"detailed_count":len(detail),"true_in_grid_range":int(sum(grid[0]<=r["true_log_gap"]<=grid[-1] for r in rows)),"legacy_true_better_than_selected":sum(r["objective_true"]["legacy"]<r["objective_selected"]["legacy"] for r in detail),"refined_true_better_than_selected_legacy":sum(r["objective_true"]["frequency_refined"]<r["objective_selected"]["legacy"] for r in detail),"true_log_gap_median":float(np.median([r["true_log_gap"] for r in rows])),"no_decision_change":True,"scientific_hold":True}
for name,data in (("result.json",result),("trials.json",rows)):(OUT/name).write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")
print("R4B5_DIAG_RESULT",json.dumps(result,allow_nan=False),flush=True)
