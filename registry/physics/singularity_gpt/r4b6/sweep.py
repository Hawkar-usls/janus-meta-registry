"""Paired noise/missingness degradation of frozen geometry and blind joint estimator."""
import ast,json,hashlib,sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE.parent/"r4b2"),str(HERE.parent/"r4b3")]
import rivals
from generator import ar
P=json.loads((HERE/"protocol.json").read_text());S=P["sweep"]
OUT=Path("r4b6-output");OUT.mkdir(exist_ok=True)
def load(path,names,env):
    nodes=[x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),"exec"),env)
    return env
g=load(HERE.parent/"r4b5"/"controls.py",{"extrema","geometric"},{"np":np});extrema=g["extrema"];geometry=g["geometric"]
phase=load(HERE.parent/"r4b3"/"phase.py",{"phase_ci"},{"np":np,"least_squares":least_squares})["phase_ci"]
kind=sys.argv[1];assert kind in S["noise_types"]
rng=np.random.default_rng(S["seed"]);rows=[]
def geom_metrics(t,v,star,period,window):
    n=len(t);m=int(.55*n) if window=="prefix" else n
    a=geometry(t[:m],v[:m]);a["window"]=window
    if a["status"]=="FINITE" and star is not None:
        e=abs(a["t_star_estimate"]-star)
        a["local_gap_error"]=float(e/(star-t[m-1]));a["final_gap_error"]=float(e/(star-t[-1]))
        a["period_error"]=float(abs(a["period"]-period)/period)
        a["correct"]=bool(a["local_gap_error"]<=.05 and a["period_error"]<=.05)
        a["predictive_correct"]=bool(a["final_gap_error"]<=.05 and a["period_error"]<=.05)
    else:a["correct"]=False;a["predictive_correct"]=False
    return a
def joint(t,v,a,period):
    if a["status"]!="FINITE":return {"label":"REJECT","stage":"geometry"}
    z=a["t_star_estimate"]
    if z<=t[-1]:return {"label":"REJECT","stage":"extrapolated_star_before_end"}
    s=-np.log((z-t)/(z-t[0]));m=int(.55*len(t))
    pp=extrema(s[:m],v[:m])
    if len(pp)<3:return {"label":"REJECT","stage":"envelope"}
    ii=[p[2] for p in pp];aa=np.array([p[1] for p in pp])
    beta,b=np.polyfit(s[ii],np.log(aa),1)
    if not np.isfinite(beta) or not (.1<=beta<=3):return {"label":"REJECT","stage":"envelope"}
    y=v/np.exp(np.clip(b+beta*s,-650,650))
    if not np.isfinite(y).all() or max(abs(y))>1e100:return {"label":"REJECT","stage":"envelope"}
    pred,*_=rivals.detect(s,t,y)
    if pred is None:return {"label":"REJECT","stage":"rival_screen"}
    ci=phase(s,y,s[-1]/pred)
    label="DSS" if ci["equivalent"] else "AMBIGUOUS"
    return {"label":label,"stage":"phase","period":pred,"period_error":float(abs(pred-period)/period) if period else None,"beta":float(beta)}
for sub in S["classes"]:
    for i in range(S["n_per_class"]):
        period=float(rng.uniform(*S["period_range"]));cycles=S["cycles"];n=cycles*S["points_per_cycle"]+1
        u=np.linspace(0,1,n);s=u*cycles*period;ph=rng.uniform(0,2*np.pi);beta=float(rng.uniform(*S["envelope_exponent_range"]))
        drift=float(rng.uniform(*S["chirp_range"]))*rng.choice([-1,1])
        star=0. if i%2==0 else .5*np.exp(-s[-1])
        env=np.exp(beta*(s-s[-1]));t=star-np.exp(-s)
        if sub=="stationary":t=u.copy();env=np.ones(n);base=np.sin(2*np.pi*cycles*u+ph);truth=None
        elif sub=="near_dss_chirp":base=np.sin(2*np.pi*(cycles*u+.5*drift*u*u)+ph);truth=star
        else:base=np.sin(2*np.pi*cycles*u+ph);truth=star
        iid=rng.standard_normal(n);long=.7*ar(rng,n,.98)+.3*ar(rng,n,.85)
        narrow=np.sin(2*np.pi*(cycles+rng.choice([-1,1])*rng.uniform(.2,3))*u+rng.uniform(0,2*np.pi))+.25*iid
        maskdraw=rng.uniform(size=n);z={"iid":iid,"long_memory":long,"narrowband":narrow}[kind];z=z/max(np.std(z),1e-30)
        for level in S["noise_levels"]:
            if level==0 and kind!="iid":continue
            v=env*(base+level*z)
            for missing in S["missing"]:
                keep=maskdraw>=missing;keep[0]=keep[-1]=True;tt=t[keep];vv=v[keep]
                a=geom_metrics(tt,vv,truth,period,"prefix");b=geom_metrics(tt,vv,truth,period,"full")
                r={"subtype":sub,"i":i,"kind":kind,"noise":level,"missing":missing,"n":len(tt),"prefix":a,"full":b,"sha256":hashlib.sha256(np.asarray(np.column_stack((tt,vv)),dtype="<f8").tobytes()).hexdigest()}
                if level in (0,.001,.01) and missing in (0,.3):
                    r["joint"]=joint(tt,vv,a,period if sub=="positive" else None)
                rows.append(r)
    print("SUBTYPE_DONE",kind,sub,len(rows),flush=True)
summary=[]
for sub,level,missing in sorted({(r["subtype"],r["noise"],r["missing"]) for r in rows}):
    rr=[r for r in rows if (r["subtype"],r["noise"],r["missing"])==(sub,level,missing)]
    item={"subtype":sub,"noise":level,"missing":missing,"n":len(rr)}
    for w in ("prefix","full"):
        a=[r[w] for r in rr];e=[q["final_gap_error"] for q in a if "final_gap_error" in q]
        item[w]={"finite":sum(q["status"]=="FINITE" for q in a),"correct":sum(q["correct"] for q in a),"predictive_correct":sum(q["predictive_correct"] for q in a),"median_final_gap_error":float(np.median(e)) if e else None,"p95_final_gap_error":float(np.quantile(e,.95)) if e else None}
    if "joint" in rr[0]:
        a=[r["joint"] for r in rr];item["joint"]={"DSS":sum(q["label"]=="DSS" for q in a),"AMBIGUOUS":sum(q["label"]=="AMBIGUOUS" for q in a),"REJECT":sum(q["label"]=="REJECT" for q in a),"correct_positive":sum(q["label"]=="DSS" and q.get("period_error") is not None and q["period_error"]<=.05 for q in a),"stages":{s:sum(q["stage"]==s for q in a) for s in sorted({q["stage"] for q in a})}}
    summary.append(item)
result={"mode":"sweep","kind":kind,"summary":summary,"n":len(rows),"scientific_hold":True,"physical_use_authorized":False,"protocol_sha256":hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest(),"limitations":["Same idealized exponential envelope and log sampling before deletions; missingness random not clustered.","Geometry full uses full trace; prefix predictive metric compares estimated star against final gap, not just prefix gap.","Joint classifier uses prefix geometry and envelope, but frozen phase CI fits full signal after screen; no validated uncertainty." ]}
for name,data in (("trials.json",rows),("result.json",result)):(OUT/name).write_text(json.dumps(data,indent=2,allow_nan=False)+"\n")
print("R4B6_RESULT",json.dumps(result,allow_nan=False),flush=True)
