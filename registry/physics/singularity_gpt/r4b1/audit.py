"""R4B1: fixed-amplitude uniform convergence audit. No DSS/threshold fit."""
import hashlib,json,sys,time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"r3b"))
from solver_lib import initial,geometry,advance
P=json.loads((HERE/"protocol.json").read_text())
OUT=Path("r4b1-output");OUT.mkdir(exist_ok=True)
def write(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
def emit(tag,obj):
    print("R4B1_"+tag,json.dumps(obj,allow_nan=False),flush=True)
def require(ok,msg):
    if not ok: raise RuntimeError(msg)
def residual(m,m0,integrated_inward_flux,M0):
    return (m-m0-integrated_inward_flux)/M0
# Manufactured sign and injected-imbalance checks are algebra controls,
# not independent field-evolution benchmarks.
for flux in (-.12,.12):
    m0=np.array([.6,1.]); f=np.array([flux,flux])
    integ=.5*(f+f)*.5
    require(np.max(np.abs(residual(m0+integ,m0,integ,1.)))<1e-14,"FLUX_SIGN_CONTROL")
    require(np.max(np.abs(residual(m0+integ+.02,m0,integ,1.)))>.01,"IMBALANCE_CONTROL")
emit("CONTROLS",{"manufactured_inward":True,"manufactured_outward":True,"injected_imbalance":True})
def windows(data,t):
    x=np.asarray(data)
    out=[]
    for j in range(4):
        lo=t-2+.5*j; hi=lo+.5
        z=x[(x[:,0]>=lo-1e-12)&(x[:,0]<=hi+1e-12)]
        if len(z)>=3 and lo>=0:
            slope=float(np.polyfit(z[:,0],z[:,6],1)[0])
            out.append({"lo":float(lo),"hi":float(hi),"n":len(z),"slope":slope,"endpoint_delta":float(z[-1,6]-z[0,6])})
        else:
            out.append({"lo":float(lo),"hi":float(hi),"n":len(z),"slope":None,"endpoint_delta":None})
    return out
def run(cfg,adaptive=False,held=False):
    started=time.monotonic()
    A,r0,w,R,n=[cfg[k] for k in ("A","r0","w","R","n")]
    h=R/n;r=(np.arange(n)+.5)*h
    p,q=initial(r,A,r0,w);a,al,m,M0=geometry(p,q,r,h,False)
    require(np.isfinite(M0) and M0>0 and np.max(2*m/r)<.65,"INITIAL_STATE")
    # m_t = 4*pi*r²*alpha*Phi*Pi/a³, positive inward.
    # Use bracketed center values at fixed interior radii, and separately
    # reconstructed boundary fields at R. No use of dm/dt in this flux.
    radii=np.array(P["mass"]["radii"],dtype=float)
    hi=np.searchsorted(r,radii);lo=hi-1
    lam=(radii-r[lo])/(r[hi]-r[lo])
    idx=np.stack((lo,hi),axis=1)
    def mix(z): return (1-lam)*z[:,0]+lam*z[:,1]
    def fields():
        f=mix(4*np.pi*r[idx]**2*al[idx]*p[idx]*q[idx]/a[idx]**3)
        pb=1.5*p[-1]-.5*p[-2];qb=1.5*q[-1]-.5*q[-2]
        # R3B lapse normalization alpha(R)=sqrt(1-2M/R).
        # alpha/a^3=(1-2M/R)^2 at the boundary.
        fb=4*np.pi*R**2*(1-2*M/R)**2*pb*qb
        return np.r_[mix(m[idx]),M],np.r_[f,fb]
    t=0.;T=0.;Talt=0.;M=M0;steps=0
    maxdrift=0.;maxc=float(np.max(2*m/r));maxres=np.zeros(4)
    integral=np.zeros(4);flux_sq=np.zeros(4);error_sq=np.zeros(4)
    maxflux=np.zeros(4);maxres_time=np.zeros(4)
    mass0,fprev=fields();massprev=mass0.copy()
    maxflux=np.maximum(maxflux,np.abs(fprev))
    z=r[:3]**2
    weights=np.array([np.prod([-z[j]/(z[k]-z[j]) for j in range(3) if j!=k]) for k in range(3)])
    data=[];snap=[];status="UNRESOLVED";stop=None;first_eligible=None
    def sample():
        v=q[:3]/a[:3];v2=(9*v[0]-v[1])/8;v3=float(weights@v)
        return [t,T,float(v2),v3,float(8*np.pi*v2*v2),float(8*np.pi*v3*v3),float(np.max(2*m/r)),float(M),float(m[np.searchsorted(r,3.)]/M0),float((M-m[np.searchsorted(r,.9*R)])/M0),Talt,*maxres.tolist(),maxdrift]
    data.append(sample())
    def checkpoint():
        ar=np.asarray(data); k=int(np.argmax(ar[:,4]))
        c2=float(ar[k,4]);c3=float(np.max(ar[:,5]))
        cp={"t":float(t),"proper_time":float(T),"alternative_proper_time":float(Talt),"peak_compactness":maxc,"final_compactness":float(ar[-1,6]),"inner_mass_fraction":float(ar[-1,8]),"boundary_shell_mass_fraction":float(ar[-1,9]),"mass_drift":maxdrift,"mass_flux_residual_max":float(max(maxres)),"max_central_abs_Ricci":c2,"max_central_abs_Ricci_alt":c3,"min_central_Ricci_length_over_h":float(1/np.sqrt(max(c2,1e-300))/h),"min_central_Ricci_length_over_h_alt":float(1/np.sqrt(max(c3,1e-300))/h),"within_grid_estimator_relative_diff_at_peak":float(abs(ar[k,5]-c2)/max(c2,1e-300)),"peak_proper_time":float(ar[k,1]),"steps":steps}
        cp["class_at_checkpoint"]="NEAR_TRAPPING_PROXY" if maxc>=.85 else ("DISPERSAL_PROXY" if cp["inner_mass_fraction"]<.05 and cp["final_compactness"]<.2 else "UNRESOLVED")
        if held and t>=P["adaptive"]["first_check"]-1e-10:
            win=windows(data,t)
            cp["windows"]=win
            cp["eligible_stop"]=bool(cp["class_at_checkpoint"]=="DISPERSAL_PROXY" and maxdrift<.01 and max(maxres)<.01 and all(x["slope"] is not None and x["slope"]<0 and x["endpoint_delta"]<0 for x in win))
        return cp
    checkpoints=list(np.arange(.5,cfg["end"]+.25,.5)) if held else [cfg["end"]]
    failed=False
    for target in checkpoints:
        while t<target-1e-12:
            dt=min(.3*h,target-t)
            pn,qn=advance(p,q,r,h,dt,False)
            if not (np.isfinite(pn).all() and np.isfinite(qn).all()): failed=True;break
            an,aln,mn,Mn=geometry(pn,qn,r,h,False)
            if not (np.isfinite(Mn) and np.isfinite(an).all() and np.isfinite(aln).all() and np.isfinite(mn).all()): failed=True;break
            T+=dt*.5*(al[0]+aln[0])
            Talt+=dt*.5*((9*al[0]-al[1])/8+(9*aln[0]-aln[1])/8)
            t+=dt;steps+=1
            p,q,a,al,m,M=pn,qn,an,aln,mn,Mn
            massnew,fnew=fields()
            favg=.5*(fprev+fnew)
            integral+=dt*favg
            re=np.abs(residual(massnew,mass0,integral,M0))
            maxres_time=np.where(re>maxres,t,maxres_time)
            maxres=np.maximum(maxres,re)
            maxflux=np.maximum(maxflux,np.abs(fnew))
            error_sq+=dt*((massnew-massprev)/dt-favg)**2
            flux_sq+=dt*favg**2
            massprev=massnew;fprev=fnew
            maxdrift=max(maxdrift,abs(M-M0)/M0);maxc=max(maxc,float(np.max(2*m/r)));data.append(sample())
            if maxc>=.85:break
        cp=checkpoint();snap.append(cp)
        if failed:
            status="NUMERICAL_FAILURE";break
        if cp["class_at_checkpoint"]=="NEAR_TRAPPING_PROXY":
            status=cp["class_at_checkpoint"];break
        if cp.get("eligible_stop",False) and first_eligible is None:
            first_eligible=cp.copy()
        if adaptive and cp.get("eligible_stop",False):
            status=cp["class_at_checkpoint"];stop=cp.copy();break
        status=cp["class_at_checkpoint"]
    x=np.asarray(data)
    require(np.isfinite(x).all() and np.all(np.diff(x[:,1])>0),"PROPER_TIME_INTEGRITY")
    mass_records=[]
    for j,rr in enumerate([*radii.tolist(),R]):
        mass_records.append({"radius":rr,"initial_mass":float(mass0[j]),"final_mass":float(massprev[j]),"integrated_signed_inward_flux":float(integral[j]),"max_abs_flux":float(maxflux[j]),"final_normalized_residual":float(residual(massprev,mass0,integral,M0)[j]),"max_normalized_residual":float(maxres[j]),"time_of_max_residual":float(maxres_time[j]),"instantaneous_residual_relative_l2":float(np.sqrt(error_sq[j]/flux_sq[j])) if flux_sq[j]>1e-30 else None})
    row={"A":A,"n":n,"R":R,"h":h,"status":status,"initial_mass":float(M0),"final":snap[-1],"mass_records":mass_records,"mass_budget_pass":bool(maxdrift<.01 and max(maxres)<.01),"raw_drift_pass":bool(maxdrift<.01),"flux_residual_pass":bool(max(maxres)<.01),"first_eligible_stop":first_eligible,"actual_stop":stop,"steps":steps,"elapsed_seconds":time.monotonic()-started}
    return row,x
rows={};traces={}
def execute(key,cfg,**kw):
    row,x=run(cfg,**kw);rows[key]=row;traces[key]=x
    write("cases.json",rows);np.savez_compressed(OUT/"traces.npz",**traces)
    emit("CASE",{"id":key,**row})
    return row,x
for n in P["critical"]["inference_grids"]:
    execute("critical_"+str(n),{**P["critical"],"n":n})
execute("noncritical",P["control"])
held_cfg={**P["adaptive"],"end":P["adaptive"]["full_end"]}
early,xe=execute("held_early",held_cfg,adaptive=True,held=True)
full,xf=execute("held_full",held_cfg,adaptive=False,held=True)
# Independent actual early run must match the full-run prefix exactly.
prefix_ok=bool(len(xe)<=len(xf) and np.array_equal(xe,xf[:len(xe)]))
adaptive_ok=bool(prefix_ok and early["actual_stop"] is not None and full["first_eligible_stop"] is not None and early["actual_stop"]==full["first_eligible_stop"] and early["status"]==full["status"]=="DISPERSAL_PROXY" and full["final"]["t"]>=64-1e-10 and early["final"]["t"]<full["final"]["t"] and full["mass_budget_pass"] and early["mass_budget_pass"])
adapt={"prefix_exact":prefix_ok,"pass":adaptive_ok,"early_time":early["final"]["t"],"full_time":full["final"]["t"],"early_steps":early["steps"],"full_steps":full["steps"],"step_reduction_fraction":1-early["steps"]/max(1,full["steps"]),"early_mass_drift":early["final"]["mass_drift"],"full_mass_drift":full["final"]["mass_drift"],"full_peak_compactness":full["final"]["peak_compactness"],"early_peak_compactness":early["final"]["peak_compactness"]}
emit("ADAPTIVE",adapt)
ns=P["critical"]["inference_grids"]; xx=[traces["critical_"+str(n)] for n in ns]; rr=[rows["critical_"+str(n)] for n in ns]
T=min(x[-1,1] for x in xx);require(T>0,"EMPTY_COMMON_SUPPORT")
tau=np.linspace(0,T,32769)
# No shift or selected window. Same common support for all norms.
samples=[np.stack([np.interp(tau,x[:,1],x[:,col]) for col in (2,4,5)],axis=1) for x in xx]
mask=np.ones(len(tau),dtype=bool)
for row,y in zip(rr,samples): mask&=(np.maximum(y[:,1],y[:,2])*row["h"]**2<=1/64)
def metrics(y,z):
    d=y-z
    a=float(np.linalg.norm(d)); b=float(np.linalg.norm(z))
    return {"absolute_l2":a,"relative_l2":a/max(b,1e-30),"relative_linf":float(np.max(np.abs(d)))/max(float(np.max(np.abs(z))),1e-30)}
pairs=[]
for i in range(2):
    d={"coarse":ns[i],"fine":ns[i+1],"common_proper_time":float(T),"samples":len(tau),"jointly_resolved_fraction_all_three":float(mask.mean()),"observables":{}}
    for j,key in enumerate(("signed_central_derivative","central_Ricci_proxy","central_Ricci_proxy_alt")):
        y,z=samples[i][:,j],samples[i+1][:,j]
        d["observables"][key]={"full":metrics(y,z),"jointly_resolved":metrics(y[mask],z[mask]) if mask.any() else None}
    pairs.append(d)
orders={}
for key in pairs[0]["observables"]:
    d1=pairs[0]["observables"][key]["full"]["absolute_l2"];d2=pairs[1]["observables"][key]["full"]["absolute_l2"]
    orders[key]={"difference_ratio":d1/d2 if d2>0 else None,"observed_order_diagnostic":float(np.log2(d1/d2)) if d1>0 and d2>0 else None,"decreasing":bool(d2<d1)}
convergence_ok=all(v["decreasing"] for v in orders.values()) and all(max(m["full"]["relative_l2"],m["full"]["relative_linf"])<=.1 for d in pairs for m in d["observables"].values())
local_ok=all(min(r["final"]["min_central_Ricci_length_over_h"],r["final"]["min_central_Ricci_length_over_h_alt"])>=8 for r in rr)
fine_local_ok=min(rr[-1]["final"]["min_central_Ricci_length_over_h"],rr[-1]["final"]["min_central_Ricci_length_over_h_alt"])>=8
replay={}
for n in (3072,6144):
    ref=P["replay_reference"][str(n)];r=rows["critical_"+str(n)];cp=r["final"]
    errors={k:abs(cp[v]-ref[k])/max(abs(ref[k]),1e-30) for k,v in (("peak","peak_compactness"),("mass","mass_drift"),("scale","min_central_Ricci_length_over_h"))}
    replay[str(n)]={"relative_errors":errors,"pass":bool(r["status"]==ref["status"] and max(errors.values())<=P["replay_relative_tolerance"])}
gates={"replay":all(r["pass"] for r in replay.values()),"numerical_integrity":all(r["status"]!="NUMERICAL_FAILURE" for r in rows.values()),"noncritical_control":rows["noncritical"]["status"]=="DISPERSAL_PROXY","inference_mass_budget":all(r["mass_budget_pass"] for r in rows.values()),"stable_class":all(r["status"]=="DISPERSAL_PROXY" for r in rr),"local_resolution":local_ok,"cross_grid_convergence":convergence_ok,"adaptive_validation":adaptive_ok}
mapping={"replay":"REPLAY_MISMATCH_HOLD","numerical_integrity":"NUMERICAL_FAILURE_HOLD","noncritical_control":"CONTROL_FAILURE_HOLD","inference_mass_budget":"MASS_BALANCE_HOLD","stable_class":"NONMONOTONE_OR_UNRESOLVED_CLASS_HOLD","local_resolution":"LOCAL_RESOLUTION_HOLD","cross_grid_convergence":"CONVERGENCE_HOLD","adaptive_validation":"ADAPTIVE_STOP_HOLD"}
failed=[mapping[k] for k in P["gates"] if not gates[k]]
comparison={"pairs":pairs,"observed_orders":orders,"all_three_local_resolution_pass":local_ok,"finest_local_resolution_pass":fine_local_ok,"common_proper_time":float(T),"all_three_resolved_fraction":float(mask.mean())}
write("comparison.json",comparison);emit("COMPARISON",comparison)
result={"id":P["id"],"status":failed[0] if failed else "UNIFORM_GRID_CONVERGENCE_CRITERIA_PASS__DSS_STILL_HELD","all_blockers":failed,"gates":gates,"replay":replay,"adaptive":adapt,"historical_R4B0_status":"MASS_BUDGET_HOLD","historical_grid_1536_excluded_from_inference":True,"scientific_hold":True,"dss_tested":False,"amr_implemented":False,"critical_amplitude_fit":False,"critical_exponent_fit":False,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"claim_ceiling":"Finite-resolution engineering audit only. Flux residual tests separate Einstein time equation but shares numerical field states and metric; no independent solver, no continuum or horizon proof."}
write("result.json",result);emit("RESULT",result)
