"""Precommitted adaptive vs random starts; identical per-latent seeds."""
import ast,hashlib,json,sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/"r4b2"),str(HERE.parent/"r4b3"),str(HERE.parent/"r4b7")]
import rivals
from bank import bank
P=json.loads((HERE/"protocol.json").read_text());cfg=P["bank"]
OUT=Path("r4b8-output");OUT.mkdir(exist_ok=True)
def load(path,names,env):
    nodes=[x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),"exec"),env);return env
g=load(HERE.parent/"r4b5"/"controls.py",{"extrema","geometric"},{"np":np})
phase=load(HERE.parent/"r4b3"/"phase.py",{"phase_ci"},{"np":np,"least_squares":least_squares})["phase_ci"]
def model(t,v):
    n=len(t);span=t[-1]-t[0];d=(t[-1]-t)/span
    chunks=np.array_split(np.arange(n),min(32,n//8))
    rms=np.array([np.sqrt(np.mean(v[c]**2)) for c in chunks]);centers=np.array([c.mean() for c in chunks])
    scale=np.exp(np.interp(np.arange(n),centers,np.log(np.maximum(rms,1e-280))))
    y=v/scale
    def coords(gap):return np.log1p((1-d)/(d+np.exp(gap)))
    def design(q):
        s=coords(q[0]);u=s/s[-1];a=2*np.pi*q[1]*u
        amp=np.exp(np.clip(q[2]*(s-s[-1]),-700,0))/scale
        B=np.column_stack((amp*np.sin(a),amp*np.cos(a),amp))
        return B/np.maximum(np.linalg.norm(B,axis=0),1e-280)
    def residual(q):
        B=design(q);return B@np.linalg.lstsq(B,y,rcond=None)[0]-y
    def seed(loggap):
        lg=float(np.clip(loggap,-45+1e-9,-1-1e-9));s=coords(lg);u=s/s[-1]
        zz=np.interp(np.linspace(0,1,512),u,y);power=abs(np.fft.rfft((zz-zz.mean())*np.hanning(len(zz)),n=2048))
        f=np.fft.rfftfreq(2048,d=1/511);ii=np.where((f>.2)&(f<45))[0];freq=float(f[ii[np.argmax(power[ii])]])
        beta=float(np.clip(np.polyfit(s,np.log(scale),1)[0],.100001,2.999999))
        return np.array([lg,np.clip(freq,.200001,44.999999),beta])
    def geo():
        a=g["geometric"](t,v)
        if a["status"]!="FINITE":return None,a["status"]
        return seed(np.log((a["t_star_estimate"]-t[-1])/span)),"FINITE"
    def pre(q):return float(np.sqrt(np.mean(residual(q)**2)))
    def solve(q):
        sol=least_squares(residual,q,bounds=([-45,.2,.1],[-1,45,3]),max_nfev=80,ftol=1e-8,xtol=1e-8,gtol=1e-8)
        return {"q":sol.x.tolist(),"gap":float(np.exp(sol.x[0])*span),"period":float(coords(sol.x[0])[-1]/sol.x[1]),"rmse":float(np.sqrt(np.mean(sol.fun**2))),"nfev":int(sol.nfev),"converged":bool(sol.success),"floor":bool(sol.x[0]<-44.999)}
    def classify(a):
        q=a["q"];s=coords(q[0]);y0=v/np.exp(np.clip(q[2]*(s-s[-1]),-700,0))
        pred,*_=rivals.detect(s,t,y0)
        if pred is None:return {"label":"REJECT","stage":"rival"}
        if abs(pred-a["period"])/a["period"]>.05:return {"label":"AMBIGUOUS","stage":"period_consistency"}
        ci=phase(s,y0,s[-1]/pred)
        return {"label":"DSS" if ci["equivalent"] else "AMBIGUOUS","stage":"phase","period":float(pred)}
    def profile(a):
        q=np.asarray(a["q"]);base=a["rmse"]**2;rr=[]
        for off in [-1,-.3,-.1,-.05,0,.05,.1,.3,1]:
            lg=float(np.clip(q[0]+off,-45,-1))
            sol=least_squares(lambda z:residual([lg,*z]),q[1:],bounds=([.2,.1],[45,3]),max_nfev=40)
            val=float(np.mean(sol.fun**2));rr.append({"offset":float(lg-q[0]),"objective":val,"relative_change":float((val-base)/max(base,1e-30)),"frequency":float(sol.x[0]),"beta":float(sol.x[1])})
        return rr
    return seed,geo,pre,solve,classify,profile
def score(a,truth,t,period,full_end=None):
    if a is None or truth is None:return {"local_correct":False,"final_correct":False}
    e=abs(a["gap"]-(truth-t[-1]));p=abs(a["period"]-period)/period
    final=e/(truth-(full_end if full_end is not None else t[-1]));local=e/(truth-t[-1])
    return {"local_correct":bool(local<=.05 and p<=.05),"final_correct":bool(final<=.05 and p<=.05),"local_gap_error":float(local),"final_gap_error":float(final),"period_error":float(p)}
mode,kind=sys.argv[1:3];rows=[]
for sub,i,level,missing,t,v,truth,period in bank(cfg,kind):
    # Same starts for a latent case across all perturbations and noise kinds.
    rr=np.random.default_rng(np.random.SeedSequence([851933,cfg["classes"].index(sub),i]))
    starts=rr.uniform(-45,-1,4)
    if mode=="adaptive":
        seed,geo,pre,solve,classify,profile=model(t,v);gq,gs=geo()
        gp=pre(gq) if gq is not None else None;eligible=gp is not None and gp<=.35
        fixed=[solve(seed(lg)) for lg in starts];ga=solve(gq) if gq is not None else None
        prior=solve(seed(-23));random_best=min(fixed,key=lambda x:x["rmse"])
        adaptive_best=min(([ga]+fixed[1:]) if eligible else fixed,key=lambda x:x["rmse"])
        a={"sub":sub,"i":i,"noise":level,"missing":missing,"geo_status":gs,"geo_prefit_rmse":gp,"geo_eligible":bool(eligible),"geo":ga,"geo_score":score(ga,truth,t,period),"prior":prior,"prior_score":score(prior,truth,t,period),"random_single":fixed[0],"random_single_score":score(fixed[0],truth,t,period),"random_best":random_best,"adaptive_best":adaptive_best}
        for name,b in [("random",random_best),("adaptive",adaptive_best)]:
            a[name+"_score"]=score(b,truth,t,period);a[name+"_class"]=classify(b)
        a["random_nfev"]=sum(x["nfev"] for x in fixed);a["adaptive_nfev"]=sum(x["nfev"] for x in fixed[1:])+ga["nfev"] if eligible else a["random_nfev"]
        rows.append(a)
    elif mode=="forecast":
        if sub!="positive" or level not in P["forecast"]["subset_noise"]:continue
        for fraction in P["forecast"]["fractions"]:
            m=max(16,int(fraction*len(t)));tt=t[:m];vv=v[:m]
            seed,geo,pre,solve,_,profile=model(tt,vv);q,gs=geo();a=solve(q) if q is not None else None
            rows.append({"sub":sub,"i":i,"noise":level,"missing":missing,"fraction":fraction,"geo_status":gs,"fit":a,**score(a,truth,tt,period,t[-1])})
    elif mode=="profile":
        if sub!="positive" or i>=20 or missing!=0 or level not in P["profile"]["noise_levels"]:continue
        for fraction in P["profile"]["window_fractions"]:
            m=max(16,int(fraction*len(t)));tt=t[:m];vv=v[:m]
            seed,geo,pre,solve,_,profile=model(tt,vv);q,gs=geo()
            candidates=[solve(seed(lg)) for lg in starts]
            if q is not None:candidates.append(solve(q))
            a=min(candidates,key=lambda x:x["rmse"]);pr=profile(a)
            rows.append({"sub":sub,"i":i,"noise":level,"missing":missing,"fraction":fraction,"fit":a,"profile":pr,**score(a,truth,tt,period,t[-1])})
    if len(rows) and len(rows)%500==0:print("PROGRESS",mode,kind,len(rows),flush=True)
groups={}
for r in rows:
    key=(r["sub"],r["noise"],r["missing"],r.get("fraction"))
    groups.setdefault(key,[]).append(r)
summary=[]
for (sub,level,missing,fraction),a in sorted(groups.items()):
    item={"sub":sub,"noise":level,"missing":missing,"fraction":fraction,"n":len(a)}
    if mode=="adaptive":
        item["geo_available"]=sum(r["geo"] is not None for r in a);item["geo_eligible"]=sum(r["geo_eligible"] for r in a);item["geo_correct"]=sum(r["geo_score"]["local_correct"] for r in a)
        item["geo_correct_rejected"]=sum(r["geo_score"]["local_correct"] and not r["geo_eligible"] for r in a);item["geo_incorrect_accepted"]=sum(not r["geo_score"]["local_correct"] and r["geo_eligible"] for r in a)
        for name in ("prior","random_single","random","adaptive"):
            item[name+"_correct"]=sum(r[name+"_score"]["local_correct"] for r in a)
        for name in ("random","adaptive"):
            item[name+"_labels"]={lab:sum(r[name+"_class"]["label"]==lab for r in a) for lab in ("DSS","AMBIGUOUS","REJECT")}
            item[name+"_correct_DSS"]=sum(r[name+"_class"]["label"]=="DSS" and r[name+"_score"]["local_correct"] for r in a)
            item[name+"_mean_nfev"]=float(np.mean([r[name+"_nfev"] for r in a]))
    else:
        item["local_correct"]=sum(r["local_correct"] for r in a);item["final_correct"]=sum(r["final_correct"] for r in a)
        item["available"]=sum(r["fit"] is not None for r in a)
        if mode=="profile":
            item["median_relative_objective_change"]= [float(np.median([r["profile"][j]["relative_change"] for r in a])) for j in range(9)]
    summary.append(item)
result={"mode":mode,"kind":kind,"n":len(rows),"summary":summary,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"scientific_hold":True,"physical_use_authorized":False,"limitations":["Adaptive replacement has equal selected-start count, but audit computes both paths and diagnostic prior/geometry separately; nfev is not total CPU.","Profile assumes DSS and is local, not calibrated confidence.","Classifier phase CI remains unqualified; no scientific admission."]}
for name,obj in (("trials.json",rows),("result.json",result)):(OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
print("R4B8_RESULT",json.dumps(result,allow_nan=False),flush=True)
