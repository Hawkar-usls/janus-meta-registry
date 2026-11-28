#!/usr/bin/env python3
import ast,collections,csv,datetime as dt,hashlib,io,json,math,pathlib,re,subprocess,tempfile,time,urllib.parse,urllib.request
import cv2,numpy as np
from pypdf import PdfReader
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.8D-OBJECT-IDENTITY-RECOVERY-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.8D-OBJECT-IDENTITY-RECOVERY-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());lim={"max_file_bytes":100663296,"timeout_s":35,"transfer_deadline_s":150}
def sha(b):return hashlib.sha256(b).hexdigest()
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def read(path):return json.loads((R/path).read_text())
def quant(v):
    return {"min":float(np.min(v)),"median":float(np.median(v)),"p90":float(np.quantile(v,.9)),"max":float(np.max(v))} if len(v) else {}
for path,h in p["pins"].items():assert subprocess.check_output(["git","hash-object",path],text=True).strip()==h
a=read("registry/uap/JANUS-UAP-TACHYON-R1.8A-PRIMARY-EVIDENCE-ACQUISITION-RESULT-2026-11-28-v1.0.json");b=read("registry/uap/JANUS-UAP-TACHYON-R1.8B-INSTRUMENTAL-EVIDENCE-RECONSTRUCTION-RESULT-2026-11-28-v1.0.json");c=read("registry/uap/JANUS-UAP-TACHYON-R1.8C-ANOMALOUS-TRACK-FORENSICS-RESULT-2026-11-28-v1.0.json")
by={x["id"]:x for x in b["targets"]};meta={x["id"]:x["metadata"] for x in a["targets"]}
def helpers(path,names):
    ns=ast.parse((R/path).read_text());exec(compile(ast.Module(body=[n for n in ns.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),"<pinned helpers>","exec"),globals())
helpers("research/uap_poss1/janus_uap_tachyon_r18a_primary_evidence.py",{"safeurl","download","get","magic"})
helpers("research/uap_poss1/janus_uap_tachyon_r18c_anomalous_track_forensics.py",{"checked_asset","decode","hud","mask_for","aperture","score"})
g={"np":np,"p":read("registry/uap/JANUS-UAP-TACHYON-R1.4-TEMPORAL-ARROW-CONTRACT-2026-11-28-v1.0.json"),"banks":{}}
ns=ast.parse((R/"research/uap_poss1/janus_uap_tachyon_r14_temporal_arrow.py").read_text());exec(compile(ast.Module(body=[n for n in ns.body if isinstance(n,ast.FunctionDef) and n.name in {"makebank","fits","score"}],type_ignores=[]),"<pinned R14>","exec"),g);cv2.setNumThreads(1)
manifest=[]
for v in c["windows"]:
    tr=next(t for t in by[v["id"]]["analysis"]["tracks"] if t["track_id"]==v["track"]);s=[z for z in tr["samples"] if v["start"]<=z["frame"]<v["start"]+129];assert len(s)==129 and dig(s)==v["sample_sha256"]
    manifest.append({"id":v["id"],"track":v["track"],"start":v["start"],"samples":s,"sample_sha256":v["sample_sha256"]})
assert len(manifest)==7
def spectrum(t,y):
    t=np.asarray(t,float);y=np.asarray(y,float);n=len(y)
    if n<32 or len(t)!=n or not np.all(np.isfinite(t)) or not np.all(np.isfinite(y)):return {"status":"HOLD_SHORT_OR_NONFINITE"}
    d=np.diff(t);md=float(np.median(d))
    if md<=0 or np.any(d<=0) or np.max(np.abs(d-md))>.01*md:return {"status":"HOLD_NONUNIFORM"}
    x=np.arange(n,dtype=float);z=y-np.polyval(np.polyfit(x,y,1),x)
    if np.std(z)<1e-10:return {"status":"HOLD_CONSTANT"}
    f=np.fft.rfftfreq(n,md);pow=np.abs(np.fft.rfft(z*np.hanning(n)))**2;band=(f>=1)&(f<=min(15,.5/md))
    if not band.any() or pow[band].sum()<=0:return {"status":"HOLD_NO_BAND"}
    k=np.flatnonzero(band)[np.argmax(pow[band])]
    return {"status":"DESCRIPTIVE_PEAK","n":n,"dt_s":md,"duration_s":float(t[-1]-t[0]),"resolution_hz":1/(n*md),"peak_hz":float(f[k]),"peak_band_fraction":float(pow[k]/pow[band].sum()),"cycles":float(f[k]*(t[-1]-t[0])),"band_hz":[1,min(15,.5/md)],"profile_sha256":dig(y.tolist()),"not_significance_test":True}
tt=np.arange(129)/30;pos=spectrum(tt,np.sin(2*np.pi*5*tt));neg=spectrum(tt,np.ones(129));controls={"frequency_5Hz":{"result":pos,"pass":abs(pos.get("peak_hz",0)-5)<=pos.get("resolution_hz",0)},"frequency_constant":{"result":neg,"pass":neg["status"]=="HOLD_CONSTANT"}}
def bgmask(shape,xy):
    h,w=shape;yy,xx=np.indices(shape);m=(xx>=.06*w)&(xx<.94*w)&(yy>=.06*h)&(yy<.94*h)&~((xx/w<.18)&(yy/h<.20))&~((abs(xx/w-.5)<.045)&(abs(yy/h-.5)<.085))
    for x,y in xy:m&=(xx-x)**2+(yy-y)**2>24**2
    return m
def reg(ref,cur,mask):
    h,w=ref.shape;a=ref.astype(np.float32);b=cur.astype(np.float32);a-=cv2.GaussianBlur(a,(0,0),3);b-=cv2.GaussianBlur(b,(0,0),3);v=[];eligible=0;texture=0;win=cv2.createHanningWindow((40,40),cv2.CV_32F)
    for iy,y in enumerate(range(8,h-39,40)):
        for ix,x in enumerate(range(8,w-39,40)):
            if not mask[y:y+40,x:x+40].all():continue
            eligible+=1;aa=a[y:y+40,x:x+40];bb=b[y:y+40,x:x+40]
            if min(np.std(aa),np.std(bb))<.8:continue
            texture+=1;(dx,dy),r=cv2.phaseCorrelate(aa.copy(),bb.copy(),win)
            if all(map(math.isfinite,(dx,dy,r))) and r>=.3 and math.hypot(dx,dy)<=12:v.append([ix,iy,-dx,-dy,r])
    tr=np.asarray([z[2:4] for z in v if (z[0]+z[1])%2==0]);te=np.asarray([z[2:4] for z in v if (z[0]+z[1])%2]);q={"eligible":eligible,"textured":texture,"accepted":len(v),"train":len(tr),"test":len(te)}
    if len(tr)<3 or len(te)<2:q["reason"]="INSUFFICIENT_INDEPENDENT_PATCHES";return None,q
    xy=np.median(tr,axis=0);errs=[np.linalg.norm(z-xy,axis=1) for z in (tr,te)];q["residuals"]=[quant(e) for e in errs];q["shift"]=xy.tolist()
    if any(np.median(e)>.75 or np.quantile(e,.9)>1.5 for e in errs):q["reason"]="PATCH_DISAGREEMENT";return None,q
    return np.array([[1,0,xy[0]],[0,1,xy[1]]],float),q
rng=np.random.default_rng(181804);r=cv2.GaussianBlur(rng.integers(30,220,(179,320),dtype=np.uint8),(3,3),0);m=bgmask(r.shape,[(120,90)]);cur=cv2.warpAffine(r,np.float32([[1,0,3],[0,1,-2]]),(320,179),borderMode=cv2.BORDER_REFLECT);M,q=reg(r,cur,m);err=None if M is None else float(np.linalg.norm(M[:,2]-[-3,2]));controls["registration_translation"]={"detail":q,"error_px":err,"pass":err is not None and err<=.75}
flat=np.full_like(r,100);M,q=reg(flat,flat,m);controls["registration_flat"]={"detail":q,"pass":M is None}
hudonly=flat.copy();hudonly[0:28,0:50]=r[0:28,0:50];M,q=reg(hudonly,hudonly,m);controls["registration_HUD_only"]={"detail":q,"pass":M is None}
def runs(rows,field):
    groups=collections.defaultdict(list)
    for z in rows:
        try:
            f=float(z["frame"]);t=float(z["t_s"]);y=float(z[field])
            if not f.is_integer() or not all(map(math.isfinite,(f,t,y))):continue
            groups[z.get("letter","UNLABELLED")].append((int(f),t,y))
        except (ValueError,TypeError,KeyError):continue
    out=[]
    for k,v in sorted(groups.items()):
        v.sort();chunk=[];pieces=[]
        for z in v:
            if chunk and z[0]!=chunk[-1][0]+1:pieces.append(chunk);chunk=[]
            chunk.append(z)
        if chunk:pieces.append(chunk)
        for j,ch in enumerate(pieces):
            for i in range(0,len(ch)-128,129):
                zz=ch[i:i+129];out.append({"letter":k,"run":j,"start":zz[0][0],"end":zz[-1][0],"spectrum":spectrum([x[1] for x in zz],[x[2] for x in zz])})
    return out
zrows=[];zdata={};comparison=[];pubfreq=[];ctrlfreq=[];regrows=[];dossier={};video_receipts=[]
with tempfile.TemporaryDirectory() as td:
    d=pathlib.Path(td)
    want={"README.md","reproduce_analysis.py","pr135_tracks.csv","pr135_lightcurves.csv","pr135_beats.csv","galileo_flyers.csv","SHA256SUMS"}|{f"galileo_flyer{i}_series.csv" for i in range(1,6)}
    for old in a["zenodo"]:
        key=old["key"]
        if key not in want:continue
        f=d/"z";r=get(old["receipt"]["requested_url"],f,4000000);ok=r.get("sha256")==old["receipt"].get("sha256") and "md5:"+str(r.get("md5"))==old["expected_md5"] and r.get("bytes")==old["expected_bytes"];x={"key":key,"receipt":r,"integrity":ok}
        if ok:
            t=f.read_text(encoding="utf-8-sig");zdata[key]=t
            if key.endswith(".csv"):
                rd=csv.DictReader(io.StringIO(t));x["headers"]=rd.fieldnames;x["rows"]=sum(1 for _ in rd)
        zrows.append(x);f.unlink(missing_ok=True)
    # Inspect source conventions as text only; do not execute external reproduction code.
    convention=[]
    for key in ("README.md","reproduce_analysis.py"):
        for i,line in enumerate(zdata.get(key,"").splitlines()):
            if re.search(r"(?:frame.{0,24}(?:index|number|zero.based|one.based|fps|t_s)|(?:1280|720|320|180).{0,35}(?:pixel|frame|width|height)|(?:pixel|frame|width|height).{0,35}(?:1280|720|320|180)|(?:coordinates|centroid).{0,30}(?:pixel|native|frame))",line,re.I):
                if len(convention)<60:convention.append({"file":key,"line":i+1,"line_sha256":sha(line.encode()),"numeric_tokens":re.findall(r"\b\d+(?:\.\d+)?\b",line)[:12],"labels":sorted(set(re.findall(r"\b(?:frame|index|fps|pixel|width|height|native|zero.based|one.based|coordinate|centroid)\b",line,re.I)))})
    # Original PR135 timing is authenticated against prior complete decoded video.
    for rid in ("DOW-UAP-PR135","DOW-UAP-PR168"):
        f=d/"asset";r=checked_asset(rid,f);x={"id":rid,"receipt":r,"status":"HOLD"}
        try:
            assert r["integrity"] and magic(f,"video");z=by[rid]["analysis"];w,h=z["analysis_size"];n=z["frames"];raw=d/"raw";log=d/"log";pts,hs=decode(f,raw,log,w,h,n);assert hs==z["decoded_gray_sha256"] and dig(pts)==z["pts_sha256"];x.update(status="REPLAY_VERIFIED",frame_sha_match=True,pts_sha_match=True)
            if rid.endswith("PR135"):
                if "pr135_tracks.csv" in zdata:
                    rr=csv.DictReader(io.StringIO(zdata["pr135_tracks.csv"]));tab=list(rr);assert all(k in rr.fieldnames for k in ("frame","t_s","letter","x","y"));groups=collections.defaultdict(dict);duplicates=0
                    for row in tab:
                        try:
                            j=float(row["frame"]);t,xx,yy=[float(row[k]) for k in ("t_s","x","y")];assert j.is_integer() and all(map(math.isfinite,(j,t,xx,yy)));letter=row["letter"].strip();assert letter
                            i=int(j);v=groups[letter].setdefault(i,[]);v.append((t,xx,yy));duplicates+=len(v)>1
                        except (ValueError,AssertionError):continue
                    for v in manifest:
                        if v["id"]!=rid:continue
                        q={"track":v["track"],"start":v["start"],"letters":{k:{"n":len(z),"min_frame":min(z),"max_frame":max(z)} for k,z in groups.items()},"duplicate_letter_frame_rows":duplicates,"hypotheses":[],"status":"HOLD_NO_AUTHENTICATED_MATCH"}
                        for off in (0,1):
                            for sw,sh in ((1280,720),(320,180)):
                                for k,z in sorted(groups.items()):
                                    ds=[];ts=[]
                                    for s in v["samples"]:
                                        rr=z.get(s["frame"]+off,[])
                                        if len(rr)!=1:continue
                                        t,xx,yy=rr[0];ds.append(math.hypot((xx/sw-s["x_norm"])*320,(yy/sh-s["y_norm"])*180));ts.append(abs(t-pts[s["frame"]]))
                                    if ds:q["hypotheses"].append({"letter":k,"frame_offset":off,"source_size":[sw,sh],"overlap":len(ds),"distance_320px":quant(ds),"absolute_time_error_s":quant(ts),"diagnostic_fit":len(ds)>=32 and np.median(ds)<=3 and np.quantile(ds,.9)<=6 and np.quantile(ts,.9)<=.5*float(np.median(np.diff(pts)))})
                        q["diagnostic_fit_count"]=sum(z["diagnostic_fit"] for z in q["hypotheses"]);comparison.append(q)
            else:
                frames=np.memmap(raw,dtype=np.uint8,mode="r",shape=(n,h,w))
                for v in manifest:
                    if v["id"]!=rid:continue
                    st=v["start"];s=v["samples"];xy=np.asarray([[q["x_norm"]*w,q["y_norm"]*h] for q in s]);mask=bgmask((h,w),xy);ref=np.asarray(frames[st]).copy();regs=[];curves={r:[] for r in (2,3,5)}
                    for i,(cx,cy) in enumerate(xy):
                        im=np.asarray(frames[st+i]);M,detail=reg(ref,im,mask) if i else (np.eye(2,3),{"reference":True});regs.append({"frame":st+i,"valid":M is not None,"detail":detail,"matrix":None if M is None else M.tolist()})
                        if M is not None:
                            z=M[:,:2]@np.asarray([cx,cy])+M[:,2];warped=cv2.warpAffine(im,M,(w,h),flags=cv2.INTER_LINEAR)
                            for rr in curves:curves[rr].append(aperture(warped,*z,rr,s[i]["polarity"]))
                        else:
                            for rr in curves:curves[rr].append(None)
                    valid=sum(q["valid"] for q in regs);regrows.append({"track":v["track"],"start":st,"valid_frames":valid,"registration":regs,"status":"FULL_VALIDATED_TRANSLATION" if valid==129 else "HOLD_PARTIAL_OR_UNOBSERVABLE","stabilized":{str(k):score(v) if valid==129 else {"decision":"HOLD"} for k,v in curves.items()},"profiles":curves,"possible_HUD_fraction":next(q["possible_HUD_fraction"] for q in c["windows"] if q["id"]==rid and q["track"]==v["track"] and q["start"]==st)})
                del frames
            raw.unlink();log.unlink()
        except Exception as e:x["error"]=repr(e)[:350];x["status"]="HOLD"
        video_receipts.append(x);f.unlink(missing_ok=True);print("R18D_VIDEO",rid,x["status"],flush=True)
    # Source-linked published flux and controls, no claim they share the candidate time window.
    if "pr135_lightcurves.csv" in zdata:
        rd=csv.DictReader(io.StringIO(zdata["pr135_lightcurves.csv"]));rr=list(rd)
        pubfreq=runs(rr,"flux");light_groups=collections.defaultdict(list)
        for q in rr:
            try:light_groups[q["letter"]].append(int(float(q["frame"])))
            except (ValueError,KeyError):pass
        light_coverage={k:{"n":len(v),"min_frame":min(v),"max_frame":max(v)} for k,v in light_groups.items()}
    else:light_coverage={}
    for key,t in sorted(zdata.items()):
        if not re.fullmatch(r"galileo_flyer\d_series\.csv",key):continue
        rd=csv.DictReader(io.StringIO(t));rr=list(rd);hdr=rd.fieldnames or []
        field=next((k for k in ("flux","rel_pct","brightness","contrast","signal","flux_bgsub") if k in hdr),None)
        ctrl={"key":key,"headers":hdr,"field":field,"spectra":runs(rr,field) if field and all(k in hdr for k in ("frame","t_s")) else [],"status":"SCHEMA_DIAGNOSTIC"}
        ctrlfreq.append(ctrl)
    v=next(q for q in c["windows"] if q["id"]=="DOW-UAP-PR135" and q["track"]==56);m=next(q for q in manifest if q["id"]==v["id"] and q["track"]==56);times=[s["pts_s"] for s in m["samples"]]
    freq={k:{lane:spectrum(times,z[lane+"_profile"]) for lane in ("raw","stabilized","fixed_screen")} for k,z in v["photometry"].items()}
    f=d/"pdf";r=checked_asset("DOW-UAP-D172",f);dossier={"receipt":r,"status":"HOLD","candidate_titles":[],"matches":[]}
    try:
        assert r["integrity"] and magic(f,"document");pdf=PdfReader(str(f))
        if pdf.is_encrypted and not pdf.decrypt(""):raise ValueError("PASSWORD_REQUIRED")
        candidates={};report_ids=collections.defaultdict(list);section_pages=[]
        topic=re.compile(r"radar|electromagnet|radio|propulsion|physics|optical|plasma|aerospace|gravitation|inertial|magnetic|sensor|relativ|quantum|tachyon",re.I)
        for i,pg in enumerate(pdf.pages):
            t=pg.extract_text() or "";lines=t.splitlines();section=bool(re.search(r"(?im)^\s*(?:references|bibliography|works cited)\s*$",t))
            if section:section_pages.append(i+1)
            for j,line in enumerate(lines):
                for m in re.finditer(r"\b(?:AD[- ]?[A-Z]?\d{6,9}|NASA[- ](?:TM|CR|TP)[- ]\d{4,8}|RAND[- ](?:R|RM|TR)[- ]\d{3,7})\b",line,re.I):report_ids[m.group()].append(i+1)
                titles=re.findall(r'["“]([^"”\n]{18,180})["”]',line)
                if section or re.match(r"^\s*(?:\[\d+\]|\d+\.)\s+",line):
                    # Only bibliographic-shaped lines with publication year; extract title after a year or author punctuation.
                    if re.search(r"\b(?:19|20)\d{2}\b",line):
                        titles+=re.findall(r"(?:\b(?:19|20)\d{2}\)?[.,:]\s+|[.]\s+)([A-Z][^.;]{18,150})(?:[.;]|$)",line)
                for title in titles:
                    title=" ".join(title.split()).strip(" ,.;")
                    if not topic.search(title) or not 4<=len(title.split())<=24:continue
                    if re.search(r"@|https?://|\b\d{3}-\d{2}-\d{4}\b",title):continue
                    key=title.casefold();yr=re.findall(r"\b(?:19|20)\d{2}\b",line)
                    candidates.setdefault(key,{"title":title,"year":int(yr[0]) if len(set(yr))==1 else None,"page":i+1,"line_sha256":sha(line.encode()),"status":"UNADJUDICATED_TITLE_CANDIDATE"})
        def tokens(t):return set(re.findall(r"[a-z0-9]+",t.lower()))-{"a","an","the","of","on","in","for","and","to"}
        def jac(a,b):
            a=tokens(a);b=tokens(b);return len(a&b)/len(a|b) if a|b else 0
        ordered=sorted(candidates.values(),key=lambda z:(z["page"],z["line_sha256"],z["title"]))
        dossier.update(pages=len(pdf.pages),reference_section_pages=section_pages,report_ids={k:sorted(set(v)) for k,v in report_ids.items()},candidate_count=len(ordered),candidate_titles=ordered[:120],queried_count=min(12,len(ordered)))
        for z in ordered[:12]:
            url="https://api.crossref.org/works?"+urllib.parse.urlencode({"query.bibliographic":z["title"]+(" "+str(z["year"]) if z["year"] else ""),"rows":3})
            tmp=d/"ref";r=get(url,tmp,3000000);q={"candidate":z,"receipt":r,"matches":[]}
            if r["status"]=="ACQUIRED":
                try:
                    for item in json.loads(tmp.read_text())["message"]["items"]:
                        title=(item.get("title") or [""])[0];year=(item.get("published",{}).get("date-parts") or [[None]])[0][0];sim=jac(z["title"],title);ok=sim>=.85 and (z["year"] is None or (isinstance(year,int) and abs(year-z["year"])<=1))
                        q["matches"].append({"title":title,"doi":item.get("DOI"),"year":year,"title_jaccard":sim,"bibliographic_match":ok,"claim_verified":False})
                except Exception as e:q["error"]=repr(e)[:200]
            dossier["matches"].append(q);tmp.unlink(missing_ok=True)
        dossier["status"]="BIBLIOGRAPHIC_DISCOVERY_EXECUTED__PRIMARY_MEASUREMENT_HOLD"
    except Exception as e:dossier["error"]=repr(e)[:350]
    f.unlink(missing_ok=True)
gates={"frozen_seven":len(manifest)==7,"zenodo_integrity":len(zrows)==12 and all(x["integrity"] for x in zrows),"letter_schema":len(comparison)==2 and all(x["letters"] for x in comparison),"frequency_controls":all(controls[k]["pass"] for k in ("frequency_5Hz","frequency_constant")),"PR135_frequency":any(z["status"]=="DESCRIPTIVE_PEAK" for q in freq.values() for z in q.values()),"video_replay":len(video_receipts)==2 and all(x["status"]=="REPLAY_VERIFIED" for x in video_receipts),"registration_controls":all(controls[k]["pass"] for k in ("registration_translation","registration_flat","registration_HUD_only")),"PR168_full_registration":len(regrows)==5 and all(x["valid_frames"]==129 for x in regrows),"BAASS_discovery":dossier["status"]=="BIBLIOGRAPHIC_DISCOVERY_EXECUTED__PRIMARY_MEASUREMENT_HOLD","BAASS_bibliographic_match":any(m["bibliographic_match"] for q in dossier["matches"] for m in q["matches"])}
out={"schema":"janus.uap_tachyon.object_identity_recovery.result.v1","status":"OBJECT_IDENTITY_DIAGNOSTICS_EXECUTED__PAIRED_MEASUREMENT_HOLD__PHYSICAL_CAUSALITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":sha(P.read_bytes()),"manifest_sha256":dig([{k:v for k,v in x.items() if k!="samples"} for x in manifest]),"gates":gates,"controls":controls,"zenodo":zrows,"source_convention_pointers":convention,"published_track_comparison":comparison,"published_lightcurve_coverage":light_coverage,"published_lightcurve_spectra":pubfreq,"galileo_spectra":ctrlfreq,"PR135_track56_frequency":freq,"PR168_registration":regrows,"video_receipts":video_receipts,"BAASS":dossier,"native_EYE_calls":0,"native_RETINA_calls":0,"authenticated_object_identity":False,"admitted_paired_uap_measurements":0,"physical_retrocausality_confirmed":False,"production_changed":False}
O.write_text(json.dumps(out,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
print(json.dumps({k:v for k,v in out.items() if k not in ("source_convention_pointers","PR168_registration","BAASS","zenodo","published_track_comparison")}|{"source_convention_pointer_count":len(convention),"PR168_registration":[{k:v for k,v in x.items() if k not in ("registration","profiles")}|{"reasons":dict(collections.Counter(z["detail"].get("reason","valid") for z in x["registration"]))} for x in regrows],"BAASS":{k:v for k,v in dossier.items() if k not in ("candidate_titles","matches","report_ids")}|{"bibliographic_matches":sum(m["bibliographic_match"] for q in dossier["matches"] for m in q["matches"]),"report_id_count":len(dossier.get("report_ids",{}))},"zenodo":[{"key":x["key"],"integrity":x["integrity"],"headers":x.get("headers"),"rows":x.get("rows")} for x in zrows],"published_track_comparison":[{k:v for k,v in x.items() if k!="hypotheses"}|{"hypotheses_count":len(x["hypotheses"]),"best_overlap":max([z["overlap"] for z in x["hypotheses"]],default=0)} for x in comparison]},sort_keys=True))
