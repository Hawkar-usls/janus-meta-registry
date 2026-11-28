#!/usr/bin/env python3
import collections,datetime as dt,hashlib,io,json,math,pathlib,re,subprocess,urllib.request,csv
from pypdf import PdfReader
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-R1.8-UAP-TACHYON-RECONNECTION-CONTRACT-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-R1.8-UAP-TACHYON-RECONNECTION-RESULT-2026-11-28-v1.0.json"
p=json.loads(P.read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
def dig(x):return sha(json.dumps(x,sort_keys=True,separators=(",",":"),allow_nan=False).encode())
def blob(b):return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()
def read(path):return json.loads((R/path).read_text())
q={}
for k,(path,h) in p["pins"].items():
    b=(R/path).read_bytes();assert blob(b)==h;q[k]=json.loads(b)
patterns={k:re.compile(v,re.I) for k,v in p["terms"].items()}
inventory={}
for a in q["core"]["inventory"]+q["cross"]["co_mentions"]:
    path=a["path"];h=a["git_blob_sha"]
    inventory.setdefault(path,set()).add(h)
def leaves(x,path=""):
    if isinstance(x,dict):
        for k,v in x.items():yield from leaves(v,path+"/"+str(k).replace("~","~0").replace("/","~1"))
    elif isinstance(x,list):
        for i,v in enumerate(x):yield from leaves(v,path+"/"+str(i))
    elif isinstance(x,str):yield path,x
docs=[];fails=[]
for path,hs in sorted(inventory.items()):
    try:
        b=(R/path).read_bytes();h=blob(b)
        if h not in hs:
            # Read frozen historical blob when file has since changed; no silent substitution.
            if len(hs)!=1:raise ValueError("CONFLICTING_PINS")
            h=next(iter(hs));b=subprocess.check_output(["git","cat-file","blob",h]);assert blob(b)==h
        j=json.loads(b.decode("utf-8-sig"));counts=collections.Counter();hits=[]
        for ptr,s in leaves(j):
            tags=[k for k,v in patterns.items() if v.search(s)]
            if not tags:continue
            counts.update(tags)
            if len(hits)<60:hits.append({"pointer":ptr,"tags":tags,"excerpt":s[:350],"text_sha256":sha(s.encode())})
        docs.append({"path":path,"git_blob_sha":h,"counts":dict(counts),"hits":hits,"claim_ceiling":"DISCOVERY_ONLY"})
    except Exception as e:fails.append({"path":path,"error":repr(e)[:200]})
def fetch(url,cap=20000000):
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"JANUS R1.8 public archival research"}),timeout=40) as f:
        b=f.read(cap+1);assert len(b)<=cap
        return b,{"url":url,"bytes":len(b),"sha256":sha(b),"status":f.status}
cases=[]
for s in p["sources"]:
    x={**s,"acquisition":"HOLD","timing_gate":"HOLD_NO_CALIBRATED_EMISSION_ARRIVAL_PATH","physical_claim":False}
    try:
        b,m=fetch(s["url"]);assert b.startswith(b"%PDF");pdf=PdfReader(io.BytesIO(b));pages=[a.extract_text() or "" for a in pdf.pages];t=" ".join(" ".join(pages).split());ok=all(z.lower() in t.lower() for z in s["markers"])
        x.update(receipt=m,pages=len(pages),marker_match=ok,acquisition="PRIMARY_REPORT_VERIFIED" if ok else "HOLD_TEXT_MARKERS",page_hits=[{"page":i+1,"tags":[k for k,v in patterns.items() if v.search(t)]} for i,t in enumerate(pages)])
    except Exception as e:x["error"]=repr(e)[:300]
    cases.append(x)
geo=q["geo"];reports=[]
for r in geo["phoenix_reports"]:
    x={k:r.get(k) for k in ("id","observer_locality","local_time","time_precision","record_kind","source_url","utc","object_coordinates","verified_track")}
    try:
        t=dt.datetime.fromisoformat(r["local_time"].replace("Z","+00:00"));assert t.tzinfo is not None;x["computed_utc"]=t.astimezone(dt.timezone.utc).isoformat()
    except Exception as e:x["time_error"]=repr(e)[:150]
    reports.append(x)
cases.append({"id":"PHOENIX","date":"1997-03-13","region":"Arizona/Nevada report localities","acquisition":"PINNED_REGISTRY_REPORTS","reports":reports,"track_status":geo["phoenix_track_status"],"timing_gate":"HOLD_NO_COMMON_OBJECT_OR_CALIBRATED_CLOCKS","alternatives":["aircraft formation","flares","separate reports","observer timing errors","unknown object"],"physical_claim":False})
cases.append({"id":"FAA_AZ","date":"2023-01-19","region":"Arizona","acquisition":"PINNED_PRIMARY_FAA_RECEIPT","source_sha256":q["primary"]["faa"]["sha256"],"record_status":q["primary"]["faa"]["status"],"timing_gate":"HOLD_NO_CALIBRATED_TRACK_OR_RF_WAVEFORM","alternatives":["reported UAS contact","ordinary aircraft hazard","unknown operator"],"physical_claim":False})
weather=[]
for w in p["weather"]:
    x={**w,"status":"HOLD","object_witness":False}
    url=f"https://www.ncei.noaa.gov/data/global-hourly/access/{w['year']}/{w['station']}.csv"
    try:
        b,m=fetch(url,30000000);rr=list(csv.DictReader(io.StringIO(b.decode("utf-8-sig"))));assert rr and all(r["STATION"]==w["station"] for r in rr)
        windows=[]
        for lo,hi in w["windows"]:
            rows=[]
            for r in rr:
                t=r["DATE"]
                if lo<=t<=hi:rows.append({k:r.get(k) for k in ("DATE","STATION","NAME","LATITUDE","LONGITUDE","ELEVATION","WND","VIS","TMP","DEW","SLP","GA1","REPORT_TYPE","QUALITY_CONTROL")})
            windows.append({"start_utc":lo,"end_utc":hi,"rows":rows})
        x.update(receipt=m,status="CONTEXT_ROWS_ACQUIRED" if any(v["rows"] for v in windows) else "HOLD_NO_WINDOW_ROWS",matched_windows=windows)
    except Exception as e:x["error"]=repr(e)[:350]
    weather.append(x)
def gate(m):
    required=("common_event","emission_authenticated","clock_calibrated","path_authenticated","front_measured")
    if not all(m.get(k) for k in required):return "HOLD_MISSING_MEASUREMENT"
    if m["dt_s"]+m["uncertainty_s"]<m["L_min_m"]/299792458:return "TIMING_CONFLICT_CANDIDATE_ONLY"
    return "COMPATIBLE_OR_UNRESOLVED"
base=dict(common_event=True,emission_authenticated=True,clock_calibrated=True,path_authenticated=True,front_measured=True,dt_s=1e-5,uncertainty_s=1e-7,L_min_m=3000.)
controls=[]
for name,change,expected in [("early",{"dt_s":8e-6},"TIMING_CONFLICT_CANDIDATE_ONLY"),("ordinary",{"dt_s":11e-6},"COMPATIBLE_OR_UNRESOLVED"),("uncertain",{"dt_s":8e-6,"uncertainty_s":3e-6},"COMPATIBLE_OR_UNRESOLVED"),("clock_missing",{"clock_calibrated":False},"HOLD_MISSING_MEASUREMENT"),("emitter_missing",{"emission_authenticated":False},"HOLD_MISSING_MEASUREMENT"),("path_missing",{"path_authenticated":False},"HOLD_MISSING_MEASUREMENT"),("front_missing",{"front_measured":False},"HOLD_MISSING_MEASUREMENT"),("identity_missing",{"common_event":False},"HOLD_MISSING_MEASUREMENT")]:
    m={**base,**change};a=gate(m);assert a==expected;controls.append({"id":name,"measurement":m,"result":a,"expected":expected,"physical_claim":False})
for x in cases:
    x["timing_measurement"]={k:None for k in ("dt_s","uncertainty_s","L_min_m","emission_authenticated","clock_calibrated","path_authenticated","front_measured","common_event")}
    x["numeric_timing_gate"]=gate(x["timing_measurement"])
    x["carrier_specific_response"]=False
    x["paired_waveform_admitted"]=False
    x["inverse_candidates"]=[{"hypothesis":h,"state":"OPEN_OR_PUBLISHED_ASSESSMENT_ONLY"} for h in x["alternatives"]]+[{"hypothesis":"hypothetical tachyon carrier","state":"NOT_IDENTIFIABLE_WITH_AVAILABLE_DATA"}]
    x["case_sha256"]=dig(x)
fr=q["frb"];control={"role":"ORDINARY_ASTROPHYSICAL_CONTROL_ONLY","profiles":fr["profiles"],"processed":fr["processed"],"distribution":fr["distribution"],"reconstruction":fr["reconstruction"],"not_uap_witness":True,"R17A":"parallel ongoing experiment, not used","gwosc":q["control"]["gwosc"]["event"],"gwosc_role":"known two-receiver timing control, not TOF"}
axes=read("data/JANUS-DEEP-ANALYSIS-5D-SPIRAL-ORIGIN-PRIME-ORACLE-PROTOCOL-2026-08-21-v2.1.json")["five_dimensions"]
state={"known":["prior H4/H5 HOLD"],"alternatives":["ordinary source","instrument fault","common cause","clock/path error","uncharacterized signal","hypothetical carrier"],"gaps":["calibrated paired raw UAP observations","exclusive carrier response"]};turns=[]
for k,delta in [("D1_TEMPORAL",[dig(reports),f"timing controls {len(controls)}"]),("D2_MIRROR",["arrival order not causal direction","reverse FRB shape not carrier"]),("D3_HIERARCHY",[dig([x["case_sha256"] for x in cases]),"competing histories preserved"]),("D4_ASSOCIATIVE",[dig(weather),f"documents {len(docs)}/{len(inventory)}"]),("D5_PROVENANCE",[dig(p["pins"]),dig(control),"zero physical promotion"])]:
    h=dig(state);state={**state,"known":sorted(set(state["known"])|set(delta))};turns.append({"anchor":k,"axes":axes,"parent":h,"state":dig(state),"delta":delta})
out={"schema":"janus.uap_tachyon.reconnection.result.v1","status":"UAP_RECONNECTION_EXECUTED__PAIRED_MEASUREMENT_HOLD__PHYSICAL_CAUSALITY_HOLD","source_commit":p["source_commit"],"protocol_sha256":sha(P.read_bytes()),"scan":{"planned":len(inventory),"parsed":len(docs),"with_hits":sum(bool(x["hits"]) for x in docs),"by_tag":{k:sum(k in d["counts"] for d in docs) for k in patterns},"failed":fails,"docs":docs},"cases":cases,"weather":weather,"timing_controls":controls,"ordinary_controls":control,"origin_prime_turns":turns,"origin_prime":state,"admitted_paired_uap_measurements":0,"physical_retrocausality_confirmed":False,"production_changed":False,"actual_vetoes":0}
O.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
print(json.dumps({"status":out["status"],"scan":{k:v for k,v in out["scan"].items() if k!="docs"},"cases":[{k:v for k,v in x.items() if k in ("id","acquisition","marker_match","timing_gate","numeric_timing_gate","error","receipt")} for x in cases],"weather":weather,"timing_controls":len(controls),"FRB_profiles":fr["profiles"],"paired":0},sort_keys=True))
