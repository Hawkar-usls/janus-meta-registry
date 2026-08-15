#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import re
from pathlib import Path

import requests

LAUNCH_URL='https://www.planet4589.com/space/gcat/tsv/launch/launch.tsv'
RCAT_URL='https://www.planet4589.com/space/gcat/tsv/cat/rcat.tsv'
INDEX_URL='https://www.planet4589.com/space/gcat/web/launch/index.html'
CAT_INDEX_URL='https://www.planet4589.com/space/gcat/web/cat/index.html'
UA='JANUS-JPFM-4A-GCAT-source-schema-probe/1.0 (+independent-curated-derivative; no-outcome-join)'

def sha256(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def text(b:bytes)->str:return b.decode('utf-8-sig',errors='replace')
def norm(s:str)->str:return re.sub(r'\s+',' ',s).strip()

def fetch(s,url):
    r=s.get(url,timeout=180,allow_redirects=True);r.raise_for_status();return r,r.content

def parse_tsv(raw:bytes):
    lines=text(raw).splitlines()
    candidates=[]
    for i,line in enumerate(lines[:200]):
        if '\t' not in line:continue
        cells=[c.strip() for c in line.split('\t')]
        nonempty=sum(bool(c) for c in cells)
        if len(cells)>=3 and nonempty>=3:
            candidates.append((i,cells))
    if not candidates:raise RuntimeError('No TSV-like header candidate in first 200 lines')
    # Prefer a candidate containing common identifier/date tokens; otherwise max populated cells.
    def score(item):
        _,cells=item; low=' '.join(cells).lower()
        hints=sum(x in low for x in ('launch','date','jcat','tag','vehicle','site','object','name'))
        return (hints,sum(bool(c) for c in cells),-item[0])
    header_index,header=max(candidates,key=score)
    body='\n'.join(lines[header_index:])
    reader=csv.DictReader(io.StringIO(body),delimiter='\t')
    rows=[dict(r) for r in reader]
    # Drop wholly empty rows and comment-like rows after header.
    rows=[r for r in rows if any(str(v or '').strip() for v in r.values())]
    return {
      'line_count':len(lines),'header_line_1based':header_index+1,'header':header,
      'parsed_row_count':len(rows),
      'first_rows':[{k:norm(str(v or ''))[:300] for k,v in r.items()} for r in rows[:3]]
    }

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    s=requests.Session();s.headers.update({'User-Agent':UA,'Accept':'text/tab-separated-values,text/html,*/*'})
    ir,ib=fetch(s,INDEX_URL);cir,cib=fetch(s,CAT_INDEX_URL);lr,lb=fetch(s,LAUNCH_URL);rr,rb=fetch(s,RCAT_URL)
    launch=parse_tsv(lb);rcat=parse_tsv(rb)
    html=text(ib)+' '+text(cib)
    rel=re.findall(r'GCAT\s+Release\s+([0-9.]+)',html,re.I);updates=re.findall(r'Data\s+Update\s+([^<\n|]+)',html,re.I)
    result={
      'artifact_id':'JANUS-PALOMAR-JPFM-4A-GCAT-ROW-SOURCE-SCHEMA-PROBE-v1.0',
      'experiment_id':'JPFM-4A','date':dt.date.today().isoformat(),
      'status':'INDEPENDENT_CURATED_GCAT_ROW_SOURCES_FROZEN__SCHEMA_PROBED__NO_OUTCOME_JOIN',
      'epistemic_role':'INDEPENDENT_CURATED_DERIVATIVE_SOURCE_CANDIDATE__NOT_NASA_AUTHORITY',
      'source_home':{'authority_for_its_own_dataset':'Jonathan C. McDowell / GCAT','index_url':INDEX_URL,'index_sha256':sha256(ib),'catalog_index_url':CAT_INDEX_URL,'catalog_index_sha256':sha256(cib),'release_strings_seen':sorted(set(rel)),'data_update_strings_seen':sorted(set(norm(x) for x in updates))},
      'files':{
        'launch_tsv':{'url':LAUNCH_URL,'http_status':lr.status_code,'content_type':lr.headers.get('content-type'),'bytes':len(lb),'sha256':sha256(lb),**launch},
        'rcat_tsv':{'url':RCAT_URL,'http_status':rr.status_code,'content_type':rr.headers.get('content-type'),'bytes':len(rb),'sha256':sha256(rb),**rcat}
      },
      'population_boundary':{
        'allowed':'Use GCAT only as an independent row-oriented curated derivative and cross-check candidate source.',
        'forbidden':'Do not relabel GCAT as NASA/NSSDC authority or use it to infer that a date absent from the success-selected NASA catalogue was a NASA no-launch day.',
        'admission_before_outcomes':'Cross-validate frozen GCAT rows against pre-existing official JANUS Bumper and NASA biomedical positive-event manifests and freeze study-window inclusion rules before Blue Book/POSS join.'
      },
      'outcome_blindness':{'bluebook_access':False,'poss1_access':False,'nuclear_calendar_access':False,'association_computed':False},
      'current_authority_changed':False,
      'claim_ceiling':'GCAT_SOURCE_BYTES_AND_SCHEMA_ONLY__NO_HUMAN_MADE_ASSOCIATION_CLAIM'
    }
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True),encoding='utf-8');print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
