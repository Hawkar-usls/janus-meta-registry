#!/usr/bin/env python3
import ast,collections,csv,datetime as dt,hashlib,io,json,math,pathlib,re,subprocess,tempfile,time,urllib.parse,urllib.request
import cv2,numpy as np
from pypdf import PdfReader
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.8C-ANOMALOUS-TRACK-FORENSICS-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.8C-ANOMALOUS-TRACK-FORENSICS-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());lim={"max_file_bytes":100663296,"timeout_s":35,"transfer_deadline_s":150}
def sha(b):return hashlib.sha256(b).hexdigest()
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def read(path):return json.loads((R/path).read_text())
def quant(v):return {"min":float(np.min(v)),"median":float(np.median(v)),"max":float(np.max(v))} if len(v) else {}
for path,h in p["pins"].items():assert subprocess.check_output(["git","hash-object",path],text=True).strip()==h
a=read("registry/uap/JANUS-UAP-TACHYON-R1.8A-PRIMARY-EVIDENCE-ACQUISITION-RESULT-2026-11-28-v1.0.json");b=read("registry/uap/JANUS-UAP-TACHYON-R1.8B-INSTRUMENTAL-EVIDENCE-RECONSTRUCTION-RESULT-2026-11-28-v1.0.json")
by={x["id"]:x for x in b["targets"]};meta={x["id"]:x["metadata"] for x in a["targets"]}
src=ast.parse((R/"research/uap_poss1/janus_uap_tachyon_r18a_primary_evidence.py").read_text());exec(compile(ast.Module(body=[n for n in src.body if isinstance(n,ast.FunctionDef) and n.name in {"safeurl","download","get","magic"}],type_ignores=[]),"<parent download helpers>","exec"))
g={"np":np,"p":read("registry/uap/JANUS-UAP-TACHYON-R1.4-TEMPORAL-ARROW-CONTRACT-2026-11-28-v1.0.json"),"banks":{}}
ns=ast.parse((R/"research/uap_poss1/janus_uap_tachyon_r14_temporal_arrow.py").read_text());exec(compile(ast.Module(body=[n for n in ns.body if isinstance(n,ast.FunctionDef) and n.name in {"makebank","fits","score"}],type_ignores=[]),"<pinned R14>","exec"),g);cv2.setNumThreads(1)
def score(y):
    y=np.asarray(y,float)
    if len(y)!=129 or not np.all(np.isfinite(y)) or np.std(y)<=1e-12:return {"decision":"HOLD"}
    s=g["score"](y);r=g["score"](y[::-1]);s["mirror"]=bool(abs(s["D"]+r["D"])<1e-9 and abs(s["Q"]-r["Q"])<1e-9 and {"F":"R","R":"F","ABSTAIN":"ABSTAIN"}[s["decision"]]==r["decision"]);return s
manifest=[]
for rid,tid,start,h in p["windows"]:
    tr=next(t for t in by[rid]["analysis"]["tracks"] if t["track_id"]==tid)
    assert tr["samples_sha256"]==h and dig(tr["samples"])==h
    old=next(w for w in tr["temporal_windows"] if w["start_frame"]==start);assert old["forward"]["decision"]=="R"
    s=[v for v in tr["samples"] if start<=v["frame"]<start+129];assert [v["frame"] for v in s]==list(range(start,start+129))
    manifest.append({"id":rid,"track":tid,"start":start,"sample_sha256":dig(s),"samples":s,"previous":old["forward"]})
assert len(manifest)==sum(w["forward"]["decision"]=="R" for x in b["targets"] if x["kind"]=="video" for t in x["analysis"]["tracks"] for w in t["temporal_windows"])==7
lock=dig([{k:v for k,v in x.items() if k!="samples"} for x in manifest])
def hud(x,y,w,h):return (x/w<.18 and y/h<.20) or (abs(x/w-.5)<.045 and abs(y/h-.5)<.085)
def mask_for(shape,xy):
    h,w=shape;yy,xx=np.indices(shape);m=(xx>=.06*w)&(xx<.94*w)&(yy>=.06*h)&(yy<.94*h)&~((xx/w<.18)&(yy/h<.20))&~((abs(xx/w-.5)<.045)&(abs(yy/h-.5)<.085))
    m&=(xx-xy[0])**2+(yy-xy[1])**2>24**2
    return m.astype(np.uint8)*255
def register(ref,cur,xy):
    pts=cv2.goodFeaturesToTrack(ref,maxCorners=300,qualityLevel=.01,minDistance=5,mask=mask_for(ref.shape,xy))
    if pts is None or len(pts)<30:return None,{"reason":"LOW_TEXTURE","points":0 if pts is None else len(pts)}
    f,st,_=cv2.calcOpticalFlowPyrLK(ref,cur,pts,None); 
    if f is None:return None,{"reason":"LK_FAIL"}
    back,st2,_=cv2.calcOpticalFlowPyrLK(cur,ref,f,None)
    if back is None:return None,{"reason":"LK_BACK_FAIL"}
    v=(st.ravel()>0)&(st2.ravel()>0)&(np.linalg.norm(back[:,0]-pts[:,0],axis=1)<=1.0)
    x=pts[:,0][v];y=f[:,0][v];ix=np.flatnonzero(v);train=ix%2==0;test=~train
    if train.sum()<12 or test.sum()<8:return None,{"reason":"INSUFFICIENT_SPLIT","train":int(train.sum()),"test":int(test.sum())}
    M,ins=cv2.estimateAffinePartial2D(y[train],x[train],method=cv2.RANSAC,ransacReprojThreshold=1.5,maxIters=2000,confidence=.99,refineIters=10)
    if M is None:return None,{"reason":"FIT_FAIL"}
    pred=y[test]@M[:,:2].T+M[:,2];err=np.linalg.norm(pred-x[test],axis=1);scale=math.hypot(M[0,0],M[0,1]);angle=math.degrees(math.atan2(M[1,0],M[0,0]));trans=float(np.linalg.norm(M[:,2]));n=int(ins.sum());frac=n/int(train.sum());med=float(np.median(err))
    q={"inliers":n,"fraction":frac,"test_n":int(test.sum()),"test_residual_px":med,"scale":scale,"rotation_deg":angle,"translation_px":trans}
    if n<12 or frac<.6 or med>1.5 or not .95<=scale<=1.05 or abs(angle)>5 or trans>30:q["reason"]="VALIDATION_FAIL";return None,q
    return M,q
def aperture(img,x,y,r,pol):
    h,w=img.shape;yy,xx=np.ogrid[:h,:w];d=(xx-x)**2+(yy-y)**2;core=d<=r*r;ring=(d>=(2*r)**2)&(d<=(3*r+1)**2)
    if not core.any() or not ring.any() or min(x,y,w-1-x,h-1-y)<3*r+1:return None
    return float(pol*(img[core].mean()-img[ring].mean()))
def control():
    rng=np.random.default_rng(181803);r=rng.integers(20,220,(180,320),dtype=np.uint8);r=cv2.GaussianBlur(r,(3,3),0);M=np.float32([[1,0,5],[0,1,-3]]);c=cv2.warpAffine(r,M,(320,180),borderMode=cv2.BORDER_REFLECT);q,detail=register(r,c,(160,90));err=None if q is None else float(np.max(np.abs(q-np.float32([[1,0,-5],[0,1,3]]))))
    static_span=math.hypot(np.ptp([160.]*129),np.ptp([90.]*129))
    return {"translation":{"detail":detail,"matrix":None if q is None else q.tolist(),"max_matrix_error":err,"pass":err is not None and err<=.5},"static_screen":{"span_px":static_span,"pass":static_span<=2 and hud(160,90,320,180)}}
controls=control();receipts=[];rows=[];zen=[];comparison=[];docs={}
def checked_asset(rid,path):
    m=meta[rid];x=get(m["hostedUrl"],path,lim["max_file_bytes"]);x["integrity"]=x.get("sha256")==m["sha256"] and x.get("bytes")==m["bytes"] and x.get("sha256")==by[rid]["receipt"].get("sha256")
    return x
def decode(path,raw,log,w,h,n):
    cmd=["ffmpeg","-hide_banner","-nostdin","-loglevel","info","-threads","1","-i",str(path),"-map","0:v:0","-an","-sn","-vf",f"scale={w}:{h}:flags=area,format=gray,showinfo","-fps_mode","passthrough","-frames:v",str(n+1),"-f","rawvideo","-pix_fmt","gray","-y",str(raw)]
    with log.open("wb") as e:subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=e,check=True,timeout=240)
    assert raw.stat().st_size==n*w*h;pts=[float(x) for x in re.findall(r"\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:\s*([-+0-9.eE]+)",log.read_text(errors="replace"))][:n];assert len(pts)==n
    hsh=hashlib.sha256()
    with raw.open("rb") as f:
        for c in iter(lambda:f.read(1024*1024),b""):hsh.update(c)
    return pts,hsh.hexdigest()
def exam_window(frames,pts,x,w,h):
    s=x["samples"];xy=np.asarray([[v["x_norm"]*w,v["y_norm"]*h] for v in s]);pol=s[0]["polarity"];start=x["start"];ref=np.asarray(frames[start]).copy();center=np.median(xy,axis=0);span=float(np.linalg.norm(np.ptp(xy,axis=0)));reg=[];rawcur={r:[] for r in (2,3,5)};stabcur={r:[] for r in (2,3,5)};fixed={r:[] for r in (2,3,5)}
    replay=score([v["contrast_gray"] for v in s]);assert replay["decision"]=="R" and abs(replay["D"]-x["previous"]["D"])<1e-9 and abs(replay["Q"]-x["previous"]["Q"])<1e-9
    for i,(cx,cy) in enumerate(xy):
        im=np.asarray(frames[start+i]);M=np.eye(2,3,dtype=float) if i==0 else None;q={"reference":True} if i==0 else {}
        if i:M,q=register(ref,im,xy[0])
        reg.append({"frame":start+i,"valid":M is not None,"detail":q,"matrix":None if M is None else M.tolist()})
        for r in rawcur:
            rawcur[r].append(aperture(im,cx,cy,r,pol));fixed[r].append(aperture(im,*center,r,pol))
        if M is not None:
            warped=cv2.warpAffine(im,M,(w,h),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=0);z=M[:,:2]@np.asarray([cx,cy])+M[:,2]
            for r in rawcur:stabcur[r].append(aperture(warped,*z,r,pol))
        else:
            for r in rawcur:stabcur[r].append(None)
    good=sum(z["valid"] for z in reg);hud_fraction=float(np.mean([hud(cx,cy,w,h) for cx,cy in xy]));lanes={}
    for r in rawcur:
        lanes[str(r)]={"raw":score(rawcur[r]),"stabilized":score(stabcur[r]),"fixed_screen":score(fixed[r]),"raw_profile":rawcur[r],"stabilized_profile":stabcur[r],"fixed_screen_profile":fixed[r]}
    robust=good==129 and hud_fraction==0 and span>2 and all(v["raw"]["decision"]==v["stabilized"]["decision"]=="R" for v in lanes.values())
    return {**{k:v for k,v in x.items() if k!="samples"},"prior_replay":replay,"pts_match":all(abs(pts[start+i]-v["pts_s"])<1e-7 for i,v in enumerate(s)),"screen_span_px":span,"possible_HUD_fraction":hud_fraction,"static_screen_candidate":span<=2,"registration_valid":good,"registration":reg,"photometry":lanes,"status":"ROBUST_PIXEL_MORPHOLOGY_CANDIDATE" if robust else "NOT_ROBUST_OR_HOLD","physical_claim":False}
with tempfile.TemporaryDirectory() as td:
    d=pathlib.Path(td)
    for rid in ("DOW-UAP-PR168","DOW-UAP-PR135"):
        f=d/"asset";r=checked_asset(rid,f);x={"id":rid,"receipt":r,"status":"HOLD"}
        try:
            assert r["integrity"] and magic(f,"video");z=by[rid]["analysis"];w,h=z["analysis_size"];n=z["frames"];raw=d/"raw";log=d/"log";pts,hs=decode(f,raw,log,w,h,n);x.update(gray_sha256=hs,frame_sha_match=hs==z["decoded_gray_sha256"],pts_sha_match=dig(pts)==z["pts_sha256"]);assert x["frame_sha_match"] and x["pts_sha_match"]
            frames=np.memmap(raw,dtype=np.uint8,mode="r",shape=(n,h,w))
            for v in manifest:
                if v["id"]!=rid:continue
                try:rows.append(exam_window(frames,pts,v,w,h))
                except Exception as e:rows.append({**{k:u for k,u in v.items() if k!="samples"},"status":"HOLD_ANALYSIS","error":repr(e)[:300]})
            del frames;raw.unlink();log.unlink();x["status"]="EXECUTED"
        except Exception as e:x["error"]=repr(e)[:400]
        receipts.append(x);f.unlink(missing_ok=True);print("R18C_VIDEO",rid,x["status"],flush=True)
    # Independent fetch of the already pinned published derived tables, not independent observations.
    zdata={}
    for key in ("README.md","pr135_tracks.csv","pr135_lightcurves.csv","SHA256SUMS"):
        old=next(v for v in a["zenodo"] if v["key"]==key);f=d/"z";r=get(old["receipt"]["requested_url"],f,4000000);ok=r.get("sha256")==old["receipt"].get("sha256") and "md5:"+str(r.get("md5"))==old["expected_md5"] and r.get("bytes")==old["expected_bytes"];x={"key":key,"receipt":r,"integrity":ok}
        if ok:
            t=f.read_text(encoding="utf-8-sig");zdata[key]=t
            if key.endswith(".csv"):
                rr=csv.DictReader(io.StringIO(t));x["headers"]=rr.fieldnames;x["rows"]=sum(1 for _ in rr)
        zen.append(x);f.unlink(missing_ok=True)
    # Schema-specific diagnostics only, no assumed match when index or coordinate convention is unspecified.
    if "pr135_tracks.csv" in zdata:
        rr=csv.DictReader(io.StringIO(zdata["pr135_tracks.csv"]));tab=list(rr);hdr=rr.fieldnames or [];norm={k.lower().strip():k for k in hdr}
        fcol=next((norm[k] for k in ("frame","frame_idx","frame_index","frame_number") if k in norm),None);xc=next((norm[k] for k in ("x","cx","x_px","centroid_x","x_pixel") if k in norm),None);yc=next((norm[k] for k in ("y","cy","y_px","centroid_y","y_pixel") if k in norm),None);tc=next((norm[k] for k in ("object","target","track","track_id","object_id","target_id") if k in norm),None)
        for v in manifest:
            if v["id"]!="DOW-UAP-PR135":continue
            x={"id":v["id"],"track":v["track"],"start":v["start"],"columns":{"frame":fcol,"x":xc,"y":yc,"target":tc},"status":"HOLD_SCHEMA_OR_GEOMETRY","diagnostic":[]}
            if fcol and xc and yc:
                groups=collections.defaultdict(dict)
                for q in tab:
                    try:
                        z=[float(q[k]) for k in (fcol,xc,yc)]
                        if not all(map(math.isfinite,z)) or not z[0].is_integer():continue
                        k=q[tc] if tc else "UNLABELLED";i=int(z[0]);groups[k].setdefault(i,[]).append(z[1:])
                    except (ValueError,TypeError):continue
                for off in (0,1):
                    for scale in ((1280,720),(320,180)):
                        for k,rows2 in groups.items():
                            ds=[]
                            for s in v["samples"]:
                                q=rows2.get(s["frame"]+off,[])
                                if len(q)==1:ds.append(math.hypot(q[0][0]/scale[0]-s["x_norm"],q[0][1]/scale[1]-s["y_norm"]))
                            if ds:x["diagnostic"].append({"index_offset_hypothesis":off,"source_size_hypothesis":list(scale),"published_track_label":str(k)[:80],"overlap":len(ds),"normalized_distance":quant(ds)})
                if x["diagnostic"]:x["status"]="DIAGNOSTIC_ONLY__INDEX_AND_GEOMETRY_NOT_AUTHENTICATED"
            comparison.append(x)
    for rid in ("DOW-UAP-D165","DOW-UAP-D172"):
        f=d/"pdf";r=checked_asset(rid,f);x={"receipt":r,"status":"HOLD"}
        try:
            assert r["integrity"] and magic(f,"document");pdf=PdfReader(str(f))
            if pdf.is_encrypted and not pdf.decrypt(""):raise ValueError("PASSWORD_REQUIRED")
            pages=[z.extract_text() or "" for z in pdf.pages];x["pages"]=len(pages);x["page_sha256"]=[sha(t.encode()) for t in pages]
            if rid.endswith("D165"):
                t=" ".join(pages[0].replace("–","-").replace("−","-").split());checks={"eight_detections":r"(?:eight|8)\s+detections","duration_84":r"84\s*seconds","altitude_lower":r"55,?000","altitude_upper":r"70,?000","distance_38_5":r"38\.5\s*miles","speed_1650":r"1,?650\s*mph","bearing_39":r"39\s*(?:°|degrees?)","after_48":r"48\s*seconds","sweep_12":r"12[- ]second","single_object_conditional":r"(?:if associated with a single object|same object)","continuous_track_limit":r"(?:not sufficient|not a reconstructed trajectory|continuous track)"}
                x["source_assertions"]={k:bool(re.search(v,t,re.I)) for k,v in checks.items()};x["conditional_reconstruction"]={"distance_miles":38.5,"duration_s":84,"computed_mph":38.5*3600/84,"computed_km_h":38.5*1.609344*3600/84,"assumption":"all eight detections share one object; not established","speed_authority":"conditional report estimate, not measured continuous velocity","missing":["individual calibrated radar detections","absolute timestamps","covariance","association and sensor provenance"]};x["catalog_date"]=meta[rid].get("incidentDate");x["reported_year"]=2023;x["status"]="CONTEXT_CHECKED__TRACK_IDENTITY_HOLD"
            else:
                pages_tag=[];refs=collections.defaultdict(list)
                for i,t in enumerate(pages):
                    tags=[k for k,pat in {"radar":"radar|azimuth|elevation","radio":"radio frequency|radio signal|electromagnetic","timing":"timestamp|time of flight|clock|delay","calibration":"calibrat|uncertaint|accuracy"}.items() if re.search(pat,t,re.I)]
                    if tags:pages_tag.append({"page":i+1,"tags":tags,"sha256":sha(t.encode())})
                    for m in re.finditer(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+",t,re.I):refs["DOI:"+m.group().rstrip(".,;)]")].append(i+1)
                    for m in re.finditer(r"\barXiv\s*:\s*(\d{4}\.\d{4,5}(?:v\d+)?)",t,re.I):refs["ARXIV:"+m.group(1)].append(i+1)
                verified=[];x["reference_candidates"]=len(refs);x["technical_pages"]=pages_tag
                for i,(ref,pg) in enumerate(sorted(refs.items())[:20]):
                    url="https://api.crossref.org/works/"+urllib.parse.quote(ref[4:],safe="/") if ref.startswith("DOI:") else "https://arxiv.org/abs/"+ref[6:];tmp=d/"ref";v=get(url,tmp,3000000);z={"reference":ref,"pages":sorted(set(pg)),"receipt":v,"claim_verified":False}
                    if v["status"]=="ACQUIRED" and ref.startswith("DOI:"):
                        try:
                            md=json.loads(tmp.read_text())["message"];z["bibliographic_match"]=md.get("DOI","").lower()==ref[4:].lower();z["title"]=md.get("title",[])[:1]
                        except Exception as e:z["parse_error"]=repr(e)[:200]
                    verified.append(z);tmp.unlink(missing_ok=True)
                x["references"]=verified;x["status"]="TECHNICAL_CITATION_DISCOVERY__PRIMARY_MEASUREMENT_HOLD"
        except Exception as e:x["error"]=repr(e)[:400]
        docs[rid]=x;f.unlink(missing_ok=True);print("R18C_DOCUMENT",rid,x["status"],flush=True)
gates={"seven_frozen":len(manifest)==7,"video_integrity_and_replay":len(receipts)==2 and all(x["status"]=="EXECUTED" for x in receipts),"all_windows_examined":len(rows)==7 and all("photometry" in x and x["pts_match"] for x in rows),"registration_positive":controls["translation"]["pass"],"static_screen_control":controls["static_screen"]["pass"],"zenodo_integrity":len(zen)==4 and all(x["integrity"] for x in zen),"D165_context":all(docs.get("DOW-UAP-D165",{}).get("source_assertions",{}).values()) and len(docs.get("DOW-UAP-D165",{}).get("source_assertions",{}))==11,"BAASS_reference_discovery":docs.get("DOW-UAP-D172",{}).get("status")=="TECHNICAL_CITATION_DISCOVERY__PRIMARY_MEASUREMENT_HOLD"}
state={"alternatives":["screen overlay","camera motion","local brightness","ordinary object","association error","unidentified mechanism"],"known":[],"gaps":["independent calibrated UAP observations","carrier response"]};turns=[]
for k,delta in [("D1",[lock]),("D2",[dig([x.get("prior_replay") for x in rows])]),("D3",[dig([x.get("status") for x in rows])]),("D4",[dig(comparison)]),("D5",[dig(gates),dig(docs)])]:
    h=dig(state);state={**state,"known":sorted(set(state["known"])|set(delta))};turns.append({"axis":k,"parent":h,"state":dig(state),"delta":delta})
out={"schema":"janus.uap_tachyon.anomalous_track_forensics.result.v1","status":("FORENSIC_ENGINEERING_GATES_PASS" if all(gates.values()) else "PARTIAL_FORENSIC_HOLD")+"__PAIRED_MEASUREMENT_HOLD__PHYSICAL_CAUSALITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":sha(P.read_bytes()),"manifest_sha256":lock,"gates":gates,"controls":controls,"video_receipts":receipts,"windows":rows,"zenodo":zen,"published_track_comparison":comparison,"documents":docs,"robust_pixel_windows":sum(x["status"]=="ROBUST_PIXEL_MORPHOLOGY_CANDIDATE" for x in rows),"origin_prime_turns":turns,"origin_prime":state,"native_EYE_calls":0,"native_RETINA_calls":0,"admitted_paired_uap_measurements":0,"physical_retrocausality_confirmed":False,"production_changed":False}
O.write_text(json.dumps(out,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
print(json.dumps({k:v for k,v in out.items() if k not in ("windows","documents","published_track_comparison","origin_prime","origin_prime_turns")}|{"windows":[{k:v for k,v in x.items() if k not in ("registration","photometry")}|{"decisions":{r:{k:v[k]["decision"] for k in ("raw","stabilized","fixed_screen")} for r,v in x.get("photometry",{}).items()}} for x in rows],"documents":{k:{a:b for a,b in v.items() if a not in ("page_sha256","technical_pages")} for k,v in docs.items()},"published_track_comparison":[{k:v for k,v in x.items() if k!="diagnostic"}|{"diagnostic_count":len(x["diagnostic"])} for x in comparison]},sort_keys=True))
