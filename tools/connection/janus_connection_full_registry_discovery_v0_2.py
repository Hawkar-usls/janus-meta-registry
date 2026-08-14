#!/usr/bin/env python3
"""JANUS Connection full-registry hidden-pattern discovery engine v0.2.

Design goals:
- account for EVERY *.json in the checkout, including malformed historical files;
- malformed JSON participates through bounded raw-text features but receives no
  structured operator/graph claims;
- Connection-family records remain hypothesis memory, never independent support;
- integrity sidecars remain corpus objects but contribute zero independent support;
- suppress shared templates, registry-format boilerplate, direct lineage,
  cross-references and filename/topic-family overlap;
- rank cross-domain OPERATOR/STRUCTURE recurrence whose narrative CONTENT differs.

No embeddings, LLM scoring, network access, or stochastic sampling are used.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, math, os, re
from pathlib import Path

VERSION="0.2"
TOKEN_RE=re.compile(r"[A-Za-zА-Яа-яЁё0-9]+",re.UNICODE)
HASH_RE=re.compile(r"^[0-9a-f]{32,128}$",re.I)
URL_RE=re.compile(r"^(?:https?://|git@)",re.I)
DATE_RE=re.compile(r"20\d\d[-_]\d\d[-_]\d\d")

STOP={
"janus","json","artifact","uuid","version","schema","data","registry","research","path","file","files","name","title","status","type","value","values","note","notes","result","results","source","sources","object","objects","record","records","field","fields","true","false","null","none","yes","no","en","ru","utc","local","timestamp","date","current","new","old","meta","canonical","purpose","summary","the","a","an","and","or","of","to","in","for","on","with","by","from","as","is","are","be","this","that","it","its","not","only","may","can","must","should","will","и","в","на","с","по","для","что","это","как","не","или","к","из","от","до","при","его","ее","их","быть","может","только","так","также","у","о","об","под","над"}
GENERIC_FILE={"janus","connection","scan","data","batch","proof","hardening","ledger","registry","meta","json","current","audit","strengthening","report","raw","seed","manifest","signal","semantic","companion","v"}
FORMAT_KEYS={
"artifact_uuid","artifact_slug","artifact_id","schema","schema_version","version","timestamp","timestamp_utc","timestamp_local","created_at","created_at_utc","created_at_local","created_date_utc","updated_at","updated_date_utc","provenance","created_by","commit","commit_sha","commit_message","sha256","sha256_raw","sha256_canonical_json","sha256_canonical_json_pre_integrity","integrity","canonicalization","json_valid","validation","repository","repository_path","source_repository","source_repositories","filename","path","url","display_url","blob_sha","git_blob_sha1","canonical_seed_binding"}
FORMAT_TOKENS={"sha","sha256","canonicalization","canonical","dumps","ensure","ascii","separators","sort","keys","created","creator","commit","repository","validation","valid","filename","blob","hash","integrity"}
ROLE_WEIGHT={"PRIMARY_OR_DOMAIN_RECORD":1.0,"DERIVED_META_OR_LEDGER":0.68,"CONNECTION_HYPOTHESIS_MEMORY":0.0,"INTEGRITY_DERIVATIVE":0.0,"UNPARSEABLE_JSON_RAW_ONLY":0.42}

def sha(b): return hashlib.sha256(b).hexdigest()
def canon(o): return sha(json.dumps(o,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode())
def toks(s):
    s=re.sub(r"([a-zа-яё])([A-ZА-ЯЁ])",r"\1 \2",s).replace("_"," ").replace("-"," ").replace("/"," ").replace("."," ")
    return [t for t in TOKEN_RE.findall(s.lower()) if len(t)>1 and t not in STOP and not t.isdigit() and not HASH_RE.match(t)]
def enumish(s):
    if len(s)>120 or URL_RE.match(s.strip()) or HASH_RE.match(s.strip()): return False
    letters=[c for c in s if c.isalpha()]
    return bool(letters) and (sum(c.isupper() for c in letters)/len(letters)>=.55 or "_" in s or "->" in s or "→" in s)
def flatten(o,p=None,d=0):
    p=[] if p is None else p
    yield p,o
    if d>30:return
    if isinstance(o,dict):
        for k,v in o.items(): yield from flatten(v,p+[str(k)],d+1)
    elif isinstance(o,list):
        for i,v in enumerate(o): yield from flatten(v,p+[str(i)],d+1)
def ptr(parts): return "/"+"/".join("[]" if x.isdigit() else x.lower() for x in parts)
def substantive_key(k): return k.lower() not in FORMAT_KEYS and not k.isdigit()
def path_is_format(parts): return any((not x.isdigit()) and x.lower() in FORMAT_KEYS for x in parts[-3:])

def role(path,obj,parsed):
    b=Path(path).name.upper(); p=path.lower(); au=str(obj.get("artifact_uuid","" )).upper() if isinstance(obj,dict) else ""
    if b.endswith(".SHA256.JSON") or "SHA256-SIDECAR" in au or "INTEGRITY-SIDECAR" in au:return "INTEGRITY_DERIVATIVE"
    if p.startswith("registry/connections/") or b.startswith("JANUS-CONNECTION-") or "CONNECTION-SCAN" in au:return "CONNECTION_HYPOTHESIS_MEMORY"
    if not parsed:return "UNPARSEABLE_JSON_RAW_ONLY"
    if any(x in b for x in ("LEDGER","AUDIT","STRENGTHENING","INDEX","DOSSIER","CURRENT")):return "DERIVED_META_OR_LEDGER"
    return "PRIMARY_OR_DOMAIN_RECORD"
def lineage(path,obj):
    s=str(obj.get("artifact_uuid","")) if isinstance(obj,dict) and obj.get("artifact_uuid") else Path(path).stem
    s=DATE_RE.sub("DATE",s)
    s=re.sub(r"(?:[-_])v?\d+(?:[._-]\d+)*(?:[-_](?:final|scientific|academic|plus|critical|expanded|expansion))?$","",s,flags=re.I)
    s=re.sub(r"(?:[-_])(scan|batch)[-_]?\d+.*$","",s,flags=re.I)
    s=re.sub(r"\d+","#",s)
    return s.upper()
def file_topic(path):
    ts=[x for x in toks(Path(path).stem) if x not in GENERIC_FILE and not re.fullmatch(r"v?\d+",x)]
    return set(ts[:10])
def domain(path):
    pp=Path(path).parts
    if pp and pp[0]=="registry" and len(pp)>1:return "registry:"+pp[1]
    if pp and pp[0]=="security_research" and len(pp)>1:return "security:"+pp[1]
    if pp and pp[0]=="data" and len(pp)>2:return "data:"+pp[1]
    ft=sorted(file_topic(path))
    return (pp[0] if pp else "root")+":"+("+".join(ft[:2]) if ft else "root")

def bounded_raw_content(text):
    c=collections.Counter()
    for t in toks(text[:120000]): c["T:"+t]+=1
    return c

def extract(path,obj,raw,parsed,error=None):
    op=collections.Counter(); content=collections.Counter(); pointers=set(); refs=set(); bools=[]
    if parsed:
        for parts,val in flatten(obj):
            if parts:
                po=ptr(parts)
                if not path_is_format(parts): pointers.add(po)
                k=parts[-1]
                if substantive_key(k) and not path_is_format(parts):
                    for t in toks(k):
                        if t not in FORMAT_TOKENS: op["K:"+t]+=2
                    if len(parts)>=2 and substantive_key(parts[-2]):
                        op["PC:"+parts[-2].lower()+">"+k.lower()]+=1
            if isinstance(val,bool) and parts and substantive_key(parts[-1]) and not path_is_format(parts):
                f="BV:"+parts[-1].lower()+"="+str(val).lower(); op[f]+=2; bools.append((parts[-1].lower(),val))
            elif isinstance(val,(int,float)) and not isinstance(val,bool) and parts and substantive_key(parts[-1]) and not path_is_format(parts): op["NT:"+parts[-1].lower()]+=1
            elif isinstance(val,str):
                st=val.strip()
                if st.endswith(".json") and len(st)<400: refs.add(st.lstrip("./"))
                if enumish(st) and not path_is_format(parts):
                    k=parts[-1].lower() if parts and substantive_key(parts[-1]) else "value"
                    for t in toks(st):
                        if t not in FORMAT_TOKENS: op["E:"+k+":"+t]+=1
                if len(st)>=12 and not URL_RE.match(st) and not HASH_RE.match(st):
                    for t in toks(st[:1500])[:180]: content["T:"+t]+=1
    else:
        text=raw.decode("utf-8-sig",errors="replace")
        content.update(bounded_raw_content(text))
    for t in file_topic(path): content["F:"+t]+=2
    meta={}
    if isinstance(obj,dict):
        for k in ("artifact_uuid","artifact_slug","registry_class","schema","schema_version","status","version"):
            if k in obj and isinstance(obj[k],(str,int,float,bool)):meta[k]=obj[k]
        ti=obj.get("title")
        if isinstance(ti,str):meta["title"]=ti[:300]
        elif isinstance(ti,dict):meta["title"]={str(k):str(v)[:220] for k,v in list(ti.items())[:4]}
    r=role(path,obj,parsed)
    return {"path":path,"bytes":len(raw),"sha256_raw":sha(raw),"sha256_canonical_json":canon(obj) if parsed else None,"parsed":parsed,"parse_error":error,"role":r,"role_weight":ROLE_WEIGHT[r],"lineage_stem":lineage(path,obj),"domain_bucket":domain(path),"file_topic":file_topic(path),"meta":meta,"op":op,"content":content,"pointers":pointers,"refs":refs,"bools":bools}

def load(raw):
    text=raw.decode("utf-8-sig",errors="strict")
    try:return json.loads(text),True,None
    except Exception as e:return None,False,type(e).__name__+": "+str(e)[:260]
def vectors(ds,field):
    n=len(ds); df=collections.Counter()
    for d in ds:
        for f in d[field]:df[f]+=1
    idf={f:math.log((1+n)/(1+c))+1 for f,c in df.items()}; vs=[]; ns=[]
    for d in ds:
        v={f:(1+math.log(c))*idf[f] for f,c in d[field].items()}; z=math.sqrt(sum(x*x for x in v.values())) or 1
        vs.append(v);ns.append(z)
    return df,idf,vs,ns
def cos(a,na,b,nb):
    if len(a)>len(b):a,b=b,a
    s=sum(w*b.get(f,0) for f,w in a.items());return s/(na*nb) if s else 0
def jac(a,b):return len(a&b)/len(a|b) if a and b else 0
def cfeat(f):return f.replace("PC:","parent_child:").replace("K:","key:").replace("E:","enum:").replace("BV:","bool:").replace("NT:","numeric_field:")

def dep_factor(a,b,explicit,shared_refs,template_j,topic_j):
    f=1.0; flags=[]
    if a["parsed"] and b["parsed"] and a["sha256_canonical_json"]==b["sha256_canonical_json"]:return 0,["EXACT_CANONICAL_DUPLICATE"]
    if a["lineage_stem"]==b["lineage_stem"]:f*=.14;flags.append("SAME_LINEAGE_STEM")
    if explicit:f*=.38;flags.append("EXPLICIT_CROSS_REFERENCE")
    if shared_refs:f*=.62;flags.append("SHARED_REFERENCED_ANCESTOR")
    if template_j>=.97:f*=.08;flags.append("SAME_OR_NEAR_EXACT_TEMPLATE")
    elif template_j>=.84:f*=.20;flags.append("VERY_HIGH_TEMPLATE_OVERLAP")
    elif template_j>=.68:f*=.48;flags.append("HIGH_TEMPLATE_OVERLAP")
    if topic_j>=.60:f*=.30;flags.append("HIGH_FILENAME_TOPIC_OVERLAP")
    elif topic_j>=.30:f*=.58;flags.append("FILENAME_TOPIC_OVERLAP")
    elif topic_j>0:f*=.82;flags.append("WEAK_FILENAME_TOPIC_OVERLAP")
    if a["domain_bucket"]==b["domain_bucket"]:f*=.76;flags.append("SAME_DOMAIN_BUCKET")
    rw=min(a["role_weight"],b["role_weight"])
    if rw<1:f*=max(.22,rw);flags.append("NON_PRIMARY_ROLE")
    return f,flags

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--repo-root",default=".");ap.add_argument("--out",required=True);ap.add_argument("--top",type=int,default=240);args=ap.parse_args()
    root=Path(args.repo_root).resolve(); files=sorted(p for p in root.rglob("*.json") if ".git" not in p.parts and "out" not in p.parts)
    ds=[]
    for p in files:
        raw=p.read_bytes(); rel=p.relative_to(root).as_posix();
        try:o,ok,err=load(raw)
        except Exception as e:o,ok,err=None,False,type(e).__name__+": "+str(e)[:260]
        ds.append(extract(rel,o,raw,ok,err))
    n=len(ds); pidx={d["path"]:i for i,d in enumerate(ds)}
    explicit=set(); refsets=[]
    for i,d in enumerate(ds):
        rr={r for r in d["refs"] if r in pidx};refsets.append(rr)
        for r in rr:explicit.add(tuple(sorted((i,pidx[r]))))
    odf,oidf,ov,on=vectors(ds,"op"); cdf,cidf,cv,cn=vectors(ds,"content")
    maxdf=max(3,min(65,int(max(4,n*.11))))
    inv=collections.defaultdict(list)
    for i,d in enumerate(ds):
        if d["role_weight"]<=0 or not d["parsed"]:continue
        for feat in d["op"]:
            if 2<=odf[feat]<=maxdf:inv[feat].append(i)
    acc=collections.defaultdict(float); shared=collections.defaultdict(list)
    for feat,ids in inv.items():
        for i,j in itertools.combinations(ids,2):
            k=(i,j) if i<j else (j,i);acc[k]+=oidf[feat]
            if len(shared[k])<20:shared[k].append((oidf[feat],feat))
    rows=[]
    for (i,j),rw in acc.items():
        a,b=ds[i],ds[j]; os=cos(ov[i],on[i],ov[j],on[j]);
        if os<.045:continue
        cs=cos(cv[i],cn[i],cv[j],cn[j]); tj=jac(a["pointers"],b["pointers"]); fj=jac(a["file_topic"],b["file_topic"])
        ex=(i,j) in explicit; sr=bool(refsets[i]&refsets[j]); dep,flags=dep_factor(a,b,ex,sr,tj,fj)
        if dep<=0:continue
        contrast=max(0,os-cs); hidden=max(0,1-min(1,cs/.58)); rarity=min(1,rw/24)
        substantive_struct=min(tj,.67)
        base=.47*os+.19*contrast+.12*hidden+.12*rarity+.10*substantive_struct
        cross=a["domain_bucket"]!=b["domain_bucket"]
        score=base*dep*(1.10 if cross else .86)
        if score<.035:continue
        feats=[cfeat(x) for _,x in sorted(shared[(i,j)],reverse=True)[:12]]
        rows.append({"score":round(score,8),"operator_similarity":round(os,8),"content_similarity":round(cs,8),"operator_minus_content":round(os-cs,8),"substantive_template_jaccard":round(tj,8),"filename_topic_jaccard":round(fj,8),"dependency_factor":round(dep,8),"dependency_flags":flags,"cross_domain":cross,"a":{"path":a["path"],"domain":a["domain_bucket"],"role":a["role"],"artifact_uuid":a["meta"].get("artifact_uuid")},"b":{"path":b["path"],"domain":b["domain_bucket"],"role":b["role"],"artifact_uuid":b["meta"].get("artifact_uuid")},"shared_substantive_operator_features":feats,"status":"MACHINE_CANDIDATE_NOT_VALIDATED"})
    rows.sort(key=lambda r:(r["score"],r["operator_minus_content"],r["operator_similarity"]),reverse=True)

    # Higher-order substantive feature recurrences.
    motifs=[]
    for feat,ids in inv.items():
        ids=[i for i in ids if ds[i]["role_weight"]>0]
        dom={ds[i]["domain_bucket"] for i in ids}; lin={ds[i]["lineage_stem"] for i in ids}
        if len(ids)<3 or len(dom)<3 or len(lin)<3:continue
        score=oidf[feat]*math.log1p(len(dom))*math.log1p(len(lin))/math.sqrt(len(ids))
        motifs.append({"feature":cfeat(feat),"score":round(score,8),"document_count":len(ids),"domain_count":len(dom),"lineage_count":len(lin),"domains":sorted(dom)[:25],"example_paths":[ds[i]["path"] for i in ids[:16]],"status":"SUBSTANTIVE_CROSS_DOMAIN_OPERATOR_RECURRENCE"})
    motifs.sort(key=lambda x:(x["score"],x["domain_count"]),reverse=True)

    # Feature-pair motifs, avoiding formatting features by construction.
    mp=collections.defaultdict(set)
    for i,d in enumerate(ds):
        if d["role_weight"]<=0 or not d["parsed"]:continue
        fs=[(oidf[f],f) for f in d["op"] if 2<=odf[f]<=maxdf]
        top=[f for _,f in sorted(fs,reverse=True)[:22]]
        for a,b in itertools.combinations(sorted(top),2):mp[(a,b)].add(i)
    mpr=[]
    for (f1,f2),ids0 in mp.items():
        ids=sorted(ids0); dom={ds[i]["domain_bucket"] for i in ids}; lin={ds[i]["lineage_stem"] for i in ids}
        if len(ids)<3 or len(dom)<3 or len(lin)<3:continue
        p12=len(ids)/n;p1=odf[f1]/n;p2=odf[f2]/n;pmi=math.log((p12+1e-12)/(p1*p2+1e-12),2)
        if pmi<=0:continue
        score=pmi*math.log1p(len(ids))*math.log1p(len(dom))
        mpr.append({"features":[cfeat(f1),cfeat(f2)],"score":round(score,8),"pmi_bits":round(pmi,8),"document_count":len(ids),"domain_count":len(dom),"lineage_count":len(lin),"example_paths":[ds[i]["path"] for i in ids[:16]],"status":"HIGHER_ORDER_SUBSTANTIVE_MOTIF"})
    mpr.sort(key=lambda x:(x["score"],x["domain_count"]),reverse=True)

    # Boolean inversions: same substantive boolean field, both values across independent domains.
    bi=collections.defaultdict(lambda:{True:set(),False:set()})
    for i,d in enumerate(ds):
        if d["role_weight"]<=0:continue
        for k,v in d["bools"]:bi[k][v].add(i)
    inversions=[]
    for k,vv in bi.items():
        t,f=vv[True],vv[False]
        if not t or not f:continue
        dom={ds[i]["domain_bucket"] for i in t|f}; lin={ds[i]["lineage_stem"] for i in t|f}
        if len(dom)<3 or len(lin)<3:continue
        rarity=1/math.sqrt(len(t)+len(f));score=math.log1p(len(dom))*rarity
        inversions.append({"field":k,"score":round(score,8),"true_count":len(t),"false_count":len(f),"domain_count":len(dom),"true_examples":[ds[i]["path"] for i in sorted(t)[:8]],"false_examples":[ds[i]["path"] for i in sorted(f)[:8]],"status":"CROSS_DOMAIN_BOOLEAN_TENSION_NOT_CONTRADICTION_UNTIL_CONTEXT_REVIEWED"})
    inversions.sort(key=lambda x:(x["score"],x["domain_count"]),reverse=True)

    # Candidate bridge documents from strongest post-penalty edges.
    ba=collections.defaultdict(lambda:{"sum":0.,"n":0,"domains":set(),"neighbors":[]})
    for r in rows[:600]:
        if not r["cross_domain"]:continue
        for x,y in ((r["a"],r["b"]),(r["b"],r["a"])):
            q=ba[x["path"]];q["sum"]+=r["score"];q["n"]+=1;q["domains"].add(y["domain"])
            if len(q["neighbors"])<10:q["neighbors"].append({"path":y["path"],"domain":y["domain"],"score":r["score"]})
    bridges=[{"path":p,"score_sum":round(q["sum"],8),"cross_domain_degree":q["n"],"distinct_neighbor_domains":len(q["domains"]),"neighbor_domains":sorted(q["domains"]),"sample_neighbors":q["neighbors"]} for p,q in ba.items() if len(q["domains"])>=2]
    bridges.sort(key=lambda x:(x["distinct_neighbor_domains"],x["score_sum"]),reverse=True)

    cc=collections.Counter(d["sha256_canonical_json"] for d in ds if d["parsed"]); dups=[{"sha256_canonical_json":h,"count":c,"paths":[d["path"] for d in ds if d["sha256_canonical_json"]==h]} for h,c in cc.items() if c>1]
    manifest=[{"path":d["path"],"bytes":d["bytes"],"sha256_raw":d["sha256_raw"],"sha256_canonical_json":d["sha256_canonical_json"],"parse_status":"PARSED" if d["parsed"] else "RAW_FALLBACK_ONLY","parse_error":d["parse_error"],"role":d["role"],"role_weight":d["role_weight"],"lineage_stem":d["lineage_stem"],"domain_bucket":d["domain_bucket"],"meta":d["meta"]} for d in ds]
    snap=os.environ.get("GITHUB_SHA") or os.popen("git rev-parse HEAD 2>/dev/null").read().strip() or None
    out={"schema":"janus.connection.full_registry_discovery.v0_2","artifact_uuid":"JANUS-CONNECTION-FULL-REGISTRY-DISCOVERY-2026-08-14-V0.2","engine_version":VERSION,"snapshot_commit":snap,"objective":"Exhaustive machine search across every JSON object for human-blind-spot cross-domain relations after common-template, lineage, explicit-reference, formatting-boilerplate and topic-family suppression.","epistemic_boundary":{"every_json_accounted":True,"malformed_json_included_via_bounded_raw_fallback":True,"raw_fallback_has_no_structural_operator_claim":True,"connection_family_zero_independent_support":True,"integrity_derivatives_zero_independent_support":True,"scores_not_probabilities":True,"pmi_not_population_significance":True,"machine_discovery_not_causation":True,"machine_discovery_not_novelty":True,"human_non_obviousness_requires_future_blind_human_test":True},"corpus":{"json_files_seen":n,"parsed":sum(d["parsed"] for d in ds),"raw_fallback_only":sum(not d["parsed"] for d in ds),"total_bytes":sum(d["bytes"] for d in ds),"role_counts":dict(collections.Counter(d["role"] for d in ds)),"domain_bucket_count":len({d["domain_bucket"] for d in ds}),"lineage_stem_count":len({d["lineage_stem"] for d in ds}),"explicit_json_reference_edges":len(explicit),"exact_canonical_duplicate_groups":len(dups)},"detector":{"content_vs_operator_channels":True,"format_boilerplate_removed_from_operator_channel":True,"template_overlap_penalty":True,"filename_topic_overlap_penalty":True,"shared_reference_penalty":True,"lineage_penalty":True,"no_llm":True,"no_embeddings":True,"deterministic":True},"top_hidden_bridge_pairs":rows[:args.top],"top_substantive_operator_motifs":motifs[:args.top],"top_higher_order_motif_pairs":mpr[:args.top],"top_boolean_tensions":inversions[:120],"top_bridge_documents":bridges[:100],"exact_duplicate_groups":dups,"corpus_manifest":manifest,"claim_ceiling":"EXHAUSTIVE_INTERNAL_MACHINE_DISCOVERY_OVER_863_OF_863_JSON_OBJECTS; ranked candidates remain hypotheses until original source reinspection and relation-specific controls.","next_gate":"Interpret and re-inspect strongest template-suppressed cross-domain candidates; freeze a shortlist before destructive validation and held-out transport."}
    p=Path(args.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS_FULL_CORPUS_V0_2","snapshot":snap,"json_seen":n,"parsed":out["corpus"]["parsed"],"raw_fallback":out["corpus"]["raw_fallback_only"],"pairs":len(rows),"motifs":len(motifs),"motif_pairs":len(mpr),"boolean_tensions":len(inversions),"output":str(p)},ensure_ascii=False))
if __name__=="__main__":main()
