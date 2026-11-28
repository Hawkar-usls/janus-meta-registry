#!/usr/bin/env python3
"""Pinned, read-only JSON corpus scan; no inference of physical tachyons."""
import collections, hashlib, json, pathlib, re, subprocess
from urllib.parse import urlsplit
ROOT=pathlib.Path("registry/uap")
M=ROOT/"JANUS-TACHYON-MASTER-INDEX-2026-11-28-v1.0.json"
C=ROOT/"JANUS-UAP-TACHYON-CROSS-CORPUS-2026-11-28-v1.0.json"
U=ROOT/"JANUS-UAP-R1.1-CURATED-CORE-2026-11-28-v1.0.json"
UG=ROOT/"JANUS-UAP-MASTER-INDEX-2026-11-28-v1.0.json"
source="a927c3e46f78adff4ab586019f5caec29939b04b"
def git(*a):return subprocess.check_output(["git",*a])
def read(p):return json.loads(p.read_text(encoding="utf-8"))
def write(p,v):
    s=json.dumps(v,ensure_ascii=True,indent=2,allow_nan=False)+"\n"
    p.write_text(s,encoding="utf-8");assert read(p)==v
seed=read(C);base=read(M);ucore=read(U);umaster=read(UG)
u_narrow={x["path"] for x in ucore["inventory"]}
u_wide={x["path"] for x in umaster["inventory"]}
explicit=re.compile(r"tachyon|tahyon|тахион|retrocaus|retro.byte|retro.sha|deutsch|temporal.signal|simptomat",re.I)
term=re.compile(r"tachyons?|tahyons?|тахион[а-яё]*|ретрокаузаль[а-яё]*|retro[-_ ]?causal\w*|retro[-_ ]?tahyon|retro[-_ ]?tachyon|reverse information flow|backward causation|closed timelike curves?|Deutsch.{0,15}CTC|Deutsch.{0,15}calibrator|retro[-_ ]?byte|retro[-_ ]?sha|temporal signal search|simptomat",re.I)
u_term=re.compile(r"(?<![A-Za-z])(?:UAPs?|UFOs?|NUFORC|AARO|AAWSAP|AATIP|Blue Book|POSS[-_ ]?(?:I|1)|Palomar|Phoenix Lights)(?![A-Za-z])|НЛО|unidentified (?:aerial|anomalous) phenomena",re.I)
refpat=re.compile(r"(?:data|registry|experiments|research|EYE|artifacts)/[A-Za-z0-9_./-]+\.json\b")
idpat=re.compile(r"\b(?:JANUS|EYE|PALOMAR|TOPA)[A-Z0-9_.-]*-[A-Z0-9_.-]{5,}",re.I)
fields=("artifact_id","record_id","title","title_ru","schema","version","status","scientific_status","claim_ceiling","verdict","one_line_verdict","admitted_claim","negative_findings","epistemic_limits","admitted_interpretation")
def compact(v,limit=6000):
    return v if len(json.dumps(v,ensure_ascii=True))<=limit else {"value_omitted":True}
def esc(k):return str(k).replace("~","~0").replace("/","~1")
def walk(v,p=""):
    if isinstance(v,dict):
        for k,w in v.items():
            q=p+"/"+esc(k);yield ("key",q,k);yield from walk(w,q)
    elif isinstance(v,list):
        for i,w in enumerate(v):yield from walk(w,p+"/"+str(i))
    elif isinstance(v,str):yield ("value",p,v)
def group(path):
    p=path.lower()
    if p.startswith("artifacts/") or p.startswith("eye/generated/"):return "DERIVATIVE"
    if "tachyon_star" in p or "tachyon-star" in p:return "TACHYON_STAR"
    if "traveler" in p:return "TRAVELER"
    if "simptomat" in p:return "SIMPTOMAT"
    if "demihead" in p:return "DEMIHEAD"
    if "rule-001" in p or "subjective-time" in p:return "RULE_001_PERCEPTION"
    if "physarum" in p or "thermal-reverse" in p:return "THERMAL_PHYSARUM"
    if "child-protection" in p:return "CONTEXT_NUCLEAR_CAUSAL_ANCHORS"
    if "declassified" in p:return "ARCHIVAL_BRIDGE"
    if "competing-model" in p or p.startswith("eye/"):return "EYE_MODEL_IDENTIFIABILITY"
    if "deutsch" in p or "retro-sha" in p or "retro-byte" in p or "retro" in p or "temporal-signal" in p:return "RETRO_INFORMATION"
    return "OTHER_EXPLICIT_TOPIC"
def clean(s):
    if not s.startswith(("https://","http://")) or len(s)>1500:return False
    try:
        x=urlsplit(s)
        return bool(x.netloc) and not x.username and not re.search(r"(?:token|secret|signature|password|credential|api[_-]?key)=",x.query,re.I)
    except ValueError:return False
blobs={}
for line in git("ls-tree","-rz","-l","--full-tree",source).split(b"\0"):
    if not line:continue
    header,path=line.split(b"\t",1);mode,kind,sha,size=header.decode().split();path=path.decode("utf-8","surrogateescape")
    if kind=="blob" and path.lower().endswith(".json"):blobs[path]={"path":path,"git_blob_sha":sha,"size_bytes":int(size)}
docs={}; failures=[]; ids=collections.defaultdict(list); refrows=[]; refids=[]; parsed=0; recovered=0
def reject(s):raise ValueError(s)
proc=subprocess.Popen(["git","cat-file","--batch"],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
try:
    for path,b in sorted(blobs.items()):
        proc.stdin.write((b["git_blob_sha"]+"\n").encode());proc.stdin.flush()
        hdr=proc.stdout.readline().split()
        if len(hdr)!=3 or hdr[0].decode()!=b["git_blob_sha"] or hdr[1]!=b"blob":raise RuntimeError("unexpected blob header "+path)
        n=int(hdr[2]);data=proc.stdout.read(n)
        if len(data)!=n or proc.stdout.read(1)!=b"\n":raise RuntimeError("short blob read "+path)
        enc="utf-16" if data.startswith((b"\xff\xfe",b"\xfe\xff")) else "utf-8-sig"
        try:
            raw=data.decode(enc)
            obj=json.loads(raw,parse_constant=reject)
        except (UnicodeError,ValueError,RecursionError) as e:
            failure={**b,"error":str(e)[:350],"encoding":enc}
            try:
                hits=list(term.finditer(data.decode(enc)))
                failure["raw_text_term_count"]=len(hits)
                failure["raw_text_terms"]=sorted(set(x.group().lower() for x in hits))
            except UnicodeError:failure["raw_text_term_count"]=None
            failures.append(failure)
            if explicit.search(path):docs[path]={**b,"tier":"PATH_MATCH_PARSE_FAILED","group":group(path),"match_count":0,"matches":[],"uap_mentions":[],"source_links":[],"metadata":{}}
            continue
        parsed+=1;recovered+=int(enc=="utf-16")
        meta={}
        if isinstance(obj,dict):
            meta={k:compact(obj[k]) for k in fields if k in obj}
            for k in ("artifact_id","record_id"):
                if isinstance(obj.get(k),str):ids[obj[k]].append(path)
        matches=[]; uap=[]; links=[]; nmatch=0; nuap=0; terms=set(); ut=set(); localrefs=[]; localids=[]
        for kind,p,s in walk(obj):
            ms=list(term.finditer(s))
            if ms:
                nmatch+=1;terms.update(x.group().lower() for x in ms)
                if len(matches)<80:
                    a=ms[0].start();excerpt=s if len(s)<=1000 else s[max(0,a-180):a+250]
                    matches.append({"pointer":p,"kind":kind,"terms":sorted(set(x.group() for x in ms)),"excerpt":excerpt,"is_excerpt":len(s)>1000})
            us=list(u_term.finditer(s))
            if us:
                nuap+=1;ut.update(x.group().lower() for x in us)
                if len(uap)<20:uap.append({"pointer":p,"kind":kind,"terms":sorted(set(x.group() for x in us))})
            for m in refpat.finditer(s):
                dest=m.group()
                if dest in blobs and dest!=path:localrefs.append({"from":path,"to":dest,"pointer":p,"relation":"EXPLICIT_PATH_REFERENCE"})
            if kind=="value":
                for m in idpat.finditer(s):localids.append((path,m.group().rstrip("."),p))
                if clean(s):links.append({"pointer":p,"url":s})
        refrows.extend(localrefs);refids.extend(localids)
        pathhit=bool(explicit.search(path))
        if not pathhit and not nmatch:continue
        derivative=path.startswith(("EYE/generated/","artifacts/")) or path.startswith("registry/uap/JANUS-UAP-R1")
        top_identity=" ".join(str(obj.get(k,"")) for k in ("artifact_id","title","title_ru","record_id")) if isinstance(obj,dict) else ""
        tier="DERIVATIVE_DISCOVERY" if derivative else "DIRECT_TOPIC" if pathhit or term.search(top_identity) else "CONTENT_MENTION_REVIEW"
        docs[path]={**b,"tier":tier,"group":group(path) if tier=="DIRECT_TOPIC" else ("DERIVATIVE" if derivative else "CONTENT_MENTION"),"encoding":enc,"metadata":meta,"match_count":nmatch,"terms":sorted(terms),"matches":matches,"omitted_match_rows":max(0,nmatch-len(matches)),"uap_match_count":nuap,"uap_terms":sorted(ut),"uap_mentions":uap,"omitted_uap_rows":max(0,nuap-len(uap)),"source_links":links[:120],"source_link_count":len(links),"omitted_source_links":max(0,len(links)-120)}
finally:
    proc.stdin.close()
    if proc.wait()!=0:raise RuntimeError("git cat-file failed")
assert parsed+len(failures)==len(blobs)
for path,identifier,p in refids:
    dest=ids.get(identifier,[])
    if len(dest)==1 and dest[0]!=path:refrows.append({"from":path,"to":dest[0],"pointer":p,"relation":"UNIQUE_ARTIFACT_ID_REFERENCE","artifact_id":identifier})
def uniq(items,keys):
    return sorted({tuple(x.get(k,"") for k in keys):x for x in items}.values(),key=lambda x:tuple(x.get(k,"") for k in keys))
edges=uniq([x for x in refrows if x["from"] in docs or x["to"] in docs],("from","to","pointer","relation"))
direct={p for p,d in docs.items() if d["tier"]=="DIRECT_TOPIC"}
direct_uap=direct & u_narrow
shared_all=set(docs)&u_narrow
wide_shared=set(docs)&u_wide
cross_edges=[x for x in edges if (x["from"] in direct and x["to"] in u_narrow) or (x["to"] in direct and x["from"] in u_narrow)]
co_mentions=[{"path":p,"git_blob_sha":d["git_blob_sha"],"tier":d["tier"],"tachyon_terms":d.get("terms",[]),"uap_terms":d.get("uap_terms",[]),"tachyon_match_count":d["match_count"],"uap_match_count":d.get("uap_match_count",0),"tachyon_pointers":[x["pointer"] for x in d.get("matches",[])[:5]],"uap_pointers":[x["pointer"] for x in d.get("uap_mentions",[])[:5]]} for p,d in sorted(docs.items()) if d.get("uap_match_count")]
# Every manual link must resolve at the pinned source. This validates references, not scientific claims.
for bridge in seed["manual_bridges"]:
    bridge["source_records"]=[{**blobs[p],"role":role} for role in ("tachyon","uap") for p in bridge[role]]
    assert all(p in blobs for p in bridge["tachyon"]+bridge["uap"])
coverage={"source_commit":source,"source_tree":git("rev-parse",source+"^{tree}").decode().strip(),"json_blobs":len(blobs),"parsed":parsed,"utf16_recovered":recovered,"failed_parse_count":len(failures),"failed_parse":failures,"all_blob_bytes_read":True,"structured_scan_complete":len(failures)==0,"filename_candidates":sum(bool(explicit.search(p)) for p in blobs),"candidate_documents":len(docs),"direct_topic_documents":len(direct),"tier_counts":dict(collections.Counter(d["tier"] for d in docs.values())),"direct_group_counts":dict(collections.Counter(docs[p]["group"] for p in direct)),"limits":["Path and keyword matches are discovery, not relevance or proof. Direct-topic tag is heuristic, not manual scientific admission.","All structured keys and string leaves scanned; first 80 Tachyon and 20 UAP hit rows and 120 external link rows per document retained; total counts and omission counts explicit.","Malformed JSON screened for raw terms, not silently repaired.","External source links not retrieved in this run.","No arbitrary graph-neighbor expansion into the core; explicit refs retained separately."]}
dup=collections.defaultdict(list)
for path,d in docs.items():dup[d["git_blob_sha"]].append(path)
master={**base,"status":"FULL_PINNED_BLOB_SCAN__DISCOVERY_ONLY__SCIENTIFIC_HOLD","coverage":coverage,"inventory":[docs[p] for p in sorted(docs)],"direct_topic_paths":sorted(direct),"explicit_reference_graph":edges,"duplicate_blobs":[{"git_blob_sha":k,"paths":v} for k,v in sorted(dup.items()) if len(v)>1],"cross_corpus":str(C)}
comparison={"uap_narrow_count":len(u_narrow),"uap_wide_count":len(u_wide),"tachyon_direct_count":len(direct),"tachyon_discovery_count":len(docs),"exact_shared_narrow_direct":len(direct_uap),"exact_shared_narrow_all":len(shared_all),"exact_shared_wide_all":len(wide_shared),"direct_to_narrow_reference_edges":len(cross_edges),"co_mention_documents":len(co_mentions),"manual_bridge_count":len(seed["manual_bridges"]),"empirical_physical_link_count":0}
seed.update({"status":"FULL_PINNED_SCAN__SOURCE_BOUND_CROSSWALK__NO_PHYSICAL_LINK_ESTABLISHED","coverage":coverage,"comparison":comparison,"exact_shared_narrow_direct_paths":sorted(direct_uap),"exact_shared_narrow_all_paths":sorted(shared_all),"exact_shared_wide_all_paths":sorted(wide_shared),"explicit_cross_edges":cross_edges,"co_mentions":co_mentions,"counting_contract":"Exact path overlap, reference and co-mention are distinct metrics; not independent experiments and not evidence of a shared physical carrier. Zero empirical physical links means none established by reviewed material, not universal proof of absence."})
write(M,master);write(C,seed)
print(json.dumps({"coverage":{k:v for k,v in coverage.items() if k not in ("failed_parse","limits")},"comparison":comparison,"explicit_edges":len(edges)},sort_keys=True))
