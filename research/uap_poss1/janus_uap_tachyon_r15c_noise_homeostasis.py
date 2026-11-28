#!/usr/bin/env python3
import hashlib,json,math,pathlib,subprocess,collections
import numpy as np
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.5C-NOISE-HOMEOSTASIS-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.5C-NOISE-HOMEOSTASIS-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());ex=p["experiment"];n=ex["views"];K=ex["background_samples"]
def sha(x):return hashlib.sha256(x).hexdigest()
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def ah(x):return sha(np.ascontiguousarray(x).tobytes())
def git(*a):return subprocess.check_output(["git",*a],text=True).strip()
assert git("hash-object",p["parent_code"])==p["parent_code_blob"]
assert git("hash-object",p["parent_result"])==p["parent_result_blob"]
prior=json.loads((R/p["parent_result"]).read_text());assert prior["mirror_pairs"]==30400
src=(R/p["parent_code"]).read_text();marker="\ncal={reg:"
assert src.count(marker)==1
g={};exec(compile(src.split(marker)[0],"<frozen R15B initialization>","exec"),g)
pulse=g["pulse"];ar=g["ar"];cov=g["covariance"];feature=g["feature"];cell=g["cell"];t=g["t"];N=len(t)
def noise(rng,L,sig,gain,extra):
    c=ar(rng,(1,L),.75)[0];z=sig[:,None]*ar(rng,(n,L),.35)+gain[:,None]*c
    if extra:z+=extra*gain[:,None]*ar(rng,(1,L),.85)
    ref=c+.18*ar(rng,(1,L),.35)[0]
    return z,ref
def make_session(rng,scenario):
    if scenario=="IID":sig=np.full(n,.14);gain=np.zeros(n);available=False;lane="IID"
    elif scenario=="ALIGNED_NO_REF":sig=np.full(n,.11);gain=np.full(n,.12);available=False;lane="ALIGNED_COMMON_NO_REF"
    else:sig=rng.uniform(.065,.20,n);gain=rng.uniform(.07,.20,n);available=True;lane="HETERO_COMMON_REF"
    extra=1.4 if scenario=="PERSISTENT_SHIFT" else 0.
    leak=.85 if scenario=="REF_LEAK" else 0.
    # The old epoch never sees the extra noise; current/validation do if persistent.
    old,ro=noise(rng,K,sig,gain,0.);cur,rc=noise(rng,K,sig,gain,extra);val,rv=noise(rng,K,sig,gain,extra)
    pilot=rng.choice([-1.,1.],size=K);pa,prf=noise(rng,K,sig,gain,extra);prf=prf+leak*pilot
    return dict(sig=sig,gain=gain,extra=extra,leak=leak,available=available,lane=lane,old=old,ro=ro,cur=cur,rc=rc,val=val,rv=rv,pilot=pilot,prf=prf,event_extra=1.4 if scenario=="EVENT_ONLY_SHIFT" else extra)
def lag(y):
    z=y-y.mean();return float(np.clip((z[1:]@z[:-1])/max(z@z,1e-16),-.9,.9))
def monitor(old,cur):
    a=cov(old);b=cov(cur);L=np.linalg.cholesky(a);v=np.linalg.solve(L,b);v=np.linalg.solve(L,v.T).T
    eig=np.linalg.eigvalsh((v+v.T)/2);score=float(np.max(np.abs(np.log(eig))))
    d=abs(lag(old.mean(0))-lag(cur.mean(0)))
    return {"log_eigen_ratio":score,"lag_delta":d,"eigenvalues":[float(x) for x in eig],"drift":score>math.log(1.8) or d>.20}
def qualify(s):
    if not s["available"]:return {"pass":False,"reason":"NO_REFERENCE","pilot_upper":None,"heldout_explained":None}
    x=s["pilot"]-s["pilot"].mean();y=s["prf"]-s["prf"].mean();beta=float(x@y/(x@x));err=y-beta*x
    se=math.sqrt(float(err@err/(len(x)-2)/(x@x)));upper=abs(beta)+3*se
    r=s["rc"]-s["rc"].mean();b=s["cur"]-s["cur"].mean(1,keepdims=True);coef=b@r/(r@r)
    vv=s["val"]-s["val"].mean(1,keepdims=True);rr=s["rv"]-s["rv"].mean();res=vv-coef[:,None]*rr
    gain=1-float(np.sum(res*res)/np.sum(vv*vv))
    return {"pass":bool(upper<=.12 and gain>=.15),"reason":"MEASURED_PILOT_AND_HELDOUT","pilot_slope":beta,"pilot_upper":upper,"heldout_explained":gain}
def fitmodel(b,r,mode):
    beta=np.zeros(n)
    if mode=="FULL":
        x=r-r.mean();beta=(b-b.mean(1,keepdims=True))@x/max(float(x@x),1e-12);b=b-beta[:,None]*x
        v=np.linalg.solve(cov(b),np.ones(n));w=v/v.sum()
    else:w=np.ones(n)/n
    z=w@b;var=float(np.var(z,ddof=1));rho=lag(z) if mode=="FULL" else 0.
    return {"beta":beta,"w":w,"var":var,"rho":rho,"mode":mode,"ref_mean":float(r.mean())}
def apply(model,a,r):
    return model["w"]@(a-model["beta"][:,None]*(r-model["ref_mean"]))
def fscore(model,a,r):
    return feature(apply(model,a,r),model["var"],model["rho"])
def route(s):
    d=monitor(s["old"],s["cur"]);q=qualify(s);mode="FULL" if q["pass"] else "EQ"
    # If reference status changes relative to prior availability, refresh model even without drift.
    refresh=d["drift"] or q["pass"]!=s["available"]
    b,r=(s["cur"],s["rc"]) if refresh else (s["old"],s["ro"])
    return d,q,refresh,fitmodel(b,r,mode)
def mirrored_session(s):
    z=dict(s)
    for k in ("old","ro","cur","rc","val","rv","pilot","prf"):z[k]=s[k][...,::-1]
    return z
def truth(rng,f,amp=None):
    k=rng.uniform(-.14,.14);r=rng.uniform(.05,.085);d=rng.uniform(.24,.38)
    if f=="cal":
        w=rng.uniform(.08,.28);return amp*pulse(k,w,w)
    if f=="weak_F":return .14*pulse(k,r,d)
    if f=="weak_R":return .14*pulse(k,d,r)
    if f=="strong_F":return 1.6*pulse(k,r,d)
    if f=="strong_R":return 1.6*pulse(k,d,r)
    if f.startswith("symmetric"):
        w=rng.uniform(.08,.28);return (.14 if f.endswith("weak") else 1.6)*pulse(k,w,w)
    if f=="noise":return np.zeros(N)
    if f=="double":return rng.uniform(.8,1.6)*pulse(rng.uniform(-.37,-.23),r,d)+rng.uniform(.8,1.6)*pulse(rng.uniform(.23,.37),d,r)
    if f=="clipped":return np.minimum(1.6*pulse(k,r,d),rng.uniform(.38,.65))
    raise ValueError(f)
def obs(rng,s,z,epoch):
    extra=0. if epoch=="old" else s["event_extra"] if epoch=="eval" else s["extra"]
    a,r=noise(rng,N,s["sig"],s["gain"],extra);return a+z[None,:],r+s["leak"]*z
def decide(d,th):return "ABSTAIN" if th is None else "F" if d>th else "R" if d< -th else "ABSTAIN"
def lock_cal(rng,s,models):
    # Separate signal-free noise realizations for each injected symmetric null; no event samples.
    cells={k:{str(i):[] for i in range(8)} for k in models}
    for amp in ex["calibration_amplitudes"]:
        for _ in range(ex["calibration_per_amplitude"]):
            z=truth(rng,"cal",amp);a,r=obs(rng,s,z,"current")
            for k,m in models.items():
                E,D=fscore(m,a,r);cells[k][cell(E)].append(abs(D))
    return {k:{i:{"n":len(v),"threshold":float(np.quantile(v,1-ex["alpha"],method="higher")) if len(v)>=ex["minimum_cell"] else None} for i,v in c.items()} for k,c in cells.items()}
def classify(m,a,r,lock):
    e,d=fscore(m,a,r);i=cell(e);th=lock[i]["threshold"]
    return {"E":e,"D":d,"bin":i,"decision":decide(d,th),"supported":th is not None}
def validate(rng,s,models,locks):
    c={k:0 for k in models};unsupported={k:0 for k in models};total=0
    for amp in ex["calibration_amplitudes"]:
        for _ in range(ex["validation_per_amplitude"]):
            z=truth(rng,"cal",amp);a,r=obs(rng,s,z,"current");total+=1
            for k,m in models.items():
                x=classify(m,a,r,locks[k]);c[k]+=x["decision"]!="ABSTAIN";unsupported[k]+=not x["supported"]
    return {k:{"declared":c[k],"n":total,"unsupported":unsupported[k],"pass":c[k]/total<=.05} for k in models}
rows=[];sessions=[];rec=[]
for scenario in ex["scenarios"]:
    for seed in ex["seeds"]:
        rng=np.random.default_rng(seed);s=make_session(rng,scenario);dr,q,refresh,m=route(s)
        sr=mirrored_session(s);dr2,q2,refresh2,m2=route(sr)
        assert dr["drift"]==dr2["drift"] and q["pass"]==q2["pass"] and refresh==refresh2
        assert np.allclose(m["w"],m2["w"],atol=1e-10) and np.allclose(m["beta"],m2["beta"],atol=1e-10)
        eq=fitmodel(s["cur"],s["rc"],"EQ");eq2=fitmodel(sr["cur"],sr["rc"],"EQ")
        old=fitmodel(s["old"],s["ro"],"FULL" if s["available"] else "EQ")
        oldlock=prior["calibration_lock"][s["lane"]]["8"]["FULL" if s["available"] else "EQ"]
        models={"HOME":m,"EQ":eq};locks=lock_cal(rng,s,models);h=dig(locks)
        validation=validate(rng,s,models,locks)
        allowed=validation["HOME"]["pass"]
        sessions.append({"scenario":scenario,"seed":seed,"drift":dr,"reference":q,"recalibrated":refresh,"mode":m["mode"],"lock_sha256":h,"lock":locks,"validation":validation,"old_background_sha256":ah(s["old"]),"current_background_sha256":ah(s["cur"]),"validation_background_sha256":ah(s["val"]),"model_var":m["var"],"old_var":old["var"],"eq_var":eq["var"],"direction_allowed":allowed})
        # Fresh evaluation RNG independent of calibration and validation consumption.
        rng=np.random.default_rng(seed+100000)
        for fam in ex["families"]:
            for i in range(ex["per_family"]):
                z=truth(rng,fam);a,r=obs(rng,s,z,"eval");before=ah(a);href=ah(r)
                a1=classify(m,a,r,locks["HOME"]);a2=classify(m2,a[:,::-1],r[::-1],locks["HOME"])
                assert math.isclose(a1["E"],a2["E"],rel_tol=1e-9,abs_tol=1e-9) and math.isclose(a1["D"],-a2["D"],rel_tol=1e-9,abs_tol=1e-9)
                assert a1["bin"]==a2["bin"] and a2["decision"]=={"F":"R","R":"F","ABSTAIN":"ABSTAIN"}[a1["decision"]]
                e=classify(eq,a,r,locks["EQ"]);er=classify(eq2,a[:,::-1],r[::-1],locks["EQ"])
                assert math.isclose(e["D"],-er["D"],rel_tol=1e-9,abs_tol=1e-9) and er["decision"]=={"F":"R","R":"F","ABSTAIN":"ABSTAIN"}[e["decision"]]
                b=classify(old,a,r,oldlock);home=a1["decision"] if allowed else "ABSTAIN"
                rows.append({"scenario":scenario,"seed":seed,"family":fam,"index":i,"input_sha256":before,"reference_sha256":href,"HOME":home,"HOME_shadow":a1,"EQ":e["decision"],"OLD":b["decision"],"raw_candidate_retained":True,"quarantine":not allowed})
                assert ah(a)==before and ah(r)==href
                if scenario=="IID" and fam in ("double","clipped"):
                    rec.append({"family":fam,"seed":seed,"index":i,"r":g["g"]["reconstruct"](a.mean(0),z)})
        assert dig(locks)==h
        print("R15C_SESSION",scenario,seed,dr["drift"],q["pass"],allowed,flush=True)
def summary(rr):
    out={}
    for k in ("OLD","EQ","HOME"):
        w=[x for x in rr if x["family"].startswith("weak_")];st=[x for x in rr if x["family"].startswith("strong_")];nu=[x for x in rr if x["family"].startswith("symmetric") or x["family"]=="noise"]
        def orient(a):return {"n":len(a),"correct":sum(x[k]==x["family"][-1] for x in a),"wrong":sum(x[k] not in ("ABSTAIN",x["family"][-1]) for x in a)}
        out[k]={"weak":orient(w),"strong":orient(st),"null":{"n":len(nu),"declared":sum(x[k]!="ABSTAIN" for x in nu)}}
    out["paired_strong_losses_EQ"]=sum(x["family"].startswith("strong_") and x["EQ"]==x["family"][-1] and x["HOME"]!=x["family"][-1] for x in rr)
    out["paired_strong_losses_OLD"]=sum(x["family"].startswith("strong_") and x["OLD"]==x["family"][-1] and x["HOME"]!=x["family"][-1] for x in rr)
    out["raw_candidates_retained"]=sum(x["raw_candidate_retained"] for x in rr)
    return out
def gate(z,improve):
    h=z["HOME"];e=z["EQ"];w=h["weak"];s=h["strong"];u=h["null"]
    return bool(w["wrong"]/w["n"]<=.05 and u["declared"]/u["n"]<=.05 and s["correct"]/s["n"]>=.85 and z["paired_strong_losses_EQ"]==0 and (not improve or (w["correct"]-e["weak"]["correct"])/w["n"]>=.10))
by={};per={};gates={}
for sc in ex["scenarios"]:
    by[sc]=summary([x for x in rows if x["scenario"]==sc]);per[sc]={str(seed):summary([x for x in rows if x["scenario"]==sc and x["seed"]==seed]) for seed in ex["seeds"]}
    gates[sc]=all(gate(z,sc in ("STABLE_REF","PERSISTENT_SHIFT")) for z in per[sc].values())
gates["drift_detection"]=all(s["drift"]["drift"]==(s["scenario"]=="PERSISTENT_SHIFT") for s in sessions if s["scenario"] in ("PERSISTENT_SHIFT","STABLE_REF"))
gates["reference_qualification"]=all(s["reference"]["pass"]==(s["scenario"] in ("STABLE_REF","PERSISTENT_SHIFT")) for s in sessions if s["scenario"] in ("STABLE_REF","PERSISTENT_SHIFT","REF_LEAK","ALIGNED_NO_REF"))
reconstruction={}
for fam in ("double","clipped"):
    a=[x["r"] for x in rec if x["family"]==fam];v=float(np.median([x["selected_rmse"] for x in a]));l=float(np.median([x["hidden_rmse"]["linear"] for x in a]));o=float(np.median([x["old_rmse"] for x in a]))
    reconstruction[fam]={"n":len(a),"R15":v,"linear":l,"R14":o,"gate":v<=l and v<=o}
gates["double_reconstruction"]=reconstruction["double"]["gate"]
axes=json.loads((R/"data/JANUS-DEEP-ANALYSIS-5D-SPIRAL-ORIGIN-PRIME-ORACLE-PROTOCOL-2026-08-21-v2.1.json").read_text())["five_dimensions"]
state={"known":["R15B stale covariance causes false direction"],"alternatives":["gain drift","common-noise drift","reference leakage","event-only interference","ordinary causal","hypothetical carrier"],"gaps":["actual radio reference calibration","carrier coupling","paired UAP"]};turns=[]
for name,delta in [("D1_TEMPORAL",[f"mirror pairs {len(rows)*2}"]),("D2_MIRROR",[f"drift gate {gates['drift_detection']}",f"reference gate {gates['reference_qualification']}"]),("D3_HIERARCHY",[f"{k}: {v}" for k,v in gates.items()]),("D4_ASSOCIATION",["gain and common covariance changes not uniquely attributable","event-only shift may evade background monitor"]),("D5_PROVENANCE",["background-only locks and independent validation","no physical carrier evidence","raw candidates retained"])]:
    h=dig(state);state={**state,"known":sorted(set(state["known"])|set(delta))};q=dig(state);turns.append({"anchor":name,"axes":axes,"parent":h,"state":q,"delta":delta,"status":"ORIGIN_PRIME" if h!=q else "NO_INFORMATION_GAIN"})
out={"schema":"janus.uap_tachyon.noise_homeostasis.result.v1","status":("SYNTHETIC_GATES_PASS" if all(gates.values()) else "PARTIAL_ENGINEERING_HOLD")+"__PHYSICAL_CAUSALITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":sha(P.read_bytes()),"sessions":sessions,"calibration_events":len(sessions)*len(ex["calibration_amplitudes"])*ex["calibration_per_amplitude"],"validation_events":len(sessions)*len(ex["calibration_amplitudes"])*ex["validation_per_amplitude"],"eval_events":len(rows),"mirror_pairs":len(rows)*2,"gates":gates,"by_scenario":by,"per_seed":per,"reconstruction":reconstruction,"rows":rows,"reconstruction_rows":rec,"origin_prime_turns":turns,"origin_prime":state,"production_changed":False,"actual_vetoes":0,"physical_retrocausality_confirmed":False,"real_radio_groups":0,"external_blind_exam":False}
O.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
print(json.dumps({**{k:v for k,v in out.items() if k not in ("rows","reconstruction_rows","origin_prime_turns","origin_prime","sessions","per_seed")},"session_summary":[{k:v for k,v in s.items() if k!="lock"} for s in sessions]},sort_keys=True))
