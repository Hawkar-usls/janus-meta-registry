"""Tangent-first selection stress and matched robust forecast replay."""
from common import *
mode=sys.argv[1];rows=[]
if mode=="stress":
    C=P["stress"]
    for c in explicit_bank(C,"narrowband",C["seed"]):
        u=c["u"];a=c["angle"];z=c["noise"]
        B=np.column_stack((np.ones(len(u)),np.sin(a),np.cos(a),2*np.pi*u*np.cos(a)))
        Q,_=np.linalg.qr(B);direction=np.pi*u*u*np.cos(a);direction-=Q@(Q.T@direction);direction/=np.linalg.norm(direction)
        tangent=direction*np.dot(direction,z);orth=z-tangent
        for missing in C["missing"]:
            keep=mask(c,missing);t=c["t"][keep]
            for level in C["levels"]:
                for comp,w in (("ordinary",z),("tangent",tangent),("orthogonal",orth)):
                    v=(c["env"]*(c["base"]+level*w))[keep]
                    fits,cl=candidates(t,v,c["sub"],c["i"])
                    any_correct=any(score(f,c["star"],t,c["period"])["local_correct"] for f in fits)
                    for name,f in (("min_objective",min(fits,key=lambda x:x["rmse"])),("consensus",cluster_select(fits))):
                        good=score(f,c["star"],t,c["period"])["local_correct"]
                        rows.append(dict(sub=c["sub"],i=c["i"],noise=level,missing=missing,component=comp,method=name,any_correct=any_correct,correct=good,selected_wrong=any_correct and not good,label=cl(f)["label"],phase=phase_details(t,v,f,c["drift"]) if c["star"] is not None else None,energy_fraction=float(np.dot(w,w)/np.dot(z,z)),input_sha256=hashlib.sha256(np.asarray(np.column_stack((t,v)),dtype="<f8").tobytes()).hexdigest()))
        if c["sub"]=="positive":
            # Exact mimic: same observation can be either a DSS plus coherent perturbation
            # or an unperturbed near-chirp. This is a counterexample, not a random noise rate.
            u=c["u"];t=c["t"];delta=.015
            mimic=np.sin(c["angle"]+np.pi*delta*u*u)
            v=c["env"]*mimic
            fits,cl=candidates(t,v,c["sub"],c["i"])
            for name,f in (("min_objective",min(fits,key=lambda x:x["rmse"])),("consensus",cluster_select(fits))):
                label=cl(f)["label"]
                for sub in ("positive","near_dss_chirp"):
                    rows.append(dict(sub=sub,i=c["i"],noise=None,missing=0,component="exact_mimic",method=name,any_correct=None,correct=None,selected_wrong=None,label=label,phase=None,perturbation_rms=float(np.sqrt(np.mean((mimic-c["base"])**2))),input_sha256=hashlib.sha256(np.asarray(np.column_stack((t,v)),dtype="<f8").tobytes()).hexdigest()))
        if c["i"]%20==0:print("STRESS",c["sub"],c["i"],len(rows),flush=True)
    groups={}
    for r in rows:groups.setdefault((r["sub"],r["noise"],r["missing"],r["component"],r["method"]),[]).append(r)
    summary=[]
    for (sub,noise,missing,comp,meth),a in groups.items():
        ci=[r["phase"] for r in a if r["phase"] is not None]
        summary.append(dict(sub=sub,noise=noise,missing=missing,component=comp,method=meth,n=len(a),correct=sum(r["correct"] is True for r in a),any_correct=sum(r["any_correct"] is True for r in a),wrong_given_correct=sum(r["selected_wrong"] is True for r in a),DSS=sum(r["label"]=="DSS" for r in a),AMBIGUOUS=sum(r["label"]=="AMBIGUOUS" for r in a),REJECT=sum(r["label"]=="REJECT" for r in a),phase_n=len(ci),phase_covered=sum(q["coverage"] for q in ci)))
    save(mode,rows,summary,exact_mimic_note="Identical input evaluated with identical seed and output under both labels; no classifier can distinguish those two explanations from these observations alone.")
elif mode=="forecast":
    kind=sys.argv[2];C=P["forecast"]
    for sub,i,level,missing,t,v,truth,period in bank(C,kind):
        for frac in C["fractions"]:
            m=int(frac*len(t));tt=t[:m];vv=v[:m];sd,geo,pre,solve,_,_=model(tt,vv)
            q,status=geo();lg,status2=sequence(tt,vv);q2=sd(lg) if lg is not None else None
            for name,start,st in (("legacy_single",q,status),("sequence_single",q2,status2)):
                fit=solve(start) if start is not None else None
                rows.append(dict(i=i,noise=level,missing=missing,fraction=frac,method=name,status=st,**score(fit,truth,tt,period,t[-1])))
    groups={}
    for r in rows:groups.setdefault((r["noise"],r["missing"],r["fraction"],r["method"]),[]).append(r)
    summary=[dict(noise=k[0],missing=k[1],fraction=k[2],method=k[3],n=len(a),available=sum(r["status"]=="FINITE" for r in a),local_correct=sum(r["local_correct"] for r in a),final_correct=sum(r["final_correct"] for r in a)) for k,a in sorted(groups.items())]
    save(mode,rows,summary,kind=kind,note="Historical synthetic replay, not independent physical early-stop or runtime savings.")
else:raise ValueError(mode)
