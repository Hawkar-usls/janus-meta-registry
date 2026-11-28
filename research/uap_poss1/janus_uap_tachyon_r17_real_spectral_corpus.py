#!/usr/bin/env python3
import ast,collections,csv,hashlib,io,json,math,pathlib,re,subprocess,urllib.request,urllib.error
import numpy as np,h5py
from scipy import signal
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.7-REAL-SPECTRAL-CORPUS-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.7-REAL-SPECTRAL-CORPUS-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());c=p["catalog"]
def sha(b):return hashlib.sha256(b).hexdigest()
def ah(a):return sha(np.ascontiguousarray(a).tobytes())
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def read(path):return json.loads((R/path).read_text())
def num(x):
    try:
        f=float(x);return f if math.isfinite(f) and f!=-9999 else None
    except (TypeError,ValueError):return None
def fetch(url,cap,timeout=45):
    req=urllib.request.Request(url,headers={"User-Agent":"JANUS R1.7 scientific archive pilot"})
    with urllib.request.urlopen(req,timeout=timeout) as f:
        b=f.read(cap+1)
        if len(b)>cap:raise ValueError("BYTE_CAP")
        return b,{"requested_url":url,"http_status":f.status,"bytes":len(b),"sha256":sha(b)}
for path,h in p["pins"].items():assert subprocess.check_output(["git","hash-object",path],text=True).strip()==h
r16=read("registry/uap/JANUS-UAP-TACHYON-R1.6-REAL-SPECTRAL-WITNESS-RESULT-2026-11-28-v1.0.json")
assert r16["real"]["sha256"]==c["anchor_sha256"]
# Exact R15 bank and fit functions, excluding synthetic threshold calibration and exam execution.
s=(R/"research/uap_poss1/janus_uap_tachyon_r15_causal_discrimination.py").read_text()
assert s.count("\ncal=[]\n")==1 and s.count("# Reconstruction banks with complementary model families.")==1
g={};exec(compile(s.split("\ncal=[]\n")[0],"<pinned R15 definitions>","exec"),g)
exec(compile(s[s.index("# Reconstruction banks with complementary model families."):s.index("\nrows=[]\n")],"<pinned R15 reconstruction>", "exec"),g)
old=g["old"];banks=g["bank"];t129=g["t"];fit=g["fit"]
def predict(y,b,tr,ev):
    # Held values are zero during fitting; fit's eval error is ignored for final prediction.
    return fit(y,b,tr,ev)
def reconstruct(y):
    n=len(y);t=np.linspace(-1,1,n);gap=np.abs(t)<=.16;obs=~gap
    folds=[(np.abs(t)>=lo)&(np.abs(t)<=hi)&obs for lo,hi in [(.235,.40),(.48,.65)]]
    if gap.sum()<2 or min(v.sum() for v in folds)<2 or obs.sum()<8:return {"status":"HOLD_TOO_FEW_NATIVE_BINS"}
    # No outer held information enters normalization or inner CV.
    mean=float(y[obs].mean());scale=float(np.sqrt(np.mean((y[obs]-mean)**2)))
    if scale<=1e-15:return {"status":"HOLD_DEGENERATE_VISIBLE_SCALE"}
    x=np.zeros(n);x[obs]=(y[obs]-mean)/scale
    bnk={k:np.array([np.interp(t,t129,v) for v in b]) for k,b in banks.items()}
    cv={k:0. for k in ["linear",*bnk]}
    for v in folds:
        tr=obs&~v
        cv["linear"]+=float(np.mean((np.interp(t[v],t[tr],x[tr])-x[v])**2))
        for k,b in bnk.items():cv[k]+=predict(x,b,tr,v)[2]
    chosen=min(cv,key=cv.get)
    cand={"linear":np.interp(t,t[obs],x[obs])}
    for k,b in bnk.items():cand[k]=predict(x,b,obs,gap)[1]
    B,labs,_=old["makebank"](n);l,_,pred,_=old["fits"](x,B,obs,gap);oldloss={};oldpred={}
    for k in "FRS":
        ids=np.flatnonzero(labs==k);best=l[ids].min();tie=ids[np.isclose(l[ids],best,rtol=1e-12,atol=1e-14)]
        oldloss[k]=float(l[tie].mean());oldpred[k]=pred[tie].mean(0)
    prev=min(oldloss,key=oldloss.get)
    # Only now reveal actual held measurements for scoring.
    target=(y[gap]-mean)/scale
    err={k:float(np.sqrt(np.mean((v[gap]-target)**2))) for k,v in cand.items()}
    e14=float(np.sqrt(np.mean((oldpred[prev][gap]-target)**2)))
    return {"status":"EXECUTED","chosen":chosen,"R14_chosen":prev,"cv":cv,"normalized_rmse":err,"selected":err[chosen],"linear":err["linear"],"R14":e14,"raw_selected_rmse":err[chosen]*scale,"raw_linear_rmse":err["linear"]*scale,"raw_R14_rmse":e14*scale,"observed_scale":scale,"held_indices":np.flatnonzero(gap).tolist(),"held_actual":y[gap].tolist(),"held_predictions":{k:(v[gap]*scale+mean).tolist() for k,v in cand.items()},"R14_prediction":(oldpred[prev][gap]*scale+mean).tolist()}
def axis_corr(a,b):
    m=np.isfinite(a)&np.isfinite(b)
    if m.sum()<3 or np.std(a[m])==0 or np.std(b[m])==0:return None
    return float(np.corrcoef(a[m],b[m])[0,1])
def runs(z):
    q=np.flatnonzero(np.diff(np.r_[False,z,False].astype(int)))
    return [[int(a),int(b-a)] for a,b in zip(q[::2],q[1::2])]
def analyze(x,key):
    assert x.ndim==2 and x.size<=c["max_cells"] and x.shape[1]<=c["max_time_samples"]
    h=ah(x);m=np.isfinite(x);mh=ah(m);full=m.all(1);empty=~m.any(1)
    out={"shape":list(x.shape),"sha256":h,"mask_sha256":mh,"finite":int(m.sum()),"cells":int(m.size),"nan":int(np.isnan(x).sum()),"inf":int(np.isinf(x).sum()),"fully_finite_rows":int(full.sum()),"fully_masked_rows":int(empty.sum()),"partial_rows":int((~(full|empty)).sum()),"valid_channels_per_time":m.sum(0).tolist(),"masked_row_runs":runs(empty),"mask_fraction":float(1-m.mean()),"status":"HOLD_NO_FINITE_PROFILE"}
    if full.sum()<32 or x.shape[1]<12:return out
    y=x[full].mean(0);assert np.isfinite(y).all()
    a=old["score"](y);b=old["score"](y[::-1]);flip={"F":"R","R":"F","ABSTAIN":"ABSTAIN"}
    mirror=math.isclose(a["D"],-b["D"],abs_tol=1e-9) and math.isclose(a["Q"],b["Q"],abs_tol=1e-9) and b["decision"]==flip[a["decision"]]
    v=reconstruct(y);vr=reconstruct(y[::-1])
    parity=None
    if v["status"]==vr["status"]=="EXECUTED":
        parity={k:float(np.max(np.abs(np.array(z)-np.array(vr["held_predictions"][k])[::-1]))) for k,z in v["held_predictions"].items()}
    assert ah(x)==h and ah(np.isfinite(x))==mh and ah(x[:,::-1][:,::-1])==h
    out.update(status="EXECUTED",profile=y.tolist(),forward=a,reverse=b,mirror_pass=bool(mirror),reconstruction=v,reconstruction_reverse=vr,reconstruction_mirror_max_abs=parity,original_mask_preserved=True)
    return out
def metadata(rows):
    def med(k):
        a=[num(x.get(k)) for x in rows];a=[x for x in a if x is not None];return float(np.median(a)) if a else None
    name=rows[0]["tns_name"].strip();rep={x.get("repeater_name","").strip() for x in rows};rep={x for x in rep if x.lower() not in ("","-9999","-9999.0","nan","none","null","--","n/a")}
    flags=[num(x.get("excluded_flag")) for x in rows];eligible=all(x==0 for x in flags)
    source="REPEATER:"+sorted(rep)[0] if len(rep)==1 else "EVENT:"+name
    if len(rep)>1:eligible=False
    return {"tns":name,"source":source,"population_eligible":eligible,"excluded_flags":flags,"subrows":len(rows),"snr":med("snr_fitb"),"dm":med("dm_fitb"),"width_s":med("width_fitb"),"scatter_s":med("scat_time"),"flag_fraction":med("flag_frac"),"url":c["archive"]+name+"_waterfall.h5"}
rows=[];manifest=[];catalog={};manifest_hash=None
try:
    b,cat=fetch(c["url"],2000000);assert cat["sha256"]==c["sha256"]
    csvrows=list(csv.DictReader(io.StringIO(b.decode("utf-8-sig"))));assert len(csvrows)==c["rows"]
    by=collections.defaultdict(list)
    for x in csvrows:by[x["tns_name"].strip()].append(x)
    assert len(by)==c["bursts"] and all(re.fullmatch(r"FRB\d{8}[A-Z]+",k) for k in by)
    manifest=[metadata(v) for k,v in sorted(by.items())];groups=collections.defaultdict(list)
    for x in manifest:
        if x["population_eligible"] and x["tns"]!=c["anchor"]:groups[x["source"]].append(x)
    order=sorted(groups,key=lambda k:sha(("R17-v1|"+k).encode()))
    pick={min(groups[k],key=lambda x:sha(("R17-event|"+x["tns"]).encode()))["tns"] for k in order[:c["pilot_sources"]]}
    pick.add(c["anchor"])
    for x in manifest:
        x["selected"]=x["tns"] in pick
        x["split"]="anchor" if x["tns"]==c["anchor"] else "reference" if int(sha(("R17-split|"+x["source"]).encode()),16)%10<7 else "holdout"
    manifest_hash=dig(manifest);pathlib.Path("/tmp/r17-manifest.json").write_text(json.dumps({"sha256":manifest_hash,"manifest":manifest},indent=2)+"\n")
    catalog={**cat,"rows":len(csvrows),"bursts":len(manifest),"eligible_sources":len(groups),"selected":len(pick),"deferred":len(manifest)-len(pick),"status":"PINNED_MANIFEST_LOCKED","manifest_sha256":manifest_hash}
    print("R17_MANIFEST",manifest_hash,len(manifest),len(pick),flush=True)
except Exception as e:catalog={"status":"HOLD_CATALOG","error":repr(e)[:350]}
for x in sorted([z for z in manifest if z["selected"]],key=lambda z:(z["tns"]!=c["anchor"],z["tns"])):
    row={**x,"status":"HOLD_DOWNLOAD","arrays":{}}
    try:
        b,meta=fetch(x["url"],c["max_file_bytes"],60);row.update(meta);row["status"]="DOWNLOADED"
        if x["tns"]==c["anchor"]:assert meta["sha256"]==c["anchor_sha256"]
        with h5py.File(io.BytesIO(b),"r") as h:
            d=h["frb"];name=d.attrs.get("tns_name","")
            if isinstance(name,bytes):name=name.decode()
            assert str(name)==x["tns"]
            t=d["plot_time"][:];f=d["plot_freq"][:];extent=d["extent"][:]
            assert t.ndim==f.ndim==1 and np.isfinite(t).all() and np.isfinite(f).all() and len(t)>1 and np.all(np.diff(t)>0)
            dt=float(np.median(np.diff(t)));row["axis"]={"time_step_as_stored":dt,"time_unit":"ms per current CHIME plotting documentation; historic tutorial label conflict","plot_time_sha256":ah(t),"plot_freq_sha256":ah(f),"extent":extent.tolist(),"calibrated_origin":"UNKNOWN_IF_DIFFERENT_LENGTH","calibrated_cadence":"same dt per provider"}
            row["inventory"]={k:{"shape":list(v.shape),"dtype":str(v.dtype)} for k,v in d.items() if isinstance(v,h5py.Dataset)}
            for key in ("wfall","calibrated_wfall"):
                try:
                    v=d[key];assert v.ndim==2 and v.shape[0]==len(f) and v.size<=c["max_cells"] and v.shape[1]<=c["max_time_samples"]
                    if key=="wfall":assert v.shape[1]==len(t)
                    arr=v[:];z=analyze(arr,key);z["time_origin"]="plot_time" if key=="wfall" else "sample_index_only"
                    if key=="wfall" and "spec" in d and d["spec"].shape==(len(f),):
                        m=np.isfinite(arr);cnt=m.sum(1);a=np.divide(np.where(m,arr,0.).sum(1),cnt,out=np.full(len(f),np.nan),where=cnt>0);sp=d["spec"][:]
                        z["spec_order_corr"]={"stored":axis_corr(a,sp),"reversed":axis_corr(a,sp[::-1])}
                    row["arrays"][key]=z
                except Exception as e:row["arrays"][key]={"status":"HOLD_ARRAY","error":repr(e)[:300]}
        row["status"]="PROCESSED" if any(z["status"]=="EXECUTED" for z in row["arrays"].values()) else "HOLD_NO_ADMITTED_ARRAY"
    except Exception as e:row["error"]=repr(e)[:350]
    rows.append(row);print("R17_FILE",x["tns"],row["status"],{k:v["status"] for k,v in row["arrays"].items()},flush=True)
assert manifest_hash is None or dig(manifest)==manifest_hash
def quant(v):
    return {str(q):float(np.quantile(v,q)) for q in [0,.1,.25,.5,.75,.9,1]} if len(v) else {}
def stats(rs,key):
    a=[r["arrays"][key] for r in rs];d=[z["forward"]["D"] for z in a];q=[z["forward"]["Q"] for z in a]
    return {"n":len(a),"sources":len({r["source"] for r in rs}),"D":quant(d),"absD":quant(np.abs(d)),"Q":quant(q),"decisions":dict(collections.Counter(z["forward"]["decision"] for z in a))}
def band(v,limits):
    return "missing" if v is None else "low" if v<limits[0] else "mid" if v<limits[1] else "high"
dist={};reco={};mirror=[];ranks=[]
for key in ("wfall","calibrated_wfall"):
    rr=[r for r in rows if r["arrays"].get(key,{}).get("status")=="EXECUTED"];mirror.extend(r["arrays"][key]["mirror_pass"] for r in rr)
    pop=[r for r in rr if r["population_eligible"] and r["split"]!="anchor"]
    ref=[r for r in pop if r["split"]=="reference"];test=[r for r in pop if r["split"]=="holdout"]
    assert not ({r["source"] for r in ref}&{r["source"] for r in test})
    dist[key]={"reference":stats(ref,key),"holdout":stats(test,key),"strata":{}}
    for field,lim in [("snr",[20,50]),("dm",[300,800]),("width_s",[.001,.005]),("scatter_s",[.001,.005]),("mask_fraction",[.2,.5])]:
        dist[key]["strata"][field]={k:stats([r for r in ref if band(r["arrays"][key]["mask_fraction"] if field=="mask_fraction" else r[field],lim)==k],key) for k in ("low","mid","high","missing")}
    a=[abs(r["arrays"][key]["forward"]["D"]) for r in ref]
    for r in test:
        d=abs(r["arrays"][key]["forward"]["D"]);ranks.append({"tns":r["tns"],"array":key,"absD":d,"reference_n":len(a),"empirical_upper_rank":(1+sum(v>=d for v in a))/(len(a)+1),"status":"DESCRIPTIVE_ONLY"})
    z=[r["arrays"][key]["reconstruction"] for r in rr if r["arrays"][key]["reconstruction"]["status"]=="EXECUTED"]
    rec={"n":len(z),"chosen":dict(collections.Counter(x["chosen"] for x in z))}
    if z:
        rec.update({k:float(np.median([x[k] for x in z])) for k in ("selected","linear","R14")})
        rec.update(wins_linear=sum(x["selected"]<x["linear"] for x in z),wins_R14=sum(x["selected"]<x["R14"] for x in z))
        rec["gate"]=rec["selected"]<=rec["linear"] and rec["selected"]<=rec["R14"]
    else:rec["gate"]=False
    reco[key]=rec
anchor=next((r for r in rows if r["tns"]==c["anchor"]),{})
gates={"catalog_manifest":catalog["status"]=="PINNED_MANIFEST_LOCKED","anchor_both_arrays":all(anchor.get("arrays",{}).get(k,{}).get("status")=="EXECUTED" for k in ("wfall","calibrated_wfall")),"pilot_coverage":sum(r["status"]=="PROCESSED" for r in rows)>=20,"R14_mirror":bool(mirror) and all(mirror),"mask_preservation":bool(mirror) and all(z.get("original_mask_preserved") for r in rows for z in r["arrays"].values() if z["status"]=="EXECUTED"),"R15_wfall":reco["wfall"]["gate"],"R15_calibrated_wfall":reco["calibrated_wfall"]["gate"],"population_reference_support":all(v["reference"]["sources"]>=100 for v in dist.values())}
axes=read("data/JANUS-DEEP-ANALYSIS-5D-SPIRAL-ORIGIN-PRIME-ORACLE-PROTOCOL-2026-08-21-v2.1.json")["five_dimensions"]
state={"known":["R1.6 real single-site control"],"alternatives":["ordinary burst","scattering","instrument response","dedispersion residual","RFI/mask","unknown interference","hypothetical carrier"],"gaps":["paired site arrays","independent noise witness","carrier coupling","population-sized reference"]};turns=[]
for k,delta in [("D1_TEMPORAL",[f"native profiles {len(mirror)}"]),("D2_MIRROR",[f"R14 mirror {sum(mirror)}/{len(mirror)}","R15 replay parity diagnostic, directional banks retained"]),("D3_INVERSE",[f"{k}: {v}" for k,v in gates.items()]),("D4_ASSOCIATIVE",["source-group split","ordinary asymmetry descriptive only"]),("D5_PROVENANCE",[str(manifest_hash),dig([{"tns":r["tns"],"sha256":r.get("sha256"),"status":r["status"]} for r in rows]),"no independent physical witness"])]:
    h=dig(state);state={**state,"known":sorted(set(state["known"])|set(delta))};q=dig(state);turns.append({"anchor":k,"axes":axes,"parent":h,"state":q,"delta":delta})
out={"schema":"janus.uap_tachyon.real_spectral_corpus.result.v1","status":("REAL_CORPUS_PILOT_EXECUTED" if mirror else "REAL_CORPUS_HOLD")+"__POPULATION_REFERENCE_HOLD__PAIRED_WITNESS_HOLD__PHYSICAL_CAUSALITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":sha(P.read_bytes()),"catalog":catalog,"manifest":manifest,"downloaded":sum("sha256" in r for r in rows),"processed":sum(r["status"]=="PROCESSED" for r in rows),"profiles":len(mirror),"mirror_passed":sum(mirror),"gates":gates,"distribution":dist,"reconstruction":reco,"holdout_ranks":ranks,"rows":rows,"origin_prime_turns":turns,"origin_prime":state,"native_RETINA_calls":0,"real_radio_groups":0,"physical_retrocausality_confirmed":False,"production_changed":False,"external_blind_exam":False,"actual_vetoes":0}
O.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
print(json.dumps({k:v for k,v in out.items() if k not in ("manifest","rows","origin_prime_turns","origin_prime","holdout_ranks")},sort_keys=True))
