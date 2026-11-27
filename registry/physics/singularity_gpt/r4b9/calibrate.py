"""Joint drift profile score; separate calibration and independent exam."""
from common import *
from scipy.special import ndtr
C=P["calibration"];mode=sys.argv[1]
def profile_model(t,v,a):
    n=len(t);span=t[-1]-t[0];d=(t[-1]-t)/span
    chunks=np.array_split(np.arange(n),min(32,n//8))
    rms=np.array([np.sqrt(np.mean(v[c]**2)) for c in chunks]);centers=np.array([c.mean() for c in chunks])
    scale=np.exp(np.interp(np.arange(n),centers,np.log(np.maximum(rms,1e-280))));y=v/scale
    def residual(q):
        s=np.log1p((1-d)/(d+np.exp(q[0])));u=s/s[-1]
        ang=2*np.pi*(q[1]*u+.5*q[3]*u*u)
        amp=np.exp(np.clip(q[2]*(s-s[-1]),-700,0))/scale
        B=np.column_stack((amp*np.sin(ang),amp*np.cos(ang),amp));B/=np.maximum(np.linalg.norm(B,axis=0),1e-280)
        return B@np.linalg.lstsq(B,y,rcond=None)[0]-y
    lo=[-45,.2,.1,-.3];hi=[-1,45,3,.3]
    sols=[least_squares(residual,[*a["q"],dr],bounds=(lo,hi),max_nfev=80,ftol=1e-8,xtol=1e-8,gtol=1e-8) for dr in (0.,-.06,.06)]
    sol=min(sols,key=lambda x:float(np.dot(x.fun,x.fun)));rss=max(float(np.dot(sol.fun,sol.fun)),1e-250)
    def profile(dr):
        if not sol.success:return None
        b=least_squares(lambda q:residual([*q,dr]),sol.x[:3],bounds=(lo[:3],hi[:3]),max_nfev=80,ftol=1e-8,xtol=1e-8,gtol=1e-8)
        val=float(np.dot(b.fun,b.fun))
        # A constrained fit materially beating the unrestricted fit invalidates the local profile.
        if not b.success or not np.isfinite(val) or val<rss*(1-1e-6):return None
        return float(max(0,n*np.log(max(val,1e-250)/rss)))
    return float(sol.x[3]),bool(sol.success),profile
def old_diagnostics(t,v,a,c,keep):
    q=a["q"];d=(t[-1]-t)/(t[-1]-t[0]);s=np.log1p((1-d)/(d+np.exp(q[0])));y=v/np.exp(np.clip(q[2]*(s-s[-1]),-700,0))
    pred,*_=rivals.detect(s,t,y)
    if pred is None:reason="RIVAL_REJECT";label="REJECT"
    elif abs(pred-a["period"])/a["period"]>.05:reason="PERIOD_CONSISTENCY";label="AMBIGUOUS"
    else:reason="PHASE";label=None
    ci=phase(s,y,float(s[-1]/pred) if pred is not None else float(q[1]))
    if not ci["fit_success"]:why="FIT_FAILURE"
    elif ci["equivalent"]:why="EQUIVALENT"
    elif 1.96*ci["se"]>.012:why="HALFWIDTH_EXCEEDS_MARGIN"
    elif abs(ci["drift"])>=.012:why="CENTER_OUTSIDE"
    else:why="BOUNDARY_OVERLAP"
    if label is None:label="DSS" if ci["equivalent"] else "AMBIGUOUS"
    out=dict(label=label,stage=reason,phase_reason=why,phase=ci,screen=reason=="PHASE")
    if c["star"] is not None:
        oracle=phase(c["s"][keep],v/c["env"][keep],6.)
        for k,z in (("blind",ci),("oracle",oracle)):
            out[k+"_coverage"]=bool(z["ci95"][0]<=c["drift"]<=z["ci95"][1]);out[k+"_halfwidth"]=float(1.96*z["se"]);out[k+"_drift"]=z["drift"]
            out[k+"_pit"]=float(ndtr((c["drift"]-z["drift"])/z["se"])) if z["se"]>0 else None
    return out
if mode=="aggregate":
    source=Path(sys.argv[2]);stats=[]
    for file in sorted(source.rglob("calibration.json")):
        q=json.loads(file.read_text())
        assert q["protocol_sha256"]==PROTOCOL_SHA and q["seed"]==C["seed"]
        stats+=q["strata"]
    assert len(stats)==24 and len({(x["kind"],x["sub"],x["noise"],x["missing"]) for x in stats})==24
    threshold=None if any(x["quantile"] is None for x in stats) else max(x["quantile"] for x in stats)
    result=dict(protocol_sha256=PROTOCOL_SHA,seed=C["seed"],threshold=threshold,strata=stats,meaning="None denotes infinite threshold from failed fits; classifier abstains.")
    (OUT/"frozen_threshold.json").write_text(dumps(result)+"\n");print("R4B9_CALIBRATION",dumps(result),flush=True);sys.exit(0)
kind=sys.argv[2];rows=[];split_seed=C["seed"] if mode=="calibrate" else C["evaluation_seed"]
threshold=None
if mode=="evaluate":
    frozen=json.loads(Path(sys.argv[3]).read_text())
    assert frozen["protocol_sha256"]==PROTOCOL_SHA and frozen["seed"]==C["seed"] and split_seed!=frozen["seed"]
    threshold=frozen["threshold"]
for c in explicit_bank(C,kind,split_seed):
    if mode=="calibrate" and c["star"] is None:continue
    for level in C["noise_levels"]:
        for missing in C["missing"]:
            keep=mask(c,missing);t=c["t"][keep];v=(c["env"]*(c["base"]+level*c["noise"]))[keep]
            fits,_=candidates(t,v,c["sub"],c["i"]);a=min(fits,key=lambda f:f["rmse"])
            good=score(a,c["star"],t,c["period"])["local_correct"]
            old=old_diagnostics(t,v,a,c,keep)
            est,success,pr=profile_model(t,v,a)
            true_score=pr(c["drift"]) if c["star"] is not None else None
            r=dict(sub=c["sub"],i=c["i"],kind=kind,noise=level,missing=missing,correct_params=good,old=old,drift_truth=c["drift"] if c["star"] is not None else None,drift_fit=est,profile_fit_success=success,true_score=true_score,input_sha256=hashlib.sha256(np.asarray(np.column_stack((t,v)),dtype="<f8").tobytes()).hexdigest())
            if mode=="evaluate":
                scores=[pr(dr) for dr in C["grid"]]
                grid_complete=all(x is not None for x in scores)
                admitted=[dr for dr,x in zip(C["grid"],scores) if x is not None and threshold is not None and x<=threshold]
                r["grid_scores"]=scores;r["grid_complete"]=grid_complete;r["admitted_grid"]=admitted
                # Conservative abstention on missing fits or infinite threshold. Grid is not a continuous certificate.
                if old["stage"]=="RIVAL_REJECT":label="REJECT"
                elif old["screen"] and success and grid_complete and admitted and abs(est)<.012 and all(abs(dr)<.012 for dr in admitted):label="DSS"
                else:label="AMBIGUOUS"
                r["candidate_label"]=label;r["covered"]=bool(true_score is not None and (threshold is None or true_score<=threshold)) if c["star"] is not None else None
            rows.append(r)
    if c["i"]%20==0:print("PROGRESS",mode,kind,c["sub"],c["i"],len(rows),flush=True)
groups={}
for r in rows:groups.setdefault((r["sub"],r["noise"],r["missing"]),[]).append(r)
summary=[]
for (sub,noise,missing),a in sorted(groups.items()):
    z=[r["true_score"] for r in a if r["true_score"] is not None]
    ordered=sorted(z);k=int(np.ceil((len(a)+1)*.95))
    item=dict(kind=kind,sub=sub,noise=noise,missing=missing,n=len(a),profile_failures=len(a)-len(z) if sub!="stationary" else None,correct_params=sum(r["correct_params"] for r in a),old_labels={lab:sum(r["old"]["label"]==lab for r in a) for lab in ("DSS","AMBIGUOUS","REJECT")},old_ambiguous_correct_params=sum(r["correct_params"] and r["old"]["label"]=="AMBIGUOUS" for r in a),old_phase_reasons={why:sum(r["old"]["phase_reason"]==why for r in a if r["old"]["label"]=="AMBIGUOUS" and r["old"]["stage"]=="PHASE") for why in ("FIT_FAILURE","HALFWIDTH_EXCEEDS_MARGIN","CENTER_OUTSIDE","BOUNDARY_OVERLAP","EQUIVALENT")},old_ambiguous_stage={why:sum(r["old"]["stage"]==why and r["old"]["label"]=="AMBIGUOUS" for r in a) for why in ("PERIOD_CONSISTENCY","PHASE")})
    if sub!="stationary":
        for kind2 in ("blind","oracle"):
            v=[r["old"][kind2+"_pit"] for r in a if r["old"][kind2+"_pit"] is not None];counts,_=np.histogram(v,bins=np.linspace(0,1,21))
            item[kind2+"_coverage"]=sum(r["old"][kind2+"_coverage"] for r in a);item[kind2+"_median_halfwidth"]=float(np.median([r["old"][kind2+"_halfwidth"] for r in a]));item[kind2+"_median_signed_drift_error"]=float(np.median([r["old"][kind2+"_drift"]-r["drift_truth"] for r in a]));item[kind2+"_pit"]={"n":len(v),"mean":float(np.mean(v)) if v else None,"variance":float(np.var(v)) if v else None,"histogram":counts.tolist()}
    if mode=="calibrate":item["quantile"]=ordered[k-1] if k<=len(ordered) else None
    else:item.update(candidate_labels={lab:sum(r["candidate_label"]==lab for r in a) for lab in ("DSS","AMBIGUOUS","REJECT")},candidate_correct_DSS=sum(r["candidate_label"]=="DSS" and r["correct_params"] for r in a),old_correct_DSS=sum(r["old"]["label"]=="DSS" and r["correct_params"] for r in a),profile_coverage=sum(r["covered"] is True for r in a) if sub!="stationary" else None,grid_failures=sum(not r["grid_complete"] for r in a))
    summary.append(item)
if mode=="calibrate":
    (OUT/"calibration.json").write_text(dumps(dict(protocol_sha256=PROTOCOL_SHA,seed=split_seed,strata=[{k:x[k] for k in ("kind","sub","noise","missing","n","profile_failures","quantile")} for x in summary]))+"\n")
save(mode,rows,summary,kind=kind,seed=split_seed,threshold=threshold,limitations=["Profile score is a local joint refit, not a globally certified likelihood surface.","Calibration and exam use disjoint latent seeds; shared perturbations within split are not independent strata.","A grid confidence set is not a continuous region; scientific hold even if candidate counts pass.","Failed truth profiles remain in denominator; no physical inference."])
