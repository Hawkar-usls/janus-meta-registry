#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import requests

DOC_ID="19720015241"
URL=f"https://ntrs.nasa.gov/api/citations/{DOC_ID}/downloads/{DOC_ID}.txt"
FROZEN_SHA256="28f50ebccea5989f3f926f062068627e3c478d394ffda7cb17a877c9133a2302"
UA="JANUS-JPFM-4A-NTRS-fulltext-capture/1.0 (+source-only; no-outcome-join)"

def sha256(b:bytes)->str:return hashlib.sha256(b).hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--raw-out',type=Path,required=True);ap.add_argument('--receipt-out',type=Path,required=True);a=ap.parse_args()
    r=requests.get(URL,headers={'User-Agent':UA,'Accept':'text/plain,*/*'},timeout=180,allow_redirects=True);r.raise_for_status();raw=r.content
    got=sha256(raw)
    if got!=FROZEN_SHA256:raise RuntimeError(f'NTRS fulltext bytes changed: {got}')
    a.raw_out.parent.mkdir(parents=True,exist_ok=True);a.raw_out.write_bytes(raw)
    receipt={
      'artifact_id':'JANUS-PALOMAR-JPFM-4A-NTRS-19720015241-FULLTEXT-CAPTURE-v1.0',
      'experiment_id':'JPFM-4A','date':dt.date.today().isoformat(),
      'status':'FROZEN_OFFICIAL_NTRS_FULLTEXT_CAPTURED_FOR_SOURCE_PARSER_DEVELOPMENT',
      'source':{'url':URL,'http_status':r.status_code,'content_type':r.headers.get('content-type'),'bytes':len(raw),'sha256':got,'expected_sha256':FROZEN_SHA256},
      'raw_artifact_filename':a.raw_out.name,
      'outcome_blindness':{'bluebook_access':False,'poss1_access':False,'nuclear_calendar_access':False,'association_computed':False},
      'analysis_semantics':'RAW_OFFICIAL_TEXT_CAPTURE_ONLY__NO_ROCKET_ROWS_ADMITTED_BY_THIS_ARTIFACT',
      'current_authority_changed':False,
      'claim_ceiling':'SOURCE_CAPTURE_ONLY__NO_ROCKET_EVENT_OR_ASSOCIATION_CLAIM'
    }
    a.receipt_out.parent.mkdir(parents=True,exist_ok=True);a.receipt_out.write_text(json.dumps(receipt,indent=2,ensure_ascii=False),encoding='utf-8');print(json.dumps(receipt,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
