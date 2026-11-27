"""R4B5 fixed-amplitude convergence and finite proxy bracket exam."""
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
B=P["boundary"]["nontrivial_controls"];G=P["convergence"]
OUT=Path("r4b5-bracket-output");OUT.mkdir(exist_ok=True)
def write(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
def emit(tag,obj): print("R4B5_BRACKET_"+tag,json.dumps(obj,allow_nan=False),flush=True)
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
    row={"A":A,"family":cfg.get("family","original"),"CFL":cfg.get("CFL",.3),"n":n,"R":R,"h":h,"candidate":candidate,"flat":flat,"status":status,"t":float(t),"proper_time":float(T),"steps":steps,"peak_compactness":peak,"final_compactness":float(x[-1,6]),"inner_mass_fraction":float(x[-1,8]),"initial_mass_or_flat_energy":E0,"mass_drift":drift,"final_mass_loss_fraction":(E0-energy())/E0,"direct_outward_fraction":float(-integ[0]/E0),"old_extrapolated_outward_fraction":float(-integ[1]/E0),"direct_balance_residual_max":float(maxres[0]),"old_balance_residual_max":float(maxres[1]),"analytic_outward_fraction":float(-integ[2]/E0) if flat else None,"analytic_energy_loss_fraction":analytic_loss,"reference_interior_outward_fraction":-refinteg/E0 if rr is not None else None,"reference_interior_balance_residual_max":maxrefres if rr is not None else None,"curvature_peak":maxR2,"curvature_peak_alt":maxR3,"scale":float(1/np.sqrt(max(maxR2,1e-300))/h),"scale_alt":float(1/np.sqrt(max(maxR3,1e-300))/h),"elapsed_seconds":time.monotonic()-tic}
    return row,x
rows={};traces={}
def execute(key,cfg,candidate,flat=False,probe=False):
    r,x=run(cfg,candidate,flat,probe);rows[key]=r;traces[key]=x
    write("cases.json",rows);np.savez_compressed(OUT/"traces.npz",**traces)
    emit("CASE",{"id":key,**r});return r,x


def finish(status,gates,**extra):
    result={"id":P["id"],"status":status,"gates":gates,"scientific_hold":True,"dss_tested":False,"amr_implemented":False,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"claim_ceiling":P["claim_ceiling"],**extra}
    write("result.json",result);emit("RESULT",result)
    sys.exit(0)
def boundary_compare(A,flat=False):
    name=("flat_" if flat else "curved_")+str(A)
    cfg={"A":A,"r0":5,"w":1,"R":B["small_R"],"n":B["small_n"],"end":B["end"],"probe_radius":B["probe_radius"]}
    small,x=execute(name,cfg,True,flat,True)
    t=x[:,0];rp=B["probe_radius"];mask=(t>=12)&(t<=22+1e-10)
    p,q,s=x[:,9],x[:,10],x[:,11]
    if flat:
        xp=rp+t-5;xm=-rp+t-5
        ep=np.exp(-xp*xp);em=np.exp(-xm*xm);dp=-2*xp*ep;dm=-2*xm*em
        pr=A*((dp+dm)/rp-(ep-em)/(rp*rp));qr=A*(dp-dm)/rp;sr=A*(ep-em)/rp
        ref_flux=small["analytic_outward_fraction"]
        reference_ok=abs(ref_flux-small["analytic_energy_loss_fraction"])<.01
    else:
        ref,y=execute(name+"_reference",{**cfg,"R":B["reference_R"],"n":B["reference_n"],"reference_radius":B["small_R"]},False,False,True)
        pr,qr,sr=[np.interp(t,y[:,0],y[:,i]) for i in (9,10,11)]
        ref_flux=ref["reference_interior_outward_fraction"]
        reference_ok=ref["status"]=="DISPERSAL_PROXY" and ref["t"]>=22-1e-8 and ref["mass_drift"]<.01 and ref["direct_balance_residual_max"]<.01 and ref["reference_interior_balance_residual_max"]<.01
    field=norm(np.stack([p,q,s/rp],axis=1),np.stack([pr,qr,sr/rp],axis=1))
    incoming=float(np.linalg.norm((p+q+s/rp-pr-qr-sr/rp)[mask])/max(float(np.linalg.norm((qr-pr-sr/rp)[mask])),1e-30))
    checks={"reference":bool(reference_ok),"complete":small["status"]=="DISPERSAL_PROXY" and small["t"]>=22-1e-8,"nonzero_outgoing":small["direct_outward_fraction"]>=.25 and ref_flux>=.25,"flux_balance":small["direct_balance_residual_max"]<.01,"flux_agreement":abs(small["direct_outward_fraction"]-ref_flux)<=.05,"field":field<=.05,"incoming":incoming<=.05}
    result={"name":name,"pass":all(checks.values()),"checks":checks,"direct_outward_fraction":small["direct_outward_fraction"],"reference_outward_fraction":ref_flux,"field_relative_l2":field,"incoming_relative_l2":incoming,"mass_balance_residual":small["direct_balance_residual_max"]}
    emit("BOUNDARY",result);return result
OBS=(("signed_derivative",2),("curvature",4),("curvature_alt",5))
PEAKS=("peak_compactness","curvature_peak","curvature_peak_alt")
def pair(k1,k2,tau=None):
    x,y=traces[k1],traces[k2]
    if tau is None:tau=np.linspace(0,min(x[-1,1],y[-1,1]),32769)
    stats={}
    for name,col in OBS:
        a=np.interp(tau,x[:,1],x[:,col]);b=np.interp(tau,y[:,1],y[:,col]);d=a-b
        stats[name]={"relative_l2":norm(a,b),"relative_linf":linf(a,b),"abs_l2":float(np.linalg.norm(d)),"abs_linf":float(np.max(np.abs(d)))}
    return stats
def pair_ok(stats,tol):return all(max(d["relative_l2"],d["relative_linf"])<=tol for d in stats.values())
def complete(r):
    return r["status"]=="DISPERSAL_PROXY" and r["t"]>=16-1e-8 and min(r["scale"],r["scale_alt"])>=8 and r["mass_drift"]<.01 and r["direct_balance_residual_max"]<.01

def cost(cfg):
    return 160*(cfg["n"]/24576)**2*(cfg["end"]/16)*(.3/cfg.get("CFL",.3))
def admitted(cfg):
    elapsed=time.monotonic()-START;project=cost(cfg)
    return elapsed+project<=P["budget"]["execution_budget_seconds"]
def config(family,A,n,CFL=.3):
    r0,w=(6,1.4) if family=="wide" else (5,1)
    return {"family":family,"A":A,"r0":r0,"w":w,"R":30,"n":n,"end":16,"CFL":CFL,"reference_radius":12}
def numeric(r):
    cls=r["status"]
    return cls in ("DISPERSAL_PROXY","NEAR_TRAPPING_PROXY") and (cls!="DISPERSAL_PROXY" or r["t"]>=16-1e-8) and min(r["scale"],r["scale_alt"])>=8 and r["mass_drift"]<.01 and r["direct_balance_residual_max"]<.01 and r["reference_interior_balance_residual_max"] is not None and r["reference_interior_balance_residual_max"]<.01
def pair_report(k1,k2,tau=None):
    a,b=rows[k1],rows[k2];stats=pair(k1,k2,tau)
    dc=abs(a["peak_compactness"]-b["peak_compactness"])
    rc=dc/max(abs(b["peak_compactness"]),1e-30)
    ricci={name:abs(a[name]-b[name])/max(abs(b[name]),1e-30) for name in PEAKS[1:]}
    checks={"numeric":numeric(a) and numeric(b),"class":a["status"]==b["status"],"C_absolute":dc<=G["peak_C_absolute_pair_max"],"C_relative":rc<=G["peak_C_relative_pair_max"],"Ricci":all(v<=G["peak_R_relative_pair_max"] for v in ricci.values()),"trace":pair_ok(stats,.1)}
    return {"pass":all(checks.values()),"checks":checks,"C_absolute":dc,"C_relative":rc,"Ricci_relative":ricci,"trace":stats,"end_t":[a["t"],b["t"]],"proper_time":[a["proper_time"],b["proper_time"]],"outer_flux_nontrivial":[a["direct_outward_fraction"]>=.25,b["direct_outward_fraction"]>=.25]}
boundary=[boundary_compare(A) for A in B["A"]]
gates={"boundary":all(x["pass"] for x in boundary)}
if not gates["boundary"]:finish("OPEN_BOUNDARY_FLUX_HOLD",gates,boundary=boundary)
base=config("original",G["A"],12288)
for key,n,cfl in (("ind_coarse",12288,.3),("ind_medium",24576,.3),("ind_temporal",24576,.15)):
    cfg={**base,"n":n,"CFL":cfl}
    if not admitted(cfg):finish("COMPUTE_BUDGET_HOLD",gates,boundary=boundary,unstarted=key)
    execute(key,cfg,True)
tau=np.linspace(0,min(traces[k][-1,1] for k in ("ind_coarse","ind_medium","ind_temporal")),32769)
sp=pair("ind_coarse","ind_medium",tau);tm=pair("ind_medium","ind_temporal",tau)
temporal={}
for name,_ in OBS:
    for n in ("l2","linf"):
        d=tm[name]["abs_"+n];v=sp[name]["abs_"+n];rel=tm[name]["relative_"+n]
        temporal[name+"_"+n]={"relative":rel,"temporal_over_spatial":d/v if v>0 else None,"pass":rel<.01 and d<=.25*v}
for name in PEAKS:
    a,b,c=[rows[k][name] for k in ("ind_coarse","ind_medium","ind_temporal")]
    d=abs(b-c);v=abs(a-b);rel=d/max(abs(c),1e-30)
    temporal[name]={"relative":rel,"temporal_over_spatial":d/v if v>0 else None,"pass":rel<.01 and d<=.25*v}
gates["temporal"]=all(numeric(rows[k]) and rows[k]["status"]=="DISPERSAL_PROXY" for k in ("ind_coarse","ind_medium","ind_temporal")) and all(x["pass"] for x in temporal.values())
emit("TEMPORAL",{"pass":gates["temporal"],"metrics":temporal})
if not gates["temporal"]:finish("INDEPENDENT_TEMPORAL_HOLD",gates,boundary=boundary,temporal=temporal)
cfg={**base,"n":49152}
if not admitted(cfg):finish("COMPUTE_BUDGET_HOLD",gates,boundary=boundary,temporal=temporal,unstarted="ind_fine")
execute("ind_fine",cfg,True)
tau=np.linspace(0,min(traces[k][-1,1] for k in ("ind_coarse","ind_medium","ind_fine")),32769)
p12=pair_report("ind_coarse","ind_medium",tau);p23=pair_report("ind_medium","ind_fine",tau)
def order(d1,d2,monotone=True):
    p=float(np.log2(d1/d2)) if d1>0 and d2>0 else None
    return {"d12":d1,"d23":d2,"p":p,"decreasing":d2<d1,"monotone":bool(monotone),"second_order_consistent":p is not None and 1.5<=p<=2.5 and bool(monotone)}
orders={}
for name,_ in OBS:
    for n in ("l2","linf"):
        orders[name+"_"+n]=order(p12["trace"][name]["abs_"+n],p23["trace"][name]["abs_"+n])
for name in PEAKS:
    a,b,c=[rows[k][name] for k in ("ind_coarse","ind_medium","ind_fine")]
    orders[name]=order(abs(a-b),abs(b-c),(a-b)*(b-c)>0)
ind={"pair_12":p12,"pair_23":p23,"orders":orders,"common_proper_time":float(tau[-1]),"pass":p12["pass"] and p23["pass"] and all(x["decreasing"] and x["monotone"] and x["second_order_consistent"] for x in orders.values())}
gates["independent_triplet"]=ind["pass"];emit("INDEPENDENT_CONVERGENCE",ind)
# Diagnostic scan proceeds even if independent order fails, but final gate stays closed.
scan={};missing=[];confirmed={};brackets={}
for family in ("original","wide","novel"):
    scan[family]=[]
    for A in P["scan"][family]:
        key=family+"_"+str(A)
        if family=="original" and A==G["A"]:
            rows[key]=rows["ind_coarse"];traces[key]=traces["ind_coarse"]
        else:
            cfg=config(family,A,12288)
            if not admitted(cfg):missing.append(key);continue
            execute(key,cfg,True)
        r=rows[key];scan[family].append({"A":A,"key":key,"class":r["status"],"numeric_pass":numeric(r)})
    emit("SCAN",{"family":family,"cases":scan[family]})
# Confirm only adjacent opposite diagnostic classes, never replace unresolved points.
for family,items in scan.items():
    brackets[family]=[]
    for lo,hi in zip(items,items[1:]):
        prescribed=P["scan"][family]
        if prescribed.index(hi["A"])-prescribed.index(lo["A"])!=1:continue
        if {lo["class"],hi["class"]}!={"DISPERSAL_PROXY","NEAR_TRAPPING_PROXY"}:continue
        if not (lo["numeric_pass"] and hi["numeric_pass"]):continue
        for item in (lo,hi):
            key=item["key"];new=key+"_confirm"
            if new in confirmed:continue
            cfg=config(family,item["A"],24576)
            if not admitted(cfg):missing.append(new);continue
            execute(new,cfg,True)
            confirmed[new]=pair_report(key,new);emit("CONFIRM",{"id":new,**confirmed[new]})
        a=confirmed.get(lo["key"]+"_confirm");b=confirmed.get(hi["key"]+"_confirm")
        if a and b and a["pass"] and b["pass"]:
            brackets[family].append({"lower_A":lo["A"],"upper_A":hi["A"],"lower_class":lo["class"],"upper_class":hi["class"],"width":hi["A"]-lo["A"],"ordered":lo["class"]=="DISPERSAL_PROXY"})
nonmonotone={}
for family,items in scan.items():
    classes=[x["class"] for x in items if x["numeric_pass"]]
    nonmonotone[family]=any(a=="NEAR_TRAPPING_PROXY" and b=="DISPERSAL_PROXY" for a,b in zip(classes,classes[1:]))
gates["scan_complete"]=not missing
gates["proxy_bracket"]=all(any(x["ordered"] for x in brackets[f]) and not nonmonotone[f] for f in brackets)
status="MULTIFAMILY_PROXY_BRACKET_PASS__SCIENTIFIC_HOLD" if all(gates.values()) else "COMPUTE_BUDGET_HOLD" if missing else "CRITICAL_BRACKET_HOLD"
finish(status,gates,boundary=boundary,temporal=temporal,independent=ind,scan=scan,confirmed=confirmed,brackets=brackets,nonmonotone=nonmonotone,unstarted=missing,blockers=[k for k,v in gates.items() if not v])
