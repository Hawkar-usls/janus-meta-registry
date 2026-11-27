#!/usr/bin/env python3
"""Reference-free candidate echo estimator. Does not consume R1/R2 or reference period."""
import json,math
from pathlib import Path
import numpy as np
from solver_lib import initial,geometry,advance
HERE=Path(__file__).resolve().parent;OUT=Path("singularity-r3b-output");OUT.mkdir(exist_ok=True)
P=json.loads((HERE/"protocol.json").read_text())
def write(n,d): (OUT/n).write_text(json.dumps(d,indent=2,allow_nan=False)+"\n")
def trace(n,A,r0,w):
    h=30/n;r=(np.arange(n)+.5)*h
    p,q=initial(r,A,r0,w);a,al,m,M0=geometry(p,q,r,h,False)
    if not np.isfinite(M0) or np.max(2*m/r)>=.65:return {"class":"INVALID_INITIAL"},np.empty((0,6))
    t=0.;proper=0.;M=M0;maxdrift=0.;maxc=float(np.max(2*m/r));data=[];status="UNRESOLVED"
    def sample():
        # Even central derivative: extrapolate first two cell centers to r=0.
        v=(9*q[0]/a[0]-q[1]/a[1])/8
        curv=8*np.pi*v*v
        return [t,proper,float(v),float(curv),float(np.max(2*m/r)),float(M)]
    data.append(sample())
    while t<16-1e-12:
        dt=min(.3*h,16-t)
        pn,qn=advance(p,q,r,h,dt,False)
        if not (np.isfinite(pn).all() and np.isfinite(qn).all()):status="NUMERICAL_FAILURE";break
        an,aln,mn,Mn=geometry(pn,qn,r,h,False)
        if not np.isfinite(Mn):status="NUMERICAL_FAILURE";break
        proper+=dt*.5*(al[0]+aln[0]);t+=dt
        p,q,a,al,m,M=pn,qn,an,aln,mn,Mn
        maxdrift=max(maxdrift,abs(M-M0)/max(M0,1e-30));maxc=max(maxc,float(np.max(2*m/r)))
        data.append(sample())
        if maxc>=.85:status="NEAR_TRAPPING_PROXY";break
    inner=float(m[np.searchsorted(r,3.)]/max(M0,1e-30))
    if status=="UNRESOLVED" and t>=16-1e-8 and inner<.05 and np.max(2*m/r)<.2:status="DISPERSAL_PROXY"
    return {"class":status,"peak_compactness":maxc,"mass_drift":float(maxdrift),"end_t":t,"central_proper_time":proper},np.array(data)
def echo_estimate(data,n):
    if len(data)<3:return {"status":"INSUFFICIENT_TRACE"}
    h=30/n;v=data[:,2];mag=abs(v);t=data[:,1]
    # Fixed minimum peak magnitude relative to trace maximum; no period supplied.
    peaks=np.where((mag[1:-1]>mag[:-2])&(mag[1:-1]>=mag[2:]))[0]+1
    peaks=[int(i) for i in peaks if mag[i]>max(mag)*1e-4 and data[i,3]>0 and 1/math.sqrt(data[i,3])>=8*h]
    # Require five adjacent resolved extrema with alternating signs, rising magnitudes
    # and shrinking proper-time intervals. Select latest qualifying window, not closest
    # to an expected period.
    cand=[]
    for k in range(len(peaks)-4):
        ii=peaks[k:k+5];amp=mag[ii];sg=np.sign(v[ii]);dt=np.diff(t[ii])
        if not (np.all(sg[1:]!=sg[:-1]) and np.all(amp[1:]>1.1*amp[:-1]) and np.all(dt>0) and np.all(dt[1:]<dt[:-1])):continue
        ds=2*np.log(dt[:-1]/dt[1:])
        med=float(np.median(ds))
        if med<=0 or np.max(abs(ds-med))/med>.2:continue
        cand.append({"peak_indices":ii,"proper_times":t[ii].tolist(),"signed_amplitudes":v[ii].tolist(),"intervals":dt.tolist(),"full_period_candidates":ds.tolist(),"full_period_median":med})
    return {"status":"CANDIDATE_ONLY" if cand else "INSUFFICIENT_RESOLVED_ECHOES","resolved_extrema":len(peaks),"qualifying_windows":len(cand),"candidate":cand[-1] if cand else None}
allrows=[];traces={};est=[]
for i,fam in enumerate(P["echo_probe"]["families"]):
    for n in P["echo_probe"]["resolutions"]:
        lo,hi=fam["bracket"];lastlow=None;lastupper=None
        # Evaluate original endpoints independently at this resolution.
        for step,A in enumerate([lo,hi]):
            row,data=trace(n,A,fam["r0"],fam["width"]);key=f"family{i}_n{n}_endpoint{step}"
            traces[key]=data;allrows.append({"family":i,"n":n,"A":A,"key":key,**row})
            if step==0 and row["class"]=="DISPERSAL_PROXY" and row["mass_drift"]<.05:lastlow=(A,key)
            if step==1 and row["class"]=="NEAR_TRAPPING_PROXY" and row["mass_drift"]<.05:lastupper=(A,key)
        if lastlow is not None and lastupper is not None:
            for step in range(P["echo_probe"]["bisection_steps"]):
                A=(lo+hi)/2;row,data=trace(n,A,fam["r0"],fam["width"]);key=f"family{i}_n{n}_mid{step}"
                traces[key]=data;allrows.append({"family":i,"n":n,"A":A,"key":key,**row})
                if row.get("mass_drift",1)>=.05:break
                if row["class"]=="DISPERSAL_PROXY":lo=A;lastlow=(A,key)
                elif row["class"]=="NEAR_TRAPPING_PROXY":hi=A;lastupper=(A,key)
                else:break
                print("BISECT",json.dumps(allrows[-1]),flush=True)
        # Only the final dispersal side is used for primary echo estimation.
        if lastlow is None or lastupper is None:
            est.append({"family":i,"n":n,"status":"INVALID_PROXY_BRACKET"})
        else:
            est.append({"family":i,"n":n,"proxy_bracket":[lo,hi],"amplitude":lastlow[0],**echo_estimate(traces[lastlow[1]],n)})
        write("echo_cases.json",allrows)
np.savez_compressed(OUT/"echo_traces.npz",**traces)
valid=[z for z in est if z.get("candidate")]
vals=[z["candidate"]["full_period_median"] for z in valid]
agreement=len(vals)==4 and max(vals)-min(vals)<=.1*np.median(vals)
report={"status":"CANDIDATE_CROSS_RESOLUTION_AGREEMENT" if agreement else "DSS_NOT_ESTABLISHED","estimates":est,"cross_resolution_and_family_agreement":bool(agreement),"reference_period_used":False,"known_answer_in_training":False,"event_horizon_confirmed":False,"independent_DSS_confirmation":False,"case_count":len(allrows),"trace_columns":["coordinate_time","central_proper_time","central_signed_derivative","abs_central_Ricci_estimate","max_compactness","outer_mass"]}
write("echo_result.json",report);print("ECHO_RESULT",json.dumps(report),flush=True)
