import ast,collections,csv,datetime as dt,hashlib,io,itertools,json,math,pathlib,re,subprocess,tempfile,time,urllib.parse,urllib.request,importlib.util,sys
import cv2,numpy as np,sympy as sp
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.8G-PHYSICAL-DISCRIMINATION-CONTRACT-2026-11-28-v1.0.json";O=U/"JANUS-UAP-TACHYON-R1.8G-PHYSICAL-DISCRIMINATION-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());lim={"max_file_bytes":100663296,"timeout_s":35,"transfer_deadline_s":150}
def sha(b):return hashlib.sha256(b).hexdigest()
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def read(path):return json.loads((R/path).read_text())
def quant(v):return {"min":float(np.min(v)),"median":float(np.median(v)),"max":float(np.max(v))} if len(v) else {}
for path,h in p["pins"].items():assert subprocess.check_output(["git","hash-object",path],text=True).strip()==h,(path,h)
a=read("registry/uap/JANUS-UAP-TACHYON-R1.8A-PRIMARY-EVIDENCE-ACQUISITION-RESULT-2026-11-28-v1.0.json");b=read("registry/uap/JANUS-UAP-TACHYON-R1.8B-INSTRUMENTAL-EVIDENCE-RECONSTRUCTION-RESULT-2026-11-28-v1.0.json");f=read("registry/uap/JANUS-UAP-TACHYON-R1.8F-GEOMETRIC-EVIDENCE-SYNTHESIS-RESULT-2026-11-28-v1.0.json")
by={x["id"]:x for x in b["targets"]};meta={x["id"]:x["metadata"] for x in a["targets"]}
def helpers(path,names):
    ns=ast.parse((R/path).read_text());exec(compile(ast.Module(body=[n for n in ns.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),"<pinned helpers>","exec"),globals())
helpers("research/uap_poss1/janus_uap_tachyon_r18a_primary_evidence.py",{"safeurl","download","get","magic"})
helpers("research/uap_poss1/janus_uap_tachyon_r18c_anomalous_track_forensics.py",{"checked_asset","decode","aperture","score"})
g={"np":np,"p":read("registry/uap/JANUS-UAP-TACHYON-R1.4-TEMPORAL-ARROW-CONTRACT-2026-11-28-v1.0.json"),"banks":{}}
ns=ast.parse((R/"research/uap_poss1/janus_uap_tachyon_r14_temporal_arrow.py").read_text());exec(compile(ast.Module(body=[n for n in ns.body if isinstance(n,ast.FunctionDef) and n.name in {"makebank","fits","score"}],type_ignores=[]),"<pinned R14>","exec"),g);cv2.setNumThreads(1)
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,R/path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
ret=load("native_topa_retina","research/uap_poss1/pinned_topa_retina_video.py")
eye=load("native_eye","EYE/r4_1/eye_r4_1_minimum_witness_set_solver.py")
def spectrum(t,y):
    try:y=np.array(y,float);t=np.array(t,float)
    except (ValueError,TypeError):return {"status":"HOLD_MISSING"}
    n=len(y)
    if n<32 or n!=len(t) or not np.isfinite(y).all() or not np.isfinite(t).all():return {"status":"HOLD_LENGTH_OR_MISSING"}
    dd=np.diff(t);d=float(np.median(dd))
    if d<=0 or np.any(dd<=0) or np.max(abs(dd-d))>.01*d:return {"status":"HOLD_CADENCE"}
    k=np.arange(n);z=y-np.polyval(np.polyfit(k,y,1),k)
    if np.std(z)<1e-10:return {"status":"HOLD_CONSTANT"}
    fr=np.fft.rfftfreq(n,d);power=np.abs(np.fft.rfft(z*np.hanning(n)))**2;ix=np.flatnonzero((fr>=1)&(fr<=min(15,.5/d)))
    if not len(ix) or power[ix].sum()<=0:return {"status":"HOLD_BAND"}
    i=ix[np.argmax(power[ix])];return {"status":"DESCRIPTIVE","n":n,"peak_hz":float(fr[i]),"resolution_hz":1/(n*d),"peak_fraction":float(power[i]/power[ix].sum()),"cycles":float(fr[i]*(t[-1]-t[0]))}
def finite(v):
    try:x=float(v);return x if math.isfinite(x) else None
    except (TypeError,ValueError):return None
def chunks(tab):
    v=[];last=None
    for i,y in sorted(tab.items()):
        if y is None or (last is not None and i!=last+1):
            if v:yield v
            v=[]
        if y is not None:v.append((i,y))
        last=i
    if v:yield v
def profiles(tab,d):
    return [{"first":v[0][0],"last":v[-1][0],"spectrum":spectrum(np.arange(129)*d,[y for _,y in v])} for run in chunks(tab) for start in range(0,len(run)-128,129) for v in [run[start:start+129]]]
def pinned(key,path):
    old=next(x for x in a["zenodo"] if x["key"]==key);r=get(old["receipt"]["requested_url"],path,lim["max_file_bytes"]);r["integrity"]=r.get("sha256")==old["receipt"].get("sha256") and r.get("bytes")==old["expected_bytes"] and "md5:"+str(r.get("md5"))==old["expected_md5"];return r
rid="DOW-UAP-PR135";z=by[rid]["analysis"];tr=next(x for x in z["tracks"] if x["track_id"]==56);assert dig(tr["samples"])==tr["samples_sha256"];core=[v for v in tr["samples"] if 692<=v["frame"]<=820];assert len(core)==129
points={};ext=f["PR135"]["track56_extensions"]
for e in ext:
    assert dig(e["samples"])==e["sha256"]
    for v in e["samples"]:points[v["frame"]]={"frame":v["frame"],"x":v["x"],"y":v["y"],"role":"EXTENSION","ncc":v.get("ncc")}
w,h=z["analysis_size"];n=z["frames"]
for v in core:points[v["frame"]]={"frame":v["frame"],"x":v["x_norm"]*w,"y":v["y_norm"]*h,"role":"ORIGINAL_CORE"}
points=[points[i] for i in sorted(points)];assert [v["frame"] for v in points]==list(range(510,839))
lock=dig(points);track={"status":"HOLD","manifest_sha256":lock,"points":points,"identity_authenticated":False};retina={"status":"HOLD","native_bridge_calls":0,"native_vision_calls":0};galileo=[];published=[];receipts=[]
with tempfile.TemporaryDirectory() as td:
    d=pathlib.Path(td);asset=d/"source.mp4";r=checked_asset(rid,asset);track["receipt"]=r
    pts=[]
    try:
        assert r["integrity"] and magic(asset,"video");raw=d/"raw";log=d/"log";pts,hs=decode(asset,raw,log,w,h,n);assert hs==z["decoded_gray_sha256"] and dig(pts)==z["pts_sha256"];frames=np.memmap(raw,dtype=np.uint8,mode="r",shape=(n,h,w));t=[pts[v["frame"]] for v in points];center=np.median([[v["x"],v["y"]] for v in points],axis=0);pol=core[0]["polarity"]
        lanes={};wins=[510,639,692,710]
        for radius in (2,3,5):
            moving=[aperture(frames[v["frame"]],v["x"],v["y"],radius,pol) for v in points];fixed=[aperture(frames[v["frame"]],*center,radius,pol) for v in points]
            lanes[str(radius)]={}
            for name,y in (("moving",moving),("fixed_screen",fixed)):
                ss=[]
                for start in wins:
                    yy=y[start-510:start-510+129];ss.append({"first":start,"last":start+128,"score":score(yy)})
                lanes[str(radius)][name]={"profile":y,"spectrum":spectrum(t,y),"segments":[{"first":l,"last":u,"spectrum":spectrum(t[l-510:u-509],y[l-510:u-509])} for l,u in ((510,691),(692,820),(821,838))],"windows":ss}
        track.update(status="FULL_CANDIDATE_PHOTOMETRY",frame_replay=True,pts=t,lanes=lanes,span_px=float(np.linalg.norm(np.ptp([[v["x"],v["y"]] for v in points],axis=0))),endpoint_stops=[e["stop"] for e in ext]);del frames
    except Exception as e:track["error"]=repr(e)[:300]
    if r.get("integrity"):
        try:
            q=ret.process_video(asset,rid,d/"retina",2.0,30,320,False,"",0);manifest=json.loads((pathlib.Path(q["unit_dir"])/"frame_manifest.json").read_text());retina={"status":"NATIVE_VIDEO_QC_EXECUTED__VISION_HOLD","native_bridge_calls":1,"native_vision_calls":0,"source_sha_match":q["sha256"]==r["sha256"],"sample_frames":q["frame_sample_count"],"contact_sheets":len(q["contact_sheets"]),"frame_records":manifest["frames"],"frame_pts_note":"Native sampler PTS after resampling; not native full-rate PTS.","radio_retina":"HOLD_INCOMPATIBLE_INPUT"}
        except Exception as e:retina["error"]=repr(e)[:300]
    keys=["pr135_lightcurves.csv","pr135_size.csv","galileo_flyers.csv","README.md","reproduce_analysis.py"]+[f"galileo_flyer{i}_series.csv" for i in range(1,6)]
    tables={}
    for key in keys:
        dest=d/"table";rr=pinned(key,dest);receipts.append({"key":key,**rr})
        if rr["integrity"]:tables[key]=dest.read_text(encoding="utf-8-sig")
        dest.unlink(missing_ok=True)
    if pts and "pr135_lightcurves.csv" in tables:
        grp=collections.defaultdict(dict)
        for row in csv.DictReader(io.StringIO(tables["pr135_lightcurves.csv"])):
            i=finite(row.get("frame"));t=finite(row.get("t_s"));v=finite(row.get("flux"));k=row.get("letter")
            if i is None or not i.is_integer() or not 1<=i<=len(pts) or t is None or abs(t-pts[int(i)-1])>.5*np.median(np.diff(pts)):continue
            grp[k][int(i)-1]=v
        for k,v in sorted(grp.items()):
            published.append({"letter":k,"rows":len(v),"windows":profiles(v,float(np.median(np.diff(pts)))),"full_runs":[{"first":run[0][0],"last":run[-1][0],"spectrum":spectrum([pts[i] for i,_ in run],[y for _,y in run])} for run in chunks(v)],"geometry_authenticated":False})
    meta_g=list(csv.DictReader(io.StringIO(tables.get("galileo_flyers.csv",""))))
    for i in range(1,6):
        prefix=f"flyer{i}_";key=next(x["key"] for x in a["zenodo"] if x["key"].startswith(prefix) and x["key"].endswith(".mp4"));clip=d/"control.mp4";r=pinned(key,clip);x={"id":i,"receipt":r,"status":"HOLD"}
        try:
            assert r["integrity"];probe=ret.ffprobe(clip);s=next(v for v in probe["streams"] if v["codec_type"]=="video");w2=320;h2=round(w2*s["height"]/s["width"]);nn=int(s["nb_frames"]);raw=d/"graw";log=d/"glog";pp,hs=decode(clip,raw,log,w2,h2,nn);dd=np.diff(pp);cad=float(np.median(dd));assert cad>0 and np.all(dd>0) and np.max(abs(dd-cad))<=.01*cad
            rows=list(csv.DictReader(io.StringIO(tables[f"galileo_flyer{i}_series.csv"])));assert rows and all(k in rows[0] for k in ("frame","delta","delta_area","delta_sky_plus","delta_sky_minus"))
            series={k:{} for k in ("delta","delta_area","delta_sky_plus","delta_sky_minus")}
            for row in rows:
                v=finite(row["frame"])
                if v is None or not v.is_integer():continue
                j=int(v)
                for k in series:
                    if j in series[k]:raise ValueError("DUPLICATE_FRAME")
                    series[k][j]=finite(row[k])
            keys2=sorted(series["delta"]);assert keys2[-1]-keys2[0]+1<=nn
            # Cadence bound to clip, not claimed absolute frame origin.
            m=next((r for r in meta_g if str(r.get("flyer","")).lower() in (str(i),f"flyer{i}",f"flyer {i}")),None)
            if m is None and len(meta_g)==5:m=meta_g[i-1]
            source_duration=finite(m.get("dur_s")) if m else None;source_frames=finite(m.get("frames")) if m else None
            dur_ok=source_duration is not None and source_frames is not None and abs(source_duration-source_frames*cad)<=max(.15,2*cad)
            x.update(status="CADENCE_LINKED_DIAGNOSTICS" if dur_ok else "HOLD_DECLARED_CADENCE",decoded_frames=nn,dt_s=cad,series_rows=len(rows),source_duration=source_duration,source_frames=source_frames,duration_consistent=dur_ok,absolute_frame_origin_authenticated=False,windows={k:profiles(v,cad) if dur_ok else [] for k,v in series.items()})
            vals=[(series["delta"][j],series["delta_area"][j]) for j in keys2 if series["delta"][j] is not None and series["delta_area"][j] is not None];x["brightness_area_correlation"]=float(np.corrcoef(np.asarray(vals).T)[0,1]) if len(vals)>=32 and min(np.std(vals,axis=0))>1e-10 else None
            raw.unlink();log.unlink()
        except Exception as e:x["error"]=repr(e)[:300]
        galileo.append(x);clip.unlink(missing_ok=True);print("R18G_GALILEO",i,x["status"],flush=True)
# Native witness solver: present evidence nonexclusive; hypothetical tests only under explicitly limited rivals.
causes=["IMAGING_ARTIFACT","ORDINARY_SUBLUMINAL_CARRIER","SPECIFIED_SPACELIKE_CARRIER"]
pairs=list(itertools.combinations(causes,2))
model={"id":"R18G_Prospective_Witnesses","cause_classes":causes,"already_acquired":["PIXEL_PROFILE"],"requirements":{"required_independent_separators_per_pair":2,"unknown_independence_conflicts":True},"tests":[{"id":"PIXEL_PROFILE","available":True,"distinguishes":[],"failure_domains":["same_video"]},{"id":"CALIBRATED_INDEPENDENT_IMAGER","available":False,"distinguishes":[list(pairs[0]),list(pairs[1])],"failure_domains":["independent_imager"],"condition":"common calibrated real-world signal"},{"id":"INDEPENDENT_NONOPTICAL_WITNESS","available":False,"distinguishes":[list(pairs[0]),list(pairs[1])],"failure_domains":["independent_nonoptical"],"condition":"authenticated same carrier, independent calibration"},{"id":"SIGNAL_FRONT_TOF_A","available":False,"distinguishes":[list(pairs[2])],"failure_domains":["clock_path_A"],"condition":"authenticated common front, conservative timing and path; excludes subluminal only under stated model"},{"id":"SIGNAL_FRONT_TOF_B","available":False,"distinguishes":[list(pairs[2])],"failure_domains":["clock_path_B"],"condition":"independent replicate, exclusive specified carrier prediction also required"}]}
def eyesolve(m):
    ca,te,req,ac=eye.parse(m);s=eye.search(ca,te,req,ac);return eye.outputs(pathlib.Path("R18G_declared_model.json"),m,ca,te,req,ac,s)["solver_receipt.json"]
current=eyesolve(model);pros=json.loads(json.dumps(model))
for q in pros["tests"]:q["available"]=True
future=eyesolve(pros);eye_result={"native_calls":2,"model":model,"current":current,"counterfactual":future,"unknown_other_mechanisms_unresolved":True,"counterfactual_not_measurements":True}
# Independent symbolic curvature using diagonal metrics and direct tensor contraction.
def invariants(coords,diag):
    n=len(coords);S=sp.simplify;G=sp.diag(*diag);gi=G.inv()
    C=[[[S(sum(gi[i,k]*(sp.diff(G[k,j],coords[l])+sp.diff(G[k,l],coords[j])-sp.diff(G[j,l],coords[k])) for k in range(n))/2) for l in range(n)] for j in range(n)] for i in range(n)]
    Rm={}
    for i,j,k,l in itertools.product(range(n),repeat=4):
        if k==l:continue
        v=S(sp.diff(C[i][l][j],coords[k])-sp.diff(C[i][k][j],coords[l])+sum(C[i][k][m]*C[m][l][j]-C[i][l][m]*C[m][k][j] for m in range(n)))
        if v!=0:Rm[i,j,k,l]=v
    ric=sp.Matrix(n,n,lambda j,l:S(sum(Rm.get((i,j,i,l),0) for i in range(n))));sc=S(sum(gi[j,j]*ric[j,j] for j in range(n)));kre=S(sum(G[i,i]*gi[j,j]*gi[k,k]*gi[l,l]*v*v for (i,j,k,l),v in Rm.items()))
    return sc,kre
t,x,r,theta,phi,H,M=sp.symbols("t x r theta phi H M",real=True,positive=True);geo=[]
for name,coords,diag,er,ek in [("MINKOWSKI_2D",(t,x),[-1,1],0,0),("EXPANDING_2D",(t,x),[-1,sp.exp(2*H*t)],2*H**2,4*H**4),("MINKOWSKI_SPHERICAL_4D",(t,r,theta,phi),[-1,1,r*r,r*r*sp.sin(theta)**2],0,0),("SCHWARZSCHILD_EXTERIOR",(t,r,theta,phi),[-(1-2*M/r),1/(1-2*M/r),r*r,r*r*sp.sin(theta)**2],0,48*M*M/r**6)]:
    try:
        sr,sk=invariants(coords,diag);geo.append({"id":name,"ricci_scalar":str(sr),"kretschmann":str(sk),"expected_R":str(er),"expected_K":str(ek),"pass":sp.simplify(sr-er)==0 and sp.simplify(sk-ek)==0})
    except Exception as e:geo.append({"id":name,"pass":False,"error":repr(e)[:300]})
gs={"np":np,"math":math,"xs":np.linspace(.025,.975,32),"phase":np.arange(64)/64}
ns=ast.parse((R/"research/uap_poss1/pinned_singularity_r2_source.py").read_text());exec(compile(ast.Module(body=[n for n in ns.body if isinstance(n,ast.FunctionDef) and n.name=="geom"],type_ignores=[]),"<pinned native geom>","exec"),gs);zz=np.zeros((64,32,4));zz[:,:,0]=1;zz[:,:,1]=1.25;native=gs["geom"](4.,3.,zz)["diagnostic"]
geometry={"independent_symbolic_cases":geo,"native_collapse_geom_calls":1,"native_diagnostic":native,"native_domain":"synthetic collapse not UAP; independent evaluator is experimental extension in registry only","weights_changed":False}
axes=read("data/JANUS-DEEP-ANALYSIS-5D-SPIRAL-ORIGIN-PRIME-ORACLE-PROTOCOL-2026-08-21-v2.1.json")["five_dimensions"]
rev=list(reversed(points));state={"candidate_sha256":lock,"alternatives":["screen artifact","ordinary object","association error","unknown physical mechanism","specified hypothetical carrier"],"observations":[]};chain=[]
for axis,value in [(list(axes)[4],dig(track.get("receipt",{}))),(list(axes)[3],dig(eye_result)),(list(axes)[2],dig({"core":129,"extension":200,"identity":False})),(list(axes)[1],dig(track.get("lanes",{}))),(list(axes)[0],dig(rev))]:
    old=dig(state);state={**state,"observations":state["observations"]+[value]};chain.append({"axis":axis,"direction":axes[axis][1],"previous":old,"state":dig(state),"evidence_sha256":value})
spiral={"axes":axes,"turns":chain,"reversed_candidate_sha256":dig(rev),"roundtrip_exact":dig(list(reversed(rev)))==lock,"authority":"reversible representation and provenance chain; not physical retrocausality"}
admission={"D165":"conditional association, no common calibrated signal front","PR135":"pixel-plane photometry only","PR168":"low texture and possible HUD, no calibrated path","necessary":["authenticated same emission and arrival front","independent path and clock calibration","conservative uncertainty bound","carrier-specific exclusive prediction","independent replication"],"criterion":"delta_t + upper timing uncertainty < L_min/c can reject ordinary causal propagation only with authenticated path and association","admitted":0}
gates={"frozen_329":len(points)==329,"frame_replay":track.get("frame_replay",False),"photometry":track["status"]=="FULL_CANDIDATE_PHOTOMETRY","spiral_roundtrip":spiral["roundtrip_exact"],"native_EYE":eye_result["native_calls"]==2 and bool(current["remaining_unresolved_pairs"]),"native_RETINA_video_QC":retina.get("source_sha_match",False) and retina.get("sample_frames",0)>0,"native_RETINA_vision":False,"published_AF":len(published)==6 and all(x["windows"] for x in published),"Galileo_controls":len(galileo)==5 and all(x["status"]=="CADENCE_LINKED_DIAGNOSTICS" and x["windows"]["delta"] for x in galileo),"symbolic_geometry":len(geo)==4 and all(x["pass"] for x in geo),"native_geometry":native["lorentzian_fraction"]==1 and native["null_residual_max"]<1e-12,"physical_admission":False}
out={"schema":"janus.uap_tachyon.physical_discrimination.result.v1","status":"PHYSICAL_DISCRIMINATION_DIAGNOSTICS__OBJECT_IDENTITY_HOLD__PHYSICAL_CAUSALITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":sha(P.read_bytes()),"gates":gates,"track56":track,"reverse_5D":spiral,"native_RETINA":retina,"native_EYE":eye_result,"published_AF":published,"Galileo":galileo,"table_receipts":receipts,"geometry":geometry,"admission":admission,"production_changed":False}
O.write_text(json.dumps(out,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
print(json.dumps({"status":out["status"],"gates":gates,"track56":{k:v for k,v in track.items() if k not in ("points","pts","lanes")}|{"lanes":{k:{a:{b:c for b,c in q.items() if b!="profile"} for a,q in v.items()} for k,v in track.get("lanes",{}).items()}},"native_RETINA":{k:v for k,v in retina.items() if k!="frame_records"},"native_EYE":{"current":current,"counterfactual":future},"published_AF":published,"Galileo":[{k:v for k,v in q.items() if k!="receipt"} for q in galileo],"geometry":geometry,"reverse_5D":spiral,"admission":admission},sort_keys=True))
