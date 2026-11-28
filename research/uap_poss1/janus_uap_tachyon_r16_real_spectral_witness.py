#!/usr/bin/env python3
import ast,collections,concurrent.futures,csv,hashlib,io,json,math,pathlib,subprocess,urllib.request,urllib.parse
import numpy as np,h5py
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.6-REAL-SPECTRAL-WITNESS-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.6-REAL-SPECTRAL-WITNESS-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());s=p["source"];rt=p["retina"];ou=p["outrigger"]
def sha(b):return hashlib.sha256(b).hexdigest()
def ah(a):return sha(np.ascontiguousarray(a).tobytes())
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def git(*a):return subprocess.check_output(["git",*a],text=True).strip()
def clean(x):
    if isinstance(x,np.generic):return clean(x.item())
    if isinstance(x,bytes):return x.decode("utf-8","replace")
    if isinstance(x,np.ndarray):return clean(x.tolist())
    if isinstance(x,(list,tuple)):return [clean(z) for z in x]
    if isinstance(x,dict):return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,float) and not math.isfinite(x):return None
    if x is None or isinstance(x,(float,int,bool,str)):return x
    return str(x)
def fetch(url,cap=2_000_000,timeout=20):
    req=urllib.request.Request(url,headers={"User-Agent":"JANUS R1.6 public scientific data audit"})
    with urllib.request.urlopen(req,timeout=timeout) as f:
        b=f.read(cap+1);assert len(b)<=cap
        # Store stable requested URL, not temporary signed redirect credentials.
        return b,{"requested_url":url,"http_status":f.status,"bytes":len(b),"sha256":sha(b)}
def read(path):return json.loads((R/path).read_text())
assert git("hash-object",p["parent_result"])==p["parent_result_blob"]
prior=read(p["parent_result"]);assert prior["real_acquisition"]["waterfall"]["sha256"]==s["sha256"]
assert git("hash-object",rt["temporal_code"])==rt["temporal_blob"]
nodes=ast.parse((R/rt["temporal_code"]).read_text());names={"makebank","fits","score"}
g={"np":np,"p":read(rt["temporal_contract"]),"banks":{}}
exec(compile(ast.Module(body=[z for z in nodes.body if isinstance(z,ast.FunctionDef) and z.name in names],type_ignores=[]),"<pinned R14 temporal functions>","exec"),g)
def meanmask(x,m,axis):
    count=m.sum(axis=axis);total=np.where(m,x,0.).sum(axis=axis,dtype=float)
    return np.divide(total,count,out=np.full(np.shape(count),np.nan,dtype=float),where=count>0),count
def metric(y,t):
    y=np.asarray(y,float);e=np.r_[y[:6],y[-6:]];e=e[np.isfinite(e)]
    if len(e)<8 or not np.isfinite(y).any():return {"status":"HOLD_INSUFFICIENT_EDGES"}
    base=float(e.mean());rms=float(np.sqrt(np.mean((e-base)**2)));i=int(np.nanargmax(y))
    return {"peak_index":i,"peak_ms":float(t[i]),"baseline":base,"edge_rms":rms,"peak_over_edge_rms":float((y[i]-base)/rms) if rms>0 else None}
def corr(a,b):
    m=np.isfinite(a)&np.isfinite(b)
    if m.sum()<3 or np.std(a[m])==0 or np.std(b[m])==0:return None
    return float(np.corrcoef(a[m],b[m])[0,1])
def maskruns(z):
    q=np.flatnonzero(np.diff(np.r_[False,z,False].astype(int)));return [[int(a),int(b-a)] for a,b in zip(q[::2],q[1::2])]
def inverse(y):
    # Fixed mirrored holdout windows. Model family selection uses observed data only.
    y=np.asarray(y,float);n=len(y);B,labs,_=g["makebank"](n);idx=np.arange(n);gap=((idx>=11)&(idx<16))|((idx>=n-16)&(idx<n-11));tr=~gap
    l,_,pred,_=g["fits"](y,B,tr,gap);out={}
    for k in "FRS":
        ids=np.flatnonzero(labs==k);best=l[ids].min();tie=ids[np.isclose(l[ids],best,rtol=1e-12,atol=1e-14)];z=pred[tie].mean(0)
        out[k]={"observed_mse":float(l[tie].mean()),"held_measured_rmse":float(np.sqrt(np.mean((z[gap]-y[gap])**2))),"replay":z.tolist()}
    z=np.interp(idx,idx[tr],y[tr]);out["linear"]={"held_measured_rmse":float(np.sqrt(np.mean((z[gap]-y[gap])**2))),"replay":z.tolist()}
    best=min(out[k]["observed_mse"] for k in "FRS");out["selected_by_observed_fit"]=[k for k in "FRS" if math.isclose(out[k]["observed_mse"],best,rel_tol=1e-12,abs_tol=1e-14)]
    out["held_indices"]=idx[gap].tolist();return out
def temporal(y):
    if len(y)!=38 or not np.all(np.isfinite(y)):return {"status":"HOLD_MISSING_PROFILE"}
    a=g["score"](y);b=g["score"](y[::-1]);flip={"F":"R","R":"F","ABSTAIN":"ABSTAIN"}
    assert math.isclose(a["D"],-b["D"],abs_tol=1e-10) and math.isclose(a["Q"],b["Q"],abs_tol=1e-10) and b["decision"]==flip[a["decision"]]
    u=inverse(y);v=inverse(y[::-1])
    for k,j in [("F","R"),("R","F"),("S","S"),("linear","linear")]:
        assert np.allclose(u[k]["replay"],v[j]["replay"][::-1],rtol=1e-10,atol=1e-10)
        assert math.isclose(u[k]["held_measured_rmse"],v[j]["held_measured_rmse"],rel_tol=1e-10,abs_tol=1e-10)
    return {"status":"R14_EXECUTED__MORPHOLOGY_ONLY","forward":a,"reverse":b,"inverse":u,"inverse_reverse":v}
def shift(x,f,dm,dt):
    # For positive residual DM, read later low-frequency samples.
    sh=4.148808*dm*((f/1000.)**-2-.8**-2)/dt
    j=np.arange(x.shape[1])[None,:]+sh[:,None];lo=np.floor(j).astype(int);hi=np.ceil(j).astype(int)
    ok=(lo>=0)&(hi<x.shape[1]);r=np.arange(len(f))[:,None]
    u=x[r,np.clip(lo,0,x.shape[1]-1)];v=x[r,np.clip(hi,0,x.shape[1]-1)];ok&=np.isfinite(u)&np.isfinite(v)
    z=np.where(ok,(1-(j-lo))*u+(j-lo)*v,np.nan)
    return meanmask(z,ok,0)
real={}
try:
    b,meta=fetch(s["url"],67_108_864,45);assert meta["sha256"]==s["sha256"] and len(b)==s["bytes"]
    with h5py.File(io.BytesIO(b),"r") as h:
        d=h["frb"];inventory={k:{"shape":list(v.shape),"dtype":str(v.dtype)} for k,v in d.items() if isinstance(v,h5py.Dataset)}
        x=d["wfall"][:];t=d["plot_time"][:];f=d["plot_freq"][:];extent=d["extent"][:];attrs=clean(dict(d.attrs))
        assert list(x.shape)==s["shape"] and ah(x)==s["data_sha256"] and ah(t)==s["time_axis_sha256"] and ah(f)==s["frequency_axis_sha256"]
        spec=d["spec"][:];model=d["model_wfall"][:]
    assert np.all(np.diff(t)>0) and np.all(np.isfinite(f)) and (np.all(np.diff(f)>0) or np.all(np.diff(f)<0))
    m=np.isfinite(x);full=m.all(1);empty=~m.any(1);partial=~(full|empty);rowavg,_=meanmask(x,m,1)
    # imshow default origin upper: first array row nearest extent[3], independently compare spec order.
    assert len(extent)==4 and np.isfinite(extent).all()
    freq=np.sort(f)[::-1] if extent[3]>extent[2] else np.sort(f)
    assert min(abs(freq[0]-extent[3]),abs(freq[-1]-extent[2]))<1.
    aligned_spec={"stored_order_corr":None,"reverse_order_corr":None}
    if spec.ndim==1 and len(spec)==len(f):
        aligned_spec={"stored_order_corr":corr(rowavg,spec),"reverse_order_corr":corr(rowavg,spec[::-1])}
    axis={"extent":extent.tolist(),"row0_MHz":float(freq[0]),"last_row_MHz":float(freq[-1]),"spec_crosscheck":aligned_spec,"time_unit":"ms per current CHIME tutorial; historical label conflicts","dt_ms":float(np.median(np.diff(t))),"interpretation":"Processed dedispersed cutout; row order from official imshow origin/extent; spec correlations diagnostic."}
    assert abs(axis["dt_ms"]-.98304)<1e-5
    mask={"finite_cells":int(m.sum()),"total_cells":int(m.size),"finite_fraction":float(m.mean()),"nan_cells":int(np.isnan(x).sum()),"inf_cells":int(np.isinf(x).sum()),"fully_finite_rows":int(full.sum()),"fully_masked_rows":int(empty.sum()),"partially_masked_rows":int(partial.sum()),"mask_sha256":ah(m),"valid_channels_per_time":m.sum(0).tolist(),"masked_row_runs":maskruns(empty),"catalog_flag_fraction":s["catalog1"]["flag_frac"],"masked_row_fraction":float(empty.mean()),"flag_fraction_agrees_to_rounding":abs(float(empty.mean())-s["catalog1"]["flag_frac"])<=.0005}
    y,c=meanmask(x[full],np.isfinite(x[full]),0);assert full.any() and np.all(np.isfinite(y));before=ah(x)
    bands=[]
    for j in range(4):
        low=400+100*j;high=500+100*j;sel=full&(freq>=low)&(freq<high)
        if sel.any():
            a,_=meanmask(x[sel],np.isfinite(x[sel]),0);bands.append({"band_MHz":[low,high],"channels":int(sel.sum()),"profile":a.tolist(),"metrics":metric(a,t),"temporal":temporal(a)})
        else:bands.append({"band_MHz":[low,high],"channels":0,"status":"HOLD_NO_FINITE_ROWS"})
    coarse,counts=meanmask(x.reshape(64,256,38),m.reshape(64,256,38),1)
    dispersion=[]
    for dm in [-2.,-1.,-.5,-.25,0.,.25,.5,1.,2.]:
        a,w=shift(x,freq,dm,axis["dt_ms"]);a2,w2=shift(x[:,::-1],freq,-dm,axis["dt_ms"])
        assert np.array_equal(w,w2[::-1]) and np.allclose(a,a2[::-1],equal_nan=True,rtol=1e-9,atol=1e-9)
        dispersion.append({"residual_DM":dm,"profile":clean(a),"valid_channels_per_time":w.tolist(),"metrics":metric(a,t),"mirror_pass":True})
    residual={"status":"HOLD_MODEL_DIMENSIONS","shape":list(model.shape)}
    if model.shape==x.shape:
        mm=m&np.isfinite(model);assert mm.any()
        r=x[mm].astype(float)-model[mm].astype(float)
        residual={"status":"DESCRIPTIVE_ARCHIVE_FIT_RESIDUAL_NOT_INDEPENDENT","common_cells":int(mm.sum()),"rmse":float(np.sqrt(np.mean(r*r))),"median":float(np.median(r)),"mad":float(np.median(np.abs(r-np.median(r)))),"model_sha256":ah(model),"residual_sha256":ah(r)}
    assert ah(x)==before and ah(x[:,::-1][:,::-1])==before
    real={**meta,"status":"REAL_PROCESSED_SPECTRAL_CONTROL_EXECUTED","dataset_inventory":inventory,"attrs":attrs,"axis":axis,"mask":mask,"native_RETINA":{"status":"HOLD_ROLE_CONTRACT","required_roles":["ON","OFF","REPEAT_ON","REPEAT_OFF"],"actual":"one processed FRB intensity spectrum","native_calls":0},"temporal_RETINA":temporal(y),"full_profile":y.tolist(),"profile_metrics":metric(y,t),"time_ms":t.tolist(),"bands":bands,"coarse_waterfall":clean(coarse),"coarse_valid_counts":counts.tolist(),"residual_dispersion":dispersion,"archive_model_residual":residual,"independent_witnesses":0,"raw_voltage":False,"catalog1":s["catalog1"]}
except Exception as e:
    real={"status":"HOLD_REAL_CONTROL","error":repr(e)[:500]}
print("R16_REAL",real["status"],flush=True)
# Exact cross-catalog name match and bounded per-event data discovery.
def norm(v):return "".join(str(v).upper().split()).removeprefix("FRB")
def file_links(x,path=""):
    out=[]
    if isinstance(x,dict):
        for k,v in x.items():out+=file_links(v,path+"/"+str(k))
    elif isinstance(x,list):
        for i,v in enumerate(x):out+=file_links(v,path+"/"+str(i))
    elif isinstance(x,str) and x.startswith("https://"):
        u=urllib.parse.urlsplit(x);low=u.path.lower()
        if low.endswith((".h5",".hdf5",".fits",".fit",".fil",".npz",".npy",".msgpack",".uvfits")) or any(z in path.lower() for z in ("baseband","visibility","raw_data","waveform","waterfall_file")):
            # Do not record query strings or temporary auth tokens.
            out.append({"field":path,"url":urllib.parse.urlunsplit((u.scheme,u.netloc,u.path,"",""))})
    return out
def inspect_event(row):
    name=row["tns_name"];url=ou["api"]+"/catalogs/outriggers1/bursts/"+urllib.parse.quote(name,safe="")
    try:
        b,meta=fetch(url,500_000,12);j=json.loads(b)
        return {"tns_name":name,"event_id":row["event_id"],"status":"DETAIL_READ","sha256":meta["sha256"],"keys":sorted(j.keys()),"plot_keys":[str(x.get("key")) for x in j.get("plots",[]) if isinstance(x,dict)],"potential_data_links":file_links(j)}
    except Exception as e:return {"tns_name":name,"event_id":row["event_id"],"status":"HOLD_DETAIL","error":repr(e)[:220]}
search={}
try:
    b,meta=fetch(ou["csv"]);assert meta["sha256"]==ou["sha256"];rows=list(csv.DictReader(io.StringIO(b.decode("utf-8-sig"))));assert len(rows)==ou["expected_rows"] and len({r["event_id"] for r in rows})==83
    search={"status":"CATALOG_HASH_MATCH","catalog":meta,"candidates":len(rows)}
    hits=[];pages=[];url=ou["api"]+"/catalogs/catalog2/bursts?version="+ou["catalog2_version"]+"&per_page=1000";idx={};seen=set()
    try:
        for i in range(10):
            if not url:break
            url=urllib.parse.urljoin(ou["api"]+"/",url);assert urllib.parse.urlsplit(url).netloc=="chime-frb.ca" and url not in seen;seen.add(url)
            bb,mm=fetch(url,12_000_000);jj=json.loads(bb);pages.append(mm)
            for r in jj["rows"]:idx.setdefault(norm(r["tns_name"]),[]).append(r)
            url=jj["links"]["next"]
        assert not url
        for row in rows:
            rr=idx.get(norm(row["tns_name"]),[])
            if rr:hits.append({"tns_name":row["tns_name"],"outrigger_event_id":row["event_id"],"catalog2_rows":len(rr),"catalog2_event_ids":[str(r.get("event_id")) for r in rr]})
        search["catalog2_join"]={"status":"EXACT_NAME_JOIN_EXECUTED","pages":pages,"matched_events":len(hits),"matches":hits,"waveform_pairs":0}
    except Exception as e:search["catalog2_join"]={"status":"HOLD_JOIN","pages":pages,"error":repr(e)[:250]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:details=list(pool.map(inspect_event,rows))
    search["details"]=details;search["details_read"]=sum(r["status"]=="DETAIL_READ" for r in details);search["details_failed"]=83-search["details_read"];search["events_with_potential_data_links"]=sum(bool(r.get("potential_data_links")) for r in details)
    search["admission"]="HOLD_NO_VERIFIED_PAIRED_ARRAYS";search["admitted_pairs"]=0
except Exception as e:search={"status":"HOLD_CATALOG","error":repr(e)[:400],"admitted_pairs":0}
print("R16_OUTRIGGER",search.get("status"),search.get("details_read"),flush=True)
axes=read("data/JANUS-DEEP-ANALYSIS-5D-SPIRAL-ORIGIN-PRIME-ORACLE-PROTOCOL-2026-08-21-v2.1.json")["five_dimensions"]
state={"known":["R15E acquired single-site processed FRB and 83-event catalog"],"alternatives":["ordinary astrophysical pulse","dedispersion residual","channel mask/RFI","instrument response","unmeasured noise","hypothetical carrier"],"gaps":["paired CHIME/KKO time aligned arrays","independent noise witness","calibrated carrier coupling","paired UAP"]};turns=[]
for anchor,delta in [("D1_TEMPORAL",[real["status"],"time unit documented; processed not raw"]),("D2_MIRROR",["native RETINA roles not admissible",real.get("temporal_RETINA",{}).get("status","HOLD")]),("D3_INVERSE",["held measured bins, not latent truth","archive model residual descriptive",str(real.get("mask",{}).get("flag_fraction_agrees_to_rounding"))]),("D4_ASSOCIATIVE",[search["status"],f"detail endpoints read {search.get('details_read',0)}"]),("D5_PROVENANCE",["source hashes frozen","no authenticated paired arrays","no exclusive carrier evidence"])]:
    h=dig(state);state={**state,"known":sorted(set(state["known"])|set(delta))};v=dig(state);turns.append({"anchor":anchor,"axes":axes,"parent":h,"state":v,"delta":delta,"status":"ORIGIN_PRIME" if h!=v else "NO_INFORMATION_GAIN"})
out={"schema":"janus.uap_tachyon.real_spectral_witness.result.v1","status":("REAL_SINGLE_SITE_CONTROL_EXECUTED" if real["status"]=="REAL_PROCESSED_SPECTRAL_CONTROL_EXECUTED" else "REAL_CONTROL_HOLD")+"__PAIRED_WITNESS_HOLD__PHYSICAL_CAUSALITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":sha(P.read_bytes()),"real":real,"outrigger_search":search,"origin_prime_turns":turns,"origin_prime":state,"real_single_site_controls":int(real["status"]=="REAL_PROCESSED_SPECTRAL_CONTROL_EXECUTED"),"real_radio_groups":0,"external_blind_exam":False,"physical_retrocausality_confirmed":False,"production_changed":False,"actual_vetoes":0}
O.write_text(json.dumps(clean(out),indent=2,allow_nan=False)+"\n")
summary={k:v for k,v in real.items() if k in ("status","error","axis","mask","profile_metrics","archive_model_residual","native_RETINA","dataset_inventory")}
if "mask" in summary:summary["mask"]={k:v for k,v in summary["mask"].items() if k!="masked_row_runs"}
if "temporal_RETINA" in real:summary["temporal"]={k:v for k,v in real["temporal_RETINA"].items() if k in ("status","forward","reverse")}
if "residual_dispersion" in real:summary["residual_dispersion"]=[{"residual_DM":r["residual_DM"],"metrics":r["metrics"]} for r in real["residual_dispersion"]]
if "bands" in real:summary["bands"]=[{k:v for k,v in r.items() if k in ("band_MHz","channels","metrics","status")} for r in real["bands"]]
print(json.dumps(clean({"status":out["status"],"real":summary,"outrigger":{k:v for k,v in search.items() if k not in ("details","catalog2_join")},"catalog2_join":{k:v for k,v in search.get("catalog2_join",{}).items() if k not in ("matches","pages")}}),sort_keys=True))
