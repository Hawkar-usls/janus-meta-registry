#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import requests

URL='https://ntrs.nasa.gov/api/citations/19720015241/downloads/19720015241.txt'
SHA='28f50ebccea5989f3f926f062068627e3c478d394ffda7cb17a877c9133a2302'
UA='JANUS-JPFM-4A-NTRS-date-disagreement-probe/1.0 (+source-only; no-outcome-join)'
QUERIES={
 'ALBERT_IV': ['491208','491212','1949 Dec  8','1949 Dec 8','1949 Dec 12','Albert IV','Alb 4','V-2 No. 31'],
 'PATRICIA_MIKE': ['520521','520522','1952 May 21','1952 May 22','Aeromed 3','USAF 26','Patricia','Mike']
}

def sha256(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def clean(s:str)->str:return re.sub(r'\s+',' ',s).strip()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    r=requests.get(URL,headers={'User-Agent':UA,'Accept':'text/plain,*/*'},timeout=180);r.raise_for_status();raw=r.content
    if sha256(raw)!=SHA:raise RuntimeError('Frozen NTRS fulltext bytes changed')
    text=raw.decode('utf-8',errors='replace');lines=text.splitlines();nonempty=[line for line in lines if line.strip()]
    # Three representations: exact raw text, normalized whitespace per line, and a bounded concatenation of nonempty cells.
    norm_lines=[clean(line) for line in lines]
    cell_stream='|'.join(clean(line) for line in nonempty)
    compact_stream=re.sub(r'\s+','', '\n'.join(nonempty))
    findings={}
    for event,terms in QUERIES.items():
        ef={}
        for term in terms:
            raw_hits=[]
            q=term.lower()
            for i,line in enumerate(lines):
                if q in line.lower():
                    lo=max(0,i-8);hi=min(len(lines),i+9)
                    raw_hits.append({'line_number_1based':i+1,'context':[{'n':j+1,'text':clean(lines[j])[:500]} for j in range(lo,hi)]})
                    if len(raw_hits)>=30:break
            variants={
              'raw_line_hits':len(raw_hits),
              'cell_stream_occurrences':cell_stream.lower().count(q),
              'compact_stream_occurrences':compact_stream.lower().count(re.sub(r'\s+','',term.lower()))
            }
            ef[term]={'counts':variants,'raw_contexts':raw_hits}
        findings[event]=ef
    result={
      'artifact_id':'JANUS-PALOMAR-JPFM-4A-NTRS-DISPUTED-LAUNCH-DATE-PROBE-v1.0',
      'experiment_id':'JPFM-4A','date':dt.date.today().isoformat(),
      'status':'FROZEN_NTRS_FULLTEXT_TARGETED_DATE_DISAGREEMENT_PROBE__NO_OUTCOME_JOIN',
      'source':{'url':URL,'sha256':SHA,'bytes':len(raw),'line_count':len(lines)},
      'queries':QUERIES,
      'findings':findings,
      'interpretation_boundary':{
        'allowed':'Report whether disputed date/name tokens occur in the frozen official NTRS text extraction and preserve local source contexts.',
        'not_allowed':'A token occurrence alone does not establish row association in the fragmented wide table. Absence of a token does not prove the event/date is absent from the underlying PDF/native ROCKET file.',
        'crossvalidation_gate_changed':False
      },
      'outcome_blindness':{'bluebook_access':False,'poss1_access':False,'nuclear_calendar_access':False,'association_computed':False},
      'current_authority_changed':False,
      'claim_ceiling':'TARGETED_OFFICIAL_SOURCE_DATE_DISAGREEMENT_PROBE_ONLY__NO_ASSOCIATION_CLAIM'
    }
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
