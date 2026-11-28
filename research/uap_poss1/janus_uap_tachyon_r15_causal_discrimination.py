#!/usr/bin/env python3
import ast,collections,hashlib,io,json,math,pathlib,subprocess,urllib.request
import numpy as np,h5py
from scipy import signal
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.5-REVERSE-CAUSAL-DISCRIMINATION-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.5-REVERSE-CAUSAL-DISCRIMINATION-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());cfg=p["shape"]
def sha(b):return hashlib.sha256(b).hexdigest()
def dig(x):return sha(json.dumps(x,sort_keys=True,ensure_ascii=True,separators=(",",":"),allow_nan=False).encode())
def ah(x):return sha(np.ascontiguousarray(x).tobytes())
def read(path):return json.loads((R/path).read_text())
def git(*args):return subprocess.check_output(["git",*args],text=True).strip()
assert git("hash-object",p["parent_code"])==p["parent_code_blob"]
prior=read(p["parent_result"]);assert prior["native"]["score_parity"]==288 and prior["cases"]==768
# Exact old functions, no top-level side effects and no change to their definitions.
astree=ast.parse((R/p["parent_code"]).read_text());names={"makebank","fits","score","replay"}
old={"np":np,"p":read(p["parent_contract"]),"banks":{}}
exec(compile(ast.Module(body=[n for n in astree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),"<pinned R1.4 definitions>","exec"),old)
t=np.linspace(-1,1,129);N=len(t);rho=.35
def pulse(k,r,d):return np.exp(np.where(t<=k,(t-k)/r,-(t-k)/d))
def ar(rng,shape):
    # Stationary initial sample, independently generated for each repeat.
    z=rng.normal(size=shape);x=z.copy()
    for i in range(1,shape[-1]):x[...,i]=rho*x[...,i-1]+math.sqrt(1-rho*rho)*z[...,i]
    return .14*x
def sample(rng,fam):
    k=rng.uniform(-.14,.14);r=rng.uniform(.05,.085);d=rng.uniform(.24,.38);bg=rng.uniform(-.4,.4)
    if fam=="weak_F":z=.14*pulse(k,r,d)
    elif fam=="weak_R":z=.14*pulse(k,d,r)
    elif fam=="strong_F":z=1.6*pulse(k,r,d)
    elif fam=="strong_R":z=1.6*pulse(k,d,r)
    elif fam=="symmetric":z=.14*pulse(k,.16,.16) if rng.random()<.5 else 1.6*pulse(k,.16,.16)
    elif fam=="noise":z=np.zeros(N)
    elif fam=="double":z=rng.uniform(.8,1.6)*pulse(rng.uniform(-.37,-.23),r,d)+rng.uniform(.8,1.6)*pulse(rng.uniform(.23,.37),d,r)
    elif fam=="clipped":z=np.minimum(1.6*pulse(k,r,d),rng.uniform(.38,.65))
    elif fam=="causal_smoothed":z=signal.lfilter([.35],[1,-.65],1.6*pulse(k,r,d))
    else:raise ValueError(fam)
    truth=bg+z
    obs=truth+ar(rng,(cfg["replicates"],N));background=ar(rng,(cfg["replicates"],256))
    return obs.mean(0),truth,float(np.var(background.mean(0),ddof=1))
B=[];lab=[]
for k in np.linspace(-.25,.25,17):
    for r in [.04,.06,.08,.12,.16,.24,.32,.4]:
        for d in [.04,.06,.08,.12,.16,.24,.32,.4]:
            B.append(pulse(k,r,d));lab.append("F" if r<d else "R" if r>d else "S")
B=np.array(B);lab=np.array(lab)
# Symmetric full-sample least squares; calibration absorbs colored-noise correlations.
def fit(y,bank,mask,evalmask):
    x=bank[:,mask];v=y[mask];xm=x.mean(1);ym=v.mean();xc=x-xm[:,None]
    a=np.maximum(0,xc@(v-ym)/np.maximum((xc*xc).sum(1),1e-20))
    q=a[:,None]*bank+(ym-a*xm)[:,None]
    loss=((q[:,mask]-v)**2).mean(1);best=float(loss.min())
    ix=np.flatnonzero(np.isclose(loss,best,rtol=1e-11,atol=1e-14));pred=q[ix].mean(0)
    return best,pred,float(np.mean((pred[evalmask]-y[evalmask])**2))
allmask=np.ones(N,dtype=bool)
F=B[lab=="F"];Rev=B[lab=="R"]
def direction(y,var):
    l,_,_=fit(y,F,allmask,allmask);r,_,_=fit(y,Rev,allmask,allmask)
    return float((r-l)/max(var,1e-16))
def decide(d,thr):return "F" if d>thr else "R" if d< -thr else "ABSTAIN"
cal=[]
for seed in cfg["calibration_seeds"]:
    rng=np.random.default_rng(seed)
    for fam in ("symmetric","noise"):
        for _ in range(128):
            y,z,var=sample(rng,fam);cal.append(abs(direction(y,var)))
thr=float(np.quantile(cal,.99,method="higher"));assert thr>0
# Reconstruction banks with complementary model families. Fit only observed samples.
two=[]
for k1 in [-.4,-.325,-.25,-.175]:
    for k2 in [.175,.25,.325,.4]:
        for r,d in [(.06,.24),(.08,.32),(.12,.24),(.16,.16)]:
            for q in [.65,1.,1.55]:two.append(pulse(k1,r,d)+q*pulse(k2,d,r))
clip=np.array([np.minimum(x,a) for x in B for a in [.25,.4,.55,.7]])
# Downsample templates for instrument-smoothing lane, no inverse filter on actual measurements.
smooth=np.array([signal.lfilter([a],[1,-(1-a)],x) for x in B[::4] for a in [.25,.35,.55]])
bank={"single":B,"double":np.array(two),"clipped":clip,"causal_smooth":smooth}
gap=np.abs(t)<=.16;obs=~gap
folds=[(np.abs(t)>=lo)&(np.abs(t)<=hi)&obs for lo,hi in [( .235,.40),(.48,.65)]]
def linear(y,tr):return np.interp(t,t[tr],y[tr])
def reconstruct(y,truth):
    cv={k:0. for k in ["linear",*bank]}
    for v in folds:
        tr=obs&~v
        cv["linear"]+=float(np.mean((linear(y,tr)[v]-y[v])**2))
        for k,b in bank.items():cv[k]+=fit(y,b,tr,v)[2]
    chosen=min(cv,key=cv.get)
    candidates={"linear":linear(y,obs)}
    for k,b in bank.items():candidates[k]=fit(y,b,obs,gap)[1]
    err={k:float(np.sqrt(np.mean((q[gap]-truth[gap])**2))) for k,q in candidates.items()}
    return {"chosen":chosen,"cv":cv,"hidden_rmse":err,"selected_rmse":err[chosen],"old_rmse":old["replay"](y,truth)["selected_hidden_rmse"],"alternative_predictions_sha256":{k:ah(q[gap]) for k,q in candidates.items()}}
rows=[]
for seed in cfg["eval_seeds"]:
    rng=np.random.default_rng(seed)
    for fam in cfg["families"]:
        for i in range(cfg["per_family"]):
            y,z,var=sample(rng,fam);before=ah(y);d=direction(y,var);dr=direction(y[::-1],var)
            assert math.isclose(d,-dr,rel_tol=1e-10,abs_tol=1e-10)
            a=decide(d,thr);b=decide(dr,thr);assert b=={"F":"R","R":"F","ABSTAIN":"ABSTAIN"}[a]
            o=old["score"](y)["decision"]
            rr=reconstruct(y,z);assert ah(y)==before
            rows.append({"seed":seed,"family":fam,"i":i,"source_sha256":before,"old":o,"new":a,"D":d,"reverse_D":dr,"reconstruction":rr})
    print("R15_SEED",seed,flush=True)
def summary(rs):
    out={}
    for mode in ("old","new"):
        a=[x for x in rs if x["family"].startswith("weak_")];b=[x for x in rs if x["family"].startswith("strong_")];c=[x for x in rs if x["family"] in ("symmetric","noise")]
        def orient(z):return {"n":len(z),"correct":sum(x[mode]==x["family"][-1] for x in z),"wrong":sum(x[mode] not in (x["family"][-1],"ABSTAIN") for x in z)}
        out[mode]={"weak":orient(a),"strong":orient(b),"null":{"n":len(c),"declared":sum(x[mode]!="ABSTAIN" for x in c)}}
    a,b=out["old"],out["new"]
    out["gate"]=bool((b["weak"]["correct"]-a["weak"]["correct"])/b["weak"]["n"]>=.10 and b["weak"]["wrong"]/b["weak"]["n"]<=.05 and b["null"]["declared"]/b["null"]["n"]<=.05 and b["strong"]["correct"]/b["strong"]["n"]>=.85 and (a["strong"]["correct"]-b["strong"]["correct"])/b["strong"]["n"]<=.05)
    return out
by={str(s):summary([x for x in rows if x["seed"]==s]) for s in cfg["eval_seeds"]}
reco={}
for fam in cfg["families"]:
    rr=[x["reconstruction"] for x in rows if x["family"]==fam]
    a=float(np.median([x["selected_rmse"] for x in rr]));b=float(np.median([x["hidden_rmse"]["linear"] for x in rr]));c=float(np.median([x["old_rmse"] for x in rr]))
    reco[fam]={"new_median":a,"linear_median":b,"r14_median":c,"paired_wins_vs_linear":sum(x["selected_rmse"]<x["hidden_rmse"]["linear"] for x in rr),"n":len(rr),"selection":dict(collections.Counter(x["chosen"] for x in rr)),"gate":a<=b and a<=c}
# Independent timing measurement logic. Values in ns and m, fixed toy family.
rng=np.random.default_rng(p["causality"]["seed"]);C=299792458.
def timing(x):
    if not x["clock_calibrated"] or not x["path_authenticated"]:return "HOLD_MISSING_CALIBRATION_OR_PATH"
    # Intervals are deterministic worst-case bounds, not Gaussian confidence intervals.
    upper=x["recorded_ns"]-x["bias_ns"]+x["uncertainty_ns"]
    limit=x["L_min_m"]/C*1e9
    if upper<limit:return "TIMING_CONFLICT_CANDIDATE_ONLY"
    return "COMPATIBLE_OR_UNRESOLVED"
witness=[]
for fam in p["causality"]["cases"]:
    for i in range(p["causality"]["per_case"]):
        L=float(rng.uniform(3,6));light=L/C*1e9;unc=.25
        x={"recorded_ns":light+2+float(rng.uniform(0,1)),"bias_ns":0.,"uncertainty_ns":unc,"L_min_m":L-.01,"clock_calibrated":True,"path_authenticated":True,"independent_coupling":False}
        if fam in ("advanced_toy","common_cause","leakage","unverified_coupling"):x["recorded_ns"]=light-2
        if fam=="clock_bias_explains":x["recorded_ns"]=light-2;x["bias_ns"]=-4
        if fam=="missing_clock":x["recorded_ns"]=light-2;x["clock_calibrated"]=False
        if fam=="ambiguous_path":x["recorded_ns"]=light-2;x["path_authenticated"]=False
        v=timing(x);expected="TIMING_CONFLICT_CANDIDATE_ONLY" if fam in ("advanced_toy","common_cause","leakage","unverified_coupling") else "HOLD_MISSING_CALIBRATION_OR_PATH" if fam in ("missing_clock","ambiguous_path") else "COMPATIBLE_OR_UNRESOLVED"
        assert v==expected
        witness.append({"family":fam,"inputs":x,"decision":v,"physical_claim":False,"surviving_alternatives":["clock/systematic outside assumed bounds","common cause or misassociation","leakage or selection","uncharacterized response","ordinary cause","hypothetical carrier"]})
# Exact paired observable evidence, differing latent causal stories.
identical=[]
for i in range(32):
    x=witness[32+i]["inputs"];assert timing(x)==timing(dict(x))
    identical.append({"input_sha256":dig(x),"stories":["advanced toy","ordinary common cause with apparent source pairing"],"decision":timing(x),"carrier_identified":False})
real={}
try:
    m=read("registry/uap/JANUS-UAP-TACHYON-R1.2-MEASUREMENT-RESULT-2026-11-28-v1.0.json");a={}
    for k,g in m["gwosc"]["files"].items():
        with urllib.request.urlopen(urllib.request.Request(g["url"],headers={"User-Agent":"JANUS R1.5 research"}),timeout=45) as f:b=f.read(12_000_001)
        assert len(b)<=12_000_000 and sha(b)==g["sha256"]
        with h5py.File(io.BytesIO(b),"r") as h:x=h["strain/Strain"][:]
        assert len(x)==131072 and np.all(np.isfinite(x));a[k]=x
    fs=4096;sos=signal.butter(4,[35,350],btype="bandpass",fs=fs,output="sos");w={}
    for k,x in a.items():
        bg=np.concatenate((x[:12*fs],x[20*fs:]));fq,ps=signal.welch(bg,fs=fs,nperseg=fs);v=np.interp(np.fft.rfftfreq(len(x),1/fs),fq,ps);v=np.maximum(v,np.max(v)*1e-12)
        w[k]=signal.sosfiltfilt(sos,np.fft.irfft(np.fft.rfft(x)/np.sqrt(v),n=len(x)))
    l,h=int(15.25*fs),int(15.5*fs);r=w["L1"][l:h];r=r-r.mean();vals=[]
    for lag in range(-41,42):
        q=w["H1"][l+lag:h+lag];q=q-q.mean();vals.append(float(q@r/(np.linalg.norm(q)*np.linalg.norm(r))))
    j=int(np.argmax(np.abs(vals)));lag=j-41
    real={"status":"GWOSC_RAW_HASH_MATCH__ORDINARY_TIMING_CONTROL","H1_minus_L1_ms":lag*1000/fs,"correlation":vals[j],"parent_lag_samples":m["gwosc"]["event"]["lag_samples"],"lag_parity":lag==m["gwosc"]["event"]["lag_samples"],"emitter_time":None,"same_carrier_emission_pair":False,"causal_verdict":"HOLD_NO_EMITTER_OR_EXCLUSIVE_RESPONSE","chime":m["chime"]["status"],"opera":m["published_control"]["status"]}
except Exception as e:real={"status":"HOLD_ACQUISITION","error":str(e)[:300]}
# 5D evidence graph: state advancement through actual measured results.
axes=read(p["spiral"])["five_dimensions"];assert len(axes)==5
state={"known":["R1.4 morphology not causal arrow"],"alternatives":["ordinary causal","common cause","instrument","leakage","hypothetical carrier"],"gaps":["H4 calibrated interaction","H5 paired UAP","external blind radio"]};turns=[]
def turn(anchor,delta):
    global state
    prev=dig(state);new={**state,"known":sorted(set(state["known"])|set(delta))};h=dig(new)
    turns.append({"anchor":anchor,"axes":axes,"parent_state_sha256":prev,"state_sha256":h,"delta":delta,"status":"ORIGIN_PRIME" if h!=prev else "NO_INFORMATION_GAIN"});state=new
turn("D1_TEMPORAL",[f"weak shape gate seeds {sum(v['gate'] for v in by.values())}/3",f"mirror pairs {len(rows)}"])
turn("D2_MIRROR",[f"identical causal-story pairs {len(identical)}","morphology not physical direction"])
turn("D3_INVERSE",[f"double gate {reco['double']['gate']}",f"clipped gate {reco['clipped']['gate']}","all family reconstructions retained"])
turn("D4_ASSOCIATIVE",[f"bounded synthetic timing controls {len(witness)}","timing conflict is candidate only"])
turn("D5_PROVENANCE",[real["status"],"R14 source blob verified","no H4/H5 promotion"])
gates={"weak_and_strong_shape":all(x["gate"] for x in by.values()),"double_reconstruction":reco["double"]["gate"],"clipped_reconstruction":reco["clipped"]["gate"],"timing_controls":len(witness)==256,"real_control":real.get("lag_parity",False)}
out={"schema":"janus.uap_tachyon.reverse_causal_discrimination.result.v1","status":("SYNTHETIC_GATES_PASS" if all(gates.values()) else "PARTIAL_ENGINEERING_HOLD")+"__PHYSICAL_CAUSALITY_HOLD","protocol_sha256":sha(P.read_bytes()),"source_commit":p["source_commit"],"cases":len(rows),"calibration_nulls":len(cal),"threshold":thr,"gates":gates,"pooled":summary(rows),"per_seed":by,"reconstruction":reco,"synthetic_timing":dict(collections.Counter(x["decision"] for x in witness)),"timing_rows":witness,"identical_causal_pairs":identical,"real_control":real,"rows":rows,"origin_prime_turns":turns,"origin_prime":state,"production_changed":False,"actual_vetoes":0,"physical_retrocausality_confirmed":False,"real_paired_uap_measurements":0,"external_blind_exam":False,"prior_native_receipt_verified":True,"native_rerun":False}
O.write_text(json.dumps(out,indent=2,ensure_ascii=True,allow_nan=False)+"\n")
print(json.dumps({k:v for k,v in out.items() if k not in ("rows","timing_rows","identical_causal_pairs","origin_prime_turns","origin_prime")},sort_keys=True))
