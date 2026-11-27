"""R4A: fixed-amplitude resolution tests and extended-time diagnostic."""
import json,sys,hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"r3b"))
from solver_lib import initial,geometry,advance
OUT=Path("r4a-output");OUT.mkdir(exist_ok=True)
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
rows=[];traces={}
for A in P["fixed_amplitudes"]:
    for n in P["resolution"]:
        row,x=run(A,5.,1.,30,n,[16.]);key=f"fixed_{A}_{n}"
        rows.append({"key":key,**row});traces[key]=x
        print("FIXED",json.dumps(rows[-1]),flush=True)
        write("fixed.json",rows)
pairs=[]
for A in P["fixed_amplitudes"]:
    c,f=[traces[f"fixed_{A}_{n}"] for n in P["resolution"]]
    T=min(c[-1,1],f[-1,1]);t=np.linspace(0,T,4096)
    v=np.interp(t,c[:,1],c[:,2]);w=np.interp(t,f[:,1],f[:,2])
    lc=np.interp(t,c[:,1],c[:,4]);lf=np.interp(t,f[:,1],f[:,4])
    h1=30/P["resolution"][0];h2=30/P["resolution"][1]
    mask=(lc*h1*h1<=1/64)&(lf*h2*h2<=1/64)
    rel=lambda x,y:float(np.linalg.norm(x-y)/max(np.linalg.norm(y),1e-30))
    pairs.append({"A":A,"common_proper_time":float(T),"central_derivative_relative_l2":rel(v,w),"jointly_resolved_fraction":float(mask.mean()),"jointly_resolved_derivative_relative_l2":rel(v[mask],w[mask]) if mask.any() else None,"peak_Ricci_ratio_fine_over_coarse_common_interval":float(max(lf)/max(max(lc),1e-300))})
write("matched_pairs.json",pairs)
print("MATCHED",json.dumps(pairs),flush=True)
e=P["extended"];orig,x=run(e["amplitude"],e["r0"],e["width"],30,1536,[16.]);traces["held_original"]=x
ext,x=run(e["amplitude"],e["r0"],e["width"],e["domain"],e["n"],e["checkpoints"]);traces["held_extended"]=x
np.savez_compressed(OUT/"traces.npz",**traces)
report={"status":"R4A_DIAGNOSTICS_COMPLETED__SCIENTIFIC_HOLD","fixed_cases":rows,"matched_pairs":pairs,"held_original":orig,"held_extended":ext,"reference_period_used":False,"amr_implemented":False,"scientific_claim":"No DSS or true threshold inferred; fixed-amplitude and time-horizon diagnostics only.","protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest()}
write("result.json",report);print("R4A_RESULT",json.dumps(report),flush=True)
