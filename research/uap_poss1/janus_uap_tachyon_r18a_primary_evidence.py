#!/usr/bin/env python3
import ast,collections,csv,datetime as dt,hashlib,io,json,math,pathlib,re,subprocess,tempfile,time,urllib.parse,urllib.request
import numpy as np
from pypdf import PdfReader
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.8A-PRIMARY-EVIDENCE-ACQUISITION-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.8A-PRIMARY-EVIDENCE-ACQUISITION-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());lim=p["limits"]
def sha(b):return hashlib.sha256(b).hexdigest()
def ah(a):return sha(np.ascontiguousarray(a).tobytes())
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def read(path):return json.loads((R/path).read_text())
for path,h in p["pins"].items():assert subprocess.check_output(["git","hash-object",path],text=True).strip()==h
prior=read("registry/uap/JANUS-UAP-TACHYON-OPEN-EVIDENCE-ACQUISITION-2026-11-28-v1.0.json");by={x["id"]:x for x in prior["receipts"]}
idrx=re.compile(r"^(?:DOW|FBI|CIA|NASA|ODNI|USG|DOE|DOS)-UAP-(?:PR|D)\d+\b",re.I)
def ident(x):
    m=idrx.match(str(x).strip());return m.group().upper() if m else None
records=by["PURSUE_ARCHIVE_JSON"]["records"];idx=collections.defaultdict(list)
for x in records:
    k=ident(x.get("title",""))
    if k:idx[k].append(x)
assert all(len(idx[k])==1 for k in p["target_ids"])
manifest=[{"id":k,**idx[k][0]} for k in p["target_ids"]];lock=dig(manifest)
def safeurl(u):
    z=urllib.parse.urlsplit(u);return urllib.parse.urlunsplit((z.scheme,z.netloc,z.path,"",""))
def download(url,path,cap):
    h=hashlib.sha256();md=hashlib.md5();n=0;start=time.monotonic()
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"JANUS R1.8A public research"}),timeout=lim["timeout_s"]) as f,open(path,"wb") as w:
        while True:
            b=f.read(1024*1024)
            if not b:break
            n+=len(b)
            if n>cap:raise ValueError("BYTE_CAP")
            if time.monotonic()-start>lim["transfer_deadline_s"]:raise TimeoutError("TRANSFER_DEADLINE")
            h.update(b);md.update(b);w.write(b)
        return {"requested_url":url,"final_url":safeurl(f.geturl()),"status":"ACQUIRED","http_status":f.status,"content_type":f.headers.get("Content-Type"),"bytes":n,"sha256":h.hexdigest(),"md5":md.hexdigest(),"retrieved_utc":now()}
def get(url,path,cap):
    try:return download(url,path,cap)
    except Exception as e:return {"requested_url":url,"status":"HOLD_ACQUISITION","error":repr(e)[:350]}
def magic(path,kind):
    with open(path,"rb") as f:b=f.read(32)
    return b.startswith(b"%PDF") if kind=="document" else b[4:8]==b"ftyp"
g={"np":np,"p":read("registry/uap/JANUS-UAP-TACHYON-R1.4-TEMPORAL-ARROW-CONTRACT-2026-11-28-v1.0.json"),"banks":{}}
nodes=ast.parse((R/"research/uap_poss1/janus_uap_tachyon_r14_temporal_arrow.py").read_text())
exec(compile(ast.Module(body=[z for z in nodes.body if isinstance(z,ast.FunctionDef) and z.name in {"makebank","fits","score"}],type_ignores=[]),"<pinned R14>", "exec"),g)
def finite(v):return float(v) if math.isfinite(float(v)) else None
def quant(v):
    return {"min":float(np.min(v)),"median":float(np.median(v)),"max":float(np.max(v))} if len(v) else {}
measure=re.compile(r"(?<![\w.])[-+]?\d+(?:[.,]\d+)?(?:\s*(?:±|\+/-)\s*\d+(?:\.\d+)?)?\s*(?:km/s|m/s|mph|knots?|kts?|GHz|MHz|kHz|Hz|nT|µT|uT|mT|microseconds?|milliseconds?|µs|ms|seconds?|minutes?|feet|ft|meters?|metres?|kilometers?|km|nautical miles?|nmi|degrees?|°|dB)(?!\w)",re.I)
clock=re.compile(r"\b(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d+)?)?(?:\s*(?:UTC|GMT|Z|local))?\b|\b(?:[01]\d|2[0-3])[0-5]\d\s*(?:UTC|GMT|Z)\b",re.I)
datepat=re.compile(r"\b(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}\b|\b\d{1,2}[/-]\d{1,2}[/-](?:19|20)\d{2}\b|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+(?:19|20)\d{2}\b",re.I)
latlon=re.compile(r"\b(?:lat(?:itude)?)\s*[:=]?\s*([-+]?\d{1,2}\.\d+)\s*[,;/ ]+\s*(?:lon(?:gitude)?)\s*[:=]?\s*([-+]?\d{1,3}\.\d+)\b",re.I)
tagpat={k:re.compile(v,re.I) for k,v in {"radar":"radar|azimuth|elevation","radio":"radio frequency|radio signal|electromagnetic|\\bRF\\b","optical":"infrared|EO/IR|sensor|camera","uncertainty":"uncertaint|error|estimate|approximate|accuracy|calibrat","timing":"clock|timestamp|time of flight|delay|UTC"}.items()}
def pdf_audit(path):
    f=PdfReader(str(path));n=len(f.pages);pages=[];empty=0
    if n>lim["max_pdf_pages"]:return {"status":"HOLD_PAGE_CAP","pages":n}
    for i,page in enumerate(f.pages):
        try:
            t=page.extract_text() or "";tags=[k for k,v in tagpat.items() if v.search(t)];tokens=[];counts=collections.Counter()
            for line in t.splitlines():
                h=sha(line.encode());lt=[k for k,v in tagpat.items() if v.search(line)]
                for kind,pat in [("date",datepat),("clock",clock),("measurement",measure)]:
                    for m in pat.finditer(line):
                        counts[kind]+=1
                        if len(tokens)<40:tokens.append({"kind":kind,"token":m.group(),"line_sha256":h,"tags":lt,"authority":"UNADJUDICATED_REPORT_TOKEN"})
                for m in latlon.finditer(line):
                    a,b=map(float,m.groups())
                    if abs(a)<=90 and abs(b)<=180:
                        counts["coordinate_pair"]+=1
                        # Exact potentially sensitive locations retained only as source pointer and hash.
                        if len(tokens)<40:tokens.append({"kind":"labelled_coordinate_pair","line_sha256":h,"value_sha256":dig([a,b]),"status":"SOURCE_REVIEW_REQUIRED__NO_OBJECT_ASSOCIATION"})
            empty+=not bool(t.strip());pages.append({"page":i+1,"text_chars":len(t),"text_sha256":sha(t.encode()),"tags":tags,"token_counts":dict(counts),"tokens":tokens,"truncated":sum(counts.values())>len(tokens)})
        except Exception as e:pages.append({"page":i+1,"status":"HOLD_PAGE_PARSE","error":repr(e)[:200]})
    return {"status":"TEXT_TOKENS_EXTRACTED" if any(x.get("text_chars",0)>0 for x in pages) else "HOLD_NO_TEXT_LAYER","pages":n,"empty_text_pages":empty,"parsed_pages":sum("text_chars" in x for x in pages),"page_receipts":pages,"calibrated_measurements":0,"coordinate_authority":"unadjudicated; exact location not admitted","ocr":False}
def video_audit(path):
    probe=subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_streams","-show_format","-of","json",str(path)],capture_output=True,text=True,check=True,timeout=30)
    j=json.loads(probe.stdout);s=j["streams"][0];w,h=lim["frame_width"],lim["frame_height"];n=lim["max_video_frames"]
    cmd=["ffmpeg","-hide_banner","-nostdin","-loglevel","info","-threads","1","-i",str(path),"-map","0:v:0","-an","-sn","-vf",f"scale={w}:{h}:flags=area,format=gray,showinfo","-fps_mode","passthrough","-frames:v",str(n),"-f","rawvideo","-pix_fmt","gray","pipe:1"]
    q=subprocess.run(cmd,capture_output=True,check=True,timeout=100);assert len(q.stdout)%(w*h)==0
    frames=np.frombuffer(q.stdout,dtype=np.uint8).reshape(-1,h,w);m=len(frames)
    pts=[float(x) for x in re.findall(r"\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:\s*([-+0-9.eE]+)",q.stderr.decode("utf-8","replace"))][:m]
    mean=frames.mean(axis=(1,2));motion=np.abs(np.diff(frames.astype(np.float32),axis=0)).mean(axis=(1,2))
    uniform=False;delta=[]
    if len(pts)==m and m>=2:
        delta=np.diff(pts);med=float(np.median(delta));uniform=bool(med>0 and np.all(delta>0) and np.max(np.abs(delta-med))<=.01*med)
    windows=[]
    if uniform:
        for start in range(0,m-128,129):
            y=mean[start:start+129]
            if np.std(y)<=1e-12:continue
            a=g["score"](y);b=g["score"](y[::-1]);flip={"F":"R","R":"F","ABSTAIN":"ABSTAIN"}
            windows.append({"start_frame":start,"end_frame":start+128,"forward":a,"reverse":b,"mirror":bool(abs(a["D"]+b["D"])<=1e-9 and abs(a["Q"]-b["Q"])<=1e-9 and flip[a["decision"]]==b["decision"]),"profile_sha256":ah(y)})
    return {"status":"EYE_SHADOW_FRAME_DIAGNOSTIC_EXECUTED","stream":{k:s.get(k) for k in ("codec_name","width","height","pix_fmt","r_frame_rate","avg_frame_rate","time_base","start_time","duration","nb_frames")},"format_duration":j.get("format",{}).get("duration"),"analyzed_frames":m,"decoded_gray_sha256":sha(q.stdout),"frame_pts_s":pts,"pts_complete":len(pts)==m,"pts_step_s":quant(delta),"uniform_pts_1pct":uniform,"global_mean_gray":mean.tolist(),"global_mean_abs_frame_difference":motion.tolist(),"temporal_R14_windows":windows,"native_EYE_calls":0,"native_RETINA_calls":0,"physical_velocity":None,"scope":"first bounded frames; full-frame display brightness, not tracked object or calibrated sensor signal"}
def titleyears(x):return sorted(set(re.findall(r"\b(?:19|20)\d{2}\b",x.get("title",""))))
rows=[];video_hash={}
with tempfile.TemporaryDirectory() as td:
    d=pathlib.Path(td)
    for x in manifest:
        rid=x["id"];kind=x["type"];a=d/(rid+".official");b=d/(rid+".mirror")
        r={"id":rid,"metadata":x,"title_years":titleyears(x),"catalog_incident_date":x.get("incidentDate"),"event_time_admission":"HOLD_UNVERIFIED_SOURCE_DATE","status":"HOLD"}
        o=get(x["officialUrl"],a,lim["max_file_bytes"] if kind=="document" else lim["max_page_bytes"]);m=get(x["hostedUrl"],b,lim["max_file_bytes"])
        if o["status"]=="ACQUIRED":
            o["is_media_bytes"]=magic(a,kind);o["matches_mirror_manifest"]=bool(o["is_media_bytes"] and o["sha256"]==x["sha256"] and o["bytes"]==x["bytes"])
            if kind=="video" and not o["is_media_bytes"]:o["role"]="OFFICIAL_LANDING_PAGE_ONLY"
        if m["status"]=="ACQUIRED":
            m["is_media_bytes"]=magic(b,kind);m["matches_manifest"]=bool(m["is_media_bytes"] and m["sha256"]==x["sha256"] and m["bytes"]==x["bytes"])
        r.update(official=o,mirror=m,primary_mirror_byte_match=bool(o.get("matches_mirror_manifest") and m.get("matches_manifest")))
        if m.get("matches_manifest"):
            r["status"]="MIRROR_BYTES_MATCH_MANIFEST"
            try:
                r["analysis"]=pdf_audit(b) if kind=="document" else video_audit(b)
                if kind=="video":video_hash[rid]=m["sha256"]
            except Exception as e:r["analysis"]={"status":"HOLD_ANALYSIS","error":repr(e)[:350]}
        elif o.get("matches_mirror_manifest"):
            r["status"]="OFFICIAL_BYTES_MATCH_MANIFEST__MIRROR_HOLD"
            try:r["analysis"]=pdf_audit(a) if kind=="document" else video_audit(a)
            except Exception as e:r["analysis"]={"status":"HOLD_ANALYSIS","error":repr(e)[:350]}
        else:r["status"]="HOLD_INTEGRITY_OR_ACCESS"
        r["timing_gate"]="HOLD_NO_CALIBRATED_COMMON_EMISSION_ARRIVAL_PATH";r["carrier_claim"]=False;rows.append(r)
        print("R18A_TARGET",rid,r["status"],r.get("analysis",{}).get("status"),flush=True)
        a.unlink(missing_ok=True);b.unlink(missing_ok=True)
    zfiles=by["ZENODO_23021686"]["files"];selected=[x for x in zfiles if x["key"].endswith(".csv") or x["key"] in ("SHA256SUMS","README.md","reproduce_analysis.py","DOD_111985782.mp4") or (x["key"].startswith("flyer") and x["key"].endswith(".mp4"))]
    selected.sort(key=lambda x:(x["key"]!="SHA256SUMS",x["key"]));zen=[];checks={}
    for i,x in enumerate(selected):
        b=d/("zen"+str(i));r={"key":x["key"],"expected_md5":x["checksum"],"expected_bytes":x["size"]};a=get(x["download"],b,lim["max_file_bytes"]);r["receipt"]=a
        r["integrity"]=a["status"]=="ACQUIRED" and a["bytes"]==x["size"] and "md5:"+a["md5"]==x["checksum"]
        if r["integrity"]:
            try:
                if x["key"]=="SHA256SUMS":
                    for line in b.read_text().splitlines():
                        m=re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+)$",line)
                        if m:checks[m[2].strip().removeprefix("./")]=m[1].lower()
                elif x["key"] in checks:r["published_sha256_match"]=a["sha256"]==checks[x["key"]]
                if r.get("published_sha256_match") is False:raise ValueError("PUBLISHED_SHA256_MISMATCH")
                if x["key"].endswith(".mp4"):
                    assert magic(b,"video")
                    r["analysis"]=video_audit(b)
                    if x["key"]=="DOD_111985782.mp4":r["PR135_mirror_byte_match"]=a["sha256"]==video_hash.get("DOW-UAP-PR135")
                elif x["key"].endswith(".csv"):
                    t=csv.DictReader(io.StringIO(b.read_text(encoding="utf-8-sig")));rr=list(t);s={}
                    for k in t.fieldnames or []:
                        vals=[]
                        for row in rr:
                            try:v=float(row.get(k,""));assert math.isfinite(v);vals.append(v)
                            except (ValueError,TypeError,AssertionError):pass
                        if vals:s[k]={"n_finite":len(vals),**quant(vals)}
                    r["derived_table"]={"rows":len(rr),"headers":t.fieldnames,"numeric_columns":s,"role":"PUBLISHED_DERIVED_DATA_NOT_INDEPENDENT_TARGET_TRACK"}
            except Exception as e:r["analysis_error"]=repr(e)[:250]
        zen.append(r);b.unlink(missing_ok=True)
        print("R18A_ZENODO",x["key"],r["integrity"],flush=True)
    def csv_header(raw):
        t=raw.decode("utf-8-sig");assert not t.lstrip().startswith("<")
        rd=csv.reader(io.StringIO(t,newline=""),delimiter=",",quotechar='"',strict=True);hdr=[x.strip().strip("\ufeff") for x in next(rd)];assert len(hdr)==len(set(hdr));return hdr,rd
    weather=[]
    for w in p["noaa"]["stations"]:
        x={**w,"attempts":[],"status":"HOLD_NO_CONTEXT","matched_windows":[]}
        lo=min(a[0] for a in w["windows"])[:10];hi=max(a[1] for a in w["windows"])[:10]
        urls=[f"https://www.ncei.noaa.gov/data/global-hourly/access/{w['year']}/{w['station']}.csv","https://www.ncei.noaa.gov/access/services/data/v1?"+urllib.parse.urlencode({"dataset":"global-hourly","stations":w["station"],"startDate":lo,"endDate":hi,"format":"csv","includeAttributes":"true"})]
        for i,url in enumerate(urls):
            b=d/"weather";a=get(url,b,30000000);x["attempts"].append(a)
            if a["status"]!="ACQUIRED":continue
            try:
                hdr,rd=csv_header(b.read_bytes());a["headers"]=hdr;lookup={k.upper():k for k in hdr}
                assert "STATION" in lookup and "DATE" in lookup
                rr=[]
                for raw in rd:
                    if len(raw)!=len(hdr):raise ValueError("NOAA_ROW_LENGTH")
                    rr.append({k.upper():v for k,v in zip(hdr,raw)})
                assert rr and all(r["STATION"].strip()==w["station"] for r in rr)
                out=[]
                for lo,hi in w["windows"]:
                    z=[]
                    for r in rr:
                        t=dt.datetime.fromisoformat(r["DATE"].replace("Z","+00:00"))
                        if t.tzinfo is not None:t=t.astimezone(dt.timezone.utc).replace(tzinfo=None)
                        if dt.datetime.fromisoformat(lo)<=t<=dt.datetime.fromisoformat(hi):z.append({k:r.get(k) for k in ("STATION","DATE","NAME","LATITUDE","LONGITUDE","WND","VIS","TMP","DEW","SLP","REPORT_TYPE","QUALITY_CONTROL")})
                    out.append({"start_utc":lo,"end_utc":hi,"rows":z})
                x["matched_windows"]=out;x["status"]="CONTEXT_ROWS_ACQUIRED" if any(v["rows"] for v in out) else "HOLD_NO_WINDOW_ROWS"
                if x["status"]=="CONTEXT_ROWS_ACQUIRED":break
            except Exception as e:a["parse_error"]=repr(e)[:300]
        weather.append(x)
    # Strict CSV repair; reject malformed rows instead of guessing shifted columns.
    tracker={"status":"HOLD"};b=d/"tracker";a=get(by["PURSUE_TRACKER_CSV"]["requested_url"],b,8000000);tracker["receipt"]=a
    if a["status"]=="ACQUIRED":
        try:
            hdr,rd=csv_header(b.read_bytes());tracker["headers"]=hdr;assert all(k in hdr for k in ("Title","Release Date","Type"))
            valid=[];rejected=[];seen=collections.Counter();counts=collections.Counter()
            try:
                for raw in rd:
                    if len(raw)!=len(hdr):rejected.append({"line":rd.line_num,"reason":"COLUMN_COUNT","count":len(raw)});continue
                    q=dict(zip(hdr,raw));rid=ident(q["Title"])
                    try:
                        day=dt.datetime.strptime(q["Release Date"].strip(),"%m/%d/%Y").date().isoformat()
                        if not rid:raise ValueError("UNANCHORED_ID")
                        kind=q["Type"].strip().lower()
                        if kind not in ("document","video","image","pdf","photo","audio"):raise ValueError("TYPE")
                    except Exception as e:rejected.append({"line":rd.line_num,"reason":str(e)[:120]});continue
                    seen[rid]+=1;counts[day]+=1;valid.append({"id":rid,"release_date":day,"type":kind,"line":rd.line_num})
            except csv.Error as e:tracker["parser_stop"]={"line":rd.line_num,"error":str(e),"unread_tail":"NOT_PARSED"}
            overlap=set(seen)&set(idx);conflicts=[]
            for v in valid:
                if v["id"] in idx and not any(x.get("releaseDate")==v["release_date"] for x in idx[v["id"]]):conflicts.append(v)
            tracker.update(status="STRICT_ROWS_PARSED_WITH_QUARANTINE",valid_rows=len(valid),rejected_rows=len(rejected),rejects=rejected,distinct_ids=len(seen),duplicate_ids={k:v for k,v in seen.items() if v>1},release_dates=dict(counts),mirror_id_overlap=len(overlap),date_conflicts=conflicts,valid=valid)
        except Exception as e:tracker["error"]=repr(e)[:300]
axes=read("data/JANUS-DEEP-ANALYSIS-5D-SPIRAL-ORIGIN-PRIME-ORACLE-PROTOCOL-2026-08-21-v2.1.json")["five_dimensions"]
videos=[r["analysis"] for r in rows if r.get("analysis",{}).get("status")=="EYE_SHADOW_FRAME_DIAGNOSTIC_EXECUTED"];zvideos=[r["analysis"] for r in zen if r.get("analysis",{}).get("status")=="EYE_SHADOW_FRAME_DIAGNOSTIC_EXECUTED"];windows=[w for v in videos+zvideos for w in v["temporal_R14_windows"]]
gates={"exact_target_manifest":len(rows)==len(p["target_ids"]),"all_target_mirror_integrity":all(r["mirror"].get("matches_manifest",False) for r in rows),"target_video_analysis":len(videos)==4,"temporal_mirror":bool(windows) and all(w["mirror"] for w in windows),"zenodo_controls":sum(r.get("integrity",False) and not r.get("analysis_error") and r["key"].startswith("flyer") and r["key"].endswith(".mp4") for r in zen)==5,"NOAA_context":all(w["status"]=="CONTEXT_ROWS_ACQUIRED" for w in weather),"CSV_strict_complete":tracker["status"]=="STRICT_ROWS_PARSED_WITH_QUARANTINE" and not tracker.get("parser_stop") and tracker.get("valid_rows",0)>0}
state={"known":["R1.8 paired measurement HOLD"],"alternatives":["ordinary object","display or compression artifact","parallax","instrument fault","timing or metadata error","unidentified mechanism","hypothetical carrier"],"gaps":["calibrated paired raw UAP measurements","absolute clock","exclusive carrier response"]};turns=[]
for k,delta in [("D1_TEMPORAL",[f"PTS-scored windows {len(windows)}",dig([r["timing_gate"] for r in rows])]),("D2_MIRROR",[f"parity {sum(w['mirror'] for w in windows)}/{len(windows)}"]),("D3_HIERARCHY",[dig([{k:r[k] for k in ("id","status")} for r in rows]),"numeric tokens not calibrated measurements"]),("D4_ASSOCIATIVE",[dig(weather),f"Zenodo integrity {sum(r['integrity'] for r in zen)}/{len(zen)}","global display metrics not object identification"]),("D5_PROVENANCE",[lock,dig(gates),"physical HOLD"])]:
    h=dig(state);state={**state,"known":sorted(set(state["known"])|set(delta))};turns.append({"anchor":k,"axes":axes,"parent":h,"state":dig(state),"delta":delta})
out={"schema":"janus.uap_tachyon.primary_evidence_acquisition.result.v1","status":("PRIMARY_EVIDENCE_ENGINEERING_GATES_PASS" if all(gates.values()) else "PARTIAL_PRIMARY_EVIDENCE_HOLD")+"__PAIRED_MEASUREMENT_HOLD__PHYSICAL_CAUSALITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":sha(P.read_bytes()),"manifest_sha256":lock,"targets":rows,"zenodo":zen,"weather":weather,"tracker_csv":tracker,"gates":gates,"target_mirror_hash_matches":sum(bool(r["mirror"].get("matches_manifest")) for r in rows),"official_mirror_byte_matches":sum(r["primary_mirror_byte_match"] for r in rows),"target_videos_analyzed":len(videos),"zenodo_videos_analyzed":len(zvideos),"temporal_windows":len(windows),"mirror_passed":sum(w["mirror"] for w in windows),"origin_prime_turns":turns,"origin_prime":state,"native_EYE_calls":0,"native_RETINA_calls":0,"admitted_paired_uap_measurements":0,"physical_retrocausality_confirmed":False,"production_changed":False}
O.write_text(json.dumps(out,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
print(json.dumps({k:v for k,v in out.items() if k not in ("targets","zenodo","weather","tracker_csv","origin_prime","origin_prime_turns")}|{"targets":[{"id":r["id"],"status":r["status"],"official":r["official"],"mirror":r["mirror"],"analysis":{k:v for k,v in r.get("analysis",{}).items() if k in ("status","pages","empty_text_pages","parsed_pages","analyzed_frames","pts_complete","uniform_pts_1pct","stream","error")}} for r in rows],"zenodo":[{"key":r["key"],"integrity":r["integrity"],"analysis_status":r.get("analysis",{}).get("status"),"error":r.get("analysis_error"),"PR135_mirror_byte_match":r.get("PR135_mirror_byte_match")} for r in zen],"weather":[{"case":w["case"],"status":w["status"],"attempts":w["attempts"],"counts":[len(a["rows"]) for a in w["matched_windows"]]} for w in weather],"tracker":{k:v for k,v in tracker.items() if k not in ("valid","rejects","date_conflicts","duplicate_ids")}},sort_keys=True))
