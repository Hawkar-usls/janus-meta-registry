#!/usr/bin/env python3
import collections,concurrent.futures,csv,datetime,hashlib,html.parser,io,json,pathlib,re,urllib.parse,urllib.request
R=pathlib.Path.cwd();U=R/"registry/uap"
P=U/"JANUS-UAP-TACHYON-OPEN-EVIDENCE-CATALOG-2026-11-28-v1.0.json"
O=U/"JANUS-UAP-TACHYON-OPEN-EVIDENCE-ACQUISITION-2026-11-28-v1.0.json"
p=json.loads(P.read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def safeurl(u):
    z=urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit((z.scheme,z.netloc,z.path,z.query if z.netloc.endswith("zenodo.org") else "",""))
def fetch(s):
    req=urllib.request.Request(s["url"],headers={"User-Agent":"JANUS open scientific metadata intake/1.0","Accept":"*/*"})
    with urllib.request.urlopen(req,timeout=25) as f:
        b=f.read(s["cap"]+1)
        if len(b)>s["cap"]:raise ValueError("BYTE_CAP")
        return b,{"url":s["url"],"final_url":safeurl(f.geturl()),"http_status":f.status,"content_type":f.headers.get("Content-Type"),"bytes":len(b),"sha256":sha(b),"retrieved_utc":now()}
def clean_key(k):return re.sub(r"[^a-z0-9]","",k.lower())
allowed={"id","fileid","recordid","documentid","title","name","agency","agencyid","publisher","release","releasedate","releaseid","releasenumber","incidentdate","incidentlocation","eventdate","eventlocation","date","publicationdate","published","filetype","type","mediatype","recordtype","url","sourceurl","officialurl","officiallandingurl","originalurl","downloadurl","archiveurl","archiveurls","hostedurl","hostedcopy","sha256","checksum","pagecount","pages","bytes","size","fulltextjsonurl","license","status","naid","slug","filename","sourcefile","sourcefilename","fileurl","link","originalfileurl","mediaurl","released","filetitle","recordtitle","location","descriptionurl"}
def metadata(row):
    if not isinstance(row,dict):return {}
    out={}
    for k,v in row.items():
        nk=clean_key(str(k))
        if nk not in allowed:continue
        if v is None or isinstance(v,(int,float,bool)):out[k]=v
        elif isinstance(v,str):out[k]=v[:2000]
        elif isinstance(v,list) and all(isinstance(i,str) for i in v):out[k]=[i[:2000] for i in v[:30]]
        elif isinstance(v,dict):out[k]=metadata(v)
    return out
def list_rows(j):
    if isinstance(j,list):return j
    if isinstance(j,dict):
        for k in ("records","documents","files","items","entries","data","results","catalog"):
            if k in j:
                x=list_rows(j[k])
                if x:return x
    return []
def csvrows(b):
    if b.lstrip().startswith(b"<"):raise ValueError("HTML_NOT_CSV")
    for enc in ("utf-8-sig","cp1252"):
        try:
            t=b.decode(enc);dialect=csv.Sniffer().sniff(t[:12000],delimiters=",;\t");r=csv.DictReader(io.StringIO(t),dialect=dialect)
            rows=list(r)
            if len(r.fieldnames or [])<2:raise ValueError("CSV_HEADERS")
            return r.fieldnames,rows
        except (UnicodeError,csv.Error):continue
    raise ValueError("CSV_PARSE")
class Links(html.parser.HTMLParser):
    def __init__(self,base):super().__init__();self.base=base;self.links=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);u=a.get("href")
        if not u:return
        u=urllib.parse.urljoin(self.base,u);z=urllib.parse.urlsplit(u)
        if z.scheme not in ("http","https"):return
        if re.search(r"\.(pdf|json|csv|zip|xlsx|mp4|webm|fits|h5|hdf5|wav)(?:$|[?#])|catalog-export-|/sightings-reports/|/videoid/",u,re.I):
            self.links.append(u)
def inspect(s):
    x={"id":s["id"],"requested_url":s["url"],"status":"HOLD"}
    try:
        b,m=fetch(s);x.update(receipt=m)
        fmt=s["format"]
        if fmt in ("csv","case_schema"):
            hdr,rows=csvrows(b);x.update(headers=hdr,row_count=len(rows))
            if fmt=="csv":
                x["records"]=[metadata(r) for r in rows];x["nonempty_metadata_rows"]=sum(bool(r) for r in x["records"])
            else:x["privacy"]="case CSV acquired and counted; no individual case or witness rows copied"
        elif fmt=="json":
            j=json.loads(b);x["root_keys"]=list(j) if isinstance(j,dict) else None
            if s["id"].endswith("CHECKSUMS"):x["published_checksums"]=j
            else:
                rows=list_rows(j);x.update(row_count=len(rows),records=[metadata(r) for r in rows]);x["nonempty_metadata_rows"]=sum(bool(r) for r in x["records"])
                if not rows:raise ValueError("NO_RECORD_LIST")
        elif fmt=="zenodo":
            j=json.loads(b);md=j.get("metadata",{});x["deposit"]={k:md.get(k) for k in ("title","publication_date","version","license","doi","resource_type","access_right")};x["doi"]=j.get("doi");x["files"]=[{"key":f.get("key"),"size":f.get("size"),"checksum":f.get("checksum"),"download":f.get("links",{}).get("self")} for f in j.get("files",[])];x["file_count"]=len(x["files"])
        elif fmt=="numeric_control":
            j=json.loads(b);x["numeric_control_data"]=j;x["row_count"]=len(j.get("data",[])) if isinstance(j,dict) else len(j)
        elif fmt=="links":
            h=Links(s["url"]);h.feed(b.decode("utf-8","replace"));x["asset_links"]=sorted(set(h.links));x["asset_link_count"]=len(x["asset_links"])
        x["status"]="ACQUIRED_AND_PARSED"
    except Exception as e:x["error"]=repr(e)[:400]
    return x
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:r=list(pool.map(inspect,p["acquisition_plan"]))
by={x["id"]:x for x in r}
# The official endpoint, mirrors, and their counts remain separate evidence sources.
summary={}
for k in ("PURSUE_CSV","PURSUE_ARCHIVE_JSON","PURSUE_TRACKER_CSV"):
    x=by[k];rr=x.get("records",[]);counts=collections.Counter()
    ids=collections.Counter()
    for a in rr:
        for key,v in a.items():
            if clean_key(key) in ("release","releasedate","releaseid","releasenumber") and v is not None:
                counts[str(v)]+=1;break
        for i in set(re.findall(r"\b(?:DOW|FBI|CIA|NASA|ODNI|USG|DOE|DOS)-UAP-(?:PR|D)\d+\b",json.dumps(a,ensure_ascii=False),re.I)):ids[i.upper()]+=1
    summary[k]={"status":x["status"],"rows":x.get("row_count"),"release_labels":dict(counts),"distinct_pattern_ids":len(ids),"priority_ids_found":{i:ids[i] for i in sorted(ids) if any(i in q["id"] for q in p["priority_targets"])}}
result={"schema":"janus.uap_tachyon.open_evidence_acquisition.v1","status":"BOUNDED_OPEN_METADATA_ACQUISITION_EXECUTED__PHYSICAL_CLAIMS_HOLD","catalog_sha256":sha(P.read_bytes()),"retrieved_utc":now(),"source_catalog_count":p["source_count"],"planned_probes":len(r),"parsed_probes":sum(x["status"]=="ACQUIRED_AND_PARSED" for x in r),"pursue_counts":summary,"receipts":r,"limits":["Raw videos, giant archives and witness data not downloaded in this pass; only selected metadata and numeric controls.","Mirrors are secondary; exact primary comparison requires successful original byte acquisition and revision equality.","Numeric controls are not UAP events; no coincidence analysis performed.","Acquired catalog rows are records not independent physical observations."],"physical_retrocausality_confirmed":False,"production_changed":False}
O.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
print(json.dumps({"status":result["status"],"planned_probes":len(r),"parsed_probes":result["parsed_probes"],"pursue_counts":summary,"receipts":[{k:v for k,v in x.items() if k in ("id","status","error","row_count","file_count","asset_link_count","receipt")} for x in r]},sort_keys=True))
