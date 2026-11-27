"""Observed-residual routing and disjoint conditional calibration; synthetic only."""
import sys,ast,json,hashlib,time
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"r4b9"))
import common as parent
from common import model,score,sequence,candidates,explicit_bank,mask,bank,rivals,phase
P=json.loads((HERE/"protocol.json").read_text());B=P["bank"];SHA=hashlib.sha256((HERE/"protocol.json").read_bytes()).hexdigest()
OUT=Path("r4b10-output");OUT.mkdir(exist_ok=True)
def write(name,obj): (OUT/name).write_text(json.dumps(obj,allow_nan=False,separators=(",",":"))+"\n")
def read(path):return json.loads(Path(path).read_text())
def result(mode,rows,summary,**kw):
    write("trials.json",rows);q=dict(mode=mode,n=len(rows),summary=summary,protocol_sha256=SHA,scientific_hold=True,physical_use_authorized=False,**kw);write("result.json",q);print("R4B10_RESULT",json.dumps(q,allow_nan=False),flush=True)
def load(names):
    path=HERE.parent/"r4b9"/"calibrate.py";nodes=[x for x in ast.parse(path.read_text()).body if isinstance(x,ast.FunctionDef) and x.name in names]
    env={"np":np,"least_squares":least_squares,"rivals":rivals,"phase":phase}
    from scipy.special import ndtr
    env["ndtr"]=ndtr;exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),"exec"),env);return env
helpers=load({"profile_model","old_diagnostics"});profile_model=helpers["profile_model"];old_diagnostics=helpers["old_diagnostics"]
KINDS=B["noise_types"];KNOWN=KINDS[:3]
def examples(seed,kind):
    # Truth is used only for synthetic construction/scoring. All routes see t,v only.
    cfg={"classes":B["classes"],"n_per_class":B["n_per_class"]}
    for c in explicit_bank(cfg,kind if kind in KNOWN else "narrowband",seed):
        z=c["noise"]
        if kind in ("tangent","orthogonal"):
            u=c["u"];a=c["angle"];Q,_=np.linalg.qr(np.column_stack((np.ones(len(u)),np.sin(a),np.cos(a),2*np.pi*u*np.cos(a))))
            w=np.pi*u*u*np.cos(a);w-=Q@(Q.T@w);w/=np.linalg.norm(w);tangent=w*np.dot(w,z)
            z=tangent if kind=="tangent" else z-tangent
        for level in B["noise_levels"]:
            for missing in B["missing"]:
                keep=mask(c,missing);t=c["t"][keep];v=(c["env"]*(c["base"]+level*z))[keep]
                yield c,keep,level,missing,t,v
def fit(t,v,c):
    fits,_=candidates(t,v,c["sub"],c["i"]);return min(fits,key=lambda x:x["rmse"])
def features(t,v,a):
    q=a["q"];d=(t[-1]-t)/(t[-1]-t[0]);s=np.log1p((1-d)/(d+np.exp(q[0])));u=s/s[-1]
    y=v/np.exp(np.clip(q[2]*(s-s[-1]),-700,0));y/=max(np.sqrt(np.mean(y*y)),1e-30)
    M=np.column_stack((np.ones(len(u)),np.sin(2*np.pi*q[1]*u),np.cos(2*np.pi*q[1]*u)));r=y-M@np.linalg.lstsq(M,y,rcond=None)[0]
    rms=max(float(np.sqrt(np.mean(r*r))),1e-15);z=r-r.mean()
    ac=[float(np.dot(z[:-lag],z[lag:])/max(np.dot(z,z),1e-30)) for lag in (1,4,16)]
    ps=abs(np.fft.rfft(z*np.hanning(len(z))))[1:]**2;ps/=max(float(ps.sum()),1e-30)
    ent=float(-np.sum(ps*np.log(np.maximum(ps,1e-30)))/np.log(len(ps)))
    return ac+[float(ps.max()),ent,float(np.log(rms)),float(np.log(len(r)))]
def train(rows):
    X=np.asarray([r["features"] for r in rows]);mu=X.mean(0);sd=np.maximum(X.std(0),1e-9);z=(X-mu)/sd
    centers={};radius={}
    for kind in KNOWN:
        a=z[[r["kind"]==kind for r in rows]];c=a.mean(0);centers[kind]=c.tolist();radius[kind]=float(np.quantile(np.linalg.norm(a-c,axis=1),.95))
    return dict(protocol_sha256=SHA,seed=B["router_train_seed"],mean=mu.tolist(),sd=sd.tolist(),centers=centers,radius=radius)
def route(f,r):
    z=(np.asarray(f)-r["mean"])/np.asarray(r["sd"]);dist=sorted((float(np.linalg.norm(z-c)),k) for k,c in r["centers"].items())
    d,k=dist[0];ratio=d/max(dist[1][0],1e-12)
    return (k if d<=r["radius"][k] and ratio<=.8 else "unknown"),d,ratio
def q95(rows):
    values=sorted(r["true_score"] for r in rows if r["true_score"] is not None);k=int(np.ceil((len(rows)+1)*.95))
    return values[k-1] if k<=len(values) and k>0 else None
def maximum(q):return None if not q or any(x is None for x in q) else max(q)
def groups(rows,keys):
    out={}
    for r in rows:out.setdefault(tuple(r[k] for k in keys),[]).append(r)
    return out
def thresholds(rows):
    strata=["kind","sub","noise","missing"]
    true_groups=groups(rows,strata);global_q=maximum([q95(a) for a in true_groups.values()])
    oracle={k:maximum([q95(a) for key,a in true_groups.items() if key[0]==k]) for k in KINDS}
    routes={}
    for name in KNOWN+["unknown"]:
        rg=groups([r for r in rows if r["route"]==name],strata)
        dense=[q95(a) for a in rg.values() if len(a)>=20]
        sparse=any(len(a)<20 for a in rg.values())
        routes[name]=global_q if name=="unknown" or sparse or not dense else maximum(dense)
    return dict(protocol_sha256=SHA,seed=B["calibration_seed"],global_threshold=global_q,routes=routes,oracle=oracle,strata=[dict(zip(strata,k),n=len(a),q=q95(a)) for k,a in true_groups.items()],route_cells=[dict(zip(["route"]+strata,k),n=len(a),q=q95(a) if len(a)>=20 else None) for k,a in groups(rows,["route"]+strata).items()])
mode=sys.argv[1]
if mode=="fit-router":
    rows=[]
    for kind in KNOWN:
        for c,keep,l,m,t,v in examples(B["router_train_seed"],kind):
            a=fit(t,v,c);rows.append(dict(kind=kind,sub=c["sub"],i=c["i"],noise=l,missing=m,features=features(t,v,a)))
        print("ROUTER_TRAIN",kind,len(rows),flush=True)
    r=train(rows);write("router.json",r);result(mode,rows,[],router=r);sys.exit(0)
if mode=="freeze":
    root=Path(sys.argv[2]);rows=[]
    for f in sorted(root.rglob("calibration_rows.json")):
        a=read(f);assert a["protocol_sha256"]==SHA and a["seed"]==B["calibration_seed"];rows.extend(a["rows"])
    assert len(rows)==len(KINDS)*2*B["n_per_class"]*len(B["noise_levels"])*len(B["missing"])
    q=thresholds(rows);write("thresholds.json",q);result(mode,[],[],thresholds=q);sys.exit(0)
if mode=="forecast":
    kind=sys.argv[2];C=P["forecast"];rows=[]
    for sub,i,l,m,t,v,truth,period in bank(C,kind):
        for f in C["fractions"]:
            n=int(f*len(t));tt=t[:n];vv=v[:n];sd,geo,pre,solve,_,_=model(tt,vv)
            for name in C["compare"]:
                start=time.process_time()
                if name=="legacy_single":q,status=geo()
                else:
                    lg,status=sequence(tt,vv);q=sd(lg) if lg is not None else None
                a=solve(q) if q is not None else None
                rows.append(dict(i=i,noise=l,missing=m,fraction=f,method=name,status=status,cpu_seconds=time.process_time()-start,**score(a,truth,tt,period,t[-1])))
    summary=[dict(zip(["noise","missing","fraction","method"],k),n=len(a),available=sum(r["status"]=="FINITE" for r in a),local_correct=sum(r["local_correct"] for r in a),final_correct=sum(r["final_correct"] for r in a),median_estimator_cpu_seconds=float(np.median([r["cpu_seconds"] for r in a]))) for k,a in groups(rows,["noise","missing","fraction","method"]).items()]
    result(mode,rows,summary,kind=kind,note="Estimator CPU only; fractions are sample counts, not physical solver CPU fractions.");sys.exit(0)
kind=sys.argv[2];router=read(sys.argv[3]);assert router["protocol_sha256"]==SHA and router["seed"]==B["router_train_seed"]
split=B[{"router-exam":"router_exam_seed","calibrate":"calibration_seed","evaluate":"evaluation_seed"}[mode]]
frozen=read(sys.argv[4]) if mode=="evaluate" else None
if frozen is not None:assert frozen["protocol_sha256"]==SHA and frozen["seed"]==B["calibration_seed"]
rows=[]
for c,keep,l,m,t,v in examples(split,kind):
    if mode=="calibrate" and c["star"] is None:continue
    a=fit(t,v,c);f=features(t,v,a);rt,dist,ratio=route(f,router)
    r=dict(kind=kind,sub=c["sub"],i=c["i"],noise=l,missing=m,route=rt,distance=dist,ratio=ratio,features=f,input_sha256=hashlib.sha256(np.asarray(np.column_stack((t,v)),dtype="<f8").tobytes()).hexdigest())
    if mode!="router-exam":
        est,ok,pr=profile_model(t,v,a);true=pr(c["drift"]) if c["star"] is not None else None
        r.update(true_score=true,estimate=est,profile_fit_success=ok,correct_params=score(a,c["star"],t,c["period"])["local_correct"])
        if mode=="evaluate":
            old=old_diagnostics(t,v,a,c,keep);r["old_label"]=old["label"];grid=parent.P["calibration"]["grid"];scores=[pr(x) for x in grid];r["grid_complete"]=all(x is not None for x in scores)
            for name,threshold in (("global",frozen["global_threshold"]),("conditional",frozen["routes"][rt]),("oracle_noise_diagnostic",frozen["oracle"][kind])):
                admitted=[x for x,z in zip(grid,scores) if threshold is not None and z is not None and z<=threshold]
                label="REJECT" if old["stage"]=="RIVAL_REJECT" else ("DSS" if old["screen"] and ok and r["grid_complete"] and admitted and abs(est)<.012 and all(abs(x)<.012 for x in admitted) else "AMBIGUOUS")
                r[name]=dict(label=label,truth_included=bool(true is not None and (threshold is None or true<=threshold)) if c["star"] is not None else None,threshold=threshold)
    rows.append(r)
    if len(rows)%180==0:print("PROGRESS",mode,kind,len(rows),flush=True)
summary=[]
for key,a in groups(rows,["sub","noise","missing"]).items():
    item=dict(zip(["sub","noise","missing"],key),n=len(a),routes={x:sum(r["route"]==x for r in a) for x in KNOWN+["unknown"]})
    if mode=="evaluate":
        item["correct_params"]=sum(r["correct_params"] for r in a)
        for name in ("global","conditional","oracle_noise_diagnostic"):
            item[name]=dict(DSS=sum(r[name]["label"]=="DSS" for r in a),correct_DSS=sum(r[name]["label"]=="DSS" and r["correct_params"] for r in a),AMBIGUOUS=sum(r[name]["label"]=="AMBIGUOUS" for r in a),REJECT=sum(r[name]["label"]=="REJECT" for r in a),truth_included=sum(r[name]["truth_included"] is True for r in a) if key[0]!="stationary" else None)
        item["grid_failures"]=sum(not r["grid_complete"] for r in a)
    summary.append(item)
if mode=="calibrate":write("calibration_rows.json",dict(protocol_sha256=SHA,seed=split,rows=[{k:r[k] for k in ("kind","sub","noise","missing","route","true_score")} for r in rows]))
result(mode,rows,summary,kind=kind,seed=split,limitations=["Noise labels unavailable at inference; oracle route is diagnostic only.","Sparse intersections trigger global fallback; no guaranteed conditional coverage under unseen noise laws.","Finite grid not continuous confidence certificate; tangent noise has synthetic oracle construction only."])
