"""Paired nuisance-information ablation. Frozen R4B3 decision, no tuning."""
import ast,hashlib,json,sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/"r4b3"),str(HERE.parent/"r4b2")]
from generator import cases
import rivals
P=json.loads((HERE/"protocol.json").read_text());G=P["generator"]
cfg={**G,"new_seed":G["seed"]}
OUT=Path("r4b4-output");OUT.mkdir(exist_ok=True)
mode=sys.argv[1];assert mode in ("clean","A","B","C","D")
# Extract original functions without executing the R4B3 experiment.
source=HERE.parent/"r4b3"/"phase.py"
tree=ast.parse(source.read_text())
env={"np":np,"least_squares":least_squares}
nodes=[x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in ("normalize_blind","phase_ci")]
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),"exec"),env)
blind=env["normalize_blind"];phase_ci=env["phase_ci"]
def write(n,d): (OUT/n).write_text(json.dumps(d,indent=2,allow_nan=False)+"\n")
def time_only(t,y):
    n=len(t);m=int(.55*n);span=t[-1]-t[0];d=(t[-1]-t)/span;best=None
    for lg in np.linspace(-45,-1,29):
        gap=np.exp(lg);s=-np.log((d+gap)/(1+gap));u=s/s[-1]
        coord=u[:m];z=np.interp(np.linspace(coord[0],coord[-1],512),coord,y[:m])
        freq=np.fft.rfftfreq(2048,d=(coord[-1]-coord[0])/511)
        amp=abs(np.fft.rfft((z-z.mean())*np.hanning(len(z)),n=2048))
        good=(freq>.3)&(freq<45)
        if not good.any():continue
        f=float(freq[np.flatnonzero(good)[np.argmax(amp[good])]])
        b=np.column_stack((np.ones(m),np.sin(2*np.pi*f*coord),np.cos(2*np.pi*f*coord)))
        r=y[:m]-b@np.linalg.lstsq(b,y[:m],rcond=None)[0]
        loss=float(np.mean(r*r)/max(np.mean(y[:m]**2),1e-20))
        if best is None or loss<best[0]:best=(loss,s,lg)
    if best is None:return None
    _,s,lg=best
    return s,y,{"log_gap_estimate":float(lg)}
def envelope_only(s,v):
    m=int(.55*len(v));idx=np.array_split(np.arange(m),12)
    a=np.array([np.sqrt(np.mean(v[z]**2)) for z in idx]);x=np.array([np.mean(s[z]) for z in idx])
    if min(a)<=0:return None
    beta,b=np.polyfit(x,np.log(a),1)
    if not (.1<=beta<=3):return None
    logenv=np.clip(b+beta*s,-650,650);y=v/np.exp(logenv)
    return s,y,{"envelope_exponent_estimate":float(beta),"logenv":logenv}
def classify(c,md):
    t=c["t"];v=c["raw"];s0=c["s"];e=c["envelope"];n=len(t)
    if md=="A":q=(s0,v/e,{})
    elif md=="B":q=time_only(t,v/e)
    elif md=="C":q=envelope_only(s0,v)
    else:q=blind(t,v)
    label="AMBIGUOUS";stage="nuisance_failure";pred=None;ci=None;nu={};screen=None
    if q is not None:
        s,y,nu=q
        if np.isfinite(y).all() and max(abs(y))<1e100:
            # Save independently scored nuisance quantities, never supply truth to detector.
            if "log_gap_estimate" in nu:
                true_gap=(c["star"]-t[-1])/(t[-1]-t[0])
                nu["true_log_gap"]=float(np.log(true_gap))
                nu["log_gap_error"]=float(nu["log_gap_estimate"]-nu["true_log_gap"])
            if md=="C":le=nu.pop("logenv")
            elif md=="D":
                # Reconstruct envelope estimate up to an irrelevant constant.
                le=nu["envelope_exponent_estimate"]*s
            else:le=np.log(e)
            z=le-np.log(e);nu["envelope_log_rmse_gain_removed"]=float(np.sqrt(np.mean((z-z.mean())**2)))
            pred,scores,_,_=rivals.detect(s,t,y)
            screen={name:{"validation_nrmse":x["validation_nrmse"],"test_nrmse":x["test_nrmse"]} for name,x in scores.items()}
            if pred is None:label="REJECT";stage="rival_screen_rejection"
            else:
                ci=phase_ci(s,y,s[-1]/pred);stage="phase_ambiguous"
                if ci["equivalent"]:label="DSS";stage="DSS"
    truth=c["truth_period"];err=abs(pred-truth)/truth if pred is not None and truth is not None else None
    correct=bool(label=="DSS" and err is not None and err<=.05) if truth is not None else label!="DSS"
    return {"subtype":c["subtype"],"i":c["i"],"kind":c["kind"],"level":c["level"],"truth_period":truth,"label":label,"stage":stage,"correct":correct,"pred":pred,"relative_error":err,"nuisance":nu,"screen":screen,"phase":ci,"input_sha256":hashlib.sha256(np.asarray(np.column_stack((t,v)),dtype="<f8").tobytes()).hexdigest()}
rows=[]
for c in cases(cfg):
    if c["level"]==0 and c["kind"]!="iid":continue
    if mode=="clean" and (c["subtype"]!="positive" or c["level"]!=0):continue
    rows.append(classify(c,"D" if mode=="clean" else mode))
    if len(rows)%600==0:print("PROGRESS",mode,len(rows),flush=True);write("partial_trials.json",rows)
    if mode=="clean" and len(rows)==G["clean_unique_positive_count"]:break
summary=[]
for k,l,sub in sorted({(r["kind"],r["level"],r["subtype"]) for r in rows}):
    a=[r for r in rows if (r["kind"],r["level"],r["subtype"])==(k,l,sub)]
    def med(key):
        x=[r["nuisance"][key] for r in a if key in r["nuisance"]]
        return float(np.median(np.abs(x))) if x else None
    ci=[r["phase"] for r in a if r["phase"] is not None]
    summary.append({"kind":k,"level":l,"subtype":sub,"n":len(a),"DSS":sum(r["label"]=="DSS" for r in a),"AMBIGUOUS":sum(r["label"]=="AMBIGUOUS" for r in a),"REJECT":sum(r["label"]=="REJECT" for r in a),"correct":sum(r["correct"] for r in a),"nuisance_failure":sum(r["stage"]=="nuisance_failure" for r in a),"rival_screen_rejection":sum(r["stage"]=="rival_screen_rejection" for r in a),"phase_ambiguous":sum(r["stage"]=="phase_ambiguous" for r in a),"median_abs_log_gap_error":med("log_gap_error"),"median_envelope_log_rmse":med("envelope_log_rmse_gain_removed"),"phase_intervals_n":len(ci),"phase_intervals_containing_zero":sum(r["ci95"][0]<=0<=r["ci95"][1] for r in ci) if sub=="positive" else None})
gate=all(r["correct"]>=90 and r["AMBIGUOUS"]<=5 if r["subtype"]=="positive" else r["DSS"]<=5 for r in summary)
result={"mode":mode,"summary":summary,"gate":gate,"n":len(rows),"ordered_input_hashes_sha256":hashlib.sha256("".join(r["input_sha256"] for r in rows).encode()).hexdigest(),"generator_sha256":hashlib.sha256((HERE.parent/"r4b3"/"generator.py").read_bytes()).hexdigest(),"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"frozen_decision":True,"confidence_coverage_validated":False,"scientific_hold":True,"physical_use_authorized":False,"production_changed":False}
write("trials.json",rows);write("result.json",result);print("R4B4_RESULT",json.dumps(result,allow_nan=False),flush=True)
