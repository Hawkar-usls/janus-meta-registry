"""Frozen BLIND transition and equal-budget joint estimator comparisons."""
import ast,hashlib,json,sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/"r4b2"),str(HERE.parent/"r4b3")]
import rivals
from bank import bank
P=json.loads((HERE/"protocol.json").read_text())
OUT=Path("r4b7-output");OUT.mkdir(exist_ok=True)
def load(path,names,env):
    nodes=[x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),"exec"),env);return env
g=load(HERE.parent/"r4b5"/"controls.py",{"extrema","geometric"},{"np":np})
phase=load(HERE.parent/"r4b3"/"phase.py",{"phase_ci"},{"np":np,"least_squares":least_squares})["phase_ci"]
old=load(HERE.parent/"r4b6"/"sweep.py",{"geom_metrics","joint"},{"np":np,"geometry":g["geometric"],"extrema":g["extrema"],"rivals":rivals,"phase":phase})
mode,kind=sys.argv[1:3];cfg=P["transition" if mode=="transition" else "joint"]
rng=np.random.default_rng(P["joint"]["random_init_seed"])
def fit(t,v,strategy):
    n=len(t);span=t[-1]-t[0];d=(t[-1]-t)/span
    # Fixed, fit-window-only local scaling keeps the early lobes represented.
    chunks=np.array_split(np.arange(n),min(32,n//8))
    rms=np.array([np.sqrt(np.mean(v[c]**2)) for c in chunks]);centers=np.array([c.mean() for c in chunks])
    scale=np.exp(np.interp(np.arange(n),centers,np.log(np.maximum(rms,1e-280))))
    y=v/scale
    def coords(gap):
        return np.log1p((1-d)/(d+np.exp(gap)))
    def design(q):
        s=coords(q[0]);u=s/s[-1];angle=2*np.pi*q[1]*u
        amp=np.exp(np.clip(q[2]*(s-s[-1]),-700,0))/scale
        # Profile linear sine/cosine amplitudes, with an envelope-scaled offset.
        B=np.column_stack((amp*np.sin(angle),amp*np.cos(angle),amp))
        norm=np.maximum(np.linalg.norm(B,axis=0),1e-280);return B/norm
    def residual(q):
        B=design(q);return B@np.linalg.lstsq(B,y,rcond=None)[0]-y
    geom=g["geometric"](t,v) if strategy=="geometric" else None
    if strategy=="geometric":
        if geom["status"]!="FINITE":return {"status":"INIT_UNAVAILABLE","nfev":0}
        loggap=np.log((geom["t_star_estimate"]-t[-1])/span)
    elif strategy=="prior_center":loggap=-23.
    else:loggap=float(rng.uniform(-45,-1))
    loggap=float(np.clip(loggap,-45+1e-9,-1-1e-9));s=coords(loggap);u=s/s[-1]
    zz=np.interp(np.linspace(0,1,512),u,y);power=abs(np.fft.rfft((zz-zz.mean())*np.hanning(len(zz)),n=2048))
    freqs=np.fft.rfftfreq(2048,d=1/511);ii=np.where((freqs>.2)&(freqs<45))[0];f=float(freqs[ii[np.argmax(power[ii])]])
    beta=float(np.clip(np.polyfit(s,np.log(scale),1)[0],.100001,2.999999))
    x0=[loggap,np.clip(f,.200001,44.999999),beta]
    sol=least_squares(residual,x0,bounds=([-45,.2,.1],[-1,45,3]),max_nfev=80,ftol=1e-8,xtol=1e-8,gtol=1e-8)
    gap=float(np.exp(sol.x[0])*span);period=float(coords(sol.x[0])[-1]/sol.x[1])
    return {"status":"FINITE","loggap":float(sol.x[0]),"gap":gap,"period":period,"beta":float(sol.x[2]),"nfev":int(sol.nfev),"converged":bool(sol.success),"rmse":float(np.sqrt(np.mean(sol.fun**2))),"initial_loggap":loggap,"at_floor":bool(sol.x[0]<-44.999)}
rows=[]
for sub,i,level,missing,t,v,truth,period in bank(cfg,kind):
    h=hashlib.sha256(np.asarray(np.column_stack((t,v)),dtype="<f8").tobytes()).hexdigest()
    if mode=="transition":
        a=old["geom_metrics"](t,v,truth,period,"prefix");b=old["joint"](t,v,a,period if sub=="positive" else None)
        rows.append({"sub":sub,"i":i,"noise":level,"missing":missing,"sha256":h,"geometry":a,"joint":b})
    else:
        for window in cfg["windows"]:
            m=int(.55*len(t)) if window=="prefix" else len(t)
            for strategy in cfg["strategies"]:
                a=fit(t[:m],v[:m],strategy)
                if a["status"]=="FINITE" and truth is not None:
                    e=abs(a["gap"]-(truth-t[m-1]));pe=abs(a["period"]-period)/period
                    a.update({"local_gap_error":float(e/(truth-t[m-1])),"final_gap_error":float(e/(truth-t[-1])),"period_error":float(pe),"local_correct":bool(e/(truth-t[m-1])<=.05 and pe<=.05),"final_correct":bool(e/(truth-t[-1])<=.05 and pe<=.05)})
                rows.append({"sub":sub,"i":i,"noise":level,"missing":missing,"window":window,"strategy":strategy,"sha256":h,"fit":a})
    if len(rows)%600==0:print("PROGRESS",mode,kind,len(rows),flush=True)
summary=[]
if mode=="transition":
    for sub,n,m in sorted({(r["sub"],r["noise"],r["missing"]) for r in rows}):
        rr=[r for r in rows if (r["sub"],r["noise"],r["missing"])==(sub,n,m)];a=[r["joint"] for r in rr]
        summary.append({"sub":sub,"noise":n,"missing":m,"n":len(rr),"DSS":sum(x["label"]=="DSS" for x in a),"AMBIGUOUS":sum(x["label"]=="AMBIGUOUS" for x in a),"REJECT":sum(x["label"]=="REJECT" for x in a),"correct_positive":sum(x["label"]=="DSS" and x.get("period_error") is not None and x["period_error"]<=.05 for x in a),"stages":{s:sum(x["stage"]==s for x in a) for s in sorted({x["stage"] for x in a})}})
else:
    keys=("sub","noise","missing","window","strategy")
    groups={}
    for r in rows:groups.setdefault(tuple(r[k] for k in keys),[]).append(r["fit"])
    for key,a in sorted(groups.items()):
        f=[x for x in a if x["status"]=="FINITE"];e=[x["final_gap_error"] for x in f if "final_gap_error" in x]
        summary.append({**dict(zip(keys,key)),"n":len(a),"finite":len(f),"converged":sum(x["converged"] for x in f),"floor":sum(x["at_floor"] for x in f),"local_correct":sum(x.get("local_correct",False) for x in f),"final_correct":sum(x.get("final_correct",False) for x in f),"median_final_gap_error":float(np.median(e)) if e else None,"median_rmse":float(np.median([x["rmse"] for x in f])) if f else None,"mean_nfev":float(np.mean([x["nfev"] for x in a]))})
result={"mode":mode,"kind":kind,"n":len(rows),"summary":summary,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"bank_sha256":hashlib.sha256((HERE/"bank.py").read_bytes()).hexdigest(),"scientific_hold":True,"physical_use_authorized":False,"limitations":["One start per strategy, same optimizer evaluation cap; frequency and envelope seeds conditional on chosen time seed.","Joint fits assume DSS; finite fits on negatives are not classifier false alarms. No classifier admission in joint arm.","Full-window fit is retrospective; prefix predictions scored separately."]}
for name,obj in (("trials.json",rows),("result.json",result)):(OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
# Aggregate logs limited; full stratification remains in artifact.
if mode=="joint":
    logs=[x for x in summary if x["sub"]=="positive" and x["missing"]==0]
else:logs=summary
print("R4B7_RESULT",json.dumps({**result,"summary":logs},allow_nan=False),flush=True)
