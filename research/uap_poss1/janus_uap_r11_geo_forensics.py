#!/usr/bin/env python3
import json, pathlib, subprocess, re, collections
ROOT=pathlib.Path("registry/uap")
GEO=ROOT/"JANUS-UAP-NEVADA-ARIZONA-GEO-INDEX-2026-11-28-v1.0.json"
MASTER=ROOT/"JANUS-UAP-MASTER-INDEX-2026-11-28-v1.0.json"
FORENSICS=ROOT/"JANUS-UAP-R1.1-GEO-FORENSICS-2026-11-28-v1.0.json"
REPAIR=ROOT/"JANUS-UAP-R1.1-PARSE-RECOVERY-2026-11-28-v1.0.json"
CORE=ROOT/"JANUS-UAP-R1.1-CURATED-CORE-2026-11-28-v1.0.json"
def read(p):return json.loads(p.read_text(encoding="utf-8"))
def write(p,x):
    p.write_text(json.dumps(x,ensure_ascii=True,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    assert read(p)==x
g,m,f=map(read,(GEO,MASTER,FORENSICS))
assert len(g["matches"])==len(f["match_adjudications"])==156
for i,(a,b) in enumerate(zip(g["matches"],f["match_adjudications"])):
    assert b["r1_match_index"]==i and all(a[k]==b[k] for k in ("source_path","git_blob_sha","json_pointer","match_kind"))
    assert b["event_id"] is None or b["event_id"] in f["events"]
    assert b["category"]!="UNRESOLVED_REVIEW"
for p in f["chronology"]["observation_and_aviation_candidates"]:
    assert f["events"][p]["kind"] in ("ARCHIVAL_OBSERVATION_CLUSTER","ARCHIVAL_REPORT_UNLOCALIZED","DOCUMENTED_AVIATION_INCIDENT")
pattern=re.compile(g["filter"]["nevada_regex"]+"|"+g["filter"]["arizona_regex"],re.I)
rep=[]
def reject_constant(s):raise ValueError(s)
for e in g["coverage"]["failed_json_parse"]:
    raw=subprocess.check_output(["git","cat-file","blob",e["git_blob_sha"]])
    encoding="utf-16" if raw.startswith((b"\xff\xfe",b"\xfe\xff")) else "utf-8-sig"
    row={"path":e["path"],"git_blob_sha":e["git_blob_sha"],"encoding":encoding,"original_error":e["error"],"bytes":len(raw)}
    try:
        text=raw.decode(encoding)
        hits=[{"offset":x.start(),"term":x.group(),"context":text[max(0,x.start()-100):x.end()+100]} for x in pattern.finditer(text)]
        row["geo_text_hits"]=hits
        try:
            obj=json.loads(text,parse_constant=reject_constant)
            row["status"]="RECOVERED_STRICT_JSON_READ_ONLY"
            row["root_type"]=type(obj).__name__
        except ValueError as ex:
            row["status"]="QUARANTINED_NON_SINGLE_JSON"
            row["strict_parse_error"]=str(ex)
            try:
                obj,end=json.JSONDecoder(parse_constant=reject_constant).raw_decode(text.lstrip())
                tail=text.lstrip()[end:]
                row["first_value_root_type"]=type(obj).__name__
                row["trailing_nonwhitespace_chars"]=len(tail.strip())
                row["trailing_preview"]=tail.strip()[:300]
            except ValueError as ex2:row["first_value_error"]=str(ex2)
    except UnicodeError as ex:
        row["status"]="QUARANTINED_DECODE_FAILURE";row["decode_error"]=str(ex)
    rep.append(row)
write(REPAIR,{"schema":"janus.uap.parse_recovery.v1.0","source_commit":g["coverage"]["source_commit"],"originals_modified":False,"records":rep,"recovered_strict":sum(x["status"]=="RECOVERED_STRICT_JSON_READ_ONLY" for x in rep),"quarantined":sum(x["status"].startswith("QUARANTINED") for x in rep),"geo_text_hit_count":sum(len(x.get("geo_text_hits",[])) for x in rep),"rule":"UTF-16 BOM decode where applicable; strict parse; malformed files quarantined and text screened, never silently truncated."})
# Restrict to explicit topical paths, not broad content keywords or graph-neighbor expansion.
# These are review candidates, NOT a validated scientific dataset.
allow=re.compile(r"^registry/uap/|^data/JANUS-(?:UAP-|PALOMAR-|BLUEBOOK-|ECHO-COUSTEAU-MILITARY-SONAR-UAP|TOPA-ART-BELL-REAL-CALLER-ARCHIVE|TOPA-ADVERSARIAL-FALSIFICATION)|^registry/cosmology/JANUS-(?:UAP-|POSS1-|BLUEBOOK-|JPFM-|NUCLEAR-UAP-)|^data/janus(?:-meta-registry-v(?:10\.0-uap|11\.1-omni-galileo|12\.2-nuclear)|-tectonic-uap|_meta_registry_conus|_meta_registry_global|_nuclear_emulation)|^data/JANUS-NUCLEAR-EMULATION",re.I)
rows=[]
for d in m["inventory"]:
    p=d["path"]
    if allow.search(p) and d.get("verification")=="CONTENT_PARSED_BLOB_MATCH":
        rows.append({k:d[k] for k in ("path","git_blob_sha","group","status","scientific_status","claim_ceiling","verdict","CURRENT_VERDICT") if k in d})
# Explicit reviewed legacy sources, with tags to distinguish claim records from proof.
extra={a["source_path"] for a in f["match_adjudications"] if a["category"] in ("AVIATION_INCIDENT_RECORD","ARCHIVAL_EPISODE_RECORD","CONTEXT_SITE","OUT_OF_REGION_CONTEXT")}
known={x["path"] for x in rows}
for d in m["inventory"]:
    if d["path"] in extra-known and d.get("verification")=="CONTENT_PARSED_BLOB_MATCH":
        rows.append({k:d[k] for k in ("path","git_blob_sha","group","status","scientific_status","claim_ceiling") if k in d})
rows.sort(key=lambda x:x["path"])
assert len(rows)==len({x["path"] for x in rows}) and len(rows)<m["inventory_count"]
for x in rows:
    p=x["path"]
    x["role"]="HISTORICAL_OR_REVIEW_CANDIDATE"
    if "ART-BELL" in p:x["role"]="CLAIM_ARCHIVE_NOT_EVENT_EVIDENCE"
    elif "SHARD-" in p:x["role"]="TECHNICAL_RECEIPT"
    elif "RETRO" in p.upper() or "/uap/" in p:x["role"]="EXPERIMENT_OR_HYPOTHESIS_NOT_PHYSICAL_PROOF"
    elif "AUDIT" in p or "RESULT" in p or "RUN-" in p:x["role"]="RESEARCH_RESULT_REQUIRES_CLAIM_CEILING"
write(CORE,{"schema":"janus.uap.curated_core.v1.0","source_commit":g["coverage"]["source_commit"],"authority_changed":False,"status":"NARROW_EXPLICIT_TOPIC_NAVIGATION__NOT_SCIENTIFIC_ADMISSION","parent_inventory_count":m["inventory_count"],"curated_count":len(rows),"excluded_count":m["inventory_count"]-len(rows),"rules":["Explicit topic allowlist plus geo-reviewed source paths only; no one-hop expansion.","Derivative visualization receipts, incidental lexical matches and unrelated files excluded.","Scientific admission requires independent source-level review; negative results retained."],"scientific_boundaries":m["scientific_boundaries"],"inventory":rows})
r=read(REPAIR);print(json.dumps({"geo_rows":len(f["match_adjudications"]),"categories":f["coverage"]["counts"],"core_count":len(rows),"recovered_strict":r["recovered_strict"],"quarantined":r["quarantined"],"recovery_geo_text_hits":r["geo_text_hit_count"]},sort_keys=True))
