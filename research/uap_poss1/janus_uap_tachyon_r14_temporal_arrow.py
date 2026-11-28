#!/usr/bin/env python3
import hashlib,importlib.util,io,json,math,os,pathlib,subprocess,urllib.request
import numpy as np,h5py
from scipy import signal
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.4-TEMPORAL-ARROW-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.4-TEMPORAL-ARROW-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());ex=p["exam"]
def sha(b):return hashlib.sha256(b).hexdigest()
def canon(v):return json.dumps(v,sort_keys=True,ensure_ascii=True,separators=(",",":"),allow_nan=False).encode()
def dig(v):return sha(canon(v))
def git(*a):return subprocess.check_output(["git",*a])
def arrhash(a):return sha(np.ascontiguousarray(a).tobytes())
parent=json.loads((R/p["parent_result"]).read_text())
assert parent["retina"]["status"]=="NATIVE_FORWARD_REVERSE_REPLAY_PASS" and parent["retina"]["native_calls"]==576
banks={}
def makebank(n):
    if n in banks:return banks[n]
    t=np.linspace(-1,1,n);gs=[];labels=[]
    for peak in p["model"]["parameters"]["normalized_peaks"]:
        for r in p["model"]["parameters"]["normalized_tau"]:
            for d in p["model"]["parameters"]["normalized_tau"]:
                gs.append(np.exp(np.where(t<=peak,(t-peak)/r,-(t-peak)/d)))
                labels.append("F" if r<d else "R" if r>d else "S")
    B=np.array(gs);labs=np.array(labels);idx=np.arange(n);mask=np.minimum(idx,n-1-idx)%2==0
    banks[n]=(B,labs,mask)
    return banks[n]
def fits(y,B,train,evalmask):
    X=B[:,train];Y=y[train];xm=X.mean(1);ym=Y.mean()
    XC=X-xm[:,None];a=np.maximum(0,XC@(Y-ym)/np.maximum((XC*XC).sum(1),1e-20));b=ym-a*xm
    pred=a[:,None]*B+b[:,None]
    tr=((pred[:,train]-Y)**2).mean(1)
    te=((pred[:,evalmask]-y[evalmask])**2).mean(1)
    null=float(np.mean((y[evalmask]-ym)**2))
    return tr,te,pred,null
def score(y):
    y=np.asarray(y,float);assert y.ndim==1 and len(y)>=12 and np.all(np.isfinite(y))
    B,labs,mask=makebank(len(y));loss={k:0. for k in "FRS"};null=0.
    for tr in (mask,~mask):
        l,e,_,z=fits(y,B,tr,~tr);null+=z
        for k in loss:
            ids=np.flatnonzero(labs==k);best=l[ids].min()
            # Average tied candidates so exact mirror bank has no index-order advantage.
            tie=ids[np.isclose(l[ids],best,rtol=1e-12,atol=1e-14)]
            loss[k]+=float(e[tie].mean())
    if null<=1e-20:return {"D":0.,"Q":0.,"decision":"ABSTAIN","loss":loss}
    D=(loss["R"]-loss["F"])/null;Q=1-min(loss.values())/null
    decision="F" if Q>=.25 and D>=.12 else "R" if Q>=.25 and D<=-.12 else "ABSTAIN"
    return {"D":float(D),"Q":float(Q),"decision":decision,"loss":loss}
def mirror(y,a):
    b=score(y[::-1]);assert abs(a["D"]+b["D"])<=1e-10 and abs(a["Q"]-b["Q"])<=1e-10
    assert b["decision"]=={"F":"R","R":"F","ABSTAIN":"ABSTAIN"}[a["decision"]]
    assert arrhash(y)==arrhash(y[::-1][::-1])
    return b
def pulse(t,k,r,d):return np.exp(np.where(t<=k,(t-k)/r,-(t-k)/d))
def generate(rng,kind):
    t=np.linspace(-1,1,129);k=rng.uniform(-.14,.14);r=rng.uniform(.05,.085);d=rng.uniform(.24,.38);a=rng.uniform(1.3,2.2);bg=rng.uniform(-.4,.4)
    noise=rng.normal(0,.055,len(t))
    if kind=="fast_rise_slow_decay":clean=bg+a*pulse(t,k,r,d)
    elif kind in ("slow_rise_fast_decay","ordinary_causal_slow_rise"):clean=bg+a*pulse(t,k,d,r)
    elif kind=="symmetric":clean=bg+a*pulse(t,k,.16,.16)
    elif kind=="two_pulse":clean=bg+a*(pulse(t,-.28,r,d)+pulse(t,.31,d,r))
    elif kind=="colored_noise":
        clean=np.full(len(t),bg);noise=signal.lfilter([1],[1,-.85],rng.normal(0,.22,len(t)))
    elif kind=="weak_fast":clean=bg+.14*pulse(t,k,r,d);noise=rng.normal(0,.14,len(t))
    elif kind=="clipped_fast":clean=bg+np.minimum(a*pulse(t,k,r,d),.55)
    else:raise ValueError(kind)
    return clean+noise,clean
def replay(y,truth):
    B,labs,_=makebank(len(y));t=np.linspace(-1,1,len(y));gap=np.abs(t)<=.16;tr=~gap
    l,_,pred,_=fits(y,B,tr,gap);out={}
    for k in "FRS":
        ids=np.flatnonzero(labs==k);best=l[ids].min();tie=ids[np.isclose(l[ids],best,rtol=1e-12,atol=1e-14)]
        z=pred[tie].mean(0);out[k]={"observed_fit_mse":float(l[tie].mean()),"hidden_clean_rmse":float(np.sqrt(np.mean((z[gap]-truth[gap])**2)))}
    interp=np.interp(t[gap],t[tr],y[tr]);out["linear"]={"hidden_clean_rmse":float(np.sqrt(np.mean((interp-truth[gap])**2)))}
    # Choice uses observed data alone. Hidden truth used for evaluation only.
    chosen=min("FRS",key=lambda k:out[k]["observed_fit_mse"]);out["selected_by_observed_fit"]=chosen
    out["selected_hidden_rmse"]=out[chosen]["hidden_clean_rmse"]
    return out
rows=[]
for seed in ex["seeds"]:
    rng=np.random.default_rng(seed)
    for family in ex["families"]:
        for i in range(ex["per_family_per_seed"]):
            y,z=generate(rng,family);a=score(y);b=mirror(y,a);rows.append({"seed":seed,"family":family,"index":i,"source_sha256":arrhash(y),"forward":a,"reverse":b,"replay":replay(y,z)})
def counts(rs):
    return {k:sum(x["forward"]["decision"]==k for x in rs) for k in ["F","R","ABSTAIN"]}
by={};gates=[]
for seed in ex["seeds"]:
    r=[x for x in rows if x["seed"]==seed];c={k:counts([x for x in r if x["family"]==k]) for k in ex["families"]}
    strong=c["fast_rise_slow_decay"]["F"]+c["slow_rise_fast_decay"]["R"];wrong=c["fast_rise_slow_decay"]["R"]+c["slow_rise_fast_decay"]["F"];sym=c["symmetric"]["ABSTAIN"]
    ok=strong/64>=.85 and wrong/64<=.05 and sym/32>=.8
    gates.append(ok);by[str(seed)]={"families":c,"strong_correct":strong,"strong_wrong":wrong,"symmetric_abstain":sym,"gate":ok}
reconstruction={}
for k in ex["families"]:
    rr=[x["replay"] for x in rows if x["family"]==k]
    reconstruction[k]={"selected_median_hidden_rmse":float(np.median([x["selected_hidden_rmse"] for x in rr])),"linear_median_hidden_rmse":float(np.median([x["linear"]["hidden_clean_rmse"] for x in rr])),"candidate_median_hidden_rmse":{s:float(np.median([x[s]["hidden_clean_rmse"] for x in rr])) for s in "FRS"}}
# Exact observational equivalence: identical RNG initial state, different causal story.
from numpy.random import default_rng
pairs=[]
for i in range(32):
    a,_=generate(default_rng(614300+i),"slow_rise_fast_decay");b,_=generate(default_rng(614300+i),"ordinary_causal_slow_rise")
    assert np.array_equal(a,b) and score(a)==score(b)
    pairs.append({"source_sha256":arrhash(a),"decision":score(a)["decision"],"causal_label_identifiable":False})
# Terminal-state analogue: x_{t+1}=x_t+u_t, different trajectories and same endpoint.
def trajectory(u):return [0]+list(np.cumsum(u).astype(int))
h=[trajectory([1,2,1]),trajectory([2,0,2])]
h=[[int(v) for v in x] for x in h];assert h[0]!=h[1] and h[0][-1]==h[1][-1]==4
egg={"histories":h,"same_terminal":4,"unique_predecessor":False,"replay_pass":True}
# Known real ordinary event, offline envelope analysis, no signal-front inference.
real={}
try:
    old=json.loads((R/p["measurement"]).read_text());gg=old["gwosc"]["files"];fs=4096
    for d in ("H1","L1"):
        g=gg[d];req=urllib.request.Request(g["url"],headers={"User-Agent":"JANUS temporal arrow research/1.4"})
        with urllib.request.urlopen(req,timeout=45) as f:b=f.read(12_000_001)
        assert len(b)<=12_000_000 and sha(b)==g["sha256"]
        with h5py.File(io.BytesIO(b),"r") as f:x=f["strain/Strain"][:]
        assert len(x)==131072 and np.all(np.isfinite(x))
        sos=signal.butter(4,[35,350],btype="bandpass",fs=fs,output="sos")
        z=signal.sosfiltfilt(sos,x);kernel=np.ones(129)/129
        env=np.sqrt(np.maximum(0,np.convolve(z*z,kernel,"same")))
        # Fixed 0.25s windows, 129 points; scaled by off-event median to avoid numerical degeneracy.
        scale=float(np.median(env[:12*fs]));assert scale>0
        def win(s):
            start=int(round(s*fs));y=env[start+np.arange(129)*8]/scale
            a=score(y);return {"forward":a,"reverse":mirror(y,a)}
        real[d]={"sha256":sha(b),"event":win(15.25),"off":[win(i) for i in [3,5,7,9,11,20,22,24,26,28]]}
    real["status"]="KNOWN_GWOSC_OFFLINE_ENVELOPE_CONTROL_EXECUTED"
except Exception as e:real["status"]="HOLD_REAL_CONTROL";real["error"]=str(e)[:350]
# Existing spectral detector is an independent, frozen lane.
native={}
try:
    n=p["native"];subprocess.run(["git","fetch","--depth=1","https://github.com/Hawkar-usls/janus-meta-registry.git",n["receipt_commit"]],check=True,timeout=100)
    old=json.loads(git("show",n["receipt_commit"]+":"+n["receipt"]));ct=json.loads(git("show",n["receipt_commit"]+":"+n["contract"]))
    folder=pathlib.Path("/tmp/r14-cosmos");folder.mkdir(exist_ok=True)
    for a in (["git","init","-q",str(folder)],["git","-C",str(folder),"fetch","--depth=1","https://github.com/Hawkar-usls/Janus-Cosmos.git",n["cosmos_commit"]],["git","-C",str(folder),"checkout","--detach","FETCH_HEAD"]):subprocess.run(a,check=True,timeout=120)
    assert git("-C",str(folder),"hash-object",str(folder/n["code"])).decode().strip()==n["blob"]
    os.chdir(folder);sp=importlib.util.spec_from_file_location("retina",folder/n["code"]);nm=importlib.util.module_from_spec(sp);sp.loader.exec_module(nm)
    e=ct["frozen_exam"];contexts=[tuple(x) for x in e["contexts_hz_s"]];bn={x:nm.templates(*x) for x in contexts};nr=[]
    for seed in e["seeds"]:
        rng=np.random.default_rng(seed)
        for family in e["classes"]:
            for idx in range(e["examples_per_class_per_seed"]):
                df,dt=contexts[int(rng.integers(len(contexts)))];cube=nm.generate(rng,family,df,dt,True);bank,params=bn[(df,dt)]
                before=arrhash(cube);prior=old["rows"][len(nr)];assert before==prior["source_sha256"] and prior["seed"]==seed and prior["class"]==family
                q=nm.score(cube,bank,params,df);assert all(math.isclose(q[k],prior["native_score"][k],rel_tol=1e-10,abs_tol=1e-10) for k in q)
                # Narrow central-band excess over shoulders, ON and REPEAT_ON independently averaged.
                a=cube[[0,2],:,:];env=(a[:,:,21:28].mean(2)-np.concatenate([a[:,:,:7],a[:,:,42:]],axis=2).mean(2)).mean(0)
                s=score(env);r=mirror(env,s);assert arrhash(cube)==before
                nr.append({"source_sha256":before,"seed":seed,"family":family,"native_score":q,"arrow":s,"mirror":r})
    assert len(nr)==288
    native={"status":"NATIVE_SCORE_PARITY_PASS__ARROW_SHADOW_EXECUTED","score_parity":len(nr),"inputs_unchanged":len(nr),"arrow_counts":{k:sum(x["arrow"]["decision"]==k for x in nr) for k in ["F","R","ABSTAIN"]},"rows":nr}
except Exception as e:native={"status":"HOLD_NATIVE_PARITY","error":str(e)[:350]}
finally:os.chdir(R)
# Canonical five axes, state enrichment and explicit no-gain if replay adds nothing.
spiral=json.loads((R/p["canonical_spiral"]).read_text());assert len(spiral["five_dimensions"])==5
state={"known":["R1.3 native spectral score symmetric on tested cubes"],"gaps":["H4 carrier coupling","H5 paired event","external blind radio data"]};turns=[]
def turn(k,delta):
    global state
    prev=dig(state);new={"known":sorted(set(state["known"])|set(delta)),"gaps":state["gaps"]};h=dig(new)
    turns.append({"anchor":k,"parent_state_sha256":prev,"state_sha256":h,"axes":spiral["five_dimensions"],"delta":delta,"status":"ORIGIN_PRIME" if h!=prev else "NO_INFORMATION_GAIN"});state=new
turn("D1_TEMPORAL",[f"mirror pairs={len(rows)}",f"strong shape gates={sum(gates)}/3"])
turn("D2_MIRROR",[f"ordinary causal identical morphology pairs={len(pairs)}","cause not identifiable from direction"])
turn("D3_INVERSE",["terminal admits two distinct histories","held gap forward replay evaluated against linear baseline"])
turn("D4_D5_SOURCE",[real["status"],native["status"],"no calibrated exclusive carrier observable"])
status="TEMPORAL_SHAPE_GATE_PASS" if all(gates) else "TEMPORAL_SHAPE_GATE_HOLD"
out={"schema":"janus.uap_tachyon.temporal_arrow.result.v1","status":status+"__PHYSICAL_CAUSALITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":sha(P.read_bytes()),"cases":len(rows),"mirror_pairs":len(rows),"shape_gates":by,"aggregate":{k:counts([x for x in rows if x["family"]==k]) for k in ex["families"]},"reconstruction":reconstruction,"identical_observable_pairs":pairs,"egg":egg,"real_control":real,"native":native,"origin_prime_turns":turns,"origin_prime":state,"rows":rows,"physical_retrocausality_confirmed":False,"actual_vetoes":0,"production_changed":False,"external_blind_exam":False,"real_radio_groups":0,"limitations":["Shape orientation is not causal direction; identical ordinary causal trajectories can have reverse-shaped envelopes.","Strong synthetic gates are frozen engineering criteria not empirical science.","Reconstruction is missing-data interpolation/extrapolation, not prospective forecasting.","Real GWOSC envelope is offline/acausal filtering and an ordinary control, not radio data or signal front.","Canonical 5D trace is a new adapter, not generalized native spiral engine."]}
O.write_text(json.dumps(out,ensure_ascii=True,indent=2,allow_nan=False)+"\n")
print(json.dumps({"status":out["status"],"cases":len(rows),"mirror_pairs":len(rows),"gates":by,"aggregate":out["aggregate"],"reconstruction":reconstruction,"identical_observable_pairs":len(pairs),"real_control":{k:({"event":v["event"]} if isinstance(v,dict) and "event" in v else v) for k,v in real.items()},"native":{k:v for k,v in native.items() if k!="rows"},"turns":len(turns),"physical_causality":"HOLD"},sort_keys=True))
