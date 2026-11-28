#!/usr/bin/env python3
"""Read-only scan of a pinned Git tree; writes only the two requested indexes."""
import argparse, collections, json, math, pathlib, re, subprocess
from urllib.parse import urlsplit

P=argparse.ArgumentParser()
P.add_argument("--source", required=True)
a=P.parse_args()
SOURCE=a.source
REPO="Hawkar-usls/janus-meta-registry"
MASTER="registry/uap/JANUS-UAP-MASTER-INDEX-2026-11-28-v1.0.json"
GEO="registry/uap/JANUS-UAP-NEVADA-ARIZONA-GEO-INDEX-2026-11-28-v1.0.json"
def git(*args):
    return subprocess.check_output(["git",*args])
SOURCE=git("rev-parse",SOURCE+"^{commit}").decode().strip()
tree=git("rev-parse",SOURCE+"^{tree}").decode().strip()
raw=git("ls-tree","-rz","-l","--full-tree",SOURCE)
blobs={}
tree_count=0
for line in raw.split(b"\0"):
    if not line: continue
    tree_count+=1
    header,path=line.split(b"\t",1)
    mode,kind,sha,size=header.decode().split()
    path=path.decode("utf-8","surrogateescape")
    if kind=="blob" and path.lower().endswith(".json"):
        blobs[path]={"path":path,"git_blob_sha":sha,"size_bytes":int(size)}
G=[("FRESCO",r"^artifacts/janus-fresco-forge/.*(?:uap|palomar|blue.?book|poss.?1)"),
   ("RETRO",r"^registry/uap/|retro.?tahyon|retrocausal|^EYE/r4_7_rt"),
   ("EYE",r"^EYE/.*palomar|^data/EYE-R3-PALOMAR|PALOMAR-XE325"),
   ("JPFM",r"^data/JANUS-PALOMAR-|JANUS-JPFM"),
   ("BLUEBOOK",r"blue.?book"),("POSS_I",r"poss.?1"),
   ("NUCLEAR_UAP",r"nuclear.*uap|uap.*nuclear|nuclear.attraction|nuclear.emulation|conus|atomic.*uap|uap.*atomic"),
   ("UAP",r"uap|ufo|нло|galileo|vasco|nimitz|aawsap|aatip|aaro"),
   ("COUSTEAU_ADJACENT",r"ECHO-COUSTEAU.*(?:ANOMALY|ACOUSTIC|PALOMAR|SONAR)|TOBI-SPERMAN-THE-SONAR"),
   ("KUSTO_ADJACENT",r"^experiments/kusto/"),
   ("INTERPRETIVE_ADJACENT",r"FALLOUT.*ATOMIC|ATOMIC.*FALLOUT|TACHYON-CHILD-PROTECTION-NUCLEAR|NUCLEAR-ALCHEMICAL-SPIRAL")]
G=[(k,re.compile(v,re.I)) for k,v in G]
UAP=re.compile(r"\b(?:UAPs?|UFOs?|AARO|AAWSAP|AATIP|NUFORC|MUFON|VASCO|POSS[-_ ]?(?:I|1)|Palomar|Project Blue Book|Blue Book|Phoenix Lights|Nimitz|Tic[- ]Tac|unidentified (?:anomalous|aerial|flying) (?:phenomena|objects?))\b|(?<!\w)НЛО(?!\w)|неопознанн\w* (?:летающ\w*|аномальн\w*)",re.I)
NV=re.compile(r"\bNevada\b|Невад[а-яё]*|\bArea[\s_-]*51\b|Зон[а-яё]*\s*51\b|\bGroom Lake\b|Грум[- ]Лейк|\bNellis\b|Неллис|\bLas Vegas\b|Лас[- ]Вегас|\bYucca (?:Flat|Mountain)\b|\bTonopah\b|Тонопа|\bPapoose Lake\b|\bJackass Flats\b|\bFrenchman Flat\b|\bReno\b|\bCarson City\b|\bRachel,? NV\b|\b(?:Mercury|Indian Springs),? NV\b",re.I)
AZ=re.compile(r"\bArizona\b|Аризон[а-яё]*|\bPhoenix\b|Финикс|\bTucson\b|Тусон|\bFlagstaff\b|Флагстафф|\bSedona\b|Седон[а-яё]*|\bKingman\b|Кингман|\bPrescott\b|\bYuma\b|\bLuke (?:AFB|Air Force Base)\b|\bDavis[- ]Monthan\b|\bFort Huachuca\b|\bGila Bend\b|\b(?:Mesa|Scottsdale|Tempe),? AZ\b|\bBarry M\.? Goldwater\b",re.I)
PATH_RE=re.compile(r"(?:data|registry|experiments|research|EYE|artifacts)/[A-Za-z0-9_./-]+\.json\b")
ID_RE=re.compile(r"\b(?:JANUS|EYE|PALOMAR|TOPA)[A-Z0-9_.-]*-[A-Z0-9_.-]{5,}",re.I)
CONTEXT=re.compile(r"^(?:id|event_id|case_id|study_id|artifact_id|name|title|date|event_date|year|location|site|state|coordinates|latitude|longitude|lat|lon|lng|status|verification_status|primary_sources|description)$",re.I)
FIELDS=("artifact_id","record_id","title","schema","schema_version","version","date","created_date","status","scientific_status","claim_ceiling","verdict","CURRENT_VERDICT","aggregate_verdict","one_line_verdict","canonical_summary_ru","negative_findings","epistemic_limits","interpretation_boundaries")
def compact(v,limit=4000):
    return v if len(json.dumps(v,ensure_ascii=True))<=limit else None
def pointer(k):
    return str(k).replace("~","~0").replace("/","~1")
def walk(v,p="",parents=()):
    if isinstance(v,dict):
        yield ("object",p,v,parents)
        for k,w in v.items():
            q=p+"/"+pointer(k)
            yield ("key",q,k,parents+(v,))
            yield from walk(w,q,parents+(v,))
    elif isinstance(v,list):
        for i,w in enumerate(v): yield from walk(w,p+"/"+str(i),parents+(v,))
    elif isinstance(v,str):
        yield ("value",p,v,parents)
def context(parents):
    out={}
    for v in parents[-3:]:
        if isinstance(v,dict):
            for k,w in v.items():
                if CONTEXT.match(k) and compact(w,1500) is not None: out[k]=w
    return out
def geo_terms(s):
    return sorted(set(["NV:"+m.group() for m in NV.finditer(s)]+["AZ:"+m.group() for m in AZ.finditer(s)]))
def excerpt(s,terms):
    if len(s)<=1500:return s,False
    spans=[]
    for term in terms:
        i=s.lower().find(term[3:].lower())
        if i>=0: spans.append(s[max(0,i-160):i+len(term[3:])+160])
    return " … ".join(spans),True
def classify(p,kind,parents):
    field=p.rsplit("/",1)[-1]
    if kind=="key": return "KEY_MENTION_REQUIRES_REVIEW"
    if re.search(r"source|author|affiliation|url|reference|bibliog",p,re.I):return "SOURCE_OR_REFERENCE_CONTEXT"
    if re.search(r"hypothes|analogy|fiction|interpret|specul",p,re.I):return "HYPOTHESIS_OR_INTERPRETATION"
    if re.search(r"location|site|state|coordinates|region|place|city",field,re.I):
        if any(isinstance(x,dict) and any(k in x for k in ("event_id","case_id","incident_id")) for x in parents[-2:]):
            return "ARCHIVAL_EVENT_LOCATION_CANDIDATE"
        return "LOCATION_FIELD_CANDIDATE"
    return "TEXT_MENTION_REQUIRES_CONTEXT_REVIEW"
def coordinates(v):
    lower={str(k).lower():w for k,w in v.items()}
    lat=lower.get("latitude",lower.get("lat"))
    lon=lower.get("longitude",lower.get("lon",lower.get("lng")))
    if isinstance(lat,bool) or isinstance(lon,bool): return None
    if not isinstance(lat,(int,float)) or not isinstance(lon,(int,float)):return None
    if not (math.isfinite(lat) and math.isfinite(lon)):return None
    states=[]
    if 35<=lat<=42.01 and -120.01<=lon<=-114:states.append("NV")
    if 31.3<=lat<=37.01 and -114.83<=lon<=-109.03:states.append("AZ")
    return (lat,lon,states) if states else None
def clean_url(s):
    if not s.startswith(("https://","http://")) or len(s)>1500:return False
    try:
        u=urlsplit(s)
        return bool(u.netloc) and not u.username and not re.search(r"(?:token|secret|signature|password|credential|api[_-]?key)=",u.query,re.I)
    except ValueError:return False
def strict_constant(v): raise ValueError("non-standard JSON constant: "+v)
def unique_dict(items,keys):
    return sorted({tuple(str(x.get(k,"")) for k in keys):x for x in items}.values(),key=lambda x:tuple(str(x.get(k,"")) for k in keys))
def path_group(p):
    return next((k for k,r in G if r.search(p)),None)

docs={}; ids=collections.defaultdict(list); failures=[]; parse_ok=0
proc=subprocess.Popen(["git","cat-file","--batch"],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
try:
    for path,b in sorted(blobs.items()):
        proc.stdin.write((b["git_blob_sha"]+"\n").encode());proc.stdin.flush()
        hdr=proc.stdout.readline().split()
        if len(hdr)!=3 or hdr[1]!=b"blob":raise RuntimeError("cat-file missing "+path)
        size=int(hdr[2]);data=proc.stdout.read(size)
        if len(data)!=size or proc.stdout.read(1)!=b"\n":raise RuntimeError("cat-file short read "+path)
        if hdr[0].decode()!=b["git_blob_sha"]:raise RuntimeError("blob SHA mismatch")
        g=path_group(path)
        try:
            obj=json.loads(data.decode("utf-8-sig"),parse_constant=strict_constant)
        except (UnicodeError,ValueError,RecursionError) as exc:
            failures.append({"path":path,"git_blob_sha":b["git_blob_sha"],"error":str(exc)[:300]})
            if g:docs[path]={**b,"group":g,"verification":"BLOB_READ_PARSE_FAILED","references":[],"id_refs":[],"geo":[],"urls":[]}
            continue
        parse_ok+=1
        meta={}
        if isinstance(obj,dict):
            for k in FIELDS:
                if k in obj:
                    value=compact(obj[k])
                    if value is not None:meta[k]=value
                    else:meta[k]={"source_json_pointer":"/"+pointer(k),"value_omitted_from_index":True}
            for k in ("artifact_id","record_id"):
                if isinstance(obj.get(k),str):ids[obj[k]].append(path)
        terms=set(); geos=[]; refs=[]; idrefs=[]; urls=[]
        for kind,p,v,parents in walk(obj):
            if kind=="object":
                xy=coordinates(v)
                if xy:
                    geos.append({"source_path":path,"git_blob_sha":b["git_blob_sha"],"json_pointer":p,"match_kind":"COORDINATE_BBOX","matched_terms":xy[2],"classification":"APPROXIMATE_BOUNDING_BOX_CANDIDATE_NOT_STATE_BOUNDARY","source_value":{"latitude":xy[0],"longitude":xy[1]},"parent_context":context(parents+(v,)),"event_location_verified":False})
                continue
            for m in UAP.finditer(v):terms.add(m.group().lower())
            for m in PATH_RE.finditer(v):
                if m.group() in blobs and m.group()!=path:refs.append({"from":path,"to":m.group(),"pointer":p,"match_kind":kind,"relation":"EXPLICIT_PATH_REFERENCE"})
            if kind=="value":
                for m in ID_RE.finditer(v):idrefs.append((m.group().rstrip("."),p))
                if clean_url(v):urls.append({"from":path,"pointer":p,"url":v})
            mt=geo_terms(v)
            if kind=="value" and p.rsplit("/",1)[-1].lower() in ("state","state_code","region","us_state") and v.strip().upper() in ("NV","AZ"):
                mt.append(v.strip().upper()+":"+v)
            if mt:
                val,short=excerpt(v,mt)
                geos.append({"source_path":path,"git_blob_sha":b["git_blob_sha"],"json_pointer":p,"match_kind":kind,"matched_terms":sorted(set(mt)),"classification":classify(p,kind,parents),"source_value":val,"value_is_excerpt":short,"parent_context":context(parents),"event_location_verified":False})
        docs[path]={**b,**meta,"group":g or ("CONTENT_UAP_CANDIDATE" if terms else None),"verification":"CONTENT_PARSED_BLOB_MATCH","uap_terms":sorted(terms),"references":refs,"id_refs":idrefs,"geo":geos,"urls":urls}
finally:
    proc.stdin.close()
    if proc.wait()!=0:raise RuntimeError("cat-file failed")
assert parse_ok+len(failures)==len(blobs)
seed={p for p,d in docs.items() if d.get("group")}
edges=[]
for path,d in docs.items():
    edges.extend(d["references"])
    for identifier,p in d["id_refs"]:
        dest=ids.get(identifier,[])
        if len(dest)==1 and dest[0]!=path:edges.append({"from":path,"to":dest[0],"pointer":p,"relation":"UNIQUE_ARTIFACT_ID_REFERENCE","artifact_id":identifier})
edges=unique_dict(edges,("from","to","pointer","relation","match_kind"))
# One hop, not unrestricted transitive expansion. Keep all explicit edges among admitted inventory.
related=set(seed)
for edge in edges:
    if edge["from"] in seed or edge["to"] in seed:related.update((edge["from"],edge["to"]))
inventory=[]
for path in sorted(related):
    d=docs.get(path,{**blobs[path],"verification":"BLOB_READ_PARSE_FAILED"})
    e={k:v for k,v in d.items() if k not in ("references","id_refs","geo","urls")}
    e["group"]=e.get("group") or "EXPLICIT_REFERENCE_ADJACENT"
    inventory.append(e)
graph=[e for e in edges if e["from"] in related and e["to"] in related]
sources=unique_dict([s for p in related for s in docs.get(p,{}).get("urls",[])],("from","pointer","url"))
geo=[]
for p,d in docs.items():
    for m in d["geo"]:
        m["uap_linkage"]="DISCOVERY_INVENTORY" if p in related else "UNLINKED_GEO_CANDIDATE"
        geo.append(m)
geo=unique_dict(geo,("source_path","json_pointer","match_kind"))
duplicate_blobs=collections.defaultdict(list)
for e in inventory:duplicate_blobs[e["git_blob_sha"]].append(e["path"])
coverage={"repository":REPO,"source_commit":SOURCE,"source_tree":tree,"tree_complete":True,"tree_blob_entries":tree_count,"json_blobs":len(blobs),"parsed_blob_verified":parse_ok,"failed_json_parse_count":len(failures),"failed_json_parse":failures,"unscanned_repository_json_count":0,"scope":"ALL_PINNED_TREE_JSON_BLOB_BYTES_SCANNED__PARSE_FAILURES_EXPLICIT","limits":["Not a scientific evidence admission.","External links are recorded, not fetched or authenticated.","Content term and one-hop reference membership may include unrelated or interpretive documents.","JSON parse failures are not searchable as structured JSON.","No geographic claim from lexical aliases or bounding-box membership.","Bounding boxes are screening approximations, not state polygons; locations in arbitrary coordinate arrays or prose are not geocoded.","No independent verification of archive claims."]}
boundaries=[
("data/JANUS-UAP-DOMAIN-INDEX-2026-08-15-v1.1.json","Dense public POSS-I binary candidate presence equals observing schedule; conditional positive residual not robust; no common external trigger admitted."),
("data/JANUS-UAP-DOMAIN-INDEX-2026-08-14-v1.0.json","No positive nuclear STARLIKE specificity in reconstructed Blue Book archive; nonnuclear baseline remains."),
("registry/cosmology/JANUS-UAP-NUCLEAR-FULL-PUBLIC-DOSSIER-2026-09-27-v1.0.json","Archival reports exist; nuclear causation, nonhuman origin and quantum branching not established."),
("registry/cosmology/JANUS-UAP-DECLASSIFIED-RETROCAUSALITY-TACHYON-UKRAINE-DOSSIER-2026-08-27-v1.0.json","Government-sponsored research discussed retrocausality and tachyon-like mechanisms; physical mechanism not established."),
("data/JANUS-PALOMAR-JPFM-5B-WEATHER-ADJUSTED-POSS-RUN-001.json","Wet-day observing schedule association only; no residual rate association."),
("data/PALOMAR-XE325-OBSERVER-EVIDENCE-2026-09-01-v1.0.json","Marks exist beyond one digitized representation; origin unresolved."),
("registry/uap/JANUS-PRINCIPLE-DEUTSCH-v2-NEW-FUTURE-AB-RESULT-2026-11-06-v1.0.json","New blinded future test at chance; no retrocausal signal.")]
master={"schema":"janus.uap.master_index.v1.0","artifact_id":"JANUS-UAP-MASTER-INDEX-2026-11-28-v1.0","date":"2026-11-28","status":"R1_FULL_BLOB_SCAN__DISCOVERY_NAVIGATION_ONLY__SEMANTIC_REVIEW_REQUIRED","authority_changed":False,"coverage":coverage,"geo_index":GEO,"group_counts":dict(collections.Counter(x["group"] for x in inventory)),"inventory_count":len(inventory),"inventory":inventory,"explicit_reference_graph":graph,"external_source_links":sources,"duplicate_blob_paths":[{"git_blob_sha":k,"paths":v} for k,v in sorted(duplicate_blobs.items()) if len(v)>1],"scientific_boundaries":[{"source":p,"result":r} for p,r in boundaries if p in blobs],"next_gate":"Review semantic relevance, geographic event roles, source quality and unresolved records; no current-authority change."}
linked=[m for m in geo if m["uap_linkage"]=="DISCOVERY_INVENTORY"]
unlinked=[m for m in geo if m["uap_linkage"]=="UNLINKED_GEO_CANDIDATE"]
def tally(m):
    return {"matched_files":len(set(x["source_path"] for x in m)),"matched_entries":len(m),"nevada_candidates":sum(any(t=="NV" or t.startswith("NV:") for t in x["matched_terms"]) for x in m),"arizona_candidates":sum(any(t=="AZ" or t.startswith("AZ:") for t in x["matched_terms"]) for x in m),"verified_event_locations":0}
geofile={"schema":"janus.uap.nevada_arizona_geo_index.v1.0","artifact_id":"JANUS-UAP-NEVADA-ARIZONA-GEO-INDEX-2026-11-28-v1.0","date":"2026-11-28","status":"ALL_JSON_BLOBS_SCANNED__GEOGRAPHIC_CANDIDATES_NOT_VERIFIED","master_index":MASTER,"authority_changed":False,"coverage":coverage,"filter":{"states":["Nevada","Arizona"],"nevada_regex":NV.pattern,"arizona_regex":AZ.pattern,"coordinate_bbox":"approximate explicit numeric latitude/longitude keys only","match_roles":"source, event/location fields, interpretation, key, free text, coordinate candidate","warning":"Aliases, state codes, bounding boxes and UAP linkage are not independent verification."},"counts":tally(linked),"unlinked_counts":tally(unlinked),"matches":linked,"unlinked_geo_candidates":unlinked,"review_required":True}
assert all(e["from"] in related and e["to"] in related for e in graph)
assert all(m["source_path"] in blobs and m["git_blob_sha"]==blobs[m["source_path"]]["git_blob_sha"] for m in geo)
assert len(inventory)==len(set(e["path"] for e in inventory))
for path,obj in [(MASTER,master),(GEO,geofile)]:
    data=json.dumps(obj,ensure_ascii=True,indent=2,allow_nan=False)+"\n"
    json.loads(data)
    pathlib.Path(path).write_text(data,encoding="utf-8")
print(json.dumps({"source":SOURCE,"json_blobs":len(blobs),"parsed":parse_ok,"parse_failures":len(failures),"inventory":len(inventory),"edges":len(graph),"source_links":len(sources),"geo":tally(linked),"unlinked":tally(unlinked)},sort_keys=True))
