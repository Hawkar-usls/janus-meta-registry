#!/usr/bin/env python3
import ast,collections,csv,datetime as dt,hashlib,io,json,math,pathlib,re,subprocess,tempfile,time,urllib.parse,urllib.request
import cv2,numpy as np
from pypdf import PdfReader
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.8B-INSTRUMENTAL-EVIDENCE-RECONSTRUCTION-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.8B-INSTRUMENTAL-EVIDENCE-RECONSTRUCTION-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());cfg=p["video"]
def sha(b):return hashlib.sha256(b).hexdigest()
def ah(a):return sha(np.ascontiguousarray(a).tobytes())
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def read(path):return json.loads((R/path).read_text())
def quant(v):
    return {"min":float(np.min(v)),"median":float(np.median(v)),"max":float(np.max(v))} if len(v) else {}
for path,h in p["pins"].items():assert subprocess.check_output(["git","hash-object",path],text=True).strip()==h
prev=read("registry/uap/JANUS-UAP-TACHYON-R1.8A-PRIMARY-EVIDENCE-ACQUISITION-RESULT-2026-11-28-v1.0.json")
lim={"max_pdf_pages":600,"max_file_bytes":100663296,"timeout_s":35,"transfer_deadline_s":150}
# Reuse only the audited pure helper definitions; never execute the parent script top level.
parent=ast.parse((R/"research/uap_poss1/janus_uap_tachyon_r18a_primary_evidence.py").read_text())
names={"measure","clock","datepat","latlon","tagpat"}
nodes=[n for n in parent.body if (isinstance(n,ast.FunctionDef) and n.name in {"safeurl","download","get","magic","pdf_audit"}) or (isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in n.targets))]
exec(compile(ast.Module(body=nodes,type_ignores=[]),"<pinned R18A helpers>","exec"))
g={"np":np,"p":read("registry/uap/JANUS-UAP-TACHYON-R1.4-TEMPORAL-ARROW-CONTRACT-2026-11-28-v1.0.json"),"banks":{}}
ns=ast.parse((R/"research/uap_poss1/janus_uap_tachyon_r14_temporal_arrow.py").read_text())
exec(compile(ast.Module(body=[n for n in ns.body if isinstance(n,ast.FunctionDef) and n.name in {"makebank","fits","score"}],type_ignores=[]),"<pinned R14>","exec"),g)
cv2.setNumThreads(1)
def detections(frame):
    a=frame.astype(np.float32);res=a-cv2.GaussianBlur(a,(0,0),cfg["local_sigma"])
    med=float(np.median(res));mad=float(np.median(np.abs(res-med)));thr=max(cfg["min_threshold"],cfg["mad_factor"]*1.4826*mad);h,w=a.shape;ex=math.ceil(w*cfg["edge_margin"]);ey=math.ceil(h*cfg["edge_margin"]);out=[]
    for pol in (1,-1):
        mask=(pol*res>thr).astype(np.uint8);mask[:ey,:]=0;mask[-ey:,:]=0;mask[:,:ex]=0;mask[:,-ex:]=0
        n,labels,stats,cent=cv2.connectedComponentsWithStats(mask,8)
        for i in range(1,n):
            x,y,bw,bh,area=map(int,stats[i])
            if not cfg["min_area"]<=area<=cfg["max_area"]:continue
            if max(bw,bh)>5*min(bw,bh):continue
            xx,yy=map(float,cent[i]);val=float(np.mean(pol*res[y:y+bh,x:x+bw][labels[y:y+bh,x:x+bw]==i]))
            out.append([xx,yy,area,val,pol])
    return sorted(out,key=lambda z:(-z[3],z[0],z[1],z[4]))[:cfg["max_candidates"]]
class Tracks:
    def __init__(self):self.active={};self.done=[];self.n=0
    def step(self,i,ds):
        for k,t in list(self.active.items()):
            if i-t[-1][0]>cfg["max_gap"]+1:self.done.append(t);del self.active[k]
        pairs=[]
        for k,t in self.active.items():
            a=t[-1]
            for j,z in enumerate(ds):
                if a[-1]!=z[-1]:continue
                dist=math.hypot(a[1]-z[0],a[2]-z[1])
                if dist<=cfg["max_jump_px"]*(i-a[0]):pairs.append((dist,k,j))
        used=set();assigned=set()
        for _,k,j in sorted(pairs):
            if k in assigned or j in used:continue
            self.active[k].append([i,*ds[j]]);assigned.add(k);used.add(j)
        for j,z in enumerate(ds):
            if j not in used:self.active[self.n]=[[i,*z]];self.n+=1
    def finish(self):
        self.done.extend(self.active.values());self.active={}
        return [t for t in self.done if len(t)>=cfg["min_track_frames"] and math.hypot(np.ptp([z[1] for z in t]),np.ptp([z[2] for z in t]))>=cfg["min_span_px"]]
def synthetic(move):
    rng=np.random.default_rng(181800);tracker=Tracks()
    for i in range(80):
        a=np.clip(100+rng.normal(0,1.5,(120,320)),0,255).astype(np.uint8);cv2.circle(a,(45+i*2 if move else 45,60),3,220,-1);tracker.step(i,detections(a))
    z=tracker.finish();return {"moving":move,"accepted_tracks":len(z),"longest":max([len(t) for t in z],default=0),"target_match":any(len(t)>=70 and np.median([abs(v[1]-(45+2*v[0] if move else 45)) for v in t])<=2 and np.median([abs(v[2]-60) for v in t])<=2 for t in z)}
controls={"positive":synthetic(True),"static_negative":synthetic(False)}
def video_audit(path,work):
    q=subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_streams","-of","json",str(path)],capture_output=True,text=True,check=True,timeout=30);s=json.loads(q.stdout)["streams"][0]
    w=cfg["width"];h=max(1,round(w*s["height"]/s["width"]));n=cfg["max_frames"];expected=int(s["nb_frames"]) if str(s.get("nb_frames","")).isdigit() else None
    if expected is not None and expected>n:raise ValueError("FRAME_CAP")
    log=work/"ffmpeg.log";raw=work/"gray.raw"
    cmd=["ffmpeg","-hide_banner","-nostdin","-loglevel","info","-threads","1","-i",str(path),"-map","0:v:0","-an","-sn","-vf",f"scale={w}:{h}:flags=area,format=gray,showinfo","-fps_mode","passthrough","-frames:v",str(n+1),"-f","rawvideo","-pix_fmt","gray","-y",str(raw)]
    with log.open("wb") as e:subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=e,check=True,timeout=240)
    size=raw.stat().st_size;assert size%(w*h)==0;m=size//(w*h)
    if m>n:raise ValueError("FRAME_CAP")
    pts=[float(x) for x in re.findall(r"\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:\s*([-+0-9.eE]+)",log.read_text(errors="replace"))][:m];valid=len(pts)==m and m>1 and all(b>a for a,b in zip(pts,pts[1:]));delta=np.diff(pts) if valid else []
    tracker=Tracks();hh=hashlib.sha256();prevframe=None;shift=[];det_counts=[];window=cv2.createHanningWindow((w,h),cv2.CV_32F)
    with raw.open("rb") as f:
        for i in range(m):
            b=f.read(w*h);assert len(b)==w*h;hh.update(b);a=np.frombuffer(b,dtype=np.uint8).reshape(h,w);ds=detections(a);det_counts.append(len(ds));tracker.step(i,ds);v=a.astype(np.float32)
            if prevframe is not None:
                (dx,dy),response=cv2.phaseCorrelate(prevframe.copy(),v.copy(),window)
                if all(map(math.isfinite,(dx,dy,response))) and response>=.25:shift.append([i,dx,dy,response])
            prevframe=v
    tr=tracker.finish();res=[];scored=0
    for k,t in enumerate(tr):
        samples=[]
        for i,x,y,area,contrast,pol in t:samples.append({"frame":i,"pts_s":pts[i] if valid else None,"x_norm":x/w,"y_norm":y/h,"area_px":area,"contrast_gray":contrast,"polarity":pol})
        windows=[]
        for j in range(0,len(t)-128,129):
            z=t[j:j+129];ids=[a[0] for a in z]
            if not valid or ids!=list(range(ids[0],ids[0]+129)):continue
            d=np.diff([pts[i] for i in ids]);med=np.median(d)
            if med<=0 or np.max(np.abs(d-med))>.01*med:continue
            y=np.asarray([a[4] for a in z])
            if np.std(y)<=1e-12:continue
            a=g["score"](y);b=g["score"](y[::-1]);flip={"F":"R","R":"F","ABSTAIN":"ABSTAIN"}
            windows.append({"start_frame":ids[0],"forward":a,"reverse":b,"mirror":bool(abs(a["D"]+b["D"])<=1e-9 and abs(a["Q"]-b["Q"])<=1e-9 and flip[a["decision"]]==b["decision"])})
        res.append({"track_id":k,"n":len(t),"coverage":len(t)/(t[-1][0]-t[0][0]+1),"span_px":float(math.hypot(np.ptp([a[1] for a in t]),np.ptp([a[2] for a in t]))),"area":quant([a[3] for a in t]),"contrast":quant([a[4] for a in t]),"samples_sha256":dig(samples),"samples":samples,"temporal_windows":windows,"claim_ceiling":"PIXEL_FEATURE_CANDIDATE__NOT_OBJECT_IDENTITY"})
    raw.unlink();log.unlink()
    return {"status":"FULL_STREAM_PIXEL_CANDIDATES_EXECUTED","stream":{k:s.get(k) for k in ("codec_name","width","height","avg_frame_rate","r_frame_rate","nb_frames","duration","time_base")},"frames":m,"expected_stream_frames":expected,"full_count_matches":expected==m if expected is not None else None,"pts_complete_monotonic":valid,"pts_sha256":dig(pts),"pts_step_s":quant(delta),"decoded_gray_sha256":hh.hexdigest(),"analysis_size":[w,h],"detections_per_frame":quant(det_counts),"global_translation_diagnostic":{"valid_pairs":len(shift),"total_pairs":max(0,m-1),"shift_px":quant([math.hypot(a[1],a[2]) for a in shift]),"response":quant([a[3] for a in shift]),"not_compensated":True},"candidate_tracks":len(res),"tracks":res,"native_EYE_calls":0,"native_RETINA_calls":0,"physical_velocity":None}
rows=[];comparison=[];weather=[]
with tempfile.TemporaryDirectory() as td:
    work=pathlib.Path(td)
    for r in prev["targets"]:
        m=r["metadata"];rid=r["id"];b=work/"asset";a=get(m["hostedUrl"],b,lim["max_file_bytes"]);x={"id":rid,"kind":m["type"],"receipt":a,"expected_sha256":m["sha256"],"metadata_date":m.get("incidentDate"),"title":m.get("title"),"event_time_admission":"HOLD_UNVERIFIED_SOURCE_DATE","integrity":a.get("sha256")==m["sha256"] and a.get("bytes")==m["bytes"] and a.get("sha256")==r["mirror"].get("sha256")}
        if x["integrity"]:
            try:
                assert magic(b,m["type"])
                if m["type"]=="document":
                    f=PdfReader(str(b))
                    if f.is_encrypted and not f.decrypt(""):raise ValueError("PASSWORD_REQUIRED_HOLD")
                    x["analysis"]=pdf_audit(b)
                else:x["analysis"]=video_audit(b,work)
            except Exception as e:x["analysis"]={"status":"HOLD_ANALYSIS","error":repr(e)[:400]}
        rows.append(x);b.unlink(missing_ok=True);print("R18B_TARGET",rid,x["integrity"],x.get("analysis",{}).get("status"),flush=True)
    for r in prev["zenodo"]:
        if not(r["key"].startswith("flyer") and r["key"].endswith(".mp4")):continue
        b=work/"asset";a=get(r["receipt"]["requested_url"],b,lim["max_file_bytes"]);x={"key":r["key"],"receipt":a,"integrity":a.get("sha256")==r["receipt"].get("sha256") and a.get("bytes")==r["expected_bytes"] and "md5:"+str(a.get("md5"))==r["expected_md5"]}
        if x["integrity"]:
            try:assert magic(b,"video");x["analysis"]=video_audit(b,work)
            except Exception as e:x["analysis"]={"status":"HOLD_ANALYSIS","error":repr(e)[:400]}
        comparison.append(x);b.unlink(missing_ok=True);print("R18B_CONTROL",r["key"],x["integrity"],x.get("analysis",{}).get("status"),flush=True)
    for z in p["noaa"]["stations"]:
        url=p["noaa"]["url_template"].format(**z);b=work/"weather";a=get(url,b,30000000);x={**z,"receipt":a,"status":"HOLD_NO_CONTEXT","matched_windows":[],"object_witness":False}
        if a["status"]=="ACQUIRED":
            try:
                txt=b.read_text(encoding="utf-8-sig");rd=csv.DictReader(io.StringIO(txt,newline=""));hdr=[k.strip() for k in rd.fieldnames or []];x["headers"]=hdr[:40]
                if "STATION" not in hdr or "DATE" not in hdr:raise ValueError("NOAA_SCHEMA_MISMATCH")
                rr=[]
                for r in rd:
                    r={k.strip():v for k,v in r.items() if k is not None}
                    assert r["STATION"]==z["station"];t=dt.datetime.fromisoformat(r["DATE"].replace("Z","+00:00"))
                    if t.tzinfo is not None:t=t.astimezone(dt.timezone.utc).replace(tzinfo=None)
                    assert t.year==z["year"];rr.append((t,r))
                for lo,hi in z["windows"]:
                    v=[{k:r.get(k) for k in ("STATION","DATE","NAME","LATITUDE","LONGITUDE","WND","VIS","TMP","DEW","SLP","REPORT_TYPE","QUALITY_CONTROL")} for t,r in rr if dt.datetime.fromisoformat(lo)<=t<=dt.datetime.fromisoformat(hi)]
                    x["matched_windows"].append({"start_utc":lo,"end_utc":hi,"rows":v})
                x["status"]="CONTEXT_ROWS_ACQUIRED" if all(v["rows"] for v in x["matched_windows"]) else "HOLD_MISSING_WINDOW"
            except Exception as e:x["error"]=repr(e)[:350]
        weather.append(x)
pdfs=[x for x in rows if x["kind"]=="document"];vids=[x for x in rows if x["kind"]=="video"];by={x["id"]:x for x in rows}
def textpass(x):
    a=x.get("analysis",{});return x["integrity"] and a.get("status")=="TEXT_TOKENS_EXTRACTED" and a.get("parsed_pages")==a.get("pages")
def vpass(x):
    a=x.get("analysis",{});return x["integrity"] and a.get("status")=="FULL_STREAM_PIXEL_CANDIDATES_EXECUTED" and a.get("pts_complete_monotonic") and a.get("full_count_matches") is not False
windows=[w for x in vids+comparison for t in x.get("analysis",{}).get("tracks",[]) for w in t["temporal_windows"]]
def describe(z):
    t=[a for x in z for a in x.get("analysis",{}).get("tracks",[])];return {"videos":sum(vpass(x) for x in z),"candidate_tracks":len(t),"length_frames":quant([x["n"] for x in t]),"span_px":quant([x["span_px"] for x in t]),"median_area_px":quant([x["area"]["median"] for x in t]),"median_contrast_gray":quant([x["contrast"]["median"] for x in t]),"coverage":quant([x["coverage"] for x in t]),"interpretation":"descriptive pixel candidates only; different optics and frame rates"}
gates={"six_pdf_integrity":len(pdfs)==6 and all(x["integrity"] for x in pdfs),"six_pdf_text":len(pdfs)==6 and all(textpass(x) for x in pdfs),"D165_BAASS_text":all(textpass(by[k]) for k in ("DOW-UAP-D165","DOW-UAP-D172")),"all_6125_frames":len(vids)==4 and all(vpass(x) and x["analysis"]["frames"]==cfg["expected_frames"][x["id"]] for x in vids),"five_galileo_clips":len(comparison)==5 and all(vpass(x) for x in comparison),"synthetic_positive":controls["positive"]["target_match"],"synthetic_static_negative":controls["static_negative"]["accepted_tracks"]==0,"temporal_mirror":bool(windows) and all(w["mirror"] for w in windows),"NOAA_all_windows":all(x["status"]=="CONTEXT_ROWS_ACQUIRED" for x in weather)}
axes=read("data/JANUS-DEEP-ANALYSIS-5D-SPIRAL-ORIGIN-PRIME-ORACLE-PROTOCOL-2026-08-21-v2.1.json")["five_dimensions"];state={"known":["R18A mirror integrity verified"],"alternatives":["object motion","camera motion","overlay","compression","ordinary object","unknown mechanism","hypothetical carrier"],"gaps":["native sensor calibration","common emission/arrival","clock/path","exclusive carrier response"]};turns=[]
for k,delta in [("D1_TEMPORAL",[f"frames {sum(x.get('analysis',{}).get('frames',0) for x in vids)}",f"windows {len(windows)}"]),("D2_MIRROR",[f"parity {sum(w['mirror'] for w in windows)}/{len(windows)}"]),("D3_HIERARCHY",[dig([{"id":x["id"],"integrity":x["integrity"],"status":x.get("analysis",{}).get("status")} for x in rows]),"pixel candidate not physical object"]),("D4_ASSOCIATIVE",[dig(weather),dig(describe(comparison))]),("D5_PROVENANCE",[dig(p["pins"]),dig(gates),"physical HOLD"])]:
    h=dig(state);state={**state,"known":sorted(set(state["known"])|set(delta))};turns.append({"anchor":k,"axes":axes,"parent":h,"state":dig(state),"delta":delta})
out={"schema":"janus.uap_tachyon.instrumental_reconstruction.result.v1","status":("ENGINEERING_GATES_PASS" if all(gates.values()) else "PARTIAL_INSTRUMENTAL_HOLD")+"__PAIRED_MEASUREMENT_HOLD__PHYSICAL_CAUSALITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":sha(P.read_bytes()),"targets":rows,"galileo":comparison,"weather":weather,"synthetic_controls":controls,"gates":gates,"morphology":{"PURSUE":describe(vids),"Galileo":describe(comparison)},"temporal_windows":len(windows),"mirror_passed":sum(w["mirror"] for w in windows),"origin_prime_turns":turns,"origin_prime":state,"native_EYE_calls":0,"native_RETINA_calls":0,"admitted_paired_uap_measurements":0,"physical_retrocausality_confirmed":False,"production_changed":False}
O.write_text(json.dumps(out,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
def compact(x):
    a=x.get("analysis",{});return {"id":x.get("id",x.get("key")),"integrity":x["integrity"],"analysis":{k:v for k,v in a.items() if k not in ("page_receipts","tracks")}}
print(json.dumps({k:v for k,v in out.items() if k not in ("targets","galileo","origin_prime","origin_prime_turns","weather")}|{"targets":[compact(x) for x in rows],"galileo":[compact(x) for x in comparison],"weather":[{"case":x["case"],"status":x["status"],"error":x.get("error"),"receipt":x["receipt"],"window_counts":[len(w["rows"]) for w in x["matched_windows"]]} for x in weather]},sort_keys=True))
