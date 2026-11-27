"""Clean geometric identifiability controls and separate envelope / PIT audits."""
import ast,hashlib,json,sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from scipy.special import ndtr
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/"r4b3"),str(HERE.parent/"r4b2")]
from generator import cases
import rivals
P=json.loads((HERE/"protocol.json").read_text());C=P["controls"]
parent=json.loads((HERE.parent/"r4b4"/"protocol.json").read_text())["generator"]
cfg={**parent,"new_seed":parent["seed"]}
OUT=Path("r4b5-output");OUT.mkdir(exist_ok=True)
mode=sys.argv[1]
def frozen(path,name,env):
    node=next(x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),"exec"),env)
    return env[name]
phase_ci=frozen(HERE.parent/"r4b3"/"phase.py","phase_ci",{"np":np,"least_squares":least_squares})
envelope_only=frozen(HERE.parent/"r4b4"/"ablate.py","envelope_only",{"np":np})
def extrema(t,v):
    # One peak per complete sign lobe; quadratic interpolation in physical time.
    edges=np.r_[0,np.where(np.signbit(v[1:])!=np.signbit(v[:-1]))[0]+1,len(v)]
    peaks=[]
    for j,k in zip(edges[1:-2],edges[2:-1]):
        i=int(j+np.argmax(abs(v[j:k])))
        if i<1 or i>=len(v)-1 or k-j<4:continue
        tt=t[i-1:i+2]-t[i];scale=max(abs(tt))
        if scale<=0:continue
        xx=tt/scale;yy=abs(v[i-1:i+2]);coef=np.polyfit(xx,yy/max(yy),2)
        offset=-coef[1]/(2*coef[0]) if coef[0]<0 else 0.
        if offset<xx[0] or offset>xx[-1]:offset=0.
        peaks.append((float(t[i]+offset*scale),float(abs(v[i])),i))
    return peaks
def geometric(t,v):
    p=extrema(t,v)
    if len(p)<5:return {"status":"INSUFFICIENT_PEAKS","peaks":len(p)}
    tp=np.array([x[0] for x in p]);dt=np.diff(tp);q=dt[1:]/dt[:-1]
    med=float(np.median(q))
    if not (0<med<.98):return {"status":"NO_RELIABLE_FINITE_ACCUMULATION","peaks":len(p),"median_ratio":med}
    if np.max(abs(q-med))/med>.05:return {"status":"INCONSISTENT_CONTRACTION","peaks":len(p),"median_ratio":med}
    # Latest triplet avoids extrapolating a tiny final gap from very early peaks.
    z=float(tp[-1]+dt[-1]*q[-1]/(1-q[-1]))
    if z<=t[-1]:return {"status":"ESTIMATE_BEFORE_WINDOW_END","peaks":len(p),"median_ratio":med,"t_star_estimate":z}
    return {"status":"FINITE","peaks":len(p),"median_ratio":med,"period":float(-2*np.log(med)),"t_star_estimate":z}
def clean_controls():
    rng=np.random.default_rng(C["fresh_seed"]);rows=[]
    for sub in ("positive","stationary"):
        for i in range(C["positive_n"] if sub=="positive" else C["stationary_n"]):
            period=float(rng.uniform(*C["period_range"]));cycles=C["cycles"];n=cycles*C["points_per_cycle"]+1
            u=np.linspace(0,1,n);phase=rng.uniform(0,2*np.pi);s=u*cycles*period
            gap=float(np.exp(-s[-1]));star=0. if i%2==0 else .5*gap
            if sub=="positive":
                t=star-np.exp(-s);beta=float(rng.uniform(.6,1.4));v=np.exp(beta*(s-s[-1]))*np.sin(2*np.pi*cycles*u+phase)
            else:t=u.copy();v=np.sin(2*np.pi*cycles*u+phase)
            for window in ("prefix","full"):
                m=int(C["training_fraction"]*n) if window=="prefix" else n
                a=geometric(t[:m],v[:m]);r={"subtype":sub,"i":i,"window":window,"true_star":star if sub=="positive" else None,"true_period":period if sub=="positive" else None,**a}
                if sub=="positive" and a["status"]=="FINITE":
                    # Compare at end of supplied window, and at end of whole trace.
                    est=a["t_star_estimate"];r["relative_gap_error_at_window_end"]=abs(est-star)/(star-t[m-1]);r["relative_gap_error_at_full_end"]=abs(est-star)/(star-t[-1]);r["relative_period_error"]=abs(a["period"]-period)/period
                r["correct"]=bool(a["status"]=="FINITE" and r["relative_gap_error_at_window_end"]<=C["gates"]["relative_gap_error_max"] and r["relative_period_error"]<=C["gates"]["period_error_max"]) if sub=="positive" else a["status"]!="FINITE"
                rows.append(r)
    summary=[]
    for window in ("prefix","full"):
        for sub in ("positive","stationary"):
            rr=[r for r in rows if r["window"]==window and r["subtype"]==sub]
            q=[r["relative_gap_error_at_full_end"] for r in rr if "relative_gap_error_at_full_end" in r]
            summary.append({"window":window,"subtype":sub,"n":len(rr),"finite":sum(r["status"]=="FINITE" for r in rr),"correct":sum(r["correct"] for r in rr),"median_full_end_relative_gap_error":float(np.median(q)) if q else None,"true_zero_star_correct":sum(r["correct"] and r["true_star"]==0 for r in rr)})
    return {"summary":summary,"rows":rows,"note":"Prefix success at its own end is not proof of accurate extrapolation to full trace; full-window diagnostic uses later data."}
def envelope_audit():
    rows=[]
    for c in cases(cfg):
        if c["subtype"]!="positive" or c["level"]!=0 or c["kind"]!="iid":continue
        s,t,v,e=c["s"],c["t"],c["raw"],c["envelope"];m=int(.55*len(v))
        q=envelope_only(s,v);pp=extrema(s[:m],v[:m])
        for method in ("rms","peaks"):
            if method=="rms": le=q[2]["logenv"] if q else None
            else:
                if len(pp)<3:le=None
                else:
                    ii=[x[2] for x in pp];aa=np.array([x[1] for x in pp]);beta,b=np.polyfit(s[ii],np.log(aa),1);le=b+beta*s
            if le is None:
                rows.append({"method":method,"i":c["i"],"status":"FIT_FAIL","correct":False});continue
            diff=le-np.log(e);diff-=np.mean(diff[:m]);rmse=float(np.sqrt(np.mean(diff[m:]**2)))
            y=v/np.exp(le);pred,*_=rivals.detect(s,t,y);label="REJECT";ci=None
            if pred is not None:
                ci=phase_ci(s,y,s[-1]/pred);label="DSS" if ci["equivalent"] else "AMBIGUOUS"
            rows.append({"method":method,"i":c["i"],"status":label,"heldout_log_envelope_rmse":rmse,"correct":bool(label=="DSS" and abs(pred-c["truth_period"])/c["truth_period"]<=.05)})
        if len(rows)==200:break
    summary=[]
    for method in ("rms","peaks"):
        a=[r for r in rows if r["method"]==method];e=[r["heldout_log_envelope_rmse"] for r in a if "heldout_log_envelope_rmse" in r]
        summary.append({"method":method,"n":len(a),"correct":sum(r["correct"] for r in a),"median_heldout_log_envelope_rmse":float(np.median(e)) if e else None,"ambiguous":sum(r["status"]=="AMBIGUOUS" for r in a),"reject":sum(r["status"]=="REJECT" for r in a)})
    return {"summary":summary,"rows":rows,"oracle_time":True}
def pit_audit():
    rows=[]
    for c in cases(cfg):
        if c["subtype"]!="positive" or c["level"]==0:continue
        s,t,y=c["s"],c["t"],c["raw"]/c["envelope"];m=int(.55*len(y))
        u=s/s[-1];tt=(t-t[0])/(t[-1]-t[0]);q,w=rivals.fit(u,tt,y[:m],"DSS")
        ci=phase_ci(s,y,float(q[0]));se=ci["se"]
        pit=float(ndtr(-ci["drift"]/se)) if se>0 else None
        rows.append({"kind":c["kind"],"level":c["level"],"i":c["i"],"PIT":pit,"coverage":ci["ci95"][0]<=0<=ci["ci95"][1],"fit_success":ci["fit_success"],"drift":ci["drift"],"se":se})
        if len(rows)==600:break
    summary=[]
    for k,l in sorted({(r["kind"],r["level"]) for r in rows}):
        a=[r for r in rows if r["kind"]==k and r["level"]==l];v=[r["PIT"] for r in a if r["PIT"] is not None]
        counts,_=np.histogram(v,bins=np.linspace(0,1,11))
        summary.append({"kind":k,"level":l,"n":len(a),"coverage":sum(r["coverage"] for r in a),"fit_success":sum(r["fit_success"] for r in a),"pit_histogram":counts.tolist(),"pit_n":len(v),"median_signed_drift":float(np.median([r["drift"] for r in a]))})
    return {"summary":summary,"rows":rows,"screened":False,"oracle_time_envelope":True,"PIT_interpretation":"Gaussian confidence-distribution diagnostic under fixed zero drift; not posterior predictive PIT or coverage proof."}
result={"geometry":clean_controls,"envelope":envelope_audit,"pit":pit_audit}[mode]()
rows=result.pop("rows");result.update({"mode":mode,"scientific_hold":True,"physical_use_authorized":False,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest()})
for name,data in (("result.json",result),("trials.json",rows)):(OUT/name).write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")
print("R4B5_CONTROL_RESULT",json.dumps(result,allow_nan=False),flush=True)
