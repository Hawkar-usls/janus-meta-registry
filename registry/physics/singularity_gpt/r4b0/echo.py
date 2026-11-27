"""Target-free DSS detector adaptation from COSMOS RETINA / NOISE principles."""
import ast,hashlib,json,math,sys
from pathlib import Path
import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import savgol_filter, find_peaks
HERE=Path(__file__).resolve().parent
P=json.loads((HERE/"protocol.json").read_text());D=P["detector"]
OUT=Path("r4b0-output");OUT.mkdir(exist_ok=True)
def write(n,d): (OUT/n).write_text(json.dumps(d,indent=2,allow_nan=False)+"\n")
def frozen():
    path=HERE.parent/"r3b"/"echo_probe.py"
    node=next(n for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=="echo_estimate")
    env={"np":np,"math":math};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),"exec"),env)
    return env["echo_estimate"]
def legacy_diagnosis():
    period=5.2;s=np.linspace(0,period*5,16384)
    t=-np.exp(-s);v=np.exp(s-s[-1])*np.sin(2*np.pi*s/period+.31)
    curv=8*np.pi*v*v;h=30/12288;mag=abs(v)
    raw=np.where((mag[1:-1]>mag[:-2])&(mag[1:-1]>=mag[2:]))[0]+1
    cutoff=[int(i) for i in raw if mag[i]>max(mag)*1e-4]
    resolved=[i for i in cutoff if curv[i]>0 and 1/np.sqrt(curv[i])>=8*h]
    x=np.column_stack((t,t,v,curv,np.zeros_like(t),np.ones_like(t)))
    return {"original_result":frozen()(x,12288),"raw_extrema":len(raw),"after_relative_amplitude_cutoff":len(cutoff),"after_resolution_gate":len(resolved),"required_extrema":5,"ideal_five_peak_dynamic_range":float(np.exp(2*period)),"original_dynamic_range_limit":10000,"raw_peak_relative_amplitudes":(mag[raw]/max(mag)).tolist(),"diagnostic":"Amplitude cutoff is incompatible with five ideal successive growing extrema at period 5.2; measure actual funnel separately from sampling."}
def robust(x):
    return float(1.4826*np.median(abs(x-np.median(x))))
def features(v,smooth):
    r=v-smooth; e=abs(np.fft.rfft(r-r.mean()))**2
    q=r[:-1];w=r[1:];den=np.linalg.norm(q-q.mean())*np.linalg.norm(w-w.mean())
    return {"residual_mad":robust(r),"residual_lag1":float(np.dot(q-q.mean(),w-w.mean())/den) if den>0 else 0.,"residual_fft_high_fraction":float(e[len(e)//2:].sum()/max(e[1:].sum(),1e-300)),"haar_detail_fraction":float(np.sum((r[::2]-r[1::2])**2)/max(2*np.sum(r*r),1e-300))}
def single(t,v,window):
    smooth=savgol_filter(median_filter(v,size=5,mode="nearest"),window,2,mode="interp")
    # Use the largest absolute extremum in each sign lobe, not every noisy local extremum.
    starts=np.r_[0,np.where(np.signbit(smooth[1:])!=np.signbit(smooth[:-1]))[0]+1,len(v)]
    peaks=[]
    for j,k in zip(starts[1:-2],starts[2:-1]):
        if k-j<window//2:continue
        i=int(j+np.argmax(abs(smooth[j:k])))
        if abs(smooth[i])<np.max(abs(smooth))*D["relative_cutoff"]:continue
        snr=abs(smooth[i])/max(robust((v-smooth)[j:k]),1e-300)
        if snr<D["local_snr_min"]:continue
        peaks.append(i)
    cand=[]
    for start in range(len(peaks)-D["min_peaks"]+1):
        ids=np.array(peaks[start:start+D["min_peaks"]]);a=abs(smooth[ids]);sg=np.sign(smooth[ids]);dt=np.diff(t[ids])
        if not (np.all(sg[1:]!=sg[:-1]) and np.all(a[1:]>1.1*a[:-1]) and np.all(dt>0) and np.all(dt[1:]<dt[:-1])):continue
        ratios=2*np.log(dt[:-1]/dt[1:])
        # RETINA: early block fit, later block prediction (not independent physical data).
        p=float(np.median(ratios[:3]))
        if p<=0 or np.max(abs(ratios[:3]-p))/p>D["interval_ratio_tolerance"]:continue
        if np.max(abs(ratios[3:]-p))/p>D["heldout_tolerance"]:continue
        cand.append({"period":p,"peak_indices":ids.tolist(),"heldout_relative_error":float(np.max(abs(ratios[3:]-p))/p)})
    return (cand[-1] if cand else None),features(v,smooth)
def estimate(t,v):
    a,fa=single(t,v,D["windows"][0]);b,fb=single(t,v,D["windows"][1])
    period=None
    if a and b and abs(a["period"]-b["period"])/max(a["period"],b["period"])<=D["cross_scale_tolerance"]:
        period=float((a["period"]+b["period"])/2)
    return period,{"small":a,"large":b,"noise_small":fa,"noise_large":fb}
def signal(rng,period,kind,level,positive):
    n=P["synthetic"]["points"];s=np.linspace(0,5*period,n)
    phase=rng.uniform(0,2*np.pi);t=-np.exp(-s)
    envelope=np.exp(s-s[-1]);u=s/s[-1]
    if positive:angle=2*np.pi*s/period+phase
    elif rng.integers(2)==0:
        angle=2*np.pi*5*(t-t[0])/(t[-1]-t[0])+phase
    else:
        angle=2*np.pi*5*(u+.32*np.sin(2*np.pi*u)/(2*np.pi)+.5*u*u)+phase
    base=envelope*np.sin(angle)
    z=rng.standard_normal(n)
    if kind=="ar1":
        for i in range(1,n):z[i]=.94*z[i-1]+np.sqrt(1-.94**2)*z[i]
    elif kind=="structured":
        z=.65*np.sin(2*np.pi*(19*u+7*u*u)+rng.uniform(0,2*np.pi))+.35*z
    z=z/max(np.std(z),1e-30)
    return t,base+level*envelope*z
def main():
    rng=np.random.default_rng(P["synthetic"]["seed"]);rows=[]
    diag=legacy_diagnosis();write("legacy_diagnosis.json",diag);print("LEGACY_DIAG",json.dumps(diag),flush=True)
    clean=[]
    for period in P["synthetic"]["clean_periods"]:
        t,v=signal(rng,period,"iid",0,True);pred,detail=estimate(t,v)
        clean.append({"truth":period,"estimate":pred,"relative_error":abs(pred-period)/period if pred is not None else None,"details":detail})
    for kind in P["synthetic"]["noise_types"]:
        for level in P["synthetic"]["noise_levels"]:
            for positive in (True,False):
                for i in range(P["synthetic"]["n_per_noise_type_level_class"]):
                    period=float(rng.uniform(*P["synthetic"]["positive_period_range"]))
                    t,v=signal(rng,period,kind,level,positive);pred,detail=estimate(t,v)
                    err=abs(pred-period)/period if positive and pred is not None else None
                    rows.append({"kind":kind,"level":level,"positive":positive,"i":i,"truth":period if positive else None,"estimate":pred,"relative_error":err,"correct":bool(err is not None and err<=.05) if positive else pred is None,"details":detail})
    summary=[]
    for kind in P["synthetic"]["noise_types"]:
        for level in P["synthetic"]["noise_levels"]:
            a=[r for r in rows if r["kind"]==kind and r["level"]==level and r["positive"]];b=[r for r in rows if r["kind"]==kind and r["level"]==level and not r["positive"]]
            summary.append({"kind":kind,"level":level,"positive_correct":sum(r["correct"] for r in a),"positive_detected":sum(r["estimate"] is not None for r in a),"positive_n":len(a),"negative_hits":sum(not r["correct"] for r in b),"negative_n":len(b)})
    gate=all(r["positive_correct"]>=90 and r["negative_hits"]<=5 for r in summary)
    result={"legacy_diagnosis":diag,"clean":clean,"summary":summary,"synthetic_gate":gate,"physical_trace_evaluated":False,"physical_DSS_established":False,"limitations":["Uniform log-coordinate synthetic generator; sample-index smoothing does not establish applicability to irregular physical traces.","Structured noise surrogate is not calibrated to EKG residuals.","Holdout blocks of extrema are not independent observations.","No physical resolution gate transferred to this synthetic-only candidate; physical use forbidden pending independent resolution and native sampling validation."],"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest()}
    write("all_trials.json",rows);write("result.json",result);print("R4B0_ECHO_RESULT",json.dumps(result,allow_nan=False),flush=True)
if __name__=="__main__":main()
