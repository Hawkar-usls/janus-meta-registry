#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import requests

BASE='https://www.ngdc.noaa.gov/stp/space-weather/solar-data/solar-features/solar-flares/h-alpha/events/documentation/misc/'
DOCS=['f_event.fmt','f_event-group.fmt','flares.txt']
UA='JANUS-JPFM-3B-legacy-event-docs-freezer/1.0'

def h(b:bytes)->str:return hashlib.sha256(b).hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',type=Path,required=True); a=ap.parse_args()
    s=requests.Session(); s.headers['User-Agent']=UA
    rows=[]
    for name in DOCS:
        u=BASE+name
        r=s.get(u,timeout=120); r.raise_for_status(); b=r.content
        text=b.decode('ascii',errors='replace')
        rows.append({'filename':name,'url':u,'sha256':h(b),'bytes':len(b),'lines':len(text.splitlines()),'text':text})
    payload={
      'artifact_id':'JANUS-PALOMAR-JPFM-3B-NOAA-LEGACY-EVENT-DOCUMENTATION-FREEZE-v1.0',
      'status':'SOURCE_DOCUMENTATION_FROZEN__OUTCOME_BLIND',
      'authority':'NOAA/NCEI H-alpha events documentation/misc',
      'documents':rows,
      'combined_ordered_sha256':h(b''.join((x['filename']+'|'+x['sha256']+'\n').encode() for x in rows)),
      'outcome_blindness':{'bluebook_access':False,'poss1_access':False,'nuclear_calendar_access':False,'association_computed':False},
      'claim_ceiling':'FORMAT_DOCUMENTATION_ONLY__NO_EVENT_OR_ASSOCIATION_CLAIM'
    }
    a.out.parent.mkdir(parents=True,exist_ok=True); a.out.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(payload,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
