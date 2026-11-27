"""R4B5A.1 same-h reference domain recovery."""
import hashlib,json,sys,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"r3b"))
from solver_lib import initial,geometry
sys.path.insert(0,str(HERE.parent/"r4b3"))
from boundary_solver import scalar_initial,advance3,face
P=json.loads((HERE/"protocol.json").read_text());F=None
START=time.monotonic()
B=P["configuration"];G=P["thresholds"]
OUT=Path("r4b5a1-output");OUT.mkdir(exist_ok=True)
def write(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
def emit(tag,obj): print("R4B5A1_"+tag,json.dumps(obj,allow_nan=False),flush=True)
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
    if cfg.get("family")=="novel":q=np.zeros_like(q)
    a,al,m,M=geometry(p,q,r,h,flat)
    require(np.isfinite(M),"INIT_FINITE")
    def energy():
        return float(2*np.pi*h*np.sum(r*r*(p*p+q*q))) if flat else float(M)
    E0=energy();require(E0>0,"INITIAL_ENERGY")
    t=0.;T=0.;peak=0.;drift=0.;maxR2=0.;maxR3=0.;steps=0
    z=r[:3]**2;weights=np.array([np.prod([-z[j]/(z[k]-z[j]) for j in range(3) if j!=k]) for k in range(3)])
    max_speed=float(np.max(al/a))
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
        dt=min(cfg.get("CFL",.3)*h,end-t)
        pn,qn,sn=advance3(p,q,s,r,h,dt,flat,candidate)
        if not all(np.isfinite(v).all() for v in (pn,qn,sn)):
            status="NUMERICAL_FAILURE";break
        an,aln,mn,Mn=geometry(pn,qn,r,h,flat)
        if not (np.isfinite(Mn) and np.isfinite(an).all() and np.isfinite(aln).all() and np.isfinite(mn).all()):
            status="NUMERICAL_FAILURE";break
        max_speed=max(max_speed,float(np.max(aln/an)))
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
    row={"A":A,"family":cfg.get("family","original"),"CFL":cfg.get("CFL",.3),"n":n,"R":R,"h":h,"candidate":candidate,"flat":flat,"status":status,"t":float(t),"proper_time":float(T),"steps":steps,"peak_compactness":peak,"final_compactness":float(x[-1,6]),"inner_mass_fraction":float(x[-1,8]),"initial_mass_or_flat_energy":E0,"mass_drift":drift,"final_mass_loss_fraction":(E0-energy())/E0,"direct_outward_fraction":float(-integ[0]/E0),"old_extrapolated_outward_fraction":float(-integ[1]/E0),"direct_balance_residual_max":float(maxres[0]),"old_balance_residual_max":float(maxres[1]),"analytic_outward_fraction":float(-integ[2]/E0) if flat else None,"analytic_energy_loss_fraction":analytic_loss,"reference_interior_outward_fraction":-refinteg/E0 if rr is not None else None,"reference_interior_balance_residual_max":maxrefres if rr is not None else None,"curvature_peak":maxR2,"curvature_peak_alt":maxR3,"scale":float(1/np.sqrt(max(maxR2,1e-300))/h),"scale_alt":float(1/np.sqrt(max(maxR3,1e-300))/h),"max_characteristic_speed":max_speed,"elapsed_seconds":time.monotonic()-tic}
    return row,x
rows={};traces={}
def execute(key,cfg,candidate,flat=False,probe=False):
    r,x=run(cfg,candidate,flat,probe);rows[key]=r;traces[key]=x
    write("cases.json",rows);np.savez_compressed(OUT/"traces.npz",**traces)
    emit("CASE",{"id":key,**r});return r,x




def finish(status,gates,**extra):
    result={"id":P["id"],"status":status,"gates":gates,"scientific_hold":True,"dss_tested":False,"amr_implemented":False,"A_0_1152_run":False,"fine_run":False,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"claim_ceiling":P["claim_ceiling"],**extra}
    write("result.json",result);emit("RESULT",result)
    sys.exit(0)
for case in B["cases"]:
    cfg={**B,**case}
    if case["R"]>B["interior_flux_radius"]:cfg["reference_radius"]=B["interior_flux_radius"]
    execute(case["id"],cfg,case["candidate"],False,True)
def compare(k1,k2,proper=True):
    a,b=traces[k1],traces[k2];col=1 if proper else 0
    end=min(a[-1,col],b[-1,col]);t=np.linspace(0,end,32769)
    aa=np.stack([np.interp(t,a[:,col],a[:,i]) for i in range(a.shape[1])],axis=1)
    bb=np.stack([np.interp(t,b[:,col],b[:,i]) for i in range(b.shape[1])],axis=1)
    rp=B["probe_radius"]
    va=aa[:,9:12].copy();vb=bb[:,9:12].copy()
    va[:,2]/=rp;vb[:,2]/=rp
    # Fixed incoming comparison window from the small-domain t=12 slice.
    start=float(np.interp(12,a[:,0],a[:,col]))
    mask=t>=start
    require(mask.any(),"INCOMING_WINDOW_EMPTY")
    ia=va[:,0]+va[:,1]+va[:,2];ib=vb[:,0]+vb[:,1]+vb[:,2]
    ob=vb[:,1]-vb[:,0]-vb[:,2]
    inc=float(np.linalg.norm((ia-ib)[mask])/max(float(np.linalg.norm(ob[mask])),1e-30))
    obs={}
    for name,i in (("signed_derivative",2),("curvature",4),("curvature_alt",5)):
        obs[name]={"L2":norm(aa[:,i],bb[:,i]),"Linf":linf(aa[:,i],bb[:,i])}
    peaks={}
    for name,i in (("C",6),("Ricci",4),("Ricci_alt",5)):
        pa=float(max(np.max(a[a[:,col]<=end,i]),np.interp(end,a[:,col],a[:,i])))
        pb=float(max(np.max(b[b[:,col]<=end,i]),np.interp(end,b[:,col],b[:,i])))
        peaks[name]={"first":pa,"second":pb,"absolute":abs(pa-pb),"relative":abs(pa-pb)/max(abs(pb),1e-30)}
    flux_a=float(-aa[-1,12]/rows[k1]["initial_mass_or_flat_energy"])
    flux_b=float(-bb[-1,17]/rows[k2]["initial_mass_or_flat_energy"])
    return {"time_coordinate":"central_proper_time" if proper else "coordinate_time","common_end":float(end),"coverage":float(end/max(a[-1,col],b[-1,col])),"incoming_window_start":start,"field_l2":norm(va,vb),"incoming_l2":inc,"central":obs,"peaks":peaks,"first_face_outward":flux_a,"second_interior_outward":flux_b,"flux_abs_difference":abs(flux_a-flux_b)}
def valid(r,reference=False):
    return r["status"]=="DISPERSAL_PROXY" and r["t"]>=22-1e-8 and min(r["scale"],r["scale_alt"])>=8 and r["direct_balance_residual_max"]<.01 and (not reference or r["reference_interior_balance_residual_max"]<.01)
# Historical replay of the failed control, not a reclassification.
old={"small":{"peak_compactness":.12198178025293767,"curvature_peak":2.7323625729617635,"direct_balance_residual_max":.00000927832197915772},"r25_legacy":{"peak_compactness":.12198178022484639,"curvature_peak":2.732362573371706,"direct_balance_residual_max":.09185855292585131,"reference_interior_balance_residual_max":.000006681594580876634}}
replay={}
for key,vals in old.items():
    errors={k:abs(rows[key][k]-v)/max(abs(v),1e-30) for k,v in vals.items()}
    replay[key]={"errors":errors,"pass":max(errors.values())<=1e-8}
gates={"historical_replay":all(v["pass"] for v in replay.values())}
emit("REPLAY",replay)
causal={}
for k,r in rows.items():
    margin=r["R"]-B["interior_flux_radius"]-B["end"]
    causal[k]={"same_h":abs(r["h"]-B["h"])<=1e-15,"max_characteristic_speed":r["max_characteristic_speed"],"coordinate_distance_minus_window":margin,"causal_margin_positive":margin>0}
gates["same_h_and_far_causal_margin"]=all(v["same_h"] and v["max_characteristic_speed"]<=1+1e-12 for v in causal.values()) and all(causal[k]["causal_margin_positive"] for k in ("r50","r62_5"))
gates["far_reference_integrity"]=all(valid(rows[k],True) for k in ("r50","r62_5"))
emit("CAUSAL",causal)
far=compare("r50","r62_5")
far_checks={"coverage":far["coverage"]>=.95,"field":far["field_l2"]<=.05,"central":all(max(v.values())<=.01 for v in far["central"].values()),"C":far["peaks"]["C"]["absolute"]<=.0005 and far["peaks"]["C"]["relative"]<=.01,"Ricci":all(far["peaks"][k]["relative"]<=.02 for k in ("Ricci","Ricci_alt"))}
gates["far_reference_invariance"]=all(far_checks.values())
emit("FAR",{"proper":far,"coordinate_diagnostic":compare("r50","r62_5",False),"checks":far_checks})
comparisons={}
for k in ("r25_legacy","r25_candidate","r50","r62_5"):
    d=compare("small",k)
    checks={"coverage":d["coverage"]>=.95,"small_integrity":valid(rows["small"]),"reference_integrity":valid(rows[k],True),"outgoing":min(d["first_face_outward"],d["second_interior_outward"])>=.25,"flux_agreement":d["flux_abs_difference"]<=.05,"field":d["field_l2"]<=.05,"incoming":d["incoming_l2"]<=.05}
    comparisons[k]={"proper":d,"coordinate_diagnostic":compare("small",k,False),"checks":checks,"pass":all(checks.values())}
    emit("COMPARISON",{"id":k,**comparisons[k]})
gates["small_vs_valid_far_references"]=all(comparisons[k]["pass"] for k in ("r50","r62_5"))
status="REFERENCE_DOMAIN_RECOVERY_PASS__SCIENTIFIC_HOLD" if all(gates.values()) else "REFERENCE_DOMAIN_RECOVERY_HOLD"
finish(status,gates,replay=replay,causal=causal,far=far,far_checks=far_checks,comparisons=comparisons,blockers=[k for k,v in gates.items() if not v])
