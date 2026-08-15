#!/usr/bin/env python3
"""JANUS Project Blue Book public exact-date index v0.2.

v0.2 corrective change:
- morphology/disposition screening is performed ONLY on narrative summary text,
  never on the fixed checkbox vocabulary printed on Project 10073 record cards;
- occurrence date prefers the first exact date in the narrative summary, then an
  explicit record-card DATE field;
- the blind case table is written and SHA-256 frozen before the nuclear calendar
  is fetched or joined;
- every admitted convenience-mirror row must carry a NARA NAID.

The mirror is an access layer over public-domain NARA scans/transcriptions, not
an evidentiary replacement for NARA T1206. A later spot-check gate binds a
frozen random sample back to the underlying record cards.
"""
from __future__ import annotations

import argparse, csv, hashlib, io, json, re, urllib.parse, urllib.request, urllib.robotparser
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

RUNNER_ID = "JANUS-BLUEBOOK-PUBLIC-CASE-INDEX-v0.2"
BASE = "https://www.govweird.com"
TOPIC_PREFIX = "/topics/ufo/project-blue-book/"
UA = "JANUS-BlueBook-PublicIndex/0.2 (+research; provenance-preserving)"
ROBOTS_URL = BASE + "/robots.txt"
SITEMAPS = [BASE + "/sitemap.xml", BASE + "/sitemap_index.xml", BASE + "/sitemap-0.xml"]

SIPRI_URL = "https://gist.githubusercontent.com/ZijunXu/2c9d8a8db6420799ed944187100f8aee/raw/sipri-report-explosions.csv"
SIPRI_SHA = "1bdfb18cc41741e6c45c5bdfa3d70d8d0739e08b406c647aa1913ce013ee5b95"
COUNTRIES = {"USA", "USSR", "UK"}
STRICT_TYPES = {"AIRDROP", "TOWER", "SURFACE", "ATMOSPH", "BARGE", "BALLOON", "ROCKET", "SHIP"}
START, END = date(1949, 11, 19), date(1957, 4, 28)

MONTHS = {m: i for i, names in enumerate([
    (), ("jan","january"), ("feb","february"), ("mar","march"), ("apr","april"), ("may",),
    ("jun","june"), ("jul","july"), ("aug","august"), ("sep","sept","september"),
    ("oct","october"), ("nov","november"), ("dec","december")
]) for m in names}
MON = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
NARR_DATE_A = re.compile(rf"\b({MON})\s+(\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+(19\d{{2}})\b", re.I)
NARR_DATE_B = re.compile(rf"\b(\d{{1,2}})\s+({MON})[,]?\s+(19\d{{2}})\b", re.I)
CARD_DATE = re.compile(r"(?:^|\n)\s*(?:1\.\s*)?DATE\s*(?::|\|)?\s*(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{2,4})\b", re.I)
NAID_RE = re.compile(r"(?:Case File\s*)?NARA NAID\s*(\d{6,12})|National Archives Catalog\s*[·:\-]?\s*NAID\s*(\d{6,12})", re.I)
ROLL_RE = re.compile(r"T1206\s*,?\s*Roll\s*(\d{1,3})", re.I)
PAGE_RE = re.compile(r"Page count\s*(\d+)", re.I)

# Narrative-only blind morphology screens.
STARLIKE = [
    re.compile(r"\bstar[- ]?like\b", re.I),
    re.compile(r"\blike (?:a |the )?(?:large |big |bright |very bright )?star\b", re.I),
    re.compile(r"\bresembl(?:ed|ing) (?:a |the )?(?:bright )?star\b", re.I),
    re.compile(r"\bpoint of light\b", re.I),
    re.compile(r"\bpinpoint(?:s)? of light\b", re.I),
    re.compile(r"\bstar[- ]sized\b", re.I),
]
COMPACT_LIGHT = re.compile(r"\b(bright|white|blue|green|red|yellow|orange|amber|luminous|glowing)\s+(?:point|light|lights|object)\b|\bbright light\b", re.I)
FORMATION = re.compile(r"\b(formation|v[- ]formation|rows? of|cluster of|group of|trail formation|diamond formation|box formation)\b", re.I)
RADAR = re.compile(r"\b(radar contact|radar return|radar track|tracked by radar|radar and visual|visual and radar|radar)\b", re.I)
CRAFT = re.compile(r"\b(disc|disk|cigar[- ]shaped|cylinder|cylindrical|triangular|triangle[- ]shaped|saucer|fuselage|wingless craft|craft body)\b", re.I)
ASTRO_EXPL = re.compile(r"\b(?:air force|investigator|evaluation|conclusion|concluded|identified|believed)[^.]{0,100}\b(venus|jupiter|meteor|meteors|fireball|astronomical|star)\b", re.I)
AIRCRAFT_EXPL = re.compile(r"\b(?:air force|investigator|evaluation|conclusion|concluded|identified|believed)[^.]{0,100}\b(aircraft|airplane|jet|contrail)\b", re.I)
BALLOON_EXPL = re.compile(r"\b(?:air force|investigator|evaluation|conclusion|concluded|identified|believed)[^.]{0,100}\b(balloon|balloons)\b", re.I)


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script","style","noscript"}: self.skip += 1
        if tag.lower() in {"p","div","br","li","h1","h2","h3","tr","td","th","section"}: self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag.lower() in {"script","style","noscript"} and self.skip: self.skip -= 1
        if tag.lower() in {"p","div","li","h1","h2","h3","tr","section"}: self.parts.append("\n")
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)
    def text(self):
        s="".join(self.parts).replace("\r","\n")
        s=re.sub(r"[\t ]+"," ",s); s=re.sub(r"\n\s*\n+","\n",s)
        return s.strip()


def fetch(url, timeout=45):
    req=urllib.request.Request(url, headers={"User-Agent":UA,"Accept":"text/html,application/xml,text/xml,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r: return r.read()

def sha(b): return hashlib.sha256(b).hexdigest()
def file_sha(p): return sha(Path(p).read_bytes())
def month(s): return MONTHS.get(s.lower().rstrip(".")[:3]) or MONTHS.get(s.lower().rstrip("."))
def norm_year(y): return 1900+y if y < 100 else y


def robots_and_sitemaps():
    raw=fetch(ROBOTS_URL).decode("utf-8",errors="replace")
    rp=urllib.robotparser.RobotFileParser(); rp.parse(raw.splitlines())
    if not rp.can_fetch(UA, BASE+TOPIC_PREFIX+"probe"):
        raise SystemExit("fail-closed: robots.txt disallows Project Blue Book crawl")
    sms=[ln.split(":",1)[1].strip() for ln in raw.splitlines() if ln.lower().startswith("sitemap:")]
    return raw, list(dict.fromkeys(sms+SITEMAPS))


def sitemap_urls(url, seen, depth=0):
    if url in seen or depth>4: return set()
    seen.add(url)
    try: root=ET.fromstring(fetch(url))
    except Exception: return set()
    name=lambda x:x.split("}")[-1].lower()
    out=set()
    if name(root.tag)=="sitemapindex":
        for e in root.iter():
            if name(e.tag)=="loc" and e.text: out |= sitemap_urls(e.text.strip(),seen,depth+1)
    else:
        for e in root.iter():
            if name(e.tag)=="loc" and e.text:
                u=e.text.strip(); p=urllib.parse.urlparse(u)
                if p.netloc.endswith("govweird.com") and p.path.startswith(TOPIC_PREFIX): out.add(u)
    return out


def extract_summary(text):
    m=re.search(r"(?:^|\n)Summary\s*\n",text,re.I)
    if not m: return ""
    tail=text[m.end():]
    stop=re.search(r"\nReported location\b|\nDate of incident\b|\nOriginal case file scans\b",tail,re.I)
    return (tail[:stop.start()] if stop else tail[:6000]).strip()


def exact_dates(text):
    vals=[]
    for pat,mode in [(NARR_DATE_A,0),(NARR_DATE_B,1)]:
        for m in pat.finditer(text):
            try:
                if mode==0: mo,dy,yr=month(m.group(1)),int(m.group(2)),int(m.group(3))
                else: dy,mo,yr=int(m.group(1)),month(m.group(2)),int(m.group(3))
                if mo: vals.append(date(yr,mo,dy))
            except ValueError: pass
    out=[]
    for d in vals:
        if d not in out: out.append(d)
    return out


def occurrence_date(summary, full):
    ds=exact_dates(summary)
    if ds: return ds[0].isoformat(), "NARRATIVE_FIRST_EXACT_DATE"
    m=CARD_DATE.search(full)
    if m:
        try:
            d=date(norm_year(int(m.group(3))), month(m.group(2)) or 0, int(m.group(1)))
            return d.isoformat(), "RECORD_CARD_DATE"
        except ValueError: pass
    return "", "NO_EXACT_DATE"


def page_disposition(full, summary):
    pre=full.split("Summary",1)[0][-1200:]
    if re.search(r"\bUnidentified\b",pre,re.I): return "UNIDENTIFIED_HEADER"
    if re.search(r"\bInsufficient Data\b",pre,re.I): return "INSUFFICIENT_DATA_HEADER"
    if ASTRO_EXPL.search(summary): return "EXPLAINED_ASTRONOMICAL_NARRATIVE"
    if AIRCRAFT_EXPL.search(summary): return "EXPLAINED_AIRCRAFT_NARRATIVE"
    if BALLOON_EXPL.search(summary): return "EXPLAINED_BALLOON_NARRATIVE"
    return "UNPARSED"


def blind_features(summary, full):
    return {
        "starlike_screen": int(any(p.search(summary) for p in STARLIKE)),
        "compact_light_screen": int(bool(COMPACT_LIGHT.search(summary))),
        "formation_screen": int(bool(FORMATION.search(summary))),
        "radar_screen": int(bool(RADAR.search(summary))),
        "resolved_craftlike_screen": int(bool(CRAFT.search(summary))),
        "disposition_screen": page_disposition(full,summary),
    }

@dataclass
class Row:
    source_url:str; nara_naid:str; title:str; occurrence_date:str; occurrence_date_rule:str
    microfilm_roll:str; page_count:str; starlike_screen:int; compact_light_screen:int
    formation_screen:int; radar_screen:int; resolved_craftlike_screen:int; disposition_screen:str
    summary_sha256:str; summary_chars:int; summary_sample:str; parse_status:str


def parse_case(url):
    try:
        html=fetch(url).decode("utf-8",errors="replace")
        x=HTMLText(); x.feed(html); full=x.text(); summary=extract_summary(full)
        nm=NAID_RE.search(full); naid=(nm.group(1) or nm.group(2)) if nm else ""
        title=""
        mt=re.search(r"Project Blue Book:\s*([^<\n]+)",html,re.I)
        if mt: title=re.sub(r"\s+"," ",mt.group(1)).strip()[:350]
        od,rule=occurrence_date(summary,full)
        rm=ROLL_RE.search(full); pm=PAGE_RE.search(full)
        f=blind_features(summary,full)
        status="OK"
        if not naid: status="REJECT_NO_NARA_NAID"
        elif not summary: status="REJECT_NO_NARRATIVE_SUMMARY"
        elif not od: status="NO_EXACT_DATE"
        return Row(url,naid,title,od,rule,rm.group(1) if rm else "",pm.group(1) if pm else "",
                   f["starlike_screen"],f["compact_light_screen"],f["formation_screen"],f["radar_screen"],
                   f["resolved_craftlike_screen"],f["disposition_screen"],sha(summary.encode()),len(summary),
                   re.sub(r"\s+"," ",summary)[:1600],status)
    except Exception as e:
        return Row(url,"","","","FETCH_ERROR","","",0,0,0,0,0,"UNPARSED","",0,str(e)[:800],"FETCH_ERROR")


def strict_calendar(raw):
    if sha(raw)!=SIPRI_SHA: raise SystemExit("fail-closed: frozen nuclear calendar bytes changed")
    out=set()
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        if (r.get("country") or "").upper().strip() not in COUNTRIES: continue
        if (r.get("type") or "").upper().strip() not in STRICT_TYPES: continue
        s=(r.get("date_long") or "").strip()
        if re.fullmatch(r"\d{8}",s):
            d=datetime.strptime(s,"%Y%m%d").date()
            if START<=d<=END: out.add(d)
    return sorted(out)

def nearest_lag(d, tests):
    t=min(tests,key=lambda x:(abs((d-x).days),x)); return (d-t).days

def write_csv(path, rows, fields):
    with Path(path).open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(rows)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--out-dir",default="work/bluebook_exact")
    ap.add_argument("--workers",type=int,default=8); ap.add_argument("--max-pages",type=int,default=0)
    a=ap.parse_args(); out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)

    robots,sms=robots_and_sitemaps(); (out/"govweird_robots.txt").write_text(robots,encoding="utf-8")
    urls=set(); seen=set()
    for sm in sms: urls |= sitemap_urls(sm,seen)
    urls=sorted(urls)
    if not urls: raise SystemExit("fail-closed: no Blue Book URLs discovered")
    discovered=len(urls)
    if a.max_pages>0: urls=urls[:a.max_pages]
    (out/"discovered_urls.txt").write_text("\n".join(urls)+"\n",encoding="utf-8")
    print(f"[discover] total={discovered} selected={len(urls)}")

    rows=[]
    with ThreadPoolExecutor(max_workers=max(1,min(a.workers,10))) as ex:
        fs={ex.submit(parse_case,u):u for u in urls}
        for i,f in enumerate(as_completed(fs),1):
            rows.append(f.result())
            if i%250==0 or i==len(urls): print(f"[fetch] {i}/{len(urls)}")

    # De-duplicate by NARA NAID before any nuclear information exists.
    by_naid={}; duplicate_naids=Counter()
    rejects=[]
    for r in sorted(rows,key=lambda x:(x.nara_naid or "~",x.source_url)):
        if not r.nara_naid:
            rejects.append(r); continue
        duplicate_naids[r.nara_naid]+=1
        by_naid.setdefault(r.nara_naid,r)
    dedup=list(by_naid.values())+rejects
    dedup.sort(key=lambda r:(r.occurrence_date or "9999",r.nara_naid,r.source_url))

    fields=list(asdict(dedup[0]).keys())
    blind=out/"bluebook_case_index_blind.csv"; write_csv(blind,[asdict(r) for r in dedup],fields)
    blind_hash=file_sha(blind)
    print(f"[blind-freeze] rows={len(dedup)} sha256={blind_hash}")

    # Nuclear join occurs only after blind file bytes are frozen.
    calraw=fetch(SIPRI_URL); tests=strict_calendar(calraw)
    joined=[]
    valid=[]
    for r in dedup:
        d=asdict(r); lag=""
        if r.nara_naid and r.occurrence_date:
            od=date.fromisoformat(r.occurrence_date)
            if START<=od<=END:
                valid.append(r); lag=nearest_lag(od,tests)
        d.update({
            "nearest_strict_nuclear_lag_days":lag,
            "nuclear_day":int(lag==0) if lag!="" else "",
            "nuclear_pm1":int(abs(lag)<=1) if lag!="" else "",
            "nuclear_pm2":int(abs(lag)<=2) if lag!="" else "",
            "nuclear_pm4":int(abs(lag)<=4) if lag!="" else "",
        }); joined.append(d)
    joined_fields=fields+["nearest_strict_nuclear_lag_days","nuclear_day","nuclear_pm1","nuclear_pm2","nuclear_pm4"]
    write_csv(out/"bluebook_case_index_nuclear_joined.csv",joined,joined_fields)

    daily=[]; by_all=Counter(); by_star=Counter(); by_compact=Counter()
    for r in valid:
        od=date.fromisoformat(r.occurrence_date); by_all[od]+=1
        if r.starlike_screen: by_star[od]+=1
        if r.compact_light_screen: by_compact[od]+=1
    cur=START
    while cur<=END:
        lag=nearest_lag(cur,tests)
        daily.append({"date":cur.isoformat(),"case_count":by_all[cur],"starlike_count":by_star[cur],"compact_light_count":by_compact[cur],
                      "nearest_strict_nuclear_lag_days":lag,"nuclear_day":int(lag==0),"nuclear_pm1":int(abs(lag)<=1),
                      "nuclear_pm2":int(abs(lag)<=2),"nuclear_pm4":int(abs(lag)<=4)})
        cur+=timedelta(days=1)
    write_csv(out/"bluebook_daily_counts.csv",daily,list(daily[0].keys()))

    def subset_counts(name,pred):
        ss=[r for r in valid if pred(r)]; l=[nearest_lag(date.fromisoformat(r.occurrence_date),tests) for r in ss]
        return {f"{name}_cases":len(ss),f"{name}_nuclear_day":sum(x==0 for x in l),f"{name}_pm1":sum(abs(x)<=1 for x in l),
                f"{name}_pm4":sum(abs(x)<=4 for x in l),f"{name}_outside_pm4":sum(abs(x)>4 for x in l)}
    counts={};
    for nm,p in [("all",lambda r:True),("starlike",lambda r:r.starlike_screen==1),("compact_light",lambda r:r.compact_light_screen==1),
                 ("formation",lambda r:r.formation_screen==1),("radar",lambda r:r.radar_screen==1),("craftlike",lambda r:r.resolved_craftlike_screen==1)]:
        counts.update(subset_counts(nm,p))

    receipt={
        "runner_id":RUNNER_ID,
        "status":"FULL_PUBLIC_BLIND_CASE_INDEX_READY_FOR_VALIDATION_AND_MATCHED_CONTROL" if a.max_pages==0 else "PILOT_PUBLIC_BLIND_CASE_INDEX_READY",
        "source":{"mirror":BASE,"discovered_bluebook_urls":discovered,"fetched_urls":len(urls),"robots_sha256":sha(robots.encode()),
                  "authority_boundary":"Each retained convenience row requires a NARA NAID; NARA T1206 remains primary provenance."},
        "corrective_change":"v0.2 screens morphology on narrative Summary only; fixed record-card checkbox vocabulary is excluded.",
        "blind_freeze":{"file":blind.name,"sha256":blind_hash,"rows":len(dedup),"nuclear_join_after_freeze":True},
        "parse":{"raw_rows":len(rows),"unique_nara_naids":len(by_naid),"duplicate_naids":sum(v>1 for v in duplicate_naids.values()),
                 "with_exact_date":sum(bool(r.occurrence_date) for r in by_naid.values()),"valid_study_window":len(valid),
                 "status_counts":dict(Counter(r.parse_status for r in dedup)),"date_rule_counts":dict(Counter(r.occurrence_date_rule for r in dedup)),
                 "disposition_counts_in_window":dict(Counter(r.disposition_screen for r in valid))},
        "nuclear_calendar":{"sha256":sha(calraw),"strict_unique_dates":len(tests)},
        "exploratory_case_counts_not_rate_normalized":counts,
        "mandatory_before_inference":[
            "Freeze a deterministic random NARA spot-check sample from the blind-index hash.",
            "Validate occurrence date and phenotype against underlying record-card scans for that sample.",
            "Manual/blind adjudication of STARLIKE candidates and matched negative cases.",
            "Event-cluster deduplication where multiple case files refer to the same mass sighting.",
            "Matched non-nuclear date/permutation analysis controlling year, season and the July-1952 media wave.",
            "Treat daily zero reports as absence from this case archive, not as measured zero person-observation exposure."
        ],
        "claim_ceiling":"EXACT_DATE_PUBLIC_CASE_INDEX_AND_BLIND_MORPHOLOGY_SCREEN_ONLY__NUCLEAR_SPECIFICITY_NOT_ADMITTED"
    }
    (out/"bluebook_public_case_index_receipt.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(receipt,indent=2,ensure_ascii=False))

if __name__=="__main__": main()
