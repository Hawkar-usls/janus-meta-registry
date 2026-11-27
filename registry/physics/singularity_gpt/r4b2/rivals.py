"""Synthetic-only rival-model predictive qualification. No physical DSS claims."""
import json,math,hashlib,sys,ast
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
HERE=Path(__file__).resolve().parent
P=json.loads((HERE/"protocol.json").read_text());D=P["detector"];OUT=Path("r4b2-output");OUT.mkdir(exist_ok=True)
def write(n,d): (OUT/n).write_text(json.dumps(d,indent=2,allow_nan=False)+"\n")
def basis(u,t,model,q):
    if model=="DSS":
        a=2*np.pi*q[0]*u;env=np.ones_like(u)
    elif model=="CHIRP":
        a=2*np.pi*(q[0]*u+.5*q[1]*u*u);env=np.ones_like(u)
    elif model=="LINEAR_TIME":
        a=2*np.pi*q[0]*t;env=np.exp(np.clip(q[1]*(u-.5),-12,12))
    elif model=="TRANSIENT":
        a=2*np.pi*q[0]*u;env=np.exp(-.5*((u-q[1])/q[2])**2)
    else:return np.ones((len(u),1))
    return np.column_stack((np.ones_like(u),env*np.sin(a),env*np.cos(a)))
def fit(u,t,y,model):
    m=len(y)
    if model=="NOISE":return np.array([]),np.array([y.mean()])
    # FFT seeds from training only. Full-span frequencies are not supplied by generator.
    coord=t[:m] if model=="LINEAR_TIME" else u[:m]
    z=np.interp(np.linspace(coord[0],coord[-1],m),coord,y)
    fft=abs(np.fft.rfft((z-z.mean())*np.hanning(m),n=4096))
    freq=np.fft.rfftfreq(4096,d=(coord[-1]-coord[0])/(m-1))
    mask=(freq>=.3)&(freq<=40)
    inds=np.flatnonzero(mask);ix=inds[np.argmax(fft[inds])];f=float(freq[ix])
    if model=="DSS": starts=[[f],[max(.3,f-1.5)],[min(40,f+1.5)]];lo=[.2];hi=[45]
    elif model=="CHIRP": starts=[[f,0],[max(.3,f-1),4],[min(40,f+1),-4]];lo=[.2,-20];hi=[45,20]
    elif model=="LINEAR_TIME":starts=[[f,0],[max(.3,f/2),0]];lo=[.2,-8];hi=[45,8]
    else:starts=[[f,.4,.25],[f,.7,.45]];lo=[.2,0,.04];hi=[45,1.2,1.5]
    def residual(q):
        b=basis(u[:m],t[:m],model,q);w=np.linalg.lstsq(b,y,rcond=None)[0]
        return b@w-y
    best=None
    for q in starts:
        sol=least_squares(residual,np.clip(q,np.array(lo)+1e-8,np.array(hi)-1e-8),bounds=(lo,hi),max_nfev=45,ftol=1e-6,xtol=1e-6)
        cost=float(np.dot(sol.fun,sol.fun))
        if best is None or cost<best[0]:best=(cost,sol.x)
    q=best[1];b=basis(u[:m],t[:m],model,q);w=np.linalg.lstsq(b,y,rcond=None)[0]
    return q,w
def detect(s,t,y):
    u=s/s[-1];t=(t-t[0])/(t[-1]-t[0]);n=len(y);m=int(.55*n);k=int(.78*n)
    models=("DSS","CHIRP","LINEAR_TIME","TRANSIENT","NOISE")
    pred={};params={}
    for name in models:
        q,w=fit(u,t,y[:m],name);pred[name]=basis(u,t,name,q)@w;params[name]=q
    r=y[:m]-pred["DSS"][:m];r0=r[:-1];r1=r[1:];rho=float(np.clip(np.dot(r0,r1)/max(np.dot(r0,r0),1e-20),-.95,.95))
    sig=max(float(np.sqrt(np.mean((r1-rho*r0)**2))),1e-6)
    scale=max(float(np.sqrt(np.mean(y[:m]**2))),1e-9)
    scores={}
    for name in models:
        r=y-pred[name];wh=r[1:]-rho*r[:-1];p=len(params[name])+ (1 if name=="NOISE" else 3)
        # Shared conditional Gaussian error model. Scores are predictive losses, not posteriors.
        def loss(lo,hi):
            v=wh[lo-1:hi-1];return float(.5*np.mean((v/sig)**2)+np.log(sig)+p*np.log(m)/(2*(hi-lo)))
        def rmse(lo,hi):return float(np.sqrt(np.mean(r[lo:hi]**2))/scale)
        scores[name]={"validation_nrmse":rmse(m,k),"test_nrmse":rmse(k,n),"validation_conditional_nll":loss(m,k),"test_conditional_nll":loss(k,n),"parameters":params[name].tolist()}
    ds=scores["DSS"];rivals=[scores[x] for x in models if x!="DSS"]
    good=all(ds[key]<=.15 for key in ("validation_nrmse","test_nrmse"))
    # A practically indistinguishable nested chirp with almost zero curvature is
    # not evidence against DSS; strongly improved prediction by any rival rejects.
    for key in ("validation_nrmse","test_nrmse"):
        if any(ds[key]-r[key]>.015 for r in rivals):good=False
    # Phase-coherence check via both contiguous held-out blocks above.
    period=float(s[-1]/params["DSS"][0]) if good else None
    return period,scores,rho,sig
def bank(seed):
    rng=np.random.default_rng(seed);n=D["points"];rows=[]
    for subtype in ["positive"]+D["negative_subtypes"]:
        for i in range(D["n_each_positive_and_each_negative_subtype"]):
            period=float(rng.uniform(*D["period_range"]));s=np.linspace(0,D["cycles"]*period,n);u=s/s[-1]
            t=-np.exp(-s);phase=rng.uniform(0,2*np.pi);freq=D["cycles"]
            env=np.exp(s-s[-1])
            if subtype=="positive":base=np.sin(2*np.pi*freq*u+phase)
            elif subtype in ("chirp","near_dss_chirp"):
                d=float(rng.uniform(.7,4) if subtype=="chirp" else rng.uniform(.015,.15))*rng.choice([-1,1])
                base=np.sin(2*np.pi*(freq*u+.5*d*u*u)+phase)
            elif subtype=="linear_time":base=np.sin(2*np.pi*freq*(t-t[0])/(t[-1]-t[0])+phase)
            elif subtype=="transient":base=np.exp(-.5*((u-rng.uniform(.2,.8))/rng.uniform(.07,.22))**2)*np.sin(2*np.pi*freq*u+phase)
            else:
                base=rng.standard_normal(n)
                for j in range(1,n):base[j]=.85*base[j-1]+np.sqrt(1-.85**2)*base[j]
            # Same latent waveform, phase, and iid innovation for every noise type/level.
            iid=rng.standard_normal(n);ar=iid.copy()
            for j in range(1,n):ar[j]=.94*ar[j-1]+np.sqrt(1-.94**2)*ar[j]
            structured=.65*np.sin(2*np.pi*(19*u+7*u*u)+rng.uniform(0,2*np.pi))+.35*iid
            for kind,z in (("iid",iid),("ar1",ar),("structured",structured)):
                z=z/max(np.std(z),1e-20)
                for level in D["noise_levels"]:
                    y=base+level*z
                    pred,scores,rho,sig=detect(s,t,y)
                    err=abs(pred-period)/period if pred is not None and subtype=="positive" else None
                    rows.append({"subtype":subtype,"i":i,"noise":kind,"level":level,"truth":period if subtype=="positive" else None,"estimate":pred,"relative_error":err,"correct":bool(err is not None and err<=.05) if subtype=="positive" else pred is None,"scores":scores,"training_ar1":rho,"training_scale":sig})
        print("SUBTYPE_DONE",subtype,flush=True);write("partial_trials.json",rows)
    return rows
def legacy():
    path=HERE.parent/"r3b"/"echo_probe.py";node=next(x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name=="echo_estimate")
    env={"np":np,"math":math};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),"exec"),env)
    rows=[]
    for p in np.arange(1,6.001,.25):
        s=np.linspace(0,5*p,16384);t=-np.exp(-s);v=np.exp(s-s[-1])*np.sin(2*np.pi*s/p+.31);mag=abs(v)
        raw=np.where((mag[1:-1]>mag[:-2])&(mag[1:-1]>=mag[2:]))[0]+1
        r=env["echo_estimate"](np.column_stack((t,t,v,8*np.pi*v*v,np.zeros_like(t),np.ones_like(t))),12288)
        rows.append({"period":float(p),"raw_peaks":len(raw),"retained_after_cutoff":int(np.sum(mag[raw]>max(mag)*1e-4)),"detected":r["candidate"] is not None})
    return rows
def main():
    rows=bank(D["seed"]);summary=[]
    for kind in D["noise_types"]:
        for level in D["noise_levels"]:
            for sub in ["positive"]+D["negative_subtypes"]:
                rr=[r for r in rows if r["noise"]==kind and r["level"]==level and r["subtype"]==sub]
                summary.append({"noise":kind,"level":level,"subtype":sub,"n":len(rr),"correct":sum(r["correct"] for r in rr),"detections":sum(r["estimate"] is not None for r in rr)})
    gate=all(r["correct"]>=90 if r["subtype"]=="positive" else r["detections"]<=5 for r in summary)
    result={"summary":summary,"gate":gate,"legacy_filter_sweep":legacy(),"synthetic_only":True,"known_accumulation_time_and_envelope":True,"physical_DSS_established":False,"scientific_hold":True,"production_changed":False,"limitations":["Shared conditional Gaussian residual model, not validated physical likelihoods; NLL reported but decision uses held-block NRMSE.","Known generator envelope divided out, known accumulation time; no physical application authorized.","Near-DSS chirps may be observationally indistinguishable; count as negative by construction, not physical classification.","Paired bank tests noise differences on identical latent signals; not direct replay of R4B0 detector; original generator audit remains separate."],"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest()}
    write("all_trials.json",rows);write("result.json",result);print("R4B2_RESULT",json.dumps(result,allow_nan=False),flush=True)
if __name__=="__main__":main()
