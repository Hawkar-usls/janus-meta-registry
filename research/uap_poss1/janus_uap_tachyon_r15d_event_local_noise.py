#!/usr/bin/env python3
import hashlib,json,math,pathlib,subprocess,collections
import numpy as np
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.5D-EVENT-LOCAL-NOISE-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.5D-EVENT-LOCAL-NOISE-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());ex=p["experiment"];n=ex["views"];K=ex["background_samples"]
def sha(x):return hashlib.sha256(x).hexdigest()
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def ah(x):return sha(np.ascontiguousarray(x).tobytes())
def git(*a):return subprocess.check_output(["git",*a],text=True).strip()
assert git("hash-object",p["parent_code"])==p["parent_code_blob"]
assert git("hash-object",p["parent_result"])==p["parent_result_blob"]
prior=json.loads((R/p["parent_result"]).read_text());assert prior["eval_events"]==6480
src=(R/p["parent_code"]).read_text();marker="\nrows=[];sessions=[];rec=[]"
assert src.count(marker)==1
g={};exec(compile(src.split(marker)[0],"<frozen R15C initialization>","exec"),g)
ar=g["ar"];cov=g["cov"];feature=g["feature"];cell=g["cell"];t=g["t"];N=len(t);truth=g["truth"]
one=np.ones(n);H=np.eye(n)-np.ones((n,n))/n
windows=[slice(i,i+ex["window_length"]) for i in ex["windows"]]
def session(rng,sc):
    sig=np.full(n,.14) if sc=="IID" else rng.uniform(.065,.20,n)
    a=np.zeros(n) if sc=="IID" else rng.uniform(.07,.20,n)
    b=np.full(n,.17) if sc=="ALIGNED_HIDDEN" else rng.uniform(.06,.28,n)
    avail=np.array([sc!="IID",sc not in ("IID","UNTRACKED_BURST","ALIGNED_HIDDEN")],bool)
    leak=np.array([0.,.85 if sc=="REF_LEAK" else 0.])
    return dict(sig=sig,a=a,b=b,available=avail,leak=leak)
def draw(rng,s,L,burst,signal=None):
    c=ar(rng,(1,L),.75)[0];d=ar(rng,(1,L),.85)[0]
    if burst:
        u=np.linspace(-1,1,L);center=rng.uniform(-.2,.2);gate=np.exp(-.5*((u-center)/.38)**2);d=d*1.8*gate
    else:d=d*0.
    y=s["sig"][:,None]*ar(rng,(n,L),.35)+s["a"][:,None]*c+s["b"][:,None]*d
    refs=np.stack([c+.18*ar(rng,(1,L),.35)[0],d+.18*ar(rng,(1,L),.35)[0]])
    if signal is not None:y+=signal[None,:];refs+=s["leak"][:,None]*signal
    refs[~s["available"]]=0.
    return y,refs
def characterize(rng,s):
    # Separately controlled transfer measurement with stationary second excitation.
    def controlled():
        c=ar(rng,(1,K),.75)[0];d=ar(rng,(1,K),.85)[0]
        y=s["sig"][:,None]*ar(rng,(n,K),.35)+s["a"][:,None]*c+s["b"][:,None]*d
        r=np.stack([c+.18*ar(rng,(1,K),.35)[0],d+.18*ar(rng,(1,K),.35)[0]])
        r[~s["available"]]=0.
        return y,r
    b,r=controlled();v,vr=controlled();calm,cr=draw(rng,s,K,False)
    pilot=rng.choice([-1.,1.],size=K);_,pr=draw(rng,s,K,False,pilot)
    return dict(b=b,r=r,v=v,vr=vr,calm=calm,cr=cr,pilot=pilot,pr=pr,available=s["available"])
def mirror_context(c):
    return {k:(v if k=="available" else v[...,::-1]) for k,v in c.items()}
def centered(a):return a-a.mean(axis=-1,keepdims=True)
def regress(b,r,ok):
    out=np.zeros((n,2));x=centered(r[ok]);y=centered(b)
    if len(x):out[:,ok]=np.linalg.solve(x@x.T+np.eye(len(x))*1e-9,x@y.T).T
    return out
def qualify(c):
    pilot=centered(c["pilot"]);out=[]
    for i in range(2):
        if not c["available"][i]:out.append({"pass":False,"reason":"ABSENT"});continue
        y=centered(c["pr"][i]);sl=float(pilot@y/(pilot@pilot));res=y-sl*pilot
        upper=abs(sl)+3*math.sqrt(float(res@res/(K-2)/(pilot@pilot)))
        x=centered(c["r"][i]);beta=centered(c["b"])@x/max(float(x@x),1e-12)
        vv=centered(c["v"]);rr=centered(c["vr"][i]);expl=1-float(np.sum((vv-beta[:,None]*rr)**2)/np.sum(vv*vv))
        out.append({"pass":bool(upper<=.12 and expl>=.08),"pilot_upper":upper,"heldout_explained":expl})
    return out
def model(c):
    q=qualify(c);ok=np.array([x["pass"] for x in q],bool)
    beta=regress(c["b"],c["r"],ok)
    res=c["b"]-beta@c["r"];v=np.linalg.solve(cov(res),one);w=v/(one@v)
    # No-reference path uses equal weights to protect previous detections.
    if not ok.any():w=one/n
    assert math.isclose(float(w@one),1.,abs_tol=1e-12)
    bg=c["calm"]-beta@c["cr"];y=w@bg
    return dict(beta=beta,w=w,var=float(np.var(y,ddof=1)),rho=g["lag"](y) if ok.any() else 0.,q=q,ok=ok,
                contrast_scale=max(float(np.mean((H@bg)**2)),1e-12),ref_scale=max(float(np.var(c["cr"][1])),1e-12))
def local(m,a,r):
    pred=m["beta"]@r;res=a-pred;y=m["w"]@res
    # Covariance of signal-orthogonal contrasts, calculated separately per mirrored block.
    cs=[];rs=[];tr=[]
    for w in windows:
        x=H@res[:,w];C=centered(x)@centered(x).T/(x.shape[1]-1)
        cs.append(float(np.trace(C)/(n*m["contrast_scale"])))
        rs.append(float(np.var(r[1,w],ddof=1)/m["ref_scale"]) if m["ok"][1] else 0.)
        tr.append(float(np.linalg.eigvalsh(C)[-1]))
    E,D=feature(y,m["var"],m["rho"])
    return dict(E=E,D=D,contrast=cs,ref_power=rs,local_max=max(cs),witness_max=max(rs),leading_eigenvalues=tr,
                residual_sha256=ah(res),noise_prediction_sha256=ah(pred),replay_rmse=float(np.sqrt(np.mean((res+pred-a)**2))))
def bg_baseline(c):
    q=qualify(c);return g["fitmodel"](c["calm"],c["cr"][0],"FULL" if q[0]["pass"] else "EQ"),g["fitmodel"](c["calm"],c["cr"][0],"EQ")
def scorebase(m,a,r):
    E,D=g["fscore"](m,a,r[0]);return E,D
def qtile(v,q):return float(np.quantile(v,q,method="higher"))
def guarded(x,lim):return x["local_max"]>lim
def guardlock(rng,s,m):
    vals=[];wits=[]
    for i in range(ex["guard_cal"]):
        # Controlled burst only for a qualified measured witness; unknown residual interference is not normalized away.
        a,r=draw(rng,s,N,bool(i%2 and m["ok"][1]));x=local(m,a,r);vals.append(x["local_max"])
        if i%2==0:wits.append(x["witness_max"])
    return qtile(vals,.99),qtile(wits,.99)
def locks(rng,s,m,old,eq,lim):
    z={k:{str(i):[] for i in range(8)} for k in ("LOCAL","HOME","EQ")}
    for amp in ex["calibration_amplitudes"]:
        for i in range(ex["cal_per_amp"]):
            y=truth(rng,"cal",amp)
            # No science samples; independent background draws with prescribed controlled excitation.
            a,r=draw(rng,s,N,bool(i%2 and m["ok"][1]),y)
            q=local(m,a,r)
            if not guarded(q,lim):z["LOCAL"][cell(q["E"])].append(abs(q["D"]))
            E,D=scorebase(eq,a,r);z["EQ"][cell(E)].append(abs(D))
            a0,r0=draw(rng,s,N,False,y);E,D=scorebase(old,a0,r0);z["HOME"][cell(E)].append(abs(D))
    return {k:{i:{"n":len(v),"threshold":qtile(v,.975) if len(v)>=60 else None} for i,v in c.items()} for k,c in z.items()}
def dec(E,D,lock):
    th=lock[cell(E)]["threshold"];return "ABSTAIN" if th is None else "F" if D>th else "R" if D< -th else "ABSTAIN"
def decision(q,lim,lock):return "ABSTAIN" if guarded(q,lim) else dec(q["E"],q["D"],lock)
def validate(rng,s,m,old,eq,lim,lock):
    counts={k:0 for k in lock};total=0
    for amp in ex["calibration_amplitudes"]:
        for i in range(ex["validation_per_amp"]):
            z=truth(rng,"cal",amp);a,r=draw(rng,s,N,bool(i%2 and m["ok"][1]),z);q=local(m,a,r)
            counts["LOCAL"]+=decision(q,lim,lock["LOCAL"])!="ABSTAIN"
            E,D=scorebase(eq,a,r);counts["EQ"]+=dec(E,D,lock["EQ"])!="ABSTAIN"
            a0,r0=draw(rng,s,N,False,z);E,D=scorebase(old,a0,r0);counts["HOME"]+=dec(E,D,lock["HOME"])!="ABSTAIN";total+=1
    return {k:{"n":total,"declared":v,"pass":v/total<=.05} for k,v in counts.items()}
rows=[];sessions=[];rec=[]
for sc in ex["scenarios"]:
    for seed in ex["seeds"]:
        rng=np.random.default_rng(seed);s=session(rng,sc);c=characterize(rng,s);m=model(c);mm=model(mirror_context(c))
        assert np.allclose(m["beta"],mm["beta"],atol=1e-10) and np.allclose(m["w"],mm["w"],atol=1e-10) and np.array_equal(m["ok"],mm["ok"])
        old,eq=bg_baseline(c);lim,wlim=guardlock(rng,s,m);lock=locks(rng,s,m,old,eq,lim);h=dig(lock)
        val=validate(rng,s,m,old,eq,lim,lock);allowed=val["LOCAL"]["pass"]
        sessions.append({"scenario":sc,"seed":seed,"qualification":m["q"],"guard_threshold":lim,"witness_threshold":wlim,"lock":lock,"lock_sha256":h,"validation":val,"training_sha256":ah(c["b"]),"validation_sha256":ah(c["v"]),"calm_sha256":ah(c["calm"]),"pilot_sha256":ah(c["pilot"]),"weights":m["w"].tolist(),"coefficients":m["beta"].tolist()})
        rng=np.random.default_rng(seed+200000)
        for fam in ex["families"]:
            for i in range(ex["per_family"]):
                z=truth(rng,fam);burst=sc in ("TRACKED_BURST","UNTRACKED_BURST","ALIGNED_HIDDEN","REF_LEAK")
                a,r=draw(rng,s,N,burst,z);ha=ah(a);hr=ah(r);q=local(m,a,r);rev=local(mm,a[:,::-1],r[:,::-1])
                assert math.isclose(q["E"],rev["E"],rel_tol=1e-9,abs_tol=1e-9) and math.isclose(q["D"],-rev["D"],rel_tol=1e-9,abs_tol=1e-9)
                assert np.allclose(q["contrast"],rev["contrast"][::-1],rtol=1e-9,atol=1e-9) and np.allclose(q["ref_power"],rev["ref_power"][::-1],rtol=1e-9,atol=1e-9)
                d=decision(q,lim,lock["LOCAL"]);dr=decision(rev,lim,lock["LOCAL"]);assert dr=={"F":"R","R":"F","ABSTAIN":"ABSTAIN"}[d]
                E,D=scorebase(old,a,r);b=dec(E,D,lock["HOME"]);E,D=scorebase(eq,a,r);e=dec(E,D,lock["EQ"])
                assert q["replay_rmse"]<1e-12 and ah(a)==ha and ah(r)==hr
                rows.append({"scenario":sc,"seed":seed,"family":fam,"index":i,"input_sha256":ha,"reference_sha256":hr,"HOME":b,"EQ":e,"LOCAL":d if allowed else "ABSTAIN","guarded":guarded(q,lim),"witness_burst":bool(m["ok"][1] and q["witness_max"]>wlim),"validation_hold":not allowed,"raw_candidate_retained":True,"local_evidence":q})
                if sc=="IID" and fam in ("double","clipped"):rec.append({"family":fam,"result":g["g"]["g"]["reconstruct"](a.mean(0),z)})
        assert dig(lock)==h
        print("R15D_SESSION",sc,seed,m["ok"].tolist(),allowed,flush=True)
def summary(rr):
    o={}
    for k in ("HOME","EQ","LOCAL"):
        w=[x for x in rr if x["family"].startswith("weak_")];s=[x for x in rr if x["family"].startswith("strong_")];z=[x for x in rr if x["family"].startswith("symmetric") or x["family"]=="noise"]
        def orient(a):return {"n":len(a),"correct":sum(x[k]==x["family"][-1] for x in a),"wrong":sum(x[k] not in ("ABSTAIN",x["family"][-1]) for x in a)}
        o[k]={"weak":orient(w),"strong":orient(s),"null":{"n":len(z),"declared":sum(x[k]!="ABSTAIN" for x in z)}}
    o["paired_EQ_strong_losses"]=sum(x["family"].startswith("strong_") and x["EQ"]==x["family"][-1] and x["LOCAL"]!=x["family"][-1] for x in rr)
    o["guarded"]=sum(x["guarded"] for x in rr);o["witness_burst"]=sum(x["witness_burst"] for x in rr);o["validation_hold"]=sum(x["validation_hold"] for x in rr);o["n"]=len(rr);o["raw_retained"]=sum(x["raw_candidate_retained"] for x in rr)
    return o
def gate(o,sc):
    a=o["LOCAL"];b=o["EQ"];w=a["weak"];s=a["strong"];z=a["null"];delta=.10 if sc=="TRACKED_BURST" else -.05 if sc in ("IID","STABLE_REF") else -1.
    return bool((w["correct"]-b["weak"]["correct"])/w["n"]>=delta and w["wrong"]/w["n"]<=.05 and z["declared"]/z["n"]<=.05 and s["correct"]/s["n"]>=.85 and o["paired_EQ_strong_losses"]==0)
by={sc:summary([x for x in rows if x["scenario"]==sc]) for sc in ex["scenarios"]}
per={sc:{str(seed):summary([x for x in rows if x["scenario"]==sc and x["seed"]==seed]) for seed in ex["seeds"]} for sc in ex["scenarios"]}
gates={sc:all(gate(x,sc) for x in per[sc].values()) for sc in ex["scenarios"]}
reco={}
for fam in ("double","clipped"):
    a=[x["result"] for x in rec if x["family"]==fam];v=float(np.median([x["selected_rmse"] for x in a]));l=float(np.median([x["hidden_rmse"]["linear"] for x in a]));o=float(np.median([x["old_rmse"] for x in a]))
    reco[fam]={"n":len(a),"R15":v,"linear":l,"R14":o,"gate":v<=l and v<=o}
gates["double_reconstruction"]=reco["double"]["gate"]
# Same observed time series, same zero witness, opposite decompositions.
z=truth(np.random.default_rng(616999),"weak_F");x=np.tile(z,(n,1));zero=np.zeros_like(x);r=np.zeros((2,N))
identity={"observed_signal_story_sha256":ah(x+zero),"observed_noise_story_sha256":ah(zero+x),"reference_sha256":ah(r),"identifiable":False};assert identity["observed_signal_story_sha256"]==identity["observed_noise_story_sha256"]
axes=json.loads((R/"data/JANUS-DEEP-ANALYSIS-5D-SPIRAL-ORIGIN-PRIME-ORACLE-PROTOCOL-2026-08-21-v2.1.json").read_text())["five_dimensions"]
state={"known":["R15C event-only interference not visible in preceding background"],"alternatives":["ordinary signal","common noise","gain drift","reference leakage","unmeasured aligned interference","hypothetical carrier"],"gaps":["authenticated simultaneous radio witnesses","carrier coupling","paired UAP"]};turns=[]
for name,delta in [("D1_TEMPORAL",[f"mirrored events {len(rows)}"]),("D2_MIRROR",[f"tracked witness burst {by['TRACKED_BURST']['witness_burst']}",f"untracked guard {by['UNTRACKED_BURST']['guarded']}"]),("D3_HIERARCHY",[f"{k} gate {v}" for k,v in gates.items()]),("D4_INVERSE",["additive replay verified, not unique decomposition","aligned latent source not identifiable"]),("D5_PROVENANCE",["independent calibration and heldout validation","raw inputs retained","no real carrier evidence"])]:
    h=dig(state);state={**state,"known":sorted(set(state["known"])|set(delta))};q=dig(state);turns.append({"anchor":name,"axes":axes,"parent":h,"state":q,"delta":delta,"status":"ORIGIN_PRIME" if h!=q else "NO_INFORMATION_GAIN"})
out={"schema":"janus.uap_tachyon.event_local_noise.result.v1","status":("SYNTHETIC_GATES_PASS" if all(gates.values()) else "PARTIAL_ENGINEERING_HOLD")+"__PHYSICAL_CAUSALITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":sha(P.read_bytes()),"sessions":sessions,"eval_events":len(rows),"mirror_pairs":len(rows),"calibration_events":len(sessions)*len(ex["calibration_amplitudes"])*ex["cal_per_amp"],"validation_events":len(sessions)*len(ex["calibration_amplitudes"])*ex["validation_per_amp"],"guard_control_events":len(sessions)*ex["guard_cal"],"gates":gates,"by_scenario":by,"per_seed":per,"reconstruction":reco,"nonidentifiability":identity,"rows":rows,"reconstruction_rows":rec,"origin_prime_turns":turns,"origin_prime":state,"production_changed":False,"actual_vetoes":0,"physical_retrocausality_confirmed":False,"real_radio_groups":0,"external_blind_exam":False}
O.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
print(json.dumps({**{k:v for k,v in out.items() if k not in ("rows","reconstruction_rows","origin_prime_turns","origin_prime","sessions","per_seed")},"session_summary":[{k:v for k,v in s.items() if k!="lock"} for s in sessions]},sort_keys=True))
