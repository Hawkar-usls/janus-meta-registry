"""Frozen R4B3 diagnostic; no DSS, no critical fit."""
import hashlib,json,sys,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"r3b"))
from solver_lib import initial,geometry
from boundary_solver import scalar_initial,advance3,face
P=json.loads((HERE/"protocol.json").read_text());D=P["design"];C=D["cases"];G=D["gates"]
OUT=Path("r4b3-output");OUT.mkdir(exist_ok=True)
def write(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
def emit(tag,obj): print("R4B3_"+tag,json.dumps(obj,allow_nan=False),flush=True)
def require(ok,msg):
    if not ok: raise RuntimeError(msg)
def norm(a,b):
    return float(np.linalg.norm(a-b)/max(float(np.linalg.norm(b)),1e-30))
def linf(a,b):
    return float(np.max(np.abs(a-b))/max(float(np.max(np.abs(b))),1e-30))
def run(cfg,candidate,flat=False,probe=False):
    tic=time.monotonic()
    A,r0,w,R,n,end=[cfg[k] for k in ("A","r0","w","R","n","end")]
    h=R/n;r=(np.arange(n)+.5)*h
    p,q=initial(r,A,r0,w);s=scalar_initial(r,A,r0,w)
    a,al,m,M=geometry(p,q,r,h,flat)
    require(np.isfinite(M),"INIT_FINITE")
    def energy():
        return float(2*np.pi*h*np.sum(r*r*(p*p+q*q))) if flat else float(M)
    E0=energy();require(E0>0,"INITIAL_ENERGY")
    t=0.;T=0.;peak=0.;drift=0.;maxR2=0.;maxR3=0.;steps=0
    z=r[:3]**2;weights=np.array([np.prod([-z[j]/(z[k]-z[j]) for j in range(3) if j!=k]) for k in range(3)])
    data=[];maxres=np.zeros(2);integ=np.zeros(3);refinteg=0.;maxrefres=0.;refm0=None
    # For the larger domain, independently sample mass and signed flux at
    # the matching interior areal radius. Never infer flux from dm/dt.
    rr=cfg.get("reference_radius")
    if rr is not None:
        require(not flat and rr<R,"REFERENCE_RADIUS")
        hi=int(np.searchsorted(r,rr));lo=hi-1;lam=(rr-r[lo])/(r[hi]-r[lo])
        def reference():
            f=4*np.pi*r[lo:hi+1]**2*al[lo:hi+1]*p[lo:hi+1]*q[lo:hi+1]/a[lo:hi+1]**3
            return float((1-lam)*m[lo]+lam*m[hi]),float((1-lam)*f[0]+lam*f[1])
        refm0,refprev=reference()
    boundary_r=np.array([R])
    probe_r=np.array([cfg.get("probe_radius",10.)])
    def flux():
        U,W=face(p,q,s,r,h,a,al,M,flat,candidate)
        # v(R)=a(R)^-2 under the original lapse normalization.
        f=4*np.pi*R*R*U*W
        pb=1.5*p[-1]-.5*p[-2];qb=1.5*q[-1]-.5*q[-2]
        old=4*np.pi*R*R*(1. if flat else (1-2*M/R)**2)*pb*qb
        exact=0.
        if flat:
            ep,eq=initial(boundary_r,A,r0,w,t)
            exact=float(4*np.pi*R*R*ep[0]*eq[0])
        return np.array([f,old,exact])
    fprev=flux()
    def collect():
        nonlocal peak,maxR2,maxR3,drift
        v=q[:3]/a[:3];v2=float((9*v[0]-v[1])/8);v3=float(weights@v)
        R2=8*np.pi*v2*v2;R3=8*np.pi*v3*v3;maxR2=max(maxR2,R2);maxR3=max(maxR3,R3)
        c=float(np.max(2*m/r));peak=max(peak,c);E=energy()
        drift=max(drift,abs(E-E0)/E0)
        inner=float(m[np.searchsorted(r,3.)]/E0) if not flat else float(2*np.pi*h*np.sum((r*r*(p*p+q*q))[r<3])/E0)
        pp=qq=ss=0.
        if probe:
            pp=float(np.interp(probe_r[0],r,p));qq=float(np.interp(probe_r[0],r,q));ss=float(np.interp(probe_r[0],r,s))
        data.append([t,T,v2,v3,R2,R3,c,E,inner,pp,qq,ss,*integ.tolist(),*maxres.tolist(),refinteg,maxrefres])
    collect();status="UNRESOLVED"
    while t<end-1e-12:
        dt=min(.3*h,end-t)
        pn,qn,sn=advance3(p,q,s,r,h,dt,flat,candidate)
        if not all(np.isfinite(v).all() for v in (pn,qn,sn)):
            status="NUMERICAL_FAILURE";break
        an,aln,mn,Mn=geometry(pn,qn,r,h,flat)
        if not (np.isfinite(Mn) and np.isfinite(an).all() and np.isfinite(aln).all() and np.isfinite(mn).all()):
            status="NUMERICAL_FAILURE";break
        T+=dt*.5*(al[0]+aln[0]);t+=dt;steps+=1
        p,q,s,a,al,m,M=pn,qn,sn,an,aln,mn,Mn
        fnew=flux();integ+=.5*dt*(fprev+fnew);fprev=fnew
        E=energy();maxres=np.maximum(maxres,np.abs((E-E0-integ[:2])/E0))
        if rr is not None:
            rm,rf=reference();refinteg+=.5*dt*(refprev+rf);refprev=rf
            maxrefres=max(maxrefres,abs(rm-refm0-refinteg)/E0)
        collect()
        if peak>=.85:status="NEAR_TRAPPING_PROXY";break
    x=np.asarray(data);require(np.isfinite(x).all() and np.all(np.diff(x[:,1])>0),"TRACE_FINITE")
    if status=="UNRESOLVED" and t>=end-1e-8 and x[-1,8]<.05 and x[-1,6]<.2:status="DISPERSAL_PROXY"
    # Flat analytic energy evaluated independently on the same radial grid.
    analytic_loss=None
    if flat:
        ep,eq=initial(r,A,r0,w,t)
        exact_E=float(2*np.pi*h*np.sum(r*r*(ep*ep+eq*eq)))
        analytic_loss=(E0-exact_E)/E0
    row={"A":A,"n":n,"R":R,"h":h,"candidate":candidate,"flat":flat,"status":status,"t":float(t),"proper_time":float(T),"steps":steps,"peak_compactness":peak,"final_compactness":float(x[-1,6]),"inner_mass_fraction":float(x[-1,8]),"initial_mass_or_flat_energy":E0,"mass_drift":drift,"final_mass_loss_fraction":(E0-energy())/E0,"direct_outward_fraction":float(-integ[0]/E0),"old_extrapolated_outward_fraction":float(-integ[1]/E0),"direct_balance_residual_max":float(maxres[0]),"old_balance_residual_max":float(maxres[1]),"analytic_outward_fraction":float(-integ[2]/E0) if flat else None,"analytic_energy_loss_fraction":analytic_loss,"reference_interior_outward_fraction":-refinteg/E0 if rr is not None else None,"reference_interior_balance_residual_max":maxrefres if rr is not None else None,"curvature_peak":maxR2,"curvature_peak_alt":maxR3,"scale":float(1/np.sqrt(max(maxR2,1e-300))/h),"scale_alt":float(1/np.sqrt(max(maxR3,1e-300))/h),"elapsed_seconds":time.monotonic()-tic}
    return row,x
rows={};traces={}
def execute(key,cfg,candidate,flat=False,probe=False):
    r,x=run(cfg,candidate,flat,probe);rows[key]=r;traces[key]=x
    write("cases.json",rows);np.savez_compressed(OUT/"traces.npz",**traces)
    emit("CASE",{"id":key,**r});return r,x
for arm,flag in (("legacy",False),("candidate",True)):
    execute("flat_"+arm,C["flat"],flag,True,True)
    execute("curved_"+arm,C["curved_small"],flag,False,True)
execute("curved_reference",C["curved_reference"],False,False,True)
def probe_metrics(key,refkey=None):
    x=traces[key];t=x[:,0];r0=C["flat"]["r0"];w=C["flat"]["w"];A=C["flat"]["A"];rp=C["flat"]["probe_radius"]
    mask=(t>=12)&(t<=22+1e-10)
    if not mask.any():return {"field_relative_l2":None,"incoming_relative_l2":None}
    p,q,s=x[:,9],x[:,10],x[:,11]
    if refkey is None:
        # analytic flat solution at the fixed interior probe, vectorized in t
        xp=(rp+t-r0)/w;xm=(-rp+t-r0)/w
        ep=np.exp(-xp*xp);em=np.exp(-xm*xm);dp=-2*xp*ep/w;dm=-2*xm*em/w
        pr=A*((dp+dm)/rp-(ep-em)/(rp*rp));qr=A*(dp-dm)/rp;sr=A*(ep-em)/rp
    else:
        z=traces[refkey];pr,qr,sr=[np.interp(t,z[:,0],z[:,i]) for i in (9,10,11)]
    field=norm(np.stack([p,q,s/rp],axis=1),np.stack([pr,qr,sr/rp],axis=1))
    inc=p+q+s/rp;inref=pr+qr+sr/rp;outref=qr-pr-sr/rp
    incoming=float(np.linalg.norm((inc-inref)[mask])/max(float(np.linalg.norm(outref[mask])),1e-30))
    return {"field_relative_l2":field,"incoming_relative_l2":incoming,"reflection_window":[12,22]}
metrics={}
for arm in ("legacy","candidate"):
    metrics["flat_"+arm]=probe_metrics("flat_"+arm)
    metrics["curved_"+arm]=probe_metrics("curved_"+arm,"curved_reference")
flat=rows["flat_candidate"];curved=rows["curved_candidate"];ref=rows["curved_reference"]
flat_analytic_ok=abs(flat["analytic_outward_fraction"]-flat["analytic_energy_loss_fraction"])<.01
boundary_gates={"flat_analytic_reference":flat_analytic_ok,"flat_nonzero_outgoing":flat["analytic_outward_fraction"]>=.25 and flat["direct_outward_fraction"]>=.25,"flat_face_balance":flat["direct_balance_residual_max"]<.01,"flat_face_analytic_agreement":abs(flat["direct_outward_fraction"]-flat["analytic_outward_fraction"])<=.05,"flat_field_agreement":metrics["flat_candidate"]["field_relative_l2"] is not None and metrics["flat_candidate"]["field_relative_l2"]<=.05,"flat_reflection":metrics["flat_candidate"]["incoming_relative_l2"] is not None and metrics["flat_candidate"]["incoming_relative_l2"]<=.05,"curved_nonzero_outgoing":curved["direct_outward_fraction"]>=.25 and ref["reference_interior_outward_fraction"]>=.25,"curved_face_balance":curved["direct_balance_residual_max"]<.01,"curved_face_reference_agreement":abs(curved["direct_outward_fraction"]-ref["reference_interior_outward_fraction"])<=.05,"curved_reference_balance":ref["mass_drift"]<.01 and ref["direct_balance_residual_max"]<.01 and ref["reference_interior_balance_residual_max"]<.01,"curved_reflection":metrics["curved_candidate"]["incoming_relative_l2"] is not None and metrics["curved_candidate"]["incoming_relative_l2"]<=.05,"curved_field_agreement":metrics["curved_candidate"]["field_relative_l2"] is not None and metrics["curved_candidate"]["field_relative_l2"]<=.05,"all_boundary_runs_complete":all(rows[k]["t"]>=22-1e-8 and rows[k]["status"]=="DISPERSAL_PROXY" for k in rows)}
boundary={"pass":all(boundary_gates.values()),"gates":boundary_gates,"probe_metrics":metrics,"direct_vs_legacy_reconstruction":{k:{"direct":r["direct_outward_fraction"],"old":r["old_extrapolated_outward_fraction"],"direct_residual":r["direct_balance_residual_max"],"old_residual":r["old_balance_residual_max"]} for k,r in rows.items()}}
emit("BOUNDARY",boundary)
for n in C["critical"]["grids"]:
    for arm,flag in (("legacy",False),("candidate",True)):
        execute("critical_"+str(n)+"_"+arm,{**C["critical"],"n":n},flag)
execute("critical_extended",C["domain_extension"],True)
def compare(k1,k2,threshold):
    x,y=traces[k1],traces[k2];T=min(x[-1,1],y[-1,1]);require(T>0,"COMMON_TIME")
    tau=np.linspace(0,T,32769)
    stats={}
    for name,col in (("signed_derivative",2),("curvature",4),("curvature_alt",5)):
        u=np.interp(tau,x[:,1],x[:,col]);v=np.interp(tau,y[:,1],y[:,col])
        stats[name]={"relative_l2":norm(u,v),"relative_linf":linf(u,v)}
    return {"pair":[k1,k2],"common_proper_time":float(T),"observables":stats,"threshold":threshold,"pass":all(max(d.values())<=threshold for d in stats.values())}
comparisons={
 "candidate_pair":compare("critical_12288_candidate","critical_24576_candidate",.1),
 "legacy_pair":compare("critical_12288_legacy","critical_24576_legacy",.1),
 "legacy_vs_candidate_12288":compare("critical_12288_candidate","critical_12288_legacy",.01),
 "legacy_vs_candidate_24576":compare("critical_24576_candidate","critical_24576_legacy",.01),
 "domain_extension_same_h":compare("critical_12288_candidate","critical_extended",.01)}
refvals={12288:(.503472341319628,.00017573496230898145,10.366140822556378),24576:(.5031986242510851,.00003987763055451122,21.41605685847866)}
replay={}
for n,vals in refvals.items():
    row=rows["critical_"+str(n)+"_legacy"]
    diffs={k:abs(row[k]-v)/max(abs(v),1e-30) for k,v in zip(("peak_compactness","mass_drift","scale"),vals)}
    replay[str(n)]={"relative_errors":diffs,"pass":row["status"]=="DISPERSAL_PROXY" and max(diffs.values())<=1e-8}
central=[r for k,r in rows.items() if k.startswith("critical_")]
central_gates={"legacy_replay":all(r["pass"] for r in replay.values()),"stable_class":all(r["status"]=="DISPERSAL_PROXY" and r["t"]>=16-1e-8 for r in central),"local_resolution":all(min(r["scale"],r["scale_alt"])>=8 for r in central),"closed_mass_balance":all(r["mass_drift"]<.01 and r["direct_balance_residual_max"]<.01 for r in central),"central_comparisons":all(r["pass"] for r in comparisons.values())}
central_report={"pass":all(central_gates.values()),"gates":central_gates,"comparisons":comparisons,"replay":replay}
emit("CENTRAL",central_report)
gates={"boundary_recovery":boundary["pass"],"central_nonregression":central_report["pass"]}
result={"id":P["id"],"status":"BOUNDARY_RECOVERY_PASS__SCIENTIFIC_HOLD" if all(gates.values()) else "OPEN_BOUNDARY_FLUX_HOLD" if not boundary["pass"] else "CENTRAL_REGRESSION_HOLD","gates":gates,"boundary":boundary,"central":central_report,"historical_R4B2_status":"OPEN_BOUNDARY_FLUX_HOLD","scientific_hold":True,"n49152_run":False,"dss_tested":False,"amr_implemented":False,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"claim_ceiling":"Only a weak-pulse boundary benchmark and fixed-amplitude pair/domain regression. Sommerfeld approximate in curved space, direct face flux not exact discrete mass conservation; no asymptotic or DSS claim."}
write("result.json",result);emit("RESULT",result)
