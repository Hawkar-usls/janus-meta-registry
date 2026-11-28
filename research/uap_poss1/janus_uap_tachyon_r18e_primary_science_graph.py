import ast,collections,concurrent.futures,csv,datetime as dt,hashlib,io,json,math,pathlib,re,subprocess,tempfile,time,urllib.parse,urllib.request
import numpy as np,cv2
from pypdf import PdfReader
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.8E-PRIMARY-SCIENCE-GRAPH-CONTRACT-2026-11-28-v1.0.json";O=U/"JANUS-UAP-TACHYON-R1.8E-PRIMARY-SCIENCE-GRAPH-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text());lim={"max_file_bytes":100663296,"timeout_s":35,"transfer_deadline_s":150}
def sha(b):return hashlib.sha256(b).hexdigest()
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def read(path):return json.loads((R/path).read_text())
def norm(s):return " ".join(re.findall(r"[a-z0-9]+",s.lower()))
def quant(v):return {"min":float(np.min(v)),"median":float(np.median(v)),"p90":float(np.quantile(v,.9)),"max":float(np.max(v))} if len(v) else {}
for path,h in p["pins"].items():assert subprocess.check_output(["git","hash-object",path],text=True).strip()==h
a=read("registry/uap/JANUS-UAP-TACHYON-R1.8A-PRIMARY-EVIDENCE-ACQUISITION-RESULT-2026-11-28-v1.0.json");b=read("registry/uap/JANUS-UAP-TACHYON-R1.8B-INSTRUMENTAL-EVIDENCE-RECONSTRUCTION-RESULT-2026-11-28-v1.0.json");d=read("registry/uap/JANUS-UAP-TACHYON-R1.8D-OBJECT-IDENTITY-RECOVERY-RESULT-2026-11-28-v1.0.json");ba=read("registry/uap/JANUS-BAASS-DIRD-PRIMARY-SOURCE-ACQUISITION-2026-11-28-v1.0.json")
by={x["id"]:x for x in b["targets"]};meta={x["id"]:x["metadata"] for x in a["targets"]}
def helpers(path,names):
    ns=ast.parse((R/path).read_text());exec(compile(ast.Module(body=[n for n in ns.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),"<pinned helpers>","exec"),globals())
helpers("research/uap_poss1/janus_uap_tachyon_r18a_primary_evidence.py",{"safeurl","download","get","magic"})
helpers("research/uap_poss1/janus_uap_tachyon_r18c_anomalous_track_forensics.py",{"checked_asset","decode","aperture"})
def parsepdf(path,text=False):
    r=PdfReader(str(path))
    if r.is_encrypted and not r.decrypt(""):raise ValueError("PASSWORD_REQUIRED")
    pg=[v.extract_text() or "" for v in r.pages] if text else []
    return len(r.pages),pg
def acquire(x):
    with tempfile.TemporaryDirectory() as td:
        f=pathlib.Path(td)/"asset";r=get(x["url"],f,25000000);q={**x,"receipt":r,"status":"HOLD"};pg=[]
        try:
            assert r["status"]=="ACQUIRED" and magic(f,"document")
            n,pg=parsepdf(f,x["analysis"]=="THEORETICAL_BIBLIOGRAPHY");q.update(status="PDF_ACQUIRED",pages=n,inventory_page_match=n==x["inventory_pages"],text_pages=sum(bool(t.strip()) for t in pg) if pg else None)
            if pg:q["page_sha256"]=[sha(t.encode()) for t in pg]
        except Exception as e:q["error"]=repr(e)[:250]
        return q,pg
assert [v["id"] for v in p["manifest"]]==list(range(1,38)) and sum(v["inventory_pages"] for v in p["manifest"])==1473
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:acq=list(pool.map(acquire,p["manifest"]))
rows=[x for x,_ in acq];pgs={x["id"]:v for x,v in acq};print("R18E_DIRD",sum(x["status"]=="PDF_ACQUIRED" for x in rows),flush=True)
edges=[];science=[];baass={"status":"HOLD"};foia={"status":"HOLD"}
with tempfile.TemporaryDirectory() as td:
    work=pathlib.Path(td);f=work/"asset";r=get(p["foia"]["url"],f,10000000);foia["receipt"]=r
    try:
        assert r["status"]=="ACQUIRED" and magic(f,"document");n,pg=parsepdf(f,True);t=norm(" ".join(pg));foia.update(status="ACQUIRED",pages=n,reference_match="foia 00159 2018" in t,inventory_count_match=bool(re.search(r"37 documents.{0,30}1?473 pages",t)),page_sha256=[sha(v.encode()) for v in pg])
    except Exception as e:foia["error"]=repr(e)[:200]
    f.unlink(missing_ok=True);r=checked_asset("DOW-UAP-D172",f);baass["receipt"]=r
    def hits(pages,phrase):
        key=norm(phrase);return [{"page":i+1,"page_sha256":sha(t.encode()),"line_sha256":[sha(l.encode()) for l in t.splitlines() if key in norm(l)]} for i,t in enumerate(pages) if key and re.search(r"\b"+re.escape(key)+r"\b",norm(t))]
    try:
        assert r["integrity"] and magic(f,"document");n,bpages=parsepdf(f,True);baass.update(status="ACQUIRED",pages=n)
        for q in p["theory_links"]:
            for title in q.get("alias",[]):
                for h in hits(bpages,title):edges.append({"from":"BAASS_D172","to":"DIRD_%02d"%q["id"],"type":"TITLE_OR_ALIAS_MATCH","phrase":title,**h,"identity_proof":False})
    except Exception as e:baass["error"]=repr(e)[:250]
    f.unlink(missing_ok=True)
    for q in p["theory_links"]+p["additional_science"]:
        doi=q.get("paper",q.get("doi"))
        if not doi:continue
        x={**q,"doi":doi,"status":"HOLD","bibliographic_match":False,"physical_claim_verified":False}
        if "id" in q:
            for h in hits(pgs.get(q["id"],[]),q["title"]):edges.append({"from":"DIRD_%02d"%q["id"],"to":doi,"type":"EXACT_NORMALIZED_CITATION_TEXT",**h,"physical_claim_verified":False})
        r=get("https://api.crossref.org/works/"+urllib.parse.quote(doi,safe="/"),f,3000000);x["receipt"]=r
        try:
            assert r["status"]=="ACQUIRED";md=json.loads(f.read_text())["message"];title=(md.get("title") or [""])[0];yr=(md.get("published",{}).get("date-parts") or [[None]])[0][0]
            x.update(status="METADATA_RESOLVED",resolved_title=title,resolved_year=yr,bibliographic_match=norm(title)==norm(q["title"]) and md.get("DOI","").lower()==doi.lower() and (q.get("year") is None or q["year"]==yr))
        except Exception as e:x["error"]=repr(e)[:200]
        f.unlink(missing_ok=True)
        if q.get("arxiv"):
            r=get("https://arxiv.org/pdf/"+q["arxiv"],f,12000000);x["open_primary_receipt"]=r
            try:
                assert r["status"]=="ACQUIRED" and magic(f,"document");n,pp=parsepdf(f,True);x["open_primary"]={"pages":n,"title_hits":hits(pp[:2],q["title"]),"page_sha256":[sha(t.encode()) for t in pp],"role":"THEORETICAL_PRIMARY_TEXT_NOT_EXPERIMENT"}
            except Exception as e:x["open_primary_error"]=repr(e)[:200]
            f.unlink(missing_ok=True)
        science.append(x)
    # Source-native geometry helper from pinned R2, synthetic fields only.
    s2=read("registry/physics/JANUS_SINGULARITY_GPT_R2_RESULT_2026-11-27.json");s4=read("registry/physics/JANUS_SINGULARITY_GPT_R4B10B1_RESULT_2026-11-27.json")
    gs={"np":np,"math":math,"xs":np.linspace(.025,.975,32),"phase":np.arange(64)/64}
    ns=ast.parse((R/"research/uap_poss1/pinned_singularity_r2_source.py").read_text())
    exec(compile(ast.Module(body=[n for n in ns.body if isinstance(n,ast.FunctionDef) and n.name=="geom"],type_ignores=[]),"<SINGULARITY R2 geom>","exec"),gs)
    z=np.zeros((64,32,4));z[:,:,0]=1;z[:,:,1]=1.25
    native=gs["geom"](4.,3.,z)["diagnostic"]
    generic=[]
    for shift in (0.,.2,1.2,-1.2):
        G=np.array([[-1+shift*shift,-shift],[-shift,1.]])
        nulls=[shift-1,shift+1];res=[float(abs(np.array([1.,v])@G@np.array([1.,v]))) for v in nulls]
        generic.append({"coordinate_shift":shift,"metric":G.tolist(),"det":float(np.linalg.det(G)),"null_residual":max(res),"local_light_speed_c":1,"not_physical_drive_design":True})
    singularity={"native_geom_calls":1,"domain":"synthetic R2 collapse metric fields, not warp metric and not UAP","diagnostic":native,"generic_null_controls":generic,"R2_status":s2["status"],"R4B10B1_status":s4["status"],"physical_DSS_authorized":s4.get("physical_DSS_authorized"),"weights_promoted":False,"neural_training":False,"pass":native["lorentzian_fraction"]==1 and native["null_residual_max"]<1e-12 and all(x["det"]<0 and x["null_residual"]<1e-12 for x in generic)}
    # PR135: exact source frames and published table, compare same-frame coordinates without assuming identity.
    zdata={};zrec=[]
    for key in ("pr135_tracks.csv","pr135_lightcurves.csv","README.md","reproduce_analysis.py"):
        old=next(v for v in a["zenodo"] if v["key"]==key);r=get(old["receipt"]["requested_url"],f,4000000);ok=r.get("sha256")==old["receipt"].get("sha256") and "md5:"+str(r.get("md5"))==old["expected_md5"] and r.get("bytes")==old["expected_bytes"]
        if ok:zdata[key]=f.read_text(encoding="utf-8-sig")
        zrec.append({"key":key,"receipt":r,"integrity":ok});f.unlink(missing_ok=True)
    video={"status":"HOLD","zenodo":zrec,"authenticated_identity":False}
    try:
        rid="DOW-UAP-PR135";r=checked_asset(rid,f);video["receipt"]=r;assert r["integrity"] and magic(f,"video")
        z=by[rid]["analysis"];w,h=z["analysis_size"];n=z["frames"];raw=work/"raw";log=work/"log";pts,hs=decode(f,raw,log,w,h,n);assert hs==z["decoded_gray_sha256"] and dig(pts)==z["pts_sha256"];video["frame_replay"]=True;frames=np.memmap(raw,dtype=np.uint8,mode="r",shape=(n,h,w));dtm=float(np.median(np.diff(pts)))
        tr=collections.defaultdict(dict);flux=collections.defaultdict(dict)
        for q in csv.DictReader(io.StringIO(zdata["pr135_tracks.csv"])):
            i=int(float(q["frame"]));k=q["letter"];assert i not in tr[k];tr[k][i]=(float(q["t_s"]),float(q["x"]),float(q["y"]))
        for q in csv.DictReader(io.StringIO(zdata["pr135_lightcurves.csv"])):
            i=int(float(q["frame"]));k=q["letter"];assert i not in flux[k];flux[k][i]=(float(q["t_s"]),float(q["flux"]))
        assert set(tr)==set("ABCDEF") and set(flux)==set(tr)
        def spec(t,y):
            t=np.asarray(t,float);y=np.asarray(y,float);dd=np.diff(t);md=float(np.median(dd))
            if len(y)<32 or not np.all(np.isfinite(y)) or md<=0 or np.max(abs(dd-md))>.01*md:return {"status":"HOLD"}
            xx=np.arange(len(y));z=y-np.polyval(np.polyfit(xx,y,1),xx)
            if np.std(z)<1e-10:return {"status":"HOLD_CONSTANT"}
            ff=np.fft.rfftfreq(len(z),md);pp=np.abs(np.fft.rfft(z*np.hanning(len(z))))**2;ix=np.flatnonzero((ff>=1)&(ff<=min(15,.5/md)))
            return {"status":"DESCRIPTIVE","peak_hz":float(ff[ix[np.argmax(pp[ix])]]),"resolution_hz":1/(len(z)*md)}
        hypotheses=[]
        for off in (0,1):
            for sw,sh in ((1280,720),(320,180)):
                per=[]
                for letter,q in sorted(tr.items()):
                    pairs=[];errs=[];ferr=[];brightness=[];indices=[]
                    for j,(t,x,y) in sorted(q.items()):
                        i=j-off
                        if not 0<=i<n:continue
                        errs.append(abs(t-pts[i]));cx=x*w/sw;cy=y*h/sh
                        if j not in flux[letter] or not 0<=cx<w or not 0<=cy<h:continue
                        ft,fy=flux[letter][j];val=aperture(frames[i],cx,cy,3,1)
                        if val is None or not math.isfinite(fy):continue
                        pairs.append([val,fy]);ferr.append(abs(ft-pts[i]));brightness.append(fy);indices.append(i)
                    cor=None
                    if len(pairs)>=32 and min(np.std(np.asarray(pairs),axis=0))>1e-9:cor=float(np.corrcoef(np.asarray(pairs).T)[0,1])
                    valid_time=len(errs)>0 and np.quantile(errs,.9)<=.5*dtm and len(ferr)>0 and np.quantile(ferr,.9)<=.5*dtm
                    freq=spec([pts[i] for i in indices],brightness) if valid_time and len(indices)>=32 and indices==list(range(indices[0],indices[0]+len(indices))) else {"status":"HOLD_TIME_OR_GAPS"}
                    per.append({"letter":letter,"pairs":len(pairs),"track_time_error_s":quant(errs),"flux_time_error_s":quant(ferr),"valid_time":bool(valid_time),"correlation":cor,"published_flux_native_pts_spectrum":freq})
                hypotheses.append({"offset":off,"source_size":[sw,sh],"letters":per,"time_valid_letters":sum(x["valid_time"] for x in per),"geometry_authenticated":False})
        video["hypotheses"]=hypotheses
        # Strict local template continuation. Each step uses previous frame patch, independent reverse check and runner-up separation.
        def match(im,templ,xy,radius=12):
            x,y=map(lambda v:int(round(v)),xy);h,w=im.shape;half=5
            if min(x,y,w-1-x,h-1-y)<radius+half:return None
            crop=im[y-radius-half:y+radius+half+1,x-radius-half:x+radius+half+1]
            if np.std(templ)<2:return None
            q=cv2.matchTemplate(crop,templ,cv2.TM_CCOEFF_NORMED);_,best,_,loc=cv2.minMaxLoc(q);xx,yy=loc;copy=q.copy();copy[max(0,yy-2):yy+3,max(0,xx-2):xx+3]=-2
            if best<.8 or best-float(copy.max())<.05:return None
            return np.array([x-radius+xx,y-radius+yy],float),float(best)
        def template(im,xy):
            x,y=map(lambda v:int(round(v)),xy);return im[y-5:y+6,x-5:x+6] if 5<=x<im.shape[1]-5 and 5<=y<im.shape[0]-5 else None
        def extend(i,xy,step):
            out=[{"frame":i,"x":float(xy[0]),"y":float(xy[1])}];reason="LIMIT"
            for _ in range(548):
                j=i+step
                if not 0<=j<n:reason="STREAM_EDGE";break
                t=template(frames[i],xy)
                if t is None or t.shape!=(11,11):reason="BOUNDARY";break
                v=match(frames[j],t,xy)
                if v is None:reason="LOW_CONFIDENCE_OR_AMBIGUITY";break
                xx,conf=v;t2=template(frames[j],xx);back=match(frames[i],t2,xx) if t2 is not None and t2.shape==(11,11) else None
                if back is None or np.linalg.norm(back[0]-xy)>2:reason="FORWARD_BACKWARD_FAIL";break
                out.append({"frame":j,"x":float(xx[0]),"y":float(xx[1]),"ncc":conf});i=j;xy=xx
            return {"count":len(out)-1,"stop":reason,"samples":out,"sha256":dig(out)}
        # Published extensions under both coordinate conventions and only timing-valid hypotheses; no identity merge.
        ext=[]
        for hyp in hypotheses:
            if hyp["time_valid_letters"]!=6:continue
            off=hyp["offset"];sw,sh=hyp["source_size"]
            for k,q in sorted(tr.items()):
                v=[]
                for j,step in ((min(q),-1),(max(q),1)):
                    _,x,y=q[j];xy=np.array([x*w/sw,y*h/sh])
                    if 0<=j-off<n and 0<=xy[0]<w and 0<=xy[1]<h:v.append({"direction":step,**extend(j-off,xy,step)})
                ext.append({"letter":k,"offset":off,"source_size":[sw,sh],"extensions":v,"geometry_authenticated":False})
        t=next(t for t in z["tracks"] if t["track_id"]==56);s=[x for x in t["samples"] if 692<=x["frame"]<=820];assert len(s)==129
        e56=[{"direction":step,**extend(v["frame"],np.array([v["x_norm"]*w,v["y_norm"]*h]),step)} for v,step in ((s[0],-1),(s[-1],1))]
        overlaps=[]
        for q in ext:
            pp={v["frame"]:(v["x"],v["y"]) for e in q["extensions"] for v in e["samples"]}
            tt={v["frame"]:(v["x"],v["y"]) for e in e56 for v in e["samples"]};tt.update({v["frame"]:(v["x_norm"]*w,v["y_norm"]*h) for v in s})
            common=set(pp)&set(tt);overlaps.append({"letter":q["letter"],"offset":q["offset"],"source_size":q["source_size"],"shared_frames":len(common),"distance_px":quant([math.hypot(pp[i][0]-tt[i][0],pp[i][1]-tt[i][1]) for i in common]),"identity_authenticated":False})
        video.update(status="PUBLISHED_TRACK_DIAGNOSTICS_EXECUTED",letters={k:{"rows":len(v),"first":min(v),"last":max(v)} for k,v in tr.items()},extensions=ext,track56_extensions=e56,overlaps=overlaps)
        del frames
    except Exception as e:video["error"]=repr(e)[:350]
    f.unlink(missing_ok=True)
gates={"public_manifest":len(rows)==37,"all_public_pdf_acquired":all(x["status"]=="PDF_ACQUIRED" for x in rows),"all_inventory_pages_match":all(x.get("inventory_page_match") for x in rows),"foia_letter":foia.get("reference_match",False) and foia.get("inventory_count_match",False),"BAASS_hash":baass.get("status")=="ACQUIRED","DIRD_citation_edges":any(x["type"]=="EXACT_NORMALIZED_CITATION_TEXT" for x in edges),"primary_doi_metadata":sum(x["bibliographic_match"] for x in science if "id" in x)==3,"singularity_native_geometry":singularity["pass"],"PR135_replay":video.get("frame_replay",False),"PR135_published_diagnostic":video["status"]=="PUBLISHED_TRACK_DIAGNOSTICS_EXECUTED"}
out={"schema":"janus.uap_tachyon.primary_science_graph.result.v1","status":("ENGINEERING_GATES_PASS" if all(gates.values()) else "PARTIAL_PRIMARY_SCIENCE_GRAPH_HOLD")+"__OBJECT_IDENTITY_HOLD__PHYSICAL_CAUSALITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":sha(P.read_bytes()),"pins":p["pins"],"gates":gates,"foia":foia,"BAASS":baass,"DIRD":rows,"graph_edges":edges,"science":science,"model_contracts":p["models"],"singularity":singularity,"PR135":video,"official_original_byte_equivalence":False,"native_EYE_calls":0,"native_RETINA_calls":0,"admitted_paired_uap_measurements":0,"physical_claims_confirmed":0,"production_changed":False}
O.write_text(json.dumps(out,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
print(json.dumps({"status":out["status"],"gates":gates,"DIRD":[{k:v for k,v in x.items() if k!="page_sha256"} for x in rows],"foia":{k:v for k,v in foia.items() if k!="page_sha256"},"edges":edges,"science":[{k:v for k,v in x.items() if k!="open_primary"} for x in science],"singularity":singularity,"PR135":{k:v for k,v in video.items() if k not in ("extensions","track56_extensions")}|{"extensions":[{"letter":q["letter"],"offset":q["offset"],"source_size":q["source_size"],"counts":[{k:v for k,v in x.items() if k!="samples"} for x in q["extensions"]]} for q in video.get("extensions",[])],"track56_extensions":[{k:v for k,v in x.items() if k!="samples"} for x in video.get("track56_extensions",[])]}},sort_keys=True))
