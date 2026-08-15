#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import requests

DOC_ID='19720008279'
API=f'https://ntrs.nasa.gov/api/citations/{DOC_ID}'
UA='JANUS-JPFM-4A-NSSDC-rocket-guide-probe/1.0 (+source-only; no-outcome-join)'
TERMS=[
 'magnetic tape','machine-sensible','rocket information system','rocket information file',
 'Sounding Rocket Launching Report','launching report','standard output','standard outputs',
 'record format','field','character','card','tape','WDC-A','NSSDC','rocket identification',
 'launch date','launch site','serial number','output'
]

def sha256(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def norm(s:str)->str:return re.sub(r'\s+',' ',s).strip()

def contexts(lines:list[str],term:str,limit:int=30,radius:int=2):
    out=[]; needle=term.lower()
    for i,line in enumerate(lines):
        if needle in line.lower():
            lo=max(0,i-radius);hi=min(len(lines),i+radius+1)
            out.append({'line_number_1based':i+1,'lines':[{'n':j+1,'text':norm(lines[j])[:800]} for j in range(lo,hi)]})
            if len(out)>=limit:break
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    s=requests.Session();s.headers.update({'User-Agent':UA,'Accept':'application/json,text/plain,*/*'})
    ar=s.get(API,timeout=180);ar.raise_for_status();api_raw=ar.content;payload=ar.json()
    downloads=payload.get('downloads') if isinstance(payload,dict) else None
    txt_path=None;pdf_path=None
    if isinstance(downloads,list):
        for item in downloads:
            if not isinstance(item,dict):continue
            links=item.get('links') or {}
            if isinstance(links,dict):
                txt_path=txt_path or links.get('fulltext')
                pdf_path=pdf_path or links.get('pdf') or links.get('original')
    txt_url=('https://ntrs.nasa.gov'+txt_path) if txt_path and txt_path.startswith('/') else txt_path
    txt_rec=None; term_contexts={}
    if txt_url:
        tr=s.get(txt_url,timeout=180);tr.raise_for_status();raw=tr.content;text=raw.decode('utf-8',errors='replace');lines=text.splitlines()
        txt_rec={'url':txt_url,'final_url':tr.url,'http_status':tr.status_code,'content_type':tr.headers.get('content-type'),'bytes':len(raw),'sha256':sha256(raw),'line_count':len(lines)}
        term_contexts={term:contexts(lines,term) for term in TERMS}
        status='OFFICIAL_NSSDC_ROCKET_GUIDE_FULLTEXT_FROZEN__FORMAT_CONTEXTS_PROBED__NO_OUTCOME_JOIN'
    else:
        status='OFFICIAL_NSSDC_ROCKET_GUIDE_API_FROZEN__FULLTEXT_LINK_NOT_EXPOSED_FAIL_CLOSED'
    result={
      'artifact_id':'JANUS-PALOMAR-JPFM-4A-NSSDC-INTERNATIONAL-ROCKET-DATA-GUIDE-PROBE-v1.0',
      'experiment_id':'JPFM-4A','date':dt.date.today().isoformat(),'status':status,
      'source':{
        'authority':'NASA/NSSDC via NASA Technical Reports Server','document_id':DOC_ID,
        'title':payload.get('title') if isinstance(payload,dict) else None,
        'report_numbers':payload.get('otherReportNumbers') if isinstance(payload,dict) else None,
        'api_url':API,'api_http_status':ar.status_code,'api_bytes':len(api_raw),'api_sha256':sha256(api_raw),
        'downloads_metadata':downloads,'pdf_link':pdf_path,'fulltext_link':txt_path
      },
      'fulltext_freeze':txt_rec,
      'source_only_term_contexts':term_contexts,
      'interpretation_gate':{
        'allowed':'Identify documented native record/output semantics and public source locators.',
        'forbidden':'No rocket event rows, no no-launch dates, no Blue Book/POSS join, no OCR-derived completeness claim.'
      },
      'outcome_blindness':{'bluebook_access':False,'poss1_access':False,'nuclear_calendar_access':False,'association_computed':False},
      'next_gate':'Use the frozen guide only to identify native file/output structure and official public descendants; do not parse rocket events until a deterministic row source or validated output representation is frozen.',
      'current_authority_changed':False,
      'claim_ceiling':'NSSDC_ROCKET_INFORMATION_SYSTEM_DOCUMENTATION_ONLY__NO_EVENT_OR_ASSOCIATION_CLAIM'
    }
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
