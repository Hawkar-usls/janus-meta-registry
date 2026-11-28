#!/usr/bin/env python3
import ast,collections,hashlib,json,math,pathlib,subprocess,sys,tempfile,time,urllib.request
import h5py,numpy as np
from scipy import signal
from scipy.stats import beta
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.7A-SPECTRAL-POPULATION-EXPANSION-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.7A-SPECTRAL-POPULATION-EXPANSION-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());cfg=p["selection"]
def sha(b):return hashlib.sha256(b).hexdigest()
def ah(x):return sha(np.ascontiguousarray(x).tobytes())
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def read(path):return json.loads((R/path).read_text())
def gitblob(path):return subprocess.check_output(["git","hash-object",path],text=True).strip()
assert gitblob(p["parent_result"])==p["parent_blob"] and gitblob(p["r14_code"])==p["r14_blob"]
prev=read(p["parent_result"]);assert dig(prev["manifest"])==p["parent_manifest_sha256"]
pilot=[dict(x,split="pilot") for x in prev["manifest"] if x["selected"]];excluded={x["source"] for x in pilot}
groups=collections.defaultdict(list)
for x in prev["manifest"]:
    if x["population_eligible"] and x["source"] not in excluded:groups[x["source"]].append(x)
plan=pilot[:]
for split in ("reference","holdout"):
    keys=sorted([k for k,v in groups.items() if v[0]["split"]==split],key=lambda k:sha(("R17A-source|"+k).encode()))
    assert len(keys)>=cfg[split]
    for k in keys[:cfg[split]]:
        z=min(groups[k],key=lambda x:sha(("R17A-event|"+x["tns"]).encode()));plan.append(dict(z,split=split))
assert len(plan)==cfg["reference"]+cfg["holdout"]+cfg["pilot_diagnostic"]
assert len({x["tns"] for x in plan})==len(plan)
assert len({x["source"] for x in plan if x["split"]!="pilot"})==cfg["reference"]+cfg["holdout"]
plan=sorted(plan,key=lambda x:sha(("R17A-shard|"+x["tns"]).encode()))
for i,x in enumerate(plan):x["shard"]=i%cfg["shards"]
lock=dig(plan)
g={"np":np,"p":read(p["r14_contract"]),"banks":{}}
nodes=ast.parse((R/p["r14_code"]).read_text());exec(compile(ast.Module(body=[n for n in nodes.body if isinstance(n,ast.FunctionDef) and n.name in {"makebank","fits","score"}],type_ignores=[]),"<pinned R14>","exec"),g)
def score(y):
    y=np.asarray(y,float);assert len(y)>=12 and np.isfinite(y).all()
    a=g["score"](y);b=g["score"](y[::-1]);flip={"F":"R","R":"F","ABSTAIN":"ABSTAIN"}
    return {"D":a["D"],"Q":a["Q"],"decision":a["decision"],"reverse_D":b["D"],"reverse_Q":b["Q"],"reverse_decision":b["decision"],"mirror":bool(abs(a["D"]+b["D"])<1e-9 and abs(a["Q"]-b["Q"])<1e-9 and flip[a["decision"]]==b["decision"]),"n":len(y),"profile_sha256":ah(y),"profile":y.tolist()}
def fetch(url,path):
    h=hashlib.sha256();n=0
    req=urllib.request.Request(url,headers={"User-Agent":"JANUS R17A CHIME scientific archive audit"})
    deadline=time.monotonic()+240
    with urllib.request.urlopen(req,timeout=cfg["timeout_seconds"]) as f,open(path,"wb") as w:
        while True:
            b=f.read(1024*1024)
            if not b:break
            n+=len(b)
            if n>cfg["cap_bytes"]:raise ValueError("BYTE_CAP")
            if time.monotonic()>deadline:raise TimeoutError("TRANSFER_DEADLINE")
            w.write(b);h.update(b)
        return {"bytes":n,"sha256":h.hexdigest(),"http_status":f.status}
def load(d,key,nf):
    v=d[key]
    if v.ndim!=2 or v.shape[0]!=nf:raise ValueError("SHAPE")
    if v.size>cfg["max_cells"] or v.shape[1]>cfg["max_samples"]:raise ValueError("ARRAY_CAP")
    x=v[:];m=np.isfinite(x);ok=m.all(1)
    z={"shape":list(x.shape),"sha256":ah(x),"mask_sha256":ah(m),"finite_cells":int(m.sum()),"total_cells":int(m.size),"full_rows":int(ok.sum()),"masked_rows":int((~m.any(1)).sum()),"partial_rows":int((m.any(1)&~ok).sum()),"mask_fraction":float(1-m.mean()),"status":"HOLD_PROFILE"}
    if ok.sum()>=32 and x.shape[1]>=12:z.update(status="EXECUTED",score=score(x[ok].mean(0)))
    return x,ok,z
def sample(ids,k=128):
    return ids[np.linspace(0,len(ids)-1,min(k,len(ids))).astype(int)] if len(ids) else ids
def curves(w,c,ids,reverse=False):
    n=w.shape[1];m=c.shape[1];ls=m-n+1;out=[]
    for i in ids:
        a=w[i];a=a[::-1] if reverse else a;a=a-a.mean();b=c[i]
        den=np.linalg.norm(a)
        if den<=1e-15:continue
        s=np.r_[0,np.cumsum(b)];q=np.r_[0,np.cumsum(b*b)];var=np.maximum(q[n:]-q[:-n]-(s[n:]-s[:-n])**2/n,0)
        good=var>1e-24;cc=signal.correlate(b,a,mode="valid",method="fft")
        z=np.divide(cc,den*np.sqrt(var),out=np.zeros(ls),where=good)
        out.append(np.clip(z,-1,1))
    return (np.mean(out,axis=0),len(out)) if out else (np.zeros(ls),0)
def align(w,c,common):
    if c.shape[1]<w.shape[1] or w.shape[1]<12:return {"status":"HOLD_WINDOW"}
    ix=np.flatnonzero(common);a=sample(ix[ix%2==0]);b=sample(ix[ix%2==1])
    tr,n=curves(w,c,a);va,m=curves(w,c,b);j=int(np.argmax(tr));k=int(np.argmax(va))
    second=float(np.max(np.delete(tr,j))) if len(tr)>1 else -1.
    rv,_=curves(w,c,b,True);margin=float(tr[j]-second)
    ok=n>=32 and m>=32 and tr[j]>=.8 and va[j]>=.8 and margin>=.02 and j==k
    return {"status":"EMPIRICALLY_REGISTERED" if ok else "HOLD_ALIGNMENT","offset_samples":j,"validation_best_offset":k,"train_corr":float(tr[j]),"held_frequency_corr":float(va[j]),"train_margin":margin,"reverse_control_best_corr":float(rv.max()),"train_rows":n,"held_rows":m,"candidate_offsets":len(tr),"train_rows_sha256":ah(a),"held_rows_sha256":ah(b)}
def norm_mean(x):
    a=x-x.mean(1,keepdims=True);s=np.sqrt(np.mean(a*a,axis=1));ok=s>1e-15
    if ok.sum()<32:return None
    return (a[ok]/s[ok,None]).mean(0)
def analyze(meta):
    out={**meta,"status":"HOLD_DOWNLOAD","arrays":{}}
    try:
        with tempfile.TemporaryDirectory() as td:
            f=pathlib.Path(td)/"event.h5";out.update(fetch(meta["url"],f));out["status"]="DOWNLOADED"
            with h5py.File(f,"r") as h:
                d=h["frb"];name=d.attrs.get("tns_name","")
                if isinstance(name,bytes):name=name.decode()
                assert str(name)==meta["tns"]
                t=d["plot_time"][:];freq=d["plot_freq"][:];assert len(t)>1 and np.isfinite(t).all() and np.all(np.diff(t)>0)
                out["dt_as_stored"]=float(np.median(np.diff(t)));out["time_axis_sha256"]=ah(t);out["frequency_axis_sha256"]=ah(freq)
                out["inventory"]={k:list(v.shape) for k,v in d.items() if isinstance(v,h5py.Dataset)}
                data={}
                for key in ("wfall","calibrated_wfall"):
                    try:
                        x,ok,z=load(d,key,len(freq))
                        if key=="wfall" and x.shape[1]!=len(t):raise ValueError("TIME_AXIS_LENGTH")
                        out["arrays"][key]=z;data[key]=(x,ok)
                    except Exception as e:out["arrays"][key]={"status":"HOLD_ARRAY","error":repr(e)[:250]}
                if len(data)==2:
                    w,wm=data["wfall"];c,cm=data["calibrated_wfall"];common=wm&cm
                    a=align(w,c,common);out["alignment"]=a;out["common_rows"]=int(common.sum())
                    if a["status"]=="EMPIRICALLY_REGISTERED":
                        j=a["offset_samples"];wc=w[common];cc=c[common,j:j+w.shape[1]];cf=c[common]
                        z={"A_wfall_own":w[wm].mean(0),"B_wfall_common":wc.mean(0),"C_cal_crop_common":cc.mean(0),"D_cal_full_common":cf.mean(0),"E_cal_full_own":c[cm].mean(0)}
                        for k,v in [("F_cal_crop_standardized",cc),("G_wfall_crop_standardized",wc)]:
                            q=norm_mean(v)
                            if q is not None:z[k]=q
                        out["ablation"]={k:score(v) for k,v in z.items()}
                        out["alignment"]["wfall_axis_start"]=float(t[0]);out["alignment"]["wfall_axis_end"]=float(t[-1]);out["alignment"]["calibrated_origin"]="INFERRED_RELATIVE_ONLY"
                    out["masks_preserved"]=all(ah(x)==out["arrays"][k]["sha256"] and ah(np.isfinite(x))==out["arrays"][k]["mask_sha256"] for k,(x,_) in data.items())
                else:out["masks_preserved"]=all(ah(x)==out["arrays"][k]["sha256"] and ah(np.isfinite(x))==out["arrays"][k]["mask_sha256"] for k,(x,_) in data.items())
                out["status"]="PROCESSED" if any(z["status"]=="EXECUTED" for z in out["arrays"].values()) else "HOLD_NO_PROFILE"
    except Exception as e:out["error"]=repr(e)[:400]
    return out
def shard(i):
    rows=[]
    for x in plan:
        if x["shard"]!=i:continue
        r=analyze(x);rows.append(r);print("R17A_FILE",i,x["tns"],x["split"],r["status"],r.get("alignment",{}).get("status"),flush=True)
    pathlib.Path("shard.json").write_text(json.dumps({"shard":i,"plan_sha256":lock,"rows":rows},allow_nan=False)+"\n")
def getscore(r,lane):
    if lane in ("wfall","calibrated_wfall"):
        a=r["arrays"].get(lane,{});return a.get("score") if a.get("status")=="EXECUTED" else None
    return r.get("ablation",{}).get(lane)
def T(s):return abs(s["D"]) if s["Q"]>=.25 else 0.
def quant(v):return {str(q):float(np.quantile(v,q)) for q in [0,.1,.25,.5,.75,.9,.95,1]} if len(v) else {}
def interval(k,n):
    return [float(beta.ppf(.025,k,n-k+1)) if k else 0.,float(beta.ppf(.975,k+1,n-k)) if k<n else 1.] if n else None
def merge(path):
    rows=[];seen=set()
    for f in sorted(pathlib.Path(path).rglob("shard.json")):
        j=json.loads(f.read_text());assert j["plan_sha256"]==lock and j["shard"] not in seen;seen.add(j["shard"]);rows+=j["rows"]
    assert seen==set(range(cfg["shards"])) and len(rows)==len(plan)
    assert {r["tns"] for r in rows}=={r["tns"] for r in plan}
    by={r["tns"]:r for r in rows}
    for x in plan:assert all(by[x["tns"]][k]==x[k] for k in ("source","split","shard","url"))
    lanes=["wfall","calibrated_wfall","B_wfall_common","C_cal_crop_common","D_cal_full_common","F_cal_crop_standardized","G_wfall_crop_standardized"]
    dist={};ranks=[]
    for lane in lanes:
        ref=[(r,getscore(r,lane)) for r in rows if r["split"]=="reference" and getscore(r,lane) is not None];test=[(r,getscore(r,lane)) for r in rows if r["split"]=="holdout" and getscore(r,lane) is not None]
        assert not ({r["source"] for r,_ in ref}&{r["source"] for r,_ in test})
        a=[T(s) for _,s in ref];cal={"lane":lane,"reference":[{"source":r["source"],"tns":r["tns"],"T":T(s)} for r,s in sorted(ref,key=lambda z:z[0]["source"])]};h=dig(cal);n=len(a)
        hits=0
        for r,s in test:
            v=(1+sum(x>=T(s) for x in a))/(n+1);candidate=n>=100 and v<=.05;hits+=candidate
            ranks.append({"tns":r["tns"],"lane":lane,"T":T(s),"rank":v,"candidate":candidate,"lock_sha256":h})
        def summary(z):return {"n":len(z),"D":quant([s["D"] for _,s in z]),"Q":quant([s["Q"] for _,s in z]),"T":quant([T(s) for _,s in z]),"decisions":dict(collections.Counter(s["decision"] for _,s in z))}
        dist[lane]={"reference":summary(ref),"holdout":summary(test),"lock_sha256":h,"calibration":cal,"support":n>=100 and len(test)>=30,"holdout_tail_candidates":hits,"holdout_tail_interval":interval(hits,len(test)) if n>=100 else None}
    aligned=[r for r in rows if r.get("alignment",{}).get("status")=="EMPIRICALLY_REGISTERED" and "ablation" in r]
    pair=[r for r in rows if all(r["arrays"].get(k,{}).get("status")=="EXECUTED" for k in ("wfall","calibrated_wfall"))]
    transitions={}
    for x,y in [("A_wfall_own","B_wfall_common"),("B_wfall_common","C_cal_crop_common"),("C_cal_crop_common","D_cal_full_common"),("D_cal_full_common","E_cal_full_own"),("G_wfall_crop_standardized","F_cal_crop_standardized"),("A_wfall_own","E_cal_full_own")]:
        z=[(r["ablation"][x],r["ablation"][y]) for r in aligned if x in r["ablation"] and y in r["ablation"]]
        transitions[x+"__"+y]={"n":len(z),"delta_D":quant([b["D"]-a["D"] for a,b in z]),"delta_absD":quant([abs(b["D"])-abs(a["D"]) for a,b in z]),"R_to_other":sum(a["decision"]=="R" and b["decision"]!="R" for a,b in z),"decision_transitions":dict(collections.Counter(a["decision"]+"->"+b["decision"] for a,b in z))}
    recovery={}
    for name in p["recovery"]["download_cap_failures"]+p["recovery"]["array_cap_failures"]:
        r=by[name];recovery[name]={"status":r["status"],"bytes":r.get("bytes"),"error":r.get("error"),"arrays":{k:{i:v for i,v in a.items() if i in ("status","error","shape")} for k,a in r["arrays"].items()}}
    sc=[a["score"] for r in rows for a in r["arrays"].values() if a["status"]=="EXECUTED"]+[a for r in rows for a in r.get("ablation",{}).values()]
    gates={"reference_and_holdout_wfall":dist["wfall"]["support"],"reference_and_holdout_calibrated":dist["calibrated_wfall"]["support"],"registration_coverage":bool(pair) and len(aligned)/len(pair)>=.8,"mirror":bool(sc) and all(a["mirror"] for a in sc),"mask_preservation":bool(sc) and all(r.get("masks_preserved",False) for r in rows if r["status"]=="PROCESSED"),"five_recoveries":all(all(r["arrays"].get(k,{}).get("status")=="EXECUTED" for k in ("wfall","calibrated_wfall")) for r in recovery.values())}
    axes=read("data/JANUS-DEEP-ANALYSIS-5D-SPIRAL-ORIGIN-PRIME-ORACLE-PROTOCOL-2026-08-21-v2.1.json")["five_dimensions"];state={"known":["R17 representation-dependent morphology"],"alternatives":["window length","frequency mask","channel gain","scattering","instrument","ordinary astrophysics","unknown interference","hypothetical carrier"],"gaps":["paired physical witness","carrier model","absolute timing"]};turns=[]
    for k,delta in [("D1_TEMPORAL",[f"profiles {len(sc)}"]),("D2_MIRROR",[f"mirror {sum(s['mirror'] for s in sc)}/{len(sc)}"]),("D3_HIERARCHY",[f"registered {len(aligned)}/{len(pair)}",dig(transitions)]),("D4_ASSOCIATIVE",[dig({k:v["lock_sha256"] for k,v in dist.items()}),"source-disjoint descriptive tails"]),("D5_PROVENANCE",[lock,dig([{"tns":r["tns"],"sha":r.get("sha256")} for r in rows]),"physical HOLD"])]:
        h=dig(state);state={**state,"known":sorted(set(state["known"])|set(delta))};turns.append({"anchor":k,"axes":axes,"parent":h,"state":dig(state),"delta":delta})
    out={"schema":"janus.uap_tachyon.spectral_population_expansion.result.v1","status":("POPULATION_ENGINEERING_GATES_PASS" if all(gates.values()) else "PARTIAL_POPULATION_HOLD")+"__PAIRED_WITNESS_HOLD__PHYSICAL_CAUSALITY_HOLD","protocol_sha256":sha(P.read_bytes()),"source_commit":p["source_commit"],"manifest_sha256":lock,"manifest":plan,"downloaded":sum("sha256" in r for r in rows),"processed":sum(r["status"]=="PROCESSED" for r in rows),"paired":len(pair),"registered":len(aligned),"profiles":len(sc),"mirror_passed":sum(s["mirror"] for s in sc),"gates":gates,"recovery":recovery,"distribution":dist,"transitions":transitions,"holdout_ranks":ranks,"rows":rows,"origin_prime_turns":turns,"origin_prime":state,"physical_retrocausality_confirmed":False,"native_RETINA_calls":0,"real_radio_groups":0,"production_changed":False,"actual_vetoes":0}
    O.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    compact={k:v for k,v in out.items() if k not in ("manifest","rows","origin_prime","origin_prime_turns","holdout_ranks","distribution")};compact["distribution"]={k:{a:b for a,b in v.items() if a!="calibration"} for k,v in dist.items()};print(json.dumps(compact,sort_keys=True))
if sys.argv[1]=="merge":merge(sys.argv[2])
else:shard(int(sys.argv[1]))
