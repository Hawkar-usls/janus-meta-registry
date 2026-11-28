#!/usr/bin/env python3
import hashlib, json, pathlib, re, datetime, urllib.request, urllib.error, zipfile, io, subprocess
from zoneinfo import ZoneInfo
from openpyxl import load_workbook
ROOT=pathlib.Path("registry/uap")
REPORT=ROOT/"JANUS-UAP-R1.2-SPATIOTEMPORAL-RECONSTRUCTION-2026-11-28-v1.0.json"
OUT=ROOT/"JANUS-UAP-R1.2-PRIMARY-ACQUISITION-2026-11-28-v1.0.json"
report=json.loads(REPORT.read_text())
sources={s["id"]:s["url"] for s in report["sources"]}
def get(key,cap):
    url=sources[key]
    req=urllib.request.Request(url,headers={"User-Agent":"JANUS archival research/1.2 (public-source verification)","Accept":"*/*"})
    with urllib.request.urlopen(req,timeout=55) as resp:
        data=resp.read(cap+1)
        if len(data)>cap:raise ValueError("size cap exceeded")
        return data,{"url":url,"final_url":resp.geturl(),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),"http_status":resp.status,"content_type":resp.headers.get("Content-Type")}
def iso(v):
    return v.isoformat() if isinstance(v,(datetime.date,datetime.datetime,datetime.time)) else v
def error(e):
    return {"status":"INPUT_ACQUISITION_OR_PARSE_BLOCKED","error":str(e)[:500]}
for r in report["phoenix_reports"]:
    if r["local_time"]:
        t=datetime.datetime.fromisoformat(r["local_time"])
        assert t.astimezone(datetime.timezone.utc)==datetime.datetime.fromisoformat(r["utc"].replace("Z","+00:00"))
        zone=ZoneInfo("America/Los_Angeles" if r["state"]=="NV" else "America/Phoenix")
        assert t.utcoffset()==t.replace(tzinfo=zone).utcoffset()
    assert r["object_coordinates"] is None and not r["verified_track"]
faa={}
try:
    data,proof=get("FAA_XLSX",25_000_000)
    if not data.startswith(b"PK"):raise ValueError("not an XLSX ZIP")
    wb=load_workbook(io.BytesIO(data),read_only=True,data_only=True)
    hits=[]; scanned=0;sheets=[]
    for ws in wb:
        sheets.append(ws.title)
        for idx,row in enumerate(ws.iter_rows(values_only=True),1):
            scanned+=1
            vals=[iso(v) for v in row]
            txt=" ".join(str(v) for v in vals if v is not None)
            datehit=bool(re.search(r"2023-01-19|01/19/2023|1/19/2023|19 Jan(?:uary)? 2023|Jan(?:uary)? 19,? 2023|1/19/23|01/19/23",txt,re.I))
            eventhit=bool(re.search(r"F[- ]?16|R[- ]?2301E|orange.{0,20}white|white.{0,20}orange",txt,re.I))
            if datehit and eventhit:
                hits.append({"sheet":ws.title,"row_number":idx,"cells":[{"column":i+1,"value":v} for i,v in enumerate(vals) if v is not None]})
    faa={**proof,"status":"ORIGINAL_XLSX_PARSED__CANDIDATE_ROWS_FOUND" if hits else "ORIGINAL_XLSX_PARSED__TARGET_NOT_LOCATED","sheets":sheets,"rows_scanned":scanned,"candidate_rows":hits,"match_rule":"date AND aircraft/range/color terms; candidate match requires manual adjudication"}
except Exception as exc:faa=error(exc)
nara={}
try:
    data,proof=get("NARA_METADATA",105_000_000)
    obj=json.loads(data)
    # Only title fields are screened; no inferred event locality from description or archive location.
    pat=re.compile(r"\b(?:Nevada|Arizona|Henderson|Las Vegas|Elko|Tonopah|Phoenix|Tucson|Prescott|Kingman|Reno|Nellis|Yuma|Flagstaff)\b",re.I)
    rows=[];titles_seen=0
    def walk(v):
        global titles_seen
        if isinstance(v,dict):
            for k,w in v.items():
                if k.lower() in ("title","recordtitle","record_title") and isinstance(w,str):
                    titles_seen+=1
                    if pat.search(w):
                        rows.append({"title":w[:500],"naid":v.get("naId",v.get("naid",v.get("id"))),"terms":sorted(set(x.group() for x in pat.finditer(w)))})
                if isinstance(w,(dict,list)):walk(w)
        elif isinstance(v,list):
            for w in v:walk(w)
    walk(obj)
    # Avoid claiming archive completeness; metadata title matches are not verified sightings.
    nara={**proof,"status":"METADATA_PARSED__TITLE_CANDIDATES" if titles_seen else "METADATA_PARSED__TITLE_SCHEMA_UNRESOLVED","titles_seen":titles_seen,"candidate_count":len(rows),"candidates":rows,"claim_ceiling":"Title mentions only; verify actual case card and state/date separately."}
except Exception as exc:nara=error(exc)
# DOE exact-date join requires machine-readable chronology, not guessing from source coverage.
# Official catalog landing page is pinned by source URL, and a PDF link is discovered only on the official govinfo host.
doe={}
try:
    data,proof=get("DOE",5_000_000)
    doe={**proof,"status":"OFFICIAL_CATALOG_LANDING_RETRIEVED__EXACT_DATE_JOIN_NOT_EXECUTED","case_dates":["1952-10-17","1957-11-23"],"claim_ceiling":"Catalog metadata does not establish date-level test absence."}
except Exception as exc:doe=error(exc)
result={"schema":"janus.uap.primary_acquisition.v1.0","date":"2026-11-28","authority_changed":False,"status":"ACQUISITION_EXECUTED__SOURCE_SPECIFIC_RESULTS","parent_report":str(REPORT),"faa":faa,"nara":nara,"doe":doe,"time_validation":"PASS","physical_track_claim":"NOT_IDENTIFIED"}
OUT.write_text(json.dumps(result,ensure_ascii=True,indent=2,allow_nan=False)+"\n")
assert json.loads(OUT.read_text())==result
print(json.dumps({"faa":faa["status"],"faa_candidate_count":len(faa.get("candidate_rows",[])),"nara":nara["status"],"nara_candidates":nara.get("candidate_count"),"doe":doe["status"],"time_validation":"PASS"}))
