"""Separate preregistered R4B8A diagnostic, never mutate R4B8."""
import ast,hashlib,json,sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from scipy.ndimage import median_filter
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/x) for x in ("r4b2","r4b3","r4b7")]
import rivals
from bank import bank
P=json.loads((HERE/"protocol.json").read_text())
OUT=Path("r4b8a-output");OUT.mkdir(exist_ok=True)
def load(path,names,env):
    nodes=[x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),"exec"),env);return env
g=load(HERE.parent/"r4b5"/"controls.py",{"extrema","geometric"},{"np":np})
phase=load(HERE.parent/"r4b3"/"phase.py",{"phase_ci"},{"np":np,"least_squares":least_squares})["phase_ci"]
old=load(HERE.parent/"r4b8"/"examine.py",{"model","score"},{"np":np,"g":g,"rivals":rivals,"phase":phase,"least_squares":least_squares})
model,score=old["model"],old["score"]
def sequence(t,v):
    # Fixed median filtering is in sample-index space, not oracle log-time.
    peaks=g["extrema"](t,median_filter(v,size=5,mode="nearest"))
    if len(peaks)<5:return None,"INSUFFICIENT_PEAKS"
    tp=np.array([x[0] for x in peaks]);dt=np.diff(tp)
    if np.any(dt<=0):return None,"NONPOSITIVE_INTERVAL"
    k=np.arange(len(dt));y=np.log(dt/dt[0])
    b0=np.polyfit(k,y,1)
    opt=least_squares(lambda b:b[0]+b[1]*k-y,[b0[1],b0[0]],loss="soft_l1",f_scale=.05,max_nfev=80)
    q=float(np.exp(opt.x[1]))
    if not (0<q<.98):return None,"NO_RELIABLE_FINITE_ACCUMULATION"
    if np.median(abs(opt.fun))>.1:return None,"INCONSISTENT_SEQUENCE"
    # Extrapolate from each observed interval to last peak with the common ratio.
    # Use actual peak times to avoid treating a fitted intercept as exact.
    j=np.arange(len(dt));tail=dt*q**(len(dt)-j)/(1-q)
    gaps=tail+(tp[-1]-t[-1]);gap=float(np.median(gaps[-min(5,len(gaps)):]))
    if gap<=0:return None,"ESTIMATE_BEFORE_WINDOW_END"
    return float(np.log(gap/(t[-1]-t[0]))),"FINITE"
def cluster_select(c):
    # Medoid-like support count; deterministic ties by objective.
    def support(a):return sum(abs(a["q"][0]-b["q"][0])<=.1 and abs(a["period"]-b["period"])/max(a["period"],b["period"])<=.05 for b in c)
    return min(c,key=lambda a:(-support(a),a["rmse"]))
mode,kind=sys.argv[1:3];cfg=P[mode];rows=[]
for sub,i,level,missing,t,v,truth,period in bank(cfg,kind):
    seed,geo,pre,solve,classify,_=model(t,v);q,status=geo()
    if mode=="availability":
        lg,status2=sequence(t,v);a=solve(q) if q is not None else None;b=solve(seed(lg)) if lg is not None else None
        rows.append({"sub":sub,"i":i,"noise":level,"missing":missing,"legacy_status":status,"sequence_status":status2,"legacy_score":score(a,truth,t,period),"sequence_score":score(b,truth,t,period),"legacy":a,"sequence":b})
    elif mode=="forecast":
        for fraction in cfg["fractions"]:
            m=int(fraction*len(t));tt=t[:m];vv=v[:m]
            ss,gg,_,sl,_,_=model(tt,vv);q,status=gg();a=sl(q) if q is not None else None
            rows.append({"sub":sub,"i":i,"noise":level,"missing":missing,"fraction":fraction,"status":status,**score(a,truth,tt,period,t[-1])})
    else:
        rr=np.random.default_rng(np.random.SeedSequence([cfg["random_seed"],cfg["classes"].index(sub),i]))
        fixed=[solve(seed(x)) for x in rr.uniform(-45,-1,4)]
        ga=solve(q) if q is not None else None;rm=pre(q) if q is not None else None
        for threshold in cfg["thresholds"]:
            eligible=rm is not None and rm<=threshold
            c=[ga]+fixed[1:] if eligible else fixed
            any_correct=any(score(a,truth,t,period)["local_correct"] for a in c)
            for method,a in (("min_objective",min(c,key=lambda z:z["rmse"])),("consensus",cluster_select(c))):
                rows.append({"sub":sub,"i":i,"noise":level,"missing":missing,"threshold":threshold,"method":method,"geo_available":ga is not None,"geo_eligible":bool(eligible),"geo_correct":score(ga,truth,t,period)["local_correct"],"any_correct":any_correct,"selected":score(a,truth,t,period),"class":classify(a),"prefit":rm})
    if len(rows)%600==0:print("PROGRESS",mode,kind,len(rows),flush=True)
groups={}
for r in rows:
    key=(r["sub"],r["noise"],r["missing"],r.get("fraction"),r.get("threshold"),r.get("method"));groups.setdefault(key,[]).append(r)
summary=[]
for (sub,noise,missing,fraction,threshold,method),a in sorted(groups.items()):
    item={"sub":sub,"noise":noise,"missing":missing,"n":len(a)}
    if mode=="availability":
        for name in ("legacy","sequence"):
            item[name+"_available"]=sum(r[name] is not None for r in a);item[name+"_correct"]=sum(r[name+"_score"]["local_correct"] for r in a)
            item[name+"_statuses"]={s:sum(r[name+"_status"]==s for r in a) for s in sorted({r[name+"_status"] for r in a})}
    elif mode=="forecast":
        item.update({"fraction":fraction,"local_correct":sum(r["local_correct"] for r in a),"final_correct":sum(r["final_correct"] for r in a),"available":sum(r["status"]=="FINITE" for r in a)})
    else:
        item.update({"threshold":threshold,"method":method,"geo_available":sum(r["geo_available"] for r in a),"geo_eligible":sum(r["geo_eligible"] for r in a),"geo_correct_rejected":sum(r["geo_correct"] and not r["geo_eligible"] for r in a),"geo_incorrect_accepted":sum(not r["geo_correct"] and r["geo_eligible"] for r in a),"correct":sum(r["selected"]["local_correct"] for r in a),"any_correct":sum(r["any_correct"] for r in a),"wrong_given_correct_candidate":sum(r["any_correct"] and not r["selected"]["local_correct"] for r in a),"correct_DSS":sum(r["class"]["label"]=="DSS" and r["selected"]["local_correct"] for r in a),"DSS":sum(r["class"]["label"]=="DSS" for r in a),"AMBIGUOUS":sum(r["class"]["label"]=="AMBIGUOUS" for r in a),"REJECT":sum(r["class"]["label"]=="REJECT" for r in a)})
    summary.append(item)
result={"mode":mode,"kind":kind,"n":len(rows),"summary":summary,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"scientific_hold":True,"physical_use_authorized":False,"limitations":["Sequence estimator changes peak extraction and interval fit together; not a proof of cause.","Threshold sweep and cluster comparisons diagnostic only; no best threshold promoted.","No oracle tangent injection or calibrated uncertainty in this run; shared-start consensus not independent evidence."]}
for name,obj in (("trials.json",rows),("result.json",result)):(OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+"\n")
print("R4B8A_RESULT",json.dumps(result,allow_nan=False),flush=True)
