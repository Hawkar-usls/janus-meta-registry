#!/usr/bin/env python3
import hashlib,json,math,pathlib,subprocess,collections
import numpy as np
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.5B-CORRELATED-NOISE-IMMUNITY-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.5B-CORRELATED-NOISE-IMMUNITY-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());ex=p["experiment"]
def sha(b):return hashlib.sha256(b).hexdigest()
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def ah(x):return sha(np.ascontiguousarray(x).tobytes())
def git(*a):return subprocess.check_output(["git",*a],text=True).strip()
for key,b in [("parent_result","parent_result_blob"),("parent_code","parent_code_blob"),("r15_code","r15_blob")]:assert git("hash-object",p[key])==p[b]
prior=json.loads((R/p["parent_result"]).read_text());assert prior["eval_events"]==1440
src=(R/p["r15_code"]).read_text();assert src.count("\nrows=[]\n")==1
g={};exec(compile(src.split("\nrows=[]\n")[0],"<pinned R15 initialization>","exec"),g)
B=g["B"];labs=g["lab"];t=g["t"];N=len(t);groups={k:np.flatnonzero(labs==k) for k in "FRS"}
reps=[8,16];modes=["EQ","GLS","REF","FULL"];edges=[0,4,8,16,32,64,128,256]
def pulse(k,r,d):return g["pulse"](k,r,d)
def ar(rng,shape,rho):
    z=rng.normal(size=shape);x=z.copy()
    for i in range(1,shape[-1]):x[...,i]=rho*x[...,i-1]+math.sqrt(1-rho*rho)*z[...,i]
    return x
def sample(rng,reg,fam,amp=None):
    k=rng.uniform(-.14,.14);r=rng.uniform(.05,.085);d=rng.uniform(.24,.38);bg=rng.uniform(-.4,.4)
    if fam=="cal":
        q=rng.uniform(.08,.28);z=amp*pulse(k,q,q)
    elif fam=="weak_F":z=.14*pulse(k,r,d)
    elif fam=="weak_R":z=.14*pulse(k,d,r)
    elif fam=="strong_F":z=1.6*pulse(k,r,d)
    elif fam=="strong_R":z=1.6*pulse(k,d,r)
    elif fam.startswith("symmetric"):
        q=rng.uniform(.08,.28);z=(.14 if fam.endswith("weak") else 1.6)*pulse(k,q,q)
    elif fam=="noise":z=np.zeros(N)
    elif fam=="double":z=rng.uniform(.8,1.6)*pulse(rng.uniform(-.37,-.23),r,d)+rng.uniform(.8,1.6)*pulse(rng.uniform(.23,.37),d,r)
    elif fam=="clipped":z=np.minimum(1.6*pulse(k,r,d),rng.uniform(.38,.65))
    else:raise ValueError(fam)
    truth=bg+z;K=ex["background_samples"]
    if reg=="IID":sig=np.full(16,.14);gain=np.zeros(16)
    elif reg=="ALIGNED_COMMON_NO_REF":sig=np.full(16,.11);gain=np.full(16,.12)
    else:sig=rng.uniform(.065,.20,16);gain=rng.uniform(.07,.20,16)
    c=ar(rng,(1,N),.75)[0];cb=ar(rng,(1,K),.75)[0]
    obs=truth[None,:]+sig[:,None]*ar(rng,(16,N),.35)+gain[:,None]*c
    back=sig[:,None]*ar(rng,(16,K),.35)+gain[:,None]*cb
    ref=c+.18*ar(rng,(1,N),.35)[0];rb=cb+.18*ar(rng,(1,K),.35)[0]
    qualified=reg in ("HETERO_COMMON_REF","COVARIANCE_SHIFT")
    if reg=="REFERENCE_UNQUALIFIED":ref=ref+8*z
    if reg=="COVARIANCE_SHIFT":obs=obs+gain[:,None]*1.0*ar(rng,(1,N),.85)
    return obs,back,ref,rb,qualified,truth
def covariance(b):
    x=b-b.mean(1,keepdims=True);C=x@x.T/(x.shape[1]-1);return .85*C+.15*np.diag(np.diag(C))+np.eye(len(b))*1e-10
def prep(a,b,r,rb,qualified,n,mode):
    a=a[:n];b=b[:n];ref_used=qualified and mode in ("REF","FULL")
    if ref_used:
        x=rb-rb.mean();beta=(b-b.mean(1,keepdims=True))@x/max(float(x@x),1e-12)
        a=a-beta[:,None]*(r-rb.mean());b=b-beta[:,None]*x
    C=covariance(b);one=np.ones(n)
    if mode in ("GLS","FULL"):
        v=np.linalg.solve(C,one);w=v/(one@v)
    else:w=one/n
    y=w@a;bg=w@b
    assert math.isclose(float(w@one),1.,abs_tol=1e-12)
    z=bg-bg.mean();var=float(z@z/(len(z)-1))
    rho=float(np.clip((z[1:]@z[:-1])/max(z@z,1e-16),-.9,.9)) if mode=="FULL" else 0.
    return y,var,rho,w,ref_used
# Stationary AR(1) precision: endpoint terms symmetric; remove constant using same metric.
def Q(x,rho):
    q=(1+rho*rho)*x.copy();q[...,0]=x[...,0];q[...,-1]=x[...,-1]
    q[...,1:]-=rho*x[...,:-1];q[...,:-1]-=rho*x[...,1:]
    return q/(1-rho*rho)
# Precomputed quadratic forms give exact template normalization with symmetric precision.
ones=np.ones(N);s=B.sum(1);e=B[:,0]+B[:,-1];ss=(B*B).sum(1);ee=B[:,0]**2+B[:,-1]**2;adj=(B[:,1:]*B[:,:-1]).sum(1)
X=B-B.mean(1,keepdims=True);X=X/np.linalg.norm(X,axis=1,keepdims=True)
def feature(y,var,rho):
    qy=Q(y,rho);q1=Q(ones,rho);den=float(q1.sum());qy=qy-q1*(qy.sum()/den)
    if rho==0.:a=np.maximum(0,X@(y-y.mean()))/math.sqrt(max(var,1e-16))
    else:
        bq1=((1+rho*rho)*s-rho*rho*e-rho*(2*s-e))/(1-rho*rho)
        bqb=((1+rho*rho)*ss-rho*rho*ee-2*rho*adj)/(1-rho*rho)
        norm=np.sqrt(np.maximum(bqb-bq1*bq1/den,1e-16));a=np.maximum(0,B@qy)/norm/math.sqrt(max(var,1e-16))
    z={k:float(a[ix].max()) for k,ix in groups.items()};E=max(z.values());D=(z["F"]**2-z["R"]**2)/max(E,1.)
    return E,D
def cell(e):return str(int(np.searchsorted(edges,e,side="right")-1))
cal={reg:{str(n):{mode:{str(i):[] for i in range(len(edges))} for mode in modes} for n in reps} for reg in ex["regimes"]}
for reg in ex["regimes"]:
    for seed in ex["calibration_seeds"]:
        rng=np.random.default_rng(seed)
        for amp in ex["calibration_amplitudes"]:
            for _ in range(ex["calibration_per_amplitude"]):
                a,b,r,rb,ok,_=sample(rng,reg,"cal",amp)
                for n in reps:
                    for mode in modes:
                        y,v,rho,_,_=prep(a,b,r,rb,ok,n,mode);E,D=feature(y,v,rho);cal[reg][str(n)][mode][cell(E)].append(abs(D))
    print("R15B_CAL",reg,flush=True)
lock={reg:{n:{mode:{i:{"n":len(v),"threshold":float(np.quantile(v,.975,method="higher")) if len(v)>=60 else None} for i,v in cells.items()} for mode,cells in md.items()} for n,md in nn.items()} for reg,nn in cal.items()}
lockhash=dig(lock);pathlib.Path("/tmp/r15b-calibration-lock.json").write_text(json.dumps(lock,indent=2)+"\n")
print("R15B_LOCK",lockhash,flush=True)
def decide(D,th):return "ABSTAIN" if th is None else "F" if D>th else "R" if D< -th else "ABSTAIN"
def classification(y,var,rho,reg,n,mode):
    E,D=feature(y,var,rho);i=cell(E);th=lock[reg][str(n)][mode][i]["threshold"]
    return {"E":E,"D":D,"bin":i,"decision":decide(D,th),"supported":th is not None}
def old_decision(y,v,n):
    E,D=feature(y,v,0.);th=prior["calibration_lock"][str(n)][cell(E)]["threshold"]
    return decide(D,th)
rows=[];rec=[]
for reg in ex["regimes"]+ex["stress"]:
    stress=reg in ex["stress"];seeds=[ex["stress_seed"]] if stress else ex["eval_seeds"]
    for seed in seeds:
        rng=np.random.default_rng(seed)
        for fam in ex["stress_families"] if stress else ex["families"]:
            for i in range(ex["eval_per_family"]):
                a,b,r,rb,ok,truth=sample(rng,reg,fam);h=ah(a);hbg=ah(b)
                for n in reps:
                    rr={"regime":reg,"seed":seed,"family":fam,"index":i,"views":n,"source_sha256":h,"background_sha256":hbg,"modes":{}}
                    for mode in modes:
                        y,v,rho,w,used=prep(a,b,r,rb,ok,n,mode);y2,v2,rho2,w2,used2=prep(a[:,::-1],b[:,::-1],r[::-1],rb[::-1],ok,n,mode)
                        assert np.allclose(y,y2[::-1],rtol=1e-10,atol=1e-10) and np.allclose(w,w2,rtol=1e-10,atol=1e-10)
                        assert math.isclose(v,v2,rel_tol=1e-10,abs_tol=1e-12) and math.isclose(rho,rho2,abs_tol=1e-10)
                        lane="HETERO_COMMON_REF" if stress else reg;q=classification(y,v,rho,lane,n,mode);mirror=classification(y2,v2,rho2,lane,n,mode)
                        assert math.isclose(q["E"],mirror["E"],rel_tol=1e-9,abs_tol=1e-9) and math.isclose(q["D"],-mirror["D"],rel_tol=1e-9,abs_tol=1e-9)
                        assert q["bin"]==mirror["bin"] and mirror["decision"]=={"F":"R","R":"F","ABSTAIN":"ABSTAIN"}[q["decision"]]
                        rr["modes"][mode]={**q,"variance":v,"rho":rho,"weight_min":float(w.min()),"weight_max":float(w.max()),"weight_sum":float(w.sum()),"reference_used":used}
                        if mode=="EQ":rr["R15A"]=old_decision(y,v,n)
                        if mode=="EQ" and n==8 and reg=="IID" and fam in ("double","clipped"):
                            z=g["reconstruct"](y,truth);rec.append({"family":fam,"seed":seed,"index":i,"unchanged_R15":z})
                    assert ah(a)==h and ah(b)==hbg
                    rows.append(rr)
        print("R15B_EVAL",reg,seed,flush=True)
assert dig(lock)==lockhash
def summary(rs):
    out={}
    for mode in ["R15A",*modes]:
        def decision(x):return x["R15A"] if mode=="R15A" else x["modes"][mode]["decision"]
        weak=[x for x in rs if x["family"].startswith("weak_")];strong=[x for x in rs if x["family"].startswith("strong_")];null=[x for x in rs if x["family"].startswith("symmetric") or x["family"]=="noise"]
        def orient(a):return {"n":len(a),"correct":sum(decision(x)==x["family"][-1] for x in a),"wrong":sum(decision(x) not in (x["family"][-1],"ABSTAIN") for x in a)}
        out[mode]={"weak":orient(weak),"strong":orient(strong),"null":{"n":len(null),"declared":sum(decision(x)!="ABSTAIN" for x in null)},"null_by_family":{k:{"n":sum(x["family"]==k for x in null),"declared":sum(x["family"]==k and decision(x)!="ABSTAIN" for x in null)} for k in ["noise","symmetric_weak","symmetric_strong"]}}
        if mode!="R15A":out[mode].update({"unsupported":sum(not x["modes"][mode]["supported"] for x in rs),"median_variance":float(np.median([x["modes"][mode]["variance"] for x in rs]))})
    out["paired_EQ_strong_losses"]=sum(x["family"].startswith("strong_") and x["modes"]["EQ"]["decision"]==x["family"][-1] and x["modes"]["FULL"]["decision"]!=x["family"][-1] for x in rs)
    return out
def gate(s,delta):
    a=s["EQ"];b=s["FULL"];w=b["weak"];st=b["strong"];z=b["null"]
    return bool((w["correct"]-a["weak"]["correct"])/w["n"]>=delta and w["wrong"]/w["n"]<=.05 and z["declared"]/z["n"]<=.05 and st["correct"]/st["n"]>=.85 and s["paired_EQ_strong_losses"]==0)
by={};per={};gates={}
for reg in ex["regimes"]+ex["stress"]:
    by[reg]={str(n):summary([x for x in rows if x["regime"]==reg and x["views"]==n]) for n in reps}
    per[reg]={str(s):summary([x for x in rows if x["regime"]==reg and x["views"]==8 and x["seed"]==s]) for s in ([ex["stress_seed"]] if reg in ex["stress"] else ex["eval_seeds"])}
    if reg in ex["stress"]:
        q=by[reg]["8"];a=q["FULL"];gates[reg]=bool(a["null"]["declared"]/a["null"]["n"]<=.05 and a["weak"]["wrong"]/a["weak"]["n"]<=.05 and a["strong"]["correct"]/a["strong"]["n"]>=.85 and q["paired_EQ_strong_losses"]==0)
    else:gates[reg]=all(gate(s,.10 if reg=="HETERO_COMMON_REF" else -.05) for s in per[reg].values())
reco={}
for f in ("double","clipped"):
    a=[x["unchanged_R15"] for x in rec if x["family"]==f];n=float(np.median([x["selected_rmse"] for x in a]));l=float(np.median([x["hidden_rmse"]["linear"] for x in a]));o=float(np.median([x["old_rmse"] for x in a]))
    reco[f]={"n":len(a),"R15_median":n,"linear_median":l,"R14_median":o,"gate":n<=l and n<=o}
gates["double_reconstruction"]=reco["double"]["gate"]
# Exact observational nonidentifiability with equal spatial loading; identical bytes.
z=pulse(.0,.08,.32);obs=np.tile(z,(8,1));x=np.zeros_like(obs)
assert np.array_equal(obs+x,x+obs)
identity={"signal_plus_noise_sha256":ah(obs+x),"noise_plus_signal_sha256":ah(x+obs),"stories":["all common waveform is signal","all common waveform is noise"],"same_observables":True,"identifiable_without_external_information":False}
axes=json.loads((R/"data/JANUS-DEEP-ANALYSIS-5D-SPIRAL-ORIGIN-PRIME-ORACLE-PROTOCOL-2026-08-21-v2.1.json").read_text())["five_dimensions"]
state={"known":["R15A correlated noise remains blocker"],"alternatives":["ordinary causal","common cause","instrument","leakage","hypothetical carrier"],"gaps":["real radio","calibrated carrier","paired UAP"]};turns=[]
for name,delta in [("D1_CALIBRATION",[lockhash]),("D2_MIRROR",[f"mirrors {len(rows)*len(modes)}"]),("D3_COVARIANCE",[f"{k} gate {v}" for k,v in gates.items()]),("D4_RECONSTRUCTION",["R15 selector unchanged","common aligned noise nonidentifiable without independent information"]),("D5_PROVENANCE",["source pins checked","synthetic offband qualification only","no physical carrier evidence"])]:
    h=dig(state);state={**state,"known":sorted(set(state["known"])|set(delta))};q=dig(state);turns.append({"anchor":name,"axes":axes,"parent":h,"state":q,"delta":delta,"status":"ORIGIN_PRIME" if h!=q else "NO_INFORMATION_GAIN"})
out={"schema":"janus.uap_tachyon.correlated_noise_immunity.result.v1","status":("SYNTHETIC_GATES_PASS" if all(gates.values()) else "PARTIAL_ENGINEERING_HOLD")+"__PHYSICAL_CAUSALITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":sha(P.read_bytes()),"calibration_events":len(ex["regimes"])*len(ex["calibration_seeds"])*len(ex["calibration_amplitudes"])*ex["calibration_per_amplitude"],"eval_events":len([x for x in rows if x["views"]==8 and x["regime"] in ex["regimes"]]),"stress_events":len([x for x in rows if x["views"]==8 and x["regime"] in ex["stress"]]),"mirror_pairs":len(rows)*len(modes),"calibration_lock_sha256":lockhash,"calibration_lock":lock,"gates":gates,"by_regime":by,"primary_by_seed":per,"reconstruction":reco,"nonidentifiability":identity,"rows":rows,"reconstruction_rows":rec,"origin_prime_turns":turns,"origin_prime":state,"physical_retrocausality_confirmed":False,"external_blind_exam":False,"real_radio_groups":0,"actual_vetoes":0,"production_changed":False}
O.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
print(json.dumps({k:v for k,v in out.items() if k not in ("rows","reconstruction_rows","origin_prime_turns","origin_prime","calibration_lock","primary_by_seed")},sort_keys=True))
