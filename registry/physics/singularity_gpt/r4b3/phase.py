"""Three-way phase equivalence: oracle and training-only nuisance estimate."""
import json,sys,hashlib
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"r4b2"))
import rivals
from generator import cases
P=json.loads((HERE/"protocol.json").read_text());D=P["phase"]
OUT=Path("r4b3-output");OUT.mkdir(exist_ok=True)
mode=sys.argv[1];assert mode in ("oracle","blind")
def write(n,x): (OUT/n).write_text(json.dumps(x,indent=2,allow_nan=False)+"\n")
def normalize_blind(t,v):
    # Only first 55% waveform used to select nuisance parameters. The observed
    # sampling times are known; no true accumulation time or envelope supplied.
    n=len(t);m=int(.55*n);span=t[-1]-t[0];d=(t[-1]-t)/span
    best=None
    for lg in np.linspace(-45,-1,29):
        gap=np.exp(lg);s=-np.log((d+gap)/(1+gap));u=s/s[-1]
        idx=np.array_split(np.arange(m),12)
        a=np.array([np.sqrt(np.mean(v[z]**2)) for z in idx]);x=np.array([np.mean(s[z]) for z in idx])
        if min(a)<=0:continue
        slope,b=np.polyfit(x,np.log(a),1)
        if not (.1<=slope<=3):continue
        logenv=np.clip(b+slope*s,-650,650);y=v/np.exp(logenv)
        if not np.isfinite(y).all():continue
        # quick training-only FFT phase fit; normalized span spans unknown cycles
        z=np.interp(np.linspace(u[0],u[m-1],512),u[:m],y[:m])
        freq=np.fft.rfftfreq(2048,d=(u[m-1]-u[0])/511)
        amp=abs(np.fft.rfft((z-z.mean())*np.hanning(len(z)),n=2048))
        good=(freq>.3)&(freq<45)
        if not np.any(good):continue
        f=float(freq[np.where(good)[0][np.argmax(amp[good])]])
        bmat=np.column_stack((np.ones(m),np.sin(2*np.pi*f*u[:m]),np.cos(2*np.pi*f*u[:m])))
        residual=y[:m]-bmat@np.linalg.lstsq(bmat,y[:m],rcond=None)[0]
        loss=float(np.mean(residual**2)/max(np.mean(y[:m]**2),1e-20)+.05*np.mean((np.log(a)-(b+slope*x))**2))
        if best is None or loss<best[0]:best=(loss,s,y,lg,float(slope))
    if best is None:return None
    _,s,y,lg,beta=best
    return s,y,{"log_gap_estimate":float(lg),"envelope_exponent_estimate":beta}
def phase_ci(s,y,f0):
    u=s/s[-1];n=len(y)
    scale=max(np.sqrt(np.mean(y*y)),1e-12);z=y/scale
    a=2*np.pi*f0*u;B=np.column_stack((np.ones(n),np.sin(a),np.cos(a)))
    w=np.linalg.lstsq(B,z,rcond=None)[0]
    def pred(p):
        a=2*np.pi*(p[3]*u+.5*p[4]*u*u)
        return p[0]+p[1]*np.sin(a)+p[2]*np.cos(a)
    p0=np.r_[w,np.clip(f0,.21,44.9),0.]
    sol=least_squares(lambda p:pred(p)-z,p0,bounds=([-20,-20,-20,.2,-20],[20,20,20,45,20]),max_nfev=60)
    J=sol.jac;r=sol.fun;bread=np.linalg.pinv(J.T@J,rcond=1e-12)
    # Approximate block sandwich, with independent-noise floor. Coverage is not guaranteed.
    groups=np.array_split(np.arange(n),max(8,n//32))
    score=np.array([J[g].T@r[g] for g in groups])
    cov=bread@(score.T@score)@bread*len(groups)/(len(groups)-1)
    iid=bread*float(np.dot(r,r)/max(n-5,1))
    se=float(np.sqrt(max(cov[4,4],iid[4,4],0)))
    est=float(sol.x[4]);ci=[est-1.96*se,est+1.96*se]
    return {"drift":est,"se":se,"ci95":ci,"fit_success":bool(sol.success),"equivalent":bool(sol.success and ci[0]>=-.012 and ci[1]<=.012)}
rows=[]
for c in cases(D):
    if mode=="oracle":s=c["s"];y=c["raw"]/c["envelope"];nu={"oracle":True}
    else:
        q=normalize_blind(c["t"],c["raw"])
        if q is None:s=y=None;nu={"nuisance_fit_failed":True}
        else:s,y,nu=q
    pred=None;ci=None;label="AMBIGUOUS";scores=None
    if s is not None and np.isfinite(y).all() and max(abs(y))<1e100:
        pred,scores,_,_=rivals.detect(s,c["t"],y)
        if pred is None:label="REJECT"
        else:
            ci=phase_ci(s,y,s[-1]/pred)
            if ci["equivalent"]:label="DSS"
    truth=c["truth_period"];err=abs(pred-truth)/truth if pred is not None and truth is not None else None
    correct=label=="DSS" and err is not None and err<=.05 if c["subtype"]=="positive" else label!="DSS"
    rows.append({"subtype":c["subtype"],"i":c["i"],"kind":c["kind"],"level":c["level"],"truth_period":truth,"truth_drift":c["truth_drift"],"pred":pred,"relative_error":err,"label":label,"correct":bool(correct),"phase":ci,"nuisance":nu,"input_sha256":hashlib.sha256(np.asarray(np.column_stack((c["t"],c["raw"])),dtype="<f8").tobytes()).hexdigest()})
    if len(rows)%600==0:print("PROGRESS",mode,len(rows),flush=True);write("partial_trials.json",rows)
summary=[]
for k,l,sub in sorted({(r["kind"],r["level"],r["subtype"]) for r in rows}):
    a=[r for r in rows if (r["kind"],r["level"],r["subtype"])==(k,l,sub)]
    summary.append({"kind":k,"level":l,"subtype":sub,"n":len(a),"DSS":sum(r["label"]=="DSS" for r in a),"AMBIGUOUS":sum(r["label"]=="AMBIGUOUS" for r in a),"REJECT":sum(r["label"]=="REJECT" for r in a),"correct":sum(r["correct"] for r in a)})
gate=all(r["correct"]>=90 and r["AMBIGUOUS"]<=5 if r["subtype"]=="positive" else r["DSS"]<=5 for r in summary)
result={"mode":mode,"summary":summary,"gate":gate,"generator_sha256":hashlib.sha256((HERE/"generator.py").read_bytes()).hexdigest(),"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"synthetic_only":True,"physical_use_authorized":False,"confidence_coverage_validated":False,"scientific_hold":True,"limitations":["Blind nuisance uses observed sampling schedule and training amplitude; not independent physical sampling.","Approximate block covariance, confidence interval coverage not independently validated.","Rejection and ambiguity both count as no false DSS; positive ambiguity and sensitivity separately gated."]}
write("trials.json",rows);write("result.json",result);print("R4B3_PHASE_RESULT",json.dumps(result,allow_nan=False),flush=True)
