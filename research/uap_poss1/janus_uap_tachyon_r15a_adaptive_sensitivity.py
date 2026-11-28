#!/usr/bin/env python3
import collections,hashlib,json,math,pathlib,subprocess
import numpy as np
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.5A-ADAPTIVE-TEMPORAL-SENSITIVITY-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.5A-ADAPTIVE-TEMPORAL-SENSITIVITY-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());m=p["method"];ev=m["evaluation"]
def sha(b):return hashlib.sha256(b).hexdigest()
def digest(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def ah(x):return sha(np.ascontiguousarray(x).tobytes())
def git(*a):return subprocess.check_output(["git",*a],text=True).strip()
assert git("hash-object",p["parent_code"])==p["parent_blob"]
assert git("hash-object",p["parent_result"])==p["parent_result_blob"]
parent=json.loads((R/p["parent_result"]).read_text());assert parent["cases"]==1296
# Execute exactly the frozen parent's initialization and reconstruction functions.
# Stop before evaluation loop: no prior evaluation rows are used to tune or calibrate.
src=(R/p["parent_code"]).read_text();marker="\nrows=[]\n"
assert src.count(marker)==1
g={};exec(compile(src.split(marker)[0],"<pinned R15 initialization>","exec"),g)
assert abs(g["thr"]-parent["threshold"])<1e-10
B=g["B"];labs=g["lab"];t=g["t"];N=len(t);reps=m["repeats"]
# Same bank, normalized zero-mean templates. All scores from measured data.
X=B-B.mean(1,keepdims=True);X=X/np.linalg.norm(X,axis=1,keepdims=True)
groups={k:np.flatnonzero(labs==k) for k in "FRS"}
def feature(y,var):
    a=np.maximum(0,X@(y-y.mean()))/math.sqrt(max(var,1e-16))
    z={k:float(a[ix].max()) for k,ix in groups.items()};e=max(z.values())
    d=(z["F"]**2-z["R"]**2)/max(e,1.)
    return e,d,(z["F"]**2-z["R"]**2)/N
def pulse(k,r,d):return g["pulse"](k,r,d)
def ar(rng,shape):return g["ar"](rng,shape)
def sample(rng,fam,amp=None,stress=False):
    k=rng.uniform(-.14,.14);r=rng.uniform(.05,.085);d=rng.uniform(.24,.38);bg=rng.uniform(-.4,.4)
    if fam=="cal":z=amp*pulse(k,*(lambda a:(a,a))(rng.uniform(.08,.28)))
    elif fam=="weak_F":z=.14*pulse(k,r,d)
    elif fam=="weak_R":z=.14*pulse(k,d,r)
    elif fam=="strong_F":z=1.6*pulse(k,r,d)
    elif fam=="strong_R":z=1.6*pulse(k,d,r)
    elif fam.startswith("symmetric"):
        a=.14 if fam.endswith("weak") else 1.6
        w=rng.uniform(.08,.28);z=a*pulse(k,w,w)
    elif fam=="noise":z=np.zeros(N)
    elif fam=="double":z=rng.uniform(.8,1.6)*pulse(rng.uniform(-.37,-.23),r,d)+rng.uniform(.8,1.6)*pulse(rng.uniform(.23,.37),d,r)
    elif fam=="clipped":z=np.minimum(1.6*pulse(k,r,d),rng.uniform(.38,.65))
    elif fam=="causal_smoothed":z=g["signal"].lfilter([.35],[1,-.65],1.6*pulse(k,r,d))
    else:raise ValueError(fam)
    truth=bg+z
    obs=ar(rng,(16,N));b=ar(rng,(16,256))
    if stress:
        obs=math.sqrt(.6)*obs+math.sqrt(.4)*ar(rng,(1,N))
        b=math.sqrt(.6)*b+math.sqrt(.4)*ar(rng,(1,256))
        ys=np.asarray([bg+np.interp(t+rng.uniform(-.015,.015),t,z) for _ in range(16)])
    else:ys=truth[None,:]
    return ys+obs,b,truth
def prefix(a,b,n):
    y=a[:n].mean(0);var=float(np.var(b[:n].mean(0),ddof=1))
    return y,var
edges=m["bins"]
def cell(e):return int(np.searchsorted(edges,e,side="right")-1)
# Calibration uses only symmetric/noise observations, with new seed and continuous width.
cal={str(n):{str(i):[] for i in range(len(edges))} for n in reps}
rawcal={str(n):{str(i):[] for i in range(len(edges))} for n in reps}
for seed in m["calibration"]["seeds"]:
    rng=np.random.default_rng(seed)
    for amp in m["calibration"]["amplitudes"]:
        for _ in range(m["calibration"]["per_amplitude_per_seed"]):
            a,b,_=sample(rng,"cal",amp)
            for n in reps:
                y,v=prefix(a,b,n);e,d,raw=feature(y,v);i=str(cell(e));cal[str(n)][i].append(abs(d));rawcal[str(n)][i].append(abs(raw))
lock={}
for n in reps:
    lock[str(n)]={}
    for i,vals in cal[str(n)].items():
        raw=rawcal[str(n)][i]
        lock[str(n)][i]={"n":len(vals),"threshold":float(np.quantile(vals,.975,method="higher")) if len(vals)>=80 else None,"raw_q99":float(np.quantile(raw,.99,method="higher")) if vals else None}
lockhash=digest(lock);L=pathlib.Path("/tmp/r15a-calibration-lock.json");L.write_text(json.dumps(lock,indent=2)+"\n")
print("R15A_CALIBRATION_LOCK",lockhash,flush=True)
def classify(y,v,n):
    e,d,raw=feature(y,v);i=cell(e);th=lock[str(n)][str(i)]["threshold"]
    q="ABSTAIN" if th is None else "F" if d>th else "R" if d< -th else "ABSTAIN"
    return {"E":e,"D":d,"raw_D":raw,"bin":i,"threshold":th,"decision":q,"supported":th is not None}
rows=[];reconstruction=[]
def evaluate(seed,families,stress=False):
    rng=np.random.default_rng(seed);rr=[]
    for fam in families:
        for i in range(ev["per_family"]):
            a,b,truth=sample(rng,fam,stress=stress);before=ah(a)
            for n in reps:
                y,v=prefix(a,b,n);q=classify(y,v,n);rev=classify(y[::-1],v,n)
                assert math.isclose(q["E"],rev["E"],rel_tol=1e-10,abs_tol=1e-10) and math.isclose(q["D"],-rev["D"],rel_tol=1e-10,abs_tol=1e-10)
                assert q["bin"]==rev["bin"] and rev["decision"]=={"F":"R","R":"F","ABSTAIN":"ABSTAIN"}[q["decision"]]
                o=g["old"]["score"](y)["decision"];raw=g["direction"](y,v);assert math.isclose(raw,q["raw_D"],rel_tol=1e-9,abs_tol=1e-9)
                prev=g["decide"](raw,g["thr"])
                rr.append({"seed":seed,"family":fam,"index":i,"repeats":n,"source_sha256":ah(y),"R14":o,"R15":prev,"R15A":q["decision"],"E":q["E"],"D":q["D"],"bin":q["bin"],"supported":q["supported"],"stress":stress})
                if not stress and n==8 and fam in ("double","clipped"):
                    r=g["reconstruct"](y,truth)
                    if i==0:assert r==g["reconstruct"](y,truth)
                    reconstruction.append({"seed":seed,"family":fam,"index":i,"unchanged_R15":r})
            assert ah(a)==before
    return rr
for seed in ev["seeds"]:
    rows+=evaluate(seed,ev["families"]);print("R15A_EVAL_SEED",seed,flush=True)
stress=evaluate(ev["stress"]["seed"],ev["stress"]["families"],True)
assert digest(lock)==lockhash
nulls=("symmetric_weak","symmetric_strong","noise")
def summary(rr):
    o={}
    for alg in ("R14","R15","R15A"):
        w=[x for x in rr if x["family"].startswith("weak_")];s=[x for x in rr if x["family"].startswith("strong_")];z=[x for x in rr if x["family"] in nulls]
        def orient(a):return {"n":len(a),"correct":sum(x[alg]==x["family"][-1] for x in a),"wrong":sum(x[alg] not in ("ABSTAIN",x["family"][-1]) for x in a)}
        o[alg]={"weak":orient(w),"strong":orient(s),"null":{"n":len(z),"declared":sum(x[alg]!="ABSTAIN" for x in z)},"null_by_family":{k:{"n":sum(x["family"]==k for x in z),"declared":sum(x["family"]==k and x[alg]!="ABSTAIN" for x in z)} for k in nulls}}
    a=o["R14"];b=o["R15A"];w=b["weak"];s=b["strong"];z=b["null"]
    losses=sum(x["family"].startswith("strong_") and x["R15"]==x["family"][-1] and x["R15A"]!=x["family"][-1] for x in rr)
    o["paired_R15_strong_losses"]=losses;o["unsupported"]=sum(not x["supported"] for x in rr)
    o["gate"]=bool(w["n"] and s["n"] and z["n"] and (w["correct"]-a["weak"]["correct"])/w["n"]>=.10 and w["wrong"]/w["n"]<=.05 and z["declared"]/z["n"]<=.05 and s["correct"]/s["n"]>=.85 and (a["strong"]["correct"]-s["correct"])/s["n"]<=.05 and losses==0)
    return o
by={str(n):summary([x for x in rows if x["repeats"]==n]) for n in reps}
seeds={str(s):summary([x for x in rows if x["seed"]==s and x["repeats"]==8]) for s in ev["seeds"]}
stress_by={str(n):summary([x for x in stress if x["repeats"]==n]) for n in reps}
z=stress_by["8"]["R15A"];stress_gate=z["null"]["declared"]/z["null"]["n"]<=.05 and z["weak"]["wrong"]/z["weak"]["n"]<=.05
rec={}
for fam in ("double","clipped"):
    a=[x["unchanged_R15"] for x in reconstruction if x["family"]==fam]
    new=float(np.median([x["selected_rmse"] for x in a]));lin=float(np.median([x["hidden_rmse"]["linear"] for x in a]));old=float(np.median([x["old_rmse"] for x in a]))
    rec[fam]={"n":len(a),"unchanged_R15_median":new,"linear_median":lin,"R14_median":old,"gate":new<=lin and new<=old,"selector_changed":False}
axes=json.loads((R/"data/JANUS-DEEP-ANALYSIS-5D-SPIRAL-ORIGIN-PRIME-ORACLE-PROTOCOL-2026-08-21-v2.1.json").read_text())["five_dimensions"]
state={"known":["R15 global threshold suppressed all weak evaluation decisions"],"alternatives":["ordinary causal","common cause","instrument","leakage","hypothetical carrier"],"gaps":["real radio","H4 calibrated carrier","H5 paired event"]};turns=[]
def turn(anchor,delta):
    global state
    prev=digest(state);new={**state,"known":sorted(set(state["known"])|set(delta))};h=digest(new);turns.append({"anchor":anchor,"axes":axes,"parent":prev,"state":h,"delta":delta,"status":"ORIGIN_PRIME" if prev!=h else "NO_INFORMATION_GAIN"});state=new
turn("D1_CALIBRATION",[f"null lock {lockhash}","stratified thresholds, unsupported abstention"])
turn("D2_MIRROR",[f"exact mirror checked for {len(rows)+len(stress)} prefix observations"])
turn("D3_ACCUMULATION",[f"primary seeds pass {sum(x['gate'] for x in seeds.values())}/3"])
turn("D4_RECONSTRUCTION",[f"frozen double gate {rec['double']['gate']}",f"frozen clipped gate {rec['clipped']['gate']}"])
turn("D5_PROVENANCE",[f"stress gate {stress_gate}","prior code and receipt verified","no real carrier evidence"])
gates={"primary_shape_all_seeds":all(x["gate"] for x in seeds.values()),"double_reconstruction":rec["double"]["gate"],"stress_null_and_wrong":bool(stress_gate)}
out={"schema":"janus.uap_tachyon.adaptive_temporal_sensitivity.result.v1","status":("SYNTHETIC_ADAPTIVE_GATES_PASS" if all(gates.values()) else "PARTIAL_ENGINEERING_HOLD")+"__PHYSICAL_CAUSALITY_HOLD","protocol_sha256":sha(P.read_bytes()),"source_commit":p["source_commit"],"calibration_events":len(m["calibration"]["seeds"])*len(m["calibration"]["amplitudes"])*m["calibration"]["per_amplitude_per_seed"],"calibration_lock_sha256":lockhash,"calibration_lock":lock,"eval_events":len(rows)//len(reps),"stress_events":len(stress)//len(reps),"mirror_pairs":len(rows)+len(stress),"gates":gates,"by_repeats":by,"primary_by_seed":seeds,"stress_by_repeats":stress_by,"reconstruction":rec,"reconstruction_rows":reconstruction,"rows":rows,"stress_rows":stress,"origin_prime_turns":turns,"origin_prime":state,"production_changed":False,"actual_vetoes":0,"physical_retrocausality_confirmed":False,"external_blind_exam":False,"real_radio_groups":0,"native_rerun":False}
O.write_text(json.dumps(out,indent=2,ensure_ascii=True,allow_nan=False)+"\n")
print(json.dumps({k:v for k,v in out.items() if k not in ("rows","stress_rows","reconstruction_rows","origin_prime_turns","origin_prime")},sort_keys=True))
