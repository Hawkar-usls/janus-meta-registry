#!/usr/bin/env python3
import collections,csv,hashlib,io,json,math,pathlib,subprocess,urllib.request
import numpy as np,h5py
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.5E-PROTECTED-MULTI-WITNESS-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.5E-PROTECTED-MULTI-WITNESS-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());ex=p["experiment"]
def sha(x):return hashlib.sha256(x).hexdigest()
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def ah(x):return sha(np.ascontiguousarray(x).tobytes())
def git(*a):return subprocess.check_output(["git",*a],text=True).strip()
assert git("hash-object",p["parent_code"])==p["parent_code_blob"]
assert git("hash-object",p["parent_result"])==p["parent_result_blob"]
prior=json.loads((R/p["parent_result"]).read_text());assert prior["eval_events"]==6480
src=(R/p["parent_code"]).read_text();marker="\nrows=[];sessions=[];rec=[]"
assert src.count(marker)==1
g={};exec(compile(src.split(marker)[0],"<pinned R15D initialization>","exec"),g)
N=g["N"];cell=g["cell"];truth=g["truth"];draw=g["draw"];local=g["local"];qtile=g["qtile"]
routes=["TRACKED","CALM","UNKNOWN","NO_REFERENCE"]
def route(m,q,wlim):
    if m["ok"][1]:return "TRACKED" if q["witness_max"]>wlim else "CALM"
    return "UNKNOWN" if m["ok"][0] else "NO_REFERENCE"
def observed(m,eq,a,r,wlim):
    q=local(m,a,r);E,D=g["scorebase"](eq,a,r)
    return route(m,q,wlim),q,float(E),float(D)
def caldraw(rng,s,z,i):
    # Controlled disturbance excitation is an independent background acquisition,
    # not an event label; instrument metadata determines available controls.
    return draw(rng,s,N,bool(i%2 and s["available"].any()),z)
def calibrate(rng,s,m,eq,wlim,lim):
    cells={k:{mode:{str(i):[] for i in range(8)} for mode in ("EQ","CLEAN")} for k in routes}
    for amp in ex["amplitudes"]:
        for i in range(ex["cal_per_amp"]):
            z=truth(rng,"cal",amp);a,r=caldraw(rng,s,z,i);k,q,E,D=observed(m,eq,a,r,wlim)
            cells[k]["EQ"][cell(E)].append(abs(D))
            if not g["guarded"](q,lim):cells[k]["CLEAN"][cell(q["E"])].append(abs(q["D"]))
    return {k:{mode:{i:{"n":len(v),"threshold":qtile(v,.975 if mode=="EQ" else .99) if len(v)>=ex["min_cell"] else None} for i,v in c.items()} for mode,c in md.items()} for k,md in cells.items()}
def lanes(k,q,E,D,lock,lim):
    a=g["dec"](E,D,lock[k]["EQ"]);b="ABSTAIN" if g["guarded"](q,lim) else g["dec"](q["E"],q["D"],lock[k]["CLEAN"])
    return a,b
def fuse(a,b,allow):
    conflict=a!="ABSTAIN" and b!="ABSTAIN" and a!=b
    out=a if a!="ABSTAIN" else b if allow else "ABSTAIN"
    confident=out if allow and not conflict else "ABSTAIN"
    return out,confident,conflict
def validate(rng,s,m,eq,wlim,lim,lock):
    v={k:{"n":0,"EQ":0,"CLEAN":0,"union":0} for k in routes}
    for amp in ex["amplitudes"]:
        for i in range(ex["validation_per_amp"]):
            z=truth(rng,"cal",amp);a,r=caldraw(rng,s,z,i);k,q,E,D=observed(m,eq,a,r,wlim);a,b=lanes(k,q,E,D,lock,lim);u,_,_=fuse(a,b,True)
            v[k]["n"]+=1;v[k]["EQ"]+=a!="ABSTAIN";v[k]["CLEAN"]+=b!="ABSTAIN";v[k]["union"]+=u!="ABSTAIN"
    for k,x in v.items():x["allow"]=bool(x["n"]>=80 and x["union"]/x["n"]<=.05)
    return v
rows=[];sessions=[];rec=[];traces=[]
for sc in ex["scenarios"]:
    for seed in ex["seeds"]:
        rng=np.random.default_rng(seed);s=g["session"](rng,sc);c=g["characterize"](rng,s);m=g["model"](c);mm=g["model"](g["mirror_context"](c));_,eq=g["bg_baseline"](c);_,eqm=g["bg_baseline"](g["mirror_context"](c))
        assert np.array_equal(m["ok"],mm["ok"]) and np.allclose(m["beta"],mm["beta"],atol=1e-10) and np.allclose(m["w"],mm["w"],atol=1e-10)
        lim,wlim=g["guardlock"](rng,s,m);lock=calibrate(rng,s,m,eq,wlim,lim);h=dig(lock)
        val=validate(rng,s,m,eq,wlim,lim,lock)
        sessions.append({"scenario":sc,"seed":seed,"qualification":m["q"],"guard":lim,"witness":wlim,"lock":lock,"lock_sha256":h,"validation":val,"training_sha256":ah(c["b"]),"pilot_sha256":ah(c["pilot"]),"heldout_sha256":ah(c["v"])})
        rng=np.random.default_rng(seed+300000)
        for fam in ex["families"]:
            for i in range(ex["per_family"]):
                z=truth(rng,fam);burst=sc in ("TRACKED_BURST","UNTRACKED_BURST","ALIGNED_HIDDEN","REF_LEAK")
                a,r=draw(rng,s,N,burst,z);ha=ah(a);hr=ah(r);k,q,E,D=observed(m,eq,a,r,wlim);kr,qr,Er,Dr=observed(mm,eqm,a[:,::-1],r[:,::-1],wlim)
                assert k==kr and math.isclose(q["E"],qr["E"],rel_tol=1e-9,abs_tol=1e-9) and math.isclose(q["D"],-qr["D"],rel_tol=1e-9,abs_tol=1e-9)
                assert math.isclose(E,Er,rel_tol=1e-9,abs_tol=1e-9) and math.isclose(D,-Dr,rel_tol=1e-9,abs_tol=1e-9)
                assert g["guarded"](q,lim)==g["guarded"](qr,lim)
                aa,bb=lanes(k,q,E,D,lock,lim);ar,br=lanes(kr,qr,Er,Dr,lock,lim)
                u,conf,cfl=fuse(aa,bb,val[k]["allow"]);ur,cr,cf=fuse(ar,br,val[k]["allow"]);flip={"F":"R","R":"F","ABSTAIN":"ABSTAIN"}
                assert all(flip[x]==y for x,y in [(aa,ar),(bb,br),(u,ur),(conf,cr)]) and cfl==cf
                assert aa=="ABSTAIN" or aa==u
                assert q["replay_rmse"]<1e-12 and ah(a)==ha and ah(r)==hr
                rows.append({"scenario":sc,"seed":seed,"family":fam,"index":i,"route":k,"source_sha256":ha,"reference_sha256":hr,"EQ":aa,"CLEAN":bb,"FUSION":u,"CONFIDENCE":conf,"conflict":cfl,"route_validated":val[k]["allow"],"guarded":g["guarded"](q,lim),"raw_candidate_retained":True,"local_evidence":q})
                if i==0:
                    pred=m["beta"]@r;res=a-pred;traces.append({"scenario":sc,"seed":seed,"family":fam,"raw_mean":a.mean(0).tolist(),"prediction_mean":pred.mean(0).tolist(),"residual_mean":res.mean(0).tolist(),"weighted_clean":(m["w"]@res).tolist(),"source_sha256":ha})
                if sc=="IID" and fam in ("double","clipped"):
                    rec.append({"family":fam,"result":g["g"]["g"]["g"]["reconstruct"](a.mean(0),z)})
        assert dig(lock)==h
        print("R15E_SESSION",sc,seed,{k:v["allow"] for k,v in val.items()},flush=True)
def summary(rr):
    o={}
    for k in ("EQ","CLEAN","FUSION","CONFIDENCE"):
        w=[x for x in rr if x["family"].startswith("weak_")];s=[x for x in rr if x["family"].startswith("strong_")];z=[x for x in rr if x["family"].startswith("symmetric") or x["family"]=="noise"]
        def orient(a):return {"n":len(a),"correct":sum(x[k]==x["family"][-1] for x in a),"wrong":sum(x[k] not in ("ABSTAIN",x["family"][-1]) for x in a)}
        o[k]={"weak":orient(w),"strong":orient(s),"null":{"n":len(z),"declared":sum(x[k]!="ABSTAIN" for x in z)}}
        o[k]["paired_EQ_strong_losses"]=sum(x["family"].startswith("strong_") and x["EQ"]==x["family"][-1] and x[k]!=x["family"][-1] for x in rr)
    o.update({"n":len(rr),"conflicts":sum(x["conflict"] for x in rr),"unvalidated":sum(not x["route_validated"] for x in rr),"raw_retained":sum(x["raw_candidate_retained"] for x in rr),"EQ_overwrites":sum(x["EQ"]!="ABSTAIN" and x["FUSION"]!=x["EQ"] for x in rr),"route_counts":dict(collections.Counter(x["route"] for x in rr))})
    return o
def gate(o,sc):
    a=o["FUSION"];b=o["EQ"];w=a["weak"];s=a["strong"];z=a["null"];delta=.10 if sc=="TRACKED_BURST" else -.05 if sc in ("IID","STABLE_REF") else -1.
    return bool((w["correct"]-b["weak"]["correct"])/w["n"]>=delta and w["wrong"]/w["n"]<=.05 and z["declared"]/z["n"]<=.05 and s["correct"]/s["n"]>=.85 and a["paired_EQ_strong_losses"]==0)
by={sc:summary([x for x in rows if x["scenario"]==sc]) for sc in ex["scenarios"]}
per={sc:{str(seed):summary([x for x in rows if x["scenario"]==sc and x["seed"]==seed]) for seed in ex["seeds"]} for sc in ex["scenarios"]}
gates={sc:all(gate(x,sc) for x in per[sc].values()) for sc in ex["scenarios"]}
gates["protected_baseline"]=all(x["EQ_overwrites"]==0 and x["raw_retained"]==x["n"] for x in by.values())
reco={}
for fam in ("double","clipped"):
    a=[x["result"] for x in rec if x["family"]==fam];v=float(np.median([x["selected_rmse"] for x in a]));l=float(np.median([x["hidden_rmse"]["linear"] for x in a]));o=float(np.median([x["old_rmse"] for x in a]))
    reco[fam]={"n":len(a),"R15":v,"linear":l,"R14":o,"gate":v<=l and v<=o}
gates["double_reconstruction"]=reco["double"]["gate"]
# Real acquisition is fail-closed, independent of synthetic gate and no pickle loading.
def fetch(url,cap):
    req=urllib.request.Request(url,headers={"User-Agent":"JANUS R1.5E research data audit"})
    with urllib.request.urlopen(req,timeout=40) as f:
        b=f.read(cap+1);assert len(b)<=cap
        return b,{"url":f.geturl(),"http_status":f.status,"bytes":len(b),"sha256":sha(b)}
real={}
sources=p["real_acquisition"]["sources"];cap=p["real_acquisition"]["cap_bytes"]
try:
    b,meta=fetch(sources[0]["url"],2_000_000);a=list(csv.DictReader(io.StringIO(b.decode("utf-8-sig"))));assert len(a)==83 and all(x.get("tns_name") and x.get("event_id") for x in a)
    real["outrigger_catalog"]={**meta,"status":"CATALOG_ACQUIRED__NOT_WAVEFORM","rows":len(a),"unique_events":len(set(x["event_id"] for x in a)),"candidate_ids":[{"tns_name":x["tns_name"],"event_id":x["event_id"]} for x in a],"paired_waveforms":0}
except Exception as e:real["outrigger_catalog"]={"status":"HOLD_ACQUISITION","error":str(e)[:350]}
try:
    b,meta=fetch(sources[1]["url"],cap)
    with h5py.File(io.BytesIO(b),"r") as f:
        d=f["frb"];w=d["wfall"];assert w.ndim==2 and w.size<=16_000_000
        x=w[:];tt=d["plot_time"][:];ff=d["plot_freq"][:]
        assert x.shape==(len(ff),len(tt)) and np.all(np.isfinite(tt)) and np.all(np.isfinite(ff))
        assert len(tt)>1 and len(ff)>1 and (np.all(np.diff(tt)>0) or np.all(np.diff(tt)<0)) and (np.all(np.diff(ff)>0) or np.all(np.diff(ff)<0))
        finite=np.isfinite(x);assert finite.any()
        real["waterfall"]={**meta,"status":"REAL_PROCESSED_SPECTRUM_ACQUIRED__WITNESS_HOLD","shape":list(x.shape),"finite_fraction":float(finite.mean()),"data_sha256":ah(x),"time_axis_sha256":ah(tt),"frequency_axis_sha256":ah(ff),"frequency_range_MHz":[float(ff.min()),float(ff.max())],"time_axis_range_as_stored":[float(tt.min()),float(tt.max())],"median_time_step_as_stored":float(np.median(np.abs(np.diff(tt)))),"independent_simultaneous_witnesses":0,"raw_voltage":False}
except Exception as e:real["waterfall"]={"status":"HOLD_ACQUISITION_OR_SCHEMA","error":str(e)[:350]}
real["drift"]={"status":"DISCOVERY_ONLY__MATCHED_TIMESTAMPS_AND_SENSOR_IDS_REQUIRED","source":sources[2]["url"]}
real["ecallisto"]={"status":"DISCOVERY_ONLY__CONTACT_HOST_BEFORE_USE","source":sources[3]["url"]}
real["admission"]="HOLD_NO_AUTHENTICATED_PAIRED_SCIENCE_AND_INDEPENDENT_NOISE_WITNESS"
axes=json.loads((R/"data/JANUS-DEEP-ANALYSIS-5D-SPIRAL-ORIGIN-PRIME-ORACLE-PROTOCOL-2026-08-21-v2.1.json").read_text())["five_dimensions"]
state={"known":["R15D measured burst improved but compound gates failed"],"alternatives":["ordinary signal","common noise","gain drift","reference leakage","unmeasured aligned interference","hypothetical carrier"],"gaps":["authenticated simultaneous radio witnesses","carrier coupling","paired UAP"]};turns=[]
for name,delta in [("D1_TEMPORAL",[f"mirrored events {len(rows)}"]),("D2_MIRROR",[f"protected baseline {gates['protected_baseline']}","conflicts retained"]),("D3_HIERARCHY",[f"{k} gate {v}" for k,v in gates.items()]),("D4_INVERSE",["raw and residual alternatives retained","additive replay does not identify latent source"]),("D5_PROVENANCE",[real["outrigger_catalog"]["status"],real["waterfall"]["status"],real["admission"]])]:
    h=dig(state);state={**state,"known":sorted(set(state["known"])|set(delta))};q=dig(state);turns.append({"anchor":name,"axes":axes,"parent":h,"state":q,"delta":delta,"status":"ORIGIN_PRIME" if h!=q else "NO_INFORMATION_GAIN"})
out={"schema":"janus.uap_tachyon.protected_multi_witness.result.v1","status":("SYNTHETIC_GATES_PASS" if all(gates.values()) else "PARTIAL_ENGINEERING_HOLD")+"__REAL_WITNESS_HOLD__PHYSICAL_CAUSALITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":sha(P.read_bytes()),"sessions":sessions,"calibration_events":len(sessions)*len(ex["amplitudes"])*ex["cal_per_amp"],"validation_events":len(sessions)*len(ex["amplitudes"])*ex["validation_per_amp"],"guard_events":len(sessions)*ex["guard_controls"],"eval_events":len(rows),"mirror_pairs":len(rows),"gates":gates,"by_scenario":by,"per_seed":per,"reconstruction":reco,"real_acquisition":real,"rows":rows,"reconstruction_rows":rec,"retained_traces":traces,"origin_prime_turns":turns,"origin_prime":state,"production_changed":False,"actual_vetoes":0,"physical_retrocausality_confirmed":False,"real_radio_groups":0,"external_blind_exam":False}
O.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
print(json.dumps({**{k:v for k,v in out.items() if k not in ("rows","reconstruction_rows","retained_traces","origin_prime_turns","origin_prime","sessions","per_seed","real_acquisition")},"real_acquisition":{k:({a:b for a,b in v.items() if a!="candidate_ids"} if isinstance(v,dict) else v) for k,v in real.items()},"session_summary":[{"scenario":s["scenario"],"seed":s["seed"],"qualification":s["qualification"],"validation":s["validation"]} for s in sessions]},sort_keys=True))
