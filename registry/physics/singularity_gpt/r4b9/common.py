"""R4B9 helpers; frozen parent methods loaded without executing their drivers."""
import ast,hashlib,json,sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from scipy.ndimage import median_filter
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/x) for x in ("r4b2","r4b3","r4b7")]
import rivals
from bank import bank
P=json.loads((HERE/"protocol.json").read_text())
PROTOCOL_SHA=hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest()
OUT=Path("r4b9-output");OUT.mkdir(exist_ok=True)
def load(path,names,env):
    nodes=[x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),"exec"),env)
    return env
g=load(HERE.parent/"r4b5"/"controls.py",{"extrema","geometric"},{"np":np})
phase=load(HERE.parent/"r4b3"/"phase.py",{"phase_ci"},{"np":np,"least_squares":least_squares})["phase_ci"]
old=load(HERE.parent/"r4b8"/"examine.py",{"model","score"},{"np":np,"g":g,"rivals":rivals,"phase":phase,"least_squares":least_squares})
model,score=old["model"],old["score"]
seq=load(HERE.parent/"r4b8a"/"examine.py",{"sequence","cluster_select"},{"np":np,"g":g,"least_squares":least_squares,"median_filter":median_filter})
sequence,cluster_select=seq["sequence"],seq["cluster_select"]
def dumps(obj):return json.dumps(obj,allow_nan=False,separators=(",",":"))
def save(mode,rows,summary,**extra):
    result={"mode":mode,"n":len(rows),"summary":summary,"protocol_sha256":PROTOCOL_SHA,"scientific_hold":True,"physical_use_authorized":False,**extra}
    for name,x in (("trials.json",rows),("result.json",result)):(OUT/name).write_text(dumps(x)+"\n")
    print("R4B9_RESULT",dumps(result),flush=True)
def explicit_bank(cfg,kind,seed):
    for sub in cfg["classes"]:
        for i in range(cfg["n_per_class"]):
            # Same latent signal across noise kinds and perturbations, disjoint seeds across splits.
            rng=np.random.default_rng(np.random.SeedSequence([seed,cfg["classes"].index(sub),i]))
            period=float(rng.uniform(1.2,5.6));u=np.linspace(0,1,769);s=u*6*period
            beta=float(rng.uniform(.6,1.4));ph=float(rng.uniform(0,2*np.pi))
            drift=float(rng.uniform(.015,.15)*rng.choice([-1,1])) if sub=="near_dss_chirp" else 0.
            star=0. if i%2==0 else .5*np.exp(-s[-1]);t=star-np.exp(-s)
            e=np.exp(beta*(s-s[-1]))
            if sub=="stationary":t=u.copy();e=np.ones(len(u));star=None
            a=2*np.pi*(6*u+.5*drift*u*u)+ph;base=np.sin(a)
            def ar(rho):
                x=rng.standard_normal(len(u))
                for j in range(1,len(x)):x[j]=rho*x[j-1]+np.sqrt(1-rho*rho)*x[j]
                return x
            iid=rng.standard_normal(len(u));long=.7*ar(.98)+.3*ar(.85)
            narrow=np.sin(2*np.pi*(6+rng.choice([-1,1])*rng.uniform(.2,3))*u+rng.uniform(0,2*np.pi))+.25*iid
            z={"iid":iid,"long_memory":long,"narrowband":narrow}[kind];z=z/max(np.std(z),1e-30)
            draw=rng.uniform(size=len(u))
            yield dict(sub=sub,i=i,period=period,star=star,drift=drift,u=u,s=s,t=t,env=e,base=base,angle=a,noise=z,draw=draw,phase=ph)
def mask(c,missing):
    keep=c["draw"]>=missing;keep[0]=keep[-1]=True;return keep
def candidates(t,v,sub,i):
    sd,geo,pre,solve,cl,_=model(t,v)
    rng=np.random.default_rng(np.random.SeedSequence([851933,["positive","near_dss_chirp","stationary"].index(sub),i]))
    starts=rng.uniform(-45,-1,4);q,gs=geo()
    eligible=q is not None and pre(q)<=.35
    qs=[sd(x) for x in starts]
    if eligible:qs[0]=q
    fits=[solve(x) for x in qs]
    return fits,cl
def phase_details(t,v,a,truth=None):
    q=a["q"];span=t[-1]-t[0];d=(t[-1]-t)/span
    s=np.log1p((1-d)/(d+np.exp(q[0])));y=v/np.exp(np.clip(q[2]*(s-s[-1]),-700,0))
    ci=phase(s,y,float(q[1]))
    if not ci["fit_success"]:reason="FIT_FAILURE"
    elif ci["equivalent"]:reason="EQUIVALENT"
    elif 1.96*ci["se"]>.012:reason="HALFWIDTH_EXCEEDS_MARGIN"
    elif abs(ci["drift"])>=.012:reason="CENTER_OUTSIDE"
    else:reason="BOUNDARY_OVERLAP"
    ci["reason"]=reason
    if truth is not None:ci["coverage"]=bool(ci["ci95"][0]<=truth<=ci["ci95"][1])
    return ci
