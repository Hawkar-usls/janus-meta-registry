"""R4B0: precommitted uniform-grid diagnostic, unchanged R4A integrator."""
import json,sys,hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"r3b"))
from solver_lib import initial,geometry,advance
OUT=Path("r4b0-output");OUT.mkdir(exist_ok=True)
P=json.loads((HERE/"protocol.json").read_text())
def write(n,d): (OUT/n).write_text(json.dumps(d,indent=2,allow_nan=False)+"\n")
def run(A,r0,w,R,n,checkpoints):
    h=R/n;r=(np.arange(n)+.5)*h
    p,q=initial(r,A,r0,w);a,al,m,M0=geometry(p,q,r,h,False)
    assert np.isfinite(M0) and np.max(2*m/r)<.65
    t=0.;T=0.;maxdrift=0.;maxc=float(np.max(2*m/r));data=[];snap=[];status="UNRESOLVED";i=0
    # Three-point even extrapolation using r^2.
    z=r[:3]**2;weights=np.array([np.prod([-z[j]/(z[k]-z[j]) for j in range(3) if j!=k]) for k in range(3)])
    def sample():
        v=q[:3]/a[:3];v2=(9*v[0]-v[1])/8;v3=float(weights@v)
        curv=8*np.pi*v2*v2;curv3=8*np.pi*v3*v3
        return [t,T,float(v2),v3,curv,curv3,float(np.max(2*m/r)),float(M),float(m[np.searchsorted(r,3.)]/M0),float((M-m[np.searchsorted(r,.9*R)])/M0)]
    M=M0;data.append(sample())
    def checkpoint():
        arr=np.asarray(data);sel=arr[:,0]>=t-.5
        slope=float(np.polyfit(arr[sel,0],arr[sel,6],1)[0]) if sel.sum()>1 else None
        cur=arr[:,4];k=int(np.argmax(cur))
        local=1/np.sqrt(max(cur[k],1e-300))/h
        disp=bool(arr[-1,8]<.05 and arr[-1,6]<.2)
        return {"t":t,"proper_time":T,"peak_compactness":maxc,"final_compactness":float(arr[-1,6]),"dC_dt_last_half":slope,"inner_mass_fraction":float(arr[-1,8]),"boundary_shell_mass_fraction":float(arr[-1,9]),"mass_drift":maxdrift,"max_central_abs_Ricci":float(cur[k]),"min_central_Ricci_length_over_h":float(local),"curvature_estimator_relative_diff_at_peak":float(abs(arr[k,5]-cur[k])/max(cur[k],1e-300)),"peak_proper_time":float(arr[k,1]),"dispersal_criteria":disp,"class_at_checkpoint":"NEAR_TRAPPING_PROXY" if maxc>=.85 else ("DISPERSAL_PROXY" if disp else "UNRESOLVED")}
    while t<checkpoints[-1]-1e-12:
        dt=min(.3*h,checkpoints[i]-t)
        pn,qn=advance(p,q,r,h,dt,False)
        if not (np.isfinite(pn).all() and np.isfinite(qn).all()):status="NUMERICAL_FAILURE";break
        an,aln,mn,Mn=geometry(pn,qn,r,h,False)
        if not np.isfinite(Mn):status="NUMERICAL_FAILURE";break
        T+=dt*.5*(al[0]+aln[0]);t+=dt
        p,q,a,al,m,M=pn,qn,an,aln,mn,Mn
        maxdrift=max(maxdrift,abs(M-M0)/M0);maxc=max(maxc,float(np.max(2*m/r)));data.append(sample())
        if maxc>=.85:status="NEAR_TRAPPING_PROXY";snap.append(checkpoint());break
        if t>=checkpoints[i]-1e-10:
            snap.append(checkpoint());i+=1
            if i==len(checkpoints):status=snap[-1]["class_at_checkpoint"];break
    if not snap or snap[-1]["t"]<t-1e-10:snap.append(checkpoint())
    return {"A":A,"n":n,"R":R,"h":h,"status":status,"checkpoints":snap},np.asarray(data)

def trend(row,x):
    # Nonoverlapping physical-time windows, not resolution-dependent step counts.
    answers=[]
    for cp in row["checkpoints"]:
        t=cp["t"];windows=[]
        for j in range(4):
            lo=t-2+.5*j;hi=lo+.5
            z=x[(x[:,0]>=lo-1e-12)&(x[:,0]<=hi+1e-12)]
            if len(z)>=3 and lo>=0:
                slope=float(np.polyfit(z[:,0],z[:,6],1)[0])
                windows.append({"lo":lo,"hi":hi,"n":len(z),"slope":slope,"endpoint_delta":float(z[-1,6]-z[0,6])})
            else: windows.append({"lo":lo,"hi":hi,"n":len(z),"slope":None,"endpoint_delta":None})
        yes=bool(cp["peak_compactness"]<.85 and cp["inner_mass_fraction"]<.05 and all(w["slope"] is not None and w["slope"]<0 and w["endpoint_delta"]<0 for w in windows))
        answers.append({"t":t,"trend_only":yes,"primary_class":cp["class_at_checkpoint"],"windows":windows,"inner_mass_fraction":cp["inner_mass_fraction"],"mass_drift":cp["mass_drift"]})
    return answers
rows={};traces={}
for cfg in P["cases"]:
    key=cfg["id"]
    row,x=run(cfg["A"],cfg["r0"],cfg["w"],cfg["R"],cfg["n"],cfg["checkpoints"])
    row["trend"]=trend(row,x)
    row["mass_budget_pass"]=bool(row["checkpoints"][-1]["mass_drift"]<P["classification"]["mass_drift_max_strict"])
    rows[key]=row;traces[key]=x
    write("cases.json",rows)
    np.savez_compressed(OUT/"traces.npz",**traces)
    print("R4B0_CASE",json.dumps({"id":key,**row},allow_nan=False),flush=True)
pairs=[]
for k1,k2 in [("critical_1536","critical_3072"),("critical_3072","critical_6144")]:
    c,f=traces[k1],traces[k2];T=min(c[-1,1],f[-1,1])
    t=np.linspace(0,T,4096)
    v=np.interp(t,c[:,1],c[:,2]);w=np.interp(t,f[:,1],f[:,2])
    lc=np.interp(t,c[:,1],c[:,4]);lf=np.interp(t,f[:,1],f[:,4])
    h1=rows[k1]["h"];h2=rows[k2]["h"]
    mask=(lc*h1*h1<=1/64)&(lf*h2*h2<=1/64)
    rel=lambda x,y:float(np.linalg.norm(x-y)/max(np.linalg.norm(y),1e-30))
    pair={"coarse":k1,"fine":k2,"common_proper_time":float(T),"central_derivative_relative_l2":rel(v,w),"jointly_resolved_fraction":float(mask.mean()),"jointly_resolved_derivative_relative_l2":rel(v[mask],w[mask]) if mask.any() else None,"peak_Ricci_ratio_fine_over_coarse_common_interval":float(max(lf)/max(max(lc),1e-300))}
    pairs.append(pair)
write("matched_pairs.json",pairs)
print("R4B0_MATCHED",json.dumps(pairs,allow_nan=False),flush=True)
replay_ok=rows["critical_1536"]["status"]=="NEAR_TRAPPING_PROXY" and rows["critical_3072"]["status"]=="DISPERSAL_PROXY"
mass_ok=all(r["mass_budget_pass"] for r in rows.values())
control_ok=rows["noncritical_6144"]["status"]=="DISPERSAL_PROXY"
fine=rows["critical_6144"]["status"]
if any(r["status"]=="NUMERICAL_FAILURE" for r in rows.values()): decision="NUMERICAL_FAILURE_HOLD"
elif not replay_ok: decision="REPLAY_MISMATCH_HOLD"
elif not mass_ok: decision="MASS_BUDGET_HOLD"
elif not control_ok: decision="NONCRITICAL_CONTROL_HOLD"
elif fine=="DISPERSAL_PROXY": decision="FINE_GRID_DISPERSAL_PROXY__AMR_VALIDATION_JUSTIFIED_NOT_CONVERGED"
elif fine=="NEAR_TRAPPING_PROXY": decision="NONMONOTONE_PROXY__SCHEME_AUDIT_BEFORE_AMR"
else: decision="CLASSIFIER_OR_RESOLUTION_HOLD"
result={"id":P["id"],"status":decision,"reproduction_pass":replay_ok,"mass_budget_pass":mass_ok,"noncritical_control_pass":control_ok,"cases":rows,"matched_pairs":pairs,"scientific_hold":True,"dss_tested":False,"amr_implemented":False,"n12288_run":False,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"claim_ceiling":"Uniform-grid fixed-point diagnosis only; trend is not an independent final classification; no continuum threshold, horizon, DSS or critical exponent inferred."}
write("result.json",result)
print("R4B0_RESULT",json.dumps({k:v for k,v in result.items() if k not in ("cases","matched_pairs")},allow_nan=False),flush=True)
