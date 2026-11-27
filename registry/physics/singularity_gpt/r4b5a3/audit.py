"""R4B5A.3 fixed-time compactness and threshold crossing audit."""
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
B=P["configuration"];G=P["gates"]
OUT=Path("r4b5a3-output");OUT.mkdir(exist_ok=True)
def write(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
def emit(tag,obj): print("R4B5A3_"+tag,json.dumps(obj,allow_nan=False),flush=True)
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
        if peak>=.85:
            if min(1/np.sqrt(max(maxR2,1e-300))/h,1/np.sqrt(max(maxR3,1e-300))/h)<8 or drift>=.01 or maxres[0]>=.01 or maxrefres>=.01:
                status="SAFETY_HOLD";break
        if peak>=.90:status="EVENT_090_REACHED";break
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
    result={"id":P["id"],"status":status,"gates":gates,"scientific_hold":True,"identifiability_hold":"independent R4B.10, not re-audited","dss_tested":False,"amr_implemented":False,"historical_compactness_fail_preserved":True,"fine_run":"fine" in rows,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"claim_ceiling":P["claim_ceiling"],**extra}
    write("result.json",result);emit("RESULT",result);sys.exit(0)
archive=json.loads((HERE.parent/"r4b5a2"/"result_archive.json").read_text())
require(archive["run"]==P["parent"]["run"],"PARENT_RUN")
records=archive["logged_evidence"];parent=records[-1]["data"]
require(parent["status"]=="CURVATURE_RECOVERY_HOLD" and parent["gates"]["independent_family_boundary"] and parent["gates"]["temporal"] and parent["fine_run"],"PARENT_ADMISSION")
old={r["data"]["id"]:r["data"] for r in records if r["kind"]=="CASE"}
thresholds=P["events"]["thresholds"];windows=P["fixed_windows"]["tau_ends"]
def cfg(n,cfl=.3):
    return {"A":B["A"],"r0":B["r0"],"w":B["w"],"R":B["R"],"end":B["end"],"n":n,"CFL":cfl,"family":"original","reference_radius":B["reference_radius"]}
def crossing(key,c):
    x=traces[key];indices=np.flatnonzero(x[:,6]>=c)
    if len(indices)==0:return None
    i=int(indices[0])
    if i==0:return None
    a,b=x[i-1],x[i];den=b[6]-a[6]
    if den<=0:return None
    frac=float((c-a[6])/den);z=a+frac*(b-a)
    return {"index":i,"tau":float(z[1]),"t":float(z[0]),"Ricci":float(z[4]),"Ricci_alt":float(z[5]),"native_C":float(np.max(x[:i+1,6])),"native_overshoot":float(b[6]-c),"native_tau":float(b[1]),"native_t":float(b[0]),"native_Ricci":float(np.max(x[:i+1,4])),"native_Ricci_alt":float(np.max(x[:i+1,5])),"bracket_C":[float(a[6]),float(b[6])],"bracket_tau":[float(a[1]),float(b[1])]}
def check_run(key):
    r=rows[key];ev={str(c):crossing(key,c) for c in thresholds};x=traces[key]
    numeric=r["status"]=="EVENT_090_REACHED" and min(r["scale"],r["scale_alt"])>=8 and max(r["mass_drift"],r["direct_balance_residual_max"],r["reference_interior_balance_residual_max"])<.01
    e=ev["0.85"];replay={}
    if e is not None:
        i=e["index"];prefix=x[:i+1];E0=r["initial_mass_or_flat_energy"]
        vals={"peak_compactness":e["native_C"],"curvature_peak":e["native_Ricci"],"curvature_peak_alt":e["native_Ricci_alt"],"t":e["native_t"],"proper_time":e["native_tau"],"mass_drift":float(np.max(np.abs(prefix[:,7]-E0))/E0),"direct_balance_residual_max":float(prefix[-1,15]),"reference_interior_balance_residual_max":float(prefix[-1,18])}
        replay={k:abs(v-old[key][k])/max(abs(old[key][k]),1e-30) for k,v in vals.items()}
    checks={"numeric":bool(numeric),"all_events":all(v is not None for v in ev.values()),"fixed_support":x[-1,1]>=max(windows),"prefix_replay":bool(replay) and max(replay.values())<=1e-8}
    report={"pass":all(checks.values()),"checks":checks,"events":ev,"replay_errors":replay}
    emit("EVENTS",{"id":key,**report});return report
gates={"sealed_parent_boundary":True};checks={}
for key,n,cfl in (("coarse",12288,.3),("medium",24576,.3),("medium_half",24576,.15)):
    execute(key,cfg(n,cfl),True)
    checks[key]=check_run(key)
    if not checks[key]["pass"]:finish("EVENT_ADMISSION_HOLD",{**gates,"pre_fine_integrity":False},checks=checks,unresolved=key)
gates["pre_fine_integrity"]=True
OBS=(("C",6),("signed_derivative",2),("Ricci",4),("Ricci_alt",5))
def fixed_peak(x,col,end):
    require(x[-1,1]>=end,"FIXED_SUPPORT")
    return float(max(np.max(x[x[:,1]<=end,col]),np.interp(end,x[:,1],x[:,col])))
def fixed_pair(k1,k2,end):
    x,y=traces[k1],traces[k2]
    require(min(x[-1,1],y[-1,1])>=end,"FIXED_SUPPORT")
    tau=np.linspace(0,end,32769);out={}
    for name,col in OBS:
        a=np.interp(tau,x[:,1],x[:,col]);b=np.interp(tau,y[:,1],y[:,col]);d=a-b
        pa,pb=fixed_peak(x,col,end),fixed_peak(y,col,end)
        out[name]={"abs_l2":float(np.linalg.norm(d)),"abs_linf":float(np.max(np.abs(d))),"rel_l2":norm(a,b),"rel_linf":linf(a,b),"peak_first":pa,"peak_second":pb,"peak_signed":pa-pb,"peak_rel":abs(pa-pb)/max(abs(pb),1e-30)}
    return out
def temporal_check(d,s,rel):
    return {"absolute":d,"spatial_absolute":s,"relative":rel,"temporal_over_spatial":d/s if s>0 else None,"pass":rel<.01 and d<=.25*s}
temporal={}
for end in windows:
    sp=fixed_pair("coarse","medium",end);tm=fixed_pair("medium","medium_half",end);m={}
    for name,_ in OBS:
        for n in ("l2","linf"):
            m[name+"_"+n]=temporal_check(tm[name]["abs_"+n],sp[name]["abs_"+n],tm[name]["rel_"+n])
        if name!="signed_derivative":
            m[name+"_peak"]=temporal_check(abs(tm[name]["peak_signed"]),abs(sp[name]["peak_signed"]),tm[name]["peak_rel"])
    temporal[str(end)]={"metrics":m,"pass":all(v["pass"] for v in m.values())}
event_temporal={}
for c in thresholds:
    a,b,d=[checks[k]["events"][str(c)] for k in ("coarse","medium","medium_half")]
    event_temporal[str(c)]=temporal_check(abs(b["tau"]-d["tau"]),abs(a["tau"]-b["tau"]),abs(b["tau"]-d["tau"])/abs(d["tau"]))
gates["temporal"]=all(v["pass"] for v in temporal.values()) and all(v["pass"] for v in event_temporal.values())
emit("TEMPORAL",{"fixed_windows":temporal,"event_times":event_temporal,"pass":gates["temporal"]})
if not gates["temporal"]:finish("EVENT_TEMPORAL_HOLD",gates,checks=checks,temporal=temporal,event_temporal=event_temporal)
elapsed=time.monotonic()-START;estimate=4*rows["medium"]["elapsed_seconds"]
gates["budget"]=elapsed+estimate<=P["budget"]["maximum_projected_total_seconds"]
emit("BUDGET",{"elapsed":elapsed,"projected_fine":estimate,"pass":gates["budget"]})
if not gates["budget"]:finish("COMPUTE_BUDGET_HOLD",gates)
execute("fine",cfg(49152),True);checks["fine"]=check_run("fine")
gates["fine_integrity"]=checks["fine"]["pass"]
if not gates["fine_integrity"]:finish("EVENT_ADMISSION_HOLD",gates,checks=checks)
def order(a,b,signed=False):
    d1,d2=abs(a),abs(b);p=float(np.log2(d1/d2)) if d1>0 and d2>0 else None
    monotone=not signed or a*b>0
    return {"d12":d1,"d23":d2,"p":p,"monotone":bool(monotone),"decreasing":d2<d1,"pass":p is not None and 1.5<=p<=2.5 and bool(monotone) and d2<d1}
fixed={}
for end in windows:
    a=fixed_pair("coarse","medium",end);b=fixed_pair("medium","fine",end)
    orders={};checks_window={}
    for name,_ in OBS:
        for n in ("l2","linf"):orders[name+"_"+n]=order(a[name]["abs_"+n],b[name]["abs_"+n])
        if name!="signed_derivative":orders[name+"_peak"]=order(a[name]["peak_signed"],b[name]["peak_signed"],True)
        checks_window[name+"_trace"]=max(a[name]["rel_l2"],a[name]["rel_linf"],b[name]["rel_l2"],b[name]["rel_linf"])<=.1
    checks_window["C_peak_abs"]=abs(b["C"]["peak_signed"])<=.0005
    checks_window["C_peak_rel"]=b["C"]["peak_rel"]<=.01
    checks_window["C_trace_abs"]=b["C"]["abs_linf"]<=.0005
    checks_window["C_order"]=all(orders[k]["pass"] for k in ("C_l2","C_linf","C_peak"))
    checks_window["Ricci_peaks"]=all(b[k]["peak_rel"]<=.02 for k in ("Ricci","Ricci_alt"))
    checks_window["other_orders"]=all(v["pass"] for k,v in orders.items() if not k.startswith("C_"))
    report={"tau_end":end,"pair_12":a,"pair_23":b,"orders":orders,"checks":checks_window,"pass":all(checks_window.values())}
    fixed[str(end)]=report;emit("FIXED_WINDOW",report)
gates["fixed_time_compactness"]=all(all(v for k,v in r["checks"].items() if k.startswith("C_")) for r in fixed.values())
gates["fixed_time_other_observables"]=all(all(v for k,v in r["checks"].items() if not k.startswith("C_")) for r in fixed.values())
events={}
for c in thresholds:
    a,b,d=[checks[k]["events"][str(c)] for k in ("coarse","medium","fine")]
    dt1=a["tau"]-b["tau"];dt2=b["tau"]-d["tau"]
    c1=a["native_C"]-b["native_C"];c2=b["native_C"]-d["native_C"]
    tord=order(dt1,dt2,True);native=order(c1,c2,True)
    ricci={k:abs(b[k]-d[k])/max(abs(d[k]),1e-30) for k in ("Ricci","Ricci_alt")}
    checks_event={"tau_absolute":abs(dt2)<=.0005,"tau_order":tord["pass"],"event_Ricci":max(ricci.values())<=.02}
    report={"threshold":c,"tau":[a["tau"],b["tau"],d["tau"]],"native_C":[a["native_C"],b["native_C"],d["native_C"]],"native_overshoot":[a["native_overshoot"],b["native_overshoot"],d["native_overshoot"]],"tau_order":tord,"native_C_order_diagnostic":native,"event_Ricci_relative":ricci,"checks":checks_event,"pass":all(checks_event.values())}
    events[str(c)]=report;emit("EVENT_COMPARE",report)
gates["event_invariance"]=all(v["pass"] for v in events.values())
# Reconstruct exact historical .85 prefixes; interpolate only at common endpoint.
prefix={k:traces[k][:checks[k]["events"]["0.85"]["index"]+1] for k in ("coarse","medium","fine")}
cut=min(x[-1,1] for x in prefix.values())
decomp={}
for k1,k2 in (("coarse","medium"),("medium","fine")):
    a,b=prefix[k1],prefix[k2];r={}
    for name,col in (("Ricci",4),("Ricci_alt",5)):
        an,bn=float(np.max(a[:,col])),float(np.max(b[:,col]));ac,bc=fixed_peak(a,col,cut),fixed_peak(b,col,cut)
        native=an-bn;common=ac-bc;tail=(an-ac)-(bn-bc)
        r[name]={"native_signed_difference":native,"common_signed_difference":common,"tail_difference":tail,"tail_share":tail/native if native else None,"decomposition_residual":native-common-tail,"native_relative":abs(native)/max(abs(bn),1e-30),"common_relative":abs(common)/max(abs(bc),1e-30)}
    decomp[k1+"_"+k2]=r
d=decomp["medium_fine"];gates["Ricci_nonregression"]=all(max(v["native_relative"],v["common_relative"])<=.02 for v in d.values()) and d["Ricci"]["native_relative"]<=P["ricci_nonregression"]["reference_medium_fine_native_relative"]+1e-10 and d["Ricci"]["common_relative"]<=P["ricci_nonregression"]["reference_medium_fine_common_relative"]+1e-10
emit("RICCI_DECOMPOSITION",{"common_tau":float(cut),"pairs":decomp,"pass":gates["Ricci_nonregression"]})
status="FIXED_TIME_EVENT_CONSISTENCY_PASS__SCIENTIFIC_HOLD" if all(gates.values()) else "COMPACTNESS_CONVERGENCE_HOLD"
finish(status,gates,checks=checks,temporal=temporal,event_temporal=event_temporal,fixed_windows=fixed,event_comparisons=events,ricci_decomposition=decomp,blockers=[k for k,v in gates.items() if not v])
