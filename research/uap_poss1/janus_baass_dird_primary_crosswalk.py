import csv,hashlib,io,json,pathlib,re,time,urllib.request,urllib.parse,datetime,collections,concurrent.futures
from pypdf import PdfReader
R=pathlib.Path.cwd();P=R/"registry/uap/JANUS-BAASS-DIRD-PRIMARY-SOURCE-CROSSWALK-2026-11-28-v1.0.json";O=R/"registry/uap/JANUS-BAASS-DIRD-PRIMARY-SOURCE-ACQUISITION-2026-11-28-v1.0.json";p=json.loads(P.read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
def norm(s):return " ".join(re.findall(r"[a-z0-9]+",s.lower()))
def get(url,cap):
    start=time.monotonic()
    with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"JANUS public archival bibliography"}),timeout=35) as f:
        buf=bytearray()
        while True:
            b=f.read(1024*1024)
            if not b:break
            buf.extend(b)
            if len(buf)>cap:raise ValueError("BYTE_CAP")
            if time.monotonic()-start>120:raise TimeoutError("TRANSFER_DEADLINE")
        b=bytes(buf);return b,{"url":url,"final_url":f.geturl(),"bytes":len(b),"sha256":sha(b),"http_status":f.status,"retrieved_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
def pdf(s,cap):
    x={"id":s["id"],"status":"HOLD"}
    try:
        b,m=get(s["url"],cap);x["receipt"]=m;assert b.startswith(b"%PDF")
        if "sha256" in s:assert m["sha256"]==s["sha256"] and m["bytes"]==s["bytes"]
        r=PdfReader(io.BytesIO(b))
        if r.is_encrypted and not r.decrypt(""):raise ValueError("PASSWORD_REQUIRED")
        pages=[]
        for i,z in enumerate(r.pages):
            try:pages.append(z.extract_text() or "")
            except Exception as e:pages.append("");x.setdefault("page_errors",[]).append({"page":i+1,"error":repr(e)[:150]})
        x.update(status="PDF_ACQUIRED",pages=len(pages),text_pages=sum(bool(t.strip()) for t in pages),page_sha256=[sha(t.encode()) for t in pages])
        return x,pages
    except Exception as e:x["error"]=repr(e)[:250];return x,[]
def hits(pages,titles):
    out=[]
    for i,t in enumerate(pages):
        n=norm(t)
        for title in titles:
            q=norm(title)
            if q and re.search(r"(?<!\w)"+re.escape(q)+r"(?!\w)",n):
                out.append({"page":i+1,"title":title,"page_sha256":sha(t.encode()),"line_sha256":[sha(l.encode()) for l in t.splitlines() if q in norm(l)],"relation":"EXACT_NORMALIZED_PAGE_TEXT_MATCH__NOT_IDENTITY_PROOF"})
    return out
ba,bpages=pdf(p["parent_BAASS"],100663296)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    z=list(pool.map(lambda s:pdf(s,25000000),p["sources"]))
by={s["id"]:(x,pg) for s,(x,pg) in zip(p["sources"],z)}
memo=by["DIA_MEMO_2009"][1];rows=[]
for s,(x,pg) in zip(p["sources"],z):
    names=[s["title"]]+s.get("aliases",[])
    x.update(role=s["role"],expected_title=s["title"],title_hits=hits(pg[:3],names),BAASS_matches=hits(bpages,names),memo_matches=hits(memo,names) if s["id"]!="DIA_MEMO_2009" else [],physical_claim_verified=False)
    rows.append(x)
    print("DIRD",s["id"],x["status"],len(x["BAASS_matches"]),flush=True)
papers=[]
for s in p["papers"]:
    x={**s,"status":"HOLD","source_page_match":False,"bibliographic_match":False,"physical_claim_verified":False}
    pg=by[s["source"]][1];x["source_page_hits"]=hits(pg,[s["title"]]);x["source_page_match"]=any(h["page"]==s["page"] for h in x["source_page_hits"])
    try:
        b,m=get("https://api.crossref.org/works/"+urllib.parse.quote(s["doi"],safe="/"),2000000);x["receipt"]=m;d=json.loads(b)["message"];t=(d.get("title") or [""])[0];yr=(d.get("published",{}).get("date-parts") or [[None]])[0][0];x.update(resolved_title=t,resolved_year=yr,resolved_doi=d.get("DOI"),bibliographic_match=norm(t)==norm(s["title"]) and yr==s["year"] and d.get("DOI","").lower()==s["doi"].lower(),status="METADATA_RESOLVED")
    except Exception as e:x["error"]=repr(e)[:200]
    papers.append(x)
out={"schema":"janus.baass.dird.primary_acquisition.v1","status":"BOUNDED_PRIMARY_CROSSWALK_EXECUTED__PHYSICAL_CLAIMS_HOLD","catalog_sha256":sha(P.read_bytes()),"BAASS":ba,"sources":rows,"papers":papers,"official_pdfs_acquired":sum(x["status"]=="PDF_ACQUIRED" for x in rows),"BAASS_title_link_count":sum(bool(x["BAASS_matches"]) for x in rows if x["id"]!="DIA_MEMO_2009"),"memo_title_link_count":sum(bool(x["memo_matches"]) for x in rows),"paper_bibliographic_matches":sum(x["bibliographic_match"] for x in papers),"paper_source_page_matches":sum(x["source_page_match"] for x in papers),"physical_claims_confirmed":0,"production_changed":False}
O.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
print(json.dumps({k:v for k,v in out.items() if k not in ("sources","BAASS","papers")}|{"sources":[{k:v for k,v in x.items() if k!="page_sha256"} for x in rows],"papers":papers},sort_keys=True))
