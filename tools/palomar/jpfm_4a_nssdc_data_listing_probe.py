#!/usr/bin/env python3
from __future__ import annotations

import argparse, datetime as dt, hashlib, json, re
from pathlib import Path
import requests

DOCS={
 '1978':'19790004781',
 '1980':'19810001581',
 '1994':'19950010026'
}
TERMS=['rocket','sounding rocket','rocket file','ROCKET System','non-satellite','data form','magnetic tape','online','near-line','offline','master directory','WDC-A','launch date']
UA='JANUS-JPFM-4A-NSSDC-data-listing-probe/1.0 (+source-only; no-outcome-join)'

def sha(b):return hashlib.sha256(b).hexdigest()
def norm(s):return re.sub(r'\s+',' ',s).strip()
def ctx(lines,term,limit=40,radius=2):
    q=term.lower();out=[]
    for i,line in enumerate(lines):
        if q in line.lower():
            out.append({'line_number_1based':i+1,'lines':[{'n':j+1,'text':norm(lines[j])[:900]} for j in range(max(0,i-radius),min(len(lines),i+radius+1))]})
            if len(out)>=limit:break
    return out

def probe(session,year,doc):
    api=f'https://ntrs.nasa.gov/api/citations/{doc}';r=session.get(api,timeout=180);r.raise_for_status();raw=r.content;p=r.json();downloads=p.get('downloads',[]) if isinstance(p,dict) else []
    txt=None
    for item in downloads if isinstance(downloads,list) else []:
        if isinstance(item,dict) and isinstance(item.get('links'),dict) and item['links'].get('fulltext'):
            txt='https://ntrs.nasa.gov'+item['links']['fulltext'];break
    base={'year_label':year,'document_id':doc,'title':p.get('title') if isinstance(p,dict) else None,'report_numbers':p.get('otherReportNumbers') if isinstance(p,dict) else None,'api_sha256':sha(raw),'api_bytes':len(raw),'fulltext_url':txt}
    if not txt:
        base.update({'status':'FULLTEXT_LINK_NOT_EXPOSED','fulltext':None,'term_contexts':{}});return base
    tr=session.get(txt,timeout=180);tr.raise_for_status();tb=tr.content;text=tb.decode('utf-8',errors='replace');lines=text.splitlines()
    base.update({'status':'FULLTEXT_FROZEN','fulltext':{'http_status':tr.status_code,'bytes':len(tb),'sha256':sha(tb),'line_count':len(lines)},'term_contexts':{t:ctx(lines,t) for t in TERMS}});return base

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();s=requests.Session();s.headers.update({'User-Agent':UA,'Accept':'application/json,text/plain,*/*'})
    docs=[probe(s,y,d) for y,d in DOCS.items()]
    result={'artifact_id':'JANUS-PALOMAR-JPFM-4A-NSSDC-DATA-LISTING-ROCKET-LINEAGE-PROBE-v1.0','experiment_id':'JPFM-4A','date':dt.date.today().isoformat(),'status':'OFFICIAL_NSSDC_DATA_LISTINGS_PROBED_FOR_ROCKET_PRODUCT_LINEAGE__NO_OUTCOME_JOIN','documents':docs,'search_semantics':{'purpose':'Locate any public dataset/master-directory/access-path descendant of the historical NSSDC ROCKET information system or its standard outputs.','terms':TERMS,'absence_rule':'No term hit is evidence only that the frozen extracted text did not contain that literal term; it is not proof that a dataset or historical product never existed.'},'outcome_blindness':{'bluebook_access':False,'poss1_access':False,'nuclear_calendar_access':False,'association_computed':False},'next_gate':'If a rocket product identifier/access path is found, freeze that official descendant before parser work. If no public descendant is found, retain the row-manifest gate and do not fall back to request-only data or OCR proximity guesses.','current_authority_changed':False,'claim_ceiling':'NSSDC_PRODUCT_LINEAGE_SOURCE_SEARCH_ONLY__NO_ROCKET_EVENT_OR_ASSOCIATION_CLAIM'}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
